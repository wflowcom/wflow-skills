"""Show the layout of a spreadsheet: sheets, guessed header row, columns with sample values.

Usage: python inspect_xls.py <file.xlsx|.csv> [--sheet NAME] [--header-row N]
Prints JSON to stdout. Needs only openpyxl (no pandas).
"""

import argparse
import csv
import io
import json
import sys


def text(v):
    if v is None:
        return ""
    s = str(v).strip()
    return s[:-2] if s.endswith(".0") and s[:-2].lstrip("-").isdigit() else s


def read_csv(path):
    """-> (encoding, dialect, rows)"""
    for enc in ("utf-8-sig", "cp1250"):
        try:
            with open(path, encoding=enc) as f:
                raw = f.read()
            break
        except UnicodeDecodeError:
            continue
    else:
        raise SystemExit("Cannot decode CSV (tried utf-8, cp1250)")
    dialect = csv.Sniffer().sniff(raw[:4000], delimiters=",;\t")
    return enc, dialect, list(csv.reader(io.StringIO(raw), dialect))


def read_book(path, sheet=None):
    """-> {sheet name: list of rows (lists of raw values)}"""
    if path.lower().endswith(".csv"):
        return {"csv": read_csv(path)[2]}
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        names = [sheet] if sheet else wb.sheetnames
        return {n: [list(r) for r in wb[n].iter_rows(values_only=True)] for n in names}
    finally:
        wb.close()


def unique_headers(headers):
    """A repeated header gets " (2)", " (3)"… so every column can be mapped on its own."""
    seen: dict = {}
    out = []
    for h in headers:
        seen[h] = seen.get(h, 0) + 1
        out.append(f"{h} ({seen[h]})" if h and seen[h] > 1 else h)
    return out


def guess_header_row(rows):
    best, best_score = 0, -1
    for i, r in enumerate(rows[:15]):
        vals = [text(v) for v in r if text(v)]
        if len(vals) < 2:
            continue
        texty = sum(
            1 for v in vals if not v.replace(",", "").replace(".", "").replace("-", "").replace(" ", "").isdigit()
        )
        score = texty * 2 + len(vals)
        if score > best_score and texty >= max(2, len(vals) * 0.6):
            best, best_score = i, score
    return best


def describe(rows, idx):
    width = max((len(r) for r in rows), default=0)
    hdr = unique_headers([text(h) for h in rows[idx]] + [""] * (width - len(rows[idx])))
    body = [r + [None] * (width - len(r)) for r in rows[idx + 1 :] if any(text(v) for v in r)]
    cols = []
    for i, h in enumerate(hdr):
        vals = [text(r[i]) for r in body if text(r[i])]
        if not h and not vals:
            continue
        seen = list(dict.fromkeys(vals))
        cols.append(
            {"column": h or f"(empty {i + 1})", "filled": len(vals), "distinct": len(seen), "samples": seen[:4]}
        )
    return {"headerRow": idx + 1, "dataRows": len(body), "columns": cols}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--sheet")
    ap.add_argument("--header-row", type=int, help="1-based; default = guessed")
    a = ap.parse_args()
    out = {}
    for name, rows in read_book(a.file, a.sheet).items():
        if not any(any(text(v) for v in r) for r in rows):
            out[name] = {"empty": True}
            continue
        idx = a.header_row - 1 if a.header_row else guess_header_row(rows)
        out[name] = describe(rows, idx)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    main()
