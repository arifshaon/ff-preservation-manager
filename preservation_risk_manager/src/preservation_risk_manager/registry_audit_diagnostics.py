from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from preservation_risk_manager.answer_derivation import derive_answers
from preservation_risk_manager.data_access import RegistryReader
from preservation_risk_manager.evidence_packs import build_evidence_pack
from preservation_risk_manager.frameworks import RiskFramework
from preservation_risk_manager.scoring import score_answers


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


def _new_question_stats(framework: RiskFramework) -> dict[str, dict[str, Any]]:
    return {
        question.id: {
            "label": question.label,
            "critical": question.critical,
            "evidence_fields": list(question.evidence_fields),
            "answered": 0,
            "abstained": 0,
            "missing_evidence": 0,
            "unknown_with_matching_evidence": 0,
            "conflicts": 0,
            "source_support": defaultdict(set),
        }
        for question in framework.questions
    }


def _serialise_question_stats(stats: dict[str, dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for question_id, row in stats.items():
        stored = dict(row)
        stored["source_support"] = {
            source: len(format_ids)
            for source, format_ids in sorted(row["source_support"].items())
        }
        output[question_id] = stored
    return output


def refine_registry_risk_evidence_diagnostics(
    report: dict[str, Any],
    reader: RegistryReader,
    framework: RiskFramework,
    *,
    institution_id: str | None = None,
    sample_limit: int = 25,
) -> dict[str, Any]:
    """Add production-PUID coverage diagnostics and conflict matrices.

    The authoritative machine path starts from an exact PRONOM PUID.  Whole-
    registry coverage can therefore hide the operational question: how many PUID
    formats can actually be assessed, and why are the others suppressed?  This
    refinement reports that subset explicitly and decomposes deterministic
    conflicts by question, answer combination, and source combination.
    """
    formats = reader.list_canonical_formats()
    current_claims = [
        row
        for row in reader.query("criterion_claims", {})
        if _claim_in_scope(row, institution_id=institution_id)
    ]
    claims_by_canonical: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in current_claims:
        claims_by_canonical[str(claim.get("canonical_id") or "")].append(claim)

    puid_answered_distribution: Counter[int] = Counter()
    puid_analysis_status: Counter[str] = Counter()
    puid_band_distribution: Counter[str] = Counter()
    puid_suppressed_reasons: Counter[str] = Counter()
    puid_gap_patterns: Counter[str] = Counter()
    puid_question_stats = _new_question_stats(framework)
    puid_source_formats: dict[str, set[str]] = defaultdict(set)
    puid_gap_samples: list[dict[str, Any]] = []
    puid_formats = 0
    puid_band_eligible = 0
    puid_total_completeness = 0.0

    conflict_by_question: Counter[str] = Counter()
    conflict_by_answer_combination: Counter[str] = Counter()
    conflict_by_source_combination: Counter[str] = Counter()
    conflict_by_question_and_sources: Counter[str] = Counter()
    conflict_samples: list[dict[str, Any]] = []
    conflict_total = 0
    puid_conflict_total = 0

    for format_doc in formats:
        format_id = _format_id(format_doc)
        puids = _puid_values(format_doc)
        claims = _claims_for_format(reader, claims_by_canonical, format_doc)
        evidence_pack = build_evidence_pack(
            format_doc,
            institution_id=institution_id,
            criterion_claims=claims,
        )
        answer_document = derive_answers(framework, evidence_pack)
        analysis = score_answers(
            framework,
            answer_document.get("scoring_answers") or answer_document["answers"],
        )
        results_by_question = {row["question_id"]: row for row in analysis["question_results"]}

        is_puid = bool(puids)
        if is_puid:
            puid_formats += 1
            puid_answered_distribution[int(analysis["answered_questions"])] += 1
            puid_analysis_status[str(analysis["analysis_status"])] += 1
            puid_total_completeness += float(analysis["evidence_completeness"])
            analysed_band = analysis.get("analysed_band")
            if analysed_band:
                puid_band_eligible += 1
                puid_band_distribution[str(analysed_band)] += 1
            else:
                puid_suppressed_reasons[str(analysis.get("band_suppressed_reason") or "unknown")] += 1

        unanswered: list[str] = []
        for question in framework.questions:
            derivation = answer_document["derivation"][question.id]
            scoring_row = results_by_question[question.id]
            status = str(derivation.get("status") or "")

            if is_puid:
                stats = puid_question_stats[question.id]
                if scoring_row.get("abstention"):
                    stats["abstained"] += 1
                    unanswered.append(question.id)
                else:
                    stats["answered"] += 1
                if status == "missing_evidence":
                    stats["missing_evidence"] += 1
                elif status == "unknown":
                    stats["unknown_with_matching_evidence"] += 1
                elif status == "derived_conflict_conservative":
                    stats["conflicts"] += 1
                for evidence_claim in derivation.get("evidence_claims") or []:
                    source = _claim_source(evidence_claim)
                    stats["source_support"][source].add(format_id)
                    puid_source_formats[source].add(format_id)

            if status != "derived_conflict_conservative":
                continue

            conflict_total += 1
            if is_puid:
                puid_conflict_total += 1
            answers = sorted(str(value) for value in derivation.get("conflicting_answer_ids") or [])
            sources = sorted({_claim_source(claim) for claim in derivation.get("evidence_claims") or []})
            answer_signature = " vs ".join(answers) if answers else "unknown"
            source_signature = " + ".join(sources) if sources else "unknown"
            conflict_by_question[question.id] += 1
            conflict_by_answer_combination[answer_signature] += 1
            conflict_by_source_combination[source_signature] += 1
            conflict_by_question_and_sources[f"{question.id} | {source_signature}"] += 1
            if len(conflict_samples) < sample_limit:
                conflict_samples.append({
                    "canonical_id": format_id,
                    "preferred_name": _format_name(format_doc),
                    "puids": puids,
                    "question_id": question.id,
                    "conflicting_answer_ids": answers,
                    "sources": sources,
                    "is_puid_format": is_puid,
                })

        if is_puid and unanswered:
            pattern = " + ".join(sorted(unanswered))
            puid_gap_patterns[pattern] += 1
            if len(puid_gap_samples) < sample_limit:
                puid_gap_samples.append({
                    "canonical_id": format_id,
                    "preferred_name": _format_name(format_doc),
                    "puids": puids,
                    "answered_questions": int(analysis["answered_questions"]),
                    "unanswered_questions": sorted(unanswered),
                    "band_suppressed_reason": analysis.get("band_suppressed_reason"),
                })

    puid_report = {
        "formats": puid_formats,
        "band_eligible_formats": puid_band_eligible,
        "band_eligible_percent": round((puid_band_eligible / puid_formats * 100.0), 2) if puid_formats else 0.0,
        "average_evidence_completeness": round((puid_total_completeness / puid_formats), 4) if puid_formats else 0.0,
        "coverage_by_answered_questions": {
            str(answered): count for answered, count in sorted(puid_answered_distribution.items())
        },
        "analysis_status_distribution": dict(sorted(puid_analysis_status.items())),
        "band_distribution": dict(sorted(puid_band_distribution.items())),
        "band_suppressed_reasons": dict(sorted(puid_suppressed_reasons.items())),
        "question_coverage": _serialise_question_stats(puid_question_stats),
        "gap_patterns": dict(sorted(puid_gap_patterns.items(), key=lambda item: (-item[1], item[0]))),
        "source_support": {
            source: len(format_ids)
            for source, format_ids in sorted(puid_source_formats.items())
        },
        "gap_samples": puid_gap_samples,
    }

    base_conflict_count = int((report.get("conflicts") or {}).get("count") or 0)
    conflict_report = {
        "total": conflict_total,
        "puid_format_conflicts": puid_conflict_total,
        "non_puid_format_conflicts": conflict_total - puid_conflict_total,
        "matches_base_audit_count": conflict_total == base_conflict_count,
        "base_audit_count": base_conflict_count,
        "by_question": dict(sorted(conflict_by_question.items(), key=lambda item: (-item[1], item[0]))),
        "by_answer_combination": dict(
            sorted(conflict_by_answer_combination.items(), key=lambda item: (-item[1], item[0]))
        ),
        "by_source_combination": dict(
            sorted(conflict_by_source_combination.items(), key=lambda item: (-item[1], item[0]))
        ),
        "by_question_and_source_combination": dict(
            sorted(conflict_by_question_and_sources.items(), key=lambda item: (-item[1], item[0]))
        ),
        "samples": conflict_samples,
    }

    report["puid_diagnostics"] = puid_report
    report["conflict_diagnostics"] = conflict_report
    return report


def render_registry_audit_diagnostics_markdown(report: dict[str, Any]) -> str:
    puid = report.get("puid_diagnostics") or {}
    conflicts = report.get("conflict_diagnostics") or {}
    lines = [
        "## PUID production-path diagnostics",
        "",
        f"- PUID formats: **{puid.get('formats', 0)}**",
        f"- PUID formats eligible for a deterministic band: **{puid.get('band_eligible_formats', 0)}** ({puid.get('band_eligible_percent', 0)}%)",
        f"- Average PUID evidence completeness: **{float(puid.get('average_evidence_completeness', 0)) * 100:.1f}%**",
        "",
        "### PUID coverage by answered questions",
        "",
        "| Answered questions | PUID formats |",
        "|---:|---:|",
    ]
    for answered, count in (puid.get("coverage_by_answered_questions") or {}).items():
        lines.append(f"| {answered} | {count} |")

    lines.extend(["", "### PUID band suppression reasons", ""])
    for reason, count in (puid.get("band_suppressed_reasons") or {}).items():
        lines.append(f"- {reason}: **{count}**")
    if not puid.get("band_suppressed_reasons"):
        lines.append("- None")

    lines.extend([
        "",
        "### PUID question coverage",
        "",
        "| Question | Answered | Abstained | Missing evidence | Unknown evidence | Conflicts |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for question_id, row in (puid.get("question_coverage") or {}).items():
        lines.append(
            f"| {question_id} | {row.get('answered', 0)} | {row.get('abstained', 0)} | "
            f"{row.get('missing_evidence', 0)} | {row.get('unknown_with_matching_evidence', 0)} | "
            f"{row.get('conflicts', 0)} |"
        )

    lines.extend(["", "### Most common PUID gap patterns", ""])
    for pattern, count in list((puid.get("gap_patterns") or {}).items())[:10]:
        lines.append(f"- {pattern}: **{count}**")
    if not puid.get("gap_patterns"):
        lines.append("- None")

    lines.extend([
        "",
        "## Conflict diagnostics",
        "",
        f"- Total deterministic format/question conflicts: **{conflicts.get('total', 0)}**",
        f"- Conflicts on PUID formats: **{conflicts.get('puid_format_conflicts', 0)}**",
        f"- Conflicts on non-PUID formats: **{conflicts.get('non_puid_format_conflicts', 0)}**",
        f"- Matches base audit count: **{conflicts.get('matches_base_audit_count', False)}**",
        "",
        "### Conflicts by question",
        "",
    ])
    for question_id, count in (conflicts.get("by_question") or {}).items():
        lines.append(f"- {question_id}: **{count}**")

    lines.extend(["", "### Conflicts by source combination", ""])
    for source_set, count in list((conflicts.get("by_source_combination") or {}).items())[:15]:
        lines.append(f"- {source_set}: **{count}**")

    lines.extend(["", "### Conflicts by answer combination", ""])
    for answer_set, count in list((conflicts.get("by_answer_combination") or {}).items())[:15]:
        lines.append(f"- {answer_set}: **{count}**")

    lines.append("")
    return "\n".join(lines)
