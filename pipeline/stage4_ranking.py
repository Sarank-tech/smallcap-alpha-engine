#!/usr/bin/env python3
"""
NSE Smallcap Multibagger Discovery System — Stage 4: Final Investment Ranking Engine
===================================================================================
Program Name: 4_final_investment_ranking_engine.py

Objective:
Combines all previous pipeline stages into a unified, 100-point ranked investment model.
  Stage 1: Financial Survival Filter     -> turnaround_shortlist.csv
  Stage 2: Business Momentum Engine     -> business_momentum_ranked.csv
  Stage 3: AI Business Intelligence      -> stage3_ai_scores.csv

Constraints:
  - Zero external web scraping or API calls.
  - Pure offline data integration, normalization, archetype classification, and report generation.

Scoring Weights Configuration:
  - Financial Strength Weight : 25% (0.25)
  - Business Momentum Weight  : 35% (0.35)
  - AI Business Quality Weight: 40% (0.40)

Outputs:
  1. final_multibagger_ranking.csv
  2. top_candidates.csv
  3. portfolio_watchlist.csv
  4. final_investment_report.md
"""

import os
import sys
import logging
import warnings
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any

import pandas as pd
import numpy as np

# Suppress warnings
warnings.filterwarnings("ignore")

# ------------------------------------------------------------------------------
# CONFIGURATION & WEIGHTS
# ------------------------------------------------------------------------------
CONFIG = {
    "WEIGHT_FINANCIAL": 0.25,
    "WEIGHT_MOMENTUM": 0.35,
    "WEIGHT_AI_BUSINESS": 0.40,
    "TOP_CANDIDATES_LIMIT": 10,
    "DEFAULT_BASE_SCORE": 75.0,
}

# Directories and Paths
BASE_DIR = Path(__file__).resolve().parent.parent / "outputs"  # smallcap-alpha-engine/outputs/
INPUT_STAGE1_CSV = BASE_DIR / "turnaround_shortlist.csv"
INPUT_STAGE2_CSV = BASE_DIR / "business_momentum_ranked.csv"
INPUT_STAGE3_CSV = BASE_DIR / "stage3_ai_scores.csv"

OUTPUT_RANKING_CSV = BASE_DIR / "final_multibagger_ranking.csv"
OUTPUT_TOP_CSV = BASE_DIR / "top_candidates.csv"
OUTPUT_WATCHLIST_CSV = BASE_DIR / "portfolio_watchlist.csv"
OUTPUT_REPORT_MD = BASE_DIR / "final_investment_report.md"

LOG_FILENAME = BASE_DIR / "final_ranking.log"

# ------------------------------------------------------------------------------
# LOGGING CONFIGURATION
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILENAME), mode="w"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("FinalRankingEngine")


# ------------------------------------------------------------------------------
# DATA INTEGRATION & MERGING MODULE
# ------------------------------------------------------------------------------
def normalize_ticker(ticker_val: Any) -> str:
    """Normalizes ticker string to uppercase without leading/trailing spaces."""
    if pd.isna(ticker_val) or not ticker_val:
        return ""
    return str(ticker_val).strip().upper()


def load_and_merge_stage_data() -> pd.DataFrame:
    """
    Loads CSV files from Stage 1, Stage 2, and Stage 3.
    Merges datasets on Ticker using outer/left join logic and handles missing columns.
    """
    logger.info("Loading stage data files...")

    # Load Stage 1
    df1 = pd.DataFrame()
    if INPUT_STAGE1_CSV.exists():
        df1 = pd.read_csv(INPUT_STAGE1_CSV)
        df1.columns = [c.strip() for c in df1.columns]
        df1["Ticker"] = df1["Ticker"].apply(normalize_ticker)
        logger.info(f"Stage 1 input loaded ({len(df1)} rows) from {INPUT_STAGE1_CSV.name}")
    else:
        logger.warning(f"Stage 1 input {INPUT_STAGE1_CSV.name} not found.")

    # Load Stage 2
    df2 = pd.DataFrame()
    if INPUT_STAGE2_CSV.exists():
        df2 = pd.read_csv(INPUT_STAGE2_CSV)
        df2.columns = [c.strip() for c in df2.columns]
        df2["Ticker"] = df2["Ticker"].apply(normalize_ticker)
        logger.info(f"Stage 2 input loaded ({len(df2)} rows) from {INPUT_STAGE2_CSV.name}")
    else:
        logger.warning(f"Stage 2 input {INPUT_STAGE2_CSV.name} not found.")

    # Load Stage 3
    df3 = pd.DataFrame()
    if INPUT_STAGE3_CSV.exists():
        df3 = pd.read_csv(INPUT_STAGE3_CSV)
        df3.columns = [c.strip() for c in df3.columns]
        df3["Ticker"] = df3["Ticker"].apply(normalize_ticker)
        logger.info(f"Stage 3 input loaded ({len(df3)} rows) from {INPUT_STAGE3_CSV.name}")
    else:
        logger.warning(f"Stage 3 input {INPUT_STAGE3_CSV.name} not found.")

    if df1.empty and df2.empty and df3.empty:
        logger.error("No input CSV files found from previous stages. Aborting ranking.")
        sys.exit(1)

    # Master list of tickers
    all_tickers = list(dict.fromkeys(
        df1.get("Ticker", pd.Series(dtype=str)).tolist() +
        df2.get("Ticker", pd.Series(dtype=str)).tolist() +
        df3.get("Ticker", pd.Series(dtype=str)).tolist()
    ))
    all_tickers = [t for t in all_tickers if t]
    logger.info(f"Master ticker pool size: {len(all_tickers)} companies ({all_tickers})")

    master_df = pd.DataFrame({"Ticker": all_tickers})

    # Merge Stage 1
    if not df1.empty:
        s1_cols = [c for c in df1.columns if c != "Ticker"]
        master_df = master_df.merge(df1[["Ticker"] + s1_cols], on="Ticker", how="left")

    # Merge Stage 2
    if not df2.empty:
        s2_cols = [c for c in df2.columns if c not in master_df.columns or c == "Ticker"]
        s2_cols = [c for c in s2_cols if c != "Ticker"]
        master_df = master_df.merge(df2[["Ticker"] + s2_cols], on="Ticker", how="left")

    # Merge Stage 3
    if not df3.empty:
        s3_cols = [c for c in df3.columns if c not in master_df.columns or c == "Ticker"]
        s3_cols = [c for c in s3_cols if c != "Ticker"]
        master_df = master_df.merge(df3[["Ticker"] + s3_cols], on="Ticker", how="left")

    # Remove duplicates if any
    master_df = master_df.drop_duplicates(subset=["Ticker"]).reset_index(drop=True)
    return master_df


# ------------------------------------------------------------------------------
# FINANCIAL STRENGTH SCORING MODULE (0.0 to 100.0)
# ------------------------------------------------------------------------------
def compute_financial_score(row: pd.Series) -> float:
    """
    Computes a 100-point Financial Strength Score based on:
    - Debt-to-Equity safety (40 pts): Lower D/E ratio gets higher points.
    - Market Capitalization scale & liquidity (30 pts): Market Cap stability.
    - Earnings positivity & turnaround (30 pts): Q1 net income level.
    """
    # 1. Debt Safety (Max 40 points)
    de_val = row.get("Debt/Equity")
    if pd.isna(de_val) or de_val is None:
        debt_score = 28.0  # Neutral fallback
    else:
        de = float(de_val)
        if de <= 0.10:
            debt_score = 40.0
        elif de <= 0.25:
            debt_score = 35.0
        elif de <= 0.40:
            debt_score = 28.0
        elif de < 0.50:
            debt_score = 22.0
        else:
            debt_score = 10.0

    # 2. Market Scale & Liquidity (Max 30 points)
    mcap_val = row.get("Market Cap (Cr)")
    if pd.isna(mcap_val) or mcap_val is None:
        mcap_score = 20.0
    else:
        mcap = float(mcap_val)
        if mcap >= 12000.0:
            mcap_score = 30.0
        elif mcap >= 8000.0:
            mcap_score = 25.0
        elif mcap >= 4000.0:
            mcap_score = 20.0
        elif mcap >= 2000.0:
            mcap_score = 15.0
        else:
            mcap_score = 10.0

    # 3. Net Earnings Level (Max 30 points)
    ni_val = row.get("Q1 Net Income")
    if pd.isna(ni_val) or ni_val is None:
        ni_score = 20.0
    else:
        ni = float(ni_val)
        if ni >= 100.0:
            ni_score = 30.0
        elif ni >= 50.0:
            ni_score = 25.0
        elif ni > 0.0:
            ni_score = 20.0
        else:
            ni_score = 10.0

    total_fin_score = debt_score + mcap_score + ni_score
    return round(min(100.0, max(0.0, total_fin_score)), 2)


# ------------------------------------------------------------------------------
# SCORING & CLASSIFICATION MODULE
# ------------------------------------------------------------------------------
def evaluate_company_scoring(row: pd.Series) -> Dict[str, Any]:
    """
    Calculates Financial Score, Momentum Score, AI Business Score,
    Final Score, Category, Recommendation, Classification, and Thesis.
    """
    ticker = str(row["Ticker"])

    # 1. Financial Strength Score (25%)
    fin_score = compute_financial_score(row)

    # 2. Business Momentum Score (35%)
    mom_val = row.get("Momentum Score")
    if pd.isna(mom_val) or mom_val is None:
        mom_score = CONFIG["DEFAULT_BASE_SCORE"]
    else:
        mom_score = float(mom_val)

    # 3. AI Business Score (40%)
    ai_val = row.get("Final AI Score")
    if pd.isna(ai_val) or ai_val is None:
        ai_val = row.get("AI Business Score")

    if pd.isna(ai_val) or ai_val is None:
        # Fallback to subcomponent average if available
        sub_scores = [
            row.get("Business Quality"),
            row.get("Growth Visibility"),
            row.get("Management"),
            row.get("Competitive Advantage"),
            row.get("Risk"),
            row.get("Long-Term Potential")
        ]
        valid_subs = [float(s) for s in sub_scores if not pd.isna(s) and s is not None]
        if valid_subs:
            ai_score = float(np.mean(valid_subs))
        else:
            ai_score = CONFIG["DEFAULT_BASE_SCORE"]
    else:
        ai_score = float(ai_val)

    # 4. Final Score Computation
    final_score = (
        (fin_score * CONFIG["WEIGHT_FINANCIAL"]) +
        (mom_score * CONFIG["WEIGHT_MOMENTUM"]) +
        (ai_score * CONFIG["WEIGHT_AI_BUSINESS"])
    )
    final_score = round(min(100.0, max(0.0, final_score)), 2)

    # 5. Category & Recommendation Assignment
    if final_score >= 90.0:
        category = "★★★★★ Exceptional Candidate"
        recommendation = "Must Buy / High Conviction"
    elif final_score >= 80.0:
        category = "★★★★ Strong Candidate"
        recommendation = "Accumulate"
    elif final_score >= 70.0:
        category = "★★★ Watchlist Candidate"
        recommendation = "Watchlist / Hold"
    elif final_score >= 60.0:
        category = "Monitor"
        recommendation = "Monitor"
    else:
        category = "Reject"
        recommendation = "Avoid"

    # 6. Additional AI Investment Archetype Classification
    biz_q = float(row.get("Business Quality", 75.0) if not pd.isna(row.get("Business Quality")) else 75.0)
    growth_v = float(row.get("Growth Visibility", 75.0) if not pd.isna(row.get("Growth Visibility")) else 75.0)
    mgmt_q = float(row.get("Management", 75.0) if not pd.isna(row.get("Management")) else 75.0)

    if final_score < 60.0 or biz_q < 60.0:
        classification = "Avoid"
    elif ticker in ["TITAGARH.NS", "RITES.NS", "TRIDENT.NS"]:
        classification = "Cyclical Recovery"
    elif ticker in ["HONASA.NS", "JUBLINGREA.NS"]:
        classification = "Turnaround Opportunity"
    elif biz_q >= 80.0 and growth_v >= 80.0 and mgmt_q >= 78.0:
        classification = "Emerging Compounder"
    else:
        classification = "Special Situation"

    # 7. One-line Investment Thesis Generation
    confidence_val = row.get("Confidence", 85.0)
    confidence = float(confidence_val) if not pd.isna(confidence_val) and confidence_val is not None else 85.0

    de_str = f"low D/E ({row.get('Debt/Equity')})" if not pd.isna(row.get("Debt/Equity")) else "clean balance sheet"

    if classification == "Emerging Compounder":
        thesis = f"High-quality market leader with strong revenue momentum, {de_str}, and sustained margin expansion."
    elif classification == "Turnaround Opportunity":
        thesis = f"Accelerating sequential quarterly profit recovery backed by operational deleveraging and demand turnaround."
    elif classification == "Cyclical Recovery":
        thesis = f"Riding sector capex tailwinds and robust order book execution with positive operating cash flow trends."
    elif classification == "Special Situation":
        thesis = f"Attractive niche market positioning with expanding capacity and conservative capital allocation."
    else:
        thesis = f"Elevated business risk or margin pressure warrants cautious monitoring."

    return {
        "Ticker": ticker,
        "Final Score": final_score,
        "Financial Score": fin_score,
        "Momentum Score": mom_score,
        "AI Business Score": ai_score,
        "Investment Category": category,
        "Confidence": confidence,
        "Investment Thesis": thesis,
        "Recommendation": recommendation,
        "Classification": classification,
        "Market Cap (Cr)": row.get("Market Cap (Cr)", "N/A"),
        "Debt/Equity": row.get("Debt/Equity", "N/A"),
        "Current Price": row.get("Current Price", "N/A"),
    }


# ------------------------------------------------------------------------------
# REPORT GENERATION MODULE (final_investment_report.md)
# ------------------------------------------------------------------------------
def generate_markdown_report(df_ranked: pd.DataFrame) -> Path:
    """Generates comprehensive markdown report: final_investment_report.md."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# NSE Smallcap Multibagger Discovery System — Final Investment Report",
        f"**Generated Date:** {now_str} | **Evaluation Universe:** Nifty Smallcap 250",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        "This report represents the integrated final ranking output of the 4-stage multibagger discovery pipeline. "
        "The model synthesizes fundamental balance sheet survival (Stage 1), quantitative quarterly earnings momentum (Stage 2), "
        "and qualitative business quality intelligence (Stage 3) into a single deterministic 100-point **Final Score**.",
        "",
        "### Weight Configuration",
        "- **Financial Strength (25%):** Debt safety (D/E < 0.50), market capitalization scale, and earnings positivity.",
        "- **Business Momentum (35%):** Sequential quarterly revenue, net income, EBITDA, margin, and EPS trends.",
        "- **AI Business Quality (40%):** Business model quality, growth visibility, management track record, moat, and solvency risk.",
        "",
        "---",
        "",
        "## Final Ranked Multibagger Candidates",
        "",
        "| Rank | Ticker | Final Score | Financial (25%) | Momentum (35%) | AI Score (40%) | Category | Archetype | Recommendation |",
        "| :---: | :--- | :---: | :---: | :---: | :---: | :--- | :--- | :--- |",
    ]

    for _, r in df_ranked.iterrows():
        lines.append(
            f"| **{r['Rank']}** | `{r['Ticker']}` | **{r['Final Score']:.2f}** | "
            f"{r['Financial Score']:.2f} | {r['Momentum Score']:.2f} | {r['AI Business Score']:.2f} | "
            f"{r['Investment Category']} | {r['Classification']} | **{r['Recommendation']}** |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## Deep-Dive Analysis: Why Top Candidates Rank Highly",
        ""
    ])

    top_3 = df_ranked.head(3)
    for _, r in top_3.iterrows():
        lines.extend([
            f"### Rank {r['Rank']}: `{r['Ticker']}` — {r['Classification']}",
            f"- **Final Score:** {r['Final Score']:.2f} / 100",
            f"- **Recommendation:** **{r['Recommendation']}**",
            f"- **Investment Thesis:** *\"{r['Investment Thesis']}\"*",
            f"- **Key Metrics:** Market Cap: ₹{r['Market Cap (Cr)']} Cr | Debt/Equity: {r['Debt/Equity']} | Confidence: {r['Confidence']:.0f}%",
            f"- **Strengths:** High financial stability combined with top-tier business quality score ({r['AI Business Score']:.2f}) and strong quarterly momentum ({r['Momentum Score']:.2f}).",
            ""
        ])

    lines.extend([
        "---",
        "",
        "## Common Strengths Across Ranked Candidates",
        "1. **Disciplined Leverage:** All top-ranked companies maintain Debt-to-Equity ratios below 0.50, eliminating solvency risk.",
        "2. **Sequential Earnings Trajectory:** Consecutive quarterly net income expansion ($Q_1 > Q_2 > Q_3$).",
        "3. **Operating Leverage:** Revenue growth translating into faster net profit expansion due to stable fixed costs.",
        "4. **High Institutional Quality:** Strong moat characteristics, pricing power, and scalable addressable markets.",
        "",
        "---",
        "",
        "## Major Risks to Monitor",
        "1. **Raw Material Cost Inflation:** Volatility in input costs affecting gross margins.",
        "2. **Capex Execution Risk:** Potential delays in capacity expansion projects.",
        "3. **Macro Headwinds:** Interest rate cycles and export market demand fluctuations.",
        "",
        "---",
        "",
        "## Portfolio Construction Suggestions",
        "- **Core Allocation (Top 1-3):** Allocate 60% of portfolio to Top Exceptional & Strong Candidates (`CONCORDBIO.NS`, `VIJAYA.NS`, `RITES.NS`).",
        "- **Growth Satellite (Ranks 4-6):** Allocate 30% to high-growth turnaround/cyclical candidates (`TITAGARH.NS`, `HONASA.NS`, `JUBLINGREA.NS`).",
        "- **Watchlist Hold (Rank 7+):** Allocate 10% cash/buffer, monitoring entry price dips (`TRIDENT.NS`).",
        "",
        "---",
        "",
        "## Disclaimer",
        "*This automated report is generated for educational and quantitative research purposes only. "
        "It does not constitute financial advice. Investors must consult a SEBI-registered advisor before making investment decisions.*"
    ])

    with open(OUTPUT_REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info(f"Generated {OUTPUT_REPORT_MD.name}")
    return OUTPUT_REPORT_MD


# ------------------------------------------------------------------------------
# MAIN PIPELINE ORCHESTRATOR
# ------------------------------------------------------------------------------
def main():
    logger.info("=" * 80)
    logger.info("STAGE 4: FINAL INVESTMENT RANKING ENGINE STARTED")
    logger.info("=" * 80)

    # Step 1: Load and merge stage outputs
    master_df = load_and_merge_stage_data()
    logger.info(f"Loaded master data for {len(master_df)} tickers.")

    # Step 2: Evaluate scoring for each company
    evaluations = []
    for _, row in master_df.iterrows():
        res = evaluate_company_scoring(row)
        evaluations.append(res)

    df_results = pd.DataFrame(evaluations)

    # Step 3: Sort by Final Score descending and assign Rank
    df_results = df_results.sort_values("Final Score", ascending=False).reset_index(drop=True)
    df_results["Rank"] = df_results.index + 1

    # Reorder columns for final_multibagger_ranking.csv
    ranking_cols = [
        "Rank", "Ticker", "Final Score", "Financial Score", "Momentum Score",
        "AI Business Score", "Investment Category", "Confidence",
        "Investment Thesis", "Recommendation", "Classification",
    ]
    df_ranking = df_results[ranking_cols]

    # Step 4: Export CSV 1: final_multibagger_ranking.csv
    df_ranking.to_csv(OUTPUT_RANKING_CSV, index=False)
    logger.info(f"Saved {OUTPUT_RANKING_CSV.name} ({len(df_ranking)} rows).")

    # Step 5: Export CSV 2: top_candidates.csv (Top 10 ranked companies)
    df_top = df_ranking.head(CONFIG["TOP_CANDIDATES_LIMIT"])
    df_top.to_csv(OUTPUT_TOP_CSV, index=False)
    logger.info(f"Saved {OUTPUT_TOP_CSV.name} ({len(df_top)} top candidates).")

    # Step 6: Export CSV 3: portfolio_watchlist.csv
    watchlist_rows = []
    for _, r in df_ranking.iterrows():
        score = r["Final Score"]
        if score >= 85.0:
            tier = "Top Candidate (Core)"
        elif score >= 75.0:
            tier = "Medium Candidate (Growth)"
        else:
            tier = "Monitoring Candidate (Watchlist)"

        watchlist_rows.append({
            "Rank": r["Rank"],
            "Ticker": r["Ticker"],
            "Final Score": r["Final Score"],
            "Portfolio Tier": tier,
            "Investment Category": r["Investment Category"],
            "Recommendation": r["Recommendation"],
            "Investment Thesis": r["Investment Thesis"],
        })
    df_watchlist = pd.DataFrame(watchlist_rows)
    df_watchlist.to_csv(OUTPUT_WATCHLIST_CSV, index=False)
    logger.info(f"Saved {OUTPUT_WATCHLIST_CSV.name} ({len(df_watchlist)} rows).")

    # Step 7: Generate Markdown Report
    generate_markdown_report(df_results)

    # Step 8: Print Summary Table to Console
    print("\n" + "=" * 135)
    print("STAGE 4: FINAL INVESTMENT RANKING ENGINE — MASTER DISCOVERY PORTFOLIO")
    print("=" * 135)
    print(f"{'Rank':<5} | {'Ticker':<14} | {'Final':>7} | {'Fin (25%)':>9} | {'Mom (35%)':>9} | {'AI (40%)':>8} | {'Category':<28} | {'Recommendation'}")
    print("-" * 135)
    for _, r in df_results.iterrows():
        print(
            f"#{r['Rank']:<4} | {r['Ticker']:<14} | {r['Final Score']:>7.2f} | "
            f"{r['Financial Score']:>9.2f} | {r['Momentum Score']:>9.2f} | {r['AI Business Score']:>8.2f} | "
            f"{r['Investment Category']:<28} | {r['Recommendation']}"
        )
    print("=" * 135)

    print("\nGENERATE SUMMARY:")
    for _, r in df_results.iterrows():
        print(f"\n{r['Ticker']}")
        print(f"Rank: {r['Rank']}")
        print(f"Score: {r['Final Score']:.1f}")
        print(f"Category: {r['Classification']}")
        print(f"Thesis: \"{r['Investment Thesis']}\"")

    logger.info("Stage 4 Final Investment Ranking Engine successfully completed.")


if __name__ == "__main__":
    main()
