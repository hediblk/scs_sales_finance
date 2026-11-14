# UI (React + Vite + Recharts)

```bash
cd ui
npm install
npm run dev
```

Opens on http://localhost:5173. The FastAPI back end must run on port 8000 (see `api/README.md`); Vite proxies `/api` to it. There is no placeholder data: if a call fails, the screen shows the error with a Retry button.

`VITE_API_BASE` in `ui/.env.local` points elsewhere if needed (`http://host:8000`). Every screen reads data through `src/data/api.js` only.

## Wiring: every control and the endpoint behind it

| Page | Control | Endpoint (or client-side job) |
|---|---|---|
| All | Sidebar navigation | Client: changes page |
| All | Open-alert badge on Action queue | `GET /api/alerts` (count of open alerts) |
| All | Drill-down panel (click a customer or rep anywhere) | `GET /api/entity/{id}` |
| Dataset | Raw / Clean switch, table cards | `GET /api/{raw\|clean}/tables` |
| Dataset | Column profile cards | `GET /api/{raw\|clean}/{table}/profile` |
| Dataset | Click a top value, search, sort a column, Previous / Next | `GET /api/{raw\|clean}/{table}/rows?col&val&q&sort&desc&offset&limit` |
| Dataset | Raw / clean charts, Table toggle | `GET /api/{raw\|clean}/charts` (toggle is client-side) |
| Dataset | Set-aside panel, Values | `GET /api/clean/set-aside` (Values is client-side) |
| Dataset | Explore chart (Clean) | `GET /api/explore` |
| The gap | KPI tiles, who is right, recommendation | `GET /api/overview` |
| The gap | Bridge chart (click a bar: scroll to its driver, show the refund split) | `GET /api/gap` |
| The gap | Driver cards, "Handled in the tool" links | `GET /api/gap` (links navigate) |
| The gap | Driver charts: metric / group by / split, filter bar, click to drill, Back to the story view | `GET /api/explore`, `GET /api/explore/options` |
| Any chart | See these orders: Action queue / Ask | Client: opens the queue with filters, or sends a question to `POST /api/ask` |
| Action queue | Rule sliders (C1 discount and window, C2, C3) | `GET /api/simulate`, then `GET /api/alerts?condition&value&window` |
| Action queue | Rule tabs, status, rep, region, segment, id search | Client: filters the alerts already loaded |
| Action queue | Alert card: reasons, what happened next | `GET /api/alerts`, `GET /api/actions` |
| Action queue | Advisory note | `POST /api/alerts/{id}/triage` |
| Action queue | Email draft (editable), Copy text | `POST /api/alerts/{id}/draft` (copy is client-side) |
| Action queue | Release quota credit / Close the task / Override, with a reason | `POST /api/alerts/{id}/override` |
| Action queue | Ask about this alert | `POST /api/ask` with `alert_id` |
| What if | Discount and window sliders, results, bridge toggle, Q4 run-rate, assumptions | `GET /api/whatif?threshold&window&rule=cap` (toggle is client-side) |
| Accounts & Limits | Customers: tiles, cards, segment chips, search, sort | `GET /api/accounts` (filters are client-side) |
| Accounts & Limits | Reps: quarter tabs, table | `GET /api/reps` (tabs are client-side) |
| Activity log | All / System / User / Outbox, recipient chips, search | `GET /api/actions` (filters are client-side) |
| Ask | Question box, suggestions, Ask | `POST /api/ask` |

Times in the activity log: rows from the automatic chains carry the date only (`ts_precision: "day"`, the data has no time of day); rows a person wrote keep their real time.

## Where things are

| Path | Role |
|---|---|
| `src/nav.js` | The pages, their order, titles and one-line leads |
| `src/pages/` | Dataset, The gap, Action queue, What if, Accounts & Limits, Activity log, Ask |
| `src/components/DynamicChart.jsx`, `Filters.jsx` | The one chart component on `/api/explore`, and the per-page filter bar |
| `src/components/` | Bridge chart, alert card (FindingDetail), rule sliders, drill-down panel, shell |
| `src/theme/tokens.css` | Brand tokens (Chrome & Oak is the default) |
| `src/theme/app.css` | Layout and components, tokens only |

Before a demo run: `POST /api/admin/reset` on the back end clears overrides, drafts and advisory notes.
