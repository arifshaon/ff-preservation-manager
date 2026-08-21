from registry_builder.models import CanonicalFormat
from registry_builder.risk_synthesis import synthesize_risk_assessments


def test_canonical_serialization_retains_nara_and_institution_risk_separately():
    fmt = CanonicalFormat(
        canonical_id="puid-fmt-18",
        preferred_name="Portable Document Format",
        source_records=[
            {
                "source_id": "nara",
                "source_type": "nara_digital_preservation_framework",
                "source_record_id": "NF00018",
                "urls": {},
            }
        ],
        external_hazard=[
            {
                "source_id": "nara",
                "source_type": "nara_digital_preservation_framework",
                "source": "NARA Digital Preservation Framework",
                "band": "Moderate",
                "rating": 2.0,
                "native_band": "Moderate Risk",
                "external_rating_native": 12.0,
                "external_rating_native_scale": "nara_file_format_risk_matrix",
                "external_rating_native_direction": "higher_is_safer",
            }
        ],
        institution_policy_overlays=[
            {
                "institution_id": "qnl",
                "institution_name": "Qatar National Library",
                "institution_format_id": "QNL-PDF",
                "local_risk_level": "High Risk",
            }
        ],
    )

    data = fmt.to_dict()

    assert len(data["risk_assessments"]) == 2
    nara = next(x for x in data["risk_assessments"] if x["source_id"] == "nara")
    qnl = next(x for x in data["risk_assessments"] if x["source_id"] == "qnl")
    assert nara["native_label"] == "Moderate Risk"
    assert nara["native_score"] == 12.0
    assert nara["native_scale"] == "nara_file_format_risk_matrix"
    assert nara["semantic_level"] == "moderate"
    assert nara["source_record_id"] == "NF00018"
    assert qnl["native_label"] == "High Risk"
    assert qnl["semantic_level"] == "high"
    assert data["synthesized_risk"]["semantic_level"] == "high"
    assert data["synthesized_risk"]["source_divergence"] is True
    assert data["synthesized_risk"]["basis"] == "conservative_semantic_upper_bound"
    assert "not numerically averaged" in data["synthesized_risk"]["explanation"]


def test_dpc_style_family_assessment_can_coexist_with_exact_format_assessment():
    assessments = [
        {
            "assessment_role": "external",
            "source_id": "nara",
            "source_type": "nara_digital_preservation_framework",
            "source_record_id": "NF-PDFA3",
            "source_label": "NARA",
            "native_label": "Low",
            "semantic_level": "low",
            "scope_type": "exact_format",
            "scope_name": "PDF/A-3",
        },
        {
            "assessment_role": "external",
            "source_id": "dpc_bit_list_2025",
            "source_type": "dpc_bit_list",
            "source_record_id": "PDF",
            "source_label": "DPC Global Bit List 2025",
            "native_label": "Vulnerable",
            "semantic_level": "moderate",
            "scope_type": "format_family",
            "scope_name": "PDF",
        },
    ]

    result = synthesize_risk_assessments(assessments)

    assert result["semantic_level"] == "moderate"
    assert result["source_divergence"] is True
    assert result["scope_divergence"] is True
    assert len(result["contributors"]) == 2
    assert "DPC Global Bit List 2025: Vulnerable -> Moderate concern" in result["explanation"]


def test_loc_sustainability_source_does_not_create_overall_risk_assessment():
    fmt = CanonicalFormat(
        canonical_id="loc-fdd000277",
        preferred_name="PDF",
        source_records=[
            {
                "source_id": "loc",
                "source_type": "loc_fdd_xml",
                "source_record_id": "fdd000277",
                "urls": {},
            }
        ],
    )

    data = fmt.to_dict()

    assert data["risk_assessments"] == []
    assert data["synthesized_risk"]["assessed"] is False
    assert data["synthesized_risk"]["basis"] == "no_semantically_mapped_assessment"
