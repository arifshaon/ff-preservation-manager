from registry_builder.identifier_rules import load_identifier_rules
from registry_builder.models import Identifier, RawFormatRecord
from registry_builder.normalize import normalize_record
from registry_builder.reconcile import reconcile


def test_generic_identifier_kind_can_be_verified_and_used_as_strong_key():
    rules = load_identifier_rules({"dpc": {"strength": "strong", "verified_from": ["dpc_bit_list"]}})
    record = normalize_record(
        RawFormatRecord(
            source_id="dpc",
            source_type="dpc_bit_list",
            source_record_id="dpc-1",
            name="Example DPC Format",
            identifiers=[Identifier("dpc", "DPC-001", "dpc_bit_list", False, "dpc-1")],
        ),
        identifier_rules=rules,
    )

    assert record.identifiers[0].kind == "dpc"
    assert record.identifiers[0].value == "DPC-001"
    assert record.identifiers[0].verified is True

    registry = reconcile([record], identifier_rules=rules)

    assert registry[0].canonical_id == "dpc-dpc-001"
    assert registry[0].identifiers["dpc"] == ["DPC-001"]


def test_source_native_rating_direction_is_copied_without_nara_gap_assumption():
    rules = load_identifier_rules({"dpc": {"strength": "strong", "verified_from": ["dpc_bit_list"]}})
    external = normalize_record(
        RawFormatRecord(
            source_id="dpc",
            source_type="dpc_bit_list",
            source_record_id="dpc-1",
            name="Example DPC Format",
            identifiers=[Identifier("dpc", "DPC-001", "dpc_bit_list", False, "dpc-1")],
            hazard={
                "rating": 2.0,
                "external_rating_native": 4.0,
                "external_rating_native_scale": "dpc_bitlist_scale",
                "external_rating_native_direction": "lower_is_safer",
            },
        ),
        identifier_rules=rules,
    )

    registry = reconcile([external], identifier_rules=rules)
    assessment = registry[0].hazard_assessment

    assert assessment["external_rating_native"] == 4.0
    assert assessment["external_rating_native_direction"] == "lower_is_safer"
    assert assessment["external_rating_native_scale"] == "dpc_bitlist_scale"
    assert "external_native_gap_to_institution_band" not in assessment
