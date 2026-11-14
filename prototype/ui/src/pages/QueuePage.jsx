import { useEffect, useMemo, useState } from "react";
import { isOpen, useApp } from "../state.jsx";
import { dateLabel, money, num } from "../lib/format.js";
import { ConditionControl } from "../components/ThresholdSlider.jsx";
import { FindingDetail, impactLabel } from "../components/FindingDetail.jsx";
import { Empty, Loading } from "../components/ui.jsx";
import { TaskList } from "../components/TaskList.jsx";

const SEV = { high: 3, medium: 2, low: 1 };
const SEV_TONE = { high: "bad", medium: "warn", low: "neutral" };
const STATUS_FILTERS = [["open", "Open"], ["closed", "Closed or overridden"], ["all", "All"]];
const PAGE = 60;
const MAIN = "qe_discount"; // C1 sits in the header; the others fold under "Other rules"

const uniq = (xs) => [...new Set(xs.filter(Boolean))].sort();

function AlertQueue({ params }) {
  const { alerts, alertsLoading, conditions, labels } = useApp();
  const [cond, setCond] = useState(params?.condition ?? MAIN);
  const [status, setStatus] = useState("open");
  const [rep, setRep] = useState(params?.rep ?? "");
  const [region, setRegion] = useState(params?.region ?? "");
  const [segment, setSegment] = useState(params?.segment ?? "");
  const [shown, setShown] = useState(PAGE);
  const [find, setFind] = useState("");
  const [focusId, setFocusId] = useState(null);

  useEffect(() => {
    if (params?.condition) setCond(params.condition);
    setRep(params?.rep ?? ""); setRegion(params?.region ?? ""); setSegment(params?.segment ?? "");
  }, [params?.condition, params?.rep, params?.region, params?.segment]);

  const condById = useMemo(() => Object.fromEntries(conditions.map((c) => [c.id, c])), [conditions]);
  const main = condById[MAIN] ?? conditions[0];
  const others = conditions.filter((c) => c.id !== main?.id);

  const base = useMemo(() => alerts
    .filter((a) => !rep || a.owner === rep)
    .filter((a) => !region || a.region === region)
    .filter((a) => !segment || a.segment === segment), [alerts, rep, region, segment]);

  // A search looks across every rule and status (the demo opens alerts by order or return id).
  const needle = find.trim().toLowerCase();
  const list = useMemo(() => base
    .filter((a) => needle || cond === "all" || a.condition_id === cond)
    .filter((a) => needle || status === "all" || (status === "open" ? isOpen(a) : !isOpen(a)))
    .filter((a) => !needle || [a.id, a.order_id, a.return_id, a.entity_id, a.entity_name].some((v) => v && String(v).toLowerCase().includes(needle)))
    .sort((a, b) => (SEV[b.severity] ?? 0) - (SEV[a.severity] ?? 0) || b.created_at.localeCompare(a.created_at) || b.amount - a.amount),
  [base, cond, status, needle]);

  const focused = list.find((a) => a.id === focusId) ?? list[0] ?? null;
  const openAll = base.filter(isOpen);
  const heldQe = openAll.filter((a) => a.condition_id === MAIN);
  const countFor = (id) => base.filter((a) => (id === "all" || a.condition_id === id) && (status === "all" || (status === "open" ? isOpen(a) : !isOpen(a)))).length;
  const overridden = alerts.filter((a) => a.status === "overridden");

  return (
    <>
      <section className="card queue-top">
        <div>
          <span className="mini-label">Quota credit on hold now</span>
          <div className="counter">{money(heldQe.reduce((s, a) => s + a.amount, 0))}</div>
          <div className="counter-sub">
            <b>{num(openAll.length)}</b> open alerts on {num(new Set(openAll.map((a) => a.entity_id)).size)} {labels.entities}.
            {others.map((c) => {
              const n = openAll.filter((a) => a.condition_id === c.id).length;
              return n ? <span key={c.id}> {n} {c.name.toLowerCase()}.</span> : null;
            })}
          </div>
        </div>
        <div>
          {main && <ConditionControl condition={main} />}
          {others.length > 0 && (
            <details className="other-rules">
              <summary>Other rules ({others.map((c) => c.name).join(", ")})</summary>
              <div className="sliders">{others.map((c) => <ConditionControl key={c.id} condition={c} compact />)}</div>
            </details>
          )}
        </div>
      </section>

      <div className="filters">
        <div className="tabs" role="tablist" aria-label="Condition">
          <button type="button" role="tab" aria-selected={cond === "all"} className={cond === "all" ? "is-on" : ""} onClick={() => setCond("all")}>
            All<span className="count">{countFor("all")}</span>
          </button>
          {conditions.map((c) => (
            <button key={c.id} type="button" role="tab" aria-selected={cond === c.id} className={cond === c.id ? "is-on" : ""} onClick={() => setCond(c.id)}>
              {c.name}<span className="count">{countFor(c.id)}</span>
            </button>
          ))}
        </div>
        <label className="select"><span className="sr-only">Status</span>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUS_FILTERS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </label>
        <label className="select"><span className="sr-only">{labels.owner}</span>
          <select value={rep} onChange={(e) => setRep(e.target.value)}>
            <option value="">Every {labels.ownerLower}</option>
            {uniq(alerts.map((a) => a.owner)).map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </label>
        <label className="select"><span className="sr-only">Region</span>
          <select value={region} onChange={(e) => setRegion(e.target.value)}>
            <option value="">Every region</option>
            {uniq(alerts.map((a) => a.region)).map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </label>
        <label className="select"><span className="sr-only">Segment</span>
          <select value={segment} onChange={(e) => setSegment(e.target.value)}>
            <option value="">Every segment</option>
            {uniq(alerts.map((a) => a.segment)).map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </label>
        <input className="search" type="search" placeholder="Find an order, return or customer id" value={find}
          onChange={(e) => { setFind(e.target.value); setShown(PAGE); }} aria-label="Find an alert" style={{ minWidth: 230 }} />
        {alertsLoading && <span className="muted small">Recounting...</span>}
      </div>

      {!alerts.length && alertsLoading ? <Loading what="Loading the queue" /> : (
        <div className="triage">
          <div className="rail" aria-label="Alerts">
            {list.length === 0 && <Empty>No alerts match these filters at the current thresholds.</Empty>}
            {list.slice(0, shown).map((a) => (
              <button key={a.id} type="button" className={`rail-row${focused?.id === a.id ? " is-on" : ""}`} onClick={() => setFocusId(a.id)}>
                <div className="rail-top">
                  <span className={`chip chip-${SEV_TONE[a.severity]}`}>{a.severity}</span>
                  <span className="muted small">{condById[a.condition_id]?.name ?? a.condition_id}</span>
                  <span className="rail-date">{dateLabel(a.created_at)}</span>
                </div>
                <div className="rail-title">{a.entity_name}{a.product ? ` · ${a.product}` : ""}</div>
                <div className="rail-sub"><span>{a.owner}{a.region ? ` · ${a.region}` : ""}</span><b title={impactLabel(a)}>{money(a.amount)}</b></div>
              </button>
            ))}
            {list.length > shown && (
              <button type="button" className="btn btn-quiet btn-sm rail-more" onClick={() => setShown((n) => n + PAGE)}>
                Show {Math.min(PAGE, list.length - shown)} more of {list.length - shown}
              </button>
            )}
            {overridden.length > 0 && (
              <div className="donelist">
                <div className="donelist-head">Overridden this session · {overridden.length}</div>
                {overridden.map((a) => (
                  <div key={a.id} className="done-row">
                    <button type="button" className="title-link" onClick={() => { setStatus("all"); setFocusId(a.id); }}>{a.entity_name}</button>
                    <span>{money(a.amount)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div>
            {focused ? <FindingDetail alert={focused} condition={condById[focused.condition_id]} /> : <div className="card muted">Pick an alert on the left.</div>}
          </div>
        </div>
      )}
    </>
  );
}

// Two views: alerts our rules raised on the data, and tasks created by "Apply rules to simulation".
export default function QueuePage({ params }) {
  const [view, setView] = useState(params?.view === "tasks" ? "tasks" : "alerts");
  useEffect(() => { if (params?.view) setView(params.view === "tasks" ? "tasks" : "alerts"); }, [params?.view]);
  return (
    <>
      <div className="view-switch tabs big" role="tablist" aria-label="Queue view">
        <button type="button" role="tab" aria-selected={view === "alerts"} className={view === "alerts" ? "is-on" : ""} onClick={() => setView("alerts")}>Rule alerts</button>
        <button type="button" role="tab" aria-selected={view === "tasks"} className={view === "tasks" ? "is-on" : ""} onClick={() => setView("tasks")}>Simulator tasks</button>
      </div>
      {view === "tasks" ? <TaskList /> : <AlertQueue params={params} />}
    </>
  );
}
