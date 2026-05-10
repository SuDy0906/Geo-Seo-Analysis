"""
Foundation technical SEO — reads cached HTML only (no live fetch).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis_plots import seo_batch_figures, seo_single_scores_bar  # noqa: E402
from product_ui import (  # noqa: E402
    DISPLAY_COLUMNS_FOUNDATION_RESULTS,
    gap_after_chart,
    render_chart_insight,
)
from scraper_store import (  # noqa: E402
    get_cached_snapshot,
    list_cached_ok_urls,
    site_store_from_main_url,
    store_stats as scrape_store_stats,
)
from seo_audit import (  # noqa: E402
    AuditReport,
    fxstreet_page_family,
    run_fxstreet_seo_audit,
    validate_fxstreet_url,
)

st.set_page_config(page_title="Foundation SEO", page_icon="📊", layout="wide")

st.title("Foundation technical scorecard")
st.caption(
    "Offline analysis of saved HTML for the selected site origin. "
    "Run **Sitemap crawler** or **Article index** first, then score batches here."
)

main = st.sidebar.text_input(
    "Site origin",
    value="https://www.fxstreet.com/",
    help="Must match the crawl you already finished.",
    key="l1_origin",
)
store = site_store_from_main_url(main)
s = scrape_store_stats(store)
st.sidebar.metric("Cached pages", s["ok_bodies"])
st.sidebar.metric("Article registry", s.get("article_registry", 0))
st.sidebar.caption(f"Active host: **{store.canonical_root_host}**")

st.subheader("Batch analysis from cache")

if "l1_cache_summary" not in st.session_state:
    st.session_state["l1_cache_summary"] = None
    st.session_state["l1_cache_detail"] = None

scope = st.radio(
    "URL scope",
    options=["all_cached", "articles_only"],
    format_func=lambda x: "Entire cache with HTML" if x == "all_cached" else "Editorial articles only",
    horizontal=True,
    key="l1_cache_scope",
)
path_needle = ""
if scope == "articles_only" and not store.is_fxstreet:
    path_needle = st.text_input(
        "URL contains (optional substring for non‑FX sites)",
        value="",
        key="l1_cache_path_sub",
    )

max_urls = st.number_input(
    "Maximum URLs to score (newest first)",
    min_value=1,
    max_value=min(50_000, max(s["ok_bodies"], 1)),
    value=min(200, max(s["ok_bodies"], 1)),
    key="l1_cache_max",
)

r1, r2 = st.columns(2)
with r1:
    run_cache = st.button("Run batch score", type="primary", key="btn_l1_cache_run")
with r2:
    if st.button("Reset results", key="btn_l1_cache_clear"):
        st.session_state["l1_cache_summary"] = None
        st.session_state["l1_cache_detail"] = None
        st.rerun()

if run_cache:
    use_articles = bool(scope == "articles_only" and store.is_fxstreet)
    pc = (path_needle or "").strip() if (scope == "articles_only" and not store.is_fxstreet) else ""

    targets = list_cached_ok_urls(
        int(max_urls),
        store=store,
        article_stories_only=use_articles,
        article_match="path",
        path_contains=pc,
    )

    if not targets:
        st.warning("No cached URLs matched this scope.")
    else:
        summary: list[dict] = []
        detail_by_url: dict[str, AuditReport] = {}
        prog = st.progress(0)
        status = st.empty()
        for i, u in enumerate(targets):
            status.caption(f"Scoring {i + 1} of {len(targets)}")
            prog.progress((i + 1) / max(len(targets), 1))
            ve = validate_fxstreet_url(u)
            if ve is not None:
                summary.append(
                    {
                        "url": u,
                        "template": "",
                        "overall": None,
                        "technical": None,
                        "finance": None,
                        "error": ve,
                    }
                )
                continue

            snap = get_cached_snapshot(u, store=store)
            if not snap:
                summary.append(
                    {
                        "url": u,
                        "template": "",
                        "overall": None,
                        "technical": None,
                        "finance": None,
                        "error": "No cached body for this URL.",
                    }
                )
                continue

            html, fu, sc, hdrs = snap
            rep = run_fxstreet_seo_audit(
                u,
                prefetched_html=html,
                prefetched_final_url=fu,
                prefetched_status_code=sc,
                prefetched_load_seconds=0.0,
                prefetched_headers=hdrs,
            )
            fam = fxstreet_page_family(rep.final_url)
            summary.append(
                {
                    "url": rep.final_url,
                    "template": fam,
                    "overall": rep.overall_score if not rep.error else None,
                    "technical": rep.technical_score if not rep.error else None,
                    "finance": rep.finance_score if not rep.error else None,
                    "error": rep.error or "",
                }
            )
            if not rep.error:
                detail_by_url[rep.final_url] = rep
        prog.empty()
        status.empty()
        st.session_state["l1_cache_summary"] = summary
        st.session_state["l1_cache_detail"] = detail_by_url
        st.rerun()

cache_summary = st.session_state.get("l1_cache_summary") or []
if cache_summary:
    detail_by_url = st.session_state.get("l1_cache_detail") or {}
    df = pd.DataFrame(cache_summary)
    show_df = df.rename(columns=DISPLAY_COLUMNS_FOUNDATION_RESULTS)
    if "seconds" in show_df.columns:
        show_df = show_df.drop(columns=["seconds"], errors="ignore")
    st.subheader("Summary table")
    st.dataframe(show_df, use_container_width=True, hide_index=True)
    st.download_button(
        "Export CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="foundation_batch_export.csv",
        mime="text/csv",
        key="l1_cache_dl",
    )

    st.subheader("Visual insights")
    for i, (_chart_name, fig_i, insight_id) in enumerate(seo_batch_figures(df)):
        st.plotly_chart(fig_i, use_container_width=True, key=f"l1_batch_plot_{i}")
        render_chart_insight(st, insight_id)
        gap_after_chart(st)

    inspect_choices = [r["url"] for r in cache_summary if r["url"] in detail_by_url]
    if inspect_choices:
        with st.expander("Detailed page review", expanded=False):
            pick = st.selectbox("Choose URL", options=inspect_choices, key="l1_cache_inspect_pick")
            rep = detail_by_url[pick]
            st.markdown(f"**Page archetype:** `{fxstreet_page_family(pick)}`")
            cc1, cc2, cc3 = st.columns(3)
            cc1.metric("Headline score", rep.overall_score)
            cc2.metric("Technical pillar", rep.technical_score)
            cc3.metric("Market context", rep.finance_score)
            st.plotly_chart(
                seo_single_scores_bar(rep.overall_score, rep.technical_score, rep.finance_score),
                use_container_width=True,
                key=f"l1_pick_scores_{hash(pick) & 0xFFFF_FFFF}",
            )
            render_chart_insight(st, "foundation_single_scores")
            gap_after_chart(st)
            prio = rep.fix_priorities()
            if prio:
                prio_df = pd.DataFrame(prio).rename(
                    columns={
                        "check_id": "Checkpoint",
                        "label": "Focus area",
                        "detail": "Guidance",
                        "finance_context": "Impacts market pillar",
                        "priority": "Severity",
                    }
                )
                st.dataframe(prio_df, use_container_width=True, hide_index=True)
            chk_rows = [
                {"Checkpoint": c.id, "Label": c.label, "Pass": c.passed, "Notes": c.detail[:400]}
                for c in rep.checks
            ]
            st.dataframe(pd.DataFrame(chk_rows), use_container_width=True, hide_index=True)

st.divider()
st.markdown(
    "**Scope note:** scoring rules are tuned for FXStreet templates today. "
    "Other hosts remain storable, but results may read as *not applicable* until localized rules ship."
)
