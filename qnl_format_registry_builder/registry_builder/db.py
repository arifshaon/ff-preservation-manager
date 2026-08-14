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
CREATE TABLE IF NOT EXISTS qnl_policy_overlay (
  canonical_id TEXT NOT NULL,
  qnl_format_id TEXT,
  spreadsheet_risk_level TEXT,
  preservation_action TEXT,
  proposed_preservation_plan TEXT,
  preferred_tools TEXT,
  conversion_process TEXT,
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
        con.execute("DELETE FROM qnl_policy_overlay")
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
            for qnl in fmt.qnl_policy_overlay:
                con.execute(
                    "INSERT INTO qnl_policy_overlay VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        fmt.canonical_id,
                        qnl.get("qnl_format_id"),
                        qnl.get("spreadsheet_risk_level"),
                        qnl.get("preservation_action"),
                        qnl.get("proposed_preservation_plan"),
                        qnl.get("preferred_tools"),
                        qnl.get("conversion_process"),
                        qnl.get("source_file"),
                        qnl.get("source_row"),
                    ),
                )
        con.commit()
    finally:
        con.close()
