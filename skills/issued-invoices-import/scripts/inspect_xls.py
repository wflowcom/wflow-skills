"""Show the layout of a spreadsheet: sheets, guessed header row, columns with sample values.

Usage: python inspect_xls.py <file.xlsx|.xls|.csv> [--sheet NAME] [--header-row N]
Prints JSON to stdout.
"""

import argparse
import json
import sys

import pandas as pd


def read_raw(path, sheet=None, dtype=str):
    """dtype=str for display; dtype=object keeps Excel numbers and dates in their own type."""
    if path.lower().endswith(".csv"):
        for enc in ("utf-8-sig", "cp1250"):
            try:
                df = pd.read_csv(
                    path, header=None, dtype=str, sep=None, engine="python", encoding=enc, skip_blank_lines=False
                )
                return {"csv": df}
            except UnicodeDecodeError:
                continue
        raise SystemExit("Cannot decode CSV (tried utf-8, cp1250)")
    book = pd.read_excel(path, sheet_name=None if sheet is None else sheet, header=None, dtype=dtype)
    return book if isinstance(book, dict) else {sheet: book}


def unique_headers(headers):
    """A repeated header gets " (2)", " (3)"… so every column can be mapped on its own."""
    seen: dict[str, int] = {}
    out = []
    for h in headers:
        seen[h] = seen.get(h, 0) + 1
        out.append(f"{h} ({seen[h]})" if h and seen[h] > 1 else h)
    return out


def guess_header_row(df):
    """First row among the first 15 where most cells are non-empty text (not numbers)."""
    best, best_score = 0, -1
    for i in range(min(15, len(df))):
        row = df.iloc[i].dropna().astype(str).str.strip()
        row = row[row != ""]
        if row.empty:
            continue
        texts = sum(
            1 for v in row if not v.replace(",", "").replace(".", "").replace("-", "").replace(" ", "").isdigit()
        )
        score = texts * 2 + len(row)
        if score > best_score and texts >= max(2, len(row) * 0.6):
            best, best_score = i, score
    return best


def describe(df, header_idx):
    headers = unique_headers(
        [str(h).strip() if pd.notna(h) else f"(empty {i + 1})" for i, h in enumerate(df.iloc[header_idx])]
    )
    body = df.iloc[header_idx + 1 :].dropna(how="all")
    cols = []
    for i, h in enumerate(headers):
        vals = body.iloc[:, i].dropna().astype(str).str.strip()
        vals = vals[vals != ""]
        cols.append(
            {
                "column": h,
                "filled": len(vals),
                "distinct": int(vals.nunique()),
                "samples": vals.unique()[:4].tolist(),
            }
        )
    return {"headerRow": header_idx + 1, "dataRows": len(body), "columns": cols}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--sheet")
    ap.add_argument("--header-row", type=int, help="1-based; default = guessed")
    a = ap.parse_args()

    out = {}
    for name, df in read_raw(a.file, a.sheet).items():
        # keep empty rows so headerRow matches what build_documents.py reads
        table = df.dropna(axis=1, how="all")
        if table.empty:
            out[str(name)] = {"empty": True}
            continue
        idx = a.header_row - 1 if a.header_row else guess_header_row(table)
        out[str(name)] = describe(table, idx)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    main()
