import { useState } from "react";
import { api } from "../data/api.js";
import { useApp, useResource } from "../state.jsx";
import { money, num, plainRules } from "../lib/format.js";
import { BridgeChart, ChartRenderer, Legend } from "../components/Chart.jsx";
import { Chip, ErrorBox, Loading, SectionHead, Tile } from "../components/ui.jsx";
import { DynamicChart } from "../components/DynamicChart.jsx";
import { FilterBar, FilterProvider } from "../components/Filters.jsx";

const BUSINESS = ["Reseller", "SMB", "Enterprise"];
// Each driver chart is a preset of /api/explore that opens on the view the story needs.
const PRESETS = {
  discount_band_returns: {
    metric: "return_rate", by: "discount_band", filters: { segment: BUSINESS },
    title: "Deep discounts come back as returns",
    caption: "Business orders by discount band: share returned. Switch the metric to gross margin % for the other half of the story.",
  },
  qe_week_share: {
    metric: "revenue", by: "days_to_quarter_end", split: "rep", highlight: "R07", normalize: "share",
    title: "R07 books half the quarter in its last two weeks",
    caption: "Share of each side's revenue by days before quarter end: R07 against every other rep.",
  },
  furniture_damage_region: {
    metric: "return_rate", by: "region", filters: { category: ["Furniture"] },
    title: "Furniture comes back most on the long routes",
    caption: "Furniture orders returned, by region (all return reasons).",
  },
};

const CRITERIA = [
  ["changed_in_2026", "Changed in 2026"],
  ["controllable", "Company controls it"],
  ["rule_catchable", "A rule catches it early"],
];

function Criterion({ value, label }) {
  const cls = value === true ? "yes" : value === false ? "no" : "";
  const mark = value === true ? "Yes" : value === false ? "No" : "Not checked";
  return <span className={`crit ${cls}`}>{label}: <i>{mark}</i></span>;
}

function HandledBy({ ids }) {
  const { conditions, go } = useApp();
  if (!ids?.length) return null;
  const items = ids.map((id) => {
    const c = conditions.find((x) => x.id === id);
    if (c) return { id, label: `${c.name} (queue)`, onClick: () => go("queue", { condition: id }) };
    if (id === "reps") return { id, label: "Reps tab", onClick: () => go("accounts", { tab: "reps" }) };
    if (id === "accounts" || id === "customers") return { id, label: "Customers tab", onClick: () => go("accounts", { tab: "customers" }) };
    return { id, label: id };
  });
  return (
    <div className="handled">
      <span className="mini-label">Handled in the tool</span>
      {items.map((it) => it.onClick
        ? <button key={it.id} type="button" className="chip-btn" onClick={it.onClick}>{it.label}</button>
        : <span key={it.id} className="chip">{it.label}</span>)}
    </div>
  );
}

// Driver 1 gets both halves of its story: when R07 books, and what deep discounts do.
const DRIVER_PRESETS = { qe_push: ["qe_week_share", "discount_band_returns"] };

function DriverCard({ d, chart, highlight }) {
  const presets = (DRIVER_PRESETS[d.id] ?? [d.chart_id]).map((id) => PRESETS[id]).filter(Boolean);
  const preset = presets[0];
  return (
    <article id={`driver-${d.id}`} className={`card driver rank-${d.rank}${highlight ? " is-highlight" : ""}`}>
      <div className="driver-rank"><b>{d.rank}</b><span>rank</span></div>
      <div className="driver-main">
        <header className="driver-head">
          <h3>{d.title}</h3>
          <div className="driver-impact">
            <b>{d.impact != null ? money(d.impact) : "n/a"}</b>
            {/* The basis and period of each amount, on screen: the four drivers measure different things. */}
            {(d.impact_note ?? d.impact_label) && <span className="impact-basis">{d.impact_note ?? d.impact_label}</span>}
          </div>
        </header>
        <div className="criteria">{CRITERIA.map(([k, l]) => <Criterion key={k} value={d[k]} label={l} />)}</div>
        <div className={preset || chart ? "driver-grid" : ""}>
          <dl className="wwt">
            <div><dt>What happened</dt><dd>{plainRules(d.what)}</dd></div>
            <div><dt>Why it happened</dt><dd>{plainRules(d.why)}</dd></div>
            <div className="is-todo"><dt>What to do</dt><dd>{plainRules(d.todo)}</dd></div>
          </dl>
          {preset ? (
            <div className="mini-chart dyn-wrap dyn-stack">
              {presets.map((p) => <DynamicChart key={p.title} preset={p} height={190} />)}
            </div>
          ) : chart && (
            // Customer-level comparison: not expressible with /api/explore yet, so it stays as computed.
            <div className="mini-chart">
              <h4>{chart.title}</h4>
              <Legend series={chart.series} />
              <ChartRenderer chart={chart} height={170} />
            </div>
          )}
        </div>
        <HandledBy ids={d.handled_by} />
      </div>
    </article>
  );
}

const VERDICT = { right: ["good", "Right"], partly: ["warn", "Partly right"], wrong: ["bad", "Wrong"] };

function WhoIsRight({ rows }) {
  return (
    <section className="card table-card">
      <div style={{ padding: "16px 18px 6px" }}><h2 style={{ fontSize: 16 }}>Who is right</h2></div>
      <table className="table">
        <thead><tr><th>Executive</th><th>Claim</th><th>Verdict</th></tr></thead>
        <tbody>
          {rows.map((r) => {
            const v = VERDICT[r.verdict];
            return (
              <tr key={r.exec}>
                <td><b>{r.exec}</b></td>
                <td>{plainRules(r.claim)}</td>
                <td>
                  {v ? <><Chip tone={v[0]}>{v[1]}</Chip><div className="small" style={{ marginTop: 6 }}>{plainRules(r.evidence)}</div></> : plainRules(r.verdict)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

export default function GapPage() {
  const gap = useResource("gap", api.gap);
  const ov = useResource("overview", api.overview);
  const [sel, setSel] = useState(null);

  if (gap.error || ov.error) return <ErrorBox error={gap.error ?? ov.error} onRetry={() => { gap.reload(); ov.reload(); }} />;
  if (!gap.data || !ov.data) return <Loading what="Loading the overview" />;
  const g = gap.data;
  const o = ov.data;
  const charts = Object.fromEntries((o.charts ?? []).map((c) => [c.id, c]));
  const drivers = [...(g.drivers ?? [])].sort((a, b) => a.rank - b.rank);
  const who = g.who_is_right?.length ? g.who_is_right : o.who_is_right ?? [];
  const reco = o.recommendation ?? [];

  const selectBar = (b) => {
    setSel(b.id);
    if (b.driver_id) document.getElementById(`driver-${b.driver_id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  };
  const selBar = g.bridge.find((b) => b.id === sel);
  const selDriver = selBar?.driver_id;

  return (
    <>
      <div className="tiles">{(o.kpis ?? []).map((k) => <Tile key={k.id} {...k} />)}</div>

      <div className="gap-hero">
        <section className="card">
          <div className="chart-head">
            <div>
              <h3>From revenue growth to profit-after-refunds growth</h3>
              <p>{g.period}. Each bar is money in dollars; click one to open the driver behind it.</p>
            </div>
          </div>
          <BridgeChart bridge={g.bridge} selected={sel} onSelect={selectBar} />
          {selBar?.split && (
            <table className="table compact" style={{ marginTop: 8 }}>
              <thead><tr><th>{selBar.label}, by reason</th><th className="num">Jan-Sep 2025</th><th className="num">Jan-Sep 2026</th><th className="num">Change</th></tr></thead>
              <tbody>{selBar.split.map((s) => (
                <tr key={s.label}><td>{s.label}</td><td className="num">{money(s.y2025)}</td><td className="num">{money(s.y2026)}</td><td className="num"><b>+{money(s.change)}</b></td></tr>
              ))}</tbody>
            </table>
          )}
        </section>
        <section className="card gap-headline">
          <div className="gap-big">How it looks<b>+{num(g.headline.revenue_growth_pct)}% revenue</b>{money(g.headline.revenue_growth)} more than last year</div>
          <div className="gap-arrow" />
          <div className="gap-big">How it is<b className="is-bad">+{num(g.headline.profit_after_refunds_growth_pct)}% profit after refunds</b>once discounts, cost of goods and refunds are paid</div>
          {reco.length > 0 && (
            <>
              <div className="gap-arrow" />
              <div className="reco">
                <span className="mini-label">What we recommend</span>
                <ol>{reco.map((r, i) => <li key={i}>{plainRules(r)}</li>)}</ol>
              </div>
            </>
          )}
        </section>
      </div>

      <FilterProvider id="gap">
        <section className="block">
          <SectionHead title="What drives the gap, ranked">
            Same four answers for every driver: what happened, why it happened, what to do, and where the tool handles it.
          </SectionHead>
          <FilterBar note="Filters apply to the driver charts. The bridge and the headline numbers stay on Jan-Sep 2026 vs Jan-Sep 2025." />
          <div className="drivers">
            {drivers.map((d) => <DriverCard key={d.id} d={d} chart={charts[d.chart_id]} highlight={selDriver === d.id} />)}
          </div>
        </section>
      </FilterProvider>

      {g.why_first && (
        <section className="block card why-first">
          <h2>Which first, and why</h2>
          <p>{plainRules(g.why_first)}</p>
        </section>
      )}

      {who.length > 0 && <section className="block"><WhoIsRight rows={who} /></section>}
    </>
  );
}
