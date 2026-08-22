from __future__ import annotations

from types import SimpleNamespace

import preservation_risk_manager.integration_cli as integration_cli


class _Reader:
    def get_criterion_claims_for_format(self, format_doc, institution_id=None):
        return []


class _Provider:
    config = SimpleNamespace(web_research_enabled=True)

    def describe(self):
        return {"provider": "fake", "model": "fake-web"}


def test_synthesis_mode_routes_to_registry_first_web_research_when_provider_config_enables_it(monkeypatch):
    calls = {"web": 0, "bounded": 0}
    format_doc = {
        "canonical_id": "puid-fmt-276",
        "preferred_name": "PDF 1.7",
        "puids": ["fmt/276"],
    }

    class _Resolver:
        def __init__(self, reader):
            self.reader = reader

        def resolve(self, token):
            return SimpleNamespace(resolved=True, format_doc=format_doc)

    monkeypatch.setattr(integration_cli, "FormatResolver", _Resolver)
    monkeypatch.setattr(integration_cli, "_ai_format_context", lambda reader, row: row)
    monkeypatch.setattr(
        integration_cli,
        "build_evidence_pack",
        lambda row, institution_id=None, criterion_claims=None: {
            "format": {"format_id": "puid-fmt-276", "label": "PDF 1.7", "puids": ["fmt/276"]}
        },
    )
    monkeypatch.setattr(
        integration_cli,
        "derive_answers",
        lambda framework, pack: {"answers": {}, "scoring_answers": {}},
    )
    monkeypatch.setattr(integration_cli, "score_answers", lambda framework, answers: {"analysis_status": "Not Assessed"})
    monkeypatch.setattr(integration_cli, "build_ai_source_evidence", lambda *args, **kwargs: [])
    monkeypatch.setattr(integration_cli, "load_synthesis_policy", lambda: object())

    def _web(**kwargs):
        calls["web"] += 1
        assert kwargs["governed_synthesis"]["semantic_level"] == "low"
        assert kwargs["risk_assessments"][0]["source_id"] == "nara_digital_preservation_framework"
        return {
            "status": "ok",
            "mode": "registry_first_web_research",
            "overall_synthesized_risk": {
                "assessed": True,
                "semantic_level": "moderate",
                "semantic_label": "Moderate concern",
                "web_researched": True,
            },
        }

    def _bounded(**kwargs):
        calls["bounded"] += 1
        raise AssertionError("bounded synthesis must not be used when web research is explicitly enabled")

    monkeypatch.setattr(integration_cli, "synthesize_with_web_research", _web)
    monkeypatch.setattr(integration_cli, "synthesize_with_ai", _bounded)

    response = {
        "status": "ok",
        "scope": "global",
        "institution_id": None,
        "result": {
            "external_risk_context": {
                "assessments": [
                    {
                        "source_id": "nara_digital_preservation_framework",
                        "source_record_id": "NF00369",
                        "native_label": "Low Risk",
                        "scope_type": "exact_format",
                    }
                ],
                "policy_synthesized_risk": {
                    "assessed": True,
                    "semantic_level": "low",
                    "semantic_label": "Low concern",
                },
            }
        },
    }

    result = integration_cli._apply_ai_risk_assessment(
        _Reader(),
        object(),
        {"action": "assess_format", "format": "puid-fmt-276"},
        response,
        provider=_Provider(),
        ai_mode="synthesize",
        max_evidence_items=20,
    )

    assert calls == {"web": 1, "bounded": 0}
    assert result["result"]["overall_synthesized_risk"]["semantic_level"] == "moderate"
    assert result["ai_risk_assessment"] == {
        "status": "synthesis_only",
        "ai_mode": "synthesize",
        "web_research_enabled": True,
        "question_level_ai_requested": False,
    }
