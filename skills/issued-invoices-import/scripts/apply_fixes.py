"""Write the fixes agreed with the user into a corrected copy of the source file.

Usage: python apply_fixes.py <file> <fixes.json> <out-file>

fixes.json (`sheet`, `headerRow`, `decimalComma` copied from the profile's `source`):
  {"sheet": "Invoices", "headerRow": 3, "decimalComma": true,
   "changes": [{"row": 16, "column": "Celkem s DPH", "value": 12100, "reason": "recomputed from base and VAT"}],
   "skipRows": [{"row": 17, "reason": "invoice number missing - client adds it"}]}

`row` = the spreadsheet row number as build_documents.py reports it. `value` is written as given -
numbers as numbers, dates as text in the file's own format (e.g. "30.09.2026").
A column that does not exist yet is added at the end of the header.

xlsx/xlsm: changed cells yellow with the original value in a comment, skipped rows grey. The cell comments
are read by the client in Excel, so they stay in Czech; `reason` is written as given.
xls: the profile's sheet converted to xlsx (values only) first. csv: same delimiter and encoding, no colours;
left-out rows stay in it, so the row numbers in fixes.json still hold for build_documents.py --fixes.
The source file is never overwritten.
"""

import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inspect_xls import unique_headers

FILL_CHANGED = "FFF2CC"
FILL_SKIPPED = "D9D9D9"


def fix_excel(path, fixes, out):
    from openpyxl import Workbook, load_workbook
    from openpyxl.comments import Comment
    from openpyxl.styles import PatternFill

    if path.lower().endswith(".xls"):
        import pandas as pd

        df = pd.read_excel(path, sheet_name=fixes.get("sheet") or 0, header=None, dtype=object)
        wb = Workbook()
        ws = wb.active
        if fixes.get("sheet"):
            ws.title = fixes["sheet"]
        for r in df.itertuples(index=False):
            ws.append([None if (isinstance(v, float) and pd.isna(v)) else v for v in r])
        note = "converted from .xls (values only)"
    else:
        wb = load_workbook(path)
        ws = wb[fixes["sheet"]] if fixes.get("sheet") else wb.active
        # openpyxl can damage formulas (array formulas especially) - keep values only if there are any
        if any(c.data_type == "f" for row in ws.iter_rows() for c in row):
            wb = load_workbook(path, data_only=True)
            ws = wb[fixes["sheet"]] if fixes.get("sheet") else wb.active
            note = "the file contained formulas - the copy holds only their values"
        else:
            note = None

    h = fixes.get("headerRow", 1)
    names = unique_headers([str(c.value).strip() if c.value is not None else "" for c in ws[h]])
    cols = {n: i + 1 for i, n in enumerate(names) if n}
    yellow = PatternFill("solid", fgColor=FILL_CHANGED)
    grey = PatternFill("solid", fgColor=FILL_SKIPPED)

    for ch in fixes.get("changes", []):
        name = ch["column"]
        if name not in cols:
            col = ws.max_column + 1
            ws.cell(row=h, column=col, value=name)
            cols[name] = col
        cell = ws.cell(row=ch["row"], column=cols[name])
        old = cell.value
        cell.value = ch["value"]
        cell.fill = yellow
        text = f"Původně: {'(prázdné)' if old in (None, '') else old}"
        if ch.get("reason"):
            text += f"\n{ch['reason']}"
        cell.comment = Comment(text, "Import do wflow")

    for sk in fixes.get("skipRows", []):
        for cell in ws[sk["row"]]:
            cell.fill = grey
        ws.cell(row=sk["row"], column=1).comment = Comment(
            f"Vynecháno z importu: {sk.get('reason', '')}", "Import do wflow"
        )

    wb.save(out)
    return note


def fix_csv(path, fixes, out):
    raw = Path(path).read_bytes()
    enc = "utf-8-sig"
    try:
        content = raw.decode(enc)
    except UnicodeDecodeError:
        enc = "cp1250"
        content = raw.decode(enc)
    dialect = csv.Sniffer().sniff(content.splitlines()[0])
    rows = list(csv.reader(content.splitlines(), dialect))
    h = fixes.get("headerRow", 1) - 1
    cols = {n: i for i, n in enumerate(unique_headers([c.strip() for c in rows[h]])) if n}
    for ch in fixes.get("changes", []):
        if ch["column"] not in cols:
            rows[h].append(ch["column"])
            cols[ch["column"]] = len(rows[h]) - 1
        r = rows[ch["row"] - 1]
        r.extend([""] * (cols[ch["column"]] + 1 - len(r)))
        v = ch["value"]
        comma = isinstance(v, float) and fixes.get("decimalComma", True)
        r[cols[ch["column"]]] = str(v).replace(".", ",") if comma else str(v)
    with open(out, "w", newline="", encoding=enc) as f:
        csv.writer(f, delimiter=dialect.delimiter).writerows(rows)
    return "CSV has no colours - left-out rows stay in the file unmarked" if fixes.get("skipRows") else None


def main(path, fixes_path, out):
    if os.path.abspath(path) == os.path.abspath(out):
        raise SystemExit("The output must be a new file - the source is never overwritten.")
    with open(fixes_path, encoding="utf-8-sig") as f:
        fixes = json.load(f)
    if path.lower().endswith(".csv"):
        note = fix_csv(path, fixes, out)
    else:
        if out.lower().endswith(".xls"):
            out = out[:-4] + ".xlsx"
        note = fix_excel(path, fixes, out)
    print(
        json.dumps(
            {
                "out": out,
                "changes": len(fixes.get("changes", [])),
                "skipped": len(fixes.get("skipRows", [])),
                "note": note,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
