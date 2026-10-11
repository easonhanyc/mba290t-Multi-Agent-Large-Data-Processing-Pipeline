"""Bridge to the course-provided check_submission.py (row hashing, profile, audit).

`row_sha` here is a byte-for-byte reimplementation of the provided helper, so the pipeline
runs without importing course code; tests assert both agree on every checkpoint row.
`ingestion.json` is always produced by the provided helper itself, as the contract requires.
"""

import hashlib
import importlib.util
import json
from functools import lru_cache
from pathlib import Path

FIELDS = ("review_id", "review_text", "review_rating", "review_likes", "app_version", "review_timestamp")
AUDIT_VERSION = "a5-audit-v1"


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)


def row_sha(row) -> str:
    # Exact strings; no trimming, translation, or Unicode normalisation.
    return hashlib.sha256(canonical([row[k] for k in FIELDS]).encode("utf-8")).hexdigest()


@lru_cache(maxsize=4)
def load_checker(path: str):
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"check_submission.py not found at {p}. Set paths.checker in config/pipeline.toml.")
    spec = importlib.util.spec_from_file_location("course_check_submission", p)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if getattr(module, "VERSION", None) != AUDIT_VERSION:
        raise ValueError(f"Unexpected checker version {getattr(module, 'VERSION', None)!r}; expected {AUDIT_VERSION}")
    return module


def helper_profile(checker_path, csv_path) -> dict:
    """The provided helper's deterministic full-file profile (exact ingestion.json content)."""
    return load_checker(str(checker_path)).profile(Path(csv_path))
