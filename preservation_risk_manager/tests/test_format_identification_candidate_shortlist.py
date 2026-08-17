from __future__ import annotations

from preservation_risk_manager.ai.base import AIProvider, AIProviderCapabilities, AIResponse
from preservation_risk_manager.format_identification import (
    AIFormatIdentificationPlugin,
    IdentificationResolver,
    shortlist_candidates,
)


class FakeReader:
    def __init__(self, rows):
        self.rows = rows

    def list_canonical_formats(self):
        return list(self.rows)


class AbstainingProvider(AIProvider):
    provider_name = "fake"
    capabilities = AIProviderCapabilities(structured_output=True)

    @property
    def model_name(self):
        return "fake-model"

    def generate(self, request):
        return AIResponse(
            provider=self.provider_name,
            model=self.model_name,
            structured={
                "status": "abstain",
                "candidate_canonical_id": "",
                "confidence": 0.0,
                "rationale": "Multiple versions remain plausible.",
            },
        )


def _rows():
    return [
        {
            "canonical_id": "fmt-swf-v1",
            "preferred_name": "Shockwave Flash 1",
            "identifiers": {"puid": ["fmt/9991"]},
            "extensions": ["swf"],
        },
        {
            "canonical_id": "fmt-swf-v2",
            "preferred_name": "Shockwave Flash 2",
            "identifiers": {"puid": ["fmt/9992"]},
            "extensions": ["swf"],
        },
        {
            "canonical_id": "fmt-pdf",
            "preferred_name": "PDF 1.7",
            "identifiers": {"puid": ["fmt/276"]},
            "extensions": ["pdf"],
        },
    ]


def test_swf_token_keeps_swf_records_in_candidate_shortlist():
    candidates = shortlist_candidates("Adobe Shockwave Flash SWF file", _rows(), limit=20)
    ids = [row["canonical_id"] for row in candidates]
    assert "fmt-swf-v1" in ids
    assert "fmt-swf-v2" in ids


def test_ai_abstention_reports_candidate_shortlist_for_audit():
    plugin = AIFormatIdentificationPlugin(AbstainingProvider())
    result = IdentificationResolver(FakeReader(_rows()), plugin=plugin).resolve(
        "Adobe Shockwave Flash SWF file"
    )
    assert result.ai_attempted is True
    assert result.ai_metadata["accepted"] is False
    assert result.ai_metadata["candidate_count"] >= 2
    ids = [row["canonical_id"] for row in result.ai_metadata["candidates"]]
    assert "fmt-swf-v1" in ids
    assert "fmt-swf-v2" in ids
