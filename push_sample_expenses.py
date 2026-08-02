#!/usr/bin/env python3
"""
Push sample expenses — takes the best-performing model's results for a few
bills and creates real expense entries in Zoho Books.

Usage:
    python push_sample_expenses.py
    python push_sample_expenses.py --count 3
    python push_sample_expenses.py --provider gemini --count 5
"""

import argparse
import csv
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from zoho.create_expense import create_expense  # noqa: E402
from zoho.auth import get_access_token  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def find_best_provider(report_path: str) -> str:
    """Read report.csv and return the provider with the highest overall accuracy."""
    path = Path(report_path)
    if not path.is_file():
        logger.error("Report file not found: %s. Run scoring first.", report_path)
        sys.exit(1)

    best_provider = None
    best_accuracy = -1.0

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            if len(row) >= 5 and row[1].strip() == "OVERALL":
                provider = row[0].strip()
                try:
                    accuracy = float(row[4].strip())
                except ValueError:
                    continue
                if accuracy > best_accuracy:
                    best_accuracy = accuracy
                    best_provider = provider

    if best_provider is None:
        logger.error("Could not determine best provider from %s", report_path)
        sys.exit(1)

    logger.info("Best provider: %s (overall accuracy: %.1f%%)", best_provider, best_accuracy)
    return best_provider


def main():
    parser = argparse.ArgumentParser(
        description="Push sample bill extractions to Zoho Books as expenses."
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        help="Provider to use. If not specified, auto-selects the best from report.csv.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=5,
        help="Number of bills to push (default: 5).",
    )
    parser.add_argument(
        "--results-dir",
        type=str,
        default="./results",
        help="Directory containing provider result JSONs (default: ./results).",
    )
    parser.add_argument(
        "--report",
        type=str,
        default="results/report.csv",
        help="Path to report.csv for auto-selecting best provider.",
    )
    args = parser.parse_args()

    # Determine provider
    if args.provider:
        provider = args.provider.strip().lower()
    else:
        provider = find_best_provider(args.report)

    # Load provider results
    results_file = Path(args.results_dir) / f"{provider}.json"
    if not results_file.is_file():
        logger.error("Provider results not found: %s", results_file)
        sys.exit(1)

    with open(results_file, "r", encoding="utf-8") as f:
        all_results = json.load(f)

    # Select bills to push
    bill_keys = list(all_results.keys())[:args.count]
    if not bill_keys:
        logger.error("No bills found in %s", results_file)
        sys.exit(1)

    logger.info(
        "Pushing %d bill(s) from provider '%s' to Zoho Books...",
        len(bill_keys), provider,
    )

    # Get a single access token for all requests
    try:
        access_token = get_access_token()
    except Exception as e:
        logger.error("Failed to obtain Zoho access token: %s", e)
        sys.exit(1)

    created_ids = []
    for bill_key in bill_keys:
        extraction = all_results[bill_key]
        logger.info("Pushing %s ...", bill_key)

        try:
            expense_id = create_expense(extraction, access_token=access_token)
            created_ids.append(expense_id)
            logger.info("  ✓ Created expense: %s", expense_id)
        except Exception as e:
            logger.error("  ✗ Failed for %s: %s: %s", bill_key, type(e).__name__, e)

    # Summary
    print()
    print(f"{'=' * 50}")
    print(f"  Pushed {len(created_ids)}/{len(bill_keys)} expenses to Zoho Books")
    print(f"  Provider: {provider}")
    print(f"{'=' * 50}")
    if created_ids:
        print("  Created expense IDs:")
        for eid in created_ids:
            print(f"    • {eid}")
    print()


if __name__ == "__main__":
    main()
