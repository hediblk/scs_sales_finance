import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "../data/api.js";
import { useResource } from "../state.jsx";

// One filter set per page, shared by every DynamicChart on that page.
// Dimensions match the /api/explore filters; values are lists (comma-joined in the query).
export const DIMS = [
  ["region", "Region"],
  ["rep", "Account rep"],
  ["segment", "Segment"],
  ["product", "Product"],
  ["category", "Category"],
];
export const PERIODS = [
  ["all", "Jan 2025 to Sep 2026", null, null],
  ["2026", "Jan-Sep 2026", "2026-01-01", "2026-09-30"],
  ["2025ytd", "Jan-Sep 2025", "2025-01-01", "2025-09-30"],
  ["2025", "Full year 2025", "2025-01-01", "2025-12-31"],
];

const Ctx = createContext(null);
const EMPTY = { region: [], rep: [], segment: [], product: [], category: [], from: null, to: null, periodLabel: null };

// Filters survive page switches within the session (keyed by the provider's id).
const saved = new Map();

export function FilterProvider({ id, initial, children }) {
  const [f, setF] = useState(() => (id && saved.has(id) ? saved.get(id) : { ...EMPTY, ...initial }));
  useEffect(() => { if (id) saved.set(id, f); }, [id, f]);
  const addFilter = useCallback((dim, value) => setF((s) => (s[dim]?.includes(value) ? s : { ...s, [dim]: [...(s[dim] ?? []), value] })), []);
  const removeFilter = useCallback((dim, value) => setF((s) => ({ ...s, [dim]: s[dim].filter((v) => v !== value) })), []);
  const setPeriod = useCallback((from, to, periodLabel) => setF((s) => ({ ...s, from, to, periodLabel })), []);
  const clearAll = useCallback(() => setF(EMPTY), []);
  const value = useMemo(() => ({ filters: f, addFilter, removeFilter, setPeriod, clearAll }), [f, addFilter, removeFilter, setPeriod, clearAll]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

// Outside a provider, charts still work with no filters.
const NONE = { filters: EMPTY, addFilter: () => {}, removeFilter: () => {}, setPeriod: () => {}, clearAll: () => {} };
export const useFilters = () => useContext(Ctx) ?? NONE;

// Query params for /api/explore from page filters plus a preset's fixed filters.
export function filterParams(f, fixed = {}) {
  const out = {};
  for (const [dim] of DIMS) {
    const vals = [...new Set([...(fixed[dim] ?? []), ...(f[dim] ?? [])])];
    if (vals.length) out[dim] = vals.join(",");
  }
  if (f.from || fixed.from) out.from = f.from ?? fixed.from;
  if (f.to || fixed.to) out.to = f.to ?? fixed.to;
  return out;
}

export function describeFilters(f) {
  const bits = DIMS.filter(([d]) => f[d]?.length).map(([d, l]) => `${l.toLowerCase()} ${f[d].join(" or ")}`);
  if (f.from || f.to) bits.push(`between ${f.from ?? "2025-01-01"} and ${f.to ?? "2026-09-30"}`);
  return bits.join(", ");
}

export function FilterBar({ note }) {
  const { filters: f, addFilter, removeFilter, setPeriod, clearAll } = useFilters();
  const opts = useResource("explore-options", api.exploreOptions);
  const periodKey = PERIODS.find(([, , from, to]) => from === f.from && to === f.to)?.[0] ?? "custom";
  const chips = DIMS.flatMap(([d, l]) => (f[d] ?? []).map((v) => ({ d, l, v })));
  return (
    <div className="filter-bar card">
      <div className="filter-row">
        <span className="mini-label" style={{ margin: 0 }}>Filters</span>
        <label className="select"><span className="sr-only">Period</span>
          <select value={periodKey} onChange={(e) => {
            const p = PERIODS.find(([k]) => k === e.target.value);
            if (p) setPeriod(p[2], p[3], null);
          }}>
            {PERIODS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            {periodKey === "custom" && <option value="custom">{f.periodLabel ?? `${f.from} to ${f.to}`}</option>}
          </select>
        </label>
        {DIMS.map(([d, l]) => (
          <label key={d} className="select"><span className="sr-only">{l}</span>
            <select value="" onChange={(e) => e.target.value && addFilter(d, e.target.value)}>
              <option value="">{l}</option>
              {(opts.data?.filters?.[d] ?? []).filter((v) => !f[d]?.includes(v)).map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </label>
        ))}
        {(chips.length > 0 || f.from || f.to) && <button type="button" className="link-btn small" onClick={clearAll}>Clear all</button>}
      </div>
      {chips.length > 0 && (
        <div className="filter-chips">
          {chips.map(({ d, l, v }) => (
            <span key={`${d}-${v}`} className="fchip">
              {l}: <b>{v}</b>
              <button type="button" onClick={() => removeFilter(d, v)} aria-label={`Remove ${l} ${v}`}>×</button>
            </span>
          ))}
        </div>
      )}
      {note && <p className="muted small" style={{ margin: "6px 0 0" }}>{note}</p>}
    </div>
  );
}
