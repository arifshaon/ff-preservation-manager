from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from preservation_risk_manager.answer_derivation import (
    _answer_from_claim,
    _claim_matches_field,
    derive_answers,
)
from preservation_risk_manager.data_access import RegistryReader
from preservation_risk_manager.evidence_packs import build_evidence_pack
from preservation_risk_manager.frameworks import RiskFramework


def _format_id(format_doc: dict[str, Any]) -> str:
    return str(format_doc.get("canonical_id") or format_doc.get("format_id") or format_doc.get("id") or "")


def _format_name(format_doc: dict[str, Any]) -> str:
    return str(
        format_doc.get("preferred_name")
        or format_doc.get("format_name")
        or format_doc.get("name")
        or _format_id(format_doc)
    )


def _puid_values(format_doc: dict[str, Any]) -> list[str]:
    values: list[str] = []
    identifiers = format_doc.get("identifiers") or {}
    if isinstance(identifiers, dict):
        raw = identifiers.get("puid") or []
        if not isinstance(raw, list):
            raw = [raw]
        for value in raw:
            text = str(value or "").strip()
            if text and text not in values:
                values.append(text)
    raw_puids = format_doc.get("puids") or []
    if not isinstance(raw_puids, list):
        raw_puids = [raw_puids]
    for value in raw_puids:
        text = str(value or "").strip()
        if text and text not in values:
            values.append(text)
    return values


def _claim_key(row: dict[str, Any]) -> str:
    if row.get("_storage_key"):
        return str(row["_storage_key"])
    parts = (
        row.get("canonical_id"),
        row.get("criterion_id"),
        row.get("value"),
        row.get("source_id"),
        row.get("source_record_id"),
        row.get("mapping_rule_id"),
        row.get("institution_id"),
    )
    return "|".join(str(part or "") for part in parts)


def _claim_source(row: dict[str, Any]) -> str:
    return str(row.get("source_id") or row.get("source_type") or "unknown")


def _is_institution_scoped(row: dict[str, Any]) -> bool:
    if row.get("institution_id"):
        return True
    return str(row.get("source_independence") or "").lower() == "institution_scoped"


def _claim_in_scope(row: dict[str, Any], *, institution_id: str | None) -> bool:
    if row.get("current") is False:
        return False
    if not institution_id:
        return not _is_institution_scoped(row)
    if not _is_institution_scoped(row):
        return True
    return str(row.get("institution_id") or "") == institution_id


def _claims_for_format(
    reader: RegistryReader,
    claims_by_canonical: dict[str, list[dict[str, Any]]],
    format_doc: dict[str, Any],
) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    seen: set[str] = set()
    for canonical_id in reader.criterion_claim_canonical_ids(format_doc):
        for claim in claims_by_canonical.get(canonical_id, []):
            key = _claim_key(claim)
            if key in seen:
                continue
            seen.add(key)
            claims.append(claim)
    return claims


def _field_answer_sets(question, claims: list[dict[str, Any]]) -> dict[str, set[str]]:
    answers: dict[str, set[str]] = defaultdict(set)
    for evidence_field in question.evidence_fields:
        for claim in claims:
            if not _claim_matches_field(claim, evidence_field):
                continue
            answer_id = _answer_from_claim(question, evidence_field, claim)
            if answer_id:
                answers[str(evidence_field)].add(str(answer_id))
    return dict(answers)


def _classify_conflict(question, derivation: dict[str, Any]) -> dict[str, Any]:
    claims = [claim for claim in derivation.get("evidence_claims") or [] if isinstance(claim, dict)]
    by_field = _field_answer_sets(question, claims)
    same_field_conflicts = {
        field: sorted(answer_ids)
        for field, answer_ids in by_field.items()
        if len(answer_ids) > 1
    }
    active_fields = {
        field: sorted(answer_ids)
        for field, answer_ids in by_field.items()
        if answer_ids
    }

    if same_field_conflicts:
        classification = "same_criterion_evidence_conflict"
    elif len(active_fields) > 1:
        classification = "composite_field_aggregation"
    else:
        classification = "unclassified_conflict"

    return {
        "classification": classification,
        "field_answers": active_fields,
        "same_field_conflicts": same_field_conflicts,
        "sources": sorted({_claim_source(claim) for claim in claims}),
        "mapping_rule_ids": sorted({
            str(claim.get("mapping_rule_id"))
            for claim in claims
            if claim.get("mapping_rule_id")
        }),
    }


def refine_conflict_semantics(
    report: dict[str, Any],
    reader: RegistryReader,
    framework: RiskFramework,
    *,
    institution_id: str | None = None,
    sample_limit: int = 25,
) -> dict[str, Any]:
    """Separate true evidence disagreement from intended composite aggregation.

    A framework question may intentionally combine several evidence fields.  If
    those component criteria produce different controlled answers, the scorer
    conservatively chooses the higher-risk answer.  That is not automatically a
    contradiction: e.g. hardware_dependency=none and plugin_dependency=high is a
    valid composite result of specialist_dependency.  A genuine evidence
    conflict exists when the *same criterion/evidence field* yields more than one
    controlled answer for the same format/question.

    This refinement is diagnostic only; it does not change derivation or scoring.
    """
    current_claims = [
        row
        for row in reader.query("criterion_claims", {})
        if _claim_in_scope(row, institution_id=institution_id)
    ]
    claims_by_canonical: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in current_claims:
        claims_by_canonical[str(claim.get("canonical_id") or "")].append(claim)

    by_classification: Counter[str] = Counter()
    genuine_by_question: Counter[str] = Counter()
    composite_by_question: Counter[str] = Counter()
    genuine_by_field: Counter[str] = Counter()
    composite_field_combinations: Counter[str] = Counter()
    genuine_source_combinations: Counter[str] = Counter()
    genuine_mapping_rule_combinations: Counter[str] = Counter()
    genuine_samples: list[dict[str, Any]] = []
    composite_samples: list[dict[str, Any]] = []
    puid_genuine = 0
    puid_composite = 0

    for format_doc in reader.list_canonical_formats():
        claims = _claims_for_format(reader, claims_by_canonical, format_doc)
        evidence_pack = build_evidence_pack(
            format_doc,
            institution_id=institution_id,
            criterion_claims=claims,
        )
        answer_document = derive_answers(framework, evidence_pack)
        puids = _puid_values(format_doc)
        is_puid = bool(puids)

        for question in framework.questions:
            derivation = answer_document["derivation"][question.id]
            if str(derivation.get("status") or "") != "derived_conflict_conservative":
                continue

            classified = _classify_conflict(question, derivation)
            classification = classified["classification"]
            by_classification[classification] += 1
            base = {
                "canonical_id": _format_id(format_doc),
                "preferred_name": _format_name(format_doc),
                "puids": puids,
                "question_id": question.id,
                "conflicting_answer_ids": sorted(
                    str(value) for value in derivation.get("conflicting_answer_ids") or []
                ),
                "field_answers": classified["field_answers"],
                "sources": classified["sources"],
                "mapping_rule_ids": classified["mapping_rule_ids"],
            }

            if classification == "same_criterion_evidence_conflict":
                genuine_by_question[question.id] += 1
                if is_puid:
                    puid_genuine += 1
                for field in classified["same_field_conflicts"]:
                    genuine_by_field[field] += 1
                source_signature = " + ".join(classified["sources"]) or "unknown"
                genuine_source_combinations[source_signature] += 1
                rule_signature = " + ".join(classified["mapping_rule_ids"]) or "unknown"
                genuine_mapping_rule_combinations[rule_signature] += 1
                if len(genuine_samples) < sample_limit:
                    genuine_samples.append(base | {"classification": classification})
            elif classification == "composite_field_aggregation":
                composite_by_question[question.id] += 1
                if is_puid:
                    puid_composite += 1
                field_signature = " + ".join(sorted(classified["field_answers"]))
                composite_field_combinations[field_signature] += 1
                if len(composite_samples) < sample_limit:
                    composite_samples.append(base | {"classification": classification})

    raw_total = sum(by_classification.values())
    genuine_total = by_classification.get("same_criterion_evidence_conflict", 0)
    composite_total = by_classification.get("composite_field_aggregation", 0)
    unclassified_total = by_classification.get("unclassified_conflict", 0)

    interpretation = {
        "raw_derived_conflict_count": raw_total,
        "genuine_evidence_conflicts": genuine_total,
        "composite_aggregations": composite_total,
        "unclassified_conflicts": unclassified_total,
        "puid_genuine_evidence_conflicts": puid_genuine,
        "puid_composite_aggregations": puid_composite,
        "by_classification": dict(sorted(by_classification.items())),
        "genuine_by_question": dict(sorted(genuine_by_question.items(), key=lambda item: (-item[1], item[0]))),
        "genuine_by_evidence_field": dict(sorted(genuine_by_field.items(), key=lambda item: (-item[1], item[0]))),
        "genuine_by_source_combination": dict(
            sorted(genuine_source_combinations.items(), key=lambda item: (-item[1], item[0]))
        ),
        "genuine_by_mapping_rule_combination": dict(
            sorted(genuine_mapping_rule_combinations.items(), key=lambda item: (-item[1], item[0]))
        ),
        "composite_by_question": dict(sorted(composite_by_question.items(), key=lambda item: (-item[1], item[0]))),
        "composite_field_combinations": dict(
            sorted(composite_field_combinations.items(), key=lambda item: (-item[1], item[0]))
        ),
        "genuine_samples": genuine_samples,
        "composite_samples": composite_samples,
        "note": (
            "Composite aggregations retain the existing conservative scoring result but are not counted as "
            "same-criterion evidence disagreements. No scoring or mapping behavior is changed by this diagnostic."
        ),
    }
    report["conflict_interpretation"] = interpretation
    summary = report.setdefault("summary", {})
    summary["raw_derived_conflict_format_questions"] = raw_total
    summary["genuine_evidence_conflict_format_questions"] = genuine_total
    summary["composite_aggregation_format_questions"] = composite_total
    return report


def render_conflict_semantics_markdown(report: dict[str, Any]) -> str:
    data = report.get("conflict_interpretation") or {}
    lines = [
        "## Conflict interpretation",
        "",
        f"- Raw `derived_conflict_conservative` format/questions: **{data.get('raw_derived_conflict_count', 0)}**",
        f"- Genuine same-criterion evidence conflicts: **{data.get('genuine_evidence_conflicts', 0)}**",
        f"- Composite field aggregations: **{data.get('composite_aggregations', 0)}**",
        f"- Unclassified conflicts: **{data.get('unclassified_conflicts', 0)}**",
        "",
        "> Composite aggregation does not change scoring: the existing conservative answer remains authoritative. "
        "It simply distinguishes mixed component evidence from a contradiction within the same criterion.",
        "",
        "### Genuine conflicts by evidence field",
        "",
    ]
    for field, count in (data.get("genuine_by_evidence_field") or {}).items():
        lines.append(f"- {field}: **{count}**")
    if not data.get("genuine_by_evidence_field"):
        lines.append("- None")
    lines.extend(["", "### Composite aggregations by question", ""])
    for question_id, count in (data.get("composite_by_question") or {}).items():
        lines.append(f"- {question_id}: **{count}**")
    if not data.get("composite_by_question"):
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)
