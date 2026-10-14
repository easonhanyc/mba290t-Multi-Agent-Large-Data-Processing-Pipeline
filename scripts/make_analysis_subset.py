"""Write the declared analysis scope: a deterministic, uniform 200,000-review sample of the full CSV.

    python3 scripts/make_analysis_subset.py            # -> data/analysis_200k.csv + data/analysis_200k.manifest.json

Rule (the course's own sampling order, from prepare_dataset.py / manifest.json): among unique-ID,
nonempty, valid-rating records, rank by SHA-256("berkeley-fall-2026-assignment-5-v1:" + review_id)
and keep the lowest N. Under this rule the first 50 are the golden set and the next 10,000 are
analysis_10000.csv (which contains checkpoint_500.csv and cost_100.csv), so every course file is
inside the scope. All empty-text rows are added so they are explicitly quarantined. Rows are written
unchanged, in source order, with the course's CSV writer settings. Standard library only.
"""

import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGICAL_ROOT = Path(os.path.abspath(__file__)).parent.parent  # the repo as reached, before resolving symlinks
DATASET = ROOT / "Final Assignment - Spotify Reviews Dataset"
FIELDS = ("review_id", "review_text", "review_rating", "review_likes", "app_version", "review_timestamp")
SEED = "berkeley-fall-2026-assignment-5-v1"
FULL_SHA = "1fc85de68a304dd8978b537cfa58793d5f41cbaf417fa32cb53899f83a2fcef6"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def shown(path):
    """Path as recorded in the manifest: relative to the repo when inside it, else absolute (never raises).

    The logical path (symlinks not resolved) is tried first, so a dataset folder that is a symlink inside the repo
    is still recorded relative to the repo; a path that is outside the repo either way is recorded resolved.
    """
    logical, resolved = Path(os.path.abspath(path)), Path(path).resolve()
    for candidate, root in ((logical, LOGICAL_ROOT), (logical, ROOT), (resolved, ROOT)):
        try:
            return candidate.relative_to(root).as_posix()
        except ValueError:
            continue
    return str(resolved)


def ids_of(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [r["review_id"] for r in csv.DictReader(f)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--full", type=Path, default=DATASET / "spotify_reviews_18months.csv")
    ap.add_argument("--n", type=int, default=200_000, help="sampled nonempty reviews (default 200,000)")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "analysis_200k.csv")
    args = ap.parse_args(argv)
    full_as_given, out_as_given = Path(os.path.abspath(args.full)), Path(os.path.abspath(args.out))  # for the manifest
    args.full, args.out = args.full.resolve(), args.out.resolve()  # relative paths are taken from the current directory

    full_sha = sha256_file(args.full)
    if full_sha != FULL_SHA:
        print(f"warning: {args.full} sha256 {full_sha} differs from the course manifest {FULL_SHA}", file=sys.stderr)
    rows, ranks, empty_ids, seen = [], [], set(), set()
    with open(args.full, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, strict=True):
            row = {k: row[k] for k in FIELDS}
            rows.append(row)
            rid = row["review_id"]
            dup = rid in seen
            seen.add(rid)
            if not row["review_text"].strip():
                empty_ids.add(rid)
                continue
            if dup or not rid or row["review_rating"] not in {"1", "2", "3", "4", "5"}:
                continue
            ranks.append((int.from_bytes(hashlib.sha256(f"{SEED}:{rid}".encode()).digest(), "big"), rid))
    ranks.sort()
    if len(ranks) < args.n:
        raise SystemExit(f"only {len(ranks)} eligible records; cannot sample {args.n}")
    chosen = {rid for _, rid in ranks[:args.n]}
    keep = chosen | empty_ids
    args.out.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        for row in rows:
            if row["review_id"] in keep:
                w.writerow(row)
                written += 1
    texts = [r["review_text"] for r in rows if r["review_id"] in chosen]
    contains = {}
    for name in ("golden_50_to_label.csv", "analysis_10000.csv", "checkpoint_500.csv", "cost_100.csv"):
        p = DATASET / name
        if p.exists():
            ids = ids_of(p)
            contains[name] = {"rows": len(ids), "all_in_scope": set(ids) <= keep}
    manifest = {
        "file": shown(out_as_given), "sha256": sha256_file(args.out), "bytes": args.out.stat().st_size,
        "rows": written, "sampled_nonempty": len(chosen), "empty_text_rows_added": len(empty_ids),
        "distinct_sampled_texts": len(set(texts)),
        "full_source": {"file": shown(full_as_given),
                        "sha256": full_sha, "rows": len(rows), "matches_course_manifest": full_sha == FULL_SHA},
        "method": (f"Lowest SHA-256('{SEED}:' + review_id) among unique-ID, nonempty, valid-rating records "
                   f"(the course's sampling rule), first {args.n}; plus every empty-text row so it is explicitly "
                   "quarantined. Rows unchanged, source order, csv.DictWriter(lineterminator='\\n')."),
        "contains_course_files": contains,
        "out_of_scope_rows": len(rows) - written,
        "out_of_scope_reason": ("Not classified: outside the declared 200,000-review analysis scope chosen to keep "
                                "total API spend under the $10 project budget. Ingested and profiled only."),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "command": "python3 scripts/make_analysis_subset.py" + (f" --n {args.n}" if args.n != 200_000 else "")
                   + (f" --full '{shown(full_as_given)}'" if args.full != (DATASET / "spotify_reviews_18months.csv").resolve() else "")
                   + (f" --out '{shown(out_as_given)}'" if args.out != (ROOT / "data" / "analysis_200k.csv").resolve() else ""),
    }
    mpath = args.out.with_suffix(".manifest.json")
    mpath.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("file", "sha256", "rows", "sampled_nonempty", "empty_text_rows_added",
                                               "distinct_sampled_texts", "contains_course_files")}, indent=2))


if __name__ == "__main__":
    main()
