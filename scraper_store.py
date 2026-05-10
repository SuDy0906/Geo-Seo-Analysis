"""
Persistent HTML cache: SQLite index + gzipped bodies per site origin.

Legacy FXStreet data stays under ``data/fxstreet_scrape/``. Other origins use
``data/site_scrape/<host>/``.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Literal
from urllib.parse import urlparse

from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent


def _stripped_dom_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(" ", strip=True)


def extract_html_text_for_index(html: str) -> str:
    """
    Text for SQLite ``text_extract``: prefer trafilatura (main content), but on hub /
    listing pages trafilatura often drops large visible regions versus the DOM, so fall
    back to stripped HTML text when extraction is thin or wildly shorter than DOM.
    """
    import trafilatura

    raw_tf = (
        trafilatura.extract(html, include_comments=False, include_tables=True, favor_recall=True)
        or ""
    )
    tf_s = raw_tf.strip()
    dom_s = _stripped_dom_text(html).strip()
    if len(tf_s) < 120:
        return dom_s
    # Listing / mosaic pages: TF can return a compact slice while `<body>` holds far more copy.
    if len(dom_s) > len(tf_s) + 2500 and len(tf_s) < 2000:
        return dom_s
    return raw_tf.strip()


def _normalize_origin_input(main: str) -> str:
    s = main.strip()
    if not s:
        return "https://www.fxstreet.com/"
    if not s.startswith(("http://", "https://")):
        s = "https://" + s
    return s


def canonical_root(hostname: str) -> str:
    h = (hostname or "").strip().lower()
    if h.startswith("www."):
        h = h[4:]
    return h


@dataclass(frozen=True)
class SiteStore:
    """Storage root for one crawl origin."""

    seed_url: str
    hostname: str
    data_dir: Path

    @property
    def canonical_root_host(self) -> str:
        return canonical_root(self.hostname)

    @property
    def is_fxstreet(self) -> bool:
        return self.canonical_root_host == "fxstreet.com" or self.canonical_root_host.endswith(".fxstreet.com")

    def body_rel_fragment(self, url: str) -> str:
        rel = self.data_dir.relative_to(PROJECT_ROOT / "data")
        return str(Path("data") / rel / "html" / f"{_url_hash(url)}.html.gz")


def hostname_allowed_for_store(hostname: str, store: SiteStore) -> bool:
    hn = canonical_root(hostname)
    root = store.canonical_root_host
    if hn == root:
        return True
    if hn == f"www.{root}":
        return True
    if hn.endswith("." + root) and root.count(".") >= 1:
        return True
    return False


def site_store_from_main_url(main_url: str) -> SiteStore:
    """Map user \"main URL\" to on-disk bucket. FXStreet retains ``data/fxstreet_scrape/``."""
    raw = _normalize_origin_input(main_url)
    p = urlparse(raw)
    host = (p.hostname or "").lower() or "fxstreet.com"
    root = canonical_root(host)

    if root.endswith("fxstreet.com"):
        data_dir = PROJECT_ROOT / "data" / "fxstreet_scrape"
    else:
        safe = re.sub(r"[^a-z0-9._-]+", "_", root.replace(".", "_")) or "unknown_host"
        data_dir = PROJECT_ROOT / "data" / "site_scrape" / safe

    origin = f"{p.scheme or 'https'}://{p.netloc}/"
    return SiteStore(seed_url=origin, hostname=host, data_dir=data_dir.resolve())


DEFAULT_STORE = site_store_from_main_url("https://www.fxstreet.com/")


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()


def _pick_headers(headers: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in headers.items():
        lk = k.lower()
        if lk in ("x-robots-tag", "content-type"):
            out[k] = v
    return out


class _ConnCtx:
    def __init__(self, store: SiteStore) -> None:
        store.data_dir.mkdir(parents=True, exist_ok=True)
        (store.data_dir / "html").mkdir(parents=True, exist_ok=True)
        self._cx = sqlite3.connect(store.data_dir / "index.sqlite", timeout=60)

    def __enter__(self) -> sqlite3.Connection:
        self._cx.row_factory = sqlite3.Row
        return self._cx

    def __exit__(self, *a: object) -> None:
        self._cx.close()


def init_store(store: SiteStore | None = None) -> SiteStore:
    store = store or DEFAULT_STORE
    store.data_dir.mkdir(parents=True, exist_ok=True)
    (store.data_dir / "html").mkdir(parents=True, exist_ok=True)
    with _ConnCtx(store) as cx:
        cx.execute(
            """
            CREATE TABLE IF NOT EXISTS pages (
                url TEXT PRIMARY KEY,
                final_url TEXT NOT NULL,
                status_code INTEGER,
                content_type TEXT,
                fetched_at TEXT NOT NULL,
                error TEXT,
                body_rel TEXT,
                text_extract TEXT,
                headers_json TEXT
            )
            """
        )
        cx.execute("CREATE INDEX IF NOT EXISTS idx_pages_status ON pages (status_code)")
        cx.execute(
            """
            CREATE TABLE IF NOT EXISTS articles (
                url TEXT PRIMARY KEY,
                discovered_at TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT ''
            )
            """
        )
        cx.execute(
            "CREATE INDEX IF NOT EXISTS idx_articles_discovered ON articles (discovered_at)"
        )
        cx.commit()
    return store


def register_article_urls(
    store: SiteStore | None,
    urls: Iterable[str],
    *,
    source: str = "article_scraper",
) -> int:
    """
    Register editorial/article URLs separately from arbitrary ``pages`` rows.

    Idempotent per URL (keeps earliest ``discovered_at``).
    Returns number of newly inserted URLs.
    """
    store = init_store(store)
    now = datetime.now(timezone.utc).isoformat()
    src = (source or "").strip()[:240]
    by_url: dict[str, tuple[str, str, str]] = {}
    for u in urls:
        s = (u or "").strip()
        if s.startswith("http") and s not in by_url:
            by_url[s] = (s, now, src)
    tuples = list(by_url.values())
    if not tuples:
        return 0
    with _ConnCtx(store) as cx:
        before = int(cx.execute("SELECT COUNT(*) FROM articles").fetchone()[0])
        for batch_start in range(0, len(tuples), 500):
            batch = tuples[batch_start : batch_start + 500]
            cx.executemany(
                """
                INSERT OR IGNORE INTO articles (url, discovered_at, source)
                VALUES (?, ?, ?)
                """,
                batch,
            )
        cx.commit()
        after = int(cx.execute("SELECT COUNT(*) FROM articles").fetchone()[0])
    return max(0, after - before)


def backfill_articles_from_cached_pages(
    store: SiteStore | None = None,
    *,
    source: str = "backfill_pages_news_analysis",
) -> int:
    """
    Pull ``/news/`` and ``/analysis/`` URLs from existing ``pages`` rows into ``articles``.

    Does not download anything; useful after upgrading an older cache.
    """
    store = init_store(store)
    now = datetime.now(timezone.utc).isoformat()
    with _ConnCtx(store) as cx:
        before = int(cx.execute("SELECT COUNT(*) FROM articles").fetchone()[0])
        cx.execute(
            """
            INSERT OR IGNORE INTO articles (url, discovered_at, source)
            SELECT url, ?, ?
            FROM pages
            WHERE (
              instr(lower(url), '/news/') > 0 OR instr(lower(url), '/analysis/') > 0
            )
            """,
            (now, source[:240]),
        )
        cx.commit()
        after = int(cx.execute("SELECT COUNT(*) FROM articles").fetchone()[0])
    return max(0, after - before)


def _article_registry_count(store: SiteStore) -> int:
    with _ConnCtx(store) as cx:
        n = cx.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    return int(n)


def list_article_urls_with_snapshot(
    limit: int = 50_000,
    *,
    store: SiteStore | None = None,
) -> list[str]:
    """URLs registered in ``articles`` that currently have OK HTML in ``pages``."""
    store = init_store(store)
    with _ConnCtx(store) as cx:
        rows = cx.execute(
            """
            SELECT p.url FROM articles a
            INNER JOIN pages p ON p.url = a.url
            WHERE p.status_code = 200
              AND (p.error IS NULL OR p.error = '')
              AND IFNULL(p.body_rel, '') != ''
            ORDER BY p.fetched_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [r[0] for r in rows]


def save_page(
    url: str,
    *,
    store: SiteStore,
    final_url: str,
    status_code: int | None,
    content_type: str | None,
    error: str | None,
    html: str | None,
    headers: dict[str, str] | None,
    text_extract: str | None = None,
) -> None:
    init_store(store)
    now = datetime.now(timezone.utc).isoformat()
    err_s = (error or "").strip()
    ok_save = bool(html and status_code == 200 and not err_s)
    rel = store.body_rel_fragment(url.strip())
    path = PROJECT_ROOT / rel
    body_rel_db = ""
    if not ok_save and path.is_file():
        try:
            path.unlink()
        except OSError:
            pass
    if ok_save:
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as gz:
            gz.write(html or "")
        body_rel_db = rel
    hj = json.dumps(_pick_headers(headers or {})) if headers else None
    with _ConnCtx(store) as cx:
        cx.execute(
            """
            INSERT INTO pages (url, final_url, status_code, content_type, fetched_at, error, body_rel, text_extract, headers_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
              final_url=excluded.final_url,
              status_code=excluded.status_code,
              content_type=excluded.content_type,
              fetched_at=excluded.fetched_at,
              error=excluded.error,
              body_rel=excluded.body_rel,
              text_extract=excluded.text_extract,
              headers_json=excluded.headers_json
            """,
            (
                url.strip(),
                final_url.strip(),
                status_code,
                content_type or "",
                now,
                error or "",
                body_rel_db or "",
                (text_extract or "")[:120_000],
                hj or "",
            ),
        )
        cx.commit()


def get_record(url: str, *, store: SiteStore | None = None) -> dict | None:
    store = init_store(store)
    with _ConnCtx(store) as cx:
        row = cx.execute("SELECT * FROM pages WHERE url = ?", (url.strip(),)).fetchone()
    return dict(row) if row else None


def load_html_body(body_rel: str) -> str | None:
    if not body_rel:
        return None
    path = PROJECT_ROOT / body_rel
    if not path.is_file():
        return None
    with gzip.open(path, "rt", encoding="utf-8") as gz:
        return gz.read()


def get_cached_snapshot(
    url: str, *, store: SiteStore | None = None
) -> tuple[str, str, int, dict[str, str]] | None:
    store = store or DEFAULT_STORE
    init_store(store)
    rec = get_record(url, store=store)
    if not rec:
        return None
    if rec.get("status_code") != 200 or (rec.get("error") or "").strip():
        return None
    rel_raw = rec.get("body_rel") or ""
    html = load_html_body(rel_raw)
    if not html:
        return None
    hj = rec.get("headers_json") or "{}"
    try:
        headers = json.loads(hj)
        if not isinstance(headers, dict):
            headers = {}
        headers = {str(k): str(v) for k, v in headers.items()}
    except json.JSONDecodeError:
        headers = {}
    return html, str(rec["final_url"]), int(rec["status_code"]), headers


def store_stats(store: SiteStore | None = None) -> dict[str, int]:
    store = init_store(store)
    with _ConnCtx(store) as cx:
        total = cx.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        ok = cx.execute(
            """
            SELECT COUNT(*) FROM pages
            WHERE status_code = 200
              AND (error IS NULL OR error = '')
              AND IFNULL(body_rel, '') != ''
            """
        ).fetchone()[0]
        art = cx.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        art_ok = cx.execute(
            """
            SELECT COUNT(*) FROM articles a
            INNER JOIN pages p ON p.url = a.url
            WHERE p.status_code = 200
              AND (p.error IS NULL OR p.error = '')
              AND IFNULL(p.body_rel, '') != ''
            """
        ).fetchone()[0]
    return {
        "rows": int(total),
        "ok_bodies": int(ok),
        "article_registry": int(art),
        "article_with_html": int(art_ok),
    }


def list_cached_urls(limit: int = 50_000, *, store: SiteStore | None = None) -> list[str]:
    store = init_store(store)
    with _ConnCtx(store) as cx:
        rows = cx.execute(
            """
            SELECT url FROM pages
            WHERE status_code = 200 AND (error IS NULL OR error = '') AND body_rel != ''
            ORDER BY fetched_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [r[0] for r in rows]


def list_cached_ok_urls(
    limit: int = 10_000,
    *,
    store: SiteStore | None = None,
    article_stories_only: bool = False,
    article_match: Literal["path", "relaxed", "strict"] = "path",
    path_contains: str = "",
) -> list[str]:
    """
    Paths with usable HTML snapshots.

    For non-FX stores, optionally filter URLs with ``path_contains`` (substring match, lowercased).

    FX ``article_stories_only``:

    - If the ``articles`` registry has any rows, lists **only** registered article URLs that
      also have OK HTML in ``pages`` (preferred).
    - Otherwise falls back to path heuristics on ``pages`` and applies ``article_match``.

    Non-FX: if ``article_stories_only`` and the registry is non-empty, uses the same JOIN;
    else ``path_contains`` on ``pages`` only.
    """
    store = init_store(store)
    needle = (path_contains or "").strip().lower()

    use_join = article_stories_only and _article_registry_count(store) > 0

    if use_join:
        fetch_cap = min(max(limit * 25, 8_000), 100_000)
        with _ConnCtx(store) as cx:
            join_sql = """
            SELECT p.url FROM articles a
            INNER JOIN pages p ON p.url = a.url
            WHERE p.status_code = 200
              AND (p.error IS NULL OR p.error = '')
              AND IFNULL(p.body_rel, '') != ''
            """
            qvals2: list = []
            if needle:
                join_sql += " AND instr(lower(p.url), ?) > 0 "
                qvals2.append(needle)
            join_sql += " ORDER BY p.fetched_at DESC LIMIT ?"
            qvals2.append(fetch_cap)
            rows = cx.execute(join_sql, tuple(qvals2)).fetchall()
        urls = [r[0] for r in rows]
        if article_stories_only and store.is_fxstreet:
            from article_discovery import (
                is_fxstreet_article_url,
                is_fxstreet_news_analysis_path_url,
            )

            filt: Callable[[str], bool]
            if article_match == "strict":
                filt = lambda u: is_fxstreet_article_url(u, strict=True)
            elif article_match == "relaxed":
                filt = lambda u: is_fxstreet_article_url(u, strict=False)
            else:
                filt = is_fxstreet_news_analysis_path_url

            urls = [u for u in urls if filt(u)][:limit]
        else:
            urls = urls[:limit]
        return urls

    fetch_cap = limit
    if article_stories_only and store.is_fxstreet:
        fetch_cap = min(max(limit * 25, 8_000), 100_000)

    wheres = [
        "status_code = 200",
        "(error IS NULL OR error = '')",
        "IFNULL(body_rel, '') != ''",
    ]
    qvals: list = []

    if article_stories_only and store.is_fxstreet:
        wheres.append("(instr(lower(url), '/news/') > 0 OR instr(lower(url), '/analysis/') > 0)")
    if needle:
        wheres.append("instr(lower(url), ?) > 0")
        qvals.append(needle)

    qvals.append(fetch_cap)
    where_sql = " AND ".join(wheres)

    with _ConnCtx(store) as cx:
        rows = cx.execute(
            f"""
            SELECT url FROM pages
            WHERE {where_sql}
            ORDER BY fetched_at DESC
            LIMIT ?
            """,
            tuple(qvals),
        ).fetchall()

    urls = [r[0] for r in rows]
    if article_stories_only and store.is_fxstreet:
        from article_discovery import (
            is_fxstreet_article_url,
            is_fxstreet_news_analysis_path_url,
        )

        filt_fn: Callable[[str], bool]
        if article_match == "strict":
            filt_fn = lambda u: is_fxstreet_article_url(u, strict=True)
        elif article_match == "relaxed":
            filt_fn = lambda u: is_fxstreet_article_url(u, strict=False)
        else:
            filt_fn = is_fxstreet_news_analysis_path_url

        urls = [u for u in urls if filt_fn(u)][:limit]
    else:
        urls = urls[:limit]

    return urls


def clear_store(store: SiteStore | None = None) -> None:
    store = store or DEFAULT_STORE
    init_store(store)
    with _ConnCtx(store) as cx:
        cx.execute("DELETE FROM articles")
        cx.execute("DELETE FROM pages")
        cx.commit()
    html_dir = store.data_dir / "html"
    if html_dir.is_dir():
        for p in html_dir.glob("*.html.gz"):
            try:
                p.unlink()
            except OSError:
                pass


@dataclass
class FetchResult:
    url: str
    final_url: str
    status_code: int | None
    error: str | None
    html: str | None
    skipped: bool = False


def fetch_and_store_url(
    url: str,
    *,
    store: SiteStore,
    session,
    timeout: float = 25.0,
    skip_if_ok: bool = False,
    index_as_article: bool = False,
) -> FetchResult:
    import requests

    from seo_audit import DEFAULT_HEADERS, validate_fxstreet_url, _host_ok_for_fxstreet

    init_store(store)

    if store.is_fxstreet:
        verr = validate_fxstreet_url(url)
        if verr:
            save_page(
                url,
                store=store,
                final_url=url.strip(),
                status_code=None,
                content_type=None,
                error=verr,
                html=None,
                headers=None,
            )
            return FetchResult(url, url, None, verr, None, skipped=False)
    else:
        pu = urlparse(url.strip())
        if not pu.scheme.startswith("http") or not pu.hostname:
            err = "Invalid URL"
            save_page(
                url,
                store=store,
                final_url=url.strip(),
                status_code=None,
                content_type=None,
                error=err,
                html=None,
                headers=None,
            )
            return FetchResult(url, url, None, err, None, skipped=False)
        if not hostname_allowed_for_store(pu.hostname, store):
            err = "URL host does not match selected site origin"
            save_page(
                url,
                store=store,
                final_url=url.strip(),
                status_code=None,
                content_type=None,
                error=err,
                html=None,
                headers=None,
            )
            return FetchResult(url, url, None, err, None, skipped=False)

    if skip_if_ok:
        snap = get_cached_snapshot(url, store=store)
        if snap:
            if index_as_article:
                register_article_urls(store, [url], source="article_scraper_skip")
            return FetchResult(url, snap[1], 200, None, snap[0], skipped=True)

    session.headers.update(DEFAULT_HEADERS)
    try:
        resp = session.get(url.strip(), timeout=timeout, allow_redirects=True)
    except requests.RequestException as e:
        save_page(
            url,
            store=store,
            final_url=url.strip(),
            status_code=None,
            content_type=None,
            error=str(e),
            html=None,
            headers=None,
        )
        return FetchResult(url, url.strip(), None, str(e), None, skipped=False)

    final = resp.url
    fin_host = urlparse(final).hostname or ""

    if store.is_fxstreet:
        if not _host_ok_for_fxstreet(fin_host):
            err = "Redirect left fxstreet.com"
            save_page(
                url,
                store=store,
                final_url=final,
                status_code=resp.status_code,
                content_type=resp.headers.get("Content-Type"),
                error=err,
                html=None,
                headers=dict(resp.headers),
            )
            return FetchResult(url, final, resp.status_code, err, None, skipped=False)
    else:
        if not hostname_allowed_for_store(fin_host, store):
            err = "Redirect left allowed host for this site"
            save_page(
                url,
                store=store,
                final_url=final,
                status_code=resp.status_code,
                content_type=resp.headers.get("Content-Type"),
                error=err,
                html=None,
                headers=dict(resp.headers),
            )
            return FetchResult(url, final, resp.status_code, err, None, skipped=False)

    ctype = (resp.headers.get("Content-Type") or "").lower()
    html = resp.text if "html" in ctype else None
    err: str | None = None
    if resp.status_code >= 400:
        err = f"HTTP {resp.status_code}"
    elif html is None:
        err = f"Non-HTML: {ctype or 'unknown'}"

    text_ex: str | None = None
    if html and not err:
        try:
            text_ex = extract_html_text_for_index(html)
        except Exception:
            text_ex = ""

    save_page(
        url,
        store=store,
        final_url=final,
        status_code=resp.status_code,
        content_type=resp.headers.get("Content-Type"),
        error=err,
        html=html if not err else None,
        headers=dict(resp.headers),
        text_extract=text_ex,
    )
    if index_as_article:
        register_article_urls(store, [url], source="article_scraper_fetch")

    return FetchResult(
        url,
        final,
        resp.status_code,
        err,
        html if not err else None,
        skipped=False,
    )
