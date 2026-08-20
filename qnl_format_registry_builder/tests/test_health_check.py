"""Each check must actually catch the defect it exists for."""

from registry_builder.health_check import (
    check_claims_point_at_live_canonicals,
    check_no_source_lost_its_claims,
    check_reconciliation_is_order_independent,
    check_unendorsed_claims_are_not_identifiers,
    run_health_check,
    summarise_cross_authority_merges,
)


def _registry():
    return [{
        "canonical_id": "puid-fmt-354",
        "preferred_name": "PDF/A-1b",
        "identifiers": {"puid": ["fmt/354"], "loc": ["fdd000252"]},
        "identifier_claims": [
            {"kind": "puid", "value": "fmt/354", "verified": True, "source": "pronom_registry"},
            {"kind": "loc", "value": "fdd000252", "verified": True, "source": "loc_fdd_xml"},
        ],
        "source_records": [
            {"source_id": "pronom_registry", "source_record_id": "fmt/354"},
            {"source_id": "loc_fdd_xml", "source_record_id": "fdd000252"},
        ],
    }]


def test_stale_claim_is_caught():
    claims = [{"canonical_id": "nara-nf00372", "source_id": "nara_digital_preservation_framework"}]

    result = check_claims_point_at_live_canonicals(_registry(), claims)

    assert result["status"] == "FAIL"
    assert result["stale_by_source"] == {"nara_digital_preservation_framework": 1}


def test_live_claim_passes():
    claims = [{"canonical_id": "puid-fmt-354", "source_id": "pronom_registry"}]

    assert check_claims_point_at_live_canonicals(_registry(), claims)["status"] == "pass"


def test_source_whose_stored_claims_vanished_from_the_export_is_caught():
    claims = [{"canonical_id": "puid-fmt-354", "source_id": "pronom_registry"}]

    result = check_no_source_lost_its_claims(claims, {"pronom_registry", "loc_fdd_xml"})

    assert result["status"] == "FAIL"
    assert result["missing_from_export"] == ["loc_fdd_xml"]


def test_source_that_never_had_claims_is_not_a_failure():
    """A graph-linking source such as Wikidata contributes identity, not claims."""
    claims = [{"canonical_id": "puid-fmt-354", "source_id": "pronom_registry"}]

    result = check_no_source_lost_its_claims(claims, {"pronom_registry"})

    assert result["status"] == "pass"


def test_claims_check_is_skipped_without_the_store():
    assert check_no_source_lost_its_claims([], None)["status"] == "SKIP"


def test_unendorsed_claim_leaking_into_the_identifier_map_is_caught():
    registry = _registry()
    registry[0]["identifiers"]["puid"].append("fmt/141")
    registry[0]["identifier_claims"].append(
        {"kind": "puid", "value": "fmt/141", "verified": False, "endorsed": False, "source": "loc_fdd_xml"}
    )

    result = check_unendorsed_claims_are_not_identifiers(registry)

    assert result["status"] == "FAIL"
    assert result["leaked"][0]["value"] == "fmt/141"


def test_unendorsed_claim_kept_only_as_evidence_passes():
    registry = _registry()
    registry[0]["identifier_claims"].append(
        {"kind": "puid", "value": "fmt/141", "verified": False, "endorsed": False, "source": "loc_fdd_xml"}
    )

    result = check_unendorsed_claims_are_not_identifiers(registry)

    assert result["status"] == "pass"
    assert result["unendorsed_claims"] == 1


def test_order_dependent_reconciliation_is_caught():
    class Fake:
        def __init__(self, canonical_id):
            self.canonical_id = canonical_id
            self.source_records = [{"source_id": "s", "source_record_id": canonical_id}]

    calls = {"n": 0}

    def unstable(records):
        # Returns a different assignment on later calls, as an order-dependent
        # reconciler effectively does.
        calls["n"] += 1
        return [Fake("a" if calls["n"] == 1 else "b")]

    result = check_reconciliation_is_order_independent(["r"], unstable, shuffles=1)

    assert result["status"] == "FAIL"


def test_stable_reconciliation_passes():
    class Fake:
        canonical_id = "puid-fmt-354"
        source_records = [{"source_id": "s", "source_record_id": "r"}]

    result = check_reconciliation_is_order_independent(["r1", "r2"], lambda records: [Fake()], shuffles=2)

    assert result["status"] == "pass"


def _healthy_claims():
    return [
        {"canonical_id": "puid-fmt-354", "source_id": "pronom_registry"},
        {"canonical_id": "puid-fmt-354", "source_id": "loc_fdd_xml"},
    ]


def test_skipped_check_never_reports_pass():
    report = run_health_check(_registry(), _healthy_claims())

    for name in ("reconciliation_is_order_independent", "no_source_lost_its_claims"):
        assert next(c for c in report["checks"] if c["check"] == name)["status"] == "SKIP"

    # A skipped check must not let the run claim a clean bill of health.
    assert report["status"] == "incomplete"


def test_failing_check_makes_the_whole_report_fail():
    claims = _healthy_claims() + [{"canonical_id": "gone", "source_id": "pronom_registry"}]

    report = run_health_check(_registry(), claims, stored_claim_sources={"pronom_registry", "loc_fdd_xml"})

    assert report["status"] == "FAIL"


def test_all_checks_passing_reports_ok():
    report = run_health_check(
        _registry(), _healthy_claims(),
        source_records=["r"], reconcile_fn=lambda records: [],
        stored_claim_sources={"pronom_registry", "loc_fdd_xml"},
    )

    assert [c["status"] for c in report["checks"]] == ["pass"] * 4
    assert report["status"] == "ok"


def test_merge_summary_counts_source_pairs():
    summary = summarise_cross_authority_merges(_registry())

    assert summary["canonicals_with_multiple_sources"] == 1
    assert summary["merges_by_source_pair"] == {"loc_fdd_xml + pronom_registry": 1}
