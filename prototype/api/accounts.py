"""Accounts & Limits: business customers (credit limit vs balance) and reps (quarterly revenue, net of returns,
quota-countable after C1 holds). Credit holds and quarterly targets are advisory inputs a person sets; both are
logged. Targets are not in the data, so they start empty and are never invented."""
import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

from . import actions, detect
from .pipeline import EXTRACTED_ON, Dataset

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ROOT / "data" / "state" / "targets.json"


# ---------------------------------------------------------------- customers
@lru_cache(maxsize=1)
def _times_over_limit(ds_id):
    ds = _DS[ds_id]
    o = ds.orders[ds.orders.terms_days > 0].sort_values("order_date")
    far = pd.Timestamp("2100-01-01")
    counts = {}
    for cid, g in o.groupby("customer_id"):
        lim = g.credit_limit.iloc[0]
        od, pdt, amt = g.order_date.values, g.payment_date.fillna(far).values, g.revenue.values
        counts[cid] = int(sum(amt[(od <= od[i]) & (pdt > od[i])].sum() > lim for i in range(len(g))))
    return counts


_DS = {}


def _holds():
    """Latest credit-hold decision per account, from the action log."""
    state = {}
    for r in actions.load_user_rows():
        if r.get("action") == "credit_hold" and r["alert_id"].startswith("acct-"):
            state[r["alert_id"][5:]] = {"on": r.get("on", True), "reason": r["detail"], "ts": r["ts"]}
    return state


def accounts(ds: Dataset):
    _DS[id(ds)] = ds
    over = _times_over_limit(id(ds))
    ar = detect.ar_position(ds)
    holds = _holds()
    c = ds.customers[ds.customers.segment.isin(["SMB", "Enterprise", "Reseller"])]
    out = []
    for r in c.itertuples():
        owed = float(ar.owed.get(r.customer_id, 0.0))
        od = int(ar.max_overdue.get(r.customer_id, 0)) if r.customer_id in ar.index else 0
        h = holds.get(r.customer_id, {})
        out.append({"id": r.customer_id, "name": detect.entity_name(r.segment, r.customer_id), "segment": r.segment,
                    "region": r.region, "rep": r.account_rep, "terms": r.payment_terms, "credit_limit": float(r.credit_limit),
                    "open_balance": round(owed, 2), "utilization": round(owed / r.credit_limit, 3) if r.credit_limit else None,
                    "days_overdue": max(od, 0), "times_over_limit": over.get(r.customer_id, 0),
                    "credit_hold": bool(h.get("on", False)), "credit_hold_reason": h.get("reason") if h.get("on") else None})
    out.sort(key=lambda a: (-(a["utilization"] or 0), -a["days_overdue"]))
    return out


def set_credit_hold(ds: Dataset, cid, on, reason):
    acc = next((a for a in accounts(ds) if a["id"] == cid), None)
    if acc is None:
        return None
    verb = "placed" if on else "lifted"
    actions.log(f"acct-{cid}", "credit_hold", reason or f"Credit hold {verb}", actor="user", extra={"on": bool(on)})
    actions.log(f"acct-{cid}", "notify", f"Credit hold {verb} on {acc['name']}: {reason}", actor="system",
                to=acc["rep"] or "Accounts receivable")
    return next(a for a in accounts(ds) if a["id"] == cid)


# ---------------------------------------------------------------- reps
def _targets():
    if TARGETS.exists():
        try:
            return json.loads(TARGETS.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def set_target(rep, quarter, target):
    t = _targets()
    t.setdefault(rep, {})[quarter] = None if target is None else float(target)
    TARGETS.parent.mkdir(parents=True, exist_ok=True)
    TARGETS.write_text(json.dumps(t, indent=1), encoding="utf-8")
    actions.log(f"rep-{rep}", "target", f"Quarterly target for {rep}, {quarter}: {target}", actor="user")


def reset_targets():
    if TARGETS.exists():
        TARGETS.unlink()


def reps(ds: Dataset):
    o = ds.orders[ds.orders.sales_rep.notna()]
    # C1 holds at the default rule: credit not countable while held, cancelled when the goods came back.
    al = actions.apply_overrides(detect.qe_alerts(ds, **detect.C1_DEFAULT))
    not_countable = {a["order_id"] for a in al
                     if a["status"] == "auto_held" or (a["status"] == "resolved" and a["resolution"] == "returned")}
    o = o.assign(countable=~o.order_id.isin(not_countable))
    team = o.groupby("quarter").apply(lambda g: 100 * (1 - g.revenue.sum() / g.list_rev.sum()), include_groups=False)
    targets = _targets()
    out = []
    for rep, g in o.groupby("sales_rep"):
        qs = []
        for q, gq in g.groupby("quarter"):
            qs.append({"quarter": q, "revenue": round(float(gq.revenue.sum()), 2),
                       "net_of_returns": round(float(gq.revenue.sum() - gq.refund.sum()), 2),
                       "quota_countable": round(float(gq[gq.countable].revenue.sum() - gq[gq.countable].refund.sum()), 2),
                       "held_or_cancelled": round(float(gq[~gq.countable].revenue.sum()), 2),
                       "avg_discount": round(float(100 * (1 - gq.revenue.sum() / gq.list_rev.sum())), 1),
                       "team_avg_discount": round(float(team[q]), 1),
                       "quarter_end_share": round(float(100 * gq[gq.days_to_qend <= 13].revenue.sum() / gq.revenue.sum()), 1),
                       "target": targets.get(rep, {}).get(q)})
        out.append({"id": rep, "region": g.region.mode()[0], "customers": int(g.customer_id.nunique()), "quarters": qs})
    return out


def rep(ds: Dataset, rep_id):
    return next((r for r in reps(ds) if r["id"] == rep_id), None)


def as_of():
    return f"{EXTRACTED_ON:%Y-%m-%d}"
