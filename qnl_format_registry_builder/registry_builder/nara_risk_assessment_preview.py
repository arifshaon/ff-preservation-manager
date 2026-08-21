from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Any

from registry_builder.risk_synthesis import risk_assessments_from_canonical_fields
from registry_builder.storage import create_store
from registry_builder.storage.base import RegistryStore


NARA_SOURCE_ID = "nara_digital_preservation_framework"
NARA_SOURCE_TYPE = "nara_digital_preservation_framework"
PROJECTION_VERSION = "nara-native-risk-v2-source-provenance"


def _load_config(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Pipeline config must contain a JSON object")
    storage = data.get("storage")
    if not isinstance(storage, dict):
        raise ValueError("Pipeline config must contain a storage object")
    return data


def _latest_completed_source_run_id(store: RegistryStore, source_id: str) -> str | None:
    latest: tuple[tuple[str, str], str] | None = None
    for run in store.query("runs"):
        run_id = str(run.get("run_id") or "")
        if not run_id:
            continue
        source_completed = any(
            str(item.get("source_id") or "") == source_id and item.get("status") == "completed"
            for item in (run.get("sources") or [])
        )
        if not source_completed:
            continue
        sort_key = (str(run.get("finished_at") or run.get("started_at") or run_id), run_id)
        if latest is None or sort_key > latest[0]:
            latest = (sort_key, run_id)
    return latest[1] if latest else None


def _nara_source_record_ids(row: dict[str, Any]) -> list[str]:
    """Return NARA source refs present on a canonical record.

    This is retained for auditing the legacy canonical view. It is deliberately
    not used to create v2 claims because source_records may also contain related
    cross-reference-only records.
    """

    ids: list[str] = []
    for source in row.get("source_records") or []:
        if (
            str(source.get("source_id") or "") == NARA_SOURCE_ID
            or str(source.get("source_type") or "") == NARA_SOURCE_TYPE
        ):
            value = source.get("source_record_id")
            if value:
                ids.append(str(value))
    return list(dict.fromkeys(ids))


def _verified_canonical_nara_ids(row: dict[str, Any]) -> list[str]:
    """Return NARA identities that actually contribute to canonical identity.

    A NARA source record may appear under ``source_records`` only because it has
    an explicit cross-reference to a PUID owned by another canonical. Those
    relationship-only refs must not become exact-format NARA risk claims. The
    canonical ``identifiers.nara`` values, backed by verified NARA identifier
    claims, are the authoritative record of identity-contributing NARA rows.
    """

    ids: list[str] = []
    identifiers = row.get("identifiers") or {}
    if isinstance(identifiers, dict):
        for value in identifiers.get("nara") or []:
            if value:
                ids.append(str(value))

    # Compatibility fallback for older canonical rows that retained verified
    # identifier claims but did not yet serialize the identifiers index.
    for claim in row.get("identifier_claims") or []:
        if claim.get("kind") != "nara" or claim.get("verified") is False:
            continue
        value = claim.get("value") or claim.get("source_record_id")
        if value:
            ids.append(str(value))

    return list(dict.fromkeys(ids))


def _normalized_nara_assessments(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Project the existing legacy canonical NARA risk view for parity audit."""

    assessments = risk_assessments_from_canonical_fields(
        explicit_assessments=row.get("risk_assessments") or [],
        external_hazard=row.get("external_hazard") or [],
        institution_policy_overlays=row.get("institution_policy_overlays") or [],
        source_records=row.get("source_records") or [],
        canonical_name=row.get("preferred_name"),
    )
    return [
        dict(item)
        for item in assessments
        if (
            str(item.get("source_id") or "") == NARA_SOURCE_ID
            or str(item.get("source_type") or "") == NARA_SOURCE_TYPE
        )
    ]


def _source_native_nara_assessments(
    source_row: dict[str, Any],
    *,
    canonical_name: str | None,
) -> list[dict[str, Any]]:
    """Build normalized NARA assessments from one persisted NARA source row."""

    source_record_id = str(source_row.get("source_record_id") or "")
    if not source_record_id:
        return []

    hazards: list[dict[str, Any]] = []
    if source_row.get("hazard"):
        hazard = dict(source_row["hazard"])
        hazard.setdefault("source_id", NARA_SOURCE_ID)
        hazard.setdefault("source_type", NARA_SOURCE_TYPE)
        hazard.setdefault("source_record_id", source_record_id)
        hazards.append(hazard)

    explicit: list[dict[str, Any]] = []
    for item in source_row.get("risk_assessments") or []:
        assessment = dict(item)
        assessment.setdefault("source_id", NARA_SOURCE_ID)
        assessment.setdefault("source_type", NARA_SOURCE_TYPE)
        assessment.setdefault("source_record_id", source_record_id)
        explicit.append(assessment)

    assessments = risk_assessments_from_canonical_fields(
        explicit_assessments=explicit,
        external_hazard=hazards,
        source_records=[
            {
                "source_id": NARA_SOURCE_ID,
                "source_type": NARA_SOURCE_TYPE,
                "source_record_id": source_record_id,
            }
        ],
        canonical_name=canonical_name,
    )
    return [
        dict(item)
        for item in assessments
        if (
            str(item.get("source_id") or "") == NARA_SOURCE_ID
            or str(item.get("source_type") or "") == NARA_SOURCE_TYPE
        )
    ]


def _assessment_signature(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item.get("native_label"),
        item.get("native_score"),
        item.get("native_scale"),
        item.get("normalized_band"),
        item.get("normalized_score"),
        item.get("semantic_level"),
        item.get("scope_type") or "exact_format",
    )


def _claim_from_assessment(
    *,
    row: dict[str, Any],
    source_record_id: str,
    assessment: dict[str, Any],
) -> dict[str, Any]:
    item = dict(assessment)
    item["source_id"] = NARA_SOURCE_ID
    item["source_type"] = NARA_SOURCE_TYPE
    item["source_record_id"] = source_record_id
    item.setdefault("scope_type", "exact_format")
    item.setdefault("scope_name", row.get("preferred_name"))
    return {
        "canonical_id": str(row.get("canonical_id") or ""),
        "preferred_name": row.get("preferred_name"),
        "source_id": NARA_SOURCE_ID,
        "source_type": NARA_SOURCE_TYPE,
        "source_record_id": source_record_id,
        "source_record_id_basis": "verified_canonical_nara_identifier+latest_source_record",
        "projection_version": PROJECTION_VERSION,
        "native_label": item.get("native_label"),
        "native_score": item.get("native_score"),
        "native_scale": item.get("native_scale"),
        "normalized_band": item.get("normalized_band"),
        "normalized_score": item.get("normalized_score"),
        "semantic_level": item.get("semantic_level"),
        "scope_type": item.get("scope_type") or "exact_format",
        "scope_name": item.get("scope_name") or row.get("preferred_name"),
        "assessment": item,
    }


def build_nara_risk_inventory(store: RegistryStore) -> dict[str, Any]:
    canonical_rows = store.get_current_registry_view()
    latest_run_id = _latest_completed_source_run_id(store, NARA_SOURCE_ID)
    latest_source_rows = store.query("source_records", {"source_id": NARA_SOURCE_ID})
    if latest_run_id:
        latest_source_rows = [
            row for row in latest_source_rows if str(row.get("run_id") or "") == latest_run_id
        ]
    latest_by_id = {
        str(row.get("source_record_id")): row
        for row in latest_source_rows
        if row.get("source_record_id")
    }

    claims: list[dict[str, Any]] = []
    legacy_claims: list[dict[str, Any]] = []
    multiple_assessment_formats: list[dict[str, Any]] = []
    conflicting_level_formats: list[dict[str, Any]] = []
    missing_latest_source_records: list[dict[str, Any]] = []
    identity_linked_without_risk: list[dict[str, Any]] = []
    parity_mismatches: list[dict[str, Any]] = []
    source_targets: dict[str, set[str]] = defaultdict(set)
    legacy_missing_source_record_id: list[dict[str, Any]] = []

    for row in canonical_rows:
        canonical_id = str(row.get("canonical_id") or "")
        canonical_name = row.get("preferred_name")

        legacy_assessments = _normalized_nara_assessments(row)
        candidate_source_ids = _nara_source_record_ids(row)
        for assessment in legacy_assessments:
            source_record_id = assessment.get("source_record_id")
            if not source_record_id and len(candidate_source_ids) == 1:
                source_record_id = candidate_source_ids[0]
            if not source_record_id:
                legacy_missing_source_record_id.append({
                    "canonical_id": canonical_id,
                    "preferred_name": canonical_name,
                    "candidate_source_record_ids": candidate_source_ids,
                    "native_label": assessment.get("native_label"),
                    "semantic_level": assessment.get("semantic_level"),
                })
            legacy_claims.append({
                "canonical_id": canonical_id,
                "source_record_id": source_record_id,
                "assessment": dict(assessment),
            })

        canonical_claims: list[dict[str, Any]] = []
        for source_record_id in _verified_canonical_nara_ids(row):
            source_row = latest_by_id.get(source_record_id)
            if source_row is None:
                missing_latest_source_records.append({
                    "canonical_id": canonical_id,
                    "preferred_name": canonical_name,
                    "source_record_id": source_record_id,
                })
                continue

            assessments = _source_native_nara_assessments(
                source_row,
                canonical_name=canonical_name,
            )
            if not assessments:
                identity_linked_without_risk.append({
                    "canonical_id": canonical_id,
                    "preferred_name": canonical_name,
                    "source_record_id": source_record_id,
                })
                continue

            for assessment in assessments:
                claim = _claim_from_assessment(
                    row=row,
                    source_record_id=source_record_id,
                    assessment=assessment,
                )
                claims.append(claim)
                canonical_claims.append(claim)
                source_targets[source_record_id].add(canonical_id)

        if len(canonical_claims) > 1:
            levels = sorted({str(item.get("semantic_level") or "unmapped") for item in canonical_claims})
            multiple_assessment_formats.append({
                "canonical_id": canonical_id,
                "preferred_name": canonical_name,
                "assessment_count": len(canonical_claims),
                "source_record_ids": sorted(str(item["source_record_id"]) for item in canonical_claims),
                "semantic_levels": levels,
            })
            if len(levels) > 1:
                conflicting_level_formats.append({
                    "canonical_id": canonical_id,
                    "preferred_name": canonical_name,
                    "assessment_count": len(canonical_claims),
                    "source_record_ids": sorted(str(item["source_record_id"]) for item in canonical_claims),
                    "semantic_levels": levels,
                })

        legacy_signatures = Counter(_assessment_signature(item) for item in legacy_assessments)
        source_signatures = Counter(_assessment_signature(item["assessment"]) for item in canonical_claims)
        if legacy_signatures != source_signatures:
            parity_mismatches.append({
                "canonical_id": canonical_id,
                "preferred_name": canonical_name,
                "legacy_assessment_count": len(legacy_assessments),
                "source_native_assessment_count": len(canonical_claims),
                "legacy_signatures": [list(key) + [count] for key, count in sorted(legacy_signatures.items(), key=str)],
                "source_native_signatures": [list(key) + [count] for key, count in sorted(source_signatures.items(), key=str)],
            })

    duplicated_source_targets = [
        {"source_record_id": source_id, "canonical_ids": sorted(targets), "target_count": len(targets)}
        for source_id, targets in sorted(source_targets.items())
        if len(targets) > 1
    ]

    current_persisted = [
        row for row in store.query("risk_assessment_claims", {"source_id": NARA_SOURCE_ID})
        if row.get("current", True) is not False
    ]

    semantic_levels = Counter(str(row.get("semantic_level") or "unmapped") for row in claims)
    native_labels = Counter(str(row.get("native_label") or "unknown") for row in claims)
    native_scales = Counter(str(row.get("native_scale") or "unknown") for row in claims)
    scope_types = Counter(str(row.get("scope_type") or "unknown") for row in claims)
    legacy_semantic_levels = Counter(
        str(row["assessment"].get("semantic_level") or "unmapped") for row in legacy_claims
    )
    legacy_native_labels = Counter(
        str(row["assessment"].get("native_label") or "unknown") for row in legacy_claims
    )

    report = {
        "mode": "read_only_store_preview",
        "storage_write": False,
        "identity_projection": False,
        "source_id": NARA_SOURCE_ID,
        "projection_version": PROJECTION_VERSION,
        "current_canonical_format_count": len(canonical_rows),
        "latest_source_run_id": latest_run_id,
        "latest_nara_source_record_count": len(latest_source_rows),
        "projected_claim_count": len(claims),
        "canonical_formats_with_nara_assessment": len({row["canonical_id"] for row in claims}),
        "assessments_missing_source_record_id": sum(1 for row in claims if not row.get("source_record_id")),
        "legacy_projected_claim_count": len(legacy_claims),
        "legacy_assessments_missing_source_record_id": len(legacy_missing_source_record_id),
        "canonical_formats_with_multiple_nara_assessments": len(multiple_assessment_formats),
        "canonical_formats_with_conflicting_nara_levels": len(conflicting_level_formats),
        "nara_source_records_targeting_multiple_canonicals": len(duplicated_source_targets),
        "latest_source_records_missing_for_identity_links": len(missing_latest_source_records),
        "identity_linked_nara_records_without_risk": len(identity_linked_without_risk),
        "canonical_parity_mismatches": len(parity_mismatches),
        "semantic_distribution_matches_legacy": semantic_levels == legacy_semantic_levels,
        "native_label_distribution_matches_legacy": native_labels == legacy_native_labels,
        "current_persisted_nara_claims": len(current_persisted),
        "semantic_levels": dict(sorted(semantic_levels.items())),
        "native_labels": dict(sorted(native_labels.items())),
        "native_scales": dict(sorted(native_scales.items())),
        "scope_types": dict(sorted(scope_types.items())),
        "legacy_missing_source_record_id_samples": legacy_missing_source_record_id[:25],
        "multiple_assessment_samples": multiple_assessment_formats[:25],
        "conflicting_level_samples": conflicting_level_formats[:25],
        "duplicated_source_target_samples": duplicated_source_targets[:25],
        "missing_latest_source_record_samples": missing_latest_source_records[:25],
        "identity_linked_without_risk_samples": identity_linked_without_risk[:25],
        "parity_mismatch_samples": parity_mismatches[:25],
        "sample_claims": claims[:25],
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m registry_builder.nara_risk_assessment_preview",
        description=(
            "Read-only source-provenance inventory of NARA risk assessments before migration "
            "to versioned risk_assessment_claims. No storage writes are performed."
        ),
    )
    parser.add_argument("--config", default="config/sources.qnl.nara-only.json")
    parser.add_argument("--out")
    args = parser.parse_args()

    config = _load_config(args.config)
    store = create_store(config["storage"])
    try:
        report = build_nara_risk_inventory(store)
    finally:
        store.close()

    text = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
