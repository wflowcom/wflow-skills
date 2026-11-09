"""Turn a spreadsheet of issued invoices into wflow `update_document` payloads using a mapping profile.

Usage: python build_documents.py <file> <profile.json> <out.json> [--fixes fixes.json]
       --fixes leaves out the rows listed in its skipRows (see apply_fixes.py)

out.json:
  {"summary": {...},
   "documents": [{"rows": [5], "number": "...", "partnerIC": "...", "payload": {...},
                  "issues": [...],   # need the user's decision before the invoice is created
                  "notes": [...]}],  # informational: what was filled in / adjusted
   "fileIssues": [...]}
Payloads have no partner.id - the skill adds it after the register lookup.
Nothing is sent anywhere; the script only reads the file.
"""

import json
import os
import re
import sys
from collections import OrderedDict, defaultdict
from datetime import datetime
from typing import Any

import pandas as pd

# python -I leaves the script's own folder off sys.path - add it so the sibling module loads
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inspect_xls import read_raw, unique_headers

DEFAULT_VAT_TYPES = {21: "Basic", 12: "FirstReduced", 0: "Exempt"}
SUMMARY_ROW = re.compile(r"^\s*(celkem|součet|soucet|suma|total|mezisoučet)\b", re.IGNORECASE)
TOLERANCE = 1.0


def num(value, decimal_comma):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return round(float(value), 2)  # real Excel number - decimalComma applies to text only
    s = str(value).strip().replace("\u00a0", "").replace(" ", "")
    s = re.sub(r"[^\d,.\-]", "", s)  # currency symbols, "Kč"
    if s in ("", "-", ".", ","):
        return None
    s = s.replace(".", "").replace(",", ".") if decimal_comma else s.replace(",", "")
    try:
        return round(float(s), 2)
    except ValueError:
        return "ERR"


def date(value, formats):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):  # real Excel date (pd.Timestamp is a datetime)
        return value.strftime("%Y-%m-%dT00:00:00")
    s = str(value).strip()
    if not s:
        return None
    for fmt in [*formats, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%dT00:00:00")
        except ValueError:
            continue
    return "ERR"


def text(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, float) and value.is_integer():  # company ID / VS stored as a number
        value = int(value)
    if isinstance(value, datetime):
        value = value.strftime("%d.%m.%Y")
    s = str(value).strip()
    return s or None


def vat_type(rate, profile):
    custom = {int(k): v for k, v in (profile.get("vatTypes") or {}).items()}
    return custom.get(round(rate)) or DEFAULT_VAT_TYPES.get(round(rate))


KIND_WORDS = [
    ("dobropis", "CreditNote"),
    ("opravn", "CreditNote"),
    ("vrubopis", "DebitNote"),
    ("záloh", "Proforma"),
    ("zaloh", "Proforma"),
    ("proforma", "Proforma"),
]


def number_prefix(number):
    """Letters before the first digit, e.g. FV2026-0101 → FV, 2026100 → ''."""
    m = re.match(r"^([^\d]*)", number or "")
    return m.group(1).strip(" -/_").upper() if m else ""


def kind_proposal(docs):
    """Group invoices by number prefix and propose a kind from what the data shows."""
    groups = defaultdict(list)
    for d in docs:
        groups[d["kindSignals"]["prefix"]].append(d)
    out = []
    for prefix, ds in sorted(groups.items()):
        s = [d["kindSignals"] for d in ds]
        neg, novat = sum(x["negative"] for x in s), sum(x["noVat"] for x in s)
        words = sorted({x["keyword"] for x in s if x["keyword"]})
        with_word = sum(1 for x in s if x["keyword"])
        if len(words) == 1 and with_word == len(ds):
            proposal = words[0]
        elif neg == len(ds):
            proposal = "CreditNote"
        elif novat == len(ds):
            proposal = "Proforma"
        else:
            proposal = "TaxInvoice"
        out.append(
            {
                "prefix": prefix or "(no prefix)",
                "count": len(ds),
                "negative": neg,
                "withoutVat": novat,
                "keywords": words,
                "proposed": proposal,
                "examples": [d["number"] for d in ds if d["number"]][:3],
                "mixed": neg not in (0, len(ds)) or with_word not in (0, len(ds)) or len(words) > 1,
            }
        )
    return out


def load_table(path, profile):
    src = profile["source"]
    book = read_raw(path, src.get("sheet") or 0, dtype=object)
    df = next(iter(book.values()))
    df = df.dropna(axis=1, how="all")
    h = src.get("headerRow", 1) - 1
    headers = unique_headers([str(x).strip() if pd.notna(x) else "" for x in df.iloc[h]])
    body = df.iloc[h + 1 :].copy()
    body.columns = headers
    body["__row"] = range(h + 2, h + 2 + len(body))
    return body.dropna(how="all", subset=[c for c in headers if c])


def main(path, profile_path, out_path, skip_rows=frozenset()):
    with open(profile_path, encoding="utf-8-sig") as f:
        profile = json.load(f)  # tolerate a BOM (Windows editors)
    src = profile["source"]
    dc = src.get("decimalComma", True)
    dfmt = src.get("dateFormats", ["%d.%m.%Y"])
    cols = profile.get("columns", {})
    defaults = profile.get("defaults", {})
    kind_map = {k.strip().lower(): v for k, v in (profile.get("kindMap") or {}).items()}
    lines_cfg = profile.get("lineColumns") if src.get("structure") == "lines" else None
    acc_cols = {k: v for k, v in (profile.get("accountingColumns") or {}).items() if v}

    table = load_table(path, profile)
    file_issues = []
    mapped = [v for v in cols.values() if v]
    mapped += [c for vc in profile.get("vatColumns") or [] for c in (vc.get("base"), vc.get("tax")) if c]
    mapped += [v for k, v in (lines_cfg or {}).items() if isinstance(v, str)]
    mapped += list(acc_cols.values())
    missing = sorted(set(c for c in mapped if c not in table.columns))
    if missing:
        file_issues.append(f"Profile columns missing from the file: {', '.join(missing)}")
    extra = sorted(c for c in table.columns if c and c != "__row" and c not in mapped)

    def get(row, key):
        c = cols.get(key)
        return row.get(c) if c and c in row else None

    # group rows into invoices
    groups: OrderedDict[tuple, list] = OrderedDict()
    skipped = []  # left-out rows still count in the file's own totals row (review_xls.py)
    for _, row in table.iterrows():
        if int(row["__row"]) in skip_rows:
            t = num(get(row, "totalAmount"), dc) if cols.get("totalAmount") else None
            skipped.append(
                {"row": int(row["__row"]), "number": text(get(row, "number")), "total": t if t != "ERR" else None}
            )
            continue
        number = text(get(row, "number"))
        key = (number, text(get(row, "partnerIC"))) if lines_cfg else ("__row", row["__row"])
        groups.setdefault(key, []).append(row)

    docs, seen, vs_seen, summary_rows = [], defaultdict(list), defaultdict(list), []
    kind_by_prefix = profile.get("kindByPrefix") or {}
    has_kind_col = bool(cols.get("kind"))
    for rows in groups.values():
        head = rows[0]
        issues = []
        notes = []
        number = text(get(head, "number"))
        # a totals row under the table ("Celkem", or no customer and no date at all)
        no_party = not text(get(head, "partnerName")) and not text(get(head, "partnerIC"))
        if (number and SUMMARY_ROW.match(number)) or (no_party and not text(get(head, "issueDate"))):
            file_issues.append(f'row {int(head["__row"])} looks like a totals row ("{number or ""}") - left out')
            summary_rows.append({"row": int(head["__row"]), "total": num(get(head, "totalAmount"), dc)})
            continue
        p: dict[str, Any] = {"type": {"id": profile["documentType"]["id"], "kind": "OutgoingInvoice"}}
        if not number:
            issues.append("invoice number missing")
        p["number"] = number

        vs = text(get(head, "variableSymbol"))
        if not vs and profile.get("variableSymbolFromNumber") and number:
            vs = re.sub(r"\D", "", number) or None
        p["variableSymbol"] = vs

        for field in ("issueDate", "vatDate", "dueDate", "caseDate"):
            d = date(get(head, field), dfmt)
            if d == "ERR":
                issues.append(f"invalid date {cols.get(field)}: {get(head, field)}")
                d = None
            p[field] = d
        if not p["issueDate"]:
            issues.append("issue date missing")
        vat_date_defaulted = False
        if not p["vatDate"] and p["issueDate"]:
            p["vatDate"] = p["issueDate"]
            vat_date_defaulted = True
        if p["dueDate"] and p["issueDate"] and p["dueDate"] < p["issueDate"]:
            issues.append("due date is before the issue date")

        p["partnerName"] = text(get(head, "partnerName"))
        ic = text(get(head, "partnerIC"))
        if ic and ic.isdigit() and len(ic) < 8:  # CZ/SK company ID stored as a number loses leading zeros
            notes.append(f"company ID {ic} padded with zeros to {ic.zfill(8)}")
            ic = ic.zfill(8)
        p["partnerIC"] = ic
        p["partnerVAT"] = text(get(head, "partnerVAT"))
        p["partnerEmail"] = text(get(head, "partnerEmail"))

        serie = text(get(head, "serie")) or (profile.get("serie") or {}).get("code")
        if serie:
            p["serie"] = {"code": serie}
        if not p["partnerName"] and not p["partnerIC"]:
            issues.append("customer missing (neither name nor company ID)")
        addr = {
            "streetAndNumber": text(get(head, "partnerStreet")),
            "city": text(get(head, "partnerCity")),
            "postalCode": text(get(head, "partnerPostalCode")),
            "countryCode": text(get(head, "partnerCountry")) or defaults.get("countryCode"),
        }
        if any(v for k, v in addr.items() if k != "countryCode"):
            p["partnerMainAddress"] = addr

        p["currency"] = (text(get(head, "currency")) or defaults.get("currency") or "CZK").upper()
        rate = num(get(head, "exchangeRate"), dc)
        if rate not in (None, "ERR"):
            p["exchangeRate"] = rate
        if p["currency"] != defaults.get("currency", "CZK") and not p.get("exchangeRate"):
            issues.append(f"foreign currency {p['currency']} without an exchange rate")

        p["description"] = text(get(head, "description"))
        p["orderNo"] = text(get(head, "orderNo"))

        # VAT + lines
        vats: list[dict[str, Any]] = []
        if lines_cfg:
            lines: list[dict[str, Any]] = []
            by_rate: defaultdict[Any, list[float]] = defaultdict(lambda: [0.0, 0.0])
            for i, r in enumerate(rows):

                def lc(k, r=r):
                    return r.get(lines_cfg[k]) if lines_cfg.get(k) and lines_cfg[k] in r else None

                vr = num(lc("vatRate"), dc)
                if vr == "ERR":
                    issues.append(f"row {r['__row']}: invalid VAT rate {lc('vatRate')}")
                    continue
                if vr is None:
                    notes.append(f"row {r['__row']}: VAT rate empty - taken as 0 %")
                    vr = 0.0
                base = num(lc("lineBase"), dc)
                tax = num(lc("lineTax"), dc)
                total = num(lc("lineTotal"), dc)
                if base is None and total not in (None, "ERR"):
                    base = round(total / (1 + vr / 100), 2) if lines_cfg.get("amountsIncludeVat") else total
                if tax is None and base not in (None, "ERR"):
                    tax = round(base * vr / 100, 2)
                if "ERR" in (base, tax):
                    issues.append(f"row {r['__row']}: invalid amount")
                    continue
                by_rate[vr][0] += base or 0
                by_rate[vr][1] += tax or 0
                line = {
                    "order": i + 1,
                    "description": text(lc("description")),
                    "quantity": num(lc("quantity"), dc),
                    "measureUnit": text(lc("unit")),
                    "unitPrice": num(lc("unitPrice"), dc),
                    "vatRate": vr,
                    "vatType": vat_type(vr, profile),
                    "totalAmount": round(base or 0, 2),  # wflow: the line total excluding VAT
                }
                lines.append({k: v for k, v in line.items() if v is not None})
            p["lines"] = lines
            for vr, (rate_base, rate_tax) in by_rate.items():
                vats.append({"rate": vr, "base": round(rate_base, 2), "tax": round(rate_tax, 2)})
        elif profile.get("vatColumns"):
            for vc in profile["vatColumns"]:
                b = num(head.get(vc["base"]), dc) if vc.get("base") in head else None
                t = num(head.get(vc["tax"]), dc) if vc.get("tax") and vc["tax"] in head else None
                if "ERR" in (b, t):
                    issues.append(f"invalid amount in the VAT {vc['rate']} % column")
                    continue
                if b or t:
                    vats.append({"rate": vc["rate"], "base": b or 0.0, "tax": t or 0.0})
        else:
            vr = num(get(head, "vatRate"), dc)
            b, t = num(get(head, "taxExclusiveAmount"), dc), num(get(head, "taxAmount"), dc)
            if vr not in (None, "ERR") and b not in (None, "ERR"):
                vats.append({"rate": vr, "base": b, "tax": t if t not in (None, "ERR") else round(b * vr / 100, 2)})

        for v in vats:
            v["type"] = vat_type(v["rate"], profile)
            if not v["type"]:
                issues.append(f"VAT rate {v['rate']} % has no type - add it to vatTypes in the profile")
        p["vaTs"] = vats

        total = num(get(head, "totalAmount"), dc)
        base_sum = round(sum(v["base"] for v in vats), 2) if vats else num(get(head, "taxExclusiveAmount"), dc)
        tax_sum = round(sum(v["tax"] for v in vats), 2) if vats else num(get(head, "taxAmount"), dc)
        if total is None and base_sum not in (None, "ERR"):
            total = round(base_sum + (tax_sum or 0), 2)
        if total in (None, "ERR"):
            issues.append("total amount missing or invalid")
            total = None
        p["totalAmount"] = total
        p["taxExclusiveAmount"] = base_sum if base_sum != "ERR" else None
        p["taxAmount"] = tax_sum if tax_sum != "ERR" else None
        if total is not None and vats:
            diff = round(total - base_sum - tax_sum, 2)
            if abs(diff) > TOLERANCE:
                issues.append(f"VAT recap ({base_sum} + {tax_sum}) does not match the total {total}")
            elif diff:
                p["roundingAmount"] = diff

        # document kind: kind column → prefix of the number → negative total → invoice
        raw_kind = text(get(head, "kind"))
        kind = "TaxInvoice"
        prefix_kind = next(
            (
                kind_by_prefix[pr]
                for pr in sorted(kind_by_prefix, key=len, reverse=True)
                if number and number.upper().startswith(pr.upper())
            ),
            None,
        )
        if raw_kind:
            mapped_kind = kind_map.get(raw_kind.lower())
            if mapped_kind:
                kind = mapped_kind
            else:
                issues.append(f'unknown document kind "{raw_kind}" - add it to kindMap')
        elif prefix_kind:
            kind = prefix_kind
        elif profile.get("negativeTotalIsCreditNote") and total is not None and total < 0:
            kind = "CreditNote"
        p["invoiceType"] = kind
        if vat_date_defaulted:
            if kind == "Proforma":
                p["vatDate"] = None  # a proforma is not a tax document - no VAT date
            else:
                notes.append("VAT date missing - issue date used")

        # case date: column wins, otherwise copied as agreed in the profile
        if not p["caseDate"] and profile.get("caseDateFrom"):
            p["caseDate"] = p.get(profile["caseDateFrom"]) or p.get("issueDate")

        # one document line per VAT rate for header-only files
        if not lines_cfg and profile.get("linesPerVatRate") and vats:
            base_text = p.get("description") or "Plnění"  # line texts land on the client's document, in Czech
            p["lines"] = [
                {
                    "order": i + 1,
                    "description": f"{base_text} \u2013 {'osvobozeno' if not v['rate'] else str(int(v['rate'])) + ' %'}",
                    "quantity": 1.0,
                    "unitPrice": v["base"],
                    "vatRate": v["rate"],
                    "vatType": v["type"],
                    "totalAmount": v["base"],  # wflow: the line total excluding VAT
                }
                for i, v in enumerate(vats)
            ]

        # accounting dimensions
        acc = {k: {"code": v} for k, v in (profile.get("accountingDefaults") or {}).items() if v}
        for k, c in acc_cols.items():  # a column wins over the fixed default
            code = text(head.get(c)) if c in head else None
            if code:
                acc[k] = {"code": code}
        if acc:
            p["accounting"] = acc

        p = {k: v for k, v in p.items() if v is not None}
        key = (number, p.get("partnerIC"))
        seen[key].append(int(head["__row"]))
        if p.get("variableSymbol"):
            vs_seen[p["variableSymbol"]].append(number)
        docs.append(
            {
                "rows": [int(r["__row"]) for r in rows],
                "number": number,
                "partnerIC": p.get("partnerIC"),
                "partnerName": p.get("partnerName"),
                "invoiceType": kind,
                "currency": p.get("currency"),
                "totalAmount": total,
                "payload": p,
                "issues": issues,
                "notes": notes,
                "kindSignals": {
                    "prefix": number_prefix(number),
                    "negative": total is not None and total < 0,
                    "noVat": not vats and not p.get("taxAmount"),
                    "keyword": next((k for w, k in KIND_WORDS if w in (p.get("description") or "").lower()), None),
                },
            }
        )

    for (number, ic), rows in seen.items():
        if len(rows) > 1:
            file_issues.append(f"invoice {number} (company ID {ic}) is in the file more than once: rows {rows}")
    for vs, numbers in vs_seen.items():
        if len(set(numbers)) > 1:
            file_issues.append(f"same variable symbol {vs} on invoices {', '.join(sorted(set(numbers)))}")

    by_kind: defaultdict[str, int] = defaultdict(int)
    by_cur: defaultdict[str, float] = defaultdict(float)
    for d in docs:
        by_kind[d["invoiceType"]] += 1
        if d["totalAmount"] is not None:
            by_cur[d["currency"]] += d["totalAmount"]
    summary = {
        "invoices": len(docs),
        "withIssues": sum(1 for d in docs if d["issues"]),
        "withNotes": sum(1 for d in docs if d["notes"]),
        "byKind": dict(by_kind),
        "totalByCurrency": {k: round(v, 2) for k, v in by_cur.items()},
        "customers": len({d["partnerIC"] or d["partnerName"] for d in docs}),
        "unmappedColumns": extra,
    }
    if not has_kind_col:
        summary["kindProposal"] = kind_proposal(docs)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "summary": summary,
                "fileIssues": file_issues,
                "summaryRows": summary_rows,
                "skippedRows": skipped,
                "documents": docs,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(json.dumps({"summary": summary, "fileIssues": file_issues}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    args = sys.argv[1:]
    skip = set()
    if "--fixes" in args:  # rows the user chose to leave out (apply_fixes.py skipRows)
        i = args.index("--fixes")
        with open(args[i + 1], encoding="utf-8-sig") as f:
            fx = json.load(f)
        skip = {s["row"] for s in fx.get("skipRows", [])}
        del args[i : i + 2]
    if len(args) != 3:
        raise SystemExit(__doc__)
    main(args[0], args[1], args[2], skip_rows=skip)
