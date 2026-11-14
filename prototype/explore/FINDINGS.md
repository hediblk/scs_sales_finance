# Chrome & Oak: data profile and exec-claim test (2026-11-14)

Scripts: `explore/01_profile.py` (raw profile), `02_traps.py` (cleaning traps), `clean.py` (builds the cleaned copy with a full change trail), `03_claims.py` (one query per claim, on cleaned data), `04_followups.py` (rep R07, overdue aging, quiet customers).
Run from the project root: `.venv/Scripts/python.exe explore/clean.py`, then `explore/03_claims.py`. Uncleaned files stay in `data/raw/chrome_oak/`, cleaned ones and the trail are in `data/clean/chrome_oak/` (see `data/README.md`).

## What each file is and how they join

| File | Rows | One row means |
|---|---|---|
| customers.csv | 1,210 | One customer. Consumer 900, SMB 230, Enterprise 45, Reseller 35 |
| orders.csv | 6,169 (6,144 after dedupe) | One order line, one product. 2025-01-01 to 2026-09-30 |
| returns.csv | 275 | One return, at most one per order |

- `orders.customer_id` to `customers.customer_id`: 100% match. 5 customers never ordered.
- `returns.order_id` to `orders.order_id`: 100% match. Refund = qty_returned x unit_price x (1 - discount), exact on all 275 rows.
- `orders.sales_rep` equals `customers.account_rep` on every row. Order region equals customer region after cleaning.
- Segment fixes channel and terms: Consumer = Online, Prepaid. SMB = Direct, Net 30. Enterprise = Direct, Net 60. Reseller = Partner, Net 30.
- Each of the 11 reps covers one region. **Atlantic has a single rep, R07.**
- Revenue = quantity x unit_price x (1 - discount). Gross profit = revenue - quantity x unit_cost.

## Cleaning log

| Fix | Rows | Why |
|---|---|---|
| Drop exact duplicate rows | 25 | Same order_id, every column identical. Double-counted revenue |
| Normalize region spellings (ON, ontario, QC, Québec, B.C., ATL...) | 245 | 15 spellings for 5 regions |
| Normalize product names (Mech Keyboard, 24in Monitor, ERGOLIFT...) | 160 | 22 names for 10 products |
| Parse MM/DD/YYYY order dates | 122 | Rest are ISO. First part never above 12, so month first |
| Discount stored as percent (e.g. 22.5) divided by 100 | 181 | Rest are fractions. Left as is, these rows show negative revenue |
| Negative quantity made positive | 8 | Each has a payment date and no matching return, so a sign error, not a return |
| Blank unit_cost filled with the product median | 92 | Needed for margin. Cost is stable within a product |

Left alone on purpose: 92 blank `payment_date` on business orders. These are invoices still unpaid at extraction, which is the CFO signal.

## The four claims

**CEO, revenue up about a third: true on the top line.** Jan-Sep 2026 vs Jan-Sep 2025: revenue +33.1% ($2.93M to $3.90M). Gross profit +21.3%. Gross profit minus refunds +9.8%. Average discount went from 14.1% to 16.6%, margin from 29.9% to 27.2%.

**CEO, Atlantic punches above its weight: misleading.** Atlantic = rep R07 = 26% of all rep-driven revenue with 10.7% of customers.
- R07 discount 27% vs 9-12% for every other rep. R07 margin 16% vs 31-34%.
- R07 books 48% of revenue in the last 14 days of a quarter. Other reps: 12-19%.
- Changed in 2026: R07 average discount 18-19% in 2025, 28% every quarter of 2026. Quarter-end share 35-41% to 54-61%. Reseller share of R07 revenue 41-56% to 65-71%.
- 11 Atlantic resellers each took $45k-124k, mostly quarter-end, on credit limits of $20-30k.
- All 46 "Overstock / ordered in error" returns in the whole dataset belong to R07 resellers, all from quarter-end orders, median 29 days after the order, $150.5k refunded.
- Reseller refund rate: 18.3% on quarter-end orders vs 5.4% on other orders.
- Meanwhile Atlantic SMB + Enterprise revenue fell 25% ($384k to $287k, Jan-Sep).
- Back-test: "rep order in the last 14 days of the quarter with discount 25% or more" hits 207 orders, 205 of them R07, $893k revenue, $171k of refunds on those orders. At 20%: 248 orders, 220 R07. Non-R07 99th percentile discount is 20.6%.

**CFO, cash tight and profit lagging: true. Unpaid invoices: real but smaller than the margin leak.**
- Refunds Jan-Sep: $175k in 2025, $293k in 2026 (+67%). Refunds are cash out.
- Unpaid at extraction: 92 invoices, $250k. Not yet due $115k. Overdue $135k: 1-30 days $82k, 31-60 $25k, 61-90 $14k, 90+ $14k.
- 43% of paid invoices arrived late, flat between 2025 and 2026, and the median invoice is paid a day early. Late payment is a steady nuisance, not the thing that changed.
- Sharpest single case: C1173 (Ontario Enterprise, rep R04) owes $27.6k on a $25k limit, oldest invoice 221 days overdue. 12 orders ($32.7k) shipped to customers who already had an overdue invoice, 7 of them by R04.
- Only 22 orders ($120k) were placed while the customer was over its credit limit.

**Operations, returns eat time, especially big items: true.**
- Refunds as % of revenue: Furniture 9.8%, Displays 5.1%, Accessories 2.2%.
- Two separate causes. "Damaged in transit" furniture refunds: BC 16.9% and Prairies 15.4% of furniture revenue vs Ontario 3.8%, Quebec 5.4%, Atlantic 1.8%. Long-haul shipping from Montreal. And in Atlantic, the reseller overstock returns above.

**Customer Success, long-time business customers went quiet: true, and tied to bad returns.**
- 70 of 305 business customers are quiet (no order for more than twice their own median gap and more than 60 days, as of 2026-09-30). They spent $619k in 2025. 26 signed up before 2024.
- 59% of quiet customers had a damaged, defective or wrong-item return vs 27% of active ones. For all 41 of them, that bad return came at or after their last order. 31 of the 41 are furniture.
- Quiet rate is flat by region (21-25%), so this is not one rep or one region.
- This is timing and correlation; the data cannot prove the return is why they left.

## The story the data supports

The revenue growth is real, but a large part of it is R07 pushing deep-discount stock onto Atlantic resellers in the last two weeks of each quarter. That hits the rep's quarterly target, then a share comes back a month later as "overstock". It explains why profit lags revenue (CFO) and part of the returns (Ops), and it is the gap between how things look and how they are.

A second, separate problem: furniture damaged on the way to BC and the Prairies drives returns, and business customers who get a bad return tend to stop ordering (Ops and Customer Success describing the same thing).

Collections (overdue invoices, credit limits) is the weakest of the four threads: $135k overdue, 3 customers past 60 days.

## Candidate conditions for the app (pandas rules, all explainable)

1. **Quarter-end discount push** (main): business order in the last 14 days of a quarter with discount at or above X% (slider, default 20-25%), or above the rep's own median + 3 x MAD. Action: order goes to sales-manager approval, its revenue does not count toward quota until 45 days pass with no return, notify sales manager and CFO, log row. Override with reason.
2. **Quiet after a bad return**: business customer with a damaged / defective / wrong-item return and no order for more than 2x their usual gap. Action: open a Customer Success win-back task, AI drafts the apology email from the order facts, notify the rep, log row.
3. **Overdue / over limit** (small, optional): invoice more than X days overdue or open balance above credit limit. Action: credit hold on next order, notify rep and CFO.

## Option A sanity check

Millennium Mutual also has a signal: broker B07 has 29 of its 71 claims between $9,000 and $9,999, against 20 of 542 for non-broker policies. Chrome & Oak data supports a fuller story across all four exec claims, so B stays the pick.
