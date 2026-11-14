# Back end (FastAPI + pandas)

```bash
.venv/Scripts/python.exe -m uvicorn api.main:app --port 8000 --reload
```

```bash
.venv/Scripts/python.exe -m api.check
```

| File | Role |
|---|---|
| `pipeline.py` | `load()` reads `data/clean` as it is (the API never rewrites it). `build()` / `write_outputs()` are the earlier cleaning, kept for reference; the teammate owns cleaning now |
| `dataset.py` | Dataset page: `/api/{raw,clean}/...` tables, profile, rows, charts, set-aside. Everything read as text |
| `gap.py` | The gap bridge, ranked drivers, who-is-right, why-first. Provisional until the teammate's data is in |
| `accounts.py` | Accounts & Limits: business customers, reps by quarter, advisory credit hold and targets |
| `ask.py` | Read-only Ask: one SELECT on a read-only DuckDB copy of the clean tables, external access off, 500-row cap, a chart picked by code for every non-empty result |
| `detect.py` | C1 `qe_discount`, C2 `quiet_after_bad_return`, C3 `overdue_or_over_limit`. Plain pandas, thresholds as arguments, reasons per alert |
| `actions.py` | The automatic chains, rules only (flag, quota_hold, notify, release / resolve, winback_task), overrides, drafts, the advisory note, the action log |
| `ai.py` | Advisory note and email wording on top of computed facts. Model `claude-opus-5-5`, low effort, server-side refusal fallback. Template text when there is no key, an error, or a number in the AI text that is not in the facts |
| `story.py` | Overview KPIs, charts, insights, who-is-right, recommendation, customer and rep drill-downs |
| `main.py` | Endpoints on `docs/ui-contract.md` |
| `check.py` | Recomputes the headline numbers and compares them with `docs/PLAN.md` |

AI: put `ANTHROPIC_API_KEY=...` in `.env` at the project root (gitignored) to switch from template text to AI wording. Numbers and decisions never come from the model.

Demo reset: `POST /api/admin/reset` clears overrides, drafts, advisory notes, credit holds and targets.
