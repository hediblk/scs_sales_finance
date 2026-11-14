"""What if: replay Jan-Sep 2026 with the C1 rule on (quarter-end discounts above the threshold capped at it).

Two scenarios bound the answer, both plain pandas:
- keep_at_cap: flagged orders keep their quantity, discount set to the threshold, refunds unchanged (conservative).
- lose_order: flagged orders removed, with their cost of goods and their refunds.
The truth sits between the two. The Q4 2026 figure is a rough run-rate, not a forecast model.
"""
from . import detect
from .gap import _bar, _totals
from .pipeline import Dataset

SCENARIOS = {"keep_at_cap": "Customer keeps the order at the capped discount",
             "lose_order": "Customer walks away from the order"}


def _jan_sep(df, year):
    return df[(df.order_date.dt.year == year) & (df.order_date.dt.month <= 9)]


def _money(df):
    t = _totals(df)
    return {"revenue": round(t["revenue"], 2), "gross_profit": round(t["gp"], 2), "refunds": round(t["refunds"], 2),
            "profit_after_refunds": round(t["gp"] - t["refunds"], 2)}


def _growth(now, before):
    return round(100 * (now / before - 1), 1) if before else None


def _refund_split(d25, d26):
    def grp(r):
        if not isinstance(r, str):
            return None
        if r.startswith("Overstock"):
            return "Overstock / ordered in error"
        return "Damaged in transit" if r == "Damaged in transit" else "Other reasons"
    out = []
    a = d25[d25.refund > 0].groupby(d25.return_reason.map(grp)).refund.sum()
    b = d26[d26.refund > 0].groupby(d26.return_reason.map(grp)).refund.sum()
    for g in sorted(set(a.index) | set(b.index)):
        out.append({"label": g, "y2025": round(float(a.get(g, 0)), 2), "y2026": round(float(b.get(g, 0)), 2),
                    "change": round(float(b.get(g, 0) - a.get(g, 0)), 2)})
    return out


def bridge(d25, d26):
    """Same bars and shape as /api/gap, for any 2026 version of the orders."""
    a, b = _totals(d25), _totals(d26)
    d = {k: b[k] - a[k] for k in a}
    par = (b["gp"] - b["refunds"]) - (a["gp"] - a["refunds"])
    return [
        _bar("list_growth", "Growth at list price", d["list"], kind="start"),
        _bar("discounts", "Extra discounts", d["discount"], driver_id="qe_push"),
        _bar("revenue", "Revenue growth", d["revenue"], kind="subtotal"),
        _bar("unknown_cost", "Revenue on lines with no unit cost (left out of profit)", d["rev_unknown_cost"]),
        _bar("cogs", "Extra cost of goods", d["cogs"]),
        _bar("gross_profit", "Gross profit growth", d["gp"], kind="subtotal"),
        _bar("refunds", "Extra refunds", d["refunds"], driver_id="transit_damage", split=_refund_split(d25, d26)),
        _bar("result", "Profit after refunds growth", par, kind="end"),
    ]


def _apply(d26, flagged_idx, scenario, threshold):
    if scenario == "lose_order":
        return d26.drop(flagged_idx)
    s = d26.copy()
    cap = threshold / 100
    s.loc[flagged_idx, "discount"] = cap
    s.loc[flagged_idx, "revenue"] = s.loc[flagged_idx, "list_rev"] * (1 - cap)
    s.loc[flagged_idx, "gp"] = s.loc[flagged_idx, "revenue"] - s.loc[flagged_idx, "cogs"]  # stays NaN when cost unknown
    return s  # refunds unchanged on purpose (conservative)


def whatif(ds: Dataset, threshold=25.0, window=14):
    o = ds.orders
    d25, d26 = _jan_sep(o, 2025), _jan_sep(o, 2026)
    hits = detect.qe_discount_hits(ds, threshold, window)
    flagged_idx = hits.index.intersection(d26.index)
    fl = d26.loc[flagged_idx]
    base25 = _money(d25)
    actual = _money(d26)
    actual["profit_after_refunds_growth"] = _growth(actual["profit_after_refunds"], base25["profit_after_refunds"])
    actual["revenue_growth"] = _growth(actual["revenue"], base25["revenue"])

    scenarios, bridges, frames = [], {}, {}
    for sid, label in SCENARIOS.items():
        s26 = _apply(d26, flagged_idx, sid, threshold)
        m = _money(s26)
        m["profit_after_refunds_growth"] = _growth(m["profit_after_refunds"], base25["profit_after_refunds"])
        m["revenue_growth"] = _growth(m["revenue"], base25["revenue"])
        delta = {k: round(m[k] - actual[k], 2) for k in ("revenue", "gross_profit", "refunds", "profit_after_refunds")}
        scenarios.append(dict({"id": sid, "label": label}, **m, delta=delta))
        bridges[sid] = bridge(d25, s26)
        frames[sid] = m

    # rough Q4 2026 run-rate
    q = o[o.order_date < "2026-10-01"].groupby("quarter").agg(revenue=("revenue", "sum"))
    quarters = [{"quarter": k, "revenue": round(float(v), 2), "kind": "actual"} for k, v in q.revenue.items()]
    q4_2025 = float(q.revenue.get("2025Q4", 0.0))
    yoy = actual["revenue"] / base25["revenue"] - 1
    baseline = q4_2025 * (1 + yoy)
    q4 = {"baseline": round(baseline, 2)}
    for sid in SCENARIOS:
        q4[sid] = round(baseline * (frames[sid]["revenue"] / actual["revenue"]), 2)
    # same run-rate for profit after refunds (Q4 2025 refunds are complete: returns run to the 2026-10-31 extraction)
    q4_25 = o[o.quarter == "2025Q4"]
    par_q4_25 = _money(q4_25)["profit_after_refunds"]
    par_yoy = actual["profit_after_refunds"] / base25["profit_after_refunds"] - 1
    par_base = par_q4_25 * (1 + par_yoy)
    q4_par = {"baseline": round(par_base, 2)}
    for sid in SCENARIOS:
        q4_par[sid] = round(par_base * (frames[sid]["profit_after_refunds"] / actual["profit_after_refunds"]), 2)

    top = fl.sales_rep.value_counts()
    assumptions = [
        "Replay of the 2026 orders that actually happened, not a prediction of how customers would behave.",
        f"The rule flags business orders in the last {window} days of a quarter with a discount of {threshold:g}% or more (condition C1).",
        "Keep at cap: the customer still buys the same quantity at the capped discount. Refunds on those orders stay as they were, "
        "which is conservative: deep-discount overstock might not have been ordered at all.",
        "Lose order: the customer walks away. The order's revenue, cost of goods and refunds all disappear.",
        "The real outcome sits between the two scenarios.",
        "Gross profit counts only order lines with a known unit cost (98.5% of lines), as everywhere else in the tool.",
        "Refunds are counted against the year the order was placed.",
        "Q4 2026 is a rough run-rate: Q4 2025 actual x (1 + Jan-Sep revenue growth), then each scenario's Jan-Sep effect. "
        "Not a forecast model; seasonality, new customers and price changes are ignored.",
        "Provisional: computed on data/clean as of 2026-11-14 12:40, until the teammate's cleaned data is in.",
    ]
    return {
        "period": "Jan-Sep 2026", "kind": "replay", "provisional": True, "rule": "cap",
        "threshold": threshold, "window": window,
        "flagged": {"orders": int(len(fl)), "revenue": round(float(fl.revenue.sum()), 2), "refunds": round(float(fl.refund.sum()), 2),
                    "share_r07": round(100 * float((fl.sales_rep == "R07").mean()), 1) if len(fl) else 0.0,
                    "owners": {k: int(v) for k, v in top.items()},
                    "list_revenue": round(float(fl.list_rev.sum()), 2),
                    "avg_discount": round(100 * float(1 - fl.revenue.sum() / fl.list_rev.sum()), 1) if len(fl) else 0.0},
        "baseline_2025": base25,
        "actual": actual,
        "scenarios": scenarios,
        "bridge_by_scenario": bridges,
        "projection": {"quarter": "2026Q4", "kind": "run-rate",
                       "method": "Q4 2025 actual x (1 + Jan-Sep YoY growth), then the scenario's Jan-Sep relative effect",
                       "jan_sep_revenue_growth_pct": round(100 * yoy, 1),
                       "quarters": quarters, "q4": q4,
                       "q4_profit_after_refunds": q4_par},
        "assumptions": assumptions,
    }
