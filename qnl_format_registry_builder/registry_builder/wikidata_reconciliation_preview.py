from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from registry_builder.identifier_rules import load_identifier_rules, strong_identifier_kinds
from registry_builder.models import CanonicalFormat, RawFormatRecord
from registry_builder.normalize import normalize_record
from registry_builder.pipeline import (
    _storage_config,
    _stored_source_records_for_augmentation,
    load_config,
)
from registry_builder.reconcile import reconcile
from registry_builder.storage import create_store
from registry_builder.utils import write_json
from registry_builder.wikidata_projection import (
    WIKIDATA_PROJECTION_VERSION,
    project_wikidata_csv,
)


WIKIDATA_RECONCILIATION_PREVIEW_VERSION = "2026-08-21-v1-read-only"


def _authority_index(
    registry: Iterable[CanonicalFormat],
    *,
    strong_kinds: set[str],
) -> dict[tuple[str, str], set[str]]:
    index: dict[tuple[str, str], set[str]] = defaultdict(set)
    for fmt in registry:
        for kind, values in fmt.identifiers.items():
            if kind not in strong_kinds:
                continue
            for value in values:
                index[(kind, str(value))].add(fmt.canonical_id)
    return index


def _wikidata_refs_by_qid(
    registry: Iterable[CanonicalFormat],
    *,
    source_id: str,
) -> dict[str, set[str]]:
    refs: dict[str, set[str]] = defaultdict(set)
    for fmt in registry:
        for source_ref in fmt.source_records:
            if str(source_ref.get("source_id") or "") != source_id:
                continue
            qid = str(source_ref.get("source_record_id") or "")
            if qid:
                refs[qid].add(fmt.canonical_id)
    return refs


def _copied_authority_targets(
    record: RawFormatRecord,
    *,
    authority_index: dict[tuple[str, str], set[str]],
    strong_kinds: set[str],
) -> tuple[dict[str, list[str]], set[str]]:
    by_claim: dict[str, list[str]] = {}
    targets: set[str] = set()
    for identifier in record.identifiers:
        if identifier.verified or identifier.kind not in strong_kinds:
            continue
        matched = sorted(authority_index.get((identifier.kind, identifier.value), set()))
        by_claim[f"{identifier.kind}:{identifier.value}"] = matched
        targets.update(matched)
    return by_claim, targets


def preview_reconciliation(
    existing_records: Iterable[RawFormatRecord],
    wikidata_records: Iterable[RawFormatRecord],
    *,
    identifier_rules: dict[str, dict[str, Any]] | None = None,
    wikidata_source_id: str = "wikidata_file_formats",
) -> dict[str, Any]:
    """Simulate Wikidata reconciliation without persistence.

    The function uses the production reconciler for both the baseline and the
    augmented view. It reports impact only; it does not materialize risk claims,
    generate criterion claims, or write to a RegistryStore.
    """

    rules = identifier_rules or load_identifier_rules()
    strong_kinds = strong_identifier_kinds(rules)
    existing = list(existing_records)
    wikidata = list(wikidata_records)

    baseline_registry = reconcile(existing, identifier_rules=rules)
    augmented_registry = reconcile(existing + wikidata, identifier_rules=rules)

    baseline_ids = {fmt.canonical_id for fmt in baseline_registry}
    augmented_ids = {fmt.canonical_id for fmt in augmented_registry}
    authority_index = _authority_index(baseline_registry, strong_kinds=strong_kinds)
    refs_by_qid = _wikidata_refs_by_qid(
        augmented_registry,
        source_id=wikidata_source_id,
    )

    outcomes: list[dict[str, Any]] = []
    for record in wikidata:
        qid = str(record.source_record_id or "")
        role = str(record.native_fields.get("wikidata_role") or record.category or "")
        if record.record_role == "evidence_only":
            outcomes.append({
                "qid": qid,
                "name": record.name,
                "wikidata_role": role,
                "record_role": record.record_role,
                "outcome": "evidence_only",
                "authority_targets": [],
                "reconciled_canonical_ids": [],
            })
            continue

        authority_claims, authority_targets = _copied_authority_targets(
            record,
            authority_index=authority_index,
            strong_kinds=strong_kinds,
        )
        reconciled_refs = refs_by_qid.get(qid, set())
        existing_refs = sorted(reconciled_refs & baseline_ids)
        new_refs = sorted(reconciled_refs - baseline_ids)

        if len(authority_targets) > 1 or len(existing_refs) > 1:
            outcome = "ambiguous_authority_bridge"
        elif existing_refs:
            outcome = (
                "joined_existing_authority"
                if authority_targets
                else "joined_existing_weak"
            )
        elif new_refs and len(authority_targets) == 1:
            outcome = "guarded_authority_mismatch"
        elif new_refs:
            outcome = "new_canonical_candidate"
        else:
            outcome = "unresolved"

        outcomes.append({
            "qid": qid,
            "name": record.name,
            "wikidata_role": role,
            "record_role": record.record_role,
            "outcome": outcome,
            "copied_authority_claims": authority_claims,
            "authority_targets": sorted(authority_targets),
            "reconciled_canonical_ids": sorted(reconciled_refs),
            "existing_canonical_ids": existing_refs,
            "new_canonical_ids": new_refs,
            "multiple_puids": len(record.puids) > 1,
        })

    outcome_counts = Counter(row["outcome"] for row in outcomes)
    role_outcomes: dict[str, Counter[str]] = defaultdict(Counter)
    for row in outcomes:
        role_outcomes[row["wikidata_role"]][row["outcome"]] += 1

    new_candidate_qids = {
        row["qid"]
        for row in outcomes
        if row["outcome"] == "new_canonical_candidate"
    }
    ambiguous_qids = {
        row["qid"]
        for row in outcomes
        if row["outcome"] in {
            "ambiguous_authority_bridge",
            "guarded_authority_mismatch",
            "unresolved",
        }
    }
    joined_qids = {
        row["qid"]
        for row in outcomes
        if row["outcome"] in {
            "joined_existing_authority",
            "joined_existing_weak",
        }
    }

    new_canonical_ids = augmented_ids - baseline_ids
    return {
        "status": "ok",
        "preview_version": WIKIDATA_RECONCILIATION_PREVIEW_VERSION,
        "projection_version": WIKIDATA_PROJECTION_VERSION,
        "read_only": True,
        "mongo_writes": 0,
        "risk_assessments_generated": 0,
        "criterion_claims_generated": 0,
        "baseline_source_records": len(existing),
        "wikidata_records": len(wikidata),
        "wikidata_identity_records": sum(1 for record in wikidata if record.record_role != "evidence_only"),
        "wikidata_evidence_only_records": sum(1 for record in wikidata if record.record_role == "evidence_only"),
        "baseline_canonical_formats": len(baseline_registry),
        "augmented_canonical_formats": len(augmented_registry),
        "net_new_canonical_formats": len(new_canonical_ids),
        "wikidata_qids_joining_existing": len(joined_qids),
        "wikidata_qids_requiring_review": len(ambiguous_qids),
        "wikidata_qids_new_candidates": len(new_candidate_qids),
        "outcomes": dict(sorted(outcome_counts.items())),
        "outcomes_by_wikidata_role": {
            role: dict(sorted(counter.items()))
            for role, counter in sorted(role_outcomes.items())
        },
        "new_canonical_ids": sorted(new_canonical_ids),
        "review_samples": [
            row
            for row in outcomes
            if row["outcome"] in {
                "ambiguous_authority_bridge",
                "guarded_authority_mismatch",
                "unresolved",
            }
        ][:100],
        "new_candidate_samples": [
            row for row in outcomes if row["outcome"] == "new_canonical_candidate"
        ][:100],
        "joined_existing_samples": [
            row
            for row in outcomes
            if row["outcome"] in {
                "joined_existing_authority",
                "joined_existing_weak",
            }
        ][:100],
        "records": outcomes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m registry_builder.wikidata_reconciliation_preview",
        description=(
            "Read-only Wikidata reconciliation-impact preview against the current "
            "registry store. Uses the production reconciler but performs no writes."
        ),
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Frozen policy-v3 Wikidata acquisition CSV",
    )
    parser.add_argument(
        "--config",
        default="config/sources.qnl.json",
        help="Registry pipeline config used to locate MongoDB and identifier rules",
    )
    parser.add_argument(
        "--out",
        default="out/wikidata-reconciliation-preview.json",
        help="Preview JSON output",
    )
    parser.add_argument(
        "--source-id",
        default="wikidata_file_formats",
        help="Wikidata source ID used in the preview projection",
    )
    parser.add_argument(
        "--allow-baseline-drift",
        action="store_true",
        help=(
            "Allow the source-record rebuild count to differ from the persisted "
            "current canonical count. Default is to fail closed."
        ),
    )
    args = parser.parse_args()

    config = load_config(args.config)
    rules = load_identifier_rules(config.get("identifier_kinds"))
    store = create_store(_storage_config(config))
    try:
        persisted_current = store.get_current_registry_view()
        existing_records = _stored_source_records_for_augmentation(
            store,
            current_run_source_ids=set(),
            identifier_rules=rules,
        )
        wikidata_records = [
            normalize_record(record, identifier_rules=rules)
            for record in project_wikidata_csv(
                args.input,
                source_id=args.source_id,
            )
        ]
        result = preview_reconciliation(
            existing_records,
            wikidata_records,
            identifier_rules=rules,
            wikidata_source_id=args.source_id,
        )
        result["input_file"] = str(Path(args.input))
        result["config_file"] = str(Path(args.config))
        result["persisted_current_canonical_formats"] = len(persisted_current)
        result["baseline_matches_persisted_current"] = (
            result["baseline_canonical_formats"] == len(persisted_current)
        )
        if not result["baseline_matches_persisted_current"] and not args.allow_baseline_drift:
            raise RuntimeError(
                "Read-only baseline rebuild does not match persisted current registry: "
                f"rebuilt={result['baseline_canonical_formats']} "
                f"persisted={len(persisted_current)}. No writes were performed."
            )
        result["summary_file"] = str(Path(args.out))
        write_json(args.out, result)
        printable = dict(result)
        printable.pop("records", None)
        printable.pop("new_canonical_ids", None)
        print(json.dumps(printable, indent=2, ensure_ascii=False))
    finally:
        close = getattr(store, "close", None)
        if callable(close):
            close()


if __name__ == "__main__":
    main()
