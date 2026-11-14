// The only data layer. Every screen calls these functions, never fetch() directly.
// No placeholder data: a failed call throws, and the screen shows an inline error with Retry.
//
// One switch: VITE_API_BASE (in ui/.env.local).
//   unset or "/"        -> same origin, through the Vite proxy to http://localhost:8000 (default)
//   "http://host:8000"  -> that server directly (the API allows CORS)

const RAW = import.meta.env.VITE_API_BASE;
const API_BASE = !RAW || RAW === "/" ? "" : RAW.replace(/\/+$/, "");

async function request(method, path, body) {
  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error("The back end is not answering (is it running on port 8000?)");
  }
  if (res.ok) return res.json();
  const text = await res.text();
  let detail = text;
  try { detail = JSON.parse(text).detail ?? text; } catch { /* not JSON */ }
  if (res.status === 404 && detail === "Not Found") {
    throw new Error(`${path.split("?")[0]} is not served by the back end yet`);
  }
  if (res.status >= 502 || (res.status === 500 && !text.trim().startsWith("{"))) {
    throw new Error("The back end is not answering (is it running on port 8000?)");
  }
  throw new Error(typeof detail === "string" && detail ? detail : `${method} ${path} failed (${res.status})`);
}

const q = (params) =>
  new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")).toString();

export const api = {
  // Dataset page: source = "raw" (data/raw as received) or "clean" (data/clean).
  dsTables: (source) => request("GET", `/api/${source}/tables`),
  dsProfile: (source, table) => request("GET", `/api/${source}/${table}/profile`),
  // col + val filter; an empty val means "blank cells in that column", so it is always sent with col.
  dsRows: (source, table, { val, ...p } = {}) =>
    request("GET", `/api/${source}/${table}/rows?${q(p)}${p.col ? `&val=${encodeURIComponent(val ?? "")}` : ""}`),
  dsCharts: (source) => request("GET", `/api/${source}/charts`),
  setAside: () => request("GET", "/api/clean/set-aside"),

  // Every chart in the app is a preset of this endpoint (docs/ui-contract.md, "Dynamic charts").
  explore: (params) => request("GET", `/api/explore?${q(params)}`),
  exploreOptions: () => request("GET", "/api/explore/options"),

  // Policy simulator (docs/ui-contract.md, "Policy simulator"; spec docs/simulator-plan.md).
  simulator: () => request("GET", "/api/simulator"),
  simModule: (name, params) => request("GET", `/api/simulator/${name}?${q(params ?? {})}`),
  simSweep: (name) => request("GET", `/api/simulator/sweep/${name}`),
  // What if forecaster: today's policy vs the rules on, by quarter (run-rate for the next two quarters).
  forecast: (params = {}) => request("GET", `/api/forecast?${q(params)}`),

  whatif: (threshold, window) => request("GET", `/api/whatif?${q({ threshold, window, rule: "cap" })}`),

  meta: () => request("GET", "/api/meta"),
  overview: () => request("GET", "/api/overview"),
  gap: () => request("GET", "/api/gap"),
  conditions: () => request("GET", "/api/conditions"),
  simulate: (condition, value, window) => request("GET", `/api/simulate?${q({ condition, value, window })}`),
  alerts: (condition, value, window) => request("GET", `/api/alerts?${q({ condition, value, window })}`),
  entity: (id) => request("GET", `/api/entity/${encodeURIComponent(id)}`),
  alert: (alertId) => request("GET", `/api/alerts/${encodeURIComponent(alertId)}`),
  draft: (alertId) => request("POST", `/api/alerts/${encodeURIComponent(alertId)}/draft`),
  triage: (alertId) => request("POST", `/api/alerts/${encodeURIComponent(alertId)}/triage`),
  override: (alertId, reason) => request("POST", `/api/alerts/${encodeURIComponent(alertId)}/override`, { reason }),
  actions: () => request("GET", "/api/actions"),
  accounts: () => request("GET", "/api/accounts"),
  reps: () => request("GET", "/api/reps"),
  // A question starting with SELECT is sent as `sql` and runs as written (still read-only on the API side).
  ask: (question, alertId) => request("POST", "/api/ask", /^\s*select\b/i.test(question)
    ? { question, sql: question, alert_id: alertId ?? null }
    : { question, alert_id: alertId ?? null }),
};
