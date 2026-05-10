"""
Discover URL lists for full-site scrape (FXStreet public sitemaps only).
"""

from __future__ import annotations

from typing import Literal

import requests

from article_discovery import discover_fxstreet_article_urls
from seo_audit import SITEMAP_ALL_URL, crawl_fxstreet_sitemap_urls

ScrapeMode = Literal["full_site", "articles"]


def discover_urls_for_scrape(
    mode: ScrapeMode,
    *,
    session: requests.Session | None = None,
    max_sitemap_pages: int = 25_000,
    max_sitemap_fetches: int = 500,
    merge_article_sitemaps_into_full: bool = True,
    timeout: float = 35.0,
) -> list[str]:
    """
    ``full_site`` — HTML URLs collected from ``sitemap-all.xml`` (capped crawl).

    ``articles`` — editorial story URLs (`/news/`, `/analysis/`) via
    ``article_discovery`` (includes optional sitemap-all merge).

    When ``merge_article_sitemaps_into_full`` is True and mode is ``full_site``,
    URLs from dedicated news/analysis sitemaps are unioned so new stories not
    yet in ``sitemap-all`` pass are included.
    """
    sess = session or requests.Session()

    if mode == "articles":
        return discover_fxstreet_article_urls(
            session=sess,
            merge_sitemap_all=True,
            sitemap_all_max_pages=max_sitemap_pages,
            sitemap_all_max_fetches=max_sitemap_fetches,
            timeout=timeout,
        )

    pages = crawl_fxstreet_sitemap_urls(
        SITEMAP_ALL_URL,
        max_page_urls=max_sitemap_pages,
        max_sitemap_fetches=max_sitemap_fetches,
        session=sess,
        timeout=timeout,
    )

    out: set[str] = set(pages)

    if merge_article_sitemaps_into_full:
        arts = discover_fxstreet_article_urls(
            session=sess,
            merge_sitemap_all=False,
            timeout=timeout,
        )
        out.update(arts)

    return sorted(out)
