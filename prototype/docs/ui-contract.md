# UI ↔ data contract (draft, generic until the track is locked)

Stack: **React + Vite + Recharts** in `ui/` (UI session owns it), **FastAPI + pandas** in `api/` (data session owns it). Analysis scripts stay in `explore/`.
Until the API exists, the UI reads mock JSON with these exact shapes from `ui/src/mock/`. Switching to the real API = changing one base URL.
All money in CAD, plain numbers (no formatted strings). Dates ISO `YYYY-MM-DD`.

## Endpoints

### Dataset page (built first): Raw / Clean switch, same shapes for both

`/api/raw/*` reads `data/raw` exactly as received (everything read as text first, nothing coerced). `/api/clean/*` reads `data/clean` as it is now: duplicates dropped, negative quantities set aside (`review_rows.csv`), **blank unit costs stay blank, no median fill**. No new cleaning or anomaly logic is built for this page; the teammate owns that part.

`GET /api/{raw|clean}/tables`
```json
{ "tables": [{ "name": "orders", "file": "orders.csv", "rows": 6169, "columns": 13, "row_means": "one order line, one product", "key": "order_id" }],
  "joins": [{ "from": "orders.customer_id", "to": "customers.customer_id", "match_rate": 1.0 }] }
```
`GET /api/{raw|clean}/{table}/profile`
```json
[{ "column": "region", "dtype": "text", "missing": 0, "missing_pct": 0, "distinct": 15,
   "top": [{ "value": "Ontario", "count": 2088 }], "numeric": null, "date": null, "changed_cells": null }]
```
`numeric`: `{ "min": 0, "p25": 0, "median": 0, "p75": 0, "max": 0, "hist": [{ "from": 0, "to": 0, "count": 0 }] }`. `date`: `{ "min": "...", "max": "...", "formats": [{ "pattern": "YYYY-MM-DD", "count": 0 }] }`. `changed_cells` (clean only): cells in this column changed vs raw, from `changes.csv`.

`GET /api/{raw|clean}/{table}/rows?offset=0&limit=50&q=&col=&val=` → `{ "total": 0, "columns": [...], "rows": [[...]] }`. Clean rows include the `fixes` column.

`GET /api/{raw|clean}/charts` → charts in the overview chart shape: orders per month, rows per region label, discount histogram, refunds per month. Side by side, raw vs clean shows what cleaning changed (15 region labels become 5, discounts like 22.5 disappear).

`GET /api/clean/set-aside` → the dropped and set-aside rows (`dropped_rows.csv`, `review_rows.csv`) with the reason.

`GET /api/meta`
```json
{ "company": "chrome-oak", "company_name": "Chrome & Oak Office Supply", "extracted_on": "2026-10-31", "entity_label": "Customer", "owner_label": "Account rep" }
```
`company` picks the UI theme: `"chrome-oak"` or `"millennium"`.

`GET /api/data-prep`
```json
{ "files": [{ "name": "orders.csv", "rows": 0, "cols": 0, "row_means": "one order line" }],
  "steps": [{ "id": "dedupe", "title": "Removed duplicate order IDs", "why": "...", "rows_affected": 0, "effect": "Revenue drops by $X" }] }
```

`GET /api/overview`
```json
{ "kpis": [{ "id": "revenue", "label": "Revenue", "value": 0, "unit": "$", "hint": "Jan 2025 to Sep 2026", "tone": "neutral" }],
  "charts": [{ "id": "rev_vs_margin", "type": "bar", "title": "...", "caption": "...", "x": "region",
               "series": [{ "key": "revenue", "label": "Revenue" }], "rows": [{ "region": "Atlantic", "revenue": 0 }] }] }
```
`tone`: `neutral | good | warn | bad`. `type`: `bar | line | stacked-bar | scatter | bridge`.

`GET /api/gap` (the overview's centre, see "Main objective" in `docs/PLAN.md`)
```json
{ "period": "Jan-Sep 2026 vs Jan-Sep 2025",
  "headline": { "revenue_growth": 0, "revenue_growth_pct": 0, "profit_after_refunds_growth_pct": 0 },
  "bridge": [{ "id": "revenue", "label": "Revenue growth", "value": 0, "kind": "start" },
             { "id": "discounts", "label": "Extra discounts", "value": 0, "kind": "minus", "driver_id": "qe_push" },
             { "id": "cogs", "label": "Extra cost of goods", "value": 0, "kind": "minus" },
             { "id": "refunds", "label": "Extra refunds", "value": 0, "kind": "minus", "driver_id": "transit_damage" },
             { "id": "result", "label": "Profit after refunds growth", "value": 0, "kind": "end" }],
  "drivers": [{ "id": "qe_push", "rank": 1, "title": "...", "what": "...", "why": "...", "todo": "...",
                "handled_by": ["qe_discount", "reps"], "impact": 0, "changed_in_2026": true,
                "controllable": true, "rule_catchable": true, "chart_id": "discount_band_returns" }],
  "who_is_right": [{ "exec": "CEO", "claim": "...", "verdict": "partly", "evidence": "..." }],
  "why_first": "..." }
```
`kind`: `start | minus | plus | end`. `verdict`: `right | partly | wrong`. Every number by code; `what` / `why` / `todo` text is written by the team (static), not by AI.

`GET /api/insights`
```json
[{ "id": "i1", "title": "...", "what": "...", "why": "...", "action": "...", "chart_id": "rev_vs_margin" }]
```

`GET /api/conditions`
```json
[{ "id": "overdue", "name": "Invoice overdue", "rule_text": "Business customer with an invoice more than {value} days past due",
   "threshold": { "label": "Days overdue", "min": 0, "max": 120, "step": 5, "value": 45, "unit": "days" },
   "hits": 0, "amount": 0, "triggers_action": true }]
```

`GET /api/simulate?condition=overdue&value=30` → `{ "hits": 0, "amount": 0 }` ("would have flagged N, worth $X").

`GET /api/alerts?condition=overdue&value=45`
```json
[{ "id": "a1", "condition_id": "overdue", "entity_id": "C123", "entity_name": "...", "owner": "...", "region": "...", "segment": "Reseller",
   "severity": "high", "amount": 0, "reasons": ["62 days past due", "Balance 140% of credit limit"],
   "status": "auto_held", "created_at": "2026-10-31" }]
```
`severity`: `low | medium | high`. `status`: `auto_held | notified | overridden | resolved | open` (`open` = C3, detection only, no action).

### Live API notes (back end, 2026-11-14)
- Live at `http://localhost:8000` (`VITE_API_BASE=/` uses the Vite proxy). Reset demo state: `POST /api/admin/reset`.
- C1 has a second slider: `GET /api/conditions` returns a `window` object next to `threshold` (days before quarter end, 7 to 30, default 14). `simulate`, `alerts` and `actions` accept `&window=N`. Without it the default (14) is used.
- `/api/alerts` with no `condition` returns all three conditions. Optional filters: `status`, `owner`, `limit`. Sorted newest first.
- Extra alert fields (safe to ignore): C1 `order_id, product, quantity, discount_pct, below_cost, hold_until, resolution (returned | kept | null), resolved_on, refund, prior_overstock_returns`; C2 `return_id, product, return_reason, refund, usual_gap_days, escalate_on, escalated, next_order, resolution (reordered | came_back_late | null)`; overridden alerts carry `override_reason`, `overridden_at`. `amount` is the order revenue (C1), the customer's 12-month spend at risk (C2), the amount owed (C3).
- `/api/simulate` returns more than `hits`/`amount`: C1 `refunds_caught, return_rate, return_rate_other, below_cost, top_owner, top_owner_hits, top_owner_share, owners, sentence`; C2 `customers, escalated, escalated_value, reordered, sentence`. `sentence` is ready to show under the slider.
- `/api/overview` also returns `who_is_right` (exec, claim, verdict) and `recommendation` (3 lines). Chart ids: `growth_vs_profit` (bar), `discount_band_returns` (bar), `qe_week_share` (line), `rep_discount_margin` (scatter, x `discount`, y `margin`, label `rep`), `furniture_damage_region` (bar), `quiet_vs_bad_return` (bar). Every chart has `unit`.
- `/api/entity/{id}` works for customers (`C1178`) and reps (`R07`); it returns `kind: customer | rep` and a `compare` list (value vs peer median).
- `/api/data-prep` steps carry `kind: drop | fix | set_aside | kept | check` and `column`; there is also a `summary` (raw vs clean totals).
- `draft` and `triage` return a `source` field: `ai` or `template: <reason>`. No key is set yet, so it is `template: no ANTHROPIC_API_KEY`.
- `/api/actions` accepts `alert_id`, `actor`, `limit`, `condition`, `value`, `window`. Sorted newest first. About 1,700 rows unfiltered.
- Update 13:40: the C1 automatic chain is rules only: `flag`, `quota_hold`, `notify` (Sales manager, CFO), then `release` (45 days, no return) or `resolve` (returned, credit cancelled). No triage row in the chain. `POST /api/alerts/{id}/triage` is the advisory note: it returns `advisory: true` and a `label`, and never changes the alert's status, severity or hold.
- `/api/alerts` filters: `rep` (or `owner`), `region`, `segment`, `severity`, `status`. Every alert carries `segment`.
- `/api/gap`: bridge kinds are `start | minus | plus | subtotal | end`. `minus` / `plus` carry the size (positive); `start`, `subtotal`, `end` carry the signed value. Bars: growth at list price, extra discounts, revenue growth (subtotal), revenue on lines with no unit cost, extra cost of goods, gross profit growth (subtotal), extra refunds (with a `split` by reason), profit after refunds growth. `bridge_residual` is 0 when the bars add up. Response has `provisional: true` and a `provisional_note` until the teammate's data is in. Drivers add `impact_note`.
- Accounts: `/api/accounts` adds `credit_hold_reason` and accepts `segment`, `region`, `rep` filters. A credit hold needs a reason (400 without); it writes `credit_hold` (user) and `notify` (to the rep) rows with `alert_id` `acct-<id>`. `/api/reps` quarters add `held_or_cancelled`; `quota_countable` = revenue minus refunds, excluding C1 orders still on hold or returned. `PUT /api/reps/{id}/target` writes an action row with action `target`.
- `POST /api/ask`: also accepts `sql` (a SELECT you write, skips the AI). Response adds `sql_source`, `answer_source`, `row_cap` (500), `total_rows` (true count, even when `rows` is capped). Without an ANTHROPIC_API_KEY, a question with no `sql` returns an `error` saying so.
- Ask is limited to the dataset: a question that is not about Chrome & Oak's orders, customers or returns (general knowledge, forecasts, writing tasks, chit-chat) returns `error` with a fixed message and `out_of_scope: true`. Every query must read from `orders`, `customers` or `returns`. Show `error` as a gentle notice, not a failure. The AI key is set now (`/api/meta` → `ai_enabled: true`), so drafts, the advisory note and Ask answers are AI-worded (`source: "ai"`).
- `POST /api/admin/reset` also clears credit holds and targets.

`POST /api/ask` body `{ "question": "...", "alert_id": "a1 or null" }` (Then tier, read-only)
```json
{ "answer": "...", "sql": "SELECT ...", "columns": ["region", "revenue"], "rows": [["Atlantic", 0]],
  "chart": { "type": "bar", "x": "region", "series": [{ "key": "revenue", "label": "Revenue" }] }, "error": null }
```
DuckDB connection opened read-only over the clean tables; anything that is not a single SELECT is refused; row limit. When `alert_id` is set, the alert's facts are passed as context.

**Every successful Ask answer carries a visual** (team decision 2026-11-14: visualization is a judging axis). `chart` is never null when `rows` is non-empty. The type is picked by code from the result's shape, never by the AI:

| Result shape | `chart.type` | Notes |
|---|---|---|
| 1 row, 1 column | `kpi` | `{ "type": "kpi", "label": "...", "value": 0 }` |
| 1 row, several numeric columns | `kpis` | `{ "type": "kpis", "items": [{ "label": "...", "value": 0 }] }` |
| first column time-like (month, date, quarter, week, year) | `line` | all points, up to 500 |
| first column categorical, ≤ 20 rows | `bar` | up to 3 numeric series |
| first column categorical, > 20 rows | `bar` | top 20 by the first numeric column, `"note": "Top 20 of N"` |
| only numeric columns, ≥ 2 of them | `scatter` | `x` = first, `y` = second |
| no numeric column | `bar` | count of rows per value of the first column, top 20, `"note": "Rows per <col>"` |

Optional `"note"` on any chart. The UI renders the chart above the answer text and always shows the result table under it.
Live (back end): every `line`, `bar` and `scatter` chart carries its own `rows` (list of objects keyed by `x` and the series keys); draw from `chart.rows`, not from the result table, because a top-20 cut or a row count differs from the table. `scatter` adds `"y"`. A single numeric column gives a `bar` of its distribution (`x: "range"`, note "Distribution of ..."). `kpi` with text context reads like `"revenue (Atlantic)"`; `kpis` may carry a `note` with that context.

`GET /api/accounts` (Accounts & Limits, customers tab; business customers only)
```json
[{ "id": "C1173", "name": "...", "segment": "Enterprise", "region": "Ontario", "rep": "R04", "terms": "Net 60",
   "credit_limit": 25000, "open_balance": 27600, "utilization": 1.10, "days_overdue": 221, "times_over_limit": 0,
   "credit_hold": false }]
```
`POST /api/accounts/{id}/credit-hold` body `{ "on": true, "reason": "..." }` → updated account, writes an action log row (advisory).

`GET /api/reps` (Accounts & Limits, reps tab)
```json
[{ "id": "R07", "region": "Atlantic", "quarters": [{ "quarter": "2026Q3", "revenue": 0, "net_of_returns": 0,
   "quota_countable": 0, "avg_discount": 0, "team_avg_discount": 0, "quarter_end_share": 0, "target": null }] }]
```
`target` is null: targets are not in the data. `PUT /api/reps/{id}/target` body `{ "quarter": "2026Q3", "target": 0 }` lets the manager set one (advisory input).

`GET /api/entity/{entity_id}` (drill-down for a customer or a rep; restored 2026-11-14 with Accounts & Limits)
```json
{ "id": "C123", "name": "...", "facts": [{ "label": "Credit limit", "value": 0, "unit": "$" }],
  "timeline": [{ "date": "2026-01-15", "kind": "order", "amount": 0, "note": "..." }],
  "chart": { "type": "line", "x": "month", "series": [{ "key": "balance", "label": "Balance owed" }], "rows": [] } }
```

`POST /api/alerts/{id}/draft` → `{ "to": "...", "subject": "...", "body": "..." }` (AI wording, numbers filled by code).
`POST /api/alerts/{id}/triage` → `{ "summary": "...", "review_needed": true, "why": "...", "recommendation": "hold | release | escalate" }` (AI-assisted decision bonus: AI reads the facts code already computed, never computes numbers).
`POST /api/alerts/{id}/override` body `{ "reason": "..." }` → updated alert.

`GET /api/actions`
```json
[{ "ts": "2026-10-31T09:00:00", "alert_id": "a1", "actor": "system", "action": "credit_hold", "detail": "..." }]
```
`actor`: `system | user`. `action`: `flag | quota_hold | winback_task | credit_hold | notify | draft | triage | override | release | resolve`. Condition ids: `qe_discount` (C1), `quiet_after_bad_return` (C2), `overdue_or_over_limit` (C3), see `docs/PLAN.md`. A `notify` row also carries `"to": "rep name or role"` (the "notify the right person" step; shown in the UI as an outbox).

### What if (rule impact simulator, its own page)

`GET /api/whatif?threshold=25&window=14&rule=cap` (`rule`: `cap` = quarter-end discounts above the threshold need approval and are capped at it)
```json
{ "period": "Jan-Sep 2026", "kind": "replay", "provisional": true,
  "flagged": { "orders": 207, "revenue": 0, "refunds": 0, "share_r07": 0 },
  "actual":  { "revenue": 0, "gross_profit": 0, "refunds": 0, "profit_after_refunds": 0, "profit_after_refunds_growth": 0 },
  "scenarios": [
    { "id": "keep_at_cap", "label": "Customer keeps the order at the capped discount",
      "revenue": 0, "gross_profit": 0, "refunds": 0, "profit_after_refunds": 0, "profit_after_refunds_growth": 0,
      "delta": { "revenue": 0, "gross_profit": 0, "refunds": 0, "profit_after_refunds": 0 } },
    { "id": "lose_order", "label": "Customer walks away from the order", "...": "same fields" } ],
  "bridge_by_scenario": { "keep_at_cap": [ "same shape as /api/gap bridge" ], "lose_order": [] },
  "projection": { "quarter": "2026Q4", "method": "Q4 2025 actual x (1 + Jan-Sep YoY growth), then the scenario's Jan-Sep relative effect",
                  "quarters": [{ "quarter": "2025Q1", "revenue": 0, "kind": "actual" }],
                  "q4": { "baseline": 0, "keep_at_cap": 0, "lose_order": 0 } },
  "assumptions": ["Replay of 2026 orders, not a prediction of customer behaviour", "..."] }
```
Rules, all plain code:
- **keep_at_cap**: flagged orders keep their quantity, discount set to the threshold; refunds on them unchanged (conservative).
- **lose_order**: flagged orders removed with their cost of goods and their refunds.
- The truth sits between the two scenarios; the page shows them as a range.
- **projection** is a rough run-rate, labelled as such, never presented as a forecast model.

Live (back end): `/api/whatif` answers in about 50 ms, then about 5 ms from cache for a threshold/window pair already seen. `rule` other than `cap` → 400. Extra fields: `threshold`, `window`, `flagged.owners`, `flagged.list_revenue`, `flagged.avg_discount`, `baseline_2025` (Jan-Sep 2025 actuals), `actual.revenue_growth` and each scenario's `revenue_growth` (%), `range` (`[low, high]` across the two scenarios for `revenue`, `profit_after_refunds`, `profit_after_refunds_growth`, `revenue_growth`), `projection.q4_profit_after_refunds` (same run-rate for profit after refunds), `projection.jan_sep_revenue_growth_pct`. Only 2026 orders are replayed (Jan-Sep 2025 is the comparison base), so `flagged.orders` is lower than the C1 count over both years (121 vs 207 at 25%).
