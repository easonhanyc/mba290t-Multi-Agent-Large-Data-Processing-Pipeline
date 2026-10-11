-- Dashboard database: processed review data, aggregates and analysis outputs of ONE pipeline run.
-- Portable SQL (PostgreSQL in production on Neon; SQLite for local tests). Loaded by web/load_db.py.

CREATE TABLE IF NOT EXISTS runs (
  run_key TEXT PRIMARY KEY,
  label_config TEXT NOT NULL,
  analysis_input TEXT NOT NULL,
  analysis_sha256 TEXT NOT NULL,
  analysis_rows INTEGER NOT NULL,
  full_source TEXT,
  full_sha256 TEXT,
  offline_stub INTEGER NOT NULL,
  loaded_at TEXT NOT NULL,
  run_json TEXT NOT NULL,
  data_manifest_json TEXT
);

-- One row per source review in the declared scope: the six source fields plus the final record.
CREATE TABLE IF NOT EXISTS reviews (
  review_id TEXT PRIMARY KEY,
  row_num INTEGER NOT NULL,
  review_text TEXT NOT NULL,
  review_rating TEXT NOT NULL,
  review_likes INTEGER NOT NULL,
  app_version TEXT NOT NULL,
  review_timestamp TEXT NOT NULL,
  month TEXT NOT NULL,
  source_sha256 TEXT NOT NULL,
  status TEXT NOT NULL,
  reason TEXT,
  topic TEXT,
  subtopic TEXT,
  issue_id TEXT,
  area TEXT,
  intent TEXT,
  severity INTEGER,
  sentiment DOUBLE PRECISION,
  evidence_quote TEXT,
  entities TEXT,
  needs_review INTEGER,
  labeled_by TEXT,
  cache_source_id TEXT,
  label_config TEXT
);
CREATE INDEX IF NOT EXISTS reviews_issue ON reviews(issue_id);
CREATE INDEX IF NOT EXISTS reviews_month ON reviews(month);
CREATE INDEX IF NOT EXISTS reviews_intent ON reviews(intent);
CREATE INDEX IF NOT EXISTS reviews_status ON reviews(status);

CREATE TABLE IF NOT EXISTS membership (
  issue_id TEXT NOT NULL,
  review_id TEXT NOT NULL,
  PRIMARY KEY (issue_id, review_id)
);
CREATE INDEX IF NOT EXISTS membership_review ON membership(review_id);

CREATE TABLE IF NOT EXISTS issues (
  issue_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  default_name TEXT,
  summary TEXT,
  area TEXT NOT NULL,
  definition TEXT,
  named_by TEXT,
  evidence_json TEXT
);

CREATE TABLE IF NOT EXISTS ranking (
  issue_id TEXT PRIMARY KEY,
  rank INTEGER NOT NULL,
  complaint_count INTEGER NOT NULL,
  severity_sum INTEGER NOT NULL,
  mean_severity TEXT NOT NULL,
  priority_score INTEGER NOT NULL,
  cancellation_count INTEGER,
  needs_review_count INTEGER,
  share_of_complaints TEXT
);

CREATE TABLE IF NOT EXISTS area_rollup (
  area TEXT PRIMARY KEY,
  complaint_count INTEGER NOT NULL,
  severity_sum INTEGER NOT NULL,
  issues INTEGER NOT NULL,
  cancellation_count INTEGER NOT NULL,
  share_of_complaints TEXT NOT NULL,
  decision_option INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS trends_monthly (
  month TEXT PRIMARY KEY,
  partial_month TEXT,
  reviews INTEGER NOT NULL,
  complaints INTEGER NOT NULL,
  complaint_share DOUBLE PRECISION NOT NULL,
  cancellations INTEGER NOT NULL,
  areas_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claims (
  claim_id TEXT PRIMARY KEY,
  issue_id TEXT NOT NULL,
  metric TEXT NOT NULL,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recommendation (
  id INTEGER PRIMARY KEY,
  recommended_area TEXT NOT NULL,
  source TEXT NOT NULL,
  memo_config TEXT,
  generated_at TEXT,
  output_json TEXT NOT NULL,
  tokens_json TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  memo_md TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS verification (
  review_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  topic TEXT,
  intent TEXT,
  severity INTEGER,
  sentiment DOUBLE PRECISION,
  confidence TEXT,
  request_id TEXT
);

-- Saved JSON documents: analysis outputs, evaluation results and run evidence.
CREATE TABLE IF NOT EXISTS documents (
  name TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  source_file TEXT,
  body TEXT NOT NULL
);
