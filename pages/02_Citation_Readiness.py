"""
Citation and answer-engine readiness — offline scoring from cache.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis_plots import cite_batch_figures  # noqa: E402
from citeability import CiteabilityReport, report_to_row, score_fxstreet_citeability  # noqa: E402
from product_ui import display_readiness_dataframe, gap_after_chart, render_chart_insight  # noqa: E402
from scraper_store import (  # noqa: E402
    get_cached_snapshot,
    list_cached_ok_urls,
    site_store_from_main_url,
    store_stats as scrape_store_stats,
)
from seo_audit import validate_fxstreet_url  # noqa: E402


def _api_key(ui_key: str) -> str:
    if ui_key.strip():
        return ui_key.strip()
    try:
        s = st.secrets["ANTHROPIC_API_KEY"]  # type: ignore[index]
        if isinstance(s, str) and s.strip():
            return s.strip()
    except Exception:
        pass
    return (os.environ.get("ANTHROPIC_API_KEY") or "").strip()


st.set_page_config(page_title="Citation readiness", page_icon="📝", layout="wide")
st.title("Citation readiness studio")
st.caption(
    "Scores how quotable and machine-summary-friendly each cached page is. "
    "Uses the same snapshots as the foundation scorecard — no network calls here."
)

main = st.sidebar.text_input(
    "Site origin",
    value="https://www.fxstreet.com/",
    key="l2_origin",
)
store = site_store_from_main_url(main)
_ss = scrape_store_stats(store)
st.sidebar.metric("Cached pages", _ss["ok_bodies"])
st.sidebar.metric("Articles with HTML", _ss.get("article_with_html", 0))
st.sidebar.caption(f"Active host: **{store.canonical_root_host}**")

st.subheader("Batch queue")
st.markdown("URLs load from your local index only.")

pc = ""
if not store.is_fxstreet:
    pc = st.text_input("URL contains (optional substring)", "", key="l2_bulk_pc")

lc1, lc2 = st.columns(2)
with lc1:
    if store.is_fxstreet and st.button("Queue editorial articles", key="btn_l2_load_art"):
        st.session_state["l2_article_urls"] = list_cached_ok_urls(
            50_000,
            store=store,
            article_stories_only=True,
            article_match="path",
        )
        st.rerun()
with lc2:
    if st.button("Queue entire cache", key="btn_l2_load_all"):
        st.session_state["l2_article_urls"] = list_cached_ok_urls(
            50_000,
            store=store,
            article_stories_only=False,
        )
        st.rerun()

if not store.is_fxstreet and st.button("Queue filtered cache", key="btn_l2_load_sf"):
    st.session_state["l2_article_urls"] = list_cached_ok_urls(
        50_000,
        store=store,
        article_stories_only=False,
        path_contains=pc.strip(),
    )
    st.rerun()

article_urls = st.session_state.get("l2_article_urls") or []
if article_urls:
    st.caption(f"{len(article_urls)} URLs queued · scoring always processes the full queue.")

if article_urls:
    b1, b2, b3 = st.columns(3)
    with b1:
        b_spacy = st.checkbox("Enable spaCy entities", value=True, key="l2b_spacy")
    with b2:
        b_txt = st.checkbox("Enable text statistics", value=True, key="l2b_txt")
    with b3:
        b_claude = st.checkbox("Enable Claude advisory", value=False, key="l2b_claude")

    cb = 0
    anthropic_bulk = ""
    if b_claude:
        cb = int(
            st.number_input(
                "Claude rows",
                0,
                len(article_urls),
                min(10, len(article_urls)),
                help="Keeps API usage predictable on large batches.",
                key="l2b_cb",
            )
        )
        anthropic_bulk = st.text_input(
            "Anthropic API override",
            type="password",
            key="l2_sk_b",
            autocomplete="new-password",
        )

    bulk_key = _api_key(anthropic_bulk) if b_claude and cb > 0 else ""
    if b_claude and cb > 0 and not bulk_key:
        st.warning("Provide **ANTHROPIC_API_KEY** via secrets or the override to run Claude.")

    n_queue = len(article_urls)
    if st.button(f"Score all {n_queue} URLs", type="primary", key="btn_bulk_score"):
        to_run = list(article_urls)
        use_cf = bool(b_claude and cb > 0 and bulk_key)

        prog = st.progress(0)
        rows_out: list[dict] = []
        status = st.empty()

        for i, u in enumerate(to_run):
            prog.progress((i + 1) / max(len(to_run), 1))
            status.caption(f"Scoring {i + 1} of {len(to_run)}")
            ve = validate_fxstreet_url(u)
            if ve is not None:
                rows_out.append(
                    report_to_row(
                        CiteabilityReport(
                            url=u,
                            final_url=u,
                            status_code=None,
                            error=ve,
                            word_count=0,
                            dimensions={},
                            total=0.0,
                        )
                    )
                )
                continue
            snap = get_cached_snapshot(u, store=store)
            if not snap:
                rows_out.append(
                    report_to_row(
                        CiteabilityReport(
                            url=u,
                            final_url=u,
                            status_code=None,
                            error="Missing cache entry",
                            word_count=0,
                            dimensions={},
                            total=0.0,
                        )
                    )
                )
                continue
            html, fu, sc, _ = snap
            uc = bool(use_cf and i < cb)
            rep = score_fxstreet_citeability(
                u,
                use_spacy=b_spacy,
                use_textstat=b_txt,
                use_claude=uc,
                anthropic_api_key=bulk_key if uc else None,
                prefetched_html=html,
                prefetched_final_url=fu,
                prefetched_status_code=sc,
            )
            rows_out.append(report_to_row(rep))

        prog.empty()
        status.empty()
        st.session_state["l2_bulk_df"] = pd.DataFrame(rows_out)
        st.rerun()

df_cached = st.session_state.get("l2_bulk_df")
if isinstance(df_cached, pd.DataFrame) and not df_cached.empty:
    display_df = display_readiness_dataframe(df_cached)
    st.subheader("Results overview")
    st.dataframe(display_df, use_container_width=True, height=400)
    st.download_button(
        "Export CSV",
        data=df_cached.to_csv(index=False).encode("utf-8"),
        file_name="citation_readiness_export.csv",
        mime="text/csv",
        key="l2_bulk_dl",
    )
    st.subheader("Visual insights")
    for i, (_chart_name, fig_i, insight_id) in enumerate(cite_batch_figures(df_cached)):
        st.plotly_chart(fig_i, use_container_width=True, key=f"l2_batch_plot_{i}")
        render_chart_insight(st, insight_id)
        gap_after_chart(st)

    if st.button("Clear results", key="l2_clr"):
        del st.session_state["l2_bulk_df"]
        st.rerun()

st.divider()
st.markdown(
    "Prepare models once via **`python -m spacy download en_core_web_sm`**. "
    "Optional Claude keys live in `.streamlit/secrets.toml`."
)
