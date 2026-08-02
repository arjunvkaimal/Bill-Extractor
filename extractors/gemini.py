"""
Gemini extractor — uses the google-genai SDK to call Gemini 2.5 Flash vision API.
"""

import json
import logging
import os
import re
import time

from google import genai
from google.genai import types

from extractors.prompt import EXTRACTION_PROMPT

logger = logging.getLogger(__name__)

# Gemini 2.5 Flash pricing (per 1M tokens)
_INPUT_COST_PER_M = 0.30
_OUTPUT_COST_PER_M = 2.50
_MODEL = "gemini-3.5-flash"


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost from token counts."""
    return (input_tokens * _INPUT_COST_PER_M + output_tokens * _OUTPUT_COST_PER_M) / 1_000_000


def extract_bill(image_path: str) -> dict:
    """
    Extract structured data from a bill image using Gemini 2.5 Flash.

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

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise EnvironmentError("GOOGLE_API_KEY is not set in environment variables.")

    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        mime_type = "image/jpeg"
        if image_path.lower().endswith(".png"):
            mime_type = "image/png"

        client = genai.Client(api_key=api_key)

        start = time.perf_counter()
        response = client.models.generate_content(
            model=_MODEL,
            contents=[
                EXTRACTION_PROMPT,
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            ],
        )
        elapsed = time.perf_counter() - start

        raw_text = response.text or ""
        result["raw_model_response"] = raw_text
        result["latency_seconds"] = round(elapsed, 3)

        # Extract token usage for cost estimation
        input_tokens = 0
        output_tokens = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
            output_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

        result["estimated_cost_usd"] = round(_estimate_cost(input_tokens, output_tokens), 6)

        # Strip markdown fences if present (Gemini often wraps in ```json...```)
        json_text = raw_text.strip()
        json_text = re.sub(r'^```(?:json)?\s*', '', json_text)
        json_text = re.sub(r'\s*```$', '', json_text)

        # Parse JSON from model response
        parsed = json.loads(json_text)
        for field in ("vendor_name", "invoice_number", "date", "amount", "currency", "gst_details"):
            if field in parsed:
                result[field] = parsed[field]

    except json.JSONDecodeError as e:
        logger.error("Gemini returned non-JSON for %s: %s", image_path, e)
        result["raw_model_response"] = f"JSON_PARSE_ERROR: {result['raw_model_response']}"
    except Exception as e:
        logger.error("Gemini extraction failed for %s: %s", image_path, e)
        result["raw_model_response"] = f"ERROR: {type(e).__name__}: {e}"

    return result
