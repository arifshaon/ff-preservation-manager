from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from registry_builder.identifier_rules import load_identifier_rules
from registry_builder.models import CanonicalFormat, RawFormatRecord
from registry_builder.pipeline import _storage_config, load_config
from registry_builder.source_relationship_claim_materialization import (
    materialize_current_source_relationship_claims,
)
from registry_builder.storage import create_store
from registry_builder.storage.base import RegistryStore
from registry_builder.wikidata_projection import (
    WIKIDATA_POPULATION_POLICY_VERSION,
    project_wikidata_csv,
)
from registry_builder.wikidata_relationship_preview import preview_wikidata_relationships


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "wikidata_relationship_backfill.production.json"
WIKIDATA_SOURCE_ID = "wikidata_file_formats"
WIKIDATA_SOURCE_TYPE = "wikidata_sparql"
WIKIDATA_EVIDENCE_PROJECTION_VERSION = "2026-08-21-v2-evidence-only"
WIKIDATA_RELATIONSHIP_PROJECTION_VERSION = "2026-08-21-v1-authority-cross-reference"
_CANONICAL_FIELDS = set(CanonicalFormat.__dataclass_fields__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _run_id() -> str:
    return "relationship-backfill-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_backfill_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Wikidata relationship backfill config must contain a JSON object")
    data["_config_path"] = str(config_path)
    return data


def _resolve_relative(config_path: str | Path, candidate: str | Path) -> Path:
    path = Path(candidate)
    if path.is_absolute():
        return path
    return (Path(config_path).resolve().parent / path).resolve()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relationship_claim_id(edge: dict[str, Any]) -> str:
    payload = {
        "canonical_id": edge.get("canonical_id"),
        "source_id": edge.get("source_id"),
        "source_record_id": edge.get("source_record_id"),
        "relationship": edge.get("relationship"),
        "evidence_scope": edge.get("evidence_scope"),
        "copied_identifiers": sorted(
            [dict(item) for item in (edge.get("copied_identifiers") or [])],
            key=lambda item: (str(item.get("kind") or ""), str(item.get("value") or "")),
        ),
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "src-rel-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _decorate_claim(edge: dict[str, Any]) -> dict[str, Any]:
    claim = deepcopy(edge)
    claim["claim_id"] = _relationship_claim_id(edge)
    claim["projection_version"] = WIKIDATA_RELATIONSHIP_PROJECTION_VERSION
    claim["population_policy_version"] = WIKIDATA_POPULATION_POLICY_VERSION
    claim["identity_projection"] = False
    claim["identifier_promotion"] = False
    return claim


def _current_source_claims(store: RegistryStore) -> list[dict[str, Any]]:
    return [
        row
        for row in store.query("source_relationship_claims")
        if row.get("current", True) is not False
        and str(row.get("source_id") or "") == WIKIDATA_SOURCE_ID
    ]


def _superseded_claims(
    existing: list[dict[str, Any]],
    active: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    active_ids = {str(row.get("claim_id") or "") for row in active}
    return [row for row in existing if str(row.get("claim_id") or "") not in active_ids]


def _canonical_from_dict(row: dict[str, Any]) -> CanonicalFormat:
    payload = {key: deepcopy(row[key]) for key in _CANONICAL_FIELDS if key in row}
    return CanonicalFormat(**payload)


def _evidence_only_records(path: Path) -> list[RawFormatRecord]:
    records = project_wikidata_csv(
        path,
        source_id=WIKIDATA_SOURCE_ID,
        source_type=WIKIDATA_SOURCE_TYPE,
    )
    for record in records:
        record.record_role = "evidence_only"
        native = dict(record.native_fields or {})
        native["identity_projection"] = False
        native["evidence_projection_version"] = WIKIDATA_EVIDENCE_PROJECTION_VERSION
        native["relationship_projection_version"] = WIKIDATA_RELATIONSHIP_PROJECTION_VERSION
        record.native_fields = native
    return records


def _gate_report(
    preview: dict[str, Any],
    config: dict[str, Any],
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    expected = config.get("expected_counts") or {}
    checks = {
        "canonical_formats": preview.get("canonical_formats"),
        "wikidata_records": preview.get("wikidata_records"),
        "wikidata_qids_with_relationships": preview.get("wikidata_qids_with_relationships"),
        "canonical_formats_with_wikidata_relationships": preview.get("canonical_formats_with_wikidata_relationships"),
        "relationship_edges": preview.get("relationship_edges"),
        "matched_authority_claims": preview.get("matched_authority_claims"),
    }
    for key, actual in checks.items():
        if key not in expected:
            continue
        if int(actual or 0) != int(expected[key]):
            errors.append(f"{key}: expected {expected[key]}, got {actual}")

    max_unmatched = int(config.get("max_unmatched_authority_claims", 0))
    unmatched = int(preview.get("unmatched_authority_claims") or 0)
    if unmatched > max_unmatched:
        errors.append(f"unmatched_authority_claims: allowed <= {max_unmatched}, got {unmatched}")

    for key in (
        "identity_merges_performed",
        "canonical_formats_created",
        "canonical_identifiers_promoted",
        "risk_assessments_generated",
        "criterion_claims_generated",
        "mongo_writes",
    ):
        if int(preview.get(key) or 0) != 0:
            errors.append(f"{key}: expected 0, got {preview.get(key)}")

    return not errors, errors


def run_wikidata_relationship_backfill(
    *,
    store: RegistryStore,
    input_csv: str | Path,
    identifier_rules: dict[str, dict[str, Any]] | None = None,
    dry_run: bool = False,
    replace_source_claims: bool = True,
    materialize_canonical: bool = True,
    expected_counts: dict[str, int] | None = None,
    max_unmatched_authority_claims: int = 0,
) -> dict[str, Any]:
    input_path = Path(input_csv)
    records = _evidence_only_records(input_path)
    canonical_rows = store.get_current_registry_view()
    rules = identifier_rules or load_identifier_rules()
    preview = preview_wikidata_relationships(
        canonical_rows,
        records,
        identifier_rules=rules,
    )

    gate_config = {
        "expected_counts": expected_counts or {},
        "max_unmatched_authority_claims": max_unmatched_authority_claims,
    }
    gate_passed, gate_errors = _gate_report(preview, gate_config)
    claims = [_decorate_claim(edge) for edge in preview.get("relationships") or []]
    existing = _current_source_claims(store)
    superseded = _superseded_claims(existing, claims) if replace_source_claims else []
    touched_ids = {
        str(row.get("canonical_id") or "")
        for row in claims + existing
        if row.get("canonical_id")
    }

    result = {
        "status": "dry_run" if dry_run else ("completed" if gate_passed else "blocked"),
        "source_id": WIKIDATA_SOURCE_ID,
        "source_type": WIKIDATA_SOURCE_TYPE,
        "evidence_projection_version": WIKIDATA_EVIDENCE_PROJECTION_VERSION,
        "relationship_projection_version": WIKIDATA_RELATIONSHIP_PROJECTION_VERSION,
        "population_policy_version": WIKIDATA_POPULATION_POLICY_VERSION,
        "migration_gate_passed": gate_passed,
        "migration_gate_errors": gate_errors,
        "replace_source_claims": bool(replace_source_claims),
        "materialize_canonical": bool(materialize_canonical),
        "source_records_generated": len(records),
        "claims_generated": len(claims),
        "current_claims_before": len(existing),
        "claims_to_supersede": len(superseded),
        "canonical_records_to_update": len(touched_ids) if materialize_canonical else 0,
        "preview": {
            key: preview.get(key)
            for key in (
                "canonical_formats",
                "wikidata_records",
                "wikidata_qids_with_relationships",
                "canonical_formats_with_wikidata_relationships",
                "relationship_edges",
                "matched_authority_claims",
                "matched_authority_claims_by_kind",
                "unmatched_authority_claims",
                "unmatched_authority_claims_by_kind",
                "qid_outcomes",
                "qids_with_relationships_by_wikidata_role",
                "identity_merges_performed",
                "canonical_formats_created",
                "canonical_identifiers_promoted",
            )
        },
    }

    if dry_run or not gate_passed:
        return result

    run_id = _run_id()
    now = _utc_now_iso()
    input_sha256 = _sha256_file(input_path)
    store.create_run({
        "run_id": run_id,
        "run_kind": "source_relationship_backfill",
        "started_at": now,
        "finished_at": now,
        "status": "completed",
        "sources": [
            {
                "source_id": WIKIDATA_SOURCE_ID,
                "source_type": WIKIDATA_SOURCE_TYPE,
                "status": "completed",
                "records_extracted": len(records),
                "snapshots": 1,
            }
        ],
        "relationship_source_id": WIKIDATA_SOURCE_ID,
        "relationship_projection_version": WIKIDATA_RELATIONSHIP_PROJECTION_VERSION,
        "population_policy_version": WIKIDATA_POPULATION_POLICY_VERSION,
        "claims_generated": len(claims),
        "claims_superseded": len(superseded),
        "input_file": str(input_path),
        "input_sha256": input_sha256,
    })
    store.save_snapshot({
        "run_id": run_id,
        "source_id": WIKIDATA_SOURCE_ID,
        "source_type": WIKIDATA_SOURCE_TYPE,
        "uri": str(input_path),
        "sha256": input_sha256,
        "changed": True,
        "from_cache": True,
        "population_policy_version": WIKIDATA_POPULATION_POLICY_VERSION,
    })

    for record in records:
        stored_record = record.to_dict()
        stored_record["run_id"] = run_id
        store.save_source_record(stored_record)

    for row in superseded:
        stored = deepcopy(row)
        stored["current"] = False
        stored["superseded_by_run_id"] = run_id
        stored["superseded_at"] = now
        stored["superseded_reason"] = "source_replaced_by_relationship_backfill"
        store.upsert("source_relationship_claims", str(stored.get("claim_id") or ""), stored)

    for claim in claims:
        stored = deepcopy(claim)
        stored["run_id"] = run_id
        stored["current"] = True
        stored["last_seen_run_id"] = run_id
        stored["updated_at"] = now
        store.upsert("source_relationship_claims", str(stored["claim_id"]), stored)

    materialization_report: dict[str, Any] = {"enabled": False}
    canonical_records_updated = 0
    if materialize_canonical:
        canonical_objects = [_canonical_from_dict(row) for row in canonical_rows]
        materialization_report = materialize_current_source_relationship_claims(
            canonical_objects,
            store,
        )
        for fmt in canonical_objects:
            if fmt.canonical_id not in touched_ids:
                continue
            original = next(
                row for row in canonical_rows
                if str(row.get("canonical_id") or row.get("format_id") or "") == fmt.canonical_id
            )
            updated = fmt.to_dict() | {
                "run_id": original.get("run_id"),
                "format_id": fmt.canonical_id,
                "current": original.get("current", True),
                "last_seen_run_id": original.get("last_seen_run_id"),
            }
            store.upsert_canonical_format(updated)
            canonical_records_updated += 1

    result.update({
        "run_id": run_id,
        "input_sha256": input_sha256,
        "source_records_written": len(records),
        "claims_superseded": len(superseded),
        "claims_written": len(claims),
        "canonical_records_updated": canonical_records_updated,
        "materialization": materialization_report,
    })
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m registry_builder.wikidata_relationship_backfill",
        description=(
            "Persist frozen Wikidata rows as evidence-only source records and "
            "versioned source_relationship_claims without creating canonical identity."
        ),
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out")
    args = parser.parse_args()

    config = _load_backfill_config(args.config)
    pipeline_config_path = _resolve_relative(config["_config_path"], config["storage_config"])
    input_csv = _resolve_relative(config["_config_path"], config["input_csv"])
    pipeline_config = load_config(pipeline_config_path)
    rules = load_identifier_rules(pipeline_config.get("identifier_kinds"))

    store = create_store(_storage_config(pipeline_config))
    try:
        report = run_wikidata_relationship_backfill(
            store=store,
            input_csv=input_csv,
            identifier_rules=rules,
            dry_run=args.dry_run,
            replace_source_claims=bool(config.get("replace_source_claims", True)),
            materialize_canonical=bool(config.get("materialize_canonical", True)),
            expected_counts=dict(config.get("expected_counts") or {}),
            max_unmatched_authority_claims=int(config.get("max_unmatched_authority_claims", 0)),
        )
    finally:
        store.close()

    text = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
