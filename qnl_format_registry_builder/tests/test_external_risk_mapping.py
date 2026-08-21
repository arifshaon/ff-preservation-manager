from registry_builder.external_risk_mapping import apply_external_risk_mappings
from registry_builder.models import CanonicalFormat, RawFormatRecord


def _dpc_pdf_record():
    return RawFormatRecord(
        source_id="dpc_bit_list_2025",
        source_type="dpc_bit_list",
        source_record_id="Lg7_RYL0UI",
        record_role="evidence_only",
        name="PDF",
        native_fields={"slug": "pdf"},
        risk_assessments=[
            {
                "assessment_role": "external",
                "source_id": "dpc_bit_list_2025",
                "source_type": "dpc_bit_list",
                "source_record_id": "Lg7_RYL0UI",
                "source_label": "DPC Global Bit List 2025",
                "native_label": "Vulnerable",
                "native_scale": "dpc_global_bit_list_classification",
                "semantic_level": "moderate",
                "scope_type": "format_group",
                "scope_name": "PDF",
            }
        ],
    )


def _pdf_mapping():
    return {
        "mapping_version": "dpc-bit-list-2025-v1",
        "rules": [
            {
                "rule_id": "dpc-2025-pdf-family",
                "status": "approved",
                "source_id": "dpc_bit_list_2025",
                "source_type": "dpc_bit_list",
                "source_record_id": "Lg7_RYL0UI",
                "source_slug": "pdf",
                "scope_type": "format_group",
                "scope_name": "PDF",
                "target_selector": {
                    "identifier_values": {"extension": ["pdf"]},
                    "preferred_name_regex": "(?i)(PDF|Portable Document Format)",
                },
            }
        ],
    }


def test_reviewed_dpc_pdf_mapping_retains_source_native_assessment_and_scope():
    fmt = CanonicalFormat(
        canonical_id="puid-fmt-18",
        preferred_name="Portable Document Format 1.4",
        identifiers={"extension": ["pdf"], "puid": ["fmt/18"]},
        risk_assessments=[
            {
                "assessment_role": "external",
                "source_id": "nara",
                "source_type": "nara_digital_preservation_framework",
                "source_record_id": "NF00018",
                "source_label": "NARA",
                "native_label": "Low",
                "semantic_level": "low",
                "scope_type": "exact_format",
                "scope_name": "Portable Document Format 1.4",
            }
        ],
    )

    report = apply_external_risk_mappings([fmt], [_dpc_pdf_record()], _pdf_mapping())

    assert report["rules_applied"] == 1
    assert report["assessments_attached"] == 1
    dpc = next(item for item in fmt.risk_assessments if item.get("source_type") == "dpc_bit_list")
    assert dpc["native_label"] == "Vulnerable"
    assert dpc["semantic_level"] == "moderate"
    assert dpc["scope_type"] == "format_group"
    assert dpc["scope_name"] == "PDF"
    assert dpc["scope_basis"] == "reviewed_external_risk_mapping"
    assert dpc["mapping_rule_id"] == "dpc-2025-pdf-family"
    assert dpc["mapped_target_canonical_id"] == "puid-fmt-18"
    assert fmt.synthesized_risk["semantic_level"] == "moderate"
    assert fmt.synthesized_risk["source_divergence"] is True
    assert fmt.synthesized_risk["scope_divergence"] is True


def test_pdf_mapping_requires_both_pdf_extension_and_pdf_name():
    unrelated = CanonicalFormat(
        canonical_id="fmt-unrelated",
        preferred_name="Unrelated Document",
        identifiers={"extension": ["pdf"]},
    )

    report = apply_external_risk_mappings([unrelated], [_dpc_pdf_record()], _pdf_mapping())

    assert report["rules_applied"] == 0
    assert report["rules_skipped"] == 1
    assert report["skipped"][0]["reason"] == "no_target_formats"
    assert unrelated.risk_assessments == []


def test_contextual_only_rule_never_attaches_to_format():
    fmt = CanonicalFormat(
        canonical_id="fmt-video",
        preferred_name="Legacy Video",
        identifiers={"extension": ["avi"]},
    )
    record = RawFormatRecord(
        source_id="dpc_bit_list_2025",
        source_type="dpc_bit_list",
        source_record_id="D_HNpwJ3On",
        record_role="evidence_only",
        name="Legacy Video Files",
        native_fields={"slug": "legacy-video-files"},
        risk_assessments=[{"native_label": "Endangered", "semantic_level": "high"}],
    )
    mapping = {
        "mapping_version": "dpc-bit-list-2025-v1",
        "rules": [
            {
                "rule_id": "dpc-2025-legacy-video-files",
                "status": "contextual_only",
                "source_id": "dpc_bit_list_2025",
                "source_record_id": "D_HNpwJ3On",
                "target_selector": {"identifier_values": {"extension": ["avi"]}},
            }
        ],
    }

    report = apply_external_risk_mappings([fmt], [record], mapping)

    assert report["rules_applied"] == 0
    assert report["rules_skipped"] == 1
    assert fmt.risk_assessments == []
