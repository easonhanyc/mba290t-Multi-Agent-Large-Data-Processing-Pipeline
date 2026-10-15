"""Check (and if needed complete) a fresh input CSV for the pipeline; standard library only, no model calls.

The pipeline needs the six source columns of the course CSV. A fresh file from a grader may carry only some of
them, extra columns, or a different column order. This script writes a copy with exactly the six columns:
  - review_text is required (also accepted: text, content, review);
  - review_id is kept when present, otherwise generated as fresh-<row number>-<first 10 hex of SHA-256(text)>;
  - review_rating, review_likes, app_version and review_timestamp are copied when present, otherwise left blank
    (stars are never used as labels; a blank timestamp only removes that row from the monthly trends).
Source values are never edited. Every filled column is reported on screen and in <out>.manifest.json.

  python3 scripts/prepare_fresh_input.py fresh.csv runs/fresh-input/input.csv
"""

import csv
import hashlib
import json
import sys
from pathlib import Path

FIELDS = ["review_id", "review_text", "review_rating", "review_likes", "app_version", "review_timestamp"]
TEXT_ALIASES = ("review_text", "text", "content", "review")


def main(argv):
    if len(argv) != 2:
        raise SystemExit("usage: prepare_fresh_input.py <input.csv> <output.csv>")
    src, dst = Path(argv[0]), Path(argv[1])
    with open(src, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, strict=True)
        header = reader.fieldnames or []
        rows = list(reader)
    text_col = next((c for c in TEXT_ALIASES if c in header), None)
    if text_col is None:
        raise SystemExit(f"{src}: no review text column (looked for {', '.join(TEXT_ALIASES)}); columns: {header}")
    filled = [c for c in FIELDS if c not in header and not (c == "review_text")]
    out, seen = [], set()
    for n, r in enumerate(rows, 1):
        text = r.get(text_col) or ""
        rid = (r.get("review_id") or "").strip() if "review_id" in header else ""
        if not rid:
            rid = f"fresh-{n:05d}-{hashlib.sha256(text.encode()).hexdigest()[:10]}"
        rec = {"review_id": rid, "review_text": text}
        for c in FIELDS[2:]:
            rec[c] = r.get(c) or "" if c in header else ""
        out.append(rec)
        seen.add(rid)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    digest = hashlib.sha256(dst.read_bytes()).hexdigest()
    manifest = {"source": str(src), "source_sha256": hashlib.sha256(src.read_bytes()).hexdigest(), "output": str(dst),
                "output_sha256": digest, "rows": len(out), "text_column": text_col, "columns_filled_blank_or_generated": filled,
                "ignored_columns": [c for c in header if c not in FIELDS and c != text_col],
                "empty_texts": sum(not r["review_text"].strip() for r in out), "duplicate_review_ids": len(out) - len(seen)}
    Path(str(dst) + ".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    note = f"; filled: {', '.join(filled)}" if filled else ""
    print(f"[fresh] {len(out)} rows, {manifest['empty_texts']} empty texts, {manifest['duplicate_review_ids']} duplicate IDs"
          f" -> {dst}{note}")


if __name__ == "__main__":
    main(sys.argv[1:])
