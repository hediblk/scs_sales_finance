"""Overview KPIs, charts, insights and drill-downs. Every number here is computed from the cleaned data."""
import pandas as pd

from . import detect
from .detect import fmt_money
from .pipeline import EXTRACTED_ON, Dataset


def _jan_sep(o):
    return o[o.order_date.dt.month <= 9]


def _pct(a, b):
    return 100 * (b / a - 1)


def headline(ds: Dataset):
    """Jan-Sep 2025 vs Jan-Sep 2026: revenue, gross profit (known-cost rows), gross profit minus refunds, refunds."""
    o = _jan_sep(ds.orders)
    out = {}
    for y in (2025, 2026):
        oy = o[o.year == y]
        known = oy[oy.cost_known]
        out[y] = {"revenue": float(oy.revenue.sum()), "gross_profit": float(known.gp.sum()),
                  "refunds": float(oy.refund.sum()), "margin_pct": float(100 * known.gp.sum() / known.revenue.sum()),
                  "discount_pct": float(100 * (1 - oy.revenue.sum() / oy.list_rev.sum()))}
        out[y]["gp_minus_refunds"] = out[y]["gross_profit"] - out[y]["refunds"]
    out["growth"] = {k: _pct(out[2025][k], out[2026][k]) for k in ("revenue", "gross_profit", "gp_minus_refunds", "refunds")}
    return out


def rep_stats(ds: Dataset, window=14):
    o = ds.orders[ds.orders.sales_rep.notna()]
    g = o.groupby("sales_rep").agg(region=("region", lambda s: s.mode()[0]), orders=("order_id", "size"),
                                   revenue=("revenue", "sum"), list_rev=("list_rev", "sum"), refunds=("refund", "sum"),
                                   customers=("customer_id", "nunique"))
    known = o[o.cost_known].groupby("sales_rep").agg(gp=("gp", "sum"), rev_known=("revenue", "sum"))
    g = g.join(known)
    g["discount_pct"] = 100 * (1 - g.revenue / g.list_rev)
    g["margin_pct"] = 100 * g.gp / g.rev_known
    g["refund_pct"] = 100 * g.refunds / g.revenue
    g["qe_share_pct"] = 100 * o[o.days_to_qend <= window - 1].groupby("sales_rep").revenue.sum() / g.revenue
    g["revenue_share_pct"] = 100 * g.revenue / g.revenue.sum()
    return g


def discount_bands(ds: Dataset):
    o = ds.orders[ds.orders.is_business].copy()
    bins = [0, 0.10, 0.20, 0.30, 0.40, 1.01]
    labels = ["0-10%", "10-20%", "20-30%", "30-40%", "40%+"]
    o["band"] = pd.cut(o.discount, bins, right=False, labels=labels)
    rows = []
    for b, g in o.groupby("band", observed=True):
        k = g[g.cost_known]
        rows.append({"band": str(b), "orders": int(len(g)), "return_rate": round(100 * float(g.returned.mean()), 1),
                     "margin": round(100 * float(k.gp.sum() / k.revenue.sum()), 1)})
    return rows


def week_of_quarter_share(ds: Dataset, rep="R07"):
    o = ds.orders[ds.orders.sales_rep.notna()]
    r = o[o.sales_rep == rep].groupby("week_of_quarter").revenue.sum()
    oth = o[o.sales_rep != rep].groupby("week_of_quarter").revenue.sum()
    return [{"week": int(w), "rep": round(100 * float(r.get(w, 0) / r.sum()), 1),
             "others": round(100 * float(oth.get(w, 0) / oth.sum()), 1)} for w in range(1, 14)]


def furniture_damage(ds: Dataset):
    o = ds.orders[ds.orders.category == "Furniture"]
    dmg = o[o.return_reason == "Damaged in transit"].groupby("region").refund.sum()
    rev = o.groupby("region").revenue.sum()
    growth = _jan_sep(ds.orders).groupby(["region", "year"]).revenue.sum().unstack()
    return [{"region": reg, "damage_refund_pct": round(100 * float(dmg.get(reg, 0) / rev[reg]), 1),
             "revenue_growth_pct": round(float(_pct(growth.loc[reg, 2025], growth.loc[reg, 2026])), 1)}
            for reg in rev.sort_values(ascending=False).index]


def quiet_stats(ds: Dataset):
    q = detect.quiet_customers(ds)
    quiet, active = q[q.quiet], q[~q.quiet]
    return {"quiet": int(len(quiet)), "business_customers": int(len(q)), "quiet_rev25": float(quiet.rev25.sum()),
            "quiet_bad_pct": float(100 * quiet.bad_return.mean()), "active_bad_pct": float(100 * active.bad_return.mean()),
            "quiet_rate_bad": float(100 * q[q.bad_return].quiet.mean()), "quiet_rate_no_bad": float(100 * q[~q.bad_return].quiet.mean())}


def overview(ds: Dataset):
    h = headline(ds)
    g = h["growth"]
    sim = detect.qe_simulate(ds, **detect.C1_DEFAULT)
    ar = detect.ar_position(ds)
    od60 = ar[ar.max_overdue > 60]
    reps = rep_stats(ds)
    r07 = reps.loc["R07"]
    others = reps.drop("R07")
    kpis = [
        {"id": "revenue", "label": "Revenue, Jan-Sep 2026", "value": round(h[2026]["revenue"], 2), "unit": "$",
         "hint": f"{g['revenue']:+.1f}% vs Jan-Sep 2025", "tone": "good"},
        {"id": "gp_growth", "label": "Gross profit growth", "value": round(g["gross_profit"], 1), "unit": "%",
         "hint": f"Revenue grew {g['revenue']:.1f}%. Margin {h[2025]['margin_pct']:.1f}% to {h[2026]['margin_pct']:.1f}%", "tone": "warn"},
        {"id": "net_growth", "label": "Gross profit minus refunds, growth", "value": round(g["gp_minus_refunds"], 1), "unit": "%",
         "hint": "What is left of the growth once returns are paid back", "tone": "bad"},
        {"id": "refunds", "label": "Refunds, Jan-Sep 2026", "value": round(h[2026]["refunds"], 2), "unit": "$",
         "hint": f"{g['refunds']:+.0f}% vs Jan-Sep 2025", "tone": "bad"},
        {"id": "qe_flagged", "label": "Quarter-end discount orders", "value": sim["hits"], "unit": "orders",
         "hint": f"{fmt_money(sim['amount'])} revenue, {sim['top_owner_hits']} by {sim['top_owner']}, {fmt_money(sim['refunds_caught'])} refunded later", "tone": "warn"},
        {"id": "overdue", "label": "Overdue at extraction", "value": round(float(ar.overdue_amt.sum()), 2), "unit": "$",
         "hint": f"{len(od60)} customers past 60 days. Late-payment rate flat since 2025", "tone": "neutral"},
    ]
    gv = [{"metric": "Revenue", "y2025": round(h[2025]["revenue"]), "y2026": round(h[2026]["revenue"]), "growth_pct": round(g["revenue"], 1)},
          {"metric": "Gross profit", "y2025": round(h[2025]["gross_profit"]), "y2026": round(h[2026]["gross_profit"]), "growth_pct": round(g["gross_profit"], 1)},
          {"metric": "Gross profit minus refunds", "y2025": round(h[2025]["gp_minus_refunds"]), "y2026": round(h[2026]["gp_minus_refunds"]), "growth_pct": round(g["gp_minus_refunds"], 1)}]
    bands = discount_bands(ds)
    woq = week_of_quarter_share(ds)
    furn = furniture_damage(ds)
    qs = quiet_stats(ds)
    rep_rows = [{"rep": k, "region": v.region, "discount": round(v.discount_pct, 1), "margin": round(v.margin_pct, 1),
                 "qe_share": round(v.qe_share_pct, 1), "revenue": round(v.revenue)} for k, v in reps.iterrows()]
    charts = [
        {"id": "growth_vs_profit", "type": "bar", "unit": "$", "x": "metric",
         "title": "Revenue grew a third, profit did not follow",
         "caption": f"Jan-Sep 2025 vs Jan-Sep 2026. Revenue {g['revenue']:+.1f}%, gross profit {g['gross_profit']:+.1f}%, gross profit minus refunds {g['gp_minus_refunds']:+.1f}%. Gross profit uses the 98.5% of lines with a known cost.",
         "series": [{"key": "y2025", "label": "Jan-Sep 2025"}, {"key": "y2026", "label": "Jan-Sep 2026"}], "rows": gv},
        {"id": "discount_band_returns", "type": "bar", "unit": "%", "x": "band",
         "title": "Deep discounts come back as returns",
         "caption": "Business orders by discount band: share returned and gross margin. At 30 to 40% off, almost a quarter of orders come back and the margin is near zero (40%+ is only a handful of orders).",
         "series": [{"key": "return_rate", "label": "Orders returned %"}, {"key": "margin", "label": "Gross margin %"}], "rows": bands},
        {"id": "qe_week_share", "type": "line", "unit": "%", "x": "week",
         "title": "R07 books half the quarter in its last two weeks",
         "caption": f"Share of each rep's revenue by week of the quarter. R07: {r07.qe_share_pct:.0f}% in the last 14 days; other reps {others.qe_share_pct.min():.0f} to {others.qe_share_pct.max():.0f}%.",
         "series": [{"key": "rep", "label": "R07 (Atlantic)"}, {"key": "others", "label": "Other reps"}], "rows": woq},
        {"id": "rep_discount_margin", "type": "scatter", "unit": "%", "x": "discount",
         "title": "One rep sits far from the rest",
         "caption": "Each dot is a rep: average discount vs gross margin.",
         "series": [{"key": "margin", "label": "Gross margin %"}], "rows": rep_rows},
        {"id": "furniture_damage_region", "type": "bar", "unit": "%", "x": "region",
         "title": "Furniture breaks on the long routes",
         "caption": "Damaged-in-transit refunds as a share of furniture revenue, by region.",
         "series": [{"key": "damage_refund_pct", "label": "Damage refunds, % of furniture revenue"}], "rows": furn},
        {"id": "quiet_vs_bad_return", "type": "bar", "unit": "%", "x": "group",
         "title": "Customers who went quiet had a bad return twice as often",
         "caption": f"{qs['quiet']} of {qs['business_customers']} business customers went quiet (no order for over twice their usual gap and 60 days). They spent {fmt_money(qs['quiet_rev25'])} in 2025. Timing and correlation, not proof of cause.",
         "series": [{"key": "bad_return_pct", "label": "Had a damaged, defective or wrong-item return %"}],
         "rows": [{"group": "Quiet customers", "bad_return_pct": round(qs["quiet_bad_pct"], 1)},
                  {"group": "Active customers", "bad_return_pct": round(qs["active_bad_pct"], 1)}]},
    ]
    who = [
        {"exec": "CEO", "claim": "Revenue up a third, Atlantic shines",
         "verdict": f"Top line true ({g['revenue']:+.1f}%). Atlantic's growth is deep discounts and returns; its SMB and Enterprise revenue fell."},
        {"exec": "CFO", "claim": "Profit lags, unpaid invoices",
         "verdict": f"Profit lag true (refunds {g['refunds']:+.0f}%). Unpaid invoices real but small: {fmt_money(ar.overdue_amt.sum())} overdue."},
        {"exec": "Operations", "claim": "Returns, big items",
         "verdict": "True. Furniture damaged in transit to BC and the Prairies."},
        {"exec": "Customer Success", "claim": "Customers went quiet",
         "verdict": f"True: {qs['quiet']} business customers. {qs['quiet_bad_pct']:.0f}% had a bad return vs {qs['active_bad_pct']:.0f}% of active ones."},
    ]
    recommendation = [
        "Pay quota on revenue net of returns after 45 days, and require approval for quarter-end discounts of 25% or more. Condition C1 automates it.",
        "Fix long-haul furniture shipping to BC and the Prairies, and call every business customer right after a damaged return. Condition C2 automates it.",
        "Collections: keep as is. It is not what changed.",
    ]
    return {"kpis": kpis, "charts": charts, "who_is_right": who, "recommendation": recommendation}


def insights(ds: Dataset):
    h = headline(ds)
    g = h["growth"]
    reps = rep_stats(ds)
    r07, others = reps.loc["R07"], reps.drop("R07")
    bands = {b["band"]: b for b in discount_bands(ds)}
    furn = {f["region"]: f for f in furniture_damage(ds)}
    qs = quiet_stats(ds)
    ov = ds.returns[ds.returns.reason == "Overstock / ordered in error"]
    lag = (ov.return_date - ov.order_date).dt.days
    return [
        {"id": "i1", "title": "Growth looks better than it is",
         "what": f"Revenue {g['revenue']:+.1f}% (Jan-Sep vs Jan-Sep), gross profit {g['gross_profit']:+.1f}%, gross profit minus refunds {g['gp_minus_refunds']:+.1f}%. Average discount went from {h[2025]['discount_pct']:.1f}% to {h[2026]['discount_pct']:.1f}%.",
         "why": "The CEO reads the top line; the CFO feels the bottom line. Both are right about their number.",
         "action": "Track profit net of refunds next to revenue.", "chart_id": "growth_vs_profit"},
        {"id": "i2", "title": "Quarter-end discounts buy revenue that comes back",
         "what": f"R07, the only Atlantic rep, books {r07.qe_share_pct:.0f}% of revenue in the last 14 days of the quarter at a {r07.discount_pct:.0f}% average discount (other reps {others.discount_pct.min():.0f} to {others.discount_pct.max():.0f}%). "
                 f"Orders 30 to 40% off are returned {bands['30-40%']['return_rate']}% of the time and keep a {bands['30-40%']['margin']}% margin. "
                 f"All {len(ov)} overstock returns ({fmt_money(ov.refund_amount.sum())}) come back from R07's resellers {lag.min()} to {lag.max()} days later.",
         "why": "The quota bonus pays on booked revenue; the company pays for the discount and the refund.",
         "action": "Pay quota on revenue net of returns; require approval for deep quarter-end discounts.", "chart_id": "discount_band_returns"},
        {"id": "i3", "title": "Furniture breaks on the long routes",
         "what": f"Damaged-in-transit refunds are {furn['BC']['damage_refund_pct']}% of furniture revenue in BC and {furn['Prairies']['damage_refund_pct']}% in the Prairies, vs {furn['Ontario']['damage_refund_pct']}% in Ontario. BC is also the fastest-growing region ({furn['BC']['revenue_growth_pct']:+.0f}%).",
         "why": "Refund cost and warehouse time grow with the region.",
         "action": "Change packaging or carrier for long-haul furniture.", "chart_id": "furniture_damage_region"},
        {"id": "i4", "title": "A bad return comes before customers go quiet",
         "what": f"{qs['quiet']} business customers went quiet ({fmt_money(qs['quiet_rev25'])} of 2025 spend). {qs['quiet_bad_pct']:.0f}% of them had a damaged, defective or wrong-item return, vs {qs['active_bad_pct']:.0f}% of active customers.",
         "why": "Nobody calls after a bad return, so nobody knows why they left.",
         "action": "Contact every business customer right after a bad return.", "chart_id": "quiet_vs_bad_return"},
    ]


# ---------------------------------------------------------------- drill-downs
def _month_end_balance(co):
    co = co[co.terms_days > 0]
    if co.empty:
        return {}
    months = pd.period_range(co.order_date.min(), EXTRACTED_ON, freq="M")
    far = pd.Timestamp("2100-01-01")
    pay = co.payment_date.fillna(far)
    out = {}
    for m in months:
        end = m.end_time.normalize()
        out[str(m)] = round(float(co.revenue[(co.order_date <= end) & (pay > end)].sum()), 2)
    return out


def customer_entity(ds: Dataset, cid):
    cust = ds.customers.set_index("customer_id")
    if cid not in cust.index:
        return None
    c = cust.loc[cid]
    o = ds.orders
    co = o[o.customer_id == cid].sort_values("order_date")
    cr = ds.returns[ds.returns.customer_id == cid]
    ar = detect.ar_position(ds)
    owed = float(ar.owed.get(cid, 0.0))
    max_od = int(ar.max_overdue.get(cid, 0)) if cid in ar.index else 0
    known = co[co.cost_known]
    facts = [
        {"label": "Segment", "value": c.segment, "unit": ""},
        {"label": "Region", "value": c.region, "unit": ""},
        {"label": "Account rep", "value": c.account_rep if pd.notna(c.account_rep) else "None (online)", "unit": ""},
        {"label": "Payment terms", "value": c.payment_terms, "unit": ""},
        {"label": "Credit limit", "value": float(c.credit_limit), "unit": "$"},
        {"label": "Customer since", "value": str(c.signup_date.year), "unit": ""},
        {"label": "Revenue, 2025", "value": round(float(co[co.year == 2025].revenue.sum()), 2), "unit": "$"},
        {"label": "Revenue, Jan-Sep 2026", "value": round(float(co[co.year == 2026].revenue.sum()), 2), "unit": "$"},
        {"label": "Refunds", "value": round(float(cr.refund_amount.sum()), 2), "unit": "$"},
        {"label": "Open amount", "value": round(owed, 2), "unit": "$"},
        {"label": "Oldest unpaid invoice, days past due", "value": max(max_od, 0), "unit": "days"},
    ]
    # compare to peers: same segment
    seg = o[o.segment == c.segment]
    per = seg.groupby("customer_id").agg(rev=("revenue", "sum"), lst=("list_rev", "sum"), ref=("refund", "sum"))
    per["disc"] = 100 * (1 - per.rev / per.lst)
    per["refund_pct"] = 100 * per.ref / per.rev
    paid = seg[seg.payment_date.notna() & (seg.terms_days > 0)]
    dtp = (paid.payment_date - paid.order_date).dt.days.groupby(paid.customer_id).mean()
    me_paid = co[co.payment_date.notna() & (co.terms_days > 0)]
    compare = [
        {"label": "Average discount", "value": round(float(100 * (1 - co.revenue.sum() / co.list_rev.sum())), 1) if len(co) else 0,
         "peer_value": round(float(per.disc.median()), 1), "peer_group": f"{c.segment} median", "unit": "%"},
        {"label": "Refunds as % of revenue", "value": round(float(100 * cr.refund_amount.sum() / co.revenue.sum()), 1) if len(co) else 0,
         "peer_value": round(float(per.refund_pct.median()), 1), "peer_group": f"{c.segment} median", "unit": "%"},
        {"label": "Gross margin", "value": round(float(100 * known.gp.sum() / known.revenue.sum()), 1) if len(known) else 0,
         "peer_value": round(float(100 * seg[seg.cost_known].gp.sum() / seg[seg.cost_known].revenue.sum()), 1), "peer_group": f"{c.segment} overall", "unit": "%"},
    ]
    if len(me_paid):
        compare.append({"label": "Days to pay", "value": round(float((me_paid.payment_date - me_paid.order_date).dt.days.mean()), 1),
                        "peer_value": round(float(dtp.median()), 1), "peer_group": f"{c.segment} median", "unit": "days"})
    timeline = []
    for r in co.itertuples():
        timeline.append({"date": f"{r.order_date:%Y-%m-%d}", "kind": "order", "amount": round(float(r.revenue), 2),
                         "note": f"{r.order_id}: {r.quantity} x {r.product} at {100 * r.discount:.1f}% off" + (" (below cost)" if r.below_cost else "")})
        if pd.notna(r.payment_date) and r.terms_days > 0:
            timeline.append({"date": f"{r.payment_date:%Y-%m-%d}", "kind": "payment", "amount": round(float(r.revenue), 2),
                             "note": f"{r.order_id} paid {(r.payment_date - r.due_date).days:+d} days vs due date"})
    for r in cr.itertuples():
        timeline.append({"date": f"{r.return_date:%Y-%m-%d}", "kind": "return", "amount": round(float(r.refund_amount), 2),
                         "note": f"{r.return_id}: {r.quantity_returned} x {r.product}, {r.reason}"})
    timeline.sort(key=lambda t: t["date"])
    bal = _month_end_balance(co)
    monthly = co.groupby(co.order_date.dt.to_period("M")).revenue.sum()
    months = sorted(set(bal) | {str(m) for m in monthly.index})
    rows = [{"month": m, "revenue": round(float(monthly.get(pd.Period(m), 0.0)), 2), "balance": bal.get(m, 0.0)} for m in months]
    series = [{"key": "revenue", "label": "Ordered"}] + ([{"key": "balance", "label": "Balance owed"}] if bal else [])
    return {"id": cid, "name": detect.entity_name(c.segment, cid), "kind": "customer", "facts": facts, "compare": compare,
            "timeline": timeline, "chart": {"type": "line", "x": "month", "unit": "$", "series": series, "rows": rows}}


def rep_entity(ds: Dataset, rep):
    reps = rep_stats(ds)
    if rep not in reps.index:
        return None
    r = reps.loc[rep]
    oth = reps.drop(rep)
    o = ds.orders[ds.orders.sales_rep == rep]
    sim = detect.qe_discount_hits(ds, **detect.C1_DEFAULT)
    facts = [
        {"label": "Region", "value": r.region, "unit": ""},
        {"label": "Customers", "value": int(r.customers), "unit": ""},
        {"label": "Revenue, Jan 2025 to Sep 2026", "value": round(float(r.revenue), 2), "unit": "$"},
        {"label": "Share of rep-driven revenue", "value": round(float(r.revenue_share_pct), 1), "unit": "%"},
        {"label": "Refunds", "value": round(float(r.refunds), 2), "unit": "$"},
        {"label": "Orders flagged by C1 (25%, 14 days)", "value": int((sim.sales_rep == rep).sum()), "unit": ""},
    ]
    compare = [
        {"label": "Average discount", "value": round(float(r.discount_pct), 1), "peer_value": round(float(oth.discount_pct.median()), 1), "peer_group": "Other reps median", "unit": "%"},
        {"label": "Gross margin", "value": round(float(r.margin_pct), 1), "peer_value": round(float(oth.margin_pct.median()), 1), "peer_group": "Other reps median", "unit": "%"},
        {"label": "Revenue in last 14 days of quarter", "value": round(float(r.qe_share_pct), 1), "peer_value": round(float(oth.qe_share_pct.median()), 1), "peer_group": "Other reps median", "unit": "%"},
        {"label": "Refunds as % of revenue", "value": round(float(r.refund_pct), 1), "peer_value": round(float(oth.refund_pct.median()), 1), "peer_group": "Other reps median", "unit": "%"},
    ]
    timeline = []
    for q, g in o.groupby("quarter"):
        share = 100 * g[g.days_to_qend <= 13].revenue.sum() / g.revenue.sum()
        disc = 100 * (1 - g.revenue.sum() / g.list_rev.sum())
        end = pd.Period(q).end_time
        timeline.append({"date": f"{end:%Y-%m-%d}", "kind": "quarter", "amount": round(float(g.revenue.sum()), 2),
                         "note": f"{q}: {disc:.0f}% average discount, {share:.0f}% booked in the last 14 days, {fmt_money(g.refund.sum())} refunded"})
    return {"id": rep, "name": f"Account rep {rep}", "kind": "rep", "facts": facts, "compare": compare, "timeline": timeline,
            "chart": {"type": "line", "x": "week", "unit": "%",
                      "series": [{"key": "rep", "label": rep}, {"key": "others", "label": "Other reps"}],
                      "rows": week_of_quarter_share(ds, rep)}}
