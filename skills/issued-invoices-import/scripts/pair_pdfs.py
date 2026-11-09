"""Pair PDF files with invoices from build_documents.py output.

Usage: python pair_pdfs.py <out.json> <pdf-folder> [--key number|variableSymbol]
       python pair_pdfs.py <out.json> --names names.txt [--key …]
       --names: file names, one per line (a folder on the user's computer listed in Cowork)

A PDF pairs when its file name contains the key as a whole token (not part of a longer
number): FV2026-0101.pdf, FV2026-0101_Novak.pdf, "Invoice FV2026-0101.pdf". Files that are not
PDFs are ignored. Prints JSON:
  {"paired": [{"number", "file"}], "invoicesWithoutPdf": [...], "pdfsWithoutInvoice": [...],
   "ambiguous": [{"file", "numbers"}], "ignored": [...], "partial": true|false, "none": true|false}
`partial` = some invoices have a PDF and some do not; `none` = there are PDFs but not one matches -
the skill must warn and ask in both cases.
"""

import json
import os
import re
import sys


def main(out_json, folder, key, names_file=None):
    with open(out_json, encoding="utf-8") as fh:
        docs = json.load(fh)["documents"]
    if names_file:
        with open(names_file, encoding="utf-8-sig") as fh:
            files = sorted({os.path.basename(line.strip()) for line in fh if line.strip()})
        pdfs = [f for f in files if f.lower().endswith(".pdf")]
        ignored = [f for f in files if f not in pdfs]
    else:
        files = sorted(os.listdir(folder))
        pdfs = [f for f in files if f.lower().endswith(".pdf")]
        ignored = [f for f in files if f not in pdfs and os.path.isfile(os.path.join(folder, f))]

    def value(x):
        return x["number"] if key == "number" else x["payload"].get(key)

    patterns = {}
    for x in docs:
        v = value(x)
        if v:
            patterns[v] = re.compile(rf"(?<![A-Za-z0-9]){re.escape(v)}(?![A-Za-z0-9])", re.IGNORECASE)

    paired: dict[str, str] = {}
    ambiguous, used = [], set()
    for f in pdfs:
        stem = os.path.splitext(f)[0]
        hits = [v for v, rx in patterns.items() if rx.search(stem)]
        if len(hits) == 1:
            if hits[0] in paired:
                ambiguous.append({"file": f, "numbers": hits, "note": f"the invoice already has {paired[hits[0]]}"})
            else:
                paired[hits[0]] = f
            used.add(f)
        elif len(hits) > 1:
            ambiguous.append({"file": f, "numbers": hits})
            used.add(f)

    numbers = [value(x) for x in docs if value(x)]
    without = [n for n in numbers if n not in paired]
    result = {
        "paired": [{"number": n, "file": f} for n, f in paired.items()],
        "invoicesWithoutPdf": without,
        "pdfsWithoutInvoice": [f for f in pdfs if f not in used],
        "ambiguous": ambiguous,
        "ignored": ignored,
        "partial": bool(paired) and bool(without),
        "none": bool(pdfs) and not paired,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    args = sys.argv[1:]
    key, names = "number", None
    for flag in ("--key", "--names"):
        if flag in args:
            i = args.index(flag)
            if flag == "--key":
                key = args[i + 1]
            else:
                names = args[i + 1]
            del args[i : i + 2]
    if len(args) != (1 if names else 2):
        raise SystemExit(__doc__)
    main(args[0], args[1] if len(args) > 1 else None, key, names)
