from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from typing import Any, Iterable

from registry_builder.models import CanonicalFormat
from registry_builder.source_relationship_claim_materialization import (
    materialize_current_source_relationship_claims,
)
from registry_builder.storage.base import RegistryStore


PERSISTENCE_LAYER = "risk_assessment_claims"


def _current_claims(store: RegistryStore) -> list[dict[str, Any]]:
    return [
        row
        for row in store.query("risk_assessment_claims")
        if row.get("current", True) is not False
    ]


def _claim_assessment(claim: dict[str, Any]) -> dict[str, Any] | None:
    assessment = deepcopy(claim.get("assessment") or {})
    if not assessment:
        return None

    for key in (
        "source_id",
        "source_type",
        "source_record_id",
        "scope_type",
        "scope_name",
        "native_label",
        "semantic_level",
        "mapping_rule_id",
        "mapping_version",
        "projection_version",
    ):
        if assessment.get(key) is None and claim.get(key) is not None:
            assessment[key] = claim.get(key)

    assessment["persistence_layer"] = PERSISTENCE_LAYER
    if claim.get("run_id"):
        assessment["claim_run_id"] = claim.get("run_id")
    if claim.get("last_seen_run_id"):
        assessment["claim_last_seen_run_id"] = claim.get("last_seen_run_id")
    return assessment


def _is_materialized_assessment(item: dict[str, Any]) -> bool:
    return str(item.get("persistence_layer") or "") == PERSISTENCE_LAYER


def materialize_current_risk_claims(
    registry: Iterable[CanonicalFormat],
    store: RegistryStore,
    *,
    refreshed_source_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Reapply governed persistent claim layers after reconciliation.

    Canonical identity is rebuilt from source records on every pipeline run. Risk
    claims and source-relationship claims live in separate persistent collections
    and must therefore be replayed after reconciliation so unrelated source
    refreshes cannot strip governed assessment or cross-registry evidence from
    canonical documents.

    A source refresh does *not* itself supersede a governed claim. Current claims
    stay materialized until the source-specific reviewed backfill replaces them.
    When a claim source is refreshed in the same pipeline run, the report flags
    that source so operators know its reviewed backfill should be rerun.
    """

    registry_list = list(registry)
    by_id = {fmt.canonical_id: fmt for fmt in registry_list}
    claims = _current_claims(store)
    claims_by_canonical: dict[str, list[dict[str, Any]]] = defaultdict(list)
    orphan_claims: list[dict[str, Any]] = []
    invalid_claims: list[dict[str, Any]] = []

    for claim in claims:
        canonical_id = str(claim.get("canonical_id") or claim.get("format_id") or "")
        if not canonical_id or canonical_id not in by_id:
            orphan_claims.append(claim)
            continue
        assessment = _claim_assessment(claim)
        if assessment is None:
            invalid_claims.append(claim)
            continue
        claims_by_canonical[canonical_id].append(assessment)

    materialized_count = 0
    materialized_sources: Counter[str] = Counter()
    canonicals_with_claims = 0

    for fmt in registry_list:
        # Remove any previously materialized claim objects before replaying the
        # current persistent view. This makes repeated materialization idempotent.
        base_assessments = [
            deepcopy(item)
            for item in fmt.risk_assessments
            if not _is_materialized_assessment(item)
        ]
        attached = claims_by_canonical.get(fmt.canonical_id, [])
        fmt.risk_assessments = base_assessments + [deepcopy(item) for item in attached]

        sources = sorted({
            str(item.get("source_id") or item.get("source_type") or "")
            for item in attached
            if item.get("source_id") or item.get("source_type")
        })
        provenance = dict(fmt.provenance or {})
        if sources:
            provenance["materialized_risk_claim_sources"] = sources
            provenance["risk_claim_materialization"] = PERSISTENCE_LAYER
            canonicals_with_claims += 1
        else:
            provenance.pop("materialized_risk_claim_sources", None)
            provenance.pop("risk_claim_materialization", None)
        fmt.provenance = provenance
        fmt.refresh_risk_views()

        materialized_count += len(attached)
        materialized_sources.update(
            str(item.get("source_id") or item.get("source_type") or "unknown")
            for item in attached
        )

    refreshed_source_ids = set(refreshed_source_ids or set())
    current_claim_sources = {
        str(claim.get("source_id") or claim.get("source_type") or "")
        for claim in claims
        if claim.get("source_id") or claim.get("source_type")
    }
    refreshed_claim_sources = sorted(current_claim_sources & refreshed_source_ids)

    # The normal pipeline already calls this function after reconciliation. Reuse
    # that governed-claim lifecycle hook for source relationship claims as well so
    # a canonical rebuild cannot strip persisted Wikidata/other cross-registry
    # evidence. Relationship replay mutates source_records/provenance only; it does
    # not create identities or promote copied identifiers.
    source_relationship_materialization = materialize_current_source_relationship_claims(
        registry_list,
        store,
        refreshed_source_ids=refreshed_source_ids,
    )

    return {
        "enabled": True,
        "persistence_layer": PERSISTENCE_LAYER,
        "identity_projection": False,
        "current_claims_loaded": len(claims),
        "claims_materialized": materialized_count,
        "canonicals_with_materialized_claims": canonicals_with_claims,
        "claim_sources": dict(sorted(materialized_sources.items())),
        "orphan_claims": len(orphan_claims),
        "invalid_claims": len(invalid_claims),
        "refreshed_claim_sources": refreshed_claim_sources,
        "source_backfill_refresh_recommended": bool(refreshed_claim_sources),
        "source_relationship_materialization": source_relationship_materialization,
        "orphan_claim_samples": [
            {
                "canonical_id": row.get("canonical_id") or row.get("format_id"),
                "source_id": row.get("source_id") or row.get("source_type"),
                "source_record_id": row.get("source_record_id"),
            }
            for row in orphan_claims[:20]
        ],
        "invalid_claim_samples": [
            {
                "canonical_id": row.get("canonical_id") or row.get("format_id"),
                "source_id": row.get("source_id") or row.get("source_type"),
                "source_record_id": row.get("source_record_id"),
            }
            for row in invalid_claims[:20]
        ],
    }
