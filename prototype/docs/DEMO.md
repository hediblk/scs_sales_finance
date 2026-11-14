# Demo: 5 minutes + Q&A (Hedi's one-story version + forecast)

Story: **revenue on paper is not cash in the bank.** It fails in two ways: it comes back (quarter-end discount push, C1) or it is never paid (unpaid invoices, C3).
Menu: Dataset, Data cleaning, The gap, Action queue, What if, Accounts & Limits, Ask.
Numbers read from the running API on 2026-11-14; provisional until Hedi confirms them.

## Before you start (5 min before)
- [ ] `run-demo.bat` (Windows) or `./run-demo.sh` (Mac/Linux); browser on The gap, zoom so the bridge fits.
- [ ] Reset the user actions: `POST /api/admin/reset`.
- [ ] What if opens at Pricing cap 25% and Credit 60 days. If it shows anything else, set those two sliders.
- [ ] Backup screenshots ready in `docs/screens/`.

## Script

### 0:00 to 1:00 · The problem (The gap)
- "Revenue grew **$968k** (+33%). Profit after refunds grew **$68k** (+10%). Revenue on paper is not cash."
- Walk the bridge: growth at list price $1.26M, minus **$296k** extra discounts, minus extra cost of goods, minus **$118k** extra refunds, leaves $68k.
- "It fails in two ways: it comes back, or it is never paid."

### 1:00 to 2:30 · What we found (Data cleaning, then The gap)
- Data cleaning, one sentence: "181 discounts were stored as 22.5 instead of 0.225: left as is they show negative revenue, inside the exact analysis our finding rests on."
- Driver 1, it comes back: R07, the only Atlantic rep, books about half of their revenue in the last 14 days of each quarter at a 27% average discount (others 9 to 12%). Orders discounted 30 to 40% come back 23% of the time. All 46 overstock returns come from those resellers, 20 to 44 days later.
- Driver 2, it is never paid: $135k overdue, real but small and flat since 2025.
- Why #1 first: new in 2026, one cause (a quota paid on gross revenue), a rule catches it with almost no false alarms.

### 2:30 to 4:15 · The automation (Action queue)
1. "Our rule: business order in the last 14 days of a quarter with a discount of 25% or more. It flagged 207 orders, 205 are R07's."
2. Open **qe-SO-006720** (Reseller C1179, R07, $11,781, one day before quarter end): discount 34.5% vs company median 10.1%, **sold below cost**, this reseller already sent overstock back.
3. What happened, no click: quota credit held 45 days (the order still ships), sales manager and CFO notified.
4. **Email draft**: numbers from our code, wording by the AI.
5. **Ask about this alert**: "Has this order been returned, and how often did this reseller's earlier quarter-end orders come back?" The chart appears.
6. Release one alert with a written reason.

### 4:15 to 4:45 · What it would earn (What if)
- "If this rule had been on in 2026, with a 25% cap, profit after refunds would have been **$109k** higher; next quarter goes from **$269k** to **$308k**." Move the cap slider once, the forecast redraws.
- "The cap pays off as long as **45%** of affected customers keep buying."
- "The projection is a run-rate: same quarter last year times this year's growth, not a model."

### 4:45 to 5:00 · Recommendation
1. Pay quota on revenue still kept after 45 days, and require approval for quarter-end discounts of 25% or more. The tool already does the hold.
2. Unpaid invoices: follow up only the clear cases (long overdue or over the limit), the tool flags them.

## Q&A cheat sheet

| Question | Answer |
|---|---|
| Aren't you just catching R07 by design? | The 25% comes from the rest of the team (99th percentile 20.6%, company median 10.1% + 3 MAD = 27%). Set on 2025 only and applied to 2026, 124 of 141 hits are still R07. Any rep crossing it is caught. |
| Is Atlantic just selling a cheaper mix? | At the company's common product mix its margin is still 17.5% vs about 32% elsewhere. It's pricing. |
| Why not block the order? | The CEO wants growth. We stop paying quota on revenue that comes back; the order still ships. |
| What if the automation is wrong? | The quota credit waits 45 days, a manager releases it with a reason, logged. |
| Why 45 days? | Every overstock return came back between 20 and 44 days. |
| Is the forecast a model? | No: a replay of 2026 with the rule on, plus same quarter last year x this year's growth. Labelled on screen. |
| Would you never give discounts? | No. The cap is 25%, and it pays off as long as 45% of affected customers keep buying. |
| How do you know dates are month first? | Day first would put orders after the extraction date. |
| Where is the AI? | Email wording and Ask (read-only SELECT). Every flag, hold and dollar is our pandas code. |
| What about damaged furniture? | Real (BC 16.9%, Prairies 15.4% of furniture revenue), but the fix is operational (packaging, carrier), so it stays out of this tool. |
| Quota and notifications aren't in the data. | Right: the hold is a status our tool sets, and notify writes to an in-app outbox. |
