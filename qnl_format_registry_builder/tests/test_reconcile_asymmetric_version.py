from registry_builder.collision_report import build_collision_report
from registry_builder.models import RawFormatRecord
from registry_builder.normalize import normalize_record
from registry_builder.reconcile import reconcile


def _norm(records):
    return [normalize_record(record) for record in records]


def test_unversioned_copied_puid_does_not_merge_into_versioned_pronom_record():
    records = [
        RawFormatRecord(
            source_id="qnl_institution_format_evidence_2026_seed",
            source_type="qnl_institution_format_evidence",
            source_record_id="pdf-generic",
            name="PDF",
            extensions=["pdf"],
            puids=["fmt/18"],
        ),
        RawFormatRecord(
            source_id="pronom_registry",
            source_type="pronom_registry",
            source_record_id="fmt/18",
            name="Acrobat PDF 1.4 - Portable Document Format",
            extensions=["pdf"],
            puids=["fmt/18"],
            version="1.4",
        ),
    ]

    registry = reconcile(_norm(records))

    assert {fmt.canonical_id for fmt in registry} == {"fmt-pdf", "puid-fmt-18"}
    pdf14 = next(fmt for fmt in registry if fmt.canonical_id == "puid-fmt-18")
    qnl_ref = next(
        ref for ref in pdf14.source_records
        if ref.get("source_record_id") == "pdf-generic"
    )
    assert qnl_ref["relationship"] == "explicit_puid_cross_reference"
    assert qnl_ref["evidence_scope"] == "version_ambiguous_puid_cross_reference"
    assert qnl_ref["related_puids"] == ["fmt/18"]

    report = build_collision_report(registry)
    assert report["summary"]["heuristic_identifier_bridges"] == 0


def test_matching_explicit_versions_may_still_merge_on_unique_copied_puid():
    records = [
        RawFormatRecord(
            source_id="nara_digital_preservation_framework",
            source_type="nara_digital_preservation_framework",
            source_record_id="NF-PDF14",
            name="Acrobat PDF 1.4",
            extensions=["pdf"],
            nara_ids=["NF-PDF14"],
            puids=["fmt/18"],
            version="1.4",
        ),
        RawFormatRecord(
            source_id="pronom_registry",
            source_type="pronom_registry",
            source_record_id="fmt/18",
            name="Acrobat PDF 1.4",
            extensions=["pdf"],
            puids=["fmt/18"],
            version="1.4",
        ),
    ]

    registry = reconcile(_norm(records))

    assert len(registry) == 1
    fmt = registry[0]
    assert fmt.canonical_id == "puid-fmt-18"
    assert fmt.identifiers["puid"] == ["fmt/18"]
    assert fmt.identifiers["nara"] == ["NF-PDF14"]
    assert build_collision_report(registry)["summary"]["heuristic_identifier_bridges"] == 0
