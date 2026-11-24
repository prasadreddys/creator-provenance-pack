"""Verification: file hash, record integrity, schema, and parent chains."""

from __future__ import annotations

import json
import os

from .record import ProvenanceError, compute_record_sha256, sha256_file, validate_record


def load_record(path: str) -> dict:
    """Load a record JSON file; raise ProvenanceError on any problem."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            record = json.load(fh)
    except FileNotFoundError as exc:
        raise ProvenanceError(f"record file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ProvenanceError(f"record file is not valid JSON: {path}: {exc}") from exc
    if not isinstance(record, dict):
        raise ProvenanceError(f"record file must contain a JSON object: {path}")
    return record


def verify_pair(file_path: str, record: dict) -> dict:
    """Verify a file against its record.

    Returns a dict with:
      file_status: "MATCHED" | "CHANGED" | "ERROR"
      record_status: "INTACT" | "TAMPERED"
      schema_status: "OK" | "FAIL"
      errors: list of strings
      passed: bool — True only when all three checks pass
    """
    errors: list[str] = []

    schema_errors = validate_record(record)
    schema_status = "OK" if not schema_errors else "FAIL"
    errors.extend(schema_errors)

    # Record integrity: recompute record_sha256 from the body. A schema
    # failure on the hash field itself also counts as tampering.
    stored = record.get("record_sha256")
    if isinstance(stored, str):
        record_status = (
            "INTACT" if stored == compute_record_sha256(record) else "TAMPERED"
        )
        if record_status == "TAMPERED":
            errors.append("record_sha256 does not match the record body")
    else:
        record_status = "TAMPERED"
        errors.append("record_sha256 missing or malformed")

    # File hash.
    try:
        actual_sha, actual_size = sha256_file(file_path)
        if actual_sha == record.get("sha256"):
            file_status = "MATCHED"
            if actual_size != record.get("size_bytes"):
                # Hash match with a size mismatch cannot happen for real
                # files, but report it rather than silently ignoring it.
                file_status = "CHANGED"
                errors.append("file size differs from the record")
        else:
            file_status = "CHANGED"
            errors.append("file hash differs from the record")
    except FileNotFoundError:
        file_status = "ERROR"
        errors.append(f"file not found: {file_path}")
    except OSError as exc:
        file_status = "ERROR"
        errors.append(f"cannot read file: {exc}")

    passed = (
        file_status == "MATCHED"
        and record_status == "INTACT"
        and schema_status == "OK"
    )
    return {
        "file_status": file_status,
        "record_status": record_status,
        "schema_status": schema_status,
        "errors": errors,
        "passed": passed,
    }


def verify_chain(record: dict, vault_dir: str, _seen: set | None = None) -> dict:
    """Verify a record and, recursively, its parent chain.

    Parent records are looked up in *vault_dir* as
    ``<parent record_sha256>.json``. Returns a dict with:
      depth: number of links verified (1 = just this record)
      links: [{record_sha256, file_name, status, errors}, ...]
      passed: True only when every link verifies (record integrity +
        schema) and no parent is missing or broken
    """
    if _seen is None:
        _seen = set()
    links: list[dict] = []
    passed = True
    current: dict | None = record

    while current is not None:
        rec_hash = current.get("record_sha256")
        if not isinstance(rec_hash, str):
            links.append(
                {
                    "record_sha256": None,
                    "file_name": current.get("file_name"),
                    "status": "INVALID",
                    "errors": ["record_sha256 missing or malformed"],
                }
            )
            passed = False
            break
        if rec_hash in _seen:
            links.append(
                {
                    "record_sha256": rec_hash,
                    "file_name": current.get("file_name"),
                    "status": "CYCLE",
                    "errors": ["parent chain contains a cycle"],
                }
            )
            passed = False
            break
        _seen.add(rec_hash)

        schema_errors = validate_record(current)
        intact = rec_hash == compute_record_sha256(current)
        link_errors = list(schema_errors)
        if not intact:
            link_errors.append("record_sha256 does not match the record body")
        status = "OK" if not link_errors else "BROKEN"
        if link_errors:
            passed = False
        links.append(
            {
                "record_sha256": rec_hash,
                "file_name": current.get("file_name"),
                "status": status,
                "errors": link_errors,
            }
        )
        if link_errors:
            break

        parent = current.get("parent_sha256")
        if parent is None:
            break
        parent_path = os.path.join(vault_dir, f"{parent}.json")
        if not os.path.exists(parent_path):
            links.append(
                {
                    "record_sha256": parent,
                    "file_name": None,
                    "status": "MISSING",
                    "errors": [f"parent record not found in vault: {parent_path}"],
                }
            )
            passed = False
            break
        try:
            current = load_record(parent_path)
        except ProvenanceError as exc:
            links.append(
                {
                    "record_sha256": parent,
                    "file_name": None,
                    "status": "BROKEN",
                    "errors": [str(exc)],
                }
            )
            passed = False
            break

    return {"depth": len(links), "links": links, "passed": passed}
