import { useApp } from "../state.jsx";
import { dateLabel } from "../lib/format.js";

// Text wordmarks. Both companies are fictional; these are our own designs, adjust freely.
function ChromeOakMark() {
  return (
    <div className="wordmark wm-chrome-oak" aria-label="Chrome & Oak Office Supply">
      <svg className="wm-glyph" viewBox="0 0 32 32" aria-hidden="true">
        <rect x="3" y="4" width="26" height="7" rx="1.5" fill="var(--brand-2)" />
        <rect x="6" y="11" width="3" height="17" rx="1" fill="var(--brand-1)" />
        <rect x="23" y="11" width="3" height="17" rx="1" fill="var(--brand-1)" />
        <rect x="9" y="17" width="14" height="2" fill="var(--brand-1)" opacity=".55" />
      </svg>
      <div>
        <div className="wm-name"><span className="wm-chrome">Chrome</span><span className="wm-amp">&amp;</span><span className="wm-oak">Oak</span></div>
        <div className="wm-sub">Office Supply</div>
      </div>
    </div>
  );
}

function MillenniumMark() {
  return (
    <div className="wordmark wm-millennium" aria-label="Millennium Mutual">
      <svg className="wm-glyph" viewBox="0 0 32 32" aria-hidden="true">
        <circle cx="16" cy="16" r="13.5" fill="none" stroke="var(--brand-2)" strokeWidth="1.5" />
        <path d="M9 22V10.5l7 8 7-8V22" fill="none" stroke="var(--brand-1)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      </svg>
      <div>
        <div className="wm-name">Millennium <span className="wm-mutual">Mutual</span></div>
        <div className="wm-sub">Home and auto insurance since 2000</div>
      </div>
    </div>
  );
}

export function Wordmark({ meta }) {
  if (meta?.company === "chrome-oak") return <ChromeOakMark />;
  if (meta?.company === "millennium") return <MillenniumMark />;
  return <div className="wordmark"><div className="wm-name">{meta?.company_name ?? ""}</div></div>;
}

export function Sidebar({ pages, active, onSelect }) {
  const { meta, openCount } = useApp();
  return (
    <aside className="sidebar">
      <Wordmark meta={meta} />
      <nav className="nav" aria-label="Sections">
        {pages.map((p, i) => (
          <button key={p.key} type="button" className={`nav-item${active === p.key ? " is-active" : ""}`}
            aria-current={active === p.key ? "page" : undefined} onClick={() => onSelect(p.key)}>
            <span className="nav-step">{p.step ?? String(i + 1).padStart(2, "0")}</span>
            <span className="nav-text">
              <span className="nav-label">{p.label}</span>
              {p.hint && <span className="nav-hint">{p.hint}</span>}
            </span>
            {p.badge === "openAlerts" && openCount > 0 && <span className="nav-badge" title="Open alerts">{openCount}</span>}
          </button>
        ))}
      </nav>
      <div className="side-foot">
        <div><span className="side-foot-label">Data extracted</span>{meta ? dateLabel(meta.extracted_on) : ""}</div>
        {meta?.ai_enabled === false && <div><span className="side-foot-label">AI text</span>Template fallback (no key)</div>}
      </div>
    </aside>
  );
}

export function Topbar({ page, labels }) {
  const { header } = useApp();
  const own = header?.page === page.key ? header : null;
  const lead = own?.lead ?? (typeof page.lead === "function" ? page.lead(labels) : page.lead);
  return (
    <header className="topbar">
      <div className="topbar-text">
        <div className="eyebrow">{page.step ? `${page.step} ` : ""}{page.label}</div>
        <h1>{own?.title ?? page.title}</h1>
        {lead && <p className="lead">{lead}</p>}
      </div>
    </header>
  );
}
