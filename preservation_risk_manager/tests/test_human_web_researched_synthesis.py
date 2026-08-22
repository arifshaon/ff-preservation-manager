from __future__ import annotations

from preservation_risk_manager.human_renderer_multi import render_human_response


def test_human_ai_synthesis_keeps_registry_sources_and_reports_capability_use():
    governed = {
        "assessed": True,
        "semantic_level": "low",
        "semantic_label": "Low concern",
        "method": "config_driven_scope_aware_synthesis",
        "contributors": [
            {
                "source_id": "nara_digital_preservation_framework",
                "source_record_id": "NF00369",
                "scope_type": "exact_format",
            }
        ],
        "contextual_contributors": [
            {
                "source_id": "dpc_bit_list_2025",
                "source_record_id": "DPC-PDF",
                "scope_type": "format_group",
            }
        ],
    }
    ai_result = {
        "assessed": True,
        "semantic_level": "moderate",
        "semantic_label": "Moderate concern",
        "method": "ai_capability_driven_synthesis",
        "policy_id": "qnl-preservation-risk-synthesis",
        "policy_version": "1.0",
        "ai_assisted": True,
        "governed_baseline": governed,
        "governed_baseline_relation": "higher_concern",
        "confidence": 0.82,
        "rationale": "The supplied evidence plus current external context support Moderate concern.",
        "capabilities_available": {"web_search": True},
        "capabilities_used": {"web_search": True},
        "considerations": [
            {
                "finding": "Official current tooling remains available.",
                "basis": "mixed",
                "risk_effect": "reduces_concern",
            },
            {
                "finding": "Current preservation guidance identifies added complexity for some features.",
                "basis": "external_information",
                "risk_effect": "raises_concern",
            },
        ],
        "quality_warnings": [],
        "uncertainty": "External evidence does not rewrite the source-native NARA assessment.",
    }
    response = {
        "status": "ok",
        "request": {"action": "assess_format", "format": "puid-fmt-276"},
        "result": {
            "format": {
                "format_id": "puid-fmt-276",
                "label": "Acrobat PDF 1.7 - Portable Document Format",
                "puids": ["fmt/276"],
            },
            "overall_synthesized_risk": ai_result,
            "external_risk_context": {
                "assessments": [
                    {
                        "source_id": "nara_digital_preservation_framework",
                        "source_label": "NARA Digital Preservation Framework",
                        "source_record_id": "NF00369",
                        "native_label": "Low Risk",
                        "native_score": 24.0,
                        "native_scale": "nara_file_format_risk_matrix",
                        "semantic_level": "low",
                        "semantic_label": "Low concern",
                        "scope_type": "exact_format",
                        "scope_name": "Acrobat PDF 1.7 - Portable Document Format",
                    },
                    {
                        "source_id": "dpc_bit_list_2025",
                        "source_label": "DPC Global Bit List 2025",
                        "source_record_id": "DPC-PDF",
                        "native_label": "Vulnerable",
                        "native_scale": "dpc_global_bit_list_classification",
                        "semantic_level": "moderate",
                        "semantic_label": "Moderate concern",
                        "scope_type": "format_group",
                        "scope_name": "PDF",
                    },
                ],
                "registry_synthesis_parity": {
                    "registry_level": "low",
                    "policy_level": "low",
                    "semantic_level_match": True,
                },
            },
        },
        "ai_synthesis": {
            "status": "ok",
            "mode": "capability_driven_ai_synthesis",
            "provider": {"provider": "azure_openai", "model": "test-model"},
            "overall_synthesized_risk": ai_result,
            "external_capability": {
                "capability_available": True,
                "capability_invoked": True,
                "web_search_used": True,
                "sources": [
                    {"ref": "W001", "title": "Official tooling", "url": "https://example.org/tooling"},
                    {"ref": "W002", "title": "Preservation guidance", "url": "https://example.org/guidance"},
                ],
            },
            "authority_boundary": "The AI result is returned alongside the governed baseline for the consumer to evaluate.",
        },
        "ai_risk_assessment": {
            "status": "synthesis_only",
            "ai_mode": "synthesize",
            "web_research_enabled": True,
            "question_level_ai_requested": False,
        },
    }

    text = render_human_response(response)

    assert "Overall synthesized preservation risk\nModerate concern" in text
    assert "Governed config baseline: Low concern" in text
    assert "NARA Digital Preservation Framework" in text
    assert "Native assessment: Low Risk" in text
    assert "Synthesis role: governed baseline headline contributor" in text
    assert "DPC Global Bit List 2025" in text
    assert "Synthesis role: governed baseline broader-scope context" in text
    assert "AI web-search capability: available; used by the model" in text
    assert "model decided whether to use them" in text
    assert "external information" in text
    assert "Web search capability was available to the AI client; the model used it" in text
    assert "W001: Official tooling — https://example.org/tooling" in text
    assert "W002: Preservation guidance — https://example.org/guidance" in text
    assert "19 question" not in text
