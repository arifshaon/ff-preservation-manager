from __future__ import annotations

from preservation_risk_manager.ai.base import (
    AIProvider,
    AIProviderCapabilities,
    AIRequest,
    AIResponse,
    AIUsage,
)
from preservation_risk_manager.ai.request_router import route_natural_language_request
from preservation_risk_manager.format_resolver import resolve_format


class FakeRouterProvider(AIProvider):
    provider_name = "fake"
    capabilities = AIProviderCapabilities(structured_output=True)

    def __init__(self, structured):
        self.structured = structured

    @property
    def model_name(self) -> str:
        return "fake-router"

    def generate(self, request: AIRequest) -> AIResponse:
        return AIResponse(
            provider=self.provider_name,
            model=self.model_name,
            structured=self.structured,
            usage=AIUsage(input_tokens=10, output_tokens=5, total_tokens=15),
        )


def test_pdf_human_name_is_not_treated_as_generic_authority_identifier():
    formats = [
        {
            "canonical_id": "fmt-pdf",
            "preferred_name": "PDF",
            "identifiers": {"puid": ["fmt/18"], "extension": ["pdf"]},
        },
        {
            "canonical_id": "puid-fmt-14",
            "preferred_name": "Acrobat PDF 1.0 - Portable Document Format",
            "identifier_claims": [
                {"kind": "extension", "value": "PDF", "verified": False}
            ],
        },
        {
            "canonical_id": "nara-nf00362",
            "preferred_name": "Portable Document Format (PDF) version 1.0",
            "identifier_claims": [
                {"kind": "extension", "value": "PDF", "verified": False}
            ],
        },
    ]

    result = resolve_format("PDF", formats)

    assert result.resolved
    assert result.match_type == "name"
    assert result.format_doc["canonical_id"] == "fmt-pdf"


def test_verified_authority_identifier_still_beats_name_after_filtering_claim_kinds():
    formats = [
        {
            "canonical_id": "fmt-friendly-name",
            "preferred_name": "fmt/18",
        },
        {
            "canonical_id": "puid-fmt-18",
            "preferred_name": "Acrobat PDF 1.4 - Portable Document Format",
            "identifier_claims": [
                {"kind": "puid", "value": "fmt/18", "verified": True}
            ],
        },
    ]

    result = resolve_format("fmt/18", formats)

    assert result.resolved
    assert result.match_type == "verified_authority_identifier"
    assert result.format_doc["canonical_id"] == "puid-fmt-18"


def test_router_repairs_at_risk_family_misrouted_as_search_formats():
    provider = FakeRouterProvider({
        "action": "search_formats",
        "format": None,
        "query": None,
        "filters": {
            "family": "PDF",
            "risk_bands": ["Moderate", "High"],
        },
        "scope": "global",
        "institution_id": None,
        "limit": 500,
    })

    routed = route_natural_language_request(
        provider,
        "Give me the PDF formats that are at risk",
        default_limit=500,
    )

    assert routed["request"]["action"] == "list_at_risk_formats"
    assert routed["request"]["filters"]["family"] == "PDF"
    assert routed["request"]["filters"]["risk_bands"] == ["Moderate", "High"]
    assert routed["request"]["query"] is None
    assert "search_formats_with_family_and_risk_bands->list_at_risk_formats" in routed["router"]["repairs"]


def test_router_repairs_discovery_family_without_query():
    provider = FakeRouterProvider({
        "action": "search_formats",
        "format": None,
        "query": None,
        "filters": {
            "family": "PDF",
            "risk_bands": [],
        },
        "scope": "global",
        "institution_id": None,
        "limit": 100,
    })

    routed = route_natural_language_request(provider, "Find PDF formats")

    assert routed["request"]["action"] == "search_formats"
    assert routed["request"]["query"] == "PDF"
    assert "search_formats.query<-filters.family" in routed["router"]["repairs"]
