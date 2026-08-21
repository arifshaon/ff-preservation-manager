from __future__ import annotations

from preservation_risk_manager.data_access import RegistryReader
from preservation_risk_manager.format_resolver import resolve_format
from preservation_risk_manager.risk_context import build_external_risk_context


class FakeStore:
    def __init__(self, collections):
        self.collections = collections

    def query(self, collection, filt=None):
        rows = self.collections.get(collection, [])
        filt = filt or {}
        return [
            row
            for row in rows
            if all(row.get(key) == value for key, value in filt.items())
        ]


def test_ambiguous_resolution_returns_ten_choices_but_preserves_total_count():
    formats = [
        {
            "canonical_id": f"puid-fmt-{index}",
            "preferred_name": f"PDF Variant {index}",
            "extensions": ["pdf"],
        }
        for index in range(15)
    ]

    result = resolve_format("PDF", formats)

    assert result.ambiguous
    assert result.match_type == "extension"
    assert result.total_match_count == 15
    assert len(result.matches) == 10
    assert [row["canonical_id"] for row in result.matches] == [
        f"puid-fmt-{index}" for index in range(10)
    ]


def test_ambiguous_resolution_prioritizes_human_relevant_choices_without_guessing():
    formats = [
        {
            "canonical_id": "illustrator",
            "preferred_name": "Adobe Illustrator Artwork",
            "extensions": ["pdf"],
        },
        {
            "canonical_id": "pdf-family",
            "preferred_name": "PDF (Portable Document Format) Family",
            "extensions": ["pdf"],
        },
        {
            "canonical_id": "pdf-17",
            "preferred_name": "Acrobat PDF 1.7 - Portable Document Format",
            "extensions": ["pdf"],
        },
    ]

    result = resolve_format("PDF", formats)

    assert result.ambiguous
    assert result.total_match_count == 3
    assert [row["canonical_id"] for row in result.matches[:2]] == ["pdf-family", "pdf-17"]
    assert result.matches[-1]["canonical_id"] == "illustrator"


def test_external_risk_context_preserves_exact_and_group_assessments_without_averaging():
    format_doc = {
        "canonical_id": "puid-fmt-276",
        "preferred_name": "Acrobat PDF 1.7 - Portable Document Format",
        "identifiers": {
            "puid": ["fmt/276"],
            "loc": ["fdd000277"],
            "nara": ["NF00369"],
        },
        "synthesized_risk": {
            "method": "semantic_risk_synthesis_v2_scope_aware",
            "semantic_level": "low",
        },
    }
    store = FakeStore({
        "risk_assessment_claims": [
            {
                "_storage_key": "nara",
                "canonical_id": "puid-fmt-276",
                "current": True,
                "source_id": "nara_digital_preservation_framework",
                "source_record_id": "NF00369",
                "scope_type": "exact_format",
                "scope_name": "Acrobat PDF 1.7 - Portable Document Format",
                "native_label": "Low Risk",
                "native_score": 24.0,
                "normalized_band": "Low",
                "normalized_score": 1.0,
                "semantic_level": "low",
                "assessment": {
                    "source_label": "NARA Digital Preservation Framework",
                    "native_scale": "nara_file_format_risk_matrix",
                    "semantic_label": "Low concern",
                    "native_assessment": {"native_direction": "higher_is_safer"},
                },
            },
            {
                "_storage_key": "dpc",
                "canonical_id": "puid-fmt-276",
                "current": True,
                "source_id": "dpc_bit_list_2025",
                "source_record_id": "Lg7_RYL0UI",
                "scope_type": "format_group",
                "scope_name": "PDF",
                "native_label": "Vulnerable",
                "semantic_level": "moderate",
                "assessment": {
                    "source_label": "DPC Global Bit List 2025",
                    "native_scale": "dpc_global_bit_list_classification",
                    "semantic_label": "Moderate concern",
                },
            },
            {
                "_storage_key": "old-nara",
                "canonical_id": "puid-fmt-276",
                "current": False,
                "source_id": "nara_digital_preservation_framework",
                "source_record_id": "NF00369",
                "scope_type": "exact_format",
                "semantic_level": "high",
            },
        ]
    })

    context = build_external_risk_context(RegistryReader(store=store), format_doc)

    assert context["assessment_count"] == 2
    assert [row["source_id"] for row in context["assessments"]] == [
        "nara_digital_preservation_framework",
        "dpc_bit_list_2025",
    ]
    assert context["assessments"][0]["scope_type"] == "exact_format"
    assert context["assessments"][0]["native_direction"] == "higher_is_safer"
    assert context["semantic_levels"] == ["low", "moderate"]
    assert context["scoped_divergence"] is True
    assert context["scoring_effect"] == "context_only"
    assert context["aggregation_policy"] == "do_not_average_external_assessments"
    assert context["registry_synthesized_risk"]["semantic_level"] == "low"
