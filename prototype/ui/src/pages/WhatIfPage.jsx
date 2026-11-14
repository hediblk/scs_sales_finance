import { useEffect, useState } from "react";
import {
  Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "../data/api.js";
import { useApp } from "../state.jsx";
import { axisFmt, money, num, plainRules } from "../lib/format.js";
import { BridgeChart } from "../components/Chart.jsx";
import { ErrorBox, Loading, SectionHead } from "../components/ui.jsx";
import { PolicySimulator } from "../components/PolicySimulator.jsx";

const TH = { min: 15, max: 35, step: 1, def: 25 };
const WIN = { min: 7, max: 30, step: 1, def: 14 };
const METRICS = [
  ["revenue", "Revenue"],
  ["gross_profit", "Gross profit"],
  ["refunds", "Refunds"],
  ["profit_after_refunds", "Profit after refunds"],
];
const signed = (v) => `${v > 0 ? "+" : v < 0 ? "-" : ""}${money(Math.abs(v))}`;
const pctSigned = (v) => `${v > 0 ? "+" : ""}${num(v)}%`;
// Refunds going down is good; everything else going up is good.
const deltaTone = (key, v) => (Math.abs(v) < 1 ? "" : (key === "refunds" ? v < 0 : v > 0) ? "delta-down" : "delta-up");

function useWhatif(threshold, window) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    setState((s) => ({ ...s, loading: true }));
    const t = setTimeout(() => {
      api.whatif(threshold, window)
        .then((data) => live && setState({ data, error: null, loading: false }))
        .catch((error) => live && setState((s) => ({ data: s.data, error, loading: false })));
    }, 150);
    return () => { live = false; clearTimeout(t); };
  }, [threshold, window, attempt]);
  return { ...state, retry: () => setAttempt((n) => n + 1) };
}

function Slider({ id, label, spec, value, onChange, unit }) {
  return (
    <div className="slider-row">
      <label htmlFor={id}>{label}</label>
      <output htmlFor={id}>{value}{unit}</output>
      <input id={id} type="range" min={spec.min} max={spec.max} step={spec.step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </div>
  );
}

function ResultTable({ d }) {
  const sc = Object.fromEntries(d.scenarios.map((s) => [s.id, s]));
  const keep = sc.keep_at_cap;
  const lose = sc.lose_order;
  return (
    <div className="card table-card">
      <div className="table-wrap">
        <table className="table wi-table">
          <thead>
            <tr>
              <th>{d.period}</th>
              <th className="num">Actual</th>
              <th className="num">{keep?.label ?? "Keeps the order at the cap"}</th>
              <th className="num">{lose?.label ?? "Walks away"}</th>
              <th className="num">With the rule</th>
            </tr>
          </thead>
          <tbody>
            {METRICS.map(([k, label]) => {
              const lo = Math.min(keep[k], lose[k]);
              const hi = Math.max(keep[k], lose[k]);
              return (
                <tr key={k} className={k === "profit_after_refunds" ? "is-key" : ""}>
                  <td><b>{label}</b></td>
                  <td className="num">{money(d.actual[k])}</td>
                  <td className="num">{money(keep[k])}<div className={`small ${deltaTone(k, keep.delta[k])}`}>{signed(keep.delta[k])}</div></td>
                  <td className="num">{money(lose[k])}<div className={`small ${deltaTone(k, lose.delta[k])}`}>{signed(lose.delta[k])}</div></td>
                  <td className="num wi-range">between {money(lo, { compact: true })} and {money(hi, { compact: true })}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Projection({ p }) {
  const qs = p.quarters ?? [];
  const last = qs[qs.length - 1];
  const lo = Math.min(p.q4.keep_at_cap, p.q4.lose_order);
  const hi = Math.max(p.q4.keep_at_cap, p.q4.lose_order);
  const rows = [
    ...qs.map((q) => ({ quarter: q.quarter, actual: q.revenue })),
  ];
  if (last) {
    rows[rows.length - 1] = { ...rows[rows.length - 1], baseline: last.revenue, band: [last.revenue, last.revenue] };
    rows.push({ quarter: p.quarter, baseline: p.q4.baseline, band: [lo, hi] });
  }
  const Tip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    const r = payload[0].payload;
    return (
      <div className="chart-tip">
        <div className="chart-tip-label">{label}</div>
        {r.actual != null && <div className="chart-tip-row"><span className="chart-tip-name">Actual</span><span className="chart-tip-val">{money(r.actual)}</span></div>}
        {label === p.quarter && (
          <>
            <div className="chart-tip-row"><span className="chart-tip-name">Run-rate, no rule</span><span className="chart-tip-val">{money(r.baseline)}</span></div>
            <div className="chart-tip-row"><span className="chart-tip-name">With the rule</span><span className="chart-tip-val">{money(lo)} to {money(hi)}</span></div>
          </>
        )}
      </div>
    );
  };
  return (
    <section className="card">
      <div className="chart-head">
        <div>
          <h3>Quarterly revenue, then a rough Q4 2026</h3>
          <p>{p.method}.</p>
        </div>
        <span className="chip chip-warn">Rough run-rate, not a forecast model</span>
      </div>
      <ul className="legend">
        <li><span className="swatch" style={{ background: "var(--series-2)" }} />Actual</li>
        <li><span className="swatch" style={{ background: "var(--text-3)" }} />Q4 run-rate, no rule</li>
        <li><span className="swatch" style={{ background: "var(--series-1)", opacity: 0.35 }} />Q4 with the rule (between the two outcomes)</li>
      </ul>
      <div className="chart-box" style={{ height: 280 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 10, right: 28, bottom: 0, left: 4 }}>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis dataKey="quarter" tick={{ fill: "var(--text-3)", fontSize: 12 }} tickLine={false} axisLine={{ stroke: "var(--border-strong)" }} padding={{ left: 12, right: 24 }} />
            <YAxis tick={{ fill: "var(--text-3)", fontSize: 12 }} tickLine={false} axisLine={false} tickFormatter={axisFmt("$")} width={64} domain={["auto", "auto"]} />
            <Tooltip content={<Tip />} />
            <ReferenceLine x={last?.quarter} stroke="var(--border-strong)" strokeDasharray="3 3" />
            <Area dataKey="band" stroke="var(--series-1)" strokeWidth={1} fill="var(--series-1)" fillOpacity={0.25} isAnimationActive={false} />
            <Line dataKey="baseline" stroke="var(--text-3)" strokeWidth={2} strokeDasharray="5 4" dot={{ r: 3 }} isAnimationActive={false} />
            <Line dataKey="actual" stroke="var(--series-2)" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="bridge-hint">
        {p.quarter}: {money(p.q4.baseline)} without the rule; between {money(lo)} and {money(hi)} with it.
        {p.q4_profit_after_refunds && <> Profit after refunds: {money(p.q4_profit_after_refunds.baseline)} without the rule; between {money(Math.min(p.q4_profit_after_refunds.keep_at_cap, p.q4_profit_after_refunds.lose_order))} and {money(Math.max(p.q4_profit_after_refunds.keep_at_cap, p.q4_profit_after_refunds.lose_order))} with it.</>}
      </p>
    </section>
  );
}

function QuarterEndReplay() {
  const [threshold, setThreshold] = useState(TH.def);
  const [win, setWin] = useState(WIN.def);
  const [bridgeOf, setBridgeOf] = useState("keep_at_cap");
  const { data: d, error, loading, retry } = useWhatif(threshold, win);

  if (!d) return error ? <ErrorBox error={error} onRetry={retry} /> : <Loading what="Replaying 2026" />;
  const f = d.flagged;
  const sc = Object.fromEntries(d.scenarios.map((s) => [s.id, s]));
  const pg = d.range?.profit_after_refunds_growth ?? [];
  const rg = d.range?.revenue_growth ?? [];

  return (
    <>
      <section className={`card wi-controls${loading ? " is-loading" : ""}`}>
        <div className="sliders">
          <Slider id="wi-th" label="Approval needed above this discount" spec={TH} value={threshold} onChange={setThreshold} unit="%" />
          <Slider id="wi-win" label="Days before quarter end" spec={WIN} value={win} onChange={setWin} unit=" days" />
        </div>
        <p className="sim-line">
          Flagged in {d.period}: <b>{num(f.orders)}</b> orders, <b>{money(f.revenue)}</b> of revenue
          {f.avg_discount != null && <> at {num(f.avg_discount)}% average discount</>}, <b>{num(f.share_r07)}%</b> of them by R07.
          {f.refunds != null && <> {money(f.refunds)} of it was refunded later.</>}
        </p>
        {error && <ErrorBox error={error} onRetry={retry} />}
      </section>

      <div className="wi-heads">
        <div className="card wi-head">
          <span className="mini-label">Profit after refunds growth vs Jan-Sep 2025</span>
          <div className="wi-big"><span className="muted">{pctSigned(d.actual.profit_after_refunds_growth)} actual</span> <b>between {pctSigned(pg[0])} and {pctSigned(pg[1])}</b></div>
          <span className="small muted">with the rule</span>
        </div>
        <div className="card wi-head">
          <span className="mini-label">Revenue growth vs Jan-Sep 2025</span>
          <div className="wi-big"><span className="muted">{pctSigned(d.actual.revenue_growth)} actual</span> <b>between {pctSigned(rg[0])} and {pctSigned(rg[1])}</b></div>
          <span className="small muted">with the rule</span>
        </div>
      </div>

      <section className="block">
        <SectionHead title="Actual against the two outcomes">The truth sits between the two columns: some customers keep the order at the capped discount, some walk away.</SectionHead>
        <ResultTable d={d} />
      </section>

      <section className="block card">
        <div className="chart-head">
          <div>
            <h3>The gap, replayed</h3>
            <p>Same bridge as The gap page, recomputed with the rule applied to the 2026 orders.</p>
          </div>
          <div className="tabs" role="tablist" aria-label="Scenario">
            {d.scenarios.map((s) => (
              <button key={s.id} type="button" role="tab" aria-selected={bridgeOf === s.id} className={bridgeOf === s.id ? "is-on" : ""} onClick={() => setBridgeOf(s.id)}>
                {s.id === "keep_at_cap" ? "Keeps the order" : s.id === "lose_order" ? "Walks away" : s.label}
              </button>
            ))}
          </div>
        </div>
        {d.bridge_by_scenario?.[bridgeOf] ? <BridgeChart bridge={d.bridge_by_scenario[bridgeOf]} /> : <p className="muted">No bridge for this scenario.</p>}
        <p className="bridge-hint">{sc[bridgeOf]?.label}.</p>
      </section>

      {d.projection && <section className="block"><Projection p={d.projection} /></section>}

      <section className="block card wi-assumptions">
        <h3>Assumptions</h3>
        <ul>{(d.assumptions ?? []).filter((a) => !/^provisional/i.test(a)).map((a) => <li key={a}>{plainRules(a)}</li>)}</ul>
      </section>
    </>
  );
}

// Tabs: the three policy modules (all valid orders), then the quarter-end replay, which covers
// quarter-end business orders only and is a separate analysis. The page title follows the tab.
export default function WhatIfPage() {
  const { setHeader } = useApp();
  const [tab, setTab] = useState("damage_policy");
  useEffect(() => { if (tab === "replay") setHeader(null); }, [tab, setHeader]);
  useEffect(() => () => setHeader(null), [setHeader]);
  return (
    <>
      <PolicySimulator tab={tab} setTab={setTab} onHeader={(h) => setHeader({ page: "whatif", ...h })} />
      {tab === "replay" && (
        <section className="replay-sep">
          <div className="replay-head">
            <span className="chip chip-neutral">Separate analysis</span>
            <p>Quarter-end business orders only, the scope of the Action queue rule. The Pricing tab covers all valid orders, so the two results are not comparable as if only the cap changed.</p>
          </div>
          <QuarterEndReplay />
        </section>
      )}
    </>
  );
}
