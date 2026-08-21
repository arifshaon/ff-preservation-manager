from registry_builder.identifier_rules import load_identifier_rules
from registry_builder.models import Identifier, RawFormatRecord
from registry_builder.normalize import normalize_record
from registry_builder.wikidata_reconciliation_preview import preview_reconciliation


RULES = load_identifier_rules()
WIKIDATA = "wikidata_file_formats"


def _existing(
    source_id: str,
    source_type: str,
    source_record_id: str,
    name: str,
    *,
    puid: str | None = None,
    loc: str | None = None,
    nara: str | None = None,
    extension: str | None = None,
) -> RawFormatRecord:
    identifiers = []
    if puid:
        identifiers.append(Identifier("puid", puid, source_type, True, source_record_id))
    if loc:
        identifiers.append(Identifier("loc", loc, source_type, True, source_record_id))
    if nara:
        identifiers.append(Identifier("nara", nara, source_type, True, source_record_id))
    record = RawFormatRecord(
        source_id=source_id,
        source_type=source_type,
        source_record_id=source_record_id,
        name=name,
        extensions=[extension] if extension else [],
        identifiers=identifiers,
    )
    return normalize_record(record, identifier_rules=RULES)


def _wikidata(
    qid: str,
    name: str,
    *,
    role: str = "format",
    record_role: str = "format_identity",
    puids: list[str] | None = None,
    loc_ids: list[str] | None = None,
    extension: str | None = None,
) -> RawFormatRecord:
    puids = puids or []
    loc_ids = loc_ids or []
    identifiers = [Identifier("wikidata", qid, WIKIDATA, True, qid)]
    identifiers.extend(Identifier("puid", value, WIKIDATA, False, qid) for value in puids)
    identifiers.extend(Identifier("loc", value, WIKIDATA, False, qid) for value in loc_ids)
    record = RawFormatRecord(
        source_id=WIKIDATA,
        source_type="wikidata_sparql",
        source_record_id=qid,
        record_role=record_role,
        name=name,
        category=role,
        extensions=[extension] if extension else [],
        puids=puids,
        loc_ids=loc_ids,
        wikidata_ids=[qid],
        identifiers=identifiers,
        native_fields={"wikidata_role": role},
    )
    return normalize_record(record, identifier_rules=RULES)


def _rows(result):
    return {row["qid"]: row for row in result["records"]}


def test_preview_distinguishes_existing_ambiguous_new_and_evidence_only():
    existing = [
        _existing(
            "pronom_registry",
            "pronom_registry",
            "fmt/1",
            "Format One",
            puid="fmt/1",
            extension="one",
        ),
        _existing(
            "pronom_registry",
            "pronom_registry",
            "fmt/2",
            "Format Two",
            puid="fmt/2",
            extension="two",
        ),
        _existing(
            "loc_fdd_xml",
            "loc_fdd_xml",
            "fdd000003",
            "Weak Match",
            loc="fdd000003",
            extension="weak",
        ),
    ]
    wikidata = [
        _wikidata("Q1", "Format One", puids=["fmt/1"], extension="one"),
        _wikidata("Q2", "Multi PUID", puids=["fmt/1", "fmt/2"]),
        _wikidata("Q3", "Brand New Format", extension="new"),
        _wikidata("Q4", "Weak Match", extension="weak"),
        _wikidata(
            "Q5",
            "Codec Context",
            role="codec_or_encoding",
            record_role="evidence_only",
            extension="codec",
        ),
    ]

    result = preview_reconciliation(existing, wikidata, identifier_rules=RULES)
    rows = _rows(result)

    assert rows["Q1"]["outcome"] == "joined_existing_authority"
    assert rows["Q2"]["outcome"] == "ambiguous_authority_bridge"
    assert rows["Q3"]["outcome"] == "new_canonical_candidate"
    assert rows["Q4"]["outcome"] == "joined_existing_weak"
    assert rows["Q5"]["outcome"] == "evidence_only"

    assert result["mongo_writes"] == 0
    assert result["read_only"] is True
    assert result["baseline_canonical_formats"] == 3
    assert result["wikidata_qids_joining_existing"] == 2
    assert result["wikidata_qids_requiring_review"] == 1
    assert result["wikidata_qids_new_candidates"] == 1
    assert result["outcomes"]["evidence_only"] == 1


def test_preview_flags_single_authority_target_rejected_by_version_guard():
    existing = [
        _existing(
            "pronom_registry",
            "pronom_registry",
            "fmt/10",
            "Example Format 1.0",
            puid="fmt/10",
            extension="ex",
        )
    ]
    wikidata = [
        _wikidata(
            "Q10",
            "Example Format 2.0",
            puids=["fmt/10"],
            extension="ex",
        )
    ]

    result = preview_reconciliation(existing, wikidata, identifier_rules=RULES)
    row = _rows(result)["Q10"]

    assert row["outcome"] == "guarded_authority_mismatch"
    assert row["authority_targets"] == ["puid-fmt-10"]
    assert len(row["new_canonical_ids"]) == 1
    assert result["wikidata_qids_requiring_review"] == 1
    assert result["wikidata_qids_new_candidates"] == 0


def test_preview_never_uses_evidence_only_record_to_create_identity():
    existing = []
    wikidata = [
        _wikidata(
            "Q20",
            "Context Only",
            role="other_format_concept",
            record_role="evidence_only",
            puids=["fmt/999"],
        )
    ]

    result = preview_reconciliation(existing, wikidata, identifier_rules=RULES)

    assert result["baseline_canonical_formats"] == 0
    assert result["augmented_canonical_formats"] == 0
    assert result["net_new_canonical_formats"] == 0
    assert result["outcomes"] == {"evidence_only": 1}
