# Data layout

```
data/raw/chrome_oak/      uncleaned export, byte-identical to the zip. Never edited.
data/raw/millennium/      Option A export (fallback), untouched.
data/clean/chrome_oak/    cleaned copy, rebuilt by api/pipeline.py (also on every API start, or: .venv/Scripts/python.exe explore/clean.py)
data/state/               runtime state of the app (overrides, drafts, triage notes). Reset with POST /api/admin/reset
```

## What is in `data/clean/chrome_oak/`

| File | What it holds |
|---|---|
| `customers.csv`, `returns.csv` | Same as raw. Both were already clean (checked, no fix needed) |
| `orders.csv` | Cleaned orders (6,136 rows). Two extra columns: `raw_line` (line number in the raw file) and `fixes` (step ids applied to that row, `;`-separated, empty when untouched) |
| `review_rows.csv` | The 8 negative-quantity rows, set aside for a person to check. Out of the sales view |
| `changes.csv` | One row per changed cell: `raw_line`, `order_id`, `column`, `old`, `new`, `step`. 708 cells |
| `dropped_rows.csv` | Raw rows taken out of the sales view: 25 duplicates (`removed`) and 8 negative quantities (`set aside for review`) |
| `data_prep.json` | Files and steps in the `/api/data-prep` shape: rows touched, why, revenue and gross profit before and after each step |

## Trace a row

- Why does order SO-000011 look different from the raw file? Filter `changes.csv` on `order_id == "SO-000011"`.
- Which rows did a step touch? Filter `changes.csv` on `step`, or `orders.csv` on `fixes` containing the step id.
- Raw line for a cleaned row: `raw_line` in `orders.csv`.

## Before and after, whole table

| | Raw | Clean |
|---|---|---|
| Order rows | 6,169 | 6,136 (+ 8 in review) |
| Revenue | $2,569,404 | $7,973,292 |
| Gross profit (rows with a known cost) | -$3,151,790 | $2,229,755 |

The raw total is wrong mostly because 181 discounts were stored as percents (12 instead of 0.12), which makes those rows' revenue negative (-$5.1M on their own).

## Steps, in order (decisions final, see docs/PLAN.md)

| Step id | Kind | Rows | Effect |
|---|---|---|---|
| `dedupe` | drop | 25 | Removes $44,018 of double-counted revenue |
| `discount_pct` | fix | 181 | These rows go from -$5,121,624 to $314,759 |
| `neg_qty` | set aside | 8 | Out of the sales view (-$11,522). Jan-Sep growth 33.00% to 33.03% |
| `region` | fix | 245 | Total unchanged. Atlantic gains $66,814, Ontario $93,155, Quebec $75,624 |
| `product` | fix | 160 | Total unchanged. $276,774 lands on the right product |
| `date_format` | fix | 122 | Total unchanged. Month first: read day first, they would fall after the data ends |
| `cost_blank` | kept | 92 | Left blank. Margins use the 98.5% of lines with a known cost |
| `unpaid_kept` | kept | 92 | Kept on purpose: $250,004 still unpaid at extraction |
| `join_check` | check | 0 | 0 orphan orders, 0 orphan returns, 0 region mismatches |
