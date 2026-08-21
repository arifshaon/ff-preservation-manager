from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from registry_builder.adapters import resolve_adapter
from registry_builder.adapters.wikidata_sparql import WIKIDATA_POPULATION_POLICY_VERSION
from registry_builder.identifier_rules import load_identifier_rules
from registry_builder.models import RawFormatRecord, SourceSnapshot
from registry_builder.pipeline import _storage_config, load_config
from registry_builder.storage import create_store
from registry_builder.storage.base import RegistryStore
from registry_builder.wikidata_relationship_backfill import (
    WIKIDATA_SOURCE_ID,
    _current_source_claims,
    _decorate_claim,
    _resolve_relative,
    run_wikidata_relationship_backfill,
)
from registry_builder.wikidata_relationship_preview import preview_wikidata_relationships
from registry_builder.wikidata_relationship_verify import verify_wikidata_relationship_persistence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "wikidata_refresh.production.json"
PRODUCTION_ADAPTER_TYPE = "wikidata_sparql_evidence"


def _load_refresh_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Wikidata refresh config must contain a JSON object")
    data["_config_path"] = str(config_path)
    return data


def _fraction(value: int, baseline: int) -> float | None:
    if baseline <= 0:
        return None
    return abs(value) / baseline


def _drift_check(
    *,
    label: str,
    baseline: int,
    planned: int,
    max_absolute: int | None,
    max_fraction: float | None,
) -> tuple[dict[str, Any], list[str]]:
    delta = planned - baseline
    absolute_delta = abs(delta)
    fraction = _fraction(delta, baseline)
    errors: list[str] = []

    if max_absolute is not None and absolute_delta > int(max_absolute):
        errors.append(
            f"{label}: absolute change {absolute_delta} exceeds allowed {int(max_absolute)} "
            f"(baseline={baseline}, planned={planned})"
        )
    if (
        max_fraction is not None
        and fraction is not None
        and fraction > float(max_fraction)
    ):
        errors.append(
            f"{label}: fractional change {fraction:.4f} exceeds allowed "
            f"{float(max_fraction):.4f} (baseline={baseline}, planned={planned})"
        )

    return {
        "baseline": baseline,
        "planned": planned,
        "delta": delta,
        "absolute_delta": absolute_delta,
        "fractional_change": fraction,
        "max_absolute": max_absolute,
        "max_fraction": max_fraction,
    }, errors


def _planned_expected_counts(preview: dict[str, Any]) -> dict[str, int]:
    return {
        "canonical_formats": int(preview.get("canonical_formats") or 0),
        "wikidata_records": int(preview.get("wikidata_records") or 0),
        "wikidata_qids_with_relationships": int(
            preview.get("wikidata_qids_with_relationships") or 0
        ),
        "canonical_formats_with_wikidata_relationships": int(
            preview.get("canonical_formats_with_wikidata_relationships") or 0
        ),
        "relationship_edges": int(preview.get("relationship_edges") or 0),
        "matched_authority_claims": int(preview.get("matched_authority_claims") or 0),
    }


def _production_record_errors(records: list[RawFormatRecord]) -> list[str]:
    errors: list[str] = []
    non_evidence = [
        str(record.source_record_id or "")
        for record in records
        if record.record_role != "evidence_only"
    ]
    if non_evidence:
        errors.append(
            f"{len(non_evidence)} Wikidata records are not evidence_only; "
            f"samples={non_evidence[:10]}"
        )

    with_risk = [
        str(record.source_record_id or "")
        for record in records
        if record.risk_assessments
    ]
    if with_risk:
        errors.append(
            f"{len(with_risk)} Wikidata records contain risk assessments; "
            f"samples={with_risk[:10]}"
        )

    wrong_policy = [
        str(record.source_record_id or "")
        for record in records
        if str((record.native_fields or {}).get("population_policy_version") or "")
        != WIKIDATA_POPULATION_POLICY_VERSION
    ]
    if wrong_policy:
        errors.append(
            f"{len(wrong_policy)} Wikidata records carry an unexpected population policy; "
            f"samples={wrong_policy[:10]}"
        )

    return errors


def _claim_turnover(
    current_claims: list[dict[str, Any]],
    planned_claims: list[dict[str, Any]],
) -> dict[str, Any]:
    current_ids = {str(row.get("claim_id") or "") for row in current_claims}
    planned_ids = {str(row.get("claim_id") or "") for row in planned_claims}
    current_ids.discard("")
    planned_ids.discard("")
    added = sorted(planned_ids - current_ids)
    removed = sorted(current_ids - planned_ids)
    unchanged = sorted(current_ids & planned_ids)
    return {
        "current": len(current_ids),
        "planned": len(planned_ids),
        "added": len(added),
        "removed": len(removed),
        "unchanged": len(unchanged),
        "turnover": len(added) + len(removed),
        "added_samples": added[:20],
        "removed_samples": removed[:20],
    }


def _snapshot_for_backfill(snapshots: list[SourceSnapshot]) -> SourceSnapshot:
    if len(snapshots) != 1:
        raise ValueError(
            "Controlled Wikidata refresh requires exactly one final merged acquisition snapshot; "
            f"received {len(snapshots)}"
        )
    snapshot = snapshots[0]
    if not Path(snapshot.local_path).exists():
        raise FileNotFoundError(
            f"Wikidata acquisition snapshot does not exist: {snapshot.local_path}"
        )
    return snapshot


def run_wikidata_refresh(
    *,
    store: RegistryStore,
    source_config: dict[str, Any],
    workdir: str | Path,
    identifier_rules: dict[str, dict[str, Any]] | None = None,
    apply: bool = False,
    require_verified_baseline: bool = True,
    max_unmatched_authority_claims: int = 0,
    drift_gates: dict[str, Any] | None = None,
    snapshots: list[SourceSnapshot] | None = None,
) -> dict[str, Any]:
    source = dict(source_config)
    source.setdefault("id", WIKIDATA_SOURCE_ID)
    source.setdefault("type", PRODUCTION_ADAPTER_TYPE)
    if str(source.get("id") or "") != WIKIDATA_SOURCE_ID:
        raise ValueError(
            f"Controlled Wikidata refresh requires source id {WIKIDATA_SOURCE_ID!r}"
        )
    if str(source.get("type") or "") != PRODUCTION_ADAPTER_TYPE:
        raise ValueError(
            f"Controlled Wikidata refresh requires adapter type {PRODUCTION_ADAPTER_TYPE!r}"
        )

    adapter_cls = resolve_adapter(PRODUCTION_ADAPTER_TYPE)
    adapter = adapter_cls(source, Path(workdir))
    acquired = list(snapshots) if snapshots is not None else adapter.acquire()
    final_snapshot = _snapshot_for_backfill(acquired)
    records = adapter.extract(acquired)

    rules = identifier_rules or load_identifier_rules()
    canonical_rows = store.get_current_registry_view()
    preview = preview_wikidata_relationships(
        canonical_rows,
        records,
        identifier_rules=rules,
    )
    planned_claims = [
        _decorate_claim(edge) for edge in (preview.get("relationships") or [])
    ]
    current_claims = _current_source_claims(store)
    turnover = _claim_turnover(current_claims, planned_claims)
    baseline = verify_wikidata_relationship_persistence(store)

    gate_errors = _production_record_errors(records)
    if require_verified_baseline and baseline.get("status") != "ok":
        gate_errors.append(
            "Current Wikidata persistence baseline is not independently verified: "
            + "; ".join(str(item) for item in (baseline.get("errors") or []))
        )

    unmatched = int(preview.get("unmatched_authority_claims") or 0)
    if unmatched > int(max_unmatched_authority_claims):
        gate_errors.append(
            f"unmatched_authority_claims: allowed <= {int(max_unmatched_authority_claims)}, "
            f"got {unmatched}"
        )

    for key in (
        "identity_merges_performed",
        "canonical_formats_created",
        "canonical_identifiers_promoted",
        "risk_assessments_generated",
        "criterion_claims_generated",
        "mongo_writes",
    ):
        if int(preview.get(key) or 0) != 0:
            gate_errors.append(f"{key}: expected 0, got {preview.get(key)}")

    drift_gates = dict(drift_gates or {})
    drift: dict[str, Any] = {}

    population_drift, errors = _drift_check(
        label="wikidata_population",
        baseline=int(baseline.get("wikidata_source_records") or 0),
        planned=len(records),
        max_absolute=(
            int(drift_gates["max_population_change_absolute"])
            if drift_gates.get("max_population_change_absolute") is not None
            else None
        ),
        max_fraction=(
            float(drift_gates["max_population_change_fraction"])
            if drift_gates.get("max_population_change_fraction") is not None
            else None
        ),
    )
    drift["population"] = population_drift
    gate_errors.extend(errors)

    relationship_drift, errors = _drift_check(
        label="wikidata_relationship_edges",
        baseline=int(baseline.get("wikidata_relationship_claims") or 0),
        planned=len(planned_claims),
        max_absolute=(
            int(drift_gates["max_relationship_edge_change_absolute"])
            if drift_gates.get("max_relationship_edge_change_absolute") is not None
            else None
        ),
        max_fraction=(
            float(drift_gates["max_relationship_edge_change_fraction"])
            if drift_gates.get("max_relationship_edge_change_fraction") is not None
            else None
        ),
    )
    drift["relationship_edges"] = relationship_drift
    gate_errors.extend(errors)

    turnover_drift, errors = _drift_check(
        label="wikidata_relationship_claim_turnover",
        baseline=turnover["current"],
        planned=turnover["current"] + turnover["turnover"],
        max_absolute=(
            int(drift_gates["max_claim_turnover_absolute"])
            if drift_gates.get("max_claim_turnover_absolute") is not None
            else None
        ),
        max_fraction=(
            float(drift_gates["max_claim_turnover_fraction"])
            if drift_gates.get("max_claim_turnover_fraction") is not None
            else None
        ),
    )
    # For turnover, the meaningful delta is additions + removals rather than a
    # new total population. Preserve that explicitly in the report.
    turnover_drift["planned"] = turnover["turnover"]
    turnover_drift["delta"] = turnover["turnover"]
    turnover_drift["absolute_delta"] = turnover["turnover"]
    turnover_drift["fractional_change"] = _fraction(
        turnover["turnover"], turnover["current"]
    )
    drift["claim_turnover"] = turnover_drift
    # Re-evaluate the configured turnover threshold using the true turnover.
    gate_errors = [
        error
        for error in gate_errors
        if not error.startswith("wikidata_relationship_claim_turnover:")
    ]
    max_turnover_abs = drift_gates.get("max_claim_turnover_absolute")
    max_turnover_fraction = drift_gates.get("max_claim_turnover_fraction")
    if max_turnover_abs is not None and turnover["turnover"] > int(max_turnover_abs):
        gate_errors.append(
            f"wikidata_relationship_claim_turnover: {turnover['turnover']} exceeds allowed "
            f"{int(max_turnover_abs)}"
        )
    turnover_fraction = _fraction(turnover["turnover"], turnover["current"])
    if (
        max_turnover_fraction is not None
        and turnover_fraction is not None
        and turnover_fraction > float(max_turnover_fraction)
    ):
        gate_errors.append(
            f"wikidata_relationship_claim_turnover: fractional change "
            f"{turnover_fraction:.4f} exceeds allowed {float(max_turnover_fraction):.4f}"
        )

    expected_counts = _planned_expected_counts(preview)
    gate_passed = not gate_errors
    result: dict[str, Any] = {
        "status": "blocked" if not gate_passed else ("ready" if not apply else "applying"),
        "apply_requested": bool(apply),
        "population_policy_version": WIKIDATA_POPULATION_POLICY_VERSION,
        "source_id": WIKIDATA_SOURCE_ID,
        "adapter_type": PRODUCTION_ADAPTER_TYPE,
        "source_snapshot": {
            "local_path": final_snapshot.local_path,
            "sha256": final_snapshot.sha256,
            "changed": final_snapshot.changed,
            "from_cache": final_snapshot.from_cache,
        },
        "baseline_verification": baseline,
        "records_acquired": len(records),
        "planned_relationship_claims": len(planned_claims),
        "claim_turnover": turnover,
        "drift": drift,
        "gate_passed": gate_passed,
        "gate_errors": gate_errors,
        "max_unmatched_authority_claims": int(max_unmatched_authority_claims),
        "expected_post_refresh_counts": expected_counts,
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

    if not gate_passed or not apply:
        return result

    backfill = run_wikidata_relationship_backfill(
        store=store,
        input_csv=final_snapshot.local_path,
        identifier_rules=rules,
        dry_run=False,
        replace_source_claims=True,
        materialize_canonical=True,
        expected_counts=expected_counts,
        max_unmatched_authority_claims=max_unmatched_authority_claims,
    )
    result["backfill"] = backfill
    if backfill.get("status") != "completed" or not backfill.get("migration_gate_passed"):
        result["status"] = "write_failed"
        result["gate_errors"] = list(result["gate_errors"]) + [
            "Relationship backfill did not complete successfully"
        ]
        return result

    run_id = str(backfill.get("run_id") or "")
    if run_id:
        source_snapshot = deepcopy(final_snapshot.__dict__)
        source_snapshot["run_id"] = run_id
        source_snapshot["refresh_source_snapshot"] = True
        store.save_snapshot(source_snapshot)

    verification = verify_wikidata_relationship_persistence(
        store,
        expected_counts=expected_counts,
    )
    result["verification"] = verification

    post_errors: list[str] = []
    if verification.get("status") != "ok":
        post_errors.extend(str(item) for item in (verification.get("errors") or []))
    if int(backfill.get("claims_to_supersede") or 0) != int(turnover["removed"]):
        post_errors.append(
            "Backfill supersession count does not match the preflight relationship diff: "
            f"expected {turnover['removed']}, got {backfill.get('claims_to_supersede')}"
        )
    if int(backfill.get("claims_written") or 0) != len(planned_claims):
        post_errors.append(
            "Backfill written-claim count does not match the preflight relationship projection: "
            f"expected {len(planned_claims)}, got {backfill.get('claims_written')}"
        )

    if post_errors:
        result["status"] = "verification_failed"
        result["verification_errors"] = post_errors
        return result

    result["status"] = "completed"
    result["run_id"] = backfill.get("run_id")
    result["verification_errors"] = []
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m registry_builder.wikidata_refresh",
        description=(
            "Acquire the current policy-v3 Wikidata population, preflight relationship drift, "
            "and optionally apply + independently verify the governed evidence refresh."
        ),
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--workdir", default="work")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--out")
    args = parser.parse_args()

    config = _load_refresh_config(args.config)
    pipeline_config_path = _resolve_relative(config["_config_path"], config["storage_config"])
    pipeline_config = load_config(pipeline_config_path)
    rules = load_identifier_rules(pipeline_config.get("identifier_kinds"))

    source_config = dict(config.get("source") or {})
    source_config.setdefault("id", WIKIDATA_SOURCE_ID)
    source_config.setdefault("type", PRODUCTION_ADAPTER_TYPE)
    if args.offline:
        source_config["offline"] = True
    if args.restart:
        source_config["restart"] = True

    store = create_store(_storage_config(pipeline_config))
    try:
        report = run_wikidata_refresh(
            store=store,
            source_config=source_config,
            workdir=args.workdir,
            identifier_rules=rules,
            apply=args.apply,
            require_verified_baseline=bool(config.get("require_verified_baseline", True)),
            max_unmatched_authority_claims=int(
                config.get("max_unmatched_authority_claims", 0)
            ),
            drift_gates=dict(config.get("drift_gates") or {}),
        )
    finally:
        store.close()

    text = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)

    if report.get("status") in {"blocked", "write_failed", "verification_failed"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
