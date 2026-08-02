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

I set out to test Gemini, Claude, and Groq on the same 14 bills, but Claude ended up excluded from the final numbers. Every Claude call failed with a billing error before it even reached the model — that's an account credit problem, not the model being bad at reading bills. So the 33.7% you might see in an earlier version of this report isn't real; I'm not including it. The code for Claude extraction is still there and works the same way as the others, so if credit gets added later it's a one-line rerun.

### Challenges

**Ran out of API credit for two providers.** Both Anthropic and OpenAI's trial credits were gone before I could run extraction. Rather than wait around trying to get paid credit sorted for a screening task, I decided to just work with what I had — Gemini and Groq — and be upfront about why the third one is missing instead of quietly leaving in numbers that don't mean anything.

**Didn't have real handwritten bills lying around.** I don't have easy access to a stack of real shop bills, so I wrote all 14 myself. I tried to make them genuinely different from each other — different hotel/restaurant types (tiffin centres, a dhaba, a bakery, a roadside tea stall), different handwriting speed and neatness, different pens, different paper (ruled notebook pages, plain paper, and a scrappy torn slip for the tea stall one). Some bills skip the invoice number or GST line on purpose, since that's how small vendors actually write bills half the time. Writing them myself also meant I knew the exact correct answer for every field, so there was no guesswork in building the ground truth.

**Groq looked bad at first, but it was actually a parsing bug on my end.** Groq's first-run accuracy came out to 41.8%, which looked like a real problem. When I checked the raw model response instead of just trusting the score, I found Groq had actually read every bill correctly — the model just wraps its answer in a `<think>...</think>` reasoning block before the JSON, and my parser was choking on that. It also called the total field `total_amount` instead of `amount`. Once I fixed the parser to strip the reasoning block and normalize field names, Groq's real accuracy came out to 85.7%. Good lesson: a low score can mean the model messed up, or it can mean my code messed up, and you have to check the raw output to know which.

## Results (14 Sample Indian Bills)

### Per-Field Accuracy (%)

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

### Hallucination Count

| Field | gemini | groq |
|---|---|---|
| vendor_name | 1 | 0 |
| invoice_number | 0 | 0 |
| date | 0 | 0 |
| amount | 0 | 0 |
| currency | 0 | 0 |
| gst_details | 0 | 0 |
| line_items | 0 | 0 |

*Note: Gemini hallucinated a vendor name on a handwritten tea stall bill that did not contain one. Groq correctly returned null.*

### Performance & Cost

| Metric | gemini | groq |
|---|---|---|
| Avg Latency (s) | 7.121 | 26.859 |
| Cost / 100 bills (USD) | $0.0861 | $0.0463 |

## Eval Methodology

I scored each field separately against my hand-written `ground_truth.json`, instead of one combined accuracy number, because a single blended score hides exactly where a model is failing.

- **vendor_name, gst_details, line item names** — fuzzy match (rapidfuzz), so small spelling variations from OCR don't get marked wrong when they're basically right
- **invoice_number, date** — exact match after normalizing whitespace and date format, since these need to be exactly right, not close
- **amount** — matched within ₹1, to allow for rounding without letting real mistakes slip through
- **currency** — exact match
- **line_items** — compared count, item name (fuzzy), and price per item against ground truth

I also tracked hallucinations separately. If ground truth for a field was null — meaning the bill genuinely didn't have that info, like the tea stall bill with no shop name — I checked whether the model also said null, or made something up instead. A model inventing a vendor name where there wasn't one is a worse failure than just missing a field, especially since this data is going straight into accounting software, so I didn't want that to get buried inside a generic "incorrect" count.

I also recorded latency and cost per call, then scaled it up to what 100 bills would cost, since accuracy alone doesn't tell the whole story if one model is much slower or pricier at real volume.

## Recommendation

I'd go with Gemini for this.

Groq did fine overall — 85.7% isn't bad, and it's cheaper. But it fell down on exactly the fields you can't afford to get wrong in bookkeeping: only 64.3% on date and 71.4% on GST details, against Gemini's 92.9% and 100%. A wrong date puts an expense in the wrong period. A wrong or missing GST figure is a compliance problem, not just a data quality one. That's enough on its own to make the call.

The one place Groq actually did better was on the null case — it correctly said "I don't know" on the bill with no vendor name, while Gemini made one up. That's a real point in Groq's favor and worth taking seriously, but it's one data point out of 14, and it doesn't outweigh Gemini being meaningfully more reliable on the fields that actually matter most. If I saw this hallucination pattern hold up over a bigger sample, my first move would be to just tighten the prompt — tell the model explicitly not to guess — rather than switch models over it.

Groq was also slow — 26.9 seconds average, versus Gemini's 7.1 — and its output needed extra cleanup work just to parse reliably (the `<think>` block issue). That's more fragility to maintain long-term.

Cost difference between the two is small enough not to matter here — a few cents per 100 bills either way.

If I were actually shipping this, I'd use Gemini as the main extractor, and maybe run Groq as a cheap second opinion specifically on line items, since that's the one field it beat Gemini on. I'd also want to redo this whole comparison with Claude once there's actual credit to test it — right now I genuinely don't know how it would perform.