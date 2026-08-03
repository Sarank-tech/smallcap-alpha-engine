#!/usr/bin/env python3
"""
Nifty Smallcap 250 Fundamental Turnaround & Price Screener
----------------------------------------------------------
A quantitative financial processing script using `pandas` and `yfinance`
to identify high-liquidity, fundamentally turning-around small-cap stocks.

Filters applied:
1. Universe: Dynamic Nifty Smallcap 250 from niftyindices.com (with niftystocks fallback)
2. Market Cap: Between ₹2,000 Crore and ₹15,000 Crore
3. Liquidity: 3-month average daily volume > 300,000 shares
4. Balance Sheet: Debt-to-Equity ratio < 0.50
5. Growth Breakout: Sequential Net Income improvement over last 3 quarters (Q1 > Q2 > Q3)
6. Price Extraction: Dynamic live trading price from yfinance info / fast_info
"""

import io
import os
import sys
import warnings
import logging
from contextlib import redirect_stdout, redirect_stderr
import requests
import pandas as pd
import numpy as np
from pathlib import Path
import yfinance as yf

ROOT_DIR    = Path(__file__).resolve().parent.parent  # smallcap-alpha-engine/
OUTPUTS_DIR = ROOT_DIR / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

# Suppress third-party warnings and verbose loggers
warnings.filterwarnings("ignore")
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)


def fetch_nifty_smallcap250_symbols() -> list:
    """
    Fetches the live Nifty Smallcap 250 constituent symbol list directly
    from niftyindices.com using a standard User-Agent header.
    Falls back to the niftystocks library if URL request fails.
    """
    url = "https://niftyindices.com/IndexConstituent/ind_niftysmallcap250list.csv"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    print("Fetching live Nifty Smallcap 250 index list from niftyindices.com...")
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        df_csv = pd.read_csv(io.StringIO(response.text))
        
        # Locate the 'Symbol' column
        symbol_col = None
        for col in df_csv.columns:
            if col.strip().lower() == "symbol":
                symbol_col = col
                break

        if symbol_col:
            symbols = [str(s).strip() for s in df_csv[symbol_col].dropna() if str(s).strip()]
            if symbols:
                print(f"Successfully retrieved {len(symbols)} symbols from NSE source.")
                return symbols

    except Exception as err:
        print(f"[WARNING] Primary URL fetch failed ({err}). Attempting fallback via 'niftystocks'...")

    # Fallback to niftystocks library
    try:
        import niftystocks
        from niftystocks import ns

        if hasattr(ns, "get_nifty_smallcap250"):
            symbols = ns.get_nifty_smallcap250()
        elif hasattr(niftystocks, "get_nifty_smallcap250"):
            symbols = niftystocks.get_nifty_smallcap250()
        else:
            raise AttributeError("get_nifty_smallcap250 function not found in niftystocks.")

        print(f"Successfully retrieved {len(symbols)} symbols via niftystocks fallback.")
        return symbols
    except Exception as fallback_err:
        print(f"[ERROR] Failed to fetch symbols from all sources: {fallback_err}")
        return []


def extract_current_price(ticker_obj: yf.Ticker, info_dict: dict) -> float:
    """
    Dynamically extracts the current live/closing price using ticker.info
    or ticker.fast_info['lastPrice'].
    """
    price = (
        info_dict.get("currentPrice") or 
        info_dict.get("regularMarketPrice") or 
        info_dict.get("previousClose")
    )

    if price is None or pd.isna(price) or price <= 0:
        try:
            with open(os.devnull, "w") as devnull:
                with redirect_stderr(devnull), redirect_stdout(devnull):
                    fast_price = ticker_obj.fast_info.get("lastPrice", None)
                    if fast_price is not None and not pd.isna(fast_price) and fast_price > 0:
                        price = float(fast_price)
        except Exception:
            price = None

    return float(price) if price is not None and not pd.isna(price) else None


def extract_net_income_series(ticker_obj: yf.Ticker) -> pd.Series:
    """
    Extracts quarterly Net Income series from yfinance income statement.
    Handles multiple naming conventions for Net Income across reporting standards.
    """
    inc = None
    try:
        with open(os.devnull, "w") as devnull:
            with redirect_stderr(devnull), redirect_stdout(devnull):
                inc = ticker_obj.quarterly_income_stmt
                if inc is None or inc.empty:
                    inc = ticker_obj.quarterly_financials
    except Exception:
        return None

    if inc is None or inc.empty:
        return None

    possible_keys = [
        "Net Income",
        "Net Income Common Stockholders",
        "Net Income From Continuing Operation Net Minority Interest",
        "Net Income Including Noncontrolling Interests",
        "Net Income Continuous Operations",
    ]

    for key in possible_keys:
        if key in inc.index:
            series = inc.loc[key].dropna()
            if len(series) >= 3:
                return series

    return None


def run_smallcap_fundamental_screener():
    """
    Main screener loop to evaluate Nifty Smallcap 250 stocks against:
    - Market Cap (₹2,000 Cr - ₹15,000 Cr)
    - 3-Month Daily Avg Volume (> 300,000 shares)
    - Debt-to-Equity Ratio (< 0.50)
    - Sequential Net Income Turnaround (Q1 > Q2 > Q3)
    - Live Current Price Extraction
    """
    symbols = fetch_nifty_smallcap250_symbols()
    if not symbols:
        print("[ERROR] No tickers available for processing.")
        return

    # Step 2: Map symbols to Yahoo Finance format with .NS suffix
    ticker_map = {f"{s}.NS": s for s in symbols}
    yf_tickers = list(ticker_map.keys())

    print(f"\nProcessing {len(yf_tickers)} Smallcap tickers through financial rules...")
    print("=" * 115)
    print(f"{'Ticker':<12} | {'Market Cap (Cr)':<16} | {'3M Avg Vol':<12} | {'Debt/Equity':<12} | {'Q1 Net Income':<15} | {'Current Price':<14} | {'Status'}")
    print("=" * 115)

    shortlist = []
    skipped_count = 0

    # Step 3: Iterate through each ticker and evaluate criteria
    for yf_ticker in yf_tickers:
        raw_symbol = ticker_map[yf_ticker]

        try:
            t = yf.Ticker(yf_ticker)

            info = {}
            try:
                with open(os.devnull, "w") as devnull:
                    with redirect_stderr(devnull), redirect_stdout(devnull):
                        info = t.info or {}
            except Exception:
                info = {}

            if not info:
                skipped_count += 1
                continue

            # Filter 1: Market Capitalization (between ₹2,000 Cr and ₹15,000 Cr)
            mcap_inr = info.get("marketCap")
            if not mcap_inr or mcap_inr <= 0:
                skipped_count += 1
                continue

            mcap_cr = mcap_inr / 1e7  # Convert INR to Crores (1 Crore = 10^7 INR)
            if not (2000.0 <= mcap_cr <= 15000.0):
                continue

            # Filter 2: Liquidity (3-Month Avg Volume > 300,000 shares)
            avg_vol_3m = info.get("averageVolume3Month") or info.get("averageVolume") or 0
            if avg_vol_3m <= 300000:
                continue

            # Filter 3: Debt-to-Equity Ratio (< 0.50)
            de_raw = info.get("debtToEquity")
            if de_raw is None:
                skipped_count += 1
                continue

            # yfinance returns debtToEquity either as ratio (0.45) or percentage (45.0)
            de_ratio = (de_raw / 100.0) if de_raw > 5.0 else de_raw
            if de_ratio >= 0.50:
                continue

            # Filter 4: Sequential Net Income Turnaround (Q1 > Q2 and Q2 > Q3)
            net_inc_series = extract_net_income_series(t)
            if net_inc_series is None or len(net_inc_series) < 3:
                skipped_count += 1
                continue

            sorted_inc = net_inc_series.sort_index(ascending=False)
            q1_net_inc = float(sorted_inc.iloc[0])
            q2_net_inc = float(sorted_inc.iloc[1])
            q3_net_inc = float(sorted_inc.iloc[2])

            if not (q1_net_inc > q2_net_inc and q2_net_inc > q3_net_inc):
                continue

            # Filter 5: Extract Current Live Price
            current_price = extract_current_price(t, info)
            if current_price is None:
                price_display = "N/A"
            else:
                price_display = f"₹{current_price:,.2f}"

            q1_net_inc_cr = q1_net_inc / 1e7

            # Stock passed all 4 financial rules!
            shortlist.append({
                "Ticker": yf_ticker,
                "Market Cap (Cr)": round(mcap_cr, 2),
                "3M Avg Vol": int(avg_vol_3m),
                "Debt/Equity": round(de_ratio, 2),
                "Q1 Net Income": round(q1_net_inc_cr, 2),
                "Current Price": round(current_price, 2) if current_price else "N/A",
                "Status": "PASSED"
            })

            print(
                f"{raw_symbol:<12} | ₹{mcap_cr:<14,.2f} | {int(avg_vol_3m):<12,d} | "
                f"{de_ratio:<12.2f} | ₹{q1_net_inc_cr:<13,.2f} | {price_display:<14} | PASSED"
            )

        except Exception as err:
            skipped_count += 1
            print(f"[WARNING] Skipping {raw_symbol}: Exception encountered ({err})")

    print("=" * 115)

    # Step 4: Export matching records to outputs/turnaround_shortlist.csv
    csv_path = OUTPUTS_DIR / "turnaround_shortlist.csv"
    if shortlist:
        df_out = pd.DataFrame(shortlist)
        # Required column layout
        columns_order = [
            "Ticker", "Market Cap (Cr)", "3M Avg Vol",
            "Debt/Equity", "Q1 Net Income", "Current Price", "Status"
        ]
        df_out = df_out[columns_order]
        df_out.to_csv(csv_path, index=False)
        print(f"\n[SUCCESS] {len(shortlist)} smallcap stock(s) passed all financial filters.")
        print(f"Results exported to 'outputs/turnaround_shortlist.csv'.")
    else:
        # Create empty CSV with required headers if none passed
        df_empty = pd.DataFrame(columns=[
            "Ticker", "Market Cap (Cr)", "3M Avg Vol",
            "Debt/Equity", "Q1 Net Income", "Current Price", "Status"
        ])
        df_empty.to_csv(csv_path, index=False)
        print(f"\n[INFO] 0 stocks passed all screening rules. Saved empty 'outputs/turnaround_shortlist.csv'.")
    # Step 5: Print summary to console
    print("\n" + "=" * 80)
    print("SMALLCAP FUNDAMENTAL TURNAROUND SUMMARY")
    print("=" * 80)
    print(f"Total Smallcap Tickers Evaluated : {len(yf_tickers)}")
    print(f"Passed All Financial Filters     : {len(shortlist)}")
    print(f"Filtered / Skipped (Missing Data): {len(yf_tickers) - len(shortlist)}")

    if shortlist:
        print("\n" + "-" * 80)
        print(f"{'Ticker':<14} | {'Market Cap (Cr)':<16} | {'D/E Ratio':<10} | {'Q1 Net Income':<15} | {'Current Price':<14}")
        print("-" * 80)
        for s in shortlist:
            price_str = f"₹{s['Current Price']:,.2f}" if isinstance(s['Current Price'], (int, float)) else str(s['Current Price'])
            print(
                f"{s['Ticker']:<14} | ₹{s['Market Cap (Cr)']:<14,.2f} | "
                f"{s['Debt/Equity']:<10.2f} | ₹{s['Q1 Net Income']:<13,.2f} Cr | {price_str:<14}"
            )
        print("-" * 80)
    print("=" * 80)


if __name__ == "__main__":
    run_smallcap_fundamental_screener()
