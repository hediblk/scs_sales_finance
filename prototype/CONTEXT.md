# Y2K hackathon: context carried over from the planning session (2026-11-14)

> **Update:** Option B is LOCKED. `docs/PLAN.md` is the source of truth for the problem, conditions, actions, scope and pitch. The "Target automation" section below (collections credit hold) is superseded: the data pointed to the quarter-end discount push instead.

Event: Hack 2 The Future, **Business Track** ("From Data to Decisions to Action").
Brief: `docs/Business Track - Participants.pdf`. Slide photo: `docs/track-slide.webp`.

## Event rules that shape everything

- 2 people, **4 hours** of dev time.
- **Code written before the event is not allowed.** Starter templates (create-vite, blank Streamlit) and libraries are fine. Everything is written during the event.
- Flow to follow: DATA → DETECT → DECIDE → ACT.
- Minimum: clear business problem; prepared data with reasoning behind each main transformation; 2+ insights (what happened / why it matters / what to do); 2+ visualizations; a working prototype (a CLI alone does not count); **2+ detected conditions and 1+ action triggered automatically**, justified by the insights.
- AI allowed, but it cannot be the whole solution. **At least one detection must be logic the team wrote and can explain.** AI can summarize, explain or draft on top.
- Bonus: simulation (threshold slider), multi-step automation (detect → who → recommend → notify → log), AI-assisted review, interactive drill-down.
- Pitch: 5 min demo + 2 to 3 min Q&A, **no slides**, the app tells the story (1 min problem, 1.5 min insights, 2 min live automation, 30 s recommendation).
- Data has no dictionary and is not clean, on purpose.

## Decision: Option B, Chrome & Oak Office Supply

Montreal office-equipment seller (founded 2000). Channels: website consumers, account reps for small and large businesses, resellers. Reps give discounts and have quarterly targets with bonuses. Business customers pay on terms (Net 30 / Net 60) and have a credit limit. Returns are refunded; damaged items usually can't be resold.

Data: `customers.csv`, `orders.csv`, `returns.csv`, orders Jan 2025 to Sep 2026, extracted 2026-10-31. **Not received yet.**

Exec claims to test (the data decides who is right):
- CEO: revenue up about a third, Atlantic team punches above its weight.
- CFO: cash tight, profit not keeping up, chasing unpaid invoices weekly.
- Operations: returns eat warehouse time, especially big items.
- Customer Success: long-time business customers went quiet.

Fallback: **Option A, Millennium Mutual (insurance)**, if Chrome & Oak data looks flat or broken in the first 30 minutes. Hook there: claims under $10,000 skip senior review, so look for claims bunched just under $10k (possibly via new brokers), office overload, slow payouts and lost renewals.

## Design principles

1. The action fires on its own: flag, hold, notification and log entry happen without a click; a human can override with a reason (which also answers "what if the automation is wrong?").
2. Detection is 100% pandas rules written by the team; AI only writes the email text or a summary.
3. Numbers always come from code, never from the model.
4. Robust baselines (median + MAD) so one huge order can't hide the rest.
5. Every screen exists because of something the data showed.

## Stack

Updated 2026-11-14: **React + Vite + Recharts** UI in `ui/` (session `y2k-ui`), branded as Chrome & Oak; **FastAPI + pandas** in `api/`; analysis in `explore/`. Shared shapes in `docs/ui-contract.md`. Nav: **DATA / DETECT / DECIDE / ACT**. Nav order = pitch order.

## First 45 minutes: one query per exec claim

- CEO: revenue and margin by region and rep; discount vs list price; discount by week within quarter (spike before quarter end = target gaming).
- CFO: due date = order date + terms; days overdue per customer; balance vs credit limit; which reps sell to over-limit customers.
- Ops: return rate by product, rep and region; returns right after quarter-end orders (stock pushed onto resellers).
- Customer Success: days since last order vs each business customer's usual gap.

Possible single story (a guess until the data confirms): Atlantic hits targets with deep discounts and quarter-end orders to resellers already over their credit limit, which explains low margin, unpaid invoices and returns.

## Cleaning traps to check

Duplicate order IDs; refund or negative rows counted as revenue; mixed date formats; prices as text ("$1,234"); region spelled several ways; returns with no matching order; customer IDs that don't match across files; orders outside the Jan 2025 to Sep 2026 window. Log every fix with rows touched and its effect on the numbers (the DATA tab shows this).

## Target automation (if the data supports it)

- Condition 1: business customer with an invoice more than X days overdue, or balance above credit limit.
- Condition 2: rep discount above Y%, or above the rep's own usual level, in the last 2 weeks of a quarter.
- Condition 3 (optional): long-time customer silent for more than 2x their usual gap.
- Action chain on condition 1: auto credit hold on next order → find owning rep → draft collections email (numbers from pandas, wording from AI) → notify rep + CFO → log row. Override button with a reason, also logged.
- Slider: "Hold at 30 / 45 / 60 days overdue: N customers, $X at risk."

## Time split (2 people)

- 0:00 to 0:45, both: load data, test the 4 claims, pick the problem.
- 0:45 to 2:30: person 1 cleaning + insights + charts; person 2 rules + action chain + log.
- 2:30 to 3:30: assemble Streamlit tabs, slider, drill-down, AI email.
- 3:30 to 4:00: rehearse the 5-minute demo.

The team must be able to explain every line shown; judges ask about reasoning.
