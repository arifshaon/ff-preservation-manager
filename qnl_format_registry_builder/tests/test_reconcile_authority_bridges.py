from registry_builder.models import RawFormatRecord
from registry_builder.normalize import normalize_record
from registry_builder.reconcile import reconcile


def _norm(records):
    return [normalize_record(record) for record in records]


def test_nara_authority_record_bridges_to_verified_pronom_puid():
    records = [
        RawFormatRecord(
            source_id="nara",
            source_type="nara_digital_preservation_framework",
            source_record_id="NF00792",
            name="PDF Portfolio",
            extensions=["pdf"],
            nara_ids=["NF00792"],
            puids=["fmt/1451"],
        ),
        RawFormatRecord(
            source_id="pronom",
            source_type="pronom_registry",
            source_record_id="fmt/1451",
            name="PDF Portfolio Format",
            extensions=["pdf"],
            puids=["fmt/1451"],
        ),
    ]

    registry = reconcile(_norm(records))

    assert len(registry) == 1
    fmt = registry[0]
    assert fmt.canonical_id == "puid-fmt-1451"
    assert "NF00792" in fmt.identifiers["nara"]
    assert "fmt/1451" in fmt.identifiers["puid"]
    assert any(
        claim["kind"] == "nara" and claim["value"] == "NF00792" and claim["verified"]
        for claim in fmt.identifier_claims
    )
    assert any(
        claim["kind"] == "puid" and claim["value"] == "fmt/1451" and claim["verified"]
        for claim in fmt.identifier_claims
    )
    assert any(
        claim["kind"] == "puid" and claim["value"] == "fmt/1451" and not claim["verified"]
        for claim in fmt.identifier_claims
    )


def test_source_authority_bridge_respects_version_conflict():
    records = [
        RawFormatRecord(
            source_id="nara",
            source_type="nara_digital_preservation_framework",
            source_record_id="NF00004",
            name="GIF 87a",
            extensions=["gif"],
            nara_ids=["NF00004"],
            puids=["fmt/4"],
        ),
        RawFormatRecord(
            source_id="pronom",
            source_type="pronom_registry",
            source_record_id="fmt/4",
            name="GIF 89a",
            extensions=["gif"],
            puids=["fmt/4"],
        ),
    ]

    registry = reconcile(_norm(records))

    assert len(registry) == 2
    assert {fmt.canonical_id for fmt in registry} == {"nara-nf00004", "puid-fmt-4"}
