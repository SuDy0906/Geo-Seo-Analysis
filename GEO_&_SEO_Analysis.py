"""
FXStreet GEO · SEO Intelligence — launcher.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="GEO · SEO Intelligence",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("GEO · SEO Intelligence")
st.markdown(
    "Curate HTML once, analyze forever: batch scores and dashboards read from your local crawl cache—no repeated live fetching for the studios.\n\n"
    "- **Foundation SEO** · Per-URL headline and pillar scores, checklist pass/fail, and archetype-aware views—the picture of technical and on-page readiness for rankings and rich results.\n"
    "- **Citation readiness** · A structured “will this excerpt well?” lens: density of facts, readability, quotes, scannability, and exports you can prioritize for rewriting.\n"
    "- **Performance link** · Rows where Foundation and readiness metrics match the **same** URL (after redirects), plus correlation heatmaps and joint plots—seeing whether stronger SEO systematically tracks with GEO-style suitability.\n"
    "- **Sitemap crawler** · Turn sitemap inventories into downloaded pages in your store—coverage stats, retries, and a growing archive for every studio run downstream.\n"
    "- **Article index** · A focused roster of editorial URLs separate from arbitrary pages: register lists, tune fetch depth for analysis, and keep news/analysis coverage distinct from bulk site crawling."
)
st.success(
    "FXStreet installs default to **`data/fxstreet_scrape/`**. Other origins silently land "
    "under **`data/site_scrape/<hostname>/`** so experiments never collide."
)
