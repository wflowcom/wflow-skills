from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

STATUSES = ("generated", "skipped_exists", "error")
DATE_FIELDS = ("issueDate", "vatDate", "caseDate")


def parse_dmy_date(raw: str) -> date:
    return datetime.strptime(raw.strip(), "%d.%m.%Y").date()


def in_scope(
    doc: dict, flow_status: str | None, date_from: date | None, date_to: date | None, date_field: str = "issueDate"
) -> bool:
    if flow_status and doc.get("flowStatus") != flow_status:
        return False
    if date_from or date_to:
        raw = doc.get(date_field)
        if not raw:
            return False
        try:
            issued = date.fromisoformat(str(raw)[:10])
        except ValueError:
            return False
        if date_from and issued < date_from:
            return False
        if date_to and issued > date_to:
            return False
    return True


def split_docs(
    docs: list[dict],
    size: int,
    flow_status: str | None,
    date_from: date | None,
    date_to: date | None,
    date_field: str = "issueDate",
) -> list[list[dict]]:
    kept = [
        {"id": d["id"], "number": d.get("number") or d["id"]}
        for d in docs
        if in_scope(d, flow_status, date_from, date_to, date_field)
    ]
    return [kept[i : i + size] for i in range(0, len(kept), size)]


def missing_date(docs: list[dict], flow_status: str | None, date_field: str) -> int:
    return sum(1 for d in docs if in_scope(d, flow_status, None, None) and not d.get(date_field))


def append_record(path: Path, record: dict) -> None:
    if record.get("status") not in STATUSES:
        raise ValueError(f"Invalid status: {record.get('status')}")
    line = json.dumps({**record, "timestamp": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()


def merge_results(outdir: Path) -> tuple[list[dict], dict]:
    latest: dict[str, dict] = {}
    malformed = 0
    for path in sorted(outdir.glob("results_*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                latest[rec["id"]] = rec
            except (json.JSONDecodeError, KeyError, TypeError):
                malformed += 1
    expected: list[dict] = []
    for path in sorted(outdir.glob("batch_*.json")):
        expected.extend(json.loads(path.read_text(encoding="utf-8")))
    records = list(latest.values())
    summary: dict = {s: sum(1 for r in records if r.get("status") == s) for s in STATUSES}
    summary["errors"] = [
        {"number": r.get("number"), "error": r.get("error")} for r in records if r.get("status") == "error"
    ]
    summary["unverifiedTypes"] = sorted({t for r in records for t in r.get("unverifiedTypes") or []})
    summary["unverifiedProperties"] = sorted({p for r in records for p in r.get("unverifiedProperties") or []})
    summary["missing"] = [d for d in expected if d["id"] not in latest]
    summary["malformedLines"] = malformed
    return records, summary


def _self_check() -> None:
    d_from, d_to = parse_dmy_date("01.09.2026"), parse_dmy_date("30.09.2026")
    assert d_to == date(2026, 9, 30)
    same_day = {"id": "1", "number": "A", "flowStatus": "SentToERP", "issueDate": "2026-09-30T14:00:00Z"}
    assert in_scope(same_day, "SentToERP", d_from, d_to)
    assert not in_scope({**same_day, "issueDate": "2026-10-01T00:00:00Z"}, "SentToERP", d_from, d_to)
    assert in_scope({**same_day, "issueDate": "2026-09-01"}, "SentToERP", d_from, d_to)
    assert not in_scope({**same_day, "flowStatus": "Approved"}, "SentToERP", None, None)
    assert not in_scope({**same_day, "issueDate": None}, None, d_from, None)
    assert in_scope({**same_day, "issueDate": None}, None, None, None)
    case_only = {**same_day, "issueDate": None, "caseDate": "2026-09-15T00:00:00"}
    assert in_scope(case_only, "SentToERP", d_from, d_to, "caseDate")
    assert not in_scope(case_only, "SentToERP", d_from, d_to)
    assert missing_date([same_day, case_only, {**case_only, "flowStatus": "Approved"}], "SentToERP", "caseDate") == 1
    try:
        parse_dmy_date("2026-09-30")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass

    docs = [{**same_day, "id": str(i), "number": f"N{i}"} for i in range(5)]
    batches = split_docs(docs, 2, "SentToERP", None, None)
    assert [len(b) for b in batches] == [2, 2, 1]
    assert batches[0][0] == {"id": "0", "number": "N0"}

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        for i, b in enumerate(batches, 1):
            (out / f"batch_{i:03d}.json").write_text(json.dumps(b), encoding="utf-8")
        r1 = out / "results_001.jsonl"
        append_record(r1, {"id": "0", "number": "N0", "status": "error", "error": "HTTP 500"})
        append_record(
            r1,
            {
                "id": "0",
                "number": "N0",
                "status": "generated",
                "attachment": "a.pdf",
                "events": 3,
                "unverifiedTypes": ["X"],
                "unverifiedProperties": [],
            },
        )
        append_record(r1, {"id": "1", "number": "N1", "status": "skipped_exists"})
        r2 = out / "results_002.jsonl"
        append_record(
            r2,
            {
                "id": "2",
                "number": "N2",
                "status": "error",
                "error": "HTTP 403",
                "unverifiedTypes": [],
                "unverifiedProperties": ["zz"],
            },
        )
        with r2.open("a", encoding="utf-8") as fh:
            fh.write("{invalid json\n")
        records, summary = merge_results(out)
        assert summary["generated"] == 1 and summary["skipped_exists"] == 1 and summary["error"] == 1
        assert summary["errors"] == [{"number": "N2", "error": "HTTP 403"}]
        assert summary["unverifiedTypes"] == ["X"] and summary["unverifiedProperties"] == ["zz"]
        assert summary["missing"] == [{"id": "3", "number": "N3"}, {"id": "4", "number": "N4"}]
        assert summary["malformedLines"] == 1
        assert len(records) == 3 and all("timestamp" in r for r in records)
    print("self-check OK")


def _csv(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="batches.py")
    parser.add_argument("--self-check", action="store_true")
    sub = parser.add_subparsers(dest="cmd")
    s = sub.add_parser("split")
    s.add_argument("docs")
    s.add_argument("outdir")
    s.add_argument("--size", type=int, default=25)
    s.add_argument("--flow-status", default="SentToERP")
    s.add_argument("--date-field", choices=DATE_FIELDS, default="issueDate")
    s.add_argument("--from", dest="date_from")
    s.add_argument("--to", dest="date_to")
    r = sub.add_parser("record")
    r.add_argument("results")
    r.add_argument("--id", required=True)
    r.add_argument("--number", default="")
    r.add_argument("--status", choices=STATUSES, required=True)
    r.add_argument("--attachment")
    r.add_argument("--events", type=int)
    r.add_argument("--unverified-types")
    r.add_argument("--unverified-properties")
    r.add_argument("--error")
    m = sub.add_parser("merge")
    m.add_argument("outdir")
    m.add_argument("log")
    m.add_argument("--org")
    args = parser.parse_args(argv)

    if args.self_check:
        _self_check()
    elif args.cmd == "split":
        try:
            d_from = parse_dmy_date(args.date_from) if args.date_from else None
            d_to = parse_dmy_date(args.date_to) if args.date_to else None
        except ValueError:
            sys.exit("Dates must be in the format DD.MM.YYYY")
        docs = json.loads(Path(args.docs).read_text(encoding="utf-8"))
        flow_status = args.flow_status or None
        batches = split_docs(docs, args.size, flow_status, d_from, d_to, args.date_field)
        no_date = missing_date(docs, flow_status, args.date_field) if d_from or d_to else 0
        outdir = Path(args.outdir)
        outdir.mkdir(parents=True, exist_ok=True)
        paths = []
        for i, batch in enumerate(batches, 1):
            p = outdir / f"batch_{i:03d}.json"
            p.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")
            paths.append(str(p))
        print(
            json.dumps(
                {"input": len(docs), "kept": sum(len(b) for b in batches), "noDate": no_date, "batches": paths},
                ensure_ascii=False,
            )
        )
    elif args.cmd == "record":
        record = {"id": args.id, "number": args.number or args.id, "status": args.status}
        if args.attachment:
            record["attachment"] = args.attachment
        if args.events is not None:
            record["events"] = args.events
        if args.error:
            record["error"] = args.error
        record["unverifiedTypes"] = _csv(args.unverified_types)
        record["unverifiedProperties"] = _csv(args.unverified_properties)
        append_record(Path(args.results), record)
    elif args.cmd == "merge":
        records, summary = merge_results(Path(args.outdir))
        log = {
            "org": args.org,
            "generatedAt": datetime.now().isoformat(timespec="seconds"),
            "summary": summary,
            "records": records,
        }
        Path(args.log).write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False))
    else:
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv[1:])
