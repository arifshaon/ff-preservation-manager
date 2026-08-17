from __future__ import annotations

import json
import sys
from typing import Any

from preservation_risk_manager import integration_cli as base
from preservation_risk_manager.ai.base import AIProviderError
from preservation_risk_manager.format_identification import IdentificationResolver
from preservation_risk_manager.human_format_matches import human_puid_candidates
from preservation_risk_manager.human_renderer_multi import render_human_response
from preservation_risk_manager.request_api import normalize_request


_RATE_LIMIT_REASON = "provider_rate_limit_circuit_open"


def _is_rate_limit_error(exc: BaseException) -> bool:
    text = str(exc or "").lower()
    return (
        "429" in text
        or "too many requests" in text
        or "rate limit" in text
        or "ratelimit" in text
    )


class _RateLimitCircuitProvider:
    """Stop network AI calls after the first provider rate-limit response.

    The underlying provider remains responsible for normal request/response
    handling. This wrapper is scoped to one human CLI request. Once a 429-like
    provider error is observed, subsequent AI calls fail locally and immediately,
    allowing deterministic assessments to continue for every matched PUID.
    """

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
) -> dict[str, Any] | None:
    """Assess every distinct PUID matched by a human-format observation.

    Deterministic assessment is never abandoned because AI is throttled. Once a
    provider 429 is seen, the per-request AI circuit opens and the remaining PUIDs
    are assessed deterministically with an explicit AI-skipped audit marker.
    """
    candidates = human_puid_candidates(reader, request, identification)
    if not candidates:
        return None

    assessments: list[dict[str, Any]] = []
    reported_rate_limit = False
    total = len(candidates)
    for index, candidate in enumerate(candidates, start=1):
        if total > 1:
            print(
                f"[human-risk] Assessing {index}/{total}: {candidate['puid']} {candidate.get('label') or ''}".rstrip(),
                file=sys.stderr,
                flush=True,
            )

        candidate_request = dict(request)
        candidate_request["format"] = candidate["canonical_id"]
        subresponse = base.execute_request(reader, framework, candidate_request)

        if ai_mode != "off":
            if bool(getattr(provider, "rate_limited", False)):
                subresponse["ai_risk_assessment"] = _skipped_rate_limit_assessment(
                    provider,
                    ai_mode=ai_mode,
                )
            else:
                subresponse = base._apply_ai_risk_assessment(
                    reader,
                    framework,
                    candidate_request,
                    subresponse,
                    provider=provider,
                    ai_mode=ai_mode,
                    max_evidence_items=max_evidence_items,
                )
                if bool(getattr(provider, "rate_limited", False)):
                    ai_result = subresponse.setdefault("ai_risk_assessment", {})
                    ai_result["status"] = "partial_rate_limited"
                    ai_result["reason"] = _RATE_LIMIT_REASON
                    ai_result["rate_limit_error"] = (
                        getattr(provider, "rate_limit_error", None) or "429 Too Many Requests"
                    )
                    ai_result.setdefault(
                        "authority_boundary",
                        "AI interpretation was interrupted by a provider rate limit; deterministic results were retained.",
                    )

            if bool(getattr(provider, "rate_limited", False)) and not reported_rate_limit:
                print(
                    "[human-risk] Azure/OpenAI rate limit reached. AI calls are disabled for the rest of this "
                    "request; deterministic assessments will continue for all remaining PUIDs.",
                    file=sys.stderr,
                    flush=True,
                )
                reported_rate_limit = True

        subresponse["matched_puid"] = candidate["puid"]
        subresponse["matched_label"] = candidate.get("label")
        subresponse["matched_version"] = candidate.get("version")
        assessments.append(subresponse)

    if len(assessments) == 1:
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
        "matched_puid_count": len(assessments),
        "matched_puids": [item["matched_puid"] for item in assessments],
        "ai_rate_limited": bool(getattr(provider, "rate_limited", False)),
        "assessments": assessments,
    }


def _ask(args) -> dict[str, Any]:
    max_items = base._validate_ai_options(args)
    reader = base._reader_from_args(args)
    framework = base.load_framework(base._require_file(args.framework, label="Framework file"))
    config = base.load_ai_config(base._require_file(args.ai_config, label="AI config file"))
    raw_provider = base.build_ai_provider(config)
    default_scope = "institution" if args.institution else "global"
    routed = base.route_natural_language_request(
        raw_provider,
        args.question,
        framework=framework,
        default_scope=default_scope,
        default_institution_id=args.institution,
        default_limit=args.limit,
    )
    provider = _RateLimitCircuitProvider(raw_provider)
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
    )
    if response is None:
        response = base._identification_ambiguity_response(framework, routed_request, identification)
    if response is None:
        response = base.execute_request(reader, framework, prepared_request)
        if ai_mode := str(args.ai_mode or "off"):
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
