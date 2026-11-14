"""Ask: a read-only assessment tool. AI writes one SELECT, DuckDB runs it, the answer is worded from the rows.

Safety, in layers:
1. The tables live in a DuckDB file built from data/clean at startup; questions run on a *read-only* connection
   with external access off (no reading other files, no network).
2. The SQL must be one statement that starts with SELECT or WITH, with no write / DDL / file keyword.
3. Results are capped at MAX_ROWS.
Ask cannot create, clear or change alerts: it never touches the action log.
"""
import re
from pathlib import Path

import duckdb
import pandas as pd

from . import ai
from .detect import fmt_money
from .pipeline import Dataset

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "state" / "ask.duckdb"
MAX_ROWS = 500

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|create|drop|alter|truncate|copy|attach|detach|pragma|install|load|export|import|"
    r"call|set|reset|vacuum|checkpoint|grant|revoke|begin|commit|rollback|use)\b|"
    r"\b(read_csv\w*|read_parquet|read_json\w*|read_text|read_blob|glob|parquet_scan|sniff_csv|getenv|current_setting)\s*\(",
    re.I)

DATA_TABLE = re.compile(r"\b(from|join)\s+(orders|customers|returns)\b", re.I)
OUT_OF_SCOPE_MSG = ("Ask only answers questions about the Chrome & Oak data: orders, customers and returns "
                    "(Jan 2025 to Sep 2026). Try a question about revenue, discounts, reps, regions, returns or payments.")
SQL_SYSTEM = ("You are the query writer inside Chrome & Oak Office Supply's internal data tool. You only answer questions "
              "about Chrome & Oak's own sales data, using the three tables described. Write one read-only DuckDB SELECT that "
              "reads from those tables. If the question is not about this data, or the tables cannot answer it (general "
              "knowledge, other companies, advice, chit-chat, writing tasks, future predictions), reply with exactly "
              "OUT_OF_SCOPE and nothing else. Return shares and rates as percentages (0 to 100, rounded to 1 decimal) "
              "and money rounded to whole dollars. Column aliases in lower_snake_case with no currency word (all amounts "
              "are Canadian dollars), e.g. total_refunds, revenue, refund_rate_pct. Write one compact SELECT: no comments, "
              "no alignment padding or blank lines, at most 15 output columns. Reply with the SQL only.")
SQL_MAX_TOKENS = 2000
QUERY_FAILED_MSG = ("Ask could not turn this question into a working query. Try asking it more directly, for example "
                    "naming the customer, rep, product or period.")
ANSWER_SYSTEM = ("You answer questions about Chrome & Oak Office Supply's sales data using only the query result you are "
                 "given. Never add outside knowledge. All money is in Canadian dollars: write amounts as $1,234,567 "
                 "(thousands separators, no decimals), never USD or another currency. Write percentages with a % sign. "
                 "Use the numbers from the result, only adding thousands separators. Write the final answer only: no "
                 "working, no corrections, no second attempt. Plain text, no markdown.")
LEAK = re.compile(r"\.\.\.\s*no\b|\bno:|\bwait\b|\bactually,|\bcorrection\b|\blet me\b|\bUSD\b|US\$", re.I)
MONEY_WORDS = ("revenue", "refund", "amount", "cost", "price", "profit", "gp", "cogs", "limit", "balance", "owed", "sales", "spend")
PCT_WORDS = ("pct", "percent", "rate", "share")
COUNT_WORDS = ("orders", "count", "units", "quantity", "accounts", "customers", "invoices", "num_", "n_")

SCHEMA = """Tables (DuckDB SQL):
orders(order_id, order_date DATE, customer_id, region, product, category, quantity INT, unit_price DOUBLE,
       discount DOUBLE  -- fraction, 0.25 = 25%,
       unit_cost DOUBLE -- NULL when unknown, sales_channel, sales_rep -- NULL for online orders,
       payment_date DATE -- NULL = unpaid at extraction 2026-10-31, segment, payment_terms, credit_limit DOUBLE,
       list_rev DOUBLE, revenue DOUBLE  -- quantity*unit_price*(1-discount), gp DOUBLE -- NULL when cost unknown,
       refund DOUBLE -- refunded on this order, returned BOOLEAN, return_reason, year INT, quarter  -- e.g. 2026Q3,
       days_to_qend INT -- 0 = last day of the quarter, due_date DATE)
customers(customer_id, segment  -- Consumer, SMB, Enterprise, Reseller, region, signup_date DATE, account_rep, payment_terms, credit_limit DOUBLE)
returns(return_id, order_id, return_date DATE, quantity_returned INT, reason, refund_amount DOUBLE, customer_id, segment, region, sales_rep, product, category, order_date DATE)
Regions: Ontario, Quebec, Atlantic, BC, Prairies. Data: orders Jan 2025 to Sep 2026."""

ORDER_COLS = ["order_id", "order_date", "customer_id", "region", "product", "category", "quantity", "unit_price", "discount",
              "unit_cost", "sales_channel", "sales_rep", "payment_date", "segment", "payment_terms", "credit_limit",
              "list_rev", "revenue", "gp", "refund", "returned", "return_reason", "year", "quarter", "days_to_qend", "due_date"]


def build_db(ds: Dataset):
    """Write the clean tables into a DuckDB file once (this is the only write connection)."""
    DB.parent.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()
    con = duckdb.connect(str(DB))
    orders = ds.orders[ORDER_COLS].copy()
    customers = ds.customers.copy()
    returns = ds.returns[["return_id", "order_id", "return_date", "quantity_returned", "reason", "refund_amount", "customer_id",
                          "segment", "region", "sales_rep", "product", "category", "order_date"]].copy()
    for df in (orders, customers, returns):
        for col in df.columns:
            if str(df[col].dtype).startswith(("string", "object")):
                df[col] = df[col].astype(object).where(df[col].notna(), None)
    for name, df in (("orders", orders), ("customers", customers), ("returns", returns)):
        con.register("tmp_df", df)
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM tmp_df")
        con.unregister("tmp_df")
    con.close()


def _connect():
    return duckdb.connect(str(DB), read_only=True, config={"enable_external_access": False})


def check_sql(sql):
    """Return (clean_sql, error). One SELECT (or WITH ... SELECT) only."""
    s = re.sub(r"^\s*```(?:sql)?|```\s*$", "", (sql or "").strip(), flags=re.I).strip()
    s = s.rstrip(";").strip()
    if not s:
        return None, "Empty query"
    if ";" in s:
        return None, "Only one statement is allowed"
    if not re.match(r"^(select|with)\b", s, re.I):
        return None, "Only SELECT queries are allowed"
    no_strings = re.sub(r"'[^']*'", "''", s)
    if FORBIDDEN.search(no_strings):
        return None, f"Refused: '{FORBIDDEN.search(no_strings).group(0)}' is not allowed in a read-only question"
    if not DATA_TABLE.search(no_strings):
        return None, OUT_OF_SCOPE_MSG
    return s, None


def run_sql(sql):
    s, err = check_sql(sql)
    if err:
        return None, err
    con = _connect()
    try:
        df = con.execute(f"SELECT * FROM ({s}) AS q LIMIT {MAX_ROWS}").df()
        total = int(con.execute(f"SELECT count(*) FROM ({s}) AS q").fetchone()[0]) if len(df) == MAX_ROWS else len(df)
    except duckdb.Error as e:
        return None, f"Query failed: {str(e).splitlines()[0][:300]}"
    finally:
        con.close()
    df.attrs["total_rows"] = total
    return df, None


def _jsonable(v):
    try:
        if v is None or pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, pd.Timestamp):
        return f"{v:%Y-%m-%d}"
    if hasattr(v, "item"):
        return v.item()
    if hasattr(v, "isoformat"):
        return v.isoformat()[:10]
    return v


TIME_WORDS = ("month", "date", "quarter", "week", "year", "day")
TIME_VALUE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?|Q[1-4]|-W\d{2})?$")
TOP_N = 20


def _is_num(s):
    return pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s)


def _is_time(df, col):
    s = df[col]
    if pd.api.types.is_datetime64_any_dtype(s) or any(w in col.lower() for w in TIME_WORDS):
        return True
    vals = s.dropna().astype(str)
    return len(vals) > 0 and vals.str.match(TIME_VALUE).all() and not _is_num(s)


def _label(col):
    return col.replace("_", " ")


def _records(df):
    return [{c: _jsonable(v) for c, v in zip(df.columns, r)} for r in df.itertuples(index=False)]


def _chart(df):
    """Pick the visual from the result's shape (never by the AI). Never None when there are rows.
    Every chart except kpi / kpis carries its own `rows`, so a top-20 cut or a count does not depend on the table."""
    if df is None or df.empty:
        return None
    n = int(df.attrs.get("total_rows", len(df)))
    cols = list(df.columns)
    nums = [c for c in cols if _is_num(df[c])]

    if len(df) == 1:
        row = df.iloc[0]
        if len(cols) == 1 or not nums:
            return {"type": "kpi", "label": _label(cols[0] if not nums else nums[0]), "value": _jsonable(row[cols[0]])}
        context = " · ".join(str(row[c]) for c in cols if c not in nums)
        items = [{"label": _label(c) + (f" ({context})" if context and len(nums) == 1 else ""), "value": _jsonable(row[c])} for c in nums]
        if len(items) == 1:
            return dict({"type": "kpi"}, **items[0])
        return {"type": "kpis", "items": items, **({"note": context} if context else {})}

    first = cols[0]
    series_cols = [c for c in nums if c != first][:3]
    if _is_time(df, first) and series_cols:
        d = df[[first] + series_cols].sort_values(first)
        return {"type": "line", "x": first, "series": [{"key": c, "label": _label(c)} for c in series_cols], "rows": _records(d),
                **({"note": f"First {len(df)} of {n} points"} if n > len(df) else {})}

    if nums and len(nums) == len(cols):
        if len(cols) >= 2:
            return {"type": "scatter", "x": cols[0], "y": cols[1], "series": [{"key": cols[1], "label": _label(cols[1])}],
                    "rows": _records(df[[cols[0], cols[1]]]),
                    **({"note": f"First {len(df)} of {n} points"} if n > len(df) else {})}
        x = df[cols[0]].dropna().astype(float)  # one numeric column: its distribution
        bins = pd.cut(x, bins=min(TOP_N, max(1, x.nunique())), include_lowest=True)
        counts = bins.value_counts().sort_index()
        return {"type": "bar", "x": "range", "series": [{"key": "rows", "label": "Rows"}],
                "rows": [{"range": f"{iv.left:,.0f} to {iv.right:,.0f}", "rows": int(c)} for iv, c in counts.items()],
                "note": f"Distribution of {_label(cols[0])}" + (f", first {len(df)} of {n} rows" if n > len(df) else "")}

    if series_cols:
        d = df[[first] + series_cols]
        note = None
        if len(d) > TOP_N:
            d = d.sort_values(series_cols[0], ascending=False).head(TOP_N)
            note = f"Top {TOP_N} of {n}"
        return {"type": "bar", "x": first, "series": [{"key": c, "label": _label(c)} for c in series_cols], "rows": _records(d),
                **({"note": note} if note else {})}

    counts = df[first].astype(str).value_counts()
    note = f"Rows per {_label(first)}" + (f", top {TOP_N} of {len(counts)} values" if len(counts) > TOP_N else "") + \
        (f" (first {len(df)} of {n} rows)" if n > len(df) else "")
    return {"type": "bar", "x": first, "series": [{"key": "rows", "label": "Rows"}],
            "rows": [{first: k, "rows": int(v)} for k, v in counts.head(TOP_N).items()], "note": note}


def _gen_sql(question, context, failed_sql=None, failure=None):
    prompt = (f"{SCHEMA}\n\n{('Context, an alert the user is looking at:' + chr(10) + context + chr(10) + chr(10)) if context else ''}"
              f"Question: {question}\n\nReply with one DuckDB SELECT over these tables, or OUT_OF_SCOPE.")
    if failed_sql is not None:
        prompt += (f"\n\nYour previous query failed with: {failure}\nPrevious query:\n{failed_sql}\n"
                   "Return a corrected, shorter single SELECT.")
    if not ai.enabled():
        return None, "no ANTHROPIC_API_KEY"
    return ai._call(SQL_SYSTEM, prompt, max_tokens=SQL_MAX_TOKENS)


def _round(df):
    """Money-like floats to whole numbers, small floats (rates, discounts) to 3 decimals: no 75106.61825 in answers."""
    out = df.copy()
    out.attrs = dict(df.attrs)
    for c in out.columns:
        if pd.api.types.is_float_dtype(out[c]):
            big = out[c].abs().max() >= 100 if out[c].notna().any() else False
            out[c] = out[c].round(0 if big else 3)
            if out[c].dropna().apply(float.is_integer).all():
                out[c] = out[c].astype("Int64")
    return out


def _fmt(col, v):
    """Code-side formatting for the template answer: $ with separators for money, % for rates."""
    if v is None or isinstance(v, str) or not isinstance(v, (int, float)):
        return str(v)
    c = col.lower()
    if any(w in c for w in PCT_WORDS):
        return f"{v:,.1f}%"
    if any(w in c for w in MONEY_WORDS) and not any(w in c for w in COUNT_WORDS):
        return f"${v:,.0f}"
    return f"{v:,.0f}" if float(v).is_integer() or abs(v) >= 100 else f"{v:,.3g}"


def _template_answer(df):
    """Answer written by code when the AI text cannot be used: reads the result's shape, like the chart does."""
    if df.empty:
        return "No rows match."
    cols = list(df.columns)
    nums = [c for c in cols if _is_num(df[c])]
    if len(df) == 1:
        r = df.iloc[0]
        return "; ".join(f"{_label(c)}: {_fmt(c, _jsonable(r[c]))}" for c in cols) + "."
    first = cols[0]
    lead = [c for c in nums if c != first]
    if lead:
        k = lead[0]
        top = df.loc[df[k].idxmax()]
        low = df.loc[df[k].idxmin()]
        return (f"Highest {_label(k)}: {top[first]} ({_fmt(k, _jsonable(top[k]))}). Lowest: {low[first]} "
                f"({_fmt(k, _jsonable(low[k]))}). {int(df.attrs.get('total_rows', len(df)))} rows.")
    return f"{int(df.attrs.get('total_rows', len(df)))} rows returned."


def _empty(error, sql=None):
    return {"answer": None, "sql": sql, "columns": [], "rows": [], "chart": None, "error": error}


def ask(question, alert=None, sql=None):
    context = ""
    if alert:
        ids = [f"{k}: {alert[k]}" for k in ("order_id", "return_id", "product", "segment") if alert.get(k)]
        context = "\n".join([f"{alert['id']} ({alert['condition_id']}), customer_id {alert['entity_id']} ({alert['entity_name']}), "
                             f"rep {alert['owner']}, region {alert['region']}"] + ids + alert["reasons"])
    source = "sql given"
    if not sql:
        # AI-written query: never run one the model did not finish; one corrected retry on a cut-off or failing query
        failed, failure = None, None
        for attempt in range(2):
            gen, source = _gen_sql(question, context, failed, failure)
            if not gen:
                return _empty(f"Ask needs the AI to write the query ({source}). You can also send a SELECT in the `sql` field.")
            if gen.strip().upper().startswith("OUT_OF_SCOPE"):
                return dict(_empty(OUT_OF_SCOPE_MSG), out_of_scope=True)
            if source == "ai_truncated":
                failed, failure = gen, "the query was cut off before it ended (too long)"
                continue
            df, err = run_sql(gen)
            if err and err.startswith("Query failed"):
                failed, failure = gen, err.replace("Query failed: ", "")
                continue
            sql = gen
            if attempt:
                source = "ai (corrected once)"
            break
        else:
            return dict(_empty(QUERY_FAILED_MSG), query_failed=True)
    else:
        df, err = run_sql(sql)
    clean_sql = check_sql(sql)[0]
    if err:
        return dict(_empty(err, clean_sql or sql), out_of_scope=err == OUT_OF_SCOPE_MSG)
    df = _round(df)
    rows = [[_jsonable(v) for v in r] for r in df.itertuples(index=False)]
    preview = df.head(20).to_string(index=False)
    fallback = _template_answer(df)
    answer, how = fallback, "template"
    if ai.enabled() and question:
        text, how = ai.write("answer", f"Question: {question}\nQuery that produced the result:\n{clean_sql}\n"
                                       f"Query result ({len(df)} rows):\n{preview}", fallback,
                             max_tokens=400, system=ANSWER_SYSTEM, effort="medium")
        answer = " ".join(line.strip() for line in text.splitlines() if line.strip()) if text else fallback
        answer = answer.replace("**", "").replace("__", "")
        if how == "ai" and LEAK.search(answer):
            answer, how = fallback, "template: AI text had a correction or a wrong currency"
    return {"answer": answer, "sql": clean_sql, "columns": list(df.columns), "rows": rows, "chart": _chart(df),
            "error": None, "sql_source": source, "answer_source": how, "row_cap": MAX_ROWS,
            "total_rows": int(df.attrs.get("total_rows", len(df)))}


def money(x):
    return fmt_money(x)
