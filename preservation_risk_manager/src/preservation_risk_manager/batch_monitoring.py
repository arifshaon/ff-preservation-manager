from __future__ import annotations

from typing import Any, Callable

from preservation_risk_manager import integration_cli as base
from preservation_risk_manager.ai.batch_risk_analysis import apply_batched_fill_gaps
from preservation_risk_manager.format_identification import IdentificationResolver
from preservation_risk_manager.web_reports import normalize_input_format_id, report_document


Progress = Callable[[int, str], None]


def _puid_values(format_doc: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for value in format_doc.get("puids") or []:
        text = str(value).strip()
        if text and text not in values:
            values.append(text)
    identifiers = format_doc.get("identifiers") or {}
    if isinstance(identifiers, dict):
        for value in identifiers.get("puid") or []:
            text = str(value).strip()
            if text and text not in values:
                values.append(text)
    return values


def _canonical_id(format_doc: dict[str, Any]) -> str | None:
    value = format_doc.get("canonical_id") or format_doc.get("format_id") or format_doc.get("id")
    return str(value) if value is not None else None


def _label(format_doc: dict[str, Any]) -> str | None:
    value = (
        format_doc.get("preferred_name")
        or format_doc.get("format_name")
        or format_doc.get("name")
        or format_doc.get("label")
    )
    return str(value) if value is not None else None


def _batch_request(format_value: str, *, scope: str, institution_id: str | None) -> dict[str, Any]:
    return {
        "action": "assess_format",
        "format": format_value,
        "scope": scope,
        "institution_id": institution_id if scope == "institution" else None,
        "filters": {
            "family": None,
            "risk_bands": [],
            "domains": [],
            "question_ids": [],
            "content_type": None,
        },
        "limit": 100,
    }


def run_batch_assessment(
    *,
    reader,
    framework,
    format_ids: list[str],
    scope: str = "global",
    institution_id: str | None = None,
    ai_mode: str = "off",
    provider=None,
    max_ai_evidence_items: int = 20,
    max_puids_per_fill_gaps_call: int = 8,
    progress: Progress | None = None,
) -> dict[str, Any]:
    """Assess a bounded watchlist and return one canonical batch report document.

    ``off`` uses only governed registry/database evidence. ``synthesize`` adds the
    capability-driven overall AI synthesis for each successfully resolved format.
    ``fill-gaps`` preserves the older batched question-level evidence interpreter.
    The governed result remains available in every mode.
    """
    cleaned = [normalize_input_format_id(value) for value in format_ids]
    cleaned = [value for value in cleaned if value]
    if not cleaned:
        raise ValueError("At least one format identifier is required.")

    ai_mode = str(ai_mode or "off").strip().lower()
    if ai_mode not in {"off", "synthesize", "fill-gaps"}:
        raise ValueError("ai_mode must be off, synthesize, or fill-gaps.")
    if ai_mode != "off" and provider is None:
        raise ValueError("AI batch mode requires a configured provider.")

    scope = str(scope or "global").strip().lower()
    if scope not in {"global", "institution"}:
        raise ValueError("scope must be global or institution.")
    institution_id = str(institution_id or "").strip() or None
    if scope == "institution" and not institution_id:
        raise ValueError("Institution scope requires an institution_id.")

    resolver = IdentificationResolver(reader, plugin=None)
    items: list[dict[str, Any]] = []
    fill_gap_candidates: list[dict[str, Any]] = []
    fill_gap_assessments: list[dict[str, Any]] = []
    total = len(cleaned)

    for index, (original, normalized) in enumerate(zip(format_ids, cleaned), start=1):
        identification = resolver.resolve(normalized)
        if identification.resolved and identification.resolution.format_doc:
            format_doc = identification.resolution.format_doc
            canonical_id = _canonical_id(format_doc) or normalized
            request = _batch_request(canonical_id, scope=scope, institution_id=institution_id)
            response = base.execute_request(reader, framework, request)
            response["identification"] = identification.to_dict()
            puids = _puid_values(format_doc)
            resolved_puid = puids[0] if puids else None

            if ai_mode == "synthesize" and response.get("status") == "ok":
                response = base._apply_ai_risk_assessment(
                    reader,
                    framework,
                    request,
                    response,
                    provider=provider,
                    ai_mode="synthesize",
                    max_evidence_items=max_ai_evidence_items,
                )
            elif ai_mode == "fill-gaps" and response.get("status") == "ok" and puids:
                fill_gap_candidates.append(
                    {
                        "puid": puids[0],
                        "canonical_id": canonical_id,
                        "label": _label(format_doc),
                        "version": format_doc.get("version"),
                        "format_doc": format_doc,
                    }
                )
                fill_gap_assessments.append(response)
        else:
            request = _batch_request(normalized, scope=scope, institution_id=institution_id)
            response = base.execute_request(reader, framework, request)
            response["identification"] = identification.to_dict()
            resolved_puid = None

        items.append(
            {
                "input_format_id": original,
                "normalized_format_id": normalized,
                "resolved_puid": resolved_puid,
                "response": response,
            }
        )
        if progress:
            progress(
                5 + int((index / total) * 72),
                f"Assessment {index}/{total}: {original}",
            )

    if ai_mode == "fill-gaps" and fill_gap_candidates:
        if progress:
            progress(80, f"Running AI fill-gaps for {len(fill_gap_candidates)} resolved PUIDs")

        def fill_progress(message: str) -> None:
            if progress:
                progress(86, message)

        apply_batched_fill_gaps(
            provider,
            reader,
            framework,
            {
                "scope": scope,
                "institution_id": institution_id if scope == "institution" else None,
            },
            fill_gap_candidates,
            fill_gap_assessments,
            user_question="Assess preservation risk for the supplied PRONOM PUIDs.",
            max_evidence_items=max_ai_evidence_items,
            max_puids_per_call=max_puids_per_fill_gaps_call,
            progress=fill_progress,
        )

    framework_info = {
        "framework_id": framework.framework_id,
        "version": framework.version,
        "calibration_status": framework.calibration_status,
        "banding_enabled": framework.banding_enabled,
    }
    if progress:
        progress(94, "Building curator risk report")
    return report_document(
        framework=framework_info,
        scope=scope,
        institution_id=institution_id if scope == "institution" else None,
        ai_mode=ai_mode,
        items=items,
    )
