"""Tweet Analysis Agent - Pipeline Orchestrator.

Runs the 5-agent pipeline: Ingestion → Parser → Fact-Checker → Strategy Tester → Report Generator.

Usage:
    python main.py --mode urls --input data/input/sample_urls.txt
    python main.py --mode bookmarks
    python main.py --mode urls --limit 5
    python main.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path("data")
REPORTS_DIR = Path("reports")


def ensure_dirs() -> None:
    for sub in ["raw", "parsed", "verified", "tested"]:
        (DATA_DIR / sub).mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def run_pipeline(mode: str, input_file: str | None, limit: int | None, dry_run: bool) -> None:
    ensure_dirs()

    # --- Stage 1: Ingestion ---
    print("\n=== Stage 1: Ingestion ===")
    from agents.ingestion import run_ingestion

    raw_path = DATA_DIR / "raw" / "bookmarks.json"
    if dry_run:
        print("[DRY RUN] Would fetch tweets via:", mode)
        print(f"[DRY RUN] Input file: {input_file}")
        print(f"[DRY RUN] Limit: {limit}")
        raw_tweets = []
    else:
        raw_tweets = run_ingestion(mode=mode, input_file=input_file, limit=limit)
        raw_path.write_text(json.dumps([t.model_dump() for t in raw_tweets], indent=2))
        print(f"  Fetched {len(raw_tweets)} tweets → {raw_path}")

    if not raw_tweets and not dry_run:
        print("No tweets fetched. Check your API keys and input.")
        sys.exit(1)

    # --- Stage 2: Parser ---
    print("\n=== Stage 2: Parser ===")
    from agents.parser import run_parser

    parsed_path = DATA_DIR / "parsed" / "tweets_parsed.json"
    if dry_run:
        print("[DRY RUN] Would parse", len(raw_tweets), "tweets with Claude")
        parsed_tweets = []
    else:
        parsed_tweets = run_parser(raw_tweets)
        parsed_path.write_text(json.dumps([t.model_dump() for t in parsed_tweets], indent=2))
        print(f"  Parsed {len(parsed_tweets)} tweets → {parsed_path}")

    # --- Stage 3: Fact-Checker ---
    print("\n=== Stage 3: Fact-Checker ===")
    from agents.fact_checker import run_fact_checker

    verified_path = DATA_DIR / "verified" / "claims_verified.json"
    if dry_run:
        print("[DRY RUN] Would fact-check claims from", len(parsed_tweets), "tweets")
        verified_data = []
    else:
        verified_data = run_fact_checker(parsed_tweets)
        verified_path.write_text(json.dumps(verified_data, indent=2, default=str))
        print(f"  Verified claims → {verified_path}")

    # --- Stage 4: Strategy Tester ---
    print("\n=== Stage 4: Strategy Tester ===")
    from agents.strategy_tester import run_strategy_tester

    tested_path = DATA_DIR / "tested" / "strategies_tested.json"
    if dry_run:
        print("[DRY RUN] Would test strategies from", len(parsed_tweets), "tweets")
        tested_data = []
    else:
        tested_data = run_strategy_tester(parsed_tweets, verified_data)
        tested_path.write_text(json.dumps(tested_data, indent=2, default=str))
        print(f"  Tested strategies → {tested_path}")

    # --- Stage 5: Report Generator ---
    print("\n=== Stage 5: Report Generator ===")
    from agents.report_generator import run_report_generator

    if dry_run:
        print("[DRY RUN] Would generate report from all pipeline data")
        print("[DRY RUN] Pipeline structure validated successfully!")
    else:
        report = run_report_generator(parsed_tweets, verified_data, tested_data)
        findings_path = REPORTS_DIR / "findings.json"
        summary_path = REPORTS_DIR / "summary.md"
        findings_path.write_text(json.dumps(report.model_dump(), indent=2, default=str))
        summary_path.write_text(generate_summary_md(report))
        print(f"  Report → {findings_path}")
        print(f"  Summary → {summary_path}")

    print("\n=== Pipeline Complete ===")


def generate_summary_md(report) -> str:
    """Generate a human-readable markdown summary from the report."""
    from models.schemas import Report

    lines = ["# Tweet Analysis Report\n"]
    lines.append(f"Generated: {report.generated_at}\n")

    s = report.statistics
    lines.append("## Statistics\n")
    lines.append(f"- **Tweets analyzed:** {s.total_tweets}")
    lines.append(f"- **Total claims:** {s.total_claims}")
    lines.append(f"- **Verified:** {s.verified}")
    lines.append(f"- **Debunked:** {s.debunked}")
    lines.append(f"- **Partially true:** {s.partially_true}")
    lines.append(f"- **Unverifiable:** {s.unverifiable}")
    lines.append(f"- **Strategies viable:** {s.strategies_viable}")
    lines.append(f"- **Strategies dead:** {s.strategies_dead}")
    lines.append(f"- **Strategies risky:** {s.strategies_risky}")
    lines.append(f"- **Strategies scam:** {s.strategies_scam}")
    lines.append("")

    # Group findings by category
    by_category: dict[str, list] = {}
    for f in report.findings:
        cat = f.category
        by_category.setdefault(cat, []).append(f)

    for cat, findings in sorted(by_category.items()):
        lines.append(f"## {cat.upper()}\n")
        for f in findings:
            lines.append(f"### @{f.author} ([tweet]({f.url}))\n")
            lines.append(f"{f.summary}\n")
            if f.claims:
                lines.append("**Claims:**")
                for c in f.claims:
                    emoji = {"verified": "V", "debunked": "X", "partially_true": "~", "unverifiable": "?"}.get(
                        c.verdict, "?"
                    )
                    lines.append(f"- [{emoji}] {c.original.text} (confidence: {c.confidence:.0%})")
                lines.append("")
            if f.strategies:
                lines.append("**Strategies:**")
                for st in f.strategies:
                    lines.append(f"- [{st.status}] {st.original.description} (risk: {st.risk_level})")
                    if st.scam_indicators:
                        lines.append(f"  - Scam indicators: {', '.join(st.scam_indicators)}")
                lines.append("")
            if f.tools:
                lines.append("**Tools:**")
                for t in f.tools:
                    lines.append(f"- {t.name}: {t.description}")
                lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Tweet Analysis Agent Pipeline")
    parser.add_argument("--mode", choices=["urls", "bookmarks"], default="urls", help="Ingestion mode")
    parser.add_argument("--input", default="data/input/sample_urls.txt", help="Input file (for url mode)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of tweets to process")
    parser.add_argument("--dry-run", action="store_true", help="Validate pipeline without API calls")
    args = parser.parse_args()

    run_pipeline(mode=args.mode, input_file=args.input, limit=args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
