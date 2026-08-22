from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from preservation_risk_manager.ai.config import load_ai_config
from preservation_risk_manager.ai.expert_synthesis import synthesize_expert_with_ai
from preservation_risk_manager.ai.factory import build_ai_provider
from preservation_risk_manager.data_access import JsonRegistryStore, RegistryReader, load_storage_config
from preservation_risk_manager.format_identification import enrich_candidate_from_source_records
from preservation_risk_manager.format_resolver import FormatResolver
from preservation_risk_manager.frameworks import load_framework
from preservation_risk_manager.risk_context import build_external_risk_context
from preservation_risk_manager.source_evidence import build_ai_source_evidence
from preservation_risk_manager.synthesis_policy import load_synthesis_policy


def _require_file(value: str, label: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path.resolve(strict=False)}")
    return path


def _reader(args: argparse.Namespace) -> RegistryReader:
    if args.registry_json:
        return RegistryReader(store=JsonRegistryStore.from_registry_json(_require_file(args.registry_json, "Registry JSON")))
    return RegistryReader(storage_config=load_storage_config(_require_file(args.storage_config, "Storage config")))


def _display(value: Any, fallback: str = "Unknown") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _human(result: dict[str, Any]) -> str:
    fmt = result.get("format") or {}
    label = _display(fmt.get("preferred_name") or fmt.get("format_name") or fmt.get("name") or fmt.get("label") or fmt.get("canonical_id"), "Format")
    identifiers = fmt.get("identifiers") or {}
    puids = identifiers.get("puid") if isinstance(identifiers, dict) else None
    if not puids:
        puids = fmt.get("puids") or []
    puid = puids[0] if isinstance(puids, list) and puids else None
    heading = label + (f" — {puid}" if puid and str(puid) not in label else "")

    governed = result.get("governed_synthesis") or {}
    expert = result.get("ai_expert_synthesized_risk") or {}
    context = result.get("external_risk_context") or {}
    lines = [heading, ""]

    lines.extend([
        "Governed preservation risk",
        _display(governed.get("semantic_label"), "Not assessed"),
    ])
    if governed.get("method"):
        lines.append(f"Method: {str(governed.get('method')).replace('_', ' ')}")

    assessments = [row for row in context.get("assessments") or [] if isinstance(row, dict)]
    if assessments:
        lines.extend(["", "Governed source assessments"])
        for row in assessments:
            source = _display(row.get("source_label") or row.get("source_id"), "Source")
            native = _display(row.get("native_label"), "No native overall rating")
            semantic = _display(row.get("semantic_label") or row.get("semantic_level"), "Unmapped")
            scope = _display(row.get("scope_type"), "unspecified").replace("_", " ")
            scope_name = row.get("scope_name")
            lines.append(source)
            lines.append(f"  Native assessment: {native}")
            lines.append(f"  Mapped semantic risk: {semantic}")
            lines.append(f"  Scope: {scope}" + (f" — {scope_name}" if scope_name else ""))

    lines.extend(["", "AI expert preservation risk"])
    if expert.get("assessed"):
        lines.append(_display(expert.get("semantic_label")))
        try:
            lines.append(f"Confidence: {float(expert.get('confidence')):.2f}")
        except (TypeError, ValueError):
            pass
    else:
        lines.append("Not assessed")

    comparison = expert.get("comparison_to_governed") or {}
    if comparison.get("relation"):
        lines.append(f"Comparison with governed result: {str(comparison['relation']).replace('_', ' ')}")
    if expert.get("rationale"):
        lines.extend(["", "AI rationale", str(expert["rationale"])])
    if expert.get("divergence_explanation"):
        lines.append(f"Divergence explanation: {expert['divergence_explanation']}")

    findings = [row for row in expert.get("model_knowledge_findings") or [] if isinstance(row, dict)]
    if findings:
        lines.extend(["", "Broader model-knowledge findings"])
        for row in findings:
            lines.append(
                f"- {row.get('finding')} "
                f"[{str(row.get('risk_effect') or 'uncertain').replace('_', ' ')}, "
                f"confidence {float(row.get('confidence') or 0):.2f}, "
                f"temporal sensitivity {row.get('temporal_sensitivity') or 'unknown'}]"
            )

    refs = expert.get("database_evidence_refs") or []
    if refs:
        lines.extend(["", "Database evidence used", ", ".join(str(value) for value in refs)])
    if expert.get("uncertainty"):
        lines.extend(["", "Uncertainty", str(expert["uncertainty"])])

    lines.extend([
        "",
        "Knowledge boundary",
        str(expert.get("currentness_caveat") or "The AI expert result is advisory and is not live web verified."),
        "The governed config-driven result remains the auditable institutional assessment; the AI expert result is a parallel advisory opinion.",
    ])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="preservation_risk_manager expert-synthesize",
        description=(
            "Produce a parallel AI expert preservation-risk assessment using registry evidence, the configured "
            "synthesis policy, and broader model-trained knowledge. The governed result is never overwritten."
        ),
    )
    parser.add_argument("--format", required=True, help="Canonical ID, PUID, authority ID, name, MIME, or extension.")
    parser.add_argument("--framework", required=True, help="Path to the QNL risk-question framework JSON.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--storage-config", help="Registry-builder storage configuration.")
    source.add_argument("--registry-json", help="Registry JSON export.")
    parser.add_argument("--ai-config", required=True, help="AI provider configuration JSON.")
    parser.add_argument("--max-ai-evidence-items", type=int, default=120)
    parser.add_argument("--json", action="store_true", help="Return canonical JSON rather than human text.")
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    if int(args.max_ai_evidence_items) <= 0:
        raise ValueError("--max-ai-evidence-items must be greater than zero.")
    reader = _reader(args)
    resolution = FormatResolver(reader).resolve(args.format)
    if not resolution.resolved or not resolution.format_doc:
        return {
            "status": resolution.status,
            "resolution": {
                "query": resolution.query,
                "status": resolution.status,
                "match_type": resolution.match_type,
                "matches": resolution.matches,
            },
        }

    format_doc = resolution.format_doc
    try:
        format_doc = enrich_candidate_from_source_records(reader, format_doc)
    except Exception:
        pass
    policy = load_synthesis_policy()
    framework = load_framework(_require_file(args.framework, "Framework"))
    external_context = build_external_risk_context(reader, format_doc)
    governed = external_context.get("policy_synthesized_risk") or external_context.get("registry_synthesized_risk") or {
        "assessed": False,
        "semantic_level": None,
        "semantic_label": None,
    }
    claims = reader.get_criterion_claims_for_format(format_doc)
    source_evidence = build_ai_source_evidence(reader, format_doc, max_source_records=100, max_items=200)
    provider = build_ai_provider(load_ai_config(_require_file(args.ai_config, "AI config")))
    expert_result = synthesize_expert_with_ai(
        provider,
        format_context=format_doc,
        policy=policy,
        governed_synthesis=governed,
        risk_assessments=[dict(row) for row in external_context.get("assessments") or [] if isinstance(row, dict)],
        criterion_claims=[dict(row) for row in claims if isinstance(row, dict)],
        source_evidence=[dict(row) for row in source_evidence if isinstance(row, dict)],
        framework=framework,
        max_evidence_items=int(args.max_ai_evidence_items),
    )
    return {
        "status": "ok",
        "format": format_doc,
        "governed_synthesis": governed,
        "external_risk_context": external_context,
        "ai_expert_synthesized_risk": expert_result["ai_expert_synthesized_risk"],
        "ai_expert": expert_result,
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run(args)
    except Exception as exc:
        if getattr(args, "json", False):
            print(json.dumps({"status": "error", "error": str(exc)}, indent=2, sort_keys=True))
        else:
            print(f"The expert synthesis could not be completed: {exc}")
        return 2
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
    else:
        print(_human(result))
    return 0
