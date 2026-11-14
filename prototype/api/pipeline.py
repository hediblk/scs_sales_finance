"""Cleaning pipeline: raw Chrome & Oak export -> trusted tables, every decision logged as data.

Decisions are final (docs/PLAN.md, "Data prep decisions"):
  duplicates dropped, regions / products / slash dates / percent discounts fixed,
  negative quantities set aside in a review list, blank unit costs left blank,
  blank payment dates kept (unpaid invoices).

The raw files in data/raw/chrome_oak/ are never modified. `write_outputs()` writes the cleaned copy
and the trail to data/clean/chrome_oak/.
"""
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "chrome_oak"
CLEAN = ROOT / "data" / "clean" / "chrome_oak"
EXTRACTED_ON = pd.Timestamp("2026-10-31")
BUSINESS = ["SMB", "Enterprise", "Reseller"]

REGION = {"ontario": "Ontario", "on": "Ontario", "quebec": "Quebec", "québec": "Quebec", "qc": "Quebec",
          "atlantic": "Atlantic", "atl": "Atlantic", "prairies": "Prairies", "bc": "BC", "b.c.": "BC",
          "british columbia": "BC"}
PRODUCT = {"mech keyboard": "Mechanical Keyboard", "mechanical keyboard": "Mechanical Keyboard",
           "usb c dock": "USB-C Dock", "usb-c dock": "USB-C Dock",
           "24in monitor": 'Monitor 24"', "monitor 24": 'Monitor 24"', 'monitor 24"': 'Monitor 24"',
           "27in monitor": 'Monitor 27"', "monitor 27": 'Monitor 27"', 'monitor 27"': 'Monitor 27"',
           "ergolift desk": "ErgoLift Standing Desk", "ergolift standing desk": "ErgoLift Standing Desk"}


@dataclass
class Dataset:
    customers: pd.DataFrame
    orders: pd.DataFrame        # sales view: cleaned, typed, enriched; set-aside rows excluded
    returns: pd.DataFrame       # typed, joined to order facts
    review: pd.DataFrame        # rows set aside for a person to check (negative quantities)
    steps: list
    changes: pd.DataFrame       # one row per changed cell
    dropped: pd.DataFrame       # raw rows removed (duplicates) or set aside (review)
    files: list
    summary: dict
    clean_orders: pd.DataFrame  # cleaned orders in the raw schema + raw_line + fixes (what goes to orders.csv)


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def _parse_date(s):
    iso = s.str.match(r"^\d{4}-\d{2}-\d{2}$")
    return pd.to_datetime(s.where(iso), format="%Y-%m-%d").fillna(pd.to_datetime(s.where(~iso), format="%m/%d/%Y"))


def _money(x):
    return f"-${abs(x):,.0f}" if x < 0 else f"${x:,.0f}"


def _revenue(df):
    """Revenue = quantity x unit_price x (1 - discount)."""
    return _num(df.quantity) * _num(df.unit_price) * (1 - _num(df.discount))


def _totals(df):
    rev = _revenue(df)
    cost = _num(df.unit_cost)
    known = cost.notna()
    gp = (rev - _num(df.quantity) * cost)[known]
    return {"orders": int(len(df)), "revenue": round(float(rev.sum()), 2),
            "gross_profit": round(float(gp.sum()), 2),
            "margin_pct": round(float(100 * gp.sum() / rev[known].sum()), 2) if known.any() else None}


def _yoy(df):
    """Revenue growth Jan-Sep 2026 vs Jan-Sep 2025, in %."""
    d = _parse_date(df.order_date)
    rev = _revenue(df)
    jan_sep = d.dt.month <= 9
    a = rev[jan_sep & (d.dt.year == 2025)].sum()
    b = rev[jan_sep & (d.dt.year == 2026)].sum()
    return 100 * (b / a - 1)


def _type_and_enrich(c, o, r):
    """Text tables (as in the CSV files) -> typed customers, enriched sales view, typed returns."""
    if "fixes" not in o.columns:
        o = o.assign(fixes="")
    o = o.fillna("")
    cust = c.copy()
    cust["signup_date"] = pd.to_datetime(cust.signup_date)
    cust["credit_limit"] = _num(cust.credit_limit)
    cust["account_rep"] = cust.account_rep.replace("", pd.NA)

    od = o.drop(columns=["fixes"]).copy()
    od["order_date"] = pd.to_datetime(od.order_date)
    od["payment_date"] = pd.to_datetime(od.payment_date.replace("", pd.NA))
    for col in ["quantity", "unit_price", "discount", "unit_cost"]:
        od[col] = _num(od[col])
    od["quantity"] = od.quantity.astype(int)
    od["sales_rep"] = od.sales_rep.replace("", pd.NA)
    od["fixes"] = o.fixes.values

    ret = r.copy()
    ret["return_date"] = pd.to_datetime(ret.return_date)
    ret["quantity_returned"] = _num(ret.quantity_returned).astype(int)
    ret["refund_amount"] = _num(ret.refund_amount)

    # sales view: derived columns
    od = od.merge(cust[["customer_id", "segment", "signup_date", "payment_terms", "credit_limit"]], on="customer_id", how="left")
    od["list_rev"] = od.quantity * od.unit_price
    od["revenue"] = od.list_rev * (1 - od.discount)
    od["cost_known"] = od.unit_cost.notna()
    od["cogs"] = od.quantity * od.unit_cost                      # NaN when cost is unknown
    od["gp"] = od.revenue - od.cogs                              # NaN when cost is unknown
    od["below_cost"] = od.cost_known & (od.discount > 1 - od.unit_cost / od.unit_price)
    rr = ret.groupby("order_id").agg(refund=("refund_amount", "sum"), qty_ret=("quantity_returned", "sum"),
                                     return_date=("return_date", "min"), return_reason=("reason", "first")).reset_index()
    od = od.merge(rr, on="order_id", how="left")
    od["refund"] = od.refund.fillna(0.0)
    od["qty_ret"] = od.qty_ret.fillna(0).astype(int)
    od["returned"] = od.qty_ret > 0
    od["year"] = od.order_date.dt.year
    od["quarter"] = od.order_date.dt.to_period("Q").astype(str)
    q_start = od.order_date.dt.to_period("Q").dt.start_time.dt.normalize()
    q_end = od.order_date.dt.to_period("Q").dt.end_time.dt.normalize()
    od["days_to_qend"] = (q_end - od.order_date).dt.days            # 0 = last day of the quarter
    od["week_of_quarter"] = ((od.order_date - q_start).dt.days // 7 + 1).clip(upper=13)
    od["terms_days"] = od.payment_terms.map({"Prepaid": 0, "Net 30": 30, "Net 60": 60})
    od["due_date"] = od.order_date + pd.to_timedelta(od.terms_days, unit="D")
    od["is_business"] = od.segment.isin(BUSINESS)

    ret = ret.merge(od[["order_id", "customer_id", "segment", "region", "sales_rep", "product", "category",
                        "order_date", "quantity", "revenue"]], on="order_id", how="left")
    return cust, od, ret


def build() -> Dataset:
    c = pd.read_csv(RAW / "customers.csv", dtype=str, keep_default_na=False)
    o = pd.read_csv(RAW / "orders.csv", dtype=str, keep_default_na=False)
    r = pd.read_csv(RAW / "returns.csv", dtype=str, keep_default_na=False)
    files = [
        {"name": "customers.csv", "rows": len(c), "cols": c.shape[1], "row_means": "one customer: segment, region, account rep, payment terms, credit limit"},
        {"name": "orders.csv", "rows": len(o), "cols": o.shape[1], "row_means": "one order line: one product, quantity, list price, discount, unit cost, rep, payment date"},
        {"name": "returns.csv", "rows": len(r), "cols": r.shape[1], "row_means": "one return: at most one per order, quantity returned, reason, refund"},
    ]
    o.insert(0, "raw_line", o.index + 2)  # line 1 is the header
    o["fixes"] = ""
    changes, dropped, steps = [], [], []
    start = _totals(o)

    def fix(step_id, col, mask, new):
        new = new if isinstance(new, pd.Series) else pd.Series(new, index=o.index)
        mask = mask & (o[col] != new)
        for line, oid, old, nv in zip(o.loc[mask, "raw_line"], o.loc[mask, "order_id"], o.loc[mask, col], new[mask]):
            changes.append({"file": "orders.csv", "raw_line": int(line), "order_id": oid, "column": col,
                            "old": old, "new": nv, "step": step_id})
        o.loc[mask, col] = new[mask]
        o.loc[mask, "fixes"] = o.loc[mask, "fixes"].map(lambda s: f"{s};{step_id}" if s else step_id)
        return mask

    def step(step_id, kind, title, why, rows, before, after, effect, column=None):
        steps.append({"id": step_id, "kind": kind, "title": title, "why": why, "column": column,
                      "rows_affected": int(rows), "effect": effect,
                      "revenue_before": before["revenue"], "revenue_after": after["revenue"],
                      "gross_profit_before": before["gross_profit"], "gross_profit_after": after["gross_profit"]})

    # 1. exact duplicates
    b = _totals(o)
    dup = o.drop(columns=["raw_line", "fixes"]).duplicated()
    dup_rev = _revenue(o[dup]).sum()
    for line, oid in zip(o.loc[dup, "raw_line"], o.loc[dup, "order_id"]):
        dropped.append({"file": "orders.csv", "raw_line": int(line), "order_id": oid, "step": "dedupe", "outcome": "removed"})
    o = o[~dup].copy()
    step("dedupe", "drop", "Removed duplicate order rows",
         "Same order_id with every column identical: the order was counted twice.",
         dup.sum(), b, _totals(o), f"Removes ${dup_rev:,.0f} of double-counted revenue")

    # 2. percent discounts
    b = _totals(o)
    d = _num(o.discount)
    m = d > 1
    rev_before = _revenue(o[m]).sum()
    m = fix("discount_pct", "discount", m, (d / 100).round(4).map(lambda x: f"{x:g}"))
    step("discount_pct", "fix", "Converted percent discounts to fractions",
         "Most discounts are fractions (0.12). These rows hold 12 for 12%, which made their revenue negative. "
         "They sit inside the discount analysis the main finding rests on.",
         m.sum(), b, _totals(o), f"These rows go from {_money(rev_before)} to {_money(_revenue(o[m]).sum())} of revenue", "discount")

    # 3. negative quantities: set aside for review, out of the sales view
    b = _totals(o)
    neg = _num(o.quantity) < 0
    growth_before = _yoy(o)
    review = o[neg].copy()
    review["review_reason"] = "Negative quantity on an order with a payment date and no matching return"
    for line, oid in zip(review.raw_line, review.order_id):
        dropped.append({"file": "orders.csv", "raw_line": int(line), "order_id": oid, "step": "neg_qty", "outcome": "set aside for review"})
    o = o[~neg].copy()
    step("neg_qty", "set_aside", "Set aside negative quantities for review",
         "Each has a payment date and no matching return, so it is neither a clean sale nor a return. "
         "Kept in a review list instead of guessing the sign.",
         neg.sum(), b, _totals(o),
         f"Out of the sales view: {_money(_revenue(review).sum())}. Jan-Sep revenue growth {growth_before:.2f}% -> {_yoy(o):.2f}%", "quantity")

    # 4. region spellings
    b = _totals(o)
    new = o.region.str.strip().str.lower().map(REGION)
    m = fix("region", "region", new.notna(), new)
    moved = _revenue(o[m]).groupby(o.region[m]).sum().sort_values(ascending=False)
    step("region", "fix", "Unified region spellings", "15 spellings (ON, ontario, QC, Québec, B.C., ATL...) for 5 regions.",
         m.sum(), b, _totals(o), "Total unchanged. Regional totals gain " + ", ".join(f"{k} ${v:,.0f}" for k, v in moved.items()), "region")

    # 5. product names
    b = _totals(o)
    new = o["product"].str.strip().str.lower().map(PRODUCT).fillna(o["product"])
    m = fix("product", "product", pd.Series(True, index=o.index), new)
    step("product", "fix", "Unified product names", "22 names (Mech Keyboard, 24in Monitor, ERGOLIFT STANDING DESK...) for 10 products.",
         m.sum(), b, _totals(o), f"Total unchanged. ${_revenue(o[m]).sum():,.0f} now lands on the right product", "product")

    # 6. slash dates, month first
    b = _totals(o)
    slash = ~o.order_date.str.match(r"^\d{4}-\d{2}-\d{2}$")
    parsed = pd.to_datetime(o.order_date.where(slash), format="%m/%d/%Y").dt.strftime("%Y-%m-%d")
    m = fix("date_format", "order_date", slash, parsed)
    step("date_format", "fix", "Converted MM/DD/YYYY order dates to ISO",
         "The rest are YYYY-MM-DD. Read day first, these would put orders in Oct to Dec 2026, after the data ends. So month first.",
         m.sum(), b, _totals(o), f"Total unchanged. ${_revenue(o[m]).sum():,.0f} now falls in the right month and quarter", "order_date")

    # 7. blank unit cost: left blank
    blank_cost = o.unit_cost.str.strip() == ""
    coverage = 100 * (1 - blank_cost.mean())
    t = _totals(o)
    step("cost_blank", "kept", "Left blank unit costs blank",
         "No invented values. Margins use only rows with a known cost.",
         blank_cost.sum(), t, t, f"Margins computed on {coverage:.1f}% of order lines", "unit_cost")

    # 8. blank payment date: kept on purpose
    unpaid = o.payment_date.str.strip() == ""
    step("unpaid_kept", "kept", "Kept blank payment dates",
         "All on business orders (Net 30 / Net 60): invoices still unpaid when the data was extracted on 2026-10-31.",
         unpaid.sum(), t, t, f"${_revenue(o[unpaid]).sum():,.0f} unpaid at extraction", "payment_date")

    # 9. join checks
    orphan_o = int((~o.customer_id.isin(c.customer_id)).sum())
    orphan_r = int((~r.order_id.isin(pd.concat([o.order_id, review.order_id]))).sum())
    mism = int((o.merge(c[["customer_id", "region"]], on="customer_id", suffixes=("", "_c")).pipe(lambda x: x.region != x.region_c)).sum())
    step("join_check", "check", "Checked the joins between the three files",
         "orders.customer_id to customers, returns.order_id to orders, order region vs customer region.",
         orphan_o + orphan_r + mism, t, t,
         f"{orphan_o} orders without a customer, {orphan_r} returns without an order, {mism} region mismatches")

    end = _totals(o)
    clean_orders = o.copy()

    cust, od, ret = _type_and_enrich(c, o, r)

    summary = {"raw": start, "clean": end, "cells_changed": len(changes),
               "rows_removed": int(sum(1 for x in dropped if x["outcome"] == "removed")),
               "rows_set_aside": int(len(review)), "rows_fixed": int((clean_orders.fixes != "").sum()),
               "cost_coverage_pct": round(float(coverage), 1)}
    return Dataset(customers=cust, orders=od, returns=ret, review=review, steps=steps,
                   changes=pd.DataFrame(changes), dropped=pd.DataFrame(dropped), files=files,
                   summary=summary, clean_orders=clean_orders)


def load(clean_dir: Path = CLEAN) -> Dataset:
    """Read the cleaned tables from data/clean (never rebuilt here). One loader, so the teammate's version
    of data/clean can replace ours without touching the rest of the API."""
    txt = {"dtype": str, "keep_default_na": False}
    c = pd.read_csv(clean_dir / "customers.csv", **txt)
    o = pd.read_csv(clean_dir / "orders.csv", **txt)
    r = pd.read_csv(clean_dir / "returns.csv", **txt)
    cust, od, ret = _type_and_enrich(c, o, r)
    review = pd.read_csv(clean_dir / "review_rows.csv", **txt) if (clean_dir / "review_rows.csv").exists() else pd.DataFrame()
    changes = pd.read_csv(clean_dir / "changes.csv", **txt) if (clean_dir / "changes.csv").exists() else pd.DataFrame()
    dropped = pd.read_csv(clean_dir / "dropped_rows.csv", **txt) if (clean_dir / "dropped_rows.csv").exists() else pd.DataFrame()
    prep = json.loads((clean_dir / "data_prep.json").read_text(encoding="utf-8")) if (clean_dir / "data_prep.json").exists() else {}
    return Dataset(customers=cust, orders=od, returns=ret, review=review, steps=prep.get("steps", []),
                   changes=changes, dropped=dropped, files=prep.get("files", []), summary=prep.get("summary", {}),
                   clean_orders=o)


def write_outputs(ds: Dataset, out: Path = CLEAN):
    """Write the cleaned copy and the trail. LF line endings like the raw files, so they diff line by line."""
    out.mkdir(parents=True, exist_ok=True)
    lf = {"index": False, "lineterminator": "\n"}
    pd.read_csv(RAW / "customers.csv", dtype=str, keep_default_na=False).to_csv(out / "customers.csv", **lf)
    pd.read_csv(RAW / "returns.csv", dtype=str, keep_default_na=False).to_csv(out / "returns.csv", **lf)
    ds.clean_orders.to_csv(out / "orders.csv", **lf)
    ds.review.to_csv(out / "review_rows.csv", **lf)
    ds.changes.to_csv(out / "changes.csv", **lf)
    ds.dropped.to_csv(out / "dropped_rows.csv", **lf)
    payload = {"files": [dict(f, rows_clean={"orders.csv": len(ds.clean_orders)}.get(f["name"], f["rows"])) for f in ds.files],
               "steps": ds.steps, "summary": ds.summary}
    (out / "data_prep.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    ds = build()
    write_outputs(ds)
    print("raw  :", ds.summary["raw"])
    print("clean:", ds.summary["clean"])
    for s in ds.steps:
        print(f"  [{s['kind']:9}] {s['id']:12} rows={s['rows_affected']:4}  {s['effect']}")
    print({k: v for k, v in ds.summary.items() if k not in ("raw", "clean")})
