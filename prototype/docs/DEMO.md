# Demo: 5 minutes + Q&A

Numbers below come from the running API (`/api/gap`, `/api/conditions`, `/api/alerts`) on 2026-11-14 at 13:07. They are **provisional** until the teammate confirms the three bridge values (extra discounts, extra cost of goods, profit after refunds). Re-check them right before the pitch.

Suggested split: **teammate** presents the data part (they own it), **you** present the problem, the demo and the recommendation.

## Before you start (5 min before)

- [ ] API running on 8000, UI on 5173, browser on The gap page, zoom so the bridge fits the screen.
- [ ] Reset the action log (`POST /api/admin/reset`) so the demo starts clean.
- [ ] Close other tabs and notifications. Phone on silent.
- [ ] Backup ready: screenshots of each step in a folder, in case the live demo breaks.

## Script

### 0:00 to 1:00 · The problem (you, on The gap)
- "Chrome & Oak's revenue grew **$968k** this year, up 33%. Profit after refunds grew **$68k**. That gap is what we were asked to explain."
- Walk the bridge left to right: growth at list price $1.26M, minus **$296k of extra discounts**, minus extra cost of goods, minus **$118k of extra refunds**, leaves $68k.
- "Each exec had a theory. The data says:" one line each from the who-is-right table (CEO right on revenue, wrong on Atlantic; CFO right on profit, but unpaid invoices are small and flat; Ops and Customer Success right, and they describe the same problem).

### 1:00 to 2:30 · What we found and why (teammate, on The gap + Dataset)
- Cleaning in one sentence, on the Dataset page Raw / Clean switch: "181 discounts were stored as 22.5 instead of 0.225. Left as is, they show negative revenue, inside the exact analysis our main finding rests on." Flip Raw / Clean on the region chart: 15 spellings become 5.
- Driver 1, the quarter-end push: R07, the only Atlantic rep, books about half of their revenue in the last 14 days of each quarter at a 27% average discount (others 9 to 12%). Orders discounted 30 to 40% come back 23% of the time. All 46 overstock returns come from those resellers, 20 to 44 days later.
- Driver 2 and 3: furniture damaged on the way to BC and the Prairies; business customers who had a bad return went quiet twice as often.
- Why #1 first: biggest piece the company controls, new in 2026, one cause, a rule catches it with almost no false alarms.

### 2:30 to 4:30 · Live demo (you, on Action queue)
1. Open the Action queue. "207 orders were flagged by our rule: business order, last 14 days of a quarter, discount 25% or more. 205 are R07's."
2. Open **qe-SO-006720** (reseller C1179, R07, $11,781, ordered 2026-09-29, one day before quarter end). Read the reasons: discount 34.5% vs company median 10.1%, **sold below cost (margin -2.5%)**, R07 booked 61% of Q3 revenue in the last 14 days, this reseller already sent overstock back once.
3. Point at what happened automatically: status **auto_held** (quota credit held 45 days, the order still ships), sales manager and CFO notified, every step in the Activity log.
4. Move the threshold slider from 25% to 20%: "would have flagged" count and dollars change live. Back to 25%: "Every other rep stays under 20.6% in 99% of their orders."
5. Release one held order with a reason. Show the user row in the Activity log next to the system rows.
6. Switch to C2: return **RT-00270** (SMB C1030, 6 defective office chairs, $2,128 refunded, orders every 41 days). A Customer Success task was opened, the rep notified, an apology email drafted (open the draft).
7. Open **What if**. "If this rule had been on in 2026": profit after refunds would have been between [$A, customer walks away] and [$B, customer keeps the order at 25%], against $68k actual. Move the threshold slider once; the range and the redrawn bridge follow. Point at the Q4 2026 line: "rough run-rate, not a forecast". Fill [$A] and [$B] from the page once it runs.
8. If time: "Ask about this alert" on SO-006720, one question, the chart appears.

### 4:30 to 5:00 · Recommendation (you)
1. Pay quota on revenue still kept after 45 days, and require approval for quarter-end discounts of 25% or more. Our tool already does the hold.
2. Fix long-haul furniture shipping to BC and the Prairies, and call every business customer right after a bad return. Our tool opens the task.
3. Collections: keep as is. It isn't what changed.

## Q&A cheat sheet

| Question | Answer |
|---|---|
| Aren't you just catching R07 by design? | The 25% comes from the rest of the team (99th percentile 20.6%, company median 10.1% + 3 MAD = 27%). Set on 2025 data only and applied to 2026, 124 of 141 hits are still R07. Any rep crossing it gets caught. |
| Customers going quiet is $618k, bigger than the quarter-end push. Why is it not first? | The $618k is spend at risk, and the link to bad returns is timing, not proven cause. The quarter-end push is a loss that already happened, new in 2026, with one cause a rule can catch. |
| Is Atlantic just selling a cheaper mix? | At the company's common product mix its margin is still 17.5% vs about 32% elsewhere. It's pricing. |
| Why not block the order? | The CEO wants growth. We stop paying quota on revenue that comes back; the order still ships. |
| What if the automation is wrong? | C1 delays quota credit by 45 days; C2 triggers a courtesy call. Both reversible, both logged with who released it and why. |
| Why 45 days? | Every overstock return in the data came back between 20 and 44 days. |
| How do you know dates are month first? | Reading them day first would put orders after the extraction date. |
| Where is the AI? | Only text and read-only questions: email wording, the advisory note, and Ask, which can only run SELECT queries. Every flag, severity and dollar is our pandas code. |
| Quota and notifications aren't in the data. | Right: the hold is a status our tool sets and "notify" writes to an outbox in the app. In production it would plug into payroll and email. |
| Is the What if page a forecast? | No. It replays 2026 orders with the rule on, with two bounds: the customer keeps the order at the capped discount, or walks away. The truth sits between them. The Q4 line is a run-rate, labelled as such. |
| What did cleaning change? | The 181 percent-style discounts would show negative revenue; 25 duplicates double-counted sales; 8 negative quantities set aside; 92 missing costs kept blank, never invented. |
