"""Forecast for the What if page: today's policy vs the rules on, quarter by quarter, plus a run-rate for the next
two quarters. Pricing and damage replay together on the same orders; credit is reported as its own KPI.
A run-rate, not a model."""
import numpy as np
import pandas as pd

from . import simulator as sim
from .pipeline import Dataset

METRICS = ["revenue", "gross_profit", "refunds", "profit_after_refunds"]
FORECAST_QUARTERS = {"2026Q4": "2025Q4", "2027Q1": "2026Q1"}  # forecast quarter -> same quarter a year earlier


def _rows(ds: Dataset, pricing, damage):
    """Per order: weighted revenue, gross profit (known cost), refunds and packaging cost with the rules applied."""
    o = ds.orders
    n = len(o)
    w = np.ones(n)
    rev = o.revenue.values.astype(float).copy()
    if pricing:
        capf = pricing["cap"] / 100.0
        aff = o.discount.values > capf + 1e-12
        w = np.where(aff, pricing["retention"] / 100.0, 1.0)
        rev = np.where(aff, o.list_rev.values * (1 - capf), rev)
    known = o.cost_known.values
    gp = np.where(known, rev - np.where(known, o.cogs.values, 0.0), 0.0)
    refund = o.refund.values.astype(float).copy()
    icost = np.zeros(n)
    if damage:
        groups = sim.damage_groups(sim._cohort(ds, "2026"))
        targeted = sim.damage_targets(groups, damage["trigger"])
        if targeted:
            mask = np.array([k in targeted for k in zip(o["product"], o.region)])
            dmg = ((o.return_reason == sim.DAMAGE) & o.returned).values
            refund = refund - (damage["effectiveness"] / 100.0) * refund * (dmg & mask)
            icost = damage["cost"] * o.quantity.values * mask
    return pd.DataFrame({"quarter": o.quarter.values, "revenue": w * rev, "gross_profit": w * gp,
                         "refunds": w * refund, "icost": w * icost})


def _quarterly(df):
    q = df.groupby("quarter")[["revenue", "gross_profit", "refunds", "icost"]].sum()
    q["profit_after_refunds"] = q.gross_profit - q.refunds - q.icost
    return q[METRICS]


def forecast(ds: Dataset, pricing=None, damage=None, credit=None):
    cur = _quarterly(_rows(ds, None, None))
    rules = _quarterly(_rows(ds, pricing, damage)) if (pricing or damage) else cur.copy()
    actual_q = list(cur.index)
    js25 = cur.loc[[q for q in actual_q if q.startswith("2025") and q[-1] in "123"]].sum()
    js26 = cur.loc[[q for q in actual_q if q.startswith("2026") and q[-1] in "123"]].sum()
    js26r = rules.loc[[q for q in actual_q if q.startswith("2026") and q[-1] in "123"]].sum()
    growth = {m: float(js26[m] / js25[m] - 1) if js25[m] else 0.0 for m in METRICS}
    effect = {m: float(js26r[m] / js26[m]) if js26[m] else 1.0 for m in METRICS}

    series = {m: [] for m in METRICS}
    for q in actual_q:
        for m in METRICS:
            series[m].append({"quarter": q, "kind": "actual", "current": round(float(cur.loc[q, m]), 2),
                              "with_rules": round(float(rules.loc[q, m]), 2)})
    fc = {}
    for fq, base_q in FORECAST_QUARTERS.items():
        fc[fq] = {}
        for m in METRICS:
            c = float(cur.loc[base_q, m]) * (1 + growth[m])
            r = c * effect[m]
            fc[fq][m] = (c, r)
            series[m].append({"quarter": fq, "kind": "forecast", "current": round(c, 2), "with_rules": round(r, 2)})

    next_q = {m: {"current": round(fc["2026Q4"][m][0], 2), "with_rules": round(fc["2026Q4"][m][1], 2),
                  "delta": round(fc["2026Q4"][m][1] - fc["2026Q4"][m][0], 2)} for m in METRICS}
    replay = {m: {"current": round(float(js26[m]), 2), "with_rules": round(float(js26r[m]), 2),
                  "delta": round(float(js26r[m] - js26[m]), 2)} for m in METRICS}

    empty = pd.Series(dtype="datetime64[ns]")
    base_c = sim.credit_metrics(ds, empty, "prepayment", 100)
    if credit:
        _, R, _ = sim.credit_states(ds, credit["allowance"])
        cm = sim.credit_metrics(ds, R, credit["action"], credit["acceptance"])
    else:
        cm = base_c
    credit_kpi = {"enabled": bool(credit),
                  "overdue_exposure_current": round(base_c["overdue_exposure"], 2), "overdue_exposure_with_rules": round(cm["overdue_exposure"], 2),
                  "overdue_exposure_delta": round(cm["overdue_exposure"] - base_c["overdue_exposure"], 2),
                  "open_exposure_delta": round(cm["open_exposure"] - base_c["open_exposure"], 2),
                  "restricted_accounts": cm["restricted_accounts"],
                  "revenue_effect_jan_sep_2026": round(cm["revenue"] - base_c["revenue"], 2),
                  "gross_profit_effect_jan_sep_2026": round(cm["gross_profit"] - base_c["gross_profit"], 2)}
    return {
        "kind": "run-rate", "provisional": True,
        "params": {"pricing": dict(pricing or {}, enabled=bool(pricing)), "damage": dict(damage or {}, enabled=bool(damage)),
                   "credit": dict(credit or {}, enabled=bool(credit))},
        "quarters": actual_q + list(FORECAST_QUARTERS),
        "series": series,
        "kpis": {"next_quarter": {"quarter": "2026Q4", "metrics": next_q}, "replay_jan_sep_2026": replay, "credit": credit_kpi},
        "growth_used_pct": {m: round(100 * g, 1) for m, g in growth.items()},
        "rules_effect_jan_sep_2026_pct": {m: round(100 * (e - 1), 1) for m, e in effect.items()},
        "method": ("Run-rate, not a model. Forecast quarter = the same quarter a year earlier x (1 + that metric's Jan-Sep 2026 vs "
                   "Jan-Sep 2025 growth). With rules = that run-rate x the rules' relative effect on Jan-Sep 2026."),
        "assumptions": sim.COMMON_ASSUMPTIONS + [
            "Actual quarters with rules: the orders that happened, replayed with the rules on. Pricing first (capped discount, "
            "retention weight), then the damage reduction on the retained orders' damaged-in-transit refunds; each refund counted once.",
            "Damage targets are the product x region groups picked by the trigger on Jan-Sep 2026, applied to every quarter.",
            "Profit after refunds = gross profit (known-cost rows) minus refunds minus packaging cost.",
            "2026Q3 refunds are still maturing: September orders had at most 31 days for returns before the data was extracted.",
            "Seasonality, new customers, price changes and demand response beyond the retention setting are ignored.",
            "Credit restrictions are not in the four lines; their exposure and sales effects are shown in the credit KPI.",
        ],
    }
