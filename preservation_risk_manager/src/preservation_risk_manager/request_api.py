from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from preservation_risk_manager.answer_derivation import derive_answers
from preservation_risk_manager.data_access import RegistryReader
from preservation_risk_manager.evidence_gaps import diagnose_format_evidence_gaps, summarize_evidence_gaps
from preservation_risk_manager.evidence_packs import build_evidence_pack, evidence_hash
from preservation_risk_manager.evidence_remediation import (
    plan_format_evidence_remediation,
    summarize_evidence_remediation,
)
from preservation_risk_manager.format_resolver import FormatResolver
from preservation_risk_manager.frameworks import RiskFramework
from preservation_risk_manager.question_assessment import assess_format_questions, list_question_catalog
from preservation_risk_manager.risk_context import build_external_risk_context
from preservation_risk_manager.scoring import score_answers


SUPPORTED_ACTIONS = (
    "assess_format",
    "assess_format_questions",
    "search_formats",
    "assess_format_family",
    "list_at_risk_formats",
    "list_assessment_questions",
    "list_evidence_gaps",
    "plan_evidence_remediation",
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


def _identifier_bucket(format_doc: dict[str, Any], kind: str, *direct_fields: str) -> list[str]:
    values: list[str] = []
    for field in direct_fields:
        for value in _as_list(format_doc.get(field)):
            text = str(value).strip()
            if text and text not in values:
                values.append(text)
    identifiers = format_doc.get("identifiers") or {}
    if isinstance(identifiers, dict):
        for value in _as_list(identifiers.get(kind)):
            text = str(value).strip()
            if text and text not in values:
                values.append(text)
    return values


def _format_identity(format_doc: dict[str, Any]) -> dict[str, Any]:
    identity = {
        "format_id": _format_id(format_doc),
        "label": _format_label(format_doc),
        "extensions": _identifier_bucket(format_doc, "extension", "extensions", "file_extensions", "extension"),
        "mime_types": _identifier_bucket(format_doc, "mime", "mime_types", "mime_type"),
        "puids": _identifier_bucket(format_doc, "puid", "puids"),
        "loc_ids": _identifier_bucket(format_doc, "loc", "loc_ids"),
    }
    if format_doc.get("version") is not None:
        identity["version"] = str(format_doc.get("version"))
    return identity


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


def _family_searchable_values(format_doc: dict[str, Any]) -> tuple[list[str], bool]:
    explicit: list[str] = []
    for key in ("family", "format_family", "family_id", "parent_family", "member_of"):
        for value in _as_list(format_doc.get(key)):
            if isinstance(value, dict):
                continue
            text = str(value).strip()
            if text:
                explicit.append(text)
    if explicit:
        return explicit, True

    fallback: list[str] = []
    for key in (
        "preferred_name",
        "format_name",
        "name",
        "label",
        "short_name",
        "display_name",
        "aliases",
        "alternative_names",
    ):
        for value in _as_list(format_doc.get(key)):
            if isinstance(value, dict):
                continue
            text = str(value).strip()
            if text:
                fallback.append(text)
    return fallback, False


def _strong_identifiers(format_doc: dict[str, Any]) -> set[tuple[str, str]]:
    values: set[tuple[str, str]] = set()
    for kind, field in {"puid": "puids", "loc": "loc_ids", "nara": "nara_ids"}.items():
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
    ordered = sorted(
        rows,
        key=lambda row: (-_canonical_preference(row), (_format_label(row) or _format_id(row) or "").lower()),
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


def search_format_docs(reader: RegistryReader, query: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    """Return current canonical formats matching a general discovery term."""
    needle = str(query or "").strip().lower()
    if not needle:
        return []
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for row in reader.list_canonical_formats():
        normalized = [value.lower() for value in _searchable_values(row)]
        exact = needle in normalized
        contains = any(needle in value for value in normalized)
        if not exact and not contains:
            continue
        ranked.append((2 if exact else 1, (_format_label(row) or _format_id(row) or "").lower(), row))

    deduped = _dedupe_format_docs(item[2] for item in ranked)
    score_by_id = {(_format_id(item[2]) or ""): item[0] for item in ranked}
    deduped.sort(key=lambda row: (-score_by_id.get(_format_id(row) or "", 0), (_format_label(row) or _format_id(row) or "").lower()))
    rows = [deepcopy(row) for row in deduped]
    return rows[:limit] if limit is not None else rows


def search_family_docs(reader: RegistryReader, family: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    """Return plausible members of a requested format family.

    Explicit family metadata wins. Without it, only names and aliases are used;
    extensions, MIME types and authority identifiers cannot establish family
    membership.
    """
    needle = str(family or "").strip().lower()
    if not needle:
        return []
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for row in reader.list_canonical_formats():
        values, explicit = _family_searchable_values(row)
        normalized = [value.lower() for value in values]
        exact = needle in normalized
        contains = any(needle in value for value in normalized)
        if not exact and not contains:
            continue
        score = (4 if exact else 3) if explicit else (2 if exact else 1)
        ranked.append((score, (_format_label(row) or _format_id(row) or "").lower(), row))

    deduped = _dedupe_format_docs(item[2] for item in ranked)
    score_by_id = {(_format_id(item[2]) or ""): item[0] for item in ranked}
    deduped.sort(key=lambda row: (-score_by_id.get(_format_id(row) or "", 0), (_format_label(row) or _format_id(row) or "").lower()))
    rows = [deepcopy(row) for row in deduped]
    return rows[:limit] if limit is not None else rows


def _string_list(value: Any, *, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise RequestValidationError(f"{field_name} must be an array.")
    return [str(item) for item in value if str(item).strip()]


def normalize_request(request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise RequestValidationError("Request must be a JSON object.")
    action = str(request.get("action") or "").strip()
    if action not in SUPPORTED_ACTIONS:
        raise RequestValidationError(f"Unsupported action '{action}'. Allowed actions: {', '.join(SUPPORTED_ACTIONS)}")

    filters = request.get("filters") or {}
    if not isinstance(filters, dict):
        raise RequestValidationError("filters must be a JSON object when supplied.")
    risk_bands = filters.get("risk_bands")
    if risk_bands is None and action == "list_at_risk_formats":
        risk_bands = list(DEFAULT_AT_RISK_BANDS)
    if risk_bands is None:
        risk_bands = []
    risk_bands = _string_list(risk_bands, field_name="filters.risk_bands")
    domains = _string_list(filters.get("domains"), field_name="filters.domains")
    question_ids = _string_list(filters.get("question_ids"), field_name="filters.question_ids")

    scope = str(request.get("scope") or "global").strip().lower()
    if scope not in {"global", "institution"}:
        raise RequestValidationError("scope must be 'global' or 'institution'.")
    institution_id = request.get("institution_id")
    if scope == "institution" and not institution_id:
        raise RequestValidationError("institution_id is required when scope is 'institution'.")

    try:
        limit = int(request.get("limit", 100))
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
            "risk_bands": risk_bands,
            "domains": domains,
            "question_ids": question_ids,
            "content_type": str(filters.get("content_type") or "").strip() or None,
        },
        "scope": scope,
        "institution_id": str(institution_id).strip() if institution_id else None,
        "limit": limit,
    }

    if action in {"assess_format", "assess_format_questions"} and not normalized["format"]:
        raise RequestValidationError(f"format is required for {action}.")
    if action == "search_formats" and not normalized["query"]:
        raise RequestValidationError("query is required for search_formats.")
    if action == "assess_format_family" and not normalized["filters"]["family"]:
        raise RequestValidationError("filters.family is required for assess_format_family.")
    if action in {"list_evidence_gaps", "plan_evidence_remediation"} and not (
        normalized["format"] or normalized["filters"]["family"]
    ):
        raise RequestValidationError(f"format or filters.family is required for {action}.")
    return normalized


def _assessment_for_doc(
    reader: RegistryReader,
    framework: RiskFramework,
    format_doc: dict[str, Any],
    *,
    institution_id: str | None,
) -> dict[str, Any]:
    claims = reader.get_criterion_claims_for_format(format_doc, institution_id=institution_id)
    pack = build_evidence_pack(format_doc, institution_id=institution_id, criterion_claims=claims)
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
        if not bool(row.get("abstention")) and float(row.get("weighted_points") or 0) > 0
    ]
    return {
        "format": _format_identity(format_doc),
        "risk_band": analysis.get("analysed_band"),
        "band_suppressed_reason": analysis.get("band_suppressed_reason"),
        "calibration_status": analysis.get("calibration_status"),
        "banding_enabled": analysis.get("banding_enabled"),
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
        "external_risk_context": build_external_risk_context(reader, format_doc),
    }


def _band_rank(band: Any) -> int:
    return {"High": 3, "Moderate": 2, "Low": 1}.get(str(band), 0)


def _rank_assessments(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (-_band_rank(row.get("risk_band")), -float(row.get("score") or 0), str((row.get("format") or {}).get("label") or "")),
    )


def _assessment_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    band_counts = {"High": 0, "Moderate": 0, "Low": 0, "Unbanded": 0}
    status_counts: dict[str, int] = {}
    suppressed_reason_counts: dict[str, int] = {}
    for row in rows:
        band = row.get("risk_band")
        if band in {"High", "Moderate", "Low"}:
            band_counts[str(band)] += 1
        else:
            band_counts["Unbanded"] += 1
        status = str(row.get("analysis_status") or "Unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        reason = row.get("band_suppressed_reason")
        if reason:
            text = str(reason)
            suppressed_reason_counts[text] = suppressed_reason_counts.get(text, 0) + 1
    return {
        "band_counts": band_counts,
        "analysis_status_counts": status_counts,
        "band_suppressed_reason_counts": suppressed_reason_counts,
        "banded_count": band_counts["High"] + band_counts["Moderate"] + band_counts["Low"],
        "unbanded_count": band_counts["Unbanded"],
    }


def _compact_unbanded(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "format": deepcopy(row.get("format") or {}),
        "analysis_status": row.get("analysis_status"),
        "band_suppressed_reason": row.get("band_suppressed_reason"),
        "evidence_completeness": row.get("evidence_completeness"),
        "missing_count": row.get("missing_count"),
        "abstention_count": row.get("abstention_count"),
        "criterion_claims_used": row.get("criterion_claims_used"),
        "evidence_hash": row.get("evidence_hash"),
        "external_risk_context": deepcopy(row.get("external_risk_context") or {}),
    }


def _base_response(request: dict[str, Any], framework: RiskFramework) -> dict[str, Any]:
    return {
        "status": "ok",
        "request": deepcopy(request),
        "framework": {
            "framework_id": framework.framework_id,
            "version": framework.version,
            "calibration_status": framework.calibration_status,
            "banding_enabled": framework.banding_enabled,
        },
        "scope": request["scope"],
        "institution_id": request.get("institution_id"),
    }


def _resolution_failure(result: dict[str, Any], resolution: Any) -> dict[str, Any]:
    total = int(getattr(resolution, "total_match_count", 0) or len(resolution.matches))
    result["status"] = resolution.status
    result["resolution"] = {
        "query": resolution.query,
        "status": resolution.status,
        "match_type": resolution.match_type,
        "match_count": total,
        "matches_returned": len(resolution.matches),
        "matches": [_format_identity(row) for row in resolution.matches],
    }
    if resolution.status == "ambiguous":
        result["resolution"]["message"] = (
            f"'{resolution.query}' matches {total} formats; showing {len(resolution.matches)}. "
            "Specify a canonical ID or authority identifier to assess one format."
        )
    return result


def execute_request(reader: RegistryReader, framework: RiskFramework, request: dict[str, Any]) -> dict[str, Any]:
    """Execute one canonical human/system request and always return JSON-safe data."""
    request = normalize_request(request)
    result = _base_response(request, framework)
    institution_id = request.get("institution_id") if request["scope"] == "institution" else None
    action = request["action"]
    filters = request["filters"]

    if action == "list_assessment_questions":
        catalog = list_question_catalog(
            framework,
            domains=filters.get("domains"),
            question_ids=filters.get("question_ids"),
            content_type=filters.get("content_type"),
        )
        result.update({
            "domains": catalog["domains"],
            "results": catalog["questions"],
            "result_count": catalog["question_count"],
        })
        return result

    if action == "search_formats":
        matches = search_format_docs(reader, request["query"], limit=request["limit"])
        result.update({"results": [_format_identity(row) for row in matches], "result_count": len(matches)})
        return result

    single_format_actions = {
        "assess_format",
        "assess_format_questions",
        "list_evidence_gaps",
        "plan_evidence_remediation",
    }
    if action in single_format_actions and request.get("format"):
        resolution = FormatResolver(reader).resolve(request["format"])
        if not resolution.resolved or not resolution.format_doc:
            return _resolution_failure(result, resolution)
        if action == "assess_format":
            result["result"] = _assessment_for_doc(reader, framework, resolution.format_doc, institution_id=institution_id)
        elif action == "assess_format_questions":
            question_result = assess_format_questions(
                reader,
                framework,
                resolution.format_doc,
                domains=filters.get("domains"),
                question_ids=filters.get("question_ids"),
                content_type=filters.get("content_type"),
                institution_id=institution_id,
            )
            if isinstance(question_result, dict):
                question_result["external_risk_context"] = build_external_risk_context(reader, resolution.format_doc)
            result["result"] = question_result
        else:
            diagnostic = diagnose_format_evidence_gaps(
                reader,
                framework,
                resolution.format_doc,
                institution_id=institution_id,
            )
            result["result"] = (
                diagnostic
                if action == "list_evidence_gaps"
                else plan_format_evidence_remediation(diagnostic)
            )
        result["result_count"] = 1
        return result

    family = filters.get("family")
    if family:
        candidates = search_family_docs(reader, family, limit=request["limit"])
    else:
        candidates = _dedupe_format_docs(reader.list_canonical_formats())[: request["limit"]]

    if action in {"list_evidence_gaps", "plan_evidence_remediation"}:
        diagnostics = [
            diagnose_format_evidence_gaps(reader, framework, row, institution_id=institution_id)
            for row in candidates
        ]
        gap_results = [row for row in diagnostics if int(row.get("gap_count") or 0) > 0]
        status_rank = {"Needs Assessment": 3, "Not Assessed": 2, "Partially Assessed": 1, "Assessed": 0}
        gap_results.sort(
            key=lambda row: (
                -status_rank.get(str(row.get("analysis_status")), 0),
                -int(row.get("gap_count") or 0),
                str((row.get("format") or {}).get("label") or ""),
            )
        )
        result["filters"] = deepcopy(filters)
        result["candidate_count"] = len(candidates)
        if action == "list_evidence_gaps":
            result["gap_summary"] = summarize_evidence_gaps(gap_results, candidate_count=len(candidates))
            result["results"] = gap_results
        else:
            plans = [plan_format_evidence_remediation(row) for row in gap_results]
            plans.sort(
                key=lambda row: (
                    -int((row.get("priority_counts") or {}).get("P1", 0)),
                    -int((row.get("priority_counts") or {}).get("P2", 0)),
                    -int(row.get("remediation_item_count") or 0),
                    str((row.get("format") or {}).get("label") or ""),
                )
            )
            result["remediation_summary"] = summarize_evidence_remediation(
                plans,
                candidate_count=len(candidates),
            )
            result["results"] = plans
        result["result_count"] = len(result["results"])
        return result

    all_assessments = [
        _assessment_for_doc(reader, framework, row, institution_id=institution_id)
        for row in candidates
    ]
    all_assessments = _rank_assessments(all_assessments)
    assessment_summary = _assessment_summary(all_assessments)
    unbanded_results = [_compact_unbanded(row) for row in all_assessments if row.get("risk_band") is None]

    assessments = all_assessments
    if action == "list_at_risk_formats":
        allowed_bands = set(filters.get("risk_bands") or DEFAULT_AT_RISK_BANDS)
        assessments = [row for row in all_assessments if row.get("risk_band") in allowed_bands]

    result.update({
        "filters": deepcopy(filters),
        "candidate_count": len(candidates),
        "assessment_summary": assessment_summary,
        "unbanded_count": len(unbanded_results),
        "unbanded_results": unbanded_results,
        "results": assessments,
        "result_count": len(assessments),
    })
    if action == "list_at_risk_formats" and unbanded_results:
        result["coverage_warning"] = (
            f"{len(unbanded_results)} candidate format(s) could not be assigned a risk band and are not "
            "included in the at-risk result filter. Review unbanded_results before concluding that no risk was found."
        )
    return result