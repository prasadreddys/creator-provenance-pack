#!/usr/bin/env bash
# Creator Provenance Pack — unit suite + demo e2e.
# Usage: ./run_tests.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "=== unit tests ==="
python3 -m unittest discover -s tests -v

echo
echo "=== demo e2e ==="
DEMO="$(mktemp -d)"
trap 'rm -rf "$DEMO"' EXIT

echo "--- sign sample work ---"
python3 -m provenance sign --file examples/sample-work.txt \
    --author "Prasad Reddy" --origin human --tools Muse --license CC-BY-4.0 \
    --statement "Sample work for the Creator Provenance Pack demo." \
    --created 2026-11-24T07:30:00Z --out "$DEMO/sample-record.json"

echo "--- sign derived work (parent = sample record) ---"
python3 -m provenance sign --file examples/derived-work.txt \
    --author "Prasad Reddy" --origin human-ai --tools Muse "Claude Code" \
    --license CC-BY-4.0 --statement "Derived from sample-work.txt, remixed with AI assistance." \
    --parent examples/sample-record.json \
    --created 2026-11-24T08:00:00Z --out "$DEMO/derived-record.json"

echo "--- verify both records ---"
python3 -m provenance verify --file examples/sample-work.txt --record "$DEMO/sample-record.json"
python3 -m provenance verify --file examples/derived-work.txt --record "$DEMO/derived-record.json"

echo "--- verify the 2-link chain ---"
mkdir -p "$DEMO/vault"
python3 -c "
import json
rec = json.load(open('$DEMO/sample-record.json'))
open('$DEMO/vault/' + rec['record_sha256'] + '.json', 'w').write(json.dumps(rec, indent=2, sort_keys=True))
"
python3 -m provenance chain --record "$DEMO/derived-record.json" --vault "$DEMO/vault"

echo "--- render badge ---"
python3 -m provenance badge --record "$DEMO/sample-record.json" --out "$DEMO/badge.html"
grep -q "VERIFIED" "$DEMO/badge.html" && echo "badge stamp: VERIFIED"
if grep -q -E 'https?://' "$DEMO/badge.html"; then
    echo "FAIL: badge contains external URLs" >&2
    exit 1
fi
echo "badge: no external URLs"

echo
echo "=== check against hand-computed expected values ==="
python3 - "$DEMO" <<'PY'
import json, sys
demo = sys.argv[1]
expected = json.load(open("examples/expected-verify.json"))
for key, rec_file in [("sample", "sample-record.json"), ("derived", "derived-record.json")]:
    rec = json.load(open(f"{demo}/{rec_file}"))
    exp = expected[key]
    assert rec["sha256"] == exp["file_sha256"], key
    assert rec["size_bytes"] == exp["size_bytes"], key
    assert rec["record_sha256"] == exp["record_sha256"], key
    if key == "derived":
        assert rec["parent_sha256"] == exp["parent_sha256"], key
print("demo records match hand-computed expected-verify.json:")
print(f"  sample:  {expected['sample']['size_bytes']} bytes, sha256 {expected['sample']['file_sha256'][:12]}…, record {expected['sample']['record_sha256'][:12]}…")
print(f"  derived: {expected['derived']['size_bytes']} bytes, sha256 {expected['derived']['file_sha256'][:12]}…, parent {expected['derived']['parent_sha256'][:12]}…")
print(f"  chain depth: {expected['derived']['chain']['depth']}, passed: {expected['derived']['chain']['passed']}")
PY
echo "demo done."
