> Copied from the team repo (hediblk/scs_sales_finance, root PLAN.md, commit 4819644 by Hedi). Paths below are relative to that repo: `prototype/` there is the root of this project.

# Sales, returns, and credit policy simulator — UI handoff

Goal: compare simple business rules that could increase revenue and gross profit while reducing refunds and unpaid exposure. Show trade-offs and assumptions, then turn triggered conditions into useful review tasks.

Default assumption: customers keep buying at the same quantities after a discount cap. Both the cap and retention are sliders with one-percentage-point steps. Keep retention at 100% when selecting the initial cap. Packaging effectiveness and willingness to prepay are separate assumptions.

This document governs the new simulator controls, default selection, and experiments. The existing prototype plan continues to describe its other pages and workflows. This is a documentation handoff; the new simulation sweep and UI changes have not yet been implemented.

**Competition requirements**

Checked against the original Business Track - Participants.pdf in Downloads and the [repo brief](references/sales_finance_brief.txt): two insights and visualizations, a visual working prototype, at least two detected business conditions, and at least one automatic action justified by the analysis (PDF pp. 6–7). Threshold simulations are explicitly encouraged (p. 8). Demo: five minutes; team: two people; build: four hours; major implementation during the competition (pp. 9–10).

Deliver three rule definitions, with discount and damage simulations first. Credit restrictions are the third experiment. If time runs short, keep credit detection and automatic case creation, and defer its historical simulation. The first two modules already cover the required conditions, insights, charts, and actions.

**Baseline and definitions**

Use data/clean/: 1,210 customers, 6,136 sales, 275 returns. Orders end September 30, 2026; payment/return observation ends October 31, 2026. Use that snapshot. Definitions and evidence come from the [EDA notebook](output/jupyter-notebook/chrome_and_oak_eda.ipynb).

- Revenue before returns = quantity × unit_price × (1 − discount).
- Gross profit before returns = revenue − product cost, on known-cost rows only.
- Weighted gross margin = known-cost gross profit / revenue of the same known-cost rows.
- Net revenue after refunds = revenue − recorded or simulated refunds.
- Contribution after refunds and intervention cost = gross profit − refunds − extra packaging/inspection cost, on known-cost rows. This assumes no recovery of returned inventory cost and excludes overhead; label it as a contribution proxy, not audited profit.
- All monetary amounts are CAD, as confirmed by the team. Keep 92 unknown unit costs unknown. Show coverage. Aggregate returns to order grain before summing sales.

**Condition 1: discount exceeds the policy cap**

Evidence: R07's quarter-end margin is 5.9% versus 23.7% otherwise. All 46 overstock returns relate to Atlantic reseller orders handled by R07 in the final seven days of a quarter. The rule applies to all representatives; identities are drill-downs, not rule inputs.

Rule: for every valid order in the evaluation period, when discount > cap, use the cap in the simulated sale and create a pricing-review task assigned to the sales manager. Show the old/new selling price and known-cost margin; missing cost adds a cost-review reason.

Simulation: sweep every integer cap from 0% through 100% once, with retention fixed at 100%, then save the selected cap and its metrics as UI defaults. Keep quantity, unit price before discount, and unit cost fixed. Users can subsequently vary either slider in 1-percentage-point steps. Retention applies only to orders whose discount is strictly above the selected cap; orders exactly at the cap are unaffected. Weight affected order revenue and product cost by retention; unaffected orders keep weight 1. Rejected orders are assumed not fulfilled and incur no product cost.

Keep return incidence and recorded refund amounts unchanged per retained order in the first version. Apply retention weights to refunds too. Do not claim that a discount cap prevents returns. Holding refunds fixed is an explicit simplifying assumption; a real refund policy might instead follow the revised selling price.

Outputs: revenue, gross profit, weighted margin, net revenue after refunds, affected sales, and expected retained volume. The 100%-retention case is an accounting scenario, not a demand forecast. Lower caps mechanically raise revenue at unchanged volume; that alone does not establish an optimal discount policy.

**Condition 2: product/region has excessive damage returns**

Evidence: standing-desk damage return incidence is 22/71 orders in BC (31.0%) and 22/74 in Prairies (29.7%). Together: 145 shipments, 1,003 shipped units, 44 damaged-return orders, and 139,096.95 CAD in damage refunds. Damaged goods are the specific reason; do not target every return.

Rule: flag a product/region group when damage-return orders / eligible orders > 15%, with at least 30 orders. At the supplied snapshot all orders have at least 30 days of follow-up. For live use, choose and consistently apply a fixed return-observation window rather than mixing mature and new orders.

Automatic action: create one operations case per flagged product/region, with affected orders, refund amounts, and a packing/pre-dispatch inspection checklist. Recommended intervention: reinforced packaging plus inspection for future affected shipments. Carrier replacement is a follow-up investigation because carrier data is unavailable.

Simulation: apply the intervention to product/region groups selected by the damage-rate threshold, with the minimum count fixed at 30. The initial 15% threshold selects standing desks in BC/Prairies in the full-window evidence below. Sweep integer thresholds from 0% through 100% to select the default. Hold assumed damage-refund reduction at 25% and cost at 5 CAD per shipped unit for this initial sweep. Expose effectiveness and cost as sliders for subsequent sensitivity analysis. These are user-controlled assumptions, not estimated causal effects. Apply the cost to ALL targeted shipped units, not only damaged units. Reduce only damage refunds; other reasons stay unchanged. Keep original product cost unchanged and assume no additional replacement sales or recovered inventory.

Main illustration, full observed window: 25% × 139,096.95 − 5 × 1,003 = 29,759.24 CAD in avoided refunds after intervention cost. This is an incremental benefit estimate, not total gross profit. The known-cost subset has 133,649.40 CAD damage refunds and 972 shipped units: the corresponding contribution increase is 28,552.35 CAD. Four targeted orders have unknown costs, including one damaged return; keep that coverage visible.

Before-return revenue and product gross profit remain unchanged under packaging alone. Net revenue and contribution after refunds can improve. Show these separately so damage prevention receives the appropriate economic credit without mislabeling the metric.

**Condition 3: repeated serious lateness on credit purchases**

Evidence: 54 invoices are overdue at the snapshot, totaling approximately 135,367 CAD; six are more than 90 days overdue, totaling approximately 14,070 CAD. Existing credit limits do not catch all overdue accounts.

Define the policy precisely:

1. Normal: an invoice remains unpaid at its due date plus a chosen escalation allowance G, selected by the initial sweep (60 days is an illustrative setting). That is the first offense.
2. Probation: create a finance case and halve the escalation allowance for FUTURE credit invoices, to max(1, ceil(G/2)) days (30 days when G is 60). Original Net 30/Net 60 payment terms do not change. This shortens the review window, not the invoice's contractual due date.
3. Restricted: a distinct invoice placed after probation began crosses its shorter allowance while unpaid. This is the second offense. Default restriction is no further credit purchases: new purchases require prepayment. Compare a complete purchase ban as a separate, harsher scenario.

An invoice triggers once. Multiple invoices crossing on the same date produce one account-level transition. Repeated daily scans of one unpaid invoice do not create additional offenses. Existing invoices and accepted orders remain valid after restriction; they are not erased. For this simulation, restriction persists through the observation window; a real release would require finance review.

Automatic action: create/update one account case, log the state transition, assign the account rep/finance team, and generate a recommended communication. Apply restrictions inside the simulation only. The business reviewer decides actual account treatment after checking payments, returns, and disputes.

Historical simulation: process orders, payments, and escalation dates chronologically, with payments before escalation checks and new orders on the same date. Use only events known by each decision date. Before the extract, assume no prior offense history; disclose that limitation. Existing payment dates are assumed full settlement. Never use eventual payment or return outcomes to decide whether to approve an earlier order.

After restriction:

- Prepayment scenario: retain future orders and set their simulated payment date to order date. Default willingness to prepay is 100%, explicitly optimistic; its slider ranges from 0% to 100% in 1-percentage-point steps. It is independent of discount retention.
- Full-ban scenario: remove only subsequent orders and their associated revenue, product cost, payments, and returns from the counterfactual. Existing overdue balances remain owed.
- Probation alone does not make a customer pay earlier. Keep original payment timing until a modeled prepayment rule changes it. Do not assume old overdue debt is recovered.

For fractional prepayment acceptance, expected volume weights can be used after restriction; no further credit is extended then. Keep this replay separate from the discount simulator initially.

Outputs: affected accounts, restriction dates, future sales and gross profit retained/forgone, remaining overdue exposure, prepaid revenue, and workload. Historical paid-only mean days late is contextual; scenario averages must show their populations. A lower average after banning late customers is a selection effect, not proof those customers paid faster. Show paid lateness and censored unpaid aging separately.

**UI controls and selected defaults**

Percentage sliders display whole numbers 0–100; convert to fractions once in the calculation layer. A step is one percentage point. Day and cost sliders use their own units. Use the same parameters for calculations, labels, drill-downs, and task creation.

| Module | Control | Range / step | Initial value |
|---|---|---|---|
| Pricing | Discount cap | 0–100%, step 1 pp | Selected by the sweep with retention 100% |
| Pricing | Affected-order retention | 0–100%, step 1 pp | 100%; assumption, not optimized |
| Damage | Damage-rate trigger | 0–100%, step 1 pp; strict > | Selected by the sweep; minimum group size fixed at 30 |
| Damage | Assumed damage reduction | 0–100%, step 1 pp | 25%; assumption, not optimized |
| Damage | Added cost per shipped unit | CAD 0–20, step CAD 1 | CAD 5; assumption, not optimized |
| Credit | First escalation allowance G | 1–180 days, step 1 day | Selected by the chronological replay sweep |
| Credit | Probation allowance | Read-only, derived | max(1, ceil(G/2)) days |
| Credit | Second-offense action | Prepayment / full ban | Selected by the sweep; prepayment wins equivalent results |
| Credit | Prepayment acceptance | 0–100%, step 1 pp | 100%; assumption, not optimized; disabled for full ban |

Every module has an on/off toggle. Off reproduces its baseline. Keep manual controls even when the result is worse; show the negative delta. Show “Best modeled setting at the starting assumptions” beside saved defaults. Moving sliders updates only that scenario, without silently moving any other slider. “Reset to recommended” restores both saved policy settings and their associated assumptions.

**How to select the best outcome**

Do not add revenue CAD to margin percentage or use an unexplained weighted score. Apply these explicit rules, independently per module:

- Pricing: retain candidates that do not reduce revenue, gross-profit CAD, or weighted gross margin relative to baseline. Among them select highest gross-profit CAD, then highest revenue, then highest weighted margin. If all outcome metrics tie, choose the higher cap (the less restrictive rule). Include policy-off as a fallback. If manual retention creates trade-offs, show them rather than implying one setting maximizes every metric.
- At 100% retention with fixed quantities and costs, a 0% cap maximizes modeled revenue and gross profit and cannot reduce weighted gross margin. This is a boundary result of the user's assumption. Support 0% in both UI and API; do not substitute a more plausible-looking cap and call it the optimizer's result.
- Damage: hold effectiveness and cost fixed. Require net revenue after refunds, known-cost contribution CAD, and its margin (contribution / same known-cost net revenue) not to fall versus baseline; undefined margins are ineligible. Maximize known-cost contribution after refunds/intervention cost, then net revenue, then contribution margin. On ties choose fewer targeted shipments, then the higher trigger. Include policy-off, so an uneconomic intervention is never presented as the recommended default.
- Credit: retain candidates that preserve revenue, gross-profit CAD, and weighted gross margin versus the no-restriction baseline, then minimize overdue exposure at the snapshot. Break ties using lower total open exposure, fewer restricted accounts, longer allowance, then prepayment over a ban. This optimizes cash risk subject to preserving revenue and margin; restriction alone is not a revenue-growth mechanism. Include policy-off and prefer it if outcomes are otherwise identical.
- Financial comparisons use unrounded calculations with a small numeric tolerance; round only for display. Unknown-cost coverage remains visible for every candidate.

Do not optimize retention, prevention effectiveness, prepayment acceptance, or intervention cost: selecting 100% effectiveness or zero cost would optimize assumptions instead of business policy. Users can vary these sliders to see sensitivity. Defaults for those assumptions remain as above.

**One initial batch, then interactive experiments**

1. Reproduce the baseline before selecting defaults. Use Jan–Sep 2026 for pricing/damage scenario results, with the same-period 2025 figures only as historical context. Keep the full-window EDA figures above labeled as evidence, not the scenario baseline. Credit replay starts in January 2025 to establish observed account history; report its Jan–Sep 2026 sales/profit effects and October 31, 2026 exposure. Disclose any restrictions already in place at the start of 2026.
2. Pricing batch: 101 caps, retention fixed at 100%.
3. Damage batch: 101 triggers with 25% prevention and CAD 5/unit, recalculating targeted groups for each threshold. Group rates use the chosen scenario order cohort's observed returns; label this a retrospective experiment, not a deployable historical detector that knew future returns.
4. Credit batch: each integer G from 1 to 180 days under both prepayment and ban; prepayment acceptance fixed at 100%. Use the same chronological rules and observation cutoff in every replay. This batch is the first scope cut if time runs short; expose credit controls with an explicitly provisional 60-day default instead of claiming it was optimized.
5. Save the selected values, baseline/selected metrics, all evaluated candidates, objective/tie-break rules, assumptions, evaluation dates, and input file hashes together. Recompute this batch only when data, formulas, scope, or the fixed starting assumptions change. Do not run the full sweep on every page load or slider movement.
6. Slider changes run a single scenario through the same functions used for the batch. They do not automatically select new settings or create tasks. An explicit “Apply rules to simulation” button performs the condition checks and automatically creates the associated in-app tasks. The batch itself has no action side effects.
7. Initial manual checks: pricing at selected cap with retention 100%, 90%, 75%; damage effectiveness 0%, 25%, 50% and cost CAD 2/5/10; credit selected G versus 60/90 days and prepayment versus ban. These are examples to verify behavior, not fixed presets replacing sliders.

Persist a small result file at `output/simulations/defaults.json` when the simulation is implemented. It should contain `data_hashes`, `model_version`, `scope`, `assumptions`, and one result per module with `status`, `controls`, `selected_parameters`, `baseline_metrics`, `selected_metrics`, `deltas`, and `selection_reason`. Store sweep rows in `output/simulations/sweep_results.csv`. No placeholder numbers should appear as computed results. Percent deltas in rates are percentage points; monetary deltas are CAD.

**Integration handoff for the existing prototype**

The prototype is now present under `prototype/`. Extend its simulator rather than build another dashboard. Current `prototype/api/whatif.py` and `GET /api/whatif` support only quarter-end business orders and two retention endpoints (keep all / lose all); `prototype/api/main.py` currently rejects a zero cap. Those are implementation gaps for this plan, not completed features.

- Extend the simulator to accept zero, whole-percent cap/retention values, and return the selected-retention scenario with explicit period, scope, coverage, revenue, gross profit, weighted margin, refunds, and deltas.
- The new pricing simulator defaults to all valid orders in Jan–Sep 2026. Keep the existing quarter-end detector and its action workflow separately labeled; do not compare the old narrow-scope results with new all-order results as if only the cap changed.
- Existing condition IDs C1/C2/C3 are already used for other workflows. Add distinct simulator identifiers such as `pricing_policy`, `damage_policy`, and `credit_policy`; do not silently repurpose the existing customer-recovery condition.
- Add damage and credit scenario outputs with the same baseline/selected/delta envelope. Keep backend and UI mocks consistent in `prototype/docs/ui-contract.md` during implementation. This plan documents the requested extension; it does not pretend those API fields already exist.
- Data is duplicated between root `data/clean/` and `prototype/data/clean/chrome_oak/`. Verify they match before the initial batch and use the same source/hash for the optimizer and UI API. Do not quietly choose whichever folder is encountered first.
- Keep legacy Q4 run-rate projections out of the optimization objective: evaluate against observed-period scenarios. Display any retained projection separately with its assumptions.

Do not aggregate independent pricing, packaging, and credit headline gains into one combined total. A combined scenario must apply its rules to the same retained orders, with each refund and cost counted once. Defer that combined replay until the individual modules are reliable.

The packaging target was found using the complete dataset, so this is a retrospective sensitivity exercise, not out-of-sample validation. If time permits, fix rules from 2025 and report 2026 separately using information available at each decision date. Do not present the largest modeled gain as a proven best business policy.

**Interface and automatic actions**

One dashboard with rule toggles, policy settings, and assumption controls. Show baseline/scenario metrics and three evidence views: quarter-end discount/margin comparison, damage rate by product/region with denominators, and overdue aging/account status. Include a scenario comparison table with gains, costs, sales forgone, and coverage.

Applying a scenario automatically creates pricing-review, operations, or finance tasks as conditions fire. Each task has an owner role, source records, explanation, proposed mitigation, status, and event log. Deduplicate by scenario and order/group/account; identical reruns must not spam the queue. These are actual in-app actions, not just a count of flags. No external emails, integrations, interest charges, or credit scoring model are needed.

Optimize with a visible trade-off: increase contribution/profit while showing revenue sacrificed and outstanding exposure. Rank scenarios only within stated assumptions; expose cases where a margin percentage rises while gross-profit CAD falls.

**Four-hour execution**

- First 20 minutes together: freeze definitions, result-table format, and the three rules.
- Next 80 minutes: person 1 builds baseline plus discount/damage calculations; person 2 builds controls, charts, metrics, and the action queue.
- Next 60 minutes: person 1 adds the small credit-state replay; person 2 integrates cases, logs, and comparison views. If credit replay slips, retain its detection/action flow and finish the first two simulations.
- Next 40 minutes together: verify disabled rules reproduce baseline; zero damage improvement leaves only intervention cost; no missing cost becomes zero; credit restrictions do not affect earlier orders; tasks deduplicate.
- Final 40 minutes: rehearse a five-minute story—growth/margin gap, evidence for chosen rules, compare scenarios including a downside, trigger an action, recommend a policy conditional on the assumptions.
