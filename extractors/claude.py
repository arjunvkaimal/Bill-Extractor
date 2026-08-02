"""
Claude extractor — uses the anthropic SDK to call Claude Sonnet 4 vision API.
"""

import base64
import json
import logging
import os
import time

import anthropic

from extractors.prompt import EXTRACTION_PROMPT

logger = logging.getLogger(__name__)

# Claude Sonnet 4 pricing (per 1M tokens)
_INPUT_COST_PER_M = 3.00
_OUTPUT_COST_PER_M = 15.00
_MODEL = "claude-sonnet-4-20250514"


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost from token counts."""
    return (input_tokens * _INPUT_COST_PER_M + output_tokens * _OUTPUT_COST_PER_M) / 1_000_000


def extract_bill(image_path: str) -> dict:
    """
    Extract structured data from a bill image using Claude Sonnet 4.

    Args:
        image_path: Absolute or relative path to the bill image.

    Returns:
        dict with vendor_name, invoice_number, date, amount, currency,
        gst_details, raw_model_response, latency_seconds, estimated_cost_usd.
    """
    result = {
        "vendor_name": None,
        "invoice_number": None,
        "date": None,
        "amount": None,
        "currency": "INR",
        "gst_details": None,
        "raw_model_response": "",
        "latency_seconds": 0.0,
        "estimated_cost_usd": 0.0,
    }

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY is not set in environment variables.")

    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        media_type = "image/jpeg"
        if image_path.lower().endswith(".png"):
            media_type = "image/png"

        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        client = anthropic.Anthropic(api_key=api_key)

        start = time.perf_counter()
        message = client.messages.create(
            model=_MODEL,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64_image,
                            },
                        },
                        {
                            "type": "text",
                            "text": EXTRACTION_PROMPT,
                        },
                    ],
                }
            ],
        )
        elapsed = time.perf_counter() - start

        raw_text = message.content[0].text if message.content else ""
        result["raw_model_response"] = raw_text
        result["latency_seconds"] = round(elapsed, 3)

        # Extract token usage for cost estimation
        input_tokens = getattr(message.usage, "input_tokens", 0) or 0
        output_tokens = getattr(message.usage, "output_tokens", 0) or 0
        result["estimated_cost_usd"] = round(_estimate_cost(input_tokens, output_tokens), 6)

        # Parse JSON from model response
        parsed = json.loads(raw_text)
        for field in ("vendor_name", "invoice_number", "date", "amount", "currency", "gst_details"):
            if field in parsed:
                result[field] = parsed[field]

    except json.JSONDecodeError as e:
        logger.error("Claude returned non-JSON for %s: %s", image_path, e)
        result["raw_model_response"] = f"JSON_PARSE_ERROR: {result['raw_model_response']}"
    except Exception as e:
        logger.error("Claude extraction failed for %s: %s", image_path, e)
        result["raw_model_response"] = f"ERROR: {type(e).__name__}: {e}"

    return result
