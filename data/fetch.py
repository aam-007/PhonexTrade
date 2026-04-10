"""
Market data fetching layer.
Uses yfinance for live/historical data and caches results in SQLite.
Includes retry logic, freshness-aware caching, and NSE API fallback.
"""

import logging

import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
from data.database import cache_prices, get_cached_prices

logger = logging.getLogger(__name__)

BENCHMARK_TICKERS = {
    "Nifty 50": "^NSEI",
    "Nifty 500": "^CRSLDX",
}


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def get_safe_end_date(end: Optional[str]) -> str:
    """
    Ensure end date does not cause same-day empty data issues.
    If end is today (or None), shift it forward by 1 day.
    """
    today = datetime.now().strftime("%Y-%m-%d")

    if end is None or end == today:
        return (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    return end


# ---------------------------------------------------------------------------
# NSE fallback helpers
# ---------------------------------------------------------------------------

def fetch_nse_index_price(symbol: str) -> Optional[float]:
    """
    Fetch latest index value from NSE API.
    Works for indices like Nifty 50.
    """
    try:
        url = "https://www.nseindia.com/api/allIndices"

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        }

        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers)  # establish cookies
        response = session.get(url, headers=headers)

        data = response.json()

        for index in data["data"]:
            if index["index"] == "NIFTY 50" and symbol == "^NSEI":
                return float(index["last"])

        return None

    except Exception:
        return None


def fetch_nse_history(symbol: str) -> pd.Series:
    """
    Fetch limited historical data from NSE (fallback).
    Only supports NIFTY 50 for now.
    """
    try:
        if symbol != "^NSEI":
            return pd.Series(dtype=float)

        url = "https://www.nseindia.com/api/chart-databyindex?index=NIFTY%2050"

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        }

        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers)
        response = session.get(url, headers=headers)

        data = response.json()

        timestamps = data["grapthData"]

        dates = []
        prices = []

        for ts, price in timestamps:
            dates.append(datetime.fromtimestamp(ts / 1000))
            prices.append(price)

        series = pd.Series(prices, index=dates)
        return series.sort_index()

    except Exception:
        return pd.Series(dtype=float)


# ---------------------------------------------------------------------------
# Core fetch functions
# ---------------------------------------------------------------------------

def fetch_current_price(symbol: str) -> Optional[float]:
    """
    Fetch the most recent price using intraday data first,
    then fallback to recent daily close, then NSE API for indices.
    """
    try:
        ticker = yf.Ticker(symbol)

        # Try intraday data (more reliable for "today")
        hist = ticker.history(period="1d", interval="5m")

        if not hist.empty:
            price = float(hist["Close"].dropna().iloc[-1])
            print(f"[market_data]  {symbol}: current price fetched (intraday) → {price}")
            return price

        # Fallback to recent daily
        hist = ticker.history(period="5d")

        if not hist.empty:
            price = float(hist["Close"].dropna().iloc[-1])
            print(f"[market_data]  {symbol}: current price fetched (daily fallback) → {price}")
            return price

        # NSE fallback for indices
        if symbol.startswith("^"):
            nse_price = fetch_nse_index_price(symbol)
            if nse_price is not None:
                print(f"[market_data]  {symbol}: current price fetched (NSE fallback) → {nse_price}")
                return nse_price

        return None

    except Exception:
        return None


def fetch_historical_prices(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    use_cache: bool = True,
) -> pd.Series:
    """
    Fetch daily closing prices for a symbol.
    Returns a pandas Series indexed by date.
    Uses SQLite cache (freshness-aware) to reduce API calls.
    Retries with period fallback and NSE fallback if yfinance returns empty.
    """
    if start is None:
        start = (datetime.now() - timedelta(days=365 * 3)).strftime("%Y-%m-%d")
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")

    # Freshness-aware cache check
    if use_cache:
        cached = get_cached_prices(symbol)
        if cached:
            series = pd.Series(cached)
            series.index = pd.to_datetime(series.index)
            series = series.sort_index()

            if not series.empty:
                last_date = series.index[-1]
                age_days = (datetime.now() - last_date).days

                # Use cache only if it's recent (≤1 day old)
                if age_days <= 1:
                    print(f"[market_data]  {symbol}: serving {len(series)} data points from cache (age: {age_days}d)")
                    return series

    try:
        ticker = yf.Ticker(symbol)
        safe_end = get_safe_end_date(end)

        hist = ticker.history(start=start, end=safe_end)

        # Retry with period fallback if empty
        if hist.empty:
            logger.warning(f"{symbol}: Empty response from yfinance, retrying with period='1y'")
            hist = ticker.history(period="1y")

        if hist.empty:
            logger.warning(f"{symbol}: Still empty after retry, trying NSE fallback")
            # NSE fallback if still empty
            nse_series = fetch_nse_history(symbol)
            if not nse_series.empty:
                return nse_series
            return pd.Series(dtype=float)

        series = hist["Close"].copy()

        # Basic data validation: reject only if truly empty
        if len(series) == 0:
            logger.warning(f"{symbol}: Zero data points after fetch, returning empty")
            return pd.Series(dtype=float)

        print(f"[market_data] {symbol}: {len(series)} data points fetched successfully ({series.index[0].strftime('%Y-%m-%d')} → {series.index[-1].strftime('%Y-%m-%d')})")

        series.index = series.index.strftime("%Y-%m-%d")

        # Drop NaNs before caching
        series = series.dropna()

        # Cache the fetched prices
        cache_prices(symbol, series.to_dict())

        series.index = pd.to_datetime(series.index)
        return series.sort_index()

    except Exception:
        return pd.Series(dtype=float)


def fetch_benchmark_prices(benchmark_name: str, start: Optional[str] = None) -> pd.Series:
    """
    Fetch historical prices for a benchmark index.
    Tries each candidate ticker in order and returns the first non-empty result.
    Uses a visited-set guard to prevent infinite fallback loops.
    """
    primary = BENCHMARK_TICKERS.get(benchmark_name, "^NSEI")

    # Build ordered candidate list; keep unique entries only
    candidates = [primary]
    fallback = "NIFTYBEES.NS" if primary == "^NSEI" else "^NSEI"
    if fallback not in candidates:
        candidates.append(fallback)

    tried: set[str] = set()

    for symbol in candidates:
        if symbol in tried:
            continue
        tried.add(symbol)

        data = fetch_historical_prices(symbol, start=start)

        if not data.empty:
            return data

        logger.warning(f"{symbol}: benchmark data empty, trying next candidate")

    logger.error(f"All benchmark candidates exhausted for '{benchmark_name}', returning empty")
    return pd.Series(dtype=float)


def search_symbols(query: str) -> list[str]:
    """
    Return a list of matching NSE stock symbols for autocomplete.
    Uses a static list of common NSE symbols for speed.
    """
    nse_symbols = [
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
        "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BAJFINANCE.NS", "BHARTIARTL.NS",
        "KOTAK.NS", "KOTAKBANK.NS", "LT.NS", "AXISBANK.NS", "ASIANPAINT.NS",
        "HCLTECH.NS", "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS", "NESTLEIND.NS",
        "WIPRO.NS", "ULTRACEMCO.NS", "POWERGRID.NS", "NTPC.NS", "ONGC.NS",
        "TECHM.NS", "M&M.NS", "GRASIM.NS", "JSWSTEEL.NS", "TATAMOTORS.NS",
        "TATASTEEL.NS", "DRREDDY.NS", "ADANIENT.NS", "ADANIPORTS.NS", "BAJAJFINSV.NS",
        "BAJAJ-AUTO.NS", "DIVISLAB.NS", "EICHERMOT.NS", "HEROMOTOCO.NS", "INDUSINDBK.NS",
        "CIPLA.NS", "COALINDIA.NS", "BRITANNIA.NS", "BPCL.NS", "APOLLOHOSP.NS",
        "HDFCLIFE.NS", "SBILIFE.NS", "ICICIGI.NS", "TATACONSUM.NS", "UPL.NS",
        "VEDL.NS", "HINDALCO.NS", "GODREJCP.NS", "MCDOWELL-N.NS", "PFC.NS",
        "RECLTD.NS", "SIEMENS.NS", "ABB.NS", "PIDILITIND.NS", "BERGEPAINT.NS",
        "HAVELLS.NS", "VOLTAS.NS", "PAGEIND.NS", "MPHASIS.NS", "LTIM.NS",
        "PERSISTENT.NS", "COFORGE.NS", "ZOMATO.NS", "NYKAA.NS", "PAYTM.NS",
        "IRCTC.NS", "DMART.NS", "TRENT.NS", "DLFU.NS", "OBEROIRLTY.NS",
        "PHOENIXLTD.NS", "NUVOCO.NS", "MAXHEALTH.NS", "FORTIS.NS", "NHPC.NS",
        "CANBK.NS", "BANKBARODA.NS", "PNB.NS", "IDFCFIRSTB.NS", "FEDERALBNK.NS",
        "SAIL.NS", "NMDC.NS", "NATIONALUM.NS", "MOIL.NS", "WELCORP.NS",
    ]

    if not query:
        return nse_symbols[:20]

    query_upper = query.upper()
    matches = [s for s in nse_symbols if query_upper in s.upper()]
    return matches[:15]