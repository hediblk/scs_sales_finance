import { useMemo, useState } from "react";
import { useApp } from "../state.jsx";
import { humanize, num, tsLabel } from "../lib/format.js";
import { Empty } from "../components/ui.jsx";

const TABS = [["all", "All"], ["system", "System"], ["user", "User"], ["outbox", "Outbox"]];
const STEP = 150;

function Subject({ row, byId }) {
  const { openEntity } = useApp();
  const a = row.alert_id ? byId[row.alert_id] : null;
  const id = a?.entity_id ?? row.entity_id;
  if (!id) return row.alert_id ? <span className="muted small">{row.alert_id}</span> : null;
  return <button type="button" className="title-link small" onClick={() => openEntity(id)}>{a?.entity_name ?? id}</button>;
}

export default function LogPage() {
  const { actions, alerts, loadedAt } = useApp();
  const [tab, setTab] = useState("all");
  const [query, setQuery] = useState("");
  const [to, setTo] = useState("");
  const [limit, setLimit] = useState(STEP);
  const byId = useMemo(() => Object.fromEntries(alerts.map((a) => [a.id, a])), [alerts]);

  const counts = useMemo(() => ({
    all: actions.length,
    system: actions.filter((a) => a.actor === "system").length,
    user: actions.filter((a) => a.actor === "user").length,
    outbox: actions.filter((a) => a.action === "notify").length,
  }), [actions]);

  const recipients = useMemo(() => {
    const m = {};
    for (const a of actions) if (a.action === "notify") m[a.to ?? "?"] = (m[a.to ?? "?"] ?? 0) + 1;
    return Object.entries(m).sort((x, y) => y[1] - x[1]);
  }, [actions]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return [...actions]
      .sort((a, b) => b.ts.localeCompare(a.ts))
      .filter((r) => (tab === "all" ? true : tab === "outbox" ? r.action === "notify" && (!to || r.to === to) : r.actor === tab))
      .filter((r) => !q || [r.action, r.detail, r.to, r.alert_id, byId[r.alert_id]?.entity_name].some((v) => v && String(v).toLowerCase().includes(q)));
  }, [actions, tab, to, query, byId]);

  return (
    <>
      <div className="log-toolbar">
        <div className="tabs" role="tablist" aria-label="Filter the log">
          {TABS.map(([k, l]) => (
            <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? "is-on" : ""} onClick={() => { setTab(k); setLimit(STEP); }}>
              {l}<span className="count">{num(counts[k])}</span>
            </button>
          ))}
        </div>
        <input className="search" type="search" placeholder="Search action, customer, recipient..." value={query}
          onChange={(e) => { setQuery(e.target.value); setLimit(STEP); }} aria-label="Search the log" style={{ minWidth: 260 }} />
      </div>

      {tab === "outbox" && (
        <div className="outbox-who">
          <button type="button" className={`chip-btn${!to ? " is-on" : ""}`} onClick={() => setTo("")}>Everyone</button>
          {recipients.map(([who, n]) => (
            <button key={who} type="button" className={`chip-btn${to === who ? " is-on" : ""}`} onClick={() => setTo(who)}>{who} · {n}</button>
          ))}
        </div>
      )}

      {rows.length === 0 ? <Empty>No rows match.</Empty> : (
        <div className="hist-list">
          {rows.slice(0, limit).map((r, i) => (
            <div key={`${r.ts}-${r.alert_id}-${r.action}-${i}`} className={`hist-row actor-${r.actor}${r.ts > loadedAt ? " is-new" : ""}`}>
              <span className="hist-dot" aria-hidden="true" />
              <span className="hist-actor">{tab === "outbox" ? `To ${r.to}` : r.actor === "user" ? "User" : "System"}</span>
              <div>
                <div className="hist-title">
                  <b>{humanize(r.action)}</b>
                  {r.to && tab !== "outbox" && <span className="hist-to">to {r.to}</span>}
                  <Subject row={r} byId={byId} />
                </div>
                {r.detail && <div className="hist-detail">{r.detail}</div>}
              </div>
              <time className="hist-time">{tsLabel(r.ts, r.ts_precision)}</time>
            </div>
          ))}
          {rows.length > limit && (
            <div className="more">
              <button type="button" className="btn btn-quiet btn-sm" onClick={() => setLimit((n) => n + STEP)}>
                Show {Math.min(STEP, rows.length - limit)} more of {num(rows.length - limit)}
              </button>
            </div>
          )}
        </div>
      )}
    </>
  );
}
