"""Look closer at each cleaning trap found in 01_profile."""
import pandas as pd
pd.set_option("display.width", 220); pd.set_option("display.max_columns", 30)
RAW = "data/raw/chrome_oak"
c = pd.read_csv(f"{RAW}/customers.csv")
o = pd.read_csv(f"{RAW}/orders.csv")
r = pd.read_csv(f"{RAW}/returns.csv")

print("REGION spellings:", o.region.value_counts().to_dict())
print("\nPRODUCTS:", o.groupby(["category", "product"]).size().to_dict())
print("\nREPS orders:", sorted(o.sales_rep.dropna().unique()), "| customers:", sorted(c.account_rep.dropna().unique()))

nd = o[~o.order_date.str.match(r"^\d{4}-")].order_date
parts = nd.str.split("/", expand=True).astype(int)
print(f"\nNON-ISO DATES n={len(nd)}: first part max={parts[0].max()} second part max={parts[1].max()} years={parts[2].unique()}")

print("\nDISCOUNT > 1:", (o.discount > 1).sum(), sorted(o.discount[o.discount > 1].unique())[:30])
print("discount 0.5-1:", ((o.discount > 0.5) & (o.discount <= 1)).sum())

print("\nNEGATIVE QTY rows:\n", o[o.quantity < 0][["order_id", "order_date", "customer_id", "product", "quantity", "unit_price", "sales_channel", "payment_date"]])

dup = o[o.duplicated(keep=False)].sort_values("order_id")
print("\nDUPES sample:\n", dup.head(4)[["order_id", "order_date", "customer_id", "quantity", "unit_price"]])
same_id_diff_row = o[o.order_id.duplicated(keep=False) & ~o.duplicated(keep=False)]
print("same order_id but different content:", len(same_id_diff_row))

print("\nBLANK unit_cost by product:", o[o.unit_cost.isna()]["product"].value_counts().head(5).to_dict())
print("BLANK payment_date by channel:", o[o.payment_date.isna()].sales_channel.value_counts().to_dict())
print("cost blank & payment blank same rows?", (o.unit_cost.isna() & o.payment_date.isna()).sum())

print("\nORPHANS: order customers not in customers:", (~o.customer_id.isin(c.customer_id)).sum(),
      "| return orders not in orders:", (~r.order_id.isin(o.order_id)).sum(),
      "| customers with no orders:", (~c.customer_id.isin(o.customer_id)).sum())

m = o.merge(c[["customer_id", "region", "segment", "account_rep", "payment_terms"]], on="customer_id", how="left", suffixes=("", "_cust"))
print("\nseg x channel:\n", pd.crosstab(m.segment, m.sales_channel))
print("\nterms x channel:\n", pd.crosstab(m.payment_terms, m.sales_channel))
print("\norder rep != customer account_rep (non-null both):", ((m.sales_rep != m.account_rep) & m.sales_rep.notna() & m.account_rep.notna()).sum())

od = pd.to_datetime(o.order_date, format="mixed")
print("\nORDER DATE range:", od.min(), od.max(), "| outside 2025-01..2026-09:", ((od < "2025-01-01") | (od > "2026-09-30")).sum())
pdt = pd.to_datetime(o.payment_date)
print("payment before order:", (pdt < od).sum(), "| payment after extraction 2026-10-31:", (pdt > "2026-10-31").sum())

rr = r.merge(o.drop_duplicates()[["order_id", "order_date", "quantity", "unit_price", "discount", "product"]], on="order_id", how="left")
rr["od"] = pd.to_datetime(rr.order_date, format="mixed"); rr["rd"] = pd.to_datetime(rr.return_date)
print("\nRETURN qty > ordered qty:", (rr.quantity_returned > rr.quantity).sum(), "| return before order:", (rr.rd < rr.od).sum())
rr["net_unit"] = rr.unit_price * (1 - rr.discount.where(rr.discount <= 1, rr.discount / 100))
rr["implied"] = rr.refund_amount / rr.quantity_returned / rr.net_unit
print("refund / (qty_ret * net price) ratio:", rr.implied.describe().round(3).to_dict())
