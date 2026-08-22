from __future__ import annotations

from preservation_risk_manager.human_renderer_multi import render_human_response


def test_human_researched_synthesis_keeps_registry_sources_primary_and_shows_web_verification():
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
    researched = {
        "assessed": True,
        "semantic_level": "moderate",
        "semantic_label": "Moderate concern",
        "method": "ai_web_research_assisted_synthesis",
        "policy_id": "qnl-preservation-risk-synthesis",
        "policy_version": "1.0",
        "ai_assisted": True,
        "web_researched": True,
        "governed_baseline": governed,
        "governed_baseline_relation": "higher_concern",
        "rationale": "Current cited evidence qualifies the governed Low baseline.",
        "verification_findings": [
            {
                "finding": "Official current tooling remains available.",
                "relationship_to_database": "supplements",
                "risk_effect": "reduces_concern",
            },
            {
                "finding": "Current preservation guidance identifies added complexity for some features.",
                "relationship_to_database": "qualifies_or_updates",
                "risk_effect": "raises_concern",
            },
        ],
        "missing_evidence_policy": "exclude",
        "numeric_aggregation": "forbidden_across_source_scales",
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
            "overall_synthesized_risk": researched,
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
            "mode": "registry_first_web_research",
            "provider": {"provider": "azure_openai", "model": "test-model"},
            "overall_synthesized_risk": researched,
            "web_research": {
                "search_queries": ["verify PDF 1.7 current preservation tooling"],
                "citations": [
                    {"ref": "W001", "title": "Official tooling", "url": "https://example.org/tooling"},
                    {"ref": "W002", "title": "Preservation guidance", "url": "https://example.org/guidance"},
                ],
                "persisted": False,
            },
            "authority_boundary": "Registry evidence remains primary; web research verifies or supplements it.",
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
    assert "registry evidence was verified and supplemented using cited public-web research" in text
    assert "configured synthesis was used as the governed baseline" in text
    assert "qualifies or updates" in text
    assert "Registry-first web verification was performed using 2 cited web source(s)" in text
    assert "W001: Official tooling — https://example.org/tooling" in text
    assert "W002: Preservation guidance — https://example.org/guidance" in text
    assert "19 question" not in text
    assert "independent" not in text.lower()
