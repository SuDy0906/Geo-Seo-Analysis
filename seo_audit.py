"""
FXStreet-only Foundation SEO technical audit (offline HTML).

Fetches a single FXStreet URL and returns checks tuned to their Next.js
templates (news JSON-LD, economic calendar client render, hub pages).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from http_session import make_fetch_session

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120 Safari/537.36; "
        "FXStreet-GEO-Layer1-PoC/1.0"
    ),
    "Accept": "text/html,application/xhtml+xml",
}


def attach_default_headers(sess: object) -> None:
    """Merge ``DEFAULT_HEADERS`` onto plain ``requests`` sessions only (not curl_cffi impersonate)."""
    mod = getattr(type(sess), "__module__", "") or ""
    if mod.startswith("curl_cffi"):
        return
    headers = getattr(sess, "headers", None)
    if headers is None or not hasattr(headers, "update"):
        return
    headers.update(DEFAULT_HEADERS)


FINANCE_SCHEMA_HINTS = frozenset(
    {
        "newsarticle",
        "article",
        "webpage",
        "breadcrumblist",
        "organization",
        "person",
        "event",
        "dataset",
        "faqpage",
        "howto",
        "financialproduct",
        "monetaryamount",
        "investmentorsavingsproduct",
    }
)

CURRENCY_PAIR_RE = re.compile(
    r"\b(?:EUR|USD|GBP|JPY|CHF|AUD|CAD|NZD)(?:/|-)(?:EUR|USD|GBP|JPY|CHF|AUD|CAD|NZD)\b",
    re.I,
)

ISO_DATETIME_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})?)?"
)


def _host_ok_for_fxstreet(hostname: str) -> bool:
    h = hostname.lower().rstrip(".")
    return h == "fxstreet.com" or h.endswith(".fxstreet.com")


def validate_fxstreet_url(url: str) -> str | None:
    """Return an error message if URL is not on fxstreet.com, else None."""
    try:
        p = urlparse(url.strip())
    except Exception:
        return "Invalid URL."
    if p.scheme not in ("http", "https"):
        return "Use http or https."
    if not p.netloc:
        return "Missing host."
    if not _host_ok_for_fxstreet(p.hostname or ""):
        return "This PoC audits **fxstreet.com** only."
    return None


def fxstreet_page_family(final_url: str) -> str:
    """Route bucket for FXStreet-specific rules."""
    path = (urlparse(final_url).path or "/").lower().strip("/")
    parts = [x for x in path.split("/") if x]

    if not parts:
        return "homepage"

    if parts[0] == "economic-calendar" or "economic-calendar" in path:
        return "economic_calendar"

    if parts[0] == "news":
        return "news_article" if len(parts) >= 2 else "news_index"

    if parts[0] == "rates-charts":
        return "rates_charts"

    if parts[0] == "currencies":
        return "currencies"

    return "other"


def _visible_fxstreet_author_signal(soup: BeautifulSoup) -> bool:
    if soup.select("a[rel~=author]"):
        return True
    for a in soup.find_all("a", href=True):
        if "/author/" in (a.get("href") or ""):
            return True
    return False


_LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)

# One URL per major FXStreet Layer-1 bucket (deterministic PoC crawl).
FXSTREET_LAYER1_TEMPLATE_URLS: tuple[str, ...] = (
    "https://www.fxstreet.com/",
    "https://www.fxstreet.com/news",
    "https://www.fxstreet.com/economic-calendar",
    "https://www.fxstreet.com/rates-charts/eurusd",
    "https://www.fxstreet.com/currencies/eurusd",
    "https://www.fxstreet.com/markets/commodities/metals/gold",
    "https://www.fxstreet.com/macroeconomics/central-banks/fed",
    "https://www.fxstreet.com/technical-analysis/support-resistance/ichimoku",
)

GOOGLE_NEWS_SITEMAP_URL = "https://www.fxstreet.com/google-sitemap-news.xml"
SITEMAP_ALL_URL = "https://www.fxstreet.com/sitemap-all.xml"


def _dedupe_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in urls:
        u = raw.strip().rstrip("\\")
        if not u or u in seen:
            continue
        if validate_fxstreet_url(u) is None:
            seen.add(u)
            out.append(u)
    return out


def fetch_sample_fxstreet_news_article_url(
    session: requests.Session | None = None,
    timeout: float = 25.0,
) -> str | None:
    """First /news/... URL from the public Google-news sitemap (live sample)."""
    sess = session or make_fetch_session()
    attach_default_headers(sess)
    try:
        resp = sess.get(GOOGLE_NEWS_SITEMAP_URL, timeout=timeout)
        resp.raise_for_status()
    except Exception:
        return None
    for loc in _LOC_RE.findall(resp.text):
        if "/news/" in loc.lower() and re.search(r"/news/[a-z0-9%-]+-[0-9]{10,}", loc, re.I):
            return loc.rstrip("\\")
    return None


def collect_fxstreet_layer1_audit_urls(
    *,
    session: requests.Session | None = None,
    include_template_pages: bool = True,
    include_sample_news_article: bool = True,
    sitemap_extra: int = 0,
    sitemap_seed: str = SITEMAP_ALL_URL,
    max_sitemap_fetches: int = 35,
    timeout: float = 25.0,
) -> list[str]:
    """
    Build an ordered URL list for a multi-page audit.

    * ``FXSTREET_LAYER1_TEMPLATE_URLS`` hits each major template route.
    * Optional live ``/news/...`` slug from ``google-sitemap-news.xml``.
    * ``sitemap_extra`` merges up to N page URLs discovered via ``sitemap-all.xml``
      (nested sitemaps traversed breadth-first until the cap).

    Respect FXStreet crawl policies; PoC stays single-threaded GETs only.
    """
    sess = session or make_fetch_session()
    attach_default_headers(sess)

    ordered: list[str] = []

    if include_template_pages:
        ordered.extend(FXSTREET_LAYER1_TEMPLATE_URLS)

    if include_sample_news_article:
        news = fetch_sample_fxstreet_news_article_url(sess, timeout=timeout)
        if news:
            ordered.append(news)

    if sitemap_extra > 0:
        extra = crawl_fxstreet_sitemap_urls(
            sitemap_seed,
            max_page_urls=sitemap_extra,
            max_sitemap_fetches=max_sitemap_fetches,
            session=sess,
            timeout=timeout,
        )
        ordered.extend(extra)

    return _dedupe_urls(ordered)


def crawl_fxstreet_sitemap_urls(
    seed_sitemap_url: str,
    *,
    max_page_urls: int,
    max_sitemap_fetches: int = 35,
    session: requests.Session | None = None,
    timeout: float = 25.0,
) -> list[str]:
    """
    Collect fxstreet HTML page URLs from sitemap indices (breadth-first).

    Stops once ``max_page_urls`` page URLs have been queued or discovery budget ends.
    """
    if max_page_urls <= 0:
        return []

    sess = session or make_fetch_session()
    attach_default_headers(sess)

    page_urls: list[str] = []
    page_seen: set[str] = set()
    sitemap_queue: list[str] = [seed_sitemap_url.strip()]
    sitemap_seen: set[str] = set()
    fetch_count = 0

    while sitemap_queue and len(page_urls) < max_page_urls and fetch_count < max_sitemap_fetches:
        sm_url = sitemap_queue.pop(0)
        if sm_url in sitemap_seen:
            continue
        sitemap_seen.add(sm_url)

        netloc_ok = urlparse(sm_url).hostname or ""
        if not _host_ok_for_fxstreet(netloc_ok):
            continue

        fetch_count += 1
        try:
            resp = sess.get(sm_url, timeout=timeout)
            resp.raise_for_status()
        except Exception:
            continue

        locs = _LOC_RE.findall(resp.text)

        children = []
        for loc in locs:
            loc = loc.strip().rstrip("\\")
            u = urlparse(loc)
            if not _host_ok_for_fxstreet(u.hostname or ""):
                continue

            lower = loc.lower()
            if lower.endswith(".xml") or lower.endswith(".xml.gz"):
                if loc not in sitemap_seen:
                    children.append(loc)
                continue

            if lower.startswith(("https://www.fxstreet.com", "http://www.fxstreet.com")):
                if loc not in page_seen:
                    page_seen.add(loc)
                    page_urls.append(loc)
                if len(page_urls) >= max_page_urls:
                    break

        if len(page_urls) < max_page_urls:
            sitemap_queue.extend(children)

    return page_urls


@dataclass
class CheckResult:
    id: str
    label: str
    passed: bool
    detail: str
    weight: int
    finance: bool
    priority: str


@dataclass
class AuditReport:
    url: str
    final_url: str
    status_code: int | None
    load_time_seconds: float | None
    error: str | None
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def technical_score(self) -> int:
        tech = [c for c in self.checks if not c.finance]
        return _weighted_score(tech)

    @property
    def finance_score(self) -> int:
        fin = [c for c in self.checks if c.finance]
        return _weighted_score(fin)

    @property
    def overall_score(self) -> int:
        return _weighted_score(self.checks)

    def fix_priorities(self) -> list[dict[str, Any]]:
        failed = [c for c in self.checks if not c.passed]
        failed.sort(
            key=lambda c: (
                0 if c.finance else 1,
                0 if c.priority == "high" else 1 if c.priority == "medium" else 2,
                -c.weight,
            )
        )
        return [
            {
                "check_id": c.id,
                "label": c.label,
                "detail": c.detail,
                "finance_context": c.finance,
                "priority": c.priority,
            }
            for c in failed
        ]


def _weighted_score(checks: list[CheckResult]) -> int:
    if not checks:
        return 0
    earned = sum(c.weight for c in checks if c.passed)
    maximum = sum(c.weight for c in checks)
    if maximum <= 0:
        return 0
    return round(100 * earned / maximum)


def _parse_json_ld_blocks(soup: BeautifulSoup) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def is_ld_json(t: Any) -> bool:
        return bool(t and "ld+json" in str(t).lower())

    for script in soup.find_all("script", type=is_ld_json):
        raw = (script.string or script.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    out.append(item)
        elif isinstance(data, dict):
            out.append(data)
    return out


def _schema_types(json_ld: list[dict[str, Any]]) -> set[str]:
    types: set[str] = set()

    def add_type(node: Any) -> None:
        if isinstance(node, dict):
            t = node.get("@type")
            if isinstance(t, str):
                types.add(t.lower())
            elif isinstance(t, list):
                for x in t:
                    if isinstance(x, str):
                        types.add(x.lower())
            for v in node.values():
                add_type(v)
        elif isinstance(node, list):
            for x in node:
                add_type(x)

    for block in json_ld:
        add_type(block)
    return types


def _collect_schema_text(json_ld: list[dict[str, Any]], max_depth: int = 8) -> str:
    parts: list[str] = []

    def walk(node: Any, depth: int) -> None:
        if depth > max_depth:
            return
        if isinstance(node, str):
            parts.append(node)
        elif isinstance(node, dict):
            for k, v in node.items():
                if k == "@context":
                    continue
                walk(v, depth + 1)
        elif isinstance(node, list):
            for x in node:
                walk(x, depth + 1)

    for block in json_ld:
        walk(block, 0)
    return " ".join(parts)


def _header_ci(headers: dict[str, str], name: str) -> str:
    ln = name.lower()
    for k, v in headers.items():
        if str(k).lower() == ln:
            return str(v or "")
    return ""


def run_fxstreet_seo_audit(
    url: str,
    timeout: float = 20.0,
    session: requests.Session | None = None,
    *,
    prefetched_html: str | None = None,
    prefetched_final_url: str | None = None,
    prefetched_status_code: int | None = None,
    prefetched_load_seconds: float | None = None,
    prefetched_headers: dict[str, str] | None = None,
) -> AuditReport:
    sess = session or make_fetch_session()
    attach_default_headers(sess)

    report = AuditReport(
        url=url.strip(),
        final_url=url.strip(),
        status_code=None,
        load_time_seconds=None,
        error=None,
        checks=[],
    )

    pre_err = validate_fxstreet_url(report.url)
    if pre_err:
        report.error = pre_err
        return report

    hdrs: dict[str, str] = {}
    html_payload: str

    if prefetched_html is not None:
        report.final_url = (prefetched_final_url or report.url).strip()
        report.status_code = prefetched_status_code if prefetched_status_code is not None else 200
        report.load_time_seconds = prefetched_load_seconds
        html_payload = prefetched_html
        if prefetched_headers:
            hdrs = {str(k): str(v) for k, v in prefetched_headers.items()}
        ctype = "text/html"
        final_host = urlparse(report.final_url).hostname or ""
        if not _host_ok_for_fxstreet(final_host):
            report.error = "Cached URL host is outside **fxstreet.com**."
            return report
    else:
        try:
            resp = sess.get(report.url, timeout=timeout, allow_redirects=True)
        except Exception as e:
            report.error = str(e)
            return report

        report.status_code = resp.status_code
        report.final_url = resp.url
        report.load_time_seconds = resp.elapsed.total_seconds()
        hdrs = {str(k): str(v) for k, v in resp.headers.items()}

        final_host = urlparse(report.final_url).hostname or ""
        if not _host_ok_for_fxstreet(final_host):
            report.error = "Redirect resolved outside **fxstreet.com**; aborting."
            return report

        if resp.status_code >= 400:
            report.error = f"HTTP {resp.status_code}"
            return report

        ctype = (resp.headers.get("Content-Type") or "").lower()
        if "html" not in ctype and "xml" not in ctype:
            report.error = f"Non-HTML response: {ctype or 'unknown type'}"
            return report

        html_payload = resp.text

    soup = BeautifulSoup(html_payload, "html.parser")
    json_ld = _parse_json_ld_blocks(soup)
    schema_types_set = _schema_types(json_ld)
    schema_text = _collect_schema_text(json_ld)
    body_text = soup.get_text(" ", strip=True)[:8000]

    family = fxstreet_page_family(report.final_url)

    checks: list[CheckResult] = []

    title_tag = soup.title
    title_text = title_tag.get_text(strip=True) if title_tag else ""
    t_ok = bool(title_text)
    checks.append(
        CheckResult(
            id="title",
            label="Document title",
            passed=t_ok,
            detail=title_text[:120] if t_ok else "Missing <title>.",
            weight=8,
            finance=False,
            priority="high",
        )
    )
    t_len_ok = 15 <= len(title_text) <= 70
    checks.append(
        CheckResult(
            id="title_length",
            label="Title length (approx. SERP)",
            passed=t_len_ok,
            detail=f"Length {len(title_text)} chars (guideline ~15-70).",
            weight=4,
            finance=False,
            priority="medium",
        )
    )

    meta_desc = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    desc_content = (meta_desc.get("content") or "").strip() if meta_desc else ""
    d_ok = bool(desc_content)
    dc = desc_content
    if len(dc) > 160 and d_ok:
        desc_detail = dc[:160] + "..."
    else:
        desc_detail = dc if d_ok else "Missing meta description."
    checks.append(
        CheckResult(
            id="meta_description",
            label="Meta description",
            passed=d_ok,
            detail=desc_detail,
            weight=8,
            finance=False,
            priority="high",
        )
    )
    d_len_ok = (not d_ok) or (70 <= len(desc_content) <= 180)
    checks.append(
        CheckResult(
            id="meta_description_length",
            label="Meta description length (guideline)",
            passed=d_len_ok,
            detail=f"Length {len(desc_content)} chars (guideline ~70-180).",
            weight=3,
            finance=False,
            priority="low",
        )
    )

    canonical = soup.find("link", rel=lambda x: x and "canonical" in str(x).lower())
    canon_href = (canonical.get("href") or "").strip() if canonical else ""
    c_ok = bool(canon_href)
    checks.append(
        CheckResult(
            id="canonical",
            label="Canonical URL",
            passed=c_ok,
            detail=canon_href if c_ok else "No link[rel=canonical].",
            weight=7,
            finance=False,
            priority="high",
        )
    )
    canon_parsed = urlparse(canon_href) if canon_href else None
    canon_https = bool(canon_parsed and canon_parsed.scheme == "https")
    canon_host_ok = bool(canon_parsed and _host_ok_for_fxstreet(canon_parsed.hostname or ""))
    checks.append(
        CheckResult(
            id="canonical_https_fxstreet",
            label="Canonical uses https and fxstreet host",
            passed=(not c_ok) or (canon_https and canon_host_ok),
            detail=canon_href if c_ok else "Skipped (no canonical URL).",
            weight=5,
            finance=False,
            priority="medium",
        )
    )
    final_norm = report.final_url.rstrip("/").lower()
    canon_norm = canon_href.rstrip("/").lower() if canon_href else ""
    checks.append(
        CheckResult(
            id="canonical_self_reference",
            label="Canonical self-reference (or intentional variant)",
            passed=(not c_ok) or (canon_norm == final_norm),
            detail=(
                "Canonical matches final URL."
                if (c_ok and canon_norm == final_norm)
                else "Canonical differs from final URL; validate intent."
            ),
            weight=3,
            finance=False,
            priority="low",
        )
    )

    h1_tags = soup.find_all("h1")
    h1_ok = len(h1_tags) == 1
    h1_detail = f"Found {len(h1_tags)} <h1> elements."
    if h1_tags:
        snippet = h1_tags[0].get_text(strip=True)[:80]
        h1_detail += " Text: " + snippet + "..."

    checks.append(
        CheckResult(
            id="h1_single",
            label="Single H1",
            passed=h1_ok,
            detail=h1_detail,
            weight=6,
            finance=False,
            priority="high",
        )
    )

    viewports = soup.find_all(
        "meta", attrs={"name": lambda n: n is not None and str(n).lower() == "viewport"}
    )
    vp_ok = len(viewports) <= 1
    checks.append(
        CheckResult(
            id="fxstreet_single_viewport_meta",
            label="FXStreet: single viewport meta (PoC hygiene)",
            passed=vp_ok,
            detail=(
                f"{len(viewports)} meta name=viewport — prefer one."
                if not vp_ok
                else "One viewport meta."
            ),
            weight=2,
            finance=False,
            priority="low",
        )
    )

    robots = soup.find("meta", attrs={"name": re.compile(r"^robots$", re.I)})
    robots_content = (robots.get("content") or "").lower() if robots else ""
    noindex = "noindex" in robots_content
    x_robots = _header_ci(hdrs, "X-Robots-Tag").lower()
    header_noindex = "noindex" in x_robots
    checks.append(
        CheckResult(
            id="robots_indexable",
            label="Not noindex (when unintentional)",
            passed=not (noindex or header_noindex),
            detail=(
                f"meta: {robots_content or 'none'} | x-robots-tag: {x_robots or 'none'}"
            ),
            weight=8,
            finance=False,
            priority="high",
        )
    )

    og_title = soup.find("meta", property="og:title")
    og_ok = og_title is not None and bool((og_title.get("content") or "").strip())
    checks.append(
        CheckResult(
            id="og_title",
            label="Open Graph title",
            passed=og_ok,
            detail="Helps consistent previews when links are shared.",
            weight=3,
            finance=False,
            priority="low",
        )
    )
    og_desc = soup.find("meta", property="og:description")
    og_desc_ok = og_desc is not None and bool((og_desc.get("content") or "").strip())
    checks.append(
        CheckResult(
            id="og_description",
            label="Open Graph description",
            passed=og_desc_ok,
            detail="Helps social snippets preserve article context.",
            weight=2,
            finance=False,
            priority="low",
        )
    )
    tw_card = soup.find("meta", attrs={"name": re.compile(r"^twitter:card$", re.I)})
    tw_ok = tw_card is not None and bool((tw_card.get("content") or "").strip())
    checks.append(
        CheckResult(
            id="twitter_card",
            label="Twitter/X card tag",
            passed=tw_ok,
            detail="Improves rich previews when URLs are shared.",
            weight=2,
            finance=False,
            priority="low",
        )
    )

    lt = report.load_time_seconds or 0.0
    load_ok = report.load_time_seconds is not None and report.load_time_seconds < 5.0
    checks.append(
        CheckResult(
            id="ttfb_proxy",
            label="Response time (<5s, PoC proxy)",
            passed=load_ok,
            detail=f"Elapsed {lt:.2f}s (single request, not full LCP).",
            weight=4,
            finance=False,
            priority="medium",
        )
    )
    imgs = soup.find_all("img")
    if imgs:
        alt_ok = sum(1 for img in imgs if (img.get("alt") or "").strip())
        alt_ratio = alt_ok / len(imgs)
        checks.append(
            CheckResult(
                id="img_alt_coverage",
                label="Image alt coverage",
                passed=alt_ratio >= 0.8,
                detail=f"{alt_ok}/{len(imgs)} images have non-empty alt text.",
                weight=3,
                finance=False,
                priority="medium",
            )
        )

    a_tags = soup.find_all("a", href=True)
    bad_href = 0
    for a in a_tags:
        href = (a.get("href") or "").strip().lower()
        if not href or href in ("#", "javascript:void(0)", "javascript:;"):
            bad_href += 1
    if a_tags:
        bad_ratio = bad_href / len(a_tags)
        checks.append(
            CheckResult(
                id="link_hygiene",
                label="Link hygiene (avoid empty/js-only hrefs)",
                passed=bad_ratio <= 0.1,
                detail=f"{bad_href}/{len(a_tags)} links are placeholder/js-only.",
                weight=3,
                finance=False,
                priority="low",
            )
        )

    has_json_ld = len(json_ld) > 0
    checks.append(
        CheckResult(
            id="json_ld_present",
            label="Structured data (JSON-LD)",
            passed=has_json_ld,
            detail=(
                f"{len(json_ld)} JSON-LD block(s)."
                if has_json_ld
                else "No application/ld+json blocks found."
            ),
            weight=10,
            finance=True,
            priority="high",
        )
    )

    finance_type_hits = schema_types_set & FINANCE_SCHEMA_HINTS
    fk_detail = (
        ", ".join(sorted(finance_type_hits))
        if finance_type_hits
        else (", ".join(sorted(schema_types_set)) if schema_types_set else "No known types.")
    )
    fk_ok = len(finance_type_hits) > 0
    checks.append(
        CheckResult(
            id="schema_finance_relevant",
            label="Finance-relevant schema types",
            passed=fk_ok,
            detail=fk_detail,
            weight=8,
            finance=True,
            priority="high",
        )
    )

    dp = soup.find(attrs={"property": re.compile(r"article:published_time", re.I)})
    dto_el = soup.find("time", attrs={"datetime": True})
    schema_dates = ISO_DATETIME_RE.findall(schema_text)
    has_pub = dp is not None or bool(schema_dates)
    fres_ok = has_pub or dto_el is not None
    checks.append(
        CheckResult(
            id="machine_readable_dates",
            label="Machine-readable publish/update signals",
            passed=fres_ok,
            detail=(
                "article:published_time, <time datetime>, or ISO dates in JSON-LD."
                if fres_ok
                else "Add visible dates with <time datetime> and/or Article dates in JSON-LD."
            ),
            weight=9,
            finance=True,
            priority="high",
        )
    )

    author_link = soup.find("a", rel=lambda x: x and "author" in str(x).lower())
    author_meta = soup.find("meta", attrs={"name": re.compile(r"author", re.I)})
    schema_has_person = "person" in schema_types_set or "organization" in schema_types_set
    auth_ok = author_link is not None or author_meta is not None or schema_has_person
    checks.append(
        CheckResult(
            id="author_entity",
            label="Author / entity signals (for authority)",
            passed=auth_ok,
            detail=(
                "rel=author, meta author, or Person/Organization in JSON-LD."
                if auth_ok
                else "Name the analyst or entity in markup (Person + Organization)."
            ),
            weight=7,
            finance=True,
            priority="high",
        )
    )

    if family == "news_article":
        has_newsarticle = "newsarticle" in schema_types_set
        checks.append(
            CheckResult(
                id="fxstreet_newsarticle_schema",
                label="FXStreet news: NewsArticle in JSON-LD",
                passed=has_newsarticle,
                detail=(
                    "@type NewsArticle present."
                    if has_newsarticle
                    else "Editorial URLs should emit NewsArticle structured data."
                ),
                weight=10,
                finance=True,
                priority="high",
            )
        )

        og_type_el = soup.find("meta", attrs={"property": "og:type"})
        og_type_val = (og_type_el.get("content") or "").strip().lower() if og_type_el else ""
        og_article_ok = og_type_val == "article"
        checks.append(
            CheckResult(
                id="fxstreet_og_type_article",
                label="FXStreet news: og:type is article",
                passed=og_article_ok,
                detail=og_type_val or "Missing og:type.",
                weight=6,
                finance=True,
                priority="high",
            )
        )

        vis_auth = _visible_fxstreet_author_signal(soup)
        checks.append(
            CheckResult(
                id="fxstreet_visible_author_link",
                label="FXStreet news: visible author link (beyond JSON-LD)",
                passed=vis_auth,
                detail=(
                    "Found rel=author or /author/ link in HTML."
                    if vis_auth
                    else "Add a visible author/byline linking to /author/... for humans + parsers."
                ),
                weight=5,
                finance=True,
                priority="medium",
            )
        )

    if family == "economic_calendar":
        checks.append(
            CheckResult(
                id="calendar_structure",
                label="FXStreet economic calendar (single-GET PoC)",
                passed=True,
                detail=(
                    "Calendar grid renders client-side (Next.js). "
                    "No <table> in raw HTML does not imply failure — verify events in-browser or via product APIs."
                ),
                weight=6,
                finance=True,
                priority="medium",
            )
        )
    else:
        path_l = urlparse(report.final_url).path.lower()
        calendar_url = "calendar" in path_l or "economic" in path_l
        table_count = len(soup.find_all("table"))
        event_schema = "event" in schema_types_set
        cal_ok = (not calendar_url) or table_count >= 1 or event_schema
        checks.append(
            CheckResult(
                id="calendar_structure",
                label="Calendar-style page structure (when URL suggests calendar)",
                passed=cal_ok,
                detail=(
                    "URL suggests calendar/economic page; tables or Event schema aid parsing."
                    if calendar_url
                    else "Not a calendar/economic URL — informational pass."
                ),
                weight=6,
                finance=True,
                priority="medium",
            )
        )

    skip_instruments = family in ("homepage", "news_index")
    pairs_in_markup = bool(CURRENCY_PAIR_RE.search(body_text + " " + schema_text))
    inst_ok = True if skip_instruments else pairs_in_markup
    inst_detail = (
        "Skipped — FXStreet hub/listing URL (instruments not expected in summary HTML)."
        if skip_instruments
        else (
            "Explicit pairs (e.g. EUR/USD) in text/schema."
            if pairs_in_markup
            else "Add explicit pair/instrument cues for AI citation."
        )
    )
    checks.append(
        CheckResult(
            id="instrument_specificity",
            label="Instrument specificity (FXStreet context)",
            passed=inst_ok,
            detail=inst_detail,
            weight=6,
            finance=True,
            priority="medium",
        )
    )

    report.checks = checks
    return report


def run_finance_seo_audit(
    url: str,
    timeout: float = 20.0,
    session: requests.Session | None = None,
) -> AuditReport:
    """Backward-compatible alias: FXStreet-only Layer 1 audit."""
    return run_fxstreet_seo_audit(url, timeout=timeout, session=session)
