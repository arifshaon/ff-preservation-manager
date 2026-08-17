from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from preservation_risk_manager.answer_derivation import derive_answers
from preservation_risk_manager.data_access import RegistryReader
from preservation_risk_manager.evidence_packs import build_evidence_pack, evidence_hash
from preservation_risk_manager.format_resolver import FormatResolver
from preservation_risk_manager.frameworks import RiskFramework
from preservation_risk_manager.scoring import score_answers


SUPPORTED_ACTIONS = (
    "assess_format",
    "search_formats",
    "assess_format_family",
    "list_at_risk_formats",
)
DEFAULT_AT_RISK_BANDS = ("Moderate", "High")


class RequestValidationError(ValueError):
    """Raised when a canonical integration request is invalid."""


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _format_id(format_doc: dict[str, Any]) -> str | None:
    value = format_doc.get("canonical_id") or format_doc.get("format_id") or format_doc.get("id")
    return str(value) if value is not None else None


def _format_label(format_doc: dict[str, Any]) -> str | None:
    value = (
        format_doc.get("preferred_name")
        or format_doc.get("format_name")
        or format_doc.get("name")
        or format_doc.get("label")
        or format_doc.get("display_name")
    )
    return str(value) if value is not None else None


def _format_identity(format_doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "format_id": _format_id(format_doc),
        "label": _format_label(format_doc),
        "extensions": [str(value) for value in _as_list(format_doc.get("extensions") or format_doc.get("file_extensions"))],
        "mime_types": [str(value) for value in _as_list(format_doc.get("mime_types") or format_doc.get("mime_type"))],
        "puids": [str(value) for value in _as_list(format_doc.get("puids"))],
        "loc_ids": [str(value) for value in _as_list(format_doc.get("loc_ids"))],
    }


def _searchable_values(format_doc: dict[str, Any]) -> list[str]:
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
        "aliases",
        "alternative_names",
        "extensions",
        "extension",
        "file_extensions",
        "mime_types",
        "mime_type",
        "puids",
        "loc_ids",
        "nara_ids",
    ):
        for value in _as_list(format_doc.get(key)):
            if isinstance(value, dict):
                continue
            text = str(value).strip()
            if text:
                values.append(text)
    identifiers = format_doc.get("identifiers")
    if isinstance(identifiers, dict):
        for bucket in identifiers.values():
            for value in _as_list(bucket):
                text = str(value).strip()
                if text:
                    values.append(text)
    return values


def _strong_identifiers(format_doc: dict[str, Any]) -> set[tuple[str, str]]:
    values: set[tuple[str, str]] = set()
    direct = {
        "puid": "puids",
        "loc": "loc_ids",
        "nara": "nara_ids",
    }
    for kind, field in direct.items():
        for value in _as_list(format_doc.get(field)):
            text = str(value).strip().lower()
            if text:
                values.add((kind, text))
    identifiers = format_doc.get("identifiers")
    if isinstance(identifiers, dict):
        for kind in ("puid", "loc", "nara"):
            for value in _as_list(identifiers.get(kind)):
                text = str(value).strip().lower()
                if text:
                    values.add((kind, text))
    return values


def _canonical_preference(format_doc: dict[str, Any]) -> int:
    canonical_id = (_format_id(format_doc) or "").lower()
    if canonical_id.startswith("fmt-"):
        return 3
    if canonical_id.startswith(("puid-", "loc-", "nara-")):
        return 1
    return 2


def _dedupe_format_docs(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prefer aggregate canonical records over source aliases sharing strong IDs."""
    ordered = sorted(
        rows,
        key=lambda row: (
            -_canonical_preference(row),
            (_format_label(row) or _format_id(row) or "").lower(),
        ),
    )
    kept: list[dict[str, Any]] = []
    seen_strong_ids: set[tuple[str, str]] = set()
    seen_format_ids: set[str] = set()
    for row in ordered:
        format_id = (_format_id(row) or "").lower()
        strong_ids = _strong_identifiers(row)
        if format_id and format_id in seen_format_ids:
            continue
        if strong_ids and strong_ids.intersection(seen_strong_ids):
            continue
        kept.append(row)
        if format_id:
            seen_format_ids.add(format_id)
        seen_strong_ids.update(strong_ids)
    return kept


def search_format_docs(
    reader: RegistryReader,
    query: str,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return current canonical formats matching a human/family search term.

    This is intentionally a discovery search, not authoritative identity
    resolution. Exact assessment still goes through FormatResolver. Strong-ID
    duplicates are collapsed in favour of aggregate canonical records.
    """
    needle = str(query or "").strip().lower()
    if not needle:
        return []
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for row in reader.list_canonical_formats():
        values = _searchable_values(row)
        normalized = [value.lower() for value in values]
        exact = needle in normalized
        contains = any(needle in value for value in normalized)
        if not exact and not contains:
            continue
        score = 2 if exact else 1
        label = (_format_label(row) or _format_id(row) or "").lower()
        ranked.append((score, label, row))

    deduped = _dedupe_format_docs(item[2] for item in ranked)
    score_by_id = {
        (_format_id(item[2]) or ""): item[0]
        for item in ranked
    }
    deduped.sort(
        key=lambda row: (
            -score_by_id.get(_format_id(row) or "", 0),
            (_format_label(row) or _format_id(row) or "").lower(),
        )
    )
    rows = [deepcopy(row) for row in deduped]
    return rows[:limit] if limit is not None else rows


def normalize_request(request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise RequestValidationError("Request must be a JSON object.")
    action = str(request.get("action") or "").strip()
    if action not in SUPPORTED_ACTIONS:
        raise RequestValidationError(
            f"Unsupported action '{action}'. Allowed actions: {', '.join(SUPPORTED_ACTIONS)}"
        )

    filters = request.get("filters") or {}
    if not isinstance(filters, dict):
        raise RequestValidationError("filters must be a JSON object when supplied.")
    risk_bands = filters.get("risk_bands")
    if risk_bands is None and action == "list_at_risk_formats":
        risk_bands = list(DEFAULT_AT_RISK_BANDS)
    if risk_bands is None:
        risk_bands = []
    if not isinstance(risk_bands, list):
        raise RequestValidationError("filters.risk_bands must be an array.")

    scope = str(request.get("scope") or "global").strip().lower()
    if scope not in {"global", "institution"}:
        raise RequestValidationError("scope must be 'global' or 'institution'.")
    institution_id = request.get("institution_id")
    if scope == "institution" and not institution_id:
        raise RequestValidationError("institution_id is required when scope is 'institution'.")

    limit_raw = request.get("limit", 100)
    try:
        limit = int(limit_raw)
    except (TypeError, ValueError) as exc:
        raise RequestValidationError("limit must be an integer.") from exc
    if limit <= 0 or limit > 5000:
        raise RequestValidationError("limit must be between 1 and 5000.")

    normalized = {
        "action": action,
        "format": str(request.get("format") or "").strip() or None,
        "query": str(request.get("query") or "").strip() or None,
        "filters": {
            "family": str(filters.get("family") or "").strip() or None,
            "risk_bands": [str(value) for value in risk_bands],
        },
        "scope": scope,
        "institution_id": str(institution_id).strip() if institution_id else None,
        "limit": limit,
    }

    if action == "assess_format" and not normalized["format"]:
        raise RequestValidationError("format is required for assess_format.")
    if action == "search_formats" and not normalized["query"]:
        raise RequestValidationError("query is required for search_formats.")
    if action == "assess_format_family" and not normalized["filters"]["family"]:
        raise RequestValidationError("filters.family is required for assess_format_family.")
    return normalized


def _assessment_for_doc(
    reader: RegistryReader,
    framework: RiskFramework,
    format_doc: dict[str, Any],
    *,
    institution_id: str | None,
) -> dict[str, Any]:
    claims = reader.get_criterion_claims_for_format(format_doc, institution_id=institution_id)
    pack = build_evidence_pack(
        format_doc,
        institution_id=institution_id,
        criterion_claims=claims,
    )
    answers = derive_answers(framework, pack)
    analysis = score_answers(framework, answers.get("scoring_answers") or answers["answers"])
    main_risk_factors = [
        {
            "question_id": row.get("question_id"),
            "answer_id": row.get("answer_id"),
            "weighted_points": row.get("weighted_points"),
            "derivation_status": row.get("derivation_status"),
        }
        for row in analysis.get("question_results", [])
        if float(row.get("weighted_points") or 0) > 0
    ]
    return {
        "format": _format_identity(format_doc),
        "risk_band": analysis.get("analysed_band"),
        "score": analysis.get("score"),
        "max_score": analysis.get("max_score"),
        "analysis_status": analysis.get("analysis_status"),
        "evidence_completeness": analysis.get("evidence_completeness"),
        "missing_count": analysis.get("missing_count"),
        "abstention_count": analysis.get("abstention_count"),
        "main_risk_factors": main_risk_factors,
        "questions": analysis.get("question_results", []),
        "criterion_claims_used": len(claims),
        "evidence_hash": evidence_hash(pack),
    }


def _band_rank(band: Any) -> int:
    return {"High": 3, "Moderate": 2, "Low": 1}.get(str(band), 0)


def _rank_assessments(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            -_band_rank(row.get("risk_band")),
            -float(row.get("score") or 0),
            str((row.get("format") or {}).get("label") or ""),
        ),
    )


def _base_response(request: dict[str, Any], framework: RiskFramework) -> dict[str, Any]:
    return {
        "status": "ok",
        "request": deepcopy(request),
        "framework": {
            "framework_id": framework.framework_id,
            "version": framework.version,
        },
        "scope": request["scope"],
        "institution_id": request.get("institution_id"),
    }


def execute_request(
    reader: RegistryReader,
    framework: RiskFramework,
    request: dict[str, Any],
) -> dict[str, Any]:
    """Execute one canonical human/system request and always return JSON-safe data."""
    request = normalize_request(request)
    result = _base_response(request, framework)
    institution_id = request.get("institution_id") if request["scope"] == "institution" else None
    action = request["action"]

    if action == "search_formats":
        matches = search_format_docs(reader, request["query"], limit=request["limit"])
        result.update({
            "results": [_format_identity(row) for row in matches],
            "result_count": len(matches),
        })
        return result

    if action == "assess_format":
        resolution = FormatResolver(reader).resolve(request["format"])
        if not resolution.resolved or not resolution.format_doc:
            result["status"] = resolution.status
            result["resolution"] = {
                "query": resolution.query,
                "status": resolution.status,
                "match_type": resolution.match_type,
                "matches": [_format_identity(row) for row in resolution.matches],
            }
            return result
        result["result"] = _assessment_for_doc(
            reader,
            framework,
            resolution.format_doc,
            institution_id=institution_id,
        )
        result["result_count"] = 1
        return result

    family = request["filters"].get("family")
    if family:
        candidates = search_format_docs(reader, family, limit=request["limit"])
    else:
        candidates = _dedupe_format_docs(reader.list_canonical_formats())[: request["limit"]]
    assessments = [
        _assessment_for_doc(reader, framework, row, institution_id=institution_id)
        for row in candidates
    ]
    assessments = _rank_assessments(assessments)

    if action == "list_at_risk_formats":
        allowed_bands = set(request["filters"].get("risk_bands") or DEFAULT_AT_RISK_BANDS)
        assessments = [row for row in assessments if row.get("risk_band") in allowed_bands]

    result.update({
        "filters": deepcopy(request["filters"]),
        "candidate_count": len(candidates),
        "results": assessments,
        "result_count": len(assessments),
    })
    return result
