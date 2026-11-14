"""Follow-ups on the threads 03_claims opened."""
import warnings
import pandas as pd

warnings.filterwarnings("ignore")
pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 30)
pd.set_option("display.float_format", "{:,.1f}".format)
EXTRACT = pd.Timestamp("2026-10-31")
o = pd.read_pickle("explore/_orders_clean.pkl")
s = pd.read_pickle("explore/_cust_activity.pkl")
r = pd.read_csv("data/raw/chrome_oak/returns.csv", parse_dates=["return_date"])

print("=== R07 by quarter: revenue, quarter-end share, discount, reseller share, overstock refunds")
r07 = o[o.sales_rep == "R07"]
qq = r07.groupby("q").agg(rev=("revenue", "sum"), disc=("discount", "mean"), refunds=("refund", "sum"))
qq["last2w%"] = 100 * r07[r07.last2w].groupby("q").revenue.sum() / qq.rev
qq["reseller%"] = 100 * r07[r07.segment == "Reseller"].groupby("q").revenue.sum() / qq.rev
qq["disc"] *= 100
print(qq)
print("R07 customers by segment:", r07.groupby("segment").customer_id.nunique().to_dict())
top = r07[r07.segment == "Reseller"].groupby("customer_id").agg(rev=("revenue", "sum"), refunds=("refund", "sum"), orders=("order_id", "size"),
                                                                  last2w_rev=("revenue", lambda v: v[r07.loc[v.index, "last2w"]].sum()))
top = top.join(s[["credit_limit"]])
print(top.sort_values("rev", ascending=False))

ov = r.merge(o[["order_id", "order_date", "customer_id", "sales_rep", "last2w", "revenue"]], on="order_id")
ov = ov[ov.reason == "Overstock / ordered in error"]
ov["days_after_order"] = (ov.return_date - ov.order_date).dt.days
print("\noverstock returns: n", len(ov), "| from quarter-end orders:", ov.last2w.sum(), "| days order->return median",
      ov.days_after_order.median(), "| refunds $", round(ov.refund_amount.sum()), "| reps:", ov.sales_rep.value_counts().to_dict())

print("\n=== Commission view: R07 revenue with vs without overstock-returned orders and at normal discount")
r07_rev = r07.revenue.sum()
r07_net = r07_rev - r07.refund.sum()
print(f"R07 booked {r07_rev:,.0f}, net of refunds {r07_net:,.0f}, GP {r07.gp.sum():,.0f}, GP after refunds {r07.gp.sum() - r07.refund.sum():,.0f}")
others = o[o.sales_rep.notna() & (o.sales_rep != "R07")]
print(f"other reps GP margin after refunds: {100 * (others.gp.sum() - others.refund.sum()) / others.revenue.sum():.1f}% vs R07 {100 * (r07.gp.sum() - r07.refund.sum()) / r07_rev:.1f}%")
atl_direct = o[(o.region == "Atlantic") & o.segment.isin(["SMB", "Enterprise"])]
print("Atlantic SMB+Enterprise revenue by year (Jan-Sep):", atl_direct[atl_direct.order_date.dt.month <= 9].groupby("year").revenue.sum().round(0).to_dict())

print("\n=== CFO: overdue aging at extraction (2026-10-31)")
b2b = o[o.terms_days > 0].copy()
un = b2b[b2b.payment_date.isna()].copy()
un["days_overdue"] = (EXTRACT - un.due).dt.days
un["bucket"] = pd.cut(un.days_overdue, [-999, 0, 30, 60, 90, 9999], labels=["not due", "1-30", "31-60", "61-90", "90+"])
print(un.groupby("bucket").agg(n=("order_id", "size"), amt=("revenue", "sum"), customers=("customer_id", "nunique")))
cust_un = un.groupby("customer_id").agg(n=("order_id", "size"), owed=("revenue", "sum"), max_overdue=("days_overdue", "max")).join(
    s[["segment", "region", "account_rep", "credit_limit"]]).sort_values("owed", ascending=False)
cust_un["owed/limit"] = cust_un.owed / cust_un.credit_limit
print(cust_un.head(15))
print("customers with invoice 60+ days overdue:", (cust_un.max_overdue > 60).sum(), " $", round(cust_un[cust_un.max_overdue > 60].owed.sum()))
# did they keep ordering after the first unpaid invoice went overdue?
first_od = un[un.days_overdue > 0].groupby("customer_id").due.min()
after = b2b.merge(first_od.rename("first_overdue_due"), left_on="customer_id", right_index=True)
after = after[after.order_date > after.first_overdue_due]
print("orders shipped AFTER the customer already had an overdue unpaid invoice: n", len(after), " $", round(after.revenue.sum()),
      "| by rep:", after.sales_rep.value_counts().to_dict())

print("\n=== Late payment history: chronic late payers")
paid = b2b[b2b.payment_date.notna()].copy()
paid["late"] = (paid.payment_date - paid.due).dt.days
lp = paid.groupby("customer_id").agg(inv=("order_id", "size"), late_share=("late", lambda x: (x > 0).mean()), avg_late=("late", "mean"), max_late=("late", "max"))
print(lp.describe().round(1))
print("customers with >=60% invoices late and >=5 invoices:", ((lp.late_share >= 0.6) & (lp.inv >= 5)).sum())
print("late share by payment-days distribution:", paid.late.describe().round(1).to_dict())

print("\n=== CS: why did quiet customers leave? timing of bad return vs last order")
biz_ids = s.index
q = s[s.quiet]
rr = r.merge(o[["order_id", "customer_id", "product", "category"]], on="order_id")
bad = rr[rr.reason.isin(["Damaged in transit", "Defective", "Wrong item shipped"])]
lastbad = bad.groupby("customer_id").return_date.max()
qq2 = q.join(lastbad.rename("last_bad_return"))
qq2["bad_return_then_silence"] = qq2.last_bad_return.notna() & (qq2.last_bad_return >= qq2["last"] - pd.Timedelta(days=45))
print("quiet customers:", len(q), "| had bad return within 45d of (or after) their last order:", qq2.bad_return_then_silence.sum())
nq = s[~s.quiet].join(lastbad.rename("last_bad_return"))
print("share of quiet customers with ANY bad return:", round(100 * qq2.last_bad_return.notna().mean(), 1),
      "% vs active business customers:", round(100 * nq.last_bad_return.notna().mean(), 1), "%")
print("quiet rate by region (business customers):", (100 * s.groupby("region").quiet.mean()).round(1).to_dict())
print("quiet rate by rep:", (100 * s.groupby("account_rep").quiet.mean()).round(1).to_dict())
print("bad-return categories for quiet customers:", bad[bad.customer_id.isin(q.index)].category.value_counts().to_dict())
print("damaged-in-transit refund rate by region x category %:")
dm = rr[rr.reason == "Damaged in transit"].groupby(["region_x" if "region_x" in rr else "category"]).refund_amount.sum() if False else None
od = o.merge(r[r.reason == "Damaged in transit"][["order_id", "refund_amount"]].rename(columns={"refund_amount": "dmg"}), on="order_id", how="left").fillna({"dmg": 0})
t = od.groupby(["region", "category"]).agg(rev=("revenue", "sum"), dmg=("dmg", "sum"))
print((100 * t.dmg / t.rev).unstack().round(1))
print("quiet customers' 2025 revenue at risk $", round(q.rev25.sum()), "| long-time quiet:", int(q.longtime.sum()))
