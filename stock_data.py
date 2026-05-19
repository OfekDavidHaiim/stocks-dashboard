import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go


def fetch_financial_data(ticker_symbol: str):
    stock = yf.Ticker(ticker_symbol)

    try:
        financials = stock.financials.T
        balance_sheet = stock.balance_sheet.T
        history = stock.history(period="10y")
        info = stock.info
    except Exception:
        return None, None, None, None

    df_fin = financials.sort_index() if not financials.empty else pd.DataFrame()
    df_bs = balance_sheet.sort_index() if not balance_sheet.empty else pd.DataFrame()

    if not df_fin.empty:
        df_fin.index = pd.to_datetime(df_fin.index).year
        df_fin = df_fin[~df_fin.index.duplicated(keep='last')]

    if not df_bs.empty:
        df_bs.index = pd.to_datetime(df_bs.index).year
        df_bs = df_bs[~df_bs.index.duplicated(keep='last')]

    return df_fin, df_bs, history, info


def create_combo_chart(df: pd.DataFrame, column_name: str, title: str, color: str):
    if column_name not in df.columns or df[column_name].dropna().empty:
        return None

    chart_df = df[[column_name]].copy().dropna()
    chart_df['Value (B)'] = chart_df[column_name] / 1e9

    # Calculate percentage change using absolute value of the previous year
    # This prevents negative percentages when moving from a loss to a profit
    diff = chart_df[column_name].diff()
    abs_previous = chart_df[column_name].shift(1).abs()
    chart_df['Change (%)'] = (diff / abs_previous) * 100

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=chart_df.index,
        y=chart_df['Value (B)'],
        name='Value (Billion USD)',
        marker_color=color,
        opacity=0.8
    ))

    fig.add_trace(go.Scatter(
        x=chart_df.index,
        y=chart_df['Change (%)'],
        name='YoY Change (%)',
        yaxis='y2',
        mode='lines+markers+text',
        text=chart_df['Change (%)'].round(2).astype(str) + '%',
        textposition='top center',
        line=dict(color='#ff7f0e', width=3),
        marker=dict(size=8, color='#ff7f0e')
    ))

    fig.update_layout(
        title=title,
        xaxis=dict(title='Year', type='category'),
        yaxis=dict(title='Billions (USD)', side='left'),
        yaxis2=dict(title='Change (%)', overlaying='y', side='right', showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
        margin=dict(t=60, b=20)
    )

    return fig


def create_line_chart(series: pd.Series, title: str, y_label: str):
    if series.empty:
        return None

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=series.index,
        y=series.values,
        mode='lines',
        line=dict(color='#1f77b4', width=2),
        fill='tozeroy',
        fillcolor='rgba(31, 119, 180, 0.2)'
    ))

    fig.update_layout(
        title=title,
        xaxis=dict(title='Date'),
        yaxis=dict(title=y_label),
        hovermode="x unified",
        margin=dict(t=40, b=20)
    )
    return fig


st.set_page_config(page_title="Comprehensive Stock Dashboard", layout="wide")
st.title("10-Year Stock Financials Dashboard")

ticker_input = st.text_input("Enter Ticker Symbol (e.g., MSFT, AAPL, MELI):", "MSFT").upper()

if ticker_input:
    with st.spinner(f"Pulling data for {ticker_input}..."):
        df_fin, df_bs, history, info = fetch_financial_data(ticker_input)

        if history is not None and not history.empty:

            st.header("1. Market Data (10-Year Trend)")
            col1, col2 = st.columns(2)

            shares_out = info.get('sharesOutstanding', 1)
            history['Market Cap (T)'] = (history['Close'] * shares_out) / 1e12

            fig_mcap = create_line_chart(history['Market Cap (T)'], "Market Capitalization History", "Trillions (USD)")
            if fig_mcap:
                col1.plotly_chart(fig_mcap, width="stretch")

            trailing_eps = info.get('trailingEps', 0)
            if trailing_eps > 0:
                history['Estimated P/E'] = history['Close'] / trailing_eps
                fig_pe = create_line_chart(history['Estimated P/E'], "Estimated P/E Ratio History", "P/E Ratio")

                if fig_pe:
                    avg_pe = history['Estimated P/E'].mean()
                    fig_pe.add_hline(
                        y=avg_pe,
                        line_dash="dash",
                        line_color="red",
                        annotation_text=f"Average: {avg_pe:.1f}",
                        annotation_position="top left"
                    )
                    col2.plotly_chart(fig_pe, width="stretch")
            else:
                col2.info("P/E Ratio data not fully available.")

            st.markdown("---")
            st.header("2. Income Statement Metrics")

            if df_fin is not None and not df_fin.empty:

                # --- NEW: User Selection for Earnings Metric ---
                earnings_choice = st.radio(
                    "Select Earnings Metric to Display:",
                    ("Net Income (Bottom Line)", "Operating Income / EBIT"),
                    horizontal=True
                )

                col3, col4 = st.columns(2)

                # Revenue Chart
                rev_col = 'Total Revenue' if 'Total Revenue' in df_fin.columns else 'Operating Revenue'
                if rev_col in df_fin.columns:
                    fig_rev = create_combo_chart(df_fin, rev_col, "Annual Revenue", "#2ca02c")
                    if fig_rev: col3.plotly_chart(fig_rev, width="stretch")

                # Earnings Chart based on selection
                earn_target_col = None
                if earnings_choice == "Net Income (Bottom Line)":
                    earn_target_col = 'Net Income' if 'Net Income' in df_fin.columns else None
                else:
                    # Depending on the company, Yahoo Finance might use Operating Income or EBIT
                    if 'Operating Income' in df_fin.columns:
                        earn_target_col = 'Operating Income'
                    elif 'EBIT' in df_fin.columns:
                        earn_target_col = 'EBIT'

                if earn_target_col and earn_target_col in df_fin.columns:
                    fig_net = create_combo_chart(df_fin, earn_target_col, f"Annual Earnings ({earnings_choice})",
                                                 "#1f77b4")
                    if fig_net: col4.plotly_chart(fig_net, width="stretch")
                else:
                    col4.warning(f"Data for {earnings_choice} is not available for this ticker.")
            else:
                st.warning("Income statement data not available.")

            st.markdown("---")
            st.header("3. Balance Sheet Metrics")

            if df_bs is not None and not df_bs.empty:
                col5, col6 = st.columns(2)

                if 'Total Assets' in df_bs.columns:
                    fig_assets = create_combo_chart(df_bs, 'Total Assets', "Total Assets", "#9467bd")
                    if fig_assets: col5.plotly_chart(fig_assets, width="stretch")

                liab_col = 'Total Liabilities Net Minority Interest' if 'Total Liabilities Net Minority Interest' in df_bs.columns else 'Total Liabilities'
                if liab_col in df_bs.columns:
                    fig_liab = create_combo_chart(df_bs, liab_col, "Total Liabilities", "#d62728")
                    if fig_liab: col6.plotly_chart(fig_liab, width="stretch")

                col7, col8 = st.columns(2)

                if 'Total Debt' in df_bs.columns:
                    fig_debt = create_combo_chart(df_bs, 'Total Debt', "Total Debt", "#8c564b")
                    if fig_debt: col7.plotly_chart(fig_debt, width="stretch")

                cash_col = 'Cash And Cash Equivalents'
                if cash_col in df_bs.columns:
                    fig_cash = create_combo_chart(df_bs, cash_col, "Cash on Hand", "#17becf")
                    if fig_cash: col8.plotly_chart(fig_cash, width="stretch")
            else:
                st.warning("Balance sheet data not available.")

        else:
            st.error("Failed to retrieve data. Please verify the ticker symbol.")



if __name__ == "__main__":
    import sys
    from streamlit.web import cli as stcli
    from streamlit.runtime import exists

    # Run the Streamlit server only if it is not already running
    if not exists():
        sys.argv = ["streamlit", "run", __file__]
        sys.exit(stcli.main())