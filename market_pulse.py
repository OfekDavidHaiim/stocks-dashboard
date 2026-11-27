from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st


MACRO_ASSETS = [
    {"sym": "SPY",      "name_en": "S&P 500",          "name_he": "S&P 500",             "prefix": "$",  "suffix": "",  "icon": "🇺🇸"},
    {"sym": "QQQ",      "name_en": "NASDAQ-100",       "name_he": "נאסד״ק 100",          "prefix": "$",  "suffix": "",  "icon": "💻"},
    {"sym": "^TA125.TA","name_en": "TA-125 (Israel)",  "name_he": "ת״א 125",             "prefix": "",   "suffix": "",  "icon": "🇮🇱"},
    {"sym": "^VIX",     "name_en": "VIX Fear Index",   "name_he": "מדד הפחד (VIX)",      "prefix": "",   "suffix": "",  "icon": "⚡"},
    {"sym": "^TNX",     "name_en": "US 10Y Yield",     "name_he": "תשואת אג״ח 10Y",      "prefix": "",   "suffix": "%", "icon": "🏛️"},
    {"sym": "GC=F",     "name_en": "Gold",             "name_he": "זהב (Gold)",          "prefix": "$",  "suffix": "",  "icon": "🥇"},
    {"sym": "CL=F",     "name_en": "Crude Oil",        "name_he": "נפט (WTI)",           "prefix": "$",  "suffix": "",  "icon": "⛽"},
    {"sym": "BTC-USD",  "name_en": "Bitcoin",          "name_he": "ביטקוין (BTC)",       "prefix": "$",  "suffix": "",  "icon": "₿"},
    {"sym": "ILS=X",    "name_en": "USD / ILS",        "name_he": "דולר / שקל",          "prefix": "₪",  "suffix": "",  "icon": "💱"},
]

SECTOR_ETFS = [
    ("XLK",  "Technology",             "טכנולוגיה"),
    ("XLF",  "Financials",             "פיננסים"),
    ("XLV",  "Healthcare",             "בריאות"),
    ("XLY",  "Consumer Discretionary", "צריכה מחזורית"),
    ("XLP",  "Consumer Staples",       "צריכה בסיסית"),
    ("XLI",  "Industrials",            "תעשייה"),
    ("XLC",  "Communication",          "תקשורת"),
    ("XLE",  "Energy",                 "אנרגיה"),
    ("XLRE", "Real Estate",            "נדל״ן"),
    ("XLB",  "Materials",              "חומרים"),
    ("XLU",  "Utilities",              "תשתיות"),
]


@st.cache_data(ttl=600, show_spinner=False)
def _fetch_fast_close_series(sym: str, range_str: str = "1y") -> pd.Series:
    """Fast crumb-free Yahoo v8 chart close series."""
    try:
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}?range={range_str}&interval=1d"
        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=8,
        )
        if r.status_code != 200:
            return pd.Series(dtype=float)
        res = r.json().get("chart", {}).get("result", [])
        if not res:
            return pd.Series(dtype=float)
        d = res[0]
        ts = d.get("timestamp", [])
        if not ts:
            return pd.Series(dtype=float)
        closes = pd.to_numeric(d.get("indicators", {}).get("quote", [{}])[0].get("close", []), errors="coerce")
        idx = pd.to_datetime(ts, unit="s", utc=True).tz_localize(None).normalize()
        s = pd.Series(closes, index=idx).dropna()
        s = s[~s.index.duplicated(keep="last")].sort_index()
        return s
    except Exception:
        return pd.Series(dtype=float)


def _fetch_batch_series(syms: list, range_str: str = "1y") -> dict:
    out = {}
    uniq = list(dict.fromkeys([s for s in syms if s]))
    if not uniq:
        return out
    with ThreadPoolExecutor(max_workers=min(12, len(uniq))) as ex:
        futs = {ex.submit(_fetch_fast_close_series, s, range_str): s for s in uniq}
        for fut, s in futs.items():
            try:
                out[s] = fut.result()
            except Exception:
                out[s] = pd.Series(dtype=float)
    return out


def _compute_rsi_14(close: pd.Series):
    if close is None or len(close) < 15:
        return None
    delta = close.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ema_up = up.ewm(com=13, adjust=False).mean()
    ema_down = down.ewm(com=13, adjust=False).mean()
    rs = ema_up / (ema_down + 1e-10)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    v = rsi.iloc[-1]
    return float(v) if pd.notna(v) else None


def render_market_pulse_page(
    watchlists_dict: dict,
    active_watchlist: str,
    fetch_financial_data_fn,
    calculate_valuations_fn,
    fetch_earnings_fn=None,
    lang: str = "en",
):
    """
    Render the Market Pulse Command Center page:
      1. Live Macro Command Deck (SPY, QQQ, TA-125, VIX, 10Y Yield, Gold, Oil, BTC, USD/ILS) + Market Regime
      2. Interactive 4-Quadrant Sector Rotation Map (11 US Sector ETFs vs SPY)
      3. Smart Watchlist Alerts Engine (RSI < 30 / > 70, 52W Extremes, Intrinsic Value Undervalued, Upcoming Earnings)
    """
    is_he = (lang == "he")
    st.title("🌐 " + ("Market Pulse — מרכז פיקוד שוק והתראות חכמות" if is_he else "Market Pulse Command Center"))
    st.caption(
        "מדדי מאקרו בזמן אמת, מפת רוטציית סקטורים ומנוע התראות חכם על מניות המעקב שלך."
        if is_he
        else "Live global macro pulse, 4-quadrant sector rotation map, and automated technical, valuation & earnings alerts on your Watchlist."
    )

    # Fetch Macro + Sector ETFs in one fast parallel batch
    macro_syms = [m["sym"] for m in MACRO_ASSETS]
    sec_syms = [s[0] for s in SECTOR_ETFS]
    with st.spinner("טוען נתוני מאקרו וסקטורים בזמן אמת..." if is_he else "Loading live macro & sector rotation data..."):
        batch_data = _fetch_batch_series(macro_syms + sec_syms, range_str="1y")

    # =========================================================================
    # SECTION 1: MARKET REGIME BANNER + LIVE MACRO COMMAND DECK
    # =========================================================================
    spy_s = batch_data.get("SPY", pd.Series(dtype=float))
    vix_s = batch_data.get("^VIX", pd.Series(dtype=float))
    tnx_s = batch_data.get("^TNX", pd.Series(dtype=float))

    vix_val = float(vix_s.iloc[-1]) if not vix_s.empty else 18.0
    spy_above_200 = (float(spy_s.iloc[-1]) > float(spy_s.tail(200).mean())) if len(spy_s) >= 200 else True
    tnx_val = float(tnx_s.iloc[-1]) if not tnx_s.empty else 4.2

    if vix_val < 18 and spy_above_200:
        reg_en, reg_he, reg_col, reg_bg = "RISK-ON BULLISH REGIME", "מצב שוק: Risk-On חיובי (מגמת עלייה רגועה)", "#089981", "#0d2b1f"
    elif vix_val >= 25 or not spy_above_200:
        reg_en, reg_he, reg_col, reg_bg = "DEFENSIVE / HIGH-VOLATILITY REGIME", "מצב שוק: זהירות / תנודתיות גבוהה (Risk-Off)", "#f23645", "#2b0f0f"
    else:
        reg_en, reg_he, reg_col, reg_bg = "NEUTRAL / SELECTIVE REGIME", "מצב שוק: ניטרלי / סלקטיבי", "#f0b90b", "#2a220e"

    st.markdown(
        f'<div style="background:{reg_bg};border:1px solid {reg_col};border-left:5px solid {reg_col};'
        f'border-radius:10px;padding:14px 18px;margin-bottom:18px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">'
        f'<div><span style="background:{reg_col};color:#fff;font-weight:800;font-size:12px;padding:4px 10px;border-radius:6px;">{reg_he if is_he else reg_en}</span>'
        f'<span style="color:#d1d4dc;font-size:13px;margin-inline-start:12px;">'
        f'VIX: <b>{vix_val:.1f}</b> &nbsp;|&nbsp; US 10Y: <b>{tnx_val:.2f}%</b> &nbsp;|&nbsp; SPY vs 200-SMA: <b>{"Above ↑" if spy_above_200 else "Below ↓"}</b>'
        f'</span></div></div>',
        unsafe_allow_html=True,
    )

    st.markdown(f"### 📡 {'מדדי מאקרו גלובליים (Live Macro Deck)' if is_he else 'Global Macro Command Deck'}")

    # Render 3 rows x 3 columns of macro cards
    for row_start in range(0, len(MACRO_ASSETS), 3):
        cols = st.columns(3)
        for j, asset in enumerate(MACRO_ASSETS[row_start:row_start + 3]):
            s = batch_data.get(asset["sym"], pd.Series(dtype=float))
            lbl = asset["name_he"] if is_he else asset["name_en"]
            if len(s) >= 2:
                last_p = float(s.iloc[-1])
                prev_p = float(s.iloc[-2])
                d1 = ((last_p - prev_p) / prev_p * 100.0) if prev_p != 0 else 0.0
                p_1m = float(s.iloc[-22]) if len(s) >= 22 else float(s.iloc[0])
                m1 = ((last_p - p_1m) / p_1m * 100.0) if p_1m != 0 else 0.0
                # For VIX, rising is bearish (red), falling is calm (green)
                is_inv = (asset["sym"] == "^VIX")
                d1_col = ("#f23645" if d1 > 0 else "#089981") if is_inv else ("#089981" if d1 >= 0 else "#f23645")
                m1_col = ("#f23645" if m1 > 0 else "#089981") if is_inv else ("#089981" if m1 >= 0 else "#f23645")
                price_fmt = f"{asset['prefix']}{last_p:,.2f}{asset['suffix']}" if last_p < 10000 else f"{asset['prefix']}{last_p:,.0f}{asset['suffix']}"
                cols[j].markdown(
                    f'<div style="background:#1c2030;border:1px solid #2a2e39;border-top:3px solid {d1_col};'
                    f'border-radius:10px;padding:14px 16px;margin-bottom:12px;">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                    f'<span style="color:#848e9c;font-size:12px;font-weight:700;">{asset["icon"]} {lbl}</span>'
                    f'<span style="color:#64748b;font-size:10px;">{asset["sym"]}</span></div>'
                    f'<div style="font-size:24px;font-weight:800;color:#ffffff;margin:6px 0;">{price_fmt}</div>'
                    f'<div style="display:flex;gap:12px;font-size:12px;font-weight:700;">'
                    f'<span style="color:{d1_col};">1D: {d1:+.2f}%</span>'
                    f'<span style="color:{m1_col};">1M: {m1:+.1f}%</span>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
            else:
                cols[j].markdown(
                    f'<div style="background:#1c2030;border:1px solid #2a2e39;border-radius:10px;padding:14px 16px;margin-bottom:12px;">'
                    f'<div style="color:#848e9c;font-size:12px;font-weight:700;">{asset["icon"]} {lbl}</div>'
                    f'<div style="font-size:20px;color:#64748b;margin:8px 0;">N/A</div></div>',
                    unsafe_allow_html=True,
                )

    # =========================================================================
    # SECTION 2: 4-QUADRANT SECTOR ROTATION MAP
    # =========================================================================
    st.markdown("---")
    st.markdown(f"### 🧭 {'מפת רוטציית סקטורים (Sector Rotation Map vs S&P 500)' if is_he else 'Institutional Sector Rotation Map (1M vs 3M Performance)'}")

    sec_rows = []
    spy_1m = ((float(spy_s.iloc[-1]) / float(spy_s.iloc[-22]) - 1.0) * 100.0) if len(spy_s) >= 22 else 0.0
    spy_3m = ((float(spy_s.iloc[-1]) / float(spy_s.iloc[-64]) - 1.0) * 100.0) if len(spy_s) >= 64 else 0.0

    for etf, en_n, he_n in SECTOR_ETFS:
        s = batch_data.get(etf, pd.Series(dtype=float))
        if len(s) >= 64:
            r1m = (float(s.iloc[-1]) / float(s.iloc[-22]) - 1.0) * 100.0
            r3m = (float(s.iloc[-1]) / float(s.iloc[-64]) - 1.0) * 100.0
            rel_1m = r1m - spy_1m
            rel_3m = r3m - spy_3m
            if rel_1m >= 0 and rel_3m >= 0:
                quad, q_col = ("מוביל (Leading)" if is_he else "Leading"), "#089981"
            elif rel_1m >= 0 and rel_3m < 0:
                quad, q_col = ("מתאושש (Improving)" if is_he else "Improving"), "#2962ff"
            elif rel_1m < 0 and rel_3m >= 0:
                quad, q_col = ("נחלש (Weakening)" if is_he else "Weakening"), "#f0b90b"
            else:
                quad, q_col = ("מפגר (Lagging)" if is_he else "Lagging"), "#f23645"
            sec_rows.append({
                "ETF": etf,
                "Sector": he_n if is_he else en_n,
                "1M (%)": round(r1m, 2),
                "3M (%)": round(r3m, 2),
                "Rel 1M vs SPY": round(rel_1m, 2),
                "Rel 3M vs SPY": round(rel_3m, 2),
                "Quadrant": quad,
                "Color": q_col,
            })

    if sec_rows:
        df_sec = pd.DataFrame(sec_rows)
        sr_c1, sr_c2 = st.columns([1.3, 1])

        with sr_c1:
            fig_rot = go.Figure()
            fig_rot.add_trace(go.Scatter(
                x=df_sec["Rel 3M vs SPY"],
                y=df_sec["Rel 1M vs SPY"],
                mode="markers+text",
                text=[f"{r['ETF']}" for _, r in df_sec.iterrows()],
                textposition="top center",
                textfont=dict(size=11, color="#ffffff", family="Outfit, Rubik, sans-serif"),
                marker=dict(size=18, color=df_sec["Color"].tolist(), line=dict(color="#ffffff", width=1.5)),
                customdata=[
                    f"<b>{r['Sector']} ({r['ETF']})</b><br>Status: {r['Quadrant']}<br>1M Return: {r['1M (%)']:+.2f}% (vs SPY: {r['Rel 1M vs SPY']:+.2f}%)<br>3M Return: {r['3M (%)']:+.2f}% (vs SPY: {r['Rel 3M vs SPY']:+.2f}%)"
                    for _, r in df_sec.iterrows()
                ],
                hovertemplate="%{customdata}<extra></extra>",
            ))
            fig_rot.add_vline(x=0, line_dash="dash", line_color="rgba(255,255,255,0.28)")
            fig_rot.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.28)")

            x_lim = max(5.0, float(df_sec["Rel 3M vs SPY"].abs().max()) * 1.25)
            y_lim = max(4.0, float(df_sec["Rel 1M vs SPY"].abs().max()) * 1.25)
            fig_rot.add_annotation(x=x_lim * 0.65, y=y_lim * 0.85, text="🟢 LEADING", showarrow=False, font=dict(color="#089981", size=11))
            fig_rot.add_annotation(x=-x_lim * 0.65, y=y_lim * 0.85, text="🔵 IMPROVING", showarrow=False, font=dict(color="#60a5fa", size=11))
            fig_rot.add_annotation(x=x_lim * 0.65, y=-y_lim * 0.85, text="🟡 WEAKENING", showarrow=False, font=dict(color="#f0b90b", size=11))
            fig_rot.add_annotation(x=-x_lim * 0.65, y=-y_lim * 0.85, text="🔴 LAGGING", showarrow=False, font=dict(color="#f23645", size=11))

            fig_rot.update_layout(
                title=f"<b>{'רביעי רוטציה יחסית מול S&P 500' if is_he else 'Relative Sector Rotation Quadrants (vs. SPY)'}</b>",
                xaxis=dict(title="3M Relative Strength vs SPY (%)", range=[-x_lim, x_lim], ticksuffix="%", gridcolor="rgba(255,255,255,0.05)"),
                yaxis=dict(title="1M Momentum vs SPY (%)", range=[-y_lim, y_lim], ticksuffix="%", gridcolor="rgba(255,255,255,0.05)"),
                paper_bgcolor="#1c2030", plot_bgcolor="#131722", height=420, margin=dict(t=55, b=35, l=50, r=20),
            )
            st.plotly_chart(fig_rot, use_container_width=True)

        with sr_c2:
            df_bar_s = df_sec.sort_values("1M (%)", ascending=True)
            fig_sbar = go.Figure()
            fig_sbar.add_trace(go.Bar(
                y=[f"{r['ETF']} · {r['Sector'][:14]}" for _, r in df_bar_s.iterrows()],
                x=df_bar_s["1M (%)"],
                name="1M %",
                orientation="h",
                marker=dict(color=["#089981" if v >= 0 else "#f23645" for v in df_bar_s["1M (%)"]], cornerradius=4),
                text=[f"{v:+.1f}%" for v in df_bar_s["1M (%)"]],
                textposition="outside",
                textfont=dict(color="#d1d4dc", size=10),
            ))
            fig_sbar.add_vline(x=0, line_color="#94a3b8", line_width=1)
            fig_sbar.update_layout(
                title=f"<b>{'ביצועי סקטורים (חודש אחרון)' if is_he else 'Sector Performance Ranking (1-Month)'}</b>",
                xaxis=dict(ticksuffix="%", gridcolor="rgba(255,255,255,0.05)"),
                paper_bgcolor="#1c2030", plot_bgcolor="#131722", height=420, margin=dict(t=55, b=35, l=115, r=45),
                showlegend=False,
            )
            st.plotly_chart(fig_sbar, use_container_width=True)

    # =========================================================================
    # SECTION 3: SMART WATCHLIST ALERTS ENGINE
    # =========================================================================
    st.markdown("---")
    st.markdown(f"### 🚨 {'מנוע התראות חכמות על רשימת המעקב (Smart Watchlist Alerts)' if is_he else 'Smart Watchlist Alerts Engine'}")

    # Gather all unique tickers across user's watchlists
    wl_tickers = []
    if isinstance(watchlists_dict, dict):
        active_sections = watchlists_dict.get(active_watchlist) or []
        for sec in active_sections:
            wl_tickers.extend(sec.get("tickers", []))
        if not wl_tickers:
            for sections in watchlists_dict.values():
                for sec in sections:
                    wl_tickers.extend(sec.get("tickers", []))
    wl_tickers = list(dict.fromkeys([str(t).strip().upper() for t in wl_tickers if t]))

    if not wl_tickers:
        st.info("Add stocks to your Watchlist to activate automatic RSI, Valuation & Earnings alerts!" if not is_he else "הוסף מניות ל-Watchlist כדי להפעיל התראות חכמות (RSI, שווי הוגן ודוחות קרובים)!")
        return

    st.caption(
        f"{'סורק' if is_he else 'Monitoring'} {len(wl_tickers)} {'מניות מה-Watchlist הפעילה' if is_he else 'tickers from your active Watchlist'}: {', '.join(wl_tickers[:15])}{'...' if len(wl_tickers) > 15 else ''}"
    )

    # Fast technical scan (runs automatically using crumb-free chart API)
    wl_series = _fetch_batch_series(wl_tickers, range_str="1y")
    alerts = []

    for sym in wl_tickers:
        s = wl_series.get(sym, pd.Series(dtype=float))
        if len(s) < 30:
            continue
        curr_p = float(s.iloc[-1])
        rsi = _compute_rsi_14(s)
        sma50 = float(s.tail(50).mean()) if len(s) >= 50 else curr_p
        sma200 = float(s.tail(200).mean()) if len(s) >= 200 else curr_p
        hi52 = float(s.tail(252).max())
        dd_from_hi = ((curr_p - hi52) / hi52 * 100.0) if hi52 > 0 else 0.0

        if rsi is not None and rsi <= 32.0:
            alerts.append({
                "severity": "buy",
                "ticker": sym,
                "badge": "🟢 RSI OVERSOLD",
                "msg": (f"{sym} במכירת יתר! RSI(14) = {rsi:.1f} (מתחת ל-32) — הזדמנות טכנית פוטנציאלית." if is_he else f"{sym} is Oversold! RSI(14) = {rsi:.1f} (<= 32) — potential technical entry."),
            })
        elif rsi is not None and rsi >= 72.0:
            alerts.append({
                "severity": "warn",
                "ticker": sym,
                "badge": "🔴 RSI OVERBOUGHT",
                "msg": (f"{sym} בקניית יתר — RSI(14) = {rsi:.1f} (> 72). ייתכן מימוש בטווח הקצר." if is_he else f"{sym} is Overbought — RSI(14) = {rsi:.1f} (> 72). Extended short-term."),
            })

        if dd_from_hi <= -20.0:
            alerts.append({
                "severity": "info",
                "ticker": sym,
                "badge": "📉 DRAWDOWN -20%+",
                "msg": (f"{sym} נסחרת ב-{dd_from_hi:.1f}% מתחת לשיא ה-52 שבועות (${curr_p:,.2f} vs שיא ${hi52:,.2f})." if is_he else f"{sym} is {dd_from_hi:.1f}% below its 52-week high (${curr_p:,.2f} vs ${hi52:,.2f})."),
            })

        if len(s) >= 205:
            prev_sma50 = float(s.iloc[-6:-1].mean()) if len(s) >= 56 else sma50
            if sma50 > sma200 and abs((sma50 - sma200) / sma200) < 0.02 and curr_p > sma50:
                alerts.append({
                    "severity": "buy",
                    "ticker": sym,
                    "badge": "✨ GOLDEN CROSS ZONE",
                    "msg": (f"{sym} חוצה מעל ממוצע 200 (SMA50 ≈ SMA200, מחיר מעל שניהם) — איתות מומנטום חיובי." if is_he else f"{sym} near Golden Cross inflection (SMA50 > SMA200, price above both)."),
                })

    # Optional Deep Scan: 9-Model Valuation & Upcoming Earnings Alerts
    deep_btn = st.button(
        "💎 " + ("סרוק גם שווי הוגן (9 מודלים) ותאריכי דוחות קרובים ל-Watchlist" if is_he else "Run Deep Valuation & Upcoming Earnings Alert Scan"),
        key="btn_mp_deep_alerts",
        type="primary",
    )
    if deep_btn:
        deep_alerts = []
        prog = st.progress(0)
        for idx_w, sym in enumerate(wl_tickers):
            try:
                fa, ba, ca, _, _, _, hist_w, info_w = fetch_financial_data_fn(sym)
                cp = float(info_w.get("currentPrice") or (hist_w["Close"].iloc[-1] if hist_w is not None and not hist_w.empty else 0))
                if cp > 0 and info_w:
                    vals_w = calculate_valuations_fn(info_w, fa, avg_pe=20.0, growth_rate=10.0, discount_rate=10.0, terminal_growth=2.5, use_wacc=True, df_bs=ba, df_cf=ca, history=hist_w)
                    mods = {k: v for k, v in vals_w.items() if k != "_meta" and isinstance(v, dict) and "intrinsic_value" in v}
                    if mods:
                        avg_iv = sum(float(v["intrinsic_value"]) for v in mods.values()) / len(mods)
                        mos = ((avg_iv - cp) / cp) * 100.0
                        if mos >= 15.0:
                            deep_alerts.append({
                                "severity": "buy",
                                "ticker": sym,
                                "badge": f"💎 UNDERVALUED +{mos:.0f}%",
                                "msg": (f"{sym} נסחרת בהנחה! מחיר ${cp:,.2f} מול שווי הוגן (9 מודלים) של ${avg_iv:,.2f} (מרווח ביטחון +{mos:.1f}%)." if is_he else f"{sym} is Undervalued! Price ${cp:,.2f} vs 9-Model Fair Value ${avg_iv:,.2f} (+{mos:.1f}% Margin of Safety)."),
                            })
                        elif mos <= -30.0:
                            deep_alerts.append({
                                "severity": "warn",
                                "ticker": sym,
                                "badge": f"⚠️ OVERVALUED {mos:.0f}%",
                                "msg": (f"{sym} נסחרת בפרמיה גבוהה מעל שווי הקונצנזוס (${cp:,.2f} מול ${avg_iv:,.2f})." if is_he else f"{sym} trades significantly above 9-Model Fair Value (${cp:,.2f} vs ${avg_iv:,.2f})."),
                            })
                if fetch_earnings_fn:
                    _, nxt = fetch_earnings_fn(sym)
                    days_u = nxt.get("days_until")
                    if days_u is not None and 0 <= days_u <= 14:
                        deep_alerts.append({
                            "severity": "info",
                            "ticker": sym,
                            "badge": f"📅 EARNINGS IN {days_u}D",
                            "msg": (f"דוח רבעוני קרוב ל-{sym} בתאריך {nxt['date']} (בעוד {days_u} ימים)!" if is_he else f"Upcoming Earnings for {sym} on {nxt['date']} (in {days_u} days)!"),
                        })
            except Exception:
                pass
            prog.progress((idx_w + 1) / len(wl_tickers))
        prog.empty()
        st.session_state["mp_deep_alerts"] = deep_alerts

    all_alerts = (st.session_state.get("mp_deep_alerts") or []) + alerts

    if all_alerts:
        sev_style = {
            "buy":  ("#089981", "#0d2b1f"),
            "warn": ("#f23645", "#2b0f0f"),
            "info": ("#2962ff", "#152038"),
        }
        for i_al, al in enumerate(all_alerts):
            bc, bg = sev_style.get(al["severity"], ("#2962ff", "#1c2030"))
            c_msg, c_btn = st.columns([6, 1.2])
            c_msg.markdown(
                f'<div style="background:{bg};border:1px solid {bc}60;border-left:4px solid {bc};'
                f'border-radius:8px;padding:10px 14px;margin-bottom:8px;display:flex;align-items:center;gap:12px;">'
                f'<span style="background:{bc};color:#fff;font-weight:800;font-size:11px;padding:3px 8px;border-radius:5px;white-space:nowrap;">{al["badge"]}</span>'
                f'<span style="color:#e2e8f0;font-size:13px;">{al["msg"]}</span></div>',
                unsafe_allow_html=True,
            )
            if c_btn.button(f"🔍 {al['ticker']}", key=f"mp_al_open_{al['ticker']}_{i_al}", use_container_width=True):
                st.session_state.selected_ticker = al["ticker"]
                st.session_state.page_selector = "Dashboard"
                st.rerun()
    else:
        st.success("No extreme alerts triggered right now — all Watchlist stocks are trading within normal technical ranges. Click the Deep Scan button above to check 9-Model Valuation & Earnings alerts!" if not is_he else "אין כרגע התראות קיצון טכניות ב-Watchlist — לחץ על כפתור הסריקה העמוקה למעלה כדי לבדוק גם הזדמנויות שווי הוגן ודוחות קרובים.")
