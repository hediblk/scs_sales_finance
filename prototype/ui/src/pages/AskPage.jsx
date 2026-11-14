import { useEffect, useRef, useState } from "react";
import { api } from "../data/api.js";
import { useApp } from "../state.jsx";
import { ChartRenderer } from "../components/Chart.jsx";

const cellFmt = new Intl.NumberFormat("en-CA", { maximumFractionDigits: 3 });
const cell = (v) => (Math.abs(v) >= 100 ? Math.round(v).toLocaleString("en-CA") : cellFmt.format(v));
import { MockNote } from "../components/Shell.jsx";

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
      {r.answer && <div className="answer">{r.answer}</div>}
      {r.error && <div className="error-box" style={{ marginTop: r.answer ? 10 : 0 }}>{r.error}</div>}
      {r.sql && (
        <details className="sql" open>
          <summary>The query that ran (read-only)</summary>
          <pre>{r.sql}</pre>
        </details>
      )}
      {r.chart && rows.length > 1 && r.chart.series?.length > 0 && (
        // One measure per chart: mixed scales on one axis mislead. The table has every column.
        <div className="ask-chart">
          <div className="mini-label">{r.chart.series[0].label}</div>
          <ChartRenderer chart={{ ...r.chart, series: [r.chart.series[0]], rows }} height={220} />
        </div>
      )}
      {rows.length > 0 && (
        <div className="ask-table">
          <table className="table compact">
            <thead><tr>{r.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
            <tbody>
              {r.rows.slice(0, 50).map((row, i) => (
                <tr key={i}>{row.map((v, j) => <td key={j} className={typeof v === "number" ? "num" : ""}>{typeof v === "number" ? cell(v) : String(v ?? "")}</td>)}</tr>
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
              query, the rows and a chart. It cannot create, clear or change alerts. <MockNote route="/api/ask" />
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
