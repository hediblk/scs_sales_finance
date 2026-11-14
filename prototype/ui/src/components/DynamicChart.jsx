import { useEffect, useMemo, useState } from "react";
import { api } from "../data/api.js";
import { useApp, useResource } from "../state.jsx";
import { num } from "../lib/format.js";
import { ChartRenderer, Legend } from "./Chart.jsx";
import { ErrorBox } from "./ui.jsx";
import { DIMS, describeFilters, filterParams, useFilters } from "./Filters.jsx";

const FILTER_DIMS = new Set(DIMS.map(([d]) => d));
// After a click filters on the grouped value, the clicked chart regroups one level down.
const DRILL_NEXT = { region: "rep", rep: "product", segment: "region", category: "product", product: "region", quarter: "month", month: "region" };
const pad = (n) => String(n).padStart(2, "0");

// "2025Q3" -> 2025-07-01..2025-09-30, "2025-07" -> 2025-07-01..2025-07-31
function periodOf(by, v) {
  let m;
  if (by === "quarter" && (m = String(v).match(/^(\d{4})Q([1-4])$/))) {
    const y = Number(m[1]); const q = Number(m[2]);
    const end = new Date(Date.UTC(y, q * 3, 0)).getUTCDate();
    return [`${y}-${pad(q * 3 - 2)}-01`, `${y}-${pad(q * 3)}-${end}`];
  }
  if (by === "month" && (m = String(v).match(/^(\d{4})-(\d{2})$/))) {
    const end = new Date(Date.UTC(Number(m[1]), Number(m[2]), 0)).getUTCDate();
    return [`${v}-01`, `${v}-${end}`];
  }
  return null;
}

function Select({ label, value, onChange, options, allowNone }) {
  return (
    <label className="dyn-select">
      <span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {allowNone && <option value="">None</option>}
        {options.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
      </select>
    </label>
  );
}

// One chart component for the whole app, on GET /api/explore.
// preset: { metric, by, split, highlight, normalize, filters, title, caption } = the view it opens on.
export function DynamicChart({ preset = {}, height = 250 }) {
  const { filters, addFilter, setPeriod } = useFilters();
  const { go, askQuestion } = useApp();
  const opts = useResource("explore-options", api.exploreOptions);
  const [metric, setMetric] = useState(preset.metric ?? "revenue");
  const [by, setBy] = useState(preset.by ?? "quarter");
  const [split, setSplit] = useState(preset.split ?? "");
  const [msg, setMsg] = useState(null);
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const [attempt, setAttempt] = useState(0);

  const asPreset = metric === (preset.metric ?? "revenue") && by === (preset.by ?? "quarter") && split === (preset.split ?? "");
  const params = useMemo(() => ({
    metric, by,
    split: split || undefined,
    highlight: split && split === preset.split ? preset.highlight : undefined,
    normalize: split && split === preset.split ? preset.normalize : undefined,
    ...filterParams(filters, preset.filters),
  }), [metric, by, split, filters, preset.split, preset.highlight, preset.normalize, preset.filters]);
  const key = JSON.stringify(params);

  useEffect(() => {
    let live = true;
    setState((s) => ({ ...s, loading: true }));
    const t = setTimeout(() => {
      api.explore(params)
        .then((data) => live && setState({ data, error: null, loading: false }))
        .catch((error) => live && setState((s) => ({ data: s.data, error, loading: false })));
    }, 120);
    return () => { live = false; clearTimeout(t); };
  }, [key, attempt]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { if (msg) { const t = setTimeout(() => setMsg(null), 3500); return () => clearTimeout(t); } }, [msg]);

  const d = state.data;
  const chart = d?.chart;
  const rows = useMemo(() => (d ? d.rows.map((r) => Object.fromEntries(d.columns.map((c, i) => [c, r[i]]))) : []), [d]);
  const byLabel = opts.data?.by?.find((o) => o.id === by)?.label ?? by;

  const pick = (xv, seriesKey) => {
    const done = [];
    if (FILTER_DIMS.has(by)) { addFilter(by, xv); done.push(xv); } else {
      const p = periodOf(by, xv);
      if (p) { setPeriod(p[0], p[1], String(xv)); done.push(xv); }
    }
    if (seriesKey && FILTER_DIMS.has(split) && !/^Other/.test(seriesKey)) { addFilter(split, seriesKey); done.push(seriesKey); }
    if (!done.length) {
      setMsg(`${byLabel} is not a filter. Group by region, rep, segment, product, category, month or quarter to drill down.`);
      return;
    }
    const next = DRILL_NEXT[by];
    if (next && next !== split) setBy(next);
    setMsg(`Filtered on ${done.join(" and ")}${next && next !== split ? `, now grouped by ${opts.data?.by?.find((o) => o.id === next)?.label.toLowerCase() ?? next}` : ""}.`);
  };

  const single = (dim) => (filters[dim]?.length === 1 ? filters[dim][0] : (preset.filters?.[dim]?.length === 1 ? preset.filters[dim][0] : undefined));
  const toQueue = () => go("queue", Object.fromEntries(Object.entries({ condition: "all", rep: single("rep"), region: single("region"), segment: single("segment") }).filter(([, v]) => v)));
  const toAsk = () => {
    const desc = describeFilters({ ...filters, ...Object.fromEntries(Object.entries(preset.filters ?? {}).map(([k, v]) => [k, [...new Set([...(filters[k] ?? []), ...v])]])) });
    askQuestion(`List the orders${desc ? ` with ${desc}` : ""}: order date, customer, product, revenue and discount.`);
  };

  const fixed = Object.entries(preset.filters ?? {}).filter(([k]) => FILTER_DIMS.has(k));

  return (
    <figure className={`card chart-card dyn${state.loading ? " is-loading" : ""}`}>
      <figcaption className="chart-head">
        <div>
          <h3>{asPreset && preset.title ? preset.title : chart?.title ?? "Loading..."}</h3>
          {asPreset && preset.caption && <p>{preset.caption}</p>}
        </div>
        {!asPreset && (
          <button type="button" className="btn btn-quiet btn-xs" onClick={() => { setMetric(preset.metric ?? "revenue"); setBy(preset.by ?? "quarter"); setSplit(preset.split ?? ""); }}>
            Back to the story view
          </button>
        )}
      </figcaption>

      {/* Folded by default: the story view is what the demo shows; exploring is one click away. */}
      <details className="dyn-explore" open={!asPreset}>
        <summary>Change the view</summary>
        <div className="dyn-controls">
          <Select label="Metric" value={metric} onChange={setMetric} options={opts.data?.metrics ?? [{ id: metric, label: metric }]} />
          <Select label="Group by" value={by} onChange={setBy} options={opts.data?.by ?? [{ id: by, label: by }]} />
          <Select label="Split" value={split} onChange={setSplit} allowNone options={(opts.data?.split ?? []).filter((o) => o.id !== by)} />
          {fixed.length > 0 && <span className="dyn-fixed">{fixed.map(([k, v]) => `${k}: ${v.join(", ")}`).join(" · ")}</span>}
        </div>
      </details>

      {state.error && <ErrorBox error={state.error} onRetry={() => setAttempt((n) => n + 1)} />}
      {chart?.note && <p className="dyn-note">{chart.note}</p>}
      {d && rows.length === 0 && <p className="empty">No orders match these filters.</p>}
      {d && rows.length > 0 && (
        <>
          <Legend series={chart.series} />
          <ChartRenderer key={key} chart={{ ...chart, rows }} height={height} onPick={pick} />
        </>
      )}

      <footer className="dyn-foot">
        <span>{d ? `${num(d.n_orders)} orders` : ""}{msg ? "" : " · Click a bar or point to filter on it"}</span>
        {msg && <span className="dyn-msg">{msg}</span>}
        <span className="spacer" />
        <span className="muted small">See these orders:</span>
        <button type="button" className="link-btn small" onClick={toQueue}>Action queue</button>
        <button type="button" className="link-btn small" onClick={toAsk}>Ask</button>
      </footer>
    </figure>
  );
}
