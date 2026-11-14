# Y2K hackathon: plan (Option B, Chrome & Oak, LOCKED 2026-11-14)

**Simulator extension (Hedi, 2026-11-14):** [`simulator-plan.md`](simulator-plan.md) defines the policy simulator: pricing cap, damage packaging and credit restriction modules, their sliders, assumptions and default-selection rules. It supersedes the earlier What if settings in this document; the other workflows remain as described below.

Source of truth for the existing prototype workflows. Numbers come from `explore/FINDINGS.md`, the EDA notebook (`ChromeAndOak_EDA.ipynb`) and checks run by the planning session. Numbers marked "(recompute)" move slightly after the cleaning decisions below and get re-checked by the check script.

## The problem

Revenue is up 33% (Jan to Sep, year over year), gross profit only about 22%, and gross profit minus refunds about 10% (recompute). A large part of the gap is one pattern: the only Atlantic rep (R07) books 48% of revenue in the last 14 days of each quarter at a 27% average discount (other reps 9 to 12%), mostly to resellers. All 46 "overstock" returns in the dataset ($150.5k) come back from those resellers 20 to 44 days later. The rep hits the quarterly target; the company pays for the discount and the refund.

Who is right:
| Exec | Verdict |
|---|---|
| CEO: up a third, Atlantic shines | Top line true. Atlantic's growth is discounting plus returns; its SMB and Enterprise revenue fell 25% |
| CFO: profit lags, unpaid invoices | Profit lag true (refunds +67%). Unpaid invoices real but small: $135k overdue, flat since 2025 |
| Operations: returns, big items | True. Furniture damaged in transit to BC (16.9% of furniture revenue) and the Prairies (15.4%) |
| Customer Success: customers went quiet | True: 70 business customers ($619k in 2025). 59% had a bad return vs 27% of active ones |

## Main objective: explain the gap, rank it, act on the top driver

The brief asks three things in order: find **what drives the gap between how good things look and how they are**, **decide which problem is worth solving first**, build a tool to **act on it**. So the app shows everything, but as a ranked explanation, not a pile of charts.

**1. The gap, in one picture (centre of the overview).** A bridge chart from "how it looks" to "how it is", Jan to Sep 2026 vs 2025:
revenue growth (+$970k, +33%) → minus extra discounts → minus extra cost of goods → minus extra refunds (+$118k: $175k to $293k) → profit-after-refunds growth (about +10%).
Values marked missing here are for the teammate to compute: [extra discount $], [extra cost of goods $], [exact profit-after-refunds growth $]. Each bar is clickable.

**2. One card per driver**, same four fields everywhere: what happened (number + chart), **why it happened** (the cause chain), what to do, and what in the tool handles it.

| Driver | Why it happened | What to do | In the tool |
|---|---|---|---|
| Quarter-end discount push (R07, Atlantic resellers) | Quarterly target + bonus on gross revenue: deep discounts in the last 14 days, resellers send overstock back about a month later | Quota on revenue net of returns after 45 days; approval for quarter-end discounts ≥ 25% | C1, action queue, reps tab |
| Furniture damaged in transit (BC, Prairies) | Long-haul shipping of big items from Montreal; BC is also the fastest-growing region | Packaging or carrier change for long-haul furniture | Insight 3, C2 |
| Business customers going quiet | A bad return (damaged, defective, wrong item) precedes the silence in 59% of cases | Contact the customer right after a bad return | C2 |
| Late payments | Steady since 2025, not what changed | Monitor only | C3, customers tab |

**3. Which first, and why (stated on screen).** Ranked by four plain criteria: size in $, did it change in 2026, can the company control it, can a rule catch it early.
- **#1 Quarter-end discount push:** largest controllable piece, new in 2026 (R07 discount 18-19% in 2025, 28% in 2026), one cause, a rule catches it with almost no false alarms. This is what the tool automates first.
- **#2 Transit damage → quiet customers:** big ($619k of 2025 spend went quiet) but the root fix is operational; the tool handles the customer side (C2).
- **#3 Late payments:** real but flat and smaller ($135k overdue). Monitor only.

**4. Act on #1** in the action queue (C1), live.

This is also the order of the pitch: gap (1 min), drivers and why (1.5 min), acting on #1 (2 min), what to do (30 s).

## Data prep decisions (teammate's call; the table below is a proposal)

The teammate owns the data and the cleaning. Sessions don't touch `data/` until the teammate's version is in.

| Fix | Rows | Decision and reason |
|---|---|---|
| Exact duplicate rows | 25 | Dropped. Every column identical, double-counted revenue |
| Region spellings | 245 | 15 spellings mapped to 5 regions |
| Product names | 160 | 22 names mapped to 10 products |
| Slash dates | 122 | Month first. Proof: reading them day first puts orders in Oct to Dec 2026, after the data ends |
| Discounts stored as percent (22.5) | 181 | Divided by 100. Left as is they show negative revenue, and they sit inside the discount analysis the main finding rests on |
| Negative quantities | 8 | **Set aside** (kept in a review list, out of the sales view). Changes growth by 0.1 pt |
| Blank unit cost | 92 | **Left blank.** Margins use rows with a known cost (98.5% coverage). No invented values |
| Blank payment date | 92 | Left alone on purpose: unpaid invoices at extraction |

## Insights (4, minimum is 2)

| # | What happened | Why it matters | What to do | Chart |
|---|---|---|---|---|
| 1 | Revenue +33%, gross profit ~+22%, profit minus refunds ~+10% | Growth looks better than it is | Track profit net of refunds | The gap bridge chart (see Main objective) |
| 2 | R07: 48% of revenue in last 14 days of quarter, 27% discount. Orders discounted 30 to 40% come back 23.4% of the time and keep a 5.8% margin; lower bands return 3 to 6% | Quota incentive buys revenue that comes back | Quota credit net of returns; approval for deep quarter-end discounts | Return rate and margin by discount band; share of revenue by week of quarter, R07 vs others |
| 3 | Furniture damage refunds in BC and Prairies about 4x Ontario. BC is also the fastest-growing region (+50%) | Refund cost and warehouse time grow with the region | Packaging or carrier change for long-haul furniture | Furniture refund % by region |
| 4 | Quiet business customers had a bad return twice as often (59% vs 27%) | $619k of 2025 spend went quiet | Contact business customers right after a bad return | Quiet rate with vs without a bad return |

Insight 1 opens the pitch, insight 2 drives C1, insights 3 and 4 drive C2.

Supporting facts for Q&A: Atlantic margin at the company's common product mix is still 17.5% vs about 32% elsewhere, so it is pricing, not product mix. Other reps also discount a bit more in the last week of a quarter (about 10% to 15%), so the incentive problem is company-wide in a mild form; R07 is the extreme.

## Conditions and automated actions

### C1 · Quarter-end discount push (main)
- **Rule:** business order (SMB, Enterprise, Reseller) in the last 14 days of a quarter with discount ≥ 25%.
- **Why 25%:** company-wide median discount 10.1% + 3 × MAD gives 27%; every other rep's 99th percentile is 20.6%. 25% sits above normal behavior for the whole team. (A per-rep baseline was tested and rejected: deep discounting is R07's own normal, so it flags 9 orders and none of R07's.)
- **Back-test:** 207 orders, 205 R07, $893k revenue, $171k later refunded. Flagged orders are returned 25.1% of the time vs 4.2% for other business orders. With a 7-day window: 183 orders, 181 R07.
- **Out of sample:** threshold set from 2025 only (other reps' 99th percentile, 20.1%), applied to 2026: 141 orders, 124 R07.
- **Severity up** when the order is sold below cost (discount above 1 − unit_cost / unit_price): 41 orders, 40 R07, all at quarter end.
- **Action chain, automatic:** flag order → hold its quota credit 45 days (every overstock return came back within 20 to 44 days) → notify sales manager and CFO → log each step. (Then tier: the held order lands in the sales manager inbox with an advisory AI note.)
- **If it's wrong:** a legitimate deal gets quota credit 45 days later. The order still ships. Manager releases it with a reason, logged.

### C2 · Bad return on a business account (early warning)
- **Rule:** business customer gets a return marked damaged in transit, defective or wrong item.
- **Volume:** 130 returns, 104 customers, about 1.5 a week: a workload Customer Success can absorb.
- **Action chain, automatic:** open a Customer Success call task → AI drafts an apology email from the order facts (numbers by code) → notify the account rep → log.
- **Escalation:** no new order after the customer's usual gap → win-back task.
- **Evidence:** 41 of the 70 quiet customers had their bad return at or after their last order.
- **If it's wrong:** a customer gets a courtesy call they didn't need.
- **Honesty line:** timing and correlation, not proof the return caused the churn.

### C3 · Overdue or over limit (detection only)
3 customers past 60 days; C1173 owes $27.6k on a $25k limit, 221 days overdue. Shown in Accounts & Limits (customers tab: overdue days, balance vs limit) and as one line on the overview, to show we checked the CFO's claim. Detection only, no action.

## Be upfront in the pitch

The data has no quota or bonus records: the quota-credit hold is a status our tool sets. "Notify" writes to an outbox inside the app; nothing is actually sent.

## Optional features

| Feature | How | Tier |
|---|---|---|
| Simulation | C1 sliders: discount threshold 15 to 35%, window 7 to 30 days. Live: orders flagged, share R07, revenue held, refunds caught, return rate of flagged orders | Must |
| Simulation, page "What if" (team decision 2026-11-14) | Its own page. Pick the rule (cap quarter-end discounts at X%, window N days). Replay Jan-Sep 2026 with the rule on, two scenarios as a range: customer keeps the order at the capped discount / customer walks away. Shows revenue, gross profit, refunds, profit after refunds vs actual, the gap bridge redrawn per scenario, and a rough Q4 2026 run-rate projection with and without the rule. Assumptions listed on the page. Replay, not a forecast model | Then (first) |
| Multi-step automation | C1 and C2 chains, each step a log row | Must |
| Interactive exploration | Queue filters (rep, region, segment), Accounts & Limits drill-downs (customer, rep), and Ask in read-only mode, opened from an alert to see why it triggered | Then |
| AI-assisted decision | Advisory AI note in the sales manager inbox: summary of facts code computed, review needed or not. Never changes the rule's verdict | Then |

## Feature set

Each feature exists because of something the data showed.

| Feature | What it does | Tier |
|---|---|---|
| The gap (overview) | Growth vs profit bridge, who-is-right, driver cards, recommendation | Must |
| Action queue | **Rule-based only**: flag, severity, reasons and $ all come from C1 / C2 code. Filters by rep, region, segment. Release / override with reason, sliders. AI writes nothing here except the email draft text | Must |
| Activity log | System and user rows, outbox of notifications, undo on releases | Must |
| Threshold sliders | C1 sliders with live back-test numbers ("would have flagged N, $X") | Must |
| Ask | **Read-only assessment tool.** Ask a question about the data, or "Ask about this alert" from a card (context pre-filled). AI writes a SELECT, DuckDB runs it on a read-only connection over the clean tables (SELECT only, row limit), answer + the query shown + a chart. Cannot create, clear or change alerts. Covers the interactive exploration bonus | Then |
| Sales manager inbox | Sales manager inbox for held quarter-end orders. The hold is the rule's decision; an AI note labelled "advisory" sits beside it; the manager releases or keeps the hold | Then |
| Repeat offenders | Reps and resellers with the most C1 hits, a table on the overview | Then |
| Accounts & Limits | Built on the brief's business mechanics. **Customers tab** (business accounts): credit limit vs open balance, utilization, terms (Net 30 / Net 60), days overdue, times over limit. **Reps tab**: quarterly revenue gross, net of returns, and quota-countable after C1 holds; average discount vs team; quarter-end share. Quarterly targets are not in the data, so the page doesn't show them. Drill-down per customer and per rep. Home of C3 | Then (first) |
| AI-written rules | Out. Rules must be our own logic | Skip |

## Scope cut line

- **Must (first):** Dataset page, raw visualization.
- **Must:** cleaning with its log (teammate), C1 full chain, C1 sliders, C2 creating a task, action log, 2 insight charts, overview.
- **Then:** What if page (rule impact replay + Q4 run-rate), Accounts & Limits (customers + reps tabs, drill-downs), Ask (read-only), sales manager inbox with advisory AI note, AI email draft, repeat offenders table, C2 escalation, insights 3 and 4 charts.
- **Skip:** C3 action, credit hold toggle, rep target input, CFO brief, keyboard triage, login, anything not in this file.
- **Rule for every control (2026-11-14):** it stays only if it's on the demo path, covers a judging requirement or bonus, or lets a judge check a number. Otherwise it's removed, even if it works.

## Screens (proposed, confirm before the UI resumes)

**Dataset** (built first, team decision 2026-11-14): the three files exactly as received. Per table: rows, what a row means, keys and how tables join; per column: type, missing, distinct, top values, histogram or date range and formats; a searchable raw table; a few raw charts (orders per month, rows per raw region label, discount histogram, refunds per month). No cleaning, no anomaly flags: the data-quality and anomaly part is the teammate's and plugs in later. / Overview = **The gap** (bridge chart, ranked driver cards with what / why / what to do / handled by, "which first and why", who-is-right table, repeat offenders, recommendation) / Action queue (rule-based alert cards; C1 sliders in the header so moving them reshapes the queue live) / Accounts & Limits (customers and reps tabs, drill-downs open from here and from alerts) / Activity log (system vs user rows, outbox) / Ask (read-only). Data & method page: undecided. The cleaning log has to be shown somewhere (brief requirement 2): its own page, a panel on the overview, or one minute of the pitch.

## Who does what

- **Teammate: data.** Cleaning, analysis, the numbers behind the insights.
- **User: plan and process.** This plan, scope calls, the pitch and the demo flow.
- **Open:** who drives the back end (`detect.py`, `actions.py`, API) and the UI (session `y2k-ui`, paused). The data session (`y2k-hackathon`) is on hold until the user decides.
- Both: last 30 minutes rehearsing the 5 minutes and the Q&A.

## Build order (back end)

1. `pipeline.py`: cleaning from `explore/` as one function with the decisions above and the log as data.
2. `detect.py`: C1, C2, C3 as pandas functions with thresholds, returning alert rows with reasons.
3. `actions.py`: the chains writing to an action log (JSON or SQLite); release and override.
4. AI: email draft and advisory note, one call each, facts in, text out, fallback text without a key.
5. Ask (Then tier): AI writes a SELECT, DuckDB read-only connection over the clean tables, SELECT-only check, row limit, returns answer + query + rows.
6. `api/`: FastAPI on `docs/ui-contract.md`.
7. Check script: recompute and assert the headline numbers.

## 5-minute script

- **0:00 to 1:00, the gap.** Revenue +33%, profit after refunds about +10%. The bridge chart. Who-is-right table in one sentence per exec.
- **1:00 to 2:30, drivers and why.** One line on cleaning (percent discounts would show negative revenue). Driver cards in rank order: quarter-end push (discount band returns, R07 quarter-end share), transit damage and quiet customers, late payments flat. Say why #1 comes first.
- **2:30 to 4:30, live demo.** Action queue: a quarter-end R07 order flagged automatically, reasons, "sold below cost", quota credit held, sales manager and CFO in the log. Move the slider: the queue and the dollar total change. Release one order with a reason. Then a damaged return creating a Customer Success task with a drafted email.
- **4:30 to 5:00, recommendation.**

## Recommendation (30 s)

1. Pay quota on revenue net of returns after 45 days, and require approval for quarter-end discounts of 25% or more. C1 automates it.
2. Fix long-haul furniture shipping to BC and the Prairies, and call every business customer right after a damaged return. C2 automates it.
3. Collections: keep as is; it isn't what changed.

## Q&A prep

- "Aren't you just catching R07 by design?" The threshold comes from the rest of the team (99th percentile 20.6%, company median + 3 MAD = 27%), and it holds out of sample (set on 2025, 124 of 141 2026 hits are R07). Any rep crossing it is caught.
- "Is Atlantic just selling a cheaper mix?" At the common product mix its margin is still 17.5% vs about 32%.
- "Why not block the order?" The CEO wants growth. We stop paying quota on revenue that comes back; we don't stop selling.
- "What if the automation is wrong?" C1 delays quota credit, C2 triggers a courtesy call. Both reversible, both logged with who overrode and why.
- "How do you know the dates are month first?" Day first would put orders after the extraction date.
- "Where is the AI?" Only text and read-only questions: email wording, the advisory note, and Ask, which can only run SELECT queries. Every number, every flag and every severity is our pandas code.
