CREATE TABLE format_registry (
  canonical_id TEXT PRIMARY KEY,
  preferred_name TEXT NOT NULL,
  category TEXT,
  description TEXT,
  record_json TEXT NOT NULL
);

CREATE TABLE format_identifier (
  canonical_id TEXT NOT NULL REFERENCES format_registry(canonical_id),
  identifier_type TEXT NOT NULL,
  identifier_value TEXT NOT NULL,
  PRIMARY KEY (canonical_id, identifier_type, identifier_value)
);

CREATE TABLE source_record (
  canonical_id TEXT NOT NULL REFERENCES format_registry(canonical_id),
  source_id TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_record_id TEXT,
  urls_json TEXT
);

CREATE TABLE qnl_policy_overlay (
  canonical_id TEXT NOT NULL REFERENCES format_registry(canonical_id),
  qnl_format_id TEXT,
  spreadsheet_risk_level TEXT,
  preservation_action TEXT,
  proposed_preservation_plan TEXT,
  preferred_tools TEXT,
  conversion_process TEXT,
  source_file TEXT,
  source_row INTEGER
);

-- Intended next-step tables. They are not populated by the first registry build.
CREATE TABLE assessment_run (
  assessment_run_id TEXT PRIMARY KEY,
  run_started_at TEXT NOT NULL,
  run_finished_at TEXT,
  config_hash TEXT,
  notes TEXT
);

CREATE TABLE hazard_assessment (
  assessment_id TEXT PRIMARY KEY,
  canonical_id TEXT NOT NULL REFERENCES format_registry(canonical_id),
  assessment_run_id TEXT NOT NULL REFERENCES assessment_run(assessment_run_id),
  hazard_band TEXT,
  rating REAL,
  basis TEXT,
  confidence TEXT,
  divergence_flag INTEGER DEFAULT 0,
  review_required INTEGER DEFAULT 0,
  scale_version TEXT NOT NULL
);

CREATE TABLE hazard_answer (
  answer_id TEXT PRIMARY KEY,
  assessment_id TEXT NOT NULL REFERENCES hazard_assessment(assessment_id),
  criterion_id TEXT NOT NULL,
  question_id TEXT NOT NULL,
  answer_value TEXT,
  answer_score REAL,
  evidence_claim_ids_json TEXT,
  confidence TEXT,
  abstained INTEGER DEFAULT 0
);

CREATE TABLE assessment_change (
  change_id TEXT PRIMARY KEY,
  canonical_id TEXT NOT NULL REFERENCES format_registry(canonical_id),
  assessment_run_id TEXT NOT NULL REFERENCES assessment_run(assessment_run_id),
  change_type TEXT NOT NULL,
  previous_value TEXT,
  new_value TEXT,
  basis TEXT,
  recommended_action TEXT,
  review_required INTEGER DEFAULT 0
);
