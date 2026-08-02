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

[FILL IN]

## Eval Methodology

[FILL IN]

## Results Table

[FILL IN]

## Recommendation

[FILL IN]
