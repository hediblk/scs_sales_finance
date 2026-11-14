import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../data/api.js";
import { useApp, useResource } from "../state.jsx";
import { humanize, money, num } from "../lib/format.js";
import { Chip, ErrorBox, Loading } from "./ui.jsx";

// Module order on the page (damage first, as built), the API path, and the tab label.
export const SIM_MODULES = [
  ["damage_policy", "damage", "Damage"],
  ["pricing_policy", "pricing", "Pricing"],
  ["credit_policy", "credit", "Credit"],
];

// How to read each metric: label, unit, and which direction is good (for the change colour).
const METRICS = {
  revenue: ["Revenue", "$", 1],
  gross_profit: ["Gross profit (known-cost orders)", "$", 1],
  weighted_margin_pct: ["Weighted gross margin", "%", 1],
  refunds: ["Refunds", "$", -1],
  net_revenue_after_refunds: ["Net revenue after refunds", "$", 1],
  affected_orders: ["Orders above the cap", "n", 0],
  expected_retained_orders: ["Expected retained orders", "n", 0],
  expected_retained_units: ["Expected retained units", "n", 0],
  affected_unknown_cost_orders: ["Affected orders with unknown cost", "n", 0],
  intervention_cost: ["Packaging and inspection cost", "$", -1],
  avoided_damage_refunds: ["Avoided damage refunds", "$", 1],
  net_benefit: ["Net benefit (avoided refunds minus intervention cost)", "$", 1],
  contribution: ["Contribution (gross profit minus refunds and intervention cost)", "$", 1],
  contribution_margin_pct: ["Contribution margin", "%", 1],
  targeted_groups: ["Targeted product x region groups", "n", 0],
  targeted_orders: ["Targeted orders", "n", 0],
  targeted_units: ["Targeted units", "n", 0],
  overdue_invoices: ["Overdue invoices", "n", -1],
  overdue_exposure: ["Overdue exposure at Oct 31, 2026", "$", -1],
  open_exposure: ["Open exposure at Oct 31, 2026", "$", -1],
  over_90_exposure: ["Exposure over 90 days", "$", -1],
  over_90_invoices: ["Invoices over 90 days", "n", -1],
  accounts_overdue: ["Accounts overdue", "n", -1],
  restricted_accounts: ["Restricted accounts", "n", 0],
  restricted_orders: ["Orders placed under restriction", "n", 0],
  prepaid_revenue: ["Revenue paid in advance", "$", 0],
  forgone_revenue: ["Revenue lost to the restriction", "$", -1],
  flagged_accounts: ["Flagged accounts", "n", 0],
  flagged_invoices: ["Flagged invoices", "n", 0],
  flagged_exposure: ["Flagged exposure", "$", 0],
  second_offense_accounts: ["Second-offense accounts", "n", 0],
  flagged_within_credit_limit: ["Flagged but within credit limit", "n", 0],
};
const MONEY_KEY = /(revenue|profit|refund|cost|exposure|contribution|amount|balance|benefit)/i;
const meta = (k) => METRICS[k] ?? [humanize(k), k.endsWith("_pct") ? "%" : MONEY_KEY.test(k) && !k.endsWith("_orders") ? "$" : "n", 0];

function value(v, unit) {
  if (v == null) return "n/a";
  if (typeof v !== "number") return String(v);
  if (unit === "$") return money(v);
  if (unit === "%") return `${num(v)}%`;
  return num(v);
}
function deltaText(v, unit) {
  if (v == null || typeof v !== "number") return "";
  const sign = v > 0 ? "+" : v < 0 ? "-" : "";
  if (unit === "$") return `${sign}${money(Math.abs(v))}`;
  if (unit === "%") return `${sign}${num(Math.abs(v))} pts`;
  return `${sign}${num(Math.abs(v))}`;
}
const signed$ = (v) => deltaText(v ?? 0, "$") || "$0";
const toneOf = (v, dir) => (!v || !dir ? "" : v * dir > 0 ? "delta-down" : "delta-up"); // delta-down = good (green)
const optionLabel = (o) => ({ prepayment: "Prepayment", full_ban: "Full ban" }[o] ?? humanize(o));

// Current settings of a module, from its envelope: on/off plus every editable control.
const paramsOf = (env) => ({
  enabled: env?.enabled !== false,
  ...Object.fromEntries((env?.controls ?? []).filter((c) => !c.read_only && c.kind !== "derived" && !c.deferred).map((c) => [c.id, c.value])),
});
const toQuery = (p) => ({ ...p, enabled: p.enabled ? 1 : 0 });

/* ---------- Where a stepwise slider changes ---------- */

// Damage: the trigger only matters at the damage rates of eligible groups (>= 30 orders).
function damageSteps(env, trigger) {
  const eligible = (env.details?.groups ?? []).filter((g) => g.eligible).sort((a, b) => b.damage_rate_pct - a.damage_rate_pct);
  const targeted = eligible.filter((g) => g.damage_rate_pct > trigger);
  const below = eligible.find((g) => g.damage_rate_pct <= trigger); // next to join when the trigger goes under its rate
  const lowestIn = targeted[targeted.length - 1]; // first to leave when the trigger reaches its rate
  return { eligible, targeted, below, lowestIn };
}

// Credit: read the batch sweep (one row per allowance x action) and find where the outcome changes.
function sweepSteps(rows, action, g) {
  const own = (rows ?? []).filter((r) => r.action === action && r.allowance != null).sort((a, b) => a.allowance - b.allowance);
  const sig = (r) => [r.restricted_accounts, Math.round(r.overdue_exposure ?? 0), Math.round(r.revenue ?? 0)].join("|");
  const cur = own.find((r) => r.allowance === g);
  if (!cur) return null;
  const s = sig(cur);
  const lower = [...own].reverse().find((r) => r.allowance < g && sig(r) !== s);
  const higher = own.find((r) => r.allowance > g && sig(r) !== s);
  return { lower: lower?.allowance, higher: higher?.allowance };
}

/* ---------- Generic pieces ---------- */

function Control({ c, value: v, onChange, disabled, marks, hint }) {
  const id = `sim-${c.id}`;
  if (c.read_only || c.kind === "derived" || c.deferred) {
    return (
      <div className="sim-ctl is-static">
        <span className="sim-ctl-label">{c.label}</span>
        <span className="sim-ctl-val">{c.deferred ? "Not modeled yet" : `${c.value}${c.unit === "%" ? "%" : c.unit ? ` ${c.unit}` : ""}`}</span>
      </div>
    );
  }
  if (c.options) {
    return (
      <div className="sim-ctl sim-choice">
        <span className="sim-ctl-label">{c.label}</span>
        <div className="tabs" role="radiogroup" aria-label={c.label}>
          {c.options.map((o) => (
            <button key={o} type="button" role="radio" aria-checked={v === o} className={v === o ? "is-on" : ""} disabled={disabled} onClick={() => onChange(o)}>
              {optionLabel(o)}{c.recommended === o ? " (recommended)" : ""}
            </button>
          ))}
        </div>
      </div>
    );
  }
  const shown = c.unit === "%" ? `${v}%` : c.unit === "CAD" || c.unit === "$" ? money(v) : `${v} ${c.unit ?? ""}`;
  const span = (c.max - c.min) || 1;
  return (
    <div className="slider-row sim-ctl">
      <label htmlFor={id}>{c.label}</label>
      <output htmlFor={id}>{shown}</output>
      <input id={id} type="range" min={c.min} max={c.max} step={c.step ?? 1} value={v ?? c.min} disabled={disabled}
        aria-valuetext={shown} onChange={(e) => onChange(Number(e.target.value))} />
      {marks?.length > 0 && (
        <div className="sim-ticks" aria-hidden="true">
          {marks.map((m) => (
            <span key={m.key} className={`sim-tick${m.on ? " is-on" : ""}`} style={{ left: `${((m.at - c.min) / span) * 100}%` }} title={m.title} />
          ))}
        </div>
      )}
      {hint && <span className="sim-hint">{hint}</span>}
      {c.recommended != null && (
        <span className="sim-rec">Recommended: {c.unit === "%" ? `${c.recommended}%` : c.unit === "CAD" || c.unit === "$" ? money(c.recommended) : `${c.recommended} ${c.unit ?? ""}`}{c.provisional ? " (provisional)" : ""}</span>
      )}
    </div>
  );
}

function MetricsTable({ env }) {
  const keys = Object.keys(env.baseline ?? env.selected ?? {});
  const hasDelta = env.delta && Object.keys(env.delta).length > 0;
  return (
    <div className="table-wrap">
      <table className="table sim-metrics">
        <thead>
          <tr><th>{env.period}</th><th className="num">Baseline</th><th className="num">Scenario</th>{hasDelta && <th className="num">Change</th>}</tr>
        </thead>
        <tbody>
          {keys.map((k) => {
            const [label, unit, dir] = meta(k);
            const d = env.delta?.[k];
            return (
              <tr key={k} className={d ? "is-moved" : ""}>
                <td>{label}</td>
                <td className="num">{value(env.baseline?.[k], unit)}</td>
                <td className="num">{value(env.selected?.[k], unit)}</td>
                {hasDelta && <td className={`num ${toneOf(d, dir)}`}>{deltaText(d, unit)}</td>}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// A plain table for list-shaped details (rep drill-down, accounts).
function DetailTable({ rows, limit = 15 }) {
  const [all, setAll] = useState(false);
  if (!rows?.length) return <p className="muted small">None at these settings.</p>;
  const cols = Object.keys(rows[0]);
  const cell = (k, v) => (Array.isArray(v) ? (v.length && typeof v[0] !== "object" ? v.join(", ") : `${v.length}`)
    : typeof v === "number" ? (k.endsWith("_pct") ? `${num(v)}%` : MONEY_KEY.test(k) && !k.endsWith("_orders") ? money(v) : num(v))
    : typeof v === "boolean" ? (v ? "Yes" : "No") : v == null ? "" : String(v));
  return (
    <>
      <div className="table-wrap" style={{ maxHeight: 360, overflowY: "auto" }}>
        <table className="table compact">
          <thead><tr>{cols.map((c) => <th key={c}>{humanize(c)}</th>)}</tr></thead>
          <tbody>{(all ? rows : rows.slice(0, limit)).map((r, i) => (
            <tr key={i}>{cols.map((c) => <td key={c} className={typeof r[c] === "number" ? "num" : ""}>{cell(c, r[c])}</td>)}</tr>
          ))}</tbody>
        </table>
      </div>
      {rows.length > limit && <button type="button" className="link-btn small" onClick={() => setAll((x) => !x)}>{all ? "Show fewer" : `Show all ${rows.length}`}</button>}
    </>
  );
}

/* ---------- Module-specific evidence ---------- */

function DamageGroups({ groups }) {
  const rows = useMemo(() => [...(groups ?? [])].sort((a, b) => (b.targeted - a.targeted) || (b.damage_rate_pct - a.damage_rate_pct)), [groups]);
  const [all, setAll] = useState(false);
  if (!rows.length) return null;
  return (
    <div className="sim-evidence">
      <h4>Damage rate by product and region, with denominators</h4>
      <div className="table-wrap" style={{ maxHeight: 380, overflowY: "auto" }}>
        <table className="table compact">
          <thead><tr><th>Product</th><th>Region</th><th className="num">Orders</th><th className="num">Damaged</th><th className="num">Rate</th><th className="num">Damage refunds</th><th className="num">Units</th><th>Status</th></tr></thead>
          <tbody>
            {(all ? rows : rows.slice(0, 15)).map((g) => (
              <tr key={`${g.product}|${g.region}`} className={g.targeted ? "has-fix" : ""}>
                <td>{g.product}</td><td>{g.region}</td>
                <td className="num">{num(g.orders)}</td><td className="num">{num(g.damage_orders)}</td>
                <td className="num"><b>{num(g.damage_rate_pct)}%</b></td>
                <td className="num">{money(g.damage_refunds)}</td><td className="num">{num(g.units)}</td>
                <td>{g.targeted ? <Chip tone="accent">Targeted</Chip> : g.eligible ? <span className="muted small">Below trigger</span> : <span className="muted small">Under 30 orders</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > 15 && <button type="button" className="link-btn small" onClick={() => setAll((x) => !x)}>{all ? "Show fewer" : `Show all ${rows.length} groups`}</button>}
    </div>
  );
}

function BreakEven({ be }) {
  if (be === undefined) return null;
  const line = (key, label) => {
    const whole = be?.[`${key}_whole`];
    return whole == null
      ? <li>No retention level keeps {label} at or above the baseline at this cap.</li>
      : <li>{label.charAt(0).toUpperCase() + label.slice(1)} holds if at least <b>{whole}%</b> of the affected orders are kept ({num(be[key])}% exactly).</li>;
  };
  return (
    <div className="sim-breakeven">
      <h4>Break-even retention at this cap</h4>
      <ul>{line("gross_profit", "gross profit")}{line("revenue", "revenue")}</ul>
    </div>
  );
}

/* ---------- Live summary sentence (changes on every response) ---------- */

function Summary({ apiName, env, params, steps }) {
  const s = env.selected ?? {};
  const d = env.delta ?? {};
  if (!params.enabled) return <p className="sim-summary">Rule off: the scenario equals the baseline.</p>;
  let text;
  if (apiName === "damage") {
    const names = steps?.targeted.map((g) => `${g.product} in ${g.region} (${num(g.damage_rate_pct)}%)`) ?? [];
    text = `Trigger ${params.trigger}%: ${num(s.targeted_groups)} product-region groups, ${num(s.targeted_units)} units targeted. `
      + `Refunds ${signed$(d.refunds)}, intervention cost ${money(s.intervention_cost ?? 0)}, net benefit ${signed$(d.net_benefit ?? s.net_benefit)}.`;
    return (
      <div className="sim-summary" aria-live="polite">
        <p>{text}</p>
        {names.length > 0 && <p className="sim-summary-sub">Targets {names.length} {names.length === 1 ? "group" : "groups"}: {names.join(", ")}.</p>}
      </div>
    );
  }
  if (apiName === "pricing") {
    const be = env.details?.break_even_retention;
    text = `Cap ${params.cap}% at ${params.retention}% retention: ${num(s.affected_orders)} orders above the cap. `
      + `Gross profit ${signed$(d.gross_profit)}, revenue ${signed$(d.revenue)}, margin ${deltaText(d.weighted_margin_pct, "%") || "0 pts"}. `
      + (be ? `Break-even retention: ${be.gross_profit_whole != null ? `${be.gross_profit_whole}% for gross profit` : "none for gross profit"}, ${be.revenue_whole != null ? `${be.revenue_whole}% for revenue` : "none for revenue"}.` : "");
  } else if (apiName === "credit") {
    text = `Allowance ${params.allowance} ${params.allowance === 1 ? "day" : "days"}, ${optionLabel(params.action).toLowerCase()} on a second offense: ${num(s.restricted_accounts)} accounts restricted. `
      + `Overdue exposure ${signed$(d.overdue_exposure)}, revenue ${signed$(d.revenue)}${s.forgone_revenue ? `, ${money(s.forgone_revenue)} of sales lost` : ""}.`;
  }
  return <p className="sim-summary" aria-live="polite">{text}</p>;
}

/* ---------- One module ---------- */

function ModulePanel({ initial, apiName, hidden, onParams, onEnv }) {
  const [env, setEnv] = useState(initial);
  const [params, setParams] = useState(() => paramsOf(initial));
  const [period, setPeriod] = useState("2026");
  const [state, setState] = useState({ loading: false, error: null });
  const [attempt, setAttempt] = useState(0);
  const first = useRef(true);
  const reset = useRef(false);
  const sweep = useResource(`sim-sweep-${apiName}`, () => (apiName === "credit" ? api.simSweep("credit") : Promise.resolve(null)));

  useEffect(() => { onParams(params); }, [params]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { onEnv(env); }, [env]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (first.current) { first.current = false; return; }
    let live = true;
    setState({ loading: true, error: null });
    const isReset = reset.current;
    reset.current = false;
    const t = setTimeout(() => {
      const query = isReset ? (apiName === "damage" && period !== "2026" ? { period } : {}) : { ...toQuery(params), ...(apiName === "damage" ? { period } : {}) };
      api.simModule(apiName, query)
        .then((e) => {
          if (!live) return;
          setEnv(e);
          if (isReset) setParams(paramsOf(e));
          setState({ loading: false, error: null });
        })
        .catch((error) => live && setState({ loading: false, error }));
    }, 120);
    return () => { live = false; clearTimeout(t); };
  }, [JSON.stringify(params), period, attempt]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = (id, v) => setParams((p) => ({ ...p, [id]: v }));
  const doReset = () => { reset.current = true; setAttempt((n) => n + 1); };
  const rec = env.recommended;
  const controls = env.controls ?? [];
  const policy = controls.filter((c) => c.kind === "policy");
  const assumptions = controls.filter((c) => c.kind !== "policy");
  const recParams = rec?.parameters ?? {};
  const atRecommended = params.enabled && Object.keys(recParams).filter((k) => k in params).every((k) => params[k] === recParams[k]);

  // Stepwise sliders: marks and "next change" hints.
  const dSteps = apiName === "damage" ? damageSteps(env, params.trigger) : null;
  const cSteps = apiName === "credit" && sweep.data ? sweepSteps(sweep.data.rows, params.action, params.allowance) : null;
  const marksFor = (c) => (apiName === "damage" && c.id === "trigger"
    ? dSteps.eligible.map((g) => ({ key: `${g.product}|${g.region}`, at: g.damage_rate_pct, on: g.damage_rate_pct > params.trigger, title: `${g.product} in ${g.region}: ${num(g.damage_rate_pct)}% damaged (${g.orders} orders)` }))
    : null);
  const hintFor = (c) => {
    if (apiName === "damage" && c.id === "trigger" && dSteps) {
      const parts = [];
      if (dSteps.below) parts.push(`below ${num(dSteps.below.damage_rate_pct)}% (adds ${dSteps.below.product} in ${dSteps.below.region})`);
      if (dSteps.lowestIn) parts.push(`at ${num(dSteps.lowestIn.damage_rate_pct)}% (drops ${dSteps.lowestIn.product} in ${dSteps.lowestIn.region})`);
      return parts.length ? `Next change ${parts.join(" or ")}.` : null;
    }
    if (apiName === "credit" && c.id === "allowance" && cSteps) {
      const from = cSteps.lower != null ? cSteps.lower + 1 : c.min;
      const to = cSteps.higher != null ? cSteps.higher - 1 : c.max;
      const next = [cSteps.lower, cSteps.higher].filter((x) => x != null).map((x) => `${x}`).join(" or ");
      return from === to && !next ? null : `Same outcome from ${from} to ${to} days.${next ? ` Next change at ${next} days.` : ""}`;
    }
    return null;
  };
  const isDisabled = (c) => !params.enabled || (c.disabled_when && params.action === c.disabled_when);

  return (
    <section className={`card sim-module${state.loading ? " is-loading" : ""}`} hidden={hidden} aria-label={env.label}>
      <header className="sim-head">
        <div>
          <h3>{env.label}</h3>
          <p className="muted small">{env.scope} · {env.period}</p>
        </div>
        <div className="sim-head-right">
          {env.status === "detection_only" && <Chip tone="warn">Detection only, no replay yet</Chip>}
          <label className="switch">
            <input type="checkbox" checked={params.enabled} onChange={(e) => set("enabled", e.target.checked)} />
            <span>{params.enabled ? "Rule on" : "Rule off (baseline)"}</span>
          </label>
        </div>
      </header>

      <Summary apiName={apiName} env={env} params={params} steps={dSteps} />

      <div className="sim-grid">
        <div className="sim-controls">
          {policy.length > 0 && <span className="mini-label">Policy settings</span>}
          {policy.map((c) => <Control key={c.id} c={c} value={params[c.id]} onChange={(v) => set(c.id, v)} disabled={isDisabled(c)} marks={marksFor(c)} hint={hintFor(c)} />)}
          {assumptions.length > 0 && <span className="mini-label" style={{ marginTop: 10 }}>Assumptions (for sensitivity, never optimized)</span>}
          {assumptions.map((c) => <Control key={c.id} c={c} value={params[c.id]} onChange={(v) => set(c.id, v)} disabled={isDisabled(c)} />)}
          {apiName === "damage" && (
            <label className="select sim-period"><span className="mini-label">Period</span>
              <select value={period} onChange={(e) => setPeriod(e.target.value)}>
                <option value="2026">Scenario: Jan-Sep 2026</option>
                <option value="full">Evidence view: Jan 2025 to Sep 2026</option>
              </select>
            </label>
          )}
        </div>
        <div className="sim-best">
          <span className="mini-label">{rec?.label ?? "Best modeled setting at the starting assumptions"}</span>
          {Object.keys(recParams).length > 0 && (
            <p className="sim-best-params">{Object.entries(recParams).map(([k, v]) => {
              const c = controls.find((x) => x.id === k);
              return <span key={k}>{c?.label ?? humanize(k)}: <b>{c?.options ? optionLabel(v) : c?.unit === "%" ? `${v}%` : c?.unit === "CAD" || c?.unit === "$" ? money(v) : `${v}${c?.unit ? ` ${c.unit}` : ""}`}</b></span>;
            })}</p>
          )}
          {rec?.selection_reason && <p className="small">{rec.selection_reason}</p>}
          <div className="sim-best-state">
            <span className={`chip ${atRecommended ? "chip-good" : "chip-warn"}`}>{atRecommended ? "Showing the recommended setting" : "Custom setting"}</span>
            <button type="button" className="btn btn-quiet btn-sm" onClick={doReset} disabled={atRecommended}>Reset to recommended</button>
          </div>
        </div>
      </div>

      {state.error && <ErrorBox error={state.error} onRetry={() => setAttempt((n) => n + 1)} />}
      <MetricsTable env={env} />
      {env.coverage && (
        <p className="muted small" style={{ margin: "6px 0 0" }}>
          Cost known for {num(env.coverage.known_cost_orders)} of {num(env.coverage.orders)} orders ({num(env.coverage.known_cost_pct)}%). Unknown costs stay unknown.
        </p>
      )}

      {apiName === "pricing" && <BreakEven be={env.details?.break_even_retention} />}
      {apiName === "pricing" && env.details?.by_rep && <div className="sim-evidence"><h4>Affected orders by rep</h4><DetailTable rows={env.details.by_rep} /></div>}
      {apiName === "damage" && <DamageGroups groups={env.details?.groups} />}
      {apiName === "credit" && (env.details?.replay_accounts ?? env.details?.accounts) && (
        <div className="sim-evidence"><h4>Accounts in the replay</h4><DetailTable rows={env.details.replay_accounts ?? env.details.accounts} /></div>
      )}

      {(env.assumptions?.length > 0 || env.notes?.length > 0) && (
        <ul className="sim-notes">{[...(env.assumptions ?? []), ...(env.notes ?? [])].map((a) => <li key={a}>{a}</li>)}</ul>
      )}
    </section>
  );
}

/* ---------- The simulator ---------- */

// tab: one of the module ids, or "replay" (the quarter-end replay, rendered by the page).
export function PolicySimulator({ tab, setTab, onHeader }) {
  const { go } = useApp();
  const sim = useResource("simulator", api.simulator);
  const [params, setParams] = useState({});
  const [envs, setEnvs] = useState({});
  const [applying, setApplying] = useState(false);
  const [applied, setApplied] = useState(null);
  const [applyError, setApplyError] = useState(null);

  const mods = sim.data?.modules ?? {};
  const present = SIM_MODULES.filter(([id]) => mods[id] && Object.keys(mods[id]).length);

  // The page title and lead follow the active tab, from the module's own label, scope and period.
  const active = envs[tab] ?? mods[tab];
  useEffect(() => {
    if (tab === "replay" || !active) return;
    onHeader({
      title: `What if: ${active.label}`,
      lead: `${active.scope}, ${active.period}. Every number below is recomputed by the back end each time a setting moves.`,
    });
  }, [tab, active?.label, active?.scope, active?.period]); // eslint-disable-line react-hooks/exhaustive-deps

  const apply = async () => {
    setApplying(true); setApplyError(null);
    try {
      const body = {};
      for (const [id, name] of present) if (params[id]) body[name] = params[id];
      setApplied(await api.simApply(body));
    } catch (e) { setApplyError(e); } finally { setApplying(false); }
  };

  const tabs = (
    <div className="tabs" role="tablist" aria-label="What if">
      {present.map(([id, , label]) => (
        <button key={id} type="button" role="tab" aria-selected={tab === id} className={tab === id ? "is-on" : ""} onClick={() => setTab(id)}>
          {label}{params[id]?.enabled === false ? " (off)" : ""}
        </button>
      ))}
      <button type="button" role="tab" aria-selected={tab === "replay"} className={tab === "replay" ? "is-on" : ""} onClick={() => setTab("replay")}>
        Quarter-end replay
      </button>
    </div>
  );

  if (sim.error) return <>{tabs}<ErrorBox error={sim.error} onRetry={sim.reload} /></>;
  if (!sim.data) return <Loading what="Loading the policy simulator" />;

  return (
    <section className="block">
      <div className="sim-top">
        {tabs}
        {tab !== "replay" && (
          <div className="sim-apply">
            <button type="button" className="btn" onClick={apply} disabled={applying}>{applying ? "Applying..." : "Apply rules to simulation"}</button>
            <span className="muted small">Creates tasks in the Action queue for the rules that are on, at these settings.</span>
          </div>
        )}
      </div>
      {tab !== "replay" && applyError && <ErrorBox error={applyError} onRetry={apply} />}
      {tab !== "replay" && applied && (
        <div className="sim-applied">
          <b>{num(applied.created)}</b> tasks created, <b>{num(applied.updated)}</b> updated, <b>{num(applied.unchanged)}</b> unchanged.
          {" "}<button type="button" className="link-btn" onClick={() => go("queue", { view: "tasks" })}>Open them in the Action queue</button>
        </div>
      )}
      {present.map(([id, name]) => (
        <ModulePanel key={id} initial={mods[id]} apiName={name} hidden={tab !== id}
          onParams={(p) => setParams((s) => ({ ...s, [id]: p }))}
          onEnv={(e) => setEnvs((s) => ({ ...s, [id]: e }))} />
      ))}
      {tab !== "replay" && sim.data.assumptions?.length > 0 && (
        <details className="sim-global">
          <summary>Scope and shared assumptions ({sim.data.model_version})</summary>
          <ul>{sim.data.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
        </details>
      )}
    </section>
  );
}
