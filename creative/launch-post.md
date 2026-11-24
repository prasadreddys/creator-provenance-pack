# Creator Provenance Pack launch post — DRAFT, not published

Status: draft for the user's approval. Nothing posted yet. Repo not created, nothing pushed.

Rules for this post: only measured numbers, no user/sales/revenue claims, no invented quotes.

## X / Threads version

AI content floods every feed and nobody can tell who made what — or whether the file was altered after it was published.

Creator Provenance Pack gives any file a signed, verifiable record: SHA-256 hash, author, tool chain, license, and a parent link for derivatives. One command verifies it later.

Free, open source, stdlib-only Python, local files only, no sign-up.

## Longer version (README / Product Hunt style)

Provenance is the missing receipt for creative work. Creator Provenance Pack signs any file with a tamper-evident record: file hash, size, author, origin (human / human-ai / ai-generated), the tools used, license, timestamp, and an optional parent record so a remix links back to its source. `verify` re-hashes the file and the record and reports file MATCHED/CHANGED and record INTACT/TAMPERED. `chain` walks the whole derivation chain. `badge` renders a self-contained HTML badge with a VERIFIED/UNVERIFIED stamp.

- Demo: sample (109 bytes) and derived (171 bytes) records both verify MATCHED / INTACT / OK; chain depth 2, chain OK; badge stamp VERIFIED, no external URLs
- Tamper cases confirmed by hand: one byte appended to the file → file CHANGED, exit 1; one space added to the record's license → record TAMPERED, schema FAIL, exit 1
- Honest about what it is: records are tamper-evident, not authenticated — there are no key signatures, so anyone can claim any author, and the timestamp is self-asserted, not independently attested. The badge is a display of a record, not proof by itself.

Measured, not estimated: 62 unit tests, all passing. No network, no keys, no paid API.
