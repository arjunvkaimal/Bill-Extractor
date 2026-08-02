#!/usr/bin/env python3
"""
Summarize report — reads results/report.csv and prints a clean comparison
table to the console using tabulate.

Usage:
    python summarize_report.py
    python summarize_report.py --report results/report.csv
"""

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

from tabulate import tabulate

FIELD_SHORT = {
    "vendor_name": "vendor",
    "invoice_number": "inv_num",
    "date": "date",
    "amount": "amount",
    "currency": "curr",
    "gst_details": "gst",
}

DISPLAY_FIELDS = ["vendor_name", "invoice_number", "date", "amount", "currency", "gst_details"]


def load_report(report_path: str) -> dict:
    """
    Parse report.csv into a nested dict:
    {provider: {field: accuracy_str, "overall": ..., "avg_latency_s": ..., "cost_per_100": ...}}
    """
    path = Path(report_path)
    if not path.is_file():
        print(f"ERROR: Report file not found: {report_path}", file=sys.stderr)
        print("Run scoring first:  python -m eval.scorer", file=sys.stderr)
        sys.exit(1)

    data = defaultdict(dict)

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # skip header

        for row in reader:
            if not row or not row[0].strip():
                continue

            provider = row[0].strip()
            field = row[1].strip()
            accuracy = row[4].strip() if len(row) > 4 else ""

            if field == "OVERALL":
                data[provider]["overall"] = f"{accuracy}%"
            elif field == "avg_latency_s":
                data[provider]["avg_lat"] = f"{accuracy}s"
            elif field == "cost_per_100_bills_usd":
                data[provider]["cost/100"] = accuracy
            elif field in DISPLAY_FIELDS:
                data[provider][field] = f"{accuracy}%"

    return dict(data)


def print_table(data: dict):
    """Print a formatted comparison table."""
    if not data:
        print("No data to display.")
        return

    headers = ["Provider"]
    for f in DISPLAY_FIELDS:
        headers.append(FIELD_SHORT[f])
    headers.extend(["overall", "avg_lat", "cost/100"])

    rows = []
    for provider in sorted(data.keys()):
        pdata = data[provider]
        row = [provider]
        for f in DISPLAY_FIELDS:
            row.append(pdata.get(f, "—"))
        row.append(pdata.get("overall", "—"))
        row.append(pdata.get("avg_lat", "—"))
        row.append(pdata.get("cost/100", "—"))
        rows.append(row)

    print()
    print(tabulate(rows, headers=headers, tablefmt="fancy_grid"))
    print()


def main():
    parser = argparse.ArgumentParser(description="Print a summary comparison table from the scoring report.")
    parser.add_argument("--report", default="results/report.csv", help="Path to report.csv")
    args = parser.parse_args()

    data = load_report(args.report)
    print_table(data)


if __name__ == "__main__":
    main()
