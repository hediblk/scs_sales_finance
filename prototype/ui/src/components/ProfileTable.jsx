import { Fragment, useState } from "react";
import { num } from "../lib/format.js";

// One row per column, from GET /api/{raw|clean}/{table}/profile only. No detection logic here:
// every flag is read off the profile facts (distinct counts, formats, negatives, blanks, repeated keys).

// Blanks that are part of how the business works, not data problems (shown grey, with the reason).
const STRUCTURAL_BLANKS = {
  sales_rep: "online orders have no rep",
  payment_date: "invoice still unpaid at extraction",
};

const norm = (v) => String(v).normalize("NFD").replace(/[̀-ͯ]/g, "").trim().toLowerCase();

function MiniHist({ hist, w = 80, h = 18 }) {
  if (!hist?.length) return null;
  const max = Math.max(...hist.map((b) => b.count), 1);
  const bw = w / hist.length;
  return (
    <svg className="mini-hist" width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true">
      {hist.map((b, i) => {
        const bh = b.count ? Math.max(1, (b.count / max) * h) : 0;
        return <rect key={i} x={i * bw + 0.5} y={h - bh} width={Math.max(1, bw - 1)} height={bh} />;
      })}
    </svg>
  );
}

// Flags for one column, each { text, tone: "bad" | "warn" | "muted", title }.
function flagsOf(c, tmeta, aboveOne, cleanDistinct) {
  const out = [];
  if (tmeta?.key === c.column && tmeta.duplicate_keys > 0) out.push({ text: `${num(tmeta.duplicate_keys)} repeated ids`, tone: "bad" });
  const top = c.top ?? [];
  // Text written several ways: more distinct values in the raw file than after cleaning (both from the API).
  const after = cleanDistinct?.[c.column];
  const variants = c.dtype === "text" && !/_id$/.test(c.column) && (after != null ? c.distinct > after : new Set(top.map((t) => norm(t.value))).size < top.length);
  if (variants) {
    out.push({ text: `${num(c.distinct)} ${/product|name/.test(c.column) ? "names" : "spellings"}`, tone: "warn",
      title: after != null ? `${num(after)} after cleaning` : "The same value is written several ways" });
  }
  if (c.date?.formats?.length > 1) {
    const minor = [...c.date.formats].sort((a, b) => a.count - b.count)[0];
    out.push({ text: `${num(minor.count)} ${minor.pattern}`, tone: "warn", title: "Dates written in another format" });
  }
  if (c.numeric?.negatives > 0) out.push({ text: `${num(c.numeric.negatives)} negative`, tone: "bad" });
  if (c.column === "discount" && aboveOne > 0) out.push({ text: `${num(aboveOne)} above 1`, tone: "bad", title: "Discounts stored as percents (22.5 instead of 0.225)" });
  if (c.missing > 0) {
    const why = STRUCTURAL_BLANKS[c.column];
    out.push({ text: `${num(c.missing)} blank`, tone: why ? "muted" : "warn", title: why ? `Expected: ${why}` : "Missing values" });
  }
  return out;
}

function WhatsIn({ c, tmeta }) {
  if (/_id$/.test(c.column)) {
    if (tmeta?.key === c.column) return <span>{tmeta.duplicate_keys > 0 ? `${num(tmeta.duplicate_keys)} repeated` : "unique"}</span>;
    return <span>{num(c.distinct)} distinct</span>;
  }
  if (c.numeric) {
    return (
      <span className="wi-num">
        <MiniHist hist={c.numeric.hist} />
        <span>{num(c.numeric.min)} / <b>{num(c.numeric.median)}</b> / {num(c.numeric.max)}</span>
      </span>
    );
  }
  if (c.date) {
    return (
      <span>{c.date.min} to {c.date.max}
        <span className="muted"> · {c.date.formats.map((f) => `${f.pattern} ${num(f.count)}`).join(" · ")}</span>
      </span>
    );
  }
  return <span>{(c.top ?? []).slice(0, 3).map((t) => `${t.value === "" ? "(blank)" : t.value} ${num(t.count)}`).join(" · ")}</span>;
}

function Expanded({ c, onFilter }) {
  const top = c.top ?? [];
  const max = Math.max(...top.map((t) => t.count), 1);
  return (
    <div className="pt-more">
      {c.numeric && (
        <div className="pt-hist">
          <MiniHist hist={c.numeric.hist} w={360} h={70} />
          <p className="muted small">min {num(c.numeric.min)} · p25 {num(c.numeric.p25)} · median {num(c.numeric.median)} · p75 {num(c.numeric.p75)} · max {num(c.numeric.max)}{c.numeric.zeros ? ` · ${num(c.numeric.zeros)} zeros` : ""}</p>
        </div>
      )}
      {!c.numeric && top.length > 0 && (
        <ul className="prof-top">
          {top.map((t) => (
            <li key={t.value}>
              <span className="prof-val mono">{t.value === "" ? <i className="blank">blank</i> : t.value}</span>
              <span className="prof-bar"><i style={{ width: `${(t.count / max) * 100}%` }} /></span>
              <span className="prof-count">{num(t.count)}</span>
              <button type="button" className="link-btn small" onClick={() => onFilter(c.column, t.value)}>Show these rows</button>
            </li>
          ))}
          {c.distinct > top.length && <li className="muted small">{num(c.distinct - top.length)} more values</li>}
        </ul>
      )}
      {c.missing > 0 && <button type="button" className="link-btn small" onClick={() => onFilter(c.column, "")}>Show the {num(c.missing)} blank rows</button>}
    </div>
  );
}

export function ProfileTable({ rows, tmeta, source, aboveOne, cleanDistinct, onFilter }) {
  const [open, setOpen] = useState(null);
  const clean = source === "clean";
  return (
    <div className="card table-card">
      <div className="table-wrap">
        <table className="table pt">
          <thead>
            <tr><th>Column</th><th>Type</th><th>Missing</th><th className="num">Distinct</th><th>What's in it</th><th>{clean ? "Changed" : "Flags"}</th></tr>
          </thead>
          <tbody>
            {rows.map((c) => {
              const flags = clean ? [] : flagsOf(c, tmeta, aboveOne, cleanDistinct);
              const real = flags.some((f) => f.tone !== "muted") || (clean && c.changed_cells > 0);
              const isOpen = open === c.column;
              return (
                <Fragment key={c.column}>
                  <tr className={`pt-row${real ? " is-flagged" : ""}${isOpen ? " is-open" : ""}`} onClick={() => setOpen(isOpen ? null : c.column)}
                    tabIndex={0} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), setOpen(isOpen ? null : c.column))}
                    aria-expanded={isOpen}>
                    <td className="mono pt-col">{c.column}</td>
                    <td><span className="chip chip-info">{c.dtype}</span></td>
                    <td className="pt-missing">
                      {c.missing ? <>{num(c.missing)} <span className="muted">({num(c.missing_pct)}%)</span></> : <span className="muted">0</span>}
                      {c.missing > 0 && <span className="pt-bar"><i style={{ width: `${Math.max(3, c.missing_pct)}%` }} /></span>}
                    </td>
                    <td className="num">{num(c.distinct)}</td>
                    <td className="pt-what"><WhatsIn c={c} tmeta={tmeta} /></td>
                    <td className="pt-flags">
                      {clean
                        ? (c.changed_cells > 0 ? <span className="chip chip-accent">{num(c.changed_cells)} cells fixed</span> : <span className="muted small">none</span>)
                        : flags.map((f) => <span key={f.text} className={`chip chip-${f.tone === "muted" ? "neutral" : f.tone}`} title={f.title}>{f.text}</span>)}
                    </td>
                  </tr>
                  {isOpen && (
                    <tr className="pt-expand"><td colSpan={6}><Expanded c={c} onFilter={onFilter} /></td></tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
