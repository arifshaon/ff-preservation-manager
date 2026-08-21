from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from registry_builder.nara_risk_assessment_preview import (
    NARA_SOURCE_ID,
    NARA_SOURCE_TYPE,
    PROJECTION_VERSION,
    _load_config as _load_pipeline_config,
    build_nara_risk_projection,
)
from registry_builder.risk_synthesis import (
    risk_assessments_from_canonical_fields,
    synthesize_risk_assessments,
)
from registry_builder.storage import create_store
from registry_builder.storage.base import RegistryStore


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "nara_risk_assessment_backfill.production.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _run_id() -> str:
    return "risk-backfill-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_backfill_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("NARA risk backfill config must contain a JSON object")
    data["_config_path"] = str(config_path)
    return data


def _resolve_relative(config_path: str | Path, candidate: str | Path) -> Path:
    path = Path(candidate)
    if path.is_absolute():
        return path
    return (Path(config_path).resolve().parent / path).resolve()


def _claim_key(claim: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(claim.get("canonical_id") or ""),
        str(claim.get("source_id") or ""),
        str(claim.get("source_record_id") or ""),
        str(claim.get("projection_version") or ""),
    )


def _current_source_claims(store: RegistryStore) -> list[dict[str, Any]]:
    return [
        row
        for row in store.query("risk_assessment_claims", {"source_id": NARA_SOURCE_ID})
        if row.get("current", True) is not False
    ]


def _superseded_claims(
    existing: list[dict[str, Any]],
    active: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    active_keys = {_claim_key(row) for row in active}
    return [row for row in existing if _claim_key(row) not in active_keys]


def _is_nara_assessment(item: dict[str, Any]) -> bool:
    return (
        str(item.get("source_id") or "") == NARA_SOURCE_ID
        or str(item.get("source_type") or "") == NARA_SOURCE_TYPE
    )


def _is_nara_hazard(item: dict[str, Any]) -> bool:
    return (
        str(item.get("source_id") or "") == NARA_SOURCE_ID
        or str(item.get("source_type") or "") == NARA_SOURCE_TYPE
        or str(item.get("source") or "") == "NARA Digital Preservation Framework"
    )


def _normalized_non_nara_assessments(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Build materialization baseline while excluding legacy NARA projections.

    The authoritative NARA source-native claims are added separately. Raw NARA
    source records and legacy external_hazard fields remain stored for backwards
    auditability; they are simply not re-used in this materialized risk view.
    """
    explicit = [
        dict(item)
        for item in (row.get("risk_assessments") or [])
        if not _is_nara_assessment(item)
    ]
    external_hazard = [
        dict(item)
        for item in (row.get("external_hazard") or [])
        if not _is_nara_hazard(item)
    ]
    return risk_assessments_from_canonical_fields(
        explicit_assessments=explicit,
        external_hazard=external_hazard,
        institution_policy_overlays=row.get("institution_policy_overlays") or [],
        source_records=row.get("source_records") or [],
        canonical_name=row.get("preferred_name"),
    )


def _decorate_claim(claim: dict[str, Any]) -> dict[str, Any]:
    stored = deepcopy(claim)
    stored["projection_version"] = PROJECTION_VERSION
    assessment = deepcopy(stored.get("assessment") or {})
    assessment["source_id"] = NARA_SOURCE_ID
    assessment["source_type"] = NARA_SOURCE_TYPE
    assessment["source_record_id"] = stored.get("source_record_id")
    assessment["projection_version"] = PROJECTION_VERSION
    assessment["persistence_layer"] = "risk_assessment_claims"
    stored["assessment"] = assessment
    return stored


def _canonical_updates(
    canonical_by_id: dict[str, dict[str, Any]],
    active_claims: list[dict[str, Any]],
    existing_claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    active_by_id: dict[str, list[dict[str, Any]]] = {}
    for claim in active_claims:
        active_by_id.setdefault(str(claim["canonical_id"]), []).append(claim)

    touched_ids = set(active_by_id)
    touched_ids.update(
        str(row.get("canonical_id") or "")
        for row in existing_claims
        if row.get("canonical_id")
    )

    updates: list[dict[str, Any]] = []
    for canonical_id in sorted(touched_ids):
        original = canonical_by_id.get(canonical_id)
        if not original:
            continue
        updated = deepcopy(original)
        assessments = _normalized_non_nara_assessments(updated)
        assessments.extend(
            deepcopy(claim["assessment"])
            for claim in active_by_id.get(canonical_id, [])
        )
        updated["risk_assessments"] = assessments
        updated["synthesized_risk"] = synthesize_risk_assessments(assessments)
        provenance = dict(updated.get("provenance") or {})
        materialized = list(provenance.get("materialized_risk_claim_sources") or [])
        if NARA_SOURCE_ID not in materialized:
            materialized.append(NARA_SOURCE_ID)
        provenance["materialized_risk_claim_sources"] = sorted(materialized)
        provenance["nara_risk_projection_version"] = PROJECTION_VERSION
        updated["provenance"] = provenance
        updates.append(updated)
    return updates


def run_nara_risk_backfill(
    *,
    store: RegistryStore,
    dry_run: bool = False,
    replace_source_claims: bool = True,
    materialize_canonical: bool = True,
) -> dict[str, Any]:
    raw_claims, projection_report, canonical_by_id = build_nara_risk_projection(store)
    claims = [_decorate_claim(row) for row in raw_claims]
    existing = _current_source_claims(store)
    superseded = _superseded_claims(existing, claims) if replace_source_claims else []

    gate_passed = bool(projection_report.get("migration_gate_passed"))
    canonical_updates = (
        _canonical_updates(canonical_by_id, claims, existing)
        if materialize_canonical and gate_passed
        else []
    )

    before_after: list[dict[str, Any]] = []
    headline_changes = 0
    for updated in canonical_updates:
        canonical_id = str(updated.get("canonical_id") or "")
        before = canonical_by_id.get(canonical_id, {}).get("synthesized_risk") or {}
        after = updated.get("synthesized_risk") or {}
        before_level = before.get("semantic_level")
        after_level = after.get("semantic_level")
        if before_level != after_level:
            headline_changes += 1
        before_after.append({
            "canonical_id": canonical_id,
            "preferred_name": updated.get("preferred_name"),
            "before": before_level,
            "after": after_level,
            "selected_scope_tier": after.get("selected_scope_tier"),
            "source_divergence": after.get("source_divergence"),
            "scope_divergence": after.get("scope_divergence"),
            "contextual_levels": after.get("contextual_levels") or [],
        })

    result = {
        "status": "dry_run" if dry_run else ("completed" if gate_passed else "blocked"),
        "source_id": NARA_SOURCE_ID,
        "projection_version": PROJECTION_VERSION,
        "migration_gate_passed": gate_passed,
        "replace_source_claims": bool(replace_source_claims),
        "materialize_canonical": bool(materialize_canonical),
        "claims_generated": len(claims),
        "current_claims_before": len(existing),
        "claims_to_supersede": len(superseded),
        "canonical_records_to_update": len(canonical_updates),
        "canonical_headline_changes": headline_changes,
        "semantic_levels": dict(sorted(Counter(str(row.get("semantic_level") or "unknown") for row in claims).items())),
        "scope_types": dict(sorted(Counter(str(row.get("scope_type") or "unknown") for row in claims).items())),
        "projection_report": projection_report,
        "sample_changes": before_after[:20],
    }

    if dry_run or not gate_passed:
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
        "risk_source_id": NARA_SOURCE_ID,
        "projection_version": PROJECTION_VERSION,
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
        prog="python -m registry_builder.nara_risk_assessment_backfill",
        description=(
            "Persist source-native NARA risk assessments as versioned risk_assessment_claims "
            "after the strict source-provenance migration gate passes."
        ),
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out")
    args = parser.parse_args()

    config = _load_backfill_config(args.config)
    pipeline_config_path = _resolve_relative(config["_config_path"], config["storage_config"])
    pipeline_config = _load_pipeline_config(pipeline_config_path)

    store = create_store(pipeline_config["storage"])
    try:
        report = run_nara_risk_backfill(
            store=store,
            dry_run=args.dry_run,
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
