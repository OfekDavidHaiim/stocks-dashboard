import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def _sfloat(val):
    try:
        if val is None or pd.isna(val):
            return None
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except Exception:
        return None


def _estimate_screener_fair_value(row: dict):
    """
    Fast multi-model intrinsic value consensus directly from screener financial metrics:
      1. DCF-20 (Operating Cash Flow)
      2. DFCF-20 (Free Cash Flow)
      3. DNI-20 (Net Income / EPS)
      4. DFCF-Terminal (Gordon Growth)
      5. Fair PEG = 1.0 (EPS * growth)
      6. Fair PSG (Revenue/Share * margin-calibrated fair PS)
    Returns (fair_value, margin_of_safety_pct) or (None, None).
    """
    price = _sfloat(row.get("current_price"))
    if not price or price <= 0:
        return None, None

    sh = _sfloat(row.get("shares_outstanding"))
    mcap = _sfloat(row.get("market_cap"))
    if (not sh or sh <= 0) and mcap and mcap > 0:
        sh = mcap / price
    if not sh or sh <= 0:
        return None, None

    rev = _sfloat(row.get("total_revenue")) or 0.0
    ni = _sfloat(row.get("net_income")) or 0.0
    ocf = _sfloat(row.get("operating_cash_flow")) or 0.0
    fcf = _sfloat(row.get("free_cash_flow")) or 0.0
    debt = _sfloat(row.get("total_debt")) or 0.0
    cash = _sfloat(row.get("total_cash")) or 0.0
    eps = _sfloat(row.get("diluted_eps"))
    if eps is None or eps <= 0:
        eps = (ni / sh) if ni > 0 else 0.0

    rev_g = _sfloat(row.get("revenue_cagr"))
    if rev_g is None:
        rev_g = _sfloat(row.get("revenue_growth"))
    if rev_g is None:
        rev_g = 8.0
    rev_g = min(max(rev_g, 3.0), 24.0)

    earn_g = _sfloat(row.get("eps_growth"))
    if earn_g is None:
        earn_g = _sfloat(row.get("earnings_growth"))
    if earn_g is None:
        earn_g = rev_g
    # Blend earnings growth with revenue growth so single-year spikes don't blow up DCF
    base_g = min(max(0.55 * rev_g + 0.45 * min(max(earn_g, 2.0), 30.0), 4.0), 22.0)

    dr = 0.095  # Institutional 9.5% discount rate
    gt_20 = 0.04
    net_cash_ps = (cash - debt) / sh

    def _dcf20(base_ps, g_pct):
        if base_ps <= 0:
            return None
        g = min(max(g_pct, 4.0), 20.0) / 100.0
        x = (1.0 + g) / (1.0 + dr)
        y = (1.0 + gt_20) / (1.0 + dr)
        pv10 = sum(x ** k for k in range(1, 11))
        pv20 = (x ** 10) * sum(y ** k for k in range(1, 11))
        tot = base_ps * (pv10 + pv20)
        return max(tot + net_cash_ps, tot * 0.5)

    vals = []
    ocf_ps = ocf / sh
    fcf_ps = fcf / sh
    rev_ps = rev / sh

    if ocf_ps > 0:
        v = _dcf20(ocf_ps, base_g)
        if v:
            vals.append(v)
    if fcf_ps > 0:
        v = _dcf20(fcf_ps, base_g)
        if v:
            vals.append(v)
        # Gordon Terminal DCF (5Y + terminal 3%)
        g_t = min(max(base_g, 4.0), 22.0) / 100.0
        pv5 = sum((fcf_ps * ((1.0 + g_t) ** k)) / ((1.0 + dr) ** k) for k in range(1, 6))
        tv = (fcf_ps * ((1.0 + g_t) ** 5) * 1.03) / (dr - 0.03)
        pv_tv = tv / ((1.0 + dr) ** 5)
        vals.append(max(pv5 + pv_tv + net_cash_ps, (pv5 + pv_tv) * 0.5))
    if eps > 0:
        v = _dcf20(eps, base_g)
        if v:
            vals.append(v)
        # Fair PEG = 1.0 (capped 10x..32x P/E)
        fair_pe = min(max(base_g * 1.15, 10.0), 32.0)
        vals.append(eps * fair_pe)
    if rev_ps > 0 and ni > 0:
        nm = min(max(ni / rev, 0.04), 0.45)
        fair_ps = min(max(nm * 1.35 * rev_g, 0.8), 16.0)
        vals.append(rev_ps * fair_ps)

    if len(vals) < 2:
        return None, None

    # Use trimmed average to avoid single-model distortion
    vals_sorted = sorted(vals)
    if len(vals_sorted) >= 4:
        fair_v = sum(vals_sorted[1:-1]) / len(vals_sorted[1:-1])
    else:
        fair_v = sum(vals_sorted) / len(vals_sorted)

    mos = ((fair_v - price) / price) * 100.0
    mos = min(max(mos, -85.0), 250.0)
    return round(fair_v, 2), round(mos, 1)


def enrich_screener_universe(cache: dict) -> list:
    """
    Collect all unique stocks from screener cache (`all_stocks` if present, else `top_20` + `by_sector`),
    compute Multi-Model Margin of Safety %, Rule of 40, and Buffett Moat Proxy for each.
    """
    stock_map = {}
    if isinstance(cache.get("all_stocks"), list) and cache["all_stocks"]:
        for r in cache["all_stocks"]:
            t = r.get("ticker")
            if t:
                stock_map[t] = dict(r)
    else:
        for r in cache.get("top_20", []):
            t = r.get("ticker")
            if t:
                stock_map[t] = dict(r)
        for sec_list in cache.get("by_sector", {}).values():
            for r in sec_list:
                t = r.get("ticker")
                if t and t not in stock_map:
                    stock_map[t] = dict(r)

    enriched = []
    for r in stock_map.values():
        fv, mos = _estimate_screener_fair_value(r)
        r["est_fair_value"] = fv
        r["margin_of_safety"] = mos
        rg = _sfloat(r.get("revenue_growth")) or 0.0
        fm = _sfloat(r.get("fcf_margin")) or 0.0
        r["rule_of_40"] = round(rg + fm, 1)
        enriched.append(r)

    enriched.sort(key=lambda x: x.get("composite_score", 0.0), reverse=True)
    return enriched


def render_screener_v2_hub(cache: dict, lang: str = "en"):
    """
    Render Screener 2.0 above/alongside the Sector Leaderboards:
      1. Interactive Finviz-Style S&P 500 & NASDAQ Treemap Heatmap
      2. One-Click Investing Legend Presets (Warren Buffett, Rule of 40, Deep Value Bargains, Cash Cows)
      3. Interactive Multi-Filter Sliders + Quality vs. Margin of Safety Quadrant Chart + Filtered Table
    """
    is_he = (lang == "he")
    all_stocks = enrich_screener_universe(cache)
    if not all_stocks:
        return

    st.markdown(
        f"### 🔥 {'Screener 2.0 — מפת חום (Heatmap), פילטרים חכמים וצייד מציאות' if is_he else 'Screener 2.0 — Interactive Market Heatmap, Legend Presets & Bargain Hunter'}"
    )

    v2_tabs = st.tabs([
        "🗺️ " + ("מפת חום אינטראקטיבית (Finviz Heatmap)" if is_he else "Interactive Sector Heatmap (Treemap)"),
        "🎯 " + ("פילטרים חכמים + Presets של אגדות השקעה" if is_he else "Smart Filters, Legend Presets & Bargain Hunter"),
    ])

    # =========================================================================
    # V2 TAB 1: INTERACTIVE FINVIZ-STYLE TREEMAP HEATMAP
    # =========================================================================
    with v2_tabs[0]:
        hm_c1, hm_c2 = st.columns([2, 1.5])
        color_options = {
            "composite_score": ("ציון איכות כולל (0–100)" if is_he else "Composite Quality Score (0–100)"),
            "margin_of_safety": ("מרווח ביטחון / אפסייד שווי הוגן (%)" if is_he else "Margin of Safety / Valuation Upside (%)"),
            "revenue_growth": ("צמיחת הכנסות שנתית (%)" if is_he else "Revenue Growth YoY (%)"),
            "rule_of_40": ("מדד Rule of 40 (צמיחה + FCF Margin %)" if is_he else "Rule of 40 (Rev Growth + FCF Margin %)"),
        }
        chosen_metric = hm_c1.selectbox(
            "צבע מפת החום לפי:" if is_he else "Color Heatmap By:",
            options=list(color_options.keys()),
            format_func=lambda k: color_options[k],
            key="screener_v2_hm_metric",
        )

        # Quick jump from heatmap to Dashboard
        all_tickers_sorted = sorted([s["ticker"] for s in all_stocks])
        jump_t = hm_c2.selectbox(
            "פתח מניה ממפת החום בדשבורד:" if is_he else "Jump to Stock in Dashboard:",
            options=[""] + all_tickers_sorted,
            format_func=lambda x: ("בחר טיקר לפתיחה..." if is_he else "Select ticker to open...") if x == "" else x,
            key="screener_v2_hm_jump",
        )
        if jump_t:
            st.session_state.selected_ticker = jump_t
            st.session_state.page_selector = "Dashboard"
            st.rerun()

        # Build Treemap hierarchy: Market -> Sector -> Ticker
        ids, labels, parents, vals_sz, vals_col, custom_txt = [], [], [], [], [], []
        root_id = "S&P 500 & NASDAQ"
        ids.append(root_id)
        labels.append(root_id)
        parents.append("")
        vals_sz.append(0.0)
        vals_col.append(50.0 if chosen_metric == "composite_score" else 0.0)
        custom_txt.append(root_id)

        sectors_present = sorted(set(s.get("sector", "Other") or "Other" for s in all_stocks))
        for sec in sectors_present:
            sec_rows = [s for s in all_stocks if (s.get("sector") or "Other") == sec]
            sec_m_vals = [_sfloat(s.get(chosen_metric)) for s in sec_rows if _sfloat(s.get(chosen_metric)) is not None]
            sec_avg = float(np.mean(sec_m_vals)) if sec_m_vals else 0.0
            ids.append(f"SEC::{sec}")
            labels.append(f"<b>{sec}</b>")
            parents.append(root_id)
            vals_sz.append(0.0)
            vals_col.append(sec_avg)
            custom_txt.append(f"Sector: {sec} ({len(sec_rows)} stocks) | Avg: {sec_avg:.1f}")

        for s in all_stocks:
            sec = s.get("sector") or "Other"
            t = s["ticker"]
            mcap = _sfloat(s.get("market_cap")) or 10_000_000_000.0
            cval = _sfloat(s.get(chosen_metric))
            if cval is None:
                cval = 50.0 if chosen_metric == "composite_score" else 0.0
            mos_s = f"{s['margin_of_safety']:+.1f}%" if s.get("margin_of_safety") is not None else "N/A"
            fv_s = f"${s['est_fair_value']:,.2f}" if s.get("est_fair_value") is not None else "N/A"
            pr_s = f"${s.get('current_price', 0):,.2f}"
            mcap_s = f"${mcap/1e12:.2f}T" if mcap >= 1e12 else f"${mcap/1e9:.1f}B"

            val_badge = f"{cval:.1f}" if chosen_metric == "composite_score" else f"{cval:+.1f}%"
            ids.append(t)
            labels.append(f"<b>{t}</b><br>{val_badge}")
            parents.append(f"SEC::{sec}")
            vals_sz.append(max(mcap, 1e9))
            vals_col.append(cval)
            custom_txt.append(
                f"<b>{t} — {s.get('name', t)}</b><br>"
                f"Sector: {sec} | Market Cap: {mcap_s}<br>"
                f"Price: {pr_s} | Est. Fair Value: {fv_s} (MoS: {mos_s})<br>"
                f"Quality Score: {s.get('composite_score', 0):.1f}/100 | Rev Growth: {s.get('revenue_growth', 0) or 0:+.1f}% | FCF Margin: {s.get('fcf_margin', 0) or 0:.1f}%"
            )

        if chosen_metric == "composite_score":
            cmin, cmid, cmax = 35, 62, 88
        elif chosen_metric == "margin_of_safety":
            cmin, cmid, cmax = -40, 0, 45
        elif chosen_metric == "rule_of_40":
            cmin, cmid, cmax = 5, 35, 70
        else:
            cmin, cmid, cmax = -10, 10, 35

        fig_tm = go.Figure(go.Treemap(
            ids=ids,
            labels=labels,
            parents=parents,
            values=vals_sz,
            branchvalues="remainder",
            marker=dict(
                colors=vals_col,
                colorscale=[
                    [0.0, "#b91c1c"],
                    [0.35, "#7f1d1d"],
                    [0.50, "#334155"],
                    [0.72, "#047857"],
                    [1.0, "#10b981"],
                ],
                cmid=cmid,
                cmin=cmin,
                cmax=cmax,
                line=dict(color="#131722", width=1.5),
                colorbar=dict(title=color_options[chosen_metric][:18], tickfont=dict(color="#d1d4dc")),
            ),
            textinfo="label",
            textfont=dict(size=13, color="#ffffff", family="Outfit, Rubik, sans-serif"),
            customdata=custom_txt,
            hovertemplate="%{customdata}<extra></extra>",
        ))
        fig_tm.update_layout(
            paper_bgcolor="#1c2030",
            plot_bgcolor="#131722",
            height=580,
            margin=dict(t=15, b=10, l=10, r=10),
        )
        st.plotly_chart(fig_tm, use_container_width=True)

    # =========================================================================
    # V2 TAB 2: LEGEND PRESETS + MULTI-FILTER SLIDERS + QUADRANT CHART
    # =========================================================================
    with v2_tabs[1]:
        st.markdown(f"#### 🏆 {'בחר אסטרטגיית אגדות השקעה (Presets בלחיצה אחת)' if is_he else 'One-Click Investing Legend Presets'}")

        if "scr_preset" not in st.session_state:
            st.session_state.scr_preset = "all"

        p1, p2, p3, p4, p5 = st.columns(5)
        if p1.button("🌐 " + ("הכל (All)" if is_he else "All Stocks"), use_container_width=True, key="pre_all"):
            st.session_state.scr_preset = "all"
        if p2.button("🏰 Warren Buffett", use_container_width=True, key="pre_buffett"):
            st.session_state.scr_preset = "buffett"
        if p3.button("🚀 Rule of 40", use_container_width=True, key="pre_r40"):
            st.session_state.scr_preset = "rule40"
        if p4.button("💎 " + ("מציאות ערך (Deep Value)" if is_he else "Deep Value Bargains"), use_container_width=True, key="pre_value"):
            st.session_state.scr_preset = "value"
        if p5.button("💵 " + ("מכונות מזומנים (Cash Cows)" if is_he else "Cash Cows"), use_container_width=True, key="pre_cash"):
            st.session_state.scr_preset = "cash"

        preset = st.session_state.scr_preset
        preset_defaults = {
            "all":     {"score": 0,  "mos": -80, "rev_g": -30, "gm": 0,  "fcf_m": -20, "debt": 100, "r40": -50, "roe": -50, "sh": 20.0},
            "buffett": {"score": 65, "mos": -10, "rev_g": 4,   "gm": 40, "fcf_m": 12,  "debt": 45,  "r40": 15,  "roe": 15,  "sh": 1.0},
            "rule40":  {"score": 60, "mos": -80, "rev_g": 12,  "gm": 50, "fcf_m": 15,  "debt": 65,  "r40": 40,  "roe": 0,   "sh": 10.0},
            "value":   {"score": 60, "mos": 15,  "rev_g": 0,   "gm": 25, "fcf_m": 8,   "debt": 60,  "r40": 0,   "roe": 10,  "sh": 5.0},
            "cash":    {"score": 65, "mos": -20, "rev_g": 2,   "gm": 35, "fcf_m": 20,  "debt": 40,  "r40": 20,  "roe": 12,  "sh": 1.0},
        }[preset]

        preset_desc_map = {
            "all": ("מציג את כל המניות הזמינות בסקרינר." if is_he else "Showing all scanned stocks."),
            "buffett": ("🏰 וורן באפט: חפיר חזק (Gross Margin ≥ 40%), ROE ≥ 15%, חוב נמוך, FCF ≥ 12% ורכישה עצמית של מניות." if is_he else "🏰 Warren Buffett: Wide Moat (Gross Margin ≥ 40%), ROE ≥ 15%, Low Debt, FCF Margin ≥ 12%, minimal dilution/buybacks."),
            "rule40": ("🚀 Rule of 40: צמיחת הכנסות + שולי FCF ≥ 40% עם מרווח גולמי גבוה (≥ 50%) — מניות צמיחה עילית." if is_he else "🚀 Rule of 40: Revenue Growth + FCF Margin ≥ 40% with High Gross Margin (≥ 50%) — elite high-efficiency compounders."),
            "value": ("💎 צייד מציאות (Deep Value): חברות איכותיות (ציון ≥ 60) שנסחרות כרגע בהנחה של לפחות +15% מתחת לשווי ההוגן!" if is_he else "💎 Deep Value Bargains: High-quality businesses (Score ≥ 60) trading at ≥ +15% Margin of Safety below multi-model Fair Value!"),
            "cash": ("💵 מכונות מזומנים (Cash Cows): שולי תזרים חופשי ≥ 20%, חוב נמוך ואיכות מאזן גבוהה." if is_he else "💵 Cash Cows: Free Cash Flow Margin ≥ 20%, Low Leverage, and strong shareholder returns."),
        }
        st.info(preset_desc_map[preset])

        # Interactive Sliders
        all_secs = sorted(set(s.get("sector", "Other") for s in all_stocks if s.get("sector")))
        f_col1, f_col2, f_col3 = st.columns(3)
        sel_secs = f_col1.multiselect("סקטורים:" if is_he else "Sectors:", options=all_secs, default=[], key=f"f_sec_{preset}")
        min_score = f_col2.slider("מינימום ציון איכות (0–100)" if is_he else "Min Quality Score", 0, 95, int(preset_defaults["score"]), key=f"f_sc_{preset}")
        min_mos = f_col3.slider("מינימום מרווח ביטחון / אפסייד (%)" if is_he else "Min Margin of Safety (%)", -80, 80, int(preset_defaults["mos"]), key=f"f_mos_{preset}")

        f_col4, f_col5, f_col6 = st.columns(3)
        min_rev_g = f_col4.slider("מינימום צמיחת הכנסות (%)" if is_he else "Min Revenue Growth (%)", -30, 50, int(preset_defaults["rev_g"]), key=f"f_rg_{preset}")
        min_fcf_m = f_col5.slider("מינימום שולי FCF (%)" if is_he else "Min FCF Margin (%)", -20, 45, int(preset_defaults["fcf_m"]), key=f"f_fcf_{preset}")
        max_debt = f_col6.slider("מקסימום חוב לנכסים (%)" if is_he else "Max Debt / Assets (%)", 10, 100, int(preset_defaults["debt"]), key=f"f_dbt_{preset}")

        # Apply filters
        filtered = []
        for s in all_stocks:
            if sel_secs and s.get("sector") not in sel_secs:
                continue
            if (s.get("composite_score") or 0) < min_score:
                continue
            mos_v = s.get("margin_of_safety")
            if min_mos > -80 and (mos_v is None or mos_v < min_mos):
                continue
            rg_v = _sfloat(s.get("revenue_growth"))
            if min_rev_g > -30 and (rg_v is None or rg_v < min_rev_g):
                continue
            fm_v = _sfloat(s.get("fcf_margin"))
            if min_fcf_m > -20 and (fm_v is None or fm_v < min_fcf_m):
                continue
            dr_v = _sfloat(s.get("debt_ratio"))
            if max_debt < 100 and (dr_v is not None and dr_v > max_debt):
                continue
            if preset_defaults["gm"] > 0 and ((_sfloat(s.get("gross_margin")) or 0) < preset_defaults["gm"]):
                continue
            if preset_defaults["r40"] > -50 and ((_sfloat(s.get("rule_of_40")) or -99) < preset_defaults["r40"]):
                continue
            if preset_defaults["roe"] > -50 and ((_sfloat(s.get("roe")) or -99) < preset_defaults["roe"]):
                continue
            if preset_defaults["sh"] < 20.0:
                sh_chg = _sfloat(s.get("share_change_pct"))
                if sh_chg is not None and sh_chg > preset_defaults["sh"]:
                    continue
            filtered.append(s)

        # Sort Value preset by Margin of Safety, others by Composite Score
        if preset == "value":
            filtered.sort(key=lambda x: (x.get("margin_of_safety") or -999, x.get("composite_score") or 0), reverse=True)
        elif preset == "rule40":
            filtered.sort(key=lambda x: x.get("rule_of_40") or -999, reverse=True)
        else:
            filtered.sort(key=lambda x: x.get("composite_score") or 0, reverse=True)

        st.markdown(
            f"**{'נמצאו' if is_he else 'Found'} `{len(filtered)}` {'מניות תואמות מתוך' if is_he else 'matching stocks out of'} `{len(all_stocks)}`:**"
        )

        if filtered:
            # Quality vs Margin of Safety Quadrant Scatter Plot
            scat_rows = [r for r in filtered if r.get("margin_of_safety") is not None]
            if len(scat_rows) >= 2:
                fig_q = go.Figure()
                sizes = [max(10, min(38, math.log10(max(1e9, r.get("market_cap") or 1e10)) * 3.0 - 18)) for r in scat_rows]
                colors = ["#089981" if (r["margin_of_safety"] >= 10 and r["composite_score"] >= 65) else ("#2962ff" if r["composite_score"] >= 65 else "#f0b90b") for r in scat_rows]
                fig_q.add_trace(go.Scatter(
                    x=[r["margin_of_safety"] for r in scat_rows],
                    y=[r["composite_score"] for r in scat_rows],
                    mode="markers+text",
                    text=[r["ticker"] for r in scat_rows],
                    textposition="top center",
                    textfont=dict(size=10, color="#ffffff"),
                    marker=dict(size=sizes, color=colors, opacity=0.85, line=dict(color="#ffffff", width=1)),
                    customdata=[
                        f"<b>{r['ticker']} — {r.get('name', '')}</b><br>"
                        f"Quality Score: {r['composite_score']:.1f}/100<br>"
                        f"Price: ${r.get('current_price',0):,.2f} | Fair Value: ${r.get('est_fair_value',0):,.2f}<br>"
                        f"Margin of Safety: {r['margin_of_safety']:+.1f}% | Rule of 40: {r['rule_of_40']:.1f}%"
                        for r in scat_rows
                    ],
                    hovertemplate="%{customdata}<extra></extra>",
                ))
                fig_q.add_vline(x=0, line_dash="dash", line_color="rgba(255,255,255,0.28)")
                fig_q.add_hline(y=65, line_dash="dash", line_color="rgba(255,255,255,0.28)")
                fig_q.add_annotation(
                    x=max(r["margin_of_safety"] for r in scat_rows) * 0.85,
                    y=min(98, max(r["composite_score"] for r in scat_rows) + 2),
                    text=("💎 אזור הזהב: איכות גבוהה + תמחור זול" if is_he else "💎 SWEET SPOT: High Quality + Undervalued"),
                    showarrow=False, font=dict(color="#10b981", size=12, family="Outfit, Rubik, sans-serif"),
                )
                fig_q.update_layout(
                    title=f"<b>{'מפת איכות מול שווי הוגן (Quality vs. Margin of Safety)' if is_he else 'Quality Score vs. Margin of Safety (%) Quadrant Map'}</b>",
                    xaxis=dict(title=("מרווח ביטחון / אפסייד (%)" if is_he else "Margin of Safety / Upside (%)"), ticksuffix="%", gridcolor="rgba(255,255,255,0.06)"),
                    yaxis=dict(title=("ציון איכות פיננסית (0–100)" if is_he else "Financial Quality Score (0–100)"), gridcolor="rgba(255,255,255,0.06)"),
                    paper_bgcolor="#1c2030", plot_bgcolor="#131722", height=420, margin=dict(t=55, b=35, l=50, r=20),
                )
                st.plotly_chart(fig_q, use_container_width=True)

            # Interactive filtered rows with 1-click Open Dashboard buttons
            df_show = pd.DataFrame([
                {
                    "Ticker": r["ticker"],
                    "Company": r.get("name", "")[:26],
                    "Sector": r.get("sector", ""),
                    "Quality": round(r.get("composite_score", 0), 1),
                    "Price": f"${r.get('current_price', 0):,.2f}",
                    "Est. Fair Value": f"${r['est_fair_value']:,.2f}" if r.get("est_fair_value") else "N/A",
                    "Margin of Safety": f"{r['margin_of_safety']:+.1f}%" if r.get("margin_of_safety") is not None else "N/A",
                    "Rev Growth": f"{r['revenue_growth']:+.1f}%" if r.get("revenue_growth") is not None else "N/A",
                    "Gross Margin": f"{r['gross_margin']:.1f}%" if r.get("gross_margin") is not None else "N/A",
                    "FCF Margin": f"{r['fcf_margin']:.1f}%" if r.get("fcf_margin") is not None else "N/A",
                    "Rule of 40": f"{r['rule_of_40']:.1f}%",
                    "ROE": f"{r['roe']:.1f}%" if r.get("roe") is not None else "N/A",
                }
                for r in filtered[:40]
            ])
            st.dataframe(df_show, use_container_width=True, hide_index=True)

            # Quick open buttons for top 8 filtered stocks
            top_pick_cols = st.columns(min(8, len(filtered)))
            for idx_b, st_item in enumerate(filtered[:8]):
                t_b = st_item["ticker"]
                if top_pick_cols[idx_b].button(f"🔍 {t_b}", key=f"v2_open_{preset}_{t_b}_{idx_b}", use_container_width=True):
                    st.session_state.selected_ticker = t_b
                    st.session_state.page_selector = "Dashboard"
                    st.rerun()
        else:
            st.warning("No stocks matched these strict filters — try relaxing one slider." if not is_he else "לא נמצאו מניות שעומדות בכל תנאי הסינון — נסה להגמיש מעט את הסליידרים.")
