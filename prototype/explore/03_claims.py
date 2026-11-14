"""Test the four exec claims on the cleaned Chrome & Oak data (built by explore/clean.py)."""
import warnings
import pandas as pd

warnings.filterwarnings("ignore")
pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 30)
pd.set_option("display.float_format", "{:,.2f}".format)
CLEAN = "data/clean/chrome_oak"  # run explore/clean.py first; the uncleaned copy stays in data/raw/chrome_oak
EXTRACT = pd.Timestamp("2026-10-31")
c = pd.read_csv(f"{CLEAN}/customers.csv", parse_dates=["signup_date"])
o = pd.read_csv(f"{CLEAN}/orders.csv", parse_dates=["order_date", "payment_date"])
o["fixes"] = o.fixes.fillna("")
r = pd.read_csv(f"{CLEAN}/returns.csv", parse_dates=["return_date"])
print("rows touched by cleaning:", (o.fixes != "").sum(), "| cell-level trail in data/clean/chrome_oak/changes.csv")

o = o.merge(c, on="customer_id", how="left", suffixes=("", "_cust"))
print("order region != customer region after cleaning:", (o.region != o.region_cust).sum())
o["list_rev"] = o.quantity * o.unit_price
o["revenue"] = o.list_rev * (1 - o.discount)
o["cogs"] = o.quantity * o.unit_cost
o["gp"] = o.revenue - o.cogs
rr = r.groupby("order_id").agg(refund=("refund_amount", "sum"), qty_ret=("quantity_returned", "sum")).reset_index()
o = o.merge(rr, on="order_id", how="left").fillna({"refund": 0, "qty_ret": 0})
o["year"] = o.order_date.dt.year
o["q"] = o.order_date.dt.to_period("Q")
qend = o.order_date.dt.to_period("Q").dt.end_time.dt.normalize()
o["days_to_qend"] = (qend - o.order_date).dt.days
o["last2w"] = o.days_to_qend <= 13
o["terms_days"] = o.payment_terms.map({"Prepaid": 0, "Net 30": 30, "Net 60": 60})
o["due"] = o.order_date + pd.to_timedelta(o.terms_days, unit="D")
o["days_late"] = (o.payment_date.fillna(EXTRACT) - o.due).dt.days.clip(lower=0)
o["unpaid_amt"] = o.revenue.where(o.payment_date.isna(), 0)


def tbl(df, by):
    g = df.groupby(by).agg(orders=("order_id", "size"), list_rev=("list_rev", "sum"), revenue=("revenue", "sum"),
                           gp=("gp", "sum"), refunds=("refund", "sum"), unpaid=("unpaid_amt", "sum"))
    g["disc%"] = 100 * (1 - g.revenue / g.list_rev)
    g["gm%"] = 100 * g.gp / g.revenue
    g["ret%"] = 100 * g.refunds / g.revenue
    g["gp_after_ret"] = g.gp - g.refunds  # crude: refund wipes the sale, damaged stock not resold
    g["rev_share%"] = 100 * g.revenue / g.revenue.sum()
    return g


print("\n================ CEO: revenue up a third? Atlantic punches above weight?")
ytd = o[o.order_date.dt.month <= 9]
y = tbl(ytd, "year")
print(y)
print("YoY Jan-Sep revenue growth %:", round(100 * (y.revenue.iloc[1] / y.revenue.iloc[0] - 1), 1),
      "| GP growth %:", round(100 * (y.gp.iloc[1] / y.gp.iloc[0] - 1), 1),
      "| GP after refunds growth %:", round(100 * (y.gp_after_ret.iloc[1] / y.gp_after_ret.iloc[0] - 1), 1))
print("\nby region x year (Jan-Sep):")
print(tbl(ytd, ["region", "year"])[["revenue", "disc%", "gm%", "ret%", "unpaid", "rev_share%"]])
print("customer share % by region:", c.region.value_counts(normalize=True).mul(100).round(1).to_dict())
ry = ytd.groupby(["region", "year"]).revenue.sum().unstack()
print("revenue growth % by region:", (100 * (ry[2026] / ry[2025] - 1)).round(1).to_dict())
print("\nby segment x year:")
print(tbl(ytd, ["segment", "year"])[["revenue", "disc%", "gm%", "ret%", "unpaid"]])
sy = ytd.groupby(["region", "segment", "year"]).revenue.sum().unstack()
print("\nregion x segment growth:")
print(sy.assign(growth=100 * (sy[2026] / sy[2025] - 1)))

print("\n================ Quarter-end pattern (target gaming?)")
b2b = o[o.sales_rep.notna()]
print(b2b.groupby("last2w").agg(orders=("order_id", "size"), disc=("discount", "mean"), qty=("quantity", "mean")))
reg_q = b2b.groupby(["region", "last2w"]).agg(rev=("revenue", "sum"), disc=("discount", "mean")).unstack()
reg_q["rev_last2w_share%"] = 100 * reg_q[("rev", True)] / reg_q["rev"].sum(axis=1)
print(reg_q)
rep = tbl(b2b, ["sales_rep"])
rep["region"] = b2b.groupby("sales_rep").region.agg(lambda s: s.mode()[0])
rep["regions"] = b2b.groupby("sales_rep").region.nunique()
rep["last2w_rev%"] = 100 * b2b[b2b.last2w].groupby("sales_rep").revenue.sum() / rep.revenue
print("\nby rep:")
print(rep.sort_values("revenue", ascending=False)[["region", "regions", "orders", "revenue", "rev_share%", "disc%", "gm%", "ret%", "unpaid", "last2w_rev%"]])

print("\n================ CFO: cash tight, unpaid invoices?")
b2b = o[o.terms_days > 0].copy()
print("unpaid at extraction: n=", b2b.payment_date.isna().sum(), " $", round(b2b.unpaid_amt.sum()))
paid = b2b[b2b.payment_date.notna()]
paid = paid.assign(dso=(paid.payment_date - paid.order_date).dt.days, late=(paid.payment_date - paid.due).dt.days)
print("paid invoices: share paid late %:", round(100 * (paid.late > 0).mean(), 1))
print(paid.groupby(["segment", "year"]).agg(n=("dso", "size"), avg_days_to_pay=("dso", "mean"),
                                            late_share=("late", lambda s: (s > 0).mean()),
                                            avg_late=("late", lambda s: s[s > 0].mean())))
print(paid.groupby(["region"]).agg(avg_days_to_pay=("dso", "mean"), late_share=("late", lambda s: (s > 0).mean()),
                                   avg_late=("late", lambda s: s[s > 0].mean())))
print("unpaid by region/segment:")
print(b2b[b2b.payment_date.isna()].groupby(["region", "segment"]).agg(n=("order_id", "size"), amt=("revenue", "sum"),
                                                                      oldest=("order_date", "min")))

# open balance per customer at each order (incl. that order) vs credit limit
far = pd.Timestamp("2100-01-01")
ob = {}
for cid, g in b2b.sort_values("order_date").groupby("customer_id"):
    pdt = g.payment_date.fillna(far).values
    od = g.order_date.values
    amt = g.revenue.values
    for i, idx in enumerate(g.index):
        ob[idx] = amt[(od <= od[i]) & (pdt > od[i])].sum()
b2b["open_bal"] = pd.Series(ob)
b2b["over_limit"] = b2b.open_bal > b2b.credit_limit
print("\norders placed while customer over credit limit: n=", b2b.over_limit.sum(), " $", round(b2b[b2b.over_limit].revenue.sum()))
print(b2b.groupby(["region"]).agg(orders=("order_id", "size"), over_n=("over_limit", "sum"),
                                  over_rev=("revenue", lambda s: s[b2b.loc[s.index, "over_limit"]].sum())))
print(b2b.groupby(["segment"]).over_limit.agg(["sum", "mean"]))
print("by rep:", b2b.groupby("sales_rep").over_limit.sum().to_dict())
bal_now = b2b[b2b.payment_date.isna()].groupby("customer_id").revenue.sum()
cl = c.set_index("customer_id").credit_limit
print("customers over limit at extraction:", (bal_now > cl.reindex(bal_now.index)).sum(), "of", len(bal_now), "with open balance")

print("\n================ OPS: returns eat warehouse time, big items?")
print(tbl(o, "category")[["orders", "revenue", "refunds", "ret%"]])
rq = o.groupby("category").agg(units=("quantity", "sum"), units_ret=("qty_ret", "sum"), returns=("qty_ret", lambda s: (s > 0).sum()))
rq["unit_ret%"] = 100 * rq.units_ret / rq.units
print(rq)
print(tbl(o, ["segment"])[["revenue", "refunds", "ret%"]])
print(tbl(o, ["region"])[["revenue", "refunds", "ret%"]])
rm = r.merge(o[["order_id", "segment", "region", "category", "last2w", "sales_rep"]], on="order_id")
print("\nreasons x segment:")
print(pd.crosstab(rm.reason, rm.segment))
print("\nreasons x region:")
print(pd.crosstab(rm.reason, rm.region))
print("\nreturns from quarter-end (last 2w) orders share %:", round(100 * rm.last2w.mean(), 1),
      "vs share of all orders in last2w %:", round(100 * o.last2w.mean(), 1))
res = o[o.segment == "Reseller"].groupby("last2w")[["refund", "revenue"]].sum()
print("reseller refund % by quarter-end flag:", (100 * res.refund / res.revenue).round(1).to_dict())

print("\n================ CS: long-time business customers went quiet?")
biz = o[o.segment.isin(["SMB", "Enterprise", "Reseller"])]
s = biz.sort_values("order_date").groupby("customer_id").agg(
    first=("order_date", "min"), last=("order_date", "max"), n=("order_id", "size"),
    gap_med=("order_date", lambda d: d.diff().dt.days.median()),
    rev25=("revenue", lambda v: v[biz.loc[v.index, "year"] == 2025].sum()))
s = s.join(c.set_index("customer_id")[["segment", "region", "signup_date", "account_rep", "credit_limit"]])
s["days_silent"] = (pd.Timestamp("2026-09-30") - s["last"]).dt.days
s["longtime"] = s.signup_date < "2024-01-01"
s["quiet"] = (s.days_silent > 2 * s.gap_med) & (s.days_silent > 60)
print(s.groupby(["segment", "longtime"]).agg(cust=("n", "size"), quiet=("quiet", "sum"), rev25=("rev25", "sum"),
                                             quiet_rev25=("rev25", lambda v: v[s.loc[v.index, "quiet"]].sum())))
q = s[s.quiet]
print("quiet by region:", q.region.value_counts().to_dict(), "| by rep:", q.account_rep.value_counts().to_dict())
qo = biz[biz.customer_id.isin(q.index)]
oth = biz[~biz.customer_id.isin(q.index)]
print(f"refund rate quiet customers {100 * qo.refund.sum() / qo.revenue.sum():.1f}% vs others {100 * oth.refund.sum() / oth.revenue.sum():.1f}%")
dr = r.merge(biz[["order_id", "customer_id"]], on="order_id")
bad = dr[dr.customer_id.isin(q.index) & dr.reason.isin(["Damaged in transit", "Defective", "Wrong item shipped"])]
print("quiet customers with a damaged/defective/wrong-item return:", bad.customer_id.nunique(), "of", len(q))
print("quiet customers late-payment share %:", round(100 * (qo.days_late > 0).mean(), 1), "vs others", round(100 * (oth.days_late > 0).mean(), 1))
print("quiet customers avg discount %:", round(100 * qo.discount.mean(), 1), "vs others", round(100 * oth.discount.mean(), 1))
o.to_pickle("explore/_orders_clean.pkl")
s.to_pickle("explore/_cust_activity.pkl")
