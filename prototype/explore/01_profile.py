"""Raw profile of the Chrome & Oak files: shape, types, nulls, odd values."""
import re
import pandas as pd

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)
RAW = "data/raw/chrome_oak"

files = {n: pd.read_csv(f"{RAW}/{n}.csv", dtype=str, keep_default_na=False) for n in ["customers", "orders", "returns"]}

for name, df in files.items():
    print(f"\n################ {name}: {df.shape}")
    for c in df.columns:
        s = df[c]
        blanks = (s.str.strip() == "").sum()
        nun = s.nunique()
        sample = s.value_counts().head(8).to_dict() if nun <= 40 else s.sample(5, random_state=1).tolist()
        print(f"- {c}: unique={nun} blanks={blanks} :: {sample}")
    print("full-row dupes:", df.duplicated().sum())
    idcol = df.columns[0]
    print(f"dupe {idcol}:", df[idcol].duplicated().sum())

# date format check
date_cols = {"customers": ["signup_date"], "orders": ["order_date", "payment_date"], "returns": ["return_date"]}
iso = re.compile(r"^\d{4}-\d{2}-\d{2}$")
for name, cols in date_cols.items():
    for c in cols:
        s = files[name][c]
        bad = s[(s != "") & ~s.str.match(iso)]
        print(f"\n{name}.{c}: non-ISO={len(bad)} e.g. {bad.head(8).tolist()}")

# numeric check
num_cols = {"customers": ["credit_limit"], "orders": ["quantity", "unit_price", "discount", "unit_cost"], "returns": ["quantity_returned", "refund_amount"]}
for name, cols in num_cols.items():
    for c in cols:
        s = files[name][c]
        num = pd.to_numeric(s, errors="coerce")
        bad = s[num.isna() & (s != "")]
        print(f"\n{name}.{c}: non-numeric={len(bad)} e.g. {bad.head(6).tolist()} | describe:\n{num.describe().round(3).to_dict()}")
        print("  negatives:", (num < 0).sum(), " zeros:", (num == 0).sum())
