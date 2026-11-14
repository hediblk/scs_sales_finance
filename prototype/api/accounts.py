"""Accounts & Limits, read only: business customers (credit limit vs balance, days overdue) and reps (quarterly
revenue, net of returns, quota-countable after C1 holds). Every value comes from the data or from the C1 rule."""
from functools import lru_cache

import pandas as pd

from . import actions, detect
from .pipeline import Dataset

_DS = {}


# ---------------------------------------------------------------- customers
@lru_cache(maxsize=1)
def _times_over_limit(ds_id):
    """Orders placed while the customer's open balance (this order included) was above the credit limit."""
    ds = _DS[ds_id]
    o = ds.orders[ds.orders.terms_days > 0].sort_values("order_date")
    far = pd.Timestamp("2100-01-01")
    counts = {}
    for cid, g in o.groupby("customer_id"):
        lim = g.credit_limit.iloc[0]
        od, pdt, amt = g.order_date.values, g.payment_date.fillna(far).values, g.revenue.values
        counts[cid] = int(sum(amt[(od <= od[i]) & (pdt > od[i])].sum() > lim for i in range(len(g))))
    return counts


def accounts(ds: Dataset):
    _DS[id(ds)] = ds
    over = _times_over_limit(id(ds))
    ar = detect.ar_position(ds)
    c = ds.customers[ds.customers.segment.isin(["SMB", "Enterprise", "Reseller"])]
    out = []
    for r in c.itertuples():
        owed = float(ar.owed.get(r.customer_id, 0.0))
        od = int(ar.max_overdue.get(r.customer_id, 0)) if r.customer_id in ar.index else 0
        out.append({"id": r.customer_id, "name": detect.entity_name(r.segment, r.customer_id), "segment": r.segment,
                    "region": r.region, "rep": r.account_rep, "terms": r.payment_terms, "credit_limit": float(r.credit_limit),
                    "open_balance": round(owed, 2), "utilization": round(owed / r.credit_limit, 3) if r.credit_limit else None,
                    "days_overdue": max(od, 0), "times_over_limit": over.get(r.customer_id, 0)})
    out.sort(key=lambda a: (-(a["utilization"] or 0), -a["days_overdue"]))
    return out


# ---------------------------------------------------------------- reps
def reps(ds: Dataset):
    o = ds.orders[ds.orders.sales_rep.notna()]
    # C1 holds at the default rule: credit not countable while held, cancelled when the goods came back.
    al = actions.apply_overrides(detect.qe_alerts(ds, **detect.C1_DEFAULT))
    not_countable = {a["order_id"] for a in al
                     if a["status"] == "auto_held" or (a["status"] == "resolved" and a["resolution"] == "returned")}
    o = o.assign(countable=~o.order_id.isin(not_countable))
    team = o.groupby("quarter").apply(lambda g: 100 * (1 - g.revenue.sum() / g.list_rev.sum()), include_groups=False)
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
                       "quarter_end_share": round(float(100 * gq[gq.days_to_qend <= 13].revenue.sum() / gq.revenue.sum()), 1)})
        out.append({"id": rep, "region": g.region.mode()[0], "customers": int(g.customer_id.nunique()), "quarters": qs})
    return out
