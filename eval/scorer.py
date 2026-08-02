#!/usr/bin/env python3
"""
Scorer — loads ground truth and provider results, scores each field separately,
and generates report.csv + report.md.

Usage:
    python -m eval.scorer
    python -m eval.scorer --ground-truth ground_truth.json --results-dir results --output-dir results
"""

import argparse
import csv
import json
import logging
import sys
from datetime import date as date_type
from pathlib import Path

from rapidfuzz import fuzz

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

SCORED_FIELDS = ["vendor_name", "invoice_number", "date", "amount", "currency", "gst_details", "line_items"]


# ---------------------------------------------------------------------------
# Field-level scoring functions
# ---------------------------------------------------------------------------

def _normalize_str(val) -> str | None:
    """Strip and lowercase a string value, return None for null/empty."""
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _normalize_invoice(val) -> str | None:
    """Normalize invoice number: strip whitespace and common separators."""
    if val is None:
        return None
    s = str(val).strip()
    # Remove common separators for comparison
    for ch in "-/#. ":
        s = s.replace(ch, "")
    return s.upper() if s else None


def _parse_date(val) -> date_type | None:
    """Try to parse a date string in ISO format."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    try:
        return date_type.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def score_field(field: str, pred_val, truth_val, fuzzy_threshold: int = 80) -> dict:
    """
    Score a single field.

    Returns:
        {"correct": bool, "details": str}
    """
    # Both null → correct
    pred_is_null = pred_val is None or (isinstance(pred_val, str) and not pred_val.strip())
    truth_is_null = truth_val is None or (isinstance(truth_val, str) and not truth_val.strip())

    if pred_is_null and truth_is_null:
        return {"correct": True, "details": "both null"}

    # One null, other not → incorrect
    if pred_is_null and not truth_is_null:
        return {"correct": False, "details": f"predicted null, expected '{truth_val}'"}
    if not pred_is_null and truth_is_null:
        return {"correct": False, "details": f"predicted '{pred_val}', expected null"}

    # --- Field-specific scoring ---

    if field in ("vendor_name", "gst_details"):
        # Fuzzy match
        p = _normalize_str(pred_val).lower()
        t = _normalize_str(truth_val).lower()
        ratio = fuzz.ratio(p, t)
        correct = ratio >= fuzzy_threshold
        return {"correct": correct, "details": f"fuzzy={ratio:.1f} (threshold={fuzzy_threshold})"}

    elif field == "invoice_number":
        p = _normalize_invoice(pred_val)
        t = _normalize_invoice(truth_val)
        correct = p == t
        return {"correct": correct, "details": f"normalized: '{p}' vs '{t}'"}

    elif field == "date":
        p_date = _parse_date(pred_val)
        t_date = _parse_date(truth_val)
        if p_date is None or t_date is None:
            return {"correct": False, "details": f"parse failed: '{pred_val}' vs '{truth_val}'"}
        correct = p_date == t_date
        return {"correct": correct, "details": f"{p_date} vs {t_date}"}

    elif field == "amount":
        try:
            p_amt = float(pred_val)
            t_amt = float(truth_val)
        except (ValueError, TypeError):
            return {"correct": False, "details": f"non-numeric: '{pred_val}' vs '{truth_val}'"}
        diff = abs(p_amt - t_amt)
        correct = diff <= 1.0
        return {"correct": correct, "details": f"diff=₹{diff:.2f} (tolerance=₹1.00)"}

    elif field == "currency":
        p = _normalize_str(pred_val)
        t = _normalize_str(truth_val)
        correct = (p or "").upper() == (t or "").upper()
        return {"correct": correct, "details": f"'{p}' vs '{t}'"}

    elif field == "line_items":
        if not isinstance(pred_val, list): pred_val = []
        if not isinstance(truth_val, list): truth_val = []
        
        if not truth_val and not pred_val:
            return {"correct": True, "details": "both empty"}
            
        correct_count = 0
        for t_item in truth_val:
            t_name = _normalize_str(t_item.get("item_name")) or ""
            t_price = t_item.get("price")
            
            matched = False
            for p_item in pred_val:
                p_name = _normalize_str(p_item.get("item_name")) or ""
                p_price = p_item.get("price")
                
                # Check name match
                if fuzz.ratio(p_name.lower(), t_name.lower()) >= fuzzy_threshold:
                    # Check price
                    try:
                        price_diff = abs(float(p_price) - float(t_price))
                    except (ValueError, TypeError):
                        price_diff = 999.0
                        
                    if price_diff <= 1.0:
                        matched = True
                        break
            if matched:
                correct_count += 1
                
        correct = (correct_count == len(truth_val) and len(pred_val) == len(truth_val))
        return {"correct": correct, "details": f"{correct_count}/{len(truth_val)} matched (pred length {len(pred_val)})"}

    else:
        return {"correct": False, "details": f"unknown field '{field}'"}


def score_single(prediction: dict, ground_truth: dict, fuzzy_threshold: int = 80) -> dict:
    """Score all fields for a single bill."""
    return {
        field: score_field(field, prediction.get(field), ground_truth.get(field), fuzzy_threshold)
        for field in SCORED_FIELDS
    }


def score_provider(provider_results: dict, ground_truth: dict, fuzzy_threshold: int = 80) -> dict:
    """
    Score a provider's results across all bills.

    Returns:
        {
            "per_bill": {bill_key: {field: {correct, details}}},
            "per_field": {field: {"correct": int, "total": int, "accuracy": float}},
            "overall": {"correct": int, "total": int, "accuracy": float},
            "avg_latency": float,
            "total_cost": float,
            "cost_per_100": float,
        }
    """
    per_bill = {}
    field_counts = {f: {"correct": 0, "total": 0} for f in SCORED_FIELDS}
    total_correct = 0
    total_fields = 0
    latencies = []
    costs = []

    for bill_key, truth in ground_truth.items():
        pred = provider_results.get(bill_key)
        if pred is None:
            logger.warning("Provider missing result for bill: %s", bill_key)
            # Count all fields as incorrect
            per_bill[bill_key] = {f: {"correct": False, "details": "missing from results"} for f in SCORED_FIELDS}
            for f in SCORED_FIELDS:
                field_counts[f]["total"] += 1
                total_fields += 1
            continue

        scores = score_single(pred, truth, fuzzy_threshold)
        per_bill[bill_key] = scores

        latencies.append(pred.get("latency_seconds", 0))
        costs.append(pred.get("estimated_cost_usd", 0))

        for f in SCORED_FIELDS:
            field_counts[f]["total"] += 1
            total_fields += 1
            if scores[f]["correct"]:
                field_counts[f]["correct"] += 1
                total_correct += 1

    per_field = {}
    for f in SCORED_FIELDS:
        total = field_counts[f]["total"]
        correct = field_counts[f]["correct"]
        per_field[f] = {
            "correct": correct,
            "total": total,
            "accuracy": (correct / total * 100) if total > 0 else 0.0,
        }

    num_bills = len(ground_truth)
    total_cost = sum(costs)
    avg_latency = (sum(latencies) / len(latencies)) if latencies else 0.0
    cost_per_100 = (total_cost / num_bills * 100) if num_bills > 0 else 0.0

    return {
        "per_bill": per_bill,
        "per_field": per_field,
        "overall": {
            "correct": total_correct,
            "total": total_fields,
            "accuracy": (total_correct / total_fields * 100) if total_fields > 0 else 0.0,
        },
        "avg_latency": round(avg_latency, 3),
        "total_cost": round(total_cost, 6),
        "cost_per_100": round(cost_per_100, 4),
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(
    ground_truth_path: str,
    results_dir: str,
    output_dir: str,
    fuzzy_threshold: int = 80,
):
    """
    Load ground truth + all provider results, score, and write report.csv + report.md.
    """
    gt_path = Path(ground_truth_path)
    if not gt_path.is_file():
        logger.error("Ground truth file not found: %s", ground_truth_path)
        sys.exit(1)

    with open(gt_path, "r", encoding="utf-8") as f:
        ground_truth = json.load(f)

    results_path = Path(results_dir)
    provider_files = sorted(results_path.glob("*.json"))
    # Exclude report files
    provider_files = [p for p in provider_files if p.stem not in ("report",)]

    if not provider_files:
        logger.error("No provider result files found in %s", results_dir)
        sys.exit(1)

    all_scores = {}
    for pf in provider_files:
        provider_name = pf.stem
        logger.info("Scoring provider: %s", provider_name)
        with open(pf, "r", encoding="utf-8") as f:
            provider_results = json.load(f)
        all_scores[provider_name] = score_provider(provider_results, ground_truth, fuzzy_threshold)

    # --- Write CSV ---
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    csv_file = out_path / "report.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["provider", "field", "correct", "total", "accuracy_%"])

        for provider, scores in sorted(all_scores.items()):
            for field in SCORED_FIELDS:
                pf_data = scores["per_field"][field]
                writer.writerow([
                    provider, field,
                    pf_data["correct"], pf_data["total"],
                    f"{pf_data['accuracy']:.1f}",
                ])
            # Summary rows
            writer.writerow([
                provider, "OVERALL",
                scores["overall"]["correct"], scores["overall"]["total"],
                f"{scores['overall']['accuracy']:.1f}",
            ])
            writer.writerow([provider, "avg_latency_s", "", "", f"{scores['avg_latency']:.3f}"])
            writer.writerow([provider, "cost_per_100_bills_usd", "", "", f"${scores['cost_per_100']:.4f}"])
            writer.writerow([])  # blank separator

    logger.info("CSV report written to %s", csv_file)

    # --- Write Markdown ---
    md_file = out_path / "report.md"
    with open(md_file, "w", encoding="utf-8") as f:
        f.write("# Bill Extraction — Model Comparison Report\n\n")

        # Per-field accuracy table
        f.write("## Per-Field Accuracy (%)\n\n")
        providers = sorted(all_scores.keys())
        header = "| Field | " + " | ".join(providers) + " |\n"
        sep = "|---|" + "|".join(["---"] * len(providers)) + "|\n"
        f.write(header)
        f.write(sep)

        for field in SCORED_FIELDS:
            row = f"| {field} |"
            for prov in providers:
                acc = all_scores[prov]["per_field"][field]["accuracy"]
                row += f" {acc:.1f}% |"
            f.write(row + "\n")

        # Overall row
        row = "| **OVERALL** |"
        for prov in providers:
            acc = all_scores[prov]["overall"]["accuracy"]
            row += f" **{acc:.1f}%** |"
        f.write(row + "\n")

        f.write("\n## Performance & Cost\n\n")
        f.write("| Metric | " + " | ".join(providers) + " |\n")
        f.write("|---|" + "|".join(["---"] * len(providers)) + "|\n")

        row = "| Avg Latency (s) |"
        for prov in providers:
            row += f" {all_scores[prov]['avg_latency']:.3f} |"
        f.write(row + "\n")

        row = "| Cost / 100 bills (USD) |"
        for prov in providers:
            row += f" ${all_scores[prov]['cost_per_100']:.4f} |"
        f.write(row + "\n")

    logger.info("Markdown report written to %s", md_file)


def main():
    parser = argparse.ArgumentParser(description="Score LLM extraction results against ground truth.")
    parser.add_argument("--ground-truth", default="ground_truth.json", help="Path to ground truth JSON")
    parser.add_argument("--results-dir", default="./results", help="Directory with provider result JSONs")
    parser.add_argument("--output-dir", default="./results", help="Directory to write reports")
    parser.add_argument("--fuzzy-threshold", type=int, default=80, help="Fuzzy match threshold (0-100)")
    args = parser.parse_args()

    generate_report(args.ground_truth, args.results_dir, args.output_dir, args.fuzzy_threshold)


if __name__ == "__main__":
    main()
