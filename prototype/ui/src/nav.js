// The whole navigation lives here. Each page names one page component (see App.jsx),
// so merging, renaming or reordering pages is an edit to this file only.
// `lead` may be a string or a function of the labels from /api/meta.
// Nav order = pitch order: the data, the problem, the automation, then exploring an alert.

export const PAGES = [
  {
    key: "dataset", step: "01", label: "Dataset", hint: "Raw and clean files",
    title: "The three files",
    lead: "What we received, row by row and column by column. Switch to Clean to see the same views after cleaning, plus what was set aside and why.",
    page: "dataset",
  },
  {
    key: "cleaning", step: "02", label: "Data cleaning", hint: "Assumptions, raw vs clean",
    title: "How we cleaned the data",
    lead: "Every row we deleted, set aside, fixed or left blank, the assumption behind it, and what it changes between the raw and the clean numbers.",
    page: "cleaning",
  },
  {
    key: "gap", step: "03", label: "The gap", hint: "Revenue on paper vs cash",
    title: "Revenue on paper is not cash in the bank",
    lead: "Revenue grew a third, profit after refunds barely moved. Booked revenue fails to become cash in two ways: it comes back, or it is never paid.",
    page: "gap",
  },
  {
    key: "queue", step: "04", label: "Action queue", hint: "Rules that act on their own", badge: "openAlerts",
    title: "Action queue",
    lead: "Our rules check every order. A deep quarter-end discount puts the rep's quota credit on hold for 45 days and notifies the sales manager and CFO, with no click. A manager can release it with a written reason.",
    page: "queue",
  },
  {
    key: "whatif", step: "05", label: "What if", hint: "Forecast with the rules on",
    title: "Forecast: what the rules would earn",
    lead: "Today's policy against the rules on, quarter by quarter. Turn a rule on or off, or move its setting, and the forecast follows.",
    page: "whatif",
  },
  {
    key: "accounts", step: "06", label: "Accounts & Limits", hint: "Customers and reps",
    title: "Accounts and limits",
    lead: (L) => `Business ${L.entities}: credit limit against open balance, terms and days overdue. Reps: revenue gross, net of returns and quota-countable.`,
    page: "accounts",
  },
  {
    key: "ask", step: "07", label: "Ask", hint: "Read-only questions",
    title: "Ask the data",
    lead: "Plain-English questions over the clean tables, or open it from an alert to dig into why it fired. The AI writes one SELECT, a read-only connection runs it, and you see the query. It cannot change an alert.",
    page: "ask",
  },
  {
    key: "log", step: "08", label: "Activity log", hint: "System and user steps",
    title: "Activity log",
    lead: "Every automatic step and every human decision, newest first, plus the outbox of who got notified. Nothing leaves the app: notify writes to this outbox.",
    page: "log",
  },
];
