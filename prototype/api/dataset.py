"""Dataset page: the files as received (raw) or as cleaned (clean), same shapes for both.

Everything is read as text first, so nothing gets coerced: a raw value like "22.5" or "01/13/2025" is shown
exactly as it sits in the file. Types are only *detected* for the profile, never written back.
No cleaning or anomaly logic lives here (the teammate owns that part).
"""
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from .pipeline import CLEAN, RAW

TABLES = {
    "customers": {"file": "customers.csv", "key": "customer_id",
                  "row_means": "one customer: segment, region, account rep, payment terms, credit limit"},
    "orders": {"file": "orders.csv", "key": "order_id",
               "row_means": "one order line, one product: quantity, list price, discount, unit cost, rep, payment date"},
    "returns": {"file": "returns.csv", "key": "return_id",
                "row_means": "one return, at most one per order: quantity returned, reason, refund"},
}
DATE_PATTERNS = [("YYYY-MM-DD", re.compile(r"^\d{4}-\d{2}-\d{2}$")), ("NN/NN/YYYY", re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$"))]
NUM = re.compile(r"^-?\d+(\.\d+)?$")


def _dir(source):
    if source not in ("raw", "clean"):
        raise KeyError(source)
    return RAW if source == "raw" else CLEAN


@lru_cache(maxsize=8)
def table(source, name):
    """The table as text, with `raw_line` first (line number in the raw file; line 1 is the header)."""
    if name not in TABLES:
        raise KeyError(name)
    df = pd.read_csv(_dir(source) / TABLES[name]["file"], dtype=str, keep_default_na=False)
    if "raw_line" not in df.columns:
        df.insert(0, "raw_line", (df.index + 2).astype(str))
    return df


def _data_cols(df):
    return [c for c in df.columns if c not in ("raw_line", "fixes")]


def tables(source):
    out = []
    for name, spec in TABLES.items():
        df = table(source, name)
        key = df[spec["key"]]
        out.append({"name": name, "file": spec["file"], "rows": int(len(df)), "columns": len(_data_cols(df)),
                    "row_means": spec["row_means"], "key": spec["key"],
                    "key_unique": bool(key.is_unique), "duplicate_keys": int(key.duplicated().sum()),
                    "exact_duplicate_rows": int(df[_data_cols(df)].duplicated().sum())})
    c, o, r = table(source, "customers"), table(source, "orders"), table(source, "returns")
    oc = o.merge(c[["customer_id", "region", "account_rep"]], on="customer_id", how="left", suffixes=("", "_cust"))
    has = oc.region_cust.notna()
    rep_rows = oc[(oc.sales_rep != "") & has]
    joins = [
        {"from": "orders.customer_id", "to": "customers.customer_id", "match_rate": round(float(o.customer_id.isin(c.customer_id).mean()), 4)},
        {"from": "returns.order_id", "to": "orders.order_id", "match_rate": round(float(r.order_id.isin(o.order_id).mean()), 4)},
        {"from": "orders.region", "to": "customers.region (same customer, same spelling)",
         "match_rate": round(float((oc.region[has] == oc.region_cust[has]).mean()), 4)},
        {"from": "orders.sales_rep", "to": "customers.account_rep (same customer)",
         "match_rate": round(float((rep_rows.sales_rep == rep_rows.account_rep).mean()), 4) if len(rep_rows) else None},
    ]
    if source == "clean":
        review = CLEAN / "review_rows.csv"
        joins[1]["note"] = "returns can point at a set-aside order" if review.exists() else None
    return {"source": source, "tables": out, "joins": joins}


def _detect(values):
    """Detected type of the non-blank values: number, date or text."""
    if len(values) == 0:
        return "text"
    if values.str.match(NUM).mean() == 1.0:
        return "number"
    if sum(values.str.match(p).sum() for _, p in DATE_PATTERNS) == len(values):
        return "date"
    return "text"


def _hist(x, bins=20):
    if len(x) == 0:
        return []
    lo, hi = float(x.min()), float(x.max())
    if lo == hi:
        return [{"from": lo, "to": hi, "count": int(len(x))}]
    counts, edges = np.histogram(x, bins=bins, range=(lo, hi))
    return [{"from": round(float(edges[i]), 4), "to": round(float(edges[i + 1]), 4), "count": int(counts[i])} for i in range(len(counts))]


def _changed_cells(name):
    path = CLEAN / "changes.csv"
    if name != "orders" or not path.exists():
        return {}
    ch = pd.read_csv(path, dtype=str, keep_default_na=False)
    return ch.groupby("column").size().to_dict()


def profile(source, name):
    df = table(source, name)
    changed = _changed_cells(name) if source == "clean" else {}
    out = []
    for col in _data_cols(df):
        s = df[col]
        blank = s.str.strip() == ""
        vals = s[~blank]
        dtype = _detect(vals)
        item = {"column": col, "dtype": dtype, "missing": int(blank.sum()), "missing_pct": round(100 * float(blank.mean()), 2),
                "distinct": int(vals.nunique()),
                "top": [{"value": v, "count": int(n)} for v, n in vals.value_counts().head(10).items()],
                "numeric": None, "date": None,
                "changed_cells": (int(changed.get(col, 0)) if source == "clean" else None)}
        if dtype == "number":
            x = vals.astype(float)
            item["numeric"] = {"min": float(x.min()), "p25": float(x.quantile(0.25)), "median": float(x.median()),
                               "p75": float(x.quantile(0.75)), "max": float(x.max()), "negatives": int((x < 0).sum()),
                               "zeros": int((x == 0).sum()), "hist": _hist(x)}
        elif dtype == "date":
            fmts = [{"pattern": pat, "count": int(vals.str.match(rx).sum())} for pat, rx in DATE_PATTERNS]
            iso = vals[vals.str.match(DATE_PATTERNS[0][1])]
            item["date"] = {"min": iso.min() if len(iso) else None, "max": iso.max() if len(iso) else None,
                            "range_from": "YYYY-MM-DD values only", "formats": [f for f in fmts if f["count"]]}
        out.append(item)
    return out


def rows(source, name, offset=0, limit=50, q="", col="", val=""):
    df = table(source, name)
    m = pd.Series(True, index=df.index)
    if col:
        if col not in df.columns:
            raise KeyError(col)
        m &= df[col] == val
    if q:
        ql = q.lower()
        hit = pd.Series(False, index=df.index)
        for c in df.columns:
            hit |= df[c].str.lower().str.contains(ql, regex=False)
        m &= hit
    sub = df[m]
    limit = max(1, min(int(limit), 500))
    page = sub.iloc[int(offset): int(offset) + limit]
    return {"source": source, "table": name, "total": int(len(sub)), "offset": int(offset), "limit": limit,
            "columns": list(df.columns), "rows": page.values.tolist()}


def charts(source):
    o, r = table(source, "orders"), table(source, "returns")
    iso = o.order_date.str.match(DATE_PATTERNS[0][1])
    per_month = o[iso].order_date.str[:7].value_counts().sort_index()
    other_dates = int((~iso).sum())
    reg = o.region.value_counts()
    d = pd.to_numeric(o.discount, errors="coerce")
    edges = [0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 1.0, float("inf")]
    labels = ["0-5%", "5-10%", "10-15%", "15-20%", "20-25%", "25-30%", "30-35%", "35-40%", "40-50%", "50-100%", "1 or more"]
    band = pd.cut(d, edges, right=False, labels=labels)
    bc = band.value_counts().reindex(labels, fill_value=0)
    rm = r.groupby(r.return_date.str[:7]).refund_amount.apply(lambda s: pd.to_numeric(s, errors="coerce").sum()).sort_index()
    return [
        {"id": f"{source}_orders_per_month", "type": "bar", "unit": "rows", "x": "month",
         "title": "Order rows per month",
         "caption": (f"By order_date. {other_dates} rows with a NN/NN/YYYY date are not placed on this axis." if other_dates
                     else "By order_date."),
         "series": [{"key": "rows", "label": "Order rows"}],
         "rows": [{"month": m, "rows": int(n)} for m, n in per_month.items()]},
        {"id": f"{source}_region_labels", "type": "bar", "unit": "rows", "x": "label",
         "title": "Rows per region label", "caption": f"{len(reg)} distinct region labels in orders.csv.",
         "series": [{"key": "rows", "label": "Order rows"}],
         "rows": [{"label": k, "rows": int(v)} for k, v in reg.items()]},
        {"id": f"{source}_discount_hist", "type": "bar", "unit": "rows", "x": "band",
         "title": "Discount values", "caption": f"{int(bc['1 or more'])} rows hold a discount of 1 or more.",
         "series": [{"key": "rows", "label": "Order rows"}],
         "rows": [{"band": k, "rows": int(v)} for k, v in bc.items()]},
        {"id": f"{source}_refunds_per_month", "type": "bar", "unit": "$", "x": "month",
         "title": "Refunds per month", "caption": "By return_date, refund_amount summed.",
         "series": [{"key": "refunds", "label": "Refunds"}],
         "rows": [{"month": m, "refunds": round(float(v), 2)} for m, v in rm.items()]},
    ]


def set_aside():
    """Rows taken out of the clean sales view, with the reason and their raw values."""
    raw = table("raw", "orders").set_index("raw_line")
    out = []
    path = CLEAN / "dropped_rows.csv"
    if not path.exists():
        return out
    reasons = {"dedupe": "Exact duplicate of another row (every column identical)",
               "neg_qty": "Negative quantity on an order with a payment date and no matching return"}
    for r in pd.read_csv(path, dtype=str, keep_default_na=False).itertuples():
        vals = raw.loc[r.raw_line].to_dict() if r.raw_line in raw.index else {}
        out.append({"raw_line": int(r.raw_line), "order_id": r.order_id, "step": r.step,
                    "outcome": getattr(r, "outcome", ""), "reason": reasons.get(r.step, r.step), "values": vals})
    return out
