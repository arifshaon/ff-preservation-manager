from __future__ import annotations

from preservation_risk_manager.ai.base import AIProvider, AIProviderCapabilities, AIResponse
from preservation_risk_manager.format_identification import (
    AIFormatIdentificationPlugin,
    IdentificationResolver,
    normalize_format_observation,
)


class FakeReader:
    def __init__(self, rows):
        self.rows = rows

    def list_canonical_formats(self):
        return list(self.rows)


class FakeProvider(AIProvider):
    provider_name = "fake"
    capabilities = AIProviderCapabilities(structured_output=True)

    def __init__(self, decision):
        self.decision = decision
        self.calls = []

    @property
    def model_name(self):
        return "fake-model"

    def generate(self, request):
        self.calls.append(request)
        return AIResponse(
            provider=self.provider_name,
            model=self.model_name,
            structured=self.decision,
        )


def _rows():
    return [
        {
            "canonical_id": "fmt-pdf-14",
            "preferred_name": "PDF 1.4",
            "identifiers": {"puid": ["fmt/18"], "mime": ["application/pdf"]},
            "extensions": ["pdf"],
        },
        {
            "canonical_id": "fmt-pdf-17",
            "preferred_name": "PDF 1.7",
            "identifiers": {"puid": ["fmt/276"], "mime": ["application/pdf"]},
            "extensions": ["pdf"],
        },
        {
            "canonical_id": "fmt-swf",
            "preferred_name": "Adobe Flash SWF",
            "identifiers": {"puid": ["fmt/505"]},
            "extensions": ["swf"],
        },
    ]


def test_programmatic_puid_normalization():
    assert normalize_format_observation("PRONOM fmt 18") == ["fmt/18"]
    result = IdentificationResolver(FakeReader(_rows())).resolve("PRONOM fmt 18")
    assert result.resolved
    assert result.method == "deterministic_normalization"
    assert result.normalized_value == "fmt/18"
    assert result.resolution.format_doc["canonical_id"] == "fmt-pdf-14"


def test_ai_is_not_called_for_exact_identifier():
    provider = FakeProvider({
        "status": "match",
        "candidate_canonical_id": "fmt-swf",
        "confidence": 0.99,
        "rationale": "unused",
    })
    plugin = AIFormatIdentificationPlugin(provider)
    result = IdentificationResolver(FakeReader(_rows()), plugin=plugin).resolve("fmt/18")
    assert result.resolved
    assert result.method == "deterministic_exact"
    assert not result.ai_attempted
    assert provider.calls == []


def test_ai_can_choose_only_supplied_local_candidate():
    provider = FakeProvider({
        "status": "match",
        "candidate_canonical_id": "fmt-swf",
        "confidence": 0.93,
        "rationale": "The supplied description clearly refers to Flash/SWF.",
    })
    plugin = AIFormatIdentificationPlugin(provider, minimum_confidence=0.80)
    result = IdentificationResolver(FakeReader(_rows()), plugin=plugin).resolve("old adobe flash movie")
    assert result.resolved
    assert result.method == "ai_fallback"
    assert result.ai_attempted
    assert result.resolution.match_type == "ai_candidate_verified_local"
    assert result.resolution.format_doc["canonical_id"] == "fmt-swf"
    assert result.ai_metadata["accepted"] is True


def test_ai_cannot_invent_candidate_not_in_registry_shortlist():
    provider = FakeProvider({
        "status": "match",
        "candidate_canonical_id": "invented-format",
        "confidence": 0.99,
        "rationale": "invented",
    })
    plugin = AIFormatIdentificationPlugin(provider, minimum_confidence=0.80)
    result = IdentificationResolver(FakeReader(_rows()), plugin=plugin).resolve("old adobe flash movie")
    assert not result.resolved
    assert result.ai_attempted
    assert result.method == "ai_fallback_abstained"
    assert result.ai_metadata["accepted"] is False
    assert result.ai_metadata["reason"] == "candidate_not_in_supplied_registry_set"


def test_low_confidence_ai_match_is_rejected():
    provider = FakeProvider({
        "status": "match",
        "candidate_canonical_id": "fmt-swf",
        "confidence": 0.40,
        "rationale": "uncertain",
    })
    plugin = AIFormatIdentificationPlugin(provider, minimum_confidence=0.80)
    result = IdentificationResolver(FakeReader(_rows()), plugin=plugin).resolve("maybe some old multimedia")
    assert not result.resolved
    assert result.ai_attempted
    assert result.ai_metadata["accepted"] is False
