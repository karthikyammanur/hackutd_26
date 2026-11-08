-- Anonymous incident indicators. See sandbox/evidence/CONTRACT.md for what must never appear here.
-- WITHOUT ROWID where the primary key is the only lookup needed: every index costs a written row on D1.

CREATE TABLE incidents (
  incident_id TEXT PRIMARY KEY,
  occurred_hour TEXT NOT NULL,
  channel TEXT NOT NULL,
  source TEXT NOT NULL,
  method TEXT NOT NULL,
  family TEXT NOT NULL,
  predicted_method TEXT,
  tier TEXT NOT NULL,
  outcome TEXT,
  max_risk REAL NOT NULL,
  first_alert_bucket_s INTEGER,
  duration_bucket_s INTEGER,
  money_moved_before_alert INTEGER,
  model TEXT NOT NULL,
  caller_cluster TEXT,
  summary TEXT NOT NULL,
  created_at TEXT NOT NULL
) WITHOUT ROWID;

-- Keyset pagination needs (filter, occurred_hour, incident_id). Low-cardinality filters (channel, tier) walk
-- the time index and stop at the page limit, so they don't justify an extra write per incident.
CREATE INDEX idx_incidents_time ON incidents (occurred_hour, incident_id);
CREATE INDEX idx_incidents_source ON incidents (source, occurred_hour, incident_id);
CREATE INDEX idx_incidents_method ON incidents (method, occurred_hour, incident_id);
CREATE INDEX idx_incidents_family ON incidents (family, occurred_hour, incident_id);
CREATE INDEX idx_incidents_outcome ON incidents (outcome, occurred_hour, incident_id);

-- occurred_hour is copied here so a signal filter can seek and paginate without sorting.
CREATE TABLE incident_signals (
  incident_id TEXT NOT NULL,
  signal TEXT NOT NULL,
  strength REAL NOT NULL,
  occurred_hour TEXT NOT NULL,
  PRIMARY KEY (incident_id, signal)
) WITHOUT ROWID;
CREATE INDEX idx_signals_signal ON incident_signals (signal, occurred_hour, incident_id);

CREATE TABLE incident_timeline (
  incident_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  t_bucket_s INTEGER NOT NULL,
  tier TEXT NOT NULL,
  risk REAL NOT NULL,
  PRIMARY KEY (incident_id, seq)
) WITHOUT ROWID;

-- outcome is '' rather than NULL: NULLs would make primary key rows distinct and split the counts.
CREATE TABLE rollup_daily (
  day TEXT NOT NULL,
  source TEXT NOT NULL,
  channel TEXT NOT NULL,
  method TEXT NOT NULL,
  family TEXT NOT NULL,
  tier TEXT NOT NULL,
  outcome TEXT NOT NULL,
  n INTEGER NOT NULL,
  PRIMARY KEY (day, source, channel, method, family, tier, outcome)
) WITHOUT ROWID;

CREATE TABLE rollup_signal_daily (
  day TEXT NOT NULL,
  source TEXT NOT NULL,
  method TEXT NOT NULL,
  signal TEXT NOT NULL,
  n INTEGER NOT NULL,
  PRIMARY KEY (day, source, method, signal)
) WITHOUT ROWID;

CREATE VIRTUAL TABLE incidents_fts USING fts5(
  incident_id UNINDEXED, method, family, tier, signals, summary
);

-- Free-tier guard. rows includes reservations for writes in progress.
CREATE TABLE write_budget (
  day TEXT PRIMARY KEY,
  rows INTEGER NOT NULL,
  size_bytes INTEGER NOT NULL DEFAULT 0
) WITHOUT ROWID;
