"""Optional review of the file's content, run on build_documents.py output.

Usage: python review_xls.py <out.json> [--today YYYY-MM-DD]

Prints JSON: {"file": [...], "invoices": {"<number>": [...]}}
- file: findings about the file as a whole (gaps in the number series, period, dates in the
  future, cut-off export…) - the skill asks about each one separately
- invoices: findings per invoice - they join the one-by-one pass like any other issue
Nothing is sent anywhere.
"""

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime

LEGAL_FORM = re.compile(
    r"\b(s\.\s?r\.\s?o\.|spol\.\s?s\s?r\.\s?o\.|a\.\s?s\.|v\.\s?o\.\s?s\.|k\.\s?s\.|z\.\s?s\.|"
    r"o\.\s?p\.\s?s\.|z\.\s?ú\.|SE|GmbH|AG|Ltd|LLC)\b",
    re.IGNORECASE,
)
FOREIGN_VAT = re.compile(r"^[A-Z]{2}[0-9A-Z+*.]{2,13}$")
MAX_GAP_LIST = 15


def d(s):
    return datetime.strptime(s[:10], "%Y-%m-%d").date() if s else None


def ic_valid(ic):
    if not re.fullmatch(r"\d{8}", ic):
        return False
    a = sum(int(ic[i]) * (8 - i) for i in range(7))
    return (11 - a % 11) % 10 == int(ic[7])


def birth_number_valid(n):
    """10-digit Czech birth number: divisible by 11 (older rule: first 9 mod 11 == 10 and last digit 0)."""
    if len(n) != 10:
        return True  # 9-digit numbers (before 1954) have no check digit
    if int(n) % 11 == 0:
        return True
    return int(n[:9]) % 11 == 10 and n[9] == "0"


def series_gaps(numbers):
    """Group numbers by everything except the trailing digits; report missing numbers inside each group."""
    groups = defaultdict(list)
    for n in numbers:
        m = re.match(r"^(.*?)(\d+)$", n)
        if m:
            groups[m.group(1)].append((int(m.group(2)), len(m.group(2))))
    found = []
    for prefix, vals in groups.items():
        if len(vals) < 2:
            continue
        nums = sorted({v for v, _ in vals})
        width = max(w for _, w in vals)

        def fmt(i, prefix=prefix, width=width):
            return f"{prefix}{str(i).zfill(width)}"

        # a jump much larger than the file is not a missing invoice but another period / sub-series
        jump = max(10, len(nums))
        segments, cur = [], [nums[0]]
        for a, b in zip(nums[:-1], nums[1:]):
            if b - a > jump:
                segments.append(cur)
                cur = []
            cur.append(b)
        segments.append(cur)
        main = max(segments, key=len)
        for seg in segments:
            if seg is not main:
                found.append(
                    f"series {prefix or '(numeric)'}: {', '.join(fmt(i) for i in seg)} lies outside the continuous series "
                    f"{fmt(main[0])}-{fmt(main[-1])} (another period or another series?)"
                )
        for seg in segments:
            missing = [fmt(i) for a, b in zip(seg[:-1], seg[1:]) for i in range(a + 1, b)]
            if missing:
                shown = ", ".join(missing[:MAX_GAP_LIST]) + (
                    f" … (+{len(missing) - MAX_GAP_LIST})" if len(missing) > MAX_GAP_LIST else ""
                )
                found.append(
                    f"series {prefix or '(numeric)'}: {len(missing)} number{'s' * (len(missing) != 1)} missing between {fmt(seg[0])} "
                    f"and {fmt(seg[-1])} - {shown}"
                )
    return found


def main(path, today):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    docs = data["documents"]
    file_f, inv_f = [], defaultdict(list)

    # 1. number series without gaps
    # rows left out (already in wflow, user's choice) are still in the series
    left_out = [r["number"] for r in data.get("skippedRows", []) if r.get("number")]
    file_f += series_gaps([x["number"] for x in docs if x["number"]] + left_out)

    # 2. period: main month of the file, invoices outside it, dates in the future
    months = Counter(x["payload"].get("issueDate", "")[:7] for x in docs if x["payload"].get("issueDate"))
    if months:
        main_month, cnt = months.most_common(1)[0]
        others = [x["number"] for x in docs if x["payload"].get("issueDate", "")[:7] not in ("", main_month)]
        if others and cnt >= len(docs) / 2:
            file_f.append(f"most invoices are from {main_month}, outside this period: {', '.join(others)}")
    # dates in the future - one finding for the whole file, not one per invoice
    future = [
        x["number"] or f"row {x['rows'][0]}"
        for x in docs
        if any(x["payload"].get(k) and d(x["payload"][k]) > today for k in ("issueDate", "vatDate"))
    ]
    if future:
        file_f.append(
            f"{len(future)} of {len(docs)} invoices have an issue date or VAT date after today "
            f"({today:%Y-%m-%d}): {', '.join(future)}"
        )
    for x in docs:
        p, n = x["payload"], x["number"] or f"row {x['rows'][0]}"

        # 3. issued more than 15 days after the VAT date (tax documents only)
        if x["invoiceType"] != "Proforma" and p.get("issueDate") and p.get("vatDate"):
            lag = (d(p["issueDate"]) - d(p["vatDate"])).days
            if lag > 15:
                inv_f[n].append(f"issued {lag} days after the VAT date (the legal limit is 15 days)")

        # 4. company ID (IČ) / VAT ID (DIČ)
        ic, dic = p.get("partnerIC"), (p.get("partnerVAT") or "").replace(" ", "").upper()
        if ic and not ic_valid(ic):
            inv_f[n].append(f"company ID {ic} has an invalid checksum")
        if dic.startswith("CZ"):
            digits = dic[2:]
            if not re.fullmatch(r"\d{8,10}", digits):
                inv_f[n].append(f"VAT ID {dic} has an invalid format (CZ + 8-10 digits)")
            elif len(digits) == 8:  # legal person: VAT ID = CZ + company ID
                if ic and digits != ic:
                    inv_f[n].append(f"VAT ID {dic} does not match company ID {ic} (a legal person has CZ + company ID)")
            else:  # 9-10 digits = birth number → natural person / sole trader
                if not birth_number_valid(digits):
                    inv_f[n].append(f"VAT ID {dic} (birth number) has an invalid checksum")
                if LEGAL_FORM.search(p.get("partnerName") or ""):
                    inv_f[n].append(
                        f'VAT ID {dic} has the form of a natural person, but the name "{p["partnerName"]}" '
                        "looks like a company"
                    )
        elif dic and not FOREIGN_VAT.match(dic):
            inv_f[n].append(f"VAT ID {dic} has an invalid format")

        # 5. VAT = base x rate for each rate
        for v in p.get("vaTs", []):
            expected = round(v["base"] * v["rate"] / 100, 2)
            if abs(v["tax"] - expected) > 1:
                inv_f[n].append(
                    f"VAT {v['rate']} %: {v['tax']} does not match the base {v['base']} (expected {expected})"
                )

        # 6. zero amount
        if x["totalAmount"] == 0:
            inv_f[n].append("the invoice has a zero amount")

        # 7. foreign customer with Czech VAT
        if dic and not dic.startswith("CZ") and any(v["tax"] for v in p.get("vaTs", [])):
            inv_f[n].append(f"foreign customer ({dic[:2]}) with Czech VAT - check the supply mode")

    # 8. customers: same name with different company IDs, same company ID with different names
    by_ic, by_name = defaultdict(set), defaultdict(set)
    shown_name: dict[str, str] = {}
    for x in docs:
        p = x["payload"]
        key = re.sub(r"\s+", " ", (p.get("partnerName") or "").strip().lower())
        if p.get("partnerIC") and key:
            by_ic[p["partnerIC"]].add(p["partnerName"].strip())
            by_name[key].add(p["partnerIC"])
            shown_name.setdefault(key, p["partnerName"].strip())
    for ic, names in by_ic.items():
        if len(names) > 1:
            file_f.append(f"company ID {ic} has several names in the file: {', '.join(sorted(names))}")
    for key, ics in by_name.items():
        if len(ics) > 1:
            file_f.append(f'customer "{shown_name[key]}" has several company IDs in the file: {", ".join(sorted(ics))}')

    # 9. totals row equals the sum of the invoices (export not cut off)
    currencies = {x["currency"] for x in docs}
    for s in data.get("summaryRows", []):
        if s.get("total") not in (None, "ERR") and len(currencies) == 1:
            # rows left out (duplicates, user's choice) are still part of the file's own total
            total = round(
                sum(x["totalAmount"] or 0 for x in docs) + sum(r["total"] or 0 for r in data.get("skippedRows", [])), 2
            )
            if abs(total - s["total"]) > 1:
                file_f.append(
                    f"totals row {s['row']} ({s['total']}) does not match the sum of the invoices ({total}) - "
                    "the export may be incomplete"
                )
        elif s.get("total") not in (None, "ERR"):
            file_f.append(f"totals row {s['row']} cannot be checked - the invoices are in several currencies")

    # an invoice twice in the file would report everything twice
    unique = {n: list(dict.fromkeys(msgs)) for n, msgs in inv_f.items()}
    print(json.dumps({"file": file_f, "invoices": unique}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    args = sys.argv[1:]
    today = date.today()
    if "--today" in args:
        i = args.index("--today")
        today = d(args[i + 1])
        del args[i : i + 2]
    if len(args) != 1:
        raise SystemExit(__doc__)
    main(args[0], today)
