// The whole navigation lives here. Each page names one page component (see App.jsx),
// so merging, renaming or reordering pages is an edit to this file only.
// `lead` may be a string or a function of the labels from /api/meta.

export const PAGES = [
  {
    key: "dataset", step: "01", label: "Dataset", hint: "Raw and clean files",
    title: "The three files",
    lead: "What we received, row by row and column by column. Switch to Clean to see the same views after cleaning, plus what was set aside and why.",
    page: "dataset",
  },
  {
    key: "gap", step: "02", label: "The gap", hint: "Growth vs profit, ranked drivers",
    title: "The gap between growth and profit",
    lead: "Where the difference went, which driver to fix first and why, and who among the executives is right.",
    page: "gap",
  },
  {
    key: "queue", step: "03", label: "Action queue", hint: "Rule-based alerts", badge: "openAlerts",
    title: "Action queue",
    lead: "Our rules flag, hold and notify on their own. Move a threshold and the queue reshapes live. A manager can release any alert with a written reason.",
    page: "queue",
  },
  {
    key: "whatif", step: "04", label: "What if", hint: "Replay 2026 with a cap",
    title: "What if quarter-end discounts had been capped?",
    lead: "Replays the 2026 orders with an approval rule: quarter-end discounts above the threshold are capped at it. Two outcomes bound the truth: the customer keeps the order at the cap, or walks away.",
    page: "whatif",
  },
  {
    key: "accounts", step: "05", label: "Accounts & Limits", hint: "Customers and reps",
    title: "Accounts and limits",
    lead: (L) => `Business ${L.entities}: credit limit against open balance, terms and days overdue. Reps: revenue gross, net of returns and quota-countable.`,
    page: "accounts",
  },
  {
    key: "ask", step: "06", label: "Ask", hint: "Read-only questions",
    title: "Ask the data",
    lead: "Plain-English questions over the clean tables. The AI writes one SELECT, a read-only connection runs it, and you see the query. It cannot create, clear or change an alert.",
    page: "ask",
  },
  {
    key: "log", step: "07", label: "Activity log", hint: "System and user steps",
    title: "Activity log",
    lead: "Every automatic step and every human decision, newest first, plus the outbox of who got notified. Nothing leaves the app: notify writes to this outbox.",
    page: "log",
  },
];
