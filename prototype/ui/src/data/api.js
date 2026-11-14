// The only data layer. Every screen calls these functions, never fetch() directly.
//
// One switch: VITE_API_BASE (in ui/.env.local).
//   unset or "/"        -> same origin, through the Vite proxy to http://localhost:8000 (default)
//   "http://host:8000"  -> that server directly (the API allows CORS)
//   "mock"              -> mock JSON only (src/mock/, served by mockServer.js)
//
// In API mode, an endpoint the back end does not serve yet (404 "Not Found") or a back end
// that is down falls back to the mock for that endpoint only. The UI shows which ones.
import { handle as mockHandle } from "./mockServer.js";

const RAW = import.meta.env.VITE_API_BASE;
const MOCK_ONLY = RAW === "mock";
const API_BASE = !RAW || RAW === "/" || MOCK_ONLY ? "" : RAW.replace(/\/+$/, "");
export const SOURCE = MOCK_ONLY ? "mock" : "api";

// Which endpoints are currently answered by the mock (shown in the topbar).
const mocked = new Set();
const listeners = new Set();
const routeKey = (path) => path.split("?")[0].replace(/\/(C|R)\d+[^/]*$/, "/:id").replace(/\/alerts\/[^/]+\//, "/alerts/:id/");
function markMocked(path, on) {
  const k = routeKey(path);
  if (on === mocked.has(k)) return;
  on ? mocked.add(k) : mocked.delete(k);
  listeners.forEach((fn) => fn([...mocked]));
}
export function onMockedChange(fn) {
  listeners.add(fn);
  fn([...mocked]);
  return () => listeners.delete(fn);
}

async function request(method, path, body) {
  if (MOCK_ONLY) {
    markMocked(path, true);
    return mockHandle(method, path, body);
  }
  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    markMocked(path, true);
    return mockHandle(method, path, body); // back end unreachable
  }
  if (res.ok) {
    markMocked(path, false);
    return res.json();
  }
  const text = await res.text();
  let detail = text;
  try { detail = JSON.parse(text).detail ?? text; } catch { /* not JSON */ }
  const routeMissing = res.status === 404 && detail === "Not Found";
  const backendDown = res.status >= 502 || (res.status === 500 && !text.trim().startsWith("{"));
  if (routeMissing || backendDown) {
    markMocked(path, true);
    return mockHandle(method, path, body);
  }
  throw new Error(typeof detail === "string" ? detail : `${method} ${path} failed: ${res.status}`);
}

const q = (params) =>
  new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")).toString();

export const api = {
  // Dataset page: source = "raw" (data/raw as received) or "clean" (data/clean).
  dsTables: (source) => request("GET", `/api/${source}/tables`),
  dsProfile: (source, table) => request("GET", `/api/${source}/${table}/profile`),
  dsRows: (source, table, p = {}) => request("GET", `/api/${source}/${table}/rows?${q(p)}`),
  dsCharts: (source) => request("GET", `/api/${source}/charts`),
  setAside: () => request("GET", "/api/clean/set-aside"),

  meta: () => request("GET", "/api/meta"),
  dataPrep: () => request("GET", "/api/data-prep"),
  overview: () => request("GET", "/api/overview"),
  gap: () => request("GET", "/api/gap"),
  insights: () => request("GET", "/api/insights"),
  conditions: () => request("GET", "/api/conditions"),
  simulate: (condition, value, window) => request("GET", `/api/simulate?${q({ condition, value, window })}`),
  alerts: (condition, value, window) => request("GET", `/api/alerts?${q({ condition, value, window })}`),
  entity: (id) => request("GET", `/api/entity/${encodeURIComponent(id)}`),
  draft: (alertId) => request("POST", `/api/alerts/${encodeURIComponent(alertId)}/draft`),
  triage: (alertId) => request("POST", `/api/alerts/${encodeURIComponent(alertId)}/triage`),
  override: (alertId, reason) => request("POST", `/api/alerts/${encodeURIComponent(alertId)}/override`, { reason }),
  actions: () => request("GET", "/api/actions"),
  accounts: () => request("GET", "/api/accounts"),
  creditHold: (id, on, reason) => request("POST", `/api/accounts/${encodeURIComponent(id)}/credit-hold`, { on, reason }),
  reps: () => request("GET", "/api/reps"),
  setTarget: (id, quarter, target) => request("PUT", `/api/reps/${encodeURIComponent(id)}/target`, { quarter, target }),
  // A question starting with SELECT is sent as `sql` and runs as written (still read-only on the API side).
  ask: (question, alertId) => request("POST", "/api/ask", /^\s*select\b/i.test(question)
    ? { question, sql: question, alert_id: alertId ?? null }
    : { question, alert_id: alertId ?? null }),
};
