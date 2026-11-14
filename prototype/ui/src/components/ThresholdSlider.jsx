import { useEffect, useState } from "react";
import { api } from "../data/api.js";
import { useApp } from "../state.jsx";
import { fmt, money, num } from "../lib/format.js";
import { Chip } from "./ui.jsx";

// What one hit is called, per condition id (docs/ui-contract.md). Unknown ids use the entity label.
const NOUN = { qe_discount: ["order", "orders"], quiet_after_bad_return: ["bad return", "bad returns"] };
export const nounFor = (cid, labels, n) => {
  const pair = NOUN[cid] ?? [labels.entity.toLowerCase(), labels.entities];
  return n === 1 ? pair[0] : pair[1];
};

// Live back-test for one condition at one threshold (and window). Debounced for slider drags.
export function useSimulate(conditionId, value, window) {
  const [sim, setSim] = useState(null);
  useEffect(() => {
    if (value == null) return;
    let live = true;
    const t = setTimeout(() => {
      api.simulate(conditionId, value, window ?? undefined).then((r) => live && setSim(r)).catch(() => live && setSim(null));
    }, 120);
    return () => { live = false; clearTimeout(t); };
  }, [conditionId, value, window]);
  return sim;
}

function RuleText({ text, value, window }) {
  const parts = text.split(/(\{value\}|\{window\})/);
  return (
    <p className="rule-text">
      {parts.map((p, i) => (p === "{value}" ? <mark key={i}>{value}</mark> : p === "{window}" ? <mark key={i}>{window}</mark> : <span key={i}>{p}</span>))}
    </p>
  );
}

function Slider({ id, spec, value, onChange }) {
  return (
    <div className="slider-row">
      <label htmlFor={id}>{spec.label}</label>
      <output htmlFor={id}>{fmt(value, spec.unit)}</output>
      <input id={id} type="range" min={spec.min} max={spec.max} step={spec.step} value={value}
        onChange={(e) => onChange(Number(e.target.value))} />
    </div>
  );
}

// One condition: rule text with the live values, its slider(s), and "would have flagged N, worth $X".
export function ConditionControl({ condition, compact = false }) {
  const { thresholds, setThreshold, resetThreshold, labels } = useApp();
  const th = condition.threshold;
  const win = condition.window;
  const cur = thresholds[condition.id] ?? {};
  const value = cur.value ?? th.value;
  const window = win ? cur.window ?? win.value : null;
  const sim = useSimulate(condition.id, value, window);
  const changed = value !== th.value || (win && window !== win.value);
  const delta = sim ? sim.hits - condition.hits : 0;

  return (
    <div className={compact ? "other-rule" : "cond-ctl"}>
      {compact ? <h4>{condition.name}</h4> : (
        <h3>
          {condition.name}
          {condition.triggers_action
            ? <Chip tone="accent" title="Flags, holds, notifies and logs without waiting for a person">Acts automatically</Chip>
            : <Chip tone="neutral" title="Detection only, no automatic action">Detection only</Chip>}
        </h3>
      )}
      {!compact && <RuleText text={condition.rule_text} value={value} window={window} />}
      <div className="sliders">
        <Slider id={`th-${condition.id}`} spec={th} value={value} onChange={(v) => setThreshold(condition.id, { value: v })} />
        {win && <Slider id={`win-${condition.id}`} spec={win} value={window} onChange={(v) => setThreshold(condition.id, { window: v })} />}
      </div>

      <p className="sim-line" aria-live="polite">
        {sim ? (
          <>Would have flagged <b>{num(sim.hits)}</b> {nounFor(condition.id, labels, sim.hits)}, worth <b>{money(sim.amount)}</b>.</>
        ) : "Counting..."}
      </p>
      {!compact && sim && (
        <div className="sim-stats">
          {sim.top_owner && <span>{sim.top_owner}: <b>{num(sim.top_owner_hits)}</b> of them ({num(sim.top_owner_share)}%)</span>}
          {sim.refunds_caught != null && <span>Refunded later: <b>{money(sim.refunds_caught)}</b></span>}
          {sim.return_rate != null && <span>Returned: <b>{num(sim.return_rate)}%</b>{sim.return_rate_other != null && <> vs {num(sim.return_rate_other)}% for other business orders</>}</span>}
          {sim.below_cost != null && <span>Sold below cost: <b>{num(sim.below_cost)}</b></span>}
        </div>
      )}
      <p className="sim-base">
        Default {fmt(th.value, th.unit)}{win ? `, ${fmt(win.value, win.unit)}` : ""}: {num(condition.hits)} flagged, {money(condition.amount)}.
        {changed && sim && (
          <>
            {" "}<span className={delta > 0 ? "delta-up" : delta < 0 ? "delta-down" : ""}>{delta > 0 ? `+${delta}` : delta} vs default.</span>{" "}
            <button type="button" className="link-btn" onClick={() => resetThreshold(condition.id)}>Reset</button>
          </>
        )}
      </p>
    </div>
  );
}
