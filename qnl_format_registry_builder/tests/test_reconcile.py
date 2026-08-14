from registry_builder.models import RawFormatRecord
from registry_builder.normalize import normalize_record
from registry_builder.reconcile import reconcile


def test_pronom_puid_reconciles_records():
    records = [
        RawFormatRecord(source_id="a", source_type="standard_json", name="PDF/A-1", puids=["fmt/95"], extensions=[".PDF"]),
        RawFormatRecord(source_id="b", source_type="pronom_droid_xml", name="PDF/A", puids=["fmt/95"], mime_types=["application/pdf"]),
    ]
    registry = reconcile(normalize_record(r) for r in records)
    assert len(registry) == 1
    fmt = registry[0]
    assert fmt.canonical_id == "puid-fmt-95"
    assert "pdf" in fmt.identifiers["extension"]
    assert "application/pdf" in fmt.identifiers["mime"]
