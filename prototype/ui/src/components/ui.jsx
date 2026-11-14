import { fmt } from "../lib/format.js";

export function Chip({ tone = "neutral", children, title }) {
  return <span className={`chip chip-${tone}`} title={title}>{children}</span>;
}

const SEVERITY = { high: ["bad", "High"], medium: ["warn", "Medium"], low: ["neutral", "Low"] };
export function SeverityChip({ severity }) {
  const [tone, label] = SEVERITY[severity] ?? ["neutral", severity];
  return (
    <Chip tone={tone}>
      <span className={`sev-bars sev-${severity}`} aria-hidden="true"><i /><i /><i /></span>
      {label} severity
    </Chip>
  );
}

const STATUS = {
  open: ["warn", "Open"],
  auto_held: ["accent", "On hold"],
  notified: ["info", "Task open"],
  overridden: ["neutral", "Overridden"],
  resolved: ["good", "Resolved"],
};
export function StatusChip({ status }) {
  const [tone, label] = STATUS[status] ?? ["neutral", status];
  return <Chip tone={tone}>{label}</Chip>;
}

// KPI tile: small uppercase label, big value, muted hint. Tone shows as a top rule plus the hint text.
export function Tile({ label, value, unit, hint, tone = "neutral" }) {
  return (
    <div className={`tile tone-${tone}`}>
      <div className="tile-label">{label}</div>
      <div className="tile-value">{fmt(value, unit, { compact: true })}</div>
      {hint && <div className="tile-hint">{hint}</div>}
    </div>
  );
}

export function SectionHead({ title, children, aside }) {
  return (
    <div className="section-head">
      <div>
        <h2>{title}</h2>
        {children && <p>{children}</p>}
      </div>
      {aside && <div className="section-aside">{aside}</div>}
    </div>
  );
}

export function Loading({ what = "Loading" }) {
  return <div className="loading" role="status"><span className="spinner" aria-hidden="true" />{what}</div>;
}

export function ErrorBox({ error }) {
  return <div className="error-box" role="alert">Could not load: {String(error?.message ?? error)}</div>;
}

export function Empty({ children }) {
  return <div className="empty">{children}</div>;
}
