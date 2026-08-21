from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from registry_builder.dpc_risk_mapping_mongo import (
    _canonical_from_store,
    _latest_source_records,
    _load_config as _load_pipeline_config,
)
from registry_builder.external_risk_mapping import apply_external_risk_mappings, load_external_risk_mapping
from registry_builder.risk_synthesis import synthesize_risk_assessments
from registry_builder.storage import create_store
from registry_builder.storage.base import RegistryStore


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "dpc_risk_assessment_backfill.production.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _run_id() -> str:
    return "risk-backfill-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_backfill_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("DPC risk backfill config must contain a JSON object")
    data["_config_path"] = str(config_path)
    return data


def _resolve_relative(config_path: str | Path, candidate: str | Path) -> Path:
    path = Path(candidate)
    if path.is_absolute():
        return path
    return (Path(config_path).resolve().parent / path).resolve()


def _claim_key(claim: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(claim.get("canonical_id") or ""),
        str(claim.get("source_id") or ""),
        str(claim.get("source_record_id") or ""),
        str(claim.get("mapping_rule_id") or ""),
        str(claim.get("mapping_version") or ""),
    )


def _is_mapped_source_assessment(assessment: dict[str, Any], source_id: str) -> bool:
    return (
        str(assessment.get("source_id") or "") == source_id
        and bool(assessment.get("mapping_rule_id"))
    )


def _current_source_claims(store: RegistryStore, source_id: str) -> list[dict[str, Any]]:
    return [
        row
        for row in store.query("risk_assessment_claims", {"source_id": source_id})
        if row.get("current", True) is not False
    ]


def build_dpc_risk_claims(
    store: RegistryStore,
    mapping: dict[str, Any],
    *,
    include_drafts: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, dict[str, Any]]]:
    source_id = str(mapping.get("source_id") or "dpc_bit_list_2025")
    canonical_rows = store.get_current_registry_view()
    registry = [_canonical_from_store(row) for row in canonical_rows]
    original_by_id = {
        str(row.get("canonical_id")): deepcopy(row)
        for row in canonical_rows
        if row.get("canonical_id")
    }

    # Remove only previously mapped DPC assertions before replaying the approved
    # mapping. Source-native evidence records remain untouched in source_records.
    for fmt in registry:
        fmt.risk_assessments = [
            dict(item)
            for item in fmt.risk_assessments
            if not _is_mapped_source_assessment(item, source_id)
        ]
        fmt.synthesized_risk = synthesize_risk_assessments(fmt.risk_assessments)

    latest_run_id, dpc_records = _latest_source_records(store, source_id)
    report = apply_external_risk_mappings(
        registry,
        dpc_records,
        mapping,
        include_drafts=include_drafts,
    )

    claims: list[dict[str, Any]] = []
    projected_by_id: dict[str, dict[str, Any]] = {}
    for fmt in registry:
        mapped = [
            dict(item)
            for item in fmt.risk_assessments
            if _is_mapped_source_assessment(item, source_id)
        ]
        if mapped:
            projected_by_id[fmt.canonical_id] = fmt.to_dict()
        for assessment in mapped:
            claims.append({
                "canonical_id": fmt.canonical_id,
                "source_id": source_id,
                "source_type": assessment.get("source_type") or mapping.get("source_type"),
                "source_record_id": assessment.get("source_record_id"),
                "mapping_rule_id": assessment.get("mapping_rule_id"),
                "mapping_version": assessment.get("mapping_version") or mapping.get("mapping_version"),
                "scope_type": assessment.get("scope_type"),
                "scope_name": assessment.get("scope_name"),
                "native_label": assessment.get("native_label"),
                "semantic_level": assessment.get("semantic_level"),
                "assessment": assessment,
            })

    claims.sort(key=lambda item: _claim_key(item))
    report = dict(report)
    report.update({
        "source_id": source_id,
        "latest_source_run_id": latest_run_id,
        "dpc_evidence_record_count": len(dpc_records),
        "dpc_evidence_only_count": sum(1 for row in dpc_records if row.record_role == "evidence_only"),
        "canonical_format_count": len(registry),
        "claims_generated": len(claims),
        "identity_projection": False,
    })
    return claims, report, original_by_id


def _superseded_claims(
    existing: list[dict[str, Any]],
    active: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    active_keys = {_claim_key(row) for row in active}
    return [row for row in existing if _claim_key(row) not in active_keys]


def _canonical_updates(
    original_by_id: dict[str, dict[str, Any]],
    active_claims: list[dict[str, Any]],
    existing_claims: list[dict[str, Any]],
    source_id: str,
) -> list[dict[str, Any]]:
    active_by_id: dict[str, list[dict[str, Any]]] = {}
    for claim in active_claims:
        active_by_id.setdefault(str(claim["canonical_id"]), []).append(claim)

    touched_ids = set(active_by_id)
    touched_ids.update(str(row.get("canonical_id") or "") for row in existing_claims if row.get("canonical_id"))

    updates: list[dict[str, Any]] = []
    for canonical_id in sorted(touched_ids):
        original = original_by_id.get(canonical_id)
        if not original:
            continue
        updated = deepcopy(original)
        assessments = [
            dict(item)
            for item in (updated.get("risk_assessments") or [])
            if not _is_mapped_source_assessment(item, source_id)
        ]
        assessments.extend(
            deepcopy(claim["assessment"])
            for claim in active_by_id.get(canonical_id, [])
        )
        updated["risk_assessments"] = assessments
        updated["synthesized_risk"] = synthesize_risk_assessments(assessments)
        updates.append(updated)
    return updates


def run_dpc_risk_backfill(
    *,
    store: RegistryStore,
    mapping: dict[str, Any],
    dry_run: bool = False,
    include_drafts: bool = False,
    replace_source_claims: bool = True,
    materialize_canonical: bool = True,
) -> dict[str, Any]:
    source_id = str(mapping.get("source_id") or "dpc_bit_list_2025")
    claims, mapping_report, original_by_id = build_dpc_risk_claims(
        store,
        mapping,
        include_drafts=include_drafts,
    )
    existing = _current_source_claims(store, source_id)
    superseded = _superseded_claims(existing, claims) if replace_source_claims else []
    canonical_updates = _canonical_updates(
        original_by_id,
        claims,
        existing,
        source_id,
    ) if materialize_canonical else []

    before_after = []
    for updated in canonical_updates:
        canonical_id = str(updated.get("canonical_id") or "")
        before = original_by_id.get(canonical_id, {}).get("synthesized_risk") or {}
        after = updated.get("synthesized_risk") or {}
        before_after.append({
            "canonical_id": canonical_id,
            "preferred_name": updated.get("preferred_name"),
            "before": before.get("semantic_level"),
            "after": after.get("semantic_level"),
            "method_after": after.get("method"),
            "selected_scope_tier": after.get("selected_scope_tier"),
            "contextual_levels": after.get("contextual_levels") or [],
        })

    result = {
        "status": "dry_run" if dry_run else "completed",
        "source_id": source_id,
        "mapping_version": mapping.get("mapping_version"),
        "replace_source_claims": bool(replace_source_claims),
        "materialize_canonical": bool(materialize_canonical),
        "claims_generated": len(claims),
        "current_claims_before": len(existing),
        "claims_to_supersede": len(superseded),
        "canonical_records_to_update": len(canonical_updates),
        "mapping_report": mapping_report,
        "semantic_levels": dict(sorted(Counter(str(row.get("semantic_level") or "unknown") for row in claims).items())),
        "scope_types": dict(sorted(Counter(str(row.get("scope_type") or "unknown") for row in claims).items())),
        "sample_changes": before_after[:15],
    }
    if dry_run:
        return result

    run_id = _run_id()
    now = _utc_now_iso()
    store.create_run({
        "run_id": run_id,
        "run_kind": "risk_assessment_backfill",
        "started_at": now,
        "finished_at": now,
        "status": "completed",
        "sources": [],
        "risk_source_id": source_id,
        "mapping_version": mapping.get("mapping_version"),
        "claims_generated": len(claims),
        "claims_superseded": len(superseded),
    })

    for row in superseded:
        stored = deepcopy(row)
        stored["current"] = False
        stored["superseded_by_run_id"] = run_id
        stored["superseded_at"] = now
        stored["superseded_reason"] = "source_replaced_by_risk_backfill"
        key = "|".join(_claim_key(stored))
        store.upsert("risk_assessment_claims", key, stored)

    for claim in claims:
        stored = deepcopy(claim)
        stored["run_id"] = run_id
        stored["current"] = True
        stored["last_seen_run_id"] = run_id
        stored["updated_at"] = now
        key = "|".join(_claim_key(stored))
        store.upsert("risk_assessment_claims", key, stored)

    if materialize_canonical:
        for updated in canonical_updates:
            store.upsert_canonical_format(updated)

    result.update({
        "run_id": run_id,
        "claims_superseded": len(superseded),
        "claims_written": len(claims),
        "canonical_records_updated": len(canonical_updates),
    })
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m registry_builder.dpc_risk_assessment_backfill",
        description=(
            "Build versioned DPC mapped risk-assessment claims and optionally materialize "
            "the current canonical risk view. DPC source records remain evidence_only."
        ),
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out")
    args = parser.parse_args()

    config = _load_backfill_config(args.config)
    pipeline_config_path = _resolve_relative(config["_config_path"], config["storage_config"])
    pipeline_config = _load_pipeline_config(pipeline_config_path)
    mapping_path = _resolve_relative(config["_config_path"], config["mapping"])
    mapping = load_external_risk_mapping(mapping_path)

    store = create_store(pipeline_config["storage"])
    try:
        report = run_dpc_risk_backfill(
            store=store,
            mapping=mapping,
            dry_run=args.dry_run,
            include_drafts=bool(config.get("include_drafts", False)),
            replace_source_claims=bool(config.get("replace_source_claims", True)),
            materialize_canonical=bool(config.get("materialize_canonical", True)),
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
