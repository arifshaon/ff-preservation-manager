from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from registry_builder.identifier_rules import load_identifier_rules, strong_identifier_kinds
from registry_builder.models import RawFormatRecord
from registry_builder.pipeline import _storage_config, load_config
from registry_builder.storage import create_store
from registry_builder.utils import write_json
from registry_builder.wikidata_projection import (
    WIKIDATA_PROJECTION_VERSION,
    project_wikidata_csv,
)


WIKIDATA_RELATIONSHIP_PREVIEW_VERSION = "2026-08-21-v1-read-only"


def _canonical_authority_index(
    canonical_formats: Iterable[dict[str, Any]],
    *,
    strong_kinds: set[str],
) -> dict[tuple[str, str], set[str]]:
    index: dict[tuple[str, str], set[str]] = defaultdict(set)
    for fmt in canonical_formats:
        canonical_id = str(fmt.get("canonical_id") or fmt.get("format_id") or "")
        if not canonical_id:
            continue
        identifiers = fmt.get("identifiers") or {}
        for kind, values in identifiers.items():
            if kind not in strong_kinds:
                continue
            for value in values or []:
                index[(str(kind), str(value))].add(canonical_id)
    return index


def preview_wikidata_relationships(
    canonical_formats: Iterable[dict[str, Any]],
    wikidata_records: Iterable[RawFormatRecord],
    *,
    identifier_rules: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Preview Wikidata-to-canonical relationship evidence without identity changes.

    Copied PRONOM/LOC/NARA identifiers are treated as explicit cross-reference
    claims. They are never promoted to verified identifiers and never merge or
    create canonical formats. One Wikidata QID may therefore relate to several
    existing canonicals when the source concept is broader than a single registry
    identity. That multiplicity is preserved as context rather than collapsed.
    """

    rules = identifier_rules or load_identifier_rules()
    strong_kinds = strong_identifier_kinds(rules)
    canonical = list(canonical_formats)
    records = list(wikidata_records)
    authority_index = _canonical_authority_index(canonical, strong_kinds=strong_kinds)

    relationship_edges: list[dict[str, Any]] = []
    qid_summaries: list[dict[str, Any]] = []
    unmatched_claims: list[dict[str, str]] = []
    matched_claim_counts: Counter[str] = Counter()
    unmatched_claim_counts: Counter[str] = Counter()
    role_relationship_counts: Counter[str] = Counter()

    for record in records:
        qid = str(record.source_record_id or "")
        role = str(record.native_fields.get("wikidata_role") or record.category or "")
        copied_claims = [
            identifier
            for identifier in record.identifiers
            if not identifier.verified and identifier.kind in strong_kinds
        ]

        target_claims: dict[str, list[dict[str, str]]] = defaultdict(list)
        matched_claims = 0
        unmatched = 0
        for identifier in copied_claims:
            targets = sorted(authority_index.get((identifier.kind, identifier.value), set()))
            if not targets:
                unmatched += 1
                unmatched_claim_counts[identifier.kind] += 1
                unmatched_claims.append(
                    {
                        "qid": qid,
                        "name": str(record.name or ""),
                        "wikidata_role": role,
                        "kind": identifier.kind,
                        "value": identifier.value,
                    }
                )
                continue

            matched_claims += 1
            matched_claim_counts[identifier.kind] += 1
            for canonical_id in targets:
                target_claims[canonical_id].append(
                    {"kind": identifier.kind, "value": identifier.value}
                )

        target_ids = sorted(target_claims)
        if not copied_claims:
            outcome = "no_authority_cross_reference"
        elif not target_ids:
            outcome = "authority_claims_unresolved"
        elif len(target_ids) == 1:
            outcome = (
                "single_target_with_unresolved_claims"
                if unmatched
                else "single_target_cross_reference"
            )
        else:
            outcome = (
                "multi_target_context_with_unresolved_claims"
                if unmatched
                else "multi_target_context"
            )

        qid_summaries.append(
            {
                "qid": qid,
                "name": record.name,
                "wikidata_role": role,
                "projection_record_role": record.record_role,
                "outcome": outcome,
                "copied_authority_claim_count": len(copied_claims),
                "matched_authority_claim_count": matched_claims,
                "unmatched_authority_claim_count": unmatched,
                "canonical_targets": target_ids,
            }
        )

        if target_ids:
            role_relationship_counts[role] += 1
        evidence_scope = (
            "single_canonical_cross_reference"
            if len(target_ids) == 1
            else "multi_canonical_context"
        )
        for canonical_id in target_ids:
            relationship_edges.append(
                {
                    "canonical_id": canonical_id,
                    "source_id": record.source_id,
                    "source_type": record.source_type,
                    "source_record_id": qid,
                    "wikidata_role": role,
                    "relationship": "explicit_wikidata_identifier_cross_reference",
                    "evidence_scope": evidence_scope,
                    "copied_identifiers": sorted(
                        target_claims[canonical_id],
                        key=lambda item: (item["kind"], item["value"]),
                    ),
                    "source_url": record.urls.get("wikidata") if record.urls else None,
                }
            )

    outcome_counts = Counter(item["outcome"] for item in qid_summaries)
    qids_with_relationships = {
        edge["source_record_id"] for edge in relationship_edges
    }
    canonicals_with_relationships = {
        edge["canonical_id"] for edge in relationship_edges
    }

    return {
        "status": "ok",
        "preview_version": WIKIDATA_RELATIONSHIP_PREVIEW_VERSION,
        "projection_version": WIKIDATA_PROJECTION_VERSION,
        "read_only": True,
        "mongo_writes": 0,
        "canonical_formats": len(canonical),
        "wikidata_records": len(records),
        "wikidata_qids_with_relationships": len(qids_with_relationships),
        "canonical_formats_with_wikidata_relationships": len(canonicals_with_relationships),
        "relationship_edges": len(relationship_edges),
        "matched_authority_claims": sum(matched_claim_counts.values()),
        "matched_authority_claims_by_kind": dict(sorted(matched_claim_counts.items())),
        "unmatched_authority_claims": sum(unmatched_claim_counts.values()),
        "unmatched_authority_claims_by_kind": dict(sorted(unmatched_claim_counts.items())),
        "qid_outcomes": dict(sorted(outcome_counts.items())),
        "qids_with_relationships_by_wikidata_role": dict(
            sorted(role_relationship_counts.items())
        ),
        "identity_merges_performed": 0,
        "canonical_formats_created": 0,
        "canonical_identifiers_promoted": 0,
        "risk_assessments_generated": 0,
        "criterion_claims_generated": 0,
        "multi_target_samples": [
            item
            for item in qid_summaries
            if item["outcome"].startswith("multi_target_context")
        ][:100],
        "unresolved_samples": [
            item
            for item in qid_summaries
            if item["outcome"] in {
                "authority_claims_unresolved",
                "single_target_with_unresolved_claims",
                "multi_target_context_with_unresolved_claims",
            }
        ][:100],
        "relationship_samples": relationship_edges[:100],
        "unmatched_claim_samples": unmatched_claims[:100],
        "relationships": relationship_edges,
        "records": qid_summaries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m registry_builder.wikidata_relationship_preview",
        description=(
            "Preview Wikidata identifier-cross-reference relationships against "
            "the current registry without creating, merging, or writing canonicals."
        ),
    )
    parser.add_argument("--input", required=True, help="Frozen policy-v3 Wikidata CSV")
    parser.add_argument(
        "--config",
        default="config/sources.qnl.json",
        help="Registry config used to locate the current store and identifier rules",
    )
    parser.add_argument(
        "--out",
        default="out/wikidata-relationship-preview.json",
        help="Preview JSON output",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    rules = load_identifier_rules(config.get("identifier_kinds"))
    store = create_store(_storage_config(config))
    try:
        canonical = store.get_current_registry_view()
    finally:
        store.close()

    records = project_wikidata_csv(args.input)
    result = preview_wikidata_relationships(
        canonical,
        records,
        identifier_rules=rules,
    )
    result["input_file"] = str(Path(args.input))
    result["config_file"] = str(Path(args.config))
    result["summary_file"] = str(Path(args.out))
    write_json(args.out, result)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
