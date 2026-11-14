# UI (React + Vite + Recharts)

```bash
cd ui
npm install
npm run dev
```

Opens on http://localhost:5173. The FastAPI back end must run on port 8000 (see `api/README.md`); Vite proxies `/api` to it.

## Data source

One switch in `ui/.env.local`:

| `VITE_API_BASE` | Effect |
|---|---|
| unset or `/` | Live API through the Vite proxy (default) |
| `http://host:8000` | That server directly |
| `mock` | Mock JSON only, from `src/mock/` |

In live mode, an endpoint the API does not serve yet falls back to its mock file, and the topbar pill says "Live API, N on mock" (hover it for the list). Every screen reads data through `src/data/api.js` only.

## Where things are

| Path | Role |
|---|---|
| `src/nav.js` | The five pages, their order, titles and one-line leads |
| `src/pages/` | The gap, Action queue, Accounts & Limits, Activity log, Ask |
| `src/components/` | Chart (incl. the bridge chart), FindingDetail (alert card), ThresholdSlider (rule control and live back-test), EntityDrawer (drill-down), Shell (sidebar, topbar, wordmark) |
| `src/theme/tokens.css` | Brand tokens. Chrome & Oak is the default; Millennium Mutual is kept but unused |
| `src/theme/app.css` | Layout and components, tokens only |
| `src/mock/` | Fallback JSON in `docs/ui-contract.md` shapes |

Before a demo run: `POST /api/admin/reset` on the back end clears overrides, drafts and advisory notes.
