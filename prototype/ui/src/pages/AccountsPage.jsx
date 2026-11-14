import { useEffect, useMemo, useState } from "react";
import { api } from "../data/api.js";
import { useApp, useResource } from "../state.jsx";
import { money, num } from "../lib/format.js";
import { Empty, ErrorBox, Loading, Tile } from "../components/ui.jsx";

const PAGE = 48;

export function accountStatus(a) {
  if (a.credit_hold) return ["held", "Credit hold"];
  if (a.utilization > 1) return ["over", "Over limit"];
  if (a.days_overdue > 60) return ["over", `${a.days_overdue} days overdue`];
  if (a.utilization >= 0.8) return ["near", "Near limit"];
  if (a.days_overdue > 0) return ["near", `${a.days_overdue} days overdue`];
  return ["ok", "On track"];
}

function AccountCard({ a, onOpen }) {
  const [cls, label] = accountStatus(a);
  const pct = Math.round((a.utilization ?? 0) * 100);
  const util = a.utilization > 1 ? "over" : a.utilization >= 0.8 ? "near" : "ok";
  return (
    <button type="button" className={`card acct ${cls}`} onClick={onOpen}>
      <div className="acct-top">
        <div>
          <div className="acct-name">{a.name}</div>
          <div className="acct-sub">{a.segment} · {a.region} · {a.rep}</div>
        </div>
        <span className={`status-pill ${cls}`}>{label}</span>
      </div>
      <div className="acct-money">
        <div><div className="lbl">Open balance</div><div className="big">{money(a.open_balance)}</div></div>
        <div style={{ textAlign: "right" }}><div className="lbl">Credit limit</div><div className="big" style={{ color: "var(--text-2)", fontSize: 15 }}>{money(a.credit_limit)}</div></div>
      </div>
      <div className={`util ${util}`}>
        <div className="util-track"><div className="util-fill" style={{ width: `${Math.max(3, Math.min(100, pct))}%` }} /></div>
        <div className="util-meta"><span>Utilization <b>{pct}%</b></span><span>{a.terms}</span></div>
      </div>
      <div className="acct-tags">
        {a.days_overdue > 0 && <span className="chip chip-warn">{a.days_overdue} days overdue</span>}
        {a.times_over_limit > 0 && <span className="chip chip-bad">Over limit {a.times_over_limit}x</span>}
      </div>
    </button>
  );
}

const SORTS = {
  risk: ["Most at risk", (a, b) => (b.credit_hold - a.credit_hold) || (b.utilization > 1) - (a.utilization > 1) || b.days_overdue - a.days_overdue || b.utilization - a.utilization],
  overdue: ["Days overdue", (a, b) => b.days_overdue - a.days_overdue],
  utilization: ["Utilization", (a, b) => b.utilization - a.utilization],
  balance: ["Open balance", (a, b) => b.open_balance - a.open_balance],
};

function Customers() {
  const { openEntity, labels } = useApp();
  const { data, error, reload } = useResource("accounts", api.accounts);
  const [seg, setSeg] = useState("All");
  const [sort, setSort] = useState("risk");
  const [query, setQuery] = useState("");
  const [shown, setShown] = useState(PAGE);
  const rows = useMemo(() => {
    if (!data) return [];
    const q = query.trim().toLowerCase();
    return data
      .filter((a) => seg === "All" || a.segment === seg)
      .filter((a) => !q || [a.id, a.name, a.rep, a.region].some((v) => String(v).toLowerCase().includes(q)))
      .sort(SORTS[sort][1]);
  }, [data, seg, sort, query]);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loading what={`Loading ${labels.entities}`} />;
  const segs = ["All", ...new Set(data.map((a) => a.segment))];
  const over = data.filter((a) => a.utilization > 1).length;
  const near = data.filter((a) => a.utilization >= 0.8 && a.utilization <= 1).length;
  const overdue60 = data.filter((a) => a.days_overdue > 60).length;
  return (
    <>
      <div className="tiles">
        <Tile label={`Business ${labels.entities}`} value={data.length} hint={`${money(data.reduce((s, a) => s + a.open_balance, 0))} open in total`} />
        <Tile label="Over credit limit" value={over} tone={over ? "bad" : "good"} hint="Open balance above the limit" />
        <Tile label="Near limit" value={near} tone={near ? "warn" : "good"} hint="80% of the limit or more" />
        <Tile label="Past 60 days" value={overdue60} tone={overdue60 ? "warn" : "good"} hint="Oldest unpaid invoice" />
      </div>
      <div className="acct-toolbar">
        <div className="chips">
          {segs.map((s) => (
            <button key={s} type="button" className={`chip-btn${seg === s ? " is-on" : ""}`} onClick={() => setSeg(s)}>
              {s} · {s === "All" ? data.length : data.filter((a) => a.segment === s).length}
            </button>
          ))}
        </div>
        <div className="chips">
          <input className="search" type="search" placeholder="Search id, rep, region" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search accounts" />
          <label className="select"><span className="sr-only">Sort</span>
            <select value={sort} onChange={(e) => setSort(e.target.value)}>
              {Object.entries(SORTS).map(([k, [l]]) => <option key={k} value={k}>Sort: {l}</option>)}
            </select>
          </label>
        </div>
      </div>
      {rows.length ? (
        <div className="card-grid">{rows.slice(0, shown).map((a) => <AccountCard key={a.id} a={a} onOpen={() => openEntity(a.id)} />)}</div>
      ) : <Empty>No account matches.</Empty>}
      {rows.length > shown && (
        <div className="more"><button type="button" className="btn btn-quiet btn-sm" onClick={() => setShown((n) => n + PAGE)}>Show more ({rows.length - shown} left)</button></div>
      )}
    </>
  );
}

function DiscountCompare({ value, team }) {
  const max = Math.max(value, team, 1) * 1.15;
  return (
    <div className="cmp" title={`${num(value)}% vs team ${num(team)}%`}>
      <b>{num(value)}%</b><span className="muted small">team {num(team)}%</span>
      <div className="cmp-track"><i style={{ width: `${(value / max) * 100}%` }} /><u style={{ left: `${(team / max) * 100}%` }} /></div>
    </div>
  );
}

function Reps() {
  const { openEntity } = useApp();
  const res = useResource("reps", api.reps);
  const quarters = useMemo(() => [...new Set((res.data ?? []).flatMap((r) => r.quarters.map((q) => q.quarter)))].sort(), [res.data]);
  const [quarter, setQuarter] = useState(null);
  useEffect(() => { if (!quarter && quarters.length) setQuarter(quarters[quarters.length - 1]); }, [quarters, quarter]);
  if (res.error) return <ErrorBox error={res.error} onRetry={res.reload} />;
  if (!res.data) return <Loading what="Loading reps" />;
  const rows = res.data.map((r) => ({ rep: r, q: r.quarters.find((x) => x.quarter === quarter) })).filter((x) => x.q)
    .sort((a, b) => b.q.revenue - a.q.revenue);
  return (
    <>
      <div className="acct-toolbar">
        <div className="tabs" role="tablist" aria-label="Quarter">
          {quarters.map((q) => <button key={q} type="button" role="tab" aria-selected={quarter === q} className={quarter === q ? "is-on" : ""} onClick={() => setQuarter(q)}>{q}</button>)}
        </div>
        <span className="muted small">Quota-countable: revenue minus refunds, without quarter-end orders still on hold or returned. Click a rep for the details.</span>
      </div>
      <div className="card table-card">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Rep</th><th className="num">Revenue (gross)</th><th className="num">Net of returns</th><th className="num">Quota-countable</th>
                <th>Avg discount vs team</th><th className="num">Last 14 days of quarter</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ rep, q }) => {
                return (
                  <tr key={rep.id} className="is-click" onClick={() => openEntity(rep.id)}>
                    <td><span className="rep-id">{rep.id}</span><div className="muted small">{rep.region}</div></td>
                    <td className="num">{money(q.revenue)}</td>
                    <td className="num">{money(q.net_of_returns)}</td>
                    <td className="num"><b>{money(q.quota_countable)}</b></td>
                    <td><DiscountCompare value={q.avg_discount} team={q.team_avg_discount} /></td>
                    <td className="num">{num(q.quarter_end_share)}%</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

export default function AccountsPage({ params }) {
  const [tab, setTab] = useState(params?.tab === "reps" ? "reps" : "customers");
  useEffect(() => { if (params?.tab) setTab(params.tab === "reps" ? "reps" : "customers"); }, [params?.tab]);
  const { labels } = useApp();
  return (
    <>
      <div className="acct-toolbar">
        <div className="tabs" role="tablist" aria-label="Accounts and limits">
          <button type="button" role="tab" aria-selected={tab === "customers"} className={tab === "customers" ? "is-on" : ""} onClick={() => setTab("customers")}>{labels.Entities}</button>
          <button type="button" role="tab" aria-selected={tab === "reps"} className={tab === "reps" ? "is-on" : ""} onClick={() => setTab("reps")}>Reps</button>
        </div>
      </div>
      {tab === "reps" ? <Reps /> : <Customers />}
    </>
  );
}
