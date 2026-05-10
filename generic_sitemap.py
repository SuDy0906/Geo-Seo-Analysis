"""
Generic breadth-first sitemap crawl for arbitrary hosts (paired with SiteStore hostname rules).
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import requests

from http_session import make_fetch_session
from seo_audit import attach_default_headers
from scraper_store import SiteStore, hostname_allowed_for_store

_LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)


def crawl_sitemap_urls(
    seed_sitemap_url: str,
    *,
    store: SiteStore,
    max_page_urls: int,
    max_sitemap_fetches: int = 120,
    session: requests.Session | None = None,
    timeout: float = 40.0,
) -> list[str]:
    """Collect HTML page URLs from a sitemap index (same traversal idea as FXStreet crawler)."""
    if max_page_urls <= 0:
        return []

    sess = session or make_fetch_session()
    attach_default_headers(sess)

    page_urls: list[str] = []
    page_seen: set[str] = set()
    sm_queue: list[str] = [seed_sitemap_url.strip()]
    sm_seen: set[str] = set()
    fetch_count = 0

    while sm_queue and len(page_urls) < max_page_urls and fetch_count < max_sitemap_fetches:
        sm_url = sm_queue.pop(0)
        if sm_url in sm_seen:
            continue
        sm_seen.add(sm_url)

        if not hostname_allowed_for_store(urlparse(sm_url).hostname or "", store):
            continue

        fetch_count += 1
        try:
            resp = sess.get(sm_url, timeout=timeout)
            resp.raise_for_status()
        except Exception:
            continue

        locs = _LOC_RE.findall(resp.text)
        children: list[str] = []
        for loc in locs:
            loc = loc.strip().rstrip("\\")
            pu = urlparse(loc)
            if not hostname_allowed_for_store(pu.hostname or "", store):
                continue

            lower = loc.lower()
            if lower.endswith(".xml") or lower.endswith(".xml.gz"):
                if loc not in sm_seen:
                    children.append(loc)
                continue

            if loc not in page_seen:
                page_seen.add(loc)
                page_urls.append(loc)
            if len(page_urls) >= max_page_urls:
                break

        if len(page_urls) < max_page_urls:
            sm_queue.extend(children)

    return page_urls
