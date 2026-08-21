from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from registry_builder.models import CanonicalFormat, RawFormatRecord


def load_external_risk_mapping(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("External risk mapping config must contain a JSON object")
    if not isinstance(data.get("rules", []), list):
        raise ValueError("External risk mapping config rules must be a list")
    return data


def _canonical_matches(fmt: CanonicalFormat, selector: dict[str, Any]) -> bool:
    canonical_ids = selector.get("canonical_ids") or []
    if canonical_ids and fmt.canonical_id not in {str(value) for value in canonical_ids}:
        return False

    name_regex = selector.get("preferred_name_regex")
    if name_regex and not re.search(str(name_regex), fmt.preferred_name or ""):
        return False

    category_regex = selector.get("category_regex")
    if category_regex and not re.search(str(category_regex), fmt.category or ""):
        return False

    identifier_values = selector.get("identifier_values") or {}
    if not isinstance(identifier_values, dict):
        raise ValueError("target_selector.identifier_values must be an object")
    for kind, wanted in identifier_values.items():
        wanted_values = {str(value).lower() for value in (wanted or [])}
        actual_values = {str(value).lower() for value in fmt.identifiers.get(str(kind), [])}
        if wanted_values and not actual_values.intersection(wanted_values):
            return False

    method_profile_any = {str(value) for value in (selector.get("method_profile_any") or [])}
    if method_profile_any:
        assigned = {
            str(value)
            for value in (fmt.preservation_method.get("assigned_profile_ids") or [])
        }
        if not assigned.intersection(method_profile_any):
            return False

    return bool(canonical_ids or name_regex or category_regex or identifier_values or method_profile_any)


def _source_record_matches(record: RawFormatRecord, rule: dict[str, Any]) -> bool:
    if record.record_role != "evidence_only":
        return False
    source_id = rule.get("source_id")
    if source_id and record.source_id != source_id:
        return False
    source_type = rule.get("source_type")
    if source_type and record.source_type != source_type:
        return False
    source_record_id = rule.get("source_record_id")
    if source_record_id and str(record.source_record_id or "") != str(source_record_id):
        return False
    source_slug = rule.get("source_slug")
    if source_slug and str(record.native_fields.get("slug") or "") != str(source_slug):
        return False
    return True


def _assessment_key(assessment: dict[str, Any]) -> tuple[Any, ...]:
    return (
        assessment.get("source_id"),
        assessment.get("source_type"),
        assessment.get("source_record_id"),
        assessment.get("native_label"),
        assessment.get("native_score"),
        assessment.get("native_scale"),
        assessment.get("scope_type"),
        assessment.get("scope_name"),
        assessment.get("mapping_rule_id"),
    )


def apply_external_risk_mappings(
    registry: Iterable[CanonicalFormat],
    source_records: Iterable[RawFormatRecord],
    mapping: dict[str, Any],
    *,
    include_drafts: bool = False,
) -> dict[str, Any]:
    formats = list(registry)
    records = list(source_records)
    mapping_version = str(mapping.get("mapping_version") or "unversioned")
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for sequence, rule in enumerate(mapping.get("rules") or [], start=1):
        rule_id = str(rule.get("rule_id") or f"rule-{sequence}")
        status = str(rule.get("status") or "draft").lower()
        if status != "approved" and not (include_drafts and status == "draft"):
            skipped.append({"rule_id": rule_id, "status": status, "reason": "not_approved"})
            continue
        if status in {"contextual_only", "excluded"}:
            skipped.append({"rule_id": rule_id, "status": status, "reason": status})
            continue

        matching_records = [record for record in records if _source_record_matches(record, rule)]
        if len(matching_records) != 1:
            skipped.append({
                "rule_id": rule_id,
                "status": status,
                "reason": "source_record_match_count",
                "source_record_match_count": len(matching_records),
            })
            continue

        selector = rule.get("target_selector") or {}
        target_formats = [fmt for fmt in formats if _canonical_matches(fmt, selector)]
        if not target_formats:
            skipped.append({"rule_id": rule_id, "status": status, "reason": "no_target_formats"})
            continue

        record = matching_records[0]
        source_assessments = record.risk_assessments or []
        if not source_assessments:
            skipped.append({"rule_id": rule_id, "status": status, "reason": "no_source_risk_assessment"})
            continue

        attached = 0
        for fmt in target_formats:
            existing_keys = {_assessment_key(item) for item in fmt.risk_assessments}
            for source_assessment in source_assessments:
                assessment = dict(source_assessment)
                assessment["scope_type"] = rule.get("scope_type") or assessment.get("scope_type") or "contextual"
                assessment["scope_name"] = rule.get("scope_name") or assessment.get("scope_name") or record.name
                assessment["scope_basis"] = "reviewed_external_risk_mapping"
                assessment["mapping_rule_id"] = rule_id
                assessment["mapping_version"] = mapping_version
                assessment["mapped_target_canonical_id"] = fmt.canonical_id
                key = _assessment_key(assessment)
                if key not in existing_keys:
                    fmt.risk_assessments.append(assessment)
                    existing_keys.add(key)
                    attached += 1
            fmt.refresh_risk_views()

        applied.append({
            "rule_id": rule_id,
            "status": status,
            "source_id": record.source_id,
            "source_record_id": record.source_record_id,
            "source_name": record.name,
            "target_count": len(target_formats),
            "assessments_attached": attached,
            "target_canonical_ids": sorted(fmt.canonical_id for fmt in target_formats),
        })

    return {
        "enabled": True,
        "mapping_version": mapping_version,
        "rules_total": len(mapping.get("rules") or []),
        "rules_applied": len(applied),
        "rules_skipped": len(skipped),
        "assessments_attached": sum(item["assessments_attached"] for item in applied),
        "applied": applied,
        "skipped": skipped,
    }
