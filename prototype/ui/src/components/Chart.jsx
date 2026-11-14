import { useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, LabelList, Line, LineChart, ReferenceLine, ResponsiveContainer,
  Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from "recharts";
import { axisFmt, fmt, money, tickLabel } from "../lib/format.js";

// Bridge (waterfall) from /api/gap: start, minus..., end. Each bar is clickable.
export function BridgeChart({ bridge, height = 340, selected, onSelect }) {
  let running = 0;
  const rows = bridge.map((b) => {
    let base = 0;
    let signed = b.value;
    if (b.kind === "start") running = b.value;
    else if (b.kind === "minus") { running -= b.value; base = running; signed = -b.value; }
    else if (b.kind === "plus") { base = running; running += b.value; }
    else base = 0;
    return { ...b, base, bar: Math.abs(b.value), signed };
  });
  const fill = (b) => (b.kind === "minus" ? "var(--bridge-down)" : b.kind === "plus" ? "var(--bridge-up)" : "var(--bridge-total)");
  // Long labels wrap on two or three lines under each bar.
  const WrapTick = ({ x, y, payload }) => {
    const words = String(payload.value).split(" ");
    const lines = [];
    for (const w of words) {
      const last = lines[lines.length - 1];
      if (last && (last + " " + w).length <= 11) lines[lines.length - 1] = `${last} ${w}`;
      else lines.push(w);
    }
    return (
      <text x={x} y={y + 12} textAnchor="middle" fill="var(--text-2)" fontSize={11}>
        {lines.slice(0, 5).map((l, i) => <tspan key={i} x={x} dy={i ? 12 : 0}>{l}</tspan>)}
      </text>
    );
  };
  const Tip = ({ active, payload }) => {
    if (!active || !payload?.length) return null;
    const b = payload[0].payload;
    return (
      <div className="chart-tip">
        <div className="chart-tip-label">{b.label}</div>
        <div className="chart-tip-row"><span className="chart-tip-name">{b.kind === "minus" ? "Takes away" : "Amount"}</span><span className="chart-tip-val">{money(b.signed)}</span></div>
        {b.driver_id && <div className="chart-tip-row"><span className="chart-tip-name">Click to see the driver</span></div>}
      </div>
    );
  };
  return (
    <div className="chart-box" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 24, right: 8, bottom: 4, left: 4 }} barCategoryGap="22%">
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis dataKey="label" tick={<WrapTick />} tickLine={false} axisLine={{ stroke: "var(--border-strong)" }} interval={0} height={72} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} tickFormatter={axisFmt("$")} width={64} />
          <ReferenceLine y={0} stroke="var(--border-strong)" />
          <Tooltip content={<Tip />} cursor={{ fill: "var(--surface-3)" }} />
          <Bar dataKey="base" stackId="b" fill="transparent" isAnimationActive={false} />
          <Bar dataKey="bar" stackId="b" radius={[4, 4, 0, 0]} isAnimationActive={false} cursor="pointer"
            onClick={(d) => onSelect?.(d.payload ?? d)}>
            {rows.map((r) => (
              <Cell key={r.id} fill={fill(r)} stroke={selected === r.id ? "var(--text)" : "var(--surface)"} strokeWidth={selected === r.id ? 2 : 1} />
            ))}
            <LabelList dataKey="signed" position="top" formatter={(v) => money(v, { compact: true })}
              fill="var(--text)" stroke="none" fontSize={12} fontWeight={600} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// Colors come from tokens.css (--series-1..5), assigned in series order, never cycled.
const color = (i) => `var(--series-${Math.min(i + 1, 5)})`;
const AXIS = { fill: "var(--text-3)", fontSize: 12 };

function ChartTooltip({ active, payload, label, unit, xLabel }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tip">
      {label != null && <div className="chart-tip-label">{xLabel ? `${xLabel}: ` : ""}{tickLabel(label)}</div>}
      {payload.map((p) => (
        <div key={p.dataKey ?? p.name} className="chart-tip-row">
          <span className="swatch" style={{ background: p.color ?? p.fill ?? p.stroke }} />
          <span className="chart-tip-name">{p.name}</span>
          <span className="chart-tip-val">{fmt(p.value, unit)}</span>
        </div>
      ))}
    </div>
  );
}

export function Legend({ series }) {
  if (!series || series.length < 2) return null;
  return (
    <ul className="legend">
      {series.map((s, i) => (
        <li key={s.key}><span className="swatch" style={{ background: color(i) }} />{s.label}</li>
      ))}
    </ul>
  );
}

// Renders any chart object from the contract: { type, x, series, rows, unit? }.
// onPick(xValue, seriesKey?) makes bars and points clickable (drill-down).
export function ChartRenderer({ chart, height = 260, onPick }) {
  const { type = "bar", x, series = [], rows = [], unit } = chart;
  const yFmt = axisFmt(unit);
  const pickable = typeof onPick === "function";
  const common = {
    data: rows, margin: { top: 8, right: 12, bottom: 0, left: 4 },
    style: pickable ? { cursor: "pointer" } : undefined,
  };
  const grid = <CartesianGrid vertical={false} stroke="var(--border)" />;
  const xAxis = (
    <XAxis dataKey={x} tick={AXIS} tickLine={false} axisLine={{ stroke: "var(--border-strong)" }}
      tickFormatter={tickLabel} minTickGap={12} interval="preserveStartEnd" />
  );
  const yAxis = <YAxis tick={AXIS} tickLine={false} axisLine={false} tickFormatter={yFmt} width={60} />;
  const tip = <Tooltip content={<ChartTooltip unit={unit} />} cursor={{ fill: "var(--surface-3)", stroke: "var(--border-strong)" }} />;

  let body;
  if (type === "line") {
    body = (
      <LineChart {...common} onClick={pickable ? (e) => e?.activeLabel != null && onPick(e.activeLabel) : undefined}>
        {grid}{xAxis}{yAxis}{tip}
        {series.map((s, i) => (
          <Line key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={color(i)} strokeWidth={2}
            dot={false} activeDot={{ r: 5, strokeWidth: 2, stroke: "var(--surface)" }} isAnimationActive={false} />
        ))}
      </LineChart>
    );
  } else if (type === "scatter") {
    const ykey = series[0]?.key;
    body = (
      <ScatterChart margin={common.margin}>
        {grid}
        <XAxis type="number" dataKey={x} name={chart.x_label ?? x} tick={AXIS} tickLine={false}
          axisLine={{ stroke: "var(--border-strong)" }} />
        <YAxis type="number" dataKey={ykey} name={series[0]?.label} tick={AXIS} tickLine={false} axisLine={false}
          tickFormatter={yFmt} width={60} />
        <ZAxis range={[70, 70]} />
        <Tooltip content={<ScatterTip chart={chart} />} cursor={{ stroke: "var(--border-strong)" }} />
        {series.map((s, i) => (
          <Scatter key={s.key} name={s.label} data={rows} dataKey={s.key} fill={color(i)} stroke="var(--surface)" strokeWidth={2}
            isAnimationActive={false} />
        ))}
      </ScatterChart>
    );
  } else {
    const stacked = type === "stacked-bar";
    body = (
      <BarChart {...common} barGap={2} barCategoryGap="24%">
        {grid}{xAxis}{yAxis}{tip}
        {series.map((s, i) => (
          <Bar key={s.key} dataKey={s.key} name={s.label} fill={color(i)} maxBarSize={44}
            stackId={stacked ? "stack" : undefined}
            radius={!stacked || i === series.length - 1 ? [4, 4, 0, 0] : 0}
            stroke={stacked ? "var(--surface)" : undefined} strokeWidth={stacked ? 1 : 0}
            onClick={pickable ? (d) => onPick((d.payload ?? d)[x], series.length > 1 ? s.key : undefined) : undefined}
            isAnimationActive={false} />
        ))}
      </BarChart>
    );
  }
  return (
    <div className="chart-box" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">{body}</ResponsiveContainer>
    </div>
  );
}

function ScatterTip({ active, payload, chart }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  const s = chart.series[0];
  return (
    <div className="chart-tip">
      <div className="chart-tip-row"><span className="chart-tip-name">{chart.x_label ?? chart.x}</span><span className="chart-tip-val">{fmt(row[chart.x])}</span></div>
      <div className="chart-tip-row"><span className="chart-tip-name">{s.label}</span><span className="chart-tip-val">{fmt(row[s.key], chart.unit)}</span></div>
    </div>
  );
}

function DataTable({ chart }) {
  const cols = [chart.x, ...chart.series.map((s) => s.key)];
  const head = [chart.x_label ?? chart.x, ...chart.series.map((s) => s.label)];
  return (
    <div className="table-wrap">
      <table className="table compact">
        <thead><tr>{head.map((h) => <th key={h}>{h}</th>)}</tr></thead>
        <tbody>
          {chart.rows.map((r, i) => (
            <tr key={i}>{cols.map((c, j) => <td key={c} className={j ? "num" : ""}>{j ? fmt(r[c], chart.unit) : tickLabel(r[c])}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Card wrapper: title, caption, legend, chart, and a table view for accessibility and Q&A.
export function ChartCard({ chart, height, highlight = false }) {
  const [asTable, setAsTable] = useState(false);
  return (
    <figure id={`chart-${chart.id}`} className={`card chart-card${highlight ? " is-highlight" : ""}`}>
      <figcaption className="chart-head">
        <div>
          <h3>{chart.title}</h3>
          {chart.caption && <p>{chart.caption}</p>}
        </div>
        <button type="button" className="btn btn-quiet btn-xs" onClick={() => setAsTable((v) => !v)} aria-pressed={asTable}>
          {asTable ? "Chart" : "Table"}
        </button>
      </figcaption>
      {asTable ? <DataTable chart={chart} /> : (
        <>
          <Legend series={chart.series} />
          <ChartRenderer chart={chart} height={height} />
        </>
      )}
    </figure>
  );
}
