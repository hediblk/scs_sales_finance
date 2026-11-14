"""Automated action chains and the action log.

System rows are derived from the alerts (the chain each rule fires on its own, dated when it happened in
the data). User rows (overrides, drafts, triage notes) are stored in data/state/user_actions.json.
"Notify" writes to the in-app outbox: nothing is actually sent.
"""
import json
from datetime import datetime
from pathlib import Path

from . import ai
from .detect import QUOTA_HOLD_DAYS, fmt_money

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "state" / "user_actions.json"


# ---------------------------------------------------------------- user state
def load_user_rows():
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    return []


def _save_user_rows(rows):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(rows, indent=1), encoding="utf-8")


def log(alert_id, action, detail, actor="user", to=None, extra=None):
    row = {"ts": datetime.now().isoformat(timespec="seconds"), "ts_precision": "second", "alert_id": alert_id,
           "actor": actor, "action": action, "detail": detail}
    if to:
        row["to"] = to
    if extra:
        row.update(extra)
    rows = load_user_rows()
    rows.append(row)
    _save_user_rows(rows)
    return row


def reset_user_rows():
    _save_user_rows([])


def overridden_ids():
    return {r["alert_id"]: r for r in load_user_rows() if r["action"] == "override"}


def apply_overrides(alerts):
    ov = overridden_ids()
    for a in alerts:
        if a["id"] in ov:
            a["status"] = "overridden"
            a["override_reason"] = ov[a["id"]]["detail"]
            a["overridden_at"] = ov[a["id"]]["ts"]
    return alerts


# ---------------------------------------------------------------- code triage (decision by rules)
def triage_decision(a):
    """Code decides review_needed and the recommendation. AI only words it."""
    c = a["condition_id"]
    if c == "qe_discount":
        if a.get("below_cost"):
            return True, "escalate", "Sold below cost: the CFO should see it."
        if a.get("prior_overstock_returns", 0) > 0:
            return False, "hold", "Same pattern as earlier orders that came back as overstock: the hold runs its course."
        if a.get("discount_pct", 0) < 28 and a.get("segment") != "Reseller":
            return True, "release", "Close to the threshold on a direct customer: may be a legitimate deal, a manager can release it."
        return False, "hold", "Deep quarter-end discount: the 45-day hold protects the quota until the return window closes."
    if c == "quiet_after_bad_return":
        if a.get("resolution") == "reordered":
            return False, "release", "The customer ordered again: the task can close."
        if a.get("escalated"):
            return True, "escalate", "No reorder within the usual gap: Customer Success should call."
        return False, "hold", "Still inside the usual reorder window: keep the task open."
    if a.get("severity") == "high":
        return True, "escalate", "Long overdue or over the credit limit: finance should follow up."
    return False, "hold", "Watch, no action yet."


def _facts(a):
    lines = [f"Alert: {a['id']} ({a['condition_id']})", f"Account: {a['entity_name']} in {a['region']}",
             f"Account rep: {a['owner']}", f"Amount: {fmt_money(a['amount'])}"]
    lines += [f"- {r}" for r in a["reasons"]]
    return "\n".join(lines)


def triage(a):
    """Advisory note for the sales manager inbox. It never changes the alert: flag, severity, status and hold stay
    exactly as the rule set them. The suggestion comes from plain rules on the facts; AI only words the summary."""
    review, rec, why = triage_decision(a)
    facts = _facts(a) + f"\nDecision by the rules: recommendation {rec}, review needed: {'yes' if review else 'no'}. Reason: {why}"
    fallback = f"{a['entity_name']}: {a['reasons'][0]}.\n{why}"
    text, source = ai.write("triage", facts, fallback, max_tokens=300)
    parts = [p.strip() for p in text.splitlines() if p.strip()]
    summary = parts[0] if parts else fallback
    why_txt = parts[1] if len(parts) > 1 else why
    log(a["id"], "triage", f"Advisory note added ({source}): suggests {rec}. The rule's verdict is unchanged", actor="system")
    return {"summary": summary, "review_needed": review, "why": why_txt, "recommendation": rec, "source": source,
            "advisory": True, "label": "Advisory note. The hold is the rule's decision; this note does not change it."}


# ---------------------------------------------------------------- drafts
def _draft_template(a):
    c = a["condition_id"]
    if c == "qe_discount":
        to = "Sales manager"
        subject = f"Quota credit on hold: {a['order_id']}, {fmt_money(a['amount'])} at {a['discount_pct']}% off"
        body = (f"Hello,\n\nOrder {a['order_id']} by {a['owner']} for {a['entity_name']} was booked on {a['created_at']} "
                f"at a {a['discount_pct']}% discount, in the last days of the quarter. Its quota credit of {fmt_money(a['amount'])} "
                f"is on hold until {a['hold_until']}. If the goods are not returned by then, the credit is released automatically.\n\n"
                "Why it was flagged:\n" + "\n".join(f"- {r}" for r in a["reasons"]) +
                "\n\nYou can release it now from the action queue with a reason.")
    elif c == "quiet_after_bad_return":
        to = f"{a['entity_name']} (customer), from {a['owner']}"
        subject = f"About your recent {a['product']} return"
        problem = {"Damaged in transit": "damage in transit", "Defective": "defect",
                   "Wrong item shipped": "wrong item we shipped"}.get(a["return_reason"], "problem")
        body = (f"Hello,\n\nWe are sorry about the {problem} with your {a['product']} order. "
                f"Your refund of {fmt_money(a['refund'])} has been issued. "
                "Your account rep will call you this week to make sure the replacement or next order arrives in good shape.\n\n"
                f"Thank you for your business,\n{a['owner']}, Chrome & Oak Office Supply")
    else:
        to = a["owner"] or "Accounts receivable"
        subject = f"Overdue balance: {a['entity_name']}, {fmt_money(a['amount'])}"
        body = ("Hello,\n\nThis account needs a follow-up:\n" + "\n".join(f"- {r}" for r in a["reasons"]) +
                "\n\nPlease contact the customer about payment before the next order ships.")
    return to, subject, body


def draft(a):
    to, subject, body = _draft_template(a)
    facts = _facts(a) + f"\nRecipient: {to}\nPurpose: {subject}"
    if a["condition_id"] == "quiet_after_bad_return":
        facts += (f"\nThis is an apology email to the customer about the return. Product: {a['product']}. "
                  f"Reason: {a['return_reason']}. Refund: {fmt_money(a['refund'])}. Signed by account rep {a['owner']}. "
                  "Do not mention internal reasons, thresholds or spend.")
    text, source = ai.write("draft", facts, f"{subject}\n\n{body}")
    first, _, rest = text.partition("\n")
    subj = first.replace("Subject:", "").strip() or subject
    out = {"to": to, "subject": subj, "body": rest.strip() or body, "source": source}
    log(a["id"], "draft", f"Email drafted to {to} ({source})", actor="system", to=to)
    return out


# ---------------------------------------------------------------- system chains
def _ts(day, clock=None, n=None):
    """System rows come from dates in the data, which have no time of day: the timestamp is the date only."""
    return day


def chain(a):
    """The rows the automation writes for one alert, in order."""
    rows = []
    aid, day = a["id"], a["created_at"]
    c = a["condition_id"]
    if c == "qe_discount":
        rows += [
            {"ts": _ts(day), "alert_id": aid, "actor": "system", "action": "flag",
             "detail": f"Rule matched: {a['order_id']} at {a['discount_pct']}% discount, {a['reasons'][1].split(', ', 1)[1]}"},
            {"ts": _ts(day), "alert_id": aid, "actor": "system", "action": "quota_hold",
             "detail": f"Quota credit of {fmt_money(a['amount'])} for {a['owner']} held until {a['hold_until']} ({QUOTA_HOLD_DAYS} days)"},
            {"ts": _ts(day), "alert_id": aid, "actor": "system", "action": "notify", "to": "Sales manager",
             "detail": f"{a['owner']} order {a['order_id']} for {a['entity_name']}: {fmt_money(a['amount'])} at {a['discount_pct']}% off, quota credit on hold"},
            {"ts": _ts(day), "alert_id": aid, "actor": "system", "action": "notify", "to": "CFO",
             "detail": ("Sold below cost. " if a["below_cost"] else "") + f"{fmt_money(a['amount'])} under quota hold"},
        ]
        if a["resolution"] == "returned":
            rows.append({"ts": _ts(a["resolved_on"]), "alert_id": aid, "actor": "system", "action": "resolve",
                         "detail": f"Returned ({a['return_reason']}), {fmt_money(a['refund'])} refunded: quota credit cancelled"})
        elif a["resolution"] == "kept":
            rows.append({"ts": _ts(a["resolved_on"]), "alert_id": aid, "actor": "system", "action": "release",
                         "detail": f"{QUOTA_HOLD_DAYS} days with no return: quota credit of {fmt_money(a['amount'])} released"})
    elif c == "quiet_after_bad_return":
        rows += [
            {"ts": _ts(day), "alert_id": aid, "actor": "system", "action": "flag",
             "detail": f"Rule matched: {a['return_reason'].lower()} on {a['product']} for {a['entity_name']}"},
            {"ts": _ts(day), "alert_id": aid, "actor": "system", "action": "notify", "to": "Customer Success",
             "detail": f"Call task opened for {a['entity_name']} ({fmt_money(a['amount'])} ordered in the last 12 months)"},
            {"ts": _ts(day), "alert_id": aid, "actor": "system", "action": "draft",
             "detail": f"Apology email ready for {a['entity_name']}: built from the order facts, open the alert to see it"},
            {"ts": _ts(day), "alert_id": aid, "actor": "system", "action": "notify", "to": a["owner"] or "Account rep",
             "detail": f"Your customer {a['entity_name']} had a bad return ({fmt_money(a['refund'])} refunded)"},
        ]
        if a["escalated"]:
            rows.append({"ts": _ts(a["escalate_on"]), "alert_id": aid, "actor": "system", "action": "winback_task",
                         "detail": f"No reorder within {a['usual_gap_days']} days (usual gap): win-back task opened"})
        if a["resolution"] in ("reordered", "came_back_late"):
            rows.append({"ts": _ts(a["resolved_on"]), "alert_id": aid, "actor": "system", "action": "resolve",
                         "detail": f"Customer ordered again on {a['resolved_on']}: task closed"})
    else:
        rows.append({"ts": _ts(day), "alert_id": aid, "actor": "system", "action": "flag",
                     "detail": f"Detected: {a['reasons'][0]}; {a['reasons'][2]} (detection only, no automatic action)"})
    for i, r in enumerate(rows):
        r["ts_precision"] = "day"
        r["seq"] = i  # order of the steps within the chain, since same-day rows share a date
    return rows


def all_rows(alerts, condition=None, alert_id=None):
    rows = [r for a in alerts for r in chain(a)]
    known = {a["id"] for a in alerts}
    for r in load_user_rows():
        if r["alert_id"] in known or alert_id == r["alert_id"]:
            rows.append(r)
    if alert_id:
        rows = [r for r in rows if r["alert_id"] == alert_id]
    for r in rows:
        r.setdefault("ts_precision", "second")
    return sorted(rows, key=lambda r: (r["ts"], r.get("seq", 0)), reverse=True)


def override(a, reason):
    """A person overrides the automation: for C1 the quota credit is released now, for C2 the task is closed."""
    log(a["id"], "override", reason, actor="user")
    if a["condition_id"] == "qe_discount":
        log(a["id"], "release", f"Quota credit of {fmt_money(a['amount'])} released by a manager", actor="user")
    else:
        log(a["id"], "resolve", "Closed by a person", actor="user")
    a["status"] = "overridden"
    a["override_reason"] = reason
    return a
