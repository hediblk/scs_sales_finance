import { useEffect, useMemo, useState } from "react";
import {
  Area, CartesianGrid, ComposedChart, Line, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "../data/api.js";
import { axisFmt, money, num } from "../lib/format.js";
import { ErrorBox, Loading } from "./ui.jsx";

// GET /api/forecast (docs/ui-contract.md, "Forecast"): today's policy vs the rules on, by quarter,
// actual quarters then a run-rate for 2026Q4 and 2027Q1. Every module setting change re-queries it.
const METRICS = [
  ["revenue", "Revenue", 1],
  ["gross_profit", "Gross profit", 1],
  ["refunds", "Refunds", -1],
  ["profit_after_refunds", "Profit after refunds", 1],
];
const CURRENT = "var(--text-2)";
const RULES = "var(--accent)";
const signed = (v) => `${v > 0 ? "+" : v < 0 ? "-" : ""}${money(Math.abs(v ?? 0))}`;
const good = (v, dir) => (!v || !dir ? "" : v * dir > 0 ? "delta-down" : "delta-up"); // delta-down = green

// Module settings from the simulator panels -> forecast query.
export function forecastQuery(params) {
  const out = {};
  const p = params.pricing_policy, d = params.damage_policy, c = params.credit_policy;
  if (p) Object.assign(out, { pricing: p.enabled ? 1 : 0, cap: p.cap, retention: p.retention });
  if (d) Object.assign(out, { damage: d.enabled ? 1 : 0, trigger: d.trigger, effectiveness: d.effectiveness, cost: d.cost });
  if (c) Object.assign(out, { credit: c.enabled ? 1 : 0, allowance: c.allowance, action: c.action, acceptance: c.acceptance });
  return out;
}

function Tip({ active, payload, label, metricLabel }) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  return (
    <div className="chart-tip">
      <div className="chart-tip-label">{label}{r.kind === "forecast" ? " (run-rate)" : ""}</div>
      <div className="chart-tip-row"><span className="swatch" style={{ background: CURRENT }} /><span className="chart-tip-name">Today's policy</span><span className="chart-tip-val">{money(r.current)}</span></div>
      <div className="chart-tip-row"><span className="swatch" style={{ background: RULES }} /><span className="chart-tip-name">With the rules on</span><span className="chart-tip-val">{money(r.with_rules)}</span></div>
      <div className="chart-tip-row"><span className="chart-tip-name">Gap ({metricLabel.toLowerCase()})</span><span className="chart-tip-val">{signed(r.with_rules - r.current)}</span></div>
    </div>
  );
}

export function Forecaster({ params }) {
  const [metric, setMetric] = useState("profit_after_refunds");
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const [attempt, setAttempt] = useState(0);
  const query = forecastQuery(params);
  const key = JSON.stringify(query);

  useEffect(() => {
    let live = true;
    setState((s) => ({ ...s, loading: true }));
    const t = setTimeout(() => {
      api.forecast(query)
        .then((data) => live && setState({ data, error: null, loading: false }))
        .catch((error) => live && setState((s) => ({ data: s.data, error, loading: false })));
    }, 150);
    return () => { live = false; clearTimeout(t); };
  }, [key, attempt]); // eslint-disable-line react-hooks/exhaustive-deps

  const d = state.data;
  const [, mLabel, dir] = METRICS.find(([k]) => k === metric);
  const rows = useMemo(() => {
    const s = d?.series?.[metric] ?? [];
    const lastActual = [...s].reverse().find((r) => r.kind === "actual");
    return s.map((r) => {
      const isF = r.kind === "forecast";
      const bridge = r === lastActual; // the forecast lines start from the last actual quarter
      return {
        ...r,
        curA: isF ? null : r.current, rulesA: isF ? null : r.with_rules,
        curF: isF || bridge ? r.current : null, rulesF: isF || bridge ? r.with_rules : null,
        band: [Math.min(r.current, r.with_rules), Math.max(r.current, r.with_rules)],
      };
    });
  }, [d, metric]);
  const forecastQs = rows.filter((r) => r.kind === "forecast").map((r) => r.quarter);
  const lastF = rows[rows.length - 1];

  if (!d && state.error) return <ErrorBox error={state.error} onRetry={() => setAttempt((n) => n + 1)} />;
  if (!d) return <Loading what="Projecting" />;

  const nq = d.kpis?.next_quarter;
  const nm = nq?.metrics?.[metric] ?? {};
  const rep = d.kpis?.replay_jan_sep_2026?.[metric] ?? {};
  const repPct = d.rules_effect_jan_sep_2026_pct?.[metric];
  const cr = d.kpis?.credit;

  return (
    <section className={`card fc${state.loading ? " is-loading" : ""}`} aria-label="Forecaster">
      <header className="fc-head">
        <div>
          <h2>Today's policy vs the rules on, by quarter</h2>
          <p className="muted small">Actual quarters 2025Q1 to 2026Q3 replayed with the rules; 2026Q4 and 2027Q1 projected.</p>
        </div>
        <div className="tabs" role="tablist" aria-label="Metric">
          {METRICS.map(([k, l]) => (
            <button key={k} type="button" role="tab" aria-selected={metric === k} className={metric === k ? "is-on" : ""} onClick={() => setMetric(k)}>{l}</button>
          ))}
        </div>
      </header>

      <div className="fc-kpis">
        <div className="fc-kpi"><span className="mini-label">{nq?.quarter ?? "Next quarter"}, today's policy</span><b>{money(nm.current)}</b></div>
        <div className="fc-kpi"><span className="mini-label">{nq?.quarter ?? "Next quarter"}, with the rules on</span><b className="fc-rules">{money(nm.with_rules)}</b></div>
        <div className="fc-kpi"><span className="mini-label">Change next quarter</span><b className={good(nm.delta, dir)}>{signed(nm.delta)}</b></div>
        <div className="fc-kpi"><span className="mini-label">Jan-Sep 2026 replay</span><b className={good(rep.delta, dir)}>{signed(rep.delta)}</b>{repPct != null && <span className="small muted">{repPct > 0 ? "+" : ""}{num(repPct)}%</span>}</div>
        {cr && (
          <div className="fc-kpi"><span className="mini-label">Overdue exposure, Oct 31</span>
            <b className={good(cr.overdue_exposure_delta, -1)}>{cr.enabled ? signed(cr.overdue_exposure_delta) : "rule off"}</b>
            {cr.enabled && <span className="small muted">{num(cr.restricted_accounts)} accounts restricted{cr.revenue_effect_jan_sep_2026 ? `, ${signed(cr.revenue_effect_jan_sep_2026)} revenue` : ""}</span>}
          </div>
        )}
      </div>

      <ul className="legend fc-legend">
        <li><span className="swatch" style={{ background: CURRENT }} />Today's policy</li>
        <li><span className="swatch" style={{ background: RULES }} />With the rules on</li>
        <li><span className="swatch fc-swatch-band" />Gap between the two</li>
        <li><span className="fc-dash" />Dashed: projected quarters</li>
      </ul>
      <div className="chart-box" style={{ height: 340 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 18, right: 24, bottom: 0, left: 8 }}>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            {forecastQs.length > 0 && (
              <ReferenceArea x1={forecastQs[0]} x2={forecastQs[forecastQs.length - 1]} fill="var(--surface-3)" fillOpacity={0.7}
                label={{ value: "Projection (run-rate)", position: "insideTop", fill: "var(--text-2)", fontSize: 12 }} />
            )}
            <XAxis dataKey="quarter" tick={{ fill: "var(--text-3)", fontSize: 12 }} tickLine={false} axisLine={{ stroke: "var(--border-strong)" }} padding={{ left: 10, right: 10 }} />
            <YAxis tick={{ fill: "var(--text-3)", fontSize: 12 }} tickLine={false} axisLine={false} tickFormatter={axisFmt("$")} width={70} domain={["auto", "auto"]} />
            <Tooltip content={<Tip metricLabel={mLabel} />} />
            <Area dataKey="band" stroke="none" fill={RULES} fillOpacity={0.14} isAnimationActive={false} />
            <Line dataKey="curA" stroke={CURRENT} strokeWidth={2.5} dot={{ r: 3 }} connectNulls={false} isAnimationActive={false} />
            <Line dataKey="rulesA" stroke={RULES} strokeWidth={2.5} dot={{ r: 3 }} connectNulls={false} isAnimationActive={false} />
            <Line dataKey="curF" stroke={CURRENT} strokeWidth={2.5} strokeDasharray="6 5" dot={{ r: 3 }} connectNulls={false} isAnimationActive={false} />
            <Line dataKey="rulesF" stroke={RULES} strokeWidth={2.5} strokeDasharray="6 5" dot={{ r: 3 }} connectNulls={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      {lastF && (
        <p className="fc-gap">Gap in {lastF.quarter}: <b className={good(lastF.with_rules - lastF.current, dir)}>{signed(lastF.with_rules - lastF.current)}</b> {mLabel.toLowerCase()} with the rules on.</p>
      )}
      <p className="fc-method">Run-rate projection: same quarter last year x this year's growth. Not a forecasting model.</p>
      {state.error && <ErrorBox error={state.error} onRetry={() => setAttempt((n) => n + 1)} />}
    </section>
  );
}
