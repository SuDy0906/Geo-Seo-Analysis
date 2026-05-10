"""
Product copy and chart interpretations (two-line captions beneath visuals).
"""

from __future__ import annotations

from typing import Any

# Stable chart IDs → exactly two interpretation lines each.
CHART_INSIGHTS: dict[str, tuple[str, str]] = {
    "foundation_completion": (
        "Measures how many queued URLs produced a usable technical score versus errors or exclusions.",
        "Treat the green wedge as batch reliability; prioritize fixing blank or stale cache before benchmarking scores.",
    ),
    "foundation_overall_histogram": (
        "Distribution of the composite Foundation score across successfully analyzed pages.",
        "The index is calibrated to roughly 0–100; clustering above 85 often indicates strong template conformance on FXStreet.",
    ),
    "foundation_tech_vs_finance": (
        "Each point is one URL: technical readiness on the horizontal axis, finance/context depth on the vertical axis.",
        "Color reflects the headline Foundation score — use outliers to spot strong technical shells with thin market context.",
    ),
    "foundation_by_template": (
        "Compares Foundation score spreads across FXStreet-style page families (rates, hubs, editorial, etc.).",
        "The central line marks the median; the diamond summarizes mean ± dispersion — wide boxes signal inconsistent template QA.",
    ),
    "foundation_all_urls_bar": (
        "Sequential bars sort every successful URL alphabetically so you can scan extremes without truncating long tails.",
        "Read left-to-right as A→Z URLs; unusually short bars pinpoint pages needing structured data or richer metadata.",
    ),
    "foundation_single_scores": (
        "Headline composite plus two contributing pillars rendered for the URL you detailed below.",
        "Use 70 as a pragmatic review threshold — sustained scores below it usually warrant crawler or template remediation.",
    ),
    "readiness_completion": (
        "Tracks how often cite-readiness scoring completed versus exclusions in the queued batch.",
        "Orange wedges highlight cache gaps or incompatible hosts; resolve them before comparing orange vs teal bars.",
    ),
    "readiness_total_histogram": (
        "How often citation-readiness totals land across the calibrated 0–100 scale.",
        "Long left tails imply many pages lack scannable quotes, specificity, or answer-shaped structure for AI excerpts.",
    ),
    "readiness_words_vs_total": (
        "Relates readable word volume to citation-readiness totals for the same snapshots.",
        "Steep clouds without uplift suggest verbosity without evidence; leverage bottom-left clusters for rewriting.",
    ),
    "readiness_mean_dimensions": (
        "Batch-average scores for each heuristic dimension that feeds the headline readiness index.",
        "Dimensions nearer 90 indicate repeatable strengths; any dimension below ~55 merits content-design focus.",
    ),
    "readiness_all_urls_series": (
        "Plots every successful readiness score along an alphabetically sorted index for quick gap hunting.",
        "Use sustained low plateaus to theme editorial guidelines; spikes verify hero pages worth merchandising externally.",
    ),
    "readiness_bottom_pages": (
        "Surfaces the lowest readiness totals — these pages least resemble trustworthy sources for summarized answers.",
        "Pair with rewriting guidance from the spreadsheet export rather than rewriting solely from headline scores.",
    ),
    "readiness_top_pages": (
        "Showcases highest readiness totals — prioritize these when syndicating excerpts or FAQs to partners.",
        "Verify manually before external reuse; deterministic heuristics can still miss brand or compliance nuances.",
    ),
    "performance_pearson": (
        "Pairwise Pearson correlation between Foundation SEO metrics and GEO-style readiness proxies (linear association).",
        "Values nearer +1 / −1 signal stronger additive relationships; middling positives often appear when both hinge on richness.",
    ),
    "performance_spearman": (
        "Spearman rank correlations — robust when scores bunch at the top yet ordering still shifts.",
        "Compare with Pearson to detect monotone-but-nonlinear coupling driven by categorical URL mixes.",
    ),
    "performance_scatter_geo": (
        "Each dot pairs one URL’s Foundation score with its citation readiness total; tinted contours highlight density cliffs.",
        "The orange slope summarizes ordinary least squares in the observed band — flattening slopes imply diminishing GEO returns at high SEO.",
    ),
    "performance_binned_geo": (
        "Averages GEO-style readiness within equal-width bins of SEO scores while bars show ±1 standard error.",
        "Read trend direction more than steepness; widening whiskers imply heterogeneous pages inside each SEO cohort.",
    ),
}


def render_chart_insight(st: Any, insight_id: str) -> None:
    """Emit two standardized caption lines under a chart."""
    tpl = CHART_INSIGHTS.get(insight_id)
    if not tpl:
        return
    st.caption(tpl[0])
    st.caption(tpl[1])


def gap_after_chart(st: Any) -> None:
    """Breathing room before the next block (Streamlit stacks charts tightly otherwise)."""
    st.markdown(
        '<div aria-hidden="true" style="height:2.35rem;margin-bottom:0.5rem;"></div>',
        unsafe_allow_html=True,
    )


DISPLAY_COLUMNS_FOUNDATION_RESULTS: dict[str, str] = {
    "url": "Destination URL",
    "template": "Page type",
    "overall": "Foundation score",
    "technical": "Technical pillar",
    "finance": "Market context pillar",
    "error": "Status message",
}


def display_readiness_dataframe(raw: Any) -> Any:
    """Return a dataframe with readable column titles for citation readiness exports."""
    import pandas as pd

    if not isinstance(raw, pd.DataFrame) or raw.empty:
        return raw
    df = raw.copy()

    rename: dict[str, str] = {}
    if "citeability_total" in df.columns:
        rename["citeability_total"] = "Readiness index"
    if "final_url" in df.columns:
        rename["final_url"] = "Resolved URL"
    if "url" in df.columns:
        rename["url"] = "Submitted URL"
    if "status_code" in df.columns:
        rename["status_code"] = "HTTP status"
    if "word_count" in df.columns:
        rename["word_count"] = "Word count"
    if "error" in df.columns:
        rename["error"] = "Status message"
    for c in df.columns:
        cs = str(c)
        if cs.startswith("dim_"):
            readable = cs.replace("dim_", "", 1).replace("_", " ").strip().title()
            rename[c] = f"Pillar · {readable}"
    extras = {"used_spacy": "Signals · spaCy", "used_textstat": "Signals · textstat", "used_claude": "Signals · Claude"}
    rename.update({k: v for k, v in extras.items() if k in df.columns})
    return df.rename(columns=rename)
