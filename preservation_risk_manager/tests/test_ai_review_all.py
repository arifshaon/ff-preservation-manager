from __future__ import annotations

from preservation_risk_manager.ai.base import (
    AIProvider,
    AIProviderCapabilities,
    AIRequest,
    AIResponse,
    AIUsage,
)
from preservation_risk_manager.ai.review import review_answers_with_ai
from preservation_risk_manager.answer_derivation import derive_answers
from preservation_risk_manager.frameworks import RiskFramework
from preservation_risk_manager.scoring import score_answers


class FakeReviewProvider(AIProvider):
    provider_name = "fake"
    capabilities = AIProviderCapabilities(structured_output=True)

    def __init__(self, structured_responses):
        self.structured_responses = list(structured_responses)
        self.requests: list[AIRequest] = []

    @property
    def model_name(self) -> str:
        return "fake-review-model"

    def generate(self, request: AIRequest) -> AIResponse:
        self.requests.append(request)
        structured = self.structured_responses.pop(0)
        return AIResponse(
            provider=self.provider_name,
            model=self.model_name,
            structured=structured,
            usage=AIUsage(input_tokens=11, output_tokens=7, total_tokens=18),
        )


def _framework() -> RiskFramework:
    return RiskFramework.from_dict({
        "framework_id": "review_framework",
        "version": "1.0",
        "unknown_answer_id": "unknown",
        "scale": {
            "direction": "higher_is_risk",
            "min_completeness_for_band": 0.5,
            "bands": [
                {"band": "Low", "min_score": 0, "max_score": 2},
                {"band": "High", "min_score": 3, "max_score": 10},
            ],
        },
        "questions": [
            {
                "id": "q_disclosure",
                "label": "Publicly documented?",
                "evidence_fields": ["sustainability.disclosure"],
                "answers": [
                    {"id": "public_specification", "points": 0},
                    {"id": "limited_or_unclear_specification", "points": 3},
                    {"id": "unknown", "points": 1, "abstention": True},
                ],
            },
            {
                "id": "q_adoption",
                "label": "Widely adopted?",
                "evidence_fields": ["sustainability.adoption"],
                "answers": [
                    {"id": "widely_adopted", "points": 0},
                    {"id": "niche_or_declining", "points": 4},
                    {"id": "unknown", "points": 1, "abstention": True},
                ],
            },
        ],
    })


def _evidence_pack():
    return {
        "scope": "global",
        "format": {"format_id": "fmt-test", "label": "Test Format"},
        "global_evidence": [
            {
                "criterion_id": "sustainability.disclosure",
                "answer_id": "public_specification",
                "value": "MAPPED_SENTINEL_DISCLOSURE",
                "source_id": "source-a",
                "source_type": "test-source",
                "source_record_id": "record-a",
                "source_field": "native.disclosure",
                "source_value": "RAW_DISCLOSURE_EVIDENCE: fully documented in a published specification.",
                "mapping_rule_id": "MAPPING_RULE_SENTINEL_DISCLOSURE",
                "mapping_version": "MAPPING_VERSION_SENTINEL",
                "rationale": "MAPPING_RATIONALE_SENTINEL",
                "_storage_key": "STORAGE_KEY_SENTINEL",
            },
            {
                "criterion_id": "sustainability.adoption",
                "answer_id": "widely_adopted",
                "value": "MAPPED_SENTINEL_ADOPTION",
                "source_id": "source-b",
                "source_type": "test-source",
                "source_record_id": "record-b",
                "source_field": "native.adoption",
                "source_value": "RAW_ADOPTION_EVIDENCE: used broadly across multiple implementations.",
                "mapping_rule_id": "MAPPING_RULE_SENTINEL_ADOPTION",
                "mapping_version": "MAPPING_VERSION_SENTINEL",
                "rationale": "MAPPING_RATIONALE_SENTINEL",
                "_storage_key": "STORAGE_KEY_SENTINEL",
            },
        ],
        "migration_pathway_evidence": [],
    }


def test_review_all_records_agreement_and_divergence_without_changing_score():
    framework = _framework()
    evidence_pack = _evidence_pack()
    deterministic = derive_answers(framework, evidence_pack)
    baseline = score_answers(framework, deterministic["scoring_answers"])
    provider = FakeReviewProvider([
        {
            "question_id": "q_disclosure",
            "answer_id": "public_specification",
            "confidence": 0.98,
            "rationale": "The supplied raw evidence indicates public documentation.",
            "evidence_refs": ["E001"],
            "uncertainty": "",
        },
        {
            "question_id": "q_adoption",
            "answer_id": "niche_or_declining",
            "confidence": 0.72,
            "rationale": "Independent review disagrees with the deterministic mapping.",
            "evidence_refs": ["E001"],
            "uncertainty": "The raw evidence is brief.",
        },
    ])

    reviewed = review_answers_with_ai(provider, framework, evidence_pack, deterministic)
    reviewed_score = score_answers(framework, reviewed["scoring_answers"])

    assert len(provider.requests) == 2
    assert reviewed["answers"] == deterministic["answers"]
    assert reviewed["scoring_answers"] == deterministic["scoring_answers"]
    assert reviewed_score["score"] == baseline["score"] == 0
    assert reviewed_score["analysed_band"] == baseline["analysed_band"] == "Low"
    assert reviewed["ai_summary"]["evidence_view"] == "raw_source_only"
    assert reviewed["ai_summary"]["reviewed_questions"] == 2
    assert reviewed["ai_summary"]["agreements"] == 1
    assert reviewed["ai_summary"]["divergences"] == 1
    assert reviewed["ai_audit"]["q_disclosure"]["agreement"] is True
    assert reviewed["ai_audit"]["q_adoption"]["agreement"] is False
    assert reviewed["ai_audit"]["q_adoption"]["deterministic_answer_id"] == "widely_adopted"
    assert reviewed["ai_audit"]["q_adoption"]["answer_id"] == "niche_or_declining"

    # Independence contract: deterministic/mapped outputs are compared only
    # after the model answers. Raw source evidence must be present; normalized
    # values, answer IDs from evidence claims, mapping metadata, storage keys,
    # and mapping rationale must never appear in the model-facing user prompt.
    prompts = [request.messages[1].content or "" for request in provider.requests]
    combined_prompt = "\n".join(prompts)
    assert "RAW_DISCLOSURE_EVIDENCE" in combined_prompt
    assert "RAW_ADOPTION_EVIDENCE" in combined_prompt
    assert "MAPPED_SENTINEL_DISCLOSURE" not in combined_prompt
    assert "MAPPED_SENTINEL_ADOPTION" not in combined_prompt
    assert "MAPPING_RULE_SENTINEL" not in combined_prompt
    assert "MAPPING_VERSION_SENTINEL" not in combined_prompt
    assert "MAPPING_RATIONALE_SENTINEL" not in combined_prompt
    assert "STORAGE_KEY_SENTINEL" not in combined_prompt
    assert '"deterministic_result"' not in combined_prompt
    assert '"deterministic_status"' not in combined_prompt
    assert '"deterministic_answer_id"' not in combined_prompt

    cited = reviewed["ai_audit"]["q_disclosure"]["cited_evidence"][0]
    assert cited["source_value"].startswith("RAW_DISCLOSURE_EVIDENCE")
    assert "value" not in cited
    assert "answer_id" not in cited
    assert "mapping_rule_id" not in cited
    assert "mapping_version" not in cited
    assert "_storage_key" not in cited


def test_review_all_drops_evidence_without_raw_payload():
    framework = _framework()
    evidence_pack = {
        "scope": "global",
        "format": {"format_id": "fmt-mapped-only", "label": "Mapped Only"},
        "global_evidence": [
            {
                "criterion_id": "sustainability.disclosure",
                "answer_id": "public_specification",
                "value": "public_specification",
                "source_id": "source-a",
                "source_record_id": "record-a",
                "mapping_rule_id": "rule-a",
            },
            {
                "criterion_id": "sustainability.adoption",
                "answer_id": "widely_adopted",
                "value": "high",
                "source_id": "source-b",
                "source_record_id": "record-b",
                "mapping_rule_id": "rule-b",
            },
        ],
        "migration_pathway_evidence": [],
    }
    deterministic = derive_answers(framework, evidence_pack)
    provider = FakeReviewProvider([])

    reviewed = review_answers_with_ai(provider, framework, evidence_pack, deterministic)

    assert provider.requests == []
    assert reviewed["answers"] == deterministic["answers"]
    assert reviewed["ai_summary"]["skipped_no_evidence"] == 2
    assert reviewed["ai_summary"]["reviewed_questions"] == 0


def test_review_all_skips_questions_when_evidence_pack_is_empty():
    framework = _framework()
    evidence_pack = {
        "scope": "global",
        "format": {"format_id": "fmt-empty", "label": "Empty Format"},
        "global_evidence": [],
        "migration_pathway_evidence": [],
    }
    deterministic = derive_answers(framework, evidence_pack)
    provider = FakeReviewProvider([])

    reviewed = review_answers_with_ai(provider, framework, evidence_pack, deterministic)

    assert provider.requests == []
    assert reviewed["answers"] == deterministic["answers"]
    assert reviewed["ai_summary"]["skipped_no_evidence"] == 2
    assert reviewed["ai_summary"]["reviewed_questions"] == 0
