import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../data/api.js";
import { useResource } from "../state.jsx";
import { num } from "../lib/format.js";
import { ChartCard } from "../components/Chart.jsx";
import { Empty, ErrorBox, Loading, SectionHead } from "../components/ui.jsx";
import { DynamicChart } from "../components/DynamicChart.jsx";
import { FilterBar, FilterProvider } from "../components/Filters.jsx";
import { ProfileTable } from "../components/ProfileTable.jsx";

// Clean mode: the four dataset charts as live presets of /api/explore (Raw keeps the raw labels on purpose).
const CLEAN_PRESETS = [
  { metric: "orders", by: "month", title: "Orders per month", caption: "Clean orders by order month." },
  { metric: "orders", by: "region", title: "Orders per region", caption: "After cleaning, every spelling maps to one of five regions." },
  { metric: "orders", by: "discount_band", title: "Orders by discount band", caption: "After the percent fix, every discount is a fraction." },
  { metric: "refunds", by: "month", title: "Refunds per month", caption: "Refunds in dollars, clean data." },
];

const SOURCES = [
  ["raw", "Raw", "data/raw exactly as received. Every value read as text, nothing coerced or fixed."],
  ["clean", "Clean", "data/clean as it is now: duplicates dropped, negative quantities set aside, blank unit costs left blank."],
];
const PAGE = 50;
const pct = (x) => `${num(Math.round(x * 1000) / 10)}%`;

/* ---------- Tables and joins ---------- */

function TableCards({ tables, active, onPick }) {
  return (
    <div className="ds-tables">
      {tables.map((t) => (
        <button key={t.name} type="button" className={`card ds-table${active === t.name ? " is-on" : ""}`} onClick={() => onPick(t.name)} aria-pressed={active === t.name}>
          <div className="ds-table-head">
            <span className="ds-table-name">{t.name}</span>
            <span className="mono muted">{t.file}</span>
          </div>
          <div className="ds-table-nums"><b>{num(t.rows)}</b> rows <span className="muted">·</span> <b>{t.columns}</b> columns</div>
          <p className="ds-table-means">One row is {t.row_means}.</p>
          <div className="ds-table-key">
            <span>Key <span className="mono">{t.key}</span></span>
            {t.key_unique
              ? <span className="chip chip-good">unique</span>
              : <span className="chip chip-bad">{t.duplicate_keys} repeated</span>}
            {t.exact_duplicate_rows > 0 && <span className="chip chip-warn">{t.exact_duplicate_rows} exact duplicate rows</span>}
          </div>
        </button>
      ))}
    </div>
  );
}

function JoinDiagram({ tables, joins }) {
  const byName = Object.fromEntries(tables.map((t) => [t.name, t]));
  const find = (from) => joins.find((j) => j.from === from);
  const co = find("orders.customer_id");
  const or = find("returns.order_id");
  const others = joins.filter((j) => j !== co && j !== or);
  const Box = ({ name }) => (
    <div className="jd-box">
      <b>{name}</b>
      <span>{num(byName[name]?.rows)} rows</span>
      <span className="mono">{byName[name]?.key}</span>
    </div>
  );
  const Edge = ({ card, j, what }) => (
    <div className="jd-edge">
      <span className="jd-card">{card}</span>
      <span className="jd-line" aria-hidden="true" />
      <span className="jd-rate">{j ? `${pct(j.match_rate)} of ${what} match` : "not checked"}</span>
      {j?.note && <span className="jd-note">{j.note}</span>}
    </div>
  );
  return (
    <section className="card">
      <div className="chart-head"><div><h3>How the files join</h3><p>One customer has many orders; one order has at most one return.</p></div></div>
      <div className="jd">
        <Box name="customers" />
        <Edge card="1 to many" j={co} what="orders" />
        <Box name="orders" />
        <Edge card="1 to 0 or 1" j={or} what="returns" />
        <Box name="returns" />
      </div>
      {others.length > 0 && (
        <ul className="jd-checks">
          {others.map((j) => (
            <li key={j.from}><span className="mono">{j.from}</span> vs <span className="mono">{j.to}</span>: <b>{pct(j.match_rate)}</b> agree{j.note ? ` (${j.note})` : ""}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

/* ---------- Column profiles ---------- */

const shown = (v) => (v === "" || v == null ? <i className="blank">blank</i> : v);

/* ---------- Raw table ---------- */

function RowsTable({ source, table, filter, setFilter }) {
  const [offset, setOffset] = useState(0);
  const [q, setQ] = useState("");
  const [qLive, setQLive] = useState("");
  const [sort, setSort] = useState(null); // { col, desc }
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => { setOffset(0); }, [source, table, filter, q, sort]);
  useEffect(() => { const t = setTimeout(() => setQ(qLive.trim()), 250); return () => clearTimeout(t); }, [qLive]);
  useEffect(() => {
    let live = true;
    setState((s) => ({ ...s, loading: true }));
    api.dsRows(source, table, { offset, limit: PAGE, q, col: filter?.col, val: filter?.val, sort: sort?.col, desc: sort?.desc ? 1 : undefined })
      .then((data) => live && setState({ data, error: null, loading: false }))
      .catch((error) => live && setState({ data: null, error, loading: false }));
    return () => { live = false; };
  }, [source, table, offset, q, filter, sort, attempt]);

  const d = state.data;
  const rows = useMemo(() => {
    if (!d) return [];
    if (!sort || d.sort === sort.col) return d.rows; // the API sorted the whole table
    const i = d.columns.indexOf(sort.col);
    const key = (v) => (v !== "" && !Number.isNaN(Number(v)) ? Number(v) : String(v).toLowerCase());
    return [...d.rows].sort((a, b) => {
      const x = key(a[i]); const y = key(b[i]);
      const r = typeof x === typeof y ? (x < y ? -1 : x > y ? 1 : 0) : typeof x === "number" ? -1 : 1;
      return sort.desc ? -r : r;
    });
  }, [d, sort]);
  const fixIdx = d?.columns.indexOf("fixes") ?? -1;
  const clickSort = (col) => setSort((s) => (s?.col === col ? (s.desc ? null : { col, desc: true }) : { col, desc: false }));

  return (
    <section className="card ds-rows" id="ds-rows">
      <div className="ds-rows-bar">
        <input className="search" type="search" placeholder="Search every column" value={qLive} onChange={(e) => setQLive(e.target.value)} aria-label="Search rows" style={{ minWidth: 240 }} />
        {filter && (
          <span className="chip chip-accent">
            <span className="mono">{filter.col}</span> = "{filter.val === "" ? "(blank)" : filter.val}"
            <button type="button" className="link-btn" onClick={() => setFilter(null)} aria-label="Clear filter">clear</button>
          </span>
        )}
        <span className="spacer" />
        {d && <span className="muted small">{d.total ? `${num(offset + 1)} to ${num(Math.min(offset + PAGE, d.total))} of ${num(d.total)}` : "0 rows"}</span>}
        <button type="button" className="btn btn-quiet btn-sm" disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - PAGE))}>Previous</button>
        <button type="button" className="btn btn-quiet btn-sm" disabled={!d || offset + PAGE >= d.total} onClick={() => setOffset((o) => o + PAGE)}>Next</button>
      </div>
      {state.error && <ErrorBox error={state.error} onRetry={() => setAttempt((n) => n + 1)} />}
      {!d && state.loading && <Loading what="Loading rows" />}
      {d && (
        <div className={`table-wrap ds-grid${state.loading ? " is-loading" : ""}`}>
          <table className="table compact">
            <thead>
              <tr>{d.columns.map((c) => (
                <th key={c} className={c === "raw_line" ? "num" : ""}>
                  <button type="button" className="th-sort" onClick={() => clickSort(c)} aria-sort={sort?.col === c ? (sort.desc ? "descending" : "ascending") : "none"}>
                    {c === "raw_line" ? "line" : c}{sort?.col === c ? (sort.desc ? " ▼" : " ▲") : ""}
                  </button>
                </th>
              ))}</tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r[0]} className={fixIdx >= 0 && r[fixIdx] ? "has-fix" : ""}>
                  {r.map((v, i) => (
                    <td key={i} className={i === 0 ? "num muted" : i === fixIdx ? "fix-cell" : "mono"}>{shown(v)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 && <Empty>No row matches.</Empty>}
        </div>
      )}
    </section>
  );
}

/* ---------- Set aside (clean only) ---------- */

function SetAside() {
  const { data, error, reload } = useResource("ds-set-aside", api.setAside);
  const [open, setOpen] = useState(null);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loading what="Loading set-aside rows" />;
  const groups = data.reduce((m, r) => ((m[`${r.outcome}: ${r.reason}`] = (m[`${r.outcome}: ${r.reason}`] ?? 0) + 1), m), {});
  return (
    <section className="block">
      <SectionHead title="Set aside or dropped">Rows that are in the raw file but not in the clean tables, each with the reason. Nothing here is deleted from data/raw.</SectionHead>
      <div className="chips" style={{ marginBottom: 10 }}>
        {Object.entries(groups).map(([k, n]) => <span key={k} className="chip chip-neutral"><b>{n}</b> {k}</span>)}
      </div>
      <div className="card table-card">
        <div className="table-wrap" style={{ maxHeight: 420, overflowY: "auto" }}>
          <table className="table compact">
            <thead><tr><th className="num">Line</th><th>Order</th><th>Step</th><th>Outcome</th><th>Reason</th><th /></tr></thead>
            <tbody>
              {data.map((r) => (
                <Fragment key={r.raw_line}>
                  <tr>
                    <td className="num muted">{r.raw_line}</td>
                    <td className="mono">{r.order_id}</td>
                    <td>{r.step}</td>
                    <td><span className={`chip ${r.outcome === "removed" ? "chip-bad" : "chip-warn"}`}>{r.outcome}</span></td>
                    <td>{r.reason}</td>
                    <td><button type="button" className="link-btn small" onClick={() => setOpen(open === r.raw_line ? null : r.raw_line)}>{open === r.raw_line ? "Hide" : "Values"}</button></td>
                  </tr>
                  {open === r.raw_line && (
                    <tr><td colSpan={6} className="set-aside-values mono">
                      {Object.entries(r.values ?? {}).map(([k, v]) => <span key={k}>{k}=<b>{v === "" ? "(blank)" : v}</b></span>)}
                    </td></tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

/* ---------- Page ---------- */

export default function DatasetPage({ params }) {
  const [source, setSource] = useState(params?.source === "clean" ? "clean" : "raw");
  const [table, setTable] = useState(params?.table ?? "orders");
  const [filter, setFilter] = useState(null);
  const tables = useResource(`ds-tables-${source}`, () => api.dsTables(source), [source]);
  const profile = useResource(`ds-profile-${source}-${table}`, () => api.dsProfile(source, table), [source, table]);
  const charts = useResource(`ds-charts-${source}`, () => api.dsCharts(source), [source]);
  // Raw mode compares distinct counts with the clean profile to flag values written several ways.
  const cleanProfile = useResource(`ds-profile-clean-${table}`, () => api.dsProfile("clean", table), [table]);
  const cleanDistinct = Object.fromEntries((cleanProfile.data ?? []).map((c) => [c.column, c.distinct]));
  const rowsRef = useRef(null);

  useEffect(() => { setFilter(null); }, [table]);
  const filterTo = (col, val) => {
    setFilter({ col, val });
    document.getElementById("ds-rows")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const tdata = tables.data;
  const tmeta = tdata?.tables.find((t) => t.name === table);
  const chartList = Array.isArray(charts.data) ? charts.data : charts.data?.charts ?? [];
  // "N above 1" for the discount column comes from the raw discount histogram the API already computes.
  const discountHist = chartList.find((c) => /discount_hist/.test(c.id));
  const aboveOne = discountHist?.rows?.filter((r) => /1 or more/i.test(String(r[discountHist.x] ?? ""))).reduce((t, r) => t + (r.rows ?? r[discountHist.series?.[0]?.key] ?? 0), 0) ?? 0;

  return (
    <>
      <div className="ds-switch">
        <div className="tabs big" role="tablist" aria-label="Raw or clean data">
          {SOURCES.map(([k, l]) => (
            <button key={k} type="button" role="tab" aria-selected={source === k} className={source === k ? "is-on" : ""} onClick={() => setSource(k)}>{l}</button>
          ))}
        </div>
        <p>{SOURCES.find(([k]) => k === source)[2]}</p>
      </div>

      {tables.error && <ErrorBox error={tables.error} onRetry={tables.reload} />}
      {!tdata ? <Loading what="Loading the files" /> : (
        <>
          <TableCards tables={tdata.tables} active={table} onPick={setTable} />
          <JoinDiagram tables={tdata.tables} joins={tdata.joins ?? []} />
        </>
      )}

      <FilterProvider id="dataset">
      <section className="block">
        <SectionHead title="Explore (clean data)">
          Live chart on the cleaned orders, whichever mode is selected above. Change the measure, the grouping or the split; click a bar to filter.
        </SectionHead>
        <FilterBar note={source === "clean" ? "Filters apply to this chart and to the clean charts further down." : "Filters apply to this chart. The raw charts further down show the file as received."} />
        <DynamicChart height={280} />
      </section>

      <section className="block">
        <SectionHead title={`Columns in ${table}`}>
          {tmeta ? `${tmeta.columns} columns, ${num(tmeta.rows)} rows. Click a row for the full values and a link to those rows.` : ""}
        </SectionHead>
        {profile.error && <ErrorBox error={profile.error} onRetry={profile.reload} />}
        {!profile.data ? <Loading what="Profiling columns" /> : (
          <ProfileTable rows={profile.data} tmeta={tmeta} source={source} aboveOne={table === "orders" ? aboveOne : 0} cleanDistinct={cleanProfile.data ? cleanDistinct : null} onFilter={filterTo} />
        )}
      </section>

      <section className="block" ref={rowsRef}>
        <SectionHead title={`${table} rows, values as they are`}>
          {source === "raw" ? "Exactly what the file holds: mixed spellings, slash dates and percent discounts included." : "The clean table. The fixes column says what changed on each row."}
        </SectionHead>
        <RowsTable source={source} table={table} filter={filter} setFilter={setFilter} />
      </section>

      <section className="block">
        <SectionHead title={`${source === "raw" ? "Raw" : "Clean"} charts`}>
          {source === "raw" ? "The file as received, raw labels included. Switch to Clean for the same charts, live." : "Live charts on the clean data: change the view or click to filter."}
        </SectionHead>
        {source === "raw" ? (
          <>
            {charts.error && <ErrorBox error={charts.error} onRetry={charts.reload} />}
            {!charts.data ? <Loading what="Loading charts" /> : (
              <div className="grid-2">{chartList.map((c) => <ChartCard key={c.id} chart={c} height={220} />)}</div>
            )}
          </>
        ) : (
          <div className="grid-2">{CLEAN_PRESETS.map((p) => <DynamicChart key={p.title} preset={p} height={220} />)}</div>
        )}
      </section>
      </FilterProvider>

      {source === "clean" && <SetAside />}
    </>
  );
}
