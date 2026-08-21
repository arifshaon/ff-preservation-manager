from pathlib import Path

from registry_builder.criteria import load_criteria
from registry_builder.criterion_mapping import build_criterion_claims, load_mapping, validate_mapping


ROOT = Path(__file__).resolve().parents[1]


def _mapping():
    return load_mapping(ROOT / "config" / "criterion_mappings" / "loc_fdd_xml.v2.draft2.json")


def _ip_claim(source_value: str):
    criteria = load_criteria(ROOT / "config" / "criteria" / "v1.json")
    canonical = {
        "canonical_id": "loc-fdd000999",
        "current": True,
        "source_records": [
            {
                "source_id": "loc_fdd_xml",
                "source_type": "loc_fdd_xml",
                "source_record_id": "fdd000999",
            }
        ],
    }
    source_record = {
        "source_id": "loc_fdd_xml",
        "source_type": "loc_fdd_xml",
        "source_record_id": "fdd000999",
        "native_fields": {
            "sustainability_factors": {"impact_of_patents": source_value}
        },
    }
    claims = build_criterion_claims(
        [canonical],
        [source_record],
        [_mapping()],
        criteria,
        include_drafts=True,
    )
    return [claim for claim in claims if claim["criterion_id"] == "sustainability.ip_licensing"]


def test_loc_v2_draft2_validates_against_criteria():
    criteria = load_criteria(ROOT / "config" / "criteria" / "v1.json")
    errors, warnings = validate_mapping(_mapping(), criteria)
    assert errors == []
    assert warnings == []


def test_loc_v2_draft2_maps_plain_royalty_free_statement_to_no_known_barrier():
    claims = _ip_claim('AVIF is royalty free and licensed under BSD 2-Clause "Simplified" License.')
    assert len(claims) == 1
    assert claims[0]["value"] == "no_known_barrier"


def test_loc_v2_draft2_keeps_mixed_royalty_free_and_patent_pool_language_constrained():
    claims = _ip_claim(
        "The technology has a royalty-free patent license, but the vendor offers its essential patent portfolio through patent pool license programs and may negotiate bilateral licenses."
    )
    assert len(claims) == 1
    assert claims[0]["value"] == "known_constraint"


def test_loc_v2_draft2_keeps_royalty_free_with_formal_uncertainty_as_limited():
    claims = _ip_claim(
        "Implementations are intended to be royalty and license-fee free. This is not a formal guarantee, however, and the specification lists patent holders."
    )
    assert len(claims) == 1
    assert claims[0]["value"] == "limited_or_unclear"


def test_loc_v2_draft2_maps_required_royalties_to_known_constraint():
    claims = _ip_claim("License and royalties may be required for use of some technologies described in this format.")
    assert len(claims) == 1
    assert claims[0]["value"] == "known_constraint"


def test_loc_v2_draft2_does_not_treat_generic_tool_license_as_format_constraint():
    claims = _ip_claim(
        "There appear to be no licensing problems associated with the format. A third-party interpreter used for commercial distribution requires a license."
    )
    assert len(claims) == 1
    assert claims[0]["value"] == "limited_or_unclear"
