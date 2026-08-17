from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import re
from typing import Any, Iterable
import zipfile

from preservation_risk_manager.format_identification import normalize_format_observation


_FORMAT_ID_HEADERS = {
    "format",
    "format_id",
    "formatid",
    "id",
    "pronom",
    "pronom_id",
    "pronom_puid",
    "puid",
}


def _clean_token(value: Any) -> str:
    text = str(value or "").strip().lstrip("\ufeff")
    if not text:
        return ""
    return normalize_format_observation(text)


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = _clean_token(value)
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def _parse_csv(text: str) -> list[str]:
    rows = list(csv.reader(StringIO(text.lstrip("\ufeff"))))
    if not rows:
        return []

    header = [re.sub(r"[^a-z0-9_]+", "_", str(value).strip().lower()).strip("_") for value in rows[0]]
    format_column = next((index for index, value in enumerate(header) if value in _FORMAT_ID_HEADERS), None)
    start = 1 if format_column is not None else 0
    column = format_column if format_column is not None else 0

    values: list[str] = []
    for row in rows[start:]:
        if column >= len(row):
            continue
        value = str(row[column]).strip()
        if value:
            values.append(value)
    return _dedupe(values)


def parse_format_ids(text: str, *, filename: str | None = None) -> list[str]:
    """Parse pasted text or an uploaded TXT/CSV payload into distinct format IDs.

    CSV files may use a ``puid``, ``pronom_puid``, ``format_id``, ``format`` or
    ``id`` column. Headerless CSV uses the first column. Plain text accepts one
    identifier per line as well as comma, semicolon, or tab separated values.
    Identifier wrappers/spacing are normalized using the same safe programmatic
    rules as the main identification path.
    """
    raw = str(text or "")
    if not raw.strip():
        return []
    name = str(filename or "").strip().lower()
    if name.endswith(".csv"):
        return _parse_csv(raw)

    values: list[str] = []
    for line in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        values.extend(part for part in re.split(r"[,;\t]+", stripped) if part.strip())
    return _dedupe(values)


def combine_format_id_inputs(
    *,
    entered_text: str | None,
    uploaded_text: str | None,
    uploaded_filename: str | None,
) -> list[str]:
    return _dedupe(
        parse_format_ids(entered_text or "")
        + parse_format_ids(uploaded_text or "", filename=uploaded_filename)
    )


def _percentage(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value) * 100.0, 1)
    except (TypeError, ValueError):
        return None


def summary_row(item: dict[str, Any]) -> dict[str, Any]:
    response = item.get("response") if isinstance(item.get("response"), dict) else {}
    deterministic = response.get("result") if isinstance(response.get("result"), dict) else {}
    identity = deterministic.get("format") if isinstance(deterministic.get("format"), dict) else {}
    puids = identity.get("puids") if isinstance(identity.get("puids"), list) else []

    ai = response.get("ai_risk_assessment") if isinstance(response.get("ai_risk_assessment"), dict) else {}
    ai_analysis = ai.get("analysis") if isinstance(ai.get("analysis"), dict) else {}

    error = response.get("error")
    if not error and response.get("status") not in {None, "ok"}:
        resolution = response.get("resolution") if isinstance(response.get("resolution"), dict) else {}
        error = resolution.get("status") or response.get("status")

    return {
        "input_format_id": item.get("input_format_id"),
        "status": response.get("status"),
        "resolved_format_id": identity.get("format_id"),
        "puid": puids[0] if puids else item.get("resolved_puid"),
        "label": identity.get("label"),
        "version": identity.get("version"),
        "deterministic_risk_band": deterministic.get("risk_band"),
        "deterministic_analysis_status": deterministic.get("analysis_status"),
        "deterministic_score": deterministic.get("score"),
        "deterministic_max_score": deterministic.get("max_score"),
        "deterministic_evidence_completeness_pct": _percentage(deterministic.get("evidence_completeness")),
        "missing_count": deterministic.get("missing_count"),
        "abstention_count": deterministic.get("abstention_count"),
        "criterion_claims_used": deterministic.get("criterion_claims_used"),
        "ai_mode": ai.get("ai_mode"),
        "ai_status": ai.get("status"),
        "ai_risk_band": ai_analysis.get("analysed_band"),
        "ai_analysis_status": ai_analysis.get("analysis_status"),
        "ai_score": ai_analysis.get("score"),
        "ai_max_score": ai_analysis.get("max_score"),
        "ai_evidence_completeness_pct": _percentage(ai_analysis.get("evidence_completeness")),
        "error": error,
    }


def report_document(
    *,
    framework: dict[str, Any],
    scope: str,
    institution_id: str | None,
    ai_mode: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    rows = [summary_row(item) for item in items]
    success_count = sum(1 for row in rows if row.get("status") == "ok")
    return {
        "report_type": "format_risk_batch",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "framework": framework,
        "scope": scope,
        "institution_id": institution_id,
        "ai_mode": ai_mode,
        "input_count": len(items),
        "successful_assessments": success_count,
        "failed_or_unresolved": len(items) - success_count,
        "summary": rows,
        "items": items,
    }


def write_report_artifacts(report: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "risk-report.json"
    csv_path = directory / "risk-report.csv"
    zip_path = directory / "risk-report.zip"

    json_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")

    rows = report.get("summary") if isinstance(report.get("summary"), list) else []
    fieldnames = list(rows[0].keys()) if rows else ["input_format_id", "status", "error"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(csv_path, arcname=csv_path.name)
        archive.write(json_path, arcname=json_path.name)

    return {
        "csv": csv_path.name,
        "json": json_path.name,
        "zip": zip_path.name,
    }
