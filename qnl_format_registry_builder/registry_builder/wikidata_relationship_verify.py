from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any

from registry_builder.pipeline import _storage_config, load_config
from registry_builder.storage import create_store
from registry_builder.storage.base import RegistryStore
from registry_builder.wikidata_relationship_backfill import (
    DEFAULT_CONFIG,
    WIKIDATA_EVIDENCE_PROJECTION_VERSION,
    WIKIDATA_RELATIONSHIP_PROJECTION_VERSION,
    WIKIDATA_SOURCE_ID,
    WIKIDATA_SOURCE_TYPE,
    _load_backfill_config,
    _resolve_relative,
)


def _latest_wikidata_backfill_run(store: RegistryStore) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for run in store.query("runs"):
        if run.get("status") != "completed":
            continue
        if str(run.get("relationship_source_id") or "") == WIKIDATA_SOURCE_ID:
            candidates.append(run)
            continue
        for source in run.get("sources") or []:
            if (
                source.get("status") == "completed"
                and str(source.get("source_id") or "") == WIKIDATA_SOURCE_ID
            ):
                candidates.append(run)
                break
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda row: (
            str(row.get("finished_at") or row.get("started_at") or ""),
            str(row.get("run_id") or ""),
        ),
    )


def verify_wikidata_relationship_persistence(
    store: RegistryStore,
    *,
    expected_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    expected = dict(expected_counts or {})
    errors: list[str] = []

    canonical = store.get_current_registry_view()
    current_claims = [
        row
        for row in store.query("source_relationship_claims")
        if row.get("current", True) is not False
        and str(row.get("source_id") or "") == WIKIDATA_SOURCE_ID
    ]
    latest_run = _latest_wikidata_backfill_run(store)
    latest_run_id = str((latest_run or {}).get("run_id") or "")
    latest_source_records = [
        row
        for row in store.query("source_records")
        if str(row.get("source_id") or "") == WIKIDATA_SOURCE_ID
        and (not latest_run_id or str(row.get("run_id") or "") == latest_run_id)
    ]

    qids = {
        str(row.get("source_record_id") or "")
        for row in current_claims
        if row.get("source_record_id")
    }
    canonical_targets = {
        str(row.get("canonical_id") or row.get("format_id") or "")
        for row in current_claims
        if row.get("canonical_id") or row.get("format_id")
    }

    materialized_refs = []
    materialized_canonical_ids: set[str] = set()
    promoted_strong_claims = []
    for fmt in canonical:
        canonical_id = str(fmt.get("canonical_id") or fmt.get("format_id") or "")
        refs = [
            ref
            for ref in (fmt.get("source_records") or [])
            if str(ref.get("persistence_layer") or "") == "source_relationship_claims"
            and str(ref.get("source_id") or "") == WIKIDATA_SOURCE_ID
        ]
        if refs:
            materialized_canonical_ids.add(canonical_id)
            materialized_refs.extend(refs)

        for claim in fmt.get("identifier_claims") or []:
            if str(claim.get("kind") or "") not in {"puid", "loc", "nara"}:
                continue
            source = str(claim.get("source") or claim.get("source_id") or "")
            if source in {WIKIDATA_SOURCE_ID, WIKIDATA_SOURCE_TYPE}:
                promoted_strong_claims.append(
                    {
                        "canonical_id": canonical_id,
                        "kind": claim.get("kind"),
                        "value": claim.get("value"),
                        "verified": claim.get("verified", False),
                    }
                )

    evidence_role_counts = Counter(
        str(row.get("record_role") or "unknown") for row in latest_source_records
    )
    evidence_projection_counts = Counter(
        str((row.get("native_fields") or {}).get("evidence_projection_version") or "unknown")
        for row in latest_source_records
    )
    relationship_projection_counts = Counter(
        str(row.get("projection_version") or "unknown") for row in current_claims
    )
    source_records_with_risk = sum(
        1 for row in latest_source_records if row.get("risk_assessments")
    )

    actual = {
        "canonical_formats": len(canonical),
        "wikidata_source_records": len(latest_source_records),
        "wikidata_relationship_claims": len(current_claims),
        "wikidata_qids_with_relationships": len(qids),
        "canonical_formats_with_wikidata_relationships": len(canonical_targets),
        "materialized_relationship_edges": len(materialized_refs),
        "materialized_canonical_formats": len(materialized_canonical_ids),
    }

    expected_map = {
        "canonical_formats": expected.get("canonical_formats"),
        "wikidata_source_records": expected.get("wikidata_records"),
        "wikidata_relationship_claims": expected.get("relationship_edges"),
        "wikidata_qids_with_relationships": expected.get("wikidata_qids_with_relationships"),
        "canonical_formats_with_wikidata_relationships": expected.get(
            "canonical_formats_with_wikidata_relationships"
        ),
        "materialized_relationship_edges": expected.get("relationship_edges"),
        "materialized_canonical_formats": expected.get(
            "canonical_formats_with_wikidata_relationships"
        ),
    }
    for key, expected_value in expected_map.items():
        if expected_value is None:
            continue
        if int(actual[key]) != int(expected_value):
            errors.append(f"{key}: expected {expected_value}, got {actual[key]}")

    if not latest_run_id:
        errors.append("No completed Wikidata relationship backfill run found")
    if evidence_role_counts and evidence_role_counts != Counter({"evidence_only": len(latest_source_records)}):
        errors.append(f"Wikidata source records are not all evidence_only: {dict(evidence_role_counts)}")
    if evidence_projection_counts and evidence_projection_counts != Counter(
        {WIKIDATA_EVIDENCE_PROJECTION_VERSION: len(latest_source_records)}
    ):
        errors.append(
            "Unexpected Wikidata evidence projection versions: "
            + str(dict(evidence_projection_counts))
        )
    if relationship_projection_counts and relationship_projection_counts != Counter(
        {WIKIDATA_RELATIONSHIP_PROJECTION_VERSION: len(current_claims)}
    ):
        errors.append(
            "Unexpected Wikidata relationship projection versions: "
            + str(dict(relationship_projection_counts))
        )
    if promoted_strong_claims:
        errors.append(
            f"Found {len(promoted_strong_claims)} copied Wikidata strong identifiers promoted onto canonicals"
        )
    if source_records_with_risk:
        errors.append(
            f"Found {source_records_with_risk} Wikidata source records with risk assessments"
        )

    return {
        "status": "ok" if not errors else "failed",
        "errors": errors,
        "latest_wikidata_run_id": latest_run_id or None,
        **actual,
        "source_record_roles": dict(sorted(evidence_role_counts.items())),
        "evidence_projection_versions": dict(sorted(evidence_projection_counts.items())),
        "relationship_projection_versions": dict(sorted(relationship_projection_counts.items())),
        "promoted_wikidata_strong_identifier_claims": len(promoted_strong_claims),
        "wikidata_source_records_with_risk_assessments": source_records_with_risk,
        "sample_promoted_identifier_claims": promoted_strong_claims[:20],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m registry_builder.wikidata_relationship_verify",
        description=(
            "Verify persisted Wikidata evidence-only records and governed source "
            "relationships without modifying the registry."
        ),
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--out")
    args = parser.parse_args()

    config = _load_backfill_config(args.config)
    pipeline_config_path = _resolve_relative(config["_config_path"], config["storage_config"])
    pipeline_config = load_config(pipeline_config_path)
    store = create_store(_storage_config(pipeline_config))
    try:
        report = verify_wikidata_relationship_persistence(
            store,
            expected_counts=dict(config.get("expected_counts") or {}),
        )
    finally:
        store.close()

    text = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)
    if report["status"] != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
