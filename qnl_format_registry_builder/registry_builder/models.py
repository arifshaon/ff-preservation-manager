from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class Identifier:
    """A source-specific identifier claim.

    `verified` means the identifier came from the authority that owns that
    identifier namespace, for example a PUID from PRONOM/DROID XML, a LOC FDD ID
    from LOC FDD XML, or a NARA ID from a NARA source. Identifiers copied from a
    hand-maintained institutional spreadsheet remain useful evidence, but they
    are not strong reconciliation keys until confirmed by an authoritative source.
    """

    kind: str
    value: str
    source: str
    verified: bool = False
    source_record_id: str | None = None


@dataclass
class SourceSnapshot:
    source_id: str
    source_type: str
    uri: str
    acquired_at: str
    sha256: str
    local_path: str
    content_type: str | None = None
    note: str | None = None
    changed: bool | None = None
    from_cache: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawFormatRecord:
    source_id: str
    source_type: str
    source_record_id: str | None = None
    # `format_identity` records participate in canonical reconciliation.
    # `evidence_only` records are persisted and may be mapped onto canonical
    # formats, but must never create canonical identity records themselves.
    record_role: str = "format_identity"
    name: str | None = None
    category: str | None = None
    description: str | None = None
    extensions: list[str] = field(default_factory=list)
    mime_types: list[str] = field(default_factory=list)
    puids: list[str] = field(default_factory=list)
    loc_ids: list[str] = field(default_factory=list)
    nara_ids: list[str] = field(default_factory=list)
    wikidata_ids: list[str] = field(default_factory=list)
    identifiers: list[Identifier] = field(default_factory=list)
    urls: dict[str, str] = field(default_factory=dict)
    institution_policy: dict[str, Any] = field(default_factory=dict)
    institution_evidence: list[dict[str, Any]] = field(default_factory=list)
    qnl: dict[str, Any] = field(default_factory=dict)
    risk_assessments: list[dict[str, Any]] = field(default_factory=list)
    hazard: dict[str, Any] = field(default_factory=dict)
    readiness: dict[str, Any] = field(default_factory=dict)
    trend: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    native_fields: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
    version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if data.get("qnl") and not data.get("institution_policy"):
            data["institution_policy"] = data["qnl"]
        return data


@dataclass
class CanonicalFormat:
    canonical_id: str
    preferred_name: str
    category: str | None = None
    description: str | None = None
    identifiers: dict[str, list[str]] = field(default_factory=dict)
    identifier_claims: list[dict[str, Any]] = field(default_factory=list)
    source_records: list[dict[str, Any]] = field(default_factory=list)
    institution_policy_overlays: list[dict[str, Any]] = field(default_factory=list)
    institution_evidence_claims: list[dict[str, Any]] = field(default_factory=list)
    risk_assessments: list[dict[str, Any]] = field(default_factory=list)
    synthesized_risk: dict[str, Any] = field(default_factory=dict)
    external_hazard: list[dict[str, Any]] = field(default_factory=list)
    hazard_assessment: dict[str, Any] = field(default_factory=dict)
    readiness: list[dict[str, Any]] = field(default_factory=list)
    trend: list[dict[str, Any]] = field(default_factory=list)
    preservation_method: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    version: str | None = None

    def add_identifier(
        self,
        kind: str,
        value: str | None,
        *,
        source: str | None = None,
        verified: bool = False,
        source_record_id: str | None = None,
        confidence: str | None = None,
        confidence_reason: str | None = None,
    ) -> None:
        if not value:
            return
        kind = str(kind).strip()
        value = str(value).strip()
        if not kind or not value:
            return
        values = self.identifiers.setdefault(kind, [])
        if value not in values:
            values.append(value)
        claim = {
            "kind": kind,
            "value": value,
            "source": source,
            "verified": bool(verified),
            "source_record_id": source_record_id,
        }
        if confidence:
            claim["confidence"] = confidence
        if confidence_reason:
            claim["confidence_reason"] = confidence_reason
        if claim not in self.identifier_claims:
            self.identifier_claims.append(claim)

    @staticmethod
    def _risk_source_key(item: dict[str, Any]) -> str:
        return str(item.get("source_id") or item.get("source_type") or "")

    def refresh_risk_views(self) -> None:
        """Populate preferred multi-source risk views without deleting legacy data.

        Persisted ``risk_assessment_claims`` are the governed assessment layer.
        When a source has a materialized persisted claim, older raw/legacy
        projections from that same source remain stored in their native fields for
        audit but are not added a second time to the normalized risk view.
        """

        from registry_builder.risk_synthesis import (
            risk_assessments_from_canonical_fields,
            synthesize_risk_assessments,
        )

        persisted_sources = {
            self._risk_source_key(item)
            for item in self.risk_assessments
            if item.get("persistence_layer") == "risk_assessment_claims"
            and self._risk_source_key(item)
        }
        explicit_assessments = [
            item
            for item in self.risk_assessments
            if (
                item.get("persistence_layer") == "risk_assessment_claims"
                or self._risk_source_key(item) not in persisted_sources
            )
        ]
        external_hazard = [
            item
            for item in self.external_hazard
            if self._risk_source_key(item) not in persisted_sources
        ]

        self.risk_assessments = risk_assessments_from_canonical_fields(
            explicit_assessments=explicit_assessments,
            external_hazard=external_hazard,
            institution_policy_overlays=self.institution_policy_overlays,
            source_records=self.source_records,
            canonical_name=self.preferred_name,
        )
        for assessment in self.risk_assessments:
            if assessment.get("scope_type") == "institutional_format":
                assessment["scope_type"] = "exact_format"
        self.synthesized_risk = synthesize_risk_assessments(self.risk_assessments)

    def to_dict(self) -> dict[str, Any]:
        self.refresh_risk_views()
        data = asdict(self)
        for key, values in data.get("identifiers", {}).items():
            data["identifiers"][key] = sorted(values)
        data["identifier_claims"] = sorted(
            data.get("identifier_claims", []),
            key=lambda x: (x.get("kind") or "", x.get("value") or "", x.get("source") or ""),
        )
        data["institution_evidence_claims"] = sorted(
            data.get("institution_evidence_claims", []),
            key=lambda x: (
                x.get("institution_id") or "",
                x.get("criterion_id") or "",
                x.get("claim_id") or "",
            ),
        )
        data["risk_assessments"] = sorted(
            data.get("risk_assessments", []),
            key=lambda x: (
                x.get("assessment_role") or "",
                x.get("source_type") or "",
                x.get("source_id") or "",
                x.get("source_record_id") or "",
            ),
        )
        return data