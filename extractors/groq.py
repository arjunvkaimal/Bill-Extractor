"""
Groq extractor — uses the groq SDK to call Llama vision models via Groq's
ultra-fast inference API. API format is OpenAI-compatible.
"""

import base64
import json
import logging
import os
import re
import time

from groq import Groq

from extractors.prompt import EXTRACTION_PROMPT

logger = logging.getLogger(__name__)

# Groq Qwen 3.6 27B vision pricing (per 1M tokens)
_INPUT_COST_PER_M = 0.18
_OUTPUT_COST_PER_M = 0.18
_MODEL = "qwen/qwen3.6-27b"


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost from token counts."""
    return (input_tokens * _INPUT_COST_PER_M + output_tokens * _OUTPUT_COST_PER_M) / 1_000_000


def extract_bill(image_path: str) -> dict:
    """
    Extract structured data from a bill image using Groq (Llama Vision).

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

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError("GROQ_API_KEY is not set in environment variables.")

    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        media_type = "image/jpeg"
        if image_path.lower().endswith(".png"):
            media_type = "image/png"

        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:{media_type};base64,{base64_image}"

        client = Groq(api_key=api_key)

        start = time.perf_counter()
        response = client.chat.completions.create(
            model=_MODEL,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": EXTRACTION_PROMPT,
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": data_url,
                            },
                        },
                    ],
                }
            ],
        )
        elapsed = time.perf_counter() - start

        raw_text = response.choices[0].message.content if response.choices else ""
        result["raw_model_response"] = raw_text
        result["latency_seconds"] = round(elapsed, 3)

        # Extract token usage for cost estimation
        input_tokens = 0
        output_tokens = 0
        if response.usage:
            input_tokens = response.usage.prompt_tokens or 0
            output_tokens = response.usage.completion_tokens or 0
        result["estimated_cost_usd"] = round(_estimate_cost(input_tokens, output_tokens), 6)

        # Strip markdown fences if present
        json_text = raw_text.strip()
        json_text = re.sub(r'^```(?:json)?\s*', '', json_text)
        json_text = re.sub(r'\s*```$', '', json_text)

        # Parse JSON from model response
        parsed = json.loads(json_text)
        for field in ("vendor_name", "invoice_number", "date", "amount", "currency", "gst_details"):
            if field in parsed:
                result[field] = parsed[field]

    except json.JSONDecodeError as e:
        logger.error("Groq returned non-JSON for %s: %s", image_path, e)
        result["raw_model_response"] = f"JSON_PARSE_ERROR: {result['raw_model_response']}"
    except Exception as e:
        logger.error("Groq extraction failed for %s: %s", image_path, e)
        result["raw_model_response"] = f"ERROR: {type(e).__name__}: {e}"

    return result
