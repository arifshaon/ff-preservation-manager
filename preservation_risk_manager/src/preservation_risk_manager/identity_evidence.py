from __future__ import annotations

from typing import Any


def _format_id(format_record: dict[str, Any]) -> str:
    return str(
        format_record.get("canonical_id")
        or format_record.get("format_id")
        or format_record.get("id")
        or "unknown-format"
    )


def derive_registry_identity_evidence(format_record: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive narrowly scoped assessment evidence from verified registry identity.

    A verified PUID is authority-backed evidence that the format has a formal,
    specific technical-registry identifier suitable for automated identification.
    Copied/unverified PUIDs, extensions, MIME strings, LOC IDs, NARA IDs and
    Wikidata IDs do not establish this criterion here.

    This helper does not alter canonical identity or persist new claims. It only
    projects already-verified identity metadata into the risk manager's evidence
    pack for the ``identification.registry_recognition`` question.
    """
    identifier_claims = format_record.get("identifier_claims") or []
    verified_puids: list[dict[str, Any]] = []

    for claim in identifier_claims:
        if not isinstance(claim, dict):
            continue
        if str(claim.get("kind") or "").strip().lower() != "puid":
            continue
        if claim.get("verified") is not True:
            continue
        value = str(claim.get("value") or "").strip()
        if not value:
            continue
        verified_puids.append({
            "value": value,
            "source": claim.get("source"),
            "source_record_id": claim.get("source_record_id"),
        })

    if not verified_puids:
        return []

    verified_puids.sort(
        key=lambda row: (
            str(row.get("value") or ""),
            str(row.get("source") or ""),
            str(row.get("source_record_id") or ""),
        )
    )
    format_id = _format_id(format_record)
    return [{
        "claim_id": f"derived-registry-recognition:{format_id}",
        "criterion_id": "identification.registry_recognition",
        "value": "formal_registry_identifier",
        "source_id": "qnl_format_registry",
        "source_type": "canonical_identity_derivation",
        "source_record_id": format_id,
        "source_field": "identifier_claims",
        "directness": "derived",
        "covers": "full",
        "source_independence": "authority_derived",
        "derivation_rule": "verified_puid_establishes_formal_registry_identifier",
        "verified_puids": verified_puids,
    }]
