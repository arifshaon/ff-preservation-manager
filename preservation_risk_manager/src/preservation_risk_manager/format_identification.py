from __future__ import annotations

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


def normalize_format_observation(value: str) -> list[str]:
    """Return conservative deterministic variants for a format observation.

    This intentionally normalizes only syntax that is safe to recognize without
    external knowledge. It does not infer a format family/version from prose.
    """
    raw = str(value or "").strip()
    variants: list[str] = []
    if not raw:
        return variants

    match = _PUID_PATTERN.fullmatch(raw)
    if match:
        prefix = match.group(1).lower().replace("-", "")
        canonical_prefix = "x-fmt" if prefix == "xfmt" else "fmt"
        variants.append(f"{canonical_prefix}/{match.group(2)}")

    compact = raw.strip().strip("[](){}<>,;\"'")
    if compact != raw:
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


def _search_values(row: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in (
        "canonical_id",
        "format_id",
        "id",
        "preferred_name",
        "name",
        "label",
        "short_name",
        "display_name",
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


def _fuzzy_score(query: str, row: dict[str, Any]) -> float:
    """Rank local candidates for optional AI review.

    Candidate generation is intentionally broader than deterministic identity
    resolution. A descriptive observation such as ``Adobe Shockwave Flash SWF
    file`` must retain a registry record whose extension/alias is exactly ``swf``
    even though comparing the whole phrase to the three-letter token produces a
    weak SequenceMatcher score. The AI plugin still decides only among supplied
    local candidates and may abstain.
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
        if needle in candidate or candidate in needle:
            best = max(best, 0.88)

        candidate_tokens = _tokens(candidate)
        if candidate_tokens and query_tokens:
            overlap = candidate_tokens.intersection(query_tokens)
            if overlap:
                # A complete candidate token set contained in the observation is
                # highly relevant for aliases/extensions such as SWF, JPEG, TIFF.
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
        key=lambda item: (-item[0], _format_label(item[1]).lower()),
    )
    return [row for score, row in ranked[:limit] if score >= minimum_score]


def _candidate_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_id": _format_id(row),
        "label": _format_label(row),
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
                "status": "abstain",
                "reason": "no_local_candidates",
                "provider": self.provider.describe(),
                **candidate_audit,
            }

        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "status": {"type": "string", "enum": ["match", "abstain"]},
                "candidate_canonical_id": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "rationale": {"type": "string"},
            },
            "required": ["status", "candidate_canonical_id", "confidence", "rationale"],
        }
        request = AIRequest(
            messages=(
                AIMessage(
                    role="system",
                    content=(
                        "You are a bounded file-format identification assistant. Select ONLY from the supplied "
                        "local canonical registry candidates. Never invent a PUID, identifier, format, or candidate. "
                        "Treat exact format tokens, aliases, extensions and identifiers in the user's observation as "
                        "strong evidence for candidate relevance, but do not infer a specific version when the input "
                        "does not distinguish among multiple versions. If the input is insufficient, ambiguous, or "
                        "no supplied candidate is a defensible single match, return status=abstain. "
                        "candidate_canonical_id must be empty when abstaining."
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
        status = str(decision.get("status") or "abstain")
        candidate_id = str(decision.get("candidate_canonical_id") or "").strip()
        try:
            confidence = float(decision.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0

        metadata = {
            "status": status,
            "confidence": confidence,
            "rationale": str(decision.get("rationale") or ""),
            "candidate_canonical_id": candidate_id or None,
            "minimum_confidence": self.minimum_confidence,
            "provider": self.provider.describe(),
            **candidate_audit,
        }
        if status != "match" or confidence < self.minimum_confidence or not candidate_id:
            metadata["accepted"] = False
            return None, metadata

        by_id = {_format_id(row): row for row in candidates if _format_id(row)}
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

        # Do not ask AI to arbitrate an authority collision or a bare extension/MIME
        # ambiguity. Those cases either indicate a registry/data issue or simply do
        # not contain enough information for a defensible variant-level decision.
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

        all_rows = self.reader.list_canonical_formats()
        candidates = (
            list(base_resolution.matches)
            if base_resolution.ambiguous and base_resolution.matches
            else shortlist_candidates(original, all_rows, limit=self.fuzzy_candidate_limit)
        )
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

        return FormatIdentificationResult(
            input_value=original,
            normalized_value=None,
            resolution=base_resolution,
            method="ai_fallback_abstained",
            ai_attempted=True,
            ai_metadata=metadata,
        )
