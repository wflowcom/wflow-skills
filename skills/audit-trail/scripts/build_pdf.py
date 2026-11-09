from __future__ import annotations

import argparse
import io
import json
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from event_labels import label_for, unverified_types_in
from property_labels import SUPPRESSED_KEYS, label_for_array, label_for_invoice_type, label_for_property
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ATTACHMENT_PREFIX = "Auditni_stopa"

# ReportLab's built-in Helvetica cannot render č/ř/ě/ů, so use a TTF the OS already ships.
SYSTEM_FONTS = [
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    (
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ),
    (
        "/usr/share/fonts/liberation-sans/LiberationSans-Regular.ttf",
        "/usr/share/fonts/liberation-sans/LiberationSans-Bold.ttf",
    ),
]


def _register_system_font() -> None:
    for regular, bold in SYSTEM_FONTS:
        if Path(regular).is_file() and Path(bold).is_file():
            pdfmetrics.registerFont(TTFont("AuditSans", regular))
            pdfmetrics.registerFont(TTFont("AuditSans-Bold", bold))
            return
    sys.exit("No system font with Czech diacritics found (Arial, DejaVu Sans or Liberation Sans).")


_register_system_font()
FONT_REGULAR, FONT_BOLD, FONT_ITALIC = "AuditSans", "AuditSans-Bold", "AuditSans"

_STYLES = getSampleStyleSheet()

_STYLE_TITLE = ParagraphStyle("AuditTitle", parent=_STYLES["Title"], fontName=FONT_BOLD, fontSize=16, spaceAfter=2 * mm)
_STYLE_SUBTITLE = ParagraphStyle(
    "AuditSubtitle", parent=_STYLES["Normal"], fontName=FONT_REGULAR, fontSize=9, textColor=colors.grey
)
_STYLE_HEADER_LABEL = ParagraphStyle(
    "HeaderLabel", parent=_STYLES["Normal"], fontName=FONT_REGULAR, fontSize=9, textColor=colors.grey
)
_STYLE_HEADER_VALUE = ParagraphStyle("HeaderValue", parent=_STYLES["Normal"], fontSize=10, fontName=FONT_BOLD)
_STYLE_EVENT_TYPE = ParagraphStyle("EventType", parent=_STYLES["Normal"], fontSize=10.5, fontName=FONT_BOLD)
_STYLE_EVENT_ACTOR = ParagraphStyle(
    "EventActor",
    parent=_STYLES["Normal"],
    fontSize=9.5,
    fontName=FONT_BOLD,
    textColor=colors.HexColor("#1a1a1a"),
)
_STYLE_EVENT_TIME = ParagraphStyle(
    "EventTime",
    parent=_STYLES["Normal"],
    fontName=FONT_REGULAR,
    fontSize=9,
    textColor=colors.grey,
    alignment=2,  # right
)
_STYLE_EVENT_DETAIL = ParagraphStyle(
    "EventDetail",
    parent=_STYLES["Normal"],
    fontName=FONT_REGULAR,
    fontSize=9,
    textColor=colors.HexColor("#333333"),
    leftIndent=2 * mm,
)
_STYLE_UNVERIFIED_NOTE = ParagraphStyle(
    "UnverifiedNote",
    parent=_STYLES["Normal"],
    fontSize=7.5,
    textColor=colors.HexColor("#b45309"),
    fontName=FONT_ITALIC,
)


def _fmt_datetime(iso_str: str | None) -> str:
    """ISO 8601 → 'DD.MM.YYYY HH:MM', the format the UI uses."""
    if not iso_str:
        return "-"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return iso_str


def _fmt_actor(identity: dict | None) -> str:
    """fullName, else login, else '(neznámý)'. System actors (wflow automation, ERP
    connectors) have only `login`."""
    if not identity:
        return "(neznámý)"
    full_name = (identity.get("fullName") or "").strip()
    if full_name:
        return full_name
    login = (identity.get("login") or "").strip()
    return login or "(neznámý)"


def _try_parse_json(info: Any) -> Any:
    if isinstance(info, str):
        try:
            return json.loads(info)
        except (json.JSONDecodeError, ValueError):
            return None
    return info if isinstance(info, (dict, list)) else None


def _fmt_value(value: Any) -> str:
    if value in (None, ""):
        return "-/-"
    if isinstance(value, bool):
        return "Ano" if value else "Ne"
    if value in ("True", "False"):
        return "Ano" if value == "True" else "Ne"
    if isinstance(value, float):
        return f"{value:,.2f}".replace(",", " ")
    return str(value)


def _typed_info_lines(event_type: str, parsed: dict) -> list[str] | None:
    if event_type in ("TaskAdded", "TaskProcessed"):
        message = parsed.get("message")
        return [str(message)] if message else []

    if event_type in ("FileAdded", "FileDeleted", "SetMainFile"):
        name = parsed.get("name")
        return [str(name)] if name else []

    if event_type in ("Approved", "Returned") and "processed" in parsed and "total" in parsed:
        return [f"{parsed['processed']}/{parsed['total']}"]

    if event_type in ("SetDocumentApprovals", "ChangeDocumentApprovals"):
        steps = [f"{a.get('level')}. {a.get('name')}" for a in parsed.get("approvals") or [] if isinstance(a, dict)]
        name = parsed.get("name")
        return steps + ([str(name)] if name else [])

    return None


def _render_info_lines(event_type: str, info: Any, unverified: set[str] | None = None) -> list[str]:
    parsed = _try_parse_json(info)
    if parsed is None:
        return [str(info)] if info else []

    if isinstance(parsed, list):
        return [str(v) for v in parsed]
    if not isinstance(parsed, dict):
        return [str(parsed)]

    typed = _typed_info_lines(event_type, parsed)
    if typed is not None:
        return typed

    fields = parsed.get("changedProperties", parsed)
    if not isinstance(fields, dict):
        return [str(parsed)]

    lines: list[str] = []
    for key, value in fields.items():
        if key in SUPPRESSED_KEYS:
            continue
        if isinstance(value, list):
            label, verified = label_for_array(key)
            tag = "" if verified else f" [{key}]"
            lines.append(f"{label}{tag}: {len(value)}")
        elif isinstance(value, dict):
            label, verified = label_for_property(key)
            tag = "" if verified else (f" [{key}]" if label != key else "")
            lines.append(f"{label}{tag}: (objekt, {len(value)} polí)")
        elif key == "invoiceType":
            label, label_verified = label_for_property(key)
            value_label, value_verified = label_for_invoice_type(value)
            verified = label_verified and value_verified
            tag = "" if verified else f" [{key}={value!r}]"
            lines.append(f"{label}{tag}: {value_label}")
        else:
            label, verified = label_for_property(key)
            tag = "" if verified else (f" [{key}]" if label != key else "")
            lines.append(f"{label}{tag}: {_fmt_value(value)}")
        if not verified and unverified is not None:
            unverified.add(key)
    return lines


def unverified_properties_in(events: list[dict]) -> set[str]:
    found: set[str] = set()
    for event in events:
        _render_info_lines(event.get("type", ""), event.get("info"), found)
    return found


def sanitize_for_filename(value: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "-", value).strip("-") or "bez-cisla"


def attachment_name(number: str, mode: str, files: list[dict], now: datetime) -> str | None:
    base = f"{ATTACHMENT_PREFIX}_{sanitize_for_filename(str(number))}"
    lowered = base.lower()
    names = [(f.get("name") or "").lower() for f in files]
    exists = any(n == f"{lowered}.pdf" or n.startswith(f"{lowered}_") for n in names)
    if exists and mode == "skip":
        return None
    suffix = f"_{now:%Y%m%d_%H%M}" if mode == "version" else ""
    return f"{base}{suffix}.pdf"


def _header_table(document: dict, organization: str, generated_at: datetime) -> Table:
    def row(label: str, value: Any) -> list[Paragraph]:
        return [
            Paragraph(escape(label), _STYLE_HEADER_LABEL),
            Paragraph(escape(str(value)) if value not in (None, "") else "-", _STYLE_HEADER_VALUE),
        ]

    number = document.get("number") or document.get("internalCode") or "-"
    partner = document.get("partnerName") or "-"
    amount = document.get("totalAmount")
    currency = document.get("currency") or ""
    amount_str = f"{amount:,.2f} {currency}".replace(",", " ") if amount is not None else "-"
    issue_date = _fmt_datetime(document.get("issueDate"))
    due_date = _fmt_datetime(document.get("dueDate"))
    flow_status = document.get("flowStatus") or "-"

    data = [
        row("Organizace", organization),
        row("Číslo dokladu", number),
        row("Dodavatel", partner),
        row("Celková částka", amount_str),
        row("Datum vystavení", issue_date),
        row("Datum splatnosti", due_date),
        row("Stav zpracování (flowStatus)", flow_status),
        row("Report vygenerován", generated_at.strftime("%d.%m.%Y %H:%M")),
    ]
    table = Table(data, colWidths=[55 * mm, 120 * mm])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 1.5 * mm),
            ]
        )
    )
    return table


def _event_block(event: dict) -> list:
    """Flowables for one event: a (type + actor | time) row, then the detail lines."""
    label, verified = label_for(event.get("type", ""))
    actor = _fmt_actor(event.get("identity"))
    timestamp = _fmt_datetime(event.get("created"))

    left = [Paragraph(escape(label), _STYLE_EVENT_TYPE), Paragraph(escape(actor), _STYLE_EVENT_ACTOR)]
    if not verified:
        left.append(
            Paragraph(
                escape(f"(typ „{event.get('type')}“ — český popisek není ověřený vůči UI, zkontroluj)"),
                _STYLE_UNVERIFIED_NOTE,
            )
        )

    header_table = Table(
        [[left, Paragraph(escape(timestamp), _STYLE_EVENT_TIME)]],
        colWidths=[140 * mm, 35 * mm],
    )
    header_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

    flowables: list = [header_table]
    for line in _render_info_lines(event.get("type", ""), event.get("info")):
        flowables.append(Paragraph(escape(line), _STYLE_EVENT_DETAIL))
    flowables.append(Spacer(1, 1.5 * mm))
    flowables.append(HRFlowable(width="100%", thickness=0.4, color=colors.HexColor("#cccccc")))
    flowables.append(Spacer(1, 2 * mm))
    return flowables


def build_audit_pdf(
    document: dict,
    events: list[dict],
    *,
    organization: str,
    generated_at: datetime | None = None,
) -> bytes:
    """Build the audit-trail PDF for one document and return its bytes.

    Events are sorted newest first, like the Events panel in the UI, whatever order the server returned.
    """
    generated_at = generated_at or datetime.now()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=15 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        title=f"Auditní stopa — {document.get('number', '')}",
    )

    sorted_events = sorted(events, key=lambda e: e.get("created") or "", reverse=True)

    story: list = [
        Paragraph("Auditní stopa dokladu", _STYLE_TITLE),
        Paragraph(
            "Chronologický přehled událostí (od nejnovější) — vygenerováno nástrojem "
            "wflow-audit-trail z wflow.com (wflow MCP).",
            _STYLE_SUBTITLE,
        ),
        Spacer(1, 4 * mm),
        _header_table(document, organization, generated_at),
        Spacer(1, 6 * mm),
        Paragraph(f"Události ({len(sorted_events)})", _STYLE_EVENT_TYPE),
        Spacer(1, 2 * mm),
    ]
    for event in sorted_events:
        story.extend(_event_block(event))

    if not sorted_events:
        story.append(Paragraph("Pro tento doklad nebyly nalezeny žádné události.", _STYLE_EVENT_DETAIL))

    doc.build(story)
    return buf.getvalue()


def _sample_events() -> list[dict]:
    return [
        {
            "type": "Create",
            "created": "2026-09-01T08:00:00Z",
            "identity": {"fullName": "Jana Nová"},
            "info": json.dumps(
                {
                    "changedProperties": {"partnerName": "Žluťoučký kůň s.r.o.", "zzUnknownField": 1, "vats": [1, 2]},
                    "status": 0,
                }
            ),
        },
        {
            "type": "TaskAdded",
            "created": "2026-09-02T08:00:00Z",
            "identity": {"login": "automation@company.com"},
            "info": json.dumps({"status": 3, "message": "Please approve"}),
        },
        {
            "type": "FileAdded",
            "created": "2026-09-03T08:00:00Z",
            "identity": None,
            "info": json.dumps({"name": "invoice.pdf"}),
        },
        {"type": "Locked", "created": "2026-09-04T08:00:00Z", "identity": {"fullName": "Petr Říha"}},
        {"type": "UnknownType", "created": "2026-09-05T08:00:00Z", "identity": {}, "info": "plain text, not JSON"},
    ]


def _self_check() -> None:
    found: set[str] = set()
    lines = _render_info_lines(
        "Update", json.dumps({"changedProperties": {"partnerName": "Žluťoučký kůň", "zzX": "a", "status": 1}}), found
    )
    assert any("Žluťoučký kůň" in line for line in lines)
    assert not any(line.startswith("status") for line in lines)
    assert found == {"zzX"}
    assert _render_info_lines("TaskAdded", json.dumps({"status": 2, "message": "ok"})) == ["ok"]
    assert _render_info_lines("FileAdded", {"name": "a.pdf"}) == ["a.pdf"]
    assert _render_info_lines("Update", "not json") == ["not json"]
    assert _render_info_lines("Locked", None) == []
    quiet: set[str] = set()
    assert _render_info_lines("Approved", json.dumps({"status": 0, "processed": 2, "total": 4}), quiet) == ["2/4"]
    approvals = {
        "name": "Approval",
        "approvals": [
            {"level": 1, "name": "Marketing"},
            {"level": 1, "name": "Sales"},
            {"level": 2, "name": "Director"},
        ],
    }
    assert _render_info_lines("ChangeDocumentApprovals", json.dumps(approvals), quiet) == [
        "1. Marketing",
        "1. Sales",
        "2. Director",
        "Approval",
    ]
    assert _render_info_lines(
        "Update", json.dumps({"changedProperties": {"invoiceType": "0", "doNotPay": "False"}}), quiet
    ) == ["Typ faktury: Daňový doklad", "Neproplácet: Ne"]
    assert quiet == set()

    events = _sample_events()
    assert unverified_types_in(events) == {"UnknownType"}
    assert unverified_properties_in(events) == {"zzUnknownField"}

    now = datetime(2026, 9, 30, 14, 5)
    assert sanitize_for_filename("2026/001") == "2026-001"
    assert sanitize_for_filename("///") == "bez-cisla"
    assert attachment_name("2026/001", "skip", [], now) == "Auditni_stopa_2026-001.pdf"
    assert attachment_name("2026/001", "skip", [{"name": "AUDITNI_STOPA_2026-001.PDF"}], now) is None
    assert attachment_name("VF1", "skip", [{"name": "Auditni_stopa_VF10.pdf"}], now) == "Auditni_stopa_VF1.pdf"
    assert attachment_name("VF1", "skip", [{"name": "Auditni_stopa_VF1_20260101_0800.pdf"}], now) is None
    assert (
        attachment_name("VF1", "version", [{"name": "Auditni_stopa_VF1.pdf"}], now)
        == "Auditni_stopa_VF1_20260930_1405.pdf"
    )

    document = {
        "number": "VF-č.1",
        "partnerName": "Supplier ěščřžýáíé",
        "totalAmount": 1210.5,
        "currency": "CZK",
        "issueDate": "2026-09-01T00:00:00Z",
        "flowStatus": "SentToERP",
    }
    pdf = build_audit_pdf(document, events, organization="demo-test", generated_at=now)
    assert pdf.startswith(b"%PDF")
    for font in (FONT_REGULAR, FONT_BOLD):
        glyphs = pdfmetrics.getFont(font).face.charToGlyph
        assert all(ord(c) in glyphs for c in "ěščřžýáíéůúňťďĚŠČŘŽÝÁÍÉŮÚŇŤĎ"), font
    tricky = [
        {
            "type": "TaskAdded",
            "created": "2026-09-06T08:00:00Z",
            "identity": {"fullName": "A <b>"},
            "info": json.dumps({"message": "price <abc & d>"}),
        },
        {"type": "Update", "created": "2026-09-07T08:00:00Z", "identity": {}, "info": "price <abc"},
    ]
    assert build_audit_pdf({**document, "partnerName": "A<B"}, tricky, organization="o<", generated_at=now).startswith(
        b"%PDF"
    )
    assert Paragraph(escape("price <abc & d>"), _STYLE_EVENT_DETAIL).getPlainText() == "price <abc & d>"
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "a.pdf"
        out.write_bytes(pdf)
        assert out.stat().st_size > 1000
    print("self-check OK")


def _load_list(path: str, key: str | None = None) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if key is not None:
        data = data.get(key)
    if isinstance(data, dict):
        data = data.get("items")
    return data or []


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="build_pdf.py")
    parser.add_argument("--self-check", action="store_true")
    sub = parser.add_subparsers(dest="cmd")
    r = sub.add_parser("render")
    r.add_argument("input")
    r.add_argument("output")
    n = sub.add_parser("name")
    n.add_argument("--number", default="")
    n.add_argument("--id", default="")
    n.add_argument("--mode", choices=["skip", "version"], required=True)
    n.add_argument("--files", required=True)
    args = parser.parse_args(argv)

    if args.self_check:
        _self_check()
    elif args.cmd == "render":
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
        events = _load_list(args.input, "events")
        pdf = build_audit_pdf(payload["document"], events, organization=payload["org"])
        Path(args.output).write_bytes(pdf)
        print(
            json.dumps(
                {
                    "events": len(events),
                    "bytes": len(pdf),
                    "unverifiedTypes": sorted(unverified_types_in(events)),
                    "unverifiedProperties": sorted(unverified_properties_in(events)),
                },
                ensure_ascii=False,
            )
        )
    elif args.cmd == "name":
        number = args.number or args.id
        if not number:
            sys.exit("Both --number and --id are missing")
        result = attachment_name(number, args.mode, _load_list(args.files), datetime.now())
        print(result or "SKIP")
    else:
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv[1:])
