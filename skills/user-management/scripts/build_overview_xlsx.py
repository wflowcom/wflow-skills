"""wflow user overview in Excel.

Usage: python build_overview_xlsx.py <input.json> <output.xlsx>

Input: a list of rows (user and organization), format see references/excel-overview.md.
"""

import json
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HEADERS = ["User (login)", "Name", "Organization", "Role", "Team", "Document access"]
WIDTHS = [34, 24, 26, 26, 26, 70]
FILLS = [PatternFill("solid", fgColor="FFFFFF"), PatternFill("solid", fgColor="DDEBF7")]
HEADER_FILL = PatternFill("solid", fgColor="1F4E78")

LEVELS = [
    ("FullAccess", "FullAccess"),
    ("All", "All"),
    ("OnlyAssigned", "OnlyAssigned"),
    ("NoAccess", "No access"),
]


def as_text(value):
    if isinstance(value, (list, tuple)):
        return "\n".join(str(v) for v in value if v)
    return value or ""


def access_text(row):
    access = row.get("access") or {}
    full = access.get("FullAccess") or []
    total = row.get("typeCount")
    others = any(access.get(k) for k, _ in LEVELS[1:3])
    if full and not others and total and len(full) == total:
        return f"FullAccess: all types ({total})"
    lines = []
    for key, label in LEVELS:
        types = access.get(key) or []
        if types:
            lines.append(f"{label}: {', '.join(types)}")
    return "\n".join(lines)


def main(src, dst):
    with open(src, encoding="utf-8-sig") as f:
        rows = json.load(f)
    rows.sort(key=lambda r: ((r.get("login") or "").lower(), (r.get("organization") or "").lower()))

    wb = Workbook()
    ws = wb.active
    ws.title = "Users"
    ws.append(HEADERS)
    for col, width in enumerate(WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
        cell = ws.cell(row=1, column=col)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center")

    fill_idx = -1
    last_login = None
    for r in rows:
        login = r.get("login") or ""
        if login.lower() != last_login:
            fill_idx = (fill_idx + 1) % len(FILLS)
            last_login = login.lower()
        ws.append(
            [
                login,
                r.get("name") or "",
                r.get("organization") or "",
                as_text(r.get("roles")),
                as_text(r.get("teams")),
                access_text(r),
            ]
        )
        for cell in ws[ws.max_row]:
            cell.fill = FILLS[fill_idx]
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(HEADERS))}{ws.max_row}"
    wb.save(dst)
    print(f"OK: {len(rows)} rows → {dst}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python build_overview_xlsx.py <input.json> <output.xlsx>")
    main(sys.argv[1], sys.argv[2])
