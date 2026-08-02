# Taxor — Multi-LLM Bill Extraction Evaluator & Zoho Books Integration

Evaluate Gemini, Claude, and GPT-4o on extracting structured data from handwritten Indian bill/receipt images, score them against ground truth, and push the best model's results into Zoho Books as expenses.

## Setup

### 1. Clone & Install

```bash
git clone <repo-url>
cd taxor
pip install -r requirements.txt
```

### 2. Environment Variables

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `GOOGLE_API_KEY` | Google AI API key for Gemini |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude |
| `OPENAI_API_KEY` | OpenAI API key for GPT-4o |
| `ZOHO_CLIENT_ID` | Zoho OAuth client ID |
| `ZOHO_CLIENT_SECRET` | Zoho OAuth client secret |
| `ZOHO_REFRESH_TOKEN` | Zoho OAuth refresh token |
| `ZOHO_ORG_ID` | Your Zoho Books organization ID |
| `ZOHO_EXPENSE_ACCOUNT_ID` | Expense account ID (e.g., "Meals & Entertainment") |
| `ZOHO_PAID_THROUGH_ACCOUNT_ID` | Paid-through account ID (e.g., "Petty Cash") |

### 3. Images & Ground Truth

- Place bill images in `/images/` (`.jpg` or `.png`)
- Ensure `ground_truth.json` exists at the project root, keyed by filename stem

## Running Extraction

Run all three providers:
```bash
python run_extraction.py
```

Run a subset:
```bash
python run_extraction.py --providers gemini,claude
```

Custom directories:
```bash
python run_extraction.py --images-dir ./my_bills --output-dir ./my_results
```

Results are saved to `results/<provider>.json`.

## Running Scoring

Generate `report.csv` and `report.md`:
```bash
python -m eval.scorer
```

Print the comparison table to console:
```bash
python summarize_report.py
```

Options:
```bash
python -m eval.scorer --fuzzy-threshold 85
python summarize_report.py --report results/report.csv
```

## Pushing to Zoho Books

Push the best model's top 5 bills as expenses:
```bash
python push_sample_expenses.py
```

Override provider or count:
```bash
python push_sample_expenses.py --provider gemini --count 3
```

---

## Approach

Claude was excluded from the final accuracy comparison due to insufficient API credit — all 14 calls failed at the request level with a billing error before reaching the model, so the 33.7% figure seen in early testing does not reflect actual extraction capability. The pipeline is provider-agnostic and Claude extraction would run identically given API access.

### Challenges

**API access limits.** Anthropic and OpenAI trial credits were exhausted before extraction could run, which is why this evaluation compares Gemini and Groq rather than all three originally planned providers. Rather than delay the submission chasing paid credit for a screening task, I treated this as a scoping decision: ship a correct, honestly-documented two-model comparison instead of a broken three-model one.

**No access to real shop bills.** I didn't have a ready source of real handwritten bills, so I wrote all 14 myself — across different hotel/restaurant formats (South Indian tiffin centres, dhabas, bakeries, a roadside tea stall, etc.), varying handwriting speed and legibility, pen type, and paper (ruled notebook paper, plain paper, and torn slip paper for the more informal bills). This was a deliberate substitute for sourcing real bills, done to still get genuine variation in handwriting style, paper texture, and bill format/completeness (some bills omit invoice numbers or GST lines entirely, matching how small vendors actually write bills). Because I authored every bill myself, I had exact ground-truth values to score against, with no ambiguity about what the "correct" answer was.

**Parsing failures that looked like accuracy failures.** Groq's initial results scored artificially low (41.8% overall) not because the model misread the bills, but because its raw output wrapped the JSON in a `<think>...</think>` reasoning block that broke naive `json.loads()` parsing, and it used `total_amount` instead of the expected `amount` key. Inspecting `raw_model_response` directly (rather than trusting the scored output) showed Groq had actually extracted every field correctly. After fixing the parser to strip reasoning tags and normalize field names, Groq's real accuracy came out to 85.7% — a good reminder that a low score can mean "bad extraction" or "bad parsing," and it's worth checking the raw model output before drawing conclusions from either.

## Results (14 Sample Indian Bills)

### Per-Field Accuracy (%)

| Field | gemini | groq |
|---|---|---|
| Vendor Name | 92.9% | 100.0% |
| Invoice Number | 92.9% | 92.9% |
| Date | 92.9% | 64.3% |
| Amount | 92.9% | 92.9% |
| Currency | 100.0% | 100.0% |
| GST Details | 100.0% | 71.4% |
| Line Items | 71.4% | 78.6% |
| **OVERALL** | **91.8%** | **85.7%** |

### Hallucination Count

| Field | gemini | groq |
|---|---|---|
| Vendor Name | 1 | 0 |
| Invoice Number | 0 | 0 |
| Date | 0 | 0 |
| Amount | 0 | 0 |
| Currency | 0 | 0 |
| GST Details | 0 | 0 |
| Line Items | 0 | 0 |

*Note: Gemini hallucinated a vendor name on a handwritten tea stall bill that did not contain one. Groq correctly returned null.*

### Performance & Cost

| Metric | gemini | groq |
|---|---|---|
| Avg Latency (s) | 7.121 | 26.859 |
| Cost / 100 bills (USD) | $0.0861 | $0.0463 |

## Eval Methodology

Each of the 14 bills was scored per field against a hand-authored `ground_truth.json`, rather than using one blended accuracy score, so failure patterns per field are visible instead of averaged away.

- **vendor_name, gst_details, line item names** — fuzzy string matching (rapidfuzz), to tolerate minor OCR spelling variation without treating it as a wrong answer
- **invoice_number, date** — exact match after normalization (whitespace stripped, dates normalized to ISO format) since these fields have no acceptable "close enough"
- **amount** — numeric match within a ₹1 tolerance, to allow for rounding without masking real extraction errors
- **currency** — exact match
- **line_items** — each bill's item list compared against ground truth for count, item name (fuzzy), and per-item amount

**Hallucination tracking:** where ground truth for a field was `null` (i.e., the bill genuinely didn't contain that information, such as the tea stall bill with no shop name written), the model's output was checked for whether it also returned null. A model returning a fabricated value where none existed on the source bill was logged separately as a hallucination rather than just marked "incorrect" — this distinction matters specifically because this data is destined for accounting software, where an invented vendor name is a materially worse failure than a missing one.

**Cost and latency** were captured per call and extrapolated to a 100-bill run, to make the tradeoff between accuracy, speed, and cost comparable at a realistic operating volume rather than just on this 14-bill sample.

## Recommendation

**Gemini is the better choice for this use case**, despite Groq's respectable 85.7% overall accuracy and lower per-call cost. Three reasons:

1. **Reliability on the fields that matter most for bookkeeping.** Gemini scored 92.9% on `date` and 100% on `gst_details` versus Groq's 64.3% and 71.4% — these are exactly the fields an accounting system can't silently get wrong, since a wrong date miscategorizes an expense period and a wrong/missing GST figure has real compliance implications.

2. **Hallucination behavior slightly favors Groq, but it's a single data point.** Groq correctly returned `null` for the vendor-less tea stall bill, while Gemini invented a name. This is worth flagging and monitoring at scale, but on a sample of 14 it's not enough to outweigh Gemini's much stronger performance on the higher-stakes date/GST fields. If this pattern held up over a larger sample, it would push toward adding an explicit "do not guess — return null if illegible or absent" instruction reinforcement in the prompt for whichever model is used in production, rather than switching models on this basis alone.

3. **Latency is a real Groq weakness here.** 26.9s average latency is unusually high for a platform whose main selling point is speed, and is worse than Gemini's 7.1s. Combined with the earlier JSON-parsing fragility (reasoning tokens leaking into output), Groq's pipeline currently needs more defensive engineering around it than Gemini's to be production-safe.

**Cost is a secondary factor here** — both providers are inexpensive at this volume ($0.086 vs $0.046 per 100 bills), so the ~$0.04 difference per 100 bills is not large enough to offset a ~6-point accuracy gap on fields with direct compliance/bookkeeping consequences.

**If I were shipping this for real use**, I'd run Gemini as the primary extractor, with Groq (or a second Gemini pass) as a lower-cost secondary check specifically on the `line_items` field, since that's the one field where Groq actually outperformed Gemini (78.6% vs 71.4%) — a lightweight ensemble rather than a single-model decision. I'd also want to re-run this comparison with Claude included once API credit is available, since its actual accuracy remains unverified.