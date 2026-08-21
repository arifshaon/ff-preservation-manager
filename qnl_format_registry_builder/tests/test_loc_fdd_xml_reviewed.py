from __future__ import annotations

from registry_builder.adapters import resolve_adapter
from registry_builder.adapters.loc_fdd_xml_reviewed import (
    LocFddXmlReviewedAdapter,
    contextualize_loc_xml_identifier_references,
)
from registry_builder.models import Identifier, RawFormatRecord
from registry_builder.normalize import normalize_record


def test_reviewed_loc_adapter_is_registered():
    assert resolve_adapter("loc_fdd_xml_reviewed") is LocFddXmlReviewedAdapter


def test_loc_xml_puid_and_qid_references_become_contextual_only():
    record = RawFormatRecord(
        source_id="loc_fdd_xml",
        source_type="loc_fdd_xml_reviewed",
        source_record_id="fdd000001",
        name="WAVE Audio File Format",
        loc_ids=["fdd000001"],
        puids=["fmt/6"],
        wikidata_ids=["Q217570"],
        identifiers=[
            Identifier("puid", "fmt/6", "loc_fdd_xml_reviewed", False, "fdd000001"),
            Identifier("wikidata", "Q217570", "loc_fdd_xml_reviewed", False, "fdd000001"),
        ],
        native_fields={"sustainability_factors": {"adoption": "Widely adopted."}},
    )

    projected = normalize_record(contextualize_loc_xml_identifier_references(record))

    assert projected.source_type == "loc_fdd_xml"
    assert projected.loc_ids == ["fdd000001"]
    assert projected.puids == []
    assert projected.wikidata_ids == []
    assert projected.native_fields["contextual_identifier_references"] == {
        "puid": ["fmt/6"],
        "wikidata": ["Q217570"],
    }
    claims = {(claim.kind, claim.value): claim.verified for claim in projected.identifiers}
    assert claims[("loc", "fdd000001")] is True
    assert ("puid", "fmt/6") not in claims
    assert ("wikidata", "Q217570") not in claims
    assert projected.native_fields["sustainability_factors"]["adoption"] == "Widely adopted."
