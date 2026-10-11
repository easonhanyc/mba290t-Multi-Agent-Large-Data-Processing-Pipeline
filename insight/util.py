"""Small helpers: hashing, atomic file writes, JSON lines, clocks."""

import gzip
import hashlib
import json
import os
import secrets
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    """Exact-text hash used for cache keys and duplicate detection (no normalisation)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)


def short_hash(value, n=10) -> str:
    if not isinstance(value, (bytes, str)):
        value = canonical_json(value)
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()[:n]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_run_id() -> str:
    # Millisecond timestamp plus randomness: two invocations in the same second never collide.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%f")[:-3]
    return f"run-{stamp}Z-{secrets.token_hex(2)}"


def new_call_id(prefix="call") -> str:
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}-{secrets.token_hex(4)}"


def monotonic() -> float:
    return time.perf_counter()


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write_bytes(path, data: bytes) -> None:
    """Write to a temp file in the same folder, fsync, then rename over the target.

    Readers see either the old file or the complete new one, never a partial write.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_text(path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path, value, indent=2) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=indent, sort_keys=True, allow_nan=False) + "\n")


def atomic_write_jsonl(path, rows, compress=False) -> int:
    """Write an iterable of dicts as JSON lines atomically; returns the row count."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=str(path.parent))
    count = 0
    try:
        os.close(fd)
        opener = (lambda p: gzip.open(p, "wt", encoding="utf-8", compresslevel=6)) if compress else \
            (lambda p: open(p, "w", encoding="utf-8"))
        with opener(tmp) as f:
            for row in rows:
                f.write(canonical_json(row) + "\n")
                count += 1
        with open(tmp, "rb") as f:
            os.fsync(f.fileno())
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return count


def read_jsonl(path):
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def rel(path) -> str:
    """Project-relative path for logs and reports (keeps absolute home paths out of artifacts)."""
    try:
        return str(Path(path).resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def load_dotenv(path=None) -> list:
    """Minimal .env loader (standard library): KEY=VALUE lines, '#' comments, optional quotes.

    Existing environment variables win. Returns the names it set; values are never printed or logged.
    """
    if os.environ.get("INSIGHT_NO_DOTENV"):
        return []
    path = Path(path) if path else PROJECT_ROOT / ".env"
    if not path.is_file():
        return []
    names = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if key and value and key not in os.environ:
            os.environ[key] = value
            names.append(key)
    return names
