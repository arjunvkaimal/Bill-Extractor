#!/usr/bin/env python3
"""
CLI runner — extracts structured data from all bill images using one or more
LLM providers and saves results to /results/<provider>.json.

Usage:
    python run_extraction.py
    python run_extraction.py --providers gemini,claude
    python run_extraction.py --providers openai --images-dir ./my_images
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from extractors import PROVIDERS  # noqa: E402 (must come after load_dotenv)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def discover_images(images_dir: str) -> list[Path]:
    """Find all supported image files in the given directory, sorted by name."""
    images_path = Path(images_dir)
    if not images_path.is_dir():
        logger.error("Images directory does not exist: %s", images_dir)
        sys.exit(1)

    images = sorted(
        p for p in images_path.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    if not images:
        logger.error("No image files found in %s", images_dir)
        sys.exit(1)

    logger.info("Discovered %d image(s) in %s", len(images), images_dir)
    return images


def run_provider(provider_name: str, extract_fn, images: list[Path]) -> dict:
    """Run extraction for a single provider across all images."""
    results = {}
    successes = 0
    failures = 0

    rate_limit_delay = _RATE_LIMITED_PROVIDERS.get(provider_name, 0)

    for idx, img_path in enumerate(images):
        bill_key = img_path.stem  # e.g. "bill_01_sri_krishna_bhavan"

        # Rate limiting: sleep between requests (skip first request)
        if rate_limit_delay and idx > 0:
            logger.info("[%s] Rate limit: waiting %ds...", provider_name, rate_limit_delay)
            time.sleep(rate_limit_delay)

        logger.info("[%s] Processing %s ...", provider_name, bill_key)

        try:
            result = extract_fn(str(img_path))
            results[bill_key] = result

            if result.get("raw_model_response", "").startswith("ERROR:"):
                failures += 1
                logger.warning(
                    "[%s] %s — extraction returned error: %s",
                    provider_name, bill_key, result["raw_model_response"][:120],
                )
            else:
                successes += 1
                logger.info(
                    "[%s] %s — OK (%.2fs, $%.6f)",
                    provider_name, bill_key,
                    result.get("latency_seconds", 0),
                    result.get("estimated_cost_usd", 0),
                )
        except Exception as e:
            failures += 1
            logger.error("[%s] %s — UNHANDLED ERROR: %s: %s", provider_name, bill_key, type(e).__name__, e)
            results[bill_key] = {
                "vendor_name": None,
                "invoice_number": None,
                "date": None,
                "amount": None,
                "currency": "INR",
                "gst_details": None,
                "raw_model_response": f"UNHANDLED_ERROR: {type(e).__name__}: {e}",
                "latency_seconds": 0.0,
                "estimated_cost_usd": 0.0,
            }

    logger.info(
        "[%s] Done — %d/%d succeeded, %d failed",
        provider_name, successes, len(images), failures,
    )
    return results


# Providers that need rate limiting (free tier limits)
_RATE_LIMITED_PROVIDERS = {
    "gemini": 13,  # 5 req/min → 1 every 12s, use 13s for safety
    "groq": 30,    # 8000 TPM limit
}


def main():
    parser = argparse.ArgumentParser(
        description="Run LLM bill extraction across all images."
    )
    parser.add_argument(
        "--providers",
        type=str,
        default=",".join(PROVIDERS.keys()),
        help="Comma-separated list of providers to run (default: all). "
             f"Available: {', '.join(PROVIDERS.keys())}",
    )
    parser.add_argument(
        "--images-dir",
        type=str,
        default="./images",
        help="Directory containing bill images (default: ./images)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./results",
        help="Directory to write result JSON files (default: ./results)",
    )
    args = parser.parse_args()

    # Validate providers
    requested = [p.strip().lower() for p in args.providers.split(",") if p.strip()]
    invalid = [p for p in requested if p not in PROVIDERS]
    if invalid:
        logger.error(
            "Unknown provider(s): %s. Available: %s",
            ", ".join(invalid), ", ".join(PROVIDERS.keys()),
        )
        sys.exit(1)

    # Discover images
    images = discover_images(args.images_dir)

    # Ensure output directory exists
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Run each provider
    for provider_name in requested:
        extract_fn = PROVIDERS[provider_name]
        logger.info("=" * 60)
        logger.info("Starting extraction with provider: %s", provider_name)
        logger.info("=" * 60)

        results = run_provider(provider_name, extract_fn, images)

        # Save results
        output_file = output_dir / f"{provider_name}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        logger.info("Results saved to %s", output_file)

    logger.info("All done.")


if __name__ == "__main__":
    main()
