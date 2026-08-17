from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from difflib import SequenceMatcher
import json
import re
from typing import Any, Protocol

from preservation_risk_manager.ai.base import AIMessage, AIProvider, AIRequest, parse_json_object
from preservation_risk_manager.data_access import RegistryReader
from preservation_risk_manager.format_resolver import FormatResolution, FormatResolver


_PUID_PATTERN = re.compile(r"(?:pronom\s*)?(x?-?fmt)\s*[:/\- ]\s*(\d+)$", re.IGNORECASE)
_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9.+_-]*", re.IGNORECASE)
_AI_UNSAFE_AMBIGUITY_TYPES = {
    "canonical_id",
    "verified_authority_identifier",
    "authority_identifier",
    "mime_type",
    "extension",
}


@dataclass(frozen=True)
class FormatIdentificationResult:
    input_value: str
    resolution: FormatResolution
    method: str
    normalized_value: str | None = None
    ai_attempted: bool = False
    ai_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def resolved(self) -> bool:
        return self.resolution.resolved

    def to_dict(self) -> dict[str, Any]:
        return {
            "input": self.input_value,
            "normalized": self.normalized_value,
            "method": self.method,
            "status": self.resolution.status,
            "match_type": self.resolution.match_type,
            "ai_attempted": self.ai_attempted,
            "ai": dict(self.ai_metadata),
        }


class FormatIdentificationPlugin(Protocol):
    """Optional fallback plugin for unresolved/ambiguous format observations."""

    def resolve(
        self,
        query: str,
        *,
        candidates: list[dict[str, Any]],
        base_resolution: FormatResolution,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """Return a verified local candidate and plugin metadata, or (None, metadata)."""


def _canonical_puid_variant(value: str) -> str | None:
    match = _PUID_PATTERN.fullmatch(str(value or "").strip())
    if not match:
        return None
    prefix = match.group(1).lower().replace("-", "")
    canonical_prefix = "x-fmt" if prefix == "xfmt" else "fmt"
    return f"{canonical_prefix}/{match.group(2)}"


def normalize_format_observation(value: str) -> list[str]:
    """Return conservative deterministic variants for a format observation.

    Syntax wrappers are removed before PUID normalization so values such as
    ``[fmt 18]`` and ``"x-fmt 123"`` remain deterministic and never need a paid
    AI fallback. This intentionally normalizes syntax only; it does not infer a
    format family/version from prose.
    """
    raw = str(value or "").strip()
    variants: list[str] = []
    if not raw:
        return variants

    compact = raw.strip("[](){}<>,;\"'").strip()
    for candidate in (raw, compact):
        normalized_puid = _canonical_puid_variant(candidate)
        if normalized_puid:
            variants.append(normalized_puid)
    if compact and compact != raw:
        variants.append(compact)

    seen: set[str] = set()
    deduped: list[str] = []
    for item in variants:
        key = item.lower()
        if item and key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


def _format_id(row: dict[str, Any]) -> str:
    return str(row.get("canonical_id") or row.get("format_id") or row.get("id") or "")


def _format_label(row: dict[str, Any]) -> str:
    return str(row.get("preferred_name") or row.get("name") or row.get("label") or _format_id(row))


def _as_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if str(value).strip() else []


def _nested_dict(value: Any, *keys: str) -> dict[str, Any]:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def _source_record_version(row: dict[str, Any]) -> str | None:
    direct = row.get("version")
    if direct is not None and str(direct).strip():
        return str(direct).strip()
    raw_record = _nested_dict(row, "raw", "record")
    version = raw_record.get("version")
    if version is not None and str(version).strip():
        return str(version).strip()
    return None


def _source_record_signature_names(row: dict[str, Any], *, limit: int = 6) -> list[str]:
    raw_record = _nested_dict(row, "raw", "record")
    names: list[str] = []
    for signature in raw_record.get("internalSignatures", []) or []:
        if not isinstance(signature, dict):
            continue
        name = str(signature.get("name") or "").strip()
        if name and name not in names:
            names.append(name)
        if len(names) >= limit:
            break
    return names


def enrich_candidate_from_source_records(reader: RegistryReader, row: dict[str, Any]) -> dict[str, Any]:
    """Add identity discriminators retained in source records to one candidate.

    Canonical records historically kept the PRONOM name but not its dedicated
    version field. The persisted source record still contains the authoritative
    raw PRONOM JSON, so identification can recover version/signature labels at
    query time without making the model infer them or requiring an immediate
    registry rebuild.
    """
    enriched = deepcopy(row)
    versions: list[str] = []
    signature_names: list[str] = []
    details: list[dict[str, Any]] = []

    for ref in row.get("source_records", []) or []:
        if not isinstance(ref, dict):
            continue
        source_id = str(ref.get("source_id") or "").strip()
        source_record_id = str(ref.get("source_record_id") or "").strip()
        if not source_record_id:
            continue
        filt: dict[str, Any] = {"source_record_id": source_record_id}
        if source_id:
            filt["source_id"] = source_id
        try:
            source_rows = reader.query("source_records", filt)
        except Exception:
            source_rows = []
        for source_row in source_rows:
            version = _source_record_version(source_row)
            if version and version not in versions:
                versions.append(version)
            names = _source_record_signature_names(source_row)
            for name in names:
                if name not in signature_names:
                    signature_names.append(name)
            if version or names:
                detail = {
                    "source_id": source_row.get("source_id"),
                    "source_record_id": source_row.get("source_record_id"),
                    "version": version,
                }
                if names:
                    detail["internal_signature_names"] = names
                if detail not in details:
                    details.append(detail)

    existing_version = enriched.get("version")
    if existing_version is not None and str(existing_version).strip():
        version = str(existing_version).strip()
        if version not in versions:
            versions.insert(0, version)
    if len(versions) == 1:
        enriched["version"] = versions[0]
    elif versions:
        enriched["versions"] = versions
    if signature_names:
        enriched["internal_signature_names"] = signature_names[:8]
    if details:
        enriched["identification_source_details"] = details[:8]
    return enriched


def _search_values(row: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in (
        "canonical_id",
        "format_id",
        "id",
        "preferred_name",
        "format_name",
        "name",
        "label",
        "short_name",
        "display_name",
        "family",
        "format_family",
        "format_type",
        "media_type",
        "category",
        "description",
        "version",
        "versions",
        "internal_signature_names",
        "aliases",
        "alternative_names",
        "extensions",
        "mime_types",
        "puids",
        "loc_ids",
        "nara_ids",
        "wikidata_ids",
    ):
        values.extend(_as_values(row.get(key)))
    identifiers = row.get("identifiers")
    if isinstance(identifiers, dict):
        for bucket in identifiers.values():
            values.extend(_as_values(bucket))
    return [value.strip() for value in values if value.strip()]


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in _TOKEN_PATTERN.findall(str(value or "")) if len(token) >= 2}


def _meaningful_length(value: str) -> int:
    return len(re.sub(r"[^a-z0-9]+", "", str(value or "").lower()))


def _is_descriptive_query(query: str) -> bool:
    """Return true for prose-like observations that need a wider AI shortlist."""
    return len(_tokens(query)) >= 4


def _fuzzy_score(query: str, row: dict[str, Any]) -> float:
    """Rank local candidates for optional AI review.

    Candidate generation is intentionally broader than deterministic identity
    resolution. Raw substring matching is guarded so one-character extensions
    such as ``a``, ``c`` and ``o`` cannot score 0.88 merely because the character
    appears somewhere in descriptive prose. Descriptive queries deliberately
    retain weaker lexical candidates because the bounded AI stage supplies the
    semantic decision and is still restricted to local registry candidates.
    """
    needle = query.lower().strip()
    if not needle:
        return 0.0
    query_tokens = _tokens(needle)
    best = 0.0
    for value in _search_values(row):
        candidate = value.lower().strip()
        if not candidate:
            continue
        if needle == candidate:
            return 1.0

        if _meaningful_length(needle) >= 3 and needle in candidate:
            best = max(best, 0.88)
        if _meaningful_length(candidate) >= 3 and candidate in needle:
            best = max(best, 0.88)

        candidate_tokens = _tokens(candidate)
        if candidate_tokens and query_tokens:
            overlap = candidate_tokens.intersection(query_tokens)
            if overlap:
                if candidate_tokens.issubset(query_tokens):
                    best = max(best, 0.96 if len(candidate_tokens) == 1 else 0.92)
                else:
                    coverage = len(overlap) / len(candidate_tokens)
                    query_coverage = len(overlap) / len(query_tokens)
                    best = max(best, 0.55 + (0.25 * coverage) + (0.10 * query_coverage))

        best = max(best, SequenceMatcher(None, needle, candidate).ratio())
    return min(best, 1.0)


def shortlist_candidates(
    query: str,
    rows: list[dict[str, Any]],
    *,
    limit: int = 20,
    minimum_score: float = 0.25,
) -> list[dict[str, Any]]:
    ranked = sorted(
        ((_fuzzy_score(query, row), row) for row in rows),
        key=lambda item: (-item[0], _format_label(item[1]).lower(), str(item[1].get("version") or "")),
    )
    # A hard 0.25 floor is appropriate for token-like observations but can make
    # semantic fallback impossible for prose. The AI resolver cannot select a
    # candidate it never sees, so descriptive queries use a lower lexical floor
    # while retaining the same bounded candidate limit and abstention controls.
    effective_minimum = min(float(minimum_score), 0.10) if _is_descriptive_query(query) else float(minimum_score)
    return [row for score, row in ranked if score >= effective_minimum][: max(1, int(limit))]


def _candidate_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_id": _format_id(row),
        "label": _format_label(row),
        "version": row.get("version"),
        "versions": _as_values(row.get("versions")),
        "internal_signature_names": _as_values(row.get("internal_signature_names")),
        "identifiers": row.get("identifiers") or {},
        "extensions": _as_values(row.get("extensions")),
        "mime_types": _as_values(row.get("mime_types")),
    }


class AIFormatIdentificationPlugin:
    """AI fallback that may select only from verified local registry candidates."""

    def __init__(
        self,
        provider: AIProvider,
        *,
        minimum_confidence: float = 0.80,
        max_candidates: int = 20,
    ) -> None:
        self.provider = provider
        self.minimum_confidence = float(minimum_confidence)
        self.max_candidates = max(1, int(max_candidates))

    def resolve(
        self,
        query: str,
        *,
        candidates: list[dict[str, Any]],
        base_resolution: FormatResolution,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        candidates = candidates[: self.max_candidates]
        candidate_payload = [_candidate_summary(row) for row in candidates]
        candidate_audit = {
            "candidate_count": len(candidate_payload),
            "candidates": candidate_payload,
        }
        if not candidates:
            return None, {
                "status": "no_match",
                "reason": "no_local_candidates",
                "provider": self.provider.describe(),
                "accepted": False,
                **candidate_audit,
            }

        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "status": {"type": "string", "enum": ["match", "ambiguous", "no_match", "abstain"]},
                "candidate_canonical_id": {"type": "string"},
                "candidate_canonical_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "rationale": {"type": "string"},
            },
            "required": [
                "status",
                "candidate_canonical_id",
                "candidate_canonical_ids",
                "confidence",
                "rationale",
            ],
        }
        request = AIRequest(
            messages=(
                AIMessage(
                    role="system",
                    content=(
                        "You are a bounded file-format identification assistant. Use ONLY the supplied local "
                        "canonical registry candidates. Never invent a PUID, identifier, format, version, or candidate. "
                        "Return status=match only when one supplied candidate is uniquely supported by the observation. "
                        "Return status=ambiguous when two or more supplied candidates are plausible but the observation "
                        "does not provide the version/profile/other discriminator needed to choose one; list only those "
                        "plausible candidate IDs in candidate_canonical_ids. Return status=no_match when none of the "
                        "supplied candidates is a defensible match. Treat exact format tokens, aliases, extensions, "
                        "identifiers, source-declared versions, and internal-signature names as evidence. Do not infer a "
                        "specific version when it is absent from the input. For match, put the chosen supplied ID in "
                        "candidate_canonical_id and set candidate_canonical_ids to an empty array. For ambiguous, leave "
                        "candidate_canonical_id empty and list the plausible supplied IDs in candidate_canonical_ids. "
                        "For no_match, leave candidate_canonical_id empty and candidate_canonical_ids empty."
                    ),
                ),
                AIMessage(
                    role="user",
                    content=json.dumps(
                        {
                            "input": query,
                            "deterministic_status": base_resolution.status,
                            "deterministic_match_type": base_resolution.match_type,
                            "candidates": candidate_payload,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                ),
            ),
            response_schema=schema,
            response_schema_name="format_identification",
            temperature=0.0,
        )
        response = self.provider.generate(request)
        decision = response.structured or parse_json_object(response.text or "{}", label="AI identification response")
        status = str(decision.get("status") or "no_match")
        candidate_id = str(decision.get("candidate_canonical_id") or "").strip()
        candidate_ids = [
            str(value).strip()
            for value in (decision.get("candidate_canonical_ids") or [])
            if str(value).strip()
        ]
        try:
            confidence = float(decision.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0

        by_id = {_format_id(row): row for row in candidates if _format_id(row)}
        metadata = {
            "status": status,
            "confidence": confidence,
            "rationale": str(decision.get("rationale") or ""),
            "candidate_canonical_id": candidate_id or None,
            "candidate_canonical_ids": candidate_ids,
            "minimum_confidence": self.minimum_confidence,
            "provider": self.provider.describe(),
            **candidate_audit,
        }

        if status == "ambiguous":
            valid_ambiguous_ids = [value for value in candidate_ids if value in by_id]
            invalid_ids = [value for value in candidate_ids if value not in by_id]
            metadata["candidate_canonical_ids"] = valid_ambiguous_ids
            metadata["accepted"] = False
            if invalid_ids:
                metadata["invalid_candidate_canonical_ids"] = invalid_ids
            if len(valid_ambiguous_ids) < 2:
                metadata["reason"] = "ambiguous_status_requires_at_least_two_supplied_candidates"
                metadata["status"] = "no_match"
            return None, metadata

        if status != "match" or confidence < self.minimum_confidence or not candidate_id:
            metadata["accepted"] = False
            return None, metadata

        candidate = by_id.get(candidate_id)
        if candidate is None:
            metadata.update({"accepted": False, "reason": "candidate_not_in_supplied_registry_set"})
            return None, metadata

        metadata["accepted"] = True
        return candidate, metadata


class IdentificationResolver:
    """Resolve a format observation programmatically, with an optional plugin fallback."""

    def __init__(
        self,
        reader: RegistryReader,
        *,
        plugin: FormatIdentificationPlugin | None = None,
        fuzzy_candidate_limit: int = 20,
    ) -> None:
        self.reader = reader
        self.base = FormatResolver(reader)
        self.plugin = plugin
        self.fuzzy_candidate_limit = max(1, int(fuzzy_candidate_limit))

    def _enriched_candidates(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [enrich_candidate_from_source_records(self.reader, row) for row in rows]

    def resolve(self, query: str) -> FormatIdentificationResult:
        original = str(query or "").strip()
        base_resolution = self.base.resolve(original)
        if base_resolution.resolved:
            return FormatIdentificationResult(
                input_value=original,
                normalized_value=original,
                resolution=base_resolution,
                method="deterministic_exact",
            )

        for variant in normalize_format_observation(original):
            normalized_resolution = self.base.resolve(variant)
            if normalized_resolution.resolved:
                return FormatIdentificationResult(
                    input_value=original,
                    normalized_value=variant,
                    resolution=normalized_resolution,
                    method="deterministic_normalization",
                )
            if base_resolution.not_found and normalized_resolution.ambiguous:
                base_resolution = normalized_resolution

        if self.plugin is None:
            return FormatIdentificationResult(
                input_value=original,
                normalized_value=None,
                resolution=base_resolution,
                method="deterministic_best_effort",
            )

        if base_resolution.ambiguous and base_resolution.match_type in _AI_UNSAFE_AMBIGUITY_TYPES:
            return FormatIdentificationResult(
                input_value=original,
                normalized_value=None,
                resolution=base_resolution,
                method="programmatic_ambiguity_requires_review",
                ai_attempted=False,
                ai_metadata={
                    "status": "not_attempted",
                    "reason": "unsafe_or_insufficient_ambiguity_for_ai",
                },
            )

        if base_resolution.ambiguous and base_resolution.matches:
            candidates = self._enriched_candidates(list(base_resolution.matches))
        else:
            raw_candidates = shortlist_candidates(
                original,
                self.reader.list_canonical_formats(),
                limit=self.fuzzy_candidate_limit,
            )
            candidates = self._enriched_candidates(raw_candidates)

        try:
            candidate, metadata = self.plugin.resolve(
                original,
                candidates=candidates,
                base_resolution=base_resolution,
            )
        except Exception as exc:
            return FormatIdentificationResult(
                input_value=original,
                normalized_value=None,
                resolution=base_resolution,
                method="ai_fallback_error_programmatic_result_retained",
                ai_attempted=True,
                ai_metadata={
                    "status": "error",
                    "accepted": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "candidate_count": len(candidates),
                    "candidates": [_candidate_summary(row) for row in candidates],
                },
            )

        if candidate is not None:
            resolution = FormatResolution(
                query=original,
                status="resolved",
                match_type="ai_candidate_verified_local",
                format_doc=candidate,
                matches=(candidate,),
            )
            return FormatIdentificationResult(
                input_value=original,
                normalized_value=None,
                resolution=resolution,
                method="ai_fallback",
                ai_attempted=True,
                ai_metadata=metadata,
            )

        if metadata.get("status") == "ambiguous":
            wanted = set(str(value) for value in metadata.get("candidate_canonical_ids") or [])
            ambiguous_matches = tuple(row for row in candidates if _format_id(row) in wanted)
            if len(ambiguous_matches) >= 2:
                resolution = FormatResolution(
                    query=original,
                    status="ambiguous",
                    match_type="ai_candidate_ambiguity",
                    format_doc=None,
                    matches=ambiguous_matches,
                )
                return FormatIdentificationResult(
                    input_value=original,
                    normalized_value=None,
                    resolution=resolution,
                    method="ai_fallback_ambiguous",
                    ai_attempted=True,
                    ai_metadata=metadata,
                )

        method = "ai_fallback_no_match" if metadata.get("status") in {"no_match", "abstain"} else "ai_fallback_abstained"
        return FormatIdentificationResult(
            input_value=original,
            normalized_value=None,
            resolution=base_resolution,
            method=method,
            ai_attempted=True,
            ai_metadata=metadata,
        )
