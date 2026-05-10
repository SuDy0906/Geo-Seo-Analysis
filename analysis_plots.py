"""Plotly figure builders for SEO / cite-ability batch and single-url views."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go


def _short(u: str, n: int = 56) -> str:
    s = (u or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


# Title at top of paper (y=1); large top margins reserve space so titles never sit on traces (Plotly clamps title y to [0,1]).
TITLE_FONT = dict(size=15)
TITLE_TOP = dict(
    xref="paper",
    yref="paper",
    y=1.0,
    yanchor="bottom",
    x=0.5,
    xanchor="center",
    pad=dict(b=12),
)
# Single-line chart title vs title + HTML subtitle (<br><sup>…)
MARGIN_TOP_ONE = 112
MARGIN_TOP_SUB = 200

# Standard pixel heights (large top margin steals area; totals keep plot size consistent across pages).
HEIGHT_BAR_SINGLE = 408
HEIGHT_CHECKS = 348
HEIGHT_PIE = 496
# Batch charts with a subtitle line share one height so pages look even.
HEIGHT_SUB_CHART = 496
HEIGHT_URL_RUNWAY = 620
HEIGHT_CITE_MEAN_BARS = 468
HEIGHT_GEO_SCATTER = 596
HEIGHT_GEO_SCATTER_NODE = 574
HEIGHT_GEO_BUCKET = 496
HEIGHT_HEATMAP_OVER_BASE = 76

LEGEND_BELOW_PLOT = dict(
    orientation="h",
    yanchor="top",
    y=-0.22,
    xanchor="center",
    x=0.5,
    font=dict(size=12),
)

# Horizontal colorbar under the plot (avoids crowding titles on the right).
COLORBAR_H = dict(
    orientation="h",
    x=0.5,
    xanchor="center",
    y=-0.28,
    yanchor="top",
    len=0.72,
    thickness=14,
    outlinewidth=0,
)


def _chart_title(text: str) -> dict:
    return dict(text=text, font=TITLE_FONT, **TITLE_TOP)


def _completion_pie_trace(
    v_pos: int,
    v_neg: int,
    *,
    pos_color: str,
    neg_color: str,
    pos_label: str = "Completed",
    neg_label: str = "Needs attention",
) -> go.Pie:
    """Avoid a 0-width slice whose outside annotations collide with layout titles."""
    if v_neg <= 0:
        labels = [pos_label]
        values = [max(1, int(v_pos))]
        colors = [pos_color]
        textposition = "inside"
        pie_kw: dict[str, object] = {}
    elif v_pos <= 0:
        labels = [neg_label]
        values = [max(1, int(v_neg))]
        colors = [neg_color]
        textposition = "inside"
        pie_kw = {}
    else:
        labels = [pos_label, neg_label]
        values = [int(v_pos), int(v_neg)]
        colors = [pos_color, neg_color]
        textposition = "outside"
        pie_kw = dict(pull=[0.02, 0.02])
    return go.Pie(
        labels=labels,
        values=values,
        hole=0.45,
        marker=dict(colors=colors),
        textinfo="percent+label",
        texttemplate="%{label}<br>%{percent}",
        textposition=textposition,
        hovertemplate="%{label}<br>Count: %{value:.0f} · Share: %{percent}<extra></extra>",
        sort=False,
        **pie_kw,
    )

def _score_tick_settings() -> dict[str, dict]:
    """Consistent decimals on 0–100 style axes."""
    return {"tickformat": ".1f"}


def seo_single_scores_bar(overall: float, technical: float, finance: float) -> go.Figure:
    fig = go.Figure(
        data=[
            go.Bar(
                x=["Overall", "Technical", "Finance context"],
                y=[overall, technical, finance],
                marker_color=["#2563eb", "#7c3aed", "#059669"],
                text=[f"{overall:.1f}", f"{technical:.1f}", f"{finance:.1f}"],
                textposition="outside",
            )
        ]
    )
    fig.update_layout(
        title=_chart_title("Foundation score pillars"),
        yaxis_range=[0, 105],
        showlegend=False,
        margin=dict(t=MARGIN_TOP_ONE, l=52, r=40, b=52),
        height=HEIGHT_BAR_SINGLE,
        yaxis=dict(title=dict(text="Score (0–100 index)"), **_score_tick_settings()),
        xaxis=dict(tickfont=dict(size=12)),
    )
    return fig


def seo_checks_pass_bar(checks_df: pd.DataFrame) -> go.Figure | None:
    if checks_df.empty or "ok" not in checks_df.columns:
        return None
    tot = len(checks_df)
    if tot == 0:
        return None
    passed = int(checks_df["ok"].sum())
    failed = tot - passed
    fig = go.Figure(
        data=[
            go.Bar(
                x=["Passed", "Failed"],
                y=[passed, failed],
                marker_color=["#16a34a", "#dc2626"],
                text=[str(passed), str(failed)],
                textposition="outside",
            )
        ]
    )
    fig.update_layout(
        title=_chart_title("Technical checklist snapshot"),
        showlegend=False,
        margin=dict(t=MARGIN_TOP_ONE, l=52, r=36, b=52),
        height=HEIGHT_CHECKS,
        yaxis=dict(title=dict(text="Count"), tickformat="d"),
    )
    return fig


def seo_batch_figures(df: pd.DataFrame) -> list[tuple[str, go.Figure, str]]:
    out: list[tuple[str, go.Figure, str]] = []
    if df.empty:
        return out

    err_empty = df["error"].fillna("") == ""
    dfx = df.copy()
    for col in ("overall", "technical", "finance"):
        if col in dfx.columns:
            dfx[col] = pd.to_numeric(dfx[col], errors="coerce")
    ok = dfx[err_empty & dfx["overall"].notna()].copy()
    n_ok = int(err_empty.sum())
    n_fail = int(len(df) - n_ok)

    v_ok = int(max(0, n_ok))
    v_fail = int(max(0, n_fail))
    if v_ok == 0 and v_fail == 0:
        v_ok = 1
    fig_pie = go.Figure(
        data=[
            _completion_pie_trace(
                v_ok,
                v_fail,
                pos_color="#22c55e",
                neg_color="#f97316",
            )
        ]
    )
    fig_pie.update_layout(
        title=_chart_title(
            f"Batch completion mix<br><sup style='font-size:12px;color:#888'>Queued: {len(df)} URLs · {v_ok} completed · {v_fail} need attention</sup>"
        ),
        showlegend=False,
        margin=dict(t=MARGIN_TOP_SUB, b=96, l=48, r=48),
        height=HEIGHT_PIE,
        uniformtext_minsize=11,
        uniformtext_mode="hide",
    )
    out.append(("Completion", fig_pie, "foundation_completion"))

    if len(ok) >= 2:
        fig_hist = go.Figure(
            data=[go.Histogram(x=ok["overall"], nbinsx=min(30, max(8, len(ok) // 3)), marker_color="#2563eb")]
        )
        fig_hist.update_layout(
            title=_chart_title(
                f"Foundation score distribution · successful pages<br><sup style='font-size:12px;color:#888'>n = {len(ok)} pages · bins auto-scaled · scores clipped to 0–100 for display</sup>"
            ),
            xaxis=dict(title=dict(text="Foundation score"), **_score_tick_settings()),
            yaxis=dict(title=dict(text="Page count"), tickformat="d"),
            margin=dict(t=MARGIN_TOP_SUB, l=56, r=36, b=54),
            height=HEIGHT_SUB_CHART,
            bargap=0.06,
        )
        out.append(("Foundation distribution", fig_hist, "foundation_overall_histogram"))

        hover = [_short(u, 72) for u in ok["url"].astype(str)]
        fig_sc = go.Figure(
            data=[
                go.Scatter(
                    x=ok["technical"],
                    y=ok["finance"],
                    mode="markers",
                    marker=dict(
                        size=10,
                        opacity=0.72,
                        color=ok["overall"],
                        colorscale="Viridis",
                        showscale=True,
                        colorbar={
                            **COLORBAR_H,
                            "y": -0.38,
                            "len": 0.78,
                            "title": dict(text="Headline score (0–100)", font=dict(size=12)),
                        },
                        cmin=0,
                        cmax=100,
                    ),
                    customdata=hover,
                    hovertemplate=(
                        "%{customdata}<br>Technical: %{x:.2f}<br>Market pillar: %{y:.2f}<extra></extra>"
                    ),
                    showlegend=False,
                )
            ]
        )
        fig_sc.update_layout(
            title=_chart_title(
                f"Technical vs market pillars · color = headline score<br><sup style='font-size:12px;color:#888'>Same n as distribution · decimals shown to 2 d.p. on hover</sup>"
            ),
            xaxis=dict(title=dict(text="Technical pillar"), **_score_tick_settings(), range=[-2, 102]),
            yaxis=dict(title=dict(text="Market context pillar"), **_score_tick_settings(), range=[-2, 102]),
            margin=dict(t=MARGIN_TOP_SUB, l=56, r=40, b=148),
            height=HEIGHT_SUB_CHART,
            showlegend=False,
        )
        out.append(("Pillar balance", fig_sc, "foundation_tech_vs_finance"))

    if len(ok) >= 4 and ok["template"].notna().any() and ok["template"].astype(str).str.len().gt(0).any():
        tmpl_counts = ok["template"].astype(str).value_counts()
        if len(tmpl_counts) > 1:
            tmpl_list = tmpl_counts.index.tolist()[:25]
            sub = ok[ok["template"].astype(str).isin(tmpl_list)]
            fig_box = go.Figure()
            for t in tmpl_list:
                ys = sub.loc[sub["template"].astype(str) == t, "overall"].dropna()
                if len(ys):
                    fig_box.add_trace(go.Box(y=ys, name=str(t)[:28], boxmean="sd"))
            show_leg = bool(len(tmpl_list) <= 16)
            box_layout = dict(
                title=_chart_title(
                    f"Foundation score vs page archetype<br><sup style='font-size:12px;color:#888'>n = {len(sub)} audits · truncated labels at 28 characters</sup>"
                ),
                yaxis=dict(title=dict(text="Foundation score"), **_score_tick_settings(), range=[0, 102]),
                showlegend=show_leg,
                margin=dict(t=MARGIN_TOP_SUB, l=52, r=36, b=148 if show_leg else 120),
                height=max(468, len(tmpl_list) * 8 + 300),
                xaxis_tickangle=-35,
            )
            if show_leg:
                box_layout["legend"] = {**LEGEND_BELOW_PLOT, "y": -0.3}
            fig_box.update_layout(box_layout)
            out.append(("Page archetypes", fig_box, "foundation_by_template"))

    if len(ok) >= 1:
        sub = ok.copy()
        sub["_ov"] = pd.to_numeric(sub["overall"], errors="coerce").clip(0, 100)
        sub = sub.sort_values("url", key=lambda s: s.astype(str).str.lower()).reset_index(drop=True)
        n = len(sub)
        idx = list(range(n))
        hovers = [_short(str(u), 96) for u in sub["url"]]
        gap = max(0.002, min(0.35, 2.0 / max(n, 50)))
        fig_all = go.Figure(
            data=[
                go.Bar(
                    x=idx,
                    y=sub["_ov"],
                    marker=dict(color="#2563eb", line=dict(width=0)),
                    customdata=hovers,
                    hovertemplate="%{customdata}<br>Rank %{x} · Foundation: %{y:.2f}<extra></extra>",
                )
            ]
        )
        dtick = max(1, n // 20)
        fig_all.update_layout(
            title=_chart_title(
                f"Foundation footprint · all {n} URLs (A–Z sorted)<br>"
                "<sup style='font-size:12px;color:#888'>One bar per audited URL · y-axis clipped 0–100</sup>"
            ),
            xaxis=dict(title=dict(text="Alphabetized URL rank (index)"), tickmode="linear", tick0=0, dtick=dtick, tickformat="d"),
            yaxis=dict(title=dict(text="Foundation score (0–100)"), range=[0, 105], **_score_tick_settings()),
            showlegend=False,
            bargap=gap,
            margin=dict(t=MARGIN_TOP_SUB, l=58, r=40, b=62),
            height=min(HEIGHT_URL_RUNWAY, max(400, 260 + min(n // 5, 100))),
        )
        out.append(("All pages · foundation", fig_all, "foundation_all_urls_bar"))

    return out


def cite_single_dimensions_bar(dimensions: dict[str, float]) -> go.Figure:
    items = sorted(dimensions.items(), key=lambda kv: kv[1], reverse=True)
    labels = [k.replace("_", " ").title() for k, _ in items]
    vals = [float(v) for _, v in items]
    fig = go.Figure(
        go.Bar(
            x=vals,
            y=labels,
            orientation="h",
            marker=dict(color=vals, colorscale="Blues", cmid=50, showscale=False),
            text=[f"{v:.1f}" for v in vals],
            textposition="outside",
        )
    )
    fig.update_layout(
        title=_chart_title("Readiness pillars · inspected page"),
        xaxis=dict(title=dict(text="Score (0–100)"), range=[0, 105], **_score_tick_settings()),
        margin=dict(t=MARGIN_TOP_ONE, l=188, r=52, b=54),
        height=min(560, max(400, len(labels) * 32)),
        showlegend=False,
    )
    return fig


def cite_batch_figures(df: pd.DataFrame) -> list[tuple[str, go.Figure, str]]:
    out: list[tuple[str, go.Figure, str]] = []
    if df.empty:
        return out

    err_ok = df["error"].fillna("") == ""
    scored = df[err_ok].copy()
    total_col = "citeability_total" if "citeability_total" in scored.columns else None

    n_ok = int(err_ok.sum())
    n_bad = int(len(df) - n_ok)
    v_done = int(max(0, n_ok))
    v_bad = int(max(0, n_bad))
    if v_done == 0 and v_bad == 0:
        v_done = 1
    fig_pie = go.Figure(
        data=[
            _completion_pie_trace(
                v_done,
                v_bad,
                pos_color="#0d9488",
                neg_color="#ea580c",
            )
        ]
    )
    fig_pie.update_layout(
        title=_chart_title(
            f"Readiness batch mix<br><sup style='font-size:12px;color:#888'>Rows: {len(df)} · {v_done} scored · {v_bad} unresolved</sup>"
        ),
        showlegend=False,
        margin=dict(t=MARGIN_TOP_SUB, b=96, l=48, r=48),
        height=HEIGHT_PIE,
        uniformtext_minsize=11,
        uniformtext_mode="hide",
    )
    out.append(("Outcomes", fig_pie, "readiness_completion"))

    if total_col:
        scored = scored.copy()
        scored["_total"] = pd.to_numeric(scored[total_col], errors="coerce")
        scored = scored.dropna(subset=["_total"])

    num_t = (
        scored["_total"]
        if total_col and "_total" in scored.columns and len(scored.index) > 0
        else pd.Series(dtype=float)
    )

    if total_col and len(num_t) >= 2:
        fig_hist = go.Figure(
            data=[
                go.Histogram(
                    x=num_t.clip(0, 100),
                    nbinsx=min(25, max(8, len(num_t) // 2)),
                    marker_color="#0369a1",
                )
            ]
        )
        fig_hist.update_layout(
            title=_chart_title(
                f"Readiness index distribution<br><sup style='font-size:12px;color:#888'>n = {len(num_t)} pages · clipped to 0–100 before binning · counts = URLs per bucket</sup>"
            ),
            xaxis=dict(title=dict(text="Readiness index"), **_score_tick_settings()),
            yaxis=dict(title=dict(text="Page count"), tickformat="d"),
            margin=dict(t=MARGIN_TOP_SUB, l=56, r=40, b=54),
            height=HEIGHT_SUB_CHART,
            bargap=0.06,
        )
        out.append(("Index distribution", fig_hist, "readiness_total_histogram"))

        if "word_count" in scored.columns:
            scored["_wc"] = pd.to_numeric(scored["word_count"], errors="coerce")
            pair = scored.dropna(subset=["_total", "_wc"])
            if len(pair) >= 3:
                fig_sc = go.Figure(
                    go.Scatter(
                        x=pair["_wc"],
                        y=pair["_total"],
                        mode="markers",
                        marker=dict(size=11, opacity=0.74, color="#0ea5e9"),
                        text=[_short(str(u)) for u in pair["url"].astype(str)],
                        hovertemplate="%{text}<br>Words: %{x}<br>Total: %{y:.1f}<extra></extra>",
                    )
                )
                fig_sc.update_layout(
                    title=_chart_title(
                        f"Narrative length vs readiness<br><sup style='font-size:12px;color:#888'>n = {len(pair)} URLs · axes use measured counts & index (0–100)</sup>"
                    ),
                    xaxis=dict(title=dict(text="Word count"), tickformat=",d"),
                    yaxis=dict(title=dict(text="Readiness index"), **_score_tick_settings(), range=[-2, 102]),
                    margin=dict(t=MARGIN_TOP_SUB, l=56, r=40, b=54),
                    height=HEIGHT_SUB_CHART,
                    showlegend=False,
                )
                out.append(("Length vs readiness", fig_sc, "readiness_words_vs_total"))

    dim_cols = sorted(c for c in df.columns if str(c).startswith("dim_"))
    if dim_cols and len(df[err_ok]) >= 1:
        basis = df[err_ok].copy()
        means: dict[str, float] = {}
        for c in dim_cols:
            v = pd.to_numeric(basis[c], errors="coerce").dropna()
            if len(v):
                lab = c.replace("dim_", "", 1).replace("_", " ").strip().title()
                means[lab] = float(v.mean())
        if means:
            labels = list(means.keys())
            vals = list(means.values())
            fig_m = go.Figure(
                go.Bar(
                    x=labels,
                    y=vals,
                    marker_color="#0891b2",
                    text=[f"{v:.1f}" for v in vals],
                    textposition="outside",
                )
            )
            fig_m.update_layout(
                title=_chart_title(
                    f"Average readiness pillar strength<br><sup style='font-size:12px;color:#888'>Batch of {len(basis)} scored rows · each bar = mean of that pillar (0–100)</sup>"
                ),
                yaxis=dict(title=dict(text="Batch mean (0–100)"), range=[0, 105], **_score_tick_settings()),
                xaxis_tickangle=-28,
                margin=dict(t=MARGIN_TOP_SUB, l=52, r=36, b=154),
                height=HEIGHT_CITE_MEAN_BARS,
                showlegend=False,
            )
            out.append(("Pillar spotlight", fig_m, "readiness_mean_dimensions"))

    if "_total" in scored.columns and len(scored.index) >= 1:
        sl = scored.sort_values("url", key=lambda s: s.astype(str).str.lower()).reset_index(drop=True)
        sl["_tot_clip"] = pd.to_numeric(sl["_total"], errors="coerce").clip(0, 100)
        ix = list(range(len(sl)))
        hv = [_short(str(u), 96) for u in sl["url"].astype(str)]
        fig_l2_line = go.Figure(
            data=[
                go.Scatter(
                    x=ix,
                    y=sl["_tot_clip"],
                    mode="lines+markers",
                    name="Cite total",
                    line=dict(color="#0d9488", width=2),
                    marker=dict(size=6, color="#0f766e"),
                    customdata=hv,
                    hovertemplate="%{customdata}<br>Rank %{x} · Index: %{y:.2f}<extra></extra>",
                )
            ]
        )
        dt2 = max(1, len(sl) // 20)
        fig_l2_line.update_layout(
            title=_chart_title(
                f"Readiness index runway · {len(sl)} URLs (A–Z)<br>"
                "<sup style='font-size:12px;color:#888'>Markers unjittered · one point per URL · y clipped 0–100</sup>"
            ),
            xaxis=dict(title=dict(text="Alphabetized URL rank"), tickmode="linear", tick0=0, dtick=dt2, tickformat="d"),
            yaxis=dict(title=dict(text="Readiness index (0–100)"), range=[0, 105], **_score_tick_settings()),
            showlegend=False,
            margin=dict(t=MARGIN_TOP_SUB, l=58, r=40, b=62),
            height=min(HEIGHT_URL_RUNWAY, max(380, 240 + min(len(sl) // 4, 120))),
        )
        out.append(("All URLs · readiness", fig_l2_line, "readiness_all_urls_series"))

        k = min(20, len(scored))
        low = scored.nsmallest(k, "_total")
        labels = [_short(str(u), 50) for u in low["url"].astype(str)]
        fig_low = go.Figure(
            go.Bar(x=low["_total"].values, y=labels, orientation="h", marker_color="#be123c")
        )
        fig_low.update_layout(
            title=_chart_title(
                f"Lowest readiness spotlight · bottom {len(low)}<br><sup style='font-size:12px;color:#888'>Exact index scores on hover (2 decimals)</sup>"
            ),
            xaxis=dict(title=dict(text="Readiness index"), **_score_tick_settings()),
            yaxis=dict(autorange="reversed"),
            margin=dict(t=MARGIN_TOP_SUB, l=308, r=44, b=54),
            height=min(660, max(340, len(low) * 30)),
        )
        out.append(("Lowest readiness", fig_low, "readiness_bottom_pages"))

        hi = scored.nlargest(min(20, len(scored)), "_total")
        labels_hi = [_short(str(u), 50) for u in hi["url"].astype(str)]
        fig_hi = go.Figure(
            go.Bar(x=hi["_total"].values, y=labels_hi, orientation="h", marker_color="#047857")
        )
        fig_hi.update_layout(
            title=_chart_title(
                f"Highest readiness · champion set ({len(hi)})<br><sup style='font-size:12px;color:#888'>Exact index scores on hover (2 decimals)</sup>"
            ),
            xaxis=dict(title=dict(text="Readiness index"), **_score_tick_settings()),
            yaxis=dict(autorange="reversed"),
            margin=dict(t=MARGIN_TOP_SUB, l=308, r=44, b=54),
            height=min(660, max(340, len(hi) * 30)),
        )
        out.append(("Highest readiness", fig_hi, "readiness_top_pages"))

    return out


def correlation_heatmap_figure(
    corr: pd.DataFrame,
    *,
    title: str,
    height: int = 440,
) -> go.Figure | None:
    """Symmetric correlation matrix (−1 … 1); expects numeric square DataFrame."""
    if corr.empty:
        return None
    labels = [str(c) for c in corr.columns]
    z = corr.values.astype(float)
    text = [["" if np.isnan(v) else f"{v:.2f}" for v in row] for row in z]
    lbl_max = max((len(str(x)) for x in labels), default=14)
    margin_l = min(300, max(172, lbl_max * 7 + 32))
    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=labels,
            y=labels,
            text=text,
            texttemplate="%{text}",
            textfont={"size": 11},
            colorscale="RdBu",
            zmid=0,
            zmin=-1,
            zmax=1,
            colorbar={
                **COLORBAR_H,
                "y": -0.22,
                "len": 0.74,
                "title": dict(text="r", font=dict(size=12)),
            },
        )
    )
    fig.update_layout(
        title=_chart_title(title),
        margin=dict(t=MARGIN_TOP_ONE + 36, l=margin_l, r=36, b=172),
        height=height + HEIGHT_HEATMAP_OVER_BASE,
        xaxis_side="bottom",
        yaxis_autorange="reversed",
    )
    fig.update_traces(
        colorbar=dict(
            orientation="h",
            x=0.5,
            xanchor="center",
            y=-0.22,
            yanchor="top",
            len=0.74,
            thickness=14,
            title=dict(text="r", font=dict(size=12)),
        ),
        selector=dict(type="heatmap"),
    )
    return fig


def _pad_range(lo: float, hi: float, *, pad_frac: float = 0.06, hard_lo: float = 0, hard_hi: float = 100) -> tuple[float, float]:
    span = max(hi - lo, 1e-6)
    pad = max(span * pad_frac, 0.5)
    return max(hard_lo, lo - pad), min(hard_hi, hi + pad)


def seo_vs_geo_scatter_figure(
    df: pd.DataFrame,
    *,
    x_col: str = "seo_overall",
    y_col: str = "geo_total",
    label_col: str = "url_display",
) -> go.Figure | None:
    pair = df.dropna(subset=[x_col, y_col])
    if pair.empty:
        return None
    x = pair[x_col].astype(float).to_numpy()
    y = pair[y_col].astype(float).to_numpy()
    if label_col in pair.columns:
        custom = [_short(str(u), 88) for u in pair[label_col].astype(str)]
    else:
        custom = [""] * len(pair)
    x_lo, x_hi = _pad_range(float(x.min()), float(x.max()))
    y_lo, y_hi = _pad_range(float(y.min()), float(y.max()))
    fig = go.Figure()
    if len(x) >= 32:
        dens: dict[str, object] = dict(
            x=x,
            y=y,
            ncontours=16,
            colorscale="Viridis",
            contours=dict(showlines=False),
            hoverinfo="skip",
            name="Density",
            showlegend=False,
            opacity=0.85,
        )
        if len(x) >= 240:
            dens["showscale"] = True
            dens["colorbar"] = {
                **COLORBAR_H,
                "y": -0.42,
                "len": 0.85,
                "thickness": 12,
                "title": dict(text="Point density", font=dict(size=12)),
            }
        else:
            dens["showscale"] = False
        fig.add_trace(go.Histogram2dContour(**dens))
    show_legend = len(x) >= 2
    fig.add_trace(
        go.Scattergl(
            x=x,
            y=y,
            mode="markers",
            marker=dict(size=10, opacity=0.42, color="#e9d5ff", line=dict(width=0.5, color="#6b21a8")),
            customdata=custom,
            hovertemplate=(
                "%{customdata}<br>"
                "Foundation score: %{x:.2f}<br>"
                "GEO readiness proxy: %{y:.2f}<extra></extra>"
            ),
            name="Pages",
            showlegend=show_legend,
        )
    )
    if len(x) >= 3:
        coef = np.polyfit(x, y, 1)
        xs_lin = np.linspace(float(x.min()), float(x.max()), 50)
        ys_lin = coef[0] * xs_lin + coef[1]
        fig.add_trace(
            go.Scatter(
                x=xs_lin,
                y=ys_lin,
                mode="lines",
                line=dict(color="#fb923c", width=3),
                name="Ordinary least squares trend",
                showlegend=True,
            )
        )
    elif len(x) == 2:
        coef = np.polyfit(x, y, 1)
        xs_lin = np.array([float(x.min()), float(x.max())])
        ys_lin = coef[0] * xs_lin + coef[1]
        fig.add_trace(
            go.Scatter(
                x=xs_lin,
                y=ys_lin,
                mode="lines",
                line=dict(color="#fb923c", width=3),
                name="Ordinary least squares trend",
                showlegend=True,
            )
        )

    dens_on = len(x) >= 240
    leg_y = -0.32 if not dens_on else -0.62
    bot_m = 132 if not dens_on else 188
    fig.update_layout(
        title=_chart_title(
            f"Foundation vs GEO readiness · joint view<br>"
            f"<sup style='font-size:12px;color:#888'>n = {len(x)} aligned URLs · density shading when ≥32 points · trend uses full x-span</sup>"
        ),
        xaxis=dict(
            title=dict(text="Foundation score"),
            range=[x_lo, x_hi],
            **_score_tick_settings(),
        ),
        yaxis=dict(
            title=dict(text="GEO readiness proxy"),
            range=[y_lo, y_hi],
            **_score_tick_settings(),
        ),
        margin=dict(t=MARGIN_TOP_SUB, l=62, r=44, b=bot_m),
        height=HEIGHT_GEO_SCATTER if dens_on else HEIGHT_GEO_SCATTER_NODE,
        showlegend=len(x) >= 2,
        legend={**LEGEND_BELOW_PLOT, "y": leg_y},
    )
    if dens_on:
        fig.update_traces(
            colorbar=dict(
                orientation="h",
                x=0.5,
                xanchor="center",
                y=-0.42,
                yanchor="top",
                len=0.85,
                thickness=12,
                title=dict(text="Point density", font=dict(size=12)),
            ),
            selector=dict(type="histogram2dcontour"),
        )
    return fig


def seo_geo_bucketed_bar_figure(
    df: pd.DataFrame,
    *,
    x_col: str = "seo_overall",
    y_col: str = "geo_total",
    n_bins: int = 10,
) -> go.Figure | None:
    """Equal-width bins on observed SEO scores — mean GEO + SE per band (readable when dots stack)."""
    pair = df.dropna(subset=[x_col, y_col]).copy()
    if len(pair) < 6:
        return None
    lo, hi = float(pair[x_col].min()), float(pair[x_col].max())
    span = hi - lo
    if span < 1e-6:
        return None
    n_bins = int(max(4, min(n_bins, len(pair) // 3)))
    edges = np.linspace(lo, hi, n_bins + 1)
    pair["_bin"] = pd.cut(pair[x_col], bins=edges, include_lowest=True, duplicates="drop")
    grp = pair.dropna(subset=["_bin"]).groupby("_bin", observed=True)[y_col]

    mids: list[float] = []
    means: list[float] = []
    errors: list[float] = []
    counts: list[int] = []
    labels: list[str] = []

    def _half_se(s: pd.Series) -> float:
        n = len(s)
        if n <= 1:
            return 0.0
        return float(s.std(ddof=1)) / np.sqrt(n)

    for interval, ys in grp:
        if ys.empty:
            continue
        mids.append((interval.left + interval.right) / 2)
        means.append(float(ys.mean()))
        errors.append(_half_se(ys))
        ct = len(ys)
        counts.append(ct)
        labels.append(f"{interval.left:.0f}-{interval.right:.0f}")

    if len(means) < 2:
        return None

    fig = go.Figure(
        data=[
            go.Bar(
                x=mids,
                width=(edges[1] - edges[0]) * 0.92,
                y=means,
                error_y=dict(type="data", array=errors, visible=True),
                marker_color="#818cf8",
                text=[f"n={c}" for c in counts],
                textposition="outside",
                hovertemplate=(
                    "%{text}<br>Foundation band: %{customdata}<br>Mean GEO proxy: %{y:.2f} ± SEM<extra></extra>"
                ),
                customdata=labels,
                name="Mean readiness",
            )
        ]
    )
    bx_lo, bx_hi = _pad_range(lo, hi, pad_frac=0.04)
    y_max = float(np.nanmax(means) + np.nanmax(errors))
    yr_hi = min(100.5, max(y_max + 6, float(pair[y_col].max()) + 2))
    yr_lo = max(0, float(pair[y_col].min()) - 4)

    fig.update_layout(
        title=_chart_title(
            "Readiness uplift by SEO band<br>"
            "<sup style='font-size:12px;color:#888'>Means ± standard error · n label on bars · spacing auto from bin width</sup>"
        ),
        xaxis=dict(title=dict(text="Foundation bin center"), range=[bx_lo, bx_hi], **_score_tick_settings()),
        yaxis=dict(title=dict(text="Mean readiness (GEO proxy)"), range=[yr_lo, yr_hi], **_score_tick_settings()),
        showlegend=False,
        margin=dict(t=MARGIN_TOP_SUB, l=56, r=40, b=62),
        height=HEIGHT_GEO_BUCKET,
        bargap=0.12,
    )
    return fig
