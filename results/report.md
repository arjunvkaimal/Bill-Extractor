# Bill Extraction — Model Comparison Report

## Per-Field Accuracy (%)

| Field | gemini | groq |
|---|---|---|
| vendor_name | 92.9% | 100.0% |
| invoice_number | 92.9% | 92.9% |
| date | 92.9% | 64.3% |
| amount | 92.9% | 92.9% |
| currency | 100.0% | 100.0% |
| gst_details | 100.0% | 71.4% |
| line_items | 71.4% | 78.6% |
| **OVERALL** | **91.8%** | **85.7%** |

## Hallucination Count

| Field | gemini | groq |
|---|---|---|
| vendor_name | 1 | 0 |
| invoice_number | 0 | 0 |
| date | 0 | 0 |
| amount | 0 | 0 |
| currency | 0 | 0 |
| gst_details | 0 | 0 |
| line_items | 0 | 0 |

## Performance & Cost

| Metric | gemini | groq |
|---|---|---|
| Avg Latency (s) | 7.121 | 26.859 |
| Cost / 100 bills (USD) | $0.0861 | $0.0463 |
