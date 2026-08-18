from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Any

from preservation_risk_manager.answer_derivation import derive_answers
from preservation_risk_manager.data_access import RegistryReader
from preservation_risk_manager.evidence_packs import build_evidence_pack
from preservation_risk_manager.frameworks import RiskFramework
from preservation_risk_manager.scoring import score_answers


def _format_id(format_doc: dict[str, Any]) -> str:
    return str(format_doc.get("canonical_id") or format_doc.get("format_id") or format_doc.get("id") or "")


def _format_name(format_doc: dict[str, Any]) -> str:
    return str(format_doc.get("preferred_name") or format_doc.get("format_name") or format_doc.get("name") or _format_id(format_doc))


def _puid_values(format_doc: dict[str, Any]) -> list[str]:
    identifiers = format_doc.get("identifiers") or {}
    values: list[str] = []
    if isinstance(identifiers, dict):
        raw = identifiers.get("puid") or []
        if not isinstance(raw, list):
            raw = [raw]
        values.extend(str(value) for value in raw if value)
    raw_puids = format_doc.get("puids") or []
    if not isinstance(raw_puids, list):
        raw_puids = [raw_puids]
    for value in raw_puids:
        text = str(value)
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


def _relationship_scope_counts(formats: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for format_doc in formats:
        for ref in format_doc.get("source_records") or []:
            if not isinstance(ref, dict):
                continue
            source = str(ref.get("source_id") or ref.get("source_type") or "")
            if source != "loc_fdd_xml":
                continue
            scope = str(ref.get("evidence_scope") or ref.get("relationship") or "unscoped")
            counts[scope] += 1
    return dict(sorted(counts.items()))


def _projected_draft_mapping_opportunities(
    *,
    reader: RegistryReader,
    framework: RiskFramework,
    formats: list[dict[str, Any]],
    unanswered_by_format: dict[str, set[str]],
    alias_owner: dict[str, str],
    criteria_path: str | Path | None,
    mappings_path: str | Path | None,
    sample_limit: int,
) -> dict[str, Any]:
    if not criteria_path or not mappings_path:
        return {
            "status": "not_requested",
            "note": "Pass --criteria and --mappings-path to estimate draft mapping uplift.",
        }
    try:
        from registry_builder.criteria import load_criteria  # type: ignore
        from registry_builder.criterion_mapping import build_criterion_claims, load_mappings  # type: ignore
    except ImportError as exc:
        return {
            "status": "unavailable",
            "reason": f"registry_builder could not be imported: {exc}",
        }

    criteria = load_criteria(criteria_path)
    mappings = load_mappings(mappings_path)
    source_records = reader.query("source_records", {})
    if not source_records:
        return {
            "status": "unavailable",
            "reason": "No source_records collection is available through this registry source.",
        }

    accepted = build_criterion_claims(
        formats,
        source_records,
        mappings,
        criteria,
        include_drafts=False,
    )
    projected = build_criterion_claims(
        formats,
        source_records,
        mappings,
        criteria,
        include_drafts=True,
    )

    def evidence_identity(claim: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
        return (
            str(claim.get("canonical_id") or ""),
            str(claim.get("criterion_id") or ""),
            str(claim.get("value") or ""),
            _claim_source(claim),
            str(claim.get("source_record_id") or ""),
            str(claim.get("institution_id") or ""),
        )

    accepted_identities = {evidence_identity(claim) for claim in accepted}
    draft_only = [claim for claim in projected if evidence_identity(claim) not in accepted_identities]
    questions_by_criterion: dict[str, list[str]] = defaultdict(list)
    for question in framework.questions:
        for criterion in question.evidence_fields:
            questions_by_criterion[str(criterion)].append(question.id)

    rule_meta: dict[str, dict[str, Any]] = {}
    for mapping in mappings:
        source = str(mapping.get("source_id") or mapping.get("source_type") or "unknown")
        for rule in mapping.get("maps") or []:
            if not isinstance(rule, dict):
                continue
            rule_id = str(rule.get("id") or "")
            if not rule_id:
                continue
            rule_meta[rule_id] = {
                "source": source,
                "criterion_id": str(rule.get("criterion") or ""),
                "mapping_status": str(rule.get("mapping_status") or ""),
                "review_status": str(rule.get("review_status") or mapping.get("review_status") or ""),
            }

    by_rule: dict[str, dict[str, Any]] = {}
    for claim in draft_only:
        rule_id = str(claim.get("mapping_rule_id") or "unknown")
        criterion_id = str(claim.get("criterion_id") or "")
        row = by_rule.setdefault(
            rule_id,
            {
                "mapping_rule_id": rule_id,
                "criterion_id": criterion_id,
                "source": _claim_source(claim),
                "new_claims": 0,
                "new_formats": set(),
                "potential_question_gap_fills": set(),
                "questions_supported": sorted(set(questions_by_criterion.get(criterion_id, []))),
                "mapping_status": rule_meta.get(rule_id, {}).get("mapping_status"),
                "review_status": rule_meta.get(rule_id, {}).get("review_status"),
            },
        )
        row["new_claims"] += 1
        canonical_id = str(claim.get("canonical_id") or "")
        owner = alias_owner.get(canonical_id, canonical_id)
        if owner:
            row["new_formats"].add(owner)
            for question_id in questions_by_criterion.get(criterion_id, []):
                if question_id in unanswered_by_format.get(owner, set()):
                    row["potential_question_gap_fills"].add((owner, question_id))

    rows: list[dict[str, Any]] = []
    for row in by_rule.values():
        stored = dict(row)
        stored["new_formats"] = len(row["new_formats"])
        stored["potential_question_gap_fills"] = len(row["potential_question_gap_fills"])
        rows.append(stored)
    rows.sort(
        key=lambda row: (
            -int(row["potential_question_gap_fills"]),
            -int(row["new_formats"]),
            -int(row["new_claims"]),
            str(row["mapping_rule_id"]),
        )
    )
    return {
        "status": "ok",
        "accepted_claims_recomputed": len(accepted),
        "projected_claims_with_drafts": len(projected),
        "draft_only_claims": len(draft_only),
        "rules_with_uplift": len(rows),
        "top_rules": rows[:sample_limit],
    }


def build_registry_risk_evidence_audit(
    reader: RegistryReader,
    framework: RiskFramework,
    *,
    institution_id: str | None = None,
    criteria_path: str | Path | None = None,
    mappings_path: str | Path | None = None,
    sample_limit: int = 25,
) -> dict[str, Any]:
    formats = reader.list_canonical_formats()
    current_claims = [
        row for row in reader.query("criterion_claims", {})
        if _claim_in_scope(row, institution_id=institution_id)
    ]
    claims_by_canonical: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in current_claims:
        claims_by_canonical[str(claim.get("canonical_id") or "")].append(claim)

    alias_owner: dict[str, str] = {}
    for format_doc in formats:
        owner = _format_id(format_doc)
        for alias in reader.criterion_claim_canonical_ids(format_doc):
            alias_owner.setdefault(alias, owner)

    answered_distribution: Counter[int] = Counter()
    analysis_status: Counter[str] = Counter()
    band_distribution: Counter[str] = Counter()
    band_suppressed_reasons: Counter[str] = Counter()
    question_stats: dict[str, dict[str, Any]] = {}
    for question in framework.questions:
        question_stats[question.id] = {
            "label": question.label,
            "critical": question.critical,
            "evidence_fields": list(question.evidence_fields),
            "answered": 0,
            "abstained": 0,
            "missing_evidence": 0,
            "unknown_with_matching_evidence": 0,
            "conflicts": 0,
            "answer_distribution": Counter(),
            "source_support": defaultdict(set),
        }

    criterion_claims: dict[str, dict[str, Any]] = {}
    source_claims: dict[str, dict[str, Any]] = {}
    conflict_samples: list[dict[str, Any]] = []
    gap_examples: list[dict[str, Any]] = []
    unanswered_by_format: dict[str, set[str]] = {}
    band_eligible = 0
    puid_formats = 0
    puid_band_eligible = 0
    total_completeness = 0.0

    for claim in current_claims:
        criterion_id = str(claim.get("criterion_id") or "unknown")
        source = _claim_source(claim)
        canonical_id = str(claim.get("canonical_id") or "")
        criterion_row = criterion_claims.setdefault(
            criterion_id,
            {"claims": 0, "formats": set(), "sources": set()},
        )
        criterion_row["claims"] += 1
        if canonical_id:
            criterion_row["formats"].add(alias_owner.get(canonical_id, canonical_id))
        criterion_row["sources"].add(source)

        source_row = source_claims.setdefault(
            source,
            {"claims": 0, "formats": set(), "criteria": set(), "question_support": defaultdict(set)},
        )
        source_row["claims"] += 1
        if canonical_id:
            source_row["formats"].add(alias_owner.get(canonical_id, canonical_id))
        source_row["criteria"].add(criterion_id)

    for format_doc in formats:
        format_id = _format_id(format_doc)
        claims: list[dict[str, Any]] = []
        seen_claims: set[str] = set()
        for canonical_id in reader.criterion_claim_canonical_ids(format_doc):
            for claim in claims_by_canonical.get(canonical_id, []):
                key = _claim_key(claim)
                if key in seen_claims:
                    continue
                seen_claims.add(key)
                claims.append(claim)

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
        answered_distribution[int(analysis["answered_questions"])] += 1
        analysis_status[str(analysis["analysis_status"])] += 1
        total_completeness += float(analysis["evidence_completeness"])
        analysed_band = analysis.get("analysed_band")
        if analysed_band:
            band_eligible += 1
            band_distribution[str(analysed_band)] += 1
        else:
            band_suppressed_reasons[str(analysis.get("band_suppressed_reason") or "unknown")] += 1

        puids = _puid_values(format_doc)
        if puids:
            puid_formats += 1
            if analysed_band:
                puid_band_eligible += 1

        unanswered: set[str] = set()
        results_by_question = {row["question_id"]: row for row in analysis["question_results"]}
        for question in framework.questions:
            derivation = answer_document["derivation"][question.id]
            scoring_row = results_by_question[question.id]
            stats = question_stats[question.id]
            answer_id = str(derivation.get("answer_id") or "")
            stats["answer_distribution"][answer_id] += 1
            if scoring_row.get("abstention"):
                stats["abstained"] += 1
                unanswered.add(question.id)
            else:
                stats["answered"] += 1

            status = str(derivation.get("status") or "")
            if status == "missing_evidence":
                stats["missing_evidence"] += 1
            elif status == "unknown":
                stats["unknown_with_matching_evidence"] += 1
            elif status == "derived_conflict_conservative":
                stats["conflicts"] += 1
                if len(conflict_samples) < sample_limit:
                    conflict_samples.append({
                        "canonical_id": format_id,
                        "preferred_name": _format_name(format_doc),
                        "puids": puids,
                        "question_id": question.id,
                        "conflicting_answer_ids": derivation.get("conflicting_answer_ids") or [],
                        "sources": sorted({_claim_source(claim) for claim in derivation.get("evidence_claims") or []}),
                    })

            for evidence_claim in derivation.get("evidence_claims") or []:
                source = _claim_source(evidence_claim)
                stats["source_support"][source].add(format_id)
                source_row = source_claims.setdefault(
                    source,
                    {"claims": 0, "formats": set(), "criteria": set(), "question_support": defaultdict(set)},
                )
                source_row["question_support"][question.id].add(format_id)

        unanswered_by_format[format_id] = unanswered
        if unanswered and len(gap_examples) < sample_limit:
            gap_examples.append({
                "canonical_id": format_id,
                "preferred_name": _format_name(format_doc),
                "puids": puids,
                "answered_questions": int(analysis["answered_questions"]),
                "total_questions": int(analysis["total_questions"]),
                "unanswered_questions": sorted(unanswered),
                "band_suppressed_reason": analysis.get("band_suppressed_reason"),
            })

    serial_question_stats: dict[str, Any] = {}
    for question_id, row in question_stats.items():
        stored = dict(row)
        stored["answer_distribution"] = dict(sorted(row["answer_distribution"].items()))
        stored["source_support"] = {
            source: len(format_ids)
            for source, format_ids in sorted(row["source_support"].items())
        }
        serial_question_stats[question_id] = stored

    serial_criterion_claims = {
        criterion_id: {
            "claims": int(row["claims"]),
            "formats_with_claim": len(row["formats"]),
            "sources": sorted(row["sources"]),
        }
        for criterion_id, row in sorted(criterion_claims.items())
    }
    serial_source_claims = {
        source: {
            "claims": int(row["claims"]),
            "formats_with_claim": len(row["formats"]),
            "criteria": sorted(row["criteria"]),
            "question_support": {
                question_id: len(format_ids)
                for question_id, format_ids in sorted(row["question_support"].items())
            },
        }
        for source, row in sorted(source_claims.items())
    }

    report: dict[str, Any] = {
        "status": "ok",
        "framework": {
            "framework_id": framework.framework_id,
            "version": framework.version,
            "questions": len(framework.questions),
            "min_completeness_for_band": framework.min_completeness_for_band,
            "banding_enabled": framework.banding_enabled,
        },
        "scope": "institution" if institution_id else "global",
        "institution_id": institution_id,
        "summary": {
            "canonical_formats": len(formats),
            "current_criterion_claims": len(current_claims),
            "formats_with_puid": puid_formats,
            "band_eligible_formats": band_eligible,
            "band_eligible_percent": round((band_eligible / len(formats) * 100.0), 2) if formats else 0.0,
            "puid_band_eligible_formats": puid_band_eligible,
            "puid_band_eligible_percent": round((puid_band_eligible / puid_formats * 100.0), 2) if puid_formats else 0.0,
            "average_evidence_completeness": round((total_completeness / len(formats)), 4) if formats else 0.0,
            "conflict_format_questions": sum(row["conflicts"] for row in question_stats.values()),
        },
        "coverage_by_answered_questions": {
            str(answered): count for answered, count in sorted(answered_distribution.items())
        },
        "analysis_status_distribution": dict(sorted(analysis_status.items())),
        "band_distribution": dict(sorted(band_distribution.items())),
        "band_suppressed_reasons": dict(sorted(band_suppressed_reasons.items())),
        "question_coverage": serial_question_stats,
        "criterion_coverage": serial_criterion_claims,
        "source_contribution": serial_source_claims,
        "conflicts": {
            "count": sum(row["conflicts"] for row in question_stats.values()),
            "samples": conflict_samples,
        },
        "gap_examples": gap_examples,
        "loc_relationship_scopes": _relationship_scope_counts(formats),
    }
    report["draft_mapping_opportunities"] = _projected_draft_mapping_opportunities(
        reader=reader,
        framework=framework,
        formats=formats,
        unanswered_by_format=unanswered_by_format,
        alias_owner=alias_owner,
        criteria_path=criteria_path,
        mappings_path=mappings_path,
        sample_limit=sample_limit,
    )
    return report


def render_registry_risk_evidence_audit_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    framework = report.get("framework") or {}
    lines = [
        "# Registry-wide Preservation Risk / Evidence Audit",
        "",
        f"Framework: `{framework.get('framework_id')}` version `{framework.get('version')}`",
        f"Scope: `{report.get('scope')}`",
        "",
        "## Executive summary",
        "",
        f"- Canonical formats: **{summary.get('canonical_formats', 0)}**",
        f"- Current criterion claims: **{summary.get('current_criterion_claims', 0)}**",
        f"- Formats eligible for a deterministic band: **{summary.get('band_eligible_formats', 0)}** ({summary.get('band_eligible_percent', 0)}%)",
        f"- PUID formats eligible for a deterministic band: **{summary.get('puid_band_eligible_formats', 0)}** ({summary.get('puid_band_eligible_percent', 0)}%)",
        f"- Average evidence completeness: **{float(summary.get('average_evidence_completeness', 0)) * 100:.1f}%**",
        f"- Conflicting format/question derivations: **{summary.get('conflict_format_questions', 0)}**",
        "",
        "## Coverage by answered questions",
        "",
        "| Answered questions | Formats |",
        "|---:|---:|",
    ]
    for answered, count in (report.get("coverage_by_answered_questions") or {}).items():
        lines.append(f"| {answered} | {count} |")

    lines.extend(["", "## Question coverage", "", "| Question | Answered | Abstained | Missing evidence | Unknown evidence | Conflicts |", "|---|---:|---:|---:|---:|---:|"])
    for question_id, row in (report.get("question_coverage") or {}).items():
        lines.append(
            f"| {question_id} | {row.get('answered', 0)} | {row.get('abstained', 0)} | {row.get('missing_evidence', 0)} | {row.get('unknown_with_matching_evidence', 0)} | {row.get('conflicts', 0)} |"
        )

    lines.extend(["", "## Deterministic band distribution", ""])
    for band, count in (report.get("band_distribution") or {}).items():
        lines.append(f"- {band}: **{count}**")
    if not report.get("band_distribution"):
        lines.append("- No formats currently receive a deterministic band.")

    lines.extend(["", "## Evidence contribution by source", "", "| Source | Claims | Formats | Criteria |", "|---|---:|---:|---:|"])
    for source, row in (report.get("source_contribution") or {}).items():
        lines.append(f"| {source} | {row.get('claims', 0)} | {row.get('formats_with_claim', 0)} | {len(row.get('criteria') or [])} |")

    lines.extend(["", "## Criterion coverage", "", "| Criterion | Claims | Formats | Sources |", "|---|---:|---:|---|"])
    criterion_rows = sorted(
        (report.get("criterion_coverage") or {}).items(),
        key=lambda item: (-int(item[1].get("formats_with_claim", 0)), item[0]),
    )
    for criterion_id, row in criterion_rows:
        lines.append(
            f"| {criterion_id} | {row.get('claims', 0)} | {row.get('formats_with_claim', 0)} | {', '.join(row.get('sources') or [])} |"
        )

    lines.extend(["", "## LOC relationship scopes", ""])
    for scope, count in (report.get("loc_relationship_scopes") or {}).items():
        lines.append(f"- {scope}: **{count}**")

    draft = report.get("draft_mapping_opportunities") or {}
    lines.extend(["", "## Draft mapping opportunities", ""])
    if draft.get("status") != "ok":
        lines.append(f"Status: `{draft.get('status')}`. {draft.get('note') or draft.get('reason') or ''}".rstrip())
    else:
        lines.append(
            f"Draft-only projected claims: **{draft.get('draft_only_claims', 0)}** across **{draft.get('rules_with_uplift', 0)}** mapping rules."
        )
        lines.extend(["", "| Mapping rule | Criterion | Source | New formats | Potential question gap fills |", "|---|---|---|---:|---:|"])
        for row in draft.get("top_rules") or []:
            lines.append(
                f"| {row.get('mapping_rule_id')} | {row.get('criterion_id')} | {row.get('source')} | {row.get('new_formats', 0)} | {row.get('potential_question_gap_fills', 0)} |"
            )

    conflicts = report.get("conflicts") or {}
    lines.extend(["", "## Conflict samples", ""])
    if not conflicts.get("samples"):
        lines.append("No deterministic answer conflicts were found in the sampled report output.")
    else:
        for row in conflicts.get("samples") or []:
            lines.append(
                f"- `{row.get('canonical_id')}` / `{row.get('question_id')}`: {', '.join(row.get('conflicting_answer_ids') or [])} (sources: {', '.join(row.get('sources') or [])})"
            )
    lines.append("")
    return "\n".join(lines)


def write_registry_risk_evidence_audit(report: dict[str, Any], out_dir: str | Path) -> dict[str, str]:
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "registry_risk_evidence_audit.json"
    markdown_path = output / "registry_risk_evidence_audit.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    markdown_path.write_text(render_registry_risk_evidence_audit_markdown(report), encoding="utf-8")
    return {
        "json": str(json_path.resolve()),
        "markdown": str(markdown_path.resolve()),
    }
