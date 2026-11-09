"""Build the approval-paths Excel (format: approval-paths/references/excel-format.md).

Usage: python build_paths_xlsx.py <input.json> <output.xlsx>
"""

import json
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(bold=True, color="FFFFFF")
WRAP = Alignment(wrap_text=True, vertical="top")
PATH_FIELDS = ("access", "validationLockLevel", "whenUsed", "note", "id")
SHEETS = [
    (
        "rules",
        "Pravidla přiřazení",
        ["Pořadí", "Druh / typ dokladu", "Kdy přiřadit", "Podmínky", "→ Cesta", "Poznámka"],
        [8, 22, 16, 50, 45, 30],
        ("order", "documentKind", "phase", "conditions", "path", "note"),
    ),
    ("teams", "Týmy", ["Název týmu", "Členové", "ID týmu"], [30, 40, 38], ("name", "members", "id")),
    ("questions", "Otevřené otázky", ["Téma", "Otázka", "Stav"], [20, 70, 14], ("topic", "question", "status")),
]


def lines(value):
    if isinstance(value, (list, tuple)):
        return "\n".join(str(v) for v in value if v not in (None, ""))
    return "" if value is None else value


def add_sheet(wb, title, headers, widths, rows):
    ws = wb.create_sheet(title)
    ws.append(headers)
    for col, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
        cell = ws.cell(row=1, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    for row in rows:
        ws.append([lines(v) for v in row])
        for cell in ws[ws.max_row]:
            cell.alignment = WRAP
            if cell.data_type == "f":
                cell.data_type = "s"
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max(ws.max_row, 1)}"


def paths_sheet(wb, paths):
    depth = max((len(p.get("levels") or []) for p in paths), default=1) or 1
    headers = (
        ["Kód", "Název cesty"]
        + [f"Úroveň {i}" for i in range(1, depth + 1)]
        + [
            "Přístup (bez schvalování)",
            "Zákaz schválení při validační chybě od úrovně",
            "Kdy se použije",
            "Poznámka",
            "ID cesty",
        ]
    )
    widths = [10, 45] + [26] * depth + [26, 16, 40, 30, 38]
    rows = []
    for p in paths:
        levels = list(p.get("levels") or [])
        levels += [[]] * (depth - len(levels))
        rows.append([p.get("code"), p.get("name"), *levels, *(p.get(k) for k in PATH_FIELDS)])
    add_sheet(wb, "Cesty", headers, widths, rows)


def main(src, dst):
    with open(src, encoding="utf-8-sig") as f:
        data = json.load(f)

    wb = Workbook()
    wb.remove(wb.active)
    paths_sheet(wb, data.get("paths") or [])

    for key, title, headers, widths, fields in SHEETS:
        if key in data:
            add_sheet(wb, title, headers, widths, [[item.get(f) for f in fields] for item in data[key]])
    if "summary" in data:
        info = {"Organizace": data.get("organization"), **data["summary"]}
        add_sheet(wb, "Souhrn", ["Položka", "Hodnota"], [35, 50], list(info.items()))

    wb.save(dst)
    print(f"OK: {len(data.get('paths') or [])} paths -> {dst}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python build_paths_xlsx.py <input.json> <output.xlsx>")
    main(sys.argv[1], sys.argv[2])
