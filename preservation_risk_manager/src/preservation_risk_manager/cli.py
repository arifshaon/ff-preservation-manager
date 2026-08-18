from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from preservation_risk_manager.ai import (
    AIError,
    build_ai_provider,
    derive_answers_with_ai,
    load_ai_config,
    review_answers_with_ai,
)
from preservation_risk_manager.answer_derivation import derive_answers
from preservation_risk_manager.composite_risk import (
    CompositeRiskError,
    compute_composite_risk,
    load_composite_risk_config,
)
from preservation_risk_manager.data_access import JsonRegistryStore, RegistryReader, load_storage_config
from preservation_risk_manager.evidence_packs import build_evidence_pack, evidence_hash
from preservation_risk_manager.format_resolver import FormatResolver
from preservation_risk_manager.frameworks import load_framework
from preservation_risk_manager.policy_proposals import build_policy_change_proposal
from preservation_risk_manager.posture import compute_local_risk_posture
from preservation_risk_manager.literature_corpus import (
    ChunkSettings,
    LiteratureCorpusError,
    build_literature_corpus,
    init_inbox,
    search_corpus,
)
from preservation_risk_manager.scoring import score_answers
from preservation_risk_manager.training_corpus import (
    VALID_TIERS,
    CorpusSettings,
    TrainingCorpusError,
    build_training_corpus,
)


class CliFailure(Exception):
    def __init__(self, result: dict[str, Any], *, exit_code: int = 2) -> None:
        super().__init__(result.get("status", "cli_failure"))
        self.result = result
        self.exit_code = exit_code


def _require_file(path: str | Path, *, label: str) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_file():
        return candidate
    attempted = candidate.resolve(strict=False)
    raise FileNotFoundError(
        f"{label} not found: {attempted}. Pass an existing file path. "
        "If you need a registry export, run registry_builder first with exports enabled."
    )


def _load_json(path: str | Path) -> dict[str, Any]:
    path = _require_file(path, label="JSON input")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def _answer_map(answer_document: dict[str, Any]) -> dict[str, Any]:
    answers = answer_document.get("answers")
    if isinstance(answers, dict):
        return answers
    return answer_document


def _posture_fields_from_args(args: argparse.Namespace) -> tuple[str, str]:
    readiness_status = str(getattr(args, "readiness_status", None) or "Unknown")
    exposure_level = str(getattr(args, "exposure_level", None) or "Unknown")
    return readiness_status, exposure_level


def _analysis_result(
    *,
    framework_path: str | Path,
    evidence_pack: dict[str, Any],
    answer_document: dict[str, Any],
    readiness_status: str = "Unknown",
    exposure_level: str = "Unknown",
) -> dict[str, Any]:
    framework = load_framework(_require_file(framework_path, label="Framework file"))
    analysis = score_answers(framework, _answer_map(answer_document))
    result: dict[str, Any] = {
        "status": "ok",
        "format": evidence_pack.get("format"),
        "scope": evidence_pack.get("scope", "global"),
        "evidence_hash": evidence_hash(evidence_pack),
        "analysis": analysis,
    }

    institution_id = evidence_pack.get("institution_id")
    if institution_id:
        result.update({
            "institution_id": institution_id,
            "readiness_status": readiness_status,
            "exposure_level": exposure_level,
            "local_risk_posture": compute_local_risk_posture(
                analysis.get("analysed_band"),
                readiness_status,
                exposure_level=exposure_level,
            ),
        })
    return result


def analyze_fixture(args: argparse.Namespace) -> dict[str, Any]:
    evidence_pack = _load_json(args.evidence_pack)
    answer_document = _load_json(args.answers)
    readiness_status = str(answer_document.get("readiness_status") or "Unknown")
    exposure_level = str(answer_document.get("exposure_level") or "Unknown")
    return _analysis_result(
        framework_path=args.framework,
        evidence_pack=evidence_pack,
        answer_document=answer_document,
        readiness_status=readiness_status,
        exposure_level=exposure_level,
    )


def _resolution_message(resolution) -> str | None:
    if resolution.status == "ambiguous":
        noun = {
            "extension": "Extension",
            "mime_type": "MIME type",
            "authority_identifier": "Identifier",
            "verified_authority_identifier": "Verified identifier",
            "name": "Name",
            "alias": "Alias",
            "canonical_id": "Canonical ID",
        }.get(resolution.match_type or "", "Query")
        return (
            f"{noun} '{resolution.query}' matches {len(resolution.matches)} formats; "
            "specify a canonical ID or PUID."
        )
    if resolution.status == "not_found":
        return f"No format matched '{resolution.query}'."
    return None


def _resolution_summary(resolution) -> dict[str, Any]:
    summary = {
        "query": resolution.query,
        "status": resolution.status,
        "match_type": resolution.match_type,
        "match_count": len(resolution.matches),
        "matches": [
            {
                "canonical_id": match.get("canonical_id") or match.get("format_id") or match.get("id"),
                "preferred_name": match.get("preferred_name") or match.get("name") or match.get("label"),
            }
            for match in resolution.matches
        ],
    }
    message = _resolution_message(resolution)
    if message:
        summary["message"] = message
    return summary


def _registry_reader_from_args(args: argparse.Namespace) -> RegistryReader:
    registry_json = getattr(args, "registry_json", None)
    storage_config_path = getattr(args, "storage_config", None)
    if registry_json:
        registry_path = _require_file(registry_json, label="Registry JSON file")
        return RegistryReader(store=JsonRegistryStore.from_registry_json(registry_path))
    storage_path = _require_file(storage_config_path, label="Storage config file")
    return RegistryReader(storage_config=load_storage_config(storage_path))


def _compact_claim(claim: dict[str, Any]) -> dict[str, Any]:
    """Return provenance fields without long source bodies."""
    keys = (
        "claim_id",
        "source_claim_id",
        "_storage_key",
        "canonical_id",
        "criterion_id",
        "value",
        "answer_id",
        "source_id",
        "source_type",
        "source_record_id",
        "source_field",
        "mapping_rule_id",
        "mapping_version",
        "institution_id",
        "source_independence",
        "evidence_section",
        "review_status",
        "directness",
        "covers",
    )
    return {key: claim[key] for key in keys if key in claim and claim[key] is not None}


def _compact_answer_document(answer_document: dict[str, Any]) -> dict[str, Any]:
    compact = json.loads(json.dumps(answer_document, default=str))
    derivation = compact.get("derivation")
    if not isinstance(derivation, dict):
        return compact
    for result in derivation.values():
        if not isinstance(result, dict):
            continue
        claims = result.get("evidence_claims")
        if isinstance(claims, list):
            result["evidence_claims"] = [
                _compact_claim(claim)
                for claim in claims
                if isinstance(claim, dict)
            ]
    return compact


def _criterion_claims_summary(claims: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        key = (
            str(claim.get("criterion_id") or ""),
            str(claim.get("source_id") or ""),
            str(claim.get("value") or ""),
            str(claim.get("institution_id") or ""),
            str(claim.get("canonical_id") or ""),
        )
        group = grouped.setdefault(
            key,
            {
                "criterion_id": key[0],
                "source_id": key[1],
                "value": key[2],
                "institution_id": key[3] or None,
                "canonical_id": key[4],
                "count": 0,
                "source_record_ids": set(),
                "mapping_rule_ids": set(),
            },
        )
        group["count"] += 1
        if claim.get("source_record_id") is not None:
            group["source_record_ids"].add(str(claim["source_record_id"]))
        if claim.get("mapping_rule_id") is not None:
            group["mapping_rule_ids"].add(str(claim["mapping_rule_id"]))

    rows: list[dict[str, Any]] = []
    for group in grouped.values():
        row = dict(group)
        row["source_record_ids"] = sorted(row["source_record_ids"])
        row["mapping_rule_ids"] = sorted(row["mapping_rule_ids"])
        rows.append(row)
    rows.sort(key=lambda row: (
        row.get("criterion_id") or "",
        row.get("institution_id") or "",
        row.get("source_id") or "",
        row.get("canonical_id") or "",
        row.get("value") or "",
    ))

    return {
        "total_claims": len(claims),
        "groups": rows,
    }


def _resolved_analysis_context(args: argparse.Namespace) -> dict[str, Any]:
    framework_path = _require_file(args.framework, label="Framework file")
    framework = load_framework(framework_path)
    reader = _registry_reader_from_args(args)
    resolution = FormatResolver(reader).resolve(args.format)
    if not resolution.resolved or not resolution.format_doc:
        result = {"status": resolution.status, "resolution": _resolution_summary(resolution)}
        raise CliFailure(result, exit_code=2)

    criterion_claim_canonical_ids = reader.criterion_claim_canonical_ids(resolution.format_doc)
    criterion_claims = reader.get_criterion_claims_for_format(
        resolution.format_doc,
        institution_id=getattr(args, "institution", None),
    )
    evidence_pack = build_evidence_pack(
        resolution.format_doc,
        institution_id=getattr(args, "institution", None),
        criterion_claims=criterion_claims,
        include_unapproved=bool(getattr(args, "include_unapproved", False)),
    )
    answer_document = derive_answers(framework, evidence_pack)
    analysis = score_answers(framework, answer_document.get("scoring_answers") or answer_document["answers"])
    return {
        "framework": framework,
        "resolution": resolution,
        "criterion_claim_canonical_ids": criterion_claim_canonical_ids,
        "criterion_claims": criterion_claims,
        "evidence_pack": evidence_pack,
        "answer_document": answer_document,
        "analysis": analysis,
    }


def analyze_format(args: argparse.Namespace) -> dict[str, Any]:
    context = _resolved_analysis_context(args)
    output_answer_document = (
        _compact_answer_document(context["answer_document"])
        if args.compact_evidence
        else context["answer_document"]
    )
    result: dict[str, Any] = {
        "status": "ok",
        "resolution": _resolution_summary(context["resolution"]),
        "format": context["evidence_pack"].get("format"),
        "scope": context["evidence_pack"].get("scope", "global"),
        "evidence_hash": evidence_hash(context["evidence_pack"]),
        "criterion_claim_canonical_ids": context["criterion_claim_canonical_ids"],
        "criterion_claims_used": len(context["criterion_claims"]),
        "derived_answers": output_answer_document,
        "analysis": context["analysis"],
    }
    if args.evidence_summary:
        result["criterion_claims_summary"] = _criterion_claims_summary(context["criterion_claims"])

    if args.institution:
        readiness_status, exposure_level = _posture_fields_from_args(args)
        result.update({
            "institution_id": args.institution,
            "readiness_status": readiness_status,
            "exposure_level": exposure_level,
            "local_risk_posture": compute_local_risk_posture(
                context["analysis"].get("analysed_band"),
                readiness_status,
                exposure_level=exposure_level,
            ),
        })
    return result


def analyze_format_ai(args: argparse.Namespace) -> dict[str, Any]:
    context = _resolved_analysis_context(args)
    ai_config = load_ai_config(_require_file(args.ai_config, label="AI config file"))
    provider = build_ai_provider(ai_config)

    if args.ai_mode == "review-all":
        ai_answer_document = review_answers_with_ai(
            provider,
            context["framework"],
            context["evidence_pack"],
            context["answer_document"],
            max_evidence_items=args.max_ai_evidence_items,
        )
    else:
        ai_answer_document = derive_answers_with_ai(
            provider,
            context["framework"],
            context["evidence_pack"],
            context["answer_document"],
            max_evidence_items=args.max_ai_evidence_items,
        )

    ai_analysis = score_answers(
        context["framework"],
        ai_answer_document.get("scoring_answers") or ai_answer_document["answers"],
    )
    output_answer_document = (
        _compact_answer_document(ai_answer_document)
        if args.compact_evidence
        else ai_answer_document
    )
    result: dict[str, Any] = {
        "status": "ok",
        "mode": "ai_assisted",
        "ai_mode": args.ai_mode,
        "provider": provider.describe(),
        "resolution": _resolution_summary(context["resolution"]),
        "format": context["evidence_pack"].get("format"),
        "scope": context["evidence_pack"].get("scope", "global"),
        "evidence_hash": evidence_hash(context["evidence_pack"]),
        "criterion_claim_canonical_ids": context["criterion_claim_canonical_ids"],
        "criterion_claims_used": len(context["criterion_claims"]),
        "derived_answers": output_answer_document,
        "deterministic_analysis": context["analysis"],
        "analysis": ai_analysis,
    }
    if args.evidence_summary:
        result["criterion_claims_summary"] = _criterion_claims_summary(context["criterion_claims"])

    if args.institution:
        readiness_status, exposure_level = _posture_fields_from_args(args)
        result.update({
            "institution_id": args.institution,
            "readiness_status": readiness_status,
            "exposure_level": exposure_level,
            "local_risk_posture": compute_local_risk_posture(
                ai_analysis.get("analysed_band"),
                readiness_status,
                exposure_level=exposure_level,
            ),
        })
    return result


def propose_policy_change(args: argparse.Namespace) -> dict[str, Any]:
    context = _resolved_analysis_context(args)
    evidence_pack = context["evidence_pack"]
    readiness_status, exposure_level = _posture_fields_from_args(args)
    local_risk_posture = None
    if args.institution:
        local_risk_posture = compute_local_risk_posture(
            context["analysis"].get("analysed_band"),
            readiness_status,
            exposure_level=exposure_level,
        )
    derived_answers = (
        _compact_answer_document(context["answer_document"])
        if args.compact_evidence
        else context["answer_document"]
    )
    return build_policy_change_proposal(
        goal=args.goal,
        resolution=_resolution_summary(context["resolution"]),
        format_doc=evidence_pack.get("format") or {},
        scope=evidence_pack.get("scope", "global"),
        evidence_hash=evidence_hash(evidence_pack),
        analysis=context["analysis"],
        criterion_claim_canonical_ids=context["criterion_claim_canonical_ids"],
        criterion_claims_summary=_criterion_claims_summary(context["criterion_claims"]),
        derived_answers=derived_answers,
        institution_id=args.institution,
        readiness_status=readiness_status,
        exposure_level=exposure_level,
        local_risk_posture=local_risk_posture,
    )


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _tier_list(value: str) -> tuple[str, ...]:
    tiers = tuple(item.strip().upper() for item in str(value).split(",") if item.strip())
    unknown = [tier for tier in tiers if tier not in VALID_TIERS]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unknown tier(s): {', '.join(unknown)}. Allowed: {', '.join(VALID_TIERS)}"
        )
    if not tiers:
        raise argparse.ArgumentTypeError("at least one tier is required")
    return tiers


def _unit_interval(value: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if not 0 <= parsed < 1:
        raise argparse.ArgumentTypeError("must be between 0 and 1")
    return parsed


def build_corpus(args: argparse.Namespace) -> dict[str, Any]:
    """Build a versioned fine-tuning corpus and fail the build on a gate violation."""
    framework = load_framework(_require_file(args.framework, label="Framework file"))
    reader = _registry_reader_from_args(args)
    try:
        settings = CorpusSettings(
            corpus_version=args.corpus_version,
            tiers=args.tiers,
            abstention_share=args.abstention_share,
            abstention_tolerance=args.abstention_tolerance,
            split_seed=args.split_seed,
            test_share=args.test_share,
            val_share=args.val_share,
            max_evidence_items=args.max_evidence_items,
            min_test_examples_per_question=args.min_test_examples_per_question,
            max_answer_share=args.max_answer_share,
            institution_id=args.institution,
            max_formats=args.max_formats,
        )
    except TrainingCorpusError as exc:
        raise CliFailure({"status": "invalid_corpus_settings", "error": str(exc)}) from exc

    result = build_training_corpus(reader, framework, settings, Path(args.out))
    if not result["quality_gates"]["passed"]:
        # The corpus is written before this raises so a failed build can be
        # inspected. A gate failure means the corpus must not be trained on.
        raise CliFailure(result)
    return result


def composite_risk(args: argparse.Namespace) -> dict[str, Any]:
    """Deterministic composite obsolescence risk index for one format."""
    reader = _registry_reader_from_args(args)
    resolution = FormatResolver(reader).resolve(args.format)
    if not resolution.resolved or not resolution.format_doc:
        raise CliFailure({"status": resolution.status, "resolution": _resolution_summary(resolution)})
    claims = reader.get_criterion_claims_for_format(
        resolution.format_doc,
        institution_id=getattr(args, "institution", None),
    )
    # Hazard bands may live on strong-identity sibling records, just as
    # criterion claims do; fetch them through the same alias expansion.
    primary_id = resolution.format_doc.get("canonical_id")
    related_docs = [
        doc
        for cid in reader.criterion_claim_canonical_ids(resolution.format_doc)
        if cid != primary_id and (doc := reader.get_canonical_format(cid)) is not None
    ]
    try:
        config = load_composite_risk_config(getattr(args, "risk_config", None))
        assessment = compute_composite_risk(
            resolution.format_doc,
            claims,
            config=config,
            e_tool=getattr(args, "e_tool", None),
            related_format_docs=related_docs,
        )
    except CompositeRiskError as exc:
        raise CliFailure({"status": "composite_risk_error", "error": str(exc)}) from exc
    return {
        "status": assessment.get("status", "ok"),
        "resolution": _resolution_summary(resolution),
        "format": {
            "canonical_id": resolution.format_doc.get("canonical_id"),
            "preferred_name": resolution.format_doc.get("preferred_name"),
        },
        "scope": "institution" if getattr(args, "institution", None) else "global",
        "criterion_claims_used": len(claims),
        "composite_risk": assessment,
    }


def init_literature_inbox(args: argparse.Namespace) -> dict[str, Any]:
    """Create the drop folder a curator puts PDFs and OCR text into."""
    return init_inbox(Path(args.path), out_hint=args.out_hint)


def build_literature(args: argparse.Namespace) -> dict[str, Any]:
    """Ingest the inbox into a versioned, searchable chunk store."""
    try:
        settings = ChunkSettings(
            corpus_version=args.corpus_version,
            chunk_words=args.chunk_words,
            chunk_overlap=args.chunk_overlap,
            min_chars_per_doc=args.min_chars_per_doc,
        )
        return build_literature_corpus(Path(args.inbox), Path(args.out), settings)
    except LiteratureCorpusError as exc:
        raise CliFailure({"status": "literature_corpus_error", "error": str(exc)}) from exc


def search_literature(args: argparse.Namespace) -> dict[str, Any]:
    """Search a built literature corpus and return citable chunk hits."""
    try:
        return search_corpus(Path(args.corpus), args.query, limit=args.limit)
    except LiteratureCorpusError as exc:
        raise CliFailure({"status": "literature_corpus_error", "error": str(exc)}) from exc


def _add_registry_source_args(parser: argparse.ArgumentParser) -> None:
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--registry-json", help="Path to registry_builder registry.json export.")
    source.add_argument(
        "--storage-config",
        help="Path to a registry-builder storage block or full pipeline config containing 'storage'.",
    )


def _add_format_analysis_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--framework", required=True, help="Path to risk framework JSON.")
    _add_registry_source_args(parser)
    parser.add_argument("--format", required=True, help="Canonical ID, authority ID, MIME, extension, or name to resolve.")
    parser.add_argument("--institution", help="Optional institution ID for local posture analysis.")
    parser.add_argument("--readiness-status", default="Unknown", help="Institution readiness status when --institution is used.")
    parser.add_argument("--exposure-level", default="Unknown", help="Institution exposure level when --institution is used.")
    parser.add_argument("--include-unapproved", action="store_true", help="Include draft/rejected/superseded evidence claims.")
    parser.add_argument(
        "--evidence-summary",
        action="store_true",
        help="Add a compact criterion-claim summary grouped by criterion, source, value, institution, and canonical ID.",
    )
    parser.add_argument(
        "--compact-evidence",
        action="store_true",
        help="Suppress long evidence claim bodies in derived_answers while retaining provenance fields.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="preservation_risk_manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser(
        "analyze-fixture",
        help="Run framework scoring against fixture JSON files.",
    )
    analyze.add_argument("--framework", required=True, help="Path to risk framework JSON.")
    analyze.add_argument("--evidence-pack", required=True, help="Path to evidence pack JSON.")
    analyze.add_argument("--answers", required=True, help="Path to controlled answer JSON.")
    analyze.set_defaults(func=analyze_fixture)

    analyze_registry = subparsers.add_parser(
        "analyze-format",
        help="Resolve one format from a registry export or registry-builder store and run deterministic risk analysis.",
    )
    _add_format_analysis_args(analyze_registry)
    analyze_registry.set_defaults(func=analyze_format)

    analyze_registry_ai = subparsers.add_parser(
        "analyze-format-ai",
        help=(
            "Run deterministic risk analysis and either fill unresolved questions with AI or "
            "independently review all questions without changing deterministic answers."
        ),
    )
    _add_format_analysis_args(analyze_registry_ai)
    analyze_registry_ai.add_argument(
        "--ai-config",
        required=True,
        help="Path to AI provider JSON configuration, for example config/ai.local.json.",
    )
    analyze_registry_ai.add_argument(
        "--ai-mode",
        choices=("fill-gaps", "review-all"),
        default="fill-gaps",
        help=(
            "AI behavior: fill-gaps may supply unresolved controlled answers; review-all compares "
            "AI answers against deterministic answers without changing scoring inputs."
        ),
    )
    analyze_registry_ai.add_argument(
        "--max-ai-evidence-items",
        type=int,
        default=20,
        help="Maximum evidence items supplied to AI for each question it interprets or reviews.",
    )
    analyze_registry_ai.set_defaults(func=analyze_format_ai)

    propose = subparsers.add_parser(
        "propose-policy-change",
        help="Prepare an evidence-grounded draft policy/action recommendation package for human approval.",
    )
    propose.add_argument("--framework", required=True, help="Path to risk framework JSON.")
    _add_registry_source_args(propose)
    propose.add_argument("--format", required=True, help="Canonical ID, authority ID, MIME, extension, or name to resolve.")
    propose.add_argument("--institution", help="Optional institution ID for local policy proposal.")
    propose.add_argument("--readiness-status", default="Unknown", help="Institution readiness status when --institution is used.")
    propose.add_argument("--exposure-level", default="Unknown", help="Institution exposure level when --institution is used.")
    propose.add_argument("--include-unapproved", action="store_true", help="Include draft/rejected/superseded evidence claims.")
    propose.add_argument("--goal", required=True, help="Human goal for the draft policy/action recommendation.")
    propose.add_argument(
        "--compact-evidence",
        action="store_true",
        help="Suppress long evidence claim bodies in the LLM context while retaining provenance fields.",
    )
    propose.set_defaults(func=propose_policy_change)

    corpus = subparsers.add_parser(
        "build-training-corpus",
        help="Build a versioned, leakage-gated fine-tuning corpus for the risk-answer interpreter.",
    )
    corpus.add_argument("--framework", required=True, help="Path to risk framework JSON.")
    _add_registry_source_args(corpus)
    corpus.add_argument("--out", required=True, help="Output root directory; the corpus is written to <out>/<corpus-version>/.")
    corpus.add_argument("--corpus-version", required=True, help="Corpus version label, for example 2026-09.")
    corpus.add_argument(
        "--tiers",
        type=_tier_list,
        default=VALID_TIERS,
        help="Comma-separated tiers to build. A=no NARA evidence, B=leave-one-out, C=abstention. Default: A,B,C.",
    )
    corpus.add_argument(
        "--abstention-share",
        type=_unit_interval,
        default=0.12,
        help="Target share of Tier C abstention examples in the corpus. Default: 0.12.",
    )
    corpus.add_argument(
        "--abstention-tolerance",
        type=_unit_interval,
        default=0.03,
        help="Allowed deviation from --abstention-share before the build fails. Default: 0.03.",
    )
    corpus.add_argument("--split-seed", type=int, default=20260901, help="Seed for the deterministic format-level split.")
    corpus.add_argument("--test-share", type=_unit_interval, default=0.15, help="Share of formats held out for test. Default: 0.15.")
    corpus.add_argument("--val-share", type=_unit_interval, default=0.10, help="Share of formats held out for validation. Default: 0.10.")
    corpus.add_argument("--institution", help="Optional institution ID; omit to build a global corpus.")
    corpus.add_argument(
        "--max-evidence-items",
        type=_positive_int,
        default=20,
        help="Maximum evidence items supplied per question, matching inference. Default: 20.",
    )
    corpus.add_argument(
        "--min-test-examples-per-question",
        type=int,
        default=30,
        help="Gate: minimum test examples each bound question needs for per-question metrics. Default: 30.",
    )
    corpus.add_argument(
        "--max-answer-share",
        type=_unit_interval,
        default=0.90,
        help="Gate: maximum share a single answer may hold for one question. Default: 0.90.",
    )
    corpus.add_argument(
        "--max-formats",
        type=_positive_int,
        help="Optional cap on formats scanned, for smoke runs against a large registry.",
    )
    corpus.set_defaults(func=build_corpus)

    composite = subparsers.add_parser(
        "composite-risk",
        help="Deterministic composite obsolescence risk index (NARA baseline + LoC sustainability + temporal term).",
    )
    _add_registry_source_args(composite)
    composite.add_argument("--format", required=True, help="Canonical ID, authority ID, MIME, extension, or name to resolve.")
    composite.add_argument("--institution", help="Optional institution ID; adds institution-scoped claims.")
    composite.add_argument(
        "--risk-config",
        help="Optional JSON overriding gamma1/gamma2/alpha, tier bounds, criterion weights, and coverage minimum.",
    )
    composite.add_argument(
        "--e-tool",
        type=float,
        help="Open-source tool availability in [0,1]. Omitted: neutral 0.5 until an FPR source exists.",
    )
    composite.set_defaults(func=composite_risk)

    inbox = subparsers.add_parser(
        "init-literature-inbox",
        help="Create the drop folder for Corpus B documents, with a README explaining what to drop.",
    )
    inbox.add_argument("--path", required=True, help="Directory to create; the drop folder is <path>/inbox.")
    inbox.add_argument("--out-hint", default="corpus/", help="Output path shown in the generated README.")
    inbox.set_defaults(func=init_literature_inbox)

    literature = subparsers.add_parser(
        "build-literature-corpus",
        help="Build Corpus B: chunk and index PDFs/OCR text dropped in the inbox.",
    )
    literature.add_argument("--inbox", required=True, help="Directory containing dropped documents.")
    literature.add_argument("--out", required=True, help="Output root; the corpus is written to <out>/<corpus-version>/.")
    literature.add_argument("--corpus-version", required=True, help="Corpus version label, for example 2026-09.")
    literature.add_argument(
        "--chunk-words",
        type=_positive_int,
        default=220,
        help="Words per chunk. Chunks never span a page boundary. Default: 220.",
    )
    literature.add_argument(
        "--chunk-overlap",
        type=int,
        default=40,
        help="Words repeated between neighbouring chunks so claims are not split. Default: 40.",
    )
    literature.add_argument(
        "--min-chars-per-doc",
        type=int,
        default=50,
        help="Below this, a document is reported as needing OCR instead of indexed. Default: 200.",
    )
    literature.set_defaults(func=build_literature)

    find = subparsers.add_parser(
        "search-literature",
        help="Search a built literature corpus and return citable chunk IDs.",
    )
    find.add_argument("--corpus", required=True, help="Path to a built corpus directory, for example corpus/2026-09.")
    find.add_argument("--query", required=True, help="Search terms.")
    find.add_argument("--limit", type=_positive_int, default=10, help="Maximum results. Default: 10.")
    find.set_defaults(func=search_literature)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.func(args)
    except (AIError, FileNotFoundError) as exc:
        parser.exit(2, f"error: {exc}\n")
    except CliFailure as exc:
        print(json.dumps(exc.result, indent=2, sort_keys=True))
        return exc.exit_code
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
