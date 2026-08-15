from registry_builder.models import RawFormatRecord
from registry_builder.normalize import normalize_record
from registry_builder.reconcile import reconcile


def _norm(records):
    return [normalize_record(r) for r in records]


def test_verified_pronom_puid_reconciles_records():
    records = [
        RawFormatRecord(source_id="a", source_type="pronom_droid_xml", name="PDF/A-1", puids=["fmt/95"], extensions=[".PDF"]),
        RawFormatRecord(source_id="b", source_type="pronom_droid_xml", name="PDF/A", puids=["fmt/95"], mime_types=["application/pdf"]),
    ]
    registry = reconcile(_norm(records))
    assert len(registry) == 1
    fmt = registry[0]
    assert fmt.canonical_id == "puid-fmt-95"
    assert "pdf" in fmt.identifiers["extension"]
    assert "application/pdf" in fmt.identifiers["mime"]
    assert any(c["kind"] == "puid" and c["verified"] for c in fmt.identifier_claims)


def test_mime_type_does_not_merge_distinct_formats():
    records = [
        RawFormatRecord(source_id="qnl", source_type="institution_policy_xlsx", name="Chemical Markup Language", mime_types=["text"], extensions=["cml"]),
        RawFormatRecord(source_id="qnl", source_type="institution_policy_xlsx", name="Crystallographic Information File", mime_types=["text"], extensions=["cif"]),
    ]
    registry = reconcile(_norm(records))
    assert len(registry) == 2
    assert sorted(x.preferred_name for x in registry) == ["Chemical Markup Language", "Crystallographic Information File"]


def test_unverified_spreadsheet_puid_does_not_force_merge_with_pronom():
    records = [
        RawFormatRecord(source_id="qnl", source_type="institution_policy_xlsx", name="JPEG 1.00", puids=["fmt/44"], extensions=["jpg"]),
        RawFormatRecord(source_id="pronom", source_type="pronom_droid_xml", name="JFIF 1.02", puids=["fmt/44"], extensions=["jpg"]),
    ]
    registry = reconcile(_norm(records))
    assert len(registry) == 2
    assert {x.preferred_name for x in registry} == {"JPEG 1.00", "JFIF 1.02"}
    qnl = next(x for x in registry if x.preferred_name == "JPEG 1.00")
    assert any(c["kind"] == "puid" and not c["verified"] for c in qnl.identifier_claims)


def test_unverified_strong_identifier_blocks_weak_bridge_to_authority():
    records = [
        RawFormatRecord(
            source_id="qnl",
            source_type="institution_policy_xlsx",
            name="JFIF 1.02",
            puids=["fmt/999"],
            extensions=["jpg"],
            institution_policy={"institution_id": "qnl", "local_risk_level": "Low Risk"},
        ),
        RawFormatRecord(
            source_id="pronom",
            source_type="pronom_droid_xml",
            name="JFIF 1.02",
            puids=["fmt/44"],
            extensions=["jpg"],
        ),
    ]

    registry = reconcile(_norm(records))

    assert len(registry) == 2
    qnl = next(x for x in registry if x.canonical_id == "fmt-jfif-1-02")
    pronom = next(x for x in registry if x.canonical_id == "puid-fmt-44")
    assert qnl.preferred_name == "JFIF 1.02"
    assert pronom.preferred_name == "JFIF 1.02"
    assert any(c["kind"] == "puid" and c["value"] == "fmt/999" and not c["verified"] for c in qnl.identifier_claims)


def test_hazard_reconciler_is_wired_into_canonical_format():
    records = [
        RawFormatRecord(
            source_id="qnl",
            source_type="institution_policy_xlsx",
            name="Example Format",
            extensions=["exf"],
            institution_policy={"institution_id": "qnl", "local_risk_level": "High Risk"},
        ),
        RawFormatRecord(
            source_id="nara",
            source_type="nara_lod",
            name="Example Format",
            extensions=["exf"],
            hazard={"band": "High"},
        ),
    ]
    registry = reconcile(_norm(records))
    assert len(registry) == 1
    assert registry[0].hazard_assessment["band"] == "High"
    assert registry[0].hazard_assessment["basis"] == "corroborated"
    assert registry[0].hazard_assessment["review_required"] is False


def test_unique_name_extension_bridge_merges_institution_record_with_nara_authority():
    records = [
        RawFormatRecord(
            source_id="qnl",
            source_type="institution_policy_xlsx",
            name="Comma Separated Values",
            extensions=["csv"],
            institution_policy={"institution_id": "qnl", "local_risk_level": "Low Risk"},
        ),
        RawFormatRecord(
            source_id="nara",
            source_type="nara_digital_preservation_framework",
            source_record_id="NF00143",
            name="Comma Separated Values",
            extensions=["csv"],
            nara_ids=["NF00143"],
            hazard={"band": "Low", "rating": 1.0},
        ),
    ]

    registry = reconcile(_norm(records))

    assert len(registry) == 1
    fmt = registry[0]
    assert fmt.canonical_id == "nara-nf00143"
    assert fmt.hazard_assessment["basis"] == "corroborated"
    assert fmt.institution_policy_overlays[0]["institution_id"] == "qnl"


def test_reconciled_hazard_carries_native_rating_from_any_external_record():
    records = [
        RawFormatRecord(
            source_id="qnl",
            source_type="institution_policy_xlsx",
            name="Presentation Open XML",
            extensions=["pptx"],
            institution_policy={"institution_id": "qnl", "local_risk_level": "Low Risk"},
        ),
        RawFormatRecord(
            source_id="nara-action",
            source_type="nara_digital_preservation_framework",
            source_record_id="NF01000",
            name="Presentation Open XML",
            extensions=["pptx"],
            nara_ids=["NF01000"],
            hazard={"band": "Moderate", "rating": 2.0},
        ),
        RawFormatRecord(
            source_id="nara-risk-matrix",
            source_type="nara_digital_preservation_framework",
            source_record_id="NF01000",
            name="Presentation Open XML",
            extensions=["pptx"],
            nara_ids=["NF01000"],
            hazard={
                "band": "Moderate",
                "rating": 2.0,
                "external_rating_native": 22.0,
                "external_rating_native_direction": "higher_is_safer",
                "external_rating_native_scale": "nara_file_format_risk_matrix",
            },
        ),
    ]

    registry = reconcile(_norm(records))

    assert len(registry) == 1
    assessment = registry[0].hazard_assessment
    assert assessment["basis"] == "institution_override"
    assert assessment["external_rating"] == 2.0
    assert assessment["institution_rating"] == 1.0
    assert assessment["external_rating_native"] == 22.0
    assert assessment["external_rating_native_direction"] == "higher_is_safer"
    assert assessment["external_native_gap_to_institution_band"] == 1.0


def test_weak_bridge_does_not_merge_when_two_authority_records_share_name_extension():
    records = [
        RawFormatRecord(
            source_id="qnl",
            source_type="institution_policy_xlsx",
            name="Example Format",
            extensions=["exf"],
            institution_policy={"institution_id": "qnl", "local_risk_level": "Low Risk"},
        ),
        RawFormatRecord(
            source_id="nara_a",
            source_type="nara_digital_preservation_framework",
            source_record_id="NF00001",
            name="Example Format",
            extensions=["exf"],
            nara_ids=["NF00001"],
            hazard={"band": "Low", "rating": 1.0},
        ),
        RawFormatRecord(
            source_id="nara_b",
            source_type="nara_digital_preservation_framework",
            source_record_id="NF00002",
            name="Example Format",
            extensions=["exf"],
            nara_ids=["NF00002"],
            hazard={"band": "High", "rating": 3.0},
        ),
    ]

    registry = reconcile(_norm(records))

    assert len(registry) == 3
    assert {fmt.canonical_id for fmt in registry} == {"fmt-example-format", "nara-nf00001", "nara-nf00002"}
