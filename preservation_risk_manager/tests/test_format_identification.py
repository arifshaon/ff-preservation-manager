from preservation_risk_manager.ai.base import AIProvider, AIProviderCapabilities, AIResponse
from preservation_risk_manager.format_identification import (
    AIFormatIdentificationPlugin,
    IdentificationResolver,
    enrich_candidate_from_source_records,
    normalize_format_observation,
)


class FakeReader:
    def __init__(self, rows, source_records=None):
        self.rows = rows
        self.source_records = list(source_records or [])

    def list_canonical_formats(self):
        return list(self.rows)

    def query(self, collection, filt=None):
        if collection != "source_records":
            return []
        filt = filt or {}
        return [
            row
            for row in self.source_records
            if all(row.get(key) == value for key, value in filt.items())
        ]


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


class FailingProvider(FakeProvider):
    def generate(self, request):
        self.calls.append(request)
        raise RuntimeError("provider unavailable")


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


def _swf_rows():
    return [
        {
            "canonical_id": "puid-fmt-505",
            "preferred_name": "Adobe Flash",
            "identifiers": {"puid": ["fmt/505"], "extension": ["swf"]},
            "source_records": [
                {"source_id": "pronom_registry", "source_record_id": "fmt/505"}
            ],
        },
        {
            "canonical_id": "puid-fmt-506",
            "preferred_name": "Adobe Flash",
            "identifiers": {"puid": ["fmt/506"], "extension": ["swf"]},
            "source_records": [
                {"source_id": "pronom_registry", "source_record_id": "fmt/506"}
            ],
        },
    ]


def _swf_source_records():
    return [
        {
            "source_id": "pronom_registry",
            "source_record_id": "fmt/505",
            "raw": {
                "record": {
                    "formatName": "Adobe Flash",
                    "version": "8",
                    "internalSignatures": [{"name": "SWF 8"}],
                }
            },
        },
        {
            "source_id": "pronom_registry",
            "source_record_id": "fmt/506",
            "raw": {
                "record": {
                    "formatName": "Adobe Flash",
                    "version": "9",
                    "internalSignatures": [{"name": "SWF 9"}],
                }
            },
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
        "candidate_canonical_ids": [],
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
        "candidate_canonical_ids": [],
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
        "candidate_canonical_ids": [],
        "confidence": 0.40,
        "rationale": "uncertain",
    })
    plugin = AIFormatIdentificationPlugin(provider, minimum_confidence=0.80)
    result = IdentificationResolver(FakeReader(_rows()), plugin=plugin).resolve("maybe some old multimedia")
    assert not result.resolved
    assert result.ai_attempted
    assert result.ai_metadata["accepted"] is False


def test_bare_extension_ambiguity_is_not_sent_to_ai():
    provider = FakeProvider({
        "status": "match",
        "candidate_canonical_id": "fmt-pdf-14",
        "candidate_canonical_ids": [],
        "confidence": 0.99,
        "rationale": "would be unsafe",
    })
    plugin = AIFormatIdentificationPlugin(provider)
    result = IdentificationResolver(FakeReader(_rows()), plugin=plugin).resolve(".pdf")
    assert not result.resolved
    assert result.resolution.ambiguous
    assert result.method == "programmatic_ambiguity_requires_review"
    assert result.ai_attempted is False
    assert provider.calls == []


def test_ai_provider_failure_retains_programmatic_result():
    provider = FailingProvider({})
    plugin = AIFormatIdentificationPlugin(provider)
    result = IdentificationResolver(FakeReader(_rows()), plugin=plugin).resolve("old adobe flash movie")
    assert not result.resolved
    assert result.ai_attempted is True
    assert result.method == "ai_fallback_error_programmatic_result_retained"
    assert result.ai_metadata["accepted"] is False
    assert result.ai_metadata["error_type"] == "RuntimeError"


def test_candidate_is_enriched_with_authoritative_source_record_version():
    reader = FakeReader(_swf_rows(), _swf_source_records())
    enriched = enrich_candidate_from_source_records(reader, _swf_rows()[0])

    assert enriched["version"] == "8"
    assert enriched["internal_signature_names"] == ["SWF 8"]
    assert enriched["identification_source_details"][0]["source_record_id"] == "fmt/505"


def test_ai_can_report_version_ambiguity_instead_of_not_found():
    provider = FakeProvider({
        "status": "ambiguous",
        "candidate_canonical_id": "",
        "candidate_canonical_ids": ["puid-fmt-505", "puid-fmt-506"],
        "confidence": 0.95,
        "rationale": "The input identifies SWF but does not specify version 8 or 9.",
    })
    reader = FakeReader(_swf_rows(), _swf_source_records())
    plugin = AIFormatIdentificationPlugin(provider, minimum_confidence=0.80)

    result = IdentificationResolver(reader, plugin=plugin).resolve("Adobe Shockwave Flash SWF file")

    assert not result.resolved
    assert result.resolution.ambiguous
    assert result.method == "ai_fallback_ambiguous"
    assert result.resolution.match_type == "ai_candidate_ambiguity"
    assert {row["version"] for row in result.resolution.matches} == {"8", "9"}
    assert result.ai_metadata["status"] == "ambiguous"
