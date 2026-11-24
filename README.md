# Creator Provenance Pack

Prove who made a file, with what tools, under what license, and whether
it has changed since. A signed, verifiable provenance record for any file.

Free, open source, stdlib-only Python 3.12. No network, no paid APIs,
no sign-up, no accounts. All records live in local files.

## The problem

AI-generated content floods every feed and nobody can tell who made what,
or whether a file was altered after it was published. This tool gives a
creator a tamper-evident provenance record for any file: SHA-256 hash,
author, tool chain, license, creation time, and an optional parent record
so a derivative links back to its source. Anyone can verify the record
later with one command.

## Usage

```bash
# Sign a file (creates sample-work.txt.provenance.json by default)
python3 -m provenance sign --file essay.txt --author "Prasad Reddy" \
    --origin human-ai --tools Muse "Claude Code" --license CC-BY-4.0 \
    --statement "Drafted by me, edited with AI assistance."

# Verify later: file hash + record integrity + schema
python3 -m provenance verify --file essay.txt --record essay.txt.provenance.json
# file: MATCHED
# record: INTACT
# schema: OK

# A derivative links back to its source
python3 -m provenance sign --file remix.txt --author "Prasad Reddy" \
    --origin human-ai --tools Muse --parent essay.txt.provenance.json

# Verify the whole chain (parent records live in ./provenance-records
# as <record_sha256>.json)
python3 -m provenance chain --record remix.txt.provenance.json

# A shareable HTML badge (self-contained, no external resources)
python3 -m provenance badge --record essay.txt.provenance.json --out badge.html

# Templates
python3 -m provenance init --dir ./my-first-record
```

## Provenance record format

JSON, format `creator-provenance/1`:

```json
{
  "format": "creator-provenance/1",
  "file_name": "sample-work.txt",
  "sha256": "<64 hex, SHA-256 of the file>",
  "size_bytes": 123,
  "author": "Prasad Reddy",
  "created_utc": "2026-11-24T07:30:00Z",
  "origin": "human",
  "tools": ["Muse"],
  "license": "CC-BY-4.0",
  "parent_sha256": null,
  "statement": "...",
  "record_sha256": "<sha256 of the canonical record without this field>"
}
```

Rules:

- `origin` must be one of `human` / `human-ai` / `ai-generated`.
- `tools` is a list of non-empty strings. It is required (non-empty) for
  `human-ai` and `ai-generated`; it may be empty for `human`.
- `license` must be a non-empty string.
- `created_utc` must be ISO-8601 UTC ending in `Z`, e.g.
  `2026-11-24T07:30:00Z`.
- `parent_sha256` is null or 64 lowercase hex characters — the
  `record_sha256` of the parent record.
- `record_sha256` is the SHA-256 of the canonical JSON (sorted keys, no
  whitespace) of the record WITHOUT the `record_sha256` field. This is
  what makes the record tamper-evident: editing any other field changes
  the recomputed hash.

## What verification proves — and does NOT prove

`verify` proves three things:

1. **The file is unchanged** since signing (its SHA-256 matches the record).
2. **The record is intact** (its `record_sha256` matches its body).
3. **The schema is valid** (fields, origin, timestamp, hashes all well-formed).

It does **not** prove:

- That the author named in the record is really who wrote the file —
  the record is self-asserted, not signed with a cryptographic key.
  Anyone can write any author name into a record.
- That the stated tools or origin are true — the record states what the
  creator claimed, it cannot observe how the file was made.
- That the file is original, legal, or correctly licensed.

The badge's VERIFIED stamp checks the record itself only (hash + schema).
It does **not** check the file — the badge says so in its text.

## Honest limitations

- No cryptographic signatures or public-key identity: records are
  tamper-evident (edits are detectable), not authenticated (anyone can
  create a record claiming any author).
- No timestamp authority: `created_utc` is whatever the signer passed;
  it is not independently attested.
- Chain verification only follows parents present in the vault
  directory; a missing parent is reported, not fetched.
- Records are plain local files: no locking, no multi-machine sync.
- The badge is a static HTML file — it can be copied, edited, or faked
  like any other file; it is a display of a record, not proof by itself.

## Tests

```bash
./run_tests.sh   # unit suite + demo e2e
```

62 unit tests, all passing. The demo signs the example files, verifies
both records, checks the 2-link parent chain, and renders a badge.
