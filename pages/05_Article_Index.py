"""
Editorial URL registry plus HTML archiving for cite-ready cohorts.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fxstreet_scraper import discover_urls_for_scrape  # noqa: E402
from generic_sitemap import crawl_sitemap_urls  # noqa: E402
from scraper_store import (  # noqa: E402
    backfill_articles_from_cached_pages,
    clear_store,
    fetch_and_store_url,
    init_store,
    register_article_urls,
    site_store_from_main_url,
    store_stats,
)

FX_ARTICLE_MAX_SITEMAP_PAGES = 80_000
FX_ARTICLE_MAX_SITEMAP_FETCHES = 900
GEN_MAX_PAGE_URLS = 100_000
GEN_MAX_SITEMAP_FETCHES = 500
FETCH_PAUSE_SEC = 0.2
MAX_NETWORK_GETS_PER_RUN = 100_000

st.set_page_config(page_title="Article index", page_icon="📰", layout="wide")
st.title("Article index")
st.caption(
    "Maintains an explicit article registry beside raw HTML blobs so citation readiness queues stay curated."
)

origin = st.text_input(
    "Site origin",
    value="https://www.fxstreet.com/",
    help="Anchors filesystem layout for whichever host you are indexing.",
    key="article_scraper_origin",
)
store = site_store_from_main_url(origin)
init_store(store)

if st.session_state.get("_article_scraper_host") != store.canonical_root_host:
    st.session_state["article_scraper_queue"] = []
st.session_state["_article_scraper_host"] = store.canonical_root_host

stats = store_stats(store)
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Hostname", store.canonical_root_host)
m2.metric("Indexed rows", stats["rows"])
m3.metric("Pages with bodies", stats["ok_bodies"])
m4.metric("Article registry rows", stats["article_registry"])
m5.metric("Articles with HTML", stats["article_with_html"])

sess = requests.Session()
pause = FETCH_PAUSE_SEC
skip_ok = True

if store.is_fxstreet:
    st.caption(
        f"FXStreet editorial merge walks news and analysis sitemaps up to **{FX_ARTICLE_MAX_SITEMAP_PAGES:,}** "
        f"discoveries and **{FX_ARTICLE_MAX_SITEMAP_FETCHES:,}** XML windows."
    )
    if st.button("Discover full editorial catalog", key="as_fx_disc"):
        with st.spinner("Parsing FXStreet editorial sitemaps…"):
            urls = discover_urls_for_scrape(
                "articles",
                session=sess,
                max_sitemap_pages=FX_ARTICLE_MAX_SITEMAP_PAGES,
                max_sitemap_fetches=FX_ARTICLE_MAX_SITEMAP_FETCHES,
                timeout=40.0,
            )
        st.session_state["article_scraper_queue"] = urls
        added = register_article_urls(store, urls, source="article_scraper_discover_fx")
        st.success(f"Queued **{len(urls)}** URLs · registered **{added}** new article rows.")
else:
    st.caption(
        f"Generic hosts enumerate up to **{GEN_MAX_PAGE_URLS:,}** URLs or **{GEN_MAX_SITEMAP_FETCHES:,}** fetches "
        "from the declared sitemap."
    )
    sm = st.text_input("Sitemap root", value=urljoin(store.seed_url, "sitemap.xml"), key="as_gen_sm")

    if st.button("Discover editorial queue", key="as_gen_disc"):
        with st.spinner("Harvesting URLs…"):
            urls = crawl_sitemap_urls(
                sm,
                store=store,
                max_page_urls=GEN_MAX_PAGE_URLS,
                max_sitemap_fetches=GEN_MAX_SITEMAP_FETCHES,
                session=sess,
                timeout=40.0,
            )
        st.session_state["article_scraper_queue"] = urls
        added = register_article_urls(store, urls, source="article_scraper_discover_generic")
        st.success(f"Queued **{len(urls)}** URLs · registered **{added}** new article rows.")

urls = st.session_state.get("article_scraper_queue") or []

if urls:
    fetch_budget = min(MAX_NETWORK_GETS_PER_RUN, len(urls))
    st.write(
        f"{len(urls)} URLs queued · up to **{fetch_budget}** fresh captures (reuse cached 200 bodies automatically)."
    )

    if st.button("Persist HTML snapshots", type="primary", key="as_fetch"):
        prog = st.progress(0)
        status = st.empty()
        net = 0
        last_err: list[dict[str, object]] = []
        for i, u in enumerate(urls):
            if net >= fetch_budget:
                break
            status.caption(f"Archiving {i + 1} of {len(urls)} URLs")
            fr = fetch_and_store_url(
                u,
                store=store,
                session=sess,
                timeout=28.0,
                skip_if_ok=skip_ok,
                index_as_article=True,
            )
            if fr.skipped:
                prog.progress(min(1.0, (i + 1) / max(len(urls), 1)))
                continue
            net += 1
            if fr.error or (fr.status_code or 499) >= 400:
                last_err.append(
                    {"destination": u[:512], "http_status": fr.status_code, "message": (fr.error or "")[:280]}
                )
            prog.progress(min(1.0, net / max(fetch_budget, 1)))
            if pause > 0:
                time.sleep(pause)
        prog.empty()
        status.empty()
        st.session_state["article_scraper_last_errors"] = last_err[:500]
        st.success("Archive sweep complete.")
        st.rerun()

errs = st.session_state.get("article_scraper_last_errors") or []
if errs:
    st.subheader("Archive exceptions")
    st.dataframe(
        pd.DataFrame(errs).rename(
            columns={"destination": "URL", "http_status": "HTTP status", "message": "Message"}
        ),
        use_container_width=True,
        height=180,
        hide_index=True,
    )

with st.expander("Import historical pages into registry", expanded=False):
    st.markdown(
        "Use when classic `/news/` or `/analysis/` snapshots exist without matching registry rows. "
        "Operation is instantaneous and avoids outbound calls."
    )
    if st.button("Sync editorial paths from disk", key="as_backfill"):
        n = backfill_articles_from_cached_pages(store)
        st.success(f"Linked **{n}** additional article records.")
        st.rerun()

with st.expander("Clear local workspace", expanded=False):
    if st.button("Remove HTML for this hostname", key="as_wipe"):
        clear_store(store)
        st.session_state.pop("article_scraper_queue", None)
        st.success("Article workspace reset.")
        st.rerun()

st.divider()
st.markdown(
    f"**Artifacts ·** `{store.data_dir.relative_to(ROOT)}`. "
    "Pair with **Citation readiness studio** once bodies exist — scoring never revisits origin servers."
)
