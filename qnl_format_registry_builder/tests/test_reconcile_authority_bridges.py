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


def _pdfa_records():
    """PDF/A-1b as the three authorities actually describe it.

    NARA cites both a PUID and a LOC FDD ID; LOC cites the same PUID. Only
    PRONOM owns the PUID and only LOC owns the FDD ID.
    """
    return [
        RawFormatRecord(
            source_id="pronom_registry",
            source_type="pronom_registry",
            source_record_id="fmt/354",
            name="Acrobat PDF/A - Portable Document Format",
            puids=["fmt/354"],
        ),
        RawFormatRecord(
            source_id="nara_digital_preservation_framework",
            source_type="nara_digital_preservation_framework",
            source_record_id="NF00372",
            name="Portable Document Format/Archiving (PDF/A-1b) basic",
            nara_ids=["NF00372"],
            puids=["fmt/354"],
            loc_ids=["fdd000252"],
        ),
        RawFormatRecord(
            source_id="loc_fdd_xml",
            source_type="loc_fdd_xml",
            source_record_id="fdd000252",
            name="PDF/A-1b, PDF for Long-term Preservation, Basic",
            loc_ids=["fdd000252"],
            puids=["fmt/354"],
        ),
    ]


def test_adding_a_third_authority_does_not_detach_an_existing_bridge():
    """Ingesting a new source must never fragment what is already reconciled.

    NARA's record cites a PUID and a LOC FDD ID. With only PRONOM present those
    claims name one verified group and the bridge is made. Once LOC is ingested
    the FDD ID becomes a verified group of its own, so the claims name two
    groups — but both describe the same format, and the merge must survive.
    """
    pronom, nara, loc = _pdfa_records()

    before = reconcile(_norm([pronom, nara]))
    after = reconcile(_norm([pronom, nara, loc]))

    assert len(before) == 1
    assert before[0].canonical_id == "puid-fmt-354"

    assert len(after) == 1, "adding LOC must not split the existing NARA/PRONOM canonical"
    fmt = after[0]
    assert fmt.canonical_id == "puid-fmt-354"
    assert sorted({record["source_id"] for record in fmt.source_records}) == [
        "loc_fdd_xml",
        "nara_digital_preservation_framework",
        "pronom_registry",
    ]
    assert "NF00372" in fmt.identifiers["nara"]
    assert "fdd000252" in fmt.identifiers["loc"]
    assert "fmt/354" in fmt.identifiers["puid"]


def test_ingestion_order_does_not_change_the_result():
    """The same three records must reconcile identically in any order."""
    import itertools

    results = set()
    for ordering in itertools.permutations(_pdfa_records()):
        registry = reconcile(_norm(list(ordering)))
        results.add((len(registry), registry[0].canonical_id if len(registry) == 1 else None))

    assert results == {(1, "puid-fmt-354")}


def test_claims_naming_genuinely_different_formats_still_do_not_bridge():
    """The convergence rule must not merge a record citing two distinct formats."""
    records = [
        RawFormatRecord(
            source_id="pronom_registry",
            source_type="pronom_registry",
            source_record_id="fmt/18",
            name="Acrobat PDF 1.4 - Portable Document Format",
            puids=["fmt/18"],
        ),
        RawFormatRecord(
            source_id="loc_fdd_xml",
            source_type="loc_fdd_xml",
            source_record_id="fdd000123",
            name="TIFF, Revision 6.0",
            loc_ids=["fdd000123"],
        ),
        # An institutional record wrongly citing both a PDF PUID and a TIFF FDD.
        RawFormatRecord(
            source_id="institution",
            source_type="institution_policy_xlsx",
            source_record_id="row-1",
            name="Mixed citation row",
            puids=["fmt/18"],
            loc_ids=["fdd000123"],
        ),
    ]

    registry = reconcile(_norm(records))
    by_id = {fmt.canonical_id: fmt for fmt in registry}

    # The two authority records stay separate, and the ambiguous row does not
    # drag them together.
    assert "puid-fmt-18" in by_id
    assert "loc-fdd000123" in by_id
    assert len(registry) == 3
