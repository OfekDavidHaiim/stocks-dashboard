import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import yfinance as yf


def _fmt_money(val: float, sym: str = "$") -> str:
    if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
        return "N/A"
    sign = "-" if val < 0 else ""
    av = abs(float(val))
    if av >= 1e12:
        return f"{sign}{sym}{av / 1e12:.2f}T"
    if av >= 1e9:
        return f"{sign}{sym}{av / 1e9:.2f}B"
    if av >= 1e6:
        return f"{sign}{sym}{av / 1e6:.1f}M"
    if av >= 1e3:
        return f"{sign}{sym}{av / 1e3:.1f}K"
    return f"{sign}{sym}{av:,.2f}"


def _pick_row_val(row: pd.Series, candidates: list):
    for c in candidates:
        if c in row.index:
            v = pd.to_numeric(row.get(c), errors="coerce")
            if pd.notna(v) and np.isfinite(float(v)):
                return float(v)
    return None


# ==============================================================================
# FEATURE 1: INTERACTIVE SANKEY INCOME STATEMENT (APP ECONOMY INSIGHTS STYLE)
# ==============================================================================

def create_sankey_income_statement(
    df_fin: pd.DataFrame,
    selected_period,
    ticker_symbol: str = "",
    currency_sym: str = "$",
    lang: str = "en",
):
    """
    Build an interactive App Economy Insights-style Plotly Sankey diagram
    visualizing how Total Revenue flows into Cost of Revenue, Gross Profit,
    Operating Expenses (R&D, SG&A, Other), Operating Income, Tax/Interest, and Net Income.
    """
    if df_fin is None or df_fin.empty or selected_period not in df_fin.index:
        return None

    row = df_fin.loc[selected_period]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[-1]

    rev = _pick_row_val(row, ["Total Revenue", "Operating Revenue", "Revenue"])
    if rev is None or rev <= 0:
        return None

    cor = _pick_row_val(row, ["Cost Of Revenue", "Cost of Revenue", "Reconciled Cost Of Revenue"])
    gp = _pick_row_val(row, ["Gross Profit"])
    op_inc = _pick_row_val(row, ["Operating Income", "EBIT", "Total Operating Income As Reported"])
    ni = _pick_row_val(row, ["Net Income", "Net Income Common Stockholders", "Normalized Income"])
    rd = _pick_row_val(row, ["Research And Development"])
    sga = _pick_row_val(row, ["Selling General And Administration", "General And Administrative Expense"])
    tax = _pick_row_val(row, ["Tax Provision"])
    interest = _pick_row_val(row, ["Interest Expense", "Net Interest Income"])

    # Fill missing identities cleanly
    if gp is None and cor is not None:
        gp = rev - abs(cor)
    if cor is None and gp is not None:
        cor = max(0.0, rev - gp)
    if cor is not None and cor < 0:
        cor = abs(cor)
    if op_inc is None and ni is not None:
        op_inc = ni

    is_he = (lang == "he")

    def _lbl(en_name, he_name, val):
        name = he_name if is_he else en_name
        pct = (val / rev) * 100.0 if rev > 0 else 0.0
        return f"{name}<br>{_fmt_money(val, currency_sym)} ({pct:.1f}%)"

    nodes = []
    node_colors = []
    sources = []
    targets = []
    values = []
    link_colors = []

    def _add_node(label: str, color: str) -> int:
        idx = len(nodes)
        nodes.append(label)
        node_colors.append(color)
        return idx

    def _add_link(src: int, tgt: int, val: float, rgba: str):
        if val is not None and val > rev * 0.0005:
            sources.append(src)
            targets.append(tgt)
            values.append(float(val))
            link_colors.append(rgba)

    idx_rev = _add_node(_lbl("Total Revenue", "סך הכנסות", rev), "#2962ff")

    # Stage 1: Revenue -> Cost of Revenue + Gross Profit (or direct for banks without COGS)
    has_gross_split = (gp is not None and gp > 0 and cor is not None and cor > 0)
    if has_gross_split:
        idx_cor = _add_node(_lbl("Cost of Revenue", "עלות ההכנסות", cor), "#f23645")
        idx_gp = _add_node(_lbl("Gross Profit", "רווח גולמי", gp), "#089981")
        _add_link(idx_rev, idx_cor, cor, "rgba(242, 54, 69, 0.35)")
        _add_link(idx_rev, idx_gp, gp, "rgba(8, 153, 129, 0.38)")
        parent_for_op = idx_gp
        parent_pool = gp
    else:
        parent_for_op = idx_rev
        parent_pool = rev

    # Stage 2: Gross Profit (or Revenue) -> Operating Expenses + Operating Income
    if op_inc is not None:
        if op_inc >= 0:
            total_opex = max(0.0, parent_pool - op_inc)
            idx_op = _add_node(_lbl("Operating Income", "רווח תפעולי", op_inc), "#10b981")
            _add_link(parent_for_op, idx_op, op_inc, "rgba(16, 185, 129, 0.42)")

            # Break down OpEx if R&D or SG&A exist
            rd_pos = abs(rd) if (rd is not None and abs(rd) > 0) else 0.0
            sga_pos = abs(sga) if (sga is not None and abs(sga) > 0) else 0.0
            if total_opex > 0 and (rd_pos > 0 or sga_pos > 0) and (rd_pos + sga_pos) <= total_opex * 1.15:
                scale_f = min(1.0, total_opex / (rd_pos + sga_pos)) if (rd_pos + sga_pos) > 0 else 1.0
                rd_use = rd_pos * scale_f
                sga_use = sga_pos * scale_f
                other_opex = max(0.0, total_opex - rd_use - sga_use)
                if rd_use > 0:
                    idx_rd = _add_node(_lbl("R&D", "מו״פ (R&D)", rd_use), "#f59e0b")
                    _add_link(parent_for_op, idx_rd, rd_use, "rgba(245, 158, 11, 0.35)")
                if sga_use > 0:
                    idx_sga = _add_node(_lbl("SG&A", "הנהלה ושיווק (SG&A)", sga_use), "#f97316")
                    _add_link(parent_for_op, idx_sga, sga_use, "rgba(249, 115, 22, 0.35)")
                if other_opex > rev * 0.005:
                    idx_oop = _add_node(_lbl("Other OpEx", "הוצאות תפעול אחרות", other_opex), "#fb7185")
                    _add_link(parent_for_op, idx_oop, other_opex, "rgba(251, 113, 133, 0.32)")
            elif total_opex > 0:
                idx_opex = _add_node(_lbl("Operating Expenses", "הוצאות תפעול", total_opex), "#f59e0b")
                _add_link(parent_for_op, idx_opex, total_opex, "rgba(245, 158, 11, 0.35)")

            # Stage 3: Operating Income -> Tax / Interest / Other -> Net Income
            if ni is not None:
                if ni >= 0:
                    if ni <= op_inc:
                        idx_ni = _add_node(_lbl("Net Income", "רווח נקי", ni), "#00d4aa")
                        _add_link(idx_op, idx_ni, ni, "rgba(0, 212, 170, 0.48)")
                        diff_below = op_inc - ni
                        tax_pos = tax if (tax is not None and tax > 0) else 0.0
                        int_pos = abs(interest) if (interest is not None and interest != 0 and abs(interest) < diff_below * 1.1) else 0.0
                        if diff_below > rev * 0.002:
                            if tax_pos > 0 and tax_pos <= diff_below * 1.15:
                                tax_use = min(tax_pos, diff_below)
                                idx_tax = _add_node(_lbl("Income Tax", "מסים", tax_use), "#dc2626")
                                _add_link(idx_op, idx_tax, tax_use, "rgba(220, 38, 38, 0.35)")
                                rem_below = max(0.0, diff_below - tax_use)
                                if rem_below > rev * 0.002:
                                    idx_oth = _add_node(_lbl("Interest & Other", "ריבית ואחר", rem_below), "#94a3b8")
                                    _add_link(idx_op, idx_oth, rem_below, "rgba(148, 163, 184, 0.30)")
                            else:
                                idx_ti = _add_node(_lbl("Tax, Interest & Other", "מס, ריבית ואחר", diff_below), "#dc2626")
                                _add_link(idx_op, idx_ti, diff_below, "rgba(220, 38, 38, 0.35)")
                    else:
                        # Net Income > Operating Income (non-operating gains / interest income)
                        extra_inc = ni - op_inc
                        idx_nonop = _add_node(_lbl("Non-Op / Other Income", "הכנסות מימון / אחרות", extra_inc), "#38bdf8")
                        idx_ni = _add_node(_lbl("Net Income", "רווח נקי", ni), "#00d4aa")
                        _add_link(idx_op, idx_ni, op_inc, "rgba(0, 212, 170, 0.48)")
                        _add_link(idx_nonop, idx_ni, extra_inc, "rgba(56, 189, 248, 0.42)")
                else:
                    # Positive Operating Income but Net Loss
                    idx_loss = _add_node(_lbl("Tax, Interest & Net Loss", "הפסד נקי / הוצאות מימון", op_inc + abs(ni)), "#ef4444")
                    _add_link(idx_op, idx_loss, op_inc, "rgba(239, 68, 68, 0.40)")
        else:
            # Operating Loss
            total_opex = parent_pool + abs(op_inc)
            idx_opex = _add_node(_lbl("Operating Expenses", "הוצאות תפעול", total_opex), "#f59e0b")
            idx_oploss = _add_node(_lbl("Operating Loss", "הפסד תפעולי", abs(op_inc)), "#ef4444")
            _add_link(parent_for_op, idx_opex, parent_pool, "rgba(245, 158, 11, 0.35)")
            _add_link(idx_oploss, idx_opex, abs(op_inc), "rgba(239, 68, 68, 0.38)")

    if not sources:
        return None

    title_txt = (
        f"🌊 זרימת דוח רווח והפסד (Sankey) — {ticker_symbol} ({selected_period})"
        if is_he
        else f"🌊 Income Statement Flow (Sankey) — {ticker_symbol} ({selected_period})"
    )

    fig = go.Figure(data=[go.Sankey(
        arrangement="snap",
        node=dict(
            pad=22,
            thickness=22,
            line=dict(color="#131722", width=1.5),
            label=nodes,
            color=node_colors,
            hovertemplate="%{label}<extra></extra>",
        ),
        link=dict(
            source=sources,
            target=targets,
            value=values,
            color=link_colors,
            hovertemplate="%{source.label} → %{target.label}<br><b>" + currency_sym + "%{value:,.0f}</b><extra></extra>",
        ),
    )])

    fig.update_layout(
        title=dict(
            text=f"<b>{title_txt}</b>",
            font=dict(size=16, color="#ffffff", family="Outfit, Rubik, sans-serif"),
            x=0.0,
        ),
        font=dict(size=12, color="#ffffff", family="Outfit, Rubik, sans-serif"),
        paper_bgcolor="#1c2030",
        plot_bgcolor="#131722",
        height=450,
        margin=dict(t=55, b=20, l=20, r=20),
    )
    return fig


# ==============================================================================
# RESTORED QUALTRIM-STYLE YOY GROWTH (%) BAR CHART (WITH YTD APPLES-TO-APPLES)
# ==============================================================================

def create_yoy_growth_bar_chart(
    df_full: pd.DataFrame,
    column_name: str,
    title: str,
    is_quarterly: bool = True,
    max_periods: int = 40,
    bar_color: str = "#f24e4e",
    neg_color: str = "#991b1b",
    growth_mode: str = "yoy",
    x_label: str = None,
    df_q_for_ytd: pd.DataFrame = None,
    partial_meta: dict = None,
):
    """
    Create a Qualtrim-style YoY / QoQ percentage growth bar chart.
    Supports apples-to-apples YTD YoY comparison when Annual view includes a partial year.
    """
    if df_full is None or df_full.empty or column_name not in df_full.columns:
        return None

    s = pd.to_numeric(df_full[column_name], errors="coerce").dropna()
    if len(s) < 2:
        return None

    g_series = pd.Series(dtype=float)
    if is_quarterly and growth_mode == "yoy":
        g_dict = {}
        s_map = {str(k): float(v) for k, v in s.items()}
        for k_str, curr_val in s_map.items():
            try:
                prev_k = (pd.Period(k_str, freq="Q") - 4).strftime("%YQ%q")
                if prev_k in s_map and s_map[prev_k] != 0:
                    g_dict[k_str] = ((curr_val - s_map[prev_k]) / abs(s_map[prev_k])) * 100.0
            except Exception:
                pass
        if g_dict:
            g_series = pd.Series(g_dict)
        else:
            lag = 4 if len(s) > 4 else 1
            prev_s = s.shift(lag).abs().replace(0, np.nan)
            g_series = ((s.diff(lag)) / prev_s) * 100.0
            g_series = g_series.dropna()
    else:
        prev_s = s.shift(1).abs().replace(0, np.nan)
        g_series = ((s.diff(1)) / prev_s) * 100.0
        g_series = g_series.dropna()

        # Apples-to-apples YoY for partial YTD year in Annual mode
        if (
            not is_quarterly
            and partial_meta
            and partial_meta.get("n_quarters", 4) < 4
            and df_q_for_ytd is not None
            and not df_q_for_ytd.empty
            and column_name in df_q_for_ytd.columns
        ):
            p_yr = partial_meta.get("year")
            p_qs = partial_meta.get("quarters", [])
            if p_yr in g_series.index and p_qs:
                prev_qs = []
                for q_str in p_qs:
                    try:
                        prev_qs.append((pd.Period(q_str, freq="Q") - 4).strftime("%YQ%q"))
                    except Exception:
                        pass
                curr_vals = pd.to_numeric(df_q_for_ytd.loc[[q for q in p_qs if q in df_q_for_ytd.index], column_name], errors="coerce").dropna()
                prev_vals = pd.to_numeric(df_q_for_ytd.loc[[q for q in prev_qs if q in df_q_for_ytd.index], column_name], errors="coerce").dropna()
                if len(curr_vals) == len(prev_vals) and len(prev_vals) > 0 and prev_vals.sum() != 0:
                    g_series.loc[p_yr] = ((curr_vals.sum() - prev_vals.sum()) / abs(prev_vals.sum())) * 100.0

    if g_series.empty:
        return None

    g_series = g_series.tail(max_periods)
    raw_vals = [float(v) for v in g_series.values]

    p_yr_lbl = partial_meta.get("year") if (partial_meta and partial_meta.get("n_quarters", 4) < 4) else None
    p_nq_lbl = partial_meta.get("n_quarters", 0) if partial_meta else 0

    x_cats = []
    for idx in g_series.index:
        if not is_quarterly and p_yr_lbl is not None and idx == p_yr_lbl:
            x_cats.append(f"{p_yr_lbl} ({p_nq_lbl}Q YTD)")
        else:
            s_idx = str(idx)
            if "Q" in s_idx and " Q" not in s_idx:
                s_idx = s_idx.replace("Q", " Q")
            x_cats.append(s_idx)

    abs_sorted = sorted(abs(v) for v in raw_vals)
    med_abs = abs_sorted[len(abs_sorted) // 2] if abs_sorted else 20.0
    cap_limit = max(250.0, med_abs * 5.0) if med_abs < 80.0 else 1000.0
    plot_vals = [max(-cap_limit, min(cap_limit, v)) for v in raw_vals]

    colors = [bar_color if v >= 0 else neg_color for v in raw_vals]
    show_bar_text = len(x_cats) <= 14
    bar_texts = [f"{v:+.1f}%" for v in raw_vals] if show_bar_text else None

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=x_cats,
        y=plot_vals,
        customdata=raw_vals,
        name=title,
        marker=dict(color=colors, line=dict(width=0), cornerradius=4),
        text=bar_texts,
        textposition="outside" if show_bar_text else "none",
        textfont=dict(size=11, color="#d1d4dc", family="Outfit, Rubik, sans-serif"),
        cliponaxis=False,
        hovertemplate="<b>%{x}</b><br>Value: %{customdata:.2f}%<extra></extra>",
    ))

    fig.add_hline(y=0, line_color="rgba(255, 255, 255, 0.22)", line_width=1)

    fig.update_layout(
        title=dict(text=f"<b>{title}</b>", font=dict(size=16, color="#ffffff", family="Outfit, Rubik, sans-serif"), x=0.0),
        xaxis=dict(
            title=x_label or "",
            type="category",
            categoryorder="array",
            categoryarray=x_cats,
            showgrid=False,
            tickangle=0,
            nticks=14 if len(x_cats) > 16 else len(x_cats),
            tickfont=dict(color="#848e9c", size=11),
        ),
        yaxis=dict(
            title="",
            ticksuffix="%",
            showgrid=True,
            gridcolor="rgba(255, 255, 255, 0.06)",
            zeroline=True,
            zerolinecolor="rgba(255, 255, 255, 0.22)",
            tickfont=dict(color="#848e9c", size=11),
        ),
        hoverlabel=dict(bgcolor="#131722", bordercolor="#2a2e39", font=dict(color="#ffffff", size=13, family="Outfit, Rubik, sans-serif")),
        hovermode="x unified",
        bargap=0.22,
        height=370,
        showlegend=False,
        paper_bgcolor="#1c2030",
        plot_bgcolor="#131722",
        margin=dict(t=55, b=35, l=50, r=20),
    )
    return fig


# ==============================================================================
# FEATURE 3A: 10-YEAR HISTORICAL VALUATION PRICE BANDS (FASTGRAPHS / PETER LYNCH)
# ==============================================================================

def _build_daily_ttm_per_share(
    history: pd.DataFrame,
    df_q: pd.DataFrame,
    df_a: pd.DataFrame,
    col_candidates: list,
    hist_shares: pd.Series,
    is_already_per_share: bool = False,
    fx_fin_to_trade: float = 1.0,
    fx_series: pd.Series = None,
    fin_curr: str = "USD",
    trade_curr: str = "USD",
    partial_yr: int = None,
) -> pd.Series:
    """Build a daily TTM per-share fundamental series aligned with `history.index` in trading currency."""
    h_idx_naive = pd.to_datetime(history.index).tz_localize(None)
    ttm_pts = pd.Series(dtype=float)

    if df_q is not None and not df_q.empty:
        col_q = next((c for c in col_candidates if c in df_q.columns), None)
        if col_q:
            sq = pd.to_numeric(df_q[col_q], errors="coerce").dropna()
            if len(sq) >= 4:
                ttm_q = sq.rolling(4, min_periods=4).sum().dropna()
                if not ttm_q.empty:
                    q_dates = pd.PeriodIndex(ttm_q.index, freq="Q").end_time.tz_localize(None)
                    ttm_pts = pd.Series(ttm_q.values, index=q_dates)

    ann_pts = pd.Series(dtype=float)
    if df_a is not None and not df_a.empty:
        df_a_full = df_a[df_a.index != partial_yr] if partial_yr is not None else df_a
        col_a = next((c for c in col_candidates if c in df_a_full.columns), None)
        if col_a:
            sa = pd.to_numeric(df_a_full[col_a], errors="coerce").dropna()
            if not sa.empty:
                a_dates = pd.to_datetime([f"{int(y)}-12-31" for y in sa.index if str(y).isdigit()])
                if len(a_dates) == len(sa):
                    ann_pts = pd.Series(sa.values, index=a_dates)

    combined = ttm_pts.combine_first(ann_pts).sort_index() if not ttm_pts.empty else ann_pts.sort_index()
    combined = combined[~combined.index.duplicated(keep="last")]
    if combined.empty:
        return pd.Series(dtype=float)

    daily = combined.reindex(h_idx_naive.union(combined.index)).sort_index().ffill().bfill().reindex(h_idx_naive)

    # Convert from financial currency to trading currency
    if fin_curr != trade_curr:
        if fx_series is not None and not fx_series.empty:
            h_norm = pd.to_datetime(h_idx_naive).normalize()
            fx_d = fx_series.reindex(h_norm.union(fx_series.index)).sort_index().ffill().bfill().reindex(h_norm)
            fx_d = fx_d.where(fx_d > 0, fx_fin_to_trade)
            daily = pd.Series(daily.values * fx_d.values, index=h_idx_naive)
        else:
            daily = daily * fx_fin_to_trade

    daily.index = history.index
    if not is_already_per_share:
        valid_sh = hist_shares.reindex(history.index).ffill().bfill().replace(0, np.nan)
        daily = daily / valid_sh

    return daily


def create_valuation_bands_chart(
    history: pd.DataFrame,
    df_fin_a: pd.DataFrame,
    df_fin_q: pd.DataFrame,
    df_cf_a: pd.DataFrame,
    df_cf_q: pd.DataFrame,
    hist_shares: pd.Series,
    info: dict,
    ticker_symbol: str,
    band_metric: str = "P/E",
    currency_sym: str = "$",
    fx_fin_to_trade: float = 1.0,
    fx_series: pd.Series = None,
    fin_curr: str = "USD",
    trade_curr: str = "USD",
    lang: str = "en",
):
    """
    Create a FastGraphs / Peter Lynch style 10-Year Historical Valuation Price Bands chart.
    Overlays 5 dynamically calibrated valuation multiple channels (e.g. 15x, 20x, 25x, 30x, 35x EPS)
    directly on top of the stock's 10-year daily price curve.
    Returns (fig, stats_dict).
    """
    if history is None or history.empty or "Close" not in history.columns:
        return None, {}

    p_meta = info.get("_partial_year_meta") if info else None
    partial_yr = p_meta.get("year") if (p_meta and p_meta.get("n_quarters", 4) < 4) else None

    if band_metric == "P/E":
        fund_ps = _build_daily_ttm_per_share(
            history, df_fin_q, df_fin_a, ["Diluted EPS", "Basic EPS"], hist_shares,
            is_already_per_share=True, fx_fin_to_trade=fx_fin_to_trade, fx_series=fx_series,
            fin_curr=fin_curr, trade_curr=trade_curr, partial_yr=partial_yr,
        )
        m_cap = 150.0
        step_round = 1.0
        unit_name = "EPS"
    elif band_metric == "P/FCF":
        fund_ps = _build_daily_ttm_per_share(
            history, df_cf_q, df_cf_a, ["Free Cash Flow"], hist_shares,
            is_already_per_share=False, fx_fin_to_trade=fx_fin_to_trade, fx_series=fx_series,
            fin_curr=fin_curr, trade_curr=trade_curr, partial_yr=partial_yr,
        )
        m_cap = 150.0
        step_round = 1.0
        unit_name = "FCF/Sh"
    else:  # P/S
        fund_ps = _build_daily_ttm_per_share(
            history, df_fin_q, df_fin_a, ["Total Revenue", "Operating Revenue"], hist_shares,
            is_already_per_share=False, fx_fin_to_trade=fx_fin_to_trade, fx_series=fx_series,
            fin_curr=fin_curr, trade_curr=trade_curr, partial_yr=partial_yr,
        )
        m_cap = 60.0
        step_round = 0.5
        unit_name = "Rev/Sh"

    if fund_ps.empty:
        return None, {}

    df_plot = pd.DataFrame({"Close": history["Close"], "Fund": fund_ps}).dropna()
    df_plot = df_plot[df_plot["Fund"] > 0]
    if len(df_plot) < 30:
        return None, {}

    # Downsample slightly for crisp fast rendering on 10Y daily data (weekly Friday/last points)
    df_plot["Mult"] = df_plot["Close"] / df_plot["Fund"]
    valid_mults = df_plot["Mult"][(df_plot["Mult"] > 0) & (df_plot["Mult"] <= m_cap)]
    if len(valid_mults) < 20:
        return None, {}

    p10, p30, p50, p70, p90 = np.percentile(valid_mults, [10, 30, 50, 70, 90])

    def _nice(x):
        if step_round >= 1.0:
            if x >= 40:
                return round(x / 5.0) * 5.0
            return max(1.0, round(x))
        return max(0.5, round(x * 2.0) / 2.0)

    raw_levels = [_nice(v) for v in (p10, p30, p50, p70, p90)]
    # Ensure strictly increasing 5 bands
    bands = [raw_levels[0]]
    min_gap = 2.0 if band_metric != "P/S" else 0.5
    for lv in raw_levels[1:]:
        if lv <= bands[-1]:
            lv = bands[-1] + min_gap
        bands.append(lv)

    # Resample to weekly for smooth, lightweight rendering while preserving the latest point
    df_w = df_plot.resample("W-FRI").last().dropna()
    if df_plot.index[-1] not in df_w.index:
        df_w = pd.concat([df_w, df_plot.iloc[[-1]]])

    curr_mult = float(df_plot["Mult"].iloc[-1])
    med_mult = float(p50)
    pct_rank = float((valid_mults < curr_mult).mean() * 100.0)
    curr_fair_price = float(df_plot["Fund"].iloc[-1] * med_mult)

    is_he = (lang == "he")
    if pct_rank <= 25:
        status_en, status_he, status_col = "Historically Cheap (Deep Value Zone)", "זולה היסטורית (אזור ערך עמוק)", "#089981"
    elif pct_rank <= 45:
        status_en, status_he, status_col = "Below Historical Median (Attractive)", "מתחת לחציון ההיסטורי (אטרקטיבית)", "#10b981"
    elif pct_rank <= 65:
        status_en, status_he, status_col = "Fairly Valued (Near Median)", "שווי הוגן (קרוב לחציון ההיסטורי)", "#f0b90b"
    elif pct_rank <= 85:
        status_en, status_he, status_col = "Above Historical Median (Rich)", "מעל החציון ההיסטורי (יקרה יחסית)", "#f97316"
    else:
        status_en, status_he, status_col = "Historically Expensive (Stretched)", "יקרה היסטורית (אזור מתוח)", "#f23645"

    band_colors = [
        ("#089981", "rgba(8, 153, 129, 0.10)"),    # Deep Value (p10)
        ("#22c55e", "rgba(34, 197, 94, 0.10)"),    # Value (p30)
        ("#f0b90b", "rgba(240, 185, 11, 0.10)"),   # Fair Median (p50)
        ("#f97316", "rgba(249, 115, 22, 0.10)"),   # Rich (p70)
        ("#f23645", "rgba(242, 54, 69, 0.10)"),    # Stretched (p90)
    ]

    fig = go.Figure()

    for i, mult_val in enumerate(bands):
        line_c, fill_c = band_colors[i]
        m_fmt = f"{mult_val:.0f}x" if mult_val == int(mult_val) else f"{mult_val:.1f}x"
        lbl_tag = f"{m_fmt} {unit_name}" + (" (Median)" if i == 2 else "")
        fig.add_trace(go.Scatter(
            x=df_w.index,
            y=df_w["Fund"] * mult_val,
            mode="lines",
            name=lbl_tag,
            line=dict(color=line_c, width=2.0 if i == 2 else 1.2, dash="solid" if i == 2 else "dot"),
            fill="tonexty" if i > 0 else None,
            fillcolor=fill_c if i > 0 else None,
            hovertemplate=f"{lbl_tag}: {currency_sym}%{{y:,.2f}}<extra></extra>",
        ))

    # Plot actual Stock Price prominently on top
    fig.add_trace(go.Scatter(
        x=df_w.index,
        y=df_w["Close"],
        mode="lines",
        name=f"{ticker_symbol} Price",
        line=dict(color="#ffffff", width=2.8),
        hovertemplate=f"<b>{ticker_symbol}</b>: {currency_sym}%{{y:,.2f}}<extra></extra>",
    ))

    chart_title = (
        f"📈 רצועות שווי היסטוריות ({band_metric}) — {ticker_symbol} (10 שנים)"
        if is_he
        else f"📈 10-Year Historical Valuation Price Bands ({band_metric}) — {ticker_symbol}"
    )

    fig.update_layout(
        title=dict(text=f"<b>{chart_title}</b>", font=dict(size=16, color="#ffffff", family="Outfit, Rubik, sans-serif"), x=0.0),
        xaxis=dict(title="", showgrid=True, gridcolor="rgba(255,255,255,0.05)", tickfont=dict(color="#848e9c")),
        yaxis=dict(title=f"Price ({currency_sym})", showgrid=True, gridcolor="rgba(255,255,255,0.06)", tickprefix=currency_sym, tickfont=dict(color="#848e9c")),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color="#d1d4dc", size=11)),
        paper_bgcolor="#1c2030",
        plot_bgcolor="#131722",
        height=470,
        margin=dict(t=65, b=30, l=55, r=25),
    )

    stats = {
        "current_multiple": round(curr_mult, 2),
        "median_multiple": round(med_mult, 2),
        "percentile": round(pct_rank, 1),
        "fair_price_at_median": round(curr_fair_price, 2),
        "status_en": status_en,
        "status_he": status_he,
        "status_color": status_col,
        "bands": bands,
    }
    return fig, stats


# ==============================================================================
# FEATURE 3B: EARNINGS SURPRISE & POST-EARNINGS MOVE TRACKER
# ==============================================================================

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_earnings_surprise_data(ticker_symbol: str):
    """
    Fetch historical quarterly EPS Estimate vs Reported EPS and upcoming earnings date.
    Uses crumb-free, SSL-safe direct APIs (Nasdaq Earnings Surprise API + TradingView Scanner API)
    as primary sources, enriched with yfinance earnings_dates when available.
    Returns (df_surprises, next_earnings_dict).
    """
    import requests as _req

    df_out = pd.DataFrame()
    next_info = {"date": None, "days_until": None, "eps_estimate": None}
    sym = (ticker_symbol or "").strip().upper()
    if not sym:
        return df_out, next_info

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    now_ts = pd.Timestamp.now().normalize()
    rows = []

    # 1. TradingView Scanner API -> exact Next Earnings Date + Next Quarter EPS Consensus Estimate
    try:
        tv_market = "israel" if sym.endswith(".TA") else "america"
        tv_sym = sym[:-3] if sym.endswith(".TA") else sym.replace("-", ".")
        tv_resp = _req.post(
            f"https://scanner.tradingview.com/{tv_market}/scan",
            json={
                "filter": [{"left": "name", "operation": "equal", "right": tv_sym}],
                "columns": ["name", "earnings_release_next_date", "earnings_per_share_forecast_next_fq"],
                "range": [0, 1],
            },
            headers=headers,
            timeout=8,
        )
        if tv_resp.status_code == 200:
            items = tv_resp.json().get("data", [])
            if items:
                d_vals = items[0].get("d", [])
                if len(d_vals) >= 3:
                    nxt_ts = d_vals[1]
                    nxt_est = d_vals[2]
                    if nxt_ts:
                        nxt_dt = pd.to_datetime(int(nxt_ts), unit="s", utc=True).tz_localize(None).normalize()
                        days_u = int((nxt_dt - now_ts).days)
                        if days_u >= -1:
                            next_info["date"] = nxt_dt.strftime("%Y-%m-%d")
                            next_info["days_until"] = days_u
                    if nxt_est is not None:
                        try:
                            next_info["eps_estimate"] = float(nxt_est)
                        except Exception:
                            pass
    except Exception:
        pass

    # 2. Nasdaq Earnings Surprise API (US equities — crumb-free, exact Date Reported + Consensus + Actual)
    if not sym.endswith(".TA"):
        try:
            r_nq = _req.get(
                f"https://api.nasdaq.com/api/company/{sym.replace('-', '.')}/earnings-surprise",
                headers=headers,
                timeout=10,
            )
            if r_nq.status_code == 200:
                tbl_rows = (r_nq.json().get("data") or {}).get("earningsSurpriseTable", {}).get("rows") or []
                for tr_r in tbl_rows:
                    try:
                        dt_rep = pd.to_datetime(tr_r.get("dateReported")).tz_localize(None)
                        eps_act = pd.to_numeric(tr_r.get("eps"), errors="coerce")
                        eps_est = pd.to_numeric(tr_r.get("consensusForecast"), errors="coerce")
                        surp_p = pd.to_numeric(tr_r.get("percentageSurprise"), errors="coerce")
                        if pd.notna(eps_act) and pd.notna(eps_est):
                            if pd.isna(surp_p) and abs(eps_est) > 1e-6:
                                surp_p = ((eps_act - eps_est) / abs(eps_est)) * 100.0
                            fq_end = tr_r.get("fiscalQtrEnd") or ""
                            try:
                                q_lbl = pd.to_datetime(fq_end).to_period("Q").strftime("%Y Q%q") if fq_end else dt_rep.to_period("Q").strftime("%Y Q%q")
                            except Exception:
                                q_lbl = dt_rep.to_period("Q").strftime("%Y Q%q")
                            rows.append({
                                "Date": dt_rep,
                                "Quarter": q_lbl,
                                "EPS Estimate": float(eps_est),
                                "Reported EPS": float(eps_act),
                                "Surprise (%)": float(surp_p) if pd.notna(surp_p) else 0.0,
                            })
                    except Exception:
                        continue
        except Exception:
            pass

    # 3. Enrich up to 12 quarters via yfinance when available
    try:
        tk = yf.Ticker(sym)
        try:
            ed_df = tk.get_earnings_dates(limit=24)
            if ed_df is not None and not ed_df.empty:
                for dt_idx, r in ed_df.iterrows():
                    dt_naive = pd.to_datetime(dt_idx).tz_localize(None)
                    est = pd.to_numeric(r.get("EPS Estimate"), errors="coerce")
                    rep = pd.to_numeric(r.get("Reported EPS"), errors="coerce")
                    if pd.isna(rep) and dt_naive >= now_ts - pd.Timedelta(days=1):
                        if next_info["date"] is None:
                            next_info["date"] = dt_naive.strftime("%Y-%m-%d")
                            next_info["days_until"] = int((dt_naive.normalize() - now_ts).days)
                            if pd.notna(est):
                                next_info["eps_estimate"] = float(est)
                    elif pd.notna(rep) and pd.notna(est):
                        surp = ((rep - est) / abs(est)) * 100.0 if abs(est) > 1e-6 else 0.0
                        rows.append({
                            "Date": dt_naive,
                            "Quarter": dt_naive.to_period("Q").strftime("%Y Q%q"),
                            "EPS Estimate": float(est),
                            "Reported EPS": float(rep),
                            "Surprise (%)": float(surp),
                        })
        except Exception:
            pass
    except Exception:
        pass

    if rows:
        df_out = pd.DataFrame(rows).sort_values("Date").drop_duplicates(subset=["Quarter"], keep="first").tail(12)

    return df_out, next_info


def create_earnings_surprise_chart(
    df_surp: pd.DataFrame,
    history: pd.DataFrame,
    ticker_symbol: str,
    currency_sym: str = "$",
    lang: str = "en",
):
    """
    Create a 2-row institutional Earnings Surprise & Post-Earnings Reaction chart:
    - Row 1: EPS Estimate vs Actual EPS dots + Beat/Miss Surprise %
    - Row 2: 1-Day Post-Earnings Stock Price Move (%)
    Returns (fig, enriched_df, summary_dict).
    """
    if df_surp is None or df_surp.empty:
        return None, pd.DataFrame(), {}

    df = df_surp.copy().reset_index(drop=True)

    # Compute 1-Day post-earnings price move from `history`
    post_moves = []
    if history is not None and not history.empty and "Close" in history.columns:
        h_idx = pd.to_datetime(history.index).tz_localize(None).normalize()
        closes = history["Close"].values
        for _, row in df.iterrows():
            ed = pd.to_datetime(row["Date"]).normalize()
            pos = int(np.searchsorted(h_idx, ed))
            move_pct = np.nan
            if 0 < pos < len(closes):
                # If announcement was after market close (hour >= 15) or on date `pos`, compare next trading day vs prior close
                hr = pd.to_datetime(row["Date"]).hour
                if hr >= 15 and pos + 1 < len(closes):
                    prev_c = float(closes[pos])
                    next_c = float(closes[pos + 1])
                else:
                    prev_c = float(closes[pos - 1])
                    next_c = float(closes[pos])
                if prev_c > 0:
                    move_pct = ((next_c - prev_c) / prev_c) * 100.0
            post_moves.append(move_pct)
    else:
        post_moves = [np.nan] * len(df)

    df["Post-Earnings Move (%)"] = post_moves
    df["Beat"] = df["Reported EPS"] >= df["EPS Estimate"]

    is_he = (lang == "he")
    x_labels = df["Quarter"].tolist()

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.10,
        row_heights=[0.62, 0.38],
        subplot_titles=(
            ("תחזית EPS מול בפועל (Beat / Miss)" if is_he else "EPS Estimate vs. Reported Actual (Beat / Miss)"),
            ("תגובת המניה יום אחרי הדוח (%)" if is_he else "1-Day Post-Earnings Stock Move (%)"),
        ),
    )

    # Row 1: Estimate markers (hollow circle) + Actual markers (green Beat / red Miss)
    fig.add_trace(
        go.Scatter(
            x=x_labels,
            y=df["EPS Estimate"],
            mode="markers",
            name="צפי אנליסטים (Estimate)" if is_he else "EPS Estimate",
            marker=dict(size=13, color="#131722", line=dict(color="#94a3b8", width=2.5), symbol="circle"),
            hovertemplate="<b>%{x}</b><br>Estimate: " + currency_sym + "%{y:.2f}<extra></extra>",
        ),
        row=1, col=1,
    )

    act_colors = ["#089981" if b else "#f23645" for b in df["Beat"]]
    surp_texts = [f"{s:+.1f}%" for s in df["Surprise (%)"]]
    fig.add_trace(
        go.Scatter(
            x=x_labels,
            y=df["Reported EPS"],
            mode="markers+text",
            name="תוצאה בפועל (Actual)" if is_he else "Reported EPS",
            marker=dict(size=13, color=act_colors, line=dict(color="#ffffff", width=1.2)),
            text=surp_texts,
            textposition="top center",
            textfont=dict(size=10, color="#d1d4dc", family="Outfit, Rubik, sans-serif"),
            customdata=df["Surprise (%)"],
            hovertemplate="<b>%{x}</b><br>Actual: " + currency_sym + "%{y:.2f}<br>Surprise: %{customdata:+.2f}%<extra></extra>",
        ),
        row=1, col=1,
    )

    # Row 2: Post-earnings 1-day reaction bars
    mv_vals = [0.0 if pd.isna(v) else float(v) for v in df["Post-Earnings Move (%)"]]
    mv_colors = ["#089981" if v >= 0 else "#f23645" for v in mv_vals]
    mv_texts = [f"{v:+.1f}%" if pd.notna(orig) else "" for v, orig in zip(mv_vals, df["Post-Earnings Move (%)"])]

    fig.add_trace(
        go.Bar(
            x=x_labels,
            y=mv_vals,
            name="תגובת מניה (%)" if is_he else "1-Day Move (%)",
            marker=dict(color=mv_colors, cornerradius=4),
            text=mv_texts,
            textposition="outside",
            textfont=dict(size=10, color="#d1d4dc"),
            cliponaxis=False,
            hovertemplate="<b>%{x}</b><br>1-Day Reaction: %{y:+.2f}%<extra></extra>",
        ),
        row=2, col=1,
    )

    fig.add_hline(y=0, line_color="rgba(255,255,255,0.22)", line_width=1, row=2, col=1)

    title_txt = (
        f"🎯 מעקב דוחות רבעוניים, הפתעות EPS ותגובת מניה — {ticker_symbol}"
        if is_he
        else f"🎯 Earnings Surprise & Post-Earnings Reaction Tracker — {ticker_symbol}"
    )

    fig.update_layout(
        title=dict(text=f"<b>{title_txt}</b>", font=dict(size=16, color="#ffffff", family="Outfit, Rubik, sans-serif"), x=0.0),
        paper_bgcolor="#1c2030",
        plot_bgcolor="#131722",
        height=520,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.04, xanchor="right", x=1, font=dict(color="#d1d4dc", size=11)),
        margin=dict(t=80, b=30, l=50, r=25),
    )
    fig.update_yaxes(title_text=f"EPS ({currency_sym})", tickprefix=currency_sym, gridcolor="rgba(255,255,255,0.06)", row=1, col=1)
    fig.update_yaxes(title_text="1D Move %", ticksuffix="%", gridcolor="rgba(255,255,255,0.06)", row=2, col=1)
    fig.update_xaxes(type="category", tickfont=dict(color="#848e9c", size=11))

    n_beats = int(df["Beat"].sum())
    n_total = len(df)
    valid_mv = df["Post-Earnings Move (%)"].dropna()
    summary = {
        "beats": n_beats,
        "total": n_total,
        "beat_rate": round((n_beats / n_total) * 100.0, 1) if n_total > 0 else 0.0,
        "avg_surprise": round(float(df["Surprise (%)"].mean()), 2),
        "avg_post_move": round(float(valid_mv.mean()), 2) if not valid_mv.empty else None,
        "avg_abs_move": round(float(valid_mv.abs().mean()), 2) if not valid_mv.empty else None,
    }
    return fig, df, summary
