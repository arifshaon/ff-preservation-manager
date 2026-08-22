from __future__ import annotations

import preservation_risk_manager.ai.capability_result as capability_result
from preservation_risk_manager.synthesis_policy import load_synthesis_policy


def test_public_synthesis_normalizes_inconsistent_model_relation(monkeypatch):
    policy = load_synthesis_policy()

    def _raw(*args, **kwargs):
        return {
            "status": "ok",
            "governed_synthesis": {
                "assessed": True,
                "semantic_level": "low",
                "semantic_label": "Low concern",
            },
            "overall_synthesized_risk": {
                "assessed": True,
                "semantic_level": "low",
                "semantic_label": "Low concern",
                "governed_baseline_relation": "higher_concern",
                "quality_warnings": [],
            },
            "external_capability": {
                "web_search_used": False,
                "consulted_urls": [],
                "sources": [],
            },
        }

    monkeypatch.setattr(capability_result, "_synthesize_raw", _raw)

    result = capability_result.synthesize_with_capabilities(object(), policy=policy)
    overall = result["overall_synthesized_risk"]

    assert overall["governed_baseline_relation"] == "same"
    assert overall["ai_reported_governed_baseline_relation"] == "higher_concern"
    assert any("normalized the relation to 'same'" in warning for warning in overall["quality_warnings"])


def test_public_synthesis_derives_higher_and_lower_relations(monkeypatch):
    policy = load_synthesis_policy()

    def _run(ai_level: str, governed_level: str) -> str:
        def _raw(*args, **kwargs):
            return {
                "status": "ok",
                "governed_synthesis": {"assessed": True, "semantic_level": governed_level},
                "overall_synthesized_risk": {
                    "assessed": True,
                    "semantic_level": ai_level,
                    "governed_baseline_relation": "not_comparable",
                    "quality_warnings": [],
                },
                "external_capability": {"consulted_urls": [], "sources": []},
            }

        monkeypatch.setattr(capability_result, "_synthesize_raw", _raw)
        return capability_result.synthesize_with_capabilities(object(), policy=policy)[
            "overall_synthesized_risk"
        ]["governed_baseline_relation"]

    assert _run("moderate", "low") == "higher_concern"
    assert _run("low", "moderate") == "lower_concern"


def test_consulted_urls_are_exposed_when_response_has_no_citation_annotations(monkeypatch):
    policy = load_synthesis_policy()

    def _raw(*args, **kwargs):
        return {
            "status": "ok",
            "governed_synthesis": {"assessed": True, "semantic_level": "low"},
            "overall_synthesized_risk": {
                "assessed": True,
                "semantic_level": "low",
                "governed_baseline_relation": "same",
                "quality_warnings": [],
                "external_sources": [],
            },
            "external_capability": {
                "web_search_used": True,
                "consulted_urls": [
                    "https://example.org/spec",
                    "https://example.org/tooling",
                ],
                "sources": [],
            },
        }

    monkeypatch.setattr(capability_result, "_synthesize_raw", _raw)

    result = capability_result.synthesize_with_capabilities(object(), policy=policy)
    sources = result["external_capability"]["sources"]

    assert [item["ref"] for item in sources] == ["W001", "W002"]
    assert [item["url"] for item in sources] == [
        "https://example.org/spec",
        "https://example.org/tooling",
    ]
    assert result["overall_synthesized_risk"]["external_sources"] == sources
