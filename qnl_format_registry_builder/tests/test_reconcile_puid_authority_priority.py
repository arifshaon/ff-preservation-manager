from registry_builder.models import RawFormatRecord
from registry_builder.normalize import normalize_record
from registry_builder.reconcile import reconcile


def _norm(records):
    return [normalize_record(record) for record in records]


def _by_id(registry):
    return {item.canonical_id: item for item in registry}


def test_nara_puid_bridge_is_not_blocked_by_copied_loc_identifier():
    records = [
        RawFormatRecord(
            source_id="pronom_registry",
            source_type="pronom_registry",
            source_record_id="fmt/14",
            name="Acrobat PDF 1.0 - Portable Document Format",
            extensions=["pdf"],
            mime_types=["application/pdf"],
            puids=["fmt/14"],
            version="1.0",
        ),
        RawFormatRecord(
            source_id="nara_digital_preservation_framework",
            source_type="nara_digital_preservation_framework",
            source_record_id="NF00362",
            name="Portable Document Format (PDF) version 1.0",
            extensions=["pdf"],
            mime_types=["application/pdf"],
            puids=["fmt/14"],
            loc_ids=["fdd000316"],
            nara_ids=["NF00362"],
            hazard={"band": "Moderate", "rating": 2, "external_rating_native": 10},
        ),
        RawFormatRecord(
            source_id="loc_fdd_xml",
            source_type="loc_fdd_xml",
            source_record_id="fdd000316",
            name="PDF_1_3, PDF Versions 1.0-1.3",
            extensions=["pdf"],
            puids=["fmt/14", "fmt/15", "fmt/16", "fmt/17"],
            loc_ids=["fdd000316"],
        ),
        *[
            RawFormatRecord(
                source_id="pronom_registry",
                source_type="pronom_registry",
                source_record_id=f"fmt/{number}",
                name=f"Acrobat PDF {version}",
                extensions=["pdf"],
                puids=[f"fmt/{number}"],
                version=version,
            )
            for number, version in ((15, "1.1"), (16, "1.2"), (17, "1.3"))
        ],
    ]

    registry = reconcile(_norm(records))
    formats = _by_id(registry)

    assert "puid-fmt-14" in formats
    assert "nara-nf00362" not in formats
    assert "loc-fdd000316" in formats

    pdf10 = formats["puid-fmt-14"]
    assert pdf10.preferred_name == "Acrobat PDF 1.0 - Portable Document Format"
    assert pdf10.version == "1.0"
    assert pdf10.identifiers["puid"] == ["fmt/14"]
    assert pdf10.identifiers["nara"] == ["NF00362"]
    assert "loc" not in pdf10.identifiers
    assert pdf10.hazard_assessment["band"] == "Moderate"
    assert pdf10.hazard_assessment["external_rating_native"] == 10

    nara_refs = [
        ref for ref in pdf10.source_records
        if ref.get("source_id") == "nara_digital_preservation_framework"
        and ref.get("source_record_id") == "NF00362"
    ]
    assert len(nara_refs) == 1


def test_multi_puid_loc_record_stays_independent_but_links_evidence_to_each_puid():
    records = [
        RawFormatRecord(
            source_id="loc_fdd_xml",
            source_type="loc_fdd_xml",
            source_record_id="fdd000316",
            name="PDF_1_3, PDF Versions 1.0-1.3",
            extensions=["pdf"],
            puids=["fmt/14", "fmt/15", "fmt/16", "fmt/17"],
            loc_ids=["fdd000316"],
        ),
        *[
            RawFormatRecord(
                source_id="pronom_registry",
                source_type="pronom_registry",
                source_record_id=f"fmt/{number}",
                name=f"Acrobat PDF {version}",
                extensions=["pdf"],
                puids=[f"fmt/{number}"],
                version=version,
            )
            for number, version in ((14, "1.0"), (15, "1.1"), (16, "1.2"), (17, "1.3"))
        ],
    ]

    formats = _by_id(reconcile(_norm(records)))

    assert formats["loc-fdd000316"].identifiers == {"extension": ["pdf"], "loc": ["fdd000316"]}
    for number in (14, 15, 16, 17):
        fmt = formats[f"puid-fmt-{number}"]
        assert fmt.identifiers["puid"] == [f"fmt/{number}"]
        refs = [
            ref for ref in fmt.source_records
            if ref.get("source_id") == "loc_fdd_xml"
            and ref.get("source_record_id") == "fdd000316"
        ]
        assert len(refs) == 1
        assert refs[0]["relationship"] == "explicit_puid_cross_reference"
        assert refs[0]["evidence_scope"] == "multi_puid_source_record"
        assert refs[0]["related_puids"] == ["fmt/14", "fmt/15", "fmt/16", "fmt/17"]


def test_single_puid_version_conflict_is_not_linked_as_evidence():
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

    formats = _by_id(reconcile(_norm(records)))
    assert set(formats) == {"nara-nf00004", "puid-fmt-4"}
    assert not any(
        ref.get("source_record_id") == "NF00004"
        for ref in formats["puid-fmt-4"].source_records
    )
