"""The gap (overview centre): from revenue growth to profit-after-refunds growth, ranked drivers, who is right.

Every number is computed here. The why / todo / why-first text is the team's (docs/PLAN.md, "Main objective").
"""
from . import detect
from .detect import fmt_money
from .pipeline import Dataset
from .story import _jan_sep, furniture_damage, headline, quiet_stats, rep_stats

PROVISIONAL = ("Provisional: computed on data/clean as of 2026-11-14 12:40 (duplicates dropped, 8 negative quantities set aside, "
               "blank unit costs left blank). Waits for the teammate's cleaned data.")

DRIVER_TEXT = {
    "qe_push": {"title": "Quarter-end discount push (R07, Atlantic resellers)",
                "why": "Quarterly target and bonus on gross revenue: deep discounts in the last 14 days, resellers send the overstock back about a month later.",
                "todo": "Pay quota on revenue net of returns after 45 days; require approval for quarter-end discounts of 25% or more.",
                "handled_by": ["qe_discount"], "chart_id": "discount_band_returns", "controllable": True, "rule_catchable": True},
    "transit_damage": {"title": "Furniture damaged in transit (BC, Prairies)",
                       "why": "Long-haul shipping of big items from Montreal; BC is also the fastest-growing region.",
                       "todo": "Change packaging or carrier for long-haul furniture.",
                       "handled_by": ["quiet_after_bad_return"], "chart_id": "furniture_damage_region", "controllable": True, "rule_catchable": False},
    "quiet_customers": {"title": "Business customers going quiet",
                        "why": "A bad return (damaged, defective, wrong item) comes before the silence for most of them, and nobody calls.",
                        "todo": "Contact the customer right after a bad return.",
                        "handled_by": ["quiet_after_bad_return"], "chart_id": "quiet_vs_bad_return", "controllable": True, "rule_catchable": True},
    "late_payments": {"title": "Unpaid invoices",
                      "why": "Steady since 2025: real, but not what changed.",
                      "todo": "Monitor; follow up only on clear cases (long overdue or over the credit limit).",
                      "handled_by": ["overdue_or_over_limit"], "chart_id": None, "controllable": True, "rule_catchable": True},
}
WHY_FIRST = ("Revenue on paper fails to become cash in two ways: it comes back, or it is never paid. "
             "The quarter-end discount push is the big one: new in 2026, one cause (a quota paid on gross revenue), and a rule catches it "
             "with almost no false alarms, so the tool acts on it automatically. Unpaid invoices are real but small and flat since 2025: "
             "the tool flags them and a person decides. Furniture damage on long routes also costs refunds, but its fix is operational "
             "(packaging, carrier), so it stays out of this tool.")


def _totals(df):
    k = df[df.cost_known]
    return {"list": float(df.list_rev.sum()), "revenue": float(df.revenue.sum()), "discount": float((df.list_rev - df.revenue).sum()),
            "rev_unknown_cost": float(df[~df.cost_known].revenue.sum()), "cogs": float(k.cogs.sum()),
            "gp": float(k.gp.sum()), "refunds": float(df.refund.sum())}


def _bar(i, label, delta, kind=None, **extra):
    """minus / plus bars carry the size (positive); start / subtotal / end carry the signed value."""
    if kind is None:
        return dict({"id": i, "label": label, "value": round(abs(delta), 2), "kind": "minus" if delta >= 0 else "plus"}, **extra)
    return dict({"id": i, "label": label, "value": round(delta, 2), "kind": kind}, **extra)


def _refund_groups(ds: Dataset):
    ret = ds.returns[ds.returns.order_date.dt.month <= 9]

    def grp(reason):
        if reason.startswith("Overstock"):
            return "Overstock / ordered in error"
        return "Damaged in transit" if reason == "Damaged in transit" else "Other reasons"
    return ret.assign(year=ret.order_date.dt.year, group=ret.reason.map(grp))


def gap(ds: Dataset):
    o = _jan_sep(ds.orders)
    a, b = _totals(o[o.year == 2025]), _totals(o[o.year == 2026])
    d = {k: b[k] - a[k] for k in a}
    par = (b["gp"] - b["refunds"]) - (a["gp"] - a["refunds"])

    rr = _refund_groups(ds)
    rd = rr.groupby(["group", "year"]).refund_amount.sum().unstack(fill_value=0)
    split = [{"label": g, "y2025": round(float(rd.loc[g].get(2025, 0)), 2), "y2026": round(float(rd.loc[g].get(2026, 0)), 2),
              "change": round(float(rd.loc[g].get(2026, 0) - rd.loc[g].get(2025, 0)), 2)} for g in rd.index]
    bridge = [
        _bar("list_growth", "Growth at list price", d["list"], kind="start"),
        _bar("discounts", "Extra discounts", d["discount"], driver_id="qe_push"),
        _bar("revenue", "Revenue growth", d["revenue"], kind="subtotal"),
        # Revenue on lines with no known unit cost is left out of gross profit; its small change is folded into this bar
        # so the bridge still adds up without a separate column.
        _bar("cogs", "Extra cost of goods", d["cogs"] + d["rev_unknown_cost"],
             note=f"Includes {d['rev_unknown_cost']:+,.0f} of revenue on lines with no known unit cost, left out of gross profit"),
        _bar("gross_profit", "Gross profit growth", d["gp"], kind="subtotal"),
        _bar("refunds", "Extra refunds", d["refunds"], split=split),
        _bar("result", "Profit after refunds growth", par, kind="end"),
    ]
    residual = d["list"] - d["discount"] - d["rev_unknown_cost"] - d["cogs"] - d["refunds"] - par

    hits = detect.qe_discount_hits(ds, **detect.C1_DEFAULT)
    base = detect.company_discount_baseline(ds)["median"]
    extra_disc = float((hits.list_rev * (hits.discount - base)).sum())
    reps = rep_stats(ds)
    r07 = _jan_sep(ds.orders[ds.orders.sales_rep == "R07"])
    r07_disc = {int(y): float(100 * (1 - g.revenue.sum() / g.list_rev.sum())) for y, g in r07.groupby("year")}
    dmg = rr[rr.group == "Damaged in transit"].groupby("year").refund_amount.sum()
    furn = {f["region"]: f for f in furniture_damage(ds)}
    qs = quiet_stats(ds)
    ar = detect.ar_position(ds)
    paid = ds.orders[(ds.orders.terms_days > 0) & ds.orders.payment_date.notna()]
    late = paid.assign(late=(paid.payment_date - paid.due_date).dt.days > 0).groupby("year").late.mean()
    drivers = [
        {"id": "qe_push", "rank": 1,
         "what": f"R07 books {reps.loc['R07'].qe_share_pct:.0f}% of revenue in the last 14 days of the quarter. Average discount "
                 f"{r07_disc.get(2025, 0):.0f}% in Jan-Sep 2025, {r07_disc.get(2026, 0):.0f}% in Jan-Sep 2026. {len(hits)} quarter-end orders at 25% or more: "
                 f"{fmt_money(hits.revenue.sum())} of revenue, {fmt_money(hits.refund.sum())} refunded later.",
         "impact": round(extra_disc + float(hits.refund.sum()), 2),
         "impact_note": "Discount above the company median on the flagged orders, plus their refunds (Jan 2025 to Sep 2026)",
         "changed_in_2026": bool(r07_disc.get(2026, 0) - r07_disc.get(2025, 0) > 5)},
        {"id": "transit_damage", "rank": 2,
         "what": f"Damaged-in-transit refunds are {furn['BC']['damage_refund_pct']}% of furniture revenue in BC and {furn['Prairies']['damage_refund_pct']}% "
                 f"in the Prairies, vs {furn['Ontario']['damage_refund_pct']}% in Ontario. Jan-Sep damage refunds: {fmt_money(dmg.get(2025, 0))} in 2025, "
                 f"{fmt_money(dmg.get(2026, 0))} in 2026.",
         "impact": round(float(dmg.get(2026, 0)), 2), "impact_note": "Damaged-in-transit refunds, Jan-Sep 2026",
         "changed_in_2026": bool(dmg.get(2026, 0) > 1.2 * dmg.get(2025, 0))},
        {"id": "quiet_customers", "rank": 3,
         "what": f"{qs['quiet']} business customers went quiet. {qs['quiet_bad_pct']:.0f}% of them had a bad return, vs {qs['active_bad_pct']:.0f}% of active customers.",
         "impact": round(qs["quiet_rev25"], 2), "impact_note": "What the quiet customers spent in 2025",
         "changed_in_2026": True},
        {"id": "late_payments", "rank": 4,
         "what": f"{fmt_money(ar.overdue_amt.sum())} overdue at extraction, {int((ar.max_overdue > 60).sum())} customers past 60 days. "
                 f"Share of invoices paid late: {100 * late.get(2025, 0):.0f}% in 2025, {100 * late.get(2026, 0):.0f}% in 2026.",
         "impact": round(float(ar.overdue_amt.sum()), 2), "impact_note": "Overdue at extraction",
         "changed_in_2026": bool(abs(late.get(2026, 0) - late.get(2025, 0)) > 0.05)},
    ]
    drivers = [dr for dr in drivers if dr["id"] in ("qe_push", "late_payments")]
    for rank, dr in enumerate(drivers, 1):
        dr.update(DRIVER_TEXT[dr["id"]], rank=rank)

    g = headline(ds)["growth"]
    who = [
        {"exec": "CEO", "claim": "Revenue is up about a third; the Atlantic team punches above its weight", "verdict": "partly",
         "evidence": f"Revenue {g['revenue']:+.1f}% is true. Atlantic's growth is deep quarter-end discounts to resellers and returns; its SMB and Enterprise revenue fell."},
        {"exec": "CFO", "claim": "Profit is not keeping up; chasing unpaid invoices every week", "verdict": "right",
         "evidence": f"Gross profit minus refunds {g['gp_minus_refunds']:+.1f}% against revenue {g['revenue']:+.1f}%; refunds {g['refunds']:+.0f}%. Unpaid invoices are real but small and flat."},
        {"exec": "Operations", "claim": "Returns eat warehouse time, especially big items", "verdict": "right",
         "evidence": f"Furniture is returned most; damage in transit to BC ({furn['BC']['damage_refund_pct']}% of furniture revenue) and the Prairies ({furn['Prairies']['damage_refund_pct']}%)."},
        {"exec": "Customer Success", "claim": "Long-time business customers went quiet", "verdict": "right",
         "evidence": f"{qs['quiet']} business customers went quiet ({fmt_money(qs['quiet_rev25'])} of 2025 spend); {qs['quiet_bad_pct']:.0f}% had a bad return vs {qs['active_bad_pct']:.0f}% of active ones."},
    ]
    return {"period": "Jan-Sep 2026 vs Jan-Sep 2025", "provisional": True, "provisional_note": PROVISIONAL,
            "headline": {"revenue_growth": round(d["revenue"], 2), "revenue_growth_pct": round(g["revenue"], 1),
                         "gross_profit_growth_pct": round(g["gross_profit"], 1),
                         "profit_after_refunds_growth": round(par, 2), "profit_after_refunds_growth_pct": round(g["gp_minus_refunds"], 1)},
            "bridge": bridge, "bridge_residual": round(residual, 2),
            "drivers": drivers, "who_is_right": who, "why_first": WHY_FIRST}
