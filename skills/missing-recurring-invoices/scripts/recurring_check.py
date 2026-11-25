"""Missing recurring invoices – which regular received invoices did not arrive in a month, the basis
for accruals and the release of last month's accruals.

Text written into the Excel outputs (headers, sheet names, notes, warnings, review kinds) stays Czech:
the accountants read it, and `release` reads last month's Excel back by its Czech headers.

Nothing here talks to wflow; the assistant reads through the MCP and feeds JSON in.

Usage:
  python recurring_check.py collect   resp1.json [resp2.json …] [--kind docs|details] --out docs.json
  python recurring_check.py normalize --xls list.xlsx --profile profile.json|template --out list.json
  python recurring_check.py match     --list list.json --docs docs.json --period 2026-10
                                      [--date-field vatDate|acceptDate] [--history 3]
                                      [--window-start 2026-07-01] [--confirm confirm.json]
                                      --org SUBDOMAIN --out result.json
  python recurring_check.py release   --accruals last_month.xlsx --list list.json --docs docs.json
                                      --period 2026-10 [--date-field …] [--links links.json] --org … --out release.json
  python recurring_check.py report    --result result.json [--details details.json] [--release release.json]
                                      --out report.xlsx
  python recurring_check.py suggest   --docs docs.json --end 2026-10 [--months 6] [--date-field vatDate]
                                      [--details details.json] --out list.xlsx
  python recurring_check.py addrows   --xls list.xlsx --profile profile.json|template --result result.json
                                      --docs docs.json [--details details.json] --out list_doplneno.xlsx
  python recurring_check.py selftest

docs.json    = list_documents items – one array with all pages merged, or the raw responses (a dict with
               items/totalItems, or a list of such dicts). Duplicates by id and removed documents are dropped.
details.json = array of get_document responses for the printed / result "detailIds" (collect --kind details).
confirm.json = [{"row": <list row>, "document": "<number or id>"}] – invoices the user confirmed belong to a
               row although company ID (IČ) / name differ (review kind "Možná došla pod jiným IČ / názvem").
links.json   = {"<credit/debit note id>": ["<linked document id>", …]} from list_document_links.
"""

import argparse
import csv
import datetime as dt
import difflib
import json
import math
import os
import re
import sys
import tempfile
import unicodedata
from collections import Counter, defaultdict

SENT = "SentToERP"
FLOW_LABEL = {
    "New": "Nový",
    "SendToExtractionWaiting": "Čeká na vytěžení",
    "SendToExtractionError": "Chyba vytěžení",
    "SendToExtractionOK": "Odesláno k vytěžení",
    "Filled": "Vyplněno",
    "Extracted": "Vytěženo",
    "SentToReview": "Ke kontrole",
    "Reviewed": "Zkontrolováno",
    "Sent": "Odesláno",
    "SendToERPWaiting": "Čeká na odeslání do ERP",
    "SendToERPError": "Chyba odesílání do ERP",
    "SentToERP": "Odesláno do ERP",
}
DATE_LABEL = {"vatDate": "DUZP", "acceptDate": "datum přijetí", "issueDate": "datum vystavení"}
# only an ordinary invoice counts as "arrived"; the rest is counted in the summary only
COUNTED_TYPES = {None, "", "TaxInvoice"}
IGNORED_LABEL = {
    "CreditNote": "dobropis",
    "DebitNote": "vrubopis",
    "Proforma": "zálohová faktura",
    "TaxInvoicePayment": "daňový doklad k platbě",
}
FIELDS = [
    "name",
    "ic",
    "description",
    "keyword",
    "amount",
    "tolerance",
    "frequency",
    "months",
    "costCenter",
    "contract",
    "project",
    "activity",
    "account",
]
ACC_FIELDS = ["costCenter", "contract", "project", "activity", "account"]
ACC_LABEL = {
    "costCenter": "Středisko",
    "contract": "Zakázka",
    "project": "Projekt",
    "activity": "Činnost",
    "account": "Analytický účet",
}
# template written by `suggest` – also the built-in profile ("template")
TEMPLATE = {
    "name": "Firma / osoba",
    "ic": "IČ",
    "description": "Popis",
    "keyword": "Klíčové slovo",
    "amount": "Částka bez DPH",
    "tolerance": "Tolerance %",
    "frequency": "Frekvence",
    "months": "Měsíce fakturace",
    "costCenter": "Středisko",
    "contract": "Zakázka",
    "project": "Projekt",
    "activity": "Činnost",
    "account": "Analytický účet",
}
HDR_SOURCE = "Zdroj údajů"
HDR_LIST_ROW = "Řádek v původním Excelu"
OLD_HDR_LIST_ROW = "Řádek seznamu"
HDR_LIST_NAME = "Dodavatel v seznamu"
SOURCE_HELP = [
    ("seznam", "údaj z vašeho seznamu pravidelných plateb"),
    ("historie", "převzato z poslední faktury dodavatele ve wflow"),
    (
        "historie (rozpad)",
        "dohad rozdělen na střediska / zakázky ve stejném poměru jako poslední faktura",
    ),
    ("částka: průměr z N faktur", "částka v seznamu chybí, použit průměr posledních faktur"),
]
# exact tokens only (after removing diacritics) – no prefix guessing, "čer" is ambiguous on purpose
MONTH_FORMS = {
    1: "leden ledna lednu led jan january",
    2: "unor unora unoru uno feb february",
    3: "brezen brezna breznu bre mar march",
    4: "duben dubna dubnu dub apr april",
    5: "kveten kvetna kvetnu kve may maj",
    6: "cerven cervna cervnu cvn jun june",
    7: "cervenec cervence cervenci cvc jul july",
    8: "srpen srpna srpnu srp aug august",
    9: "zari zar sep sept september",
    10: "rijen rijna rijnu rij okt oct october",
    11: "listopad listopadu lis nov november",
    12: "prosinec prosince prosinci pro dec december",
}
MONTH_TOKEN = {w: m for m, forms in MONTH_FORMS.items() for w in forms.split()}
LEGAL = {
    "sro",
    "s",
    "r",
    "o",
    "as",
    "a",
    "spol",
    "ks",
    "k",
    "vos",
    "v",
    "gmbh",
    "ltd",
    "se",
    "zs",
    "z",
    "inc",
    "llc",
    "co",
    "sp",
    "zoo",
    "kg",
    "ag",
    "bv",
    "nv",
    "sa",
}
TOTAL_ROW = re.compile(r"^\s*(celkem|součet|soucet|total)\b", re.I)
VAT_RATIO = (1.18, 1.24)  # list amount without VAT vs invoice with VAT (21 %, 12 % excluded on purpose)


def strip_diacritics(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm_name(v):
    s = strip_diacritics(str(v or "").lower())
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(w for w in s.split() if w not in LEGAL)


def norm_ic(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    s = str(v).strip()
    if s.endswith(".0"):
        s = s[:-2]
    d = re.sub(r"\D", "", s)
    return d.zfill(8) if d else ""


def parse_amount(v):
    """-> (value or None, ok). ok=False when a non-empty cell is not a number."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None, True
    if isinstance(v, (int, float)):
        return float(v), True
    s = str(v).strip().replace(" ", "").replace(" ", "")
    s = re.sub(r"(,-|Kč|CZK|EUR|€)$", "", s, flags=re.I)
    if not s:
        return None, True
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif re.fullmatch(r"-?[1-9]\d{0,2}([.,]\d{3})+", s):
        s = s.replace(".", "").replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return float(s), True
    except ValueError:
        return None, False


def text(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    s = str(v).strip()
    return s[:-2] if re.fullmatch(r"-?\d+\.0", s) else s


def parse_frequency(v):
    s = strip_diacritics(text(v).lower())
    if not s:
        return "M", True
    times, count = re.match(r"(\d+)\s*(?:x|×|krát|krat)", s), re.match(r"\d+", s)
    if times and any(w in s for w in ("rocn", "rok", "year")):
        f = {"12": "M", "4": "Q", "1": "Y"}.get(times[1])
    elif any(w in s for w in ("ctvrt", "kvart", "quarter")):
        f = "Q"
    elif any(w in s for w in ("rocn", "year", "annual")):
        f = "Y"
    elif count:
        f = {"1": "M", "3": "Q", "12": "Y"}.get(count[0])
    elif s.startswith("m") or "mesic" in s or "month" in s:
        f = "M"
    elif s.startswith(("c", "q", "k")):
        f = "Q"
    else:
        f = "Y" if s.startswith(("r", "y", "a")) else None
    return f or "M", f is not None


def parse_months(v):
    """-> (sorted months, unknown tokens)"""
    s = strip_diacritics(text(v).lower())
    out, unknown = set(), []
    for token in re.split(r"[,;/+\s]+|\ba\b", s):
        part = token.strip(". -")
        if not part:
            continue
        if part.isdigit():
            if 1 <= int(part) <= 12:
                out.add(int(part))
            else:
                unknown.append(part)
        elif part in MONTH_TOKEN:
            out.add(MONTH_TOKEN[part])
        else:
            unknown.append(part)
    return sorted(out), unknown


def month_of(value):
    m = re.match(r"(\d{4})-(\d{2})-\d{2}", str(value or ""))
    return f"{m[1]}-{m[2]}" if m else None


def shift(period, n):
    y, m = map(int, period.split("-"))
    m += n
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"


def kind_of(d):
    t = d.get("type") or {}
    return t.get("kind") if isinstance(t, dict) else None


def load_json(path):
    with open(path, encoding="utf-8-sig") as f:  # tolerate a BOM (Windows tools)
        return json.load(f)


def load_docs(path):
    """-> (docs, completeness warning or '')"""
    raw = load_json(path)
    chunks = raw if isinstance(raw, list) and raw and isinstance(raw[0], dict) and "items" in raw[0] else [raw]
    items: list = []
    total = None
    for c in chunks:
        if isinstance(c, dict):
            items += c.get("items") or []
            if c.get("totalItems") is not None and c.get("page", 0) == 0:
                total = (total or 0) + c["totalItems"]
        else:
            items += c
    seen, docs = set(), []
    for d in items:
        if d.get("id") in seen:
            continue
        seen.add(d.get("id"))
        if d.get("removed") or kind_of(d) not in (None, "IncomingInvoice"):
            continue
        docs.append(d)
    warn = ""
    if total is not None and len(seen) < total:
        warn = f"načteno jen {len(seen)} z {total} dokladů – chybí další stránky, výsledek by byl neúplný"
    return docs, warn


def doc_date(d, field):
    v = d.get(field)
    if not v and field == "vatDate":
        v = d.get("issueDate")
    return v


def is_rejected(d):
    return "reject" in str(d.get("approvalStatus") or "").lower()


def cancelled_ids(docs, field, links=None):
    """Invoices cancelled by a credit note on the full amount (same supplier and month, or linked).
    Such an invoice is not an arrived invoice and does not go into averages."""
    links = links or {}
    out = set()
    inv = [d for d in docs if d.get("invoiceType") in COUNTED_TYPES]
    for n in docs:
        if n.get("invoiceType") != "CreditNote":
            continue
        na = czk(n, "taxExclusiveAmount") or czk(n, "totalAmount")
        if not na:
            continue
        linked = links.get(n.get("id")) or []
        cands = [
            d
            for d in inv
            if d["id"] not in out
            and (
                d["id"] in linked
                if linked
                else (
                    supplier_key(norm_ic(d.get("partnerIC")), d.get("partnerName"))
                    == supplier_key(norm_ic(n.get("partnerIC")), n.get("partnerName"))
                    and month_of(doc_date(d, field)) == month_of(doc_date(n, field))
                )
            )
        ]
        hit = [d for d in cands if abs((czk(d, "taxExclusiveAmount") or czk(d, "totalAmount") or 0) - na) < 0.01]
        if hit:
            out.add(sorted(hit, key=lambda d: doc_date(d, field) or "")[0]["id"])
    return out


def czk(d, key):
    """Amount in CZK; foreign currency via exchangeRate (/ exchangeRateUnits). None when no rate."""
    a = d.get(key)
    if a is None:
        return None
    a = abs(float(a))
    cur = (d.get("currency") or "CZK").upper()
    if cur == "CZK":
        return a
    rate = d.get("exchangeRate")
    if not rate:
        return None
    units = d.get("exchangeRateUnits") or 1
    return a * float(rate) / float(units)


def supplier_key(ic, name):
    return ("ic", ic) if ic else ("name", norm_name(name))


def same_supplier(row, d):
    dic = norm_ic(d.get("partnerIC"))
    if row["ic"] and dic:
        return row["ic"] == dic
    a, b = norm_name(row["name"]), norm_name(d.get("partnerName"))
    return bool(a and b) and (a == b or a in b or b in a)


def similar_supplier(row, d):
    """Looser test for 'maybe this is the one' (typo in IČ, other spelling of the name)."""
    a, b = norm_name(row["name"]), norm_name(d.get("partnerName"))
    if a and b:
        if difflib.SequenceMatcher(None, a, b).ratio() >= 0.75:
            return "podobný název"
        wa, wb = a.split(), b.split()
        if wa and wb and wa[0] == wb[0] and len(wa[0]) >= 4:
            return "stejné první slovo názvu"
    ric, dic = row["ic"], norm_ic(d.get("partnerIC"))
    if ric and dic and ric != dic and difflib.SequenceMatcher(None, ric, dic).ratio() >= 0.75:
        return "podobné IČ (překlep?)"
    return ""


def dump(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def read_sheet(path, sheet, header_row):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from inspect_xls import read_book, unique_headers

    book = read_book(path)
    used = sheet if sheet in book else next(iter(book))
    data = book[used]
    hdr = unique_headers([text(h) for h in data[header_row - 1]])
    rows = []
    for n, r in enumerate(data[header_row:], start=header_row + 1):
        rec = {hdr[i]: (r[i] if i < len(r) else None) for i in range(len(hdr)) if hdr[i]}
        if all(text(v) == "" for v in rec.values()):
            continue
        rows.append((n, rec))
    return hdr, rows, used


def normalize(xls, profile):
    src = profile.get("source") or {}
    cols = profile.get("columns") or TEMPLATE
    defaults = profile.get("defaults") or {}
    hdr, rows, sheet = read_sheet(xls, src.get("sheet"), src.get("headerRow", 1))
    missing_cols = [c for c in cols.values() if c and c not in hdr]
    mapped = [f for f in FIELDS if cols.get(f) and cols.get(f) in hdr]
    out, issues = [], []
    if src.get("sheet") and sheet != src.get("sheet"):
        issues.append({"row": "", "issue": f"list „{src['sheet']}“ v souboru není – použit list „{sheet}“"})
    for excel_row, rec in rows:
        g = {f: rec.get(cols.get(f)) if cols.get(f) else None for f in FIELDS}
        name, ic = text(g["name"]), norm_ic(g["ic"])
        if TOTAL_ROW.match(name) and not ic:
            continue
        if not name and not ic:
            issues.append({"row": excel_row, "issue": "chybí název i IČ – řádek přeskočen"})
            continue
        label = name or ic
        freq, ok = parse_frequency(g["frequency"])
        if not ok:
            issues.append(
                {"row": excel_row, "issue": f"{label}: neznámá frekvence „{text(g['frequency'])}“ – beru měsíčně"}
            )
        if not text(g["frequency"]) and defaults.get("frequency"):
            freq = defaults["frequency"]
        months, unknown = parse_months(g["months"])
        if unknown:
            issues.append(
                {
                    "row": excel_row,
                    "issue": f"{label}: nerozpoznané měsíce „{', '.join(unknown)}“ – "
                    "opravte v seznamu (nebo použijte čísla 1–12)",
                }
            )
        if freq == "Q" and len(months) == 1:
            m = months[0]
            months = sorted({(m - 1 + 3 * k) % 12 + 1 for k in range(4)})
        amount, ok = parse_amount(g["amount"])
        if not ok:
            issues.append(
                {
                    "row": excel_row,
                    "issue": f"{label}: částka „{text(g['amount'])}“ není číslo – použije se průměr z historie",
                }
            )
        elif amount is not None and amount <= 0:
            issues.append(
                {
                    "row": excel_row,
                    "issue": f"{label}: nulová nebo záporná částka {amount:g} – použije se průměr z historie",
                }
            )
            amount = None
        tol, ok = parse_amount(g["tolerance"])
        if not ok or (tol is not None and tol < 0):
            issues.append(
                {"row": excel_row, "issue": f"{label}: neplatná tolerance – beru {defaults.get('tolerance', 20)} %"}
            )
            tol = None
        out.append(
            {
                "row": excel_row,
                "name": name,
                "ic": ic,
                "description": text(g["description"]),
                "keyword": text(g["keyword"]),
                "amount": amount,
                "tolerance": tol if tol is not None else float(defaults.get("tolerance", 20)),
                "frequency": freq,
                "months": months,
                **{f: text(g[f]) for f in ACC_FIELDS},
            }
        )
    if not out:
        issues.append({"row": "", "issue": "seznam neobsahuje žádný použitelný řádek – zkontrolujte list a hlavičku"})
    keys = Counter(supplier_key(r["ic"], r["name"]) for r in out)
    dup = Counter((supplier_key(r["ic"], r["name"]), r["keyword"].lower(), r["amount"]) for r in out)
    for r in out:
        k = supplier_key(r["ic"], r["name"])
        r["sharedSupplier"] = keys[k] > 1
        if r["sharedSupplier"] and not r["keyword"] and r["amount"] is None:
            issues.append(
                {
                    "row": r["row"],
                    "issue": f"{r['name'] or r['ic']}: víc řádků jednoho dodavatele "
                    "bez klíčového slova i částky – nepůjde rozlišit",
                }
            )
        if dup[(k, r["keyword"].lower(), r["amount"])] > 1:
            issues.append(
                {
                    "row": r["row"],
                    "issue": f"{r['name'] or r['ic']}: duplicitní řádek (stejný dodavatel, klíčové slovo i částka)",
                }
            )
    return {
        "amountWithVat": bool(profile.get("amountWithVat")),
        "rows": out,
        "issues": issues,
        "missingColumns": missing_cols,
        "mappedFields": mapped,
    }


def cmd_normalize(a):
    profile = {"columns": TEMPLATE} if a.profile == "template" else load_json(a.profile)
    res = normalize(a.xls, profile)
    dump(res, a.out)
    print(
        json.dumps(
            {"rows": len(res["rows"]), "issues": res["issues"], "missingColumns": res["missingColumns"]},
            ensure_ascii=False,
            indent=1,
        )
    )
    if not res["rows"]:
        sys.exit(2)


def doc_amount(d, with_vat):
    if with_vat:
        return czk(d, "totalAmount")
    v = czk(d, "taxExclusiveAmount")
    return v if v is not None else czk(d, "totalAmount")


def score(row, d, with_vat):
    s = 0
    kw = strip_diacritics(row["keyword"].lower())
    desc = strip_diacritics(str(d.get("description") or "").lower())
    if kw and kw in desc:
        s += 2
    amt = doc_amount(d, with_vat)
    if (
        row["amount"] is not None
        and amt is not None
        and abs(amt - row["amount"]) <= row["amount"] * row["tolerance"] / 100
    ):
        s += 1
    return s


def assign_month(rows, docs, with_vat, forced=None):
    """-> (assigned {row index: [docs]}, uncertain [(doc, [row idx], note)], unassigned [docs])
    forced = {doc id: row index} – pairings the user confirmed (typo in IČ, other name)."""
    assigned, uncertain, unassigned = defaultdict(list), [], []
    forced = forced or {}
    for d in docs:
        if d.get("id") in forced:
            assigned[forced[d["id"]]].append(d)
            continue
        cands = [i for i, r in enumerate(rows) if same_supplier(r, d)]
        if not cands:
            unassigned.append(d)
            continue
        if len(cands) == 1:
            assigned[cands[0]].append(d)
            continue
        scored = sorted(((score(rows[i], d, with_vat), i) for i in cands), reverse=True)
        if scored[0][0] > 0 and scored[0][0] > scored[1][0]:
            assigned[scored[0][1]].append(d)
        else:
            uncertain.append((d, cands, "nejde rozlišit, ke kterému řádku patří"))
    return assigned, uncertain, unassigned


def expected_in(row, period, history_hits):
    m = int(period[5:])
    if row["frequency"] == "M":
        return True, ""
    if row["months"]:
        return m in row["months"], ""
    step = 3 if row["frequency"] == "Q" else 12
    if shift(period, -step) in history_hits:
        return True, f"měsíce fakturace neuvedeny – očekáváno podle faktury před {step} měs."
    return False, "měsíce fakturace neuvedeny a v historii není opora – zkontrolujte"


def link(org, d):
    t = (d.get("type") or {}).get("id")
    if not (org and t and d.get("id")):
        return ""
    return f"https://app.wflow.com/org/{org}/documents/list/kind/0/{t}/detail/{d['id']}"


def doc_row(d, field, org, note=""):
    return {
        "id": d.get("id"),
        "typeId": (d.get("type") or {}).get("id"),
        "number": d.get("number"),
        "partnerName": d.get("partnerName"),
        "partnerIC": d.get("partnerIC"),
        "date": (doc_date(d, field) or "")[:10],
        "description": d.get("description") or "",
        "totalAmount": d.get("totalAmount"),
        "taxExclusiveAmount": d.get("taxExclusiveAmount"),
        "currency": d.get("currency") or "CZK",
        "flowStatus": d.get("flowStatus"),
        "notInErp": d.get("flowStatus") != SENT,
        "accountCode": d.get("accountCode"),
        "invoiceType": d.get("invoiceType"),
        "note": note,
        "link": link(org, d),
    }


def review(res, kind, list_name="", row="", d=None, field="vatDate", org="", note=""):
    item = {"kind": kind, "row": row, "listName": list_name, "note": note}
    if d is not None:
        item.update(doc_row(d, field, org, note))
    res["review"].append(item)


def split_docs(docs, months, field):
    """-> (per_month counted invoices, ignored-by-type Counter, rejected, foreign without rate, without date)"""
    ignored: Counter = Counter()
    per_month, rejected, no_rate, no_date = defaultdict(list), [], [], []
    cancelled = cancelled_ids(docs, field)
    for d in docs:
        t = d.get("invoiceType")
        if t not in COUNTED_TYPES or d["id"] in cancelled:
            if month_of(doc_date(d, field)) == months[-1]:
                ignored["stornovaná faktura" if d["id"] in cancelled else IGNORED_LABEL.get(t, t)] += 1
            continue
        m = month_of(doc_date(d, field))
        if m is None:
            no_date.append(d)
            continue
        if m not in months:
            continue
        if is_rejected(d):
            rejected.append(d)
            continue
        if (d.get("currency") or "CZK").upper() != "CZK" and not d.get("exchangeRate"):
            no_rate.append(d)
        per_month[m].append(d)
    return per_month, ignored, rejected, no_rate, no_date


def resolve_confirms(rows, docs, confirms):
    """confirms = [{"row": <list row number>, "document": <number or id>}] -> ({doc id: row index}, issues)"""
    forced, issues = {}, []
    by_row = {str(r["row"]): i for i, r in enumerate(rows)}
    for c in confirms or []:
        i = by_row.get(str(c.get("row")))
        ref = str(c.get("document") or "")
        hit = [d for d in docs if ref and ref in (str(d.get("id")), str(d.get("number")))]
        if i is None or len(hit) != 1:
            issues.append(
                f"potvrzené spárování {c} nejde použít – "
                f"{'řádek seznamu neexistuje' if i is None else 'doklad nenalezen nebo není jednoznačný'}"
            )
            continue
        forced[hit[0]["id"]] = i
    return forced, issues


def match(lst, docs, period, field, history, org, window_start=None, docs_warning="", today=None, confirms=None):
    rows, with_vat = lst["rows"], lst.get("amountWithVat", False)
    if any(r["frequency"] == "Y" and not r["months"] for r in rows):
        history = max(history, 12)
    months = [shift(period, -k) for k in range(history, -1, -1)]  # oldest .. period
    per_month, ignored, rejected, no_rate, no_date = split_docs(docs, months, field)
    forced, confirm_issues = resolve_confirms(rows, docs, confirms)
    assign = {m: assign_month(rows, per_month[m], with_vat, forced) for m in months}
    res = {
        "organization": org,
        "period": period,
        "dateField": field,
        "dateLabel": DATE_LABEL.get(field, field),
        "historyMonths": months[:-1],
        "amountWithVat": with_vat,
        "mappedFields": lst.get("mappedFields", FIELDS),
        "listIssues": lst.get("issues", []),
        "warnings": [],
        "missing": [],
        "received": [],
        "review": [],
        "notExpected": [],
        "detailIds": [],
        "ignored": dict(ignored),
    }
    today = today or dt.date.today()
    if period >= f"{today.year:04d}-{today.month:02d}":
        res["warnings"].append(f"měsíc {period} ještě neskončil – faktury můžou dorazit, dohady budou zbytečně vysoké")
    if docs_warning:
        res["warnings"].append(docs_warning)
    res["warnings"] += confirm_issues
    if window_start and window_start[:7] > months[0]:
        res["warnings"].append(
            f"načtená historie začíná {window_start}, potřeba je od {months[0]}-01 – "
            "průměry a čtvrtletní/roční řádky můžou být špatně"
        )
    if not rows:
        res["warnings"].append("seznam je prázdný – není s čím porovnávat")
    if not any(per_month[m] for m in months):
        res["warnings"].append(
            "v načteném období nejsou žádné přijaté faktury – zkontrolujte organizaci a datum; "
            "výsledek by vypadal, jako by chybělo všechno"
        )
    ratios = []
    for i, r in enumerate(rows):
        hits = {m: assign[m][0].get(i, []) for m in months}
        hist_hits = {m for m in months[:-1] if hits[m]}
        exp, note = expected_in(r, period, hist_hits)
        now = hits[period]
        label = r["name"] or r["ic"]
        if now:
            for d in now:
                n = []
                amt = doc_amount(d, with_vat)
                base_czk = czk(d, "taxExclusiveAmount")
                if r["amount"] and base_czk:
                    ratios.append(base_czk / r["amount"])
                if r["amount"] and amt is not None and abs(amt - r["amount"]) > r["amount"] * r["tolerance"] / 100:
                    pct = (amt - r["amount"]) / r["amount"] * 100
                    n.append(f"částka se liší o {pct:+.0f} % od seznamu")
                    review(res, "Částka mimo toleranci", label, r["row"], d, field, org, n[-1])
                if not exp:
                    n.append("došla mimo očekávaný měsíc")
                if d["id"] in forced:
                    n.append(
                        f"spárováno ručně (potvrdil uživatel) – IČ / název na faktuře: "
                        f"{d.get('partnerIC') or '–'} / {d.get('partnerName') or '–'}"
                    )
                res["received"].append(
                    {
                        "row": r["row"],
                        "listName": label,
                        "listDescription": r["description"],
                        "listKeyword": r["keyword"],
                        "listAmount": r["amount"],
                        **doc_row(d, field, org, "; ".join(n)),
                    }
                )
            if len(now) > 1:
                review(
                    res,
                    "Víc faktur na jeden řádek",
                    label,
                    r["row"],
                    note=f"{len(now)} {'faktury' if len(now) < 5 else 'faktur'} za měsíc "
                    f"({', '.join(str(d.get('number')) for d in now)}) – zkontrolujte, zda nejde o další "
                    "pravidelnou platbu",
                )
            continue
        if not exp:
            res["notExpected"].append(
                {"row": r["row"], "listName": label, "frequency": r["frequency"], "months": r["months"], "note": note}
            )
            if note.startswith("měsíce fakturace neuvedeny a"):
                review(res, "Nejasná frekvence", label, r["row"], note=note)
            continue
        hist_docs = sorted((d for m in months[:-1] for d in hits[m]), key=lambda d: doc_date(d, field) or "")
        last = hist_docs[-1] if hist_docs else None
        bases = [b for b in (doc_amount(d, with_vat) for d in hist_docs[-3:]) if b is not None]
        miss = {
            "row": r["row"],
            "name": label,
            "ic": r["ic"],
            "keyword": r["keyword"],
            "description": r["description"] or (last or {}).get("description") or "",
            "frequency": r["frequency"],
            "note": note,
            "src": {},
        }
        if r["amount"] is not None:
            miss["amount"], miss["src"]["amount"] = r["amount"], "seznam"
        elif bases:
            n_bases = len(bases)
            miss["amount"] = round(sum(bases) / n_bases, 2)
            miss["src"]["amount"] = f"průměr z {n_bases} {'faktury' if n_bases == 1 else 'faktur'}"
        else:
            miss["amount"], miss["src"]["amount"] = None, ""
            review(
                res,
                "Dohad bez částky",
                label,
                r["row"],
                note="částka není v seznamu a v historii není žádná faktura – doplňte ji ručně",
            )
        for f in ACC_FIELDS:
            miss[f], miss["src"][f] = (r[f], "seznam") if r[f] else ("", "")
        if not r["account"] and last and last.get("accountCode"):
            miss["account"], miss["src"]["account"] = last["accountCode"], "historie"
        miss["lastInvoice"] = doc_row(last, field, org) if last else None
        if not last:
            miss["note"] = "; ".join(x for x in (note, "v historii žádná faktura – údaje jen ze seznamu") if x)
        # any code not given by the list -> read the last invoice (lines may split cost centres)
        if last and any(not r[f] for f in ACC_FIELDS if f != "project"):
            res["detailIds"].append(last["id"])
            miss["detailId"] = last["id"]
        # maybe it arrived under another name / IČ
        for d in assign[period][2]:
            why = similar_supplier(r, d)
            if why:
                review(
                    res,
                    "Možná došla pod jiným IČ / názvem",
                    label,
                    r["row"],
                    d,
                    field,
                    org,
                    f"{why} – pokud jde o tutéž platbu, dohad nedělejte a opravte IČ / název v seznamu",
                )
        res["missing"].append(miss)
    for d, cands, why in assign[period][1]:
        review(
            res,
            "Nejisté párování",
            rows[cands[0]]["name"] or rows[cands[0]]["ic"],
            ", ".join(str(rows[i]["row"]) for i in cands),
            d,
            field,
            org,
            why,
        )
    prev = months[:-1][-3:]
    unl: defaultdict = defaultdict(lambda: {"months": set(), "docs": []})
    for m in months:
        for d in assign[m][2]:
            k = supplier_key(norm_ic(d.get("partnerIC")), d.get("partnerName"))
            unl[k]["months"].add(m)
            unl[k]["docs"].append(d)
    for v in unl.values():
        hit = len(v["months"] & set(prev))
        if hit >= 2:
            last = sorted(v["docs"], key=lambda d: doc_date(d, field) or "")[-1]
            review(
                res,
                "Pravidelný dodavatel mimo seznam",
                last.get("partnerName"),
                "",
                last,
                field,
                org,
                f"faktury v {hit} ze {len(prev)} předchozích měsíců"
                f"{', i v kontrolovaném' if period in v['months'] else ', v kontrolovaném ne'} – doplnit do seznamu?",
            )
    for d in rejected:
        if month_of(doc_date(d, field)) == period and any(same_supplier(r, d) for r in rows):
            review(
                res,
                "Zamítnutá faktura",
                d.get("partnerName"),
                "",
                d,
                field,
                org,
                "zamítnutá ve schvalování – nepočítá se jako došlá, dohad může být potřeba",
            )
    for d in no_rate:
        if month_of(doc_date(d, field)) in months:
            review(
                res,
                "Cizí měna bez kurzu",
                d.get("partnerName"),
                "",
                d,
                field,
                org,
                "nejde přepočítat na CZK – nezapočteno do průměru ani do kontroly částky",
            )
    for d in no_date:
        if any(same_supplier(r, d) for r in rows):
            review(
                res,
                "Faktura bez data",
                d.get("partnerName"),
                "",
                d,
                field,
                org,
                f"chybí {DATE_LABEL.get(field, field)} – nejde zařadit do měsíce; pokud patří do {period}, "
                "dohad nedělejte",
            )
    if (
        len(ratios) >= 3
        and not with_vat
        and sum(1 for q in ratios if 1 / VAT_RATIO[1] <= q <= 1 / VAT_RATIO[0]) > len(ratios) / 2
    ):
        res["warnings"].append(
            "u většiny došlých faktur je základ asi o 21 % nižší než částka v seznamu – "
            "částky v seznamu jsou nejspíš s DPH (změňte nastavení „s DPH“)"
        )
    res["detailIds"] = sorted(set(res["detailIds"]))
    res["summary"] = {
        "listRows": len(rows),
        "missing": len(res["missing"]),
        "received": len(res["received"]),
        "receivedNotInErp": sum(1 for x in res["received"] if x["notInErp"]),
        "review": len(res["review"]),
        "notExpected": len(res["notExpected"]),
        "detailCalls": len(res["detailIds"]),
        "ignored": res["ignored"],
        "warnings": res["warnings"],
    }
    return res


def cmd_match(a):
    docs, warn = load_docs(a.docs)
    res = match(
        load_json(a.list),
        docs,
        a.period,
        a.date_field,
        a.history,
        a.org,
        a.window_start,
        warn,
        confirms=load_json(a.confirm) if a.confirm else None,
    )
    dump(res, a.out)
    print(json.dumps(res["summary"], ensure_ascii=False))


def code(v):
    if isinstance(v, dict):
        return v.get("code") or v.get("externalId") or ""
    return v or ""


def accounting_split(det):
    """-> list of (share, {field: code}) – one item when the invoice is not split."""
    acc = det.get("accounting") or {}
    head = {
        "costCenter": code(acc.get("costCenter")),
        "contract": code(acc.get("contract")),
        "project": code(acc.get("project")),
        "activity": code(acc.get("activity")),
        "account": det.get("accountCode") or "",
    }
    groups: defaultdict = defaultdict(float)
    total = 0.0
    for ln in det.get("lines") or []:
        la = ln.get("accounting") or {}
        c = {
            "costCenter": code(ln.get("costCenter")) or code(la.get("costCenter")) or head["costCenter"],
            "contract": code(ln.get("contract")) or code(la.get("contract")) or head["contract"],
            "project": code(la.get("project")) or head["project"],
            "activity": code(ln.get("activity")) or code(la.get("activity")) or head["activity"],
            "account": ln.get("accountCode") or head["account"],
        }
        base = abs(float(ln.get("totalAmount") or 0))
        groups[tuple(c[f] for f in ACC_FIELDS)] += base
        total += base
    if len(groups) <= 1 or not total:
        if groups:
            only = next(iter(groups))
            head = {f: head[f] or only[i] for i, f in enumerate(ACC_FIELDS)}
        return [(1.0, head)]
    return [(b / total, dict(zip(ACC_FIELDS, k))) for k, b in sorted(groups.items(), key=lambda x: -x[1])]


def invoice_codes(det):
    """-> (codes, note); a split invoice gives empty codes so the month check splits the accrual by it."""
    parts = accounting_split(det)
    if len(parts) == 1:
        return parts[0][1], ""
    diff = [f for f in ACC_FIELDS if len({c[f] for _, c in parts}) > 1]
    shares = ", ".join(f"{'/'.join(c[f] or '–' for f in diff)} {s * 100:.0f} %" for s, c in parts)
    return (
        dict.fromkeys(ACC_FIELDS, ""),
        f"poslední faktura rozúčtována: {shares} – kódy doplní kontrola měsíce podle faktury",
    )


def apply_codes(row, det):
    if not det:
        return
    codes, note = invoice_codes(det)
    for f in ACC_FIELDS:
        if note:
            row[TEMPLATE[f]] = ""
        elif not row.get(TEMPLATE[f]):
            row[TEMPLATE[f]] = codes[f]
    if note:
        row["Poznámka"] = "; ".join(x for x in (row.get("Poznámka"), note) if x)


def apply_details(res, details):
    by_id = {d.get("id"): d for d in details}
    mapped = set(res.get("mappedFields") or FIELDS)
    for m in res["missing"]:
        det = by_id.get(m.get("detailId"))
        parts = accounting_split(det) if det else [(1.0, {})]
        fixed = {f for f in ACC_FIELDS if m[f] and m["src"].get(f) == "seznam"}
        if det and len(parts) > 1 and not fixed:
            m["split"] = [{"share": round(s, 4), **c} for s, c in parts]
            for f in ACC_FIELDS:  # only fields that really got a value from the split
                m["src"][f] = "historie (rozpad)" if any(c.get(f) for _, c in parts) else ""
        else:
            codes = parts[0][1]
            for f in ACC_FIELDS:
                if not m[f] and codes.get(f):
                    m[f], m["src"][f] = codes[f], "historie"
            if det and len(parts) > 1:
                m["note"] = "; ".join(
                    x for x in (m.get("note"), "poslední faktura je rozúčtovaná – použito rozúčtování ze seznamu") if x
                )
        empty = [ACC_LABEL[f] for f in ACC_FIELDS if f in mapped and not m.get("split") and not m[f]]
        if empty:
            res["review"].append(
                {
                    "kind": "Chybí účetní údaje",
                    "row": m["row"],
                    "listName": m["name"],
                    "note": f"nedohledáno ani z historie: {', '.join(empty)} – doplňte do dohadu",
                }
            )


def read_accruals(path):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from inspect_xls import read_book

    book = read_book(path)
    sheet = next((n for n in book if "dohad" in str(n).lower() and "rozpu" not in str(n).lower()), None)
    if sheet is None and len(book) == 1:
        sheet = next(iter(book))
    if sheet is None:
        raise SystemExit('The file has no sheet "Podklad pro dohady".')
    named = "dohad" in str(sheet).lower()
    data = book[sheet]
    hdr = [text(h) for h in data[0]]

    def col(*names):
        return next((i for i, h in enumerate(hdr) if any(h.lower().startswith(n) for n in names)), None)

    ci = {
        "name": col("firma"),
        "ic": col("ič"),
        "description": col("popis"),
        "keyword": col("klíčové"),
        "amount": col("částka"),
        "row": col(HDR_LIST_ROW.lower(), OLD_HDR_LIST_ROW.lower()),
    }
    for f in ACC_FIELDS:
        ci[f] = col(ACC_LABEL[f].lower())
    if ci["name"] is None or ci["amount"] is None:
        raise SystemExit('Sheet "Podklad pro dohady" has no columns "Firma / osoba" and "Částka".')
    if not named and ci["row"] is None:
        raise SystemExit(f'The file is not an accruals file: no column "{HDR_LIST_ROW}".')
    out = []
    for n, r in enumerate(data[1:], start=2):

        def g(k, r=r):
            return r[ci[k]] if ci[k] is not None and ci[k] < len(r) else None

        if (not text(g("name")) and not text(g("ic"))) or (TOTAL_ROW.match(text(g("name"))) and not norm_ic(g("ic"))):
            continue
        amt, _ = parse_amount(g("amount"))
        out.append(
            {
                "xlsRow": n,
                "name": text(g("name")),
                "ic": norm_ic(g("ic")),
                "description": text(g("description")),
                "keyword": text(g("keyword")),
                "amount": amt or 0.0,
                "listRow": text(g("row")),
                **{f: text(g(f)) for f in ACC_FIELDS},
            }
        )
    return out


def release(accruals, lst, docs, period, field, org, links=None, with_vat=False):
    """Accruals booked for `period` (accruals file) against invoices of that period that arrived since."""
    links = links or {}
    rows = lst.get("rows") or []
    groups = defaultdict(list)  # one accrual may be split into several rows (cost centres)
    for p in accruals:
        groups[(supplier_key(p["ic"], p["name"]), p["keyword"].lower(), p["listRow"])].append(p)
    inv = [
        d
        for d in docs
        if d.get("invoiceType") in COUNTED_TYPES and not is_rejected(d) and month_of(doc_date(d, field)) == period
    ]
    notes = [
        d
        for d in docs
        if d.get("invoiceType") in ("CreditNote", "DebitNote") and month_of(doc_date(d, field)) == period
    ]
    out = {"period": period, "dateLabel": DATE_LABEL.get(field, field), "release": [], "pending": [], "review": []}
    used = set()
    cancelled = cancelled_ids(docs, field, links)
    for (_skey, _kw, list_row), parts in groups.items():
        p0 = parts[0]
        accrual = round(sum(p["amount"] for p in parts), 2)
        probe = {"name": p0["name"], "ic": p0["ic"], "keyword": p0["keyword"], "amount": accrual, "tolerance": 20.0}
        sib = [r for r in rows if same_supplier(probe, {"partnerIC": r["ic"], "partnerName": r["name"]})]
        lr = next((r for r in rows if str(r["row"]) == str(list_row)), None)
        if lr is None and len(sib) == 1:
            lr = sib[0]
        elif lr is None and sib:  # old accruals file without keyword / row – find the row by description
            best = max(
                sib,
                key=lambda r: difflib.SequenceMatcher(
                    None, norm_name(r["description"]), norm_name(p0["description"])
                ).ratio(),
            )
            if (
                difflib.SequenceMatcher(None, norm_name(best["description"]), norm_name(p0["description"])).ratio()
                >= 0.5
            ):
                lr = best
        if lr:
            probe.update(keyword=probe["keyword"] or lr["keyword"], tolerance=lr["tolerance"])
        cands = [d for d in inv if d["id"] not in used and d["id"] not in cancelled and same_supplier(probe, d)]
        if cands and (len(cands) > 1 or len(sib) > 1):  # rent + energy from one supplier – keyword/amount decide
            scored = sorted(((score(probe, d, with_vat), d) for d in cands), key=lambda x: -x[0])
            cands = (
                [d for s, d in scored if s > 0 and s == scored[0][0]]
                if scored[0][0] > 0
                else (cands if len(sib) <= 1 else [])
            )
        base = {
            "name": p0["name"],
            "ic": p0["ic"],
            "description": p0["description"],
            "accrual": accrual,
            "parts": parts,
        }
        if not cands:
            storno = any(x["id"] in cancelled and same_supplier(probe, x) for x in inv)
            note = "faktura za období stornována dobropisem" if storno else "faktura za období zatím nedošla"
            out["pending"].append({**base, "note": f"{note} – dohad trvá"})
            continue
        if len(cands) > 1:
            out["review"].append(
                {
                    **base,
                    "kind": "Víc faktur k jednomu dohadu",
                    "invoices": [doc_row(d, field, org) for d in cands],
                    "note": "nejde určit, kterou fakturou dohad rozpustit",
                }
            )
            continue
        d = cands[0]
        used.add(d["id"])
        sup_invoices = [x for x in inv if same_supplier(probe, x)]
        amt = doc_amount(d, with_vat)
        item = {
            **base,
            "invoice": doc_row(d, field, org),
            "invoiceAmount": amt,
            "diff": round(amt - accrual, 2) if amt is not None else None,
            "notes": [],
            "netAmount": amt,
            "remark": "",
        }
        # credit / debit notes of the same supplier and period
        mine = [n for n in notes if same_supplier(probe, n)]
        for n in mine:
            linked = d["id"] in (links.get(n["id"]) or [])
            other_link = bool(links.get(n["id"])) and not linked
            if linked or (not other_link and len(sup_invoices) == 1):
                sign = -1 if n.get("invoiceType") == "CreditNote" else 1
                na = doc_amount(n, with_vat) or 0
                item["notes"].append(
                    {
                        **doc_row(n, field, org),
                        "signed": sign * na,
                        "how": "propojený doklad" if linked else "stejný dodavatel a období",
                    }
                )
                if amt is not None:
                    item["netAmount"] = round((item["netAmount"] or 0) + sign * na, 2)
                if sign < 0 and amt is not None and abs(na - amt) < 0.01 and len(sup_invoices) > 1:
                    out["review"].append(
                        {
                            **base,
                            "kind": "Faktura stornována a nahrazena",
                            "invoices": [doc_row(x, field, org) for x in sup_invoices],
                            "note": f"dobropis {n.get('number')} ruší celou fakturu – rozpusťte proti nové faktuře",
                        }
                    )
            elif not other_link:
                out["review"].append(
                    {
                        **base,
                        "kind": "Dobropis / vrubopis nejde přiřadit",
                        "invoices": [doc_row(n, field, org)],
                        "note": "dodavatel má v období víc faktur a doklad není propojený",
                    }
                )
        if item["netAmount"] is not None and item["notes"]:
            item["netDiff"] = round(item["netAmount"] - accrual, 2)
        if amt is not None and accrual and abs(amt - accrual) > accrual * probe["tolerance"] / 100:
            item["remark"] = f"faktura se liší od dohadu o {(amt - accrual) / accrual * 100:+.0f} %"
        out["release"].append(item)
    out["summary"] = {
        "release": len(out["release"]),
        "pending": len(out["pending"]),
        "review": len(out["review"]),
        "accrualReleased": round(sum(x["accrual"] for x in out["release"]), 2),
        "accrualPending": round(sum(x["accrual"] for x in out["pending"]), 2),
    }
    return out


def cmd_release(a):
    docs, warn = load_docs(a.docs)
    lst = load_json(a.list) if a.list else {"rows": []}
    links = load_json(a.links) if a.links else {}
    out = release(
        read_accruals(a.accruals), lst, docs, a.period, a.date_field, a.org, links, lst.get("amountWithVat", False)
    )
    if warn:
        out["warning"] = warn
    dump(out, a.out)
    print(json.dumps(out["summary"], ensure_ascii=False))


def cmd_report(a):
    res = load_json(a.result)
    if a.details:
        det = load_json(a.details)
        apply_details(res, det if isinstance(det, list) else [det])
    rel = load_json(a.release) if a.release else None
    write_report(res, a.out, rel)
    s = dict(res["summary"])
    s["review"] = len(res["review"])
    s["missingRows"] = sum(len(m.get("split") or [1]) for m in res["missing"])
    if rel:
        s["releaseSummary"] = rel["summary"]
    print(json.dumps(s, ensure_ascii=False))


def report_amount(x, with_vat):
    return x.get("totalAmount") if with_vat else x.get("taxExclusiveAmount")


def write_report(res, out, rel=None):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    head_fill = PatternFill("solid", fgColor="1F3864")
    head_font = Font(bold=True, color="FFFFFF")
    soft = PatternFill("solid", fgColor="FFF2CC")
    show_project = any(m.get("project") or any(p.get("project") for p in m.get("split") or []) for m in res["missing"])

    def sheet(ws, headers, rows, widths):
        ws.append(headers)
        for c in ws[1]:
            c.fill, c.font = head_fill, head_font
            c.alignment = Alignment(wrap_text=True, vertical="top")
        for r in rows:
            ws.append([v.get("text") if isinstance(v, dict) else v for v in r])
            for col, v in enumerate(r, 1):
                if isinstance(v, dict) and v.get("url"):
                    cell = ws.cell(ws.max_row, col)
                    cell.hyperlink, cell.font = v["url"], Font(color="0563C1", underline="single")
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A2"
        if rows:
            ws.auto_filter.ref = ws.dimensions

    s = res["summary"]
    ws = wb.active
    ws.title = "Souhrn"
    ign = res.get("ignored") or {}
    info = [
        ("Organizace", res.get("organization")),
        ("Kontrolovaný měsíc", res["period"]),
        ("Rozhodné datum", res["dateLabel"]),
        ("Historie pro průměr", ", ".join(res["historyMonths"][-3:])),
        ("Částky", "s DPH" if res.get("amountWithVat") else "bez DPH, v CZK"),
        ("Řádků v seznamu", s["listRows"]),
        ("Chybí – podklad pro dohady", len(res["missing"])),
        ("Došlé faktury", s["received"]),
        ("  z toho neodeslané do ERP", s["receivedNotInErp"]),
        ("Ke kontrole", len(res["review"])),
        ("V tomto měsíci se neočekávají", s["notExpected"]),
        ("Nezapočteno (jiné druhy dokladů)", ", ".join(f"{v}× {k}" for k, v in ign.items()) or "–"),
    ]
    if rel:
        rs = rel["summary"]
        info += [
            ("Rozpuštění dohadů za", rel["period"]),
            ("  rozpustit", f"{rs['release']} (dohady {rs['accrualReleased']:,.2f} Kč)".replace(",", " ")),
            ("  dohad trvá", f"{rs['pending']} (dohady {rs['accrualPending']:,.2f} Kč)".replace(",", " ")),
            ("  ke kontrole", rs["review"]),
        ]
    for k, v in info:
        ws.append([k, v])
    ws.append([])
    ws.append([HDR_SOURCE])
    ws.cell(ws.max_row, 1).font = Font(bold=True)
    for k, v in SOURCE_HELP:
        ws.append([k, v])
    warns = res.get("warnings") or []
    issues = res.get("listIssues") or []
    if warns or issues:
        ws.append([])
        ws.append(["Upozornění"])
        ws.cell(ws.max_row, 1).font = Font(bold=True, color="C00000")
        for w in warns:
            ws.append(["", w])
        for i in issues:
            ws.append(["", f"seznam, řádek {i['row']}: {i['issue']}" if i.get("row") else i["issue"]])
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 34, 90

    acc_cols = ["costCenter", "contract"] + (["project"] if show_project else []) + ["activity", "account"]
    amt_label = "Částka CZK s DPH" if res.get("amountWithVat") else "Částka CZK bez DPH"
    with_vat = bool(res.get("amountWithVat"))
    amount_hdr = "Celkem s DPH" if with_vat else "Částka bez DPH"
    rows = []
    for m in res["missing"]:
        li = m.get("lastInvoice") or {}
        src = "; ".join(
            f"{('částka' if k == 'amount' else ACC_LABEL[k].lower())}: {v}"
            for k, v in m["src"].items()
            if v and v != "seznam"
        )
        tail = [
            src or "seznam",
            {"text": li.get("number") or "", "url": li.get("link")},
            li.get("date") or "",
            m.get("note") or "",
            m.get("keyword") or "",
            m["row"],
        ]
        parts = m.get("split") or [{"share": 1.0, **{f: m.get(f, "") for f in ACC_FIELDS}}]
        for p in parts:
            amount = round(m["amount"] * p["share"], 2) if m["amount"] is not None else None
            note = tail[3]
            if len(parts) > 1:
                note = "; ".join(x for x in (note, f"rozpad podle poslední faktury: {p['share'] * 100:.0f} %") if x)
            rows.append(
                [m["name"], m["ic"], m["description"], amount]
                + [p.get(f, "") for f in acc_cols]
                + tail[:3]
                + [note]
                + tail[4:]
            )
    ws = wb.create_sheet("Podklad pro dohady")
    sheet(
        ws,
        ["Firma / osoba", "IČ", "Popis", amt_label]
        + [ACC_LABEL[f] for f in acc_cols]
        + [HDR_SOURCE, "Poslední došlá faktura", "Její datum", "Poznámka", "Klíčové slovo", HDR_LIST_ROW],
        rows,
        [30, 11, 34, 16] + [13] * len(acc_cols) + [28, 20, 12, 40, 14, 9],
    )
    srccol = 5 + len(acc_cols)
    for r in range(2, ws.max_row + 1):
        ws.cell(r, 4).number_format = "#,##0.00"
        if ws.cell(r, 4).value is None:
            ws.cell(r, 4).fill = PatternFill("solid", fgColor="F8CBAD")
        if any(w in str(ws.cell(r, srccol).value) for w in ("historie", "průměr")):
            ws.cell(r, srccol).fill = soft

    rows = [
        [
            x["listName"],
            x["listDescription"],
            {"text": x["number"], "url": x["link"]},
            x["partnerName"],
            x["date"],
            report_amount(x, with_vat),
            x["currency"],
            FLOW_LABEL.get(x["flowStatus"], x["flowStatus"]),
            "ne" if x["notInErp"] else "ano",
            x["note"],
        ]
        for x in res["received"]
    ]
    ws = wb.create_sheet("Došlé")
    sheet(
        ws,
        [
            HDR_LIST_NAME,
            "Popis v seznamu",
            "Číslo faktury",
            "Dodavatel",
            res["dateLabel"],
            amount_hdr,
            "Měna",
            "Stav ve wflow",
            "V ERP",
            "Poznámka",
        ],
        rows,
        [28, 28, 18, 30, 12, 14, 7, 22, 7, 40],
    )
    for r in range(2, ws.max_row + 1):
        ws.cell(r, 6).number_format = "#,##0.00"
        if ws.cell(r, 9).value == "ne":
            ws.cell(r, 9).fill = soft

    rows = [
        [
            x["kind"],
            x.get("listName") or "",
            {"text": x.get("number") or "", "url": x.get("link")},
            x.get("partnerName") or "",
            x.get("date") or "",
            report_amount(x, with_vat),
            x.get("note") or "",
        ]
        for x in res["review"]
    ]
    ws = wb.create_sheet("Ke kontrole")
    sheet(
        ws,
        [
            "Co zkontrolovat",
            HDR_LIST_NAME,
            "Faktura",
            "Dodavatel na faktuře",
            res["dateLabel"],
            amount_hdr,
            "Poznámka",
        ],
        rows,
        [30, 30, 22, 30, 12, 14, 60],
    )

    if rel:
        ws = wb.create_sheet(f"Rozpuštění {rel['period']}")
        rows = []
        for x in rel["release"]:
            iv = x["invoice"]
            notes = ", ".join(f"{n['number']} ({n['signed']:+,.2f})".replace(",", " ") for n in x["notes"])
            rows.append(
                [
                    "Došlo – rozpustit",
                    x["name"],
                    x["description"],
                    x["accrual"],
                    {"text": iv["number"], "url": iv["link"]},
                    iv["date"],
                    x["invoiceAmount"],
                    x["diff"],
                    notes,
                    x["netAmount"] if x["notes"] else None,
                    x.get("netDiff"),
                    "; ".join(y for y in (x.get("remark"), ", ".join(n["how"] for n in x["notes"])) if y),
                ]
            )
        for x in rel["pending"]:
            rows.append(
                [
                    "Pořád chybí – dohad trvá",
                    x["name"],
                    x["description"],
                    x["accrual"],
                    "",
                    "",
                    None,
                    None,
                    "",
                    None,
                    None,
                    x["note"],
                ]
            )
        for x in rel["review"]:
            ivs = x.get("invoices") or []
            rows.append(
                [
                    f"Ke kontrole: {x['kind']}",
                    x["name"],
                    x["description"],
                    x["accrual"],
                    {"text": ", ".join(str(i["number"]) for i in ivs), "url": ivs[0]["link"] if len(ivs) == 1 else ""},
                    "",
                    None,
                    None,
                    "",
                    None,
                    None,
                    x["note"],
                ]
            )
        amt = "s DPH" if res.get("amountWithVat") else "bez DPH"
        sheet(
            ws,
            [
                "Stav",
                "Firma / osoba",
                "Popis",
                f"Dohad ({amt})",
                "Faktura",
                rel["dateLabel"],
                f"Faktura ({amt})",
                "Rozdíl faktura − dohad",
                "Dobropisy / vrubopisy",
                "Čistá částka",
                "Rozdíl čistá − dohad",
                "Poznámka",
            ],
            rows,
            [26, 30, 30, 14, 20, 12, 14, 14, 26, 14, 14, 44],
        )
        for r in range(2, ws.max_row + 1):
            for c in (4, 7, 8, 10, 11):
                ws.cell(r, c).number_format = "#,##0.00"
    wb.save(out)


def desc_key(desc):
    """'Nájem kanceláří – červenec 2026' -> 'najem kancelari'; months, years, numbers dropped."""
    s = strip_diacritics(str(desc or "").lower())
    s = re.sub(r"[^a-z]+", " ", s)
    words = [w for w in s.split() if w not in MONTH_TOKEN and len(w) > 2 and not re.fullmatch(r"q[1-4]", w)]
    return " ".join(words[:2])


def first_word(desc):
    for w in re.split(r"[^\wÀ-ž]+", str(desc or "")):
        if len(w) > 2 and strip_diacritics(w.lower()) not in MONTH_TOKEN:
            return w
    return ""


def median(vals):
    v = sorted(vals)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def counted_groups(docs, months, field):
    """-> (invoices per supplier, IČ-merge note per supplier, months with data, skipped)"""
    groups = defaultdict(list)
    seen_months = set()
    cancelled = cancelled_ids(docs, field)
    skipped: Counter = Counter()
    for d in docs:
        if d.get("invoiceType") not in COUNTED_TYPES or is_rejected(d) or d["id"] in cancelled:
            continue
        m = month_of(doc_date(d, field))
        if m is None:
            skipped["bez data"] += 1
            continue
        if m in months:
            seen_months.add(m)
            groups[supplier_key(norm_ic(d.get("partnerIC")), d.get("partnerName"))].append(d)
    # one supplier under two IČ (typo on one invoice) – merge by the normalized name, flag it
    ic_note = {}
    by_name = defaultdict(list)
    for k in groups:
        nm = norm_name(groups[k][0].get("partnerName"))
        if nm:
            by_name[nm].append(k)
    for _nm, keys in by_name.items():
        if len(keys) > 1:
            main = max(keys, key=lambda k: len(groups[k]))
            ics = sorted({norm_ic(d.get("partnerIC")) or "bez IČ" for k in keys for d in groups[k]})
            for k in keys:
                if k != main:
                    groups[main] += groups.pop(k)
            ic_note[main] = (
                f"faktury pod různými IČ ({', '.join(ics)}) – ověřte správné IČ; u faktury s jiným IČ může být překlep"
            )
    return groups, ic_note, seen_months, skipped


def coverage(months, seen_months):
    """History in wflow may start later than the window – judge regularity on the months that have data."""
    return len([m for m in months if seen_months and m >= min(seen_months)]) or len(months)


def supplier_rows(g, months, covered, field, with_vat=False, default_freq=None, note=""):
    """-> template rows for one supplier's invoices, split by description when it has several payments"""

    def candidate(docs_, keyword, note="", default=None):
        by_m = defaultdict(list)
        for d in docs_:
            by_m[month_of(doc_date(d, field))].append(d)
        hit = sorted(by_m)
        idx = [months.index(m) for m in hit]
        nums = [int(m[5:]) for m in hit]
        freq, mon = None, []
        if len(hit) >= max(2, round(covered * 2 / 3)):
            freq = "měsíčně"
        elif len(hit) >= 2 and all((b - a) % 3 == 0 for a, b in zip(idx, idx[1:])):
            freq, mon = "čtvrtletně", sorted({(nums[0] - 1 + 3 * i) % 12 + 1 for i in range(4)})
        freq = freq or default
        if not freq:
            return None
        per = max(len(v) for v in by_m.values())
        if per > 1 and not note:
            note = (
                f"až {per} faktury za měsíc a z popisu nejde poznat, o jaké platby jde – "
                "zkontrolujte, zda nejde o víc pravidelných plateb"
            )
        docs_ = sorted(docs_, key=lambda d: doc_date(d, field) or "")
        last = docs_[-1]
        # median of the last 3 invoices – one unusual invoice (extra work, price change) does not move it
        pairs = [
            (d, czk(d, "totalAmount") if with_vat else czk(d, "taxExclusiveAmount") or czk(d, "totalAmount"))
            for d in docs_[-3:]
        ]
        bases = [b for _, b in pairs if b]
        amount = round(median(bases), 2) if bases else None
        notes = [note] if note else []

        def num(v):
            return f"{v:,.0f}".replace(",", " ")

        if amount:
            odd = [(d, b) for d, b in pairs if b and abs(b - amount) > amount * 0.2]
            if odd:
                notes.append(
                    "ověřte částku: "
                    + ", ".join(
                        f"{d.get('number')} ({month_of(doc_date(d, field))}) {num(b)} Kč = {(b - amount) / amount * 100:+.0f} %"
                        for d, b in odd
                    )
                    + " proti obvyklé částce – v seznamu je obvyklá (medián posledních 3 faktur)"
                )
        foreign = sorted({(d.get("currency") or "").upper() for d in docs_} - {"", "CZK"})
        if foreign:
            fc = Counter(
                d.get("totalAmount") if with_vat else d.get("taxExclusiveAmount") or d.get("totalAmount") for d in docs_
            ).most_common(1)[0][0]
            notes.append(
                f"faktury v {', '.join(foreign)} (obvykle {num(fc)} {foreign[0]}), částka přepočtena "
                "kurzem z faktur na Kč"
            )
        ics = Counter(norm_ic(d.get("partnerIC")) for d in docs_ if norm_ic(d.get("partnerIC")))
        ic = (
            max(ics, key=lambda k: (ics[k], -next(i for i, d in enumerate(docs_) if norm_ic(d.get("partnerIC")) == k)))
            if ics
            else ""
        )
        descs = Counter((d.get("description") or "").strip() for d in docs_ if d.get("description"))
        accounts = Counter(d.get("accountCode") for d in docs_ if d.get("accountCode"))
        note = "; ".join(notes)
        return {
            TEMPLATE["name"]: last.get("partnerName"),
            TEMPLATE["ic"]: ic,  # most frequent, tie -> oldest
            TEMPLATE["description"]: re.sub(r"\s*[–-]?\s*\b\S+\s+20\d\d\b\s*$", "", descs.most_common(1)[0][0])
            if descs
            else "",
            TEMPLATE["keyword"]: keyword,
            TEMPLATE["amount"]: amount,
            TEMPLATE["tolerance"]: 20,
            TEMPLATE["frequency"]: freq,
            TEMPLATE["months"]: ", ".join(str(m) for m in mon),
            TEMPLATE["costCenter"]: "",
            TEMPLATE["contract"]: "",
            TEMPLATE["project"]: "",
            TEMPLATE["activity"]: "",
            TEMPLATE["account"]: accounts.most_common(1)[0][0] if accounts else "",
            "Faktur za období": len(docs_),
            "Měsíce s fakturou": ", ".join(hit),
            "Poznámka": note,
            "_detailId": last.get("id"),
        }

    out: list = []
    by_m = Counter(month_of(doc_date(d, field)) for d in g)
    clusters = defaultdict(list)
    for d in g:
        clusters[desc_key(d.get("description"))].append(d)
    if max(by_m.values()) > 1 and len(clusters) > 1 and "" not in clusters:
        made = [
            candidate(
                c,
                first_word(c[0].get("description")),
                "rozděleno podle popisu faktur (víc plateb od jednoho dodavatele)",
            )
            for c in clusters.values()
        ]
        out = [m for m in made if m]
    if not out:
        c = candidate(g, "", default=default_freq)
        out = [c] if c else []
    for r in out:
        r["Poznámka"] = "; ".join(x for x in (r["Poznámka"], note) if x)
    return out


def suggest(docs, end, months_n, field, details=None):
    months = [shift(end, -k) for k in range(months_n - 1, -1, -1)]
    groups, ic_note, seen_months, skipped = counted_groups(docs, months, field)
    by_id = {d.get("id"): d for d in details or []}
    out: list = []
    for key, g in groups.items():
        for r in supplier_rows(g, months, coverage(months, seen_months), field, note=ic_note.get(key, "")):
            apply_codes(r, by_id.get(r["_detailId"]))
            out.append(r)
    out.sort(key=lambda r: (str(r[TEMPLATE["name"]]).lower(), str(r[TEMPLATE["keyword"]]).lower()))
    return out, months, skipped


def cmd_suggest(a):
    docs, warn = load_docs(a.docs)
    details = load_json(a.details) if a.details else None
    rows, months, skipped = suggest(docs, a.end, a.months, a.date_field, details)
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Pravidelné platby"
    headers = [*TEMPLATE.values(), "Faktur za období", "Měsíce s fakturou", "Poznámka"]
    ws.append(headers)
    for c in ws[1]:
        c.fill, c.font = PatternFill("solid", fgColor="1F3864"), Font(bold=True, color="FFFFFF")
    for r in rows:
        ws.append([r.get(h) for h in headers])
    for i, w in enumerate([30, 11, 34, 16, 14, 11, 13, 16, 12, 12, 12, 12, 14, 10, 30, 50], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    wb.save(a.out)
    first = min((r["Měsíce s fakturou"].split(", ")[0] for r in rows), default=None)
    print(
        json.dumps(
            {
                "months": months,
                "dataFrom": first,
                "suppliers": len({r[TEMPLATE["name"]] for r in rows}),
                "rows": len(rows),
                "split": sum(1 for r in rows if r["Poznámka"].startswith("rozděleno")),
                "unclear": [r[TEMPLATE["name"]] for r in rows if r["Poznámka"].startswith("až")],
                "check": [
                    {"name": r[TEMPLATE["name"]], "keyword": r[TEMPLATE["keyword"]], "note": r["Poznámka"]}
                    for r in rows
                    if any(w in r["Poznámka"] for w in ("ověřte částku", "různými IČ"))
                ],
                "withoutDate": skipped.get("bez data", 0),
                "detailIds": sorted({r["_detailId"] for r in rows if r["_detailId"]}),
                "warning": warn,
            },
            ensure_ascii=False,
        )
    )


def added_rows(res, docs, details, with_vat, list_rows=()):
    """Template rows for the review items "Pravidelný dodavatel mimo seznam" of a match result."""
    months = res["historyMonths"] + [res["period"]]
    field = res["dateField"]
    groups, ic_note, seen, _ = counted_groups(docs, months, field)
    by_id = {d.get("id"): d for d in details or []}
    out, done = [], set()
    for x in res["review"]:
        if x["kind"] != "Pravidelný dodavatel mimo seznam":
            continue
        key = next((k for k, g in groups.items() if any(d["id"] == x.get("id") for d in g)), None)
        if key is None or key in done:
            continue
        done.add(key)
        # merging by name may pull in invoices of a supplier already on the list (IČ typo)
        g = [d for d in groups[key] if not any(same_supplier(r, d) for r in list_rows)]
        if not g:
            continue
        rows = supplier_rows(g, months, coverage(months, seen), field, with_vat, "měsíčně", ic_note.get(key, ""))
        for r in rows:
            apply_codes(r, by_id.get(r["_detailId"]))
            out.append(r)
    return out


def write_copy(src, out, profile, rows):
    """Append template rows to a copy of the user's list; -> values that have no column in the list."""
    if os.path.abspath(out) == os.path.abspath(src) or (os.path.exists(out) and os.path.samefile(out, src)):
        raise SystemExit("--out must differ from --xls: the original list is never overwritten.")
    ext = os.path.splitext(src)[1].lower()
    if ext not in (".xlsx", ".xlsm", ".csv"):
        raise SystemExit(f"Cannot write {ext or 'this'} files – save the list as .xlsx or .csv first.")
    cols = profile.get("columns") or TEMPLATE
    source = profile.get("source") or {}
    hr = source.get("headerRow", 1)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from inspect_xls import read_csv, unique_headers

    if ext == ".csv":
        enc, dialect, data = read_csv(src)
        hdr = unique_headers([text(h) for h in data[hr - 1]])
    else:
        from openpyxl import load_workbook

        wb = load_workbook(src, keep_vba=ext == ".xlsm")
        ws = wb[source["sheet"]] if source.get("sheet") in wb.sheetnames else wb.worksheets[0]
        hdr = unique_headers([text(c.value) for c in ws[hr]])
    at = {f: hdr.index(cols[f]) for f in FIELDS if cols.get(f) and cols[f] in hdr}
    unmapped = [
        {"name": r[TEMPLATE["name"]], "field": f, "value": r[TEMPLATE[f]]}
        for r in rows
        for f in FIELDS
        if f not in at and r.get(TEMPLATE[f]) not in (None, "")
    ]
    if ext == ".csv":
        while len(data) > hr and not any(text(v) for v in data[-1]):
            data.pop()
        for r in rows:
            line = [""] * len(hdr)
            for f, i in at.items():
                line[i] = text(r.get(TEMPLATE[f]))
            data.append(line)
        with open(out, "w", encoding=enc, errors="replace", newline="") as fh:
            csv.writer(fh, dialect, doublequote=True).writerows(data)
        return unmapped
    last = max((c.row for row in ws.iter_rows(min_row=hr) for c in row if text(c.value)), default=hr)
    for n, r in enumerate(rows, last + 1):
        for f, i in at.items():
            v = r.get(TEMPLATE[f])
            cell = ws.cell(n, i + 1, text(v) if f == "ic" else (None if v == "" else v))
            if f == "ic":
                cell.number_format = "@"
    wb.save(out)
    return unmapped


def cmd_addrows(a):
    profile = {"columns": TEMPLATE} if a.profile == "template" else load_json(a.profile)
    docs, _ = load_docs(a.docs)
    details = load_json(a.details) if a.details else None
    lst = normalize(a.xls, profile)
    rows = added_rows(load_json(a.result), docs, details, bool(profile.get("amountWithVat")), lst["rows"])
    unmapped = write_copy(a.xls, a.out, profile, rows) if rows else []
    print(
        json.dumps(
            {
                "rows": len(rows),
                "out": a.out if rows else None,
                "detailIds": sorted({r["_detailId"] for r in rows if r["_detailId"]}),
                "unmapped": unmapped,
                "notes": [{"name": r[TEMPLATE["name"]], "note": r["Poznámka"]} for r in rows if r["Poznámka"]],
            },
            ensure_ascii=False,
        )
    )


DOC_KEEP = [
    "id",
    "number",
    "partnerName",
    "partnerIC",
    "totalAmount",
    "taxExclusiveAmount",
    "currency",
    "exchangeRate",
    "exchangeRateUnits",
    "vatDate",
    "issueDate",
    "acceptDate",
    "flowStatus",
    "approvalStatus",
    "invoiceType",
    "description",
    "accountCode",
    "removed",
]
DETAIL_KEEP = ["id", "number", "taxExclusiveAmount", "accountCode", "accounting", "lines"]


def slim_register(v):
    return {"code": v.get("code"), "externalId": v.get("externalId")} if isinstance(v, dict) else v


def slim_accounting(acc):
    if not isinstance(acc, dict):
        return acc
    return {k: slim_register(acc.get(k)) for k in ("costCenter", "contract", "project", "activity")}


def slim_doc(d):
    out = {k: d.get(k) for k in DOC_KEEP}
    t = d.get("type") or {}
    out["type"] = {"id": t.get("id"), "kind": t.get("kind")} if isinstance(t, dict) else t
    return out


def slim_detail(d):
    out = {k: d.get(k) for k in DETAIL_KEEP}
    out["accounting"] = slim_accounting(d.get("accounting"))
    out["lines"] = [
        {
            "totalAmount": ln.get("totalAmount"),
            "accountCode": ln.get("accountCode"),
            "accounting": slim_accounting(ln.get("accounting")),
            **{k: slim_register(ln.get(k)) for k in ("costCenter", "contract", "activity")},
        }
        for ln in d.get("lines") or []
    ]
    return out


def cmd_collect(a):
    """Merge saved MCP responses (files written by the tool or by you, unchanged) into one slim file."""
    out = []
    for path in a.inputs:
        raw = load_json(path)
        chunks = raw if isinstance(raw, list) else [raw]
        for c in chunks:
            if a.kind == "details":
                for d in c["items"] if isinstance(c, dict) and "items" in c else [c]:
                    out.append(slim_detail(d))
            elif isinstance(c, dict) and "items" in c:
                out.append(
                    {
                        "items": [slim_doc(d) for d in c["items"]],
                        "totalItems": c.get("totalItems"),
                        "page": c.get("page", 0),
                        "pageSize": c.get("pageSize"),
                    }
                )
            elif isinstance(c, dict):
                out.append({"items": [slim_doc(c)], "totalItems": None, "page": 0})
    dump(out, a.out)
    if a.kind == "details":
        print(json.dumps({"details": len(out)}, ensure_ascii=False))
    else:
        items = len({d.get("id") for c in out for d in c["items"]})
        total = sum(c["totalItems"] or 0 for c in out if c.get("page", 0) == 0)
        print(
            json.dumps(
                {"responses": len(out), "items": items, "totalItems": total, "complete": items >= total},
                ensure_ascii=False,
            )
        )


def selftest():
    def doc(
        i, ic, name, date, base, desc="", status=SENT, cur="CZK", rate=None, kind="TaxInvoice", acc=None, appr="None"
    ):
        return {
            "id": f"d{i}",
            "type": {"id": "t1", "kind": "IncomingInvoice"},
            "number": f"F{i}",
            "partnerIC": ic,
            "partnerName": name,
            "vatDate": date,
            "issueDate": date,
            "taxExclusiveAmount": base,
            "totalAmount": round(base * 1.21, 2),
            "currency": cur,
            "exchangeRate": rate,
            "flowStatus": status,
            "description": desc,
            "invoiceType": kind,
            "accountCode": acc,
            "approvalStatus": appr,
        }

    # months
    assert parse_months("leden, duben, červenec, říjen") == ([1, 4, 7, 10], [])
    assert parse_months("červen, červenec") == ([6, 7], [])
    assert parse_months("cervenec") == ([7], []) and parse_months("čvn, čvc") == ([6, 7], [])
    assert parse_months("březen a květen") == ([3, 5], []) and parse_months("mar, may") == ([3, 5], [])
    assert parse_months("1/4/7/10") == ([1, 4, 7, 10], [])
    assert parse_months("čer") == ([], ["cer"])
    assert parse_frequency("čtvrtletně")[0] == "Q" and parse_amount("cca 5000") == (None, False)
    assert [parse_frequency(v)[0] for v in ("12", "1x ročně", "4x ročně", "3 měsíce", "každý měsíc")] == [
        "Y",
        "Y",
        "Q",
        "Q",
        "M",
    ]
    assert [parse_frequency(v)[0] for v in ("12× ročně", "12krát ročně", "4× ročně")] == ["M", "M", "Q"]
    assert parse_amount("12.500") == (12500.0, True) and parse_amount("0.500") == (0.5, True)
    assert parse_amount("12 500,50 Kč") == (12500.5, True)
    assert norm_name("Realitní správa, s. r. o.") == norm_name("REALITNÍ SPRÁVA s.r.o.")
    with tempfile.TemporaryDirectory() as tmp:
        csv_path = os.path.join(tmp, "list.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("Firma / osoba;IČ;Částka bez DPH\nTOTAL ČR s.r.o.;12345678;1000\n")
            f.write("TotalEnergies Marketing;;2000\nCelkem;;3000\n")
        cols = {"name": "Firma / osoba", "ic": "IČ", "amount": "Částka bez DPH"}
        nl = normalize(csv_path, {"source": {"sheet": "Seznam"}, "columns": cols})
    assert [r["name"] for r in nl["rows"]] == ["TOTAL ČR s.r.o.", "TotalEnergies Marketing"], nl["rows"]
    assert any("„Seznam“" in i["issue"] and "„csv“" in i["issue"] for i in nl["issues"]), nl["issues"]

    base_row = {
        "tolerance": 20,
        "frequency": "M",
        "months": [],
        "costCenter": "",
        "contract": "",
        "project": "",
        "activity": "",
        "account": "",
        "description": "",
        "keyword": "",
        "amount": None,
    }
    rows = [
        {
            **base_row,
            "row": 2,
            "name": "Realitní Správa s.r.o.",
            "ic": "11111111",
            "description": "Nájem",
            "keyword": "nájem",
            "amount": 50000.0,
            "costCenter": "Praha",
        },
        {
            **base_row,
            "row": 3,
            "name": "Realitní Správa s.r.o.",
            "ic": "11111111",
            "description": "Energie",
            "keyword": "energie",
        },
        {**base_row, "row": 4, "name": "Telko a.s.", "ic": "", "amount": 3000.0, "account": "518100"},
        {**base_row, "row": 5, "name": "Audit Plus", "ic": "33333333", "frequency": "Q", "months": [1, 4, 7, 10]},
        {**base_row, "row": 6, "name": "Cloud GmbH", "ic": "", "amount": 10000.0},
        {**base_row, "row": 7, "name": "Nový Nájemce", "ic": "77777777"},
        {**base_row, "row": 8, "name": "Strojírny Hronov", "ic": "44444444", "amount": 7000.0},
    ]
    docs, i = [], 0
    for m in ("2026-07", "2026-08", "2026-09"):
        i += 1
        docs.append(doc(i, "11111111", "Realitní správa, s. r. o.", f"{m}-01", 50000, "Nájem kanceláří", acc="518200"))
        i += 1
        docs.append(doc(i, "11111111", "Realitní správa, s. r. o.", f"{m}-05", 8000 + i, "Energie – záloha"))
        i += 1
        docs.append(doc(i, None, "TELKO a. s.", f"{m}-10", 3100, "Telefony"))
        i += 1
        docs.append(doc(i, None, "Cloud GmbH", f"{m}-02", 400, "Licence", cur="EUR", rate=25))
        i += 1
        docs.append(doc(i, "55555555", "Úklid Novák", f"{m}-20", 6000, "Úklid"))
        i += 1
        docs.append(doc(i, "44444444", "Strojírny Hronov a.s.", f"{m}-11", 7000, "Servis"))
    docs.append(doc(90, "33333333", "Audit Plus s.r.o.", "2026-07-15", 30000, "Audit Q2"))
    docs.append(doc(100, "11111111", "Realitní správa, s. r. o.", "2026-10-05", 9000, "Energie", status="SentToReview"))
    docs.append(doc(101, None, "Telko a.s.", "2026-10-10", 9000, "Telefony + nový tarif"))
    docs.append(doc(102, None, "Cloud GmbH", "2026-10-02", 410, "Licence", cur="EUR", rate=25))
    docs.append(doc(103, "11111111", "Realitní správa, s. r. o.", "2026-10-28", 1000, "Dobropis", kind="CreditNote"))
    docs.append(doc(104, "11111111", "Realitní správa, s. r. o.", "2026-10-29", 50000, "Nájem", kind="Proforma"))
    docs.append(doc(105, "44444441", "Strojírny Hronov a.s.", "2026-10-11", 7000, "Servis"))  # IČ typo
    docs.append(doc(106, "33333333", "Audit Plus s.r.o.", "2026-10-15", 30000, "Audit Q3", appr="Rejected"))
    res = match(
        {"rows": rows, "amountWithVat": False}, docs, "2026-10", "vatDate", 3, "org", today=dt.date(2026, 11, 16)
    )
    missing = {(m["name"], m["keyword"]): m for m in res["missing"]}
    assert set(n for n, _ in missing) == {"Realitní Správa s.r.o.", "Audit Plus", "Nový Nájemce", "Strojírny Hronov"}, (
        missing.keys()
    )
    rent = missing[("Realitní Správa s.r.o.", "nájem")]
    assert rent["amount"] == 50000 and rent["account"] == "518200"
    assert missing[("Audit Plus", "")]["amount"] == 30000
    rec = {x["number"]: x for x in res["received"]}
    assert set(rec) == {"F100", "F101", "F102"}, rec.keys()  # proforma and credit note do not count
    assert rec["F100"]["notInErp"] and rec["F100"]["row"] == 3
    kinds = Counter(x["kind"] for x in res["review"])
    for k in (
        "Částka mimo toleranci",
        "Pravidelný dodavatel mimo seznam",
        "Dohad bez částky",
        "Možná došla pod jiným IČ / názvem",
        "Zamítnutá faktura",
    ):
        assert kinds[k] == 1, (k, kinds)
    assert res["ignored"] == {"dobropis": 1, "zálohová faktura": 1}, res["ignored"]
    assert not res["warnings"], res["warnings"]
    # unfinished month + empty window warnings
    w = match({"rows": rows}, [], "2026-11", "vatDate", 3, "o", today=dt.date(2026, 11, 16))["warnings"]
    assert any("neskončil" in x for x in w) and any("žádné přijaté" in x for x in w)
    # details: split by lines, and missing codes reported only for mapped columns
    res["mappedFields"] = FIELDS
    det = {
        "id": rent.get("detailId"),
        "accounting": {"costCenter": None},
        "accountCode": None,
        "lines": [
            {"totalAmount": 30000, "costCenter": {"code": "Praha"}, "accountCode": "518200"},
            {"totalAmount": 20000, "costCenter": {"code": "Brno"}, "accountCode": "518200"},
        ],
    }
    apply_details(res, [det])
    assert not rent.get("split")  # list gives the cost centre -> list wins, no split
    assert missing.get(("Realitní Správa s.r.o.", "energie")) is None  # energy arrived
    # without codes in the list the accrual is split 60/40 by the lines of the last invoice
    hron = missing[("Strojírny Hronov", "")]
    det2 = {
        "id": hron["detailId"],
        "accounting": {"activity": {"code": "SERVIS"}},
        "accountCode": "511100",
        "lines": [
            {"totalAmount": 4200, "costCenter": {"code": "Praha"}},
            {"totalAmount": 2800, "costCenter": {"code": "Brno"}},
        ],
    }
    apply_details(res, [det2])
    assert [(round(p["share"], 2), p["costCenter"], p["activity"], p["account"]) for p in hron["split"]] == [
        (0.6, "Praha", "SERVIS", "511100"),
        (0.4, "Brno", "SERVIS", "511100"),
    ], hron["split"]
    assert any(x["kind"] == "Chybí účetní údaje" and x["listName"] == "Nový Nájemce" for x in res["review"])
    assert any(x["kind"] == "Chybí účetní údaje" and x["listName"] == "Audit Plus" for x in res["review"])
    # suggest splits rent and energy into two rows with their own account
    sug, _, _ = suggest(docs, "2026-10", 4, "vatDate")
    real = [r for r in sug if r["Firma / osoba"].startswith("Realitní")]
    assert sorted(r["Klíčové slovo"] for r in real) == ["Energie", "Nájem"], real
    assert {r["Klíčové slovo"]: r["Analytický účet"] for r in real}["Nájem"] == "518200"
    # release
    accruals = [
        {
            "xlsRow": 2,
            "name": "Realitní Správa s.r.o.",
            "ic": "11111111",
            "description": "Nájem",
            "keyword": "nájem",
            "amount": 30000.0,
            "listRow": "2",
            "costCenter": "Praha",
            "contract": "",
            "project": "",
            "activity": "",
            "account": "518200",
        },
        {
            "xlsRow": 3,
            "name": "Realitní Správa s.r.o.",
            "ic": "11111111",
            "description": "Nájem",
            "keyword": "nájem",
            "amount": 20000.0,
            "listRow": "2",
            "costCenter": "Brno",
            "contract": "",
            "project": "",
            "activity": "",
            "account": "518200",
        },
        {
            "xlsRow": 4,
            "name": "Audit Plus",
            "ic": "33333333",
            "description": "Audit",
            "keyword": "",
            "amount": 30000.0,
            "listRow": "5",
            "costCenter": "",
            "contract": "",
            "project": "",
            "activity": "",
            "account": "",
        },
    ]
    later = [
        *docs,
        doc(200, "11111111", "Realitní správa, s. r. o.", "2026-10-31", 51000, "Nájem říjen"),
        doc(201, "11111111", "Realitní správa, s. r. o.", "2026-10-31", 2000, "Sleva", kind="CreditNote"),
    ]
    rel = release(accruals, {"rows": rows}, later, "2026-10", "vatDate", "org", {"d201": ["d200"]})
    assert rel["summary"]["release"] == 1 and rel["summary"]["pending"] == 1, rel["summary"]
    r0 = rel["release"][0]
    assert r0["accrual"] == 50000 and r0["diff"] == 1000 and r0["netAmount"] == 49000 and r0["netDiff"] == -1000
    storno = [
        doc(400, "11111111", "Realitní správa, s. r. o.", "2026-11-03", 50000, "Nájem listopad"),
        doc(401, "11111111", "Realitní správa, s. r. o.", "2026-11-04", 50000, "Storno", kind="CreditNote"),
        doc(402, "11111111", "Realitní správa, s. r. o.", "2026-11-05", 8000, "Energie"),
    ]
    rel = release(accruals[:2], {"rows": rows}, storno, "2026-11", "vatDate", "org")
    assert not rel["release"] and rel["summary"]["pending"] == 1, rel
    assert "stornována" in rel["pending"][0]["note"], rel["pending"]
    # confirmed pairing: the IČ-typo invoice F105 belongs to row 8 -> arrived, no "maybe" review
    res2 = match(
        {"rows": rows, "amountWithVat": False},
        docs,
        "2026-10",
        "vatDate",
        3,
        "org",
        today=dt.date(2026, 11, 16),
        confirms=[{"row": 8, "document": "F105"}],
    )
    assert "F105" in {x["number"] for x in res2["received"]}
    assert not any(x["kind"].startswith("Možná došla") for x in res2["review"])
    assert "Strojírny Hronov" not in {m["name"] for m in res2["missing"]}
    bad = match(
        {"rows": rows},
        docs,
        "2026-10",
        "vatDate",
        3,
        "o",
        today=dt.date(2026, 11, 16),
        confirms=[{"row": 99, "document": "F105"}],
    )["warnings"]
    assert any("potvrzené spárování" in w for w in bad), bad
    # suggest: storno + replacement, outlier, foreign currency, IČ typo
    s_docs = []
    for j, m in enumerate(("2026-07", "2026-08", "2026-09", "2026-10")):
        s_docs.append(doc(300 + j, "66666666", "Úklid Plus s.r.o.", f"{m}-28", 9500, "Úklid"))
        s_docs.append(doc(310 + j, "88888888", "IT Pro s.r.o.", f"{m}-10", 31000 if m == "2026-10" else 18000, "IT"))
        s_docs.append(doc(320 + j, None, "Soft GmbH", f"{m}-02", 1200, "Licence", cur="EUR", rate=25))
    s_docs.append(doc(330, "66666666", "Úklid Plus s.r.o.", "2026-09-29", 9500, "Storno", kind="CreditNote"))
    s_docs.append(doc(331, "66666666", "Úklid Plus s.r.o.", "2026-09-30", 12000, "Úklid"))
    s_docs.append(doc(340, "99999999", "Bilance Audit s.r.o.", "2026-07-15", 45000, "Účetnictví Q2"))
    s_docs.append(doc(341, "99999969", "Bilance Audit s.r.o.", "2026-10-15", 45000, "Účetnictví Q3"))
    sug, _, _ = suggest(s_docs, "2026-10", 6, "vatDate")
    by = {r["Firma / osoba"]: r for r in sug}
    assert by["Úklid Plus s.r.o."]["Částka bez DPH"] == 9500 and not by["Úklid Plus s.r.o."]["Poznámka"].startswith(
        "až"
    ), by["Úklid Plus s.r.o."]
    assert by["IT Pro s.r.o."]["Částka bez DPH"] == 18000 and "ověřte částku" in by["IT Pro s.r.o."]["Poznámka"]
    assert "EUR" in by["Soft GmbH"]["Poznámka"] and by["Soft GmbH"]["Částka bez DPH"] == 30000
    bil = by["Bilance Audit s.r.o."]
    assert bil["Frekvence"] == "čtvrtletně" and "různými IČ" in bil["Poznámka"], bil
    assert cancelled_ids(s_docs, "vatDate") == {"d302"}
    scratch = tempfile.TemporaryDirectory()
    # release reads accruals files with the old and the new row header
    for hdr in (HDR_LIST_ROW, OLD_HDR_LIST_ROW):
        p = os.path.join(scratch.name, "dohady.csv")
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"Firma / osoba;IČ;Částka CZK bez DPH;{hdr}\nNájem s.r.o.;12345678;1000;4\nX;1;1;1\n")
        assert read_accruals(p)[0]["listRow"] == "4", hdr
    # Došlé / Ke kontrole amounts follow the list's VAT basis
    r = {"taxExclusiveAmount": 1000, "totalAmount": 1210}
    assert report_amount(r, False) == 1000 and report_amount(r, True) == 1210
    assert report_amount({"kind": "Chybí účetní údaje"}, False) is None
    # Mode 2 codes from the latest invoice; a split invoice leaves every code empty
    det_ps = {
        "id": "d400",
        "accounting": {"activity": {"code": "SPRAVA"}},
        "accountCode": "518100",
        "lines": [
            {"totalAmount": 3600, "costCenter": {"code": "Praha"}},
            {"totalAmount": 2400, "costCenter": {"code": "Brno"}},
        ],
    }
    codes, note = invoice_codes(det_ps)
    assert all(v == "" for v in codes.values()) and "Praha 60 %" in note and "Brno 40 %" in note, note
    one = {
        "id": "x",
        "accounting": {"activity": {"code": "SPRAVA"}, "costCenter": {"code": "Praha"}},
        "accountCode": "518100",
        "lines": [],
    }
    assert invoice_codes(one) == (
        {"costCenter": "Praha", "contract": "", "project": "", "activity": "SPRAVA", "account": "518100"},
        "",
    )
    p_docs = [
        doc(410 + j, "12121212", "Parking Servis s.r.o.", f"{m}-05", 6000, "Parkování", acc="518100")
        for j, m in enumerate(("2026-08", "2026-09", "2026-10"))
    ]
    p_docs[-1]["id"] = "d400"
    sug, _, _ = suggest(p_docs, "2026-10", 3, "vatDate", details=[det_ps])
    ps = sug[0]
    assert ps["_detailId"] == "d400"
    assert all(ps[TEMPLATE[f]] == "" for f in ACC_FIELDS) and "rozúčtována" in ps["Poznámka"], ps
    sug1, _, _ = suggest(p_docs, "2026-10", 3, "vatDate", details=[dict(one, id="d400")])
    assert sug1[0][TEMPLATE["costCenter"]] == "Praha" and sug1[0][TEMPLATE["activity"]] == "SPRAVA"
    # the month check splits that row's accrual 60/40 and keeps SPRAVA on both parts
    p = os.path.join(scratch.name, "seznam_ps.csv")
    with open(p, "w", encoding="utf-8") as f:
        f.write(";".join(TEMPLATE.values()) + "\n")
        f.write(";".join(text(ps[h]) for h in TEMPLATE.values()) + "\n")
    lst = normalize(p, {"columns": TEMPLATE})
    res = match(lst, p_docs, "2026-11", "vatDate", 3, "o", today=dt.date(2026, 12, 15))
    apply_details(res, [det_ps])
    split = res["missing"][0]["split"]
    assert [(round(s["share"], 2), s["costCenter"], s["activity"]) for s in split] == [
        (0.6, "Praha", "SPRAVA"),
        (0.4, "Brno", "SPRAVA"),
    ], split
    # addrows: a regular supplier missing from the list goes into a copy of the list
    k_docs = [
        doc(500, "06418273", "Kávový servis Aroma s.r.o.", "2026-07-20", 2400, "Káva", acc="518100"),
        doc(501, "06418273", "Kávový servis Aroma s.r.o.", "2026-09-20", 2400, "Káva", acc="518100"),
    ]
    tmp = scratch.name
    src = os.path.join(tmp, "seznam.csv")
    with open(src, "w", encoding="utf-8") as f:
        f.write("Dodavatel;IČ;Částka\nA s.r.o.;12345678;100\n")
    prof = {"source": {"headerRow": 1}, "columns": {"name": "Dodavatel", "ic": "IČ", "amount": "Částka"}}
    res = match(normalize(src, prof), k_docs, "2026-10", "vatDate", 3, "o", today=dt.date(2026, 11, 15))
    added = added_rows(res, k_docs, None, False)
    assert len(added) == 1, added
    kav = added[0]
    assert kav[TEMPLATE["ic"]] == "06418273" and kav[TEMPLATE["amount"]] == 2400, kav
    assert kav[TEMPLATE["frequency"]] == "měsíčně" and kav[TEMPLATE["account"]] == "518100", kav
    assert kav["_detailId"] == "d501", kav
    with open(src, "rb") as fb:
        before = fb.read()
    out = os.path.join(tmp, "seznam_doplneno.csv")
    unmapped = write_copy(src, out, prof, added)
    with open(src, "rb") as fb:
        assert fb.read() == before
    with open(out, encoding="utf-8") as f:
        assert ";06418273;" in f.read()
    back = normalize(out, prof)["rows"]
    assert len(back) == 2 and back[1]["ic"] == "06418273" and back[1]["amount"] == 2400, back
    assert {"frequency", "account"} <= {u["field"] for u in unmapped}, unmapped
    write_copy(src, out, prof, [dict(kav, **{TEMPLATE["name"]: 'Káva "Aroma" s.r.o.'})])
    assert normalize(out, prof)["rows"][1]["name"] == 'Káva "Aroma" s.r.o.'
    assert added_rows(res, k_docs, None, False, [{"ic": "06418273", "name": ""}]) == []
    # a one-off invoice next to a regular payment is never added as a monthly row
    four = ["2026-07", "2026-08", "2026-09", "2026-10"]
    rent = [doc(600 + j, "11111111", "Nájmy s.r.o.", f"{m}-03", 5000, "Nájem kanceláře") for j, m in enumerate(four)]
    rent.append(doc(610, "11111111", "Nájmy s.r.o.", "2026-10-20", 900, "Vyúčtování energií"))
    assert [r[TEMPLATE["keyword"]] for r in supplier_rows(rent, four, 4, "vatDate", default_freq="měsíčně")] == [
        "Nájem"
    ]
    try:
        write_copy(src, src, prof, added)
        raise AssertionError("write_copy overwrote the original")
    except SystemExit:
        pass
    try:
        import openpyxl
    except ImportError:
        openpyxl = None
    if openpyxl:
        xs = os.path.join(tmp, "seznam.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Seznam"
        ws.append(["Dodavatel", "IČ", "Částka"])
        ws.append(["A s.r.o.", "12345678", 100])
        ws["E2"] = "=C2*2"
        wb.save(xs)
        xout = os.path.join(tmp, "seznam_doplneno.xlsx")
        write_copy(xs, xout, dict(prof, source={"sheet": "Seznam", "headerRow": 1}), added)
        ws = openpyxl.load_workbook(xout)["Seznam"]
        assert ws["B3"].value == "06418273" and ws["B3"].number_format == "@", ws["B3"].value
        assert ws["E2"].value == "=C2*2" and ws["A3"].value == "Kávový servis Aroma s.r.o."
    scratch.cleanup()
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("normalize")
    p.add_argument("--xls", required=True)
    p.add_argument("--profile", required=True, help="profile JSON or 'template'")
    p.add_argument("--out", required=True)
    p = sub.add_parser("match")
    p.add_argument("--list", required=True)
    p.add_argument("--docs", required=True)
    p.add_argument("--period", required=True)
    p.add_argument("--date-field", default="vatDate", choices=["vatDate", "acceptDate"])
    p.add_argument("--history", type=int, default=3)
    p.add_argument("--window-start")
    p.add_argument("--org", default="")
    p.add_argument("--out", required=True)
    p.add_argument("--confirm", help='JSON [{"row": 9, "document": "<number or id>"}] – pairings the user confirmed')
    p = sub.add_parser("release")
    p.add_argument("--accruals", required=True)
    p.add_argument("--list")
    p.add_argument("--docs", required=True)
    p.add_argument("--period", required=True)
    p.add_argument("--date-field", default="vatDate", choices=["vatDate", "acceptDate"])
    p.add_argument("--links")
    p.add_argument("--org", default="")
    p.add_argument("--out", required=True)
    p = sub.add_parser("report")
    p.add_argument("--result", required=True)
    p.add_argument("--details")
    p.add_argument("--release")
    p.add_argument("--out", required=True)
    p = sub.add_parser("suggest")
    p.add_argument("--docs", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--months", type=int, default=6)
    p.add_argument("--date-field", default="vatDate", choices=["vatDate", "acceptDate"])
    p.add_argument("--details", help="get_document responses for the printed detailIds (collect --kind details)")
    p.add_argument("--out", required=True)
    p = sub.add_parser("addrows")
    p.add_argument("--xls", required=True)
    p.add_argument("--profile", required=True, help="profile JSON or 'template'")
    p.add_argument("--result", required=True)
    p.add_argument("--docs", required=True)
    p.add_argument("--details", help="get_document responses for the printed detailIds (collect --kind details)")
    p.add_argument("--out", required=True)
    p = sub.add_parser("collect")
    p.add_argument("inputs", nargs="+")
    p.add_argument("--kind", choices=["docs", "details"], default="docs")
    p.add_argument("--out", required=True)
    sub.add_parser("selftest")
    a = ap.parse_args()
    {
        "normalize": cmd_normalize,
        "match": cmd_match,
        "release": cmd_release,
        "report": cmd_report,
        "suggest": cmd_suggest,
        "addrows": cmd_addrows,
        "collect": cmd_collect,
        "selftest": lambda _: selftest(),
    }[a.cmd](a)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    main()
