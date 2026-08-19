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
    # Whether the source asserts this identifier firmly enough to reconcile on.
    # An unendorsed claim is still recorded as evidence but never bridges two
    # records together. LOC, for example, states its PRONOM equivalences in a
    # structured <sigValue> element while its prose notes may *mention* a PUID
    # precisely in order to say it is NOT the same format
    # ("Pronom's fmt/141 covers PCMWAVFORMAT but this is not precisely the same
    # as LPCM WAV"). Scraping such a mention and treating it as an equivalence
    # asserts a link the authority explicitly refused to make.
    endorsed: bool = True


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
    # How this snapshot was obtained: "local" (administrator-dropped input
    # file), "network" (fetched from the source), or "cache" (replay of a
    # previously stored snapshot). None on snapshots stored before this field
    # existed.
    acquisition_mode: str | None = None
    # When the SOURCE says this material was published/updated — a NARA release
    # date, an HTTP Last-Modified, a Bit List edition year. Distinct from
    # acquired_at, which only says when WE fetched it. Obsolescence trend needs
    # the former; conflating the two makes stale data look fresh.
    source_published_at: str | None = None
    # Source-declared edition/release label (e.g. "20260320", "2025").
    edition: str | None = None


def snapshot_currency(snapshot: "SourceSnapshot", *, now: datetime | None = None) -> dict[str, Any]:
    """Describe how old a snapshot's data is.

    Two ages are reported because they answer different questions:
    - published_age_days: how stale the source material itself is
    - acquired_age_days: how long since we last checked the source
    """
    now = now or datetime.now(timezone.utc)

    def _age_days(value: str | None) -> int | None:
        if not value:
            return None
        text = str(value).strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0, int((now - parsed).total_seconds() // 86400))

    return {
        "acquisition_mode": snapshot.acquisition_mode,
        "acquired_at": snapshot.acquired_at,
        "acquired_age_days": _age_days(snapshot.acquired_at),
        "source_published_at": snapshot.source_published_at,
        "published_age_days": _age_days(snapshot.source_published_at),
        "edition": snapshot.edition,
    }


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
    institution_policy: dict[str, Any] = field(default_factory=dict)
    # Criterion-level institutional evidence used by preservation-risk analysis.
    # Unlike institution_policy, this is evidence/context rather than a decision.
    institution_evidence: list[dict[str, Any]] = field(default_factory=list)
    # Backwards-compatible input alias. New adapters should use institution_policy.
    qnl: dict[str, Any] = field(default_factory=dict)
    hazard: dict[str, Any] = field(default_factory=dict)
    readiness: dict[str, Any] = field(default_factory=dict)
    trend: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    # Source-native fields retained for declarative criterion mappings. Adapters
    # should put upstream vocabulary here and keep criterion IDs out of adapter code.
    native_fields: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
    # Source-declared version/profile discriminator. This is identity metadata,
    # not a risk criterion. It is intentionally optional because some sources
    # encode versions in the name while others expose a dedicated field.
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
    external_hazard: list[dict[str, Any]] = field(default_factory=list)
    hazard_assessment: dict[str, Any] = field(default_factory=dict)
    readiness: list[dict[str, Any]] = field(default_factory=list)
    trend: list[dict[str, Any]] = field(default_factory=list)
    preservation_method: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    # Canonical version/profile when source evidence supplies one consistently.
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
        endorsed: bool = True,
    ) -> None:
        if not value:
            return
        kind = str(kind).strip()
        value = str(value).strip()
        if not kind or not value:
            return
        if endorsed:
            # Unendorsed claims stay out of the aggregated identifier map:
            # listing them there would read as "this format has that PUID".
            # They remain in identifier_claims as evidence.
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
        if not endorsed:
            claim["endorsed"] = False
        if confidence:
            claim["confidence"] = confidence
        if confidence_reason:
            claim["confidence_reason"] = confidence_reason
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
        data["institution_evidence_claims"] = sorted(
            data.get("institution_evidence_claims", []),
            key=lambda x: (
                x.get("institution_id") or "",
                x.get("criterion_id") or "",
                x.get("claim_id") or "",
            ),
        )
        return data
