from __future__ import annotations

import json
import re
import sys
from typing import Any

from preservation_risk_manager import integration_cli as base
from preservation_risk_manager.ai.base import AIProviderError
from preservation_risk_manager.ai.batch_risk_analysis import apply_batched_fill_gaps
from preservation_risk_manager.format_identification import IdentificationResolver
from preservation_risk_manager.human_format_matches import human_puid_candidates
from preservation_risk_manager.human_renderer_multi import render_human_response
from preservation_risk_manager.request_api import normalize_request


_RATE_LIMIT_REASON = "provider_rate_limit_circuit_open"
_SIMPLE_RISK_QUERY = re.compile(
    r"^\s*(?:(?:what(?:'s|\s+is)?|tell\s+me)\s+)?(?:the\s+)?(?:preservation\s+)?risk\s+(?:of|for)\s+(.+?)\s*\??\s*$",
    re.IGNORECASE,
)


def _is_rate_limit_error(exc: BaseException) -> bool:
    text = str(exc or "").lower()
    return "429" in text or "too many requests" in text or "rate limit" in text or "ratelimit" in text


class _RateLimitCircuitProvider:
    """Stop network AI calls after the first provider rate-limit response."""

    def __init__(self, delegate) -> None:
        self.delegate = delegate
        self.rate_limited = False
        self.rate_limit_error: str | None = None

    @property
    def model_name(self):
        return self.delegate.model_name

    @property
    def provider_name(self):
        return getattr(self.delegate, "provider_name", "unknown")

    @property
    def capabilities(self):
        return getattr(self.delegate, "capabilities", None)

    def describe(self):
        return self.delegate.describe()

    def generate(self, request):
        if self.rate_limited:
            raise AIProviderError("AI rate-limit circuit is open for this human request.")
        try:
            return self.delegate.generate(request)
        except AIProviderError as exc:
            if _is_rate_limit_error(exc):
                self.rate_limited = True
                self.rate_limit_error = "429 Too Many Requests"
            raise


def _programmatic_simple_risk_route(
    prompt: str,
    *,
    default_scope: str,
    default_institution_id: str | None,
    default_limit: int,
) -> dict[str, Any] | None:
    """Route only obvious ``risk of <format>`` questions without an AI router call."""
    match = _SIMPLE_RISK_QUERY.fullmatch(str(prompt or ""))
    if not match:
        return None
    format_value = match.group(1).strip().strip(". ")
    if not format_value:
        return None
    raw_request = {
        "action": "assess_format",
        "format": format_value,
        "query": None,
        "filters": {
            "family": None,
            "risk_bands": [],
            "domains": [],
            "question_ids": [],
            "content_type": None,
        },
        "scope": default_scope,
        "institution_id": default_institution_id if default_scope == "institution" else None,
        "limit": default_limit,
    }
    return {
        "request": normalize_request(raw_request),
        "router": {
            "provider": "programmatic",
            "model": None,
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "repairs": [],
            "raw_request": raw_request,
            "method": "programmatic_simple_risk_query",
        },
    }


def _match_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_id": row.get("canonical_id") or row.get("format_id") or row.get("id"),
        "label": row.get("preferred_name") or row.get("format_name") or row.get("name") or row.get("label"),
        "version": row.get("version"),
        "identifiers": row.get("identifiers") if isinstance(row.get("identifiers"), dict) else {},
        "puids": row.get("puids") or [],
    }


def _resolve_human_request_format(reader, request: dict[str, Any], *, plugin=None):
    """Resolve once while retaining all local matches needed for human fan-out."""
    prepared = dict(request)
    raw_format = prepared.get("format")
    if raw_format is None or not str(raw_format).strip():
        return prepared, None

    identification = IdentificationResolver(reader, plugin=plugin).resolve(str(raw_format))
    metadata = identification.to_dict()
    if identification.resolution.matches:
        metadata["matched_candidates"] = [_match_summary(row) for row in identification.resolution.matches]

    if identification.resolved and identification.resolution.format_doc:
        row = identification.resolution.format_doc
        canonical_id = row.get("canonical_id") or row.get("format_id") or row.get("id")
        if canonical_id:
            prepared["format"] = str(canonical_id)
            metadata["resolved_canonical_id"] = str(canonical_id)
            metadata["resolved_label"] = (
                row.get("preferred_name") or row.get("format_name") or row.get("name") or row.get("label")
            )
            if row.get("version") is not None:
                metadata["resolved_version"] = str(row.get("version"))
    else:
        metadata = base._promote_version_ambiguity(metadata)
    return prepared, metadata


def _skipped_rate_limit_assessment(provider, *, ai_mode: str) -> dict[str, Any]:
    return {
        "status": "skipped_rate_limited",
        "ai_mode": ai_mode,
        "provider": provider.describe(),
        "reason": _RATE_LIMIT_REASON,
        "error": getattr(provider, "rate_limit_error", None) or "429 Too Many Requests",
        "authority_boundary": (
            "AI interpretation was skipped after the provider rate limit was reached; "
            "the deterministic assessment was retained unchanged."
        ),
    }


def _assess_human_puid_matches(
    reader,
    framework,
    request: dict[str, Any],
    identification: dict[str, Any] | None,
    *,
    provider,
    ai_mode: str,
    max_evidence_items: int,
    user_question: str = "",
    human_format_assessment_limit: int = 10,
) -> dict[str, Any] | None:
    """Assess only the configured number of distinct PUID matches for a human query.

    Broad human terms such as PDF can match dozens of PRONOM records. The
    configured limit is therefore applied immediately after local identification,
    before any deterministic or AI risk work. Matches beyond the limit are
    reported for audit but are not assessed at all.
    """
    all_candidates = human_puid_candidates(reader, request, identification)
    if not all_candidates:
        return None

    matched_total = len(all_candidates)
    configured_limit = max(1, int(human_format_assessment_limit))
    limit_applied = matched_total > configured_limit
    candidates = all_candidates[:configured_limit]
    unassessed_candidates = all_candidates[configured_limit:]
    assessed_total = len(candidates)

    if limit_applied:
        print(
            f"[human-risk] {matched_total} matching PUIDs found. The configured human assessment limit is "
            f"{configured_limit}; only the first {assessed_total} will be assessed. "
            f"The remaining {len(unassessed_candidates)} will not be assessed.",
            file=sys.stderr,
            flush=True,
        )

    assessments: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates, start=1):
        if assessed_total > 1:
            print(
                f"[human-risk] Assessment {index}/{assessed_total}: {candidate['puid']} {candidate.get('label') or ''}".rstrip(),
                file=sys.stderr,
                flush=True,
            )
        candidate_request = dict(request)
        candidate_request["format"] = candidate["canonical_id"]
        subresponse = base.execute_request(reader, framework, candidate_request)
        subresponse["matched_puid"] = candidate["puid"]
        subresponse["matched_label"] = candidate.get("label")
        subresponse["matched_version"] = candidate.get("version")
        assessments.append(subresponse)

    batch_meta: dict[str, Any] | None = None
    if ai_mode == "fill-gaps" and len(candidates) > 1:
        print(
            f"[human-risk] AI fill-gaps will assess these {len(candidates)} PUIDs.",
            file=sys.stderr,
            flush=True,
        )
        batch_meta = apply_batched_fill_gaps(
            provider,
            reader,
            framework,
            request,
            candidates,
            assessments,
            user_question=user_question or str(request.get("format") or ""),
            max_evidence_items=max_evidence_items,
            max_puids_per_call=8,
            progress=lambda message: print(f"[human-risk] {message}", file=sys.stderr, flush=True),
        )
        if bool(getattr(provider, "rate_limited", False)):
            print(
                "[human-risk] Azure/OpenAI rate limit reached. No further AI calls will be made; "
                "the deterministic results for the selected PUIDs are retained.",
                file=sys.stderr,
                flush=True,
            )
    elif ai_mode != "off" and candidates:
        reported_rate_limit = False
        for candidate, subresponse in zip(candidates, assessments):
            candidate_request = dict(request)
            candidate_request["format"] = candidate["canonical_id"]
            if bool(getattr(provider, "rate_limited", False)):
                subresponse["ai_risk_assessment"] = _skipped_rate_limit_assessment(provider, ai_mode=ai_mode)
            else:
                base._apply_ai_risk_assessment(
                    reader,
                    framework,
                    candidate_request,
                    subresponse,
                    provider=provider,
                    ai_mode=ai_mode,
                    max_evidence_items=max_evidence_items,
                )
            if bool(getattr(provider, "rate_limited", False)) and not reported_rate_limit:
                print(
                    "[human-risk] Azure/OpenAI rate limit reached. AI calls are disabled for the rest of this request; "
                    "the deterministic results for the selected PUIDs are retained.",
                    file=sys.stderr,
                    flush=True,
                )
                reported_rate_limit = True

    if matched_total == 1:
        return assessments[0]

    return {
        "status": "ok",
        "request": dict(request),
        "framework": {
            "framework_id": framework.framework_id,
            "version": framework.version,
            "calibration_status": framework.calibration_status,
            "banding_enabled": framework.banding_enabled,
        },
        "scope": request.get("scope", "global"),
        "institution_id": request.get("institution_id"),
        "human_multi_puid_assessment": True,
        "matched_puid_count": matched_total,
        "matched_puids": [candidate["puid"] for candidate in all_candidates],
        "assessed_puid_count": assessed_total,
        "assessed_puids": [candidate["puid"] for candidate in candidates],
        "unassessed_puid_count": len(unassessed_candidates),
        "unassessed_puids": [candidate["puid"] for candidate in unassessed_candidates],
        "human_format_assessment_limit": configured_limit,
        "human_format_assessment_limit_applied": limit_applied,
        "ai_rate_limited": bool(getattr(provider, "rate_limited", False)),
        "ai_batch": batch_meta,
        "assessments": assessments,
    }


def _ask(args) -> dict[str, Any]:
    max_items = base._validate_ai_options(args)
    reader = base._reader_from_args(args)
    framework = base.load_framework(base._require_file(args.framework, label="Framework file"))
    config = base.load_ai_config(base._require_file(args.ai_config, label="AI config file"))
    raw_provider = base.build_ai_provider(config)
    provider = _RateLimitCircuitProvider(raw_provider)
    default_scope = "institution" if args.institution else "global"

    routed = _programmatic_simple_risk_route(
        args.question,
        default_scope=default_scope,
        default_institution_id=args.institution,
        default_limit=args.limit,
    )
    if routed is None:
        routed = base.route_natural_language_request(
            provider,
            args.question,
            framework=framework,
            default_scope=default_scope,
            default_institution_id=args.institution,
            default_limit=args.limit,
        )

    routed_request = normalize_request(routed["request"])
    plugin = base._identification_plugin(args, existing_provider=provider)
    prepared_request, identification = _resolve_human_request_format(reader, routed_request, plugin=plugin)

    response = _assess_human_puid_matches(
        reader,
        framework,
        routed_request,
        identification,
        provider=provider,
        ai_mode=args.ai_mode,
        max_evidence_items=max_items,
        user_question=args.question,
        human_format_assessment_limit=config.human_format_assessment_limit,
    )
    if response is None:
        response = base._identification_ambiguity_response(framework, routed_request, identification)
    if response is None:
        response = base.execute_request(reader, framework, prepared_request)
        ai_mode = str(args.ai_mode or "off")
        if ai_mode != "off" and provider.rate_limited:
            response["ai_risk_assessment"] = _skipped_rate_limit_assessment(provider, ai_mode=ai_mode)
        else:
            response = base._apply_ai_risk_assessment(
                reader,
                framework,
                prepared_request,
                response,
                provider=provider,
                ai_mode=ai_mode,
                max_evidence_items=max_items,
            )

    response["input"] = {"mode": "human_prompt", "prompt": args.question}
    response["router"] = routed["router"]
    if identification is not None:
        response["identification"] = identification
    return response


def main(argv: list[str] | None = None) -> int:
    parser = base._build_parser()
    args = parser.parse_args(argv)
    try:
        result = _ask(args) if args.command == "ask" else base._query_json(args)
    except Exception as exc:
        error = {"status": "error", "error": str(exc)}
        if args.command == "query-json" or getattr(args, "json", False):
            print(json.dumps(error, indent=2, sort_keys=True))
        else:
            print(f"The request could not be completed: {exc}")
        return 2

    if args.command == "ask" and not args.json:
        print(render_human_response(result))
    else:
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0
