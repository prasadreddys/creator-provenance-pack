"""Core record model: creation, canonical hashing, and validation.

A provenance record is a JSON object::

    {"format": "creator-provenance/1",
     "file_name": "sample-work.txt",
     "sha256": "<64 hex of the file>",
     "size_bytes": 123,
     "author": "Prasad Reddy",
     "created_utc": "2026-11-24T07:30:00Z",
     "origin": "human",
     "tools": ["Muse"],
     "license": "CC-BY-4.0",
     "parent_sha256": null,
     "statement": "...",
     "record_sha256": "<sha256 of the canonical record without this field>"}

``record_sha256`` is the SHA-256 of the canonical JSON (sorted keys, no
whitespace) of the record WITHOUT the ``record_sha256`` field. That is
what makes the record tamper-evident: any edit to any other field
changes the recomputed hash.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

FORMAT = "creator-provenance/1"
ORIGINS = ("human", "human-ai", "ai-generated")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_UTC_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class ProvenanceError(ValueError):
    """Raised when a record or its inputs fail validation."""


def sha256_file(path: str) -> tuple[str, int]:
    """Return (hex sha256, size in bytes) of the file at *path*."""
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def canonical_json(record: dict) -> str:
    """Canonical JSON: sorted keys, no whitespace, UTF-8."""
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_record_sha256(record: dict) -> str:
    """SHA-256 of the canonical record with ``record_sha256`` removed."""
    body = {k: v for k, v in record.items() if k != "record_sha256"}
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def parse_created_utc(value: str) -> datetime:
    """Parse an ISO-8601 UTC timestamp ending in ``Z``; raise otherwise."""
    if not isinstance(value, str) or not _UTC_Z.match(value):
        raise ProvenanceError(
            "created_utc must be ISO-8601 UTC ending in Z, e.g. 2026-11-24T07:30:00Z"
        )
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ProvenanceError(f"created_utc is not a valid timestamp: {value}") from exc


def validate_record(record: dict) -> list[str]:
    """Return a list of validation errors; empty means the record is valid."""
    errors: list[str] = []
    if not isinstance(record, dict):
        return ["record must be a JSON object"]

    if record.get("format") != FORMAT:
        errors.append(f"format must be {FORMAT!r}")

    file_name = record.get("file_name")
    if not isinstance(file_name, str) or not file_name:
        errors.append("file_name must be a non-empty string")

    sha = record.get("sha256")
    if not isinstance(sha, str) or not _HEX64.match(sha):
        errors.append("sha256 must be 64 lowercase hex characters")

    size = record.get("size_bytes")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        errors.append("size_bytes must be a non-negative integer")

    author = record.get("author")
    if not isinstance(author, str) or not author.strip():
        errors.append("author must be a non-empty string")

    created = record.get("created_utc")
    try:
        parse_created_utc(created)
    except ProvenanceError as exc:
        errors.append(str(exc))

    origin = record.get("origin")
    if origin not in ORIGINS:
        errors.append(f"origin must be one of {', '.join(ORIGINS)}")

    tools = record.get("tools")
    if not isinstance(tools, list) or any(
        not isinstance(t, str) or not t for t in tools
    ):
        errors.append("tools must be a list of non-empty strings")
    elif origin in ("human-ai", "ai-generated") and not tools:
        errors.append(f"tools must be non-empty for origin {origin!r}")

    license_ = record.get("license")
    if not isinstance(license_, str) or not license_.strip():
        errors.append("license must be a non-empty string")

    parent = record.get("parent_sha256")
    if parent is not None and (not isinstance(parent, str) or not _HEX64.match(parent)):
        errors.append("parent_sha256 must be null or 64 lowercase hex characters")

    statement = record.get("statement")
    if statement is not None and not isinstance(statement, str):
        errors.append("statement must be a string when present")

    rec_hash = record.get("record_sha256")
    if not isinstance(rec_hash, str) or not _HEX64.match(rec_hash):
        errors.append("record_sha256 must be 64 lowercase hex characters")

    # Only check the tamper-evidence hash when the rest is well-formed
    # enough for the computation to be meaningful.
    if not errors and rec_hash != compute_record_sha256(record):
        errors.append("record_sha256 does not match the record body (tampered?)")

    return errors


def build_record(
    *,
    file_name: str,
    file_sha256: str,
    size_bytes: int,
    author: str,
    origin: str,
    tools: list[str],
    license_: str,
    statement: str = "",
    parent_sha256: str | None = None,
    created_utc: str | None = None,
) -> dict:
    """Build a complete, signed record (with record_sha256 filled in)."""
    if created_utc is None:
        created_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    record: dict = {
        "format": FORMAT,
        "file_name": file_name,
        "sha256": file_sha256,
        "size_bytes": size_bytes,
        "author": author,
        "created_utc": created_utc,
        "origin": origin,
        "tools": list(tools),
        "license": license_,
        "parent_sha256": parent_sha256,
        "statement": statement,
    }
    errors = validate_record({**record, "record_sha256": "0" * 64})
    # validate_record also checks record_sha256 format (passes: 64 hex)
    # and the hash match (fails: placeholder) — drop the hash-mismatch
    # error here; it is expected before signing.
    errors = [e for e in errors if "does not match the record body" not in e]
    if errors:
        raise ProvenanceError("; ".join(errors))
    record["record_sha256"] = compute_record_sha256(record)
    return record
