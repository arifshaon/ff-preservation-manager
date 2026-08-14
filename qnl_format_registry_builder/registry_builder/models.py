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
    hand-maintained spreadsheet remain useful evidence, but they are not strong
    reconciliation keys until confirmed by an authoritative source.
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


@dataclass
class RawFormatRecord:
    source_id: str
    source_type: str
    source_record_id: str | None = None
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
    qnl: dict[str, Any] = field(default_factory=dict)
    hazard: dict[str, Any] = field(default_factory=dict)
    readiness: dict[str, Any] = field(default_factory=dict)
    trend: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CanonicalFormat:
    canonical_id: str
    preferred_name: str
    category: str | None = None
    description: str | None = None
    identifiers: dict[str, list[str]] = field(default_factory=dict)
    identifier_claims: list[dict[str, Any]] = field(default_factory=list)
    source_records: list[dict[str, Any]] = field(default_factory=list)
    qnl_policy_overlay: list[dict[str, Any]] = field(default_factory=list)
    external_hazard: list[dict[str, Any]] = field(default_factory=list)
    hazard_assessment: dict[str, Any] = field(default_factory=dict)
    readiness: list[dict[str, Any]] = field(default_factory=list)
    trend: list[dict[str, Any]] = field(default_factory=list)
    preservation_method: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    def add_identifier(
        self,
        kind: str,
        value: str | None,
        *,
        source: str | None = None,
        verified: bool = False,
        source_record_id: str | None = None,
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
        if claim not in self.identifier_claims:
            self.identifier_claims.append(claim)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key, values in data.get("identifiers", {}).items():
            data["identifiers"][key] = sorted(values)
        data["identifier_claims"] = sorted(
            data.get("identifier_claims", []),
            key=lambda x: (x.get("kind") or "", x.get("value") or "", x.get("source") or ""),
        )
        return data
