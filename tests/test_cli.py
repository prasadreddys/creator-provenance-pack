"""CLI end-to-end tests: sign -> verify -> chain -> badge, plus init."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

EXAMPLES = os.path.join(ROOT, "examples")


def run_cli(*argv, cwd=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = ROOT
    return subprocess.run(
        [sys.executable, "-m", "provenance", *argv],
        capture_output=True,
        text=True,
        cwd=cwd or ROOT,
        env=env,
    )


class TestCliSign(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.work = os.path.join(self.tmp, "work.txt")
        with open(self.work, "w", encoding="utf-8") as fh:
            fh.write("hello provenance\n")

    def test_sign_writes_valid_record(self):
        out = os.path.join(self.tmp, "work.provenance.json")
        proc = run_cli(
            "sign", "--file", self.work, "--author", "Prasad Reddy",
            "--origin", "human", "--tools", "Muse", "--license", "CC-BY-4.0",
            "--created", "2026-11-24T07:30:00Z", "--out", out,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rec = json.load(open(out))
        self.assertEqual(rec["author"], "Prasad Reddy")
        self.assertEqual(rec["origin"], "human")
        self.assertEqual(rec["created_utc"], "2026-11-24T07:30:00Z")
        self.assertEqual(rec["size_bytes"], 17)

    def test_sign_default_out(self):
        proc = run_cli(
            "sign", "--file", self.work, "--author", "A", "--origin", "human",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(os.path.exists(self.work + ".provenance.json"))

    def test_sign_parent_links_correctly(self):
        parent_out = os.path.join(self.tmp, "parent.json")
        run_cli(
            "sign", "--file", self.work, "--author", "A", "--origin", "human",
            "--created", "2026-11-24T07:30:00Z", "--out", parent_out,
        )
        parent = json.load(open(parent_out))
        child_out = os.path.join(self.tmp, "child.json")
        proc = run_cli(
            "sign", "--file", self.work, "--author", "A", "--origin", "human-ai",
            "--tools", "Muse", "--parent", parent_out,
            "--created", "2026-11-24T08:00:00Z", "--out", child_out,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        child = json.load(open(child_out))
        self.assertEqual(child["parent_sha256"], parent["record_sha256"])

    def test_sign_created_respected(self):
        out = os.path.join(self.tmp, "r.json")
        proc = run_cli(
            "sign", "--file", self.work, "--author", "A", "--origin", "human",
            "--created", "2026-01-02T03:04:05Z", "--out", out,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            json.load(open(out))["created_utc"], "2026-01-02T03:04:05Z"
        )

    def test_sign_missing_file_errors(self):
        proc = run_cli(
            "sign", "--file", os.path.join(self.tmp, "nope.txt"),
            "--author", "A", "--origin", "human",
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("not found", proc.stderr)

    def test_sign_bad_created_errors(self):
        proc = run_cli(
            "sign", "--file", self.work, "--author", "A", "--origin", "human",
            "--created", "yesterday",
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("created_utc", proc.stderr)

    def test_sign_empty_tools_for_ai_errors(self):
        proc = run_cli(
            "sign", "--file", self.work, "--author", "A",
            "--origin", "ai-generated",
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("tools", proc.stderr)


class TestCliVerify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.work = os.path.join(self.tmp, "work.txt")
        with open(self.work, "w", encoding="utf-8") as fh:
            fh.write("hello provenance\n")
        self.rec = os.path.join(self.tmp, "work.provenance.json")
        proc = run_cli(
            "sign", "--file", self.work, "--author", "A", "--origin", "human",
            "--created", "2026-11-24T07:30:00Z", "--out", self.rec,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_verify_good_pair(self):
        proc = run_cli("verify", "--file", self.work, "--record", self.rec)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("file: MATCHED", proc.stdout)
        self.assertIn("record: INTACT", proc.stdout)
        self.assertIn("schema: OK", proc.stdout)

    def test_verify_changed_file_fails(self):
        with open(self.work, "a", encoding="utf-8") as fh:
            fh.write("one more byte\n")
        proc = run_cli("verify", "--file", self.work, "--record", self.rec)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("file: CHANGED", proc.stdout)

    def test_verify_tampered_record_fails(self):
        rec = json.load(open(self.rec))
        rec["author"] = "Mallory"
        with open(self.rec, "w", encoding="utf-8") as fh:
            json.dump(rec, fh)
        proc = run_cli("verify", "--file", self.work, "--record", self.rec)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("record: TAMPERED", proc.stdout)


class TestCliChainAndBadge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.vault = os.path.join(self.tmp, "vault")
        os.makedirs(self.vault)
        self.work = os.path.join(self.tmp, "work.txt")
        with open(self.work, "w", encoding="utf-8") as fh:
            fh.write("hello provenance\n")
        self.parent = os.path.join(self.tmp, "parent.json")
        run_cli(
            "sign", "--file", self.work, "--author", "A", "--origin", "human",
            "--created", "2026-11-24T07:30:00Z", "--out", self.parent,
        )
        parent = json.load(open(self.parent))
        with open(
            os.path.join(self.vault, parent["record_sha256"] + ".json"),
            "w",
            encoding="utf-8",
        ) as fh:
            json.dump(parent, fh)
        self.child = os.path.join(self.tmp, "child.json")
        run_cli(
            "sign", "--file", self.work, "--author", "A", "--origin", "human-ai",
            "--tools", "Muse", "--parent", self.parent,
            "--created", "2026-11-24T08:00:00Z", "--out", self.child,
        )

    def test_chain_two_links(self):
        proc = run_cli("chain", "--record", self.child, "--vault", self.vault)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("chain depth: 2", proc.stdout)
        self.assertIn("chain: OK", proc.stdout)

    def test_chain_missing_parent(self):
        proc = run_cli("chain", "--record", self.child, "--vault", self.tmp)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("MISSING", proc.stdout)

    def test_badge_verified(self):
        out = os.path.join(self.tmp, "badge.html")
        proc = run_cli("badge", "--record", self.parent, "--out", out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        html_doc = open(out, encoding="utf-8").read()
        self.assertIn("VERIFIED", html_doc)
        self.assertIn("A", html_doc)

    def test_badge_tampered_unverified(self):
        rec = json.load(open(self.parent))
        rec["license"] = "All rights reserved"
        bad = os.path.join(self.tmp, "bad.json")
        with open(bad, "w", encoding="utf-8") as fh:
            json.dump(rec, fh)
        out = os.path.join(self.tmp, "badge.html")
        proc = run_cli("badge", "--record", bad, "--out", out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("UNVERIFIED", open(out, encoding="utf-8").read())


class TestCliInit(unittest.TestCase):
    def test_init_writes_templates(self):
        tmp = tempfile.mkdtemp()
        target = os.path.join(tmp, "starter")
        proc = run_cli("init", "--dir", target)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(os.path.exists(os.path.join(target, "sample-work.txt")))
        self.assertTrue(os.path.exists(os.path.join(target, "sample-record.json")))
        rec = json.load(open(os.path.join(target, "sample-record.json")))
        self.assertEqual(rec["file_name"], "sample-work.txt")


class TestCliExamplesE2E(unittest.TestCase):
    """Sign -> verify -> chain -> badge on the shipped examples."""

    def test_examples_match_expected_verify(self):
        expected = json.load(open(os.path.join(EXAMPLES, "expected-verify.json")))
        tmp = tempfile.mkdtemp()
        vault = os.path.join(tmp, "vault")
        os.makedirs(vault)

        sample_rec = os.path.join(EXAMPLES, "sample-record.json")
        derived_rec = os.path.join(EXAMPLES, "derived-record.json")

        # Verify both records against their files.
        for key, work_file, rec_path in [
            ("sample", "sample-work.txt", sample_rec),
            ("derived", "derived-work.txt", derived_rec),
        ]:
            exp = expected[key]
            proc = run_cli(
                "verify", "--file", os.path.join(EXAMPLES, work_file),
                "--record", rec_path,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("file: MATCHED", proc.stdout)
            self.assertIn("record: INTACT", proc.stdout)
            rec = json.load(open(rec_path))
            self.assertEqual(rec["sha256"], exp["file_sha256"])
            self.assertEqual(rec["size_bytes"], exp["size_bytes"])
            self.assertEqual(rec["record_sha256"], exp["record_sha256"])

        # Chain: vault holds the parent record under its record hash.
        parent = json.load(open(sample_rec))
        with open(
            os.path.join(vault, parent["record_sha256"] + ".json"),
            "w",
            encoding="utf-8",
        ) as fh:
            json.dump(parent, fh)
        proc = run_cli("chain", "--record", derived_rec, "--vault", vault)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("chain depth: 2", proc.stdout)
        self.assertIn("chain: OK", proc.stdout)

        # Badge for the derived record.
        badge_out = os.path.join(tmp, "badge.html")
        proc = run_cli("badge", "--record", derived_rec, "--out", badge_out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        html_doc = open(badge_out, encoding="utf-8").read()
        self.assertIn("VERIFIED", html_doc)
        self.assertIn("Prasad Reddy", html_doc)
        self.assertIn("CC-BY-4.0", html_doc)
        self.assertNotIn("https://", html_doc)


if __name__ == "__main__":
    unittest.main()
