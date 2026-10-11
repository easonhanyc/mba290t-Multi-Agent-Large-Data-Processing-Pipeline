#!/usr/bin/env python3
"""Build a synthetic scale-test CSV from checkpoint_500.csv texts (synthetic IDs, variant suffixes).

Used only to measure orchestrator overhead with the offline stub; it is not course data and never a result.
  python3 scripts/make_scale_fixture.py 20000 /path/to/scale_20k.csv
Then (rate limits lifted in a copy of config/pipeline.toml so only pipeline overhead is measured):
  python -m insight --config <unlimited.toml> run --input /path/to/scale_20k.csv --run-dir <dir> --offline-stub --workers 4
"""
import csv
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(n, out):
    random.seed(7)
    with open(ROOT / "Final Assignment - Spotify Reviews Dataset" / "checkpoint_500.csv", encoding="utf-8-sig", newline="") as f:
        src = list(csv.DictReader(f))
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["review_id", "review_text", "review_rating", "review_likes", "app_version", "review_timestamp"])
        for i in range(n):
            r = random.choice(src)
            text = r["review_text"] if random.random() < 0.27 else f"{r['review_text']} (variant {i % int(n * 0.75)})"
            w.writerow([f"SCALE-{i:06d}", text, r["review_rating"], r["review_likes"], r["app_version"], r["review_timestamp"]])
    print(f"wrote {n} synthetic rows to {out}")


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2])
