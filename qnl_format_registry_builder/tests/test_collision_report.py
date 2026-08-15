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
    }
