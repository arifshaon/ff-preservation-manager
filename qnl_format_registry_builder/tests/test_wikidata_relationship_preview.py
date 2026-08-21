from registry_builder.identifier_rules import load_identifier_rules
from registry_builder.models import Identifier, RawFormatRecord
from registry_builder.normalize import normalize_record
from registry_builder.wikidata_relationship_preview import preview_wikidata_relationships


RULES = load_identifier_rules()
WIKIDATA = "wikidata_file_formats"


def _canonical(canonical_id: str, name: str, **identifiers):
    return {
        "canonical_id": canonical_id,
        "preferred_name": name,
        "current": True,
        "identifiers": {
            kind: [value] if isinstance(value, str) else list(value)
            for kind, value in identifiers.items()
        },
    }


def _wikidata(
    qid: str,
    name: str,
    *,
    role: str = "format",
    puids=None,
    loc_ids=None,
    nara_ids=None,
):
    puids = puids or []
    loc_ids = loc_ids or []
    nara_ids = nara_ids or []
    identifiers = [Identifier("wikidata", qid, WIKIDATA, True, qid)]
    identifiers.extend(Identifier("puid", value, WIKIDATA, False, qid) for value in puids)
    identifiers.extend(Identifier("loc", value, WIKIDATA, False, qid) for value in loc_ids)
    identifiers.extend(Identifier("nara", value, WIKIDATA, False, qid) for value in nara_ids)
    return normalize_record(
        RawFormatRecord(
            source_id=WIKIDATA,
            source_type="wikidata_sparql",
            source_record_id=qid,
            record_role="format_identity",
            name=name,
            category=role,
            puids=puids,
            loc_ids=loc_ids,
            nara_ids=nara_ids,
            wikidata_ids=[qid],
            identifiers=identifiers,
            urls={"wikidata": f"https://www.wikidata.org/wiki/{qid}"},
            native_fields={"wikidata_role": role},
        ),
        identifier_rules=RULES,
    )


def _record_map(result):
    return {row["qid"]: row for row in result["records"]}


def test_relationship_preview_preserves_multi_target_context_without_merging():
    canonical = [
        _canonical("puid-fmt-1", "Variant One", puid="fmt/1"),
        _canonical("puid-fmt-2", "Variant Two", puid="fmt/2"),
        _canonical("loc-fdd000003", "LOC Format", loc="fdd000003"),
    ]
    records = [
        _wikidata("Q1", "One", puids=["fmt/1"]),
        _wikidata("Q2", "Family", role="format_family", puids=["fmt/1", "fmt/2"]),
        _wikidata("Q3", "Cross Authority", puids=["fmt/1"], loc_ids=["fdd000003"]),
        _wikidata("Q4", "No Authority"),
    ]

    result = preview_wikidata_relationships(canonical, records, identifier_rules=RULES)
    rows = _record_map(result)

    assert rows["Q1"]["outcome"] == "single_target_cross_reference"
    assert rows["Q2"]["outcome"] == "multi_target_context"
    assert rows["Q3"]["outcome"] == "multi_target_context"
    assert rows["Q4"]["outcome"] == "no_authority_cross_reference"

    assert result["canonical_formats_created"] == 0
    assert result["identity_merges_performed"] == 0
    assert result["canonical_identifiers_promoted"] == 0
    assert result["mongo_writes"] == 0
    assert result["relationship_edges"] == 5
    assert result["wikidata_qids_with_relationships"] == 3
    assert result["canonical_formats_with_wikidata_relationships"] == 3

    family_edges = [
        edge for edge in result["relationships"] if edge["source_record_id"] == "Q2"
    ]
    assert len(family_edges) == 2
    assert {edge["evidence_scope"] for edge in family_edges} == {"multi_canonical_context"}


def test_relationship_preview_reports_unresolved_copied_identifier_without_guessing():
    canonical = [_canonical("puid-fmt-1", "Variant One", puid="fmt/1")]
    records = [
        _wikidata("Q10", "Stale", puids=["fmt/999"]),
        _wikidata("Q11", "Partial", puids=["fmt/1", "fmt/999"]),
    ]

    result = preview_wikidata_relationships(canonical, records, identifier_rules=RULES)
    rows = _record_map(result)

    assert rows["Q10"]["outcome"] == "authority_claims_unresolved"
    assert rows["Q11"]["outcome"] == "single_target_with_unresolved_claims"
    assert result["matched_authority_claims_by_kind"] == {"puid": 1}
    assert result["unmatched_authority_claims_by_kind"] == {"puid": 2}
    assert result["relationship_edges"] == 1


def test_relationship_preview_keeps_copied_ids_as_relationship_evidence_only():
    canonical = [_canonical("puid-fmt-1", "Variant One", puid="fmt/1")]
    records = [_wikidata("Q20", "Variant One", puids=["fmt/1"])]

    result = preview_wikidata_relationships(canonical, records, identifier_rules=RULES)
    edge = result["relationships"][0]

    assert edge["relationship"] == "explicit_wikidata_identifier_cross_reference"
    assert edge["copied_identifiers"] == [{"kind": "puid", "value": "fmt/1"}]
    assert result["risk_assessments_generated"] == 0
    assert result["criterion_claims_generated"] == 0
