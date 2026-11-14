import { api } from "../data/api.js";
import { useResource } from "../state.jsx";
import { money, num } from "../lib/format.js";
import { ErrorBox, Loading, SectionHead } from "../components/ui.jsx";

// Plain-words "saw" and "assumed" per step. Counts and money come from /api/data-prep (api/pipeline.py).
const KIND = {
  drop: ["bad", "Deleted"],
  set_aside: ["warn", "Set aside"],
  fix: ["accent", "Fixed"],
  kept: ["info", "Left as is"],
  check: ["good", "Checked"],
};

const NOTES = {
  dedupe: {
    saw: "25 rows identical to another row in every column.",
    assumed: "Same order exported twice. Copy deleted.",
  },
  discount_pct: {
    title: "Discounts in two different units",
    saw: "Most discounts are fractions (0.12). 181 are percents (12), which made their revenue negative.",
    assumed: "Any discount above 1 is a percent, divided by 100.",
  },
  neg_qty: {
    title: "Negative quantities (negative revenue and cost)",
    saw: "8 rows with a quantity below zero, a payment date and no matching return.",
    assumed: "Can't tell a typo from a return, so moved to a review list instead of guessing.",
  },
  region: {
    saw: "15 spellings for 5 regions (ON, QC, B.C., ATL...).",
    assumed: "Each spelling maps to the region it names.",
  },
  product: {
    saw: "22 names for 10 products (Mech Keyboard, 24in Monitor...).",
    assumed: "Names differing only in case, spacing or abbreviation are the same product.",
  },
  date_format: {
    saw: "122 dates in MM/DD/YYYY, the rest YYYY-MM-DD.",
    assumed: "Month first. Day first would put orders after the data ends.",
  },
  cost_blank: {
    title: "Missing unit costs",
    saw: "92 rows with no unit cost.",
    assumed: "Unknown, not zero or average. Margins use known-cost rows only.",
  },
  unpaid_kept: {
    title: "Missing payment dates",
    saw: "92 business orders (Net 30 / Net 60) with no payment date.",
    assumed: "Unpaid at extraction (2026-10-31). Kept as open balances.",
  },
  join_check: {
    saw: "Orders vs customers, returns vs orders, order vs customer region.",
    assumed: "Nothing to fix if all match.",
  },
};

const pct = (v) => (v == null ? "n/a" : `${num(v)}%`);
const signed = (v) => (Math.abs(v) < 0.5 ? "no change" : `${v > 0 ? "+" : "-"}${money(Math.abs(v), { compact: true })}`);

function Compare({ s }) {
  const rows = [
    ["Order rows", num(s.raw.orders), num(s.clean.orders), `${num(s.clean.orders - s.raw.orders)} rows`],
    ["Revenue", money(s.raw.revenue), money(s.clean.revenue), signed(s.clean.revenue - s.raw.revenue)],
    ["Gross profit (known cost)", money(s.raw.gross_profit), money(s.clean.gross_profit), signed(s.clean.gross_profit - s.raw.gross_profit)],
    ["Margin", pct(s.raw.margin_pct), pct(s.clean.margin_pct), `${s.clean.margin_pct >= s.raw.margin_pct ? "+" : ""}${num(Math.round((s.clean.margin_pct - s.raw.margin_pct) * 10) / 10)} pts`],
  ];
  return (
    <div className="card table-card">
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th /><th className="num">Raw</th><th className="num">Clean</th><th className="num">Change</th></tr></thead>
          <tbody>
            {rows.map(([k, a, b, d]) => (
              <tr key={k}><td>{k}</td><td className="num mono">{a}</td><td className="num mono"><b>{b}</b></td><td className="num mono muted">{d}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StepCard({ step }) {
  const n = NOTES[step.id] ?? {};
  const [tone, label] = KIND[step.kind] ?? ["neutral", step.kind];
  const dRev = step.revenue_after - step.revenue_before;
  const dGp = step.gross_profit_after - step.gross_profit_before;
  return (
    <article className={`card dc-card tone-${tone}`}>
      <div className="dc-head">
        <span className={`chip chip-${tone}`}>{label}</span>
        <span className="muted small">{step.rows_affected ? `${num(step.rows_affected)} rows` : "0 rows"}{step.column ? <> · <span className="mono">{step.column}</span></> : null}</span>
      </div>
      <h3>{n.title ?? step.title}</h3>
      <dl className="dc-list">
        <dt>What we saw</dt><dd>{n.saw ?? step.why}</dd>
        <dt>What we assumed</dt><dd>{n.assumed ?? step.title}</dd>
        <dt>Effect on the clean data</dt>
        <dd>
          {step.effect}.
          {(Math.abs(dRev) >= 0.5 || Math.abs(dGp) >= 0.5) && (
            <span className="dc-delta"> Revenue {signed(dRev)}, gross profit {signed(dGp)}.</span>
          )}
        </dd>
      </dl>
    </article>
  );
}

const GROUPS = [
  ["Deleted or set aside", ["drop", "set_aside"], "Rows that are in the raw file but not in the clean sales view."],
  ["Fixed in place", ["fix"], "Same rows, corrected values. changes.csv lists every changed cell with its raw line."],
  ["Left as is, on purpose", ["kept", "check"], "Blanks we did not fill, and checks that needed no fix."],
];

export default function CleaningPage() {
  const { data, error, reload } = useResource("data-prep", api.dataPrep);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loading what="Loading the cleaning steps" />;
  const s = data.summary;
  return (
    <>
      <section className="block">
        <SectionHead title="Raw vs clean">
          {`${num(s.rows_removed)} rows deleted, ${num(s.rows_set_aside)} set aside, ${num(s.rows_fixed)} rows fixed (${num(s.cells_changed)} cells). The raw files are never modified.`}
        </SectionHead>
        <Compare s={s} />
      </section>

      {GROUPS.map(([title, kinds, lead]) => {
        const steps = data.steps.filter((st) => kinds.includes(st.kind));
        if (!steps.length) return null;
        return (
          <section className="block" key={title}>
            <SectionHead title={title}>{lead}</SectionHead>
            <div className="dc-grid">{steps.map((st) => <StepCard key={st.id} step={st} />)}</div>
          </section>
        );
      })}
    </>
  );
}
