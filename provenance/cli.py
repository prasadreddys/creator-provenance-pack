"""Command-line interface for Creator Provenance Pack."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from .badge import render_badge
from .record import (
    FORMAT,
    ORIGINS,
    ProvenanceError,
    build_record,
    parse_created_utc,
    sha256_file,
    validate_record,
)
from .verify import load_record, verify_chain, verify_pair

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return EXIT_USAGE


def _cmd_sign(args: argparse.Namespace) -> int:
    if not os.path.isfile(args.file):
        return _fail(f"file not found: {args.file}")
    if args.origin not in ORIGINS:
        return _fail(f"origin must be one of {', '.join(ORIGINS)}")
    if args.created is not None:
        try:
            parse_created_utc(args.created)
        except ProvenanceError as exc:
            return _fail(str(exc))

    parent_sha256 = None
    if args.parent:
        try:
            parent = load_record(args.parent)
        except ProvenanceError as exc:
            return _fail(str(exc))
        parent_sha256 = parent.get("record_sha256")
        if not parent_sha256:
            return _fail(f"parent record has no record_sha256: {args.parent}")

    try:
        file_sha, size = sha256_file(args.file)
        record = build_record(
            file_name=os.path.basename(args.file),
            file_sha256=file_sha,
            size_bytes=size,
            author=args.author,
            origin=args.origin,
            tools=args.tools or [],
            license_=args.license,
            statement=args.statement or "",
            parent_sha256=parent_sha256,
            created_utc=args.created,
        )
    except ProvenanceError as exc:
        return _fail(str(exc))
    except OSError as exc:
        return _fail(f"cannot read file: {exc}")

    out = args.out or f"{args.file}.provenance.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"file: {args.file}")
    print(f"sha256: {file_sha[:12]}…")
    print(f"record_sha256: {record['record_sha256'][:12]}…")
    print(f"origin: {args.origin}")
    print(f"record: {out}")
    return EXIT_OK


def _cmd_verify(args: argparse.Namespace) -> int:
    try:
        record = load_record(args.record)
    except ProvenanceError as exc:
        return _fail(str(exc))
    result = verify_pair(args.file, record)
    print(f"file: {result['file_status']}")
    print(f"record: {result['record_status']}")
    print(f"schema: {result['schema_status']}")
    for err in result["errors"]:
        print(f"  - {err}")
    return EXIT_OK if result["passed"] else EXIT_FAIL


def _cmd_chain(args: argparse.Namespace) -> int:
    try:
        record = load_record(args.record)
    except ProvenanceError as exc:
        return _fail(str(exc))
    result = verify_chain(record, args.vault)
    for i, link in enumerate(result["links"], 1):
        name = link.get("file_name") or "?"
        print(f"link {i}: {name} ({(link['record_sha256'] or '')[:12]}…) — {link['status']}")
        for err in link["errors"]:
            print(f"  - {err}")
    print(f"chain depth: {result['depth']}")
    print("chain: OK" if result["passed"] else "chain: BROKEN")
    return EXIT_OK if result["passed"] else EXIT_FAIL


def _cmd_badge(args: argparse.Namespace) -> int:
    try:
        record = load_record(args.record)
    except ProvenanceError as exc:
        return _fail(str(exc))
    html_doc = render_badge(record)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(html_doc)
    from .badge import badge_status

    print(f"badge: {args.out}")
    print(f"stamp: {badge_status(record)}")
    return EXIT_OK


def _cmd_init(args: argparse.Namespace) -> int:
    os.makedirs(args.dir, exist_ok=True)
    work = (
        "The quick brown fox jumps over the lazy dog.\n"
        "Provenance means knowing who made a thing, with what, and when.\n"
    )
    work_path = os.path.join(args.dir, "sample-work.txt")
    with open(work_path, "w", encoding="utf-8") as fh:
        fh.write(work)
    file_sha, size = sha256_file(work_path)
    record = build_record(
        file_name="sample-work.txt",
        file_sha256=file_sha,
        size_bytes=size,
        author="Prasad Reddy",
        origin="human",
        tools=["Muse"],
        license_="CC-BY-4.0",
        statement="Sample work for the Creator Provenance Pack demo.",
        created_utc="2026-11-24T07:30:00Z",
    )
    record_path = os.path.join(args.dir, "sample-record.json")
    with open(record_path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"wrote {work_path}")
    print(f"wrote {record_path}")
    print(f"record_sha256: {record['record_sha256'][:12]}…")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="provenance",
        description="Creator Provenance Pack — signed, verifiable provenance records for any file.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_sign = sub.add_parser("sign", help="Create a provenance record for a file")
    p_sign.add_argument("--file", required=True, help="File to sign")
    p_sign.add_argument("--author", required=True, help="Author name")
    p_sign.add_argument("--origin", required=True, choices=list(ORIGINS))
    p_sign.add_argument("--tools", nargs="*", default=[], help="Tools used")
    p_sign.add_argument("--license", default="CC-BY-4.0", help="License (default CC-BY-4.0)")
    p_sign.add_argument("--statement", default="", help="Short statement about the work")
    p_sign.add_argument("--parent", help="Parent record JSON (derivative work)")
    p_sign.add_argument("--created", help="Creation time, ISO-8601 UTC ending in Z")
    p_sign.add_argument("--out", help="Output record path (default <file>.provenance.json)")
    p_sign.set_defaults(func=_cmd_sign)

    p_verify = sub.add_parser("verify", help="Verify a file against its record")
    p_verify.add_argument("--file", required=True)
    p_verify.add_argument("--record", required=True)
    p_verify.set_defaults(func=_cmd_verify)

    p_chain = sub.add_parser("chain", help="Verify a record and its parent chain")
    p_chain.add_argument("--record", required=True)
    p_chain.add_argument("--vault", default="./provenance-records",
                         help="Directory holding parent records as <record_sha256>.json")
    p_chain.set_defaults(func=_cmd_chain)

    p_badge = sub.add_parser("badge", help="Generate a self-contained HTML badge")
    p_badge.add_argument("--record", required=True)
    p_badge.add_argument("--out", required=True)
    p_badge.set_defaults(func=_cmd_badge)

    p_init = sub.add_parser("init", help="Write sample work + record templates")
    p_init.add_argument("--dir", required=True)
    p_init.set_defaults(func=_cmd_init)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
