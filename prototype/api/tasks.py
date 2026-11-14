"""In-app tasks created by "Apply rules to simulation". One task per module + entity (order, product x region group,
account): an identical rerun changes nothing, a rerun with other settings adds an event to the existing task."""
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np

from . import simulator as sim
from .detect import fmt_money
from .pipeline import Dataset

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "state" / "tasks.json"


def _now():
    return datetime.now().isoformat(timespec="seconds")


def load():
    if STORE.exists():
        try:
            return json.loads(STORE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save(tasks):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(tasks), encoding="utf-8")


def reset():
    _save({})


def _upsert(tasks, t, counts):
    old = tasks.get(t["id"])
    if old is None:
        t.update(status="open", created_at=_now(),
                 events=[{"ts": _now(), "ts_precision": "second", "action": "created",
                          "detail": f"Created by Apply rules at {_fmt_params(t['parameters'])}"}])
        tasks[t["id"]] = t
        counts["created"] += 1
        return t
    if old["parameters"] == t["parameters"]:
        counts["unchanged"] += 1
        return None
    old["events"].append({"ts": _now(), "ts_precision": "second", "action": "re-evaluated",
                          "detail": f"Still triggered at {_fmt_params(t['parameters'])} (was {_fmt_params(old['parameters'])})"})
    for k in ("parameters", "title", "explanation", "source_records", "proposed_mitigation"):
        old[k] = t[k]
    counts["updated"] += 1
    return old


def _fmt_params(p):
    return ", ".join(f"{k} {v}" for k, v in p.items())


# ---------------------------------------------------------------- per module
def pricing_tasks(ds: Dataset, cap, retention):
    c = sim._cohort(ds)
    capf = cap / 100.0
    aff = c[c.discount > capf + 1e-12]
    out = []
    for r in aff.itertuples():
        old_unit = r.unit_price * (1 - r.discount)
        new_unit = r.unit_price * (1 - capf)
        if r.cost_known:
            m_old = 100 * (old_unit - r.unit_cost) / old_unit if old_unit else None
            m_new = 100 * (new_unit - r.unit_cost) / new_unit if new_unit else None
            margin = f"Known-cost margin {m_old:.1f}% at the old price, {m_new:.1f}% at the cap."
        else:
            margin = "Unit cost unknown: add a cost review before approving."
        out.append({
            "id": f"pricing_policy:{r.order_id}", "module": "pricing_policy", "entity_type": "order", "entity_id": r.order_id,
            "owner_role": "Sales manager",
            "title": f"Pricing review: {r.order_id} at {100 * r.discount:.1f}% off (cap {cap}%)",
            "explanation": (f"{r.order_id} ({r.order_date:%Y-%m-%d}, {r.segment} {r.customer_id}, rep {r.sales_rep if isinstance(r.sales_rep, str) else 'online'}): "
                            f"{r.quantity} x {r.product}. Unit price {fmt_money(old_unit)} at {100 * r.discount:.1f}% off, "
                            f"{fmt_money(new_unit)} at the {cap}% cap. {margin}"),
            "proposed_mitigation": "Approve the order at the cap, or record why a deeper discount is needed.",
            "source_records": [r.order_id],
            "parameters": {"cap": cap, "retention": retention},
            "reasons": ["discount above cap"] + ([] if r.cost_known else ["cost review: unit cost unknown"]),
        })
    return out


CHECKLIST = ["Reinforced packaging for this product on this route", "Pre-dispatch inspection with photo record",
             "Corner and edge protection for flat-pack furniture", "Carrier follow-up: carrier data is not in the dataset, investigate separately"]


def damage_tasks(ds: Dataset, trigger, effectiveness, cost):
    c = sim._cohort(ds)
    groups = sim.damage_groups(c)
    out = []
    for key in sorted(sim.damage_targets(groups, trigger)):
        p, reg = key
        g = groups.loc[key]
        sub = c[(c["product"] == p) & (c.region == reg)]
        dmg = sub[(sub.return_reason == sim.DAMAGE) & sub.returned]
        rets = ds.returns[ds.returns.order_id.isin(dmg.order_id)].return_id.tolist()
        expected = effectiveness / 100 * float(g.damage_refunds) - cost * int(g.units)
        out.append({
            "id": f"damage_policy:{p}|{reg}", "module": "damage_policy", "entity_type": "group", "entity_id": f"{p}|{reg}",
            "owner_role": "Operations",
            "title": f"Damage prevention: {p} to {reg}",
            "explanation": (f"{int(g.damage_orders)} of {int(g.orders)} orders ({100 * float(g.damage_rate):.1f}%) came back damaged in transit "
                            f"in Jan-Sep 2026, {fmt_money(float(g.damage_refunds))} refunded, {int(g.units)} units shipped. "
                            f"At {effectiveness}% fewer damage refunds and CAD {cost} per unit, the modeled benefit is {fmt_money(expected)}."),
            "proposed_mitigation": "; ".join(CHECKLIST),
            "source_records": dmg.order_id.tolist() + rets,
            "parameters": {"trigger": trigger, "effectiveness": effectiveness, "cost": cost},
            "affected_orders": int(g.orders), "damage_refunds": round(float(g.damage_refunds), 2),
        })
    return out


def credit_tasks(ds: Dataset, allowance):
    _, _, accounts, p = sim.credit_detect(ds, allowance)
    out = []
    for a in accounts:
        inv = a["invoices"]
        worst = max(i["days_past_due"] for i in inv)
        out.append({
            "id": f"credit_policy:{a['customer_id']}", "module": "credit_policy", "entity_type": "account", "entity_id": a["customer_id"],
            "owner_role": "Finance",
            "title": f"Credit case: {a['segment']} {a['customer_id']} ({'restriction recommended' if a['state'] == 'restricted_recommended' else 'probation'})",
            "explanation": (f"{len(inv)} overdue invoice(s), {fmt_money(a['owed_overdue'])} overdue, oldest {worst} days past due "
                            f"(allowance {allowance} days, probation allowance {p} days). Open balance {fmt_money(a['open_balance'])} "
                            f"on a {fmt_money(a['credit_limit'])} limit. Account rep {a['rep']}."),
            "proposed_mitigation": ("Review payments, returns and disputes, then decide: " +
                                    ("new purchases on prepayment only." if a["state"] == "restricted_recommended"
                                     else "probation (shorter escalation window on later invoices).")),
            "recommended_communication": (f"Template text: Hello, our records show {len(inv)} invoice(s) totalling {fmt_money(a['owed_overdue'])} "
                                          f"past due, the oldest by {worst} days. Please let us know the expected payment date or any "
                                          f"dispute so we can keep your account in good standing. Regards, {a['rep']} and Chrome & Oak Finance."),
            "source_records": [i["order_id"] for i in inv],
            "parameters": {"allowance": allowance},
            "assigned_rep": a["rep"], "state": a["state"],
        })
    return out


def apply(ds: Dataset, body):
    tasks = load()
    res = {"created": 0, "updated": 0, "unchanged": 0, "by_module": {}, "tasks": []}
    plans = []
    pr, dm, cr = body.get("pricing"), body.get("damage"), body.get("credit")
    if pr and pr.get("enabled", True):
        plans.append(("pricing_policy", pricing_tasks(ds, int(pr.get("cap", 0)), int(pr.get("retention", 100)))))
    if dm and dm.get("enabled", True):
        plans.append(("damage_policy", damage_tasks(ds, int(dm.get("trigger", 10)), int(dm.get("effectiveness", 25)), int(dm.get("cost", 5)))))
    if cr and cr.get("enabled", True):
        plans.append(("credit_policy", credit_tasks(ds, int(cr.get("allowance", sim.CREDIT_PROVISIONAL_G)))))
    for module, items in plans:
        counts = {"created": 0, "updated": 0, "unchanged": 0}
        for t in items:
            changed = _upsert(tasks, t, counts)
            if changed is not None and len(res["tasks"]) < 50:
                res["tasks"].append(changed)
        res["by_module"][module] = counts
        for k in counts:
            res[k] += counts[k]
    _save(tasks)
    return json.loads(json.dumps(res, default=lambda o: o.item() if isinstance(o, np.generic) else str(o)))


def listing(module=None, status=None, owner=None, limit=None):
    out = sorted(load().values(), key=lambda t: t["events"][-1]["ts"], reverse=True)
    for field, want in (("module", module), ("status", status), ("owner_role", owner)):
        if want:
            out = [t for t in out if t.get(field) == want]
    return out[:limit] if limit else out


def _finite(x):
    return x if not (isinstance(x, float) and math.isnan(x)) else None
