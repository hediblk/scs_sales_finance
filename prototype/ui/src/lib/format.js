const cad = new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD", maximumFractionDigits: 0 });
const cadCompact = new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD", notation: "compact", maximumFractionDigits: 1 });
const numFmt = new Intl.NumberFormat("en-CA", { maximumFractionDigits: 1 });
const numCompact = new Intl.NumberFormat("en-CA", { notation: "compact", maximumFractionDigits: 1 });

const isNum = (v) => typeof v === "number" && !Number.isNaN(v);

export function money(v, { compact = false } = {}) {
  if (!isNum(v)) return "n/a";
  return compact && Math.abs(v) >= 10000 ? cadCompact.format(v) : cad.format(v);
}

export function num(v, { compact = false } = {}) {
  if (!isNum(v)) return String(v ?? "n/a");
  return compact && Math.abs(v) >= 10000 ? numCompact.format(v) : numFmt.format(v);
}

// Format a value with the unit strings used in the contract: "$", "%", "days", "x", "" or any word.
export function fmt(v, unit, opts = {}) {
  if (!isNum(v)) return v == null || v === "" ? "n/a" : String(v);
  switch (unit) {
    case "$": return money(v, opts);
    case "%": return `${num(v)}%`;
    case "x": return `${num(v)}x`;
    case "days": return `${num(v)} ${v === 1 ? "day" : "days"}`;
    case undefined: case null: case "": return num(v, opts);
    default: return `${num(v, opts)} ${unit}`;
  }
}

// Short axis label for a unit.
export function axisFmt(unit) {
  return (v) => (unit === "$" ? money(v, { compact: true }) : unit === "%" ? `${num(v)}%` : num(v, { compact: true }));
}

export function plural(label = "") {
  if (/[^aeiou]y$/i.test(label)) return label.slice(0, -1) + "ies";
  if (/(s|x|ch|sh)$/i.test(label)) return label + "es";
  return label + "s";
}

export const lower = (s = "") => s.charAt(0).toLowerCase() + s.slice(1);

export function humanize(code = "") {
  const s = code.replace(/[_-]+/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function dateLabel(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m) return iso;
  return d ? `${MONTHS[m - 1]} ${d}, ${y}` : `${MONTHS[m - 1]} ${y}`;
}

export function tsLabel(ts) {
  if (!ts) return "";
  const time = ts.length > 10 ? ts.slice(11, 16) : "";
  const [, m, d] = ts.slice(0, 10).split("-").map(Number);
  return `${MONTHS[m - 1]} ${d}${time ? `, ${time}` : ""}`;
}

// "2025-01" -> "Jan 25"; anything else unchanged.
export function tickLabel(v) {
  if (typeof v === "string" && /^\d{4}-\d{2}$/.test(v)) {
    const [y, m] = v.split("-");
    return `${MONTHS[Number(m) - 1]} ${y.slice(2)}`;
  }
  return v;
}
