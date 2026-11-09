"""Read rows the client marked (coloured) in the "Cesty" sheet of the approval-paths Excel.

Usage: python read_marked_rows.py <file.xlsx>

Any fill other than white counts as a mark; one coloured cell marks the whole row; empty rows are skipped.
Prints a JSON list: {"row", "action": create|update|delete, "values": {header: value}}.
"""

import json
import re
import sys

from openpyxl import load_workbook

WHITE = {"FFFFFFFF", "00FFFFFF"}
WHITE_INDEXED = {1, 9, 65}
DELETE = re.compile(r"(?<!\w)smazat(?!\w)")


def is_marked(cell):
    fill = cell.fill
    if fill.fill_type in (None, "none"):
        return False
    color = getattr(fill, "fgColor", None)
    if color is None:
        return fill.tagname == "gradientFill"
    if color.type == "rgb":
        rgb = (color.rgb or "").upper()
        return rgb not in WHITE and rgb != "00000000"
    # theme 0 without tint is the white background
    if color.type == "theme":
        return not (color.theme == 0 and not color.tint)
    if color.type == "indexed":
        return color.indexed not in WHITE_INDEXED
    return True


def main(path):
    ws = load_workbook(path, data_only=True)["Cesty"]
    headers = [c.value for c in ws[1]]
    marked = []
    for row in ws.iter_rows(min_row=2):
        if not any(is_marked(c) for c in row):
            continue
        values = {h: c.value for h, c in zip(headers, row) if h}
        if all(v in (None, "") for v in values.values()):
            continue
        note = str(values.get("Poznámka") or "").lower()
        if DELETE.search(note):
            action = "delete"
        elif not str(values.get("ID cesty") or "").strip():
            action = "create"
        else:
            action = "update"
        marked.append({"row": row[0].row, "action": action, "values": values})
    print(json.dumps(marked, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python read_marked_rows.py <file.xlsx>")
    main(sys.argv[1])
