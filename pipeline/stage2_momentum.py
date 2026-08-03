#!/usr/bin/env python3
"""
Nifty Smallcap Business Momentum Score Screener (Stage 2)
---------------------------------------------------------
Evaluates shortlisted companies from `turnaround_shortlist.csv` (Stage 1)
by retrieving multi-quarter financial metrics via yfinance and calculating
a weighted Business Momentum Score (0-100).

Metric Components & Base Weights:
1. Sequential Quarterly Revenue Growth   (Weight: 20%)
2. Sequential Net Income Growth          (Weight: 20%)
3. EBITDA Trend (if available)           (Weight: 15%)
4. Operating Margin Trend                (Weight: 15%)
5. EPS Trend                             (Weight: 10%)
6. Operating Cash Flow Trend (if avail)  (Weight: 10%)
7. Debt Trend                            (Weight: 5%)
8. Profitability Metrics (ROE/ROCE)      (Weight: 5%)

Treats unavailable metrics gracefully by redistributing weights proportionally
to active metrics so total score is strictly normalized between 0 and 100.
"""

import os
import sys
import time
import logging
import warnings
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

import pandas as pd
import numpy as np
import yfinance as yf

# Suppress noisy third-party logging and warnings
warnings.filterwarnings("ignore")
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)

# ------------------------------------------------------------------------------
# PATHS
# ------------------------------------------------------------------------------
ROOT_DIR    = Path(__file__).resolve().parent.parent  # smallcap-alpha-engine/
OUTPUTS_DIR = ROOT_DIR / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

# ------------------------------------------------------------------------------
# LOGGING CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILENAME = OUTPUTS_DIR / "business_momentum.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILENAME), mode="w"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("BusinessMomentum")


# ------------------------------------------------------------------------------
# DATA RETRIEVAL WITH RETRY LOGIC
# ------------------------------------------------------------------------------
def fetch_ticker_financials_with_retry(
    symbol: str, max_retries: int = 3, backoff_seconds: float = 1.5
) -> Dict[str, Any]:
    """
    Retrieves quarterly income statement, balance sheet, cashflow, and info
    from yfinance for a given ticker symbol, with exponential retry logic.
    """
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"[{symbol}] Fetching financial data (Attempt {attempt}/{max_retries})...")
            ticker = yf.Ticker(symbol)

            # Suppress stdout/stderr noise from yfinance backend
            with open(os.devnull, "w") as devnull:
                with redirect_stderr(devnull), redirect_stdout(devnull):
                    inc = ticker.quarterly_income_stmt
                    if inc is None or inc.empty:
                        inc = ticker.quarterly_financials

                    bs = ticker.quarterly_balance_sheet
                    cf = ticker.quarterly_cashflow
                    info = ticker.info or {}

            # Basic validation
            if inc is not None and not inc.empty:
                logger.info(f"[{symbol}] Successfully retrieved financial statement with {len(inc.columns)} quarters.")
                return {
                    "symbol": symbol,
                    "ticker_obj": ticker,
                    "income_stmt": inc,
                    "balance_sheet": bs,
                    "cashflow": cf,
                    "info": info,
                }
            else:
                logger.warning(f"[{symbol}] Income statement empty on attempt {attempt}.")

        except Exception as err:
            logger.warning(f"[{symbol}] Attempt {attempt} failed: {err}")

        if attempt < max_retries:
            time.sleep(backoff_seconds * (2 ** (attempt - 1)))

    logger.error(f"[{symbol}] All {max_retries} attempts failed to fetch valid data.")
    return {
        "symbol": symbol,
        "ticker_obj": None,
        "income_stmt": None,
        "balance_sheet": None,
        "cashflow": None,
        "info": {},
    }


def prepare_quarterly_series(
    df: Optional[pd.DataFrame], possible_keys: List[str]
) -> Optional[pd.Series]:
    """
    Extracts a row series matching one of the possible keys from a financial DataFrame,
    sorts columns chronologically (oldest to newest), drops NaNs, and returns the series.
    """
    if df is None or df.empty:
        return None

    # Sort columns chronologically ascending
    sorted_df = df.reindex(sorted(df.columns), axis=1)

    for key in possible_keys:
        if key in sorted_df.index:
            s = sorted_df.loc[key].dropna()
            # Filter out zero/string junk if necessary
            s_numeric = pd.to_numeric(s, errors="coerce").dropna()
            if len(s_numeric) >= 2:
                return s_numeric

    return None


def clamp(val: float, min_val: float = 0.0, max_val: float = 100.0) -> float:
    """Clamps a floating point value between min_val and max_val."""
    return max(min_val, min(max_val, val))


# ------------------------------------------------------------------------------
# COMPONENT METRIC SCORING FUNCTIONS (0.0 to 100.0)
# ------------------------------------------------------------------------------

def score_revenue_growth(inc_df: Optional[pd.DataFrame]) -> Tuple[Optional[float], str]:
    """
    1. Sequential Quarterly Revenue Growth (Weight: 20%)
    Evaluates average sequential QoQ growth, growth consistency across quarters,
    and total revenue expansion across available quarters.
    """
    keys = ["Total Revenue", "Operating Revenue", "Revenue"]
    rev_series = prepare_quarterly_series(inc_df, keys)

    if rev_series is None or len(rev_series) < 2:
        return None, "Insufficient quarterly revenue data"

    vals = rev_series.values[-4:]  # take up to last 4 quarters
    if len(vals) < 2:
        return None, "Fewer than 2 quarters of revenue"

    # Sequential growth rates
    qoq_rates = [(vals[i] - vals[i - 1]) / abs(vals[i - 1]) for i in range(1, len(vals)) if vals[i - 1] != 0]
    if not qoq_rates:
        return None, "Invalid revenue growth calculation"

    avg_qoq = float(np.mean(qoq_rates))
    positive_ratio = sum(1 for r in qoq_rates if r > 0) / len(qoq_rates)
    total_growth = float((vals[-1] - vals[0]) / abs(vals[0])) if vals[0] != 0 else 0.0

    # Base score (50 for flat, +10 pts per +2% avg QoQ growth up to +30, +20 for consistency)
    score_avg = 50.0 + clamp(avg_qoq / 0.03, -1.0, 1.0) * 25.0
    score_total = 50.0 + clamp(total_growth / 0.15, -1.0, 1.0) * 25.0
    score_consistency = positive_ratio * 100.0

    final_score = clamp(0.4 * score_avg + 0.3 * score_total + 0.3 * score_consistency, 0.0, 100.0)
    details = f"Avg QoQ: {avg_qoq*100:.1f}%, Total: {total_growth*100:.1f}%, Consistent Qs: {int(positive_ratio*len(qoq_rates))}/{len(qoq_rates)}"
    return round(final_score, 2), details


def score_net_income_growth(inc_df: Optional[pd.DataFrame]) -> Tuple[Optional[float], str]:
    """
    2. Sequential Net Income Growth (Weight: 20%)
    Evaluates sequential net income improvement, profitability presence,
    and expansion trajectory.
    """
    keys = [
        "Net Income",
        "Net Income Common Stockholders",
        "Net Income From Continuing Operation Net Minority Interest",
        "Net Income Including Noncontrolling Interests",
        "Net Income Continuous Operations",
    ]
    ni_series = prepare_quarterly_series(inc_df, keys)

    if ni_series is None or len(ni_series) < 2:
        return None, "Insufficient quarterly net income data"

    vals = ni_series.values[-4:]
    if len(vals) < 2:
        return None, "Fewer than 2 quarters of net income"

    qoq_rates = []
    for i in range(1, len(vals)):
        prev = vals[i - 1]
        curr = vals[i]
        if prev != 0:
            qoq_rates.append((curr - prev) / abs(prev))

    if not qoq_rates:
        return None, "Invalid net income growth calculation"

    avg_qoq = float(np.mean(qoq_rates))
    positive_ratio = sum(1 for r in qoq_rates if r > 0) / len(qoq_rates)
    all_positive = all(v > 0 for v in vals)

    # Base score
    score_avg = 50.0 + clamp(avg_qoq / 0.05, -1.0, 1.0) * 30.0
    score_consistency = positive_ratio * 100.0
    profitability_bonus = 15.0 if all_positive else 0.0

    final_score = clamp(0.45 * score_avg + 0.45 * score_consistency + profitability_bonus, 0.0, 100.0)
    details = f"Avg QoQ: {avg_qoq*100:.1f}%, Consistent Qs: {int(positive_ratio*len(qoq_rates))}/{len(qoq_rates)}, All Profitable: {all_positive}"
    return round(final_score, 2), details


def score_ebitda_trend(inc_df: Optional[pd.DataFrame]) -> Tuple[Optional[float], str]:
    """
    3. EBITDA Trend (Weight: 15%)
    Evaluates EBITDA growth over available quarters and EBITDA margin expansion.
    Returns None if EBITDA is unavailable.
    """
    ebitda_keys = ["Normalized EBITDA", "EBITDA", "EBIT"]
    ebitda_series = prepare_quarterly_series(inc_df, ebitda_keys)

    rev_keys = ["Total Revenue", "Operating Revenue", "Revenue"]
    rev_series = prepare_quarterly_series(inc_df, rev_keys)

    if ebitda_series is None or len(ebitda_series) < 2:
        return None, "EBITDA metric not available"

    vals = ebitda_series.values[-4:]
    if len(vals) < 2:
        return None, "Fewer than 2 quarters of EBITDA"

    ebitda_growth = (vals[-1] - vals[0]) / abs(vals[0]) if vals[0] != 0 else 0.0
    qoq_rates = [(vals[i] - vals[i - 1]) / abs(vals[i - 1]) for i in range(1, len(vals)) if vals[i - 1] != 0]
    positive_ratio = sum(1 for r in qoq_rates if r > 0) / len(qoq_rates) if qoq_rates else 0.5

    # Margin trend if revenue available
    margin_expansion_bonus = 0.0
    if rev_series is not None:
        rev_vals = rev_series.reindex(ebitda_series.index).dropna().values[-len(vals):]
        if len(rev_vals) == len(vals) and all(r > 0 for r in rev_vals):
            m1 = vals[0] / rev_vals[0]
            m4 = vals[-1] / rev_vals[-1]
            margin_diff = m4 - m1
            margin_expansion_bonus = clamp(margin_diff / 0.05, -1.0, 1.0) * 15.0

    score_growth = 50.0 + clamp(ebitda_growth / 0.15, -1.0, 1.0) * 35.0
    score_consistency = positive_ratio * 100.0

    final_score = clamp(0.5 * score_growth + 0.35 * score_consistency + margin_expansion_bonus, 0.0, 100.0)
    details = f"EBITDA Growth: {ebitda_growth*100:.1f}%, Consistent Qs: {int(positive_ratio*len(qoq_rates))}/{len(qoq_rates) if qoq_rates else 0}"
    return round(final_score, 2), details


def score_op_margin_trend(inc_df: Optional[pd.DataFrame]) -> Tuple[Optional[float], str]:
    """
    4. Operating Margin Trend (Weight: 15%)
    Evaluates operating margin level and expansion across quarters.
    """
    op_inc_keys = ["Operating Income", "Operating Profit", "EBIT"]
    op_inc_series = prepare_quarterly_series(inc_df, op_inc_keys)

    rev_keys = ["Total Revenue", "Operating Revenue", "Revenue"]
    rev_series = prepare_quarterly_series(inc_df, rev_keys)

    if op_inc_series is None or rev_series is None:
        return None, "Operating income or revenue missing"

    common_dates = op_inc_series.index.intersection(rev_series.index)
    if len(common_dates) < 2:
        return None, "Fewer than 2 common quarters for operating margin"

    op_inc = op_inc_series.reindex(common_dates)
    rev = rev_series.reindex(common_dates)

    margins = (op_inc / rev).dropna().values[-4:]
    if len(margins) < 2:
        return None, "Insufficient margin data points"

    latest_margin = float(margins[-1])
    first_margin = float(margins[0])
    margin_expansion = latest_margin - first_margin

    # Score components
    score_level = clamp(latest_margin / 0.20, 0.0, 1.0) * 60.0  # 20% margin gives max level score 60
    score_trend = 20.0 + clamp(margin_expansion / 0.04, -1.0, 1.0) * 20.0  # +4% margin expansion adds 20 pts

    final_score = clamp(score_level + score_trend, 0.0, 100.0)
    details = f"Latest Margin: {latest_margin*100:.1f}%, Expansion: {margin_expansion*100:+.1f}% pts"
    return round(final_score, 2), details


def score_eps_trend(inc_df: Optional[pd.DataFrame]) -> Tuple[Optional[float], str]:
    """
    5. EPS Trend (Weight: 10%)
    Evaluates sequential Diluted/Basic EPS trend across quarters.
    """
    eps_keys = ["Diluted EPS", "Basic EPS"]
    eps_series = prepare_quarterly_series(inc_df, eps_keys)

    if eps_series is None or len(eps_series) < 2:
        return None, "EPS data unavailable"

    vals = eps_series.values[-4:]
    if len(vals) < 2:
        return None, "Fewer than 2 quarters of EPS"

    eps_growth = (vals[-1] - vals[0]) / abs(vals[0]) if vals[0] != 0 else 0.0
    qoq_rates = [(vals[i] - vals[i - 1]) / abs(vals[i - 1]) for i in range(1, len(vals)) if vals[i - 1] != 0]
    positive_ratio = sum(1 for r in qoq_rates if r > 0) / len(qoq_rates) if qoq_rates else 0.5

    score_growth = 50.0 + clamp(eps_growth / 0.15, -1.0, 1.0) * 35.0
    score_consistency = positive_ratio * 100.0

    final_score = clamp(0.6 * score_growth + 0.4 * score_consistency, 0.0, 100.0)
    details = f"Latest EPS: {vals[-1]:.2f}, Total EPS Growth: {eps_growth*100:.1f}%"
    return round(final_score, 2), details


def score_ocf_trend(
    cf_df: Optional[pd.DataFrame], inc_df: Optional[pd.DataFrame]
) -> Tuple[Optional[float], str]:
    """
    6. Operating Cash Flow Trend (Weight: 10%)
    Evaluates quarterly operating cash flow growth and cash conversion (OCF / Net Income).
    Returns None if cash flow data is unavailable (e.g. Indian stocks on yfinance).
    """
    ocf_keys = [
        "Operating Cash Flow",
        "Cash Flow From Continuing Operating Activities",
        "Free Cash Flow",
    ]
    ocf_series = prepare_quarterly_series(cf_df, ocf_keys)

    if ocf_series is None or len(ocf_series) < 2:
        return None, "Operating Cash Flow unavailable (N/A)"

    vals = ocf_series.values[-4:]
    if len(vals) < 2:
        return None, "Fewer than 2 quarters of OCF"

    ocf_growth = (vals[-1] - vals[0]) / abs(vals[0]) if vals[0] != 0 else 0.0
    positive_ratio = sum(1 for v in vals if v > 0) / len(vals)

    score_growth = 50.0 + clamp(ocf_growth / 0.15, -1.0, 1.0) * 30.0
    score_positive = positive_ratio * 20.0

    final_score = clamp(score_growth + score_positive, 0.0, 100.0)
    details = f"OCF Growth: {ocf_growth*100:.1f}%, Positive Qs: {int(positive_ratio*len(vals))}/{len(vals)}"
    return round(final_score, 2), details


def score_debt_trend(
    bs_df: Optional[pd.DataFrame], info_dict: dict
) -> Tuple[Optional[float], str]:
    """
    7. Debt Trend (Weight: 5%)
    Evaluates leverage (Debt to Equity) and deleveraging trend from balance sheet.
    """
    de_raw = info_dict.get("debtToEquity")
    de_ratio = None
    if de_raw is not None:
        de_ratio = (de_raw / 100.0) if de_raw > 5.0 else de_raw

    debt_keys = ["Total Debt", "Net Debt", "Long Term Debt"]
    debt_series = prepare_quarterly_series(bs_df, debt_keys)

    if de_ratio is None and debt_series is None:
        return None, "Debt metric unavailable"

    # Base score from Debt-to-Equity level
    if de_ratio is not None:
        if de_ratio <= 0.15:
            score_level = 100.0
        elif de_ratio <= 0.30:
            score_level = 85.0
        elif de_ratio <= 0.50:
            score_level = 65.0
        else:
            score_level = 40.0
    else:
        score_level = 60.0

    # Trend bonus if debt is decreasing across balance sheet quarters
    deleveraging_bonus = 0.0
    if debt_series is not None and len(debt_series) >= 2:
        vals = debt_series.values
        if vals[0] > 0:
            debt_change = (vals[-1] - vals[0]) / vals[0]
            if debt_change < 0:
                deleveraging_bonus = 15.0  # Debt reduction bonus
            elif debt_change > 0.20:
                deleveraging_bonus = -15.0  # Debt expansion penalty

    final_score = clamp(score_level + deleveraging_bonus, 0.0, 100.0)
    de_str = f"{de_ratio:.2f}" if de_ratio is not None else "N/A"
    details = f"D/E Ratio: {de_str}, Score Level: {score_level:.0f}"
    return round(final_score, 2), details


def score_profitability(
    info_dict: dict, bs_df: Optional[pd.DataFrame], inc_df: Optional[pd.DataFrame]
) -> Tuple[Optional[float], str]:
    """
    8. Profitability Metrics (ROCE / ROE) (Weight: 5%)
    Evaluates return on equity / return on assets / capital efficiency.
    """
    roe = info_dict.get("returnOnEquity")
    roa = info_dict.get("returnOnAssets")

    # Dynamic calculation if info is missing
    if roe is None and bs_df is not None and inc_df is not None:
        eq_series = prepare_quarterly_series(bs_df, ["Stockholders Equity", "Common Stock Equity"])
        ni_series = prepare_quarterly_series(inc_df, ["Net Income", "Net Income Common Stockholders"])
        if eq_series is not None and ni_series is not None:
            common = eq_series.index.intersection(ni_series.index)
            if len(common) >= 1:
                eq_val = eq_series.reindex(common).iloc[-1]
                ni_val = ni_series.reindex(common).iloc[-1]
                if eq_val > 0:
                    roe = (ni_val * 4) / eq_val  # Annualized quarterly ROE

    if roe is None and roa is None:
        return None, "Profitability metrics unavailable"

    metric_val = float(roe if roe is not None else roa * 1.5)

    if metric_val >= 0.20:
        score = 100.0
    elif metric_val >= 0.15:
        score = 85.0
    elif metric_val >= 0.10:
        score = 70.0
    elif metric_val >= 0.05:
        score = 55.0
    else:
        score = clamp(30.0 + metric_val * 400.0, 0.0, 50.0)

    details = f"ROE/ROA Equivalent: {metric_val*100:.1f}%"
    return round(score, 2), details


# ------------------------------------------------------------------------------
# CORE EVALUATION & WEIGHT REDISTRIBUTION ENGINE
# ------------------------------------------------------------------------------

BASE_WEIGHTS = {
    "revenue_growth": 20.0,
    "net_income_growth": 20.0,
    "ebitda_trend": 15.0,
    "op_margin_trend": 15.0,
    "eps_trend": 10.0,
    "ocf_trend": 10.0,
    "debt_trend": 5.0,
    "profitability": 5.0,
}


def evaluate_company_momentum(company_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates all 8 component metrics for a single stock, performs weight
    redistribution for missing metrics, and calculates total Momentum Score (0-100).
    """
    symbol = company_data["symbol"]
    inc = company_data["income_stmt"]
    bs = company_data["balance_sheet"]
    cf = company_data["cashflow"]
    info = company_data["info"]

    if inc is None or inc.empty:
        logger.error(f"[{symbol}] Cannot score stock due to missing income statement.")
        return {"symbol": symbol, "status": "FAILED", "reason": "No income statement"}

    # Run component evaluators
    evaluations = {
        "revenue_growth": score_revenue_growth(inc),
        "net_income_growth": score_net_income_growth(inc),
        "ebitda_trend": score_ebitda_trend(inc),
        "op_margin_trend": score_op_margin_trend(inc),
        "eps_trend": score_eps_trend(inc),
        "ocf_trend": score_ocf_trend(cf, inc),
        "debt_trend": score_debt_trend(bs, info),
        "profitability": score_profitability(info, bs, inc),
    }

    scores = {}
    details = {}
    active_weights = {}

    for metric_key, base_w in BASE_WEIGHTS.items():
        score_val, detail_msg = evaluations[metric_key]
        if score_val is not None and not np.isnan(score_val):
            scores[metric_key] = float(score_val)
            active_weights[metric_key] = base_w
        else:
            scores[metric_key] = None
        details[metric_key] = detail_msg

    # Weight redistribution
    total_active_weight = sum(active_weights.values())

    if total_active_weight <= 0:
        logger.error(f"[{symbol}] No active metrics could be scored.")
        return {"symbol": symbol, "status": "FAILED", "reason": "No active metrics"}

    # Calculate rescaled Momentum Score
    weighted_score_sum = sum(
        scores[k] * (active_weights[k] / total_active_weight)
        for k in active_weights
    )
    final_momentum_score = clamp(weighted_score_sum, 0.0, 100.0)

    logger.info(
        f"[{symbol}] Momentum Score: {final_momentum_score:.2f}/100 "
        f"({len(active_weights)}/{len(BASE_WEIGHTS)} metrics active, total active weight sum={total_active_weight:.0f}%)"
    )

    return {
        "symbol": symbol,
        "status": "SUCCESS",
        "momentum_score": round(final_momentum_score, 2),
        "active_metrics_count": len(active_weights),
        "total_active_weight": total_active_weight,
        "revenue_growth_score": scores["revenue_growth"],
        "net_income_growth_score": scores["net_income_growth"],
        "ebitda_trend_score": scores["ebitda_trend"],
        "op_margin_trend_score": scores["op_margin_trend"],
        "eps_trend_score": scores["eps_trend"],
        "ocf_trend_score": scores["ocf_trend"],
        "debt_trend_score": scores["debt_trend"],
        "profitability_score": scores["profitability"],
        "details": details,
    }


# ------------------------------------------------------------------------------
# MAIN EXECUTION FLOW
# ------------------------------------------------------------------------------

def main():
    logger.info("=" * 80)
    logger.info("STAGE 2: BUSINESS MOMENTUM SCORE SCREENER STARTED")
    logger.info("=" * 80)

    input_csv = OUTPUTS_DIR / "turnaround_shortlist.csv"
    if not input_csv.exists():
        logger.error(f"Input file '{input_csv}' not found. Please run Stage 1 filter first.")
        sys.exit(1)

    try:
        df_shortlist = pd.read_csv(input_csv)
    except Exception as err:
        logger.error(f"Failed to read '{input_csv}': {err}")
        sys.exit(1)

    if df_shortlist.empty or "Ticker" not in df_shortlist.columns:
        logger.warning(f"'{input_csv}' is empty or missing 'Ticker' column. Exiting.")
        sys.exit(0)

    tickers = [str(t).strip() for t in df_shortlist["Ticker"].dropna() if str(t).strip()]
    logger.info(f"Loaded {len(tickers)} ticker(s) from Stage 1 shortlist: {tickers}")

    results = []

    # Process each stock sequentially with progress logging
    for idx, symbol in enumerate(tickers, start=1):
        logger.info(f"\n[{idx}/{len(tickers)}] Evaluating Business Momentum for {symbol}...")
        financial_data = fetch_ticker_financials_with_retry(symbol)
        
        if financial_data["income_stmt"] is None:
            logger.warning(f"Skipping {symbol} due to unavailable financial statements.")
            continue

        eval_res = evaluate_company_momentum(financial_data)
        if eval_res.get("status") == "SUCCESS":
            results.append(eval_res)

    if not results:
        logger.warning("No stocks were successfully evaluated for Business Momentum.")
        sys.exit(0)

    # Sort results by Momentum Score descending
    results.sort(key=lambda x: x["momentum_score"], reverse=True)

    # Assign Rank
    for rank, item in enumerate(results, start=1):
        item["rank"] = rank

    # Format output DataFrame
    output_rows = []
    for item in results:
        output_rows.append({
            "Rank": item["rank"],
            "Ticker": item["symbol"],
            "Momentum Score": item["momentum_score"],
            "Revenue Growth Score": item["revenue_growth_score"] if item["revenue_growth_score"] is not None else "N/A",
            "Net Income Growth Score": item["net_income_growth_score"] if item["net_income_growth_score"] is not None else "N/A",
            "EBITDA Trend Score": item["ebitda_trend_score"] if item["ebitda_trend_score"] is not None else "N/A",
            "Op Margin Trend Score": item["op_margin_trend_score"] if item["op_margin_trend_score"] is not None else "N/A",
            "EPS Trend Score": item["eps_trend_score"] if item["eps_trend_score"] is not None else "N/A",
            "OCF Trend Score": item["ocf_trend_score"] if item["ocf_trend_score"] is not None else "N/A",
            "Debt Trend Score": item["debt_trend_score"] if item["debt_trend_score"] is not None else "N/A",
            "Profitability Score": item["profitability_score"] if item["profitability_score"] is not None else "N/A",
            "Active Metrics": f"{item['active_metrics_count']}/8",
            "Status": "PASSED",
        })

    df_output = pd.DataFrame(output_rows)
    output_csv = OUTPUTS_DIR / "business_momentum_ranked.csv"
    df_output.to_csv(output_csv, index=False)
    logger.info(f"\nSuccessfully generated '{output_csv.name}' with {len(df_output)} ranked company/companies.")

    # Print Console Summary Table
    print("\n" + "=" * 125)
    print("STAGE 2: BUSINESS MOMENTUM RANKING SUMMARY")
    print("=" * 125)
    header = f"{'Rank':<5} | {'Ticker':<14} | {'Score':<8} | {'Rev Grw':<8} | {'NI Grw':<8} | {'EBITDA':<8} | {'Op Margin':<10} | {'EPS':<8} | {'Debt':<8} | {'Active'}"
    print(header)
    print("-" * 125)

    for row in output_rows:
        rev_s = f"{row['Revenue Growth Score']:.1f}" if isinstance(row['Revenue Growth Score'], (int, float)) else str(row['Revenue Growth Score'])
        ni_s = f"{row['Net Income Growth Score']:.1f}" if isinstance(row['Net Income Growth Score'], (int, float)) else str(row['Net Income Growth Score'])
        eb_s = f"{row['EBITDA Trend Score']:.1f}" if isinstance(row['EBITDA Trend Score'], (int, float)) else str(row['EBITDA Trend Score'])
        om_s = f"{row['Op Margin Trend Score']:.1f}" if isinstance(row['Op Margin Trend Score'], (int, float)) else str(row['Op Margin Trend Score'])
        eps_s = f"{row['EPS Trend Score']:.1f}" if isinstance(row['EPS Trend Score'], (int, float)) else str(row['EPS Trend Score'])
        debt_s = f"{row['Debt Trend Score']:.1f}" if isinstance(row['Debt Trend Score'], (int, float)) else str(row['Debt Trend Score'])

        print(
            f"{row['Rank']:<5} | {row['Ticker']:<14} | {row['Momentum Score']:<8.2f} | "
            f"{rev_s:<8} | {ni_s:<8} | {eb_s:<8} | {om_s:<10} | {eps_s:<8} | {debt_s:<8} | {row['Active Metrics']}"
        )
    print("=" * 125)
    logger.info(f"Detailed logs saved to '{LOG_FILENAME.name}'.")


if __name__ == "__main__":
    main()
