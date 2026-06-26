import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import urllib.parse
import requests
import os
import json

WATCHLISTS_FILE = "watchlists.json"

def load_watchlists():
    default_watchlists = {
        "Main Watchlist": [{"title": "General", "tickers": ['MSFT', 'SPOT', 'MELI', 'SOFI', 'SHAK', 'CELH', 'CRM', 'ADBE', 'V', 'NKE', 'ORCL', 'AUDC']}],
        "Semiconductors": [{"title": "General", "tickers": ['NVDA', 'AMD', 'TSM', 'ASML', 'AVGO', 'INTC']}],
        "Finance": [{"title": "General", "tickers": ['JPM', 'BAC', 'MS', 'GS', 'V', 'MA']}]
    }
    if not os.path.exists(WATCHLISTS_FILE):
        return default_watchlists
    try:
        with open(WATCHLISTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            cleaned_data = {}
            for name, content in data.items():
                if isinstance(content, list):
                    # Check if it is the new format (list of dicts with title & tickers)
                    # or the old format (list of strings)
                    is_new_format = True
                    for item in content:
                        if not isinstance(item, dict) or "title" not in item or "tickers" not in item:
                            is_new_format = False
                            break
                    
                    if is_new_format:
                        sections = []
                        for section in content:
                            cleaned_tickers = [str(t).upper().strip() for t in section.get("tickers", []) if t]
                            sections.append({
                                "title": str(section.get("title", "General")),
                                "tickers": cleaned_tickers
                            })
                        cleaned_data[str(name)] = sections
                    else:
                        # Old format: flat list of tickers
                        cleaned_tickers = [str(t).upper().strip() for t in content if t]
                        cleaned_data[str(name)] = [{"title": "General", "tickers": cleaned_tickers}]
                else:
                    cleaned_data[str(name)] = [{"title": "General", "tickers": []}]
            return cleaned_data if cleaned_data else default_watchlists
        return default_watchlists
    except Exception:
        return default_watchlists

def save_watchlists(watchlists_dict):
    try:
        with open(WATCHLISTS_FILE, "w", encoding="utf-8") as f:
            json.dump(watchlists_dict, f, ensure_ascii=False, indent=4)
    except Exception:
        pass


# --- Portfolio Management Helpers ---
PORTFOLIO_FILE = "portfolio.json"

def load_portfolio():
    default_portfolio = {
        "Discount": [
            {
                "id": "1",
                "symbol": "NVDA",
                "currency": "USD",
                "buys": [{"p": 102.98, "q": 52.0}],
                "sells": [],
                "currentPrice": 120.0,
                "prevClosePrice": 120.0,
                "locked": False
            }
        ]
    }
    if not os.path.exists(PORTFOLIO_FILE):
        return default_portfolio
    try:
        import random
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            data = {"Discount": data}
        if isinstance(data, dict):
            if not data:
                return default_portfolio
            for port_name, port_list in data.items():
                if not isinstance(port_list, list):
                    data[port_name] = []
                    continue
                for item in port_list:
                    if "id" not in item:
                        item["id"] = f"{pd.Timestamp.now().timestamp()}_{random.random()}"
                    if "symbol" not in item:
                        item["symbol"] = ""
                    if "currency" not in item:
                        item["currency"] = "USD"
                    if "buys" not in item:
                        item["buys"] = []
                    if "sells" not in item:
                        item["sells"] = []
                    if "currentPrice" not in item:
                        item["currentPrice"] = 0.0
                    elif isinstance(item["currentPrice"], (list, tuple)):
                        item["currentPrice"] = float(item["currentPrice"][0]) if len(item["currentPrice"]) > 0 else 0.0
                    
                    if "prevClosePrice" not in item:
                        item["prevClosePrice"] = item.get("currentPrice", 0.0)
                    elif isinstance(item["prevClosePrice"], (list, tuple)):
                        item["prevClosePrice"] = float(item["prevClosePrice"][0]) if len(item["prevClosePrice"]) > 0 else 0.0
                        
                    if "locked" not in item:
                        item["locked"] = False
            return data
        return default_portfolio
    except Exception:
        return default_portfolio

def save_portfolio(portfolio_data):
    try:
        with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
            json.dump(portfolio_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        st.error(f"Error saving portfolio: {e}")

def calculate_stock_metrics(stock):
    total_buy_qty = 0.0
    total_buy_cost_raw = 0.0
    for b in stock.get("buys", []):
        qty = float(b.get("q", 0.0))
        price = float(b.get("p", 0.0))
        total_buy_qty += qty
        total_buy_cost_raw += price * qty
        
    cost_factor = 100.0 if stock.get("currency") == "ILS" else 1.0
    
    total_initial_capital = total_buy_cost_raw / cost_factor
    avg_buy_price_raw = (total_buy_cost_raw / total_buy_qty) if total_buy_qty > 0 else 0.0
    
    total_sell_qty = 0.0
    total_sell_revenue_raw = 0.0
    for s in stock.get("sells", []):
        qty = float(s.get("q", 0.0))
        price = float(s.get("p", 0.0))
        total_sell_qty += qty
        total_sell_revenue_raw += price * qty
        
    total_sell_revenue = total_sell_revenue_raw / cost_factor
    remaining_qty = max(0.0, total_buy_qty - total_sell_qty)
    
    realized_pl = total_sell_revenue - ((avg_buy_price_raw / cost_factor) * total_sell_qty)
    curr_price = float(stock.get("currentPrice", 0.0))
    unrealized_pl = ((curr_price - avg_buy_price_raw) / cost_factor) * remaining_qty
    
    current_total_value = (remaining_qty * curr_price) / cost_factor
    remaining_cost_basis = remaining_qty * (avg_buy_price_raw / cost_factor)
    
    return {
        "avg_buy_price": avg_buy_price_raw,
        "realized_pl": realized_pl,
        "unrealized_pl": unrealized_pl,
        "current_total_value": current_total_value,
        "remaining_qty": remaining_qty,
        "remaining_cost_basis": remaining_cost_basis,
        "total_initial_capital": total_initial_capital
    }

def import_portfolio_csv(file_contents):
    import io
    import csv
    import random
    
    text_data = file_contents.decode("utf-8-sig")
    f = io.StringIO(text_data)
    
    first_line = next(f, None)
    if not first_line:
        return []
    delimiter = ";" if ";" in first_line else ","
    f.seek(0)
    
    reader = csv.reader(f, delimiter=delimiter)
    headers = [h.strip().replace('"', '') for h in next(reader, [])]
    
    col_map = {
        "symbol": -1,
        "price": -1,
        "qty": -1,
        "type": -1,
        "marketPrice": -1,
        "locked": -1,
        "currency": -1
    }
    
    for idx, h in enumerate(headers):
        h_lower = h.lower()
        if "מנייה" in h_lower or "symbol" in h_lower:
            col_map["symbol"] = idx
        elif "מחיר" in h_lower and "שוק" not in h_lower:
            col_map["price"] = idx
        elif "כמות" in h_lower or "quantity" in h_lower or "qty" in h_lower:
            col_map["qty"] = idx
        elif "סוג" in h_lower or "type" in h_lower:
            col_map["type"] = idx
        elif "מחיר שוק" in h_lower or "market" in h_lower or "current" in h_lower:
            col_map["marketPrice"] = idx
        elif "נעול" in h_lower or "locked" in h_lower:
            col_map["locked"] = idx
        elif "מטבע" in h_lower or "currency" in h_lower:
            col_map["currency"] = idx
            
    if col_map["symbol"] == -1: col_map["symbol"] = 0
    if col_map["price"] == -1: col_map["price"] = 1
    if col_map["qty"] == -1: col_map["qty"] = 2
    if col_map["type"] == -1: col_map["type"] = 3
    if col_map["marketPrice"] == -1: col_map["marketPrice"] = 4
    if col_map["locked"] == -1: col_map["locked"] = 5
    if col_map["currency"] == -1: col_map["currency"] = 6
    
    imported_data = {}
    for idx, row in enumerate(reader):
        if not row or len(row) < 3:
            continue
        try:
            sym = row[col_map["symbol"]].upper().strip()
            if not sym:
                continue
            
            p = float(row[col_map["price"]]) if col_map["price"] < len(row) else 0.0
            q = float(row[col_map["qty"]]) if col_map["qty"] < len(row) else 0.0
            t_type = row[col_map["type"]].upper().strip() if col_map["type"] < len(row) else "BUY"
            mkt_p = float(row[col_map["marketPrice"]]) if col_map["marketPrice"] < len(row) else 0.0
            is_locked = row[col_map["locked"]].upper().strip() == "YES" if col_map["locked"] < len(row) else False
            curr = row[col_map["currency"]].upper().strip() if col_map["currency"] < len(row) else "USD"
            
            if sym not in imported_data:
                imported_data[sym] = {
                    "id": f"{idx}_{pd.Timestamp.now().timestamp()}_{random.random()}",
                    "symbol": sym,
                    "buys": [],
                    "sells": [],
                    "currentPrice": mkt_p,
                    "prevClosePrice": mkt_p,
                    "locked": is_locked,
                    "currency": curr
                }
            
            if t_type == "SELL":
                imported_data[sym]["sells"].append({"p": p, "q": q})
            else:
                imported_data[sym]["buys"].append({"p": p, "q": q})
                
            if mkt_p > 0:
                imported_data[sym]["currentPrice"] = mkt_p
                imported_data[sym]["prevClosePrice"] = mkt_p
        except Exception:
            continue
            
    stocks_list = list(imported_data.values())
    for s in stocks_list:
        metrics = calculate_stock_metrics(s)
        s["_sort_qty"] = metrics["remaining_qty"]
        
    stocks_list.sort(key=lambda x: x["_sort_qty"] > 0, reverse=True)
    for s in stocks_list:
        if "_sort_qty" in s:
            del s["_sort_qty"]
            
    return stocks_list

def export_portfolio_csv(portfolio_data):
    import io
    import csv
    
    output = io.StringIO()
    output.write('\uFEFF')
    writer = csv.writer(output, delimiter=',')
    
    writer.writerow(["מנייה", "מחיר", "כמות", "סוג", "מחיר שוק", "נעול", "מטבע"])
    for s in portfolio_data:
        sym = s.get("symbol", "")
        mkt_p = s.get("currentPrice", 0.0)
        locked_str = "YES" if s.get("locked") else "NO"
        curr = s.get("currency", "USD")
        
        for b in s.get("buys", []):
            writer.writerow([sym, b.get("p", 0.0), b.get("q", 0.0), "BUY", mkt_p, locked_str, curr])
        for sl in s.get("sells", []):
            writer.writerow([sym, sl.get("p", 0.0), sl.get("q", 0.0), "SELL", mkt_p, locked_str, curr])
            
    return output.getvalue().encode("utf-8")

def get_portfolio_live_price(ticker_symbol: str, currency: str):
    try:
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period="2d")
        if not hist.empty:
            price = float(hist['Close'].iloc[-1])
            prev_close = float(hist['Close'].iloc[-2]) if len(hist) >= 2 else price
            return price, prev_close
    except Exception:
        pass
    return None, None

def get_usd_ils_rate():
    try:
        stock = yf.Ticker("USDILS=X")
        hist = stock.history(period="2d")
        if not hist.empty:
            price = hist['Close'].iloc[-1]
            return float(price)
    except Exception:
        pass
    return 3.70

# --- Internationalization ---
from translations import TRANSLATIONS

def cs() -> str:
    """Get dynamic currency symbol based on current stock currency."""
    return st.session_state.get("currency_symbol", "$")

def tr(key: str) -> str:
    """Translate UI string based on selected language and handle dynamic currency symbols."""
    lang = st.session_state.get("language", "en")
    val = TRANSLATIONS.get(lang, {}).get(key, key)
    symbol = cs()
    if symbol != "$" and isinstance(val, str):
        val = val.replace("$", symbol)
    return val

@st.cache_data
def translate_text(text: str, sl: str = "en", tl: str = "he") -> str:
    """Translates dynamic text like company description using Google Translate API."""
    if not text or text.strip() == "":
        return text
    if sl == tl:
        return text
    try:
        # Split text into paragraphs/chunks to avoid URL length limits
        paragraphs = text.split("\n")
        translated_paragraphs = []
        for para in paragraphs:
            para = para.strip()
            if not para:
                translated_paragraphs.append("")
                continue
            # Google Translate free endpoint
            encoded_text = urllib.parse.quote(para)
            url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={sl}&tl={tl}&dt=t&q={encoded_text}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                result = response.json()
                translated_segments = []
                for segment in result[0]:
                    if segment[0]:
                        translated_segments.append(segment[0])
                translated_paragraphs.append("".join(translated_segments))
            else:
                translated_paragraphs.append(para)
        return "\n".join(translated_paragraphs)
    except Exception:
        return text

def get_label(label_en: str) -> str:
    """Helper to dynamically translate label to Hebrew if active."""
    return translate_text(label_en) if st.session_state.get("language", "en") == "he" else label_en

# --- Session State Initialization ---
if 'watchlists' not in st.session_state:
    st.session_state.watchlists = load_watchlists()

if 'active_watchlist' not in st.session_state:
    st.session_state.active_watchlist = list(st.session_state.watchlists.keys())[0]

# Maintain reference list for read functions
st.session_state.watchlist = st.session_state.watchlists.get(st.session_state.active_watchlist, [])

if 'selected_ticker' not in st.session_state:
    st.session_state.selected_ticker = 'MSFT'

if 'page_selector' not in st.session_state:
    st.session_state.page_selector = "Dashboard"

# --- Language / Country selection ---
if "country" not in st.session_state:
    st.session_state.country = "USA"

if "currency_symbol" not in st.session_state:
    st.session_state.currency_symbol = "$"

country_options = [tr("usa"), tr("israel")]
country_index = 0 if st.session_state.country == "USA" else 1
selected_country_label = st.sidebar.selectbox(tr("select_country"), country_options, index=country_index)

new_country = "USA" if selected_country_label == tr("usa") else "Israel"
if new_country != st.session_state.country:
    st.session_state.country = new_country
    st.session_state.language = "en" if new_country == "USA" else "he"
    st.session_state.selected_ticker = "MSFT" if new_country == "USA" else "NICE.TA"
    st.session_state.currency_symbol = "$" if new_country == "USA" else "₪"
    st.rerun()

st.session_state.language = "en" if st.session_state.country == "USA" else "he"

# --- Global Premium Styling & Typography Injection ---
st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Rubik:wght@300;400;500;600;700&display=swap');
        
        /* Global TradingView Dark Theme styling */
        html, body, [data-testid="stAppViewContainer"], .main {
            background-color: #131722 !important;
            color: #d1d4dc !important;
            font-family: 'Outfit', 'Rubik', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
        }
        
        /* Sidebar styling */
        section[data-testid="stSidebar"] {
            background-color: #1c2030 !important;
            border-right: 1px solid #2a2e39 !important;
        }
        section[data-testid="stSidebar"] * {
            color: #d1d4dc !important;
            font-family: 'Outfit', 'Rubik', sans-serif !important;
        }
        
        /* Headers */
        h1, h2, h3, h4, h5, h6 {
            color: #ffffff !important;
            font-family: 'Outfit', 'Rubik', sans-serif !important;
            font-weight: 600 !important;
        }
        
        /* Inputs & Selectboxes */
        input, select, textarea, div[data-baseweb="input"], div[data-baseweb="select"], .stSelectbox, .stTextInput {
            background-color: #1c2030 !important;
            color: #ffffff !important;
        }
        
        /* Styled sub-elements of selects & inputs */
        div[role="listbox"], div[role="option"], ul {
            background-color: #1c2030 !important;
            color: #ffffff !important;
            border: 1px solid #2a2e39 !important;
        }
        
        /* Buttons */
        div.stButton > button {
            background-color: #2962ff !important;
            color: #ffffff !important;
            border: none !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
            font-family: 'Outfit', 'Rubik', sans-serif !important;
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
        }
        div.stButton > button:hover {
            background-color: #1e4bd8 !important;
            color: #ffffff !important;
            transform: translateY(-1px) !important;
            box-shadow: 0 4px 12px rgba(41, 98, 255, 0.3) !important;
        }
        
        /* Expanders */
        div[data-testid="stExpander"] {
            background-color: #1c2030 !important;
            border: 1px solid #2a2e39 !important;
            border-radius: 8px !important;
        }
        
        /* Tabs navigation */
        button[data-testid="stTabBarTab"] {
            color: #848e9c !important;
            background-color: transparent !important;
            border: none !important;
            font-weight: 500 !important;
            font-family: 'Outfit', 'Rubik', sans-serif !important;
            transition: all 0.2s ease !important;
        }
        button[data-testid="stTabBarTab"]:hover {
            color: #ffffff !important;
        }
        button[data-testid="stTabBarTab"][aria-selected="true"] {
            color: #2962ff !important;
            border-bottom: 2px solid #2962ff !important;
        }
        
        /* Metric cards */
        div[data-testid="metric-container"] {
            background-color: #1c2030 !important;
            border: 1px solid #2a2e39 !important;
            border-radius: 8px !important;
            padding: 15px !important;
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.3) !important;
        }
        div[data-testid="metric-container"] [data-testid="stMetricValue"] {
            color: #ffffff !important;
            font-weight: 700 !important;
        }
        div[data-testid="metric-container"] [data-testid="stMetricLabel"] {
            color: #848e9c !important;
        }
        
        /* Horizontal Rule */
        hr {
            border-top: 1px solid #2a2e39 !important;
        }
    </style>
    """,
    unsafe_allow_html=True
)

# --- RTL Styling Injection if Hebrew is Selected ---
if st.session_state.language == "he":
    st.markdown(
        """
        <style>
            [data-testid="stAppViewContainer"], [data-testid="stSidebar"] {
                direction: rtl !important;
                text-align: right !important;
            }
            .stMarkdown, .stText, .stTitle, .stHeader, .stSubheader, p, h1, h2, h3, h4, h5, h6, span, label, div {
                text-align: right !important;
            }
            .stRadio > label, .stSelectbox > label, .stSlider > label {
                text-align: right !important;
                display: block;
            }
            /* Correct column visual ordering in RTL */
            [data-testid="stHorizontalBlock"] {
                flex-direction: row-reverse !important;
            }
            [data-testid="column"] {
                direction: rtl !important;
                text-align: right !important;
            }
            /* Adjust sidebar options */
            [data-testid="stSidebarNav"] {
                direction: rtl !important;
            }
            /* Adjust tabs alignment in RTL */
            [data-testid="stTabBar"] {
                direction: rtl !important;
            }
        </style>
        """,
        unsafe_allow_html=True
    )


# --- TradingView Plotly Custom Styling & Monkeypatch ---
if not hasattr(st, "_orig_plotly_chart"):
    st._orig_plotly_chart = st.plotly_chart


# ============================================================
# SECTOR SENTIMENT INTELLIGENCE
# ============================================================
SECTOR_ETF_MAP = {
    "Technology":               ("XLK",  "Technology Select Sector SPDR"),
    "Financial Services":       ("XLF",  "Financial Select Sector SPDR"),
    "Financials":               ("XLF",  "Financial Select Sector SPDR"),
    "Healthcare":               ("XLV",  "Health Care Select Sector SPDR"),
    "Consumer Cyclical":        ("XLY",  "Consumer Discretionary SPDR"),
    "Consumer Defensive":       ("XLP",  "Consumer Staples SPDR"),
    "Industrials":              ("XLI",  "Industrial Select Sector SPDR"),
    "Basic Materials":          ("XLB",  "Materials Select Sector SPDR"),
    "Energy":                   ("XLE",  "Energy Select Sector SPDR"),
    "Real Estate":              ("XLRE", "Real Estate Select Sector SPDR"),
    "Utilities":                ("XLU",  "Utilities Select Sector SPDR"),
    "Communication Services":   ("XLC",  "Communication Services SPDR"),
    "Consumer Electronics":     ("XLY",  "Consumer Discretionary SPDR"),
    "Semiconductor":            ("SOXX", "iShares Semiconductor ETF"),
    "Software":                 ("IGV",  "iShares Expanded Tech-Software ETF"),
}

@st.cache_data(ttl=3600)
def get_sector_sentiment_data(ticker_symbol: str, sector: str):
    """
    Fetches 3-month performance data for both the stock and its sector ETF.
    Returns a dict with returns, divergence score, and chart-ready DataFrames.
    """
    result = {
        "etf_ticker": None, "etf_name": None,
        "stock_return_3m": None, "etf_return_3m": None,
        "divergence": None, "signal": "neutral",
        "stock_hist": None, "etf_hist": None,
        "stock_return_1m": None, "etf_return_1m": None,
        "stock_return_6m": None, "etf_return_6m": None,
        "stock_vol": None, "etf_vol": None,
    }

    # Find ETF for sector
    etf_info = SECTOR_ETF_MAP.get(sector)
    if not etf_info:
        return result
    etf_ticker, etf_name = etf_info
    result["etf_ticker"] = etf_ticker
    result["etf_name"] = etf_name

    try:
        # Fetch 7 months of data to cover 6m, 3m, 1m windows
        end = pd.Timestamp.now()
        start = end - pd.DateOffset(months=7)
        stock_hist = yf.download(ticker_symbol, start=start, end=end, progress=False, auto_adjust=True)
        etf_hist = yf.download(etf_ticker, start=start, end=end, progress=False, auto_adjust=True)

        if stock_hist.empty or etf_hist.empty:
            return result

        # Flatten MultiIndex if present
        if isinstance(stock_hist.columns, pd.MultiIndex):
            stock_hist.columns = stock_hist.columns.get_level_values(0)
        if isinstance(etf_hist.columns, pd.MultiIndex):
            etf_hist.columns = etf_hist.columns.get_level_values(0)

        def pct_return(df, months):
            lookback = end - pd.DateOffset(months=months)
            sub = df[df.index >= lookback]
            if len(sub) < 5:
                return None
            return ((sub["Close"].iloc[-1] / sub["Close"].iloc[0]) - 1) * 100

        result["stock_return_3m"] = pct_return(stock_hist, 3)
        result["etf_return_3m"]   = pct_return(etf_hist, 3)
        result["stock_return_1m"] = pct_return(stock_hist, 1)
        result["etf_return_1m"]   = pct_return(etf_hist, 1)
        result["stock_return_6m"] = pct_return(stock_hist, 6)
        result["etf_return_6m"]   = pct_return(etf_hist, 6)

        if result["stock_return_3m"] is not None and result["etf_return_3m"] is not None:
            result["divergence"] = result["stock_return_3m"] - result["etf_return_3m"]
            if result["divergence"] > 3:
                result["signal"] = "bullish"
            elif result["divergence"] < -3:
                result["signal"] = "bearish"
            else:
                result["signal"] = "neutral"

        # Normalize price series to 100 for comparison chart (use 3M window)
        lookback_3m = end - pd.DateOffset(months=3)
        s_slice = stock_hist[stock_hist.index >= lookback_3m]["Close"]
        e_slice = etf_hist[etf_hist.index >= lookback_3m]["Close"]
        if not s_slice.empty and not e_slice.empty:
            result["stock_hist"] = (s_slice / s_slice.iloc[0]) * 100
            result["etf_hist"]   = (e_slice / e_slice.iloc[0]) * 100

        # Annualized volatility
        def ann_vol(df, months):
            lookback = end - pd.DateOffset(months=months)
            sub = df[df.index >= lookback]["Close"].pct_change().dropna()
            if len(sub) < 10:
                return None
            return sub.std() * (252 ** 0.5) * 100

        result["stock_vol"] = ann_vol(stock_hist, 3)
        result["etf_vol"]   = ann_vol(etf_hist, 3)

    except Exception:
        pass

    return result


def create_sector_divergence_chart(stock_hist, etf_hist, ticker_symbol, etf_ticker):
    """Creates a normalized comparison chart of stock vs. sector ETF (base=100)."""
    fig = go.Figure()

    if stock_hist is not None and not stock_hist.empty:
        fig.add_trace(go.Scatter(
            x=stock_hist.index,
            y=stock_hist.values,
            name=ticker_symbol,
            line=dict(color='#2962ff', width=2.5),
            mode='lines'
        ))

    if etf_hist is not None and not etf_hist.empty:
        fig.add_trace(go.Scatter(
            x=etf_hist.index,
            y=etf_hist.values,
            name=f"{etf_ticker} (Sector)",
            line=dict(color='#f59e0b', width=2, dash='dot'),
            mode='lines'
        ))

    # Add baseline
    fig.add_hline(y=100, line_dash="dash", line_color="#444c5e", line_width=1)

    fig.update_layout(
        yaxis_title="Normalized Price (Base = 100)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=40, b=20, l=40, r=20),
        hovermode="x unified",
    )
    return fig


def create_sector_radar_chart(ticker_symbol, etf_ticker, divergence, stock_vol, etf_vol,
                               stock_3m, etf_3m, stock_1m, etf_1m):
    """Creates a radar chart comparing stock vs. sector across multiple dimensions."""
    import math

    def safe_score(val, center=0, scale=20, flip=False):
        if val is None:
            return 50
        score = 50 + (val - center) / scale * 50
        if flip:
            score = 100 - score
        return max(0, min(100, score))

    div_score  = safe_score(divergence, center=0, scale=15)
    mom_3m     = safe_score(stock_3m, center=0, scale=20)
    mom_1m     = safe_score(stock_1m, center=0, scale=10)
    # Lower volatility vs sector is better (flip)
    vol_rel    = 50
    if stock_vol is not None and etf_vol is not None and etf_vol > 0:
        vol_rel = safe_score(etf_vol - stock_vol, center=0, scale=10)  # positive = stock less volatile

    categories = ["Divergence vs Sector", "3M Momentum", "1M Momentum", "Relative Stability", "Divergence vs Sector"]
    values_stock = [div_score, mom_3m, mom_1m, vol_rel, div_score]

    # ETF baseline is always 50 (neutral)
    values_etf = [50, 50, 50, 50, 50]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values_stock,
        theta=categories,
        fill='toself',
        name=ticker_symbol,
        line=dict(color='#2962ff', width=2),
        fillcolor='rgba(41, 98, 255, 0.2)'
    ))
    fig.add_trace(go.Scatterpolar(
        r=values_etf,
        theta=categories,
        fill='toself',
        name=f"{etf_ticker} Sector Baseline",
        line=dict(color='#f59e0b', width=1.5, dash='dot'),
        fillcolor='rgba(245, 158, 11, 0.1)'
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], tickfont=dict(color='#848e9c', size=9)),
            angularaxis=dict(tickfont=dict(color='#d1d4dc', size=10))
        ),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5),
        margin=dict(t=30, b=60, l=60, r=60),
    )
    return fig


def apply_tradingview_plotly_style(fig):

    if fig is None:
        return None
    
    bg_color = '#1c2030'
    grid_color = '#2a2e39'
    text_color = '#d1d4dc'
    title_color = '#ffffff'
    
    if hasattr(fig, 'update_layout'):
        fig.update_layout(
            paper_bgcolor=bg_color,
            plot_bgcolor=bg_color,
            font=dict(
                family="'Outfit', 'Rubik', -apple-system, sans-serif",
                color=text_color,
                size=12
            ),
            title_font=dict(
                family="'Outfit', 'Rubik', -apple-system, sans-serif",
                color=title_color,
                size=15
            )
        )
        # Update legend
        fig.update_layout(
            legend=dict(
                bgcolor='rgba(28, 32, 48, 0.8)',
                bordercolor=grid_color,
                borderwidth=1,
                font=dict(color=text_color, size=10)
            )
        )
        
    if hasattr(fig, 'update_xaxes'):
        fig.update_xaxes(
            showgrid=True,
            gridcolor=grid_color,
            linecolor=grid_color,
            zerolinecolor=grid_color,
            title_font=dict(color=text_color, size=11),
            tickfont=dict(color=text_color, size=10)
        )
        
    if hasattr(fig, 'update_yaxes'):
        fig.update_yaxes(
            showgrid=True,
            gridcolor=grid_color,
            linecolor=grid_color,
            zerolinecolor=grid_color,
            title_font=dict(color=text_color, size=11),
            tickfont=dict(color=text_color, size=10)
        )
        
    if hasattr(fig, 'layout'):
        if hasattr(fig.layout, 'annotations') and fig.layout.annotations:
            for ann in fig.layout.annotations:
                if hasattr(ann, 'font') and ann.font:
                    if getattr(ann.font, 'color', None) in ['#4A5568', '#1A365D', 'black', 'rgba(0,0,0,1)', 'rgba(0,0,0,0.8)']:
                        ann.font.color = '#848e9c'
                    ann.font.family = "'Outfit', 'Rubik', sans-serif"
                    
    return fig

def plotly_chart_styled(fig, use_container_width=True, **kwargs):
    styled_fig = apply_tradingview_plotly_style(fig)
    return st._orig_plotly_chart(styled_fig, use_container_width=use_container_width, **kwargs)

st.plotly_chart = plotly_chart_styled

@st.cache_data(ttl=86400)
def get_company_name(ticker_symbol: str) -> str:
    try:
        stock = yf.Ticker(ticker_symbol)
        if stock.info and 'longName' in stock.info:
            return stock.info['longName']
    except Exception:
        pass
    return ticker_symbol

def calculate_technical_consensus(df: pd.DataFrame):
    if df.empty or len(df) < 14:
        return 50.0, tr("hold"), 50.0, 0.0, 0.0, 0.0
        
    close = df['Close']
    current_price = close.iloc[-1]
    
    sma_50 = close.rolling(window=50).mean().iloc[-1] if len(close) >= 50 else current_price
    sma_200 = close.rolling(window=200).mean().iloc[-1] if len(close) >= 200 else current_price
    
    # RSI
    delta = close.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=13, adjust=False).mean()
    ema_down = down.ewm(com=13, adjust=False).mean()
    rs = ema_up / (ema_down + 1e-10)
    rsi_series = 100 - (100 / (1 + rs))
    rsi = rsi_series.iloc[-1]
    
    buy_signals = 0
    sell_signals = 0
    neutral_signals = 0
    
    if rsi < 30:
        buy_signals += 2
    elif rsi < 45:
        buy_signals += 1
    elif rsi > 70:
        sell_signals += 2
    elif rsi > 55:
        sell_signals += 1
    else:
        neutral_signals += 1
        
    if current_price > sma_50:
        buy_signals += 1
    else:
        sell_signals += 1
        
    if current_price > sma_200:
        buy_signals += 1
    else:
        sell_signals += 1
        
    if sma_50 > sma_200:
        buy_signals += 1
    else:
        sell_signals += 1
        
    total_signals = buy_signals + sell_signals + neutral_signals
    if total_signals > 0:
        gauge_value = (buy_signals / total_signals) * 100
    else:
        gauge_value = 50.0
        
    if gauge_value >= 80:
        rec = tr("strong_buy")
    elif gauge_value >= 60:
        rec = tr("buy")
    elif gauge_value >= 40:
        rec = tr("hold")
    elif gauge_value >= 20:
        rec = tr("sell")
    else:
        rec = tr("strong_sell")
        
    return gauge_value, rec, rsi, sma_50, sma_200, current_price

def create_technical_gauge(gauge_value, recommendation):
    title_text = "קונצנזוס טכני" if st.session_state.language == "he" else "Technical Consensus"
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = gauge_value,
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': f"<b>{title_text}: {recommendation}</b>", 'font': {'size': 14, 'color': '#ffffff'}},
        gauge = {
            'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "#848e9c", 'tickvals': [10, 30, 50, 70, 90], 'ticktext': [tr("strong_sell"), tr("sell"), tr("hold"), tr("buy"), tr("strong_buy")]},
            'bar': {'color': "#2962ff", 'thickness': 0.25},
            'bgcolor': "#1c2030",
            'borderwidth': 2,
            'bordercolor': "#2a2e39",
            'steps': [
                {'range': [0, 30], 'color': 'rgba(242, 54, 69, 0.15)'},
                {'range': [30, 45], 'color': 'rgba(242, 54, 69, 0.08)'},
                {'range': [45, 55], 'color': 'rgba(132, 142, 156, 0.08)'},
                {'range': [55, 70], 'color': 'rgba(8, 153, 129, 0.08)'},
                {'range': [70, 100], 'color': 'rgba(8, 153, 129, 0.15)'}
            ],
            'threshold': {
                'line': {'color': "#2962ff", 'width': 4},
                'thickness': 0.75,
                'value': gauge_value
            }
        }
    ))
    fig.update_layout(
        paper_bgcolor='#1c2030',
        plot_bgcolor='#1c2030',
        height=280,
        margin=dict(l=30, r=30, t=50, b=20)
    )
    return fig


def render_financial_forecasting_tab(df_fin_a):
    if df_fin_a is None or df_fin_a.empty:
        st.info("נתוני דוחות פיננסיים שנתיים אינם זמינים עבור מניה זו לצורך חישוב תחזיות." if st.session_state.language == 'he' else "Annual financial statement data is not available for this stock to calculate projections.")
        return

    # Check for columns
    rev_col = 'Total Revenue' if 'Total Revenue' in df_fin_a.columns else ('Operating Revenue' if 'Operating Revenue' in df_fin_a.columns else None)
    ni_col = 'Net Income' if 'Net Income' in df_fin_a.columns else None

    if not rev_col and not ni_col:
        st.info("לא נמצאו עמודות הכנסות או רווח נקי בדוחות השנתיים." if st.session_state.language == 'he' else "No revenue or net income columns found in annual reports.")
        return

    title_text = "תחזית צמיחה פיננסית" if st.session_state.language == 'he' else "Financial Growth Projections"
    st.markdown(f"### 🔮 {title_text}")
    
    methodology_desc = (
        "תחזית זו מבוססת על ממוצע רבעוני שנתי (הכנסות ורווחים שנתיים חלקי 4). "
        "המערכת מחשבת את קצב הצמיחה ההיסטורי ומאפשרת לך להשליך אותו קדימה רבעון אחר רבעון."
        if st.session_state.language == 'he' else
        "This projection is based on the annual values divided by 4 to get the average quarterly figures. "
        "It calculates historical growth rates and projects them forward quarter by quarter."
    )
    st.info(methodology_desc)

    # Prepare historical data (sort years ascending, up to last 4 years)
    df_sorted = df_fin_a.sort_index(ascending=True)
    # Filter years with valid data
    valid_years = df_sorted.index.tolist()
    if len(valid_years) < 2:
        st.warning("נדרשת היסטוריה של שנתיים לפחות כדי לחשב קצב צמיחה." if st.session_state.language == 'he' else "At least 2 years of history are required to calculate growth rates.")
        return
        
    hist_years = valid_years[-4:]
    df_hist = df_sorted.loc[hist_years]
    
    sym = cs()
    
    # Calculate historical growth rates
    hist_rev = []
    rev_growths = []
    if rev_col and rev_col in df_hist.columns:
        hist_rev = df_hist[rev_col].dropna().tolist()
        for i in range(1, len(hist_rev)):
            if hist_rev[i-1] != 0:
                rev_growths.append((hist_rev[i] - hist_rev[i-1]) / abs(hist_rev[i-1]))
    
    hist_ni = []
    ni_growths = []
    if ni_col and ni_col in df_hist.columns:
        hist_ni = df_hist[ni_col].dropna().tolist()
        for i in range(1, len(hist_ni)):
            if hist_ni[i-1] != 0:
                ni_growths.append((hist_ni[i] - hist_ni[i-1]) / abs(hist_ni[i-1]))

    avg_rev_growth = sum(rev_growths) / len(rev_growths) if rev_growths else 0.10
    avg_ni_growth = sum(ni_growths) / len(ni_growths) if ni_growths else 0.10
    
    avg_rev_growth = max(-0.5, min(1.0, avg_rev_growth))
    avg_ni_growth = max(-0.5, min(1.0, avg_ni_growth))
    
    col_c1, col_c2, col_c3 = st.columns(3)
    
    with col_c1:
        rev_growth_pct = st.slider(
            "קצב צמיחה שנתי חזוי להכנסות (%)" if st.session_state.language == 'he' else "Projected Revenue Annual Growth (%)",
            min_value=-50.0, max_value=100.0,
            value=float(round(avg_rev_growth * 100, 1)),
            step=0.1,
            key="proj_rev_growth"
        ) / 100.0

    with col_c2:
        ni_growth_pct = st.slider(
            "קצב צמיחה שנתי חזוי לרווח נקי (%)" if st.session_state.language == 'he' else "Projected Net Income Annual Growth (%)",
            min_value=-50.0, max_value=100.0,
            value=float(round(avg_ni_growth * 100, 1)),
            step=0.1,
            key="proj_ni_growth"
        ) / 100.0

    with col_c3:
        horizon_quarters = st.selectbox(
            "טווח תחזית (רבעונים)" if st.session_state.language == 'he' else "Forecasting Horizon (Quarters)",
            options=[4, 8, 12, 16],
            index=2,
            key="proj_horizon"
        )

    view_mode = st.radio(
        "בחר אופן תצוגה:" if st.session_state.language == 'he' else "Select Visualization Mode:",
        options=["רבעוני (ממוצע לרבעון)" if st.session_state.language == 'he' else "Quarterly (Average per Quarter)",
                 "שנתי (סך הכל שנתי)" if st.session_state.language == 'he' else "Annual (Annual Total)"],
        horizontal=True,
        key="proj_view_mode"
    )
    is_quarterly_mode = "רבעוני" in view_mode or "Quarterly" in view_mode

    last_year = hist_years[-1]
    last_rev = df_hist.loc[last_year, rev_col] if (rev_col and rev_col in df_hist.columns and not pd.isna(df_hist.loc[last_year, rev_col])) else 0
    last_ni = df_hist.loc[last_year, ni_col] if (ni_col and ni_col in df_hist.columns and not pd.isna(df_hist.loc[last_year, ni_col])) else 0
    
    divisor = 1e9 if max(abs(last_rev), abs(last_ni)) > 1e9 else 1e6
    if st.session_state.language == 'he':
        unit_label = "מיליארד" if divisor == 1e9 else "מיליון"
    else:
        unit_label = "Billion" if divisor == 1e9 else "Million"

    rev_q_growth = (1 + rev_growth_pct)**(0.25) - 1 if rev_growth_pct > -1 else rev_growth_pct / 4.0
    ni_q_growth = (1 + ni_growth_pct)**(0.25) - 1 if ni_growth_pct > -1 else ni_growth_pct / 4.0

    hist_labels = [f"{y}" for y in hist_years]
    
    hist_rev_vals = [r / (1.0 if not is_quarterly_mode else 4.0) for r in df_hist[rev_col].tolist()] if rev_col else []
    hist_ni_vals = [n / (1.0 if not is_quarterly_mode else 4.0) for n in df_hist[ni_col].tolist()] if ni_col else []
    
    proj_rev_q = []
    proj_ni_q = []
    
    base_rev_q = last_rev / 4.0
    base_ni_q = last_ni / 4.0
    
    for q in range(1, horizon_quarters + 1):
        proj_rev_q.append(base_rev_q * ((1 + rev_q_growth) ** q))
        proj_ni_q.append(base_ni_q * ((1 + ni_q_growth) ** q))
        
    forecast_labels = []
    forecast_rev_vals = []
    forecast_ni_vals = []
    
    if is_quarterly_mode:
        for q in range(1, horizon_quarters + 1):
            q_num = ((q - 1) % 4) + 1
            yr_offset = (q - 1) // 4 + 1
            forecast_labels.append(f"Q{q_num} {last_year + yr_offset}")
            forecast_rev_vals.append(proj_rev_q[q - 1])
            forecast_ni_vals.append(proj_ni_q[q - 1])
    else:
        num_years = horizon_quarters // 4
        for y_offset in range(1, num_years + 1):
            forecast_labels.append(f"{last_year + y_offset} (Est)")
            q_start = (y_offset - 1) * 4
            forecast_rev_vals.append(sum(proj_rev_q[q_start:q_start+4]))
            forecast_ni_vals.append(sum(proj_ni_q[q_start:q_start+4]))

    all_labels = hist_labels + forecast_labels
    
    hist_rev_scaled = [v / divisor for v in hist_rev_vals]
    hist_ni_scaled = [v / divisor for v in hist_ni_vals]
    
    fore_rev_scaled = [v / divisor for v in forecast_rev_vals]
    fore_ni_scaled = [v / divisor for v in forecast_ni_vals]
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=hist_labels,
        y=hist_rev_scaled,
        name="הכנסות (היסטוריה)" if st.session_state.language == 'he' else "Revenue (History)",
        marker_color="#2962ff",
        opacity=0.85
    ))
    
    fig.add_trace(go.Bar(
        x=forecast_labels,
        y=fore_rev_scaled,
        name="הכנסות (תחזית)" if st.session_state.language == 'he' else "Revenue (Forecast)",
        marker_color="#089981",
        opacity=0.85
    ))
    
    fig.add_trace(go.Scatter(
        x=hist_labels,
        y=hist_ni_scaled,
        mode="lines+markers",
        name="רווח נקי (היסטוריה)" if st.session_state.language == 'he' else "Net Income (History)",
        line=dict(color="#f23645", width=3),
        marker=dict(size=8, color="#f23645")
    ))
    
    fig.add_trace(go.Scatter(
        x=forecast_labels,
        y=fore_ni_scaled,
        mode="lines+markers",
        name="רווח נקי (תחזית)" if st.session_state.language == 'he' else "Net Income (Forecast)",
        line=dict(color="#ff7f0e", width=3, dash="dash"),
        marker=dict(size=8, color="#ff7f0e")
    ))
    
    title_text = (
        f"תחזית הכנסות ורווח נקי - {unit_label} {sym}"
        if st.session_state.language == 'he' else
        f"Revenue & Net Income Forecast - {unit_label} {sym}"
    )
    
    fig.update_layout(
        title=f"<b>{title_text}</b>",
        xaxis_title="רבעון / שנה" if st.session_state.language == 'he' else "Quarter / Year",
        yaxis_title=f"{unit_label} {sym}",
        barmode="group",
        hovermode="x unified",
        margin=dict(t=60, b=40, l=40, r=40),
        legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5)
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    st.markdown(f"#### {'טבלת נתוני תחזית' if st.session_state.language == 'he' else 'Projection Data Table'}")
    
    table_data = []
    for idx, yr in enumerate(hist_years):
        table_data.append({
            "Period": str(yr),
            "Type": "היסטוריה" if st.session_state.language == 'he' else "History",
            "Revenue": hist_rev_vals[idx],
            "Net Income": hist_ni_vals[idx]
        })
    for idx, lbl in enumerate(forecast_labels):
        table_data.append({
            "Period": str(lbl),
            "Type": "תחזית" if st.session_state.language == 'he' else "Forecast",
            "Revenue": forecast_rev_vals[idx],
            "Net Income": forecast_ni_vals[idx]
        })
        
    df_table = pd.DataFrame(table_data)
    df_table["Period"] = df_table["Period"].astype(str)
    
    rev_growths_table = []
    ni_growths_table = []
    for i in range(len(df_table)):
        row_type = df_table.loc[i, "Type"]
        if row_type in ["היסטוריה", "History"]:
            if i == 0:
                rev_growths_table.append("-")
                ni_growths_table.append("-")
            else:
                prev_r = df_table.loc[i-1, "Revenue"]
                curr_r = df_table.loc[i, "Revenue"]
                prev_n = df_table.loc[i-1, "Net Income"]
                curr_n = df_table.loc[i, "Net Income"]
                
                r_change = ((curr_r - prev_r) / prev_r * 100) if prev_r != 0 else 0
                n_change = ((curr_n - prev_n) / prev_n * 100) if prev_n != 0 else 0
                
                rev_growths_table.append(f"{r_change:+.1f}%")
                ni_growths_table.append(f"{n_change:+.1f}%")
        else:
            r_change = rev_growth_pct * 100.0
            n_change = ni_growth_pct * 100.0
            label_suffix = " (שנתי)" if st.session_state.language == 'he' else " (YoY)"
            rev_growths_table.append(f"{r_change:+.1f}%{label_suffix}")
            ni_growths_table.append(f"{n_change:+.1f}%{label_suffix}")
            
    df_table[st.session_state.get("language","en") == "he" and "Revenue Growth" or "Revenue Growth"] = rev_growths_table
    df_table[st.session_state.get("language","en") == "he" and "Net Income Growth" or "Net Income Growth"] = ni_growths_table

    df_table["Revenue"] = df_table["Revenue"].apply(lambda x: f"{sym}{x/divisor:.2f} {unit_label}")
    df_table["Net Income"] = df_table["Net Income"].apply(lambda x: f"{sym}{x/divisor:.2f} {unit_label}")

    if st.session_state.language == 'he':
        df_table.columns = ["תקופה", "סוג", "הכנסות", "רווח נקי", "צמיחת הכנסות", "צמיחת רווח"]
    else:
        df_table.columns = ["Period", "Type", "Revenue", "Net Income", "Revenue Growth", "Net Income Growth"]

    st.dataframe(df_table, use_container_width=True, hide_index=True)


def render_manual_valuation_calculator(info, df_fin_a, ticker_sym=""):
    """
    Manual Valuation Calculator — Bull / Base / Bear scenarios.
    Auto-populates from live ticker data; user can override any field.
    ticker_sym is included in every widget key so switching stocks
    resets all inputs to the new stock's live values.
    """
    # Sanitize ticker for use as a key suffix (remove special chars)
    _k = ticker_sym.replace(".", "_").replace("-", "_").upper() if ticker_sym else "GENERIC"
    is_he = st.session_state.get("language", "en") == "he"

    # ─── Labels ───────────────────────────────────────────────────────────────
    def lbl(en, he): return he if is_he else en

    st.markdown("---")
    st.markdown(f"## 🧮 {lbl('Manual Valuation Calculator', 'מחשבון הערכת שווי ידנית')}")
    st.info(lbl(
        "Enter the company's financial assumptions below. Fields pre-filled from live data — override anything you like.",
        "הזן נתונים פיננסיים להערכת שווי. השדות ממולאים אוטומטית מהנתונים החיים — ניתן לשנות כל ערך."
    ))

    sym_cur = cs()
    shares_out = info.get('sharesOutstanding', 1) or 1
    current_price = info.get('currentPrice') or info.get('regularMarketPrice') or 0.0
    market_cap = info.get('marketCap') or (current_price * shares_out)
    trailing_pe = info.get('trailingPE') or 20.0
    forward_pe  = info.get('forwardPE')  or trailing_pe

    # Derive base revenue from financial statements
    base_rev = 0.0
    if df_fin_a is not None and not df_fin_a.empty:
        rev_col_f = 'Total Revenue' if 'Total Revenue' in df_fin_a.columns else (
            'Operating Revenue' if 'Operating Revenue' in df_fin_a.columns else None)
        if rev_col_f:
            vals = df_fin_a[rev_col_f].dropna()
            if not vals.empty:
                base_rev = float(vals.iloc[-1])
    if base_rev == 0:
        base_rev = info.get('totalRevenue') or 0.0

    base_rev_b = base_rev / 1e9  # convert to billions for display

    # Derive base margin
    net_income = 0.0
    if df_fin_a is not None and not df_fin_a.empty and 'Net Income' in df_fin_a.columns:
        ni_vals = df_fin_a['Net Income'].dropna()
        if not ni_vals.empty:
            net_income = float(ni_vals.iloc[-1])
    if net_income == 0:
        net_income = info.get('netIncomeToCommon') or 0.0
    base_margin = (net_income / base_rev * 100) if base_rev > 0 else (info.get('profitMargins', 0.15) * 100)
    base_margin = max(min(base_margin, 60.0), -30.0)

    # Auto-derive revenue growth
    auto_rev_growth = 15.0
    earn_g = info.get('earningsGrowth')
    rev_g  = info.get('revenueGrowth')
    if rev_g and not pd.isna(rev_g):
        auto_rev_growth = round(rev_g * 100, 1)
    elif earn_g and not pd.isna(earn_g):
        auto_rev_growth = round(earn_g * 100, 1)
    auto_rev_growth = max(min(auto_rev_growth, 100.0), -30.0)

    mc_b = market_cap / 1e9 if market_cap else 0.0

    # ─── Input Section ────────────────────────────────────────────────────────
    st.markdown(f"### {lbl('📥 Inputs', '📥 קלטים')}")

    ci1, ci2 = st.columns(2)
    with ci1:
        inp_base_rev = st.number_input(
            lbl("Base Revenue ($ Billion)", "הכנסות בסיס (מיליארד $)"),
            min_value=0.0, value=round(base_rev_b, 2), step=0.5, format="%.2f",
            key=f"mval_base_rev_{_k}"
        )
        inp_rev_growth = st.number_input(
            lbl("Revenue Growth Rate (%)", "קצב צמיחת הכנסות (%)"),
            min_value=-50.0, max_value=200.0, value=float(round(auto_rev_growth, 1)), step=0.5,
            key=f"mval_rev_growth_{_k}"
        )
        inp_margin = st.number_input(
            lbl("Target Net Profit Margin (%)", "מרווח רווח נקי יעד (%)"),
            min_value=-30.0, max_value=80.0, value=round(float(base_margin), 2), step=0.1,
            key=f"mval_margin_{_k}"
        )
        inp_forecast_years = st.number_input(
            lbl("Forecast Years", "מספר שנות תחזית"),
            min_value=1, max_value=10, value=5, step=1,
            key=f"mval_years_{_k}"
        )

    with ci2:
        inp_price = st.number_input(
            lbl(f"Current Share Price ({sym_cur})", f"מחיר מניה נוכחי ({sym_cur})"),
            min_value=0.0, value=float(round(current_price, 2)), step=0.5, format="%.2f",
            key=f"mval_price_{_k}"
        )
        inp_mc = st.number_input(
            lbl("Current Market Cap ($ Billion)", "שווי שוק נוכחי (מיליארד $)"),
            min_value=0.0, value=round(float(mc_b), 2), step=1.0, format="%.2f",
            key=f"mval_mc_{_k}"
        )
        inp_base_year = st.number_input(
            lbl("Starting Year", "שנת בסיס"),
            min_value=2000, max_value=2040,
            value=int(pd.Timestamp.now().year),
            step=1, key=f"mval_start_year_{_k}"
        )
        inp_shares_b = st.number_input(
            lbl("Shares Outstanding (Billion)", "מניות במחזור (מיליארד)"),
            min_value=0.001, value=round(shares_out / 1e9, 3), step=0.01, format="%.3f",
            key=f"mval_shares_{_k}"
        )

    # ─── P/E Multiples ────────────────────────────────────────────────────────
    st.markdown(f"### {lbl('📊 Valuation Multiples (P/E)', '📊 מכפילי הערכה (P/E)')}")
    low_default  = max(int(round(trailing_pe * 0.75)), 8)
    base_default = max(int(round(trailing_pe)), 12)
    high_default = max(int(round(trailing_pe * 1.35)), 15)

    pm1, pm2, pm3 = st.columns(3)
    with pm1:
        st.markdown(f"<p style='color:#F87171;font-weight:bold'>🐻 {lbl('Low (Bear)', 'נמוך / פסימי')}</p>", unsafe_allow_html=True)
        inp_pe_low = st.number_input("", min_value=1, value=low_default, step=1, key=f"mval_pe_low_{_k}", label_visibility="collapsed")
    with pm2:
        st.markdown(f"<p style='color:#60A5FA;font-weight:bold'>📊 {lbl('Base (Neutral)', 'בסיס / ניטרלי')}</p>", unsafe_allow_html=True)
        inp_pe_base = st.number_input("", min_value=1, value=base_default, step=1, key=f"mval_pe_base_{_k}", label_visibility="collapsed")
    with pm3:
        st.markdown(f"<p style='color:#34D399;font-weight:bold'>🐂 {lbl('High (Bull)', 'גבוה / אופטימי')}</p>", unsafe_allow_html=True)
        inp_pe_high = st.number_input("", min_value=1, value=high_default, step=1, key=f"mval_pe_high_{_k}", label_visibility="collapsed")

    # ─── Computation ──────────────────────────────────────────────────────────
    fcast_years = int(inp_forecast_years)
    shares_total = inp_shares_b * 1e9

    proj_rows = []
    for i in range(1, fcast_years + 1):
        yr = int(inp_base_year) + i
        rev_b = inp_base_rev * ((1 + inp_rev_growth / 100) ** i)
        profit_b = rev_b * (inp_margin / 100)
        proj_rows.append({
            lbl("Year", "שנה"): yr,
            lbl("Revenue ($B)", "הכנסות (מ$)"):  round(rev_b, 2),
            lbl("Margin (%)", "מרווח (%)"):      round(inp_margin, 2),
            lbl("Profit ($B)", "רווח (מ$)"):     round(profit_b, 3),
        })

    df_proj = pd.DataFrame(proj_rows)

    # Final year profit for valuation
    final_profit_b = df_proj[lbl("Profit ($B)", "רווח (מ$)")].iloc[-1]
    final_profit_total = final_profit_b * 1e9

    def calc_scenario(pe_multiple):
        future_mc   = final_profit_total * pe_multiple          # market cap in $
        future_mc_b = future_mc / 1e9
        target_price = (future_mc / shares_total) if shares_total > 0 else 0.0
        cagr = ((target_price / inp_price) ** (1 / fcast_years) - 1) * 100 if inp_price > 0 and target_price > 0 else 0.0
        upside = ((target_price - inp_price) / inp_price * 100) if inp_price > 0 else 0.0
        return {
            "target_price": target_price,
            "market_cap_b": future_mc_b,
            "cagr": cagr,
            "upside": upside,
            "pe": pe_multiple,
        }

    bear_res = calc_scenario(inp_pe_low)
    base_res = calc_scenario(inp_pe_base)
    bull_res = calc_scenario(inp_pe_high)

    # ─── Projection Table ─────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(f"### {lbl('📅 Revenue & Profit Projection', '📅 תחזית הכנסות ורווח')}")
    st.dataframe(df_proj, use_container_width=True, hide_index=True)

    # ─── Bar Chart ────────────────────────────────────────────────────────────
    fig_proj = go.Figure()
    years_labels = [str(r[lbl("Year", "שנה")]) for r in proj_rows]
    rev_vals  = [r[lbl("Revenue ($B)", "הכנסות (מ$)")] for r in proj_rows]
    prof_vals = [r[lbl("Profit ($B)", "רווח (מ$)")] for r in proj_rows]

    fig_proj.add_trace(go.Bar(
        x=years_labels, y=rev_vals,
        name=lbl("Revenue ($B)", "הכנסות (מ$)"),
        marker_color='#3B82F6', opacity=0.85,
        text=[f"{sym_cur}{v:.1f}B" for v in rev_vals], textposition='outside'
    ))
    fig_proj.add_trace(go.Bar(
        x=years_labels, y=prof_vals,
        name=lbl("Profit ($B)", "רווח (מ$)"),
        marker_color='#10B981', opacity=0.85,
        text=[f"{sym_cur}{v:.2f}B" for v in prof_vals], textposition='outside'
    ))
    fig_proj.update_layout(
        title=f"<b>{lbl('Revenue & Profit Forecast', 'תחזית הכנסות ורווח')} ({inp_rev_growth:.1f}% {lbl('growth', 'צמיחה')}, {inp_margin:.1f}% {lbl('margin', 'מרווח')})</b>",
        barmode='group', margin=dict(t=60, b=40, l=40, r=40),
        xaxis_title=lbl("Year", "שנה"),
        yaxis_title=lbl("$ Billion", "מיליארד $"),
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5)
    )
    st.plotly_chart(fig_proj, use_container_width=True)

    # ─── Scenario Cards ───────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(f"### 🎯 {lbl('Target Price Scenarios', 'תרחישי מחיר יעד')} — {fcast_years} {lbl('Year', 'שנה')}")

    def scenario_card(title, color, emoji, res, col):
        arrow = "▲" if res['upside'] >= 0 else "▼"
        col.markdown(f"""
<div style="border:2px solid {color};border-radius:12px;padding:18px;background:rgba(0,0,0,0.25);min-height:200px;">
  <p style="color:{color};font-size:16px;font-weight:bold;margin:0 0 10px 0;">{emoji} {title}</p>
  <table style="width:100%;font-size:13px;color:#E2E8F0;">
    <tr><td>{lbl('P/E Multiple:','מכפיל P/E:')}</td><td style="text-align:right;font-weight:bold;">{res['pe']}x</td></tr>
    <tr><td>{lbl('Target Price:','מחיר יעד:')}</td><td style="text-align:right;font-weight:bold;font-size:17px;color:{color};">{sym_cur}{res['target_price']:.1f}</td></tr>
    <tr><td>{lbl('Est. Market Cap:','שווי שוק משוער:')}</td><td style="text-align:right;">{sym_cur}{res['market_cap_b']:.1f}B</td></tr>
    <tr><td>{lbl('Upside from now:','פוטנציאל מהיום:')}</td><td style="text-align:right;color:{color};">{arrow}{abs(res['upside']):.1f}%</td></tr>
    <tr><td>{lbl('CAGR:','CAGR:')}</td><td style="text-align:right;color:{color};">{res['cagr']:.1f}% / {lbl('yr','שנה')}</td></tr>
  </table>
</div>""", unsafe_allow_html=True)

    sc1, sc2, sc3 = st.columns(3)
    scenario_card(lbl("🐻 Bear Valuation", "🐻 תרחיש פסימי"), "#F87171", "🐻", bear_res, sc1)
    scenario_card(lbl("📊 Base Valuation", "📊 תרחיש ניטרלי"), "#60A5FA", "📊", base_res, sc2)
    scenario_card(lbl("🐂 Bull Valuation", "🐂 תרחיש אופטימי"), "#34D399", "🐂", bull_res, sc3)

    # ─── Scenario Comparison Chart ────────────────────────────────────────────
    st.markdown("---")
    scenarios = [lbl("Bear", "פסימי"), lbl("Base", "ניטרלי"), lbl("Bull", "אופטימי")]
    target_prices = [bear_res['target_price'], base_res['target_price'], bull_res['target_price']]
    colors_sc = ["#F87171", "#60A5FA", "#34D399"]

    fig_sc = go.Figure()
    fig_sc.add_trace(go.Bar(
        x=scenarios, y=target_prices,
        marker_color=colors_sc,
        text=[f"{sym_cur}{p:.1f}" for p in target_prices],
        textposition='outside',
        textfont=dict(size=14, color='white'),
        width=0.4,
    ))
    fig_sc.add_hline(
        y=inp_price,
        line_dash="solid", line_color="#FBBF24", line_width=2.5,
        annotation_text=f"  {lbl('Current Price', 'מחיר נוכחי')}: {sym_cur}{inp_price:.2f}",
        annotation_position="top right",
        annotation_font=dict(color="#FBBF24", size=13)
    )
    fig_sc.update_layout(
        title=f"<b>{lbl('Scenario Target Prices', 'מחירי יעד לפי תרחיש')} ({fcast_years} {lbl('Year Horizon', 'שנים')})</b>",
        yaxis_title=lbl(f"Target Price ({sym_cur})", f"מחיר יעד ({sym_cur})"),
        margin=dict(t=60, b=40, l=40, r=40),
        showlegend=False
    )
    st.plotly_chart(fig_sc, use_container_width=True)

    # ─── Summary Table ────────────────────────────────────────────────────────
    summary_data = [
        {lbl("Scenario","תרחיש"): lbl("🐻 Bear","🐻 פסימי"),   lbl("P/E","P/E"): f"{inp_pe_low}x",  lbl("Target Price","מחיר יעד"): f"{sym_cur}{bear_res['target_price']:.2f}", lbl("Market Cap","שווי שוק"): f"{sym_cur}{bear_res['market_cap_b']:.1f}B", lbl("Upside","פוטנציאל"): f"{bear_res['upside']:+.1f}%", lbl("CAGR","CAGR"): f"{bear_res['cagr']:.1f}%"},
        {lbl("Scenario","תרחיש"): lbl("📊 Base","📊 ניטרלי"),  lbl("P/E","P/E"): f"{inp_pe_base}x", lbl("Target Price","מחיר יעד"): f"{sym_cur}{base_res['target_price']:.2f}", lbl("Market Cap","שווי שוק"): f"{sym_cur}{base_res['market_cap_b']:.1f}B", lbl("Upside","פוטנציאל"): f"{base_res['upside']:+.1f}%", lbl("CAGR","CAGR"): f"{base_res['cagr']:.1f}%"},
        {lbl("Scenario","תרחיש"): lbl("🐂 Bull","🐂 אופטימי"), lbl("P/E","P/E"): f"{inp_pe_high}x", lbl("Target Price","מחיר יעד"): f"{sym_cur}{bull_res['target_price']:.2f}", lbl("Market Cap","שווי שוק"): f"{sym_cur}{bull_res['market_cap_b']:.1f}B", lbl("Upside","פוטנציאל"): f"{bull_res['upside']:+.1f}%", lbl("CAGR","CAGR"): f"{bull_res['cagr']:.1f}%"},
    ]
    st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)




# --- Helper Functions ---
@st.cache_data(ttl=300)
def get_ticker_tape_prices():
    tickers = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "TSLA", "NICE.TA", "TEVA"]
    tape_data = []
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            symbol_upper = ticker.upper()
            is_tase = symbol_upper.endswith(".TA")
            scale = 0.01 if is_tase else 1.0
            currency_sym = "₪" if is_tase else "$"
            
            if len(hist) >= 2:
                price = hist['Close'].iloc[-1] * scale
                prev = hist['Close'].iloc[-2] * scale
                change = ((price - prev) / prev) * 100
                tape_data.append({"ticker": ticker, "price": price, "change": change, "symbol": currency_sym})
            elif len(hist) == 1:
                price = hist['Close'].iloc[-1] * scale
                tape_data.append({"ticker": ticker, "price": price, "change": 0.0, "symbol": currency_sym})
        except Exception:
            pass
    return tape_data

def render_ticker_tape():
    tape_data = get_ticker_tape_prices()
    if not tape_data:
        return
    
    html_items = []
    for item in tape_data:
        color = "#089981" if item['change'] >= 0 else "#f23645"
        sign = "+" if item['change'] >= 0 else ""
        html_items.append(
            f'<span style="color: #ffffff; margin-left: 30px;">{item["ticker"]}</span> &nbsp;'
            f'<span style="color: #d1d4dc;">{item["symbol"]}{item["price"]:.2f}</span> &nbsp;'
            f'<span style="color: {color};">{sign}{item["change"]:.2f}%</span>'
        )
    
    joined_items = " &nbsp;&nbsp;|&nbsp;&nbsp; ".join(html_items)
    
    st.markdown(
        f"""
        <div style="background-color: #1c2030; border: 1px solid #2a2e39; border-radius: 8px; padding: 8px 15px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.15); overflow: hidden;">
            <marquee scrollamount="4" scrolldelay="20" direction="left" onmouseover="this.stop();" onmouseout="this.start();" style="font-family: 'Outfit', 'Rubik', sans-serif; font-size: 13px; font-weight: bold; vertical-align: middle;">
                {joined_items}
            </marquee>
        </div>
        """,
        unsafe_allow_html=True
    )

def fetch_financial_data(ticker_symbol: str):
    stock = yf.Ticker(ticker_symbol)

    try:
        financials = stock.financials.T
        balance_sheet = stock.balance_sheet.T
        cashflow = stock.cashflow.T
        quarterly_financials = stock.quarterly_financials.T
        quarterly_balance_sheet = stock.quarterly_balance_sheet.T
        quarterly_cashflow = stock.quarterly_cashflow.T
        history = stock.history(period="10y")
        info = dict(stock.info) if stock.info else {}
    except Exception:
        return None, None, None, None, None, None, None, None

    # Handle ILA Agora currency scaling to standard Shekels (ILS)
    try:
        if info:
            currency = info.get("currency", "USD")
            if currency == "ILA":
                scale = 0.01
                if history is not None and not history.empty:
                    for col in ['Open', 'High', 'Low', 'Close']:
                        if col in history.columns:
                            history[col] = history[col] * scale
                # Scale info price-related fields
                price_keys = [
                    'currentPrice', 'trailingEps', 'dividendRate', 'fiftyTwoWeekHigh', 
                    'fiftyTwoWeekLow', 'fiftyDayAverage', 'twoHundredDayAverage',
                    'targetHighPrice', 'targetLowPrice', 'targetMeanPrice', 'targetMedianPrice',
                    'bookValue', 'navPrice'
                ]
                for key in price_keys:
                    if key in info and info[key] is not None:
                        try:
                            info[key] = info[key] * scale
                        except Exception:
                            pass
    except Exception:
        pass

    df_fin_a = financials.sort_index() if not financials.empty else pd.DataFrame()
    df_bs_a = balance_sheet.sort_index() if not balance_sheet.empty else pd.DataFrame()
    df_cf_a = cashflow.sort_index() if not cashflow.empty else pd.DataFrame()

    df_fin_q = quarterly_financials.sort_index() if not quarterly_financials.empty else pd.DataFrame()
    df_bs_q = quarterly_balance_sheet.sort_index() if not quarterly_balance_sheet.empty else pd.DataFrame()
    df_cf_q = quarterly_cashflow.sort_index() if not quarterly_cashflow.empty else pd.DataFrame()

    if not df_fin_a.empty:
        df_fin_a.index = pd.to_datetime(df_fin_a.index).year
        df_fin_a = df_fin_a[~df_fin_a.index.duplicated(keep='last')]

    if not df_bs_a.empty:
        df_bs_a.index = pd.to_datetime(df_bs_a.index).year
        df_bs_a = df_bs_a[~df_bs_a.index.duplicated(keep='last')]

    if not df_cf_a.empty:
        df_cf_a.index = pd.to_datetime(df_cf_a.index).year
        df_cf_a = df_cf_a[~df_cf_a.index.duplicated(keep='last')]

    if not df_fin_q.empty:
        df_fin_q.index = pd.to_datetime(df_fin_q.index).to_period('Q').astype(str)
        df_fin_q = df_fin_q[~df_fin_q.index.duplicated(keep='last')]

    if not df_bs_q.empty:
        df_bs_q.index = pd.to_datetime(df_bs_q.index).to_period('Q').astype(str)
        df_bs_q = df_bs_q[~df_bs_q.index.duplicated(keep='last')]

    if not df_cf_q.empty:
        df_cf_q.index = pd.to_datetime(df_cf_q.index).to_period('Q').astype(str)
        df_cf_q = df_cf_q[~df_cf_q.index.duplicated(keep='last')]

    return df_fin_a, df_bs_a, df_cf_a, df_fin_q, df_bs_q, df_cf_q, history, info

def get_live_price_info(ticker_symbol: str):
    try:
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period="2d")
        symbol_upper = ticker_symbol.upper().strip()
        is_tase = symbol_upper.endswith(".TA")
        scale = 0.01 if is_tase else 1.0
        symbol = "₪" if is_tase else "$"
        
        if len(hist) >= 2:
            current_price = hist['Close'].iloc[-1] * scale
            prev_close = hist['Close'].iloc[-2] * scale
            daily_change = ((current_price - prev_close) / prev_close) * 100
            return current_price, daily_change, symbol
        elif len(hist) == 1:
            return hist['Close'].iloc[-1] * scale, 0.0, symbol
    except Exception:
        return None, None, "$"
    return None, None, "$"


def create_combo_chart(df: pd.DataFrame, column_name: str, title: str, color: str, change_label: str = None, x_label: str = None, value_label: str = None, y_title: str = None, divisor: float = 1e9):
    if column_name not in df.columns or df[column_name].dropna().empty:
        return None

    if change_label is None:
        change_label = tr("yoy_change")
    if x_label is None:
        x_label = tr("year")
    if value_label is None:
        value_label = tr("value_billion_usd")
    if y_title is None:
        y_title = tr("billions_usd")

    chart_df = df[[column_name]].copy().dropna()
    chart_df['Scaled_Value'] = chart_df[column_name] / divisor

    diff = chart_df[column_name].diff()
    abs_previous = chart_df[column_name].shift(1).abs()
    chart_df['Change (%)'] = (diff / abs_previous) * 100

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=chart_df.index,
        y=chart_df['Scaled_Value'],
        name=value_label,
        marker_color=color,
        opacity=0.8
    ))

    fig.add_trace(go.Scatter(
        x=chart_df.index,
        y=chart_df['Change (%)'],
        name=change_label,
        yaxis='y2',
        mode='lines+markers+text',
        text=chart_df['Change (%)'].round(2).astype(str) + '%',
        textposition='top center',
        line=dict(color='#ff7f0e', width=3),
        marker=dict(size=8, color='#ff7f0e')
    ))

    fig.update_layout(
        title=title,
        xaxis=dict(title=x_label, type='category'),
        yaxis=dict(title=y_title, side='left'),
        yaxis2=dict(title=change_label, overlaying='y', side='right', showgrid=False),
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
        xaxis=dict(title=tr("date_label")),
        yaxis=dict(title=y_label),
        hovermode="x unified",
        margin=dict(t=40, b=20)
    )
    return fig




def _get_risk_free_rate():
    """Attempt to fetch the current 10-Year US Treasury yield from yfinance; fall back to 4.5%."""
    try:
        import yfinance as _yf
        tnx = _yf.Ticker("^TNX")
        hist = tnx.history(period="5d")
        if hist is not None and not hist.empty:
            rate = hist['Close'].iloc[-1]
            if rate and rate > 0:
                return round(rate, 2)
    except Exception:
        pass
    return 4.5  # current approximate 10Y US yield


def _compute_wacc(info, risk_free_rate=4.5, market_premium=5.5, fallback_discount=10.0):
    """
    Compute WACC using CAPM for cost of equity and after-tax cost of debt.
    Returns (wacc_pct, beta_used, cost_of_equity_pct, notes).
    """
    beta = info.get('beta')
    if beta is None or pd.isna(beta) or beta <= 0:
        beta = 1.1  # market average

    cost_of_equity = risk_free_rate + beta * market_premium

    total_debt = info.get('totalDebt', 0) or 0
    total_cash = info.get('totalCash', 0) or 0
    market_cap = info.get('marketCap', 0) or 0
    net_debt = max(total_debt - total_cash, 0)
    total_capital = market_cap + net_debt

    if total_capital <= 0 or net_debt <= 0:
        # All equity — WACC equals cost of equity
        wacc = cost_of_equity
    else:
        equity_weight = market_cap / total_capital
        debt_weight = net_debt / total_capital
        tax_rate = 0.21  # US corporate tax rate
        interest_expense = info.get('interestExpense', 0) or 0
        if interest_expense < 0:
            interest_expense = abs(interest_expense)
        cost_of_debt_pretax = (interest_expense / net_debt * 100) if net_debt > 0 else risk_free_rate + 1.5
        cost_of_debt_pretax = min(max(cost_of_debt_pretax, risk_free_rate), 15.0)
        cost_of_debt_aftertax = cost_of_debt_pretax * (1 - tax_rate)
        wacc = equity_weight * cost_of_equity + debt_weight * cost_of_debt_aftertax

    wacc = min(max(wacc, 6.0), 18.0)
    return round(wacc, 2), round(beta, 2), round(cost_of_equity, 2)


def _derive_growth_rates(info, df_fin, base_growth):
    """
    Derive separate growth rates for EPS, Revenue, and FCF from available data.
    Returns dict: {eps_g, rev_g, fcf_g} each as a percentage (e.g. 12.5 for 12.5%).
    """
    def clamp(v, lo=-20.0, hi=50.0):
        return min(max(v, lo), hi)

    # --- EPS growth ---
    eps_g = base_growth
    earn_growth = info.get('earningsGrowth')
    if earn_growth is not None and not pd.isna(earn_growth) and earn_growth > -0.5:
        eps_g = clamp(earn_growth * 100)
    elif df_fin is not None and not df_fin.empty:
        eps_col = 'Diluted EPS' if 'Diluted EPS' in df_fin.columns else (
            'Basic EPS' if 'Basic EPS' in df_fin.columns else None)
        if eps_col:
            eps_series = df_fin[eps_col].dropna()
            eps_series = eps_series[eps_series > 0]
            if len(eps_series) >= 2:
                start_eps = eps_series.iloc[0]
                end_eps = eps_series.iloc[-1]
                n = len(eps_series) - 1
                if start_eps > 0:
                    cagr = ((end_eps / start_eps) ** (1 / n) - 1) * 100
                    eps_g = clamp(cagr)

    # --- Revenue growth ---
    rev_g = base_growth
    rev_growth = info.get('revenueGrowth')
    if rev_growth is not None and not pd.isna(rev_growth) and rev_growth > -0.5:
        rev_g = clamp(rev_growth * 100)
    elif df_fin is not None and not df_fin.empty:
        rev_col = 'Total Revenue' if 'Total Revenue' in df_fin.columns else (
            'Operating Revenue' if 'Operating Revenue' in df_fin.columns else None)
        if rev_col:
            rev_series = df_fin[rev_col].dropna()
            rev_series = rev_series[rev_series > 0]
            if len(rev_series) >= 2:
                start_rev = rev_series.iloc[0]
                end_rev = rev_series.iloc[-1]
                n = len(rev_series) - 1
                if start_rev > 0:
                    cagr = ((end_rev / start_rev) ** (1 / n) - 1) * 100
                    rev_g = clamp(cagr)

    # --- FCF growth ---
    fcf_g = eps_g  # default to earnings growth as proxy
    # Try to estimate from operating CF trend if available
    if df_fin is not None and not df_fin.empty:
        ocf_col = 'Operating Cash Flow' if 'Operating Cash Flow' in df_fin.columns else None
        if ocf_col:
            ocf_series = df_fin[ocf_col].dropna()
            ocf_series = ocf_series[ocf_series > 0]
            if len(ocf_series) >= 2:
                n = len(ocf_series) - 1
                start_ocf = ocf_series.iloc[0]
                end_ocf = ocf_series.iloc[-1]
                if start_ocf > 0:
                    cagr = ((end_ocf / start_ocf) ** (1 / n) - 1) * 100
                    fcf_g = clamp(cagr)

    return {'eps_g': eps_g, 'rev_g': rev_g, 'fcf_g': fcf_g}


def calculate_valuations(info, df_fin, avg_pe, growth_rate, discount_rate=10.0, years=5,
                         terminal_growth=2.5, use_wacc=True):
    valuations = {}
    shares_out = info.get('sharesOutstanding', 1)
    if not shares_out or pd.isna(shares_out) or shares_out <= 0:
        shares_out = 1

    current_price = info.get('currentPrice')
    if not current_price or pd.isna(current_price) or current_price <= 0:
        return valuations

    trailing_eps = info.get('trailingEps')
    book_value = info.get('bookValue')

    # Detect currency to format description strings
    currency = info.get("currency", "USD") if info else "USD"
    sym = "₪" if currency in ["ILA", "ILS"] else ("£" if currency in ["GBp", "GBP"] else ("€" if currency == "EUR" else "$"))

    # --- WACC: Auto compute or use provided discount_rate ---
    rf_rate = 4.5  # will be overridden by session cache if available
    if use_wacc and info:
        try:
            wacc_val, beta_val, coe_val = _compute_wacc(info, risk_free_rate=rf_rate)
            discount_rate_used = wacc_val
        except Exception:
            discount_rate_used = discount_rate
            beta_val = info.get('beta', 1.1) or 1.1
            coe_val = rf_rate + beta_val * 5.5
    else:
        discount_rate_used = discount_rate
        beta_val = info.get('beta', 1.1) or 1.1
        coe_val = discount_rate

    dr = discount_rate_used  # short alias

    # --- Differentiated per-model growth rates ---
    base_growth_val = growth_rate if (growth_rate is not None and not pd.isna(growth_rate)) else 10.0
    derived = _derive_growth_rates(info, df_fin, base_growth_val)
    eps_g = derived['eps_g']
    rev_g = derived['rev_g']
    fcf_g_raw = derived['fcf_g']

    # Safety clamps per model type
    def clamp_g(v, lo=-20.0, hi=50.0):
        return min(max(v, lo), hi)

    pe_g  = clamp_g(eps_g, -10.0, 40.0)
    rev_g = clamp_g(rev_g, -10.0, 40.0)
    fcf_g = clamp_g(fcf_g_raw, -10.0, 40.0)
    tg    = clamp_g(terminal_growth, 0.0, 5.0)

    # --- Shared base data ---
    total_revenue = info.get('totalRevenue')
    if (total_revenue is None or pd.isna(total_revenue)) and df_fin is not None and not df_fin.empty:
        rev_col = 'Total Revenue' if 'Total Revenue' in df_fin.columns else (
            'Operating Revenue' if 'Operating Revenue' in df_fin.columns else None)
        if rev_col:
            total_revenue = df_fin[rev_col].iloc[-1]
    if total_revenue is None or pd.isna(total_revenue) or total_revenue <= 0:
        total_revenue = (current_price * shares_out) / 3.0

    # EPS with smart fallback
    is_eps_normalized = False
    eps = trailing_eps
    if eps is None or pd.isna(eps) or eps <= 0:
        # Try Net Income / shares
        net_income = info.get('netIncomeToCommon') or info.get('netIncome')
        if net_income and net_income > 0:
            eps = net_income / shares_out
        else:
            eps = current_price / 15.0
            is_eps_normalized = True

    # FCF with improved fallback chain
    is_fcf_normalized = False
    fcf = info.get('freeCashflow')
    if fcf is None or pd.isna(fcf) or fcf <= 0:
        # Try: Operating CF - CapEx from df_fin
        ocf = info.get('operatingCashflow')
        capex = info.get('capitalExpenditures')
        if ocf and ocf > 0:
            capex_val = abs(capex) if capex else 0
            fcf = ocf - capex_val
            if fcf <= 0:
                fcf = None
        if not fcf or fcf <= 0:
            # Fall back to Net Income × 0.70 (much better than Revenue × 0.10)
            net_income = info.get('netIncomeToCommon') or info.get('netIncome')
            if net_income and net_income > 0:
                fcf = net_income * 0.70
                is_fcf_normalized = True
            else:
                fcf = total_revenue * 0.08
                is_fcf_normalized = True

    fcf_per_share = fcf / shares_out

    # Net Debt
    total_debt = info.get('totalDebt', 0) or 0
    total_cash = info.get('totalCash', 0) or 0
    if pd.isna(total_debt): total_debt = 0
    if pd.isna(total_cash): total_cash = 0
    net_debt = max(total_debt - total_cash, 0)
    net_debt_per_share = (total_debt - total_cash) / shares_out

    # Dynamic Graham bond yield (use session-cached or derive)
    graham_bond_yield = rf_rate + 0.5  # approx corp bond = rf + 0.5%
    graham_bond_yield = min(max(graham_bond_yield, 3.5), 8.0)

    conservative_pe = min(max(avg_pe, 10.0), 30.0) if (avg_pe and not pd.isna(avg_pe)) else 15.0

    # =========================================================
    # MODEL 1: P/E Earnings Projection
    # =========================================================
    eps_desc = f"Projects trailing EPS ({sym}{eps:.2f}) [Normalized]" if is_eps_normalized else f"Projects trailing EPS ({sym}{eps:.2f})"
    future_eps_pe = eps * ((1 + pe_g / 100) ** years)
    future_price_pe = future_eps_pe * conservative_pe
    intrinsic_pe = future_price_pe / ((1 + dr / 100) ** years)

    valuations['P/E Earnings Projection'] = {
        'intrinsic_value': intrinsic_pe,
        'future_price_5y': future_price_pe,
        'future_price': future_price_pe,
        'growth_used': pe_g,
        'discount_used': dr,
        'weight': 0.15,
        'description': f"{eps_desc} → {years}yr at EPS growth {pe_g:.1f}%, exit P/E {conservative_pe:.1f}x, WACC {dr:.1f}%."
    }

    # =========================================================
    # MODEL 2: P/S Revenue Projection
    # =========================================================
    current_rev_per_share = total_revenue / shares_out
    is_rev_normalized = (total_revenue == (current_price * shares_out) / 3.0)
    future_rev_per_share = current_rev_per_share * ((1 + rev_g / 100) ** years)

    target_ps = info.get('priceToSalesTrailing12Months')
    if target_ps is None or pd.isna(target_ps) or target_ps <= 0:
        target_ps = current_price / current_rev_per_share if current_rev_per_share > 0 else 3.0
    target_ps = min(max(target_ps, 0.3), 12.0)

    future_price_ps = future_rev_per_share * target_ps
    intrinsic_ps = future_price_ps / ((1 + dr / 100) ** years)

    rev_desc = f"Projects Revenue Per Share ({sym}{current_rev_per_share:.2f}) [Normalized]" if is_rev_normalized else f"Projects Revenue Per Share ({sym}{current_rev_per_share:.2f})"
    valuations['P/S Revenue Projection'] = {
        'intrinsic_value': intrinsic_ps,
        'future_price_5y': future_price_ps,
        'future_price': future_price_ps,
        'growth_used': rev_g,
        'discount_used': dr,
        'weight': 0.10,
        'description': f"{rev_desc} → {years}yr at revenue growth {rev_g:.1f}%, exit P/S {target_ps:.1f}x, WACC {dr:.1f}%."
    }

    # =========================================================
    # MODEL 3: FCF Projection
    # =========================================================
    future_fcf_per_share = fcf_per_share * ((1 + fcf_g / 100) ** years)

    target_fcf_multiple = info.get('priceToFreeCashflow')
    if target_fcf_multiple is None or pd.isna(target_fcf_multiple) or target_fcf_multiple <= 0:
        target_fcf_multiple = conservative_pe * 1.1  # FCF multiples tend to track PE
    target_fcf_multiple = min(max(target_fcf_multiple, 10.0), 35.0)

    future_price_fcf = future_fcf_per_share * target_fcf_multiple
    intrinsic_fcf = future_price_fcf / ((1 + dr / 100) ** years)

    fcf_desc = f"Projects FCF Per Share ({sym}{fcf_per_share:.2f}) [Normalized]" if is_fcf_normalized else f"Projects FCF Per Share ({sym}{fcf_per_share:.2f})"
    valuations['FCF Projection'] = {
        'intrinsic_value': intrinsic_fcf,
        'future_price_5y': future_price_fcf,
        'future_price': future_price_fcf,
        'growth_used': fcf_g,
        'discount_used': dr,
        'weight': 0.20,
        'description': f"{fcf_desc} → {years}yr at FCF growth {fcf_g:.1f}%, exit P/FCF {target_fcf_multiple:.1f}x, WACC {dr:.1f}%."
    }

    # =========================================================
    # MODEL 4: EV/EBITDA Projection
    # =========================================================
    ebitda = info.get('ebitda')
    is_ebitda_normalized = False
    if ebitda is None or pd.isna(ebitda) or ebitda <= 0:
        # Use operating income as proxy before margin estimate
        op_income = info.get('operatingIncome')
        if op_income and op_income > 0:
            ebitda = op_income * 1.15  # rough D&A add-back
        else:
            ebitda = total_revenue * 0.15
        is_ebitda_normalized = True

    ebitda_per_share = ebitda / shares_out
    # Use FCF growth rate for EBITDA projection (operating metric)
    future_ebitda_per_share = ebitda_per_share * ((1 + fcf_g / 100) ** years)

    target_ev_ebitda = info.get('enterpriseToEbitda')
    if target_ev_ebitda is None or pd.isna(target_ev_ebitda) or target_ev_ebitda <= 0:
        target_ev_ebitda = 12.0
    # Wider range — many growth companies trade 20-40x
    target_ev_ebitda = min(max(target_ev_ebitda, 5.0), 30.0)

    future_ev_per_share = future_ebitda_per_share * target_ev_ebitda
    # Net debt adjustment: subtract net debt per share from EV to get equity value
    future_price_ev = max(future_ev_per_share - net_debt_per_share, current_price * 0.1)
    intrinsic_ev = future_price_ev / ((1 + dr / 100) ** years)

    ebitda_desc = f"Projects EBITDA/Share ({sym}{ebitda_per_share:.2f}) [Normalized]" if is_ebitda_normalized else f"Projects EBITDA/Share ({sym}{ebitda_per_share:.2f})"
    valuations['EV/EBITDA Projection'] = {
        'intrinsic_value': intrinsic_ev,
        'future_price_5y': future_price_ev,
        'future_price': future_price_ev,
        'growth_used': fcf_g,
        'discount_used': dr,
        'weight': 0.15,
        'description': f"{ebitda_desc} → {years}yr at {fcf_g:.1f}% growth, exit EV/EBITDA {target_ev_ebitda:.1f}x, net-debt adj, WACC {dr:.1f}%."
    }

    # =========================================================
    # MODEL 5: P/B Book Value Projection
    # =========================================================
    bv = book_value if (book_value and not pd.isna(book_value) and book_value > 0) else info.get('bookValue')
    is_bv_normalized = False
    if bv is None or pd.isna(bv) or bv <= 0:
        bv = current_price / 3.0
        is_bv_normalized = True

    roe = info.get('returnOnEquity')
    book_g = roe * 100 if (roe and not pd.isna(roe) and roe > 0) else 10.0
    book_g = min(max(book_g, 3.0), 20.0)

    future_bv = bv * ((1 + book_g / 100) ** years)
    target_pb = info.get('priceToBook')
    if target_pb is None or pd.isna(target_pb) or target_pb <= 0:
        target_pb = 2.0
    target_pb = min(max(target_pb, 0.8), 8.0)

    future_price_pb = future_bv * target_pb
    intrinsic_pb = future_price_pb / ((1 + dr / 100) ** years)

    bv_desc = f"Projects BV/Share ({sym}{bv:.2f}) [Normalized]" if is_bv_normalized else f"Projects BV/Share ({sym}{bv:.2f})"
    valuations['P/B Book Value Projection'] = {
        'intrinsic_value': intrinsic_pb,
        'future_price_5y': future_price_pb,
        'future_price': future_price_pb,
        'growth_used': book_g,
        'discount_used': dr,
        'weight': 0.10,
        'description': f"{bv_desc} → {years}yr at ROE-based growth {book_g:.1f}%, exit P/B {target_pb:.1f}x, WACC {dr:.1f}%."
    }

    # =========================================================
    # MODEL 6: 2-Stage DCF (Standard)
    # =========================================================
    pv_stage1 = 0.0
    for i in range(1, years + 1):
        fcf_i = fcf_per_share * ((1 + fcf_g / 100) ** i)
        pv_stage1 += fcf_i / ((1 + dr / 100) ** i)

    future_fcf_N = fcf_per_share * ((1 + fcf_g / 100) ** years)
    if dr > tg:
        terminal_value = future_fcf_N * (1 + tg / 100) / ((dr - tg) / 100)
    else:
        terminal_value = future_fcf_N * (1 + tg / 100) / ((max(dr, tg + 0.5)) / 100)
    pv_terminal = terminal_value / ((1 + dr / 100) ** years)

    intrinsic_dcf = pv_stage1 + pv_terminal
    future_price_dcf = intrinsic_dcf * ((1 + dr / 100) ** years)

    valuations['2-Stage DCF'] = {
        'intrinsic_value': intrinsic_dcf,
        'future_price_5y': future_price_dcf,
        'future_price': future_price_dcf,
        'growth_used': fcf_g,
        'discount_used': dr,
        'weight': 0.20,
        'description': f"Discounts FCF {years}yr at {fcf_g:.1f}% growth, terminal at {tg:.1f}%, WACC {dr:.1f}%."
    }

    # =========================================================
    # MODEL 7: 3-Stage DCF (High Growth → Fade → Terminal)
    # =========================================================
    stage1_yrs = min(years, 3)
    stage2_yrs = max(years - stage1_yrs, 2)
    stage2_g = max(fcf_g * 0.5, tg + 1.0)  # fade to half
    pv_3s1 = 0.0
    last_fcf = fcf_per_share
    for i in range(1, stage1_yrs + 1):
        cf = last_fcf * (1 + fcf_g / 100)
        pv_3s1 += cf / ((1 + dr / 100) ** i)
        last_fcf = cf

    pv_3s2 = 0.0
    for j in range(1, stage2_yrs + 1):
        cf = last_fcf * (1 + stage2_g / 100)
        pv_3s2 += cf / ((1 + dr / 100) ** (stage1_yrs + j))
        last_fcf = cf

    if dr > tg:
        tv_3s = last_fcf * (1 + tg / 100) / ((dr - tg) / 100)
    else:
        tv_3s = last_fcf * (1 + tg / 100) / (max(dr, tg + 0.5) / 100)
    pv_tv_3s = tv_3s / ((1 + dr / 100) ** (stage1_yrs + stage2_yrs))

    intrinsic_3stage = pv_3s1 + pv_3s2 + pv_tv_3s
    future_price_3stage = intrinsic_3stage * ((1 + dr / 100) ** years)

    valuations['3-Stage DCF'] = {
        'intrinsic_value': intrinsic_3stage,
        'future_price_5y': future_price_3stage,
        'future_price': future_price_3stage,
        'growth_used': fcf_g,
        'discount_used': dr,
        'weight': 0.15,
        'description': f"3-Stage: {stage1_yrs}yr at {fcf_g:.1f}%, {stage2_yrs}yr fade to {stage2_g:.1f}%, terminal {tg:.1f}%, WACC {dr:.1f}%."
    }

    # =========================================================
    # MODEL 8: Earnings Power Value (EPV) — Damodaran-style
    # =========================================================
    # EPV = Normalized EBIT(1-t) / cost_of_capital  (no-growth perpetuity)
    ebit = info.get('ebit') or (ebitda * 0.85 if ebitda > 0 else eps * shares_out)
    if ebit <= 0:
        ebit = ebitda * 0.80 if ebitda > 0 else total_revenue * 0.10
    tax_rate_epv = 0.21
    nopat = ebit * (1 - tax_rate_epv) / shares_out  # NOPAT per share
    if nopat <= 0:
        nopat = eps * 0.85
    # EPV uses cost of equity (CAPM) not WACC for equity value
    cost_eq = max(coe_val, 6.0)
    intrinsic_epv = nopat / (cost_eq / 100)
    # EPV grows only at inflation (no structural growth assumed)
    inflation_rate = 2.5
    future_price_epv = intrinsic_epv * ((1 + inflation_rate / 100) ** years)

    valuations['Earnings Power Value (EPV)'] = {
        'intrinsic_value': intrinsic_epv,
        'future_price_5y': future_price_epv,
        'future_price': future_price_epv,
        'growth_used': inflation_rate,
        'discount_used': cost_eq,
        'weight': 0.05,
        'description': f"No-growth perpetuity: NOPAT/Share ({sym}{nopat:.2f}) ÷ cost of equity {cost_eq:.1f}%, inflated at {inflation_rate:.1f}%/yr."
    }

    # =========================================================
    # MODEL 9: Revised Benjamin Graham Formula
    # =========================================================
    g_capped = min(pe_g, 15.0)
    intrinsic_graham = eps * (8.5 + 2 * g_capped) * 4.4 / graham_bond_yield
    future_price_graham = intrinsic_graham * ((1 + g_capped / 100) ** years)

    valuations['Revised Benjamin Graham'] = {
        'intrinsic_value': intrinsic_graham,
        'future_price_5y': future_price_graham,
        'future_price': future_price_graham,
        'growth_used': g_capped,
        'discount_used': graham_bond_yield,
        'weight': 0.05,
        'description': f"Graham: EPS({sym}{eps:.2f}) × (8.5 + 2×{g_capped:.1f}%) × 4.4 ÷ {graham_bond_yield:.1f}% (corp bond yield)."
    }

    # =========================================================
    # MODEL 10: Buffett Owner Earnings Model
    # =========================================================
    # Owner Earnings = Net Income + D&A - Maintenance CapEx
    # Proxy: FCF is already a reasonable owner earnings proxy
    oe_per_share = fcf_per_share
    future_oe_ps = oe_per_share * ((1 + fcf_g / 100) ** years)
    # Buffett uses ~15x earnings as baseline; adjust slightly for growth
    target_oe_multiple = min(max(conservative_pe * 1.05, 13.0), 28.0)
    future_price_oe = future_oe_ps * target_oe_multiple
    intrinsic_oe = future_price_oe / ((1 + dr / 100) ** years)

    valuations['Buffett Owner Earnings'] = {
        'intrinsic_value': intrinsic_oe,
        'future_price_5y': future_price_oe,
        'future_price': future_price_oe,
        'growth_used': fcf_g,
        'discount_used': dr,
        'weight': 0.15,
        'description': f"Owner earnings ({sym}{oe_per_share:.2f}/share) → {years}yr at {fcf_g:.1f}% growth, exit {target_oe_multiple:.1f}x, WACC {dr:.1f}%."
    }

    # Store metadata for UI use
    valuations['_meta'] = {
        'wacc': dr,
        'beta': beta_val,
        'cost_of_equity': coe_val,
        'rf_rate': rf_rate,
        'terminal_growth': tg,
        'eps_growth': pe_g,
        'rev_growth': rev_g,
        'fcf_growth': fcf_g,
        'years': years,
        'graham_bond_yield': graham_bond_yield,
    }

    return valuations


def create_valuation_chart(valuations, current_price, years=5):
    if not valuations:
        return None

    meta = valuations.get('_meta', {})
    models = {k: v for k, v in valuations.items() if k != '_meta'}
    if not models:
        return None

    names = list(models.keys())
    intrinsic_values = [v['intrinsic_value'] for v in models.values()]
    future_prices = [v.get('future_price', v['future_price_5y']) for v in models.values()]
    weights = [v.get('weight', 1.0 / len(models)) for v in models.values()]

    total_weight = sum(weights)
    avg_intrinsic = sum(iv * w for iv, w in zip(intrinsic_values, weights)) / total_weight if total_weight > 0 else sum(intrinsic_values) / len(intrinsic_values)
    avg_future = sum(fp * w for fp, w in zip(future_prices, weights)) / total_weight if total_weight > 0 else sum(future_prices) / len(future_prices)
    sym = cs()

    # Color-code each bar: green if intrinsic > current price (undervalued), red if overvalued
    bar_colors_iv = ['#10B981' if iv >= current_price else '#F87171' for iv in intrinsic_values]
    bar_colors_fp = ['#3B82F6' if fp >= current_price else '#F59E0B' for fp in future_prices]

    # Margin of safety text per bar
    mos_texts = []
    for iv in intrinsic_values:
        if iv > 0 and current_price > 0:
            mos = ((iv - current_price) / current_price) * 100
            mos_texts.append(f"{sym}{iv:.1f}<br>{'▲' if mos >= 0 else '▼'}{abs(mos):.0f}%")
        else:
            mos_texts.append(f"{sym}{iv:.1f}")

    fp_texts = [f"{sym}{fp:.1f}" for fp in future_prices]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=names,
        y=intrinsic_values,
        name=tr("intrinsic_value_pv_column"),
        marker_color=bar_colors_iv,
        text=mos_texts,
        textposition='outside',
        textfont=dict(size=9),
        opacity=0.9,
        hovertemplate='<b>%{x}</b><br>Intrinsic Value: ' + sym + '%{y:.2f}<extra></extra>'
    ))

    fig.add_trace(go.Bar(
        x=names,
        y=future_prices,
        name=tr("target_price_fv_column").replace("{years}", str(years)),
        marker_color=bar_colors_fp,
        text=fp_texts,
        textposition='outside',
        textfont=dict(size=9),
        opacity=0.7,
        hovertemplate='<b>%{x}</b><br>Target Price: ' + sym + '%{y:.2f}<extra></extra>'
    ))

    fig.add_hline(
        y=current_price,
        line_dash="solid",
        line_color="#E2E8F0",
        line_width=2.5,
        annotation_text=f"  {tr('current_price')}: {sym}{current_price:.2f}",
        annotation_position="bottom right",
        annotation_font=dict(color="#E2E8F0", size=12, family="Arial")
    )

    fig.add_hline(
        y=avg_intrinsic,
        line_dash="dash",
        line_color="#10B981",
        line_width=2,
        annotation_text=f"  Weighted IV: {sym}{avg_intrinsic:.2f}",
        annotation_position="top left",
        annotation_font=dict(color="#10B981", size=11, family="Arial")
    )

    fig.add_hline(
        y=avg_future,
        line_dash="dot",
        line_color="#60A5FA",
        line_width=2,
        annotation_text=f"  Weighted Target: {sym}{avg_future:.2f}",
        annotation_position="top right",
        annotation_font=dict(color="#60A5FA", size=11, family="Arial")
    )

    years_str = tr("price_period_1y") if years == 1 else (tr("price_period_2y") if years == 2 else f"{years} {tr('price_period_5y')}")
    wacc_str = f" | WACC: {meta.get('wacc', 10):.1f}%" if meta else ""
    fig.update_layout(
        title=f"<b>{tr('multi_model_consensus')} ({years_str}){wacc_str}</b>",
        yaxis_title=tr("usd_sign"),
        barmode='group',
        hovermode="x unified",
        margin=dict(t=70, b=60, l=40, r=40),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5),
        xaxis=dict(tickangle=-35)
    )

    return fig


def create_stock_price_chart(df: pd.DataFrame, ticker_symbol: str, show_bollinger: bool = False):
    if df.empty:
        return None

    df = df.copy()
    df['SMA 50'] = df['Close'].rolling(window=50).mean()
    df['SMA 200'] = df['Close'].rolling(window=200).mean()

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['Close'],
        mode='lines',
        name=tr("close_price"),
        line=dict(color='#1f77b4', width=2),
        fill='tozeroy',
        fillcolor='rgba(31, 119, 180, 0.05)'
    ))

    if show_bollinger:
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['STD20'] = df['Close'].rolling(window=20).std()
        df['Upper'] = df['MA20'] + (df['STD20'] * 2)
        df['Lower'] = df['MA20'] - (df['STD20'] * 2)
        
        if not df['Upper'].dropna().empty:
            fig.add_trace(go.Scatter(
                x=df.index,
                y=df['Upper'],
                mode='lines',
                name=tr("show_bollinger") + " (Upper)",
                line=dict(color='rgba(173, 216, 230, 0.6)', width=1, dash='dash'),
            ))
            fig.add_trace(go.Scatter(
                x=df.index,
                y=df['Lower'],
                mode='lines',
                name=tr("show_bollinger") + " (Lower)",
                line=dict(color='rgba(173, 216, 230, 0.6)', width=1, dash='dash'),
                fill='tonexty',
                fillcolor='rgba(173, 216, 230, 0.05)'
            ))

    if not df['SMA 50'].dropna().empty:
        fig.add_trace(go.Scatter(
            x=df.index,
            y=df['SMA 50'],
            mode='lines',
            name=tr("sma_50"),
            line=dict(color='#ff7f0e', width=1.5, dash='dash')
        ))

    if not df['SMA 200'].dropna().empty:
        fig.add_trace(go.Scatter(
            x=df.index,
            y=df['SMA 200'],
            mode='lines',
            name=tr("sma_200"),
            line=dict(color='#2ca02c', width=1.5, dash='dot')
        ))

    fig.update_layout(
        title=f"<b>{ticker_symbol} - {tr('price_history_ma')}</b>",
        xaxis_title=tr("date_label"),
        yaxis_title=tr("stock_price_usd"),
        hovermode="x unified",
        margin=dict(t=60, b=20, l=40, r=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    return fig


def create_rsi_chart(df: pd.DataFrame):
    if df.empty or len(df) < 14:
        return None
    
    close = df['Close']
    delta = close.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=13, adjust=False).mean()
    ema_down = down.ewm(com=13, adjust=False).mean()
    rs = ema_up / ema_down
    rsi = 100 - (100 / (1 + rs))
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df.index,
        y=rsi,
        mode='lines',
        name='RSI',
        line=dict(color='#8A2BE2', width=2)
    ))
    
    fig.add_hline(y=70, line_dash="dash", line_color="rgba(239, 68, 68, 0.8)", annotation_text=tr("rsi_overbought"), annotation_position="top right")
    fig.add_hline(y=30, line_dash="dash", line_color="rgba(16, 185, 129, 0.8)", annotation_text=tr("rsi_oversold"), annotation_position="bottom right")
    
    fig.update_layout(
        title=f"<b>RSI (14)</b>",
        yaxis=dict(range=[10, 90], title="RSI Value"),
        xaxis_title=tr("date_label"),
        hovermode="x unified",
        margin=dict(t=40, b=20, l=40, r=40),
        height=200
    )
    return fig


def create_macd_chart(df: pd.DataFrame):
    if df.empty or len(df) < 26:
        return None
    
    close = df['Close']
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - signal_line
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df.index,
        y=macd_line,
        mode='lines',
        name='MACD Line',
        line=dict(color='#1E90FF', width=1.5)
    ))
    fig.add_trace(go.Scatter(
        x=df.index,
        y=signal_line,
        mode='lines',
        name='Signal Line',
        line=dict(color='#FF8C00', width=1.5)
    ))
    
    colors = ['rgba(16, 185, 129, 0.6)' if val >= 0 else 'rgba(239, 68, 68, 0.6)' for val in macd_hist]
    fig.add_trace(go.Bar(
        x=df.index,
        y=macd_hist,
        name='Histogram',
        marker_color=colors
    ))
    
    fig.update_layout(
        title=f"<b>MACD (12, 26, 9)</b>",
        yaxis_title="Value",
        xaxis_title=tr("date_label"),
        hovermode="x unified",
        margin=dict(t=40, b=20, l=40, r=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=250
    )
    return fig


def create_volume_chart(df: pd.DataFrame):
    if df.empty or 'Volume' not in df.columns:
        return None
        
    df = df.copy()
    if 'Open' in df.columns:
        colors = ['#10B981' if close >= open_val else '#EF4444' for close, open_val in zip(df['Close'], df['Open'])]
    else:
        colors = ['#10B981'] * len(df)
        
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df.index,
        y=df['Volume'],
        name=tr("trading_volume"),
        marker_color=colors,
        opacity=0.75
    ))
    
    fig.update_layout(
        title=f"<b>{tr('volume_chart')}</b>",
        yaxis_title=tr("volume_chart"),
        xaxis_title=tr("date_label"),
        hovermode="x unified",
        margin=dict(t=40, b=20, l=40, r=40),
        height=200
    )
    return fig


def check_ratio(val, ratio_type):
    if val is None:
        return tr("na"), "neutral", tr("data_not_available_short")

    if ratio_type == "current_ratio":
        status = "good" if val >= 1.5 else ("critical" if val < 1.0 else "warning")
        return f"{val:.2f}x", status, tr("current_ratio_desc")
    elif ratio_type == "debt_to_equity":
        ratio = val / 100.0 if val > 5.0 else val
        status = "good" if ratio <= 1.0 else ("critical" if ratio > 2.0 else "warning")
        desc = tr("debt_to_equity_desc")
        if st.session_state.language == "he":
            desc += f" (ערך גולמי: {val:.1f}%)"
        else:
            desc += f" (Raw value: {val:.1f}%)"
        return f"{ratio:.2f}x", status, desc
    elif ratio_type == "roe":
        pct = val * 100.0
        status = "good" if pct >= 15.0 else ("critical" if pct < 5.0 else "warning")
        return f"{pct:.2f}%", status, tr("roe_desc")
    elif ratio_type == "roa":
        pct = val * 100.0
        status = "good" if pct >= 8.0 else ("critical" if pct < 3.0 else "warning")
        return f"{pct:.2f}%", status, tr("roa_desc")
    elif ratio_type == "gross_margin":
        pct = val * 100.0
        status = "good" if pct >= 40.0 else ("critical" if pct < 20.0 else "warning")
        return f"{pct:.2f}%", status, tr("gross_margin_desc")
    elif ratio_type == "operating_margin":
        pct = val * 100.0
        status = "good" if pct >= 15.0 else ("critical" if pct < 5.0 else "warning")
        return f"{pct:.2f}%", status, tr("operating_margin_desc")
    return tr("na"), "neutral", ""


def render_ratio_card(label, value_str, status, description):
    colors = {
        'good': {'bg': '#1c2030', 'border': '#089981', 'text': '#089981'},
        'warning': {'bg': '#1c2030', 'border': '#ff7f0e', 'text': '#ff7f0e'},
        'critical': {'bg': '#1c2030', 'border': '#f23645', 'text': '#f23645'},
        'neutral': {'bg': '#1c2030', 'border': '#848e9c', 'text': '#ffffff'}
    }
    c = colors[status]
    lang = st.session_state.get("language", "en")
    border_style = f"border-right: 5px solid {c['border']};" if lang == "he" else f"border-left: 5px solid {c['border']};"
    card_html = f"""
    <div style="background-color: {c['bg']} !important; border: 1px solid #2a2e39 !important; {border_style} padding: 15px; border-radius: 8px; margin-bottom: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.15); height: 160px; box-sizing: border-box;">
        <h4 style="margin: 0; color: #848e9c !important; font-size: 12px; font-weight: 600; text-transform: uppercase; font-family: 'Outfit', 'Rubik', sans-serif; text-align: {'right' if lang == 'he' else 'left'} !important;">{label}</h4>
        <h2 style="margin: 5px 0; color: {c['text']} !important; font-size: 24px; font-weight: 700; font-family: 'Outfit', 'Rubik', sans-serif; text-align: {'right' if lang == 'he' else 'left'} !important;">{value_str}</h2>
        <p style="margin: 0; color: #d1d4dc !important; font-size: 11px; line-height: 1.4; font-family: 'Outfit', 'Rubik', sans-serif; text-align: {'right' if lang == 'he' else 'left'} !important;">{description}</p>
    </div>
    """
    return card_html


def render_portfolio_card(label, value_str, status, description=""):
    colors = {
        'good': {'bg': '#1c2030', 'border': '#089981', 'text': '#089981'},
        'warning': {'bg': '#1c2030', 'border': '#ff7f0e', 'text': '#ff7f0e'},
        'critical': {'bg': '#1c2030', 'border': '#f23645', 'text': '#f23645'},
        'neutral': {'bg': '#1c2030', 'border': '#848e9c', 'text': '#ffffff'}
    }
    c = colors.get(status, colors['neutral'])
    lang = st.session_state.get("language", "en")
    border_style = f"border-right: 5px solid {c['border']};" if lang == "he" else f"border-left: 5px solid {c['border']};"
    align_text = 'right' if lang == 'he' else 'left'
    
    desc_html = ""
    if description:
        desc_html = f'<p style="margin: 0; color: #d1d4dc !important; font-size: 10px; line-height: 1.4; font-family: \'Outfit\', \'Rubik\', sans-serif; text-align: {align_text} !important;">{description}</p>'
        
    card_html = f"""
    <div style="background-color: {c['bg']} !important; border: 1px solid #2a2e39 !important; {border_style} padding: 15px; border-radius: 8px; margin-bottom: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.15); box-sizing: border-box; min-height: 120px;">
        <h4 style="margin: 0; color: #848e9c !important; font-size: 11px; font-weight: 600; text-transform: uppercase; font-family: 'Outfit', 'Rubik', sans-serif; text-align: {align_text} !important;">{label}</h4>
        <h2 style="margin: 5px 0; color: {c['text']} !important; font-size: 18px; font-weight: 700; font-family: 'Outfit', 'Rubik', sans-serif; text-align: {align_text} !important;">{value_str}</h2>
        {desc_html}
    </div>
    """
    return card_html


st.set_page_config(page_title="Comprehensive Stock Dashboard", layout="wide")

# --- Sidebar Navigation ---
st.sidebar.title(tr("navigation"))
pages = ["Dashboard", "Compare", "Watchlist", "Portfolio"]
page_format_func = lambda x: tr("dashboard") if x == "Dashboard" else (tr("compare_stocks") if x == "Compare" else (tr("watchlist") if x == "Watchlist" else tr("portfolio")))
try:
    page_index = pages.index(st.session_state.page_selector)
except ValueError:
    page_index = 0
selected_page = st.sidebar.radio(tr("select_view"), pages, index=page_index, format_func=page_format_func)
st.session_state.page_selector = selected_page

# Render top ticker tape
render_ticker_tape()

# ==========================================
# PAGE 1: DASHBOARD
# ==========================================
if st.session_state.page_selector == "Dashboard":
    st.title(tr("page_title"))

    ticker_input = st.text_input(tr("ticker_input_placeholder"),
                                 st.session_state.selected_ticker).upper().strip()

    if ticker_input:
        st.session_state.selected_ticker = ticker_input
        with st.spinner(tr("pulling_data").format(ticker=ticker_input)):
            df_fin_a, df_bs_a, df_cf_a, df_fin_q, df_bs_q, df_cf_q, history, info = fetch_financial_data(ticker_input)
            if info:
                currency = info.get("currency", "USD")
                st.session_state.currency_symbol = "₪" if currency in ["ILA", "ILS"] else ("£" if currency in ["GBp", "GBP"] else ("€" if currency == "EUR" else "$"))

            if history is not None and not history.empty:
                # --- Precompute Valuation & Financial Metrics ---
                shares_out = info.get('sharesOutstanding', 1)
                if not shares_out or shares_out <= 0:
                    shares_out = 1
                history['Market Cap (T)'] = (history['Close'] * shares_out) / 1e12

                trailing_eps = info.get('trailingEps', 0)
                avg_pe = 15.0  # Default fallback
                if trailing_eps > 0:
                    history['Estimated P/E'] = history['Close'] / trailing_eps
                    avg_pe = history['Estimated P/E'].mean() if not history['Estimated P/E'].dropna().empty else 15.0

                current_price = info.get('currentPrice', history['Close'].iloc[-1] if not history.empty else 0)

                peg_ratio = info.get('pegRatio', None)
                trailing_pe = info.get('trailingPE', None)
                implied_5y_growth = None
                if peg_ratio and trailing_pe and peg_ratio > 0:
                    implied_5y_growth = trailing_pe / peg_ratio

                growth_rate = implied_5y_growth if implied_5y_growth and implied_5y_growth > 0 else 10.0
                discount_rate = 10.0

                # Valuations are typically calculated using Annual TTM data
                # WACC is auto-computed inside calculate_valuations using CAPM
                valuations = calculate_valuations(
                    info, df_fin_a, avg_pe, growth_rate, discount_rate,
                    terminal_growth=2.5, use_wacc=True
                )


                # --- 1. Company Profile Card ---
                long_name = info.get('longName', ticker_input)
                sector = info.get('sector', 'N/A')
                industry = info.get('industry', 'N/A')
                employees = info.get('fullTimeEmployees', 'N/A')
                website = info.get('website', '')
                summary = info.get('longBusinessSummary', 'No business summary available.')

                # Dynamically translate sector, industry and summary if Hebrew is selected
                if st.session_state.language == "he":
                    if sector != 'N/A': sector = translate_text(sector)
                    if industry != 'N/A': industry = translate_text(industry)
                    if summary != 'No business summary available.': summary = translate_text(summary)

                st.markdown(f"""
                <div style="background-color: #1c2030; border: 1px solid #2a2e39; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
                    <h2 style="margin: 0; color: #ffffff; font-family: 'Outfit', 'Rubik', sans-serif;">{long_name} ({ticker_input})</h2>
                    <p style="margin: 5px 0 15px 0; color: #d1d4dc; font-size: 14px; font-family: 'Outfit', 'Rubik', sans-serif;">
                        <strong style="color: #848e9c;">{tr('sector')}:</strong> {sector} &nbsp;|&nbsp; <strong style="color: #848e9c;">{tr('industry')}:</strong> {industry} &nbsp;|&nbsp; <strong style="color: #848e9c;">{tr('employees')}:</strong> {employees if isinstance(employees, int) else employees}
                    </p>
                    {f'<a href="{website}" target="_blank" style="background-color: #2962ff; color: white; padding: 8px 16px; border-radius: 6px; text-decoration: none; font-size: 14px; font-weight: bold; font-family: \'Outfit\', \'Rubik\', sans-serif; display: inline-block;">{tr("visit_website")}</a>' if website else ''}
                </div>
                """, unsafe_allow_html=True)

                # --- Quick Actions Expander ---
                quick_actions_title = "⚡ פעולות מהירות (הוספה למעקב / תיק השקעות)" if st.session_state.language == "he" else "⚡ Quick Actions (Add to Watchlist / Portfolio)"
                with st.expander(quick_actions_title, expanded=False):
                    col_qa_wl, col_qa_port = st.columns(2)
                    
                    with col_qa_wl:
                        if "watchlists" in st.session_state and st.session_state.watchlists:
                            wl_options = []
                            for wl_name, wl_sections in st.session_state.watchlists.items():
                                for section in wl_sections:
                                    wl_options.append((wl_name, section["title"]))
                            if wl_options:
                                select_wl_lbl = "הוסף לרשימת מעקב:" if st.session_state.language == "he" else "Add to Watchlist:"
                                selected_wl_opt = st.selectbox(
                                    select_wl_lbl,
                                    options=wl_options,
                                    format_func=lambda x: f"{x[0]} ➡️ {x[1]}",
                                    key="quick_add_watchlist_selector"
                                )
                                if st.button("➕ " + ("הוסף למעקב" if st.session_state.language == "he" else "Add to Watchlist"), key="quick_add_wl_btn", use_container_width=True):
                                    target_wl, target_sec = selected_wl_opt
                                    for section in st.session_state.watchlists[target_wl]:
                                        if section["title"] == target_sec:
                                            ticker_exists = any(ticker_input in s["tickers"] for s in st.session_state.watchlists[target_wl])
                                            if not ticker_exists:
                                                section["tickers"].append(ticker_input)
                                                save_watchlists(st.session_state.watchlists)
                                                st.success(f"{ticker_input} added to {target_wl} ({target_sec})!")
                                                st.rerun()
                                            else:
                                                st.warning(f"{ticker_input} is already in {target_wl}!")
                                                
                    with col_qa_port:
                        if "portfolio_dict" in st.session_state and st.session_state.portfolio_dict:
                            port_options = list(st.session_state.portfolio_dict.keys())
                            if port_options:
                                select_port_lbl = "הוסף לתיק השקעות:" if st.session_state.language == "he" else "Add to Portfolio:"
                                selected_port_opt = st.selectbox(
                                    select_port_lbl,
                                    options=port_options,
                                    key="quick_add_portfolio_selector"
                                )
                                if st.button("💼 " + ("הוסף לתיק" if st.session_state.language == "he" else "Add to Portfolio"), key="quick_add_port_btn", use_container_width=True):
                                    import random
                                    exists_in_port = any(pos.get("symbol") == ticker_input for pos in st.session_state.portfolio_dict[selected_port_opt])
                                    if not exists_in_port:
                                        st.session_state.portfolio_dict[selected_port_opt].append({
                                            "id": f"{pd.Timestamp.now().timestamp()}_{random.random()}",
                                            "symbol": ticker_input,
                                            "currency": "USD" if not ticker_input.endswith(".TA") else "ILS",
                                            "buys": [{"p": 0.0, "q": 0.0}],
                                            "sells": [],
                                            "currentPrice": 0.0,
                                            "prevClosePrice": 0.0,
                                            "locked": False
                                        })
                                        save_portfolio(st.session_state.portfolio_dict)
                                        st.success(f"{ticker_input} added to Portfolio '{selected_port_opt}'!")
                                        st.rerun()
                                    else:
                                        st.warning(f"{ticker_input} is already in Portfolio '{selected_port_opt}'!")

                with st.expander(tr("company_description")):
                    st.write(summary)
                # --- 2. Create Tabs ---
                tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
                    tr("price_market_trend"),
                    tr("financial_statements"),
                    tr("financial_health_check"),
                    tr("valuation_consensus"),
                    tr("time_machine_backtest"),
                    tr("news_market_sentiment"),
                    get_label("💰 Dividends"),
                    tr("insider_ownership_tab"),
                    get_label("🔮 Projections")
                ])

                # ==========================================
                # TAB 1: PRICE & MARKET TREND
                # ==========================================
                with tab1:
                    st.subheader(tr("stock_price_perf"))
                    price_period = st.radio(tr("select_chart_period"), [tr("price_period_1y"), tr("price_period_2y"), tr("price_period_5y"), tr("price_period_10y")],
                                            horizontal=True, key="price_period_selector")

                    if price_period == tr("price_period_1y"):
                        history_slice = history.tail(252)
                    elif price_period == tr("price_period_2y"):
                        history_slice = history.tail(504)
                    elif price_period == tr("price_period_5y"):
                        history_slice = history.tail(1260)
                    else:
                        history_slice = history

                    st.markdown("##### " + tr("technical_analysis"))
                    
                    # Compute technical consensus
                    gauge_val, rec, rsi_val, sma_50, sma_200, curr_pr = calculate_technical_consensus(history_slice)
                    
                    col_chart, col_gauge = st.columns([7, 3])
                    
                    with col_chart:
                        col_chk1, col_chk2, col_chk3 = st.columns(3)
                        chk_rsi = col_chk1.checkbox(tr("show_rsi"), value=False, key="chk_rsi")
                        chk_macd = col_chk2.checkbox(tr("show_macd"), value=False, key="chk_macd")
                        chk_boll = col_chk3.checkbox(tr("show_bollinger"), value=False, key="chk_boll")

                        fig_price = create_stock_price_chart(history_slice, ticker_input, show_bollinger=chk_boll)
                        if fig_price:
                            st.plotly_chart(fig_price, use_container_width=True)

                        if chk_rsi:
                            fig_rsi = create_rsi_chart(history_slice)
                            if fig_rsi:
                                st.plotly_chart(fig_rsi, use_container_width=True)

                        if chk_macd:
                            fig_macd = create_macd_chart(history_slice)
                            if fig_macd:
                                st.plotly_chart(fig_macd, use_container_width=True)

                        fig_vol = create_volume_chart(history_slice)
                        if fig_vol:
                            st.plotly_chart(fig_vol, use_container_width=True)
                    
                    with col_gauge:
                        fig_gauge = create_technical_gauge(gauge_val, rec)
                        if fig_gauge:
                            st.plotly_chart(fig_gauge, use_container_width=True)
                            
                        # Detail card for technical indicators
                        st.markdown(f"""
                        <div style="background-color: #131722; border: 1px solid #2a2e39; border-radius: 8px; padding: 15px; font-size: 13px; font-family: 'Outfit', 'Rubik', sans-serif;">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 8px; border-bottom: 1px solid #2a2e39; padding-bottom: 4px;">
                                <span style="color: #848e9c; font-weight: 500;">RSI (14):</span>
                                <span style="font-weight: bold; color: {'#089981' if rsi_val < 30 else ('#f23645' if rsi_val > 70 else '#ffffff')}">{rsi_val:.2f}</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; margin-bottom: 8px; border-bottom: 1px solid #2a2e39; padding-bottom: 4px;">
                                <span style="color: #848e9c; font-weight: 500;">SMA (50):</span>
                                <span style="font-weight: bold; color: {'#089981' if curr_pr > sma_50 else '#f23645'}">{cs()}{sma_50:.2f}</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; padding-bottom: 4px;">
                                <span style="color: #848e9c; font-weight: 500;">SMA (200):</span>
                                <span style="font-weight: bold; color: {'#089981' if curr_pr > sma_200 else '#f23645'}">{cs()}{sma_200:.2f}</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

                    st.markdown("---")
                    st.subheader(tr("market_cap_pe_history"))
                    col_p1, col_p2 = st.columns(2)

                    fig_mcap = create_line_chart(history_slice['Market Cap (T)'], tr("market_cap_history"),
                                                 tr("trillions_usd"))
                    if fig_mcap:
                        col_p1.plotly_chart(fig_mcap, use_container_width=True)

                    if trailing_eps > 0 and 'Estimated P/E' in history_slice.columns:
                        fig_pe = create_line_chart(history_slice['Estimated P/E'], tr("est_pe_ratio_history"),
                                                   tr("pe_ratio"))
                        if fig_pe:
                            slice_avg_pe = history_slice['Estimated P/E'].mean()
                            fig_pe.add_hline(
                                y=slice_avg_pe,
                                line_dash="dash",
                                line_color="red",
                                annotation_text=tr("period_average").format(avg=slice_avg_pe),
                                annotation_position="top left"
                            )
                            col_p2.plotly_chart(fig_pe, use_container_width=True)
                    else:
                        col_p2.info(tr("pe_ratio_unavailable"))

                # ==========================================
                # TAB 2: FINANCIAL STATEMENTS
                # ==========================================
                with tab2:
                    st.subheader(tr("income_statement_metrics"))

                    # --- NEW: TIMEFRAME SELECTOR ---
                    timeframe_choice = st.radio(
                        tr("select_data_timeframe"),
                        (tr("timeframe_annual"), tr("timeframe_quarterly")),
                        horizontal=True,
                        key="timeframe_choice_tab2"
                    )

                    is_quarterly = (timeframe_choice == tr("timeframe_quarterly"))
                    df_fin = df_fin_q if is_quarterly else df_fin_a
                    df_bs = df_bs_q if is_quarterly else df_bs_a
                    df_cf = df_cf_q if is_quarterly else df_cf_a
                    change_label = tr("qoq_change") if is_quarterly else tr("yoy_change")
                    x_label = tr("quarter") if is_quarterly else tr("year")
                    time_prefix = tr("timeframe_quarterly").split()[0] if is_quarterly else tr("timeframe_annual").split()[0]

                    if df_fin is not None and not df_fin.empty:
                        earnings_choice = st.radio(
                            tr("select_earnings_metric"),
                            ("Net Income (Bottom Line)", "Operating Income / EBIT"),
                            horizontal=True,
                            key="earnings_metric_choice"
                        )
                        # Translate option for logic/display
                        earnings_choice_translated = tr("net_income_bottom_line") if earnings_choice == "Net Income (Bottom Line)" else tr("operating_income_ebit")

                        col_f1, col_f2 = st.columns(2)

                        rev_col = 'Total Revenue' if 'Total Revenue' in df_fin.columns else 'Operating Revenue'
                        if rev_col in df_fin.columns:
                            rev_title = tr("quarterly_revenue") if is_quarterly else tr("annual_revenue")
                            fig_rev = create_combo_chart(df_fin, rev_col, rev_title, "#2ca02c",
                                                         change_label, x_label)
                            if fig_rev:
                                col_f1.plotly_chart(fig_rev, use_container_width=True)

                        earn_target_col = None
                        if earnings_choice == "Net Income (Bottom Line)":
                            earn_target_col = 'Net Income' if 'Net Income' in df_fin.columns else None
                        else:
                            if 'Operating Income' in df_fin.columns:
                                earn_target_col = 'Operating Income'
                            elif 'EBIT' in df_fin.columns:
                                earn_target_col = 'EBIT'

                        if earn_target_col and earn_target_col in df_fin.columns:
                            earn_title = (tr("quarterly_earnings") if is_quarterly else tr("annual_earnings")).format(metric=earnings_choice_translated)
                            fig_net = create_combo_chart(df_fin, earn_target_col,
                                                         earn_title, "#1f77b4",
                                                         change_label, x_label)
                            if fig_net:
                                col_f2.plotly_chart(fig_net, use_container_width=True)
                        else:
                            col_f2.warning(
                                tr("data_unavailable").format(metric=earnings_choice_translated, timeframe=time_prefix))

                        # --- NEW: Profit Margin Chart ---
                        if rev_col and earn_target_col and rev_col in df_fin.columns and earn_target_col in df_fin.columns:
                            margin_df = df_fin[[rev_col, earn_target_col]].copy().dropna()
                            margin_df = margin_df[margin_df[rev_col] != 0]  # Prevent division by zero

                            if not margin_df.empty:
                                margin_df['Margin (%)'] = (margin_df[earn_target_col] / margin_df[rev_col]) * 100

                                fig_margin = go.Figure()
                                fig_margin.add_trace(go.Scatter(
                                    x=margin_df.index,
                                    y=margin_df['Margin (%)'],
                                    mode='lines+markers+text',
                                    name=tr("profit_margin"),
                                    text=margin_df['Margin (%)'].round(2).astype(str) + '%',
                                    textposition='top center',
                                    line=dict(color='#d62728', width=3),
                                    marker=dict(size=8, color='#d62728'),
                                    fill='tozeroy',
                                    fillcolor='rgba(214, 39, 40, 0.1)',
                                    cliponaxis=False  # Prevents text/markers from being cut off at the edges
                                ))

                                # Add padding to the x-axis to prevent clipping on the left and right
                                x_padding = 0.5
                                x_max_index = len(margin_df) - 1

                                fig_margin.update_layout(
                                    title=f"<b>{tr('profit_margin')} ({time_prefix})</b> ({earnings_choice_translated} / {tr('revenue')})",
                                    xaxis=dict(
                                        title=x_label,
                                        type='category',
                                        range=[-x_padding, x_max_index + x_padding]
                                    ),
                                    yaxis=dict(title=tr("percentage")),
                                    hovermode="x unified",
                                    margin=dict(t=40, b=20)
                                )
                                st.plotly_chart(fig_margin, use_container_width=True)
                    else:
                        st.warning(tr("income_statement_unavailable").format(timeframe=time_prefix))

                    st.markdown("---")
                    st.subheader(tr("eps_title"))

                    eps_col = 'Diluted EPS' if 'Diluted EPS' in df_fin.columns else (
                        'Basic EPS' if 'Basic EPS' in df_fin.columns else None)

                    if eps_col and not df_fin[eps_col].dropna().empty:
                        eps_col_translated = tr("diluted_eps") if eps_col == 'Diluted EPS' else tr("basic_eps")
                        eps_title = (tr("quarterly_eps") if is_quarterly else tr("annual_eps")).format(metric=eps_col_translated)
                        fig_eps = create_combo_chart(
                            df_fin,
                            eps_col,
                            eps_title,
                            "#FF9F36",
                            change_label,
                            x_label,
                            value_label=tr("eps_usd"),
                            y_title=tr("usd_sign"),
                            divisor=1.0
                        )
                        if fig_eps:
                            st.plotly_chart(fig_eps, use_container_width=True)
                    else:
                        st.info(tr("eps_unavailable").format(timeframe=time_prefix))

                    st.markdown("---")
                    st.subheader(tr("share_count_title"))

                    share_col = 'Diluted Average Shares' if 'Diluted Average Shares' in df_fin.columns else (
                        'Basic Average Shares' if 'Basic Average Shares' in df_fin.columns else None)

                    if share_col and not df_fin[share_col].dropna().empty:
                        shares_title = tr("quarterly_shares_outstanding") if is_quarterly else tr("annual_shares_outstanding")
                        fig_shares = create_combo_chart(
                            df_fin,
                            share_col,
                            shares_title,
                            "#E377C2",
                            change_label,
                            x_label,
                            value_label=tr("shares_billions"),
                            y_title=tr("billions")
                        )
                        if fig_shares:
                            st.plotly_chart(fig_shares, use_container_width=True)

                        historical_shares = df_fin[share_col].dropna()
                        if len(historical_shares) > 1:
                            latest_shares = historical_shares.iloc[-1]
                            oldest_shares = historical_shares.iloc[0]
                            if latest_shares < oldest_shares:
                                st.success(
                                    tr("buyback_alert").format(pct=((oldest_shares - latest_shares) / oldest_shares) * 100))
                            elif latest_shares > oldest_shares:
                                st.warning(
                                    tr("dilution_alert").format(pct=((latest_shares - oldest_shares) / oldest_shares) * 100))
                    else:
                        st.info(tr("share_count_unavailable").format(timeframe=time_prefix))

                    st.markdown("---")

                    st.subheader(tr("cash_flow_metrics"))
                    if df_cf is not None and not df_cf.empty:
                        col_cf1, col_cf2 = st.columns(2)

                        fcf_col = 'Free Cash Flow'
                        if fcf_col in df_cf.columns:
                            fcf_title = tr("quarterly_fcf") if is_quarterly else tr("annual_fcf")
                            fig_fcf = create_combo_chart(df_cf, fcf_col, fcf_title,
                                                         "#00CC96", change_label, x_label)
                            if fig_fcf:
                                col_cf1.plotly_chart(fig_fcf, use_container_width=True)

                        ocf_col = 'Operating Cash Flow'
                        if ocf_col in df_cf.columns:
                            ocf_title = tr("quarterly_ocf") if is_quarterly else tr("annual_ocf")
                            fig_ocf = create_combo_chart(df_cf, ocf_col, ocf_title,
                                                         "#AB63FA", change_label, x_label)
                            if fig_ocf:
                                col_cf2.plotly_chart(fig_ocf, use_container_width=True)
                    else:
                        st.warning(tr("cash_flow_unavailable").format(timeframe=time_prefix))

                    st.markdown("---")
                    st.subheader(tr("balance_sheet_metrics"))
                    if df_bs is not None and not df_bs.empty:
                        col_b1, col_b2 = st.columns(2)
                        if 'Total Assets' in df_bs.columns:
                            fig_assets = create_combo_chart(df_bs, 'Total Assets', f"{time_prefix} - {tr('total_assets')}", "#9467bd",
                                                            change_label, x_label)
                            if fig_assets:
                                col_b1.plotly_chart(fig_assets, use_container_width=True)

                        liab_col = 'Total Liabilities Net Minority Interest' if 'Total Liabilities Net Minority Interest' in df_bs.columns else 'Total Liabilities'
                        if liab_col in df_bs.columns:
                            fig_liab = create_combo_chart(df_bs, liab_col, f"{time_prefix} - {tr('total_liabilities')}", "#d62728", change_label,
                                                          x_label)
                            if fig_liab:
                                col_b2.plotly_chart(fig_liab, use_container_width=True)

                        col_b3, col_b4 = st.columns(2)
                        if 'Total Debt' in df_bs.columns:
                            fig_debt = create_combo_chart(df_bs, 'Total Debt', f"{time_prefix} - {tr('total_debt')}", "#8c564b", change_label,
                                                          x_label)
                            if fig_debt:
                                col_b3.plotly_chart(fig_debt, use_container_width=True)

                        cash_col = 'Cash And Cash Equivalents'
                        if cash_col in df_bs.columns:
                            fig_cash = create_combo_chart(df_bs, cash_col, f"{time_prefix} - {tr('cash_on_hand')}", "#17becf", change_label,
                                                          x_label)
                            if fig_cash:
                                col_b4.plotly_chart(fig_cash, use_container_width=True)

                        # --- NEW: Leverage Ratios (Liabilities & Debt vs Assets) ---
                        st.markdown("---")
                        st.subheader(tr("asset_financing_leverage"))

                        assets_col = 'Total Assets'
                        debt_col = 'Total Debt'

                        if assets_col in df_bs.columns:
                            lev_df = pd.DataFrame(index=df_bs.index)
                            has_lev_data = False
                            fig_lev = go.Figure()

                            if liab_col in df_bs.columns:
                                lev_df['Liabilities to Assets (%)'] = (df_bs[liab_col] / df_bs[assets_col]) * 100
                                fig_lev.add_trace(go.Scatter(
                                    x=lev_df.index,
                                    y=lev_df['Liabilities to Assets (%)'],
                                    mode='lines+markers+text',
                                    name=tr("total_liab_assets"),
                                    text=lev_df['Liabilities to Assets (%)'].round(1).astype(str) + '%',
                                    textposition='top center',
                                    line=dict(color='#d62728', width=3),
                                    marker=dict(size=8),
                                    cliponaxis=False
                                ))
                                has_lev_data = True

                            if debt_col in df_bs.columns:
                                lev_df['Debt to Assets (%)'] = (df_bs[debt_col] / df_bs[assets_col]) * 100
                                fig_lev.add_trace(go.Scatter(
                                    x=lev_df.index,
                                    y=lev_df['Debt to Assets (%)'],
                                    mode='lines+markers+text',
                                    name=tr("total_debt_assets"),
                                    text=lev_df['Debt to Assets (%)'].round(1).astype(str) + '%',
                                    textposition='bottom center',
                                    line=dict(color='#8c564b', width=3, dash='dash'),
                                    marker=dict(size=8),
                                    cliponaxis=False
                                ))
                                has_lev_data = True

                            if has_lev_data:
                                x_padding = 0.5
                                x_max_index = len(lev_df) - 1

                                fig_lev.update_layout(
                                    title=f"<b>{tr('leverage_ratios_title')} ({time_prefix})</b>",
                                    xaxis=dict(
                                        title=x_label,
                                        type='category',
                                        range=[-x_padding, x_max_index + x_padding]
                                    ),
                                    yaxis=dict(title=tr("percentage"), ticksuffix='%'),
                                    hovermode="x unified",
                                    margin=dict(t=40, b=20),
                                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                                )
                                st.plotly_chart(fig_lev, use_container_width=True)
                            else:
                                st.info(tr("leverage_data_incomplete").format(timeframe=time_prefix))

                    else:
                        st.warning(tr("balance_sheet_unavailable").format(timeframe=time_prefix))

                    st.markdown("---")
                    st.write(f"### {get_label('Export Financial Data')}")
                    col_export1, col_export2, col_export3 = st.columns(3)
                    
                    if df_fin is not None and not df_fin.empty:
                        csv_is = df_fin.to_csv()
                        col_export1.download_button(
                            label=f"📥 {get_label('Download Income Statement')} (CSV)",
                            data=csv_is,
                            file_name=f"{ticker_input}_income_statement.csv",
                            mime="text/csv",
                            key="btn_dl_is"
                        )
                    if df_bs is not None and not df_bs.empty:
                        csv_bs = df_bs.to_csv()
                        col_export2.download_button(
                            label=f"📥 {get_label('Download Balance Sheet')} (CSV)",
                            data=csv_bs,
                            file_name=f"{ticker_input}_balance_sheet.csv",
                            mime="text/csv",
                            key="btn_dl_bs"
                        )
                    if df_cf is not None and not df_cf.empty:
                        csv_cf = df_cf.to_csv()
                        col_export3.download_button(
                            label=f"📥 {get_label('Download Cash Flow')} (CSV)",
                            data=csv_cf,
                            file_name=f"{ticker_input}_cash_flow.csv",
                            mime="text/csv",
                            key="btn_dl_cf"
                        )

                # ==========================================
                # TAB 3: FINANCIAL HEALTH CHECK
                # ==========================================
                with tab3:
                    st.subheader(tr("solvency_profitability_metrics"))
                    st.markdown(tr("solvency_explanation"))

                    h_col1, h_col2, h_col3 = st.columns(3)

                    cr_val = info.get('currentRatio')
                    cr_str, cr_status, cr_desc = check_ratio(cr_val, "current_ratio")
                    h_col1.markdown(render_ratio_card(tr("current_ratio"), cr_str, cr_status, cr_desc),
                                    unsafe_allow_html=True)

                    de_val = info.get('debtToEquity')
                    de_str, de_status, de_desc = check_ratio(de_val, "debt_to_equity")
                    h_col2.markdown(render_ratio_card(tr("debt_to_equity"), de_str, de_status, de_desc),
                                    unsafe_allow_html=True)

                    roe_val = info.get('returnOnEquity')
                    roe_str, roe_status, roe_desc = check_ratio(roe_val, "roe")
                    h_col3.markdown(render_ratio_card(tr("roe"), roe_str, roe_status, roe_desc),
                                    unsafe_allow_html=True)

                    h_col4, h_col5, h_col6 = st.columns(3)

                    roa_val = info.get('returnOnAssets')
                    roa_str, roa_status, roa_desc = check_ratio(roa_val, "roa")
                    h_col4.markdown(render_ratio_card(tr("roa"), roa_str, roa_status, roa_desc),
                                    unsafe_allow_html=True)

                    gm_val = info.get('grossMargins')
                    gm_str, gm_status, gm_desc = check_ratio(gm_val, "gross_margin")
                    h_col5.markdown(render_ratio_card(tr("gross_margin"), gm_str, gm_status, gm_desc),
                                    unsafe_allow_html=True)

                    om_val = info.get('operatingMargins')
                    om_str, om_status, om_desc = check_ratio(om_val, "operating_margin")
                    h_col6.markdown(render_ratio_card(tr("operating_margin"), om_str, om_status, om_desc),
                                    unsafe_allow_html=True)

                    st.markdown("---")
                    with st.expander("📊 " + get_label("Historical Financial Ratios (10-Year Table)")):
                        years_in_both = sorted(list(set(df_fin_a.index).intersection(set(df_bs_a.index))), reverse=True)
                        if years_in_both:
                            ratios_rows = []
                            for yr in years_in_both:
                                row_bs = df_bs_a.loc[yr]
                                row_fin = df_fin_a.loc[yr]
                                
                                ca = row_bs.get('Total Current Assets', None)
                                cl = row_bs.get('Total Current Liabilities', None)
                                curr_ratio = f"{ca / cl:.2f}x" if (ca and cl and cl > 0 and not pd.isna(ca) and not pd.isna(cl)) else 'N/A'
                                
                                debt = row_bs.get('Total Debt', None)
                                eq = row_bs.get('Stockholders Equity', None)
                                de_ratio = f"{debt / eq:.2f}x" if (debt and eq and eq > 0 and not pd.isna(debt) and not pd.isna(eq)) else 'N/A'
                                
                                rev = row_fin.get('Total Revenue', row_fin.get('Operating Revenue', 0))
                                gp = row_fin.get('Gross Profit', None)
                                op_inc = row_fin.get('Operating Income', None)
                                ni = row_fin.get('Net Income', None)
                                
                                gross_m = f"{(gp / rev) * 100:.2f}%" if (gp and rev and rev > 0 and not pd.isna(gp) and not pd.isna(rev)) else 'N/A'
                                op_m = f"{(op_inc / rev) * 100:.2f}%" if (op_inc and rev and rev > 0 and not pd.isna(op_inc) and not pd.isna(rev)) else 'N/A'
                                net_m = f"{(ni / rev) * 100:.2f}%" if (ni and rev and rev > 0 and not pd.isna(ni) and not pd.isna(rev)) else 'N/A'
                                
                                roe = f"{(ni / eq) * 100:.2f}%" if (ni and eq and eq > 0 and not pd.isna(ni) and not pd.isna(eq)) else 'N/A'
                                
                                ratios_rows.append({
                                    get_label("Year"): yr,
                                    tr("current_ratio"): curr_ratio,
                                    tr("debt_to_equity"): de_ratio,
                                    tr("gross_margin"): gross_m,
                                    tr("operating_margin"): op_m,
                                    get_label("Net Margin"): net_m,
                                    tr("roe"): roe
                                })
                            st.table(pd.DataFrame(ratios_rows))
                        else:
                            st.info(tr("data_not_available_short"))

                # ==========================================
                # TAB 4: VALUATION CONSENSUS
                # ==========================================
                with tab4:
                    st.subheader(tr("analyst_targets"))
                    target_mean = info.get('targetMeanPrice', 0)
                    target_high = info.get('targetHighPrice', 0)
                    target_low = info.get('targetLowPrice', 0)
                    analyst_count = info.get('numberOfAnalystOpinions', 0)
                    recommendation = info.get('recommendationKey', 'N/A').replace('_', ' ').title()
                    recommendation_translated = get_label(recommendation)

                    if target_mean > 0 and current_price > 0:
                        upside_mean = ((target_mean - current_price) / current_price) * 100
                        upside_high = ((target_high - current_price) / current_price) * 100
                        upside_low = ((target_low - current_price) / current_price) * 100

                        metric_col1, metric_col2, metric_col3, metric_col4, metric_col5 = st.columns(5)
                        metric_col1.metric(tr("current_price"), f"{cs()}{current_price:.2f}")
                        metric_col2.metric(tr("mean_target"), f"{cs()}{target_mean:.2f}", f"{upside_mean:.2f}%")
                        metric_col3.metric(tr("high_target"), f"{cs()}{target_high:.2f}", f"{upside_high:.2f}%")
                        metric_col4.metric(tr("low_target"), f"{cs()}{target_low:.2f}", f"{upside_low:.2f}%")
                        metric_col5.metric(tr("consensus"), recommendation_translated, f"{analyst_count} {tr('analysts')}", delta_color="off")
                    else:
                        st.info(tr("analyst_targets_unavailable"))

                    if peg_ratio:
                        st.info(tr("peg_ratio_indicator").format(peg_ratio=peg_ratio))

                    # --- Analyst Recommendation Trend (Stacked Bar Chart) ---
                    try:
                        ticker_obj = yf.Ticker(ticker_input)
                        rec_df = ticker_obj.recommendations
                    except Exception:
                        rec_df = None

                    if rec_df is not None and not rec_df.empty:
                        st.markdown("---")
                        st.subheader(tr("analyst_recommendation_trend"))
                        
                        cols_needed = ['strongBuy', 'buy', 'hold', 'sell', 'strongSell']
                        if all(c in rec_df.columns for c in cols_needed):
                            chart_rec = rec_df.copy()
                            
                            period_map_en = {"0m": "Current Month", "-1m": "1 Month Ago", "-2m": "2 Months Ago", "-3m": "3 Months Ago"}
                            period_map_he = {"0m": "חודש נוכחי", "-1m": "לפני חודש", "-2m": "לפני חודשיים", "-3m": "לפני 3 חודשים"}
                            
                            p_map = period_map_he if st.session_state.language == "he" else period_map_en
                            chart_rec['PeriodName'] = chart_rec['period'].map(p_map).fillna(chart_rec['period'])
                            
                            fig_rec = go.Figure()
                            
                            fig_rec.add_trace(go.Bar(
                                x=chart_rec['PeriodName'],
                                y=chart_rec['strongBuy'],
                                name=tr("strong_buy"),
                                marker_color='#10B981'
                            ))
                            fig_rec.add_trace(go.Bar(
                                x=chart_rec['PeriodName'],
                                y=chart_rec['buy'],
                                name=tr("buy"),
                                marker_color='#34D399'
                            ))
                            fig_rec.add_trace(go.Bar(
                                x=chart_rec['PeriodName'],
                                y=chart_rec['hold'],
                                name=tr("hold"),
                                marker_color='#FBBF24'
                            ))
                            fig_rec.add_trace(go.Bar(
                                x=chart_rec['PeriodName'],
                                y=chart_rec['sell'],
                                name=tr("sell"),
                                marker_color='#F87171'
                            ))
                            fig_rec.add_trace(go.Bar(
                                x=chart_rec['PeriodName'],
                                y=chart_rec['strongSell'],
                                name=tr("strong_sell"),
                                marker_color='#EF4444'
                            ))
                            
                            fig_rec.update_layout(
                                barmode='stack',
                                yaxis_title=tr("analysts_count_label"),
                                xaxis_title=tr("recommendation_period"),
                                margin=dict(t=30, b=20, l=40, r=40),
                                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                            )
                            st.plotly_chart(fig_rec, use_container_width=True)

                    st.markdown("---")
                    st.subheader(tr("growth_estimates"))
                    val_col1, val_col2, val_col3 = st.columns(3)

                    rev_growth = info.get('revenueGrowth', None)
                    earn_growth = info.get('earningsGrowth', None)

                    if rev_growth is not None:
                        val_col1.metric(tr("revenue_growth_next_year"), f"{rev_growth * 100:.2f}%")
                    else:
                        val_col1.metric(tr("revenue_growth_next_year"), tr("na"))

                    if earn_growth is not None:
                        val_col2.metric(tr("earnings_growth_next_year"), f"{earn_growth * 100:.2f}%")
                    else:
                        val_col2.metric(tr("earnings_growth_next_year"), tr("na"))

                    if implied_5y_growth is not None:
                        val_col3.metric(tr("eps_growth_next_5yrs"), f"{implied_5y_growth:.2f}%")
                        st.caption(tr("growth_rate_caption"))
                    else:
                        val_col3.metric(tr("eps_growth_next_5yrs"), tr("na"))

                    st.markdown("---")
                    st.subheader(tr("multi_model_consensus"))

                    # Extract _meta and build model-only dict
                    val_meta = valuations.get('_meta', {})
                    val_models = {k: v for k, v in valuations.items() if k != '_meta'}

                    if current_price and current_price > 0 and len(val_models) >= 3:
                        # --- Weighted & Simple Consensus ---
                        weights = [v.get('weight', 1.0 / len(val_models)) for v in val_models.values()]
                        total_w = sum(weights)
                        iv_list = [v['intrinsic_value'] for v in val_models.values()]
                        fp_list = [v.get('future_price_5y', v.get('future_price', 0)) for v in val_models.values()]

                        weighted_iv = sum(iv * w for iv, w in zip(iv_list, weights)) / total_w
                        simple_iv   = sum(iv_list) / len(iv_list)
                        weighted_fp = sum(fp * w for fp, w in zip(fp_list, weights)) / total_w
                        simple_fp   = sum(fp_list) / len(fp_list)
                        margin_of_safety = ((weighted_iv - current_price) / weighted_iv) * 100
                        val_years = val_meta.get('years', 5)
                        consensus_cagr = (((weighted_fp / current_price) ** (1 / val_years) - 1) * 100) if (current_price > 0 and weighted_fp > 0) else 0.0

                        # WACC / model assumptions info box
                        if val_meta:
                            wacc_val = val_meta.get('wacc', discount_rate)
                            beta_val = val_meta.get('beta', 1.1)
                            coe_val  = val_meta.get('cost_of_equity', wacc_val)
                            eps_g_val = val_meta.get('eps_growth', growth_rate)
                            rev_g_val = val_meta.get('rev_growth', growth_rate)
                            fcf_g_val = val_meta.get('fcf_growth', growth_rate)
                            tg_val    = val_meta.get('terminal_growth', 2.5)

                            st.info(
                                f"📐 **Model Assumptions** | "
                                f"WACC: **{wacc_val:.1f}%** (β={beta_val:.2f}, CoE={coe_val:.1f}%) | "
                                f"EPS Growth: **{eps_g_val:.1f}%** | "
                                f"Rev Growth: **{rev_g_val:.1f}%** | "
                                f"FCF Growth: **{fcf_g_val:.1f}%** | "
                                f"Terminal Growth: **{tg_val:.1f}%** | "
                                f"Horizon: **{val_years} years**"
                            )

                        # Main consensus metrics
                        mc1, mc2, mc3, mc4, mc5 = st.columns(5)
                        mc1.metric("⚖️ Weighted Intrinsic Value", f"{cs()}{weighted_iv:.2f}")
                        mc2.metric("📊 Simple Average IV", f"{cs()}{simple_iv:.2f}")
                        if weighted_iv > current_price:
                            mc3.metric(tr("consensus_margin_safety"), f"{margin_of_safety:.2f}%", "▲ " + tr("undervalued"))
                        else:
                            mc3.metric(tr("consensus_margin_safety"), f"{margin_of_safety:.2f}%", "▼ " + tr("overvalued_sign"), delta_color="inverse")
                        mc4.metric(tr("current_market_price"), f"{cs()}{current_price:.2f}")
                        mc5.metric(tr("consensus_cagr"), f"{consensus_cagr:.2f}%")

                        st.markdown("---")
                        chart_col, details_col = st.columns([3, 2])
                        with chart_col:
                            fig_val = create_valuation_chart(valuations, current_price, years=val_years)
                            if fig_val:
                                st.plotly_chart(fig_val, use_container_width=True)

                            # --- DCF Sensitivity Table ---
                            with st.expander("🔢 DCF Sensitivity Analysis (Intrinsic Value)"):
                                growth_scenarios = [-5, 0, +5]
                                wacc_scenarios   = [-2, 0, +2]
                                base_fcf = val_meta.get('fcf_growth', growth_rate) if val_meta else growth_rate
                                base_wacc = val_meta.get('wacc', discount_rate) if val_meta else discount_rate
                                base_tg   = val_meta.get('terminal_growth', 2.5) if val_meta else 2.5
                                base_fcf_ps = [v['intrinsic_value'] for k, v in val_models.items() if '2-Stage DCF' in k]
                                base_fcf_ps = base_fcf_ps[0] if base_fcf_ps else weighted_iv

                                # Recompute DCF for each scenario
                                fcf_real = info.get('freeCashflow') or 0
                                s_out = info.get('sharesOutstanding', 1) or 1
                                fcf_ps_base = fcf_real / s_out if fcf_real > 0 else (simple_iv * 0.05)

                                sens_rows = []
                                for dg in growth_scenarios:
                                    row = {'Growth Rate': f"{base_fcf + dg:.1f}%"}
                                    for dw in wacc_scenarios:
                                        g = (base_fcf + dg) / 100
                                        w = (base_wacc + dw) / 100
                                        tg_s = base_tg / 100
                                        if w <= tg_s: w = tg_s + 0.01
                                        pv = sum(fcf_ps_base * ((1 + g) ** i) / ((1 + w) ** i) for i in range(1, val_years + 1))
                                        fcf_n = fcf_ps_base * ((1 + g) ** val_years)
                                        tv = fcf_n * (1 + tg_s) / (w - tg_s)
                                        iv_s = pv + tv / ((1 + w) ** val_years)
                                        row[f"WACC {base_wacc + dw:.1f}%"] = f"{cs()}{iv_s:.1f}"
                                    sens_rows.append(row)

                                sens_df = pd.DataFrame(sens_rows).set_index('Growth Rate')
                                st.caption(f"📌 Base: FCF Growth {base_fcf:.1f}%, WACC {base_wacc:.1f}%, Terminal {base_tg:.1f}%")
                                st.dataframe(sens_df, use_container_width=True)

                        with details_col:
                            st.subheader(tr("individual_model_targets").format(years=val_years))
                            # Full sortable model table
                            model_rows = []
                            for name, val_data in val_models.items():
                                fv = val_data.get('future_price_5y', val_data.get('future_price', 0))
                                iv = val_data['intrinsic_value']
                                upside_iv = ((iv - current_price) / current_price * 100) if current_price > 0 else 0
                                upside_fv = ((fv - current_price) / current_price * 100) if current_price > 0 else 0
                                verdict = "✅" if iv >= current_price else "❌"
                                model_rows.append({
                                    "Model": name,
                                    "Intrinsic Value": f"{cs()}{iv:.2f}",
                                    "Upside IV": f"{'▲' if upside_iv >= 0 else '▼'}{abs(upside_iv):.1f}%",
                                    f"{val_years}Y Target": f"{cs()}{fv:.2f}",
                                    "Verdict": verdict,
                                })
                            st.dataframe(pd.DataFrame(model_rows).set_index("Model"), use_container_width=True)

                            st.markdown("---")
                            # Individual detail expandable per model
                            for idx, (name, val_data) in enumerate(val_models.items(), 1):
                                with st.expander(f"{idx}. {name}"):
                                    desc_translated = translate_text(val_data['description']) if st.session_state.get("language", "en") == "he" else val_data['description']
                                    fv = val_data.get('future_price_5y', val_data.get('future_price', 0))
                                    iv = val_data['intrinsic_value']
                                    upside = ((iv - current_price) / current_price * 100) if current_price > 0 else 0
                                    model_cagr = (((fv / current_price) ** (1 / val_years) - 1) * 100) if (current_price > 0 and fv > 0) else 0.0
                                    st.markdown(f"**Method:** {desc_translated}")
                                    st.markdown(f"**{val_years}-Year Target:** `{cs()}{fv:.2f}`")
                                    st.markdown(f"**CAGR:** `{model_cagr:.1f}%`")
                                    st.markdown(f"**Intrinsic Value (PV):** `{cs()}{iv:.2f}` ({'▲ Undervalued' if upside >= 0 else '▼ Overvalued'} {abs(upside):.1f}%)")

                    elif current_price and current_price > 0:
                        st.warning(tr("minimum_models_warning").format(num_models=len(val_models)))
                        for idx, (name, val_data) in enumerate(val_models.items(), 1):
                            st.markdown("### " + tr("valuation_number").format(idx=idx, name=name))
                            desc_translated = translate_text(val_data['description']) if st.session_state.get("language", "en") == "he" else val_data['description']
                            st.markdown(desc_translated)
                            st.markdown(tr("target_price_fv").format(years=5, val=val_data['future_price_5y']))
                            future_val = val_data.get('future_price_5y', val_data.get('future_price', 0))
                            model_cagr = (((future_val / current_price) ** (1 / 5) - 1) * 100) if (current_price > 0 and future_val > 0) else 0.0
                            st.markdown(tr("projected_cagr").format(cagr=model_cagr))
                            st.markdown(tr("intrinsic_value_pv").format(val=val_data['intrinsic_value']))
                    else:
                        st.warning(tr("valuation_requirements_warning"))


                # ==========================================
                # TAB 5: TIME MACHINE (BACKTESTING)
                # ==========================================
                with tab5:
                    st.subheader(tr("time_machine_title"))
                    st.markdown(tr("time_machine_description"))

                    if df_fin_a is not None and not df_fin_a.empty:
                        available_years = sorted(df_fin_a.index.tolist(), reverse=True)
                        current_year = pd.Timestamp.now().year
                        valid_years = available_years

                        if valid_years:
                            selected_year = st.selectbox(tr("select_historical_year"), valid_years)
                            projection_years = st.slider(tr("select_forecast_horizon"), min_value=1, max_value=5, value=5, step=1, key="backtest_horizon")

                            if selected_year:
                                target_year = selected_year + projection_years
                                st.markdown(tr("running_consensus_valuation").format(year=selected_year, years=projection_years, target_year=target_year))

                                hist_fin = df_fin_a.loc[selected_year]
                                hist_cf = df_cf_a.loc[selected_year] if (
                                            df_cf_a is not None and not df_cf_a.empty and selected_year in df_cf_a.index) else pd.Series()

                                hist_price_slice = history[history.index.year <= selected_year]
                                if not hist_price_slice.empty:
                                    hist_price = hist_price_slice['Close'].iloc[-1]
                                    hist_date = hist_price_slice.index[-1].strftime('%Y-%m-%d')

                                    st.write(tr("historical_stock_price").format(date=hist_date, price=hist_price))

                                    # --- Fetch Historical Annual Metrics ---
                                    hist_shares = hist_fin.get('Diluted Average Shares',
                                                               hist_fin.get('Basic Average Shares', shares_out))
                                    if not hist_shares or hist_shares <= 0:
                                        hist_shares = shares_out

                                    hist_eps = hist_fin.get('Diluted EPS', hist_fin.get('Basic EPS', 0))
                                    if pd.isna(hist_eps) or hist_eps == 0:
                                        hist_net_income = hist_fin.get('Net Income', 0)
                                        hist_eps = hist_net_income / hist_shares if hist_shares > 0 else 0

                                    rev_col = 'Total Revenue' if 'Total Revenue' in hist_fin else (
                                        'Operating Revenue' if 'Operating Revenue' in hist_fin else None)
                                    hist_rev = hist_fin.get(rev_col, 0) if rev_col else 0
                                    hist_rev_per_share = hist_rev / hist_shares if hist_shares > 0 else 0

                                    fcf_col = 'Free Cash Flow'
                                    hist_fcf = hist_cf.get(fcf_col, 0) if (
                                                not hist_cf.empty and fcf_col in hist_cf) else 0
                                    if pd.isna(hist_fcf) or hist_fcf <= 0:
                                        hist_fcf = hist_rev * 0.10
                                    hist_fcf_per_share = hist_fcf / hist_shares if hist_shares > 0 else 0

                                    # --- Dynamic Baseline Calculations for Growth ---
                                    auto_growth_rate = 15.0
                                    past_years = [y for y in available_years if y < selected_year]
                                    lookback_years = 0
                                    if past_years:
                                        oldest_year = min(past_years)
                                        lookback_years = selected_year - oldest_year
                                        past_fin = df_fin_a.loc[oldest_year]

                                        past_eps = past_fin.get('Diluted EPS', past_fin.get('Basic EPS', 0))
                                        if pd.isna(past_eps) or past_eps == 0:
                                            p_shares = past_fin.get('Diluted Average Shares',
                                                                    past_fin.get('Basic Average Shares', shares_out))
                                            p_ni = past_fin.get('Net Income', 0)
                                            past_eps = p_ni / p_shares if (p_shares and p_shares > 0) else 0

                                        if past_eps > 0 and hist_eps > 0 and lookback_years > 0:
                                            auto_growth_rate = ((hist_eps / past_eps) ** (1 / lookback_years) - 1) * 100

                                    auto_growth_rate = min(max(auto_growth_rate, -20.0), 50.0)

                                    # --- OVERRIDE WITH LIVE TTM DATA IF LATEST YEAR IS SELECTED (To Match Tab 4 perfectly) ---
                                    is_latest_year = (selected_year == available_years[0])

                                    if is_latest_year:
                                        hist_shares = shares_out
                                        ttm_eps = info.get('trailingEps')
                                        if ttm_eps: hist_eps = ttm_eps

                                        ttm_rev = info.get('totalRevenue')
                                        if ttm_rev and shares_out > 0:
                                            hist_rev_per_share = ttm_rev / shares_out

                                        ttm_fcf = info.get('freeCashflow')
                                        if ttm_fcf and shares_out > 0:
                                            hist_fcf_per_share = ttm_fcf / shares_out

                                    hist_pe = (hist_price / hist_eps) if hist_eps > 0 else 15.0
                                    hist_ps = (hist_price / hist_rev_per_share) if hist_rev_per_share > 0 else 3.0
                                    hist_pfcf = (hist_price / hist_fcf_per_share) if hist_fcf_per_share > 0 else 15.0

                                    default_exit_pe = min(max(avg_pe if is_latest_year else hist_pe, 10.0), 25.0)
                                    target_ps_info = info.get('priceToSalesTrailing12Months', 3.0)
                                    default_exit_ps = min(max(target_ps_info if is_latest_year else hist_ps, 0.5), 10.0)
                                    
                                    target_fcf_info = info.get('priceToFreeCashflow')
                                    if not target_fcf_info or target_fcf_info <= 0:
                                        target_fcf_info = avg_pe if avg_pe else 18.0
                                    default_exit_pfcf = min(max(target_fcf_info if is_latest_year else hist_pfcf, 12.0),
                                                            25.0)

                                    def_earn_g = auto_growth_rate
                                    def_rev_g = auto_growth_rate
                                    if is_latest_year:
                                        def_earn_g = growth_rate
                                        rg_info = info.get('revenueGrowth')
                                        if rg_info is not None: def_rev_g = rg_info * 100

                                    st.markdown("---")
                                    st.markdown(f"**{tr('base_starting_metrics')}**")
                                    col_m1, col_m2, col_m3 = st.columns(3)
                                    user_eps = col_m1.number_input(tr("base_eps"), value=float(hist_eps), step=0.1,
                                                                   format="%.2f")
                                    user_rev_ps = col_m2.number_input(tr("base_rev_share"),
                                                                      value=float(hist_rev_per_share), step=0.5,
                                                                      format="%.2f")
                                    user_fcf_ps = col_m3.number_input(tr("base_fcf_share"),
                                                                      value=float(hist_fcf_per_share), step=0.1,
                                                                      format="%.2f")

                                    st.markdown(f"**{tr('growth_assumptions')}**")
                                    col_g1, col_g2 = st.columns(2)
                                    user_earn_growth = col_g1.number_input(tr("earnings_fcf_growth_cagr"),
                                                                           value=float(def_earn_g), step=0.5,
                                                                           format="%.2f")
                                    user_rev_growth = col_g2.number_input(tr("revenue_growth_cagr"),
                                                                          value=float(def_rev_g), step=0.5,
                                                                          format="%.2f")

                                    st.markdown(
                                        f"**{tr('exit_multiples')}**")
                                    col_e1, col_e2, col_e3 = st.columns(3)
                                    user_exit_pe = col_e1.number_input(tr("target_pe"), value=float(default_exit_pe),
                                                                       step=1.0)
                                    user_exit_ps = col_e2.number_input(tr("target_ps"), value=float(default_exit_ps),
                                                                       step=0.5)
                                    user_exit_pfcf = col_e3.number_input(tr("target_pfcf"),
                                                                         value=float(default_exit_pfcf), step=1.0)

                                    # --- Reconstruct the info object to inject into calculate_valuations ---
                                    if is_latest_year:
                                        # For the most recent year, use the live ticker info directly to guarantee identical inputs.
                                        hist_info = info.copy()
                                        # Override only the editable base metrics while keeping original multiples and ratios.
                                        hist_info['sharesOutstanding'] = hist_shares
                                        hist_info['currentPrice'] = hist_price
                                        hist_info['trailingEps'] = user_eps
                                        # Derive total revenue and free cash flow from per‑share values provided by the user.
                                        hist_info['totalRevenue'] = user_rev_ps * hist_shares
                                        hist_info['freeCashflow'] = user_fcf_ps * hist_shares
                                        # Growth rates are taken from the editable fields.
                                        hist_info['revenueGrowth'] = user_rev_growth / 100.0
                                        hist_info['earningsGrowth'] = user_earn_growth / 100.0
                                        # Exit multiples: allow user edits but fall back to live values when not edited.
                                        hist_info['priceToSalesTrailing12Months'] = user_exit_ps
                                        hist_info['priceToFreeCashflow'] = user_exit_pfcf
                                    else:
                                        # Historical year: build a full info dict mirroring the structure used for live calculations.
                                        hist_bs = df_bs_a.loc[selected_year] if (df_bs_a is not None and not df_bs_a.empty and selected_year in df_bs_a.index) else pd.Series()
                                        hist_cf = df_cf_a.loc[selected_year] if (df_cf_a is not None and not df_cf_a.empty and selected_year in df_cf_a.index) else pd.Series()

                                        hist_ebitda = hist_fin.get('EBITDA', hist_fin.get('Operating Income', 0))
                                        if pd.isna(hist_ebitda) or hist_ebitda <= 0:
                                            hist_ebitda = (user_rev_ps * hist_shares) * 0.15

                                        hist_equity = hist_bs.get('Stockholders Equity', hist_bs.get('Total Assets', 0) - hist_bs.get('Total Liabilities Net Minority Interest', 0))
                                        if pd.isna(hist_equity) or hist_equity <= 0:
                                            hist_equity = hist_shares * (hist_price / 3.0)

                                        hist_bv = hist_equity / hist_shares
                                        hist_roe = (hist_fin.get('Net Income', 0) / hist_equity) if hist_equity > 0 else 0.12
                                        if pd.isna(hist_roe):
                                            hist_roe = 0.12

                                        hist_debt = hist_bs.get('Total Debt', 0)
                                        if pd.isna(hist_debt):
                                            hist_debt = 0
                                        hist_cash = hist_bs.get('Cash And Cash Equivalents', 0)
                                        if pd.isna(hist_cash):
                                            hist_cash = 0

                                        hist_info = {
                                            'sharesOutstanding': hist_shares,
                                            'currentPrice': hist_price,
                                            'trailingEps': user_eps,
                                            'totalRevenue': user_rev_ps * hist_shares,
                                            'freeCashflow': user_fcf_ps * hist_shares,
                                            'revenueGrowth': user_rev_growth / 100.0,
                                            'earningsGrowth': user_earn_growth / 100.0,
                                            'priceToSalesTrailing12Months': user_exit_ps,
                                            'priceToFreeCashflow': user_exit_pfcf,
                                            'ebitda': hist_ebitda,
                                            'bookValue': hist_bv,
                                            'returnOnEquity': hist_roe,
                                            'priceToBook': info.get('priceToBook', user_exit_ps * 2.0),
                                            'totalDebt': hist_debt,
                                            'totalCash': hist_cash,
                                            'enterpriseToEbitda': user_exit_pe,
                                        }

                                    hist_fin_df = pd.DataFrame(hist_fin).T

                                    # Execute the exact identical function utilized in Tab 4
                                    hist_valuations = calculate_valuations(hist_info, hist_fin_df, avg_pe=user_exit_pe,
                                                                           growth_rate=user_earn_growth,
                                                                           discount_rate=discount_rate,
                                                                           years=projection_years,
                                                                           use_wacc=False)

                                    hist_models = {k: v for k, v in hist_valuations.items() if k != '_meta'}

                                    if hist_models and len(hist_models) >= 2:
                                        h_weights = [v.get('weight', 1.0 / len(hist_models)) for v in hist_models.values()]
                                        h_total_w = sum(h_weights)
                                        h_ivs = [v['intrinsic_value'] for v in hist_models.values()]
                                        h_fps = [v['future_price'] for v in hist_models.values()]

                                        avg_intrinsic = sum(iv * w for iv, w in zip(h_ivs, h_weights)) / h_total_w
                                        avg_target = sum(fp * w for fp, w in zip(h_fps, h_weights)) / h_total_w

                                        st.markdown("---")
                                        st.subheader(tr("backtest_results_header").format(years=projection_years))

                                        # --- Summary metrics ---
                                        bm1, bm2, bm3, bm4 = st.columns(4)
                                        bm1.metric("📍 Starting Price", f"{cs()}{hist_price:.2f}", f"{selected_year}")
                                        bm2.metric("⚖️ Weighted Intrinsic Value", f"{cs()}{avg_intrinsic:.2f}")
                                        bm3.metric(f"🎯 Weighted {projection_years}Y Target", f"{cs()}{avg_target:.2f}")
                                        proj_cagr = ((avg_target / hist_price) ** (1 / projection_years) - 1) * 100 if hist_price > 0 and projection_years > 0 else 0
                                        bm4.metric("📈 Projected CAGR", f"{proj_cagr:.1f}%")

                                        st.markdown(
                                            tr("backtest_target_intrinsic").format(years=projection_years, avg_target=avg_target, avg_intrinsic=avg_intrinsic)
                                        )

                                        # Compare historic starting price to calculated intrinsic value
                                        diff_starting = ((hist_price - avg_intrinsic) / avg_intrinsic) * 100
                                        if hist_price < avg_intrinsic:
                                            st.info(tr("historic_price_undervalued_info").format(year=selected_year, price=hist_price, intrinsic=avg_intrinsic, pct=abs(diff_starting)))
                                        else:
                                            st.info(tr("historic_price_overvalued_info").format(year=selected_year, price=hist_price, intrinsic=avg_intrinsic, pct=abs(diff_starting)))

                                        # --- Find actual price at target year ---
                                        target_price_slice = history[history.index.year == target_year]
                                        actual_target_price = None
                                        actual_target_date = None
                                        if not target_price_slice.empty:
                                            actual_target_price = target_price_slice['Close'].iloc[-1]
                                            actual_target_date = target_price_slice.index[-1].strftime('%Y-%m-%d')

                                        # --- Full model results table ---
                                        st.markdown("---")
                                        st.markdown(f"### 📊 All Models — {projection_years}-Year Results")
                                        result_rows = []
                                        model_errors = {}  # for accuracy chart
                                        for mname, mdata in hist_models.items():
                                            fp = mdata['future_price']
                                            iv = mdata['intrinsic_value']
                                            proj_ret = ((fp / hist_price) - 1) * 100 if hist_price > 0 else 0
                                            row = {
                                                "Model": mname,
                                                "Projected Target": f"{cs()}{fp:.2f}",
                                                "Proj Return": f"{'▲' if proj_ret >= 0 else '▼'}{abs(proj_ret):.1f}%",
                                                "Intrinsic Value": f"{cs()}{iv:.2f}",
                                            }
                                            if actual_target_price is not None:
                                                err_pct = abs(fp - actual_target_price) / actual_target_price * 100
                                                accuracy = max(0, 100 - err_pct)
                                                verdict = "✅" if fp >= actual_target_price * 0.9 else "❌"
                                                row["Actual Price"] = f"{cs()}{actual_target_price:.2f}"
                                                row["Error %"] = f"{err_pct:.1f}%"
                                                row["Accuracy"] = f"{accuracy:.0f}%"
                                                row["Verdict"] = verdict
                                                model_errors[mname] = err_pct
                                            result_rows.append(row)

                                        result_df = pd.DataFrame(result_rows).set_index("Model")
                                        st.dataframe(result_df, use_container_width=True)

                                        # --- Accuracy chart (if actual price available) ---
                                        if actual_target_price is not None:
                                            st.markdown("---")
                                            st.subheader(tr("performance_at_target_year").format(year=target_year, date=actual_target_date))

                                            # Comparison metrics
                                            ap1, ap2, ap3 = st.columns(3)
                                            ap1.metric(tr("actual_closing_price_in_year").format(year=target_year), f"{cs()}{actual_target_price:.2f}")
                                            ap2.metric(tr("projected_target_price"), f"{cs()}{avg_target:.2f}")
                                            actual_cagr = ((actual_target_price / hist_price) ** (1 / projection_years) - 1) * 100 if hist_price > 0 and projection_years > 0 else 0
                                            ap3.metric("Actual CAGR", f"{actual_cagr:.1f}%")

                                            diff_pct = ((actual_target_price - avg_target) / avg_target) * 100
                                            if actual_target_price >= avg_target:
                                                st.success(tr("success_beat_target").format(years=projection_years, pct=diff_pct))
                                            else:
                                                st.warning(tr("warning_miss_target").format(year=target_year, pct=abs(diff_pct)))

                                            # --- Accuracy bar chart ---
                                            model_names_chart = list(model_errors.keys())
                                            projected_prices_chart = [hist_models[m]['future_price'] for m in model_names_chart]
                                            errors_chart = [model_errors[m] for m in model_names_chart]

                                            fig_accuracy = go.Figure()
                                            bar_colors_chart = ['#10B981' if p >= actual_target_price * 0.9 else '#F87171' for p in projected_prices_chart]
                                            fig_accuracy.add_trace(go.Bar(
                                                x=model_names_chart,
                                                y=projected_prices_chart,
                                                name=f"Projected {projection_years}Y Price",
                                                marker_color=bar_colors_chart,
                                                text=[f"{cs()}{p:.1f}" for p in projected_prices_chart],
                                                textposition='outside',
                                                opacity=0.85,
                                            ))
                                            fig_accuracy.add_hline(
                                                y=actual_target_price,
                                                line_dash="solid",
                                                line_color="#F59E0B",
                                                line_width=3,
                                                annotation_text=f"  Actual ({actual_target_date}): {cs()}{actual_target_price:.2f}",
                                                annotation_position="top right",
                                                annotation_font=dict(color="#F59E0B", size=12)
                                            )
                                            fig_accuracy.add_hline(
                                                y=hist_price,
                                                line_dash="dash",
                                                line_color="#94A3B8",
                                                line_width=2,
                                                annotation_text=f"  Starting Price ({selected_year}): {cs()}{hist_price:.2f}",
                                                annotation_position="bottom right",
                                                annotation_font=dict(color="#94A3B8", size=11)
                                            )
                                            fig_accuracy.update_layout(
                                                title=f"<b>Model Accuracy: Projected vs Actual Price ({selected_year}→{target_year})</b>",
                                                yaxis_title="Price",
                                                barmode='group',
                                                margin=dict(t=60, b=80, l=40, r=40),
                                                xaxis=dict(tickangle=-30),
                                            )
                                            st.plotly_chart(fig_accuracy, use_container_width=True)

                                            # --- Model accuracy ranking ---
                                            st.markdown("#### 🏆 Model Accuracy Ranking")
                                            sorted_models = sorted(model_errors.items(), key=lambda x: x[1])
                                            rank_rows = []
                                            for rank, (mname, err) in enumerate(sorted_models, 1):
                                                fp = hist_models[mname]['future_price']
                                                accuracy = max(0, 100 - err)
                                                medal = "🥇" if rank == 1 else ("🥈" if rank == 2 else ("🥉" if rank == 3 else f"#{rank}"))
                                                rank_rows.append({
                                                    "Rank": medal,
                                                    "Model": mname,
                                                    "Projected": f"{cs()}{fp:.2f}",
                                                    "Error %": f"{err:.1f}%",
                                                    "Accuracy Score": f"{accuracy:.0f}/100",
                                                })
                                            st.dataframe(pd.DataFrame(rank_rows).set_index("Rank"), use_container_width=True)

                                            # --- Visual timeline ---
                                            with st.expander("📈 Visual Timeline: Price Path + Model Targets"):
                                                hist_range = history[(history.index.year >= selected_year - 1) & (history.index.year <= target_year + 1)]
                                                if not hist_range.empty:
                                                    fig_timeline = go.Figure()
                                                    fig_timeline.add_trace(go.Scatter(
                                                        x=hist_range.index,
                                                        y=hist_range['Close'],
                                                        mode='lines',
                                                        name='Actual Price',
                                                        line=dict(color='#F59E0B', width=2.5),
                                                        fill='tozeroy',
                                                        fillcolor='rgba(245, 158, 11, 0.05)'
                                                    ))
                                                    colors_cycle = ['#10B981', '#3B82F6', '#8B5CF6', '#F87171', '#60A5FA', '#34D399', '#FBBF24', '#A78BFA', '#F472B6', '#2DD4BF']
                                                    for i, (mname, mdata) in enumerate(hist_models.items()):
                                                        fp = mdata['future_price']
                                                        col = colors_cycle[i % len(colors_cycle)]
                                                        fig_timeline.add_hline(
                                                            y=fp,
                                                            line_dash="dot",
                                                            line_color=col,
                                                            line_width=1.2,
                                                            annotation_text=f" {mname[:15]}: {cs()}{fp:.0f}",
                                                            annotation_position="right",
                                                            annotation_font=dict(color=col, size=8)
                                                        )
                                                    fig_timeline.update_layout(
                                                        title=f"<b>Price Path: {selected_year} → {target_year}</b>",
                                                        xaxis_title="Date",
                                                        yaxis_title="Price",
                                                        margin=dict(t=50, b=20, l=40, r=200),
                                                        height=400
                                                    )
                                                    st.plotly_chart(fig_timeline, use_container_width=True)

                                        else:
                                            # Target year is in the future relative to historical series
                                            st.subheader(tr("performance_status_future").format(year=target_year))
                                            col_perf1, col_perf2 = st.columns(2)
                                            col_perf1.metric(tr("actual_price_today"), f"{cs()}{current_price:.2f}")
                                            col_perf2.metric(tr("projected_target_price_for_year").format(year=target_year), f"{cs()}{avg_target:.2f}")

                                            years_passed = current_year - selected_year
                                            if years_passed > 0:
                                                cagr_actual = ((current_price / hist_price) ** (1 / years_passed) - 1) * 100
                                                st.write(tr("actual_return_to_date").format(year=selected_year, cagr=cagr_actual, years=years_passed))
                                                diff_pct = ((current_price - avg_target) / avg_target) * 100
                                                if current_price >= avg_target:
                                                    st.success(tr("note_already_trading_above").format(years=projection_years, pct=diff_pct))
                                                else:
                                                    st.info(tr("info_below_projected_target").format(years=projection_years, pct=abs(diff_pct)))
                                            else:
                                                st.write(tr("selected_year_is_current").format(year=selected_year, years=projection_years))

                                        # --- Detailed table expander ---
                                        with st.expander(tr("show_detailed_table")):
                                            breakdown_data = []
                                            for name, val_data in hist_models.items():
                                                name_trans = translate_text(name) if st.session_state.language == "he" else name
                                                desc_trans = translate_text(val_data['description']) if st.session_state.language == "he" else val_data['description']
                                                breakdown_data.append({
                                                    tr("valuation_model_column"): name_trans,
                                                    tr("intrinsic_value_pv_column"): f"{cs()}{val_data['intrinsic_value']:.2f}",
                                                    tr("target_price_fv_column").format(years=projection_years): f"{cs()}{val_data['future_price']:.2f}",
                                                    tr("description_column"): desc_trans
                                                })
                                            st.table(pd.DataFrame(breakdown_data))

                                    else:
                                        st.error(tr("error_not_enough_historical_valuation"))
                                else:
                                    st.error(tr("error_could_not_find_historical_price"))
                        else:
                            st.warning(tr("warning_not_enough_historical_data"))
                    else:
                        st.warning(tr("warning_historical_financials_unavailable"))


                # ==========================================
                # TAB 6: NEWS & MARKET SENTIMENT
                # ==========================================
                with tab6:

                    # ── SECTION A: SECTOR INTELLIGENCE ──────────────────────────────
                    raw_sector = info.get('sector', '')
                    st.markdown(f"## {tr('sector_sentiment_title')}")
                    st.caption(tr('sector_sentiment_subtitle'))

                    if raw_sector and raw_sector in SECTOR_ETF_MAP:
                        with st.spinner(tr("sector_loading")):
                            sd = get_sector_sentiment_data(ticker_input, raw_sector)

                        etf_ticker  = sd["etf_ticker"]
                        etf_name    = sd["etf_name"]
                        divergence  = sd["divergence"]
                        signal      = sd["signal"]

                        # ── Signal Banner ──
                        if divergence is not None:
                            diff_abs = abs(divergence)
                            if signal == "bullish":
                                banner_msg = tr("sector_outperforming").format(ticker=ticker_input, etf=etf_ticker, diff=diff_abs)
                                banner_color = "#0d2b1f"
                                border_color = "#10b981"
                                badge_color  = "#10b981"
                                badge_label  = tr("divergence_bullish")
                            elif signal == "bearish":
                                banner_msg = tr("sector_underperforming").format(ticker=ticker_input, etf=etf_ticker, diff=diff_abs)
                                banner_color = "#2b0f0f"
                                border_color = "#ef4444"
                                badge_color  = "#ef4444"
                                badge_label  = tr("divergence_bearish")
                            else:
                                banner_msg = tr("sector_inline").format(ticker=ticker_input, etf=etf_ticker)
                                banner_color = "#1c2030"
                                border_color = "#848e9c"
                                badge_color  = "#848e9c"
                                badge_label  = tr("divergence_neutral")

                            st.markdown(f"""
                            <div style="background:{banner_color}; border-left:4px solid {border_color}; border-radius:8px;
                                        padding:14px 18px; margin-bottom:18px; display:flex; align-items:center; gap:14px;">
                                <span style="background:{badge_color}; color:#fff; font-weight:700; font-size:12px;
                                             border-radius:5px; padding:4px 10px; white-space:nowrap;">{badge_label}</span>
                                <span style="color:#d1d4dc; font-size:14px; font-family:'Outfit','Rubik',sans-serif;">{banner_msg}</span>
                            </div>
                            """, unsafe_allow_html=True)

                        # ── Metric Cards ──
                        col_s1, col_s2, col_s3, col_s4, col_s5 = st.columns(5)

                        def _fmt_ret(v):
                            if v is None: return "N/A"
                            color = "#10b981" if v >= 0 else "#ef4444"
                            sign  = "+" if v >= 0 else ""
                            return f'<span style="color:{color};font-weight:700;">{sign}{v:.2f}%</span>'

                        def _fmt_div(v):
                            if v is None: return "N/A"
                            color = "#10b981" if v >= 0 else "#ef4444"
                            sign  = "+" if v >= 0 else ""
                            return f'<span style="color:{color};font-weight:800;font-size:22px;">{sign}{v:.2f}%</span>'

                        def _mini_card(col, title, html_val, subtitle=""):
                            col.markdown(f"""
                            <div style="background:#1c2030;border:1px solid #2a2e39;border-radius:8px;padding:14px 12px;text-align:center;">
                                <div style="color:#848e9c;font-size:11px;font-weight:600;text-transform:uppercase;margin-bottom:6px;font-family:'Outfit','Rubik',sans-serif;">{title}</div>
                                <div style="font-size:20px;font-family:'Outfit','Rubik',sans-serif;">{html_val}</div>
                                {f'<div style="color:#848e9c;font-size:10px;margin-top:4px;">{subtitle}</div>' if subtitle else ''}
                            </div>""", unsafe_allow_html=True)

                        _mini_card(col_s1, tr("stock_momentum"),   _fmt_ret(sd["stock_return_3m"]), "3M")
                        _mini_card(col_s2, tr("sector_momentum"),  _fmt_ret(sd["etf_return_3m"]),   f"{etf_ticker} · 3M")
                        _mini_card(col_s3, tr("divergence_score"), _fmt_div(divergence),             tr("divergence_explanation"))
                        _mini_card(col_s4, tr("stock_momentum"),   _fmt_ret(sd["stock_return_1m"]), "1M")
                        _mini_card(col_s5, tr("sector_momentum"),  _fmt_ret(sd["etf_return_1m"]),   f"{etf_ticker} · 1M")

                        st.markdown("<br>", unsafe_allow_html=True)

                        # ── Charts: Performance + Radar ──
                        col_chart_left, col_chart_right = st.columns([3, 2])

                        with col_chart_left:
                            st.markdown(f"**{tr('stock_vs_sector_perf')}**")
                            if sd["stock_hist"] is not None and sd["etf_hist"] is not None:
                                fig_div = create_sector_divergence_chart(
                                    sd["stock_hist"], sd["etf_hist"], ticker_input, etf_ticker
                                )
                                fig_div = apply_tradingview_plotly_style(fig_div)
                                fig_div.update_layout(title=f"<b>{ticker_input} vs {etf_ticker}</b> · 3M Normalized (Base=100)")
                                plotly_chart_styled(fig_div)
                            else:
                                st.info("Chart data unavailable.")

                        with col_chart_right:
                            st.markdown(f"**{tr('sector_radar_title')}**")
                            fig_radar = create_sector_radar_chart(
                                ticker_input, etf_ticker,
                                divergence,
                                sd["stock_vol"], sd["etf_vol"],
                                sd["stock_return_3m"], sd["etf_return_3m"],
                                sd["stock_return_1m"], sd["etf_return_1m"]
                            )
                            fig_radar = apply_tradingview_plotly_style(fig_radar)
                            plotly_chart_styled(fig_radar)

                        # ── 6-Month Return Comparison Bar ──
                        if sd["stock_return_6m"] is not None and sd["etf_return_6m"] is not None:
                            st.markdown("---")
                            fig_bar = go.Figure()
                            colors_bar = {
                                ticker_input: "#2962ff",
                                f"{etf_ticker} (Sector)": "#f59e0b"
                            }
                            for label, val in [(ticker_input, sd["stock_return_6m"]), (f"{etf_ticker} (Sector)", sd["etf_return_6m"])]:
                                fig_bar.add_trace(go.Bar(
                                    x=["1M Return", "3M Return", "6M Return"],
                                    y=[
                                        sd["stock_return_1m"] if label == ticker_input else sd["etf_return_1m"],
                                        sd["stock_return_3m"] if label == ticker_input else sd["etf_return_3m"],
                                        sd["stock_return_6m"] if label == ticker_input else sd["etf_return_6m"]
                                    ],
                                    name=label,
                                    marker_color=colors_bar[label],
                                    opacity=0.85
                                ))
                            fig_bar.update_layout(
                                title=f"<b>{ticker_input} vs {etf_ticker}</b> — Multi-Period Return Comparison",
                                barmode="group",
                                yaxis_title="Return (%)",
                                yaxis_ticksuffix="%",
                                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                                margin=dict(t=50, b=20)
                            )
                            fig_bar = apply_tradingview_plotly_style(fig_bar)
                            plotly_chart_styled(fig_bar)

                        # ── ETF Info Footer ──
                        st.markdown(f"""
                        <div style="background:#161b2d;border:1px solid #2a2e39;border-radius:8px;padding:12px 16px;margin-top:10px;">
                            <span style="color:#848e9c;font-size:12px;">🏷️ {tr('sector_etf_label')}: </span>
                            <span style="color:#d1d4dc;font-weight:600;font-size:13px;">{etf_ticker} — {etf_name}</span>
                            &nbsp;&nbsp;|&nbsp;&nbsp;
                            <span style="color:#848e9c;font-size:12px;">📂 {tr('sector')}: </span>
                            <span style="color:#d1d4dc;font-size:13px;">{raw_sector}</span>
                        </div>
                        """, unsafe_allow_html=True)

                    else:
                        st.info(tr("sector_no_etf") if raw_sector else "Sector information not available for this ticker.")

                    st.markdown("---")

                    # ── SECTION B: NEWS FEED ──────────────────────────────────────────
                    st.subheader(tr("news_feed"))
                    try:
                        ticker_obj = yf.Ticker(ticker_input)
                        news_list = ticker_obj.news
                    except Exception:
                        news_list = []

                    if news_list and isinstance(news_list, list):
                        for item in news_list[:6]:
                            content = item.get("content", {})
                            if content:
                                title = content.get("title", "")
                                provider = content.get("provider", {})
                                publisher = provider.get("displayName", "")
                                canonical_url = content.get("canonicalUrl", {})
                                link = canonical_url.get("url", "")
                                pub_time = content.get("pubDate", "")
                            else:
                                title = item.get("title", "")
                                publisher = item.get("publisher", "")
                                link = item.get("link", "")
                                pub_time = item.get("providerPublishTime", "")

                            try:
                                if isinstance(pub_time, (int, float)):
                                    date_str = pd.to_datetime(pub_time, unit='s').strftime('%Y-%m-%d %H:%M')
                                else:
                                    date_str = pd.to_datetime(pub_time).strftime('%Y-%m-%d %H:%M')
                            except Exception:
                                date_str = str(pub_time)

                            if st.session_state.language == "he":
                                title = translate_text(title)
                                publisher = translate_text(publisher)

                            st.markdown(f"#### {title}")
                            st.write(tr("published_by").format(publisher=publisher, date=date_str))
                            st.markdown(f"[**{tr('read_article')}**]({link})")
                            st.markdown("---")
                    else:
                        st.info(tr("no_news_available"))


                # ==========================================
                # TAB 7: DIVIDEND HISTORY
                # ==========================================
                with tab7:
                    st.subheader(get_label("Dividend History & Yield Analysis"))
                    
                    try:
                        ticker_obj = yf.Ticker(ticker_input)
                        divs = ticker_obj.dividends
                    except Exception:
                        divs = None
                    
                    if divs is not None and not divs.empty:
                        divs.index = pd.to_datetime(divs.index).tz_localize(None)
                        div_annual = divs.groupby(divs.index.year).sum()
                        
                        div_yield_val = info.get('dividendYield')
                        div_rate_val = info.get('dividendRate')
                        payout_ratio_val = info.get('payoutRatio')
                        avg_5y_yield = info.get('fiveYearAvgDividendYield')
                        
                        dy_str = f"{div_yield_val * 100:.2f}%" if (div_yield_val and not pd.isna(div_yield_val)) else "N/A"
                        dr_str = f"${div_rate_val:.2f}" if (div_rate_val and not pd.isna(div_rate_val)) else "N/A"
                        pr_str = f"{payout_ratio_val * 100:.2f}%" if (payout_ratio_val and not pd.isna(payout_ratio_val)) else "N/A"
                        ay_str = f"{avg_5y_yield:.2f}%" if (avg_5y_yield and not pd.isna(avg_5y_yield)) else "N/A"
                        
                        col_div1, col_div2, col_div3, col_div4 = st.columns(4)
                        col_div1.metric(get_label("Dividend Yield"), dy_str)
                        col_div2.metric(get_label("Annual Dividend Rate"), dr_str)
                        col_div3.metric(get_label("Payout Ratio"), pr_str)
                        col_div4.metric(get_label("5-Year Average Yield"), ay_str)
                        
                        st.markdown("---")
                        fig_div = go.Figure()
                        fig_div.add_trace(go.Bar(
                            x=div_annual.index,
                            y=div_annual.values,
                            name=get_label("Annual Dividend"),
                            marker_color='#10B981',
                            opacity=0.85
                        ))
                        
                        if len(div_annual) >= 2:
                            div_growth = div_annual.pct_change() * 100
                            fig_div.add_trace(go.Scatter(
                                x=div_growth.index,
                                y=div_growth.values,
                                name=get_label("YoY Growth (%)"),
                                yaxis="y2",
                                line=dict(color='#EF4444', width=2.5, shape='spline'),
                                mode='lines+markers'
                            ))
                        
                        fig_div.update_layout(
                            title=f"<b>{ticker_input} - {get_label('Annual Dividend History & Growth')}</b>",
                            xaxis_title=tr("year"),
                            yaxis_title=get_label("Dividends Paid (USD)"),
                            yaxis2=dict(
                                title=tr("percentage"),
                                overlaying="y",
                                side="right",
                                ticksuffix="%"
                            ),
                            margin=dict(t=50, b=20, l=40, r=40),
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                        )
                        st.plotly_chart(fig_div, use_container_width=True)
                        
                        with st.expander(get_label("View Dividend Payments Table")):
                            div_table = pd.DataFrame({
                                get_label("Year"): div_annual.index,
                                get_label("Dividends (USD)"): [f"${val:.3f}" for val in div_annual.values]
                            }).sort_values(by=get_label("Year"), ascending=False)
                            st.table(div_table)
                    else:
                        st.info(get_label("This company does not currently pay dividends."))

                # ==========================================
                # TAB 8: INSIDER & OWNERSHIP
                # ==========================================
                with tab8:
                    st.subheader(tr("insider_trading_title"))
                    
                    try:
                        ticker_obj = yf.Ticker(ticker_input)
                        major_holders = ticker_obj.major_holders
                        insider_trans = ticker_obj.insider_transactions
                    except Exception:
                        major_holders = None
                        insider_trans = None
                    
                    # 1. Shareholder Ownership Breakdown
                    st.write(f"### {tr('major_holders_title')}")
                    if major_holders is not None and not major_holders.empty:
                        holders_dict = {}
                        if 'Breakdown' in major_holders.columns and 'Value' in major_holders.columns:
                            for idx, row in major_holders.iterrows():
                                holders_dict[row['Breakdown']] = row['Value']
                        else:
                            for idx, val in major_holders.iloc[:, 0].items():
                                holders_dict[idx] = val
                        
                        insiders_held_pct = holders_dict.get('insidersPercentHeld', 0.0)
                        inst_held_pct = holders_dict.get('institutionsPercentHeld', 0.0)
                        inst_float_pct = holders_dict.get('institutionsFloatPercentHeld', 0.0)
                        inst_count = holders_dict.get('institutionsCount', 0.0)
                        
                        insiders_pct = insiders_held_pct * 100.0 if insiders_held_pct <= 1.0 else insiders_held_pct
                        inst_pct = inst_held_pct * 100.0 if inst_held_pct <= 1.0 else inst_held_pct
                        
                        retail_pct = max(0.0, 100.0 - (insiders_pct + inst_pct))
                        
                        insiders_pct_str = f"{insiders_pct:.2f}%"
                        inst_pct_str = f"{inst_pct:.2f}%"
                        inst_float_str = f"{inst_float_pct * 100.0 if inst_float_pct <= 1.0 else inst_float_pct:.2f}%"
                        inst_count_str = f"{int(inst_count):,}" if inst_count > 0 else tr("na")
                        
                        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                        col_m1.metric(tr("insiders_held"), insiders_pct_str)
                        col_m2.metric(tr("institutions_held"), inst_pct_str)
                        col_m3.metric(tr("institutions_float"), inst_float_str)
                        col_m4.metric(tr("num_institutions"), inst_count_str)
                        
                        labels = [tr("insiders_held"), tr("institutions_held"), tr("retail_other")]
                        values = [insiders_pct, inst_pct, retail_pct]
                        colors = ['#EF4444', '#3B82F6', '#10B981']
                        
                        fig_ownership = go.Figure(data=[go.Pie(
                            labels=labels, 
                            values=values, 
                            hole=.4,
                            marker=dict(colors=colors)
                        )])
                        fig_ownership.update_layout(
                            title=f"<b>{ticker_input} - {tr('major_holders_title')}</b>",
                            margin=dict(t=50, b=20, l=40, r=40),
                            legend=dict(orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5)
                        )
                        st.plotly_chart(fig_ownership, use_container_width=True)
                    else:
                        st.info(tr("no_major_holders_data"))
                        
                    st.markdown("---")
                    
                    # 2. Recent Insider Transactions
                    st.write(f"### {tr('insider_transactions_title')}")
                    if insider_trans is not None and not insider_trans.empty:
                        it_slice = insider_trans.head(20).copy()
                        
                        formatted_rows = []
                        for idx, row in it_slice.iterrows():
                            d_val = row.get('Start Date')
                            if isinstance(d_val, pd.Timestamp):
                                date_str = d_val.strftime('%Y-%m-%d')
                            else:
                                date_str = str(d_val)
                                
                            insider_name = row.get('Insider', 'N/A')
                            
                            pos = row.get('Position', 'N/A')
                            pos_translated = translate_text(pos) if st.session_state.language == "he" else pos
                            
                            shares = row.get('Shares', 0)
                            shares_str = f"{shares:,}"
                            
                            val = row.get('Value', 0)
                            val_str = f"${val:,}" if val > 0 else tr("na")
                            
                            details = row.get('Text', '')
                            details_translated = translate_text(details) if st.session_state.language == "he" else details
                            
                            own = row.get('Ownership', 'D')
                            own_translated = tr("direct") if own == 'D' else (tr("indirect") if own == 'I' else own)
                            
                            formatted_rows.append({
                                tr("date_label"): date_str,
                                tr("insider_column"): insider_name,
                                tr("position_column"): pos_translated,
                                tr("shares_column"): shares_str,
                                tr("value_column"): val_str,
                                tr("ownership_type_column"): own_translated,
                                tr("details_column"): details_translated
                            })
                        
                        df_formatted = pd.DataFrame(formatted_rows)
                        st.dataframe(df_formatted, use_container_width=True)
                    else:
                        st.info(tr("no_insider_data"))

                # ==========================================
                # TAB 9: FINANCIAL PROJECTIONS
                # ==========================================
                with tab9:
                    render_financial_forecasting_tab(df_fin_a)
                    render_manual_valuation_calculator(info, df_fin_a, ticker_input)

            else:
                st.error(tr("error_failed_retrieve_data"))


# ==========================================
# PAGE 3: COMPARE STOCKS
# ==========================================
elif st.session_state.page_selector == "Compare":
    st.title(tr("stock_comparison_page"))
    
    primary_ticker = st.session_state.selected_ticker
    
    col_input1, col_input2 = st.columns(2)
    t1 = col_input1.text_input(tr("ticker_input_placeholder") + " 1", primary_ticker).upper().strip()
    t2 = col_input2.text_input(tr("enter_ticker_compare").format(primary=primary_ticker), "").upper().strip()
    
    if t1 and t2:
        with st.spinner(tr("pulling_data").format(ticker=f"{t1} & {t2}")):
            df_fin1, df_bs1, df_cf1, _, _, _, history1, info1 = fetch_financial_data(t1)
            df_fin2, df_bs2, df_cf2, _, _, _, history2, info2 = fetch_financial_data(t2)
            
        if info1 and info2 and history1 is not None and not history1.empty and history2 is not None and not history2.empty:
            st.markdown(f"### {tr('comparison_summary').format(ticker1=t1, ticker2=t2)}")
            
            col_card1, col_card2 = st.columns(2)

            with col_card1:
                name1 = info1.get('longName', t1)
                sec1 = info1.get('sector', 'N/A')
                ind1 = info1.get('industry', 'N/A')
                if st.session_state.language == "he":
                    sec1 = translate_text(sec1)
                    ind1 = translate_text(ind1)
                st.subheader(f"{name1} ({t1})")
                st.write(f"**{tr('sector')}:** {sec1}")
                st.write(f"**{tr('industry')}:** {ind1}")
                
            with col_card2:
                name2 = info2.get('longName', t2)
                sec2 = info2.get('sector', 'N/A')
                ind2 = info2.get('industry', 'N/A')
                if st.session_state.language == "he":
                    sec2 = translate_text(sec2)
                    ind2 = translate_text(ind2)
                st.subheader(f"{name2} ({t2})")
                st.write(f"**{tr('sector')}:** {sec2}")
                st.write(f"**{tr('industry')}:** {ind2}")
            
            metrics_data = []
            
            def format_val(val, fmt_type, info_dict=None):
                if val is None or pd.isna(val) or val == 'N/A':
                    return 'N/A'
                if fmt_type == "pct":
                    return f"{val * 100:.2f}%" if abs(val) <= 1.0 else f"{val:.2f}%"
                elif fmt_type == "x":
                    return f"{val:.2f}x"
                elif fmt_type == "currency":
                    symbol = "$"
                    if info_dict:
                        currency = info_dict.get("currency", "USD")
                        symbol = "₪" if currency in ["ILA", "ILS"] else ("£" if currency in ["GBp", "GBP"] else ("€" if currency == "EUR" else "$"))
                    return f"{symbol}{val:.2f}"
                return str(val)

            def add_comparison_row(label_en, val1, val2, fmt_type):
                v1_str = format_val(val1, fmt_type, info1)
                v2_str = format_val(val2, fmt_type, info2)
                metrics_data.append({
                    tr("metric_column"): get_label(label_en),
                    t1: v1_str,
                    t2: v2_str
                })

            add_comparison_row("Current Price", info1.get('currentPrice'), info2.get('currentPrice'), "currency")
            
            mc1 = info1.get('marketCap')
            mc1 = (mc1 / 1e9) if mc1 else None
            mc2 = info2.get('marketCap')
            mc2 = (mc2 / 1e9) if mc2 else None
            add_comparison_row("Market Cap (Billion USD)", mc1, mc2, "x")
            
            add_comparison_row("P/E Ratio", info1.get('trailingPE'), info2.get('trailingPE'), "x")
            add_comparison_row("P/S Ratio", info1.get('priceToSalesTrailing12Months'), info2.get('priceToSalesTrailing12Months'), "x")
            add_comparison_row("Price/Book Ratio", info1.get('priceToBook'), info2.get('priceToBook'), "x")
            add_comparison_row("PEG Ratio", info1.get('pegRatio'), info2.get('pegRatio'), "x")
            
            add_comparison_row("Current Ratio", info1.get('currentRatio'), info2.get('currentRatio'), "x")
            
            de1 = info1.get('debtToEquity')
            de1 = (de1 / 100.0) if de1 and de1 > 5.0 else de1
            de2 = info2.get('debtToEquity')
            de2 = (de2 / 100.0) if de2 and de2 > 5.0 else de2
            add_comparison_row("Debt to Equity Ratio", de1, de2, "x")
            
            add_comparison_row("Gross Margin", info1.get('grossMargins'), info2.get('grossMargins'), "pct")
            add_comparison_row("Operating Margin", info1.get('operatingMargins'), info2.get('operatingMargins'), "pct")
            add_comparison_row("Return on Equity (ROE)", info1.get('returnOnEquity'), info2.get('returnOnEquity'), "pct")
            add_comparison_row("Return on Assets (ROA)", info1.get('returnOnAssets'), info2.get('returnOnAssets'), "pct")
            
            st.markdown("---")
            st.table(pd.DataFrame(metrics_data))
            
            st.markdown("---")
            st.subheader(tr("relative_performance_1y"))
            
            hist1 = history1.tail(252).copy()
            hist2 = history2.tail(252).copy()
            
            if not hist1.empty and not hist2.empty:
                hist1['Normalized'] = (hist1['Close'] / hist1['Close'].iloc[0] - 1) * 100
                hist2['Normalized'] = (hist2['Close'] / hist2['Close'].iloc[0] - 1) * 100
                
                fig_comp = go.Figure()
                fig_comp.add_trace(go.Scatter(x=hist1.index, y=hist1['Normalized'], name=t1, line=dict(color='#3182CE', width=2.5)))
                fig_comp.add_trace(go.Scatter(x=hist2.index, y=hist2['Normalized'], name=t2, line=dict(color='#DD6B20', width=2.5)))
                
                fig_comp.update_layout(
                    xaxis_title=tr("date_label"),
                    yaxis_title=tr("percentage"),
                    hovermode="x unified",
                    margin=dict(t=30, b=20, l=40, r=40),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.plotly_chart(fig_comp, use_container_width=True)

            # --- Financial Statement Charts Comparison ---
            st.markdown("---")
            st.subheader(get_label("Financial Statements Comparison"))

            # 1. Revenue Comparison
            st.write(f"##### {get_label('Annual Revenue')}")
            rev_col1 = 'Total Revenue' if (df_fin1 is not None and not df_fin1.empty and 'Total Revenue' in df_fin1.columns) else (
                'Operating Revenue' if (df_fin1 is not None and not df_fin1.empty and 'Operating Revenue' in df_fin1.columns) else None)
            rev_col2 = 'Total Revenue' if (df_fin2 is not None and not df_fin2.empty and 'Total Revenue' in df_fin2.columns) else (
                'Operating Revenue' if (df_fin2 is not None and not df_fin2.empty and 'Operating Revenue' in df_fin2.columns) else None)
            
            fig_rev = go.Figure()
            if rev_col1 and not df_fin1[rev_col1].dropna().empty:
                s1 = df_fin1[rev_col1] / 1e9
                fig_rev.add_trace(go.Bar(x=s1.index, y=s1, name=f"{t1} - {tr('revenue')}", marker_color='#3182CE'))
            if rev_col2 and not df_fin2[rev_col2].dropna().empty:
                s2 = df_fin2[rev_col2] / 1e9
                fig_rev.add_trace(go.Bar(x=s2.index, y=s2, name=f"{t2} - {tr('revenue')}", marker_color='#DD6B20'))
            fig_rev.update_layout(
                barmode='group',
                yaxis_title=tr("billions_usd"),
                xaxis=dict(type='category'),
                margin=dict(t=10, b=20, l=40, r=40),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_rev, use_container_width=True)

            # 2. Net Income Comparison
            st.write(f"##### {get_label('Annual Net Income')}")
            ni_col1 = 'Net Income' if (df_fin1 is not None and not df_fin1.empty and 'Net Income' in df_fin1.columns) else None
            ni_col2 = 'Net Income' if (df_fin2 is not None and not df_fin2.empty and 'Net Income' in df_fin2.columns) else None
            
            fig_ni = go.Figure()
            if ni_col1 and not df_fin1[ni_col1].dropna().empty:
                s1 = df_fin1[ni_col1] / 1e9
                fig_ni.add_trace(go.Bar(x=s1.index, y=s1, name=f"{t1} - {tr('net_income_bottom_line')}", marker_color='#3182CE'))
            if ni_col2 and not df_fin2[ni_col2].dropna().empty:
                s2 = df_fin2[ni_col2] / 1e9
                fig_ni.add_trace(go.Bar(x=s2.index, y=s2, name=f"{t2} - {tr('net_income_bottom_line')}", marker_color='#DD6B20'))
            fig_ni.update_layout(
                barmode='group',
                yaxis_title=tr("billions_usd"),
                xaxis=dict(type='category'),
                margin=dict(t=10, b=20, l=40, r=40),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_ni, use_container_width=True)

            # 3. Free Cash Flow Comparison
            st.write(f"##### {get_label('Annual Free Cash Flow (FCF)')}")
            fcf_col1 = 'Free Cash Flow' if (df_cf1 is not None and not df_cf1.empty and 'Free Cash Flow' in df_cf1.columns) else None
            fcf_col2 = 'Free Cash Flow' if (df_cf2 is not None and not df_cf2.empty and 'Free Cash Flow' in df_cf2.columns) else None
            
            fig_fcf = go.Figure()
            if fcf_col1 and not df_cf1[fcf_col1].dropna().empty:
                s1 = df_cf1[fcf_col1] / 1e9
                fig_fcf.add_trace(go.Bar(x=s1.index, y=s1, name=f"{t1} - {tr('free_cash_flow')}", marker_color='#3182CE'))
            if fcf_col2 and not df_cf2[fcf_col2].dropna().empty:
                s2 = df_cf2[fcf_col2] / 1e9
                fig_fcf.add_trace(go.Bar(x=s2.index, y=s2, name=f"{t2} - {tr('free_cash_flow')}", marker_color='#DD6B20'))
            fig_fcf.update_layout(
                barmode='group',
                yaxis_title=tr("billions_usd"),
                xaxis=dict(type='category'),
                margin=dict(t=10, b=20, l=40, r=40),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_fcf, use_container_width=True)

            # 4. Profit Margin Comparison
            st.write(f"##### {get_label('Profit Margin Comparison')}")
            fig_margin = go.Figure()
            if rev_col1 and ni_col1 and not df_fin1[rev_col1].dropna().empty and not df_fin1[ni_col1].dropna().empty:
                m1 = (df_fin1[ni_col1] / df_fin1[rev_col1]) * 100
                fig_margin.add_trace(go.Scatter(x=m1.index, y=m1, name=f"{t1} - {tr('profit_margin')}", line=dict(color='#3182CE', width=2.5)))
            if rev_col2 and ni_col2 and not df_fin2[rev_col2].dropna().empty and not df_fin2[ni_col2].dropna().empty:
                m2 = (df_fin2[ni_col2] / df_fin2[rev_col2]) * 100
                fig_margin.add_trace(go.Scatter(x=m2.index, y=m2, name=f"{t2} - {tr('profit_margin')}", line=dict(color='#DD6B20', width=2.5)))
            fig_margin.update_layout(
                yaxis_title=tr("percentage"),
                xaxis=dict(type='category'),
                margin=dict(t=10, b=20, l=40, r=40),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_margin, use_container_width=True)
        else:
            st.error(tr("error_failed_retrieve_data"))


# ==========================================
# PAGE 2: WATCHLIST
# ==========================================
elif st.session_state.page_selector == "Watchlist":
    st.title(tr("my_stock_watchlist"))

    # Callback function to handle navigation safely
    def navigate_to_dashboard(target_ticker: str):
        st.session_state.selected_ticker = target_ticker
        st.session_state.page_selector = "Dashboard"

    # Multiple watchlist selection and deletion
    col_sel, col_del = st.columns([3, 2])
    watchlist_options = list(st.session_state.watchlists.keys())
    try:
        active_idx = watchlist_options.index(st.session_state.active_watchlist)
    except ValueError:
        active_idx = 0

    selected_wl = col_sel.selectbox(
        tr("select_watchlist"),
        watchlist_options,
        index=active_idx,
        key="active_watchlist_selector"
    )

    if selected_wl != st.session_state.active_watchlist:
        st.session_state.active_watchlist = selected_wl
        st.session_state.watchlist = st.session_state.watchlists[selected_wl]
        st.rerun()

    # Align delete button layout offset depending on language to look professional
    col_del.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
    if col_del.button(tr("delete_watchlist_btn"), key="btn_del_wl", use_container_width=True):
        if len(st.session_state.watchlists) > 1:
            del st.session_state.watchlists[st.session_state.active_watchlist]
            save_watchlists(st.session_state.watchlists)
            st.session_state.active_watchlist = list(st.session_state.watchlists.keys())[0]
            st.session_state.watchlist = st.session_state.watchlists[st.session_state.active_watchlist]
            st.success(tr("watchlist_deleted"))
            st.rerun()
        else:
            st.error(tr("cannot_delete_last_watchlist"))

    # Expanders for Watchlist Creation and Section Creation
    col_exp1, col_exp2 = st.columns(2)
    
    with col_exp1.expander("➕ " + tr("create_watchlist")):
        with st.form(key="create_watchlist_form", clear_on_submit=True):
            new_wl_name = st.text_input(tr("enter_watchlist_name")).strip()
            submit_wl = st.form_submit_button(label=tr("add_watchlist_btn"))
            if submit_wl and new_wl_name:
                if new_wl_name not in st.session_state.watchlists:
                    # New watchlist starts with a default "General" section
                    st.session_state.watchlists[new_wl_name] = [{"title": "General", "tickers": []}]
                    save_watchlists(st.session_state.watchlists)
                    st.session_state.active_watchlist = new_wl_name
                    st.session_state.watchlist = st.session_state.watchlists[new_wl_name]
                    st.success(tr("watchlist_created").format(name=new_wl_name))
                    st.rerun()
                else:
                    st.warning(tr("watchlist_exists"))

    with col_exp2.expander("📁 " + tr("create_section")):
        with st.form(key="create_section_form", clear_on_submit=True):
            new_sec_name = st.text_input(tr("enter_section_name")).strip()
            submit_sec = st.form_submit_button(label=tr("add_section_btn"))
            if submit_sec and new_sec_name:
                # Add section to active watchlist sections
                existing_titles = [s["title"] for s in st.session_state.watchlist]
                if new_sec_name not in existing_titles:
                    st.session_state.watchlist.append({"title": new_sec_name, "tickers": []})
                    st.session_state.last_selected_section = new_sec_name
                    save_watchlists(st.session_state.watchlists)
                    st.success(tr("section_created").format(name=new_sec_name))
                    st.rerun()
                else:
                    st.warning(tr("section_exists"))

    # Drag and Drop Reordering & Moving Tickers between Sections
    if st.session_state.watchlist:
        with st.expander(tr("reorder_drag_drop"), expanded=False):
            from streamlit_sortables import sort_items
            sortable_data = [
                {"header": section["title"], "items": section["tickers"]}
                for section in st.session_state.watchlist
            ]
            sort_key = f"sort_wl_{st.session_state.active_watchlist}"
            sorted_data = sort_items(sortable_data, multi_containers=True, key=sort_key)
            
            data_changed = False
            if sorted_data:
                for idx, sec in enumerate(st.session_state.watchlist):
                    if idx < len(sorted_data):
                        new_title = sorted_data[idx].get("header", sec["title"])
                        new_tickers = sorted_data[idx].get("items", sec["tickers"])
                        new_tickers = [str(t).upper().strip() for t in new_tickers if t]
                        
                        if sec["title"] != new_title or sec["tickers"] != new_tickers:
                            sec["title"] = new_title
                            sec["tickers"] = new_tickers
                            data_changed = True
            
            if data_changed:
                save_watchlists(st.session_state.watchlists)
                st.rerun()

    # Add ticker to a specific section of the active watchlist
    with st.form(key="add_ticker_form", clear_on_submit=True):
        col_t1, col_t2 = st.columns(2)
        new_ticker = col_t1.text_input(tr("enter_ticker_to_add")).upper().strip()
        
        # Select target section
        section_options = [s["title"] for s in st.session_state.watchlist] if st.session_state.watchlist else ["General"]
        
        # Get active index for the section selectbox to keep the user on the same section
        default_sec_idx = 0
        if "last_selected_section" in st.session_state and st.session_state.last_selected_section in section_options:
            default_sec_idx = section_options.index(st.session_state.last_selected_section)
            
        target_section_title = col_t2.selectbox(
            tr("select_section_to_add"), 
            section_options,
            index=default_sec_idx
        )
        
        submit_button = st.form_submit_button(label=tr("add_to_watchlist"))

        if submit_button and new_ticker and target_section_title:
            # If the watchlist has no sections (should not happen, but safe fallback)
            if not st.session_state.watchlist:
                st.session_state.watchlist.append({"title": "General", "tickers": []})
            
            # Find the section and append the ticker
            for section in st.session_state.watchlist:
                if section["title"] == target_section_title:
                    # Check if ticker already exists in any section of this watchlist
                    ticker_exists = any(new_ticker in s["tickers"] for s in st.session_state.watchlist)
                    if not ticker_exists:
                        section["tickers"].append(new_ticker)
                        st.session_state.last_selected_section = target_section_title
                        save_watchlists(st.session_state.watchlists)
                        st.success(tr("ticker_added_success").format(ticker=new_ticker))
                        st.rerun()
                    else:
                        st.warning(tr("ticker_already_watchlist"))

    # Fetch live price data once per ticker (across all sections) to optimize loading speed
    all_tickers = []
    for section in st.session_state.watchlist:
        all_tickers.extend(section["tickers"])
    all_tickers = list(dict.fromkeys(all_tickers)) # Deduplicate

    price_cache = {}
    if all_tickers:
        with st.spinner(tr("pulling_data").format(ticker="watchlist")):
            for ticker in all_tickers:
                price, change, symbol = get_live_price_info(ticker)
                price_cache[ticker] = {"Price": price, "Change (%)": change, "Symbol": symbol}

    # Render overall watchlist performance comparison chart
    valid_wl_data = []
    for ticker, info in price_cache.items():
        if info["Price"] is not None:
            valid_wl_data.append({"Ticker": ticker, "Price": info["Price"], "Change (%)": info["Change (%)"]})

    if valid_wl_data:
        df_wl = pd.DataFrame(valid_wl_data)
        colors = ['#10B981' if c >= 0 else '#EF4444' for c in df_wl["Change (%)"]]
        
        fig_wl = go.Figure()
        fig_wl.add_trace(go.Bar(
            x=df_wl["Ticker"],
            y=df_wl["Change (%)"],
            marker_color=colors,
            text=df_wl["Change (%)"].round(2).astype(str) + '%',
            textposition='auto',
            opacity=0.85
        ))
        
        fig_wl.update_layout(
            title=f"<b>{tr('watchlist_performance')}</b>",
            yaxis_title=tr("percentage"),
            xaxis=dict(type='category'),
            margin=dict(t=50, b=20, l=40, r=40),
            height=320
        )
        st.plotly_chart(fig_wl, use_container_width=True)
        st.markdown("---")

    # Render sections and tickers
    if st.session_state.watchlist:
        for idx, section in enumerate(st.session_state.watchlist):
            col_sec_title, col_sec_del = st.columns([5, 1])
            col_sec_title.markdown(f"#### 📁 {section['title']}")
            
            # Allow deleting section
            if col_sec_del.button("🗑️ " + tr("delete_section"), key=f"del_sec_{section['title']}_{idx}", use_container_width=True):
                st.session_state.watchlist.remove(section)
                save_watchlists(st.session_state.watchlists)
                st.success(tr("section_deleted"))
                st.rerun()

            if section["tickers"]:
                for ticker in section["tickers"]:
                    cache = price_cache.get(ticker, {"Price": None, "Change (%)": None, "Symbol": "$"})
                    price = cache["Price"]
                    change = cache["Change (%)"]
                    symbol = cache.get("Symbol", "$")

                    if price is not None:
                        company_name = get_company_name(ticker)
                        change_color = "#089981" if change >= 0 else "#f23645"
                        change_sign = "+" if change >= 0 else ""

                        align_text = "right" if st.session_state.language == "he" else "left"
                        align_price = "left" if st.session_state.language == "he" else "right"
                        flex_dir = "row-reverse" if st.session_state.language == "he" else "row"

                        col_card, col_btn, col_remove = st.columns([6, 2, 1])

                        card_html = f"""
                        <div style="
                            background-color: #1c2030;
                            border: 1px solid #2a2e39;
                            border-radius: 8px;
                            padding: 10px 15px;
                            display: flex;
                            flex-direction: {flex_dir};
                            justify-content: space-between;
                            align-items: center;
                            font-family: 'Outfit', 'Rubik', sans-serif;
                            height: 50px;
                        ">
                            <div style="display: flex; flex-direction: column; text-align: {align_text};">
                                <span style="font-size: 15px; font-weight: bold; color: #ffffff;">{ticker}</span>
                                <span style="font-size: 10px; color: #848e9c; margin-top: 1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 180px;">{company_name}</span>
                            </div>
                            <div style="display: flex; flex-direction: {flex_dir}; align-items: center; gap: 15px; text-align: {align_price};">
                                <span style="font-size: 14px; font-weight: bold; color: #ffffff;">{symbol}{price:.2f}</span>
                                <span style="
                                    background-color: {change_color}20;
                                    color: {change_color};
                                    border: 1px solid {change_color}40;
                                    padding: 3px 8px;
                                    border-radius: 5px;
                                    font-size: 12px;
                                    font-weight: 600;
                                    min-width: 60px;
                                    text-align: center;
                                    display: inline-block;
                                ">
                                    {change_sign}{change:.2f}%
                                </span>
                            </div>
                        </div>
                        """
                        col_card.markdown(card_html, unsafe_allow_html=True)

                        col_btn.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
                        col_btn.button(
                            tr("analyze_ticker").format(ticker=ticker),
                            key=f"btn_{ticker}_{section['title']}_{idx}",
                            on_click=navigate_to_dashboard,
                            args=(ticker,),
                            use_container_width=True
                        )

                        col_remove.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
                        if col_remove.button("🗑️", key=f"remove_{ticker}_{section['title']}_{idx}", help=tr("remove_from_watchlist"), use_container_width=True):
                            section["tickers"].remove(ticker)
                            save_watchlists(st.session_state.watchlists)
                            st.rerun()

                        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
                    else:
                        st.error(tr("could_not_load_live_data").format(ticker=ticker))
            else:
                st.info("This section is currently empty. Add tickers to it above!")
            st.markdown("---")
    else:
        st.info("Watchlist is currently empty. Add a section above first!")


# ==========================================
# PAGE 3: PORTFOLIO
# ==========================================
elif st.session_state.page_selector == "Portfolio":
    st.title(tr("portfolio"))

    if "portfolio_dict" not in st.session_state:
        st.session_state.portfolio_dict = load_portfolio()
        
    portfolio_options = list(st.session_state.portfolio_dict.keys())
    if "active_portfolio" not in st.session_state or st.session_state.active_portfolio not in portfolio_options:
        st.session_state.active_portfolio = portfolio_options[0] if portfolio_options else "Discount"
        
    if st.session_state.active_portfolio not in st.session_state.portfolio_dict:
        st.session_state.portfolio_dict[st.session_state.active_portfolio] = []
        
    portfolio_data = st.session_state.portfolio_dict[st.session_state.active_portfolio]
    
    # Sort: open positions first (remaining_qty > 0), then by largest current total value
    def get_portfolio_sort_key(item_stock):
        metrics = calculate_stock_metrics(item_stock)
        is_open = 1 if metrics["remaining_qty"] > 0 else 0
        total_val = metrics["current_total_value"]
        return (is_open, total_val)
        
    portfolio_data.sort(key=get_portfolio_sort_key, reverse=True)
    
    if "display_currency" not in st.session_state:
        st.session_state.display_currency = "USD"
        
    if "usd_rate" not in st.session_state:
        with st.spinner("Fetching live exchange rate..."):
            st.session_state.usd_rate = get_usd_ils_rate()

    # Display dynamic toast notifications if set
    if "portfolio_toast" in st.session_state and st.session_state.portfolio_toast:
        st.toast(st.session_state.portfolio_toast, icon="✅")
        st.session_state.portfolio_toast = None

    # Portfolio Selection & Creation UI
    col_sel, col_del = st.columns([3, 2])
    selected_port = col_sel.selectbox(
        tr("portfolio_select"),
        portfolio_options,
        index=portfolio_options.index(st.session_state.active_portfolio) if st.session_state.active_portfolio in portfolio_options else 0,
        key="active_portfolio_selector"
    )
    if selected_port != st.session_state.active_portfolio:
        st.session_state.active_portfolio = selected_port
        st.rerun()
        
    col_del.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
    if col_del.button("🗑️ " + tr("portfolio_delete_btn"), key="btn_del_port", use_container_width=True):
        if len(portfolio_options) > 1:
            del st.session_state.portfolio_dict[st.session_state.active_portfolio]
            save_portfolio(st.session_state.portfolio_dict)
            st.session_state.active_portfolio = list(st.session_state.portfolio_dict.keys())[0]
            st.session_state.portfolio_toast = tr("portfolio_deleted")
            st.rerun()
        else:
            st.error(tr("cannot_delete_last_portfolio"))

    with st.expander("📁 " + tr("portfolio_create")):
        with st.form(key="create_portfolio_form", clear_on_submit=True):
            new_port_name = st.text_input(tr("portfolio_enter_name")).strip()
            submit_port = st.form_submit_button(label=tr("portfolio_create_btn"))
            if submit_port and new_port_name:
                if new_port_name not in st.session_state.portfolio_dict:
                    st.session_state.portfolio_dict[new_port_name] = [
                        {
                            "id": f"{pd.Timestamp.now().timestamp()}_init",
                            "symbol": "TICKER",
                            "currency": "USD",
                            "buys": [{"p": 0.0, "q": 0.0}],
                            "sells": [],
                            "currentPrice": 0.0,
                            "prevClosePrice": 0.0,
                            "locked": False
                        }
                    ]
                    save_portfolio(st.session_state.portfolio_dict)
                    st.session_state.active_portfolio = new_port_name
                    st.session_state.portfolio_toast = f"Portfolio '{new_port_name}' created!"
                    st.rerun()
                else:
                    st.warning(tr("portfolio_exists"))

    # Header controls: Rate and Display Currency
    col_rate, col_curr = st.columns([1, 1])
    
    with col_rate:
        usd_rate_val = st.number_input(
            tr("portfolio_exchange_rate"),
            value=st.session_state.usd_rate,
            step=0.01,
            format="%.4f"
        )
        if usd_rate_val != st.session_state.usd_rate:
            st.session_state.usd_rate = usd_rate_val
            st.rerun()

    with col_curr:
        display_curr_options = ["USD", "ILS"]
        selected_display_curr = st.radio(
            tr("select_view"),
            display_curr_options,
            index=display_curr_options.index(st.session_state.display_currency),
            horizontal=True
        )
        if selected_display_curr != st.session_state.display_currency:
            st.session_state.display_currency = selected_display_curr
            st.rerun()

    # Toolbar buttons
    st.markdown("### " + tr("portfolio_actions"))
    col_btn1, col_btn2, col_btn3, col_btn4 = st.columns(4)
    
    with col_btn1:
        if st.button("➕ " + tr("portfolio_add_position"), key="add_stock_pos", use_container_width=True):
            import random
            portfolio_data.append({
                "id": f"{pd.Timestamp.now().timestamp()}_{random.random()}",
                "symbol": "TICKER",
                "currency": "USD",
                "buys": [{"p": 0.0, "q": 0.0}],
                "sells": [],
                "currentPrice": 0.0,
                "prevClosePrice": 0.0,
                "locked": False
            })
            save_portfolio(st.session_state.portfolio_dict)
            st.session_state.portfolio_toast = "Position added successfully!"
            st.rerun()

    with col_btn2:
        if st.button("🔄 " + tr("portfolio_update_prices"), key="update_stock_prices", use_container_width=True):
            updated_count = 0
            with st.spinner(tr("pulling_data").format(ticker="all")):
                for s in portfolio_data:
                    if s.get("symbol") and not s.get("locked"):
                        live_price, prev_close = get_portfolio_live_price(s["symbol"], s["currency"])
                        if live_price is not None:
                            s["currentPrice"] = live_price
                            s["prevClosePrice"] = prev_close
                            updated_count += 1
            if updated_count > 0:
                save_portfolio(st.session_state.portfolio_dict)
                st.session_state.portfolio_toast = f"Updated {updated_count} stock prices successfully!"
                st.rerun()

    with col_btn3:
        # Import CSV
        csv_file = st.file_uploader(tr("portfolio_import_csv"), type=["csv"], label_visibility="collapsed")
        if csv_file is not None:
            try:
                imported_stocks = import_portfolio_csv(csv_file.read())
                if imported_stocks:
                    st.session_state.portfolio_dict[st.session_state.active_portfolio] = imported_stocks
                    save_portfolio(st.session_state.portfolio_dict)
                    st.session_state.portfolio_toast = "CSV imported successfully!"
                    st.rerun()
                else:
                    st.error("No valid positions found in CSV.")
            except Exception as ex:
                st.error(f"Error: {ex}")

    with col_btn4:
        # Export CSV
        try:
            csv_bytes = export_portfolio_csv(portfolio_data)
            st.download_button(
                label="📥 " + tr("portfolio_export_csv"),
                data=csv_bytes,
                file_name="portfolio_backup.csv",
                mime="text/csv",
                use_container_width=True
            )
        except Exception as ex:
            st.error(f"Error: {ex}")

    # Calculations
    usd_rate = st.session_state.usd_rate if st.session_state.usd_rate > 0 else 1.0
    total_remaining_cost_usd = 0.0
    total_market_value_usd = 0.0
    total_realized_usd = 0.0
    total_unrealized_usd = 0.0
    total_daily_change_usd = 0.0
    total_prev_market_value_usd = 0.0

    for s in portfolio_data:
        m = calculate_stock_metrics(s)
        factor = 1.0 / usd_rate if s.get("currency") == "ILS" else 1.0
        total_remaining_cost_usd += m["remaining_cost_basis"] * factor
        total_market_value_usd += m["current_total_value"] * factor
        total_realized_usd += m["realized_pl"] * factor
        total_unrealized_usd += m["unrealized_pl"] * factor
        
        # Calculate daily change
        remaining_qty = m["remaining_qty"]
        curr_price = float(s.get("currentPrice", 0.0))
        prev_close = float(s.get("prevClosePrice", curr_price))
        cost_factor = 100.0 if s.get("currency") == "ILS" else 1.0
        
        daily_change_val = (curr_price - prev_close) * remaining_qty / cost_factor
        daily_change_usd = daily_change_val * factor
        total_daily_change_usd += daily_change_usd
        
        prev_val_usd = (prev_close * remaining_qty / cost_factor) * factor
        total_prev_market_value_usd += prev_val_usd

    total_profit_usd = total_realized_usd + total_unrealized_usd
    total_profit_pct = (total_profit_usd / (total_remaining_cost_usd + abs(total_realized_usd))) * 100.0 if (total_remaining_cost_usd + abs(total_realized_usd)) > 0 else 0.0
    open_return_pct = (total_unrealized_usd / total_remaining_cost_usd) * 100.0 if total_remaining_cost_usd > 0 else 0.0
    daily_change_pct = (total_daily_change_usd / total_prev_market_value_usd * 100.0) if total_prev_market_value_usd > 0 else 0.0

    display_factor = usd_rate if st.session_state.display_currency == "ILS" else 1.0
    sym = "₪" if st.session_state.display_currency == "ILS" else "$"

    # Cards layout - Row 1 (4 columns)
    col_card1, col_card2, col_card3, col_card4 = st.columns(4)
    with col_card1:
        st.markdown(render_portfolio_card(tr("portfolio_cost_basis"), f"{sym}{(total_remaining_cost_usd * display_factor):,.2f}", "neutral"), unsafe_allow_html=True)
    with col_card2:
        st.markdown(render_portfolio_card(tr("portfolio_market_value"), f"{sym}{(total_market_value_usd * display_factor):,.2f}", "warning" if total_market_value_usd >= total_remaining_cost_usd else "critical"), unsafe_allow_html=True)
    with col_card3:
        st.markdown(render_portfolio_card(tr("portfolio_realized_pl"), f"{sym}{(total_realized_usd * display_factor):,.2f}", "good" if total_realized_usd >= 0 else "critical"), unsafe_allow_html=True)
    with col_card4:
        st.markdown(render_portfolio_card(tr("portfolio_unrealized_pl"), f"{sym}{(total_unrealized_usd * display_factor):,.2f}", "good" if total_unrealized_usd >= 0 else "critical"), unsafe_allow_html=True)

    # Cards layout - Row 2 (3 columns)
    col_card5, col_card6, col_card7 = st.columns(3)
    with col_card5:
        st.markdown(render_portfolio_card(tr("portfolio_total_return"), f"{total_profit_pct:+.2f}%", "good" if total_profit_usd >= 0 else "critical"), unsafe_allow_html=True)
    with col_card6:
        st.markdown(render_portfolio_card(tr("portfolio_open_return"), f"{open_return_pct:+.2f}%", "good" if total_unrealized_usd >= 0 else "critical"), unsafe_allow_html=True)
    with col_card7:
        daily_change_str = f"{sym}{(total_daily_change_usd * display_factor):+,.2f} ({daily_change_pct:+.2f}%)"
        st.markdown(render_portfolio_card(tr("portfolio_today_change"), daily_change_str, "good" if total_daily_change_usd >= 0 else "critical"), unsafe_allow_html=True)

    # Visualizations section
    if portfolio_data:
        asset_labels = []
        asset_values = []
        for s in portfolio_data:
            m = calculate_stock_metrics(s)
            val_usd = m["current_total_value"] * (1.0 / usd_rate if s.get("currency") == "ILS" else 1.0)
            if val_usd > 0:
                asset_labels.append(s.get("symbol", "N/A"))
                asset_values.append(val_usd * display_factor)
                
        curr_labels = ["USD", "ILS"]
        usd_val = sum(calculate_stock_metrics(s)["current_total_value"] for s in portfolio_data if s.get("currency") == "USD")
        ils_val_in_usd = sum(calculate_stock_metrics(s)["current_total_value"] * (1.0 / usd_rate) for s in portfolio_data if s.get("currency") == "ILS")
        curr_values = [usd_val * display_factor, ils_val_in_usd * display_factor]
        
        pl_labels = []
        pl_values = []
        for s in portfolio_data:
            m = calculate_stock_metrics(s)
            pl_usd = (m["realized_pl"] + m["unrealized_pl"]) * (1.0 / usd_rate if s.get("currency") == "ILS" else 1.0)
            pl_labels.append(s.get("symbol", "N/A"))
            pl_values.append(pl_usd * display_factor)

        # Only show visuals if there is either positive market value or non-zero P&L
        has_assets = any(v > 0 for v in asset_values)
        has_pl = any(v != 0 for v in pl_values)
        
        if has_assets or has_pl:
            st.markdown("---")
            st.markdown(f"### 📊 {tr('portfolio_visual_analysis')}")
            
            if has_assets:
                col_vis1, col_vis2 = st.columns(2)
                import plotly.graph_objects as go
                
                with col_vis1:
                    fig_asset = go.Figure(data=[go.Pie(
                        labels=asset_labels,
                        values=asset_values,
                        hole=0.4,
                        hoverinfo="label+percent+value",
                        textinfo="label+percent",
                        marker=dict(line=dict(color="#1c2030", width=2))
                    )])
                    fig_asset.update_layout(
                        title=dict(text=f"<b>{tr('portfolio_asset_allocation')}</b>", x=0.5, font=dict(size=14, color="#ffffff")),
                        margin=dict(t=40, b=10, l=10, r=10),
                        showlegend=True,
                        height=300
                    )
                    st.plotly_chart(fig_asset, use_container_width=True)
                    
                with col_vis2:
                    filtered_curr_labels = []
                    filtered_curr_values = []
                    for lbl, val in zip(curr_labels, curr_values):
                        if val > 0:
                            filtered_curr_labels.append(lbl)
                            filtered_curr_values.append(val)
                            
                    fig_curr = go.Figure(data=[go.Pie(
                        labels=filtered_curr_labels,
                        values=filtered_curr_values,
                        hole=0.4,
                        hoverinfo="label+percent+value",
                        textinfo="label+percent",
                        marker=dict(colors=["#2962ff", "#089981"], line=dict(color="#1c2030", width=2))
                    )])
                    fig_curr.update_layout(
                        title=dict(text=f"<b>{tr('portfolio_currency_exposure')}</b>", x=0.5, font=dict(size=14, color="#ffffff")),
                        margin=dict(t=40, b=10, l=10, r=10),
                        showlegend=True,
                        height=300
                    )
                    st.plotly_chart(fig_curr, use_container_width=True)
            
            if has_pl:
                import plotly.graph_objects as go
                sorted_pl = sorted(zip(pl_labels, pl_values), key=lambda x: x[1])
                s_labels = [x[0] for x in sorted_pl]
                s_values = [x[1] for x in sorted_pl]
                
                bar_colors = ['#089981' if val >= 0 else '#f23645' for val in s_values]
                
                fig_pl = go.Figure(data=[go.Bar(
                    y=s_labels,
                    x=s_values,
                    orientation='h',
                    marker_color=bar_colors,
                    hoverinfo="y+x",
                    text=[f"{sym}{val:+,.2f}" for val in s_values],
                    textposition='auto'
                )])
                fig_pl.update_layout(
                    title=dict(text=f"<b>{tr('portfolio_pl_breakdown')} ({sym})</b>", x=0.5, font=dict(size=14, color="#ffffff")),
                    margin=dict(t=40, b=20, l=20, r=20),
                    xaxis=dict(gridcolor="#2a2e39"),
                    height=max(180, 120 + len(pl_labels) * 35)
                )
                st.plotly_chart(fig_pl, use_container_width=True)

    # Detailed Table
    st.markdown("---")
    st.markdown("### " + tr("portfolio"))

    if not portfolio_data:
        st.info(tr("portfolio_empty"))
    else:
        align_text = "right" if st.session_state.language == "he" else "left"
        lang_dir = "rtl" if st.session_state.language == "he" else "ltr"
        
        table_html = f"""<div style="overflow-x: auto; font-family: 'Outfit', 'Rubik', sans-serif;" dir="{lang_dir}">
<table style="width: 100%; border-collapse: collapse; text-align: {align_text}; color: #ffffff; background-color: #1c2030; border: 1px solid #2a2e39; border-radius: 8px;">
<thead>
<tr style="border-bottom: 2px solid #2a2e39; background-color: #131722;">
<th style="padding: 12px; border-bottom: 1px solid #2a2e39;">{tr('portfolio_actions')}</th>
<th style="padding: 12px; border-bottom: 1px solid #2a2e39;">{tr('portfolio_currency')} / {tr('ticker_input_placeholder').split()[0]}</th>
<th style="padding: 12px; border-bottom: 1px solid #2a2e39;">{tr('portfolio_average_buy')}</th>
<th style="padding: 12px; border-bottom: 1px solid #2a2e39;">{tr('portfolio_initial_capital')}</th>
<th style="padding: 12px; border-bottom: 1px solid #2a2e39;">{tr('portfolio_remaining_cost')}</th>
<th style="padding: 12px; border-bottom: 1px solid #2a2e39;">{tr('portfolio_market_value')}</th>
<th style="padding: 12px; border-bottom: 1px solid #2a2e39;">{tr('portfolio_market_price')}</th>
<th style="padding: 12px; border-bottom: 1px solid #2a2e39;">{tr('portfolio_realized_pl')}</th>
<th style="padding: 12px; border-bottom: 1px solid #2a2e39;">{tr('portfolio_unrealized_pl')}</th>
</tr>
</thead>
<tbody>"""
        
        for s in portfolio_data:
            m = calculate_stock_metrics(s)
            s_curr_sym = "₪" if s.get("currency") == "ILS" else "$"
            lock_icon = "🔒" if s.get("locked") else "🔓"
            
            raw_buy_p = m["avg_buy_price"]
            curr_mkt_p = s.get("currentPrice", 0.0)
            prev_close_p = s.get("prevClosePrice", curr_mkt_p)
            
            profit_pct = ((curr_mkt_p - raw_buy_p) / raw_buy_p * 100.0) if raw_buy_p > 0 else 0.0
            
            pos_daily_change_val = curr_mkt_p - prev_close_p
            pos_daily_change_pct = ((curr_mkt_p - prev_close_p) / prev_close_p * 100.0) if prev_close_p > 0 else 0.0
            
            realized_color = "#089981" if m["realized_pl"] >= 0 else "#f23645"
            unrealized_color = "#089981" if m["unrealized_pl"] >= 0 else "#f23645"
            pos_daily_change_color = "#089981" if pos_daily_change_val >= 0 else "#f23645"
            pos_daily_change_sign = "+" if pos_daily_change_val >= 0 else ""
            
            initial_cap_str = f"{s_curr_sym}{m['total_initial_capital']:,.2f}"
            remaining_cost_str = f"{s_curr_sym}{m['remaining_cost_basis']:,.2f}"
            curr_val_str = f"{s_curr_sym}{m['current_total_value']:,.2f}"
            
            realized_str = f"{s_curr_sym}{m['realized_pl']:,.2f}"
            unrealized_str = f"{s_curr_sym}{m['unrealized_pl']:,.2f} ({profit_pct:+.2f}%)"
            
            avg_price_display = f"{m['avg_buy_price']:.2f}"
            if s.get("currency") == "ILS":
                avg_price_display += " (אג')"
                mkt_price_display = f"{curr_mkt_p:.2f} (אג')"
                pos_daily_change_val_str = f"{pos_daily_change_sign}{pos_daily_change_val:.2f} (אג')"
            else:
                mkt_price_display = f"{curr_mkt_p:.2f}"
                pos_daily_change_val_str = f"{s_curr_sym}{pos_daily_change_sign}{pos_daily_change_val:.2f}"

            table_html += f"""<tr style="border-bottom: 1px solid #2a2e39; hover: background-color: #242936;">
<td style="padding: 10px;">{lock_icon}</td>
<td style="padding: 10px; font-weight: bold; color: #2962ff;">{s.get('symbol', 'N/A')} <span style="font-size: 10px; color: #848e9c;">({s.get('currency')})</span></td>
<td style="padding: 10px;">{avg_price_display}</td>
<td style="padding: 10px;">{initial_cap_str}</td>
<td style="padding: 10px;">{remaining_cost_str}</td>
<td style="padding: 10px; font-weight: bold;">{curr_val_str}</td>
<td style="padding: 10px;">
    <div>{mkt_price_display}</div>
    <div style="font-size: 10px; color: {pos_daily_change_color}; font-weight: bold;">
        {pos_daily_change_val_str} ({pos_daily_change_pct:+.2f}%)
    </div>
</td>
<td style="padding: 10px; color: {realized_color}; font-weight: bold;">{realized_str}</td>
<td style="padding: 10px; color: {unrealized_color}; font-weight: bold;">{unrealized_str}</td>
</tr>"""
            
        table_html += """</tbody>
</table>
</div>"""
        st.markdown(table_html, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Position Management Section
        mgmt_title = "ניהול פוזיציות ופרטי קניות/מכירות" if st.session_state.language == "he" else "Manage Positions & Buy/Sell Details"
        st.markdown("### " + mgmt_title)
        
        # Helper tip for Israeli stocks suffix and units
        if st.session_state.language == "he":
            st.info("💡 עבור מניות בישראל, יש להשתמש בסיומת .TA (למשל ICL.TA). מחירים עבור מניות אלו מוזנים ומוצגים באגורות, והחישובים הסופיים מוצגים בשקלים (₪).")
        else:
            st.info("💡 For Israeli stocks, use the .TA suffix (e.g. ICL.TA). Prices for these stocks are entered and shown in Agorot, while final calculations are converted to ILS (₪).")

        for index, s in enumerate(portfolio_data):
            symbol_label = s.get("symbol") if s.get("symbol") else f"Position #{index+1}"
            exp_title = f"{symbol_label} ({s.get('currency')})"
            if s.get("locked"):
                exp_title += " 🔒 " + tr("portfolio_locked")
            
            with st.expander(exp_title, expanded=False):
                col_sym, col_cur, col_pr, col_lk, col_del_btn = st.columns([2, 2, 2, 1, 1])
                is_disabled = s.get("locked", False)
                
                with col_sym:
                    new_sym = st.text_input(
                        tr("ticker_input_placeholder").split()[0],
                        value=s.get("symbol", ""),
                        key=f"sym_input_{index}_{s['id']}",
                        disabled=is_disabled
                    ).upper().strip()
                    if new_sym != s.get("symbol"):
                        s["symbol"] = new_sym
                        save_portfolio(st.session_state.portfolio_dict)
                        st.rerun()
                
                with col_cur:
                    cur_opts = ["USD", "ILS"]
                    new_cur = st.selectbox(
                        tr("portfolio_currency"),
                        cur_opts,
                        index=cur_opts.index(s.get("currency", "USD")),
                        key=f"cur_select_{index}_{s['id']}",
                        disabled=is_disabled
                    )
                    if new_cur != s.get("currency"):
                        s["currency"] = new_cur
                        save_portfolio(st.session_state.portfolio_dict)
                        st.rerun()
                        
                with col_pr:
                    lbl = tr("portfolio_market_price")
                    if s.get("currency") == "ILS":
                        lbl += " (אגורות)"
                    new_price = st.number_input(
                        lbl,
                        value=float(s.get("currentPrice", 0.0)),
                        step=0.01,
                        key=f"price_input_{index}_{s['id']}",
                        disabled=is_disabled
                    )
                    if new_price != s.get("currentPrice"):
                        s["currentPrice"] = new_price
                        save_portfolio(st.session_state.portfolio_dict)
                        st.rerun()
                        
                with col_lk:
                    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                    new_locked = st.checkbox(
                        "🔒",
                        value=s.get("locked", False),
                        key=f"lock_checkbox_{index}_{s['id']}"
                    )
                    if new_locked != s.get("locked"):
                        s["locked"] = new_locked
                        save_portfolio(st.session_state.portfolio_dict)
                        st.rerun()
                        
                with col_del_btn:
                    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                    if st.button("🗑️", key=f"del_pos_btn_{index}_{s['id']}", help=tr("portfolio_delete_position"), use_container_width=True):
                        portfolio_data.pop(index)
                        save_portfolio(st.session_state.portfolio_dict)
                        st.session_state.portfolio_toast = "Position deleted!"
                        st.rerun()

                col_buys, col_sells = st.columns(2)
                
                with col_buys:
                    st.markdown(f"##### 📥 {tr('portfolio_buys')}")
                    buys_to_remove = []
                    for b_idx, buy in enumerate(s.get("buys", [])):
                        col_bp, col_bq, col_bd = st.columns([3, 3, 1])
                        with col_bp:
                            buy_p = col_bp.number_input(
                                f"Price {b_idx+1}",
                                value=float(buy.get("p", 0.0)),
                                step=0.01,
                                key=f"buy_p_{index}_{b_idx}_{s['id']}",
                                disabled=is_disabled,
                                label_visibility="collapsed"
                            )
                            if buy_p != buy.get("p"):
                                buy["p"] = buy_p
                                save_portfolio(st.session_state.portfolio_dict)
                        with col_bq:
                            buy_q = col_bq.number_input(
                                f"Qty {b_idx+1}",
                                value=float(buy.get("q", 0.0)),
                                step=0.01,
                                key=f"buy_q_{index}_{b_idx}_{s['id']}",
                                disabled=is_disabled,
                                label_visibility="collapsed"
                            )
                            if buy_q != buy.get("q"):
                                buy["q"] = buy_q
                                save_portfolio(st.session_state.portfolio_dict)
                        with col_bd:
                            if not is_disabled:
                                if col_bd.button("❌", key=f"del_buy_{index}_{b_idx}_{s['id']}", use_container_width=True):
                                    buys_to_remove.append(b_idx)
                                    
                    if buys_to_remove:
                        for b_idx in sorted(buys_to_remove, reverse=True):
                            s["buys"].pop(b_idx)
                        save_portfolio(st.session_state.portfolio_dict)
                        st.rerun()
                        
                    if not is_disabled:
                        if st.button("➕ " + tr("portfolio_add_buy"), key=f"add_buy_btn_{index}_{s['id']}", use_container_width=True):
                            s["buys"].append({"p": 0.0, "q": 0.0})
                            save_portfolio(st.session_state.portfolio_dict)
                            st.rerun()
                            
                with col_sells:
                    st.markdown(f"##### 📤 {tr('portfolio_sells')}")
                    sells_to_remove = []
                    for s_idx, sell in enumerate(s.get("sells", [])):
                        col_sp, col_sq, col_sd = st.columns([3, 3, 1])
                        with col_sp:
                            sell_p = col_sp.number_input(
                                f"Price {s_idx+1}",
                                value=float(sell.get("p", 0.0)),
                                step=0.01,
                                key=f"sell_p_{index}_{s_idx}_{s['id']}",
                                disabled=is_disabled,
                                label_visibility="collapsed"
                            )
                            if sell_p != sell.get("p"):
                                sell["p"] = sell_p
                                save_portfolio(st.session_state.portfolio_dict)
                        with col_sq:
                            sell_q = col_sq.number_input(
                                f"Qty {s_idx+1}",
                                value=float(sell.get("q", 0.0)),
                                step=0.01,
                                key=f"sell_q_{index}_{s_idx}_{s['id']}",
                                disabled=is_disabled,
                                label_visibility="collapsed"
                            )
                            if sell_q != sell.get("q"):
                                sell["q"] = sell_q
                                save_portfolio(st.session_state.portfolio_dict)
                        with col_sd:
                            if not is_disabled:
                                if col_sd.button("❌", key=f"del_sell_{index}_{s_idx}_{s['id']}", use_container_width=True):
                                    sells_to_remove.append(s_idx)
                                    
                    if sells_to_remove:
                        for s_idx in sorted(sells_to_remove, reverse=True):
                            s["sells"].pop(s_idx)
                        save_portfolio(st.session_state.portfolio_dict)
                        st.rerun()
                        
                    if not is_disabled:
                        if st.button("➕ " + tr("portfolio_add_sell"), key=f"add_sell_btn_{index}_{s['id']}", use_container_width=True):
                            s["sells"].append({"p": 0.0, "q": 0.0})
                            save_portfolio(st.session_state.portfolio_dict)
                            st.rerun()


# --- Execution Wrapper ---
if __name__ == "__main__":
    import sys
    from streamlit.web import cli as stcli
    from streamlit.runtime import exists

    if not exists():
        sys.argv = ["streamlit", "run", __file__]
        sys.exit(stcli.main())