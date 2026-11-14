import { useEffect, useMemo, useState } from "react";
import { api } from "../data/api.js";
import { humanize, tsLabel } from "../lib/format.js";
import { Chip, Empty, ErrorBox, Loading } from "./ui.jsx";

const MODULE_LABEL = { pricing_policy: "Pricing", damage_policy: "Damage", credit_policy: "Credit" };

function TaskCard({ t }) {
  const [open, setOpen] = useState(false);
  return (
    <article className="card task">
      <header className="task-head">
        <div>
          <div className="finding-eyebrow">{MODULE_LABEL[t.module] ?? t.module} · {humanize(t.entity_type)} {t.entity_id}</div>
          <h3>{t.title}</h3>
        </div>
        <div className="task-chips">
          <Chip tone="accent">{t.owner_role}</Chip>
          <Chip tone={t.status === "open" ? "warn" : "neutral"}>{humanize(t.status)}</Chip>
        </div>
      </header>
      {t.explanation && <p className="task-text">{t.explanation}</p>}
      {t.proposed_mitigation && <p className="task-text"><span className="mini-label">Proposed mitigation</span>{t.proposed_mitigation}</p>}
      <div className="task-meta">
        {t.parameters && <span>Settings: {Object.entries(t.parameters).map(([k, v]) => `${humanize(k)} ${v}`).join(", ")}</span>}
        {t.source_records?.length > 0 && <span>{t.source_records.length} source records</span>}
        <span>Created {tsLabel(t.created_at)}</span>
        <button type="button" className="link-btn small" onClick={() => setOpen((x) => !x)} aria-expanded={open}>{open ? "Hide details" : "Details"}</button>
      </div>
      {open && (
        <div className="task-more">
          {t.source_records?.length > 0 && <p className="mono small">{t.source_records.join(", ")}</p>}
          <ol className="task-events">
            {(t.events ?? []).map((e, i) => <li key={i}><time>{tsLabel(e.ts, e.ts_precision)}</time> <b>{humanize(e.action)}</b> {e.detail}</li>)}
          </ol>
        </div>
      )}
    </article>
  );
}

// Tasks created by "Apply rules to simulation" on the What if page (GET /api/tasks).
export function TaskList() {
  const [state, setState] = useState({ data: null, error: null });
  const [attempt, setAttempt] = useState(0);
  const [mod, setMod] = useState("all");
  const [limit, setLimit] = useState(50);
  useEffect(() => {
    let live = true;
    api.tasks().then((data) => live && setState({ data, error: null })).catch((error) => live && setState({ data: null, error }));
    return () => { live = false; };
  }, [attempt]);
  const rows = useMemo(() => (state.data ?? []).filter((t) => mod === "all" || t.module === mod), [state.data, mod]);
  if (state.error) return <ErrorBox error={state.error} onRetry={() => setAttempt((n) => n + 1)} />;
  if (!state.data) return <Loading what="Loading simulator tasks" />;
  const counts = (state.data ?? []).reduce((m, t) => ((m[t.module] = (m[t.module] ?? 0) + 1), m), {});
  return (
    <section aria-label="Simulator tasks">
      <div className="filters">
        <div className="tabs" role="tablist" aria-label="Module">
          {[["all", "All"], ...Object.entries(MODULE_LABEL)].map(([k, l]) => (
            <button key={k} type="button" role="tab" aria-selected={mod === k} className={mod === k ? "is-on" : ""} onClick={() => { setMod(k); setLimit(50); }}>
              {l}<span className="count">{k === "all" ? state.data.length : counts[k] ?? 0}</span>
            </button>
          ))}
        </div>
        <button type="button" className="btn btn-quiet btn-sm" onClick={() => setAttempt((n) => n + 1)}>Refresh</button>
      </div>
      {rows.length ? <div className="task-list">{rows.slice(0, limit).map((t) => <TaskCard key={t.id} t={t} />)}</div>
        : <Empty>No tasks yet. Turn rules on in What if and press "Apply rules to simulation".</Empty>}
      {rows.length > limit && (
        <div className="more"><button type="button" className="btn btn-quiet btn-sm" onClick={() => setLimit((n) => n + 50)}>Show 50 more of {rows.length - limit}</button></div>
      )}
    </section>
  );
}
