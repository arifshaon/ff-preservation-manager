from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from registry_builder.models import CanonicalFormat

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS format_registry (
  canonical_id TEXT PRIMARY KEY,
  preferred_name TEXT NOT NULL,
  category TEXT,
  description TEXT,
  record_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS format_identifier (
  canonical_id TEXT NOT NULL,
  identifier_type TEXT NOT NULL,
  identifier_value TEXT NOT NULL,
  PRIMARY KEY (canonical_id, identifier_type, identifier_value)
);
CREATE TABLE IF NOT EXISTS source_record (
  canonical_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_record_id TEXT,
  urls_json TEXT
);
CREATE TABLE IF NOT EXISTS institution_policy_overlay (
  canonical_id TEXT NOT NULL,
  institution_id TEXT,
  institution_name TEXT,
  institution_format_id TEXT,
  local_risk_level TEXT,
  local_preservation_action TEXT,
  local_preservation_plan TEXT,
  local_preferred_tools TEXT,
  local_conversion_process TEXT,
  source_file TEXT,
  source_row INTEGER
);
"""


def write_sqlite(path: str | Path, registry: list[CanonicalFormat]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.executescript(SCHEMA_SQL)
        con.execute("DELETE FROM format_registry")
        con.execute("DELETE FROM format_identifier")
        con.execute("DELETE FROM source_record")
        con.execute("DELETE FROM institution_policy_overlay")
        for fmt in registry:
            d = fmt.to_dict()
            con.execute(
                "INSERT INTO format_registry VALUES (?, ?, ?, ?, ?)",
                (fmt.canonical_id, fmt.preferred_name, fmt.category, fmt.description, json.dumps(d, ensure_ascii=False)),
            )
            for kind, values in fmt.identifiers.items():
                for value in values:
                    con.execute("INSERT OR IGNORE INTO format_identifier VALUES (?, ?, ?)", (fmt.canonical_id, kind, value))
            for sr in fmt.source_records:
                con.execute(
                    "INSERT INTO source_record VALUES (?, ?, ?, ?, ?)",
                    (fmt.canonical_id, sr.get("source_id"), sr.get("source_type"), sr.get("source_record_id"), json.dumps(sr.get("urls", {}))),
                )
            for policy in fmt.institution_policy_overlays:
                con.execute(
                    "INSERT INTO institution_policy_overlay VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        fmt.canonical_id,
                        policy.get("institution_id"),
                        policy.get("institution_name"),
                        policy.get("institution_format_id"),
                        policy.get("local_risk_level"),
                        policy.get("local_preservation_action"),
                        policy.get("local_preservation_plan"),
                        policy.get("local_preferred_tools"),
                        policy.get("local_conversion_process"),
                        policy.get("source_file"),
                        policy.get("source_row"),
                    ),
                )
        con.commit()
    finally:
        con.close()
