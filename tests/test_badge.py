"""Tests for the HTML badge."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from provenance.badge import badge_status, render_badge
from provenance.record import build_record, compute_record_sha256


def _record(**overrides):
    rec = build_record(
        file_name="work.txt",
        file_sha256="c" * 64,
        size_bytes=42,
        author="Prasad Reddy",
        origin="human-ai",
        tools=["Muse", "Claude Code"],
        license_="CC-BY-4.0",
        statement="A test work.",
        created_utc="2026-11-24T07:30:00Z",
    )
    rec.update(overrides)
    return rec


class TestBadge(unittest.TestCase):
    def test_contains_author_license_hash(self):
        html_doc = render_badge(_record())
        self.assertIn("Prasad Reddy", html_doc)
        self.assertIn("CC-BY-4.0", html_doc)
        self.assertIn("cccccccccccc", html_doc)  # sha256 short
        self.assertIn("work.txt", html_doc)
        self.assertIn("Human + AI assisted", html_doc)

    def test_verified_stamp_for_intact_record(self):
        self.assertEqual(badge_status(_record()), "VERIFIED")
        self.assertIn("VERIFIED", render_badge(_record()))

    def test_unverified_stamp_for_tampered_record(self):
        rec = _record()
        rec["author"] = "Mallory"
        self.assertEqual(badge_status(rec), "UNVERIFIED")
        self.assertIn("UNVERIFIED", render_badge(rec))

    def test_no_external_urls(self):
        html_doc = render_badge(_record())
        self.assertNotIn("http://", html_doc)
        self.assertNotIn("https://", html_doc)
        self.assertNotIn("<script", html_doc)
        self.assertNotIn("<img", html_doc)
        self.assertNotIn("<link", html_doc)

    def test_badge_says_file_not_checked(self):
        html_doc = render_badge(_record())
        self.assertIn("does <strong>not</strong> check the file", html_doc)

    def test_html_escapes_author(self):
        rec = _record(author="<script>alert(1)</script>")
        rec["record_sha256"] = compute_record_sha256(rec)
        html_doc = render_badge(rec)
        self.assertNotIn("<script>alert(1)</script>", html_doc)
        self.assertIn("&lt;script&gt;", html_doc)

    def test_origin_labels(self):
        for origin, label in [
            ("human", "Made by a human"),
            ("human-ai", "Human + AI assisted"),
            ("ai-generated", "AI generated"),
        ]:
            rec = _record(origin=origin)
            rec["record_sha256"] = compute_record_sha256(rec)
            self.assertIn(label, render_badge(rec))


if __name__ == "__main__":
    unittest.main()
