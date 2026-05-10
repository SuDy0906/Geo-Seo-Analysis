"""
Discover FXStreet editorial URLs (news + analysis) from public sitemaps.

Respect robots.txt / site terms; PoC uses GETs only and optional caps.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import requests

from seo_audit import (
    DEFAULT_HEADERS,
    SITEMAP_ALL_URL,
    _LOC_RE,
    crawl_fxstreet_sitemap_urls,
    validate_fxstreet_url,
)

# Official sitemaps that list recent news & analysis stories.
FXSTREET_ARTICLE_SITEMAP_URLS: tuple[str, ...] = (
    "https://www.fxstreet.com/google-sitemap-news.xml",
    "https://www.fxstreet.com/sitemap-news.xml",
    "https://www.fxstreet.com/google-sitemap-analysis.xml",
    "https://www.fxstreet.com/sitemap-analysis.xml",
)


def _fetch_locs(sess: requests.Session, sitemap_url: str, timeout: float) -> list[str]:
    try:
        resp = sess.get(sitemap_url.strip(), timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException:
        return []
    return [x.strip().rstrip("\\") for x in _LOC_RE.findall(resp.text)]


def is_fxstreet_article_url(url: str, *, strict: bool = True) -> bool:
    """
    Heuristic: standalone `/news/...` or `/analysis/...` story URLs (slugged), not section roots.

    **strict** (default): FXStreet sitemap-style slug with a long numeric story id suffix
    (``-\\d{10,}$``). Use for sitemap discovery so hub pages stay out.

    **relaxed**: short numeric suffix (6+ digits), or a long hyphenated slug without requiring
    the 10-digit tail — catches more live URLs while still skipping feeds and trivial paths.
    """
    if validate_fxstreet_url(url):
        return False
    path = (urlparse(url).path or "").lower()
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        return False
    if parts[0] not in ("news", "analysis"):
        return False
    slug = parts[-1]
    if slug in ("feed", "rss", "page"):
        return False

    if strict:
        if len(slug) < 12:
            return False
        return bool(re.search(r"-\d{10,}$", slug))

    if len(slug) < 6:
        return False
    if re.search(r"-\d{6,}$", slug):
        return True
    # Editorial slugs often look like keyword-keyword-topic without a numeric id.
    return bool(len(slug) >= 14 and "-" in slug)


def is_fxstreet_news_analysis_path_url(url: str) -> bool:
    """
    Inclusive rule: anything under `/news/` or `/analysis/` with a real path segment,
    excluding feeds, sitemap stubs, and simple ``.../page/N`` pagination.
    Use when pulling **all** cached editorial URLs regardless of slug shape.
    """
    if validate_fxstreet_url(url):
        return False
    path = (urlparse(url).path or "").lower()
    if "/news/" not in path and "/analysis/" not in path:
        return False
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        return False
    if parts[0] not in ("news", "analysis"):
        return False
    slug = parts[-1]
    if slug in ("feed", "rss", "sitemap"):
        return False
    if len(parts) >= 2 and parts[-2] == "page" and slug.isdigit():
        return False
    return True


def discover_fxstreet_article_urls(
    *,
    session: requests.Session | None = None,
    merge_sitemap_all: bool = True,
    sitemap_all_max_pages: int = 30_000,
    sitemap_all_max_fetches: int = 400,
    timeout: float = 35.0,
) -> list[str]:
    """
    Union of:

    1. URLs from **news + analysis** sitemaps (deduped).
    2. Optionally, URLs from **`sitemap-all.xml`** that pass :func:`is_fxstreet_article_url`
       (captures anything the global sitemap lists as a story-shaped path).

    Caps on (2) avoid unbounded network work; raise ``sitemap_all_max_pages`` if you need wider coverage.
    """
    sess = session or requests.Session()
    sess.headers.update(DEFAULT_HEADERS)

    found: set[str] = set()

    for sm in FXSTREET_ARTICLE_SITEMAP_URLS:
        for loc in _fetch_locs(sess, sm, timeout):
            if is_fxstreet_article_url(loc):
                found.add(loc.split("#", 1)[0])

    if merge_sitemap_all and sitemap_all_max_pages > 0:
        scanned = crawl_fxstreet_sitemap_urls(
            SITEMAP_ALL_URL,
            max_page_urls=sitemap_all_max_pages,
            max_sitemap_fetches=sitemap_all_max_fetches,
            session=sess,
            timeout=timeout,
        )
        for loc in scanned:
            if is_fxstreet_article_url(loc):
                found.add(loc.split("#", 1)[0])

    return sorted(found)
