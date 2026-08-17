from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable
import zipfile

from preservation_risk_manager import integration_cli as base
from preservation_risk_manager.ai.batch_risk_analysis import apply_batched_fill_gaps
from preservation_risk_manager.format_identification import IdentificationResolver
from preservation_risk_manager.human_renderer_multi import render_human_response
from preservation_risk_manager.integration_cli_human import _RateLimitCircuitProvider, _ask as run_human_query
from preservation_risk_manager.web_reports import (
    normalize_input_format_id,
    report_document,
    summary_row,
    write_report_artifacts,
)


Progress = Callable[..., None]


@dataclass(frozen=True)
class WebRuntimeConfig:
    framework: str
    storage_config: str | None = None
    registry_json: str | None = None
    ai_config: str | None = None
    jobs_dir: str = "web-jobs"
    default_institution_id: str | None = None
    max_workers: int = 2
    batch_max_formats: int = 5000
    max_ai_evidence_items: int = 20
    identification_ai_min_confidence: float = 0.80
    human_match_limit: int = 100

    def validate(self) -> None:
        if bool(self.storage_config) == bool(self.registry_json):
            raise ValueError("Configure exactly one of storage_config or registry_json for the web application.")
        if not Path(self.framework).expanduser().is_file():
            raise FileNotFoundError(f"Framework file not found: {self.framework}")
        source = self.storage_config or self.registry_json
        if source and not Path(source).expanduser().is_file():
            raise FileNotFoundError(f"Registry/storage config not found: {source}")
        if self.ai_config and not Path(self.ai_config).expanduser().is_file():
            raise FileNotFoundError(f"AI config not found: {self.ai_config}")
        if int(self.batch_max_formats) <= 0:
            raise ValueError("batch_max_formats must be greater than zero.")
        if int(self.max_workers) <= 0:
            raise ValueError("max_workers must be greater than zero.")


def _reader_args(config: WebRuntimeConfig) -> Namespace:
    return Namespace(registry_json=config.registry_json, storage_config=config.storage_config)


def _framework(config: WebRuntimeConfig):
    return base.load_framework(base._require_file(config.framework, label="Framework file"))


def _reader(config: WebRuntimeConfig):
    return base._reader_from_args(_reader_args(config))


def _provider(config: WebRuntimeConfig):
    if not config.ai_config:
        raise ValueError("AI mode was requested but the web application has no ai_config configured.")
    ai_config = base.load_ai_config(base._require_file(config.ai_config, label="AI config file"))
    return _RateLimitCircuitProvider(base.build_ai_provider(ai_config))


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
    value = format_doc.get("preferred_name") or format_doc.get("format_name") or format_doc.get("name") or format_doc.get("label")
    return str(value) if value is not None else None


def _write_human_artifacts(result: dict[str, Any], rendered: str, job_dir: Path) -> dict[str, str]:
    json_path = job_dir / "human-risk-result.json"
    text_path = job_dir / "human-risk-result.txt"
    zip_path = job_dir / "human-risk-result.zip"
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8")
    text_path.write_text(rendered, encoding="utf-8")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(text_path, arcname=text_path.name)
        archive.write(json_path, arcname=json_path.name)
    return {"text": text_path.name, "json": json_path.name, "zip": zip_path.name}


def run_human_web_job(
    config: WebRuntimeConfig,
    payload: dict[str, Any],
    job_id: str,
    update: Progress,
    job_dir: Path,
) -> dict[str, Any]:
    question = str(payload.get("question") or "").strip()
    if not question:
        raise ValueError("A human risk question is required.")
    ai_mode = str(payload.get("ai_mode") or "fill-gaps").strip().lower()
    if ai_mode not in {"off", "fill-gaps", "review-all"}:
        raise ValueError("ai_mode must be off, fill-gaps, or review-all.")
    if (ai_mode != "off" or bool(payload.get("enable_ai_identification", True))) and not config.ai_config:
        raise ValueError("Human AI features require ai_config in the web application configuration.")

    scope = str(payload.get("scope") or "global").strip().lower()
    institution_id = str(payload.get("institution_id") or config.default_institution_id or "").strip() or None
    if scope == "institution" and not institution_id:
        raise ValueError("Institution scope requires an institution_id.")

    update(progress=8, message="Loading registry and framework")
    args = Namespace(
        question=question,
        framework=config.framework,
        registry_json=config.registry_json,
        storage_config=config.storage_config,
        ai_config=config.ai_config,
        institution=institution_id if scope == "institution" else None,
        limit=int(payload.get("limit") or config.human_match_limit),
        json=True,
        enable_ai_identification=bool(payload.get("enable_ai_identification", True)),
        identification_ai_min_confidence=float(
            payload.get("identification_ai_min_confidence") or config.identification_ai_min_confidence
        ),
        ai_mode=ai_mode,
        max_ai_evidence_items=int(payload.get("max_ai_evidence_items") or config.max_ai_evidence_items),
    )

    update(progress=20, message="Resolving the human question and matching format IDs")
    result = run_human_query(args)
    update(progress=88, message="Rendering assessment")
    rendered = render_human_response(result)
    downloads = _write_human_artifacts(result, rendered, job_dir)
    return {
        "message": "Human risk assessment completed",
        "downloads": downloads,
        "preview": {
            "kind": "human",
            "text": rendered,
            "status": result.get("status"),
        },
    }


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


def run_batch_web_job(
    config: WebRuntimeConfig,
    payload: dict[str, Any],
    job_id: str,
    update: Progress,
    job_dir: Path,
) -> dict[str, Any]:
    format_ids = [str(value).strip() for value in payload.get("format_ids") or [] if str(value).strip()]
    if not format_ids:
        raise ValueError("At least one format ID is required.")
    if len(format_ids) > int(config.batch_max_formats):
        raise ValueError(
            f"The batch contains {len(format_ids)} IDs; the configured maximum is {config.batch_max_formats}."
        )

    ai_mode = str(payload.get("ai_mode") or "off").strip().lower()
    if ai_mode not in {"off", "fill-gaps"}:
        raise ValueError("Batch web reports support ai_mode off or fill-gaps.")
    scope = str(payload.get("scope") or "global").strip().lower()
    institution_id = str(payload.get("institution_id") or config.default_institution_id or "").strip() or None
    if scope == "institution" and not institution_id:
        raise ValueError("Institution scope requires an institution_id.")

    update(progress=5, message=f"Loading registry for {len(format_ids)} format IDs")
    reader = _reader(config)
    framework = _framework(config)
    resolver = IdentificationResolver(reader, plugin=None)
    items: list[dict[str, Any]] = []
    ai_candidates: list[dict[str, Any]] = []
    ai_assessments: list[dict[str, Any]] = []

    total = len(format_ids)
    for index, original in enumerate(format_ids, start=1):
        normalized = normalize_input_format_id(original)
        identification = resolver.resolve(normalized)
        if identification.resolved and identification.resolution.format_doc:
            format_doc = identification.resolution.format_doc
            canonical_id = _canonical_id(format_doc) or normalized
            request = _batch_request(canonical_id, scope=scope, institution_id=institution_id)
            response = base.execute_request(reader, framework, request)
            response["identification"] = identification.to_dict()
            puids = _puid_values(format_doc)
            if ai_mode == "fill-gaps" and response.get("status") == "ok" and puids:
                ai_candidates.append(
                    {
                        "puid": puids[0],
                        "canonical_id": canonical_id,
                        "label": _label(format_doc),
                        "version": format_doc.get("version"),
                        "format_doc": format_doc,
                    }
                )
                ai_assessments.append(response)
            resolved_puid = puids[0] if puids else None
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
        progress = 8 + int((index / total) * 62)
        update(progress=progress, message=f"Deterministic assessment {index}/{total}: {original}")

    if ai_mode == "fill-gaps" and ai_candidates:
        provider = _provider(config)
        update(progress=74, message=f"Preparing AI fill-gaps for {len(ai_candidates)} resolved PUIDs")
        batch_number = 0

        def ai_progress(message: str) -> None:
            nonlocal batch_number
            batch_number += 1
            update(progress=min(92, 76 + batch_number * 4), message=message)

        apply_batched_fill_gaps(
            provider,
            reader,
            framework,
            {
                "scope": scope,
                "institution_id": institution_id if scope == "institution" else None,
            },
            ai_candidates,
            ai_assessments,
            user_question="Assess preservation risk for the supplied PRONOM PUIDs.",
            max_evidence_items=int(config.max_ai_evidence_items),
            max_puids_per_call=8,
            progress=ai_progress,
        )
        if provider.rate_limited:
            update(progress=92, message="AI provider rate-limited; deterministic results retained where needed")

    update(progress=95, message="Building CSV, JSON, and ZIP reports")
    framework_info = {
        "framework_id": framework.framework_id,
        "version": framework.version,
        "calibration_status": framework.calibration_status,
        "banding_enabled": framework.banding_enabled,
    }
    report = report_document(
        framework=framework_info,
        scope=scope,
        institution_id=institution_id if scope == "institution" else None,
        ai_mode=ai_mode,
        items=items,
    )
    downloads = write_report_artifacts(report, job_dir)
    rows = [summary_row(item) for item in items]
    return {
        "message": f"Risk report completed for {len(items)} format IDs",
        "downloads": downloads,
        "preview": {
            "kind": "batch",
            "input_count": len(items),
            "successful_assessments": report["successful_assessments"],
            "failed_or_unresolved": report["failed_or_unresolved"],
            "rows": rows[:50],
            "preview_truncated": len(rows) > 50,
        },
    }
