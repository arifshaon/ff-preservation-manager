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


def test_record_citing_two_authorities_bridges_to_the_strongest_namespace():
    """Citing a PUID and an FDD must not cost the record its PUID bridge.

    NARA routinely cites both. While only PRONOM was ingested those citations
    named one verified group and the bridge was made; ingesting LOC turned the
    FDD ID into a verified group of its own, and refusing on ambiguity then
    silently undid the existing merge. PRONOM owns format identification, so the
    PUID wins — but the two authorities' own records are left unmerged, because
    a third party's crosswalk is not their assertion to make.
    """
    records = [
        RawFormatRecord(
            source_id="pronom_registry",
            source_type="pronom_registry",
            source_record_id="fmt/356",
            name="Adaptive Multi-Rate Audio",
            puids=["fmt/356"],
        ),
        RawFormatRecord(
            source_id="loc_fdd_xml",
            source_type="loc_fdd_xml",
            source_record_id="fdd000254",
            name="AMR, Adaptive Multi-Rate Speech Codec",
            loc_ids=["fdd000254"],
        ),
        RawFormatRecord(
            source_id="nara_digital_preservation_framework",
            source_type="nara_digital_preservation_framework",
            source_record_id="NF00102",
            name="Adaptive Multi Rate Audio (AMR)",
            nara_ids=["NF00102"],
            puids=["fmt/356"],
            loc_ids=["fdd000254"],
        ),
    ]

    registry = reconcile(_norm(records))
    by_id = {fmt.canonical_id: fmt for fmt in registry}

    assert set(by_id) == {"puid-fmt-356", "loc-fdd000254"}
    nara_home = by_id["puid-fmt-356"]
    assert sorted({r["source_id"] for r in nara_home.source_records}) == [
        "nara_digital_preservation_framework",
        "pronom_registry",
    ]
    # LOC's own record is untouched: NARA's crosswalk is not LOC's assertion.
    assert [r["source_id"] for r in by_id["loc-fdd000254"].source_records] == ["loc_fdd_xml"]
    # The choice among cited groups is flagged for collision review.
    claim = next(c for c in nara_home.identifier_claims
                 if c["kind"] == "loc" and c["value"] == "fdd000254")
    assert claim["confidence"] == "heuristic"


def test_ingesting_a_third_authority_never_reduces_merges():
    """The property the ranking rule exists to protect."""
    pronom, nara, loc = _pdfa_records()
    amr = [
        RawFormatRecord(source_id="pronom_registry", source_type="pronom_registry",
                        source_record_id="fmt/356", name="Adaptive Multi-Rate Audio", puids=["fmt/356"]),
        RawFormatRecord(source_id="nara_digital_preservation_framework",
                        source_type="nara_digital_preservation_framework",
                        source_record_id="NF00102", name="Adaptive Multi Rate Audio (AMR)",
                        nara_ids=["NF00102"], puids=["fmt/356"], loc_ids=["fdd000254"]),
        RawFormatRecord(source_id="loc_fdd_xml", source_type="loc_fdd_xml",
                        source_record_id="fdd000254", name="AMR, Adaptive Multi-Rate Speech Codec",
                        loc_ids=["fdd000254"]),
    ]

    def merged_source_records(records):
        merged = set()
        for fmt in reconcile(_norm(records)):
            sources = {r["source_id"] for r in fmt.source_records}
            if len(sources) > 1:
                merged |= {(r["source_id"], r["source_record_id"]) for r in fmt.source_records}
        return merged

    without_loc = merged_source_records([pronom, nara] + amr[:2])
    with_loc = merged_source_records([pronom, nara, loc] + amr)

    assert without_loc <= with_loc, "ingesting LOC must not un-merge anything"


def test_record_citing_two_formats_in_one_namespace_stays_ambiguous():
    """A tie inside one namespace is real ambiguity and must not be guessed at."""
    records = [
        RawFormatRecord(source_id="pronom_registry", source_type="pronom_registry",
                        source_record_id="fmt/18", name="Acrobat PDF 1.4", puids=["fmt/18"]),
        RawFormatRecord(source_id="pronom_registry", source_type="pronom_registry",
                        source_record_id="fmt/19", name="Acrobat PDF 1.5", puids=["fmt/19"]),
        RawFormatRecord(source_id="institution", source_type="institution_policy_xlsx",
                        source_record_id="row-1", name="Some PDF row", puids=["fmt/18", "fmt/19"]),
    ]

    registry = reconcile(_norm(records))

    assert len(registry) == 3, "a row naming two PUIDs must not be assigned to either"
