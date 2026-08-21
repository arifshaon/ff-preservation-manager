from __future__ import annotations

from registry_builder.loc_fdd_pronom_verify import verify_review_entries


class FakeStore:
    def __init__(self, by_identifier):
        self.by_identifier = by_identifier

    def find_by_identifier(self, kind, value):
        return self.by_identifier.get((kind, value))


def _canonical(canonical_id, name, claims):
    return {
        "canonical_id": canonical_id,
        "preferred_name": name,
        "identifier_claims": claims,
    }


def _entry(title="WAVE Audio File Format", fdd="fdd000001", puid="fmt/6"):
    return {
        "source_record_id": f"{fdd}:2",
        "title": title,
        "fdd_ids": [fdd],
        "puids": [puid],
        "mapping_review": {"pronom": {"status": "direct_single_candidate"}},
    }


def _loc_claim(fdd):
    return {"kind": "loc", "value": fdd, "verified": True, "source": "loc_fdd_xml"}


def _puid_claim(puid):
    return {"kind": "puid", "value": puid, "verified": True, "source": "pronom_registry"}


def test_candidate_already_reconciled_with_both_authorities_is_reported_not_approved():
    record = _canonical("puid-fmt-6", "WAVE Audio File Format", [_loc_claim("fdd000001"), _puid_claim("fmt/6")])
    store = FakeStore({("loc", "fdd000001"): record, ("puid", "fmt/6"): record})
    results, summary = verify_review_entries([_entry()], store)

    assert results[0]["status"] == "already_reconciled_authoritatively"
    assert results[0]["identity_bridge_approved"] is False
    assert summary["identity_bridges_approved"] == 0


def test_separate_authority_records_without_version_conflict_are_bridge_candidate_only():
    loc = _canonical("loc-fdd000001", "WAVE Audio File Format", [_loc_claim("fdd000001")])
    pronom = _canonical("puid-fmt-6", "WAVE Audio File Format", [_puid_claim("fmt/6")])
    store = FakeStore({("loc", "fdd000001"): loc, ("puid", "fmt/6"): pronom})
    results, _ = verify_review_entries([_entry()], store)

    assert results[0]["status"] == "bridge_candidate_authority_confirmed"
    assert results[0]["identity_bridge_approved"] is False


def test_broad_family_candidate_is_held_for_scope_review():
    loc = _canonical("loc-fdd000310", "EPUB File Format Family", [_loc_claim("fdd000310")])
    pronom = _canonical("puid-fmt-483", "ePub Format", [_puid_claim("fmt/483")])
    store = FakeStore({("loc", "fdd000310"): loc, ("puid", "fmt/483"): pronom})
    results, summary = verify_review_entries(
        [_entry(title="EPUB (Electronic Publication) File Format Family", fdd="fdd000310", puid="fmt/483")],
        store,
    )

    assert results[0]["status"] == "broad_scope_review"
    assert summary["status_counts"] == {"broad_scope_review": 1}


def test_duplicate_puid_candidates_are_all_many_to_one_scope_review():
    loc_a = _canonical("loc-fdd-a", "Example A", [_loc_claim("fdd-a")])
    loc_b = _canonical("loc-fdd-b", "Example B", [_loc_claim("fdd-b")])
    pronom = _canonical("puid-fmt-720", "Example PRONOM", [_puid_claim("fmt/720")])
    store = FakeStore({
        ("loc", "fdd-a"): loc_a,
        ("loc", "fdd-b"): loc_b,
        ("puid", "fmt/720"): pronom,
    })
    results, summary = verify_review_entries([
        _entry(title="Example A", fdd="fdd-a", puid="fmt/720"),
        _entry(title="Example B", fdd="fdd-b", puid="fmt/720"),
    ], store)

    assert [result["status"] for result in results] == ["many_to_one_scope_review", "many_to_one_scope_review"]
    assert all(result["related_fdd_ids"] == ["fdd-a", "fdd-b"] for result in results)
    assert summary["status_counts"] == {"many_to_one_scope_review": 2}


def test_version_conflict_is_held_for_review():
    loc = _canonical("loc-fdd000100", "Example Format 1.0", [_loc_claim("fdd000100")])
    pronom = _canonical("puid-fmt-100", "Example Format 2.0", [_puid_claim("fmt/100")])
    store = FakeStore({("loc", "fdd000100"): loc, ("puid", "fmt/100"): pronom})
    results, _ = verify_review_entries([_entry(title="Example Format 1.0", fdd="fdd000100", puid="fmt/100")], store)

    assert results[0]["status"] == "version_conflict_review"


def test_missing_authoritative_claim_is_not_bridge_candidate():
    loc = _canonical("loc-fdd000001", "WAVE Audio File Format", [_loc_claim("fdd000001")])
    copied_puid = _canonical(
        "fmt-wave",
        "WAVE Audio File Format",
        [{"kind": "puid", "value": "fmt/6", "verified": False, "source": "loc_fdd_xml"}],
    )
    store = FakeStore({("loc", "fdd000001"): loc, ("puid", "fmt/6"): copied_puid})
    results, _ = verify_review_entries([_entry()], store)

    assert results[0]["status"] == "authority_claim_missing"
    assert results[0]["pronom_authority_confirmed"] is False


def test_non_candidate_rows_are_not_verified():
    row = _entry()
    row["mapping_review"]["pronom"]["status"] = "contextual_only"
    results, summary = verify_review_entries([row], FakeStore({}))
    assert results == []
    assert summary["candidate_count"] == 0
