import { useEffect, useState } from "react";
import { api } from "../data/api.js";
import { useResource } from "../state.jsx";
import { humanize, money, num } from "../lib/format.js";
import { ErrorBox, Loading } from "./ui.jsx";
import { Forecaster } from "./Forecaster.jsx";

// What if = a forecast. The forecaster on top, then one compact row per rule:
// on/off, its policy slider(s) and a one-line live summary. Assumptions stay at their defaults.
const RULES = [
  ["pricing_policy", "pricing"],
  ["damage_policy", "damage"],
  ["credit_policy", "credit"],
];
// Opening settings. The page opens on the one rule we act on: the discount cap at 25% (the sweep's 0% is a
// boundary result of assuming every customer keeps buying). Damage and credit open off, as detection only:
// damage needs an operations fix (packaging, carrier), credit stays a human decision (condition C3).
const START = { pricing: { cap: 25 }, damage: { enabled: false, trigger: 15 }, credit: { allowance: 60, enabled: false } };

const signed = (v) => `${v > 0 ? "+" : v < 0 ? "-" : ""}${money(Math.abs(v ?? 0))}`;
const optionLabel = (o) => ({ prepayment: "Prepayment", full_ban: "Full ban" }[o] ?? humanize(o));

const paramsOf = (env, start) => ({
  enabled: env?.enabled !== false,
  ...Object.fromEntries((env?.controls ?? []).filter((c) => !c.read_only && c.kind !== "derived" && !c.deferred).map((c) => [c.id, c.value])),
  ...start,
});
const toQuery = (p) => ({ ...p, enabled: p.enabled ? 1 : 0 });

function Slider({ c, value, onChange, disabled, marks }) {
  const id = `rule-${c.id}`;
  const shown = c.unit === "%" ? `${value}%` : `${value} ${c.unit ?? ""}`;
  const span = (c.max - c.min) || 1;
  return (
    <div className="slider-row rule-slider">
      <label htmlFor={id}>{c.label}</label>
      <output htmlFor={id}>{shown}</output>
      <input id={id} type="range" min={c.min} max={c.max} step={c.step ?? 1} value={value ?? c.min} disabled={disabled}
        style={{ "--fill": `${(((value ?? c.min) - c.min) / span) * 100}%` }}
        aria-valuetext={shown} onChange={(e) => onChange(Number(e.target.value))} />
      {marks?.length > 0 && (
        <div className="sim-ticks" aria-hidden="true">
          {marks.map((m) => <span key={m.key} className={`sim-tick${m.on ? " is-on" : ""}`} style={{ left: `${((m.at - c.min) / span) * 100}%` }} title={m.title} />)}
        </div>
      )}
    </div>
  );
}

function Choice({ c, value, onChange, disabled }) {
  return (
    <div className="rule-choice">
      <span className="rule-choice-label">{c.label}</span>
      <div className="tabs" role="radiogroup" aria-label={c.label}>
        {c.options.map((o) => (
          <button key={o} type="button" role="radio" aria-checked={value === o} className={value === o ? "is-on" : ""} disabled={disabled} onClick={() => onChange(o)}>
            {optionLabel(o)}
          </button>
        ))}
      </div>
    </div>
  );
}

// One line, rebuilt from each response.
function summary(apiName, env, p) {
  if (!p.enabled && apiName === "damage") {
    // Detection only: name the groups the data flags, no estimate (the packaging effect would be an assumption).
    const hit = (env.details?.groups ?? []).filter((g) => g.eligible && g.damage_rate_pct > p.trigger)
      .sort((a, b) => b.damage_rate_pct - a.damage_rate_pct);
    return hit.length
      ? `Detected: ${hit.map((g) => `${g.product} in ${g.region} (${num(g.damage_rate_pct)}% damaged)`).join(", ")}. `
        + "Detection only: the fix is packaging or carrier, an operations decision. Turn on to estimate it."
      : "Detection only: no product-region group above this damage rate.";
  }
  if (!p.enabled && apiName === "credit") return "Off: unpaid invoices stay detection only (Action queue, second rule). Turn on to estimate a stricter credit policy.";
  if (!p.enabled) return "Rule off: today's policy.";
  const s = env.selected ?? {};
  const d = env.delta ?? {};
  if (apiName === "damage") {
    const eligible = (env.details?.groups ?? []).filter((g) => g.eligible).sort((a, b) => b.damage_rate_pct - a.damage_rate_pct);
    const below = eligible.find((g) => g.damage_rate_pct <= p.trigger);
    const lowestIn = eligible.filter((g) => g.damage_rate_pct > p.trigger).pop();
    const next = [below && `below ${num(below.damage_rate_pct)}%`, lowestIn && `at ${num(lowestIn.damage_rate_pct)}%`].filter(Boolean).join(" or ");
    return `Trigger ${p.trigger}%: ${num(s.targeted_groups)} product-region groups get reinforced packaging, net benefit ${signed(d.net_benefit ?? s.net_benefit)}.${next ? ` Next change ${next}.` : ""}`;
  }
  if (apiName === "pricing") {
    const be = env.details?.break_even_retention;
    return `Cap ${p.cap}%: ${num(s.affected_orders)} orders above the cap, gross profit ${signed(d.gross_profit)} if every customer keeps the order`
      + (be?.gross_profit_whole != null ? `; it still holds if at least ${be.gross_profit_whole}% do.` : ".");
  }
  if (apiName === "credit") {
    return `${p.allowance} ${p.allowance === 1 ? "day" : "days"} overdue, then ${optionLabel(p.action).toLowerCase()} on a second offense: `
      + `${num(s.restricted_accounts)} accounts restricted, overdue exposure ${signed(d.overdue_exposure)}`
      + (s.forgone_revenue ? `, ${money(s.forgone_revenue)} of sales lost.` : ", no sales lost.");
  }
  return "";
}

function RuleRow({ initial, apiName, start, onParams }) {
  const [env, setEnv] = useState(initial);
  const [params, setParams] = useState(() => paramsOf(initial, start));
  const [state, setState] = useState({ loading: false, error: null });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => { onParams(params); }, [params]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    let live = true;
    setState({ loading: true, error: null });
    const t = setTimeout(() => {
      api.simModule(apiName, toQuery(params))
        .then((e) => { if (live) { setEnv(e); setState({ loading: false, error: null }); } })
        .catch((error) => live && setState({ loading: false, error }));
    }, 120);
    return () => { live = false; clearTimeout(t); };
  }, [JSON.stringify(params), attempt]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = (id, v) => setParams((p) => ({ ...p, [id]: v }));
  const policy = (env.controls ?? []).filter((c) => c.kind === "policy" && !c.read_only && !c.deferred);
  const marks = apiName === "damage"
    ? (env.details?.groups ?? []).filter((g) => g.eligible).map((g) => ({
      key: `${g.product}|${g.region}`, at: g.damage_rate_pct, on: g.damage_rate_pct > params.trigger,
      title: `${g.product} in ${g.region}: ${num(g.damage_rate_pct)}% damaged (${g.orders} orders)`,
    }))
    : null;

  return (
    <div className={`rule-row${params.enabled ? "" : " is-off"}${state.loading ? " is-loading" : ""}`}>
      <label className="switch rule-name">
        <input type="checkbox" checked={params.enabled} onChange={(e) => set("enabled", e.target.checked)} />
        <span>{env.label}</span>
      </label>
      <div className="rule-controls">
        {policy.map((c) => (c.options
          ? <Choice key={c.id} c={c} value={params[c.id]} onChange={(v) => set(c.id, v)} disabled={!params.enabled} />
          : <Slider key={c.id} c={c} value={params[c.id]} onChange={(v) => set(c.id, v)} disabled={!params.enabled} marks={c.id === "trigger" ? marks : null} />))}
      </div>
      <p className="rule-summary" aria-live="polite">{summary(apiName, env, params)}</p>
      {state.error && <ErrorBox error={state.error} onRetry={() => setAttempt((n) => n + 1)} />}
    </div>
  );
}

export function PolicySimulator() {
  const sim = useResource("simulator", api.simulator);
  const [params, setParams] = useState({});

  if (sim.error) return <ErrorBox error={sim.error} onRetry={sim.reload} />;
  if (!sim.data) return <Loading what="Loading the rules" />;
  const mods = sim.data.modules ?? {};
  const present = RULES.filter(([id]) => mods[id] && Object.keys(mods[id]).length);
  const ready = present.every(([id]) => params[id]); // wait for every rule's opening settings

  return (
    <>
      {ready ? <Forecaster params={params} /> : <Loading what="Projecting" />}
      <section className="card rules-panel" aria-label="The rules">
        <header className="rules-head">
          <h3>The rules</h3>
          <p className="muted small">Turn a rule on or off, or move its setting: the forecast above follows.</p>
        </header>
        {present.map(([id, name]) => (
          <RuleRow key={id} initial={mods[id]} apiName={name} start={START[name]}
            onParams={(p) => setParams((s) => ({ ...s, [id]: p }))} />
        ))}
      </section>
    </>
  );
}
