import html
import math
import datetime
import numpy as np
import pandas as pd


def _safe_num(val):
    try:
        if val is None or pd.isna(val):
            return None
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except Exception:
        return None


def _col_val(df: pd.DataFrame, row_idx, candidates: list):
    if df is None or df.empty or row_idx not in df.index:
        return None
    row = df.loc[row_idx]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[-1]
    for c in candidates:
        if c in row.index:
            v = _safe_num(row.get(c))
            if v is not None:
                return v
    return None


def _strip_partial_year(df: pd.DataFrame, info: dict) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    p_meta = info.get("_partial_year_meta") if info else None
    if p_meta and p_meta.get("n_quarters", 4) < 4:
        p_yr = p_meta.get("year")
        if p_yr in df.index:
            return df[df.index != p_yr]
    return df


def compute_forensic_analysis(
    ticker_symbol: str,
    info: dict,
    df_fin_a: pd.DataFrame,
    df_bs_a: pd.DataFrame,
    df_cf_a: pd.DataFrame,
    valuations: dict = None,
    moat: dict = None,
    lang: str = "en",
) -> dict:
    """
    Compute institutional forensic quality & risk diagnostics:
      - Piotroski F-Score (0-9) with 9-point checklist
      - Altman Z-Score (Safe / Grey / Distress)
      - ROIC vs. WACC (Economic Value Spread)
      - Auto Red Flags & Green Flags
      - Master Conviction Score (0-100) + Grade
    """
    is_he = (lang == "he")
    fin = _strip_partial_year(df_fin_a, info)
    bs = _strip_partial_year(df_bs_a, info)
    cf = _strip_partial_year(df_cf_a, info)

    # Align latest 2 complete years
    fin_years = sorted([y for y in fin.index if str(y).isdigit()]) if not fin.empty else []
    bs_years = sorted([y for y in bs.index if str(y).isdigit()]) if not bs.empty else []
    cf_years = sorted([y for y in cf.index if str(y).isdigit()]) if not cf.empty else []

    y1 = fin_years[-1] if fin_years else None
    y0 = fin_years[-2] if len(fin_years) >= 2 else None
    by1 = bs_years[-1] if bs_years else None
    by0 = bs_years[-2] if len(bs_years) >= 2 else None
    cy1 = cf_years[-1] if cf_years else None

    # Extract core values
    rev_1 = _col_val(fin, y1, ["Total Revenue", "Operating Revenue"])
    rev_0 = _col_val(fin, y0, ["Total Revenue", "Operating Revenue"])
    gp_1 = _col_val(fin, y1, ["Gross Profit"])
    gp_0 = _col_val(fin, y0, ["Gross Profit"])
    op_1 = _col_val(fin, y1, ["Operating Income", "EBIT"])
    op_0 = _col_val(fin, y0, ["Operating Income", "EBIT"])
    ni_1 = _col_val(fin, y1, ["Net Income", "Net Income Common Stockholders"])
    ni_0 = _col_val(fin, y0, ["Net Income", "Net Income Common Stockholders"])
    sh_1 = _col_val(fin, y1, ["Diluted Average Shares", "Basic Average Shares"])
    sh_0 = _col_val(fin, y0, ["Diluted Average Shares", "Basic Average Shares"])
    tax_1 = _col_val(fin, y1, ["Tax Provision"])

    assets_1 = _col_val(bs, by1, ["Total Assets"])
    assets_0 = _col_val(bs, by0, ["Total Assets"])
    liab_1 = _col_val(bs, by1, ["Total Liabilities Net Minority Interest", "Total Liabilities"])
    eq_1 = _col_val(bs, by1, ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"])
    debt_1 = _col_val(bs, by1, ["Total Debt", "Long Term Debt"]) or 0.0
    debt_0 = _col_val(bs, by0, ["Total Debt", "Long Term Debt"])
    cash_1 = _col_val(bs, by1, ["Cash And Cash Equivalents"]) or 0.0
    ca_1 = _col_val(bs, by1, ["Total Current Assets", "Current Assets"])
    ca_0 = _col_val(bs, by0, ["Total Current Assets", "Current Assets"])
    cl_1 = _col_val(bs, by1, ["Total Current Liabilities", "Current Liabilities"])
    cl_0 = _col_val(bs, by0, ["Total Current Liabilities", "Current Liabilities"])
    re_1 = _col_val(bs, by1, ["Retained Earnings"])

    ocf_1 = _col_val(cf, cy1, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"])
    fcf_1 = _col_val(cf, cy1, ["Free Cash Flow"])
    sbc_1 = _col_val(cf, cy1, ["Stock Based Compensation"])

    # =========================================================================
    # 1. PIOTROSKI F-SCORE (0 - 9)
    # =========================================================================
    f_checks = []
    f_score = 0
    f_applicable = 0

    def _add_check(name_en, name_he, passed, detail_str):
        nonlocal f_score, f_applicable
        if passed is None:
            f_checks.append({"name": name_he if is_he else name_en, "passed": None, "detail": detail_str})
            return
        f_applicable += 1
        if passed:
            f_score += 1
        f_checks.append({"name": name_he if is_he else name_en, "passed": bool(passed), "detail": detail_str})

    # 1. Positive Net Income
    _add_check(
        "Positive Net Income", "רווח נקי חיובי",
        (ni_1 > 0) if ni_1 is not None else None,
        f"${ni_1/1e9:.2f}B" if ni_1 is not None else "N/A",
    )
    # 2. Positive Operating Cash Flow
    _add_check(
        "Positive Operating Cash Flow", "תזרים תפעולי חיובי",
        (ocf_1 > 0) if ocf_1 is not None else None,
        f"${ocf_1/1e9:.2f}B" if ocf_1 is not None else "N/A",
    )
    # 3. Improving ROA
    roa_1 = (ni_1 / assets_1) if (ni_1 is not None and assets_1 and assets_1 > 0) else None
    roa_0 = (ni_0 / assets_0) if (ni_0 is not None and assets_0 and assets_0 > 0) else None
    _add_check(
        "Improving ROA (YoY)", "שיפור בתשואה על הנכסים (ROA)",
        (roa_1 > roa_0) if (roa_1 is not None and roa_0 is not None) else None,
        f"{roa_1*100:.1f}% vs {roa_0*100:.1f}%" if (roa_1 is not None and roa_0 is not None) else "N/A",
    )
    # 4. Quality of Earnings (OCF > Net Income)
    _add_check(
        "Cash Flow Quality (OCF > Net Income)", "איכות רווחים (תזרים תפעולי > רווח נקי)",
        (ocf_1 > ni_1) if (ocf_1 is not None and ni_1 is not None) else None,
        f"{(ocf_1 / ni_1):.2f}x" if (ocf_1 is not None and ni_1 and ni_1 > 0) else "N/A",
    )
    # 5. Lower Leverage (Debt / Assets decreasing)
    lev_1 = (debt_1 / assets_1) if (assets_1 and assets_1 > 0) else None
    lev_0 = (debt_0 / assets_0) if (debt_0 is not None and assets_0 and assets_0 > 0) else None
    _add_check(
        "Lower Leverage (Debt/Assets ↓)", "ירידה במינוף (חוב לנכסים ↓)",
        (lev_1 <= lev_0 + 0.005) if (lev_1 is not None and lev_0 is not None) else None,
        f"{lev_1*100:.1f}% vs {lev_0*100:.1f}%" if (lev_1 is not None and lev_0 is not None) else "N/A",
    )
    # 6. Higher Liquidity (Current Ratio increasing)
    cr_1 = (ca_1 / cl_1) if (ca_1 is not None and cl_1 and cl_1 > 0) else None
    cr_0 = (ca_0 / cl_0) if (ca_0 is not None and cl_0 and cl_0 > 0) else None
    _add_check(
        "Higher Liquidity (Current Ratio ↑)", "שיפור בנזילות (יחס שוטף ↑)",
        (cr_1 >= cr_0 - 0.02) if (cr_1 is not None and cr_0 is not None) else None,
        f"{cr_1:.2f}x vs {cr_0:.2f}x" if (cr_1 is not None and cr_0 is not None) else "N/A",
    )
    # 7. No Share Dilution
    _add_check(
        "No Share Dilution (Buybacks / Flat)", "ללא דילול מניות (רכישה עצמית / יציבות)",
        (sh_1 <= sh_0 * 1.005) if (sh_1 and sh_0 and sh_0 > 0) else None,
        f"{((sh_1 - sh_0)/sh_0)*100:+.1f}% YoY" if (sh_1 and sh_0 and sh_0 > 0) else "N/A",
    )
    # 8. Higher Gross Margin
    gm_1 = (gp_1 / rev_1) if (gp_1 is not None and rev_1 and rev_1 > 0) else None
    gm_0 = (gp_0 / rev_0) if (gp_0 is not None and rev_0 and rev_0 > 0) else None
    _add_check(
        "Higher Gross Margin (YoY)", "התרחבות מרווח גולמי",
        (gm_1 >= gm_0 - 0.001) if (gm_1 is not None and gm_0 is not None) else None,
        f"{gm_1*100:.1f}% vs {gm_0*100:.1f}%" if (gm_1 is not None and gm_0 is not None) else "N/A",
    )
    # 9. Higher Asset Turnover
    at_1 = (rev_1 / assets_1) if (rev_1 is not None and assets_1 and assets_1 > 0) else None
    at_0 = (rev_0 / assets_0) if (rev_0 is not None and assets_0 and assets_0 > 0) else None
    _add_check(
        "Higher Asset Turnover (YoY)", "שיפור ביעילות הנכסים (מחזור נכסים ↑)",
        (at_1 >= at_0 - 0.005) if (at_1 is not None and at_0 is not None) else None,
        f"{at_1:.2f}x vs {at_0:.2f}x" if (at_1 is not None and at_0 is not None) else "N/A",
    )

    f_norm_9 = round((f_score / f_applicable) * 9.0) if (f_applicable > 0 and f_applicable < 9) else f_score
    if f_norm_9 >= 7:
        f_zone_en, f_zone_he, f_color = "Strong Financial Strength", "חוסן פיננסי גבוה מאוד", "#089981"
    elif f_norm_9 >= 4:
        f_zone_en, f_zone_he, f_color = "Moderate / Stable", "יציבות בינונית", "#f0b90b"
    else:
        f_zone_en, f_zone_he, f_color = "Weak / Deteriorating", "חולשה / הידרדרות פיננסית", "#f23645"

    # =========================================================================
    # 2. ALTMAN Z-SCORE
    # =========================================================================
    z_score = None
    z_zone_en, z_zone_he, z_color = "N/A", "לא זמין", "#848e9c"
    mcap_fin = _safe_num(info.get("marketCap"))
    fx_fin_to_trade = _safe_num(info.get("_fx_fin_to_trade")) or 1.0
    if mcap_fin and fx_fin_to_trade > 0:
        mcap_fin = mcap_fin / fx_fin_to_trade

    if assets_1 and assets_1 > 0 and liab_1 and liab_1 > 0:
        wc = (ca_1 - cl_1) if (ca_1 is not None and cl_1 is not None) else 0.0
        x1 = wc / assets_1
        # Use Retained Earnings if available, otherwise conservative 50% of Stockholders Equity
        re_proxy = re_1 if re_1 is not None else ((eq_1 * 0.55) if eq_1 is not None else 0.0)
        x2 = re_proxy / assets_1
        x3 = (op_1 / assets_1) if op_1 is not None else 0.0
        x4 = (mcap_fin / liab_1) if (mcap_fin and mcap_fin > 0) else ((eq_1 / liab_1) if (eq_1 and eq_1 > 0) else 0.0)
        x5 = (rev_1 / assets_1) if rev_1 is not None else 0.0
        z_raw = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5
        z_score = round(min(max(z_raw, -5.0), 30.0), 2)
        if z_score >= 2.99:
            z_zone_en, z_zone_he, z_color = "Safe Zone (Low Bankruptcy Risk)", "אזור בטוח (סיכון נמוך מאוד)", "#089981"
        elif z_score >= 1.81:
            z_zone_en, z_zone_he, z_color = "Grey Zone (Monitor Debt)", "אזור אפור (למעקב)", "#f0b90b"
        else:
            z_zone_en, z_zone_he, z_color = "Distress Zone (High Risk)", "אזור סיכון גבוה", "#f23645"

    # =========================================================================
    # 3. ROIC vs. WACC (TRUE ECONOMIC VALUE CREATION)
    # =========================================================================
    wacc_pct = 9.5
    if valuations and isinstance(valuations.get("_meta"), dict) and valuations["_meta"].get("wacc"):
        wacc_pct = float(valuations["_meta"]["wacc"])

    roic_pct = None
    roic_spread = None
    roic_zone_en, roic_zone_he, roic_color = "N/A", "לא זמין", "#848e9c"

    eff_tax = 0.21
    if op_1 and op_1 > 0 and tax_1 is not None and tax_1 > 0:
        eff_tax = min(max(tax_1 / op_1, 0.10), 0.32)

    nopat = (op_1 * (1.0 - eff_tax)) if op_1 is not None else (ni_1 if ni_1 is not None else None)
    invested_capital = None
    if eq_1 is not None:
        ic_cand = eq_1 + debt_1 - cash_1
        if ic_cand > 0:
            invested_capital = ic_cand
        elif (eq_1 + debt_1) > 0:
            invested_capital = eq_1 + debt_1
    if invested_capital is None and assets_1 and cl_1 is not None and (assets_1 - cl_1) > 0:
        invested_capital = assets_1 - cl_1

    if nopat is not None and invested_capital and invested_capital > 0:
        roic_pct = round(min(max((nopat / invested_capital) * 100.0, -50.0), 120.0), 2)
        roic_spread = round(roic_pct - wacc_pct, 2)
        if roic_spread >= 8.0:
            roic_zone_en, roic_zone_he, roic_color = "Elite Value Compounder", "מכונת יצירת ערך (Compounder)", "#089981"
        elif roic_spread >= 2.0:
            roic_zone_en, roic_zone_he, roic_color = "Value Creator (ROIC > WACC)", "יוצרת ערך כלכלי (ROIC > WACC)", "#10b981"
        elif roic_spread >= -1.0:
            roic_zone_en, roic_zone_he, roic_color = "Neutral Capital Return", "תשואה מאוזנת על ההון", "#f0b90b"
        else:
            roic_zone_en, roic_zone_he, roic_color = "Value Destroyer (ROIC < WACC)", "שוחקת ערך (ROIC < WACC)", "#f23645"

    # =========================================================================
    # 4. AUTO GREEN FLAGS & RED FLAGS DETECTOR
    # =========================================================================
    green_flags = []
    red_flags = []

    # Cash conversion (FCF / Net Income)
    if fcf_1 is not None and ni_1 is not None and ni_1 > 0:
        fcf_conv = fcf_1 / ni_1
        if fcf_conv >= 0.90:
            green_flags.append(
                f"איכות רווחים מצוינת: תזרים חופשי מהווה {fcf_conv*100:.0f}% מהרווח הנקי"
                if is_he else f"High Earnings Quality: Free Cash Flow converts {fcf_conv*100:.0f}% of Net Income"
            )
        elif fcf_conv < 0.65:
            red_flags.append(
                f"המרת מזומנים חלשה: FCF מהווה רק {fcf_conv*100:.0f}% מהרווח הנקי"
                if is_he else f"Weak Cash Conversion: FCF is only {fcf_conv*100:.0f}% of Net Income"
            )
    elif fcf_1 is not None and fcf_1 < 0:
        red_flags.append(
            "תזרים מזומנים חופשי שלילי (Negative FCF)"
            if is_he else "Negative Free Cash Flow (cash burn)"
        )

    # Stock-Based Compensation (SBC) vs FCF
    if sbc_1 is not None and sbc_1 > 0 and fcf_1 is not None and fcf_1 > 0:
        sbc_pct = (sbc_1 / fcf_1) * 100.0
        if sbc_pct > 25.0:
            red_flags.append(
                f"תגמול מבוסס מניות (SBC) גבוה מאוד: {sbc_pct:.1f}% מתזרים המזומנים החופשי"
                if is_he else f"Heavy Stock-Based Compensation (SBC): {sbc_pct:.1f}% of Free Cash Flow"
            )
        elif sbc_pct < 8.0:
            green_flags.append(
                f"תגמול מבוסס מניות (SBC) מבוקר ונמוך ({sbc_pct:.1f}% מ-FCF)"
                if is_he else f"Disciplined Stock-Based Compensation ({sbc_pct:.1f}% of FCF)"
            )

    # Multi-year Share Buybacks vs Dilution (up to 5Y)
    if not fin.empty:
        sh_col = "Diluted Average Shares" if "Diluted Average Shares" in fin.columns else ("Basic Average Shares" if "Basic Average Shares" in fin.columns else None)
        if sh_col:
            sh_s = pd.to_numeric(fin[sh_col], errors="coerce").dropna().tail(5)
            if len(sh_s) >= 2 and sh_s.iloc[0] > 0:
                sh_chg = ((sh_s.iloc[-1] - sh_s.iloc[0]) / sh_s.iloc[0]) * 100.0
                if sh_chg <= -3.0:
                    green_flags.append(
                        f"רכישה עצמית של מניות (Buybacks): כמות המניות ירדה ב-{abs(sh_chg):.1f}% ב-{len(sh_s)} השנים האחרונות"
                        if is_he else f"Shareholder-Friendly Buybacks: Share count shrank {abs(sh_chg):.1f}% over {len(sh_s)} years"
                    )
                elif sh_chg >= 8.0:
                    red_flags.append(
                        f"דילול משמעותי של בעלי מניות: כמות המניות גדלה ב-+{sh_chg:.1f}% ב-{len(sh_s)} השנים האחרונות"
                        if is_he else f"Significant Shareholder Dilution: Share count expanded +{sh_chg:.1f}% over {len(sh_s)} years"
                    )

    # Net Cash Fortress vs Debt Burden
    if cash_1 > debt_1 and cash_1 > 0:
        net_c = cash_1 - debt_1
        green_flags.append(
            f"מאזן מבצר (Net Cash): קופת המזומנים גבוהה מהחוב ב-${net_c/1e9:.2f}B"
            if is_he else f"Fortress Balance Sheet (Net Cash): Cash exceeds Total Debt by ${net_c/1e9:.2f}B"
        )
    elif debt_1 > 0 and fcf_1 and fcf_1 > 0 and (debt_1 / fcf_1) > 5.0:
        red_flags.append(
            f"עומס חוב כבד: יחס חוב לתזרים חופשי עומד על {debt_1/fcf_1:.1f}x (> 5 שנים לפירעון)"
            if is_he else f"Heavy Debt Load: Total Debt / FCF is {debt_1/fcf_1:.1f}x (> 5 years to pay off)"
        )

    # Margin Expansion / Contraction (3Y)
    if not fin.empty and "Operating Income" in fin.columns and "Total Revenue" in fin.columns:
        om_df = fin[["Total Revenue", "Operating Income"]].apply(pd.to_numeric, errors="coerce").dropna().tail(4)
        om_df = om_df[om_df["Total Revenue"] > 0]
        if len(om_df) >= 2:
            om_old = (om_df["Operating Income"].iloc[0] / om_df["Total Revenue"].iloc[0]) * 100.0
            om_new = (om_df["Operating Income"].iloc[-1] / om_df["Total Revenue"].iloc[-1]) * 100.0
            om_delta = om_new - om_old
            if om_delta >= 2.5:
                green_flags.append(
                    f"שיפור ברווחיות התפעולית: המרווח התרחב ב-+{om_delta:.1f}% (מ-{om_old:.1f}% ל-{om_new:.1f}%)"
                    if is_he else f"Expanding Operating Leverage: Operating margin rose +{om_delta:.1f}% ({om_old:.1f}% → {om_new:.1f}%)"
                )
            elif om_delta <= -3.0:
                red_flags.append(
                    f"שחיקה ברווחיות התפעולית: המרווח ירד ב-{abs(om_delta):.1f}% (מ-{om_old:.1f}% ל-{om_new:.1f}%)"
                    if is_he else f"Operating Margin Compression: Margin dropped {abs(om_delta):.1f}% ({om_old:.1f}% → {om_new:.1f}%)"
                )

    # ROIC spread flag
    if roic_spread is not None:
        if roic_spread >= 8.0:
            green_flags.append(
                f"יצירת ערך יוצאת דופן: ROIC של {roic_pct:.1f}% גבוה מ-WACC ({wacc_pct:.1f}%) ב-+{roic_spread:.1f}%"
                if is_he else f"Elite Capital Allocation: ROIC ({roic_pct:.1f}%) beats WACC ({wacc_pct:.1f}%) by +{roic_spread:.1f}%"
            )
        elif roic_spread < 0:
            red_flags.append(
                f"שחיקת ערך כלכלי: ROIC ({roic_pct:.1f}%) נמוך מעלות ההון WACC ({wacc_pct:.1f}%)"
                if is_he else f"Economic Value Destruction: ROIC ({roic_pct:.1f}%) is below WACC ({wacc_pct:.1f}%)"
            )

    # Valuation Margin of Safety Flag
    mos_pct = None
    avg_intrinsic = None
    curr_price = _safe_num(info.get("currentPrice"))
    if valuations and curr_price and curr_price > 0:
        models = {k: v for k, v in valuations.items() if k != "_meta" and isinstance(v, dict) and "intrinsic_value" in v}
        if models:
            avg_intrinsic = sum(float(v["intrinsic_value"]) for v in models.values()) / len(models)
            mos_pct = ((avg_intrinsic - curr_price) / curr_price) * 100.0
            if mos_pct >= 15.0:
                green_flags.append(
                    f"תמחור אטרקטיבי: אפסייד של +{mos_pct:.1f}% לפי קונצנזוס 9 מודלי הערכת השווי"
                    if is_he else f"Attractive Margin of Safety: +{mos_pct:.1f}% upside to 9-Model Consensus Valuation"
                )
            elif mos_pct <= -25.0:
                red_flags.append(
                    f"תמחור יקר: נסחרת בפרמיה של {abs(mos_pct):.1f}% מעל שווי הקונצנזוס של 9 המודלים"
                    if is_he else f"Stretched Valuation: Trading {abs(mos_pct):.1f}% above 9-Model Consensus Intrinsic Value"
                )

    # =========================================================================
    # 5. MASTER CONVICTION SCORE (0 - 100)
    # =========================================================================
    # Component A: Economic Moat (25%)
    moat_pts = (float(moat.get("score", 5.0)) / 10.0) * 100.0 if moat else 50.0
    # Component B: Forensic Quality — Piotroski + Altman Z (25%)
    f_pts = (f_norm_9 / 9.0) * 100.0
    z_pts = 95.0 if (z_score and z_score >= 4.0) else (80.0 if (z_score and z_score >= 2.99) else (55.0 if (z_score and z_score >= 1.81) else (25.0 if z_score is not None else 60.0)))
    forensic_pts = 0.65 * f_pts + 0.35 * z_pts
    # Component C: ROIC vs WACC (20%)
    if roic_spread is not None:
        roic_pts = min(max(50.0 + roic_spread * 3.0, 5.0), 100.0)
    else:
        roic_pts = 50.0
    # Component D: Valuation Margin of Safety (20%)
    if mos_pct is not None:
        val_pts = min(max(55.0 + mos_pct * 1.1, 10.0), 100.0)
    else:
        val_pts = 50.0
    # Component E: Growth Momentum (10%)
    rev_g_pct = ((rev_1 - rev_0) / abs(rev_0) * 100.0) if (rev_1 is not None and rev_0 and rev_0 > 0) else ((_safe_num(info.get("revenueGrowth")) or 0.0) * 100.0)
    growth_pts = min(max(45.0 + rev_g_pct * 2.2, 10.0), 100.0)

    master_score = round(
        0.25 * moat_pts + 0.25 * forensic_pts + 0.20 * roic_pts + 0.20 * val_pts + 0.10 * growth_pts,
        1,
    )
    # Small penalty/bonus for extreme flags
    master_score = round(min(max(master_score + len(green_flags) * 1.2 - len(red_flags) * 2.0, 5.0), 99.0), 1)

    if master_score >= 82:
        grade, verdict_en, verdict_he, m_color = "A+", "High-Conviction Compounder", "קנייה חזקה — חברת איכות עילית", "#089981"
    elif master_score >= 72:
        grade, verdict_en, verdict_he, m_color = "A", "Strong Institutional Quality", "איכות מוסדית גבוהה מאוד", "#10b981"
    elif master_score >= 62:
        grade, verdict_en, verdict_he, m_color = "B+", "Solid Business / Watch Entry", "עסק איכותי — לבחינת נקודת כניסה", "#2962ff"
    elif master_score >= 50:
        grade, verdict_en, verdict_he, m_color = "B", "Mixed Signals / Hold", "תמונה מעורבת — החזק / המתן", "#f0b90b"
    else:
        grade, verdict_en, verdict_he, m_color = "C", "Elevated Risk / Caution", "סיכון מוגבר — זהירות", "#f23645"

    return {
        "master_score": master_score,
        "grade": grade,
        "verdict_en": verdict_en,
        "verdict_he": verdict_he,
        "master_color": m_color,
        "sub_scores": {
            "moat": round(moat_pts, 1),
            "forensic": round(forensic_pts, 1),
            "roic": round(roic_pts, 1),
            "valuation": round(val_pts, 1),
            "growth": round(growth_pts, 1),
        },
        "piotroski": {
            "score": f_score,
            "applicable": f_applicable,
            "norm_9": f_norm_9,
            "zone_en": f_zone_en,
            "zone_he": f_zone_he,
            "color": f_color,
            "checks": f_checks,
        },
        "altman_z": {
            "score": z_score,
            "zone_en": z_zone_en,
            "zone_he": z_zone_he,
            "color": z_color,
        },
        "roic_wacc": {
            "roic": roic_pct,
            "wacc": round(wacc_pct, 2),
            "spread": roic_spread,
            "zone_en": roic_zone_en,
            "zone_he": roic_zone_he,
            "color": roic_color,
        },
        "green_flags": green_flags,
        "red_flags": red_flags,
        "avg_intrinsic": avg_intrinsic,
        "mos_pct": mos_pct,
    }


def generate_investment_memo_html(
    ticker_symbol: str,
    info: dict,
    forensic: dict,
    moat: dict,
    valuations: dict,
    currency_sym: str = "$",
    lang: str = "en",
) -> str:
    """
    Generate a clean, print-to-PDF ready Institutional Equity Research Memo (HTML).
    """
    is_he = (lang == "he")
    direction = "rtl" if is_he else "ltr"
    align = "right" if is_he else "left"
    today_str = datetime.date.today().strftime("%Y-%m-%d")

    name = html.escape(str(info.get("longName") or ticker_symbol))
    sector = html.escape(str(info.get("sector") or "N/A"))
    industry = html.escape(str(info.get("industry") or "N/A"))
    price = _safe_num(info.get("currentPrice")) or 0.0
    mcap = _safe_num(info.get("marketCap")) or 0.0
    mcap_str = f"{currency_sym}{mcap/1e12:.2f}T" if mcap >= 1e12 else (f"{currency_sym}{mcap/1e9:.2f}B" if mcap >= 1e9 else "N/A")

    m_sc = forensic["master_score"]
    m_gr = forensic["grade"]
    m_verdict = forensic["verdict_he"] if is_he else forensic["verdict_en"]
    m_col = forensic["master_color"]

    p_obj = forensic["piotroski"]
    z_obj = forensic["altman_z"]
    r_obj = forensic["roic_wacc"]

    # Valuation rows
    val_rows_html = ""
    if valuations:
        models = {k: v for k, v in valuations.items() if k != "_meta" and isinstance(v, dict) and "intrinsic_value" in v}
        for k, v in models.items():
            iv = float(v["intrinsic_value"])
            fv = float(v.get("future_price_5y", v.get("future_price", 0.0)))
            up = ((iv - price) / price * 100.0) if price > 0 else 0.0
            c_up = "#089981" if up >= 0 else "#f23645"
            val_rows_html += (
                f"<tr><td>{html.escape(k)}</td>"
                f"<td><b>{currency_sym}{iv:,.2f}</b></td>"
                f"<td style='color:{c_up};font-weight:700;'>{up:+.1f}%</td>"
                f"<td>{currency_sym}{fv:,.2f}</td></tr>"
            )

    f_rows_html = ""
    for chk in p_obj["checks"]:
        icon = "✅" if chk["passed"] is True else ("❌" if chk["passed"] is False else "➖")
        f_rows_html += f"<tr><td>{icon}</td><td>{html.escape(chk['name'])}</td><td>{html.escape(str(chk['detail']))}</td></tr>"

    green_li = "".join(f"<li style='color:#065f46;margin:4px 0;'>✅ {html.escape(g)}</li>" for g in forensic["green_flags"]) or "<li>—</li>"
    red_li = "".join(f"<li style='color:#991b1b;margin:4px 0;'>🚩 {html.escape(r)}</li>" for r in forensic["red_flags"]) or "<li>—</li>"

    avg_iv_str = f"{currency_sym}{forensic['avg_intrinsic']:,.2f}" if forensic.get("avg_intrinsic") else "N/A"
    mos_str = f"{forensic['mos_pct']:+.1f}%" if forensic.get("mos_pct") is not None else "N/A"
    roic_str = f"{r_obj['roic']:.1f}%" if r_obj["roic"] is not None else "N/A"
    z_str = f"{z_obj['score']:.2f}" if z_obj["score"] is not None else "N/A"

    doc_title = f"דו״ח מחקר אנליסט — {name} ({ticker_symbol})" if is_he else f"Institutional Equity Research Memo — {name} ({ticker_symbol})"

    return f"""<!DOCTYPE html>
<html lang="{'he' if is_he else 'en'}" dir="{direction}">
<head>
<meta charset="utf-8" />
<title>{doc_title}</title>
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f8fafc; color: #0f172a; margin: 0; padding: 28px; text-align: {align}; }}
  .container {{ max-width: 920px; margin: auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 30px 36px; box-shadow: 0 8px 24px rgba(15,23,42,0.08); }}
  .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 3px solid #1e293b; padding-bottom: 16px; margin-bottom: 22px; }}
  .badge {{ background: {m_col}; color: #fff; padding: 10px 18px; border-radius: 10px; text-align: center; min-width: 120px; }}
  .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 22px; }}
  .card {{ background: #f1f5f9; border-radius: 8px; padding: 12px 14px; border-top: 3px solid #2962ff; }}
  .card h4 {{ margin: 0; font-size: 11px; color: #64748b; text-transform: uppercase; }}
  .card .val {{ font-size: 20px; font-weight: 800; margin-top: 4px; }}
  .cols2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-bottom: 22px; }}
  .box {{ border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px 16px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 10px; }}
  th, td {{ padding: 8px 10px; border-bottom: 1px solid #e2e8f0; text-align: {align}; }}
  th {{ background: #f1f5f9; font-weight: 700; color: #334155; }}
  h2 {{ color: #1e293b; font-size: 16px; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px; margin-top: 24px; }}
  .footer {{ margin-top: 26px; font-size: 11px; color: #64748b; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 12px; }}
  @media print {{ body {{ background: #fff; padding: 0; }} .container {{ box-shadow: none; border: none; }} }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <div style="font-size:12px;color:#64748b;font-weight:700;">EQUITY RESEARCH INVESTMENT MEMO · {today_str}</div>
      <h1 style="margin:4px 0;font-size:26px;">{name} ({html.escape(ticker_symbol)})</h1>
      <div style="font-size:13px;color:#475569;">{sector} &nbsp;|&nbsp; {industry} &nbsp;|&nbsp; Market Cap: <b>{mcap_str}</b></div>
    </div>
    <div class="badge">
      <div style="font-size:11px;opacity:0.9;">MASTER SCORE</div>
      <div style="font-size:28px;font-weight:900;line-height:1.1;">{m_sc}/100 ({m_gr})</div>
      <div style="font-size:11px;margin-top:2px;">{html.escape(m_verdict)}</div>
    </div>
  </div>

  <div class="grid">
    <div class="card"><h4>{'מחיר נוכחי' if is_he else 'Current Price'}</h4><div class="val">{currency_sym}{price:,.2f}</div></div>
    <div class="card"><h4>{'שווי קונצנזוס (9 מודלים)' if is_he else '9-Model Fair Value'}</h4><div class="val">{avg_iv_str} <span style="font-size:13px;">({mos_str})</span></div></div>
    <div class="card"><h4>Piotroski F-Score</h4><div class="val" style="color:{p_obj['color']};">{p_obj['score']}/{p_obj['applicable'] or 9}</div></div>
    <div class="card"><h4>ROIC vs WACC / Altman Z</h4><div class="val" style="color:{r_obj['color']};">{roic_str} / Z={z_str}</div></div>
  </div>

  <div class="cols2">
    <div class="box" style="border-top:3px solid #089981;">
      <h3 style="margin-top:0;color:#065f46;">{'🟢 יתרונות ודגלים ירוקים (Bull Case)' if is_he else '🟢 Bull Case & Green Flags'}</h3>
      <ul style="padding-{align}:18px;margin:0;font-size:13px;">{green_li}</ul>
    </div>
    <div class="box" style="border-top:3px solid #f23645;">
      <h3 style="margin-top:0;color:#991b1b;">{'🔴 סיכונים ודגלים אדומים (Bear Case)' if is_he else '🔴 Bear Case & Red Flags'}</h3>
      <ul style="padding-{align}:18px;margin:0;font-size:13px;">{red_li}</ul>
    </div>
  </div>

  <h2>{'🎯 טבלת 9 מודלי הערכת השווי' if is_he else '🎯 9-Model Valuation Consensus Summary'}</h2>
  <table>
    <thead><tr><th>{'מודל' if is_he else 'Model'}</th><th>{'שווי הוגן (PV)' if is_he else 'Intrinsic Value'}</th><th>{'אפסייד / דאונסייד' if is_he else 'Upside / Downside'}</th><th>{'יעד ל-5 שנים (FV)' if is_he else '5-Year Target'}</th></tr></thead>
    <tbody>{val_rows_html}</tbody>
  </table>

  <h2>{'🔬 בדיקת איכות פורנזית — Piotroski F-Score (9 סעיפים)' if is_he else '🔬 Forensic Quality Checklist — Piotroski F-Score (9-Point Test)'}</h2>
  <table>
    <thead><tr><th>{'סטטוס' if is_he else 'Pass'}</th><th>{'בדיקה' if is_he else 'Criterion'}</th><th>{'נתון' if is_he else 'Reading'}</th></tr></thead>
    <tbody>{f_rows_html}</tbody>
  </table>

  <div class="footer">Generated automatically by Stocks Dashboard Quant Engine · For educational & analytical purposes only (Not financial advice).</div>
</div>
</body>
</html>"""
