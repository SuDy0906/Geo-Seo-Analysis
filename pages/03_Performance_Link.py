"""
Unified view of Foundation SEO scores versus GEO-style readiness proxies.
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis_plots import (  # noqa: E402
    correlation_heatmap_figure,
    seo_geo_bucketed_bar_figure,
    seo_vs_geo_scatter_figure,
)
from product_ui import gap_after_chart, render_chart_insight  # noqa: E402
from scraper_store import site_store_from_main_url, store_stats as scrape_store_stats  # noqa: E402


def _join_key(raw: str) -> str:
    u = (raw or "").strip()
    if not u:
        return ""
    p = urlparse(u if "://" in u else f"https://{u}")
    host = (p.netloc or "").lower().split("@")[-1]
    path = (p.path or "").rstrip("/")
    return f"{host}{path or ''}"


def _merged_seo_geo(seo_df: pd.DataFrame, geo_df: pd.DataFrame) -> pd.DataFrame:
    if seo_df.empty or geo_df.empty:
        return pd.DataFrame()

    s = seo_df.loc[seo_df["error"].fillna("") == ""].copy()
    if "url" not in s.columns:
        return pd.DataFrame()
    s["_k"] = s["url"].astype(str).map(_join_key)
    s["seo_overall"] = pd.to_numeric(s.get("overall"), errors="coerce").clip(0, 100)
    s["seo_technical"] = pd.to_numeric(s.get("technical"), errors="coerce").clip(0, 100)
    s["seo_finance"] = pd.to_numeric(s.get("finance"), errors="coerce").clip(0, 100)
    s = s[s["_k"].astype(bool) & s["seo_overall"].notna()]

    g = geo_df.loc[geo_df["error"].fillna("") == ""].copy()
    if "citeability_total" not in g.columns:
        return pd.DataFrame()

    def _row_key(r: pd.Series) -> str:
        return _join_key(str(r.get("final_url") or r.get("url") or ""))

    g["_k"] = g.apply(_row_key, axis=1)
    g["geo_total"] = pd.to_numeric(g["citeability_total"], errors="coerce").clip(0, 100)
    g = g[g["_k"].astype(bool) & g["geo_total"].notna()]
    geo_cols = ["_k", "geo_total"]
    fu = "final_url"
    if fu in g.columns:
        g["url_geo"] = g[fu].fillna(g.get("url", "")).astype(str)
    else:
        g["url_geo"] = g.get("url", pd.Series(dtype=str)).astype(str)
    geo_cols.append("url_geo")
    if "word_count" in g.columns:
        g["geo_words"] = pd.to_numeric(g["word_count"], errors="coerce")
        geo_cols.append("geo_words")

    s = s.drop_duplicates(subset=["_k"], keep="first")
    g = g.drop_duplicates(subset=["_k"], keep="first")

    left_cols = ["_k", "seo_overall", "seo_technical", "seo_finance", "url"]
    left_cols = [c for c in left_cols if c in s.columns]
    m = s[left_cols].merge(g[geo_cols], on="_k", how="inner").drop(columns=["_k"], errors="ignore")
    m["url_display"] = m["url_geo"].where(m["url_geo"].astype(str).str.len() > 0, m.get("url", ""))
    return m


DISPLAY_MERGED_PRETTY: dict[str, str] = {
    "url": "Matched URL · foundation",
    "url_geo": "Matched URL · readiness",
    "url_display": "Display URL",
    "seo_overall": "Foundation headline",
    "seo_technical": "Technical pillar",
    "seo_finance": "Market pillar",
    "geo_total": "GEO readiness index",
    "geo_words": "Word count",
}


st.set_page_config(page_title="Performance link", page_icon="🔗", layout="wide")
st.title("Performance link · SEO meets GEO readiness")
st.caption(
    "Joins headline Foundation scores with citation‑readiness proxies (GEO) for the exact same snapshots. "
    "Matches use host plus path keys so redirected URLs remain aligned across exports."
)

main = st.sidebar.text_input(
    "Site origin",
    value="https://www.fxstreet.com/",
    key="corr_origin",
)
store = site_store_from_main_url(main)
ss = scrape_store_stats(store)
st.sidebar.metric("Cached HTML pages", ss["ok_bodies"])
st.sidebar.caption(f"Active host: **{store.canonical_root_host}**")

source = st.radio(
    "Data source",
    options=["session", "csv"],
    format_func=lambda x: "Studio session snapshots" if x == "session" else "Two CSV uploads",
    horizontal=True,
    key="corr_src",
)

seo_df: pd.DataFrame | None = None
geo_df: pd.DataFrame | None = None

if source == "session":
    l1 = st.session_state.get("l1_cache_summary")
    l2 = st.session_state.get("l2_bulk_df")
    if l1:
        seo_df = pd.DataFrame(l1)
    if isinstance(l2, pd.DataFrame) and not l2.empty:
        geo_df = l2
    if seo_df is None or geo_df is None:
        st.warning(
            "Run both the **Foundation** and **Citation readiness** batches during this login session "
            "or upload CSV backups."
        )
else:
    c1, c2 = st.columns(2)
    with c1:
        f1 = st.file_uploader("Foundation batch CSV", type=["csv"], key="corr_csv_l1")
    with c2:
        f2 = st.file_uploader("Readiness batch CSV", type=["csv"], key="corr_csv_l2")
    if f1 is not None:
        seo_df = pd.read_csv(f1)
    if f2 is not None:
        geo_df = pd.read_csv(f2)
    if f1 is None or f2 is None:
        st.info("Exports come from **Export CSV** on each studio page.")

merged = (
    _merged_seo_geo(seo_df, geo_df)
    if seo_df is not None and geo_df is not None and not seo_df.empty and not geo_df.empty
    else pd.DataFrame()
)

if not merged.empty:
    n = len(merged)
    st.success(f"Aligned dataset · **{n}** overlapping URLs.")

    c1, c2, c3 = st.columns(3)
    if n >= 2:
        pr = float(merged["seo_overall"].corr(merged["geo_total"], method="pearson"))
        sp = float(merged["seo_overall"].corr(merged["geo_total"], method="spearman"))
    else:
        pr = float("nan")
        sp = float("nan")
    c1.metric("Linear association (Pearson r)", f"{pr:.3f}" if pr == pr else "—")
    c2.metric("Rank association (Spearman ρ)", f"{sp:.3f}" if sp == sp else "—")
    c3.metric("Population", n)

    num_cols = ["seo_overall", "seo_technical", "seo_finance", "geo_total"]
    if "geo_words" in merged.columns and merged["geo_words"].notna().any():
        num_cols.append("geo_words")
    mat = merged[[c for c in num_cols if c in merged.columns]].apply(pd.to_numeric, errors="coerce")
    mat = mat.dropna(axis=1, how="all")
    std = mat.std(numeric_only=True).fillna(0)
    mat = mat.loc[:, (std > 1e-9)]
    if len(mat.columns) >= 2 and n >= 3:
        pear = mat.corr(method="pearson")
        spear = mat.corr(method="spearman")

        def _lbl(x: str) -> str:
            return (
                x.replace("seo_overall", "Foundation · headline")
                .replace("seo_technical", "Foundation · technical")
                .replace("seo_finance", "Foundation · markets")
                .replace("geo_total", "GEO · readiness")
                .replace("geo_words", "Narrative length")
            )

        pear_v = pear.copy()
        pear_v.columns = [_lbl(str(c)) for c in pear_v.columns]
        pear_v.index = [_lbl(str(c)) for c in pear_v.index]
        spear_v = spear.copy()
        spear_v.columns = [_lbl(str(c)) for c in spear_v.columns]
        spear_v.index = [_lbl(str(c)) for c in spear_v.index]
        h1 = correlation_heatmap_figure(pear_v, title="Linear correlation matrix · multi-metric blend")
        h2 = correlation_heatmap_figure(spear_v, title="Rank correlation matrix · robust to plateaued scores")
        if h1 and h2:
            a, b = st.columns(2)
            with a:
                st.plotly_chart(h1, use_container_width=True, key="corr_pearson_hm")
                render_chart_insight(st, "performance_pearson")
                gap_after_chart(st)
            with b:
                st.plotly_chart(h2, use_container_width=True, key="corr_spearman_hm")
                render_chart_insight(st, "performance_spearman")
                gap_after_chart(st)
    elif n < 3:
        st.caption("Provide at least **three matched URLs** to unlock the heatmaps.")

    st.subheader("Narrative relationship charts")
    fig_sc = seo_vs_geo_scatter_figure(merged)
    if fig_sc is not None:
        st.plotly_chart(fig_sc, use_container_width=True, key="corr_scatter")
        render_chart_insight(st, "performance_scatter_geo")
        gap_after_chart(st)

    fig_bar = seo_geo_bucketed_bar_figure(merged)
    if fig_bar is not None:
        st.plotly_chart(fig_bar, use_container_width=True, key="corr_bar")
        render_chart_insight(st, "performance_binned_geo")
        gap_after_chart(st)

    with st.expander("Preview aligned table", expanded=False):
        pv = merged.head(500).rename(columns=DISPLAY_MERGED_PRETTY)
        st.dataframe(pv, use_container_width=True, hide_index=True)
    st.download_button(
        "Export aligned CSV",
        data=merged.to_csv(index=False).encode("utf-8"),
        file_name="performance_link_export.csv",
        mime="text/csv",
        key="corr_dl_merged",
    )
elif seo_df is not None and geo_df is not None and not seo_df.empty and not geo_df.empty:
    st.error(
        "Matched zero overlapping URLs — confirm identical hosts, rerun both batches before exporting, "
        "and reuse the readiness file that stores resolved destinations."
    )

st.divider()
st.markdown(
    "**Disclaimers ·** correlation highlights co‑movement, not causality. Dense SEO clusters amplify small GEO swings. "
    "**Spearman** matters when both scores saturate near the top of their scales."
)
