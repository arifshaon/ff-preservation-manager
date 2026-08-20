from registry_builder.collision_report import build_collision_report, collision_report_counts
from registry_builder.models import CanonicalFormat


def test_collision_report_surfaces_heuristic_identifier_bridge():
    fmt = CanonicalFormat(canonical_id="puid-fmt-18", preferred_name="Portable Document Format")
    fmt.add_identifier("puid", "fmt/18", source="pronom_droid_xml", verified=True)
    fmt.add_identifier(
        "puid",
        "fmt/18",
        source="institution_policy_xlsx",
        verified=False,
        confidence="heuristic",
        confidence_reason="Only one side carries an explicit version discriminator.",
    )

    report = build_collision_report([fmt])

    assert report["status"] == "review"
    assert report["summary"]["heuristic_identifier_bridges"] == 1
    bridge = report["heuristic_identifier_bridges"][0]
    assert bridge["canonical_id"] == "puid-fmt-18"
    assert bridge["kind"] == "puid"
    assert bridge["value"] == "fmt/18"
    assert bridge["confidence"] == "heuristic"


def test_collision_report_surfaces_weak_identifier_overlap():
    first = CanonicalFormat(canonical_id="fmt-a", preferred_name="Format A")
    first.add_identifier("extension", "jpg", source="a", verified=False)
    second = CanonicalFormat(canonical_id="fmt-b", preferred_name="Format B")
    second.add_identifier("extension", "jpg", source="b", verified=False)

    report = build_collision_report([first, second])

    assert report["status"] == "review"
    assert report["summary"]["weak_identifier_overlaps"] == 1
    overlap = report["weak_identifier_overlaps"][0]
    assert overlap["kind"] == "extension"
    assert overlap["value"] == "jpg"
    assert overlap["canonical_ids"] == ["fmt-a", "fmt-b"]


def test_collision_report_errors_on_verified_strong_identifier_conflict():
    first = CanonicalFormat(canonical_id="fmt-a", preferred_name="Format A")
    first.add_identifier("puid", "fmt/1", source="pronom_droid_xml", verified=True)
    second = CanonicalFormat(canonical_id="fmt-b", preferred_name="Format B")
    second.add_identifier("puid", "fmt/1", source="pronom_registry", verified=True)

    report = build_collision_report([first, second])

    assert report["status"] == "error"
    assert collision_report_counts(report)["verified_strong_identifier_conflicts"] == 1
    conflict = report["verified_strong_identifier_conflicts"][0]
    assert conflict["kind"] == "puid"
    assert conflict["canonical_ids"] == ["fmt-a", "fmt-b"]


def test_collision_report_ok_when_no_review_items():
    fmt = CanonicalFormat(canonical_id="fmt-pdf", preferred_name="PDF")
    fmt.add_identifier("extension", "pdf", source="loc_fdd_xml", verified=False)

    report = build_collision_report([fmt])

    assert report["status"] == "ok"
    assert report["summary"] == {
        "heuristic_identifier_bridges": 0,
        "weak_identifier_overlaps": 0,
        "verified_strong_identifier_conflicts": 0,
        "ambiguous_identifier_citations": 0,
    }


def test_report_names_records_citing_several_formats_in_one_namespace():
    """A record reconciliation cannot place is a finding, not silence.

    NARA says Broadcast Wave v.0 is fmt/1; LOC's signature says fmt/6.
    Reconciliation refuses to pick between them, so the report has to say why
    the record stayed on its own.
    """
    from registry_builder.models import RawFormatRecord
    from registry_builder.normalize import normalize_record
    from registry_builder.reconcile import reconcile

    records = [
        RawFormatRecord(source_id="pronom_registry", source_type="pronom_registry",
                        source_record_id="fmt/1", name="Broadcast WAVE 0 Generic", puids=["fmt/1"]),
        RawFormatRecord(source_id="pronom_registry", source_type="pronom_registry",
                        source_record_id="fmt/6", name="Waveform Audio", puids=["fmt/6"]),
        RawFormatRecord(source_id="nara_digital_preservation_framework",
                        source_type="nara_digital_preservation_framework",
                        source_record_id="NF00136", name="Broadcast Wave (BWF) v. 0",
                        nara_ids=["NF00136"], puids=["fmt/1", "fmt/6"]),
    ]
    registry = reconcile([normalize_record(r) for r in records])

    report = build_collision_report(registry)

    assert report["summary"]["ambiguous_identifier_citations"] == 1
    finding = report["ambiguous_identifier_citations"][0]
    assert finding["preferred_name"] == "Broadcast Wave (BWF) v. 0"
    assert finding["cited_canonical_ids_by_kind"]["puid"] == ["puid-fmt-1", "puid-fmt-6"]
    assert report["status"] == "review"
