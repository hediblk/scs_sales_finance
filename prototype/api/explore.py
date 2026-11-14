"""Dynamic charts: one endpoint behind every chart. Metric x group-by x optional split x filters, plain pandas on
the clean data. Margins use known-cost rows only. The chart type is picked by code, never by the AI."""
import pandas as pd

from .pipeline import Dataset

METRICS = {
    "revenue": {"label": "Revenue", "unit": "$", "additive": True},
    "gross_profit": {"label": "Gross profit", "unit": "$", "additive": True},
    "margin_pct": {"label": "Gross margin %", "unit": "%", "additive": False},
    "avg_discount": {"label": "Average discount %", "unit": "%", "additive": False},
    "refunds": {"label": "Refunds", "unit": "$", "additive": True},
    "return_rate": {"label": "Orders returned %", "unit": "%", "additive": False},
    "orders": {"label": "Orders", "unit": "orders", "additive": True},
    "units": {"label": "Units", "unit": "units", "additive": True},
}
BY = {
    "month": "Month", "quarter": "Quarter", "region": "Region", "rep": "Account rep", "segment": "Segment",
    "product": "Product", "category": "Category", "channel": "Sales channel",
    "days_to_quarter_end": "Days before quarter end", "discount_band": "Discount band",
}
ORDERED = {"month", "quarter", "days_to_quarter_end", "discount_band"}  # keep their natural order
LINE_BY = {"month", "quarter", "days_to_quarter_end"}
FILTERS = ["region", "rep", "segment", "product", "category"]
TOP_SPLIT = 6

DTQ_EDGES = list(range(0, 98, 7))  # 0-6, 7-13, ... 91-97
DTQ_LABELS = [f"{a}-{a + 6} days" for a in DTQ_EDGES[:-1]]
DISC_EDGES = [0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 10]
DISC_LABELS = ["0-5%", "5-10%", "10-15%", "15-20%", "20-25%", "25-30%", "30-35%", "35-40%", "40%+"]


def frame(ds: Dataset):
    """The clean orders with the dimensions this endpoint groups by."""
    o = ds.orders
    f = pd.DataFrame({
        "order_date": o.order_date, "month": o.order_date.dt.strftime("%Y-%m"), "quarter": o.quarter,
        "region": o.region, "rep": o.sales_rep.fillna("Online (no rep)"), "segment": o.segment,
        "product": o["product"], "category": o.category, "channel": o.sales_channel,
        "days_to_quarter_end": pd.cut(o.days_to_qend, DTQ_EDGES, right=False, labels=DTQ_LABELS).astype(str),
        "discount_band": pd.cut(o.discount, DISC_EDGES, right=False, labels=DISC_LABELS).astype(str),
        "revenue": o.revenue, "list_rev": o.list_rev,
        "gp_known": o.gp.where(o.cost_known, 0.0), "rev_known": o.revenue.where(o.cost_known, 0.0),
        "refund": o.refund, "returned": o.returned.astype(int), "units": o.quantity,
    })
    return f


def options(ds: Dataset):
    f = frame(ds)
    return {"metrics": [{"id": k, **v} for k, v in METRICS.items()],
            "by": [{"id": k, "label": v} for k, v in BY.items()],
            "split": [{"id": k, "label": v} for k, v in BY.items() if k not in ("month", "quarter")],
            "filters": {c: sorted(f[c].dropna().unique().tolist()) for c in FILTERS},
            "date_range": {"min": f"{f.order_date.min():%Y-%m-%d}", "max": f"{f.order_date.max():%Y-%m-%d}"},
            "normalize": ["none", "share"]}


def _agg(f, keys):
    g = f.groupby(keys, observed=True).agg(revenue=("revenue", "sum"), list_rev=("list_rev", "sum"), gp=("gp_known", "sum"),
                                           rev_known=("rev_known", "sum"), refunds=("refund", "sum"),
                                           returned=("returned", "sum"), orders=("revenue", "size"), units=("units", "sum"))
    return g


def _metric(g, metric):
    if metric == "revenue":
        return g.revenue
    if metric == "gross_profit":
        return g.gp
    if metric == "margin_pct":
        return 100 * g.gp / g.rev_known.where(g.rev_known != 0)
    if metric == "avg_discount":
        return 100 * (1 - g.revenue / g.list_rev.where(g.list_rev != 0))
    if metric == "refunds":
        return g.refunds
    if metric == "return_rate":
        return 100 * g.returned / g.orders
    if metric == "orders":
        return g.orders.astype(float)
    return g.units.astype(float)


def _order(values, by, ranking=None):
    vals = list(values)
    if by == "days_to_quarter_end":
        return [v for v in reversed(DTQ_LABELS) if v in vals]  # far from quarter end -> quarter end
    if by == "discount_band":
        return [v for v in DISC_LABELS if v in vals]
    if by in ORDERED:
        return sorted(vals)
    if ranking is not None:
        return [v for v in ranking.sort_values(ascending=False).index if v in vals]
    return sorted(vals)


def _num(v, metric):
    if pd.isna(v):
        return None
    if metric in ("orders", "units"):
        return int(round(float(v)))
    return round(float(v), 1 if METRICS[metric]["unit"] == "%" else 2)


def explore(ds: Dataset, metric="revenue", by="quarter", split=None, filters=None, date_from=None, date_to=None,
            highlight=None, normalize="none"):
    if metric not in METRICS:
        raise ValueError(f"metric must be one of {list(METRICS)}")
    if by not in BY:
        raise ValueError(f"by must be one of {list(BY)}")
    if split and (split not in BY or split == by):
        raise ValueError(f"split must be one of {list(BY)} and differ from by")
    f = frame(ds)
    applied = {}
    for col, vals in (filters or {}).items():
        if vals:
            f = f[f[col].isin(vals)]
            applied[col] = vals
    if date_from:
        f = f[f.order_date >= pd.Timestamp(date_from)]
        applied["from"] = date_from
    if date_to:
        f = f[f.order_date <= pd.Timestamp(date_to)]
        applied["to"] = date_to
    spec = METRICS[metric]
    share = normalize == "share" and spec["additive"]
    notes = []
    if normalize == "share" and not spec["additive"]:
        notes.append(f"{spec['label']} is already a rate, so it is not turned into a share")
    unit = "%" if share else spec["unit"]
    if f.empty:
        return {"chart": {"type": "bar", "x": by, "series": [], "unit": unit, "note": "No orders match these filters"},
                "columns": [by], "rows": [], "filters_applied": applied, "n_orders": 0}

    if not split:
        g = _agg(f, [by])
        val = _metric(g, metric)
        if share:
            val = 100 * val / val.sum()
        order = _order(val.index, by, ranking=val)
        key = metric if not share else f"{metric}_share"
        label = spec["label"] if not share else f"Share of {spec['label'].lower()} %"
        rows = [[x, _num(val[x], "margin_pct" if share else metric)] for x in order]
        chart = {"type": "line" if by in LINE_BY else "bar", "x": by, "series": [{"key": key, "label": label}], "unit": unit}
        columns = [by, key]
    else:
        f = f.copy()
        if highlight:
            hl = [h for h in highlight if h in set(f[split])]
            f[split] = f[split].where(f[split].isin(hl), f"Other {BY[split].lower()}s" if hl else "All")
            notes.append(f"{', '.join(hl)} vs all other {BY[split].lower()}s")
        else:
            rank = _metric(_agg(f, [split]), metric if spec["additive"] else "orders")
            top = rank.sort_values(ascending=False).head(TOP_SPLIT).index
            if f[split].nunique() > TOP_SPLIT:
                f[split] = f[split].where(f[split].isin(top), "Other")
                notes.append(f"Top {TOP_SPLIT} {BY[split].lower()} values, the rest grouped as Other")
        g = _agg(f, [by, split])
        val = _metric(g, metric).unstack(split)
        if share:
            val = 100 * val / val.sum(axis=0)
        totals = _metric(_agg(f, [by]), metric)
        order = _order(val.index, by, ranking=totals)
        series_order = list(val.sum(axis=0).sort_values(ascending=False).index) if spec["additive"] else list(val.columns)
        series_order = [s for s in series_order if not str(s).startswith("Other")] + [s for s in series_order if str(s).startswith("Other")]
        rows = [[x] + [_num(val.loc[x, s], "margin_pct" if share else metric) if x in val.index else None for s in series_order]
                for x in order]
        ctype = "line" if by in LINE_BY else ("stacked-bar" if spec["additive"] and not share else "bar")
        chart = {"type": ctype, "x": by, "split": split, "unit": unit,
                 "series": [{"key": str(s), "label": str(s)} for s in series_order]}
        columns = [by] + [str(s) for s in series_order]
        if share:
            notes.append(f"Each series as a share of its own total {spec['label'].lower()}")
    title = f"{'Share of ' + spec['label'].lower() if share else spec['label']} by {BY[by].lower()}" + \
        (f", split by {BY[split].lower()}" if split else "")
    chart["title"] = title
    if spec["unit"] == "$" and metric == "gross_profit" or metric == "margin_pct":
        notes.append(f"Margins use order lines with a known unit cost ({100 * ds.orders.cost_known.mean():.1f}% of lines)")
    if notes:
        chart["note"] = ". ".join(notes)
    return {"chart": chart, "columns": columns, "rows": rows, "filters_applied": applied, "n_orders": int(len(f))}
