"""SQLite state for one run directory: reviews, results, call log, verification, caches.

Durability rules
- Every model attempt is written as 'dispatched' BEFORE the request is sent and settled
  afterwards, from the worker thread that made it (per-thread connections, WAL mode).
  A crash therefore leaves a visible 'dispatched' row, reconciled to 'unknown' on restart.
- Results are written only by the orchestrator thread, one review (plus its exact-text
  aliases) per transaction, with INSERT that refuses to overwrite: a completed record is
  never relabelled or double-counted under the same label_config.
"""

import json
import sqlite3
import threading
from pathlib import Path

from .util import utc_now

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS reviews (
  row_num INTEGER PRIMARY KEY,
  review_id TEXT NOT NULL,
  review_text TEXT NOT NULL,
  review_rating TEXT NOT NULL,
  review_likes TEXT NOT NULL,
  app_version TEXT NOT NULL,
  review_timestamp TEXT NOT NULL,
  source_sha256 TEXT NOT NULL,
  text_sha256 TEXT NOT NULL,
  is_empty INTEGER NOT NULL,
  duplicate_id INTEGER NOT NULL DEFAULT 0,
  rep_row_num INTEGER
);
CREATE INDEX IF NOT EXISTS reviews_id ON reviews(review_id);
CREATE INDEX IF NOT EXISTS reviews_text ON reviews(text_sha256);
CREATE INDEX IF NOT EXISTS reviews_rep ON reviews(rep_row_num);

CREATE TABLE IF NOT EXISTS results (
  review_id TEXT NOT NULL,
  label_config TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('completed', 'quarantined')),
  topic TEXT, subtopic TEXT, intent TEXT, sentiment REAL, severity INTEGER,
  entities TEXT, evidence_quote TEXT, needs_review INTEGER,
  cache_source_id TEXT,
  labeled_by TEXT,
  reason TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  detail TEXT,
  run_id TEXT NOT NULL,
  phase TEXT NOT NULL,
  completed_at TEXT NOT NULL,
  PRIMARY KEY (review_id, label_config)
);

CREATE TABLE IF NOT EXISTS staged (
  review_id TEXT NOT NULL,
  label_config TEXT NOT NULL,
  priority REAL NOT NULL,
  primary_json TEXT,
  reasons TEXT,
  trail TEXT,
  run_id TEXT,
  created_at TEXT NOT NULL,
  PRIMARY KEY (review_id, label_config)
);

CREATE TABLE IF NOT EXISTS calls (
  request_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  role TEXT NOT NULL,
  tier TEXT,
  phase TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  effort TEXT,
  label_config TEXT,
  stage_config TEXT,
  review_ids TEXT NOT NULL,
  attempt INTEGER NOT NULL,
  task_attempt INTEGER NOT NULL,
  outcome TEXT NOT NULL CHECK (outcome IN ('dispatched', 'succeeded', 'failed', 'unknown')),
  error TEXT,
  http_status INTEGER,
  input_tokens INTEGER,
  cached_input_tokens INTEGER,
  output_tokens INTEGER,
  reasoning_tokens INTEGER,
  usage_raw TEXT,
  provider_request_id TEXT,
  model_reported TEXT,
  finish TEXT,
  reserved_usd REAL NOT NULL DEFAULT 0,
  cost_usd REAL,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  duration_s REAL,
  worker TEXT,
  max_output_tokens INTEGER,
  prompt_chars INTEGER,
  valid_output INTEGER,
  notes TEXT,
  cache_write_tokens INTEGER,
  service_tier TEXT,
  billing TEXT,
  api_equiv_usd REAL
);
CREATE INDEX IF NOT EXISTS calls_run ON calls(run_id);
CREATE INDEX IF NOT EXISTS calls_role ON calls(role);

CREATE TABLE IF NOT EXISTS verifications (
  review_id TEXT NOT NULL,
  verifier_config TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('completed', 'failed')),
  topic TEXT, intent TEXT, severity INTEGER, sentiment REAL, confidence TEXT, reason TEXT,
  request_id TEXT,
  run_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (review_id, verifier_config)
);

CREATE TABLE IF NOT EXISTS stage_cache (
  stage TEXT NOT NULL,
  cache_key TEXT NOT NULL,
  output TEXT NOT NULL,
  request_id TEXT,
  run_id TEXT,
  created_at TEXT NOT NULL,
  PRIMARY KEY (stage, cache_key)
);

CREATE TABLE IF NOT EXISTS invocations (
  run_id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  command TEXT,
  phase TEXT,
  status TEXT,
  stop_reason TEXT,
  label_config TEXT,
  workers INTEGER,
  budget_usd REAL,
  offline_stub INTEGER,
  summary TEXT
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT,
  at TEXT NOT NULL,
  stage TEXT,
  event TEXT NOT NULL,
  detail TEXT
);
"""

RESULT_FIELDS = ("review_id", "label_config", "status", "topic", "subtopic", "intent", "sentiment", "severity",
                 "entities", "evidence_quote", "needs_review", "cache_source_id", "labeled_by", "reason",
                 "attempts", "detail", "run_id", "phase", "completed_at")


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=60, isolation_level=None, check_same_thread=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=60000")
    return conn


class Store:
    def __init__(self, run_dir):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.run_dir / "state.sqlite"
        self.conn = _connect(self.path)
        self.conn.executescript(SCHEMA)
        self._migrate()
        self._local = threading.local()
        self._owner = threading.get_ident()

    def _migrate(self):
        """Add columns introduced after a run directory was created (older evidence runs stay readable)."""
        have = {r[1] for r in self.conn.execute("PRAGMA table_info(calls)")}
        for col, typ in (("cache_write_tokens", "INTEGER"), ("service_tier", "TEXT"), ("billing", "TEXT"),
                         ("api_equiv_usd", "REAL")):
            if col not in have:
                self.conn.execute(f"ALTER TABLE calls ADD COLUMN {col} {typ}")

    # ---- connections --------------------------------------------------------------------
    def _thread_conn(self) -> sqlite3.Connection:
        if threading.get_ident() == self._owner:
            return self.conn
        c = getattr(self._local, "conn", None)
        if c is None:
            c = _connect(self.path)
            self._local.conn = c
        return c

    def close(self):
        self.conn.close()

    def tx(self):
        return _Tx(self.conn)

    # ---- meta / events --------------------------------------------------------------------
    def set_meta(self, key, value):
        self.conn.execute("INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                          (key, json.dumps(value)))

    def get_meta(self, key, default=None):
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def event(self, run_id, stage, event, **detail):
        self._thread_conn().execute("INSERT INTO events(run_id, at, stage, event, detail) VALUES(?,?,?,?,?)",
                                    (run_id, utc_now(), stage, event, json.dumps(detail, ensure_ascii=False)))

    # ---- reviews ----------------------------------------------------------------------------
    def review_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]

    def insert_reviews(self, rows):
        self.conn.executemany(
            "INSERT INTO reviews(row_num, review_id, review_text, review_rating, review_likes, app_version, "
            "review_timestamp, source_sha256, text_sha256, is_empty, duplicate_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)", rows)

    def assign_representatives(self, exact_text_reuse: bool):
        """rep_row_num = earliest nonempty row with identical text (or itself when reuse is off)."""
        c = self.conn
        c.execute("UPDATE reviews SET rep_row_num = NULL")
        if exact_text_reuse:
            c.execute("DROP TABLE IF EXISTS temp.reps")
            c.execute("CREATE TEMP TABLE reps AS SELECT text_sha256, MIN(row_num) AS rep FROM reviews "
                      "WHERE is_empty = 0 AND duplicate_id = 0 GROUP BY text_sha256")
            c.execute("CREATE INDEX temp.reps_sha ON reps(text_sha256)")
            c.execute("UPDATE reviews SET rep_row_num = (SELECT rep FROM temp.reps WHERE temp.reps.text_sha256 = reviews.text_sha256) "
                      "WHERE is_empty = 0 AND duplicate_id = 0")
            c.execute("DROP TABLE temp.reps")
        else:
            c.execute("UPDATE reviews SET rep_row_num = row_num WHERE is_empty = 0 AND duplicate_id = 0")

    def review(self, review_id):
        return self.conn.execute("SELECT * FROM reviews WHERE review_id=? AND duplicate_id=0", (review_id,)).fetchone()

    def pending_representatives(self, label_config, include_staged=False):
        """Distinct texts with no saved result. Staged ones (primary done, fallback decision pending) are
        excluded unless include_staged is set."""
        staged = "" if include_staged else \
            "AND NOT EXISTS (SELECT 1 FROM staged s WHERE s.review_id = r.review_id AND s.label_config = ?1) "
        return self.conn.execute(
            "SELECT r.* FROM reviews r WHERE r.is_empty = 0 AND r.duplicate_id = 0 AND r.rep_row_num = r.row_num "
            "AND NOT EXISTS (SELECT 1 FROM results x WHERE x.review_id = r.review_id AND x.label_config = ?1) "
            + staged + "ORDER BY r.row_num", (label_config,)).fetchall()

    def stage(self, row: dict):
        cols = list(row)
        self.conn.execute(f"INSERT OR REPLACE INTO staged({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                          [row[c] for c in cols])

    def staged_list(self, label_config):
        return self.conn.execute("SELECT * FROM staged WHERE label_config=? ORDER BY priority ASC, review_id ASC",
                                 (label_config,)).fetchall()

    def unstage(self, review_id, label_config):
        self.conn.execute("DELETE FROM staged WHERE review_id=? AND label_config=?", (review_id, label_config))

    def aliases_of(self, rep_row_num, label_config):
        return self.conn.execute(
            "SELECT r.review_id FROM reviews r WHERE r.rep_row_num = ? AND r.row_num != ? AND r.duplicate_id = 0 "
            "AND NOT EXISTS (SELECT 1 FROM results x WHERE x.review_id = r.review_id AND x.label_config = ?) "
            "ORDER BY r.row_num", (rep_row_num, rep_row_num, label_config)).fetchall()

    def scope_counts(self):
        c = self.conn
        q = lambda sql: c.execute(sql).fetchone()[0]
        return {
            "rows": q("SELECT COUNT(*) FROM reviews"),
            "unique_ids": q("SELECT COUNT(*) FROM reviews WHERE duplicate_id = 0"),
            "duplicate_id_rows": q("SELECT COUNT(*) FROM reviews WHERE duplicate_id = 1"),
            "empty_texts": q("SELECT COUNT(*) FROM reviews WHERE is_empty = 1 AND duplicate_id = 0"),
            "nonempty": q("SELECT COUNT(*) FROM reviews WHERE is_empty = 0 AND duplicate_id = 0"),
            "distinct_nonempty_texts": q("SELECT COUNT(DISTINCT text_sha256) FROM reviews WHERE is_empty = 0 AND duplicate_id = 0"),
            "representatives": q("SELECT COUNT(*) FROM reviews WHERE rep_row_num = row_num"),
        }

    # ---- results ------------------------------------------------------------------------------
    def result(self, review_id, label_config):
        return self.conn.execute("SELECT * FROM results WHERE review_id=? AND label_config=?",
                                 (review_id, label_config)).fetchone()

    def insert_result(self, row: dict) -> bool:
        """INSERT OR IGNORE: returns False if a result already exists (never overwrites)."""
        values = [row.get(k) for k in RESULT_FIELDS]
        cur = self.conn.execute(
            f"INSERT OR IGNORE INTO results({','.join(RESULT_FIELDS)}) VALUES({','.join('?' * len(RESULT_FIELDS))})", values)
        return cur.rowcount == 1

    def results(self, label_config, status=None):
        sql = "SELECT * FROM results WHERE label_config=?"
        args = [label_config]
        if status:
            sql += " AND status=?"
            args.append(status)
        return self.conn.execute(sql + " ORDER BY review_id", args).fetchall()

    def completed_ids(self, label_config):
        return [r[0] for r in self.conn.execute(
            "SELECT review_id FROM results WHERE label_config=? AND status='completed' ORDER BY review_id", (label_config,))]

    def result_counts(self, label_config):
        rows = self.conn.execute(
            "SELECT status, labeled_by, COUNT(*) n FROM results WHERE label_config=? GROUP BY status, labeled_by",
            (label_config,)).fetchall()
        return [dict(r) for r in rows]

    def count_labeled_by(self, label_config, tier):
        return self.conn.execute("SELECT COUNT(*) FROM results WHERE label_config=? AND labeled_by=? AND cache_source_id IS NULL",
                                 (label_config, tier)).fetchone()[0]

    # ---- calls ---------------------------------------------------------------------------------
    def call_dispatched(self, row: dict):
        cols = list(row)
        self._thread_conn().execute(
            f"INSERT INTO calls({','.join(cols)}) VALUES({','.join('?' * len(cols))})", [row[c] for c in cols])

    def call_settled(self, request_id, fields: dict):
        cols = list(fields)
        self._thread_conn().execute(
            f"UPDATE calls SET {', '.join(c + '=?' for c in cols)} WHERE request_id=?", [fields[c] for c in cols] + [request_id])

    def reconcile_dispatched(self, run_id):
        """Calls left 'dispatched' by a killed process: the provider may have charged for them."""
        rows = self.conn.execute("SELECT request_id, run_id FROM calls WHERE outcome='dispatched'").fetchall()
        for r in rows:
            self.conn.execute(
                "UPDATE calls SET outcome='unknown', error=?, ended_at=? WHERE request_id=?",
                ("process ended before a response was recorded; outcome and charge unknown "
                 f"(reconciled by {run_id})", utc_now(), r["request_id"]))
        return len(rows)

    def iter_calls(self, run_id=None):
        """Cursor over calls (streams; safe for very large logs)."""
        if run_id:
            return self.conn.execute("SELECT * FROM calls WHERE run_id=? ORDER BY started_at", (run_id,))
        return self.conn.execute("SELECT * FROM calls ORDER BY started_at")

    def iter_results(self, label_config, status=None):
        sql = "SELECT * FROM results WHERE label_config=?"
        args = [label_config]
        if status:
            sql += " AND status=?"
            args.append(status)
        return self.conn.execute(sql + " ORDER BY review_id", args)

    def calls(self, run_id=None):
        if run_id:
            return self.conn.execute("SELECT * FROM calls WHERE run_id=? ORDER BY started_at", (run_id,)).fetchall()
        return self.conn.execute("SELECT * FROM calls ORDER BY started_at").fetchall()

    def spend_totals(self):
        row = self.conn.execute(
            "SELECT COALESCE(SUM(CASE WHEN outcome IN ('succeeded','failed') THEN COALESCE(cost_usd,0) END),0) AS spent, "
            "COALESCE(SUM(CASE WHEN outcome='unknown' THEN reserved_usd END),0) AS unknown FROM calls").fetchone()
        return float(row["spent"]), float(row["unknown"])

    # ---- verification / stage cache / invocations ----------------------------------------------
    def verification(self, review_id, verifier_config):
        return self.conn.execute("SELECT * FROM verifications WHERE review_id=? AND verifier_config=?",
                                 (review_id, verifier_config)).fetchone()

    def insert_verification(self, row: dict):
        cols = list(row)
        self.conn.execute(f"INSERT OR IGNORE INTO verifications({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                          [row[c] for c in cols])

    def verifications(self, verifier_config):
        return self.conn.execute("SELECT * FROM verifications WHERE verifier_config=? ORDER BY review_id",
                                 (verifier_config,)).fetchall()

    def cache_get(self, stage, key):
        row = self.conn.execute("SELECT output FROM stage_cache WHERE stage=? AND cache_key=?", (stage, key)).fetchone()
        return json.loads(row["output"]) if row else None

    def cache_put(self, stage, key, output, request_id, run_id):
        self.conn.execute("INSERT OR REPLACE INTO stage_cache(stage, cache_key, output, request_id, run_id, created_at) "
                          "VALUES(?,?,?,?,?,?)", (stage, key, json.dumps(output, ensure_ascii=False), request_id, run_id, utc_now()))

    def start_invocation(self, row: dict):
        cols = list(row)
        self.conn.execute(f"INSERT INTO invocations({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                          [row[c] for c in cols])

    def finish_invocation(self, run_id, fields: dict):
        cols = list(fields)
        self.conn.execute(f"UPDATE invocations SET {', '.join(c + '=?' for c in cols)} WHERE run_id=?",
                          [fields[c] for c in cols] + [run_id])

    def invocations(self):
        return self.conn.execute("SELECT * FROM invocations ORDER BY started_at").fetchall()


class _Tx:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        self.conn.execute("BEGIN IMMEDIATE")
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        self.conn.execute("ROLLBACK" if exc_type else "COMMIT")
        return False
