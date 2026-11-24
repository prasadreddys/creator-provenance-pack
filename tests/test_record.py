"""Tests for the provenance record model (creation, hashing, schema)."""

import hashlib
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from provenance.record import (
    FORMAT,
    ProvenanceError,
    build_record,
    canonical_json,
    compute_record_sha256,
    parse_created_utc,
    sha256_file,
    validate_record,
)


def _good_record(**overrides):
    rec = {
        "format": FORMAT,
        "file_name": "work.txt",
        "sha256": "a" * 64,
        "size_bytes": 10,
        "author": "Prasad Reddy",
        "created_utc": "2026-11-24T07:30:00Z",
        "origin": "human",
        "tools": ["Muse"],
        "license": "CC-BY-4.0",
        "parent_sha256": None,
        "statement": "Test work.",
    }
    rec["record_sha256"] = compute_record_sha256(rec)
    rec.update(overrides)
    return rec


class TestSha256File(unittest.TestCase):
    def test_hash_matches_hashlib(self):
        with tempfile.NamedTemporaryFile("wb", delete=False) as fh:
            fh.write(b"hello provenance\n")
            path = fh.name
        try:
            digest, size = sha256_file(path)
            self.assertEqual(digest, hashlib.sha256(b"hello provenance\n").hexdigest())
            self.assertEqual(size, 17)
        finally:
            os.unlink(path)

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            sha256_file("/nonexistent/nope.txt")


class TestCanonicalJson(unittest.TestCase):
    def test_deterministic_and_sorted(self):
        a = canonical_json({"b": 1, "a": [3, 2]})
        b = canonical_json({"a": [3, 2], "b": 1})
        self.assertEqual(a, b)
        self.assertEqual(a, '{"a":[3,2],"b":1}')

    def test_record_sha256_recomputes(self):
        rec = _good_record()
        self.assertEqual(rec["record_sha256"], compute_record_sha256(rec))
        # One-byte change to the body changes the hash.
        tampered = dict(rec)
        tampered["author"] = "Someone Else"
        self.assertNotEqual(tampered["record_sha256"], compute_record_sha256(tampered))


class TestParseCreatedUtc(unittest.TestCase):
    def test_valid(self):
        dt = parse_created_utc("2026-11-24T07:30:00Z")
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 11)

    def test_missing_z_rejected(self):
        with self.assertRaises(ProvenanceError):
            parse_created_utc("2026-11-24T07:30:00+00:00")

    def test_bad_date_rejected(self):
        with self.assertRaises(ProvenanceError):
            parse_created_utc("2026-13-24T07:30:00Z")

    def test_non_string_rejected(self):
        with self.assertRaises(ProvenanceError):
            parse_created_utc(20261124)


class TestValidateRecord(unittest.TestCase):
    def test_good_record_valid(self):
        self.assertEqual(validate_record(_good_record()), [])

    def test_bad_format(self):
        errs = validate_record(_good_record(format="other/2"))
        self.assertTrue(any("format" in e for e in errs))

    def test_bad_origin(self):
        errs = validate_record(_good_record(origin="alien"))
        self.assertTrue(any("origin" in e for e in errs))

    def test_empty_tools_for_human_ai(self):
        rec = _good_record(origin="human-ai", tools=[])
        rec["record_sha256"] = compute_record_sha256(rec)
        errs = validate_record(rec)
        self.assertTrue(any("tools" in e for e in errs))

    def test_empty_tools_for_ai_generated(self):
        rec = _good_record(origin="ai-generated", tools=[])
        rec["record_sha256"] = compute_record_sha256(rec)
        errs = validate_record(rec)
        self.assertTrue(any("tools" in e for e in errs))

    def test_empty_tools_ok_for_human(self):
        rec = _good_record(origin="human", tools=[])
        rec["record_sha256"] = compute_record_sha256(rec)
        self.assertEqual(validate_record(rec), [])

    def test_bad_timestamp(self):
        errs = validate_record(_good_record(created_utc="yesterday"))
        self.assertTrue(any("created_utc" in e for e in errs))

    def test_bad_parent_hash(self):
        errs = validate_record(_good_record(parent_sha256="xyz"))
        self.assertTrue(any("parent_sha256" in e for e in errs))

    def test_empty_license(self):
        errs = validate_record(_good_record(license="   "))
        self.assertTrue(any("license" in e for e in errs))

    def test_empty_author(self):
        errs = validate_record(_good_record(author=""))
        self.assertTrue(any("author" in e for e in errs))

    def test_negative_size(self):
        errs = validate_record(_good_record(size_bytes=-1))
        self.assertTrue(any("size_bytes" in e for e in errs))

    def test_bool_size_rejected(self):
        errs = validate_record(_good_record(size_bytes=True))
        self.assertTrue(any("size_bytes" in e for e in errs))

    def test_tampered_hash_detected(self):
        rec = _good_record()
        rec["author"] = "Mallory"
        errs = validate_record(rec)
        self.assertTrue(any("tampered" in e for e in errs))

    def test_non_dict_record(self):
        self.assertTrue(validate_record(["not", "a", "dict"]))


class TestBuildRecord(unittest.TestCase):
    def test_builds_signed_record(self):
        rec = build_record(
            file_name="w.txt",
            file_sha256="b" * 64,
            size_bytes=5,
            author="A",
            origin="human-ai",
            tools=["Muse"],
            license_="CC-BY-4.0",
            created_utc="2026-11-24T07:30:00Z",
        )
        self.assertEqual(validate_record(rec), [])
        self.assertEqual(rec["record_sha256"], compute_record_sha256(rec))

    def test_build_rejects_bad_origin(self):
        with self.assertRaises(ProvenanceError):
            build_record(
                file_name="w.txt",
                file_sha256="b" * 64,
                size_bytes=5,
                author="A",
                origin="nope",
                tools=[],
                license_="CC-BY-4.0",
            )

    def test_build_rejects_empty_tools_for_ai(self):
        with self.assertRaises(ProvenanceError):
            build_record(
                file_name="w.txt",
                file_sha256="b" * 64,
                size_bytes=5,
                author="A",
                origin="ai-generated",
                tools=[],
                license_="CC-BY-4.0",
            )

    def test_default_created_is_utc_z(self):
        rec = build_record(
            file_name="w.txt",
            file_sha256="b" * 64,
            size_bytes=5,
            author="A",
            origin="human",
            tools=[],
            license_="CC-BY-4.0",
        )
        parse_created_utc(rec["created_utc"])  # raises if malformed


if __name__ == "__main__":
    unittest.main()
