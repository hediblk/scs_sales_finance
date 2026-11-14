import { useEffect, useState } from "react";
import { api } from "../data/api.js";
import { isOpen, useApp } from "../state.jsx";
import { dateLabel, humanize, money, tsLabel } from "../lib/format.js";
import { Chip, SeverityChip, StatusChip } from "./ui.jsx";

const REC = { hold: ["accent", "Keep the hold"], release: ["good", "Release"], escalate: ["bad", "Escalate"] };

// What the $ on the card means, per condition (docs/PLAN.md).
export function impactLabel(a) {
  if (a.condition_id === "qe_discount") return a.status === "auto_held" ? "quota credit on hold" : "order revenue";
  if (a.condition_id === "quiet_after_bad_return") return "ordered in the last 12 months";
  if (a.condition_id === "overdue_or_over_limit") return "owed";
  return "impact";
}

function releaseLabel(a) {
  if (a.condition_id === "qe_discount") return "Release quota credit";
  if (a.condition_id === "quiet_after_bad_return") return "Close the task";
  return "Override";
}

function statusLine(a) {
  const bits = [];
  if (a.hold_until && a.status === "auto_held") bits.push(`Quota credit held until ${dateLabel(a.hold_until)} (45 days).`);
  if (a.below_cost) bits.push("Sold below cost.");
  if (a.escalate_on && a.status === "notified") bits.push(`Escalates to a win-back task on ${dateLabel(a.escalate_on)} if no reorder.`);
  if (a.resolution === "returned") bits.push(`Came back on ${dateLabel(a.resolved_on)}, ${money(a.refund)} refunded: quota credit cancelled.`);
  if (a.resolution === "kept") bits.push(`Hold ran its course, credit released on ${dateLabel(a.resolved_on)}.`);
  if (a.resolution === "reordered") bits.push(`Customer ordered again on ${dateLabel(a.resolved_on)}.`);
  if (a.override_reason) bits.push(`Overridden: "${a.override_reason}".`);
  return bits.join(" ");
}

function Advisory({ t }) {
  const [tone, label] = REC[t.recommendation] ?? ["neutral", t.recommendation];
  return (
    <div className="panel advisory">
      <div className="panel-head">
        <span className="panel-title">Advisory note{t.source ? ` (${t.source})` : ""}</span>
        <span className="panel-note">AI words the facts our rules computed. The rule's verdict does not change.</span>
      </div>
      <div className="panel-body">
        <p>{t.summary}</p>
        <div className="advisory-grid">
          <div><span className="mini-label">Human review needed</span><Chip tone={t.review_needed ? "warn" : "good"}>{t.review_needed ? "Yes" : "No"}</Chip></div>
          <div><span className="mini-label">Suggestion</span><Chip tone={tone}>{label}</Chip></div>
        </div>
        {t.why && <p className="small" style={{ marginTop: 10 }}>{t.why}</p>}
      </div>
    </div>
  );
}

function DraftBox({ draft, onChange }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(`To: ${draft.to}\nSubject: ${draft.subject}\n\n${draft.body}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* clipboard blocked */ }
  };
  return (
    <div className="panel">
      <div className="panel-head">
        <span className="panel-title">Email draft{draft.source ? ` (${draft.source})` : ""}</span>
        <span className="panel-note">Wording by AI, numbers by code. Edit before it goes out.</span>
      </div>
      <div className="draft-fields">
        <span>To</span><input value={draft.to} onChange={(e) => onChange({ ...draft, to: e.target.value })} />
        <span>Subject</span><input value={draft.subject} onChange={(e) => onChange({ ...draft, subject: e.target.value })} />
      </div>
      <textarea className="draft-body" value={draft.body} spellCheck={false} onChange={(e) => onChange({ ...draft, body: e.target.value })} />
      <div className="actions" style={{ margin: 0, padding: "0 14px 12px" }}>
        <button type="button" className="btn btn-quiet btn-sm" onClick={copy}>{copied ? "Copied" : "Copy text"}</button>
      </div>
    </div>
  );
}

function OverrideForm({ alert, busy, onCancel, onSubmit }) {
  const [reason, setReason] = useState("");
  return (
    <form className="panel" onSubmit={(e) => { e.preventDefault(); if (reason.trim()) onSubmit(reason.trim()); }}>
      <div className="panel-head">
        <span className="panel-title">{releaseLabel(alert)}</span>
        <span className="panel-note">The reason goes into the activity log with your decision.</span>
      </div>
      <div className="override-form">
        <textarea rows={3} value={reason} autoFocus onChange={(e) => setReason(e.target.value)}
          placeholder="Why should this alert not stand? (required)" aria-label="Reason" />
        <div className="row">
          <button type="button" className="btn btn-quiet btn-sm" onClick={onCancel}>Cancel</button>
          <button type="submit" className="btn btn-danger btn-sm" disabled={!reason.trim() || busy}>{busy ? "Saving..." : "Confirm"}</button>
        </div>
      </div>
    </form>
  );
}

// Detail pane for one alert: head with $ impact, why it fired, what the automation did,
// advisory note, email draft, release/override with a reason, Ask about this alert.
export function FindingDetail({ alert, condition }) {
  const { labels, rowsByAlert, openEntity, override, runAndLog, askAbout } = useApp();
  const [triage, setTriage] = useState(null);
  const [draft, setDraft] = useState(null);
  const [panel, setPanel] = useState(null);
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => { setTriage(null); setDraft(null); setPanel(null); setErr(null); }, [alert.id]);

  const rows = rowsByAlert[alert.id] ?? [];
  const open = isOpen(alert);
  const line = statusLine(alert);

  const load = async (which) => {
    setErr(null);
    if (panel === which) return setPanel(null);
    setPanel(which);
    try {
      if (which === "triage" && !triage) { setBusy("triage"); setTriage(await runAndLog(() => api.triage(alert.id))); }
      if (which === "draft" && !draft) { setBusy("draft"); setDraft(await runAndLog(() => api.draft(alert.id))); }
    } catch (e) { setErr(e.message); } finally { setBusy(null); }
  };

  const submit = async (reason) => {
    setBusy("override");
    try { await override(alert.id, reason); setPanel(null); } catch (e) { setErr(e.message); } finally { setBusy(null); }
  };

  return (
    <article className={`card finding sev-${alert.severity}`}>
      <header className="finding-head">
        <div>
          <div className="finding-eyebrow">{condition?.name ?? alert.condition_id} · {alert.return_id ?? alert.order_id ?? alert.id}</div>
          <h3>
            <button type="button" className="title-link" onClick={() => openEntity(alert.entity_id)}>{alert.entity_name}</button>
            {alert.product && <span className="muted" style={{ fontWeight: 500 }}> · {alert.quantity ? `${alert.quantity} x ` : ""}{alert.product}</span>}
          </h3>
          <div className="finding-meta">
            <SeverityChip severity={alert.severity} />
            <StatusChip status={alert.status} />
            {alert.segment && <span>{alert.segment}</span>}
            {alert.region && <span>{alert.region}</span>}
            <span>{labels.owner}: <button type="button" className="title-link" onClick={() => openEntity(alert.owner)}>{alert.owner}</button></span>
            <span>Flagged {dateLabel(alert.created_at)}</span>
          </div>
        </div>
        <div className="impact"><b>{money(alert.amount)}</b><span>{impactLabel(alert)}</span></div>
      </header>

      {line && <p className="explain" style={{ margin: "12px 0 0", lineHeight: 1.6 }}>{line}</p>}

      <div className="why-surfaced">
        <span className="mini-label">Why it fired</span>
        <ul>{alert.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
      </div>

      {rows.length > 0 && (
        <div>
          <span className="mini-label">What happened next</span>
          <div className="trail">
            {rows.map((r, i) => (
              <span key={i} className={`trail-step${r.actor === "user" ? " is-user" : ""}`} title={r.detail}>
                <b>{humanize(r.action)}</b>{r.to ? ` to ${r.to}` : ""} <span className="muted">{tsLabel(r.ts, r.ts_precision)}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="actions">
        <button type="button" className="btn btn-primary btn-sm" onClick={() => askAbout(alert)}>Ask about this alert</button>
        <button type="button" className={`btn btn-quiet btn-sm${panel === "draft" ? " is-on" : ""}`} onClick={() => load("draft")}>
          {busy === "draft" ? "Drafting..." : "Email draft"}
        </button>
        <span className="spacer" />
        {open
          ? <button type="button" className={`btn btn-outline-danger btn-sm${panel === "override" ? " is-on" : ""}`} onClick={() => setPanel(panel === "override" ? null : "override")}>{releaseLabel(alert)}</button>
          : <span className="closed-note">No action pending</span>}
      </div>

      {err && <div className="error-box">{err}</div>}
      {panel === "triage" && triage && <Advisory t={triage} />}
      {panel === "draft" && draft && <DraftBox draft={draft} onChange={setDraft} />}
      {panel === "override" && open && <OverrideForm alert={alert} busy={busy === "override"} onCancel={() => setPanel(null)} onSubmit={submit} />}
    </article>
  );
}
