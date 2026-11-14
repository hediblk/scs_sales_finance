import { useEffect, useState } from "react";
import { api } from "../data/api.js";
import { useApp } from "../state.jsx";
import { dateLabel, fmt, money, plainRules } from "../lib/format.js";
import { ChartRenderer, Legend } from "./Chart.jsx";
import { ErrorBox, Loading, SeverityChip, StatusChip } from "./ui.jsx";

function CompareRow({ c }) {
  const max = Math.max(Number(c.value) || 0, Number(c.peer_value) || 0) || 1;
  const ratio = c.peer_value ? c.value / c.peer_value : null;
  return (
    <div className="compare">
      <div className="compare-head">
        <span>{c.label}</span>
        {ratio != null && <b>{ratio >= 1 ? `${ratio.toFixed(1)}x the ${c.peer_group.toLowerCase()}` : `below the ${c.peer_group.toLowerCase()}`}</b>}
      </div>
      <div className="compare-bars">
        <div className="cbar"><span className="cbar-label">This one</span><span className="cbar-track"><i className="is-self" style={{ width: `${(c.value / max) * 100}%` }} /></span><span className="cbar-val">{fmt(c.value, c.unit)}</span></div>
        <div className="cbar"><span className="cbar-label">{c.peer_group}</span><span className="cbar-track"><i style={{ width: `${(c.peer_value / max) * 100}%` }} /></span><span className="cbar-val">{fmt(c.peer_value, c.unit)}</span></div>
      </div>
    </div>
  );
}

// Drill-down panel for one customer or rep. Opens from an alert, an account card, a rep row or a log row.
export function EntityDrawer() {
  const { entityId, closeEntity, labels, alerts, conditions } = useApp();
  const [state, setState] = useState({ data: null, error: null });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!entityId) return;
    let live = true;
    setState({ data: null, error: null });
    api.entity(entityId).then((data) => live && setState({ data, error: null })).catch((error) => live && setState({ data: null, error }));
    return () => { live = false; };
  }, [entityId, attempt]);

  useEffect(() => {
    if (!entityId) return;
    const onKey = (e) => e.key === "Escape" && closeEntity();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [entityId, closeEntity]);

  if (!entityId) return null;
  const d = state.data;
  const own = alerts.filter((a) => a.entity_id === entityId);
  const condName = (id) => conditions.find((c) => c.id === id)?.name ?? id;

  return (
    <div className="drawer-root">
      <button type="button" className="drawer-backdrop" aria-label="Close panel" onClick={closeEntity} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title">
        <header className="drawer-head">
          <div>
            <div className="eyebrow">{d?.kind === "rep" || /^R\d/.test(entityId) ? labels.owner : labels.entity} {entityId}</div>
            <h2 id="drawer-title">{d?.name ?? "Loading..."}</h2>
          </div>
          <button type="button" className="btn btn-quiet btn-sm" onClick={closeEntity}>Close</button>
        </header>

        {state.error && <ErrorBox error={state.error} onRetry={() => setAttempt((n) => n + 1)} />}
        {!d && !state.error && <Loading />}
        {d && (
          <div className="drawer-body">
            <div className="facts">
              {d.facts.map((f) => (
                <div key={f.label} className="fact">
                  <div className="fact-label">{plainRules(f.label)}</div>
                  <div className="fact-value">{fmt(f.value, f.unit)}</div>
                </div>
              ))}
            </div>

            {d.compare?.length > 0 && (
              <section className="drawer-section">
                <h3>Compared with peers</h3>
                {d.compare.map((c, i) => <CompareRow key={i} c={c} />)}
              </section>
            )}

            {own.length > 0 && (
              <section className="drawer-section">
                <h3>Open in the queue</h3>
                <ul className="drawer-alerts">
                  {own.map((a) => (
                    <li key={a.id}>
                      <div><b>{condName(a.condition_id)}</b> <span className="muted">{a.id}</span></div>
                      <div className="drawer-alert-meta"><SeverityChip severity={a.severity} /><StatusChip status={a.status} /><span className="num">{money(a.amount)}</span></div>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {d.chart && (
              <section className="drawer-section">
                <h3>{d.chart.series?.map((s) => s.label).join(", ")}</h3>
                <Legend series={d.chart.series} />
                <ChartRenderer chart={d.chart} height={180} />
              </section>
            )}

            {d.timeline?.length > 0 && (
              <section className="drawer-section">
                <h3>History</h3>
                <ol className="timeline">
                  {[...d.timeline].sort((a, b) => b.date.localeCompare(a.date)).map((t, i) => (
                    <li key={i} className={`tl tl-${t.kind}`}>
                      <time>{dateLabel(t.date)}</time>
                      <span className="tl-kind">{t.kind}</span>
                      <span className="tl-note">{t.note}</span>
                      <span className="tl-amt num">{t.amount ? money(t.amount) : ""}</span>
                    </li>
                  ))}
                </ol>
              </section>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}
