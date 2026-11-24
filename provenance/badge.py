"""Self-contained HTML badge for a provenance record.

The badge shows the origin label, author, license, file name, short
hashes, and a VERIFIED / UNVERIFIED stamp. The stamp is computed by
re-running the *record integrity* check only (record_sha256 over the
record body) — the file itself is NOT checked here, and the badge says
so in its text. No external resources: no links, no images, no scripts,
no fonts — everything is inline.
"""

from __future__ import annotations

import html

from .record import compute_record_sha256, validate_record

ORIGIN_LABELS = {
    "human": "Made by a human",
    "human-ai": "Human + AI assisted",
    "ai-generated": "AI generated",
}


def badge_status(record: dict) -> str:
    """'VERIFIED' when the record body is intact and the schema is OK."""
    if validate_record(record):
        return "UNVERIFIED"
    stored = record.get("record_sha256")
    return "VERIFIED" if stored == compute_record_sha256(record) else "UNVERIFIED"


def _short(value: str | None) -> str:
    if not isinstance(value, str):
        return "—"
    return value[:12] + "…" if len(value) > 12 else value


def render_badge(record: dict) -> str:
    """Render the full self-contained HTML badge document."""
    status = badge_status(record)
    origin = record.get("origin", "unknown")
    label = ORIGIN_LABELS.get(origin, "Unknown origin")
    stamp_color = "#15803d" if status == "VERIFIED" else "#b91c1c"
    stamp_bg = "#dcfce7" if status == "VERIFIED" else "#fee2e2"

    def esc(value) -> str:
        return html.escape(str(value) if value is not None else "—")

    rows = [
        ("Origin", f"{esc(label)} ({esc(origin)})"),
        ("Author", esc(record.get("author"))),
        ("License", esc(record.get("license"))),
        ("File", esc(record.get("file_name"))),
        ("Created", esc(record.get("created_utc"))),
        ("File SHA-256", esc(_short(record.get("sha256")))),
        ("Record SHA-256", esc(_short(record.get("record_sha256")))),
    ]
    tools = record.get("tools") or []
    rows.append(("Tools", esc(", ".join(tools)) if tools else "—"))
    if record.get("parent_sha256"):
        rows.append(("Parent record", esc(_short(record.get("parent_sha256")))))
    if record.get("statement"):
        rows.append(("Statement", esc(record.get("statement"))))

    body_rows = "\n".join(
        f'      <tr><th>{k}</th><td>{v}</td></tr>' for k, v in rows
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Provenance — {esc(record.get("file_name"))}</title>
<style>
  body {{ font-family: system-ui, sans-serif; background: #f8fafc; color: #0f172a; margin: 0; padding: 24px; }}
  .badge {{ max-width: 560px; margin: 0 auto; background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 24px; }}
  .stamp {{ display: inline-block; background: {stamp_bg}; color: {stamp_color}; font-weight: 700; letter-spacing: 0.08em; padding: 6px 12px; border-radius: 999px; }}
  h1 {{ font-size: 20px; margin: 12px 0 4px; }}
  p.note {{ font-size: 13px; color: #475569; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
  th, td {{ text-align: left; padding: 8px 4px; border-top: 1px solid #e2e8f0; font-size: 14px; vertical-align: top; }}
  th {{ width: 140px; color: #475569; font-weight: 600; }}
  td {{ word-break: break-all; }}
</style>
</head>
<body>
<div class="badge">
  <span class="stamp">{status}</span>
  <h1>Provenance record</h1>
  <p class="note">This stamp checks the record itself (its tamper-evident hash and schema). It does <strong>not</strong> check the file — use <code>provenance verify</code> to confirm the file still matches this record.</p>
  <table>
{body_rows}
  </table>
</div>
</body>
</html>
"""
