# Who edits what (no overlap)

One writer per file. Before editing a file you don't own, ask the planning session. Reading anything is fine.

| Session | Owns (only this session edits these) |
|---|---|
| **y2k-hackathon** (back end) | `api/**`, `data/**`, `output/**`, `explore/**`, `docs/ui-contract.md` |
| **y2k-ui** (UI 1) | `ui/src/pages/DatasetPage.jsx`, `ui/src/pages/WhatIfPage.jsx`, `ui/src/pages/GapPage.jsx`, `ui/src/components/**` **except** `FindingDetail.jsx`, `ui/src/theme/**`, `ui/src/nav.js`, `ui/src/App.jsx`, `ui/src/main.jsx`, `ui/src/data/api.js`, `ui/src/lib/**`, `ui/README.md`, `ui/package.json`, `docs/screens/**` |
| **y2k-ui-dataset** (UI 2: Ask bug, QA) | `ui/src/pages/AskPage.jsx`, `ui/src/pages/AccountsPage.jsx`, `ui/src/pages/LogPage.jsx`, `ui/src/pages/QueuePage.jsx`, `ui/src/components/FindingDetail.jsx`, `ui/src/state.jsx` |
| **Planning session** | `docs/PLAN.md`, `docs/DEMO.md`, `docs/OWNERS.md`, `docs/simulator-plan.md`, `docs/backend-pipeline.pdf`, `CONTEXT.md`, `run-demo.bat`, `.gitignore`, all git commits and pushes |

Rules:
- Need a change in a file you don't own (a new call in `api.js`, a style in `app.css`, a new endpoint)? Message its owner; don't edit it.
- New files: create them inside your own folders above.
- No session commits; the planning session commits.
- Never write the old project's name.
