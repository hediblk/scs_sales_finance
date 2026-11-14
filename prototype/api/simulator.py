"""Policy simulator (spec: docs/simulator-plan.md). Three modules, plain pandas, one envelope each:
baseline / selected / delta, controls, coverage, details, assumptions.

- pricing_policy: discount cap with retention weights, all valid orders Jan-Sep 2026.
- damage_policy: packaging + inspection for product x region groups with a high damaged-in-transit return rate.
- credit_policy: detection only at the 2026-10-31 snapshot (the chronological replay is deferred).

The sweeps that pick the recommended settings run once in `run_batch()` and are saved to output/simulations/;
slider changes call the same functions for one scenario.
"""
import csv
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .detect import fmt_money
from .pipeline import CLEAN, EXTRACTED_ON, Dataset

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "simulations"
MODEL_VERSION = "sim-2"
TOL = 1e-6  # CAD / pp tolerance for "does not fall below baseline"
DAMAGE = "Damaged in transit"
MIN_ORDERS = 30
DAMAGE_START = {"effectiveness": 25, "cost": 5}
CREDIT_PROVISIONAL_G = 60

COMMON_ASSUMPTIONS = [
    "Clean data as of 2026-11-14 12:40: orders to 2026-09-30, returns and payments observed to 2026-10-31. All money in CAD.",
    "Gross profit and contribution use only order lines with a known unit cost; unknown costs stay unknown (coverage shown).",
    "Refunds are attributed to the order they belong to (one return at most per order).",
    "Retrospective experiment on orders that already happened, not a demand forecast.",
]


def _cohort(ds: Dataset, period="2026"):
    o = ds.orders
    if period == "full":
        return o
    return o[(o.order_date.dt.year == 2026) & (o.order_date.dt.month <= 9)]


def _pct(a, b):
    return 100.0 * a / b if b else None


def _delta(sel, base):
    out = {}
    for k, v in sel.items():
        b = base.get(k)
        if isinstance(v, (int, float)) and isinstance(b, (int, float)) and not isinstance(v, bool):
            out[k] = v - b
    return out


def _round(d):
    out = {}
    for k, v in d.items():
        if isinstance(v, float):
            out[k] = None if math.isnan(v) else round(v, 2)
        else:
            out[k] = v
    return out


def _ge(a, b):
    return a is not None and b is not None and a >= b - TOL


# ================================================================ damage_policy
def damage_groups(c):
    dmg = (c.return_reason == DAMAGE) & c.returned
    c = c.assign(dmg=dmg.astype(int), dmg_refund=c.refund.where(dmg, 0.0))
    g = c.groupby(["product", "region"]).agg(orders=("order_id", "size"), damage_orders=("dmg", "sum"),
                                             damage_refunds=("dmg_refund", "sum"), units=("quantity", "sum"),
                                             unknown_cost_orders=("cost_known", lambda s: int((~s).sum())))
    g["damage_rate"] = g.damage_orders / g.orders
    g["eligible"] = g.orders >= MIN_ORDERS
    return g


def damage_metrics(c, targeted, effectiveness, cost):
    """targeted: set of (product, region). effectiveness in [0,1], cost CAD per shipped unit."""
    known = c.cost_known.values
    key = list(zip(c["product"], c.region))
    mask = np.array([k in targeted for k in key]) if targeted else np.zeros(len(c), bool)
    dmg = ((c.return_reason == DAMAGE) & c.returned).values
    dmg_refund = np.where(dmg, c.refund.values, 0.0)
    avoided = effectiveness * dmg_refund * mask
    refunds = c.refund.values - avoided
    icost = cost * c.quantity.values * mask
    rev = c.revenue.values
    gp = np.where(known, c.gp.values, 0.0)
    rev_k, ref_k, cost_k = rev[known].sum(), refunds[known].sum(), icost[known].sum()
    contribution = gp.sum() - ref_k - cost_k
    net_k = rev_k - ref_k
    return {
        "revenue": float(rev.sum()), "gross_profit": float(gp.sum()),
        "weighted_margin_pct": _pct(gp.sum(), rev_k),
        "refunds": float(refunds.sum()), "net_revenue_after_refunds": float(rev.sum() - refunds.sum()),
        "intervention_cost": float(icost.sum()), "avoided_damage_refunds": float(avoided.sum()),
        "net_benefit": float(avoided.sum() - icost.sum()),  # incremental benefit estimate, all rows (not total profit)
        "contribution": float(contribution), "contribution_margin_pct": _pct(contribution, net_k),
        "targeted_groups": len(targeted), "targeted_orders": int(mask.sum()), "targeted_units": int(c.quantity.values[mask].sum()),
        "targeted_unknown_cost_orders": int((mask & ~known).sum()),
        "targeted_unknown_cost_damaged": int((mask & ~known & dmg).sum()),
    }


def damage_targets(groups, trigger):
    t = trigger / 100.0
    sel = groups[groups.eligible & (groups.damage_rate > t + 1e-12)]
    return set(sel.index)


def damage_eligible(m, base):
    return (_ge(m["net_revenue_after_refunds"], base["net_revenue_after_refunds"])
            and _ge(m["contribution"], base["contribution"])
            and m["contribution_margin_pct"] is not None and base["contribution_margin_pct"] is not None
            and _ge(m["contribution_margin_pct"], base["contribution_margin_pct"]))


def damage_sweep(ds: Dataset, effectiveness=25, cost=5, period="2026"):
    c = _cohort(ds, period)
    groups = damage_groups(c)
    base = damage_metrics(c, set(), 0, 0)
    rows = [dict({"parameter": "off", "trigger": None}, **base, eligible=True)]
    for t in range(0, 101):
        m = damage_metrics(c, damage_targets(groups, t), effectiveness / 100, cost)
        rows.append(dict({"parameter": t, "trigger": t}, **m, eligible=damage_eligible(m, base)))
    cands = [r for r in rows if r["eligible"]]
    # max contribution, then net revenue, then margin; ties: fewer targeted units, then higher trigger (off counts as highest)
    best = sorted(cands, key=lambda r: (-r["contribution"], -r["net_revenue_after_refunds"], -(r["contribution_margin_pct"] or -1e9),
                                        r["targeted_units"], -(r["trigger"] if r["trigger"] is not None else 1e9)))[0]
    for r in rows:
        r["selected"] = r is best
    return rows, best, base


def damage_scenario(ds: Dataset, enabled=True, trigger=None, effectiveness=25, cost=5, period="2026", recommended=None):
    c = _cohort(ds, period)
    groups = damage_groups(c)
    base = damage_metrics(c, set(), 0, 0)
    rec_trigger = (recommended or {}).get("trigger")
    trig = trigger if trigger is not None else (rec_trigger if rec_trigger is not None else 15)
    targeted = damage_targets(groups, trig) if enabled else set()
    sel = damage_metrics(c, targeted, effectiveness / 100, cost) if enabled else dict(base)
    gl = []
    for (p, r), g in groups.sort_values("damage_rate", ascending=False).iterrows():
        gl.append({"product": p, "region": r, "orders": int(g.orders), "damage_orders": int(g.damage_orders),
                   "damage_rate_pct": round(100 * float(g.damage_rate), 1), "damage_refunds": round(float(g.damage_refunds), 2),
                   "units": int(g.units), "unknown_cost_orders": int(g.unknown_cost_orders), "eligible": bool(g.eligible),
                   "targeted": (p, r) in targeted})
    known = c.cost_known
    return {
        "module": "damage_policy", "label": "Damage prevention: packaging and inspection", "status": "ok", "enabled": bool(enabled),
        "period": "Jan 2025 to Sep 2026 (full window, evidence)" if period == "full" else "Jan-Sep 2026",
        "scope": "All valid orders, grouped by product x region; damaged-in-transit returns only",
        "controls": [
            {"id": "trigger", "label": "Damage-rate trigger (strictly above)", "kind": "policy", "min": 0, "max": 100, "step": 1, "unit": "%",
             "value": trig, "recommended": rec_trigger, "read_only": False},
            {"id": "effectiveness", "label": "Assumed damage-refund reduction", "kind": "assumption", "min": 0, "max": 100, "step": 1,
             "unit": "%", "value": effectiveness, "recommended": DAMAGE_START["effectiveness"], "read_only": False},
            {"id": "cost", "label": "Added cost per shipped unit", "kind": "assumption", "min": 0, "max": 20, "step": 1, "unit": "CAD",
             "value": cost, "recommended": DAMAGE_START["cost"], "read_only": False},
            {"id": "min_orders", "label": "Minimum orders per group", "kind": "derived", "min": MIN_ORDERS, "max": MIN_ORDERS, "step": 1,
             "unit": "orders", "value": MIN_ORDERS, "recommended": MIN_ORDERS, "read_only": True},
        ],
        "recommended": recommended,
        "baseline": _round(base), "selected": _round(sel), "delta": _round(_delta(sel, base)),
        "coverage": {"orders": int(len(c)), "known_cost_orders": int(known.sum()), "unknown_cost_orders": int((~known).sum()),
                     "known_cost_pct": round(100 * float(known.mean()), 1),
                     "targeted_unknown_cost_orders": sel.get("targeted_unknown_cost_orders", 0),
                     "targeted_unknown_cost_damaged": sel.get("targeted_unknown_cost_damaged", 0)},
        "details": {"groups": gl},
        "assumptions": COMMON_ASSUMPTIONS + [
            "Effectiveness and cost per unit are user assumptions, not estimated effects.",
            "The cost applies to every shipped unit in a targeted group, not only damaged units.",
            "Only damaged-in-transit refunds go down; other return reasons are unchanged.",
            "Product cost unchanged; no replacement sales and no recovered inventory assumed.",
            "Group rates come from the same cohort's observed returns: a retrospective experiment, not a detector that knew future returns.",
        ],
        "notes": ["Revenue and product gross profit do not change with packaging; net revenue after refunds and contribution can.",
                  "Contribution is a proxy (gross profit minus refunds minus intervention cost), not audited profit."],
    }


# ================================================================ pricing_policy
def _pricing_arrays(c, cap, retention):
    capf = cap / 100.0
    aff = c.discount.values > capf + 1e-12
    w = np.where(aff, retention / 100.0, 1.0)
    d = np.where(aff, capf, c.discount.values)
    rev = c.list_rev.values * (1 - d)
    return aff, w, rev


def pricing_metrics(c, cap, retention):
    aff, w, rev = _pricing_arrays(c, cap, retention)
    known = c.cost_known.values
    cogs = np.where(known, c.cogs.values, 0.0)
    gp = np.where(known, rev - cogs, 0.0) * w
    revenue = float((w * rev).sum())
    rev_k = float((w * rev)[known].sum())
    refunds = float((w * c.refund.values).sum())
    return {
        "revenue": revenue, "gross_profit": float(gp.sum()), "weighted_margin_pct": _pct(gp.sum(), rev_k),
        "refunds": refunds, "net_revenue_after_refunds": revenue - refunds,
        "affected_orders": int(aff.sum()), "expected_retained_orders": float(w[aff].sum()),
        "expected_retained_units": float((w * c.quantity.values).sum()),
        "affected_unknown_cost_orders": int((aff & ~known).sum()),
    }


def break_even(c, cap):
    """Lowest retention (%) at which the cap keeps gross profit, and revenue, at or above baseline."""
    capf = cap / 100.0
    aff = c.discount.values > capf + 1e-12
    known = c.cost_known.values
    orig = c.revenue.values
    capped = c.list_rev.values * (1 - capf)
    cogs = np.where(known, c.cogs.values, 0.0)
    out = {}
    for name, a_orig, a_cap in (("gross_profit", (orig - cogs)[aff & known].sum(), (capped - cogs)[aff & known].sum()),
                                ("revenue", orig[aff].sum(), capped[aff].sum())):
        if not aff.any() or a_orig <= 0:
            val = 0.0
        elif a_cap <= 0:
            val = None
        else:
            val = 100.0 * a_orig / a_cap
            val = None if val > 100 + TOL else val
        out[name] = None if val is None else round(val, 2)
        out[f"{name}_whole"] = None if val is None else int(math.ceil(val - 1e-9))
    return out


def pricing_eligible(m, base):
    return (_ge(m["revenue"], base["revenue"]) and _ge(m["gross_profit"], base["gross_profit"])
            and m["weighted_margin_pct"] is not None and _ge(m["weighted_margin_pct"], base["weighted_margin_pct"]))


def pricing_sweep(ds: Dataset, retention=100):
    c = _cohort(ds)
    base = pricing_metrics(c, 1000, 100)  # cap above every discount = policy off
    rows = [dict({"parameter": "off", "cap": None}, **base, eligible=True)]
    for cap in range(0, 101):
        m = pricing_metrics(c, cap, retention)
        rows.append(dict({"parameter": cap, "cap": cap}, **m, eligible=pricing_eligible(m, base)))
    cands = [r for r in rows if r["eligible"]]
    best = sorted(cands, key=lambda r: (-r["gross_profit"], -r["revenue"], -(r["weighted_margin_pct"] or -1e9),
                                        -(r["cap"] if r["cap"] is not None else 1e9)))[0]
    for r in rows:
        r["selected"] = r is best
    return rows, best, base


def pricing_scenario(ds: Dataset, enabled=True, cap=None, retention=100, recommended=None):
    c = _cohort(ds)
    base = pricing_metrics(c, 1000, 100)
    rec_cap = (recommended or {}).get("cap")
    cp = cap if cap is not None else (rec_cap if rec_cap is not None else 25)
    sel = pricing_metrics(c, cp, retention) if enabled else dict(base)
    aff, w, rev = _pricing_arrays(c, cp, retention)
    by_rep = []
    if enabled and aff.any():
        a = c[aff].assign(new_rev=w[aff] * rev[aff])
        g = a.groupby(a.sales_rep.fillna("Online (no rep)")).agg(orders=("order_id", "size"), revenue_before=("revenue", "sum"),
                                                                   revenue_after=("new_rev", "sum"))
        g["revenue_change"] = g.revenue_after - g.revenue_before
        by_rep = [{"rep": k, "orders": int(v.orders), "revenue_before": round(float(v.revenue_before), 2),
                   "revenue_after": round(float(v.revenue_after), 2), "revenue_change": round(float(v.revenue_change), 2)}
                  for k, v in g.sort_values("orders", ascending=False).iterrows()]
    known = c.cost_known
    return {
        "module": "pricing_policy", "label": "Discount cap", "status": "ok", "enabled": bool(enabled),
        "period": "Jan-Sep 2026", "scope": "All valid orders (every segment, every rep). The quarter-end What if is a separate, narrower view.",
        "controls": [
            {"id": "cap", "label": "Discount cap", "kind": "policy", "min": 0, "max": 100, "step": 1, "unit": "%",
             "value": cp, "recommended": rec_cap, "read_only": False},
            {"id": "retention", "label": "Affected-order retention", "kind": "assumption", "min": 0, "max": 100, "step": 1, "unit": "%",
             "value": retention, "recommended": 100, "read_only": False},
        ],
        "recommended": recommended,
        "baseline": _round(base), "selected": _round(sel), "delta": _round(_delta(sel, base)),
        "coverage": {"orders": int(len(c)), "known_cost_orders": int(known.sum()), "unknown_cost_orders": int((~known).sum()),
                     "known_cost_pct": round(100 * float(known.mean()), 1),
                     "affected_unknown_cost_orders": sel.get("affected_unknown_cost_orders", 0)},
        "details": {"break_even_retention": break_even(c, cp) if enabled else None, "by_rep": by_rep},
        "assumptions": COMMON_ASSUMPTIONS + [
            "Orders with a discount strictly above the cap are sold at the cap; orders at or below it are unchanged.",
            "Quantity, list price and unit cost stay fixed. Retention weights the affected orders' revenue, product cost and refunds; "
            "rejected orders are not fulfilled and carry no product cost.",
            "Recorded refunds stay as they were per retained order (simplifying assumption; a real refund would follow the new price).",
            "At 100% retention a lower cap mechanically raises revenue at unchanged volume: an accounting scenario, not a demand forecast.",
        ],
        "notes": ["break_even_retention: the lowest retention at which this cap keeps gross profit (or revenue) at or above baseline."],
    }


# ================================================================ credit_policy (detection only)
def credit_detect(ds: Dataset, allowance=60):
    o = ds.orders
    inv = o[(o.terms_days > 0) & o.payment_date.isna()].copy()
    inv["days_past_due"] = (EXTRACTED_ON - inv.due_date).dt.days
    over = inv[inv.days_past_due > 0]
    g = allowance
    p = max(1, math.ceil(g / 2))
    flagged = over[over.days_past_due > g]
    accounts = []
    for cid, f in flagged.groupby("customer_id"):
        start = (f.due_date + pd.Timedelta(days=g)).min()  # probation starts when the first invoice crosses due + G
        later = over[(over.customer_id == cid) & (over.order_date > start) & (over.days_past_due > p)]
        cust = ds.customers.set_index("customer_id").loc[cid]
        owed = float(over[over.customer_id == cid].revenue.sum())
        open_balance = float(inv[inv.customer_id == cid].revenue.sum())  # every unpaid invoice, due or not
        second_ids, first_ids = set(later.order_id), set(f.order_id)
        accounts.append({"customer_id": cid, "segment": cust.segment, "region": cust.region, "rep": cust.account_rep,
                         "credit_limit": float(cust.credit_limit), "owed_overdue": round(owed, 2), "open_balance": round(open_balance, 2),
                         "within_credit_limit": bool(open_balance <= cust.credit_limit),
                         "state": "restricted_recommended" if len(later) else "probation",
                         "probation_since": f"{start:%Y-%m-%d}",
                         "invoices": [{"order_id": r.order_id, "order_date": f"{r.order_date:%Y-%m-%d}", "due_date": f"{r.due_date:%Y-%m-%d}",
                                       "days_past_due": int(r.days_past_due), "amount": round(float(r.revenue), 2),
                                       "offense": "second" if r.order_id in second_ids else ("first" if r.order_id in first_ids else None)}
                                      for r in over[over.customer_id == cid].sort_values("due_date").itertuples()]})
    base = {"overdue_invoices": int(len(over)), "overdue_exposure": float(over.revenue.sum()),
            "over_90_exposure": float(over[over.days_past_due > 90].revenue.sum()),
            "over_90_invoices": int((over.days_past_due > 90).sum()), "accounts_overdue": int(over.customer_id.nunique())}
    sel = dict(base, flagged_accounts=len(accounts), flagged_invoices=int(len(flagged)),
               flagged_exposure=float(sum(a["owed_overdue"] for a in accounts)),
               second_offense_accounts=sum(1 for a in accounts if a["state"] == "restricted_recommended"),
               flagged_within_credit_limit=sum(1 for a in accounts if a["within_credit_limit"]))
    return base, sel, accounts, p


def credit_scenario(ds: Dataset, enabled=True, allowance=None, recommended=None):
    g = allowance if allowance is not None else CREDIT_PROVISIONAL_G
    base, sel, accounts, p = credit_detect(ds, g)
    if not enabled:
        sel, accounts = dict(base, flagged_accounts=0, flagged_invoices=0, flagged_exposure=0.0, second_offense_accounts=0,
                             flagged_within_credit_limit=0), []
    o = ds.orders
    paid = o[(o.terms_days > 0) & o.payment_date.notna()]
    late = (paid.payment_date - paid.due_date).dt.days
    return {
        "module": "credit_policy", "label": "Credit escalation", "status": "detection_only", "enabled": bool(enabled),
        "period": "Snapshot 2026-10-31", "scope": "Business invoices on Net 30 / Net 60 terms, unpaid at the snapshot",
        "controls": [
            {"id": "allowance", "label": "First escalation allowance G", "kind": "policy", "min": 1, "max": 180, "step": 1, "unit": "days",
             "value": g, "recommended": CREDIT_PROVISIONAL_G, "read_only": False, "provisional": True},
            {"id": "probation_allowance", "label": "Probation allowance", "kind": "derived", "min": 1, "max": 90, "step": 1,
             "unit": "days", "value": p, "recommended": max(1, math.ceil(CREDIT_PROVISIONAL_G / 2)), "read_only": True},
            {"id": "second_offense_action", "label": "Second-offense action", "kind": "policy", "options": ["prepayment", "full_ban"],
             "value": "prepayment", "recommended": "prepayment", "read_only": True, "deferred": True},
            {"id": "prepayment_acceptance", "label": "Prepayment acceptance", "kind": "assumption", "min": 0, "max": 100, "step": 1,
             "unit": "%", "value": 100, "recommended": 100, "read_only": True, "deferred": True},
        ],
        "recommended": recommended,
        "baseline": _round(base), "selected": _round(sel), "delta": {},
        "coverage": {"invoices_unpaid": int(((o.terms_days > 0) & o.payment_date.isna()).sum()),
                     "paid_invoices_context": int(len(paid)), "paid_late_pct": round(100 * float((late > 0).mean()), 1),
                     "paid_mean_days_late": round(float(late[late > 0].mean()), 1)},
        "details": {"accounts": accounts},
        "assumptions": COMMON_ASSUMPTIONS[:2] + [
            "Detection only: an account is flagged when an invoice is still unpaid more than G days after its due date at the snapshot.",
            "The 60-day allowance is provisional, not optimized: the chronological replay that would select it is deferred.",
            "Probation halves the allowance for later invoices (max(1, ceil(G/2)) days); payment terms do not change.",
            "No offense history before the data starts; paid-late history is shown as context only (paid invoices, not censored unpaid ones).",
            "The business reviewer decides actual account treatment after checking payments, returns and disputes.",
        ],
        "notes": ["No counterfactual yet, so there is no delta: selected shows what the rule flags today."],
    }


# ================================================================ credit_policy: chronological replay
REPLAY_START = pd.Timestamp("2025-01-01")


def credit_states(ds: Dataset, allowance):
    """Per account: probation date P and restriction date R under allowance G, from events known on each date.
    Same-day order: payments, then escalation checks, then new orders (an order on the check date counts as later).
    An invoice crosses when it is still unpaid on its check date (payment after the check, or unpaid at the snapshot)."""
    g = allowance
    p = max(1, math.ceil(g / 2))
    inv = ds.orders[ds.orders.terms_days > 0][["order_id", "customer_id", "order_date", "due_date", "payment_date"]]
    chk = inv.due_date + pd.Timedelta(days=g)
    crossed = (chk <= EXTRACTED_ON) & (inv.payment_date.isna() | (inv.payment_date > chk))
    P = chk[crossed].groupby(inv.customer_id[crossed]).min()
    pstart = inv.customer_id.map(P)
    chk2 = inv.due_date + pd.Timedelta(days=p)
    later = pstart.notna() & (inv.order_date >= pstart)
    crossed2 = later & (chk2 <= EXTRACTED_ON) & (inv.payment_date.isna() | (inv.payment_date > chk2))
    R = chk2[crossed2].groupby(inv.customer_id[crossed2]).min()
    return P, R, p


def credit_metrics(ds: Dataset, R, action, acceptance):
    """Jan-Sep 2026 sales effects and 2026-10-31 exposure once accounts are restricted from date R on."""
    o = ds.orders
    rdate = pd.to_datetime(o.customer_id.map(R.to_dict())) if len(R) else pd.Series(pd.NaT, index=o.index, dtype="datetime64[ns]")
    restricted = rdate.notna() & (o.order_date >= rdate) & (o.terms_days > 0)
    a = acceptance / 100.0
    w = np.where(restricted, 0.0 if action == "full_ban" else a, 1.0)
    # restricted orders that go ahead are prepaid at order date, so they never sit unpaid
    unpaid = o.payment_date.isna().values & (o.terms_days > 0).values & ~restricted.values
    overdue = unpaid & ((EXTRACTED_ON - o.due_date).dt.days.values > 0)
    win = ((o.order_date.dt.year == 2026) & (o.order_date.dt.month <= 9)).values
    known = o.cost_known.values
    rev = o.revenue.values
    gp = np.where(known, o.gp.values, 0.0)
    revenue = float((w * rev)[win].sum())
    gpw = float((w * gp)[win].sum())
    rev_k = float((w * rev)[win & known].sum())
    refunds = float((w * o.refund.values)[win].sum())
    restricted_rev = float(rev[restricted.values & win].sum())
    return {
        "revenue": revenue, "gross_profit": gpw, "weighted_margin_pct": _pct(gpw, rev_k), "refunds": refunds,
        "net_revenue_after_refunds": revenue - refunds,
        "overdue_exposure": float(rev[overdue].sum()), "open_exposure": float(rev[unpaid].sum()),
        "restricted_accounts": int(R.size), "restricted_orders": int((restricted.values & win).sum()),
        "prepaid_revenue": 0.0 if action == "full_ban" else a * restricted_rev,
        "forgone_revenue": restricted_rev if action == "full_ban" else (1 - a) * restricted_rev,
    }


def credit_eligible(m, base):
    return (_ge(m["revenue"], base["revenue"]) and _ge(m["gross_profit"], base["gross_profit"])
            and m["weighted_margin_pct"] is not None and _ge(m["weighted_margin_pct"], base["weighted_margin_pct"]))


def credit_sweep(ds: Dataset, acceptance=100):
    empty = pd.Series(dtype="datetime64[ns]")
    base = credit_metrics(ds, empty, "prepayment", acceptance)
    rows = [dict({"parameter": "off", "allowance": None, "action": None, "probation_accounts": 0}, **base, eligible=True)]
    for g in range(1, 181):
        P, R, _ = credit_states(ds, g)
        for action in ("prepayment", "full_ban"):
            m = credit_metrics(ds, R, action, acceptance)
            rows.append(dict({"parameter": f"{g}|{action}", "allowance": g, "action": action, "probation_accounts": int(P.size)},
                             **m, eligible=credit_eligible(m, base)))
    cands = [r for r in rows if r["eligible"]]
    # min overdue exposure; ties: lower open exposure, fewer restricted accounts, longer allowance, prepayment over ban;
    # policy off preferred when outcomes are otherwise identical
    def key(r):
        same_as_off = (abs(r["overdue_exposure"] - base["overdue_exposure"]) < TOL and abs(r["open_exposure"] - base["open_exposure"]) < TOL)
        return (r["overdue_exposure"], r["open_exposure"], r["restricted_accounts"], 0 if (r["allowance"] is None and same_as_off) else 1,
                -(r["allowance"] or 1e9), 0 if r["action"] in (None, "prepayment") else 1)
    best = sorted(cands, key=key)[0]
    for r in rows:
        r["selected"] = r is best
    return rows, best, base


def credit_replay_scenario(ds: Dataset, enabled=True, allowance=None, action=None, acceptance=100, recommended=None):
    rec = recommended or {}
    g = allowance if allowance is not None else (rec.get("allowance") or CREDIT_PROVISIONAL_G)
    act = action or rec.get("action") or "prepayment"
    empty = pd.Series(dtype="datetime64[ns]")
    base = credit_metrics(ds, empty, "prepayment", 100)
    P, R, p = credit_states(ds, g)
    sel = credit_metrics(ds, R, act, acceptance) if enabled else dict(base)
    det_base, det_sel, det_accounts, _ = credit_detect(ds, g)
    cust = ds.customers.set_index("customer_id")
    acc = []
    if enabled:
        for cid in sorted(set(P.index)):
            r = R.get(cid)
            acc.append({"customer_id": cid, "segment": cust.loc[cid, "segment"], "rep": cust.loc[cid, "account_rep"],
                        "probation_since": f"{P[cid]:%Y-%m-%d}", "restricted_since": None if r is None or pd.isna(r) else f"{r:%Y-%m-%d}",
                        "state": "restricted" if r is not None and not pd.isna(r) else "probation"})
    before_2026 = int((R < pd.Timestamp("2026-01-01")).sum()) if enabled else 0
    o = ds.orders
    paid = o[(o.terms_days > 0) & o.payment_date.notna()]
    late = (paid.payment_date - paid.due_date).dt.days
    unpaid = o[(o.terms_days > 0) & o.payment_date.isna()]
    aging = (EXTRACTED_ON - unpaid.due_date).dt.days
    return {
        "module": "credit_policy", "label": "Credit escalation", "status": "ok", "enabled": bool(enabled),
        "period": "Replay Jan 2025 to 2026-10-31; sales effects Jan-Sep 2026; exposure at 2026-10-31",
        "scope": "Business invoices on Net 30 / Net 60 terms",
        "controls": [
            {"id": "allowance", "label": "First escalation allowance G", "kind": "policy", "min": 1, "max": 180, "step": 1, "unit": "days",
             "value": g, "recommended": rec.get("allowance"), "read_only": False},
            {"id": "probation_allowance", "label": "Probation allowance", "kind": "derived", "min": 1, "max": 90, "step": 1,
             "unit": "days", "value": p, "recommended": None if rec.get("allowance") is None else max(1, math.ceil(rec["allowance"] / 2)),
             "read_only": True},
            {"id": "action", "label": "Second-offense action", "kind": "policy", "options": ["prepayment", "full_ban"],
             "value": act, "recommended": rec.get("action"), "read_only": False},
            {"id": "acceptance", "label": "Prepayment acceptance", "kind": "assumption", "min": 0, "max": 100, "step": 1, "unit": "%",
             "value": acceptance, "recommended": 100, "read_only": act == "full_ban", "disabled_when": "full_ban"},
        ],
        "recommended": recommended,
        "baseline": _round(base), "selected": _round(sel), "delta": _round(_delta(sel, base)),
        "coverage": {"credit_invoices": int((o.terms_days > 0).sum()), "known_cost_pct": round(100 * float(o.cost_known.mean()), 1),
                     "paid_invoices": int(len(paid)), "paid_late_pct": round(100 * float((late > 0).mean()), 1),
                     "paid_mean_days_late": round(float(late[late > 0].mean()), 1),
                     "unpaid_invoices": int(len(unpaid)), "unpaid_past_due": int((aging > 0).sum()),
                     "unpaid_median_days_past_due": float(aging[aging > 0].median()) if (aging > 0).any() else 0.0},
        "details": {"replay_accounts": acc, "restricted_before_2026": before_2026,
                    "probation_accounts": int(P.size) if enabled else 0,
                    "snapshot_detection": {"selected": _round(det_sel), "accounts": det_accounts}},
        "assumptions": COMMON_ASSUMPTIONS[:2] + [
            "Chronological replay from Jan 2025: each date processes payments, then escalation checks, then new orders; only events known on that date are used.",
            "First offense: an invoice still unpaid at due date + G. Probation halves the allowance for invoices placed afterwards; payment terms do not change.",
            "Second offense: an invoice placed after probation began still unpaid at due date + max(1, ceil(G/2)). Restriction persists to the end of the data.",
            "No offense history before the data starts. Existing payment dates are full settlement. Old overdue debt is not assumed recovered.",
            "Prepayment: later orders go ahead, paid at order date, weighted by prepayment acceptance (100% is optimistic). Full ban: later orders, their cost, payments and returns are removed.",
            "Paid lateness (paid invoices) and unpaid aging (censored at the snapshot) are shown separately; a lower average after a ban is a selection effect.",
        ],
        "notes": [f"{before_2026} account(s) were already restricted before 2026 in this replay." if enabled else "Policy off."],
    }


# ================================================================ batch: sweeps, defaults, persistence
def data_hashes():
    return {f: hashlib.sha256((CLEAN / f).read_bytes()).hexdigest() for f in ("customers.csv", "orders.csv", "returns.csv")}


def _reason_pricing(best, base):
    if best["cap"] is None:
        return "No cap keeps revenue, gross profit and weighted margin at or above baseline: policy off."
    return (f"Cap {best['cap']}% at 100% retention: highest gross profit ({fmt_money(best['gross_profit'])} vs "
            f"{fmt_money(base['gross_profit'])} baseline) among caps that do not reduce revenue, gross profit or weighted margin. "
            "At 100% retention with fixed quantities and costs, a lower cap mechanically raises revenue and gross profit: "
            "a boundary result of that assumption, not a demand forecast.")


def _reason_damage(best, base):
    if best["trigger"] is None or best["targeted_groups"] == 0:
        return "No trigger improves contribution at 25% effectiveness and CAD 5 per unit: policy off."
    return (f"Trigger {best['trigger']}% (strictly above, at least {MIN_ORDERS} orders) targets {best['targeted_groups']} group(s), "
            f"{best['targeted_units']} units: highest known-cost contribution ({fmt_money(best['contribution'])} vs "
            f"{fmt_money(base['contribution'])}) at the starting assumptions of 25% damage-refund reduction and CAD 5 per shipped unit; "
            "ties go to fewer targeted shipments, then the higher trigger.")


def _reason_credit(best, base):
    if best["allowance"] is None:
        return "No allowance lowers overdue exposure without cutting revenue, gross profit or margin: policy off."
    return (f"G = {best['allowance']} days with {best['action']} at 100% prepayment acceptance: lowest overdue exposure at "
            f"2026-10-31 ({fmt_money(best['overdue_exposure'])} vs {fmt_money(base['overdue_exposure'])}) among settings that keep "
            f"Jan-Sep 2026 revenue, gross profit and margin at baseline; {best['restricted_accounts']} accounts restricted. "
            "With 100% prepayment acceptance, restriction costs no sales, so the shortest allowance wins: a boundary result of that "
            "optimistic assumption. A full ban loses revenue and is never eligible.")


def run_batch(ds: Dataset, write=True):
    p_rows, p_best, p_base = pricing_sweep(ds)
    d_rows, d_best, d_base = damage_sweep(ds, **DAMAGE_START)
    c_rows, c_best, c_base = credit_sweep(ds)
    p_params = {"cap": p_best["cap"] if p_best["cap"] is not None else 100, "retention": 100}
    d_params = {"trigger": d_best["trigger"] if d_best["trigger"] is not None else 100, **DAMAGE_START}
    c_params = {"allowance": c_best["allowance"] if c_best["allowance"] is not None else 180,
                "action": c_best["action"] or "prepayment", "acceptance": 100}
    defaults = {
        "model_version": MODEL_VERSION, "generated_at": datetime.now().isoformat(timespec="seconds"),
        "data_hashes": data_hashes(), "scope": "Pricing and damage: orders Jan-Sep 2026. Credit: replay from Jan 2025, sales effects Jan-Sep 2026, exposure at 2026-10-31.",
        "assumptions": COMMON_ASSUMPTIONS,
        "evaluation": {"orders_from": "2026-01-01", "orders_to": "2026-09-30", "observed_to": f"{EXTRACTED_ON:%Y-%m-%d}"},
        "modules": {
            "pricing_policy": {"status": "ok", "controls": {"cap": [0, 100, 1], "retention": [0, 100, 1]},
                               "selected_parameters": p_params, "baseline_metrics": _round(p_base), "selected_metrics": _round(p_best),
                               "deltas": _round(_delta(p_best, p_base)), "selection_reason": _reason_pricing(p_best, p_base),
                               "objective": "Keep revenue, gross profit and weighted margin >= baseline; max gross profit, then revenue, then margin; ties: higher cap."},
            "damage_policy": {"status": "ok", "controls": {"trigger": [0, 100, 1], "effectiveness": [0, 100, 1], "cost": [0, 20, 1]},
                              "selected_parameters": d_params, "baseline_metrics": _round(d_base), "selected_metrics": _round(d_best),
                              "deltas": _round(_delta(d_best, d_base)), "selection_reason": _reason_damage(d_best, d_base),
                              "objective": "Keep net revenue after refunds, contribution and contribution margin >= baseline; max contribution, then net revenue, then margin; ties: fewer targeted units, then higher trigger."},
            "credit_policy": {"status": "ok", "controls": {"allowance": [1, 180, 1], "action": ["prepayment", "full_ban"], "acceptance": [0, 100, 1]},
                              "selected_parameters": c_params, "baseline_metrics": _round(c_base), "selected_metrics": _round(c_best),
                              "deltas": _round(_delta(c_best, c_base)), "selection_reason": _reason_credit(c_best, c_base),
                              "objective": "Keep Jan-Sep 2026 revenue, gross profit and weighted margin >= baseline; min overdue exposure at 2026-10-31; ties: lower open exposure, fewer restricted accounts, longer allowance, prepayment over ban; policy off preferred when identical."},
        },
    }
    for m in defaults["modules"].values():
        for k in ("selected_metrics",):
            if m.get(k):
                m[k] = {kk: vv for kk, vv in m[k].items() if kk not in ("parameter", "eligible", "selected")}
    if write:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "defaults.json").write_text(json.dumps(defaults, indent=2), encoding="utf-8")
        keys = sorted({k for r in p_rows + d_rows + c_rows for k in r})
        lead = ["module", "parameter", "eligible", "selected"]
        with open(OUT / "sweep_results.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=lead + [k for k in keys if k not in lead], lineterminator="\n")
            w.writeheader()
            for mod, rows in (("pricing_policy", p_rows), ("damage_policy", d_rows), ("credit_policy", c_rows)):
                for r in rows:
                    w.writerow(dict({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}, module=mod))
    return defaults


def load_defaults(ds: Dataset):
    """Saved defaults when the data hashes match; otherwise run the batch once and save it."""
    path = OUT / "defaults.json"
    if path.exists():
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            if d.get("data_hashes") == data_hashes() and d.get("model_version") == MODEL_VERSION:
                return d
        except json.JSONDecodeError:
            pass
    return run_batch(ds)


def recommended_block(defaults, module):
    m = defaults["modules"][module]
    return {"parameters": m["selected_parameters"], "label": "Best modeled setting at the starting assumptions"
            if m["status"] == "ok" else "Provisional setting (not optimized)", "selection_reason": m["selection_reason"],
            **m["selected_parameters"]}


def sweep_rows(module):
    path = OUT / "sweep_results.csv"
    if not path.exists():
        return []
    df = pd.read_csv(path)
    df = df[df.module == module].drop(columns=["module"]).dropna(axis=1, how="all")
    return json.loads(df.to_json(orient="records"))


if __name__ == "__main__":
    from .pipeline import load
    d = run_batch(load())
    print(json.dumps({k: {"selected": v["selected_parameters"], "reason": v["selection_reason"]} for k, v in d["modules"].items()}, indent=1))
