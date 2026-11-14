"""FastAPI app on docs/ui-contract.md.

Run from the project root:
    .venv/Scripts/python.exe -m uvicorn api.main:app --port 8000 --reload
"""
from functools import lru_cache

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import accounts, actions, ai, dataset, detect, story
from . import ask as ask_mod
from . import gap as gap_mod
from . import whatif as whatif_mod
from . import explore as explore_mod
from . import simulator as sim
from . import tasks as tasks_mod
from . import forecast as forecast_mod
from .pipeline import EXTRACTED_ON, load

app = FastAPI(title="Chrome & Oak decision desk")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DS = load()  # reads data/clean as it is; never rewritten by the API
ask_mod.build_db(DS)  # DuckDB copy for Ask, opened read-only per question
SIM_DEFAULTS = sim.load_defaults(DS)  # saved batch when the data hashes match, else the batch runs once here


# ---------------------------------------------------------------- policy simulator (docs/simulator-plan.md)
def _rng(name, v, lo, hi):
    if v is not None and not (lo <= v <= hi):
        raise HTTPException(400, f"{name} must be between {lo} and {hi}")
    return v


@lru_cache(maxsize=2048)
def _sim_pricing(enabled, cap, retention):
    return sim.pricing_scenario(DS, enabled, cap, retention, sim.recommended_block(SIM_DEFAULTS, "pricing_policy"))


@lru_cache(maxsize=2048)
def _sim_damage(enabled, trigger, effectiveness, cost, period):
    return sim.damage_scenario(DS, enabled, trigger, effectiveness, cost, period, sim.recommended_block(SIM_DEFAULTS, "damage_policy"))


@lru_cache(maxsize=2048)
def _sim_credit(enabled, allowance, action=None, acceptance=100):
    return sim.credit_replay_scenario(DS, enabled, allowance, action, acceptance, sim.recommended_block(SIM_DEFAULTS, "credit_policy"))


@app.get("/api/simulator")
def simulator_all():
    p = SIM_DEFAULTS["modules"]
    return {"model_version": SIM_DEFAULTS["model_version"], "data_hashes": SIM_DEFAULTS["data_hashes"],
            "generated_at": SIM_DEFAULTS["generated_at"], "scope": SIM_DEFAULTS["scope"], "assumptions": SIM_DEFAULTS["assumptions"],
            "modules": {"pricing_policy": _sim_pricing(True, *(p["pricing_policy"]["selected_parameters"][k] for k in ("cap", "retention"))),
                        "damage_policy": _sim_damage(True, *(p["damage_policy"]["selected_parameters"][k] for k in ("trigger", "effectiveness", "cost")), "2026"),
                        "credit_policy": _sim_credit(True, *(p["credit_policy"]["selected_parameters"][k] for k in ("allowance", "action", "acceptance")))}}


@app.get("/api/simulator/pricing")
def simulator_pricing(enabled: bool = True, cap: int | None = None, retention: int = 100):
    _rng("cap", cap, 0, 100), _rng("retention", retention, 0, 100)
    return _sim_pricing(enabled, cap, retention)


@app.get("/api/simulator/damage")
def simulator_damage(enabled: bool = True, trigger: int | None = None, effectiveness: int = 25, cost: int = 5, period: str = "2026"):
    _rng("trigger", trigger, 0, 100), _rng("effectiveness", effectiveness, 0, 100), _rng("cost", cost, 0, 20)
    if period not in ("2026", "full"):
        raise HTTPException(400, "period must be 2026 or full")
    return _sim_damage(enabled, trigger, effectiveness, cost, period)


@app.get("/api/simulator/credit")
def simulator_credit(enabled: bool = True, allowance: int | None = None, action: str | None = None, acceptance: int = 100):
    _rng("allowance", allowance, 1, 180), _rng("acceptance", acceptance, 0, 100)
    if action is not None and action not in ("prepayment", "full_ban"):
        raise HTTPException(400, "action must be prepayment or full_ban")
    return _sim_credit(enabled, allowance, action, acceptance)


@lru_cache(maxsize=4096)
def _forecast(pricing, damage, credit):
    return forecast_mod.forecast(DS, dict(pricing) if pricing else None, dict(damage) if damage else None,
                                 dict(credit) if credit else None)


@app.get("/api/forecast")
def forecast(pricing: bool = True, cap: int | None = None, retention: int | None = None,
             damage: bool = True, trigger: int | None = None, effectiveness: int | None = None, cost: int | None = None,
             credit: bool = True, allowance: int | None = None, action: str | None = None, acceptance: int | None = None):
    """What if page: current policy vs rules on, per quarter, plus a run-rate for 2026Q4 and 2027Q1."""
    rec = {k: v["selected_parameters"] for k, v in SIM_DEFAULTS["modules"].items()}
    for name, v, lo, hi in (("cap", cap, 0, 100), ("retention", retention, 0, 100), ("trigger", trigger, 0, 100),
                            ("effectiveness", effectiveness, 0, 100), ("cost", cost, 0, 20), ("allowance", allowance, 1, 180),
                            ("acceptance", acceptance, 0, 100)):
        _rng(name, v, lo, hi)
    if action is not None and action not in ("prepayment", "full_ban"):
        raise HTTPException(400, "action must be prepayment or full_ban")
    pick = lambda v, mod, k: v if v is not None else rec[mod][k]
    p = (("cap", pick(cap, "pricing_policy", "cap")), ("retention", pick(retention, "pricing_policy", "retention"))) if pricing else None
    d = (("trigger", pick(trigger, "damage_policy", "trigger")), ("effectiveness", pick(effectiveness, "damage_policy", "effectiveness")),
         ("cost", pick(cost, "damage_policy", "cost"))) if damage else None
    c = (("allowance", pick(allowance, "credit_policy", "allowance")), ("action", pick(action, "credit_policy", "action")),
         ("acceptance", pick(acceptance, "credit_policy", "acceptance"))) if credit else None
    return _forecast(p, d, c)


@app.get("/api/simulator/sweep/{module}")
def simulator_sweep(module: str):
    mod = {"pricing": "pricing_policy", "damage": "damage_policy", "credit": "credit_policy"}.get(module)
    if not mod:
        raise HTTPException(404, "Sweeps exist for pricing, damage and credit")
    fixed = {"pricing_policy": {"retention": 100}, "damage_policy": sim.DAMAGE_START, "credit_policy": {"acceptance": 100}}[mod]
    return {"module": mod, "fixed_assumptions": fixed, "rows": sim.sweep_rows(mod)}


@app.post("/api/simulator/apply")
def simulator_apply(body: dict = Body(default={})):
    """"Apply rules to simulation": run the condition checks at these settings and create deduplicated in-app tasks."""
    if not any((body or {}).get(k) for k in ("pricing", "damage", "credit")):
        raise HTTPException(400, "Send at least one of pricing, damage, credit")
    return tasks_mod.apply(DS, body or {})


@app.get("/api/tasks")
def tasks_list(module: str | None = None, status: str | None = None, owner: str | None = None, limit: int | None = None):
    return tasks_mod.listing(module, status, owner, limit)


def _defaults(condition, value, window):
    spec = detect.CONDITIONS[condition]
    v = spec["threshold"]["value"] if value is None else value
    w = (spec.get("window") or {}).get("value") if window is None else window
    return v, w


@lru_cache(maxsize=256)
def _alerts_cached(condition, value, window):
    return detect.alerts_for(DS, condition, value, window)


def _alerts(condition, value=None, window=None):
    if condition not in detect.CONDITIONS:
        raise HTTPException(404, f"Unknown condition {condition}. Use one of {list(detect.CONDITIONS)}")
    v, w = _defaults(condition, value, window)
    return actions.apply_overrides([dict(a) for a in _alerts_cached(condition, v, w)])


def _find_alert(alert_id):
    a = detect.alert_by_id(DS, alert_id)
    if a is None:
        raise HTTPException(404, f"No alert {alert_id}")
    return actions.apply_overrides([a])[0]


@app.get("/api/meta")
def meta():
    return {"company": "chrome-oak", "company_name": "Chrome & Oak Office Supply", "extracted_on": f"{EXTRACTED_ON:%Y-%m-%d}",
            "entity_label": "Customer", "owner_label": "Account rep", "period": "Jan 2025 to Sep 2026",
            "ai_enabled": ai.enabled(), "ai_model": ai.MODEL}


# ---------------------------------------------------------------- dataset page (raw / clean, same shapes)
def _ds_call(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except KeyError as e:
        raise HTTPException(404, f"Unknown {e}. Sources: raw, clean. Tables: {list(dataset.TABLES)}")


@app.get("/api/{source}/tables")
def ds_tables(source: str):
    return _ds_call(dataset.tables, source)


@app.get("/api/{source}/charts")
def ds_charts(source: str):
    return _ds_call(dataset.charts, source)


@app.get("/api/clean/set-aside")
def ds_set_aside():
    return dataset.set_aside()


@app.get("/api/{source}/{name}/profile")
def ds_profile(source: str, name: str):
    return _ds_call(dataset.profile, source, name)


@app.get("/api/{source}/{name}/rows")
def ds_rows(source: str, name: str, offset: int = 0, limit: int = 50, q: str = "", col: str = "", val: str = "",
            sort: str = "", desc: bool = False):
    return _ds_call(dataset.rows, source, name, offset, limit, q, col, val, sort, desc)


@app.get("/api/data-prep")
def data_prep():
    files = [dict(f, rows_clean={"orders.csv": len(DS.clean_orders)}.get(f["name"], f["rows"])) for f in DS.files]
    return {"files": files, "steps": DS.steps, "summary": DS.summary}


@lru_cache(maxsize=1)
def _overview():
    return story.overview(DS)


@app.get("/api/overview")
def overview():
    return _overview()


@lru_cache(maxsize=1)
def _gap():
    return gap_mod.gap(DS)


@app.get("/api/gap")
def gap():
    return _gap()


@lru_cache(maxsize=1)
def _insights():
    return story.insights(DS)


@lru_cache(maxsize=1024)
def _explore(metric, by, split, filters, date_from, date_to, highlight, normalize):
    return explore_mod.explore(DS, metric, by, split or None, dict(filters), date_from or None, date_to or None,
                               list(highlight) or None, normalize)


def _csv(v):
    return tuple(sorted(x.strip() for x in v.split(",") if x.strip())) if v else ()


@app.get("/api/explore/options")
def explore_options():
    return explore_mod.options(DS)


@app.get("/api/explore")
def explore(metric: str = "revenue", by: str = "quarter", split: str = "", region: str = "", rep: str = "",
            segment: str = "", product: str = "", category: str = "", date_from: str = Query("", alias="from"),
            date_to: str = Query("", alias="to"), highlight: str = "", normalize: str = "none"):
    """Every chart in the app is a preset of this query. Plain pandas, cached per query."""
    filters = tuple((k, _csv(v)) for k, v in (("region", region), ("rep", rep), ("segment", segment),
                                               ("product", product), ("category", category)) if v)
    try:
        return _explore(metric, by, split, filters, date_from, date_to, _csv(highlight), normalize)
    except ValueError as e:
        raise HTTPException(400, str(e))


@lru_cache(maxsize=512)
def _whatif(threshold, window):
    return whatif_mod.whatif(DS, threshold, window)


@app.get("/api/whatif")
def whatif(threshold: float = 25, window: int = 14, rule: str = "cap"):
    if rule != "cap":
        raise HTTPException(400, "Only rule=cap is available: quarter-end discounts above the threshold are capped at it")
    if not (0 < threshold <= 100) or not (1 <= window <= 92):
        raise HTTPException(400, "threshold must be in (0, 100], window in [1, 92] days")
    return _whatif(round(float(threshold), 2), int(window))


@app.get("/api/insights")
def insights():
    return _insights()


@app.get("/api/conditions")
def conditions():
    out = []
    for cid, spec in detect.CONDITIONS.items():
        v, w = _defaults(cid, None, None)
        sim = detect.simulate(DS, cid, v, w)
        out.append({"id": cid, "name": spec["name"], "rule_text": spec["rule_text"], "threshold": spec["threshold"],
                    "window": spec.get("window"), "hits": sim["hits"], "amount": sim["amount"],
                    "triggers_action": spec["triggers_action"], "actions": spec["actions"], "sentence": sim["sentence"]})
    return out


@app.get("/api/simulate")
def simulate(condition: str, value: float | None = None, window: int | None = None):
    if condition not in detect.CONDITIONS:
        raise HTTPException(404, f"Unknown condition {condition}")
    v, w = _defaults(condition, value, window)
    return detect.simulate(DS, condition, v, w)


@app.get("/api/alerts")
def alerts(condition: str | None = None, value: float | None = None, window: int | None = None,
           status: str | None = None, owner: str | None = None, rep: str | None = None,
           region: str | None = None, segment: str | None = None, severity: str | None = None,
           limit: int | None = None):
    """Rule-based queue: flag, severity, reasons and $ all come from detect.py. Filters: status, rep (or owner),
    region, segment, severity."""
    conds = [condition] if condition else list(detect.CONDITIONS)
    out = []
    for c in conds:
        out += _alerts(c, value if condition else None, window if condition else None)
    for field, want in (("status", status), ("owner", owner or rep), ("region", region),
                        ("segment", segment), ("severity", severity)):
        if want:
            out = [a for a in out if a.get(field) == want]
    sev = {"high": 0, "medium": 1, "low": 2}
    out.sort(key=lambda a: (a["created_at"], -sev[a["severity"]]), reverse=True)
    return out[:limit] if limit else out


@app.get("/api/alerts/{alert_id}")
def alert(alert_id: str):
    return _find_alert(alert_id)


@app.get("/api/entity/{entity_id}")
def entity(entity_id: str):
    e = story.rep_entity(DS, entity_id) if entity_id.startswith("R") else story.customer_entity(DS, entity_id)
    if e is None:
        raise HTTPException(404, f"No customer or rep {entity_id}")
    return e


@app.post("/api/alerts/{alert_id}/draft")
def draft(alert_id: str):
    return actions.draft(_find_alert(alert_id))


@app.post("/api/alerts/{alert_id}/triage")
def triage(alert_id: str):
    return actions.triage(_find_alert(alert_id))


@app.post("/api/alerts/{alert_id}/override")
def override(alert_id: str, body: dict = Body(default={})):
    reason = (body or {}).get("reason", "").strip()
    if not reason:
        raise HTTPException(400, "An override needs a reason")
    return actions.override(_find_alert(alert_id), reason)


@app.get("/api/actions")
def action_log(condition: str | None = None, value: float | None = None, window: int | None = None,
               alert_id: str | None = None, actor: str | None = None, limit: int | None = None):
    conds = [condition] if condition else list(detect.CONDITIONS)
    al = []
    for c in conds:
        al += _alerts(c, value if condition else None, window if condition else None)
    if alert_id and alert_id.split("-")[0] in ("qe", "br", "od") and not any(a["id"] == alert_id for a in al):
        al.append(_find_alert(alert_id))
    rows = actions.all_rows(al, alert_id=alert_id)
    if actor:
        rows = [r for r in rows if r["actor"] == actor]
    return rows[:limit] if limit else rows


# ---------------------------------------------------------------- Accounts & Limits
@app.get("/api/accounts")
def accounts_list(segment: str | None = None, region: str | None = None, rep: str | None = None):
    out = accounts.accounts(DS)
    for field, want in (("segment", segment), ("region", region), ("rep", rep)):
        if want:
            out = [a for a in out if a[field] == want]
    return out


@app.get("/api/reps")
def reps_list():
    return accounts.reps(DS)


# ---------------------------------------------------------------- Ask (read-only)
@app.post("/api/ask")
def ask(body: dict = Body(default={})):
    body = body or {}
    question = (body.get("question") or "").strip()
    if not question and not body.get("sql"):
        raise HTTPException(400, "Send a question (or a SELECT in `sql`)")
    alert = _find_alert(body["alert_id"]) if body.get("alert_id") else None
    return ask_mod.ask(question, alert=alert, sql=body.get("sql"))


@app.post("/api/admin/reset")
def reset():
    """Clear user overrides, drafts, advisory notes and simulator tasks (before a demo run)."""
    actions.reset_user_rows()
    tasks_mod.reset()
    return {"ok": True}
