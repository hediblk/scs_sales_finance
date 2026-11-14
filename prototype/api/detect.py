"""Detection rules. Plain pandas, thresholds as arguments, every alert carries its reasons.

C1 qe_discount            business order in the last `window` days of a quarter with discount >= `threshold` %
C2 quiet_after_bad_return business customer gets a damaged / defective / wrong-item return
C3 overdue_or_over_limit  invoice more than `days` overdue, or open balance above the credit limit (detection only)

Alerts are built "as of" the extraction date (2026-10-31): the rule runs on each event when it happens
(order date, return date) and the follow-up steps (quota release, reorder, escalation) are read from what
happened next in the data.
"""
import pandas as pd

from .pipeline import EXTRACTED_ON, Dataset

QUOTA_HOLD_DAYS = 45                     # every overstock return came back within 20 to 44 days
BAD_REASONS = ["Damaged in transit", "Defective", "Wrong item shipped"]
C1_DEFAULT = {"threshold": 25, "window": 14}
C2_DEFAULT = {"gap_mult": 1.0}
C3_DEFAULT = {"days": 60}


def fmt_money(x):
    return f"-${abs(x):,.0f}" if x < 0 else f"${x:,.0f}"


def company_discount_baseline(ds: Dataset):
    """Median and MAD of business-order discounts: the backing for the 25% threshold.

    MAD is scaled by 1.4826 so it is comparable to a standard deviation (the usual robust z-score):
    median 10.1% + 3 x scaled MAD = 27%. Unscaled it would give 21.5%.
    """
    d = ds.orders.loc[ds.orders.sales_rep.notna(), "discount"]
    med = float(d.median())
    mad = 1.4826 * float((d - med).abs().median())
    others_p99 = float(ds.orders.loc[ds.orders.sales_rep.notna() & (ds.orders.sales_rep != "R07"), "discount"].quantile(0.99))
    return {"median": med, "mad": mad, "median_plus_3mad": med + 3 * mad, "other_reps_p99": others_p99}


def entity_name(seg, cid):
    return f"{seg} {cid}"


# ---------------------------------------------------------------- C1
def qe_discount_hits(ds: Dataset, threshold=25.0, window=14):
    o = ds.orders
    m = o.is_business & (o.days_to_qend <= window - 1) & (o.discount >= threshold / 100 - 1e-9)
    return o[m]


def _rep_quarter_share(ds: Dataset, window):
    """Share of each rep's quarter revenue booked in the last `window` days of that quarter."""
    o = ds.orders[ds.orders.sales_rep.notna()]
    tot = o.groupby(["sales_rep", "quarter"]).revenue.sum()
    end = o[o.days_to_qend <= window - 1].groupby(["sales_rep", "quarter"]).revenue.sum()
    return (100 * end / tot).fillna(0)


def _prior_overstock(ds: Dataset):
    """For each order: number of earlier overstock returns by the same customer (known at order time)."""
    ov = ds.returns[ds.returns.reason == "Overstock / ordered in error"][["customer_id", "return_date"]]
    return ov


def qe_alert(row, ds: Dataset, threshold, window, rep_share=None, overstock=None, baseline=None):
    baseline = baseline or company_discount_baseline(ds)
    rep_share = _rep_quarter_share(ds, window) if rep_share is None else rep_share
    overstock = _prior_overstock(ds) if overstock is None else overstock
    hold_until = row.order_date + pd.Timedelta(days=QUOTA_HOLD_DAYS)
    reasons = [
        f"Discount {100 * row.discount:.1f}% (threshold {threshold:g}%, company median {100 * baseline['median']:.1f}%)",
        f"Ordered {row.order_date:%Y-%m-%d}, " + ("on the last day of the quarter" if row.days_to_qend == 0 else f"{int(row.days_to_qend)} day{'s' if row.days_to_qend != 1 else ''} before quarter end"),
    ]
    share = rep_share.get((row.sales_rep, row.quarter), None)
    if share is not None:
        reasons.append(f"{row.sales_rep} booked {share:.0f}% of {row.quarter} revenue in the last {window} days")
    if row.below_cost:
        margin = 100 * row.gp / row.revenue
        reasons.append(f"Sold below cost: margin {margin:.1f}% (unit cost {fmt_money(row.unit_cost)}, net price {fmt_money(row.unit_price * (1 - row.discount))})")
    prior = int(((overstock.customer_id == row.customer_id) & (overstock.return_date < row.order_date)).sum())
    if prior:
        reasons.append(f"{row.segment} with {prior} earlier overstock return{'s' if prior > 1 else ''}")

    severity = "high" if row.below_cost else ("medium" if row.discount >= 0.30 else "low")
    returned_in_hold = bool(row.returned and row.return_date <= hold_until)
    if returned_in_hold:
        status, resolution, resolved_on = "resolved", "returned", row.return_date
    elif hold_until <= EXTRACTED_ON:
        status, resolution, resolved_on = "resolved", "kept", hold_until
    else:
        status, resolution, resolved_on = "auto_held", None, None
    return {
        "id": f"qe-{row.order_id}", "condition_id": "qe_discount", "entity_id": row.customer_id,
        "entity_name": entity_name(row.segment, row.customer_id), "owner": row.sales_rep, "region": row.region,
        "severity": severity, "amount": round(float(row.revenue), 2), "reasons": reasons, "status": status,
        "created_at": f"{row.order_date:%Y-%m-%d}",
        # extra fields (not in the base contract, safe to ignore)
        "order_id": row.order_id, "product": row.product, "quantity": int(row.quantity),
        "discount_pct": round(100 * float(row.discount), 1), "below_cost": bool(row.below_cost),
        "segment": row.segment, "hold_until": f"{hold_until:%Y-%m-%d}", "resolution": resolution,
        "resolved_on": None if resolved_on is None else f"{resolved_on:%Y-%m-%d}",
        "refund": round(float(row.refund), 2), "return_reason": row.return_reason if row.returned else None,
        "prior_overstock_returns": prior,
    }


def qe_alerts(ds: Dataset, threshold=25.0, window=14):
    hits = qe_discount_hits(ds, threshold, window)
    rs, ov, bl = _rep_quarter_share(ds, window), _prior_overstock(ds), company_discount_baseline(ds)
    return [qe_alert(r, ds, threshold, window, rs, ov, bl) for r in hits.itertuples()]


def qe_simulate(ds: Dataset, threshold=25.0, window=14):
    o = ds.orders
    hits = qe_discount_hits(ds, threshold, window)
    biz = o[o.is_business]
    rest = biz.drop(hits.index)
    top_rep = hits.sales_rep.value_counts()
    return {
        "hits": int(len(hits)), "amount": round(float(hits.revenue.sum()), 2),
        "refunds_caught": round(float(hits.refund.sum()), 2),
        "return_rate": round(100 * float(hits.returned.mean()), 1) if len(hits) else 0.0,
        "return_rate_other": round(100 * float(rest.returned.mean()), 1),
        "below_cost": int(hits.below_cost.sum()),
        "top_owner": top_rep.index[0] if len(top_rep) else None,
        "top_owner_hits": int(top_rep.iloc[0]) if len(top_rep) else 0,
        "top_owner_share": round(100 * float(top_rep.iloc[0] / len(hits)), 1) if len(hits) else 0.0,
        "owners": {k: int(v) for k, v in top_rep.items()},
        "sentence": (f"At {threshold:g}% in the last {window} days: {len(hits)} orders, {fmt_money(hits.revenue.sum())} of revenue "
                     f"under quota hold, {fmt_money(hits.refund.sum())} later refunded. "
                     f"{(top_rep.iloc[0] if len(top_rep) else 0)} of them by {top_rep.index[0] if len(top_rep) else '-'}."),
    }


# ---------------------------------------------------------------- C2
def _usual_gap(dates):
    d = pd.Series(sorted(dates)).diff().dt.days.dropna()
    return float(d.median()) if len(d) else None


def bad_return_hits(ds: Dataset):
    r = ds.returns
    return r[r.reason.isin(BAD_REASONS) & r.segment.isin(["SMB", "Enterprise", "Reseller"])]


def bad_return_alert(row, ds: Dataset, gap_mult=1.0):
    o = ds.orders
    co = o[o.customer_id == row.customer_id]
    before = co[co.order_date <= row.return_date]
    gap = _usual_gap(before.order_date) or _usual_gap(co.order_date) or 30.0
    deadline = row.return_date + pd.Timedelta(days=round(gap_mult * gap))
    after = co[co.order_date > row.return_date].order_date
    next_order = after.min() if len(after) else None
    spend_12m = float(before[before.order_date > row.return_date - pd.Timedelta(days=365)].revenue.sum())
    cust = ds.customers.set_index("customer_id").loc[row.customer_id]
    since = int(cust.signup_date.year)

    reasons = [
        f"{row.reason}: {row.quantity_returned} x {row.product}, {fmt_money(row.refund_amount)} refunded",
        f"Customer since {since}, {fmt_money(spend_12m)} ordered in the 12 months before",
        f"Usual gap between orders: {gap:.0f} days",
    ]
    escalated = False
    if next_order is not None and next_order <= deadline:
        status, resolution, resolved_on = "resolved", "reordered", next_order
        reasons.append(f"Reordered {(next_order - row.return_date).days} days after the return")
    elif deadline <= EXTRACTED_ON:
        escalated = True
        status, resolution, resolved_on = "notified", None, None
        if next_order is not None:
            status, resolution, resolved_on = "resolved", "came_back_late", next_order
            reasons.append(f"No reorder within {gap_mult * gap:.0f} days: escalated to win-back, came back after {(next_order - row.return_date).days} days")
        else:
            reasons.append(f"No order in the {(EXTRACTED_ON - row.return_date).days} days since the return: escalated to win-back")
    else:
        status, resolution, resolved_on = "notified", None, None
        reasons.append(f"Waiting: usual reorder window ends {deadline:%Y-%m-%d}")
    severity = "high" if spend_12m >= 20000 else ("medium" if spend_12m >= 5000 else "low")
    return {
        "id": f"br-{row.return_id}", "condition_id": "quiet_after_bad_return", "entity_id": row.customer_id,
        "entity_name": entity_name(row.segment, row.customer_id), "owner": row.sales_rep, "region": row.region,
        "severity": severity, "amount": round(spend_12m, 2), "reasons": reasons, "status": status,
        "created_at": f"{row.return_date:%Y-%m-%d}",
        "return_id": row.return_id, "order_id": row.order_id, "product": row.product, "category": row.category,
        "return_reason": row.reason, "refund": round(float(row.refund_amount), 2), "segment": row.segment,
        "usual_gap_days": round(gap), "escalate_on": f"{deadline:%Y-%m-%d}", "escalated": escalated,
        "next_order": None if next_order is None else f"{next_order:%Y-%m-%d}", "resolution": resolution,
        "resolved_on": None if resolved_on is None else f"{resolved_on:%Y-%m-%d}",
    }


def bad_return_alerts(ds: Dataset, gap_mult=1.0):
    return [bad_return_alert(r, ds, gap_mult) for r in bad_return_hits(ds).itertuples()]


def bad_return_simulate(ds: Dataset, gap_mult=1.0):
    al = bad_return_alerts(ds, gap_mult)
    esc = [a for a in al if a["escalated"]]
    return {"hits": len(al), "amount": round(sum(a["refund"] for a in al), 2),
            "customers": len({a["entity_id"] for a in al}),
            "escalated": len(esc), "escalated_value": round(sum(a["amount"] for a in esc), 2),
            "reordered": sum(1 for a in al if a["resolution"] == "reordered"),
            "sentence": (f"{len(al)} bad returns on {len({a['entity_id'] for a in al})} business customers open a Customer Success task. "
                         f"Escalating after {gap_mult:g}x the usual gap sends {len(esc)} to win-back.")}


def quiet_customers(ds: Dataset, as_of="2026-09-30"):
    """Business customers silent for more than 2x their usual gap and more than 60 days."""
    o = ds.orders[ds.orders.is_business]
    as_of = pd.Timestamp(as_of)
    g = o.sort_values("order_date").groupby("customer_id").agg(
        last=("order_date", "max"), gap=("order_date", lambda d: d.diff().dt.days.median()),
        rev25=("revenue", lambda v: v[o.loc[v.index, "year"] == 2025].sum()))
    g["silent"] = (as_of - g["last"]).dt.days
    g["quiet"] = (g.silent > 2 * g.gap) & (g.silent > 60)
    bad = bad_return_hits(ds).customer_id.unique()
    g["bad_return"] = g.index.isin(bad)
    return g


# ---------------------------------------------------------------- C3
def ar_position(ds: Dataset):
    o = ds.orders[ds.orders.terms_days > 0]
    un = o[o.payment_date.isna()].copy()
    un["days_overdue"] = (EXTRACTED_ON - un.due_date).dt.days
    g = un.groupby("customer_id").agg(open_invoices=("order_id", "size"), owed=("revenue", "sum"),
                                      max_overdue=("days_overdue", "max"),
                                      overdue_amt=("revenue", lambda v: v[un.loc[v.index, "days_overdue"] > 0].sum()))
    return g.join(ds.customers.set_index("customer_id")[["segment", "region", "account_rep", "credit_limit", "payment_terms"]])


def overdue_alerts(ds: Dataset, days=60):
    g = ar_position(ds)
    hit = g[(g.max_overdue > days) | (g.owed > g.credit_limit)]
    out = []
    for cid, r in hit.iterrows():
        over = r.owed > r.credit_limit
        reasons = [f"Oldest unpaid invoice {int(r.max_overdue)} days past due" if r.max_overdue > 0 else "No invoice past due yet",
                   f"Owes {fmt_money(r.owed)} on {int(r.open_invoices)} invoice{'s' if r.open_invoices > 1 else ''}",
                   f"Balance at {100 * r.owed / r.credit_limit:.0f}% of the {fmt_money(r.credit_limit)} credit limit",
                   f"Terms: {r.payment_terms}"]
        severity = "high" if (over and r.max_overdue > days) or r.max_overdue > 90 else ("medium" if over or r.max_overdue > days else "low")
        out.append({"id": f"od-{cid}", "condition_id": "overdue_or_over_limit", "entity_id": cid,
                    "entity_name": entity_name(r.segment, cid), "owner": r.account_rep, "region": r.region,
                    "severity": severity, "amount": round(float(r.owed), 2), "reasons": reasons, "status": "open",
                    "created_at": f"{EXTRACTED_ON:%Y-%m-%d}", "days_overdue": int(r.max_overdue),
                    "over_limit": bool(over), "segment": r.segment})
    return out


def overdue_simulate(ds: Dataset, days=60):
    al = overdue_alerts(ds, days)
    g = ar_position(ds)
    return {"hits": len(al), "amount": round(sum(a["amount"] for a in al), 2),
            "overdue_total": round(float(g.overdue_amt.sum()), 2),
            "sentence": f"More than {days:g} days overdue or over limit: {len(al)} customers owing {fmt_money(sum(a['amount'] for a in al))}."}


# ---------------------------------------------------------------- registry
CONDITIONS = {
    "qe_discount": {
        "name": "Quarter-end discount push",
        "rule_text": "Business order in the last {window} days of a quarter with a discount of {value}% or more",
        "threshold": {"label": "Discount", "min": 15, "max": 35, "step": 1, "value": 25, "unit": "%"},
        "window": {"label": "Days before quarter end", "min": 7, "max": 30, "step": 1, "value": 14, "unit": "days"},
        "triggers_action": True,
        "actions": ["flag", "quota_hold", "notify", "release", "resolve"],
    },
    "quiet_after_bad_return": {
        "name": "Bad return on a business account",
        "rule_text": "Business customer gets a damaged, defective or wrong-item return. Escalate to win-back after {value}x their usual gap with no reorder",
        "threshold": {"label": "Escalate after", "min": 1, "max": 3, "step": 0.5, "value": 1, "unit": "x usual gap"},
        "triggers_action": True,
        "actions": ["flag", "notify", "draft", "winback_task", "resolve"],
    },
    "overdue_or_over_limit": {
        "name": "Overdue or over credit limit",
        "rule_text": "Business customer with an invoice more than {value} days past due, or a balance above the credit limit",
        "threshold": {"label": "Days overdue", "min": 0, "max": 120, "step": 5, "value": 60, "unit": "days"},
        "triggers_action": False,
        "actions": ["flag"],
    },
}


def alerts_for(ds: Dataset, condition, value=None, window=None):
    if condition == "qe_discount":
        return qe_alerts(ds, float(value if value is not None else 25), int(window if window is not None else 14))
    if condition == "quiet_after_bad_return":
        return bad_return_alerts(ds, float(value if value is not None else 1.0))
    if condition == "overdue_or_over_limit":
        return overdue_alerts(ds, float(value if value is not None else 60))
    raise KeyError(condition)


def simulate(ds: Dataset, condition, value=None, window=None):
    if condition == "qe_discount":
        return qe_simulate(ds, float(value if value is not None else 25), int(window if window is not None else 14))
    if condition == "quiet_after_bad_return":
        return bad_return_simulate(ds, float(value if value is not None else 1.0))
    if condition == "overdue_or_over_limit":
        return overdue_simulate(ds, float(value if value is not None else 60))
    raise KeyError(condition)


def alert_by_id(ds: Dataset, alert_id, value=None, window=None):
    """Build one alert from its id, whatever the slider position (ids are stable)."""
    kind, _, key = alert_id.partition("-")
    if kind == "qe":
        row = ds.orders[ds.orders.order_id == key]
        if row.empty:
            return None
        return qe_alert(next(row.itertuples()), ds, float(value or 25), int(window or 14))
    if kind == "br":
        row = ds.returns[ds.returns.return_id == key]
        if row.empty:
            return None
        return bad_return_alert(next(row.itertuples()), ds, float(value or 1.0))
    if kind == "od":
        return next((a for a in overdue_alerts(ds, 0) if a["id"] == alert_id), None)
    return None
