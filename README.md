# Chrome & Oak — Sales & Finance

Option B for the SCS hackathon: understand where sales growth fails to translate into margin and cash, then build a focused tool for staff to act on it. Two people, four hours.

Start with the [executed EDA notebook](output/jupyter-notebook/chrome_and_oak_eda.ipynb) or download the [HTML companion](output/jupyter-notebook/chrome_and_oak_eda.html). The [selected scenario and shared challenge requirements](references/sales_finance_brief.txt) are included.

The notebook contains 37 code cells and 115 figures across 15 sections. It covers data quality, sales trends, discounts, margins, returns, payment timing, credit exposure, customer activity, and sensitivity checks. The prototype is still to be built.

## Findings worth building on

- **Growth is outpacing gross profit:** Jan–Sep 2026 revenue rose 33.0% versus Jan–Sep 2025, while known-cost gross profit rose 21.7%. Known-cost weighted margin fell from 29.8% to 27.2%.
- **Atlantic warrants a closer look:** its full-window known-cost margin is 16.3%, the lowest region. Section 9 checks within-product margins and a common product mix; section 14 checks discount-cleaning sensitivity.
- **Returns and cash provide supporting context:** furniture accounts for 399,708 currency units in recorded refunds. The open-invoice proxy totals 250,004, including 135,367 past recorded terms. These are not verified ledger balances.

Figures are descriptive under the notebook's assumptions. Missing costs remain unknown; gross profit excludes overhead. Currency is unconfirmed, so amounts use CU. Patterns do not establish causality or rep misconduct.

## Suggested four-hour scope

Build one margin-review screen using the existing cleaning and aggregation logic. Show two charts: comparable revenue versus gross-profit growth, and regional margins with product drill-down.

Detect two conditions: (1) a known-cost order has negative gross profit; (2) a region/product group's weighted margin falls below a clearly labeled, configurable review threshold, with a minimum group size. Automatically create an in-app review task containing the affected orders, the trigger, and supporting amounts. Treat this as a review lead; do not present hypothetical recovered margin as guaranteed savings.

Person 1 handles data preparation, calculations, and detections; person 2 handles the screen, review queue, and demo. Spend the first 30 minutes agreeing on definitions, the next two hours building, the next hour integrating and checking, and the final 30 minutes rehearsing.

The brief requires at least two insights, two visualizations, two detected business conditions, and one automated action in a working visual prototype. At least one detection must be explainable team-written logic. Major implementation work belongs during the competition; this repository currently supplies the exploration and source data.

## Data

- `data/raw/customers.csv`: 1,210 customers.
- `data/raw/orders.csv`: 6,169 raw rows; 6,144 distinct orders after removing 25 exact duplicates; 6,136 valid positive-quantity sales after quarantining 8 rows.
- `data/raw/returns.csv`: 275 return events.

Orders cover January 2025–September 2026; the payment/return snapshot is October 31, 2026. The notebook normalizes 181 mixed-scale discounts and retains 92 valid sales with unknown costs. It includes alternative assumptions and row-level review tables.

`data/clean/` holds the cleaned dataset: duplicates dropped, region and product names normalized, MM/DD/YYYY dates parsed, percent-style discounts divided by 100, the 8 negative-quantity rows set aside (`review_rows.csv`), and blank unit costs left blank (no median fill). `changes.csv` traces every changed cell back to its raw line; `dropped_rows.csv` lists what left the sales view.

By default, the notebook reads `data/clean/` (`USE_CLEAN = True` in its loading cell) and shows the cleaning trail right after loading. Set `USE_CLEAN = False` to run on the original source ZIP embedded in the notebook, or set `DATA_ZIP` to analyze another ZIP. The three `data/raw/` CSVs match the embedded files byte for byte.

## Run

Use Python 3.12+ and uv:

```bash
uv sync --locked
uv run jupyter lab
```

Open `output/jupyter-notebook/chrome_and_oak_eda.ipynb` and run all cells. To execute it and regenerate the HTML:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run jupyter nbconvert --to notebook --execute --inplace output/jupyter-notebook/chrome_and_oak_eda.ipynb --ExecutePreprocessor.timeout=300
PYTHONDONTWRITEBYTECODE=1 uv run jupyter nbconvert --to html output/jupyter-notebook/chrome_and_oak_eda.ipynb
```

The notebook keeps summaries and review tables in memory; optional CSV exports are commented out in the final cell.
