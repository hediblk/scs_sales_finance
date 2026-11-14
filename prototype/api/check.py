"""Recompute the headline numbers from the raw files and check them against docs/PLAN.md.

    .venv/Scripts/python.exe -m api.check

OK     matches PLAN (within rounding)
MOVED  close to PLAN but not the same: the PLAN number came from before the final cleaning decisions
FAIL   off by more than the tolerance: the pitch must not use the PLAN number
Exit code 1 if any FAIL. Answers "how do you know this is right?" in Q&A.
"""
import sys

import pandas as pd

from . import detect, story
from .pipeline import load as build  # check what the API serves: data/clean as it is

ds = build()
o = ds.orders
rows = []


def check(name, plan, got, tol, unit="", exact=False):
    diff = abs(got - plan)
    if exact:
        status = "OK" if diff == 0 else "FAIL"
    else:
        status = "OK" if diff <= tol / 4 else ("MOVED" if diff <= tol else "FAIL")
    rows.append((status, name, plan, got, unit))


h = story.headline(ds)
g = h["growth"]
check("Revenue growth Jan-Sep (%)", 33, g["revenue"], 1.0, "%")
check("Gross profit growth (%)", 22, g["gross_profit"], 1.5, "%")
check("Gross profit minus refunds growth (%)", 10, g["gp_minus_refunds"], 1.5, "%")
check("Refunds growth (%)", 67, g["refunds"], 2, "%")

reps = story.rep_stats(ds)
r07, oth = reps.loc["R07"], reps.drop("R07")
check("R07 share of revenue in last 14 days (%)", 48, r07.qe_share_pct, 1.5, "%")
check("R07 average discount (%)", 27, r07.discount_pct, 1.0, "%")
check("Other reps, lowest average discount (%)", 9, oth.discount_pct.min(), 1.0, "%")
check("Other reps, highest average discount (%)", 12, oth.discount_pct.max(), 1.0, "%")

bands = {b["band"]: b for b in story.discount_bands(ds)}
check("30-40% band return rate (%)", 23.4, bands["30-40%"]["return_rate"], 1.0, "%")
check("30-40% band margin (%)", 5.8, bands["30-40%"]["margin"], 1.0, "%")

ov = ds.returns[ds.returns.reason == "Overstock / ordered in error"]
lag = (ov.return_date - ov.order_date).dt.days
check("Overstock returns (count)", 46, len(ov), 0, exact=True)
check("Overstock returns, all R07", 46, int((ov.sales_rep == "R07").sum()), 0, exact=True)
check("Overstock refunds ($k)", 150.5, ov.refund_amount.sum() / 1000, 0.5, "$k")
check("Overstock return lag, min (days)", 20, lag.min(), 0, exact=True)
check("Overstock return lag, max (days)", 44, lag.max(), 0, exact=True)

js = o[o.order_date.dt.month <= 9]
atl = js[(js.region == "Atlantic") & js.segment.isin(["SMB", "Enterprise"])].groupby("year").revenue.sum()
check("Atlantic SMB + Enterprise revenue change (%)", -25, 100 * (atl[2026] / atl[2025] - 1), 1.5, "%")

# Atlantic margin at the company's product mix: per-product margin in Atlantic, weighted by company revenue mix
k = o[o.cost_known & o.is_business]
mix = k.groupby("product").revenue.sum() / k.revenue.sum()
def mix_margin(df):
    m = df.groupby("product").apply(lambda x: x.gp.sum() / x.revenue.sum(), include_groups=False)
    return 100 * (m * mix).sum() / mix[m.index].sum()
check("Atlantic margin at company product mix (%)", 17.5, mix_margin(k[k.region == "Atlantic"]), 1.0, "%")
check("Other regions margin at company product mix (%)", 32, mix_margin(k[k.region != "Atlantic"]), 1.5, "%")

ar = detect.ar_position(ds)
check("Overdue at extraction ($k)", 135, ar.overdue_amt.sum() / 1000, 2, "$k")
check("Customers past 60 days overdue", 3, int((ar.max_overdue > 60).sum()), 0, exact=True)
check("C1173 owed ($k)", 27.6, ar.loc["C1173"].owed / 1000, 0.2, "$k")
check("C1173 credit limit ($k)", 25, ar.loc["C1173"].credit_limit / 1000, 0, exact=True)
check("C1173 days overdue", 221, int(ar.loc["C1173"].max_overdue), 0, exact=True)

furn = {f["region"]: f for f in story.furniture_damage(ds)}
check("BC furniture damage refunds (% of furniture revenue)", 16.9, furn["BC"]["damage_refund_pct"], 0.5, "%")
check("Prairies furniture damage refunds (%)", 15.4, furn["Prairies"]["damage_refund_pct"], 0.5, "%")
check("BC revenue growth (%)", 50, furn["BC"]["revenue_growth_pct"], 2, "%")

qs = story.quiet_stats(ds)
check("Quiet business customers", 70, qs["quiet"], 0, exact=True)
check("Quiet customers 2025 spend ($k)", 619, qs["quiet_rev25"] / 1000, 3, "$k")
check("Quiet customers with a bad return (%)", 59, qs["quiet_bad_pct"], 1.0, "%")
check("Active customers with a bad return (%)", 27, qs["active_bad_pct"], 1.0, "%")
q = detect.quiet_customers(ds)
bad = detect.bad_return_hits(ds)
last_bad = bad.groupby("customer_id").return_date.max()
qq = q[q.quiet].join(last_bad.rename("lb"))
check("Quiet customers whose bad return came at or after their last order",
      41, int((qq.lb.notna() & (qq.lb >= qq["last"] - pd.Timedelta(days=45))).sum()), 0, exact=True)

c1 = detect.qe_simulate(ds, 25, 14)
check("C1 hits (25%, 14 days)", 207, c1["hits"], 0, exact=True)
check("C1 hits by R07", 205, c1["top_owner_hits"], 0, exact=True)
check("C1 revenue ($k)", 893, c1["amount"] / 1000, 2, "$k")
check("C1 later refunded ($k)", 171, c1["refunds_caught"] / 1000, 1, "$k")
check("C1 return rate of flagged orders (%)", 25.1, c1["return_rate"], 0.5, "%")
check("Return rate of other business orders (%)", 4.2, c1["return_rate_other"], 0.5, "%")
c7 = detect.qe_simulate(ds, 25, 7)
check("C1 hits, 7-day window", 183, c7["hits"], 0, exact=True)
check("C1 hits by R07, 7-day window", 181, c7["top_owner_hits"], 0, exact=True)
bc = o[o.below_cost]
check("Orders sold below cost (all)", 41, len(bc), 0, exact=True)
check("Orders sold below cost, R07", 40, int((bc.sales_rep == "R07").sum()), 0, exact=True)
check("C1 hits sold below cost", 40, c1["below_cost"], 0, exact=True)

bl = detect.company_discount_baseline(ds)
check("Company median discount (%)", 10.1, 100 * bl["median"], 0.2, "%")
check("Company median + 3 scaled MAD (%)", 27, 100 * bl["median_plus_3mad"], 0.5, "%")
check("Other reps 99th percentile discount (%)", 20.6, 100 * bl["other_reps_p99"], 0.2, "%")

# out of sample: threshold from 2025 only (other reps p99), applied to 2026
b25 = o[o.sales_rep.notna() & (o.sales_rep != "R07") & (o.year == 2025)].discount.quantile(0.99)
h26 = o[o.is_business & (o.year == 2026) & (o.days_to_qend <= 13) & (o.discount >= b25)]
check("Out of sample: 2025 other-rep p99 (%)", 20.1, 100 * b25, 0.2, "%")
check("Out of sample: 2026 hits", 141, len(h26), 0, exact=True)
check("Out of sample: 2026 hits by R07", 124, int((h26.sales_rep == "R07").sum()), 0, exact=True)

# per-rep baseline (rejected): each rep's own median + 3 scaled MAD, last 14 days
b = o[o.sales_rep.notna()]
stats = b.groupby("sales_rep").discount.agg(med="median", mad=lambda d: 1.4826 * (d - d.median()).abs().median())
thr = b.sales_rep.map(stats.med + 3 * stats.mad)
per_rep = b[(b.days_to_qend <= 13) & (b.discount >= thr)]
check("Per-rep baseline hits (rejected rule)", 9, len(per_rep), 0, exact=True)
check("Per-rep baseline hits by R07", 0, int((per_rep.sales_rep == "R07").sum()), 0, exact=True)

c2 = detect.bad_return_simulate(ds)
check("C2 bad returns on business accounts", 130, c2["hits"], 0, exact=True)
check("C2 customers", 104, c2["customers"], 0, exact=True)

check("Margin coverage, lines with known cost (%)", 98.5, ds.summary["cost_coverage_pct"], 0.1, "%")

w = max(len(r[1]) for r in rows)
for status, name, plan, got, unit in rows:
    print(f"{status:5}  {name:<{w}}  PLAN {plan:>9}  now {round(float(got), 2):>11}")
n = {s: sum(1 for r in rows if r[0] == s) for s in ("OK", "MOVED", "FAIL")}
print(f"\n{n['OK']} OK, {n['MOVED']} MOVED, {n['FAIL']} FAIL")
sys.exit(1 if n["FAIL"] else 0)
