from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from typing import Any, Iterable

from registry_builder.models import CanonicalFormat
from registry_builder.storage.base import RegistryStore


PERSISTENCE_LAYER = "source_relationship_claims"


def _current_claims(store: RegistryStore) -> list[dict[str, Any]]:
    return [
        row
        for row in store.query(PERSISTENCE_LAYER)
        if row.get("current", True) is not False
    ]


def _claim_source_ref(claim: dict[str, Any]) -> dict[str, Any] | None:
    source_id = str(claim.get("source_id") or "")
    source_record_id = str(claim.get("source_record_id") or "")
    relationship = str(claim.get("relationship") or "")
    if not source_id or not source_record_id or not relationship:
        return None

    ref: dict[str, Any] = {
        "source_id": source_id,
        "source_type": claim.get("source_type"),
        "source_record_id": source_record_id,
        "relationship": relationship,
        "evidence_scope": claim.get("evidence_scope"),
        "persistence_layer": PERSISTENCE_LAYER,
    }
    copied = [dict(item) for item in (claim.get("copied_identifiers") or [])]
    if copied:
        ref["identifier_cross_references"] = copied
    if claim.get("wikidata_role"):
        ref["wikidata_role"] = claim.get("wikidata_role")
    source_url = claim.get("source_url")
    if source_url:
        ref["urls"] = {"wikidata": source_url}
    if claim.get("projection_version"):
        ref["projection_version"] = claim.get("projection_version")
    if claim.get("run_id"):
        ref["claim_run_id"] = claim.get("run_id")
    if claim.get("last_seen_run_id"):
        ref["claim_last_seen_run_id"] = claim.get("last_seen_run_id")
    return ref


def _is_materialized_ref(item: dict[str, Any]) -> bool:
    return str(item.get("persistence_layer") or "") == PERSISTENCE_LAYER


def materialize_current_source_relationship_claims(
    registry: Iterable[CanonicalFormat],
    store: RegistryStore,
    *,
    refreshed_source_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Replay current governed source relationships onto rebuilt canonicals.

    Relationship claims are evidence links only. They never create canonical
    identities and never promote copied identifiers. Replaying them after normal
    reconciliation ensures unrelated source refreshes cannot strip reviewed
    cross-registry relationships from the current canonical view.
    """

    registry_list = list(registry)
    by_id = {fmt.canonical_id: fmt for fmt in registry_list}
    claims = _current_claims(store)
    refs_by_canonical: dict[str, list[dict[str, Any]]] = defaultdict(list)
    orphan_claims: list[dict[str, Any]] = []
    invalid_claims: list[dict[str, Any]] = []

    for claim in claims:
        canonical_id = str(claim.get("canonical_id") or claim.get("format_id") or "")
        if not canonical_id or canonical_id not in by_id:
            orphan_claims.append(claim)
            continue
        ref = _claim_source_ref(claim)
        if ref is None:
            invalid_claims.append(claim)
            continue
        refs_by_canonical[canonical_id].append(ref)

    relationships_materialized = 0
    materialized_sources: Counter[str] = Counter()
    canonicals_with_relationships = 0

    for fmt in registry_list:
        base_refs = [
            deepcopy(item)
            for item in fmt.source_records
            if not _is_materialized_ref(item)
        ]
        attached = refs_by_canonical.get(fmt.canonical_id, [])
        fmt.source_records = base_refs + [deepcopy(item) for item in attached]

        sources = sorted({
            str(item.get("source_id") or item.get("source_type") or "")
            for item in attached
            if item.get("source_id") or item.get("source_type")
        })
        provenance = dict(fmt.provenance or {})
        if sources:
            provenance["materialized_source_relationship_claim_sources"] = sources
            provenance["source_relationship_claim_materialization"] = PERSISTENCE_LAYER
            canonicals_with_relationships += 1
        else:
            provenance.pop("materialized_source_relationship_claim_sources", None)
            provenance.pop("source_relationship_claim_materialization", None)
        fmt.provenance = provenance

        relationships_materialized += len(attached)
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

    return {
        "enabled": True,
        "persistence_layer": PERSISTENCE_LAYER,
        "identity_projection": False,
        "identifier_promotion": False,
        "current_claims_loaded": len(claims),
        "relationships_materialized": relationships_materialized,
        "canonicals_with_materialized_relationships": canonicals_with_relationships,
        "claim_sources": dict(sorted(materialized_sources.items())),
        "orphan_claims": len(orphan_claims),
        "invalid_claims": len(invalid_claims),
        "refreshed_claim_sources": refreshed_claim_sources,
        "source_backfill_refresh_recommended": bool(refreshed_claim_sources),
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
