#!/usr/bin/env python3
"""
NSE Multibagger Discovery System — Master Pipeline Orchestrator
================================================================
Program Name: run_pipeline.py

Objective:
Executes the entire 5-stage multibagger discovery pipeline sequentially
in a single command (`python3 run_pipeline.py`).

Pipeline Stages:
  Stage 1: pipeline/stage1_filter.py           -> outputs/turnaround_shortlist.csv
  Stage 2: pipeline/stage2_momentum.py         -> outputs/business_momentum_ranked.csv
  Stage 3: pipeline/stage3_ai_intelligence.py  -> outputs/stage3_ai_scores.csv
  Stage 4: pipeline/stage4_ranking.py          -> outputs/final_multibagger_ranking.csv
  Stage 5: pipeline/stage5_portfolio.py        -> outputs/portfolio_plan.csv

Features:
  - Single-command execution: `python3 run_pipeline.py`
  - Flexible stage selection: `--from-stage N` or `--stage N`
  - Workspace cleaning: `--clean` flag to start fresh
  - Real-time stage logging, elapsed time tracking, and assertion checks
"""

import sys
import time
import argparse
import subprocess
import logging
from pathlib import Path
from datetime import datetime

# ------------------------------------------------------------------------------
# CONFIGURATION & STAGE DEFINITIONS
# ------------------------------------------------------------------------------
ROOT_DIR  = Path(__file__).resolve().parent  # smallcap-alpha-engine/
OUTPUTS_DIR = ROOT_DIR / "outputs"

# Default portfolio capital investment passed to Stage 5 (Modify here as needed)
PORTFOLIO_CAPITAL_INR = 100000.0  # default capital

STAGES = [
    {
        "num": 1,
        "name": "Stage 1: Financial Survival Screener",
        "script": "pipeline/stage1_filter.py",
        "expected_output": "turnaround_shortlist.csv",
    },
    {
        "num": 2,
        "name": "Stage 2: Business Momentum Engine",
        "script": "pipeline/stage2_momentum.py",
        "expected_output": "business_momentum_ranked.csv",
    },
    {
        "num": 3,
        "name": "Stage 3: AI Business Intelligence Engine",
        "script": "pipeline/stage3_ai_intelligence.py",
        "expected_output": "stage3_ai_scores.csv",
    },
    {
        "num": 4,
        "name": "Stage 4: Final Investment Ranking Engine",
        "script": "pipeline/stage4_ranking.py",
        "expected_output": "final_multibagger_ranking.csv",
    },
    {
        "num": 5,
        "name": "Stage 5: Portfolio & Sell Strategy Engine",
        "script": "pipeline/stage5_portfolio.py",
        "expected_output": "portfolio_plan.csv",
    },
]

# ------------------------------------------------------------------------------
# LOGGING SETUP
# ------------------------------------------------------------------------------
OUTPUTS_DIR.mkdir(exist_ok=True)  # ensure outputs/ exists
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(OUTPUTS_DIR / "master_pipeline.log", mode="w"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("MasterPipeline")


# ------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------------------------
def clean_previous_outputs():
    """Removes output CSVs and log files from outputs/ for a fresh pipeline run."""
    files_to_remove = [
        "turnaround_shortlist.csv",
        "business_momentum_ranked.csv",
        "stage3_ai_scores.csv",
        "final_multibagger_ranking.csv",
        "top_candidates.csv",
        "portfolio_watchlist.csv",
        "final_investment_report.md",
        "portfolio_plan.csv",
        "portfolio_strategy_report.md",
        "business_momentum.log",
        "ai_business_intelligence.log",
        "final_ranking.log",
        "portfolio_strategy.log",
        "master_pipeline.log",
    ]
    logger.info("Cleaning previous pipeline outputs and logs...")
    for filename in files_to_remove:
        p = OUTPUTS_DIR / filename
        if p.exists():
            p.unlink()
            logger.info(f"  Removed: outputs/{filename}")
    # Also remove index.html from root
    html = ROOT_DIR / "index.html"
    if html.exists():
        html.unlink()
        logger.info("  Removed: index.html")


def run_stage(stage_info: dict, capital: float = PORTFOLIO_CAPITAL_INR) -> float:
    """Runs a single pipeline stage using subprocess with error handling and timing."""
    num = stage_info["num"]
    name = stage_info["name"]
    script_name = stage_info["script"]
    expected_out = OUTPUTS_DIR / stage_info["expected_output"]
    script_path = ROOT_DIR / script_name

    if not script_path.exists():
        logger.error(f"[{name}] Script '{script_name}' not found at {script_path}")
        sys.exit(1)

    print("\n" + "=" * 90)
    print(f"  ▶ RUNNING {name.upper()}")
    print(f"    Script: {script_name}")
    print("=" * 90)

    start_time = time.time()

    # Execute stage script in subprocess
    try:
        cmd = [sys.executable, str(script_path)]
        if num == 5:
            cmd.extend(["--capital", str(capital)])
        result = subprocess.run(cmd, cwd=str(ROOT_DIR), check=True)
        elapsed = time.time() - start_time

        if result.returncode == 0:
            if expected_out.exists() and expected_out.stat().st_size > 0:
                print(f"  ✔ {name} COMPLETED SUCCESSFULLY in {elapsed:.2f}s")
                print(f"    Output verified: {expected_out.name} ({expected_out.stat().st_size} bytes)")
                return elapsed
            else:
                logger.error(f"[{name}] Expected output '{expected_out.name}' missing or empty after run.")
                sys.exit(1)
        else:
            logger.error(f"[{name}] Failed with exit code {result.returncode}")
            sys.exit(result.returncode)

    except subprocess.CalledProcessError as err:
        logger.error(f"[{name}] Execution failed with error: {err}")
        sys.exit(err.returncode)
    except Exception as ex:
        logger.error(f"[{name}] Unexpected execution error: {ex}")
        sys.exit(1)


# ------------------------------------------------------------------------------
# MAIN PIPELINE ORCHESTRATOR
# ------------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="NSE Smallcap Multibagger Master Pipeline Orchestrator"
    )
    parser.add_argument(
        "--from-stage",
        type=int,
        choices=[1, 2, 3, 4, 5],
        default=1,
        help="Start pipeline from specified stage number (default: 1)",
    )
    parser.add_argument(
        "--stage",
        type=int,
        choices=[1, 2, 3, 4, 5],
        default=None,
        help="Run ONLY the specified stage number",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean old output CSVs and log files before running",
    )
    parser.add_argument(
        "--capital", "--portfolio-size",
        type=float,
        default=PORTFOLIO_CAPITAL_INR,
        help=f"Total portfolio capital in INR passed to Stage 5 (default: {PORTFOLIO_CAPITAL_INR})",
    )
    args = parser.parse_args()

    start_total_time = time.time()

    print("=" * 90)
    print(" 🚀 NSE MULTIBAGGER DISCOVERY SYSTEM — MASTER PIPELINE ORCHESTRATOR")
    print(f"    Execution Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 90)

    if args.clean:
        clean_previous_outputs()

    # Determine stages to execute
    if args.stage is not None:
        stages_to_run = [s for s in STAGES if s["num"] == args.stage]
    else:
        stages_to_run = [s for s in STAGES if s["num"] >= args.from_stage]

    stage_timings = {}

    for stage in stages_to_run:
        elapsed = run_stage(stage, capital=args.capital)
        stage_timings[stage["name"]] = elapsed

    total_elapsed = time.time() - start_total_time

    # Pipeline Completion Summary
    print("\n" + "=" * 90)
    print(" 🎉 ALL STAGES EXECUTED SUCCESSFULLY")
    print("=" * 90)
    print(f"{'Pipeline Stage':<45} | {'Execution Time':>15} | {'Status'}")
    print("-" * 90)
    for name, elapsed in stage_timings.items():
        print(f"{name:<45} | {elapsed:>14.2f}s | ✔ SUCCESS")
    print("-" * 90)
    print(f"{'Total Pipeline Duration':<45} | {total_elapsed:>14.2f}s | COMPLETE")
    print("=" * 90)

    print("\n📁 GENERATED DELIVERABLES (outputs/ folder):")
    print("  1. Stage 1 Shortlist  : outputs/turnaround_shortlist.csv")
    print("  2. Stage 2 Momentum   : outputs/business_momentum_ranked.csv")
    print("  3. Stage 3 AI Scores  : outputs/stage3_ai_scores.csv + outputs/research/<TICKER>/")
    print("  4. Stage 4 Rankings   : outputs/final_multibagger_ranking.csv + outputs/final_investment_report.md")
    print("  5. Stage 5 Portfolio  : outputs/portfolio_plan.csv + outputs/portfolio_strategy_report.md")

    # Generate interactive HTML dashboard
    dashboard_script = ROOT_DIR / "dashboard" / "generate_dashboard.py"
    if dashboard_script.exists():
        try:
            subprocess.run([sys.executable, str(dashboard_script)], cwd=str(ROOT_DIR), check=True)
            print("  6. Interactive Dashboard: index.html (Open in your browser!)")
        except Exception as e:
            logger.warning(f"Could not generate HTML dashboard: {e}")

    print("\nOpen `index.html` in your browser to view the interactive pipeline dashboard.\n")


if __name__ == "__main__":
    main()
