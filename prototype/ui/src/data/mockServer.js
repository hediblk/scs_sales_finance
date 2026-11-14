// In-browser stand-in for the FastAPI backend. Same paths, same response shapes as
// docs/ui-contract.md. Used per endpoint when the live API does not serve it yet,
// or for everything with VITE_API_BASE=mock. State (overrides, holds, targets) lives until reload.
import metaDefault from "../mock/meta.json";
import metaMillennium from "../mock/meta.millennium.json";
import dataPrep from "../mock/data-prep.json";
import overview from "../mock/overview.json";
import gap from "../mock/gap.json";
import insights from "../mock/insights.json";
import conditionsSeed from "../mock/conditions.json";
import alertsSeed from "../mock/alerts.json";
import actionsSeed from "../mock/actions.json";
import entityTemplate from "../mock/entity.json";
import draftTemplate from "../mock/draft.json";
import triageTemplate from "../mock/triage.json";
import accountsSeed from "../mock/accounts.json";
import repsSeed from "../mock/reps.json";
import askTemplate from "../mock/ask.json";

// Dataset page fallbacks: snapshots of the live /api/{raw|clean}/* responses (first 100 rows per table).
const datasetFiles = import.meta.glob("../mock/dataset/*.json", { eager: true, import: "default" });
const ds = (name) => datasetFiles[`../mock/dataset/${name}.json`];

function datasetRoute(p, qp) {
  let m;
  if ((m = p.match(/^\/api\/(raw|clean)\/tables$/))) return ds(`${m[1]}-tables`);
  if ((m = p.match(/^\/api\/(raw|clean)\/charts$/))) return ds(`${m[1]}-charts`);
  if (p === "/api/clean/set-aside") return ds("clean-set-aside");
  if ((m = p.match(/^\/api\/(raw|clean)\/(customers|orders|returns)\/profile$/))) return ds(`${m[1]}-${m[2]}-profile`);
  if ((m = p.match(/^\/api\/(raw|clean)\/(customers|orders|returns)\/rows$/))) {
    const snap = ds(`${m[1]}-${m[2]}-rows`);
    const q = (qp.q ?? "").toLowerCase();
    const ci = snap.columns.indexOf(qp.col);
    const rows = snap.rows
      .filter((r) => !q || r.some((v) => String(v).toLowerCase().includes(q)))
      .filter((r) => ci < 0 || !qp.val || String(r[ci]) === qp.val);
    const offset = Number(qp.offset ?? 0);
    const limit = Number(qp.limit ?? 50);
    return { ...snap, total: rows.length, offset, limit, rows: rows.slice(offset, offset + limit), snapshot: true };
  }
  return null;
}

const clone = (x) => JSON.parse(JSON.stringify(x));
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const money = (v) => new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD", maximumFractionDigits: 0 }).format(v);

// Mock-only fields: alerts.json rows carry `_metric` (compared to the threshold) and `_window`.
const population = clone(alertsSeed);
const statusById = {};
const actions = clone(actionsSeed);
const accounts = clone(accountsSeed);
const reps = clone(repsSeed);

const condById = Object.fromEntries(conditionsSeed.map((c) => [c.id, c]));
const matches = (a, value, window) =>
  a._metric >= Number(value) && (a._window == null || window == null || a._window <= Number(window));
const publicAlert = (a) => {
  const { _metric, _window, ...rest } = a;
  return { ...rest, status: statusById[a.id] ?? a.status };
};
const nowIso = () => new Date().toISOString().slice(0, 19);
const median = (xs) => {
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
const hash = (s) => [...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);
const defaults = (cid) => [condById[cid]?.threshold.value, condById[cid]?.window?.value ?? null];

function meta() {
  // Preview helper: ?company=millennium loads the second mock meta. Default is Chrome & Oak.
  const want = typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("company") : null;
  return want === "millennium" ? metaMillennium : metaDefault;
}

function simulate(cid, value, window) {
  const hits = population.filter((a) => a.condition_id === cid && matches(a, value, window));
  const amount = hits.reduce((s, a) => s + a.amount, 0);
  return { hits: hits.length, amount, sentence: `${hits.length} flagged, ${money(amount)} (mock data).` };
}

function entity(id) {
  const own = population.filter((a) => a.entity_id === id);
  const first = own[0];
  const e = clone(entityTemplate);
  if (!first) return { ...e, id, name: id };
  const k = 0.5 + (hash(id) % 100) / 100;
  e.id = id;
  e.name = first.entity_name;
  e.facts[0].value = own.reduce((s, a) => s + a.amount, 0);
  e.facts.push({ label: "Region", value: first.region, unit: "" });
  e.compare = own.map((a) => {
    const c = condById[a.condition_id];
    const peers = population.filter((p) => p.condition_id === a.condition_id);
    return { label: c.threshold.label, value: a._metric, peer_value: Number(median(peers.map((p) => p._metric)).toFixed(1)), peer_group: "All flagged median", unit: c.threshold.unit };
  });
  e.timeline = e.timeline.map((t) => ({ ...t, amount: Math.round((t.amount * k) / 50) * 50 }));
  e.chart.rows = e.chart.rows.map((r) => ({ ...r, balance: Math.round((r.balance * k) / 100) * 100 }));
  return e;
}

function fill(template, a) {
  const vars = { owner: a.owner, entity_name: a.entity_name, amount: money(a.amount), reasons: a.reasons.map((r) => `- ${r}`).join("\n") };
  const out = {};
  for (const [k, v] of Object.entries(template)) out[k] = typeof v === "string" ? v.replace(/\{(\w+)\}/g, (m, key) => vars[key] ?? m) : v;
  return out;
}

export async function handle(method, path, body) {
  const url = new URL(path, "http://mock.local");
  const p = url.pathname;
  const qp = Object.fromEntries(url.searchParams);
  let m;

  if (method === "GET") {
    const dsHit = datasetRoute(p, qp);
    if (dsHit) return clone(dsHit);
    if (p === "/api/meta") return meta();
    if (p === "/api/data-prep") return clone(dataPrep);
    if (p === "/api/overview") return clone(overview);
    if (p === "/api/gap") return clone(gap);
    if (p === "/api/insights") return clone(insights);
    if (p === "/api/conditions")
      return conditionsSeed.map((c) => ({ ...clone(c), ...simulate(c.id, ...defaults(c.id)) }));
    if (p === "/api/simulate") {
      const [v, w] = defaults(qp.condition);
      return simulate(qp.condition, qp.value ?? v, qp.window ?? w);
    }
    if (p === "/api/alerts") {
      return population
        .filter((a) => !qp.condition || a.condition_id === qp.condition)
        .filter((a) => {
          const [v, w] = defaults(a.condition_id);
          return matches(a, qp.condition ? qp.value ?? v : v, qp.condition ? qp.window ?? w : w);
        })
        .map(publicAlert);
    }
    if ((m = p.match(/^\/api\/entity\/(.+)$/))) {
      await wait(100);
      return entity(decodeURIComponent(m[1]));
    }
    if (p === "/api/actions") return clone(actions).sort((a, b) => b.ts.localeCompare(a.ts));
    if (p === "/api/accounts") return clone(accounts);
    if (p === "/api/reps") return clone(reps);
  }

  if (method === "POST" && (m = p.match(/^\/api\/accounts\/([^/]+)\/credit-hold$/))) {
    const acct = accounts.find((a) => a.id === decodeURIComponent(m[1]));
    if (!acct) throw new Error(`mock: no account ${m[1]}`);
    acct.credit_hold = Boolean(body?.on);
    actions.push({ ts: nowIso(), alert_id: null, entity_id: acct.id, actor: "user", action: "credit_hold",
      detail: `${acct.credit_hold ? "Credit hold on" : "Credit hold lifted"} for ${acct.name}: ${body?.reason || "(no reason)"}` });
    return clone(acct);
  }

  if (method === "PUT" && (m = p.match(/^\/api\/reps\/([^/]+)\/target$/))) {
    const rep = reps.find((r) => r.id === decodeURIComponent(m[1]));
    const q = rep?.quarters.find((x) => x.quarter === body?.quarter);
    if (!q) throw new Error("mock: no such rep or quarter");
    q.target = body.target === "" || body.target == null ? null : Number(body.target);
    return clone(rep);
  }

  if (method === "POST" && p === "/api/ask") {
    await wait(500);
    return { ...clone(askTemplate), answer: `${askTemplate.answer}${body?.alert_id ? ` (asked about alert ${body.alert_id})` : ""}` };
  }

  if (method === "POST" && (m = p.match(/^\/api\/alerts\/([^/]+)\/(draft|triage|override)$/))) {
    const [, id, verb] = m;
    const a = population.find((x) => x.id === id);
    if (!a) throw new Error(`mock: no alert ${id}`);
    if (verb === "draft") {
      await wait(400);
      actions.push({ ts: nowIso(), alert_id: id, actor: "system", action: "draft", detail: `Email drafted to ${a.owner}`, to: a.owner });
      return fill(draftTemplate, a);
    }
    if (verb === "triage") {
      await wait(500);
      const rec = a.severity === "high" ? "escalate" : a.severity === "medium" ? "hold" : "release";
      actions.push({ ts: nowIso(), alert_id: id, actor: "system", action: "triage", detail: `Triage note (mock): ${rec}` });
      return { ...fill(triageTemplate, a), review_needed: a.severity !== "low", recommendation: rec, source: "mock" };
    }
    if (verb === "override") {
      await wait(150);
      statusById[id] = "overridden";
      actions.push({ ts: nowIso(), alert_id: id, actor: "user", action: "override", detail: body?.reason || "(no reason given)" });
      if (a.condition_id === "qe_discount")
        actions.push({ ts: nowIso(), alert_id: id, actor: "user", action: "release", detail: `Quota credit of ${money(a.amount)} released by a manager` });
      return { ...publicAlert(a), override_reason: body?.reason };
    }
  }

  throw new Error(`mock: no route for ${method} ${path}`);
}
