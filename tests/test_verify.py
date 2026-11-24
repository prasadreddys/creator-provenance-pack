"""Tests for verify_pair and verify_chain."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from provenance.record import (
    ProvenanceError,
    build_record,
    compute_record_sha256,
)
from provenance.verify import load_record, verify_chain, verify_pair

SAMPLE = b"alpha\nbravo\ncharlie\n"  # 3 lines, 3 words


def _write(path, data: bytes):
    with open(path, "wb") as fh:
        fh.write(data)


def _sign(tmp, name, data, **kw):
    path = os.path.join(tmp, name)
    _write(path, data)
    import hashlib

    rec = build_record(
        file_name=name,
        file_sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        author=kw.get("author", "Prasad Reddy"),
        origin=kw.get("origin", "human"),
        tools=kw.get("tools", ["Muse"]),
        license_=kw.get("license", "CC-BY-4.0"),
        statement=kw.get("statement", ""),
        parent_sha256=kw.get("parent_sha256"),
        created_utc="2026-11-24T07:30:00Z",
    )
    rec_path = os.path.join(tmp, name + ".provenance.json")
    with open(rec_path, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=2, sort_keys=True)
    return path, rec_path, rec


class TestLoadRecord(unittest.TestCase):
    def test_missing_file(self):
        with self.assertRaises(ProvenanceError):
            load_record("/nonexistent/record.json")

    def test_invalid_json(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            fh.write("{not json")
            path = fh.name
        try:
            with self.assertRaises(ProvenanceError):
                load_record(path)
        finally:
            os.unlink(path)

    def test_non_object(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            fh.write("[1, 2]")
            path = fh.name
        try:
            with self.assertRaises(ProvenanceError):
                load_record(path)
        finally:
            os.unlink(path)


class TestVerifyPair(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_good_pair_passes(self):
        path, rec_path, _ = _sign(self.tmp, "work.txt", SAMPLE)
        result = verify_pair(path, load_record(rec_path))
        self.assertTrue(result["passed"])
        self.assertEqual(result["file_status"], "MATCHED")
        self.assertEqual(result["record_status"], "INTACT")
        self.assertEqual(result["schema_status"], "OK")

    def test_changed_file_detected(self):
        path, rec_path, _ = _sign(self.tmp, "work.txt", SAMPLE)
        _write(path, SAMPLE + b"tampered!\n")
        result = verify_pair(path, load_record(rec_path))
        self.assertFalse(result["passed"])
        self.assertEqual(result["file_status"], "CHANGED")
        self.assertEqual(result["record_status"], "INTACT")

    def test_tampered_record_detected(self):
        path, rec_path, rec = _sign(self.tmp, "work.txt", SAMPLE)
        rec["author"] = "Mallory"
        with open(rec_path, "w", encoding="utf-8") as fh:
            json.dump(rec, fh, indent=2, sort_keys=True)
        result = verify_pair(path, load_record(rec_path))
        self.assertFalse(result["passed"])
        self.assertEqual(result["record_status"], "TAMPERED")
        self.assertEqual(result["schema_status"], "FAIL")

    def test_corrupted_record_schema_fails(self):
        path, rec_path, rec = _sign(self.tmp, "work.txt", SAMPLE)
        rec["origin"] = "alien"
        rec["record_sha256"] = compute_record_sha256(rec)
        with open(rec_path, "w", encoding="utf-8") as fh:
            json.dump(rec, fh, indent=2, sort_keys=True)
        result = verify_pair(path, load_record(rec_path))
        self.assertFalse(result["passed"])
        self.assertEqual(result["schema_status"], "FAIL")

    def test_missing_file_errors(self):
        _, rec_path, _ = _sign(self.tmp, "work.txt", SAMPLE)
        result = verify_pair(os.path.join(self.tmp, "gone.txt"), load_record(rec_path))
        self.assertFalse(result["passed"])
        self.assertEqual(result["file_status"], "ERROR")


class TestVerifyChain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.vault = os.path.join(self.tmp, "vault")
        os.makedirs(self.vault)
        _, self.parent_path, self.parent = _sign(self.tmp, "orig.txt", SAMPLE)
        with open(
            os.path.join(self.vault, self.parent["record_sha256"] + ".json"),
            "w",
            encoding="utf-8",
        ) as fh:
            json.dump(self.parent, fh, indent=2, sort_keys=True)
        _, self.child_path, self.child = _sign(
            self.tmp,
            "remix.txt",
            SAMPLE + b"remix\n",
            origin="human-ai",
            parent_sha256=self.parent["record_sha256"],
        )

    def test_two_link_chain_verifies(self):
        result = verify_chain(self.child, self.vault)
        self.assertTrue(result["passed"])
        self.assertEqual(result["depth"], 2)
        self.assertEqual([l["status"] for l in result["links"]], ["OK", "OK"])

    def test_single_link_no_parent(self):
        result = verify_chain(self.parent, self.vault)
        self.assertTrue(result["passed"])
        self.assertEqual(result["depth"], 1)

    def test_missing_parent_reported(self):
        result = verify_chain(self.child, os.path.join(self.tmp, "empty-vault"))
        self.assertFalse(result["passed"])
        self.assertEqual(result["links"][-1]["status"], "MISSING")

    def test_broken_parent_reported(self):
        bad_parent = dict(self.parent)
        bad_parent["author"] = "Mallory"
        with open(
            os.path.join(self.vault, self.parent["record_sha256"] + ".json"),
            "w",
            encoding="utf-8",
        ) as fh:
            json.dump(bad_parent, fh, indent=2, sort_keys=True)
        result = verify_chain(self.child, self.vault)
        self.assertFalse(result["passed"])
        self.assertEqual(result["links"][-1]["status"], "BROKEN")

    def test_tampered_child_breaks_chain(self):
        bad_child = dict(self.child)
        bad_child["license"] = "All rights reserved"
        result = verify_chain(bad_child, self.vault)
        self.assertFalse(result["passed"])
        self.assertEqual(result["links"][0]["status"], "BROKEN")
        self.assertEqual(result["depth"], 1)


if __name__ == "__main__":
    unittest.main()
