import { useEffect, useRef, useState } from "react";
import { api } from "../data/api.js";
import { useApp } from "../state.jsx";
import { ChartRenderer, Legend } from "../components/Chart.jsx";


const cellFmt = new Intl.NumberFormat("en-CA", { maximumFractionDigits: 3 });
const cell = (v) => (typeof v !== "number" ? String(v ?? "") : Math.abs(v) >= 100 ? Math.round(v).toLocaleString("en-CA") : cellFmt.format(v));
const pretty = (s = "") => String(s).replace(/_/g, " ");

// The visual the back end picked from the result's shape (docs/ui-contract.md, POST /api/ask).
function Visual({ chart, rows }) {
  if (!chart) return null;
  if (chart.type === "kpi") {
    return <div className="tiles ask-kpis"><div className="tile"><div className="tile-label">{pretty(chart.label)}</div><div className="tile-value">{cell(chart.value)}</div></div></div>;
  }
  if (chart.type === "kpis") {
    return (
      <div className="tiles ask-kpis">
        {(chart.items ?? []).map((k) => <div key={k.label} className="tile"><div className="tile-label">{pretty(k.label)}</div><div className="tile-value">{cell(k.value)}</div></div>)}
      </div>
    );
  }
  if (!rows.length) return null;
  let series = chart.series ?? [];
  if (chart.type === "scatter" && !series.length && chart.y) series = [{ key: chart.y, label: chart.y }];
  // Series on very different scales would flatten each other on one axis: keep the first, the table has the rest.
  const span = (k) => Math.max(...rows.map((r) => Math.abs(Number(r[k]) || 0)));
  const s0 = series[0] ? span(series[0].key) : 0;
  const sameScale = series.filter((s) => { const v = span(s.key); return s0 && v / s0 < 10 && s0 / (v || 1) < 10; });
  const plotted = sameScale.length ? sameScale : series.slice(0, 1);
  return (
    <div className="ask-chart">
      {plotted.length === 1 && <div className="mini-label">{pretty(plotted[0].label)}</div>}
      <Legend series={plotted.map((s) => ({ ...s, label: pretty(s.label) }))} />
      <ChartRenderer chart={{ ...chart, series: plotted.map((s) => ({ ...s, label: pretty(s.label) })), rows }} height={230} />
      {(chart.note || plotted.length < series.length) && (
        <p className="ask-note">{[chart.note, plotted.length < series.length ? "Other columns are in the table below." : null].filter(Boolean).join(" ")}</p>
      )}
    </div>
  );
}

const SUGGESTIONS = [
  "Revenue by region, Jan-Sep 2026 vs Jan-Sep 2025",
  "Which reps give the deepest discounts in the last 14 days of a quarter?",
  "Return rate by product category",
  "Top 10 resellers by refunds",
];
const ALERT_SUGGESTIONS = [
  "Why did this alert trigger?",
  "Show this customer's orders and returns",
  "How does this rep's discount compare with the team?",
];

let savedTurns = []; // survives page switches within the session

function Answer({ t }) {
  if (t.error) return <div className="error-box" style={{ margin: 0 }}>{t.error}</div>;
  const r = t.res;
  const rows = (r.rows ?? []).map((row) => Object.fromEntries((r.columns ?? []).map((c, i) => [c, row[i]])));
  return (
    <>
      <Visual chart={r.chart} rows={rows} />
      {r.answer && <div className="answer" style={{ marginTop: r.chart ? 12 : 0 }}>{r.answer}</div>}
      {r.error && (
        <div className={r.out_of_scope ? "ask-notice" : "error-box"} style={{ marginTop: r.answer ? 10 : 0 }}>{r.error}</div>
      )}
      {r.sql && (
        <details className="sql">
          <summary>Show the query that ran (read-only)</summary>
          <pre>{r.sql}</pre>
        </details>
      )}
      {rows.length > 0 && (
        <div className="ask-table">
          <table className="table compact">
            <thead><tr>{r.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
            <tbody>
              {r.rows.slice(0, 50).map((row, i) => (
                <tr key={i}>{row.map((v, j) => <td key={j} className={typeof v === "number" ? "num" : ""}>{cell(v)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

export default function AskPage() {
  const { askContext, setAskContext } = useApp();
  const [turns, setTurns] = useState(savedTurns);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef(null);

  useEffect(() => { savedTurns = turns; endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [turns, busy]);

  // A question handed over by a chart's "See these orders" link.
  const { takePendingQuestion } = useApp();
  useEffect(() => {
    const q = takePendingQuestion();
    if (q) send(q);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const send = async (text) => {
    const q = (text ?? input).trim();
    if (!q || busy) return;
    setInput("");
    const ctx = askContext;
    setTurns((t) => [...t, { role: "user", content: q, alert: ctx ? { id: ctx.id, name: ctx.entity_name } : null }]);
    setBusy(true);
    try {
      const res = await api.ask(q, ctx?.id);
      setTurns((t) => [...t, { role: "assistant", res }]);
    } catch (e) {
      setTurns((t) => [...t, { role: "assistant", error: e.message }]);
    } finally {
      setBusy(false);
    }
  };

  const chips = askContext ? ALERT_SUGGESTIONS : SUGGESTIONS;

  return (
    <div className="ask-wrap">
      <div className="ask-thread">
        {turns.length === 0 && !busy ? (
          <div className="ask-empty">
            <h3>{askContext ? `Ask about ${askContext.entity_name}` : "Ask a question about the clean data"}</h3>
            <p>
              The AI turns your question into one SELECT. A read-only connection runs it with a row limit, and you see the
              query, the rows and a chart. It cannot create, clear or change alerts.
            </p>
            <div className="chips">{chips.map((s) => <button key={s} type="button" className="chip-btn" onClick={() => send(s)}>{s}</button>)}</div>
          </div>
        ) : turns.map((t, i) => (
          <div key={i} className={`msg ${t.role}`}>
            <div className="bubble">
              {t.role === "user" ? (
                <>
                  {t.alert && <div className="context-chip">About alert {t.alert.id}, {t.alert.name}</div>}
                  {t.content}
                </>
              ) : <Answer t={t} />}
            </div>
          </div>
        ))}
        {busy && <div className="msg assistant"><div className="bubble"><div className="loading" style={{ padding: 0 }}><span className="spinner" />Writing and running the query...</div></div></div>}
        <div ref={endRef} />
      </div>

      <div className="ask-input">
        {askContext && (
          <div className="row" style={{ alignItems: "center" }}>
            <span className="chip chip-accent">Context: alert {askContext.id}, {askContext.entity_name}</span>
            <button type="button" className="link-btn small" onClick={() => setAskContext(null)}>Clear</button>
            <span className="spacer" />
            {turns.length > 0 && <span className="chips">{ALERT_SUGGESTIONS.slice(0, 2).map((s) => <button key={s} type="button" className="chip-btn" onClick={() => send(s)}>{s}</button>)}</span>}
          </div>
        )}
        <div className="row">
          <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()}
            placeholder="Ask about revenue, discounts, returns, reps, regions..." disabled={busy} aria-label="Question" />
          <button type="button" className="btn" onClick={() => send()} disabled={busy || !input.trim()}>Ask</button>
          {turns.length > 0 && <button type="button" className="btn btn-quiet" onClick={() => setTurns([])}>Clear</button>}
        </div>
        <span className="readonly-note">Read-only. Numbers come from the query result, never from the model. A question that starts with SELECT runs as written.</span>
      </div>
    </div>
  );
}
