from __future__ import annotations

from pathlib import Path
from typing import Any

from preservation_risk_manager.data_access import RegistryReader
from preservation_risk_manager.frameworks import RiskFramework
from preservation_risk_manager.registry_audit import write_registry_risk_evidence_audit


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


def _claim_source(row: dict[str, Any]) -> str:
    return str(row.get("source_id") or row.get("source_type") or "unknown")


def _evidence_identity(claim: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    return (
        str(claim.get("canonical_id") or ""),
        str(claim.get("criterion_id") or ""),
        str(claim.get("value") or ""),
        _claim_source(claim),
        str(claim.get("source_record_id") or ""),
        str(claim.get("institution_id") or ""),
    )


def _mapping_rule_metadata(mappings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    for mapping in mappings:
        source = str(mapping.get("source_id") or mapping.get("source_type") or "unknown")
        for rule in mapping.get("maps") or []:
            if not isinstance(rule, dict):
                continue
            rule_id = str(rule.get("id") or "")
            if not rule_id:
                continue
            metadata[rule_id] = {
                "source": source,
                "criterion_id": str(rule.get("criterion") or ""),
                "mapping_status": str(rule.get("mapping_status") or ""),
                "review_status": str(rule.get("review_status") or mapping.get("review_status") or ""),
                "directness": str(rule.get("directness") or ""),
                "covers": str(rule.get("covers") or ""),
                "source_independence": str(rule.get("source_independence") or ""),
                "rationale": str(rule.get("rationale") or ""),
            }
    return metadata


def refine_registry_risk_evidence_audit(
    report: dict[str, Any],
    reader: RegistryReader,
    framework: RiskFramework,
    *,
    institution_id: str | None = None,
    criteria_path: str | Path | None = None,
    mappings_path: str | Path | None = None,
) -> dict[str, Any]:
    """Add scope accounting and governance context to a registry audit.

    The base audit intentionally scores only evidence in the requested scope.  A
    global audit therefore excludes institution-scoped claims.  Draft mapping
    recomputation must use the same scope or its accepted-claim count is not
    comparable with the audit summary.

    Draft mapping uplift is a coverage diagnostic, never an approval decision.
    This function makes that boundary explicit and carries the mapping rule's
    rationale/directness/coverage into the report so partial or source-scoped
    evidence cannot look authoritative merely because it fills many gaps.
    """
    all_current_claims = [
        row for row in reader.query("criterion_claims", {})
        if row.get("current") is not False
    ]
    in_scope_claims = [
        row for row in all_current_claims
        if _claim_in_scope(row, institution_id=institution_id)
    ]
    institution_scoped_claims = [row for row in all_current_claims if _is_institution_scoped(row)]

    summary = report.setdefault("summary", {})
    # Backwards-compatible field: it remains the count actually available to
    # scoring in this audit scope.
    summary["current_criterion_claims"] = len(in_scope_claims)
    summary["current_criterion_claims_in_scope"] = len(in_scope_claims)
    summary["current_criterion_claims_total"] = len(all_current_claims)
    summary["institution_scoped_current_claims_total"] = len(institution_scoped_claims)
    summary["claim_scope_note"] = (
        "Global audits exclude institution-scoped criterion claims from scoring; "
        "institution audits include global claims plus claims for the requested institution."
    )

    draft = report.get("draft_mapping_opportunities") or {}
    if draft.get("status") != "ok":
        return report

    draft["scope"] = "institution" if institution_id else "global"
    draft["ranking_note"] = (
        "Potential question gap fills measure coverage opportunity only. They are not approval "
        "recommendations and do not establish that a source-scoped or partial mapping is suitable "
        "for global deterministic scoring."
    )

    if not criteria_path or not mappings_path:
        return report

    try:
        from registry_builder.criteria import load_criteria  # type: ignore
        from registry_builder.criterion_mapping import build_criterion_claims, load_mappings  # type: ignore
    except ImportError:
        return report

    criteria = load_criteria(criteria_path)
    mappings = load_mappings(mappings_path)
    formats = reader.list_canonical_formats()
    source_records = reader.query("source_records", {})
    if source_records:
        accepted_all = build_criterion_claims(
            formats,
            source_records,
            mappings,
            criteria,
            include_drafts=False,
        )
        projected_all = build_criterion_claims(
            formats,
            source_records,
            mappings,
            criteria,
            include_drafts=True,
        )
        accepted = [claim for claim in accepted_all if _claim_in_scope(claim, institution_id=institution_id)]
        projected = [claim for claim in projected_all if _claim_in_scope(claim, institution_id=institution_id)]
        accepted_ids = {_evidence_identity(claim) for claim in accepted}
        draft_only = [claim for claim in projected if _evidence_identity(claim) not in accepted_ids]
        draft["accepted_claims_recomputed"] = len(accepted)
        draft["projected_claims_with_drafts"] = len(projected)
        draft["draft_only_claims"] = len(draft_only)

    rule_metadata = _mapping_rule_metadata(mappings)
    for row in draft.get("top_rules") or []:
        rule_id = str(row.get("mapping_rule_id") or "")
        meta = rule_metadata.get(rule_id, {})
        for key in ("directness", "covers", "source_independence", "rationale"):
            if meta.get(key):
                row[key] = meta[key]
        row["coverage_opportunity_only"] = True
        if str(row.get("mapping_status") or "") != "accepted":
            row["approval_status"] = "requires_human_review"
        if row.get("covers") and row.get("covers") != "full":
            row["governance_caution"] = (
                "Partial criterion coverage: review semantic scope before using this rule in deterministic scoring."
            )
        elif row.get("source_independence") and row.get("source_independence") != "independent":
            row["governance_caution"] = (
                "Source-derived evidence: review source scope and transferability before deterministic use."
            )

    report["draft_mapping_opportunities"] = draft
    return report


def write_refined_registry_risk_evidence_audit(
    report: dict[str, Any],
    out_dir: str | Path,
) -> dict[str, str]:
    paths = write_registry_risk_evidence_audit(report, out_dir)
    markdown_path = Path(paths["markdown"])
    text = markdown_path.read_text(encoding="utf-8")
    marker = "## Draft mapping opportunities\n\n"
    draft = report.get("draft_mapping_opportunities") or {}
    note = str(draft.get("ranking_note") or "").strip()
    if note and marker in text:
        text = text.replace(marker, marker + f"> **Governance note:** {note}\n\n", 1)
    markdown_path.write_text(text, encoding="utf-8")
    return paths
