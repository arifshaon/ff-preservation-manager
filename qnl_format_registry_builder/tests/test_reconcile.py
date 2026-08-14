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
        RawFormatRecord(source_id="qnl", source_type="qnl_policy_xlsx", name="Chemical Markup Language", mime_types=["text"], extensions=["cml"]),
        RawFormatRecord(source_id="qnl", source_type="qnl_policy_xlsx", name="Crystallographic Information File", mime_types=["text"], extensions=["cif"]),
    ]
    registry = reconcile(_norm(records))
    assert len(registry) == 2
    assert sorted(x.preferred_name for x in registry) == ["Chemical Markup Language", "Crystallographic Information File"]


def test_unverified_spreadsheet_puid_does_not_force_merge_with_pronom():
    records = [
        RawFormatRecord(source_id="qnl", source_type="qnl_policy_xlsx", name="JPEG 1.00", puids=["fmt/44"], extensions=["jpg"]),
        RawFormatRecord(source_id="pronom", source_type="pronom_droid_xml", name="JFIF 1.02", puids=["fmt/44"], extensions=["jpg"]),
    ]
    registry = reconcile(_norm(records))
    assert len(registry) == 2
    assert {x.preferred_name for x in registry} == {"JPEG 1.00", "JFIF 1.02"}
    qnl = next(x for x in registry if x.preferred_name == "JPEG 1.00")
    assert any(c["kind"] == "puid" and not c["verified"] for c in qnl.identifier_claims)


def test_hazard_reconciler_is_wired_into_canonical_format():
    records = [
        RawFormatRecord(
            source_id="qnl",
            source_type="qnl_policy_xlsx",
            name="Example Format",
            extensions=["exf"],
            qnl={"spreadsheet_risk_level": "High Risk"},
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
