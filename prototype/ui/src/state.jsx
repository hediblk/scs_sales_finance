import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./data/api.js";
import { lower, plural } from "./lib/format.js";

const Ctx = createContext(null);
export const useApp = () => useContext(Ctx);

// Small cached loader for read-only endpoints (overview, gap, insights, data-prep).
const cache = new Map();
export function useResource(key, loader, deps = []) {
  const [state, setState] = useState(() => (cache.has(key) ? { data: cache.get(key), error: null } : { data: null, error: null }));
  const [tick, setTick] = useState(0);
  const lastKey = useRef(key);
  useEffect(() => {
    const keyChanged = lastKey.current !== key;
    lastKey.current = key;
    if (cache.has(key) && tick === 0) {
      if (keyChanged) setState({ data: cache.get(key), error: null });
      return;
    }
    if (keyChanged) setState({ data: null, error: null });
    let live = true;
    loader()
      .then((data) => { cache.set(key, data); if (live) setState({ data, error: null }); })
      .catch((error) => live && setState((s) => ({ data: s.data, error })));
    return () => { live = false; };
  }, [key, tick, ...deps]); // eslint-disable-line react-hooks/exhaustive-deps
  const reload = useCallback(() => setTick((t) => t + 1), []);
  const set = useCallback((data) => { cache.set(key, data); setState({ data, error: null }); }, [key]);
  return { ...state, reload, set };
}

// "open" = detection only (C3), "auto_held" = C1 quota hold running, "notified" = C2 task open.
export const OPEN_STATUSES = new Set(["open", "auto_held", "notified"]);
export const isOpen = (a) => OPEN_STATUSES.has(a.status);

function readHash(pages) {
  const [k, qs] = window.location.hash.replace(/^#\/?/, "").split("?");
  const key = pages.some((p) => p.key === k) ? k : pages[0].key;
  return { key, params: Object.fromEntries(new URLSearchParams(qs ?? "")) };
}

export function AppProvider({ pages, children }) {
  const [meta, setMeta] = useState(null);
  const [conditions, setConditions] = useState([]);
  const [thresholds, setThresholds] = useState({}); // { [conditionId]: { value, window } }
  const [alerts, setAlerts] = useState([]);
  const [alertsLoading, setAlertsLoading] = useState(true);
  const [actions, setActions] = useState([]);
  const [entityId, setEntityId] = useState(null);
  const [error, setError] = useState(null);
  const [route, setRoute] = useState(() => readHash(pages));
  const [askContext, setAskContext] = useState(null); // alert object when "Ask about this alert"
  const [header, setHeader] = useState(null); // { page, title, lead } set by a page that changes its own heading
  const loadedAt = useRef(new Date().toISOString().slice(0, 19));

  useEffect(() => {
    const onHash = () => setRoute(readHash(pages));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [pages]);

  const go = useCallback((key, params) => {
    const qs = params ? `?${new URLSearchParams(params)}` : "";
    window.location.hash = `/${key}${qs}`;
    window.scrollTo({ top: 0 });
  }, []);

  // First load. `retry` runs it again after a failure (no placeholder data, ever).
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    setError(null);
    Promise.all([api.meta(), api.conditions(), api.actions()])
      .then(([m, c, a]) => {
        setMeta(m);
        setConditions(c);
        setThresholds((t) => (Object.keys(t).length ? t : Object.fromEntries(c.map((x) => [x.id, { value: x.threshold.value, window: x.window?.value ?? null }]))));
        setActions(a);
      })
      .catch(setError);
  }, [attempt]);
  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  // Theme: the palette switches on meta.company (see theme/tokens.css).
  useEffect(() => {
    if (!meta) return;
    document.documentElement.dataset.company = meta.company;
    document.title = meta.company_name;
  }, [meta]);

  // The queue always reflects the current thresholds. Debounced so slider drags stay smooth.
  useEffect(() => {
    if (!conditions.length) return;
    let live = true;
    setAlertsLoading(true);
    const t = setTimeout(() => {
      Promise.all(conditions.map((c) => {
        const th = thresholds[c.id] ?? {};
        return api.alerts(c.id, th.value ?? c.threshold.value, th.window ?? c.window?.value);
      }))
        .then((lists) => { if (live) { setAlerts(lists.flat()); setAlertsLoading(false); } })
        .catch((e) => { if (live) { setError(e); setAlertsLoading(false); } });
    }, 180);
    return () => { live = false; clearTimeout(t); };
  }, [conditions, thresholds, attempt]);

  const refreshActions = useCallback(() => api.actions().then(setActions).catch(() => {}), []);

  const setThreshold = useCallback((id, patch) => setThresholds((t) => ({ ...t, [id]: { ...t[id], ...patch } })), []);
  const resetThreshold = useCallback((id) => {
    const c = conditions.find((x) => x.id === id);
    if (c) setThresholds((t) => ({ ...t, [id]: { value: c.threshold.value, window: c.window?.value ?? null } }));
  }, [conditions]);

  const override = useCallback(async (alertId, reason) => {
    const updated = await api.override(alertId, reason);
    setAlerts((list) => list.map((a) => (a.id === alertId ? { ...a, ...updated } : a)));
    await refreshActions();
    return updated;
  }, [refreshActions]);

  const runAndLog = useCallback(async (fn) => {
    const out = await fn();
    refreshActions();
    return out;
  }, [refreshActions]);

  const askAbout = useCallback((alert) => {
    setAskContext(alert);
    go("ask");
  }, [go]);

  // "See these orders" from a chart: Ask opens and sends this question once.
  const pendingQuestion = useRef(null);
  const askQuestion = useCallback((question) => {
    setAskContext(null);
    pendingQuestion.current = question;
    go("ask");
  }, [go]);
  const takePendingQuestion = useCallback(() => {
    const q = pendingQuestion.current;
    pendingQuestion.current = null;
    return q;
  }, []);

  const labels = useMemo(() => {
    const entity = meta?.entity_label ?? "Customer";
    const owner = meta?.owner_label ?? "Account rep";
    return { entity, owner, entities: lower(plural(entity)), Entities: plural(entity), ownerLower: lower(owner) };
  }, [meta]);

  // notify rows grouped by alert: "Notified: Sales manager, CFO" on each card.
  const notifiedByAlert = useMemo(() => {
    const out = {};
    for (const a of actions) {
      if (a.action !== "notify" || !a.alert_id) continue;
      (out[a.alert_id] ||= []).push({ to: a.to ?? "someone", ts: a.ts });
    }
    return out;
  }, [actions]);

  const rowsByAlert = useMemo(() => {
    const out = {};
    for (const a of actions) if (a.alert_id) (out[a.alert_id] ||= []).push(a);
    // Chain order: date, then step number inside the chain (seq), then real time for human rows.
    for (const k in out) out[k].sort((x, y) => x.ts.slice(0, 10).localeCompare(y.ts.slice(0, 10)) || (x.seq ?? 99) - (y.seq ?? 99) || x.ts.localeCompare(y.ts));
    return out;
  }, [actions]);

  const value = {
    meta, labels, conditions, thresholds, setThreshold, resetThreshold,
    alerts, alertsLoading, actions, notifiedByAlert, rowsByAlert, refreshActions, override, runAndLog,
    entityId, openEntity: setEntityId, closeEntity: () => setEntityId(null),
    route, go, askContext, setAskContext, askAbout, askQuestion, takePendingQuestion, header, setHeader,
    error, retry, loadedAt: loadedAt.current,
    openCount: alerts.filter(isOpen).length,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
