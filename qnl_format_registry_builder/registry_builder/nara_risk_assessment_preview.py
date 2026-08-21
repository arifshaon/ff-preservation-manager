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
PROJECTION_VERSION = "nara-native-risk-v1"


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


def _normalized_nara_assessments(row: dict[str, Any]) -> list[dict[str, Any]]:
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


def build_nara_risk_inventory(store: RegistryStore) -> dict[str, Any]:
    canonical_rows = store.get_current_registry_view()
    latest_run_id = _latest_completed_source_run_id(store, NARA_SOURCE_ID)
    latest_source_rows = store.query("source_records", {"source_id": NARA_SOURCE_ID})
    if latest_run_id:
        latest_source_rows = [
            row for row in latest_source_rows if str(row.get("run_id") or "") == latest_run_id
        ]

    claims: list[dict[str, Any]] = []
    multiple_assessment_formats: list[dict[str, Any]] = []
    missing_source_record_id: list[dict[str, Any]] = []
    source_targets: dict[str, set[str]] = defaultdict(set)

    for row in canonical_rows:
        canonical_id = str(row.get("canonical_id") or "")
        assessments = _normalized_nara_assessments(row)
        if len(assessments) > 1:
            multiple_assessment_formats.append({
                "canonical_id": canonical_id,
                "preferred_name": row.get("preferred_name"),
                "assessment_count": len(assessments),
            })

        candidate_source_ids = _nara_source_record_ids(row)
        for assessment in assessments:
            item = dict(assessment)
            source_record_id = item.get("source_record_id")
            source_record_id_basis = "assessment"
            if not source_record_id and len(candidate_source_ids) == 1:
                source_record_id = candidate_source_ids[0]
                source_record_id_basis = "single_canonical_nara_source_record"
            if not source_record_id:
                missing_source_record_id.append({
                    "canonical_id": canonical_id,
                    "preferred_name": row.get("preferred_name"),
                    "candidate_source_record_ids": candidate_source_ids,
                    "native_label": item.get("native_label"),
                    "semantic_level": item.get("semantic_level"),
                })

            if source_record_id:
                source_targets[str(source_record_id)].add(canonical_id)

            claims.append({
                "canonical_id": canonical_id,
                "preferred_name": row.get("preferred_name"),
                "source_id": NARA_SOURCE_ID,
                "source_type": NARA_SOURCE_TYPE,
                "source_record_id": source_record_id,
                "source_record_id_basis": source_record_id_basis if source_record_id else None,
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
        "assessments_missing_source_record_id": len(missing_source_record_id),
        "canonical_formats_with_multiple_nara_assessments": len(multiple_assessment_formats),
        "nara_source_records_targeting_multiple_canonicals": len(duplicated_source_targets),
        "current_persisted_nara_claims": len(current_persisted),
        "semantic_levels": dict(sorted(Counter(str(row.get("semantic_level") or "unmapped") for row in claims).items())),
        "native_labels": dict(sorted(Counter(str(row.get("native_label") or "unknown") for row in claims).items())),
        "native_scales": dict(sorted(Counter(str(row.get("native_scale") or "unknown") for row in claims).items())),
        "scope_types": dict(sorted(Counter(str(row.get("scope_type") or "unknown") for row in claims).items())),
        "missing_source_record_id_samples": missing_source_record_id[:25],
        "multiple_assessment_samples": multiple_assessment_formats[:25],
        "duplicated_source_target_samples": duplicated_source_targets[:25],
        "sample_claims": claims[:25],
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m registry_builder.nara_risk_assessment_preview",
        description=(
            "Read-only inventory of current NARA risk assessments before migration "
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
