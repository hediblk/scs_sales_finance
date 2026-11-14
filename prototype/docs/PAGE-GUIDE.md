# Page guide: what each page does and what to say

Story: **revenue on paper is not cash in the bank.** It comes back (quarter-end discount push, C1) or it is never paid (unpaid invoices, C3).
Menu, in pitch order: **Dataset → Data cleaning → The gap → Action queue → What if → Accounts & Limits → Ask → Activity log.** Numbers are provisional until Hedi confirms them.

## 1. Dataset ("what we received")
- **Raw / Clean switch**: the 3 files as received, or after cleaning.
- File cards (rows, what a row is, key), the join diagram (customers 1 → many orders 1 → 0 or 1 return, 100% match).
- Column table with flags: 15 region spellings, 122 slash dates, 8 negative quantities, 182 discounts above 1 in Raw (181 after removing duplicates), 92 blank costs.
- Explore chart (pick measure, group by, split) and the searchable raw table.
- **Say**: "No data dictionary, data not clean. Flip to Clean: 15 spellings become 5."

## 2. Data cleaning ("what we fixed and why", Hedi's page)
- Every step: rows deleted, set aside, fixed or left blank, the assumption behind it, and what it changes between raw and clean numbers.
- **Say**: "The 181 discounts stored as 22.5 would show negative revenue, inside the exact analysis our finding rests on."

## 3. The gap ("the problem")
- 4 tiles: revenue +33%, profit after refunds +10%, 207 quarter-end discount orders, $135k overdue.
- Bridge: growth at list price $1.26M, extra discounts -$296k, revenue +$968k, extra cost of goods -$782k, extra refunds -$118k, **profit after refunds +$68k**.
- **Two ways revenue fails to become cash**, each with what happened, why, what to do, the rule that handles it, and its charts:
  1. It comes back: the quarter-end discount push (R07, Atlantic resellers).
  2. It is never paid: unpaid invoices, $135k, small and flat since 2025.
- **Say**: "Revenue grew $968k, profit after refunds $68k. Revenue on paper is not cash."

## 4. Action queue ("the automation")
- Rule card: business order in the last 14 days of a quarter with discount 25% or more; sliders; "would have flagged 207 orders, $892,567"; 205 are R07's; returned 25.1% vs 4.2%.
- Second rule: unpaid or over credit limit, detection only.
- Alert card (open **qe-SO-006720**): why it fired, what happened with no click (quota credit held 45 days, sales manager and CFO notified), **Ask about this alert** (main action), **Email draft**, **Release** with a written reason.
- **Say**: "Nobody clicked: the rule flagged it, held the quota credit and notified."

## 5. What if ("what the rule would earn")
- Forecast chart by quarter, 2025Q1 to 2027Q1: today's policy vs the rules on; solid = actual, dashed = projection. Switch: revenue / gross profit / refunds / profit after refunds. Strip: next quarter, the 2026 replay, overdue exposure.
- One row per rule (on/off + slider) with a live sentence. Opens at **cap 25%, credit 60 days**.
- **Say**: "With a 25% cap, 2026 profit after refunds would be $109k higher; next quarter goes from $269k to $308k. It pays off as long as 45% of affected customers keep buying. The projection is a run-rate, not a model."

## 6. Accounts & Limits (the cards)
- Customers: 310 business customers, $250k open, 1 over its limit, 3 past 60 days; one card per customer (balance vs limit, terms, days overdue); click for the detail.
- Reps: revenue per quarter (gross, net of returns, quota-countable after the holds), discount vs the team.
- **Say** (if asked about unpaid invoices): "C1173 owes $27.6k on a $25k limit, 221 days overdue; only 3 customers are past 60 days."

## 7. Ask (read only)
- Plain-English question → chart picked by code, 1 or 2 sentences, the SQL, the table. Reads only the 3 clean tables, refuses anything else, changes nothing.
- Best from an alert: "Has this order been returned, and how often did this reseller's earlier quarter-end orders come back?"

## 8. Activity log (the audit trail, last in the menu)
- Every automatic step (flag, quota hold, notify) and every human decision (release with its reason, email draft), newest first; filter by recipient to see the outbox (sales manager, CFO, reps).
- **Say** (only if asked "how do you know it really did it?"): "Here's every step the rule took on its own, and who overrode what, with their reason."
