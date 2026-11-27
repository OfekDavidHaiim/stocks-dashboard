import math
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st


@st.cache_data(ttl=1800, show_spinner=False)
def _fetch_chart_and_divs(ticker_symbol: str, range_str: str = "5y"):
    """
    Crumb-free direct Yahoo Finance v8 chart fetcher returning (close_series, dividends_series).
    Handles ILA (Israeli Agorot -> ILS) scaling automatically for .TA symbols.
    """
    try:
        sym = ticker_symbol.strip().upper()
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}?range={range_str}&interval=1d&events=div"
        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=10,
        )
        if r.status_code != 200:
            return pd.Series(dtype=float), pd.Series(dtype=float)
        res = r.json().get("chart", {}).get("result", [])
        if not res:
            return pd.Series(dtype=float), pd.Series(dtype=float)
        d = res[0]
        meta = d.get("meta") or {}
        ts = d.get("timestamp", [])
        if not ts:
            return pd.Series(dtype=float), pd.Series(dtype=float)
        q = d.get("indicators", {}).get("quote", [{}])[0]
        closes = pd.to_numeric(q.get("close", []), errors="coerce")
        idx = pd.to_datetime(ts, unit="s", utc=True).tz_localize(None).normalize()
        s_close = pd.Series(closes, index=idx).dropna()
        s_close = s_close[~s_close.index.duplicated(keep="last")].sort_index()

        scale = 0.01 if (meta.get("currency") == "ILA" or sym.endswith(".TA")) else 1.0
        if scale != 1.0:
            s_close = s_close * scale

        divs_raw = d.get("events", {}).get("dividends", {}) or {}
        div_map = {}
        for k, v in divs_raw.items():
            try:
                dt = pd.to_datetime(int(k), unit="s", utc=True).tz_localize(None).normalize()
                amt = float(v.get("amount", 0.0))
                if meta.get("currency") == "ILA":
                    amt = amt * 0.01
                if amt > 0:
                    div_map[dt] = div_map.get(dt, 0.0) + amt
            except Exception:
                pass
        s_divs = pd.Series(div_map).sort_index() if div_map else pd.Series(dtype=float)
        return s_close, s_divs
    except Exception:
        return pd.Series(dtype=float), pd.Series(dtype=float)


def _fetch_many_charts(symbols: list, range_str: str = "5y") -> dict:
    out = {}
    unique_syms = list(dict.fromkeys([s for s in symbols if s]))
    if not unique_syms:
        return out
    with ThreadPoolExecutor(max_workers=min(10, len(unique_syms))) as ex:
        futs = {ex.submit(_fetch_chart_and_divs, sym, range_str): sym for sym in unique_syms}
        for fut, sym in futs.items():
            try:
                out[sym] = fut.result()
            except Exception:
                out[sym] = (pd.Series(dtype=float), pd.Series(dtype=float))
    return out


def render_portfolio_xray(
    portfolio_data: list,
    calculate_stock_metrics_fn,
    fetch_financial_data_fn,
    calculate_valuations_fn,
    usd_rate: float = 3.70,
    display_currency: str = "USD",
    lang: str = "en",
):
    """
    Render the Hedge-Fund Grade Portfolio X-Ray & Quant Risk Engine inside the Portfolio page:
      1. Historical Cumulative Performance vs SPY & QQQ + Quant Risk Ratios (Sharpe, Sortino, Beta, Alpha, Max Drawdown)
      2. Interactive Correlation Matrix Heatmap + Diversification Score
      3. Monte Carlo Simulation (2,000 Paths, 5-10Y Fan Chart)
      4. Portfolio Intrinsic Value Upside (9-Model Consensus) & 12-Month Passive Dividend Calendar
    """
    is_he = (lang == "he")
    sym_disp = "₪" if display_currency == "ILS" else "$"
    disp_factor = usd_rate if display_currency == "ILS" else 1.0

    # Extract open positions with positive market value
    open_positions = []
    for s in portfolio_data:
        ticker = str(s.get("symbol", "")).strip().upper()
        if not ticker or ticker == "TICKER":
            continue
        m = calculate_stock_metrics_fn(s)
        rem_qty = float(m.get("remaining_qty", 0.0))
        val_native = float(m.get("current_total_value", 0.0))
        if rem_qty <= 0 or val_native <= 0:
            continue
        curr = s.get("currency", "USD")
        val_usd = val_native / usd_rate if (curr == "ILS" and usd_rate > 0) else val_native
        open_positions.append({
            "symbol": ticker,
            "currency": curr,
            "qty": rem_qty,
            "val_usd": val_usd,
            "cost_usd": (float(m.get("remaining_cost_basis", 0.0)) / usd_rate) if (curr == "ILS" and usd_rate > 0) else float(m.get("remaining_cost_basis", 0.0)),
        })

    if not open_positions:
        return

    total_val_usd = sum(p["val_usd"] for p in open_positions)
    if total_val_usd <= 0:
        return
    for p in open_positions:
        p["weight"] = p["val_usd"] / total_val_usd

    st.markdown("---")
    st.markdown(
        f"## 🧬 {'Portfolio X-Ray — מנוע סיכונים וניתוח ברמת קרן גידור' if is_he else 'Portfolio X-Ray & Hedge-Fund Quant Risk Engine'}"
    )
    st.caption(
        "השוואת התיק מול S&P 500 ו-NASDAQ, מטריצת קורלציה, סימולציית Monte Carlo, שווי הוגן כולל ולוח דיבידנדים חודשי."
        if is_he
        else "Benchmark comparison vs SPY/QQQ, Sharpe/Sortino/Beta/Alpha/Drawdown, Correlation Heatmap, Monte Carlo Fan Chart, Portfolio Fair Value & Dividend Calendar."
    )

    xray_tabs = st.tabs([
        "📈 " + ("ביצועים ומדדי סיכון (vs SPY/QQQ)" if is_he else "Performance & Quant Risk"),
        "🔥 " + ("מטריצת קורלציה ופיזור" if is_he else "Correlation Heatmap"),
        "🎲 " + ("סימולציית Monte Carlo" if is_he else "Monte Carlo Simulation"),
        "🎯 " + ("שווי הוגן לתיק + לוח דיבידנדים" if is_he else "Portfolio Fair Value & Dividends"),
    ])

    # Fetch 5Y daily prices + dividends for all holdings + SPY + QQQ once (cached)
    holding_syms = [p["symbol"] for p in open_positions]
    chart_map = _fetch_many_charts(holding_syms + ["SPY", "QQQ"], range_str="5y")

    # Build daily return matrix
    close_dict = {}
    for sym in holding_syms + ["SPY", "QQQ"]:
        sc, _ = chart_map.get(sym, (pd.Series(dtype=float), pd.Series(dtype=float)))
        if sc is not None and len(sc) >= 20:
            close_dict[sym] = sc

    df_prices_all = pd.DataFrame(close_dict).sort_index().ffill()

    # =========================================================================
    # X-RAY TAB 1: PERFORMANCE VS SPY & QQQ + QUANT RISK METRICS
    # =========================================================================
    with xray_tabs[0]:
        col_h1, _ = st.columns([2, 3])
        lookback_opts = {"1Y": 252, "2Y": 504, "3Y": 756, "5Y": 1260}
        lb_choice = col_h1.radio(
            "טווח השוואה היסטורי:" if is_he else "Historical Lookback:",
            options=list(lookback_opts.keys()),
            index=1,
            horizontal=True,
            key="xray_lookback",
        )
        n_days = lookback_opts[lb_choice]

        valid_holdings = [p for p in open_positions if p["symbol"] in df_prices_all.columns]
        if valid_holdings and not df_prices_all.empty:
            w_sum = sum(p["weight"] for p in valid_holdings)
            weights = {p["symbol"]: p["weight"] / w_sum for p in valid_holdings}

            df_sub = df_prices_all.tail(n_days + 1)
            df_ret = df_sub.pct_change().dropna(how="all")

            # Weighted daily portfolio return (renormalizing weights on days where a ticker didn't trade)
            h_cols = [p["symbol"] for p in valid_holdings]
            h_ret = df_ret[h_cols].fillna(0.0)
            w_vec = np.array([weights[c] for c in h_cols])
            port_ret = pd.Series(h_ret.values @ w_vec, index=h_ret.index, name="Portfolio").dropna()

            spy_ret = df_ret["SPY"].reindex(port_ret.index).fillna(0.0) if "SPY" in df_ret.columns else pd.Series(dtype=float)
            qqq_ret = df_ret["QQQ"].reindex(port_ret.index).fillna(0.0) if "QQQ" in df_ret.columns else pd.Series(dtype=float)

            # Cumulative returns (%)
            port_cum = ((1.0 + port_ret).cumprod() - 1.0) * 100.0
            spy_cum = ((1.0 + spy_ret).cumprod() - 1.0) * 100.0 if not spy_ret.empty else pd.Series(dtype=float)
            qqq_cum = ((1.0 + qqq_ret).cumprod() - 1.0) * 100.0 if not qqq_ret.empty else pd.Series(dtype=float)

            # Quant Risk Metrics
            rf_annual = 0.0425
            rf_daily = rf_annual / 252.0
            n_obs = max(len(port_ret), 1)
            cagr_port = ((1.0 + port_ret).prod() ** (252.0 / n_obs) - 1.0) if n_obs >= 20 else 0.0
            vol_ann = float(port_ret.std() * math.sqrt(252.0))
            sharpe = ((cagr_port - rf_annual) / vol_ann) if vol_ann > 1e-6 else 0.0

            downside = port_ret[port_ret < rf_daily] - rf_daily
            down_vol = float(np.sqrt(np.mean(downside ** 2)) * math.sqrt(252.0)) if len(downside) > 0 else vol_ann
            sortino = ((cagr_port - rf_annual) / down_vol) if down_vol > 1e-6 else 0.0

            beta, alpha = 1.0, 0.0
            if not spy_ret.empty and spy_ret.var() > 1e-10:
                cov = float(np.cov(port_ret.values, spy_ret.values)[0, 1])
                beta = cov / float(spy_ret.var())
                cagr_spy = ((1.0 + spy_ret).prod() ** (252.0 / n_obs) - 1.0) if n_obs >= 20 else 0.0
                alpha = (cagr_port - (rf_annual + beta * (cagr_spy - rf_annual))) * 100.0

            # Drawdown series
            wealth = (1.0 + port_ret).cumprod()
            running_max = wealth.cummax()
            dd_series = ((wealth - running_max) / running_max) * 100.0
            max_dd = float(dd_series.min()) if not dd_series.empty else 0.0

            # Quant KPI Cards
            def _qcard(col, lbl, val_str, color="#ffffff", sub=""):
                col.markdown(
                    f'<div style="background:#1c2030;border:1px solid #2a2e39;border-top:3px solid {color};'
                    f'border-radius:8px;padding:12px 10px;text-align:center;margin-bottom:12px;">'
                    f'<div style="font-size:10px;color:#848e9c;text-transform:uppercase;font-weight:700;">{lbl}</div>'
                    f'<div style="font-size:21px;font-weight:800;color:{color};margin:4px 0;">{val_str}</div>'
                    f'<div style="font-size:10px;color:#848e9c;">{sub}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            qc1, qc2, qc3, qc4, qc5, qc6 = st.columns(6)
            _qcard(qc1, "Sharpe Ratio", f"{sharpe:.2f}", "#089981" if sharpe >= 1.0 else ("#f0b90b" if sharpe >= 0.5 else "#f23645"), "> 1.0 Strong")
            _qcard(qc2, "Sortino Ratio", f"{sortino:.2f}", "#089981" if sortino >= 1.5 else ("#f0b90b" if sortino >= 0.8 else "#f23645"), "Downside Adj.")
            _qcard(qc3, "Alpha (vs SPY)", f"{alpha:+.1f}%", "#089981" if alpha >= 0 else "#f23645", "Annualized")
            _qcard(qc4, "Beta (vs SPY)", f"{beta:.2f}", "#60a5fa" if 0.7 <= beta <= 1.3 else "#f0b90b", "Market Sens.")
            _qcard(qc5, "Volatility", f"{vol_ann*100:.1f}%", "#f0b90b" if vol_ann <= 0.25 else "#f23645", "Annualized σ")
            _qcard(qc6, "Max Drawdown", f"{max_dd:.1f}%", "#089981" if max_dd > -15 else ("#f0b90b" if max_dd > -28 else "#f23645"), "Peak-to-Trough")

            # Cumulative Performance Chart
            fig_perf = go.Figure()
            fig_perf.add_trace(go.Scatter(
                x=port_cum.index, y=port_cum.values,
                name=("התיק שלי (Portfolio)" if is_he else "My Portfolio"),
                line=dict(color="#2962ff", width=3),
                fill="tozeroy", fillcolor="rgba(41, 98, 255, 0.08)",
            ))
            if not spy_cum.empty:
                fig_perf.add_trace(go.Scatter(
                    x=spy_cum.index, y=spy_cum.values,
                    name="S&P 500 (SPY)",
                    line=dict(color="#f0b90b", width=2, dash="dot"),
                ))
            if not qqq_cum.empty:
                fig_perf.add_trace(go.Scatter(
                    x=qqq_cum.index, y=qqq_cum.values,
                    name="NASDAQ-100 (QQQ)",
                    line=dict(color="#089981", width=2, dash="dash"),
                ))
            fig_perf.add_hline(y=0, line_color="rgba(255,255,255,0.2)", line_width=1)
            fig_perf.update_layout(
                title=f"<b>{'ביצועים מצטברים: התיק שלי מול S&P 500 ו-NASDAQ' if is_he else 'Cumulative Return: Portfolio vs. S&P 500 (SPY) & NASDAQ (QQQ)'} ({lb_choice})</b>",
                yaxis=dict(title="Return (%)", ticksuffix="%", gridcolor="rgba(255,255,255,0.06)"),
                xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                paper_bgcolor="#1c2030", plot_bgcolor="#131722", height=400, margin=dict(t=60, b=25, l=50, r=20),
            )
            st.plotly_chart(fig_perf, use_container_width=True)

            # Underwater Drawdown Chart
            fig_dd = go.Figure()
            fig_dd.add_trace(go.Scatter(
                x=dd_series.index, y=dd_series.values,
                name="Drawdown (%)",
                line=dict(color="#f23645", width=2),
                fill="tozeroy", fillcolor="rgba(242, 54, 69, 0.22)",
            ))
            fig_dd.update_layout(
                title=f"<b>{'גרף ירידות מהשיא (Underwater Max Drawdown)' if is_he else 'Portfolio Underwater Drawdown (% from Peak)'}</b>",
                yaxis=dict(title="Drawdown (%)", ticksuffix="%", gridcolor="rgba(255,255,255,0.06)"),
                xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                hovermode="x unified",
                paper_bgcolor="#1c2030", plot_bgcolor="#131722", height=240, margin=dict(t=45, b=20, l=50, r=20),
            )
            st.plotly_chart(fig_dd, use_container_width=True)
        else:
            st.info("Not enough historical price data for portfolio positions." if not is_he else "אין מספיק נתוני היסטוריה לפוזיציות בתיק.")

    # =========================================================================
    # X-RAY TAB 2: CORRELATION HEATMAP & DIVERSIFICATION SCORE
    # =========================================================================
    with xray_tabs[1]:
        corr_syms = [p["symbol"] for p in open_positions if p["symbol"] in df_prices_all.columns]
        if "SPY" in df_prices_all.columns and "SPY" not in corr_syms:
            corr_syms.append("SPY")

        if len(corr_syms) >= 2:
            df_c = df_prices_all[corr_syms].tail(504).pct_change().dropna(how="all")
            corr_mat = df_c.corr().round(2)

            # Average pairwise correlation among user holdings (excluding SPY)
            hold_only = [s for s in corr_syms if s != "SPY"]
            if len(hold_only) >= 2:
                sub_m = corr_mat.loc[hold_only, hold_only].values
                tri = sub_m[np.triu_indices_from(sub_m, k=1)]
                avg_corr = float(np.nanmean(tri)) if len(tri) > 0 else 0.5
            else:
                avg_corr = 1.0

            div_score = round(max(0.0, min(100.0, (1.0 - max(0.0, avg_corr)) * 115.0)), 1)
            div_col = "#089981" if div_score >= 65 else ("#f0b90b" if div_score >= 40 else "#f23645")
            st.markdown(
                f'<div style="background:#1c2030;border:1px solid #2a2e39;border-left:4px solid {div_col};'
                f'border-radius:8px;padding:12px 16px;margin-bottom:14px;font-size:13px;color:#d1d4dc;">'
                f'🛡️ <strong>{"ציון פיזור תיק (Diversification Score)" if is_he else "Portfolio Diversification Score"}: '
                f'<span style="color:{div_col};font-size:16px;">{div_score}/100</span></strong> &nbsp;|&nbsp; '
                f'{"קורלציה ממוצעת בין האחזקות" if is_he else "Average Pairwise Correlation"}: <strong>{avg_corr:.2f}</strong> '
                f'({"פיזור מצוין — מתחת ל-0.45" if (is_he and avg_corr < 0.45) else ("ריכוז סיכון בינוני-גבוה — רוב המניות נעות יחד" if is_he else ("Well diversified (< 0.45)" if avg_corr < 0.45 else "Moderate/High correlation — holdings tend to move together"))})'
                f'</div>',
                unsafe_allow_html=True,
            )

            fig_hm = go.Figure(data=go.Heatmap(
                z=corr_mat.values,
                x=corr_mat.columns.tolist(),
                y=corr_mat.index.tolist(),
                zmin=-1, zmax=1,
                colorscale=[
                    [0.0, "#1d4ed8"],
                    [0.5, "#1e293b"],
                    [1.0, "#ef4444"],
                ],
                text=corr_mat.values,
                texttemplate="%{text:.2f}",
                textfont=dict(size=11, color="#ffffff"),
                hovertemplate="%{x} ↔ %{y}<br>Correlation: <b>%{z:.2f}</b><extra></extra>",
            ))
            fig_hm.update_layout(
                title=f"<b>{'מטריצת קורלציה בין מניות התיק (2 שנים)' if is_he else 'Portfolio Holdings Correlation Matrix (2-Year Daily Returns)'}</b>",
                paper_bgcolor="#1c2030", plot_bgcolor="#131722",
                height=max(380, 220 + len(corr_syms) * 32),
                margin=dict(t=55, b=30, l=60, r=30),
            )
            st.plotly_chart(fig_hm, use_container_width=True)
        else:
            st.info("Add at least 2 positions to compute the correlation matrix." if not is_he else "יש להוסיף לפחות 2 מניות לתיק כדי לחשב מטריצת קורלציה.")

    # =========================================================================
    # X-RAY TAB 3: MONTE CARLO SIMULATION (2,000 PATHS, 5-10Y FAN CHART)
    # =========================================================================
    with xray_tabs[2]:
        mc_c1, mc_c2, mc_c3 = st.columns(3)
        mc_years = mc_c1.slider("אופק סימולציה (שנים)" if is_he else "Simulation Horizon (Years)", 3, 15, 10, key="mc_years")
        mc_monthly = mc_c2.number_input(
            f"{'הפקדה חודשית נוספת' if is_he else 'Monthly Contribution'} ({sym_disp})",
            min_value=0.0, value=0.0, step=100.0, key="mc_monthly",
        )
        mc_paths = mc_c3.selectbox("מספר תרחישים (Paths)" if is_he else "Monte Carlo Paths", [1000, 2500, 5000], index=1, key="mc_paths")

        # Estimate drift & vol from portfolio history (with sensible institutional guardrails)
        valid_h = [p for p in open_positions if p["symbol"] in df_prices_all.columns]
        mu_est, vol_est = 0.10, 0.20
        if valid_h and not df_prices_all.empty:
            w_s = sum(p["weight"] for p in valid_h)
            h_cols = [p["symbol"] for p in valid_h]
            w_v = np.array([p["weight"] / w_s for p in valid_h])
            r_hist = df_prices_all[h_cols].tail(756).pct_change().fillna(0.0)
            p_r = pd.Series(r_hist.values @ w_v)
            if len(p_r) >= 40:
                raw_mu = float(p_r.mean() * 252.0)
                raw_vol = float(p_r.std() * math.sqrt(252.0))
                mu_est = min(max(raw_mu, 0.04), 0.22)  # Cap extreme historical drift for realistic forecasts
                vol_est = min(max(raw_vol, 0.08), 0.55)

        start_val_disp = total_val_usd * disp_factor
        months = mc_years * 12
        dt = 1.0 / 12.0
        rng = np.random.default_rng(42)
        shocks = rng.normal(loc=(mu_est - 0.5 * vol_est ** 2) * dt, scale=vol_est * math.sqrt(dt), size=(mc_paths, months))
        growth_factors = np.exp(shocks)

        paths = np.zeros((mc_paths, months + 1), dtype=float)
        paths[:, 0] = start_val_disp
        for m_i in range(1, months + 1):
            paths[:, m_i] = paths[:, m_i - 1] * growth_factors[:, m_i - 1] + mc_monthly

        p10 = np.percentile(paths, 10, axis=0)
        p25 = np.percentile(paths, 25, axis=0)
        p50 = np.percentile(paths, 50, axis=0)
        p75 = np.percentile(paths, 75, axis=0)
        p90 = np.percentile(paths, 90, axis=0)

        total_contributed = start_val_disp + mc_monthly * months
        prob_profit = float((paths[:, -1] > total_contributed).mean() * 100.0)
        prob_double = float((paths[:, -1] >= total_contributed * 2.0).mean() * 100.0)

        km1, km2, km3, km4 = st.columns(4)
        km1.metric("תרחיש פסימי (10%)" if is_he else "Bear Case (10th %ile)", f"{sym_disp}{p10[-1]:,.0f}")
        km2.metric("תחזית חציונית (50%)" if is_he else "Median Expected (50th %ile)", f"{sym_disp}{p50[-1]:,.0f}", f"{((p50[-1]/total_contributed)-1)*100:+.0f}%")
        km3.metric("תרחיש אופטימי (90%)" if is_he else "Bull Case (90th %ile)", f"{sym_disp}{p90[-1]:,.0f}")
        km4.metric("הסתברות לרווח / להכפלה" if is_he else "Prob. Profit / 2x", f"{prob_profit:.0f}% / {prob_double:.0f}%")

        x_yrs = np.linspace(0, mc_years, months + 1)
        fig_mc = go.Figure()
        fig_mc.add_trace(go.Scatter(x=x_yrs, y=p90, name="90th Percentile (Bull)", line=dict(color="#089981", width=1.5, dash="dot")))
        fig_mc.add_trace(go.Scatter(x=x_yrs, y=p75, name="75th Percentile", line=dict(color="rgba(8,153,129,0.0)"), fill="tonexty", fillcolor="rgba(8, 153, 129, 0.12)", showlegend=False))
        fig_mc.add_trace(go.Scatter(x=x_yrs, y=p25, name="25th–75th Band", line=dict(color="rgba(41,98,255,0.0)"), fill="tonexty", fillcolor="rgba(41, 98, 255, 0.22)"))
        fig_mc.add_trace(go.Scatter(x=x_yrs, y=p10, name="10th Percentile (Stress)", line=dict(color="#f23645", width=1.5, dash="dot"), fill="tonexty", fillcolor="rgba(242, 54, 69, 0.10)"))
        fig_mc.add_trace(go.Scatter(x=x_yrs, y=p50, name="Median Path (50%)", line=dict(color="#ffffff", width=3)))

        fig_mc.update_layout(
            title=f"<b>{'סימולציית Monte Carlo לתיק' if is_he else 'Portfolio Monte Carlo Fan Chart'} ({mc_paths:,} paths · μ={mu_est*100:.1f}%, σ={vol_est*100:.1f}%)</b>",
            xaxis=dict(title=("שנים מהיום" if is_he else "Years Ahead"), gridcolor="rgba(255,255,255,0.05)"),
            yaxis=dict(title=f"Portfolio Value ({sym_disp})", tickprefix=sym_disp, gridcolor="rgba(255,255,255,0.06)"),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            paper_bgcolor="#1c2030", plot_bgcolor="#131722", height=420, margin=dict(t=60, b=30, l=65, r=20),
        )
        st.plotly_chart(fig_mc, use_container_width=True)

    # =========================================================================
    # X-RAY TAB 4: PORTFOLIO INTRINSIC VALUE UPSIDE + MONTHLY DIVIDEND CALENDAR
    # =========================================================================
    with xray_tabs[3]:
        # --- Part A: 12-Month Passive Dividend Income Calendar (Instant — already fetched!) ---
        st.markdown(f"#### 💰 {'לוח הכנסה פסיבית מדיבידנדים (12 חודשים קדימה)' if is_he else '12-Month Expected Passive Dividend Income Calendar'}")
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        month_totals_usd = {m: 0.0 for m in range(1, 13)}
        cutoff_1y = pd.Timestamp.now().normalize() - pd.Timedelta(days=370)
        div_breakdown = []

        for p in open_positions:
            _, s_divs = chart_map.get(p["symbol"], (pd.Series(dtype=float), pd.Series(dtype=float)))
            if s_divs is not None and not s_divs.empty:
                recent_d = s_divs[s_divs.index >= cutoff_1y]
                if not recent_d.empty:
                    ann_div_native = float(recent_d.sum()) * p["qty"]
                    ann_div_usd = (ann_div_native / usd_rate) if (p["currency"] == "ILS" and usd_rate > 0) else ann_div_native
                    for dt_d, amt_d in recent_d.items():
                        pay_native = float(amt_d) * p["qty"]
                        pay_usd = (pay_native / usd_rate) if (p["currency"] == "ILS" and usd_rate > 0) else pay_native
                        month_totals_usd[int(dt_d.month)] += pay_usd
                    div_breakdown.append({
                        "Ticker": p["symbol"],
                        "Annual Dividend": f"{sym_disp}{ann_div_usd * disp_factor:,.2f}",
                        "Yield (%)": f"{(ann_div_usd / p['val_usd'] * 100.0):.2f}%" if p["val_usd"] > 0 else "0.00%",
                    })

        total_ann_div_disp = sum(month_totals_usd.values()) * disp_factor
        port_div_yield = (sum(month_totals_usd.values()) / total_val_usd) * 100.0 if total_val_usd > 0 else 0.0

        dc1, dc2, dc3 = st.columns(3)
        dc1.metric("דיבידנד שנתי צפוי" if is_he else "Est. Annual Dividends", f"{sym_disp}{total_ann_div_disp:,.2f}")
        dc2.metric("ממוצע חודשי" if is_he else "Monthly Average", f"{sym_disp}{total_ann_div_disp / 12.0:,.2f}")
        dc3.metric("תשואת דיבידנד של התיק" if is_he else "Portfolio Dividend Yield", f"{port_div_yield:.2f}%")

        if total_ann_div_disp > 0:
            m_vals_disp = [month_totals_usd[m] * disp_factor for m in range(1, 13)]
            fig_div_cal = go.Figure(go.Bar(
                x=month_names,
                y=m_vals_disp,
                marker=dict(color="#089981", cornerradius=5),
                text=[f"{sym_disp}{v:,.0f}" if v > 0 else "" for v in m_vals_disp],
                textposition="outside",
                textfont=dict(color="#d1d4dc", size=11),
                hovertemplate="<b>%{x}</b><br>Est. Payout: " + sym_disp + "%{y:,.2f}<extra></extra>",
            ))
            fig_div_cal.update_layout(
                title=f"<b>{'צפי תזרים דיבידנדים חודשי' if is_he else 'Projected Monthly Dividend Payouts'} ({sym_disp})</b>",
                yaxis=dict(tickprefix=sym_disp, gridcolor="rgba(255,255,255,0.06)"),
                paper_bgcolor="#1c2030", plot_bgcolor="#131722", height=320, margin=dict(t=50, b=25, l=50, r=20),
            )
            st.plotly_chart(fig_div_cal, use_container_width=True)
            if div_breakdown:
                with st.expander("📋 " + ("פירוט דיבידנדים לפי מניה" if is_he else "Dividend Breakdown by Holding")):
                    st.table(pd.DataFrame(div_breakdown))
        else:
            st.info("None of the open holdings paid dividends in the last 12 months." if not is_he else "אף אחת מהמניות הפתוחות בתיק לא חילקה דיבידנד ב-12 החודשים האחרונים.")

        # --- Part B: Full Portfolio 9-Model Intrinsic Value Upside ---
        st.markdown("---")
        st.markdown(f"#### 🎯 {'שווי הוגן משוקלל לתיק כולו (קונצנזוס 9 מודלים)' if is_he else 'Weighted Portfolio Intrinsic Value (9-Model Valuation Consensus)'}")

        run_val_btn = st.button(
            "🚀 " + ("חשב שווי הוגן (9 מודלים) לכל מניות התיק" if is_he else "Run 9-Model Fair Value Scan on All Holdings"),
            key="btn_xray_portfolio_val",
            type="primary",
        )
        if run_val_btn:
            val_results = []
            prog = st.progress(0)
            for idx_p, p in enumerate(open_positions):
                sym_t = p["symbol"]
                try:
                    fa, ba, ca, _, _, _, hist_t, info_t = fetch_financial_data_fn(sym_t)
                    cp = float(info_t.get("currentPrice") or (hist_t["Close"].iloc[-1] if hist_t is not None and not hist_t.empty else 0))
                    if cp > 0 and info_t:
                        vals_t = calculate_valuations_fn(info_t, fa, avg_pe=20.0, growth_rate=10.0, discount_rate=10.0, terminal_growth=2.5, use_wacc=True, df_bs=ba, df_cf=ca, history=hist_t)
                        models_t = {k: v for k, v in vals_t.items() if k != "_meta" and isinstance(v, dict) and "intrinsic_value" in v}
                        if models_t:
                            avg_iv = sum(float(v["intrinsic_value"]) for v in models_t.values()) / len(models_t)
                            upside = ((avg_iv - cp) / cp) * 100.0
                            fair_val_usd = p["val_usd"] * (avg_iv / cp)
                            val_results.append({
                                "Ticker": sym_t,
                                "Weight (%)": round(p["weight"] * 100.0, 1),
                                "Current Price": cp,
                                "Fair Value (9-Model)": round(avg_iv, 2),
                                "Upside (%)": round(upside, 1),
                                "Position Value USD": p["val_usd"],
                                "Position Fair Value USD": fair_val_usd,
                            })
                except Exception:
                    pass
                prog.progress((idx_p + 1) / len(open_positions))
            prog.empty()
            st.session_state["xray_val_results"] = val_results

        val_results = st.session_state.get("xray_val_results")
        if val_results:
            tot_curr_v = sum(r["Position Value USD"] for r in val_results)
            tot_fair_v = sum(r["Position Fair Value USD"] for r in val_results)
            port_upside = ((tot_fair_v - tot_curr_v) / tot_curr_v * 100.0) if tot_curr_v > 0 else 0.0

            vc1, vc2, vc3 = st.columns(3)
            vc1.metric("שווי שוק נוכחי (מכוסה)" if is_he else "Covered Market Value", f"{sym_disp}{tot_curr_v * disp_factor:,.0f}")
            vc2.metric("שווי הוגן כולל (9 מודלים)" if is_he else "Portfolio Fair Value", f"{sym_disp}{tot_fair_v * disp_factor:,.0f}")
            vc3.metric("אפסייד / מרווח ביטחון כולל" if is_he else "Weighted Portfolio Upside", f"{port_upside:+.1f}%")

            df_vr = pd.DataFrame(val_results).sort_values("Upside (%)", ascending=True)
            bar_cs = ["#089981" if u >= 0 else "#f23645" for u in df_vr["Upside (%)"]]
            fig_puv = go.Figure(go.Bar(
                y=df_vr["Ticker"],
                x=df_vr["Upside (%)"],
                orientation="h",
                marker=dict(color=bar_cs, cornerradius=4),
                text=[f"{u:+.1f}%" for u in df_vr["Upside (%)"]],
                textposition="outside",
                textfont=dict(color="#ffffff", size=11),
            ))
            fig_puv.add_vline(x=0, line_color="#94a3b8", line_width=1.5)
            fig_puv.update_layout(
                title=f"<b>{'אפסייד / תמחור יתר לפי מניה (9 מודלים)' if is_he else 'Intrinsic Value Upside / Downside by Holding'}</b>",
                xaxis=dict(ticksuffix="%", gridcolor="rgba(255,255,255,0.06)"),
                paper_bgcolor="#1c2030", plot_bgcolor="#131722",
                height=max(260, 120 + len(df_vr) * 34),
                margin=dict(t=50, b=25, l=65, r=55),
            )
            st.plotly_chart(fig_puv, use_container_width=True)
            st.dataframe(df_vr[["Ticker", "Weight (%)", "Current Price", "Fair Value (9-Model)", "Upside (%)"]], use_container_width=True, hide_index=True)
