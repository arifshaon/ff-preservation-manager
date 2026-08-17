from __future__ import annotations

from preservation_risk_manager.ai.base import (
    AIProvider,
    AIProviderCapabilities,
    AIRequest,
    AIResponse,
    AIUsage,
)
from preservation_risk_manager.ai.risk_analysis import derive_answers_with_ai
from preservation_risk_manager.answer_derivation import derive_answers
from preservation_risk_manager.frameworks import RiskFramework
from preservation_risk_manager.scoring import score_answers


class FakeRiskProvider(AIProvider):
    provider_name = "fake"
    capabilities = AIProviderCapabilities(structured_output=True)

    def __init__(self, structured_responses):
        self.structured_responses = list(structured_responses)
        self.requests: list[AIRequest] = []

    @property
    def model_name(self) -> str:
        return "fake-risk-model"

    def generate(self, request: AIRequest) -> AIResponse:
        self.requests.append(request)
        structured = self.structured_responses.pop(0)
        return AIResponse(
            provider=self.provider_name,
            model=self.model_name,
            structured=structured,
            usage=AIUsage(input_tokens=10, output_tokens=5, total_tokens=15),
        )


def _framework() -> RiskFramework:
    return RiskFramework.from_dict({
        "framework_id": "test_framework",
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
                "value": "openly_documented",
                "source_id": "source-a",
                "source_record_id": "record-a",
            },
            {
                "criterion_id": "sustainability.adoption",
                "value": "ambiguous_source_wording",
                "source_id": "source-b",
                "source_record_id": "record-b",
                "note": "The format is now restricted to a small legacy community.",
            },
        ],
        "migration_pathway_evidence": [],
    }


def test_ai_only_fills_unresolved_question_and_scoring_stays_deterministic():
    framework = _framework()
    evidence_pack = _evidence_pack()
    deterministic = derive_answers(framework, evidence_pack)
    provider = FakeRiskProvider([{
        "question_id": "q_adoption",
        "answer_id": "niche_or_declining",
        "confidence": 0.9,
        "rationale": "The supplied source describes a small legacy community.",
        "evidence_refs": ["E001"],
        "uncertainty": "",
    }])

    hybrid = derive_answers_with_ai(provider, framework, evidence_pack, deterministic)
    analysis = score_answers(framework, hybrid["scoring_answers"])

    assert len(provider.requests) == 1
    assert hybrid["derivation"]["q_disclosure"]["status"] == "derived"
    assert hybrid["answers"]["q_disclosure"] == "public_specification"
    assert hybrid["answers"]["q_adoption"] == "niche_or_declining"
    assert hybrid["derivation"]["q_adoption"]["status"] == "ai_interpreted"
    assert hybrid["ai_summary"]["accepted_answers"] == 1
    assert analysis["score"] == 4
    assert analysis["analysed_band"] == "High"


def test_hallucinated_evidence_reference_is_rejected_and_deterministic_answer_is_preserved():
    framework = _framework()
    evidence_pack = _evidence_pack()
    deterministic = derive_answers(framework, evidence_pack)
    provider = FakeRiskProvider([{
        "question_id": "q_adoption",
        "answer_id": "niche_or_declining",
        "confidence": 0.9,
        "rationale": "Unsupported citation.",
        "evidence_refs": ["E999"],
        "uncertainty": "",
    }])

    hybrid = derive_answers_with_ai(provider, framework, evidence_pack, deterministic)

    assert hybrid["answers"]["q_adoption"] == "unknown"
    assert hybrid["derivation"]["q_adoption"]["status"] == "unknown"
    assert hybrid["ai_summary"]["failed_questions"] == 1
    assert "not supplied" in hybrid["ai_audit"]["q_adoption"]["error"]


def test_no_evidence_skips_ai_call():
    framework = _framework()
    evidence_pack = {
        "scope": "global",
        "format": {"format_id": "fmt-empty", "label": "Empty Format"},
        "global_evidence": [],
        "migration_pathway_evidence": [],
    }
    deterministic = derive_answers(framework, evidence_pack)
    provider = FakeRiskProvider([])

    hybrid = derive_answers_with_ai(provider, framework, evidence_pack, deterministic)

    assert provider.requests == []
    assert hybrid["ai_summary"]["eligible_questions"] == 2
    assert hybrid["ai_summary"]["skipped_no_evidence"] == 2
    assert hybrid["answers"]["q_disclosure"] == "unknown"
    assert hybrid["answers"]["q_adoption"] == "unknown"
