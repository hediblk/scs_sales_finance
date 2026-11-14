"""Rebuild data/clean/chrome_oak/ from the raw export. The cleaning logic lives in api/pipeline.py (single source).

Run from the project root:  .venv/Scripts/python.exe explore/clean.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.pipeline import build, write_outputs  # noqa: E402

if __name__ == "__main__":
    ds = build()
    write_outputs(ds)
    print("raw  :", ds.summary["raw"])
    print("clean:", ds.summary["clean"])
    for s in ds.steps:
        print(f"  [{s['kind']:9}] {s['id']:12} rows={s['rows_affected']:4}  {s['effect']}")
