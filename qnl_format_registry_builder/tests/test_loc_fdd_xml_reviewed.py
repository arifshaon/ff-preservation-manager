from __future__ import annotations

import xml.etree.ElementTree as ET

from registry_builder.adapters import resolve_adapter
from registry_builder.adapters.loc_fdd_xml_reviewed import (
    LOC_SUSTAINABILITY_TOP_LEVEL_FACTORS,
    LocFddXmlReviewedAdapter,
    contextualize_loc_xml_identifier_references,
    extract_reviewed_loc_sustainability_factors,
    normalize_loc_sustainability_structure,
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


def test_reviewed_loc_projection_keeps_only_official_seven_top_level_factors():
    factor_values = {
        "disclosure": "Fully disclosed.",
        "documentation": "Published specification, version 1.",
        "adoption": "Widely adopted.",
        "transparency": "Human-readable.",
        "self_documentation": "Includes embedded metadata.",
        "external_dependencies": "None.",
        "impact_of_patents": "No known patent claims.",
        "technical_protection_mechanisms": "None.",
    }
    record = RawFormatRecord(
        source_id="loc_fdd_xml",
        source_type="loc_fdd_xml_reviewed",
        source_record_id="fdd000999",
        name="Test Format",
        loc_ids=["fdd000999"],
        native_fields={"sustainability_factors": factor_values},
        evidence=[{"type": "loc_fdd_xml_zip", "sustainability_factor_count": 8}],
    )

    projected = normalize_loc_sustainability_structure(record)

    assert tuple(projected.native_fields["sustainability_factors"]) == LOC_SUSTAINABILITY_TOP_LEVEL_FACTORS
    assert "documentation" not in projected.native_fields["sustainability_factors"]
    assert projected.native_fields["sustainability_factor_details"] == {
        "disclosure": {"documentation": "Published specification, version 1."}
    }
    assert projected.evidence[0]["sustainability_factor_count"] == 7
    assert projected.evidence[0]["sustainability_supporting_evidence_count"] == 1
    assert projected.evidence[0]["sustainability_framework"] == "loc_seven_sustainability_factors"


def test_reviewed_factor_extraction_accepts_structured_exact_labels():
    root = ET.fromstring(
        """
        <fdd>
          <factor type="Disclosure"><p>Fully disclosed.</p></factor>
          <factor><label>Adoption</label><p>Widely adopted.</p></factor>
          <technicalProtectionConsiderations>None.</technicalProtectionConsiderations>
        </fdd>
        """
    )

    factors = extract_reviewed_loc_sustainability_factors(root)

    assert factors == {
        "disclosure": "Fully disclosed.",
        "adoption": "Widely adopted.",
        "technical_protection_mechanisms": "None.",
    }


def test_reviewed_factor_extraction_does_not_promote_factor_names_from_free_text():
    root = ET.fromstring(
        """
        <fdd>
          <notes>
            See Technical Protection Considerations for another format.
            Licensing and patents are discussed elsewhere.
          </notes>
          <description>
            This prose mentions transparency and adoption but is not a sustainability factor field.
          </description>
        </fdd>
        """
    )

    assert extract_reviewed_loc_sustainability_factors(root) == {}
