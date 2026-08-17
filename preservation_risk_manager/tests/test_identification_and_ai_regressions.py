from argparse import Namespace
import string

import pytest

from preservation_risk_manager.ai.base import AIProvider, AIProviderCapabilities, AIResponse
from preservation_risk_manager.format_identification import (
    AIFormatIdentificationPlugin,
    IdentificationResolver,
    _fuzzy_score,
    normalize_format_observation,
    shortlist_candidates,
)
from preservation_risk_manager.human_renderer import render_human_response
from preservation_risk_manager.integration_cli import (
    _apply_ai_risk_assessment,
    _query_json,
)
from preservation_risk_manager.request_api import RequestValidationError


class FakeReader:
    def __init__(self, rows):
        self.rows = list(rows)

    def list_canonical_formats(self):
        return list(self.rows)

    def query(self, collection, filt=None):
        return []


class FakeProvider(AIProvider):
    provider_name = "fake"
    capabilities = AIProviderCapabilities(structured_output=True)

    def __init__(self):
        self.calls = []

    @property
    def model_name(self):
        return "fake-model"

    def generate(self, request):
        self.calls.append(request)
        return AIResponse(
            provider=self.provider_name,
            model=self.model_name,
            structured={
                "status": "no_match",
                "candidate_canonical_id": "",
                "candidate_canonical_ids": [],
                "confidence": 0.0,
                "rationale": "unused",
            },
        )


def test_descriptive_shortlist_survives_many_one_character_extensions():
    query = "an old adobe animation movie file from a floppy disk"
    junk_rows = [
        {
            "canonical_id": f"fmt-{letter}",
            "preferred_name": letter.upper(),
            "extensions": [letter],
        }
        for letter in string.ascii_lowercase
    ]
    swf = {
        "canonical_id": "fmt-swf",
        "preferred_name": "Shockwave Flash",
        "extensions": ["swf"],
    }

    assert _fuzzy_score(query, swf) < 0.25
    assert all(_fuzzy_score(query, row) < 0.88 for row in junk_rows)

    shortlist = shortlist_candidates(query, junk_rows + [swf], limit=20)
    ids = [row["canonical_id"] for row in shortlist]
    assert "fmt-swf" in ids


def test_wrapped_puids_resolve_deterministically_without_ai_call():
    rows = [
        {
            "canonical_id": "fmt-pdf-14",
            "preferred_name": "PDF 1.4",
            "identifiers": {"puid": ["fmt/18"]},
        },
        {
            "canonical_id": "fmt-legacy",
            "preferred_name": "Legacy format",
            "identifiers": {"puid": ["x-fmt/123"]},
        },
    ]
    provider = FakeProvider()
    plugin = AIFormatIdentificationPlugin(provider)
    resolver = IdentificationResolver(FakeReader(rows), plugin=plugin)

    first = resolver.resolve("[fmt 18]")
    second = resolver.resolve('"x-fmt 123"')

    assert normalize_format_observation("[fmt 18]")[0] == "fmt/18"
    assert normalize_format_observation('"x-fmt 123"')[0] == "x-fmt/123"
    assert first.resolved and first.method == "deterministic_normalization"
    assert second.resolved and second.method == "deterministic_normalization"
    assert provider.calls == []


def test_human_renderer_discloses_ai_identification_and_risk_mode():
    response = {
        "status": "ok",
        "request": {"action": "assess_format"},
        "result": {
            "format": {"format_id": "fmt-swf", "label": "Shockwave Flash"},
            "risk_band": None,
            "banding_enabled": True,
            "band_suppressed_reason": "insufficient_evidence_completeness",
            "score": 4,
            "max_score": 18,
            "analysis_status": "Partially Assessed",
            "evidence_completeness": 0.67,
            "missing_count": 1,
            "abstention_count": 1,
            "main_risk_factors": [],
        },
        "identification": {
            "method": "ai_fallback",
            "status": "resolved",
            "ai_attempted": True,
            "resolved_canonical_id": "fmt-swf",
            "resolved_label": "Shockwave Flash",
            "ai": {
                "status": "match",
                "accepted": True,
                "confidence": 0.83,
                "rationale": "Best supplied local candidate.",
            },
        },
        "ai_risk_assessment": {
            "status": "ok",
            "ai_mode": "fill-gaps",
            "provider": "fake/fake-model",
            "analysis": {
                "analysed_band": "Moderate",
                "score": 10,
                "max_score": 18,
                "analysis_status": "Assessed",
                "evidence_completeness": 1.0,
            },
            "derived_answers": {
                "ai_summary": {
                    "accepted_answers": 2,
                    "abstentions": 0,
                    "failed_questions": 0,
                }
            },
            "authority_boundary": "AI cannot replace deterministically resolved answers.",
        },
    }

    rendered = render_human_response(response)

    assert "ai_fallback" in rendered
    assert "0.83" in rendered
    assert "AI-assisted format identification" in rendered
    assert "AI-assisted risk interpretation" in rendered
    assert "fill-gaps" in rendered
    assert "authority" in rendered.lower()


def test_whitespace_around_action_does_not_disable_ai_gate():
    response = _apply_ai_risk_assessment(
        FakeReader([]),
        None,
        {"action": " assess_format ", "format": "missing"},
        {"status": "ok"},
        provider=None,
        ai_mode="fill-gaps",
        max_evidence_items=20,
    )

    assert response["ai_risk_assessment"]["status"] == "not_run"
    assert response["ai_risk_assessment"]["reason"] == "canonical_format_not_resolved"


def test_invalid_ai_evidence_limit_fails_before_reader_or_execution(monkeypatch):
    def should_not_open_reader(_args):
        pytest.fail("reader should not be opened for an invalid AI evidence limit")

    monkeypatch.setattr(
        "preservation_risk_manager.integration_cli._reader_from_args",
        should_not_open_reader,
    )
    args = Namespace(
        max_ai_evidence_items=0,
        identification_ai_min_confidence=0.80,
    )

    with pytest.raises(RequestValidationError, match="greater than zero"):
        _query_json(args)
