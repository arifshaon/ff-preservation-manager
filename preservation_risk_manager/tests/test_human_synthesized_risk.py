from __future__ import annotations

from preservation_risk_manager.human_renderer_multi import render_human_response


def _base_response():
    return {
        "status": "ok",
        "request": {"action": "assess_format", "format": "puid-fmt-276"},
        "result": {
            "format": {
                "format_id": "puid-fmt-276",
                "label": "Acrobat PDF 1.7 - Portable Document Format",
                "puids": ["fmt/276"],
            },
            "missing_count": 19,
            "abstention_count": 19,
            "external_risk_context": {
                "assessments": [
                    {
                        "source_id": "nara_digital_preservation_framework",
                        "source_label": "NARA Digital Preservation Framework",
                        "source_record_id": "NF00369",
                        "native_label": "Low Risk",
                        "native_scale": "nara_file_format_risk_matrix",
                        "semantic_level": "low",
                        "semantic_label": "Low concern",
                        "scope_type": "exact_format",
                        "scope_name": "Acrobat PDF 1.7 - Portable Document Format",
                    },
                    {
                        "source_id": "dpc_bit_list_2025",
                        "source_label": "DPC Global Bit List 2025",
                        "source_record_id": "Lg7_RYL0UI",
                        "native_label": "Vulnerable",
                        "native_scale": "dpc_global_bit_list_classification",
                        "semantic_level": "moderate",
                        "semantic_label": "Moderate concern",
                        "scope_type": "format_group",
                        "scope_name": "PDF",
                    },
                ],
                "synthesis_policy": {
                    "policy_id": "qnl-preservation-risk-synthesis",
                    "version": "1.0",
                },
                "policy_synthesized_risk": {
                    "assessed": True,
                    "semantic_level": "low",
                    "semantic_label": "Low concern",
                    "policy_id": "qnl-preservation-risk-synthesis",
                    "policy_version": "1.0",
                    "method": "config_driven_scope_aware_synthesis",
                    "selected_scope_types": ["exact_format"],
                    "contributing_levels": ["low"],
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
                            "source_record_id": "Lg7_RYL0UI",
                            "scope_type": "format_group",
                        }
                    ],
                },
                "registry_synthesis_parity": {
                    "registry_level": "low",
                    "policy_level": "low",
                    "semantic_level_match": True,
                },
            },
        },
    }


def test_normal_risk_question_leads_with_source_synthesis_not_missing_framework_questions():
    response = _base_response()

    text = render_human_response(response)

    assert "Overall synthesized preservation risk\nLow concern" in text
    assert "NARA Digital Preservation Framework" in text
    assert "Native assessment: Low Risk" in text
    assert "Mapped semantic risk: Low concern" in text
    assert "Synthesis role: headline contributor" in text
    assert "DPC Global Bit List 2025" in text
    assert "Native assessment: Vulnerable" in text
    assert "Mapped semantic risk: Moderate concern" in text
    assert "Synthesis role: broader-scope context" in text
    assert "most-specific populated scope: exact format" in text
    assert "Missing sources contribute nothing" in text
    assert "19 question" not in text
    assert "Evidence completeness" not in text
    assert "matches the existing locked MongoDB synthesis" in text


def test_synthesis_only_mode_reports_ai_result_and_capability_use_separately_from_baseline():
    response = _base_response()
    governed = response["result"]["external_risk_context"]["policy_synthesized_risk"]
    ai_result = {
        "assessed": True,
        "semantic_level": "moderate",
        "semantic_label": "Moderate concern",
        "method": "ai_capability_driven_synthesis",
        "ai_assisted": True,
        "confidence": 0.75,
        "governed_baseline": governed,
        "governed_baseline_relation": "higher_concern",
        "capabilities_available": {"web_search": True},
        "capabilities_used": {"web_search": False},
        "rationale": "The AI considered the supplied registry evidence and methodology context.",
        "considerations": [],
        "quality_warnings": [],
        "uncertainty": "No external search was used.",
    }
    response["result"]["overall_synthesized_risk"] = ai_result
    response["ai_synthesis"] = {
        "status": "ok",
        "mode": "capability_driven_ai_synthesis",
        "provider": {"provider": "azure_openai", "model": "test"},
        "overall_synthesized_risk": ai_result,
        "external_capability": {
            "capability_available": True,
            "capability_invoked": True,
            "web_search_used": False,
            "sources": [],
        },
        "authority_boundary": "The consumer decides how to use the AI result; the governed baseline remains auditable.",
    }
    response["ai_risk_assessment"] = {
        "status": "synthesis_only",
        "ai_mode": "synthesize",
    }

    text = render_human_response(response)

    assert "Overall synthesized preservation risk\nModerate concern" in text
    assert "Governed config baseline: Low concern" in text
    assert "AI web-search capability: available; not used by the model" in text
    assert "AI-assisted synthesis\n- Status: ok." in text
    assert "AI-assisted synthesized level: moderate." in text
    assert "Web search capability was available to the AI client; the model did not use it." in text
    assert "not_requested_synthesis_only" not in text
