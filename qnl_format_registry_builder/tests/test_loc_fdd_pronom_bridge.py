from __future__ import annotations

import json
from pathlib import Path

from registry_builder.adapters import resolve_adapter
from registry_builder.adapters.loc_fdd_pronom_bridge import LocFddPronomBridgeAdapter
from registry_builder.loc_fdd_pronom_bridge_approve import build_bridge_mapping
from registry_builder.models import Identifier, RawFormatRecord, SourceSnapshot
from registry_builder.normalize import normalize_record
from registry_builder.reconcile import reconcile


def _snapshot(path: Path) -> SourceSnapshot:
    return SourceSnapshot(
        source_id="loc_fdd_pronom_bridge_20260713",
        source_type="loc_fdd_pronom_bridge",
        uri=str(path),
        acquired_at="2026-08-21T00:00:00+00:00",
        sha256="bridge123",
        local_path=str(path),
        content_type="application/json",
    )


def test_bridge_adapter_is_registered():
    assert resolve_adapter("loc_fdd_pronom_bridge") is LocFddPronomBridgeAdapter


def test_policy_approval_selects_only_authority_confirmed_bridge_candidates():
    verification = [
        {
            "source_record_id": "fdd000001:2",
            "title": "WAVE Audio File Format",
            "fdd_id": "fdd000001",
            "puid": "fmt/6",
            "loc_canonical_id": "loc-fdd000001",
            "pronom_canonical_id": "puid-fmt-6",
            "status": "bridge_candidate_authority_confirmed",
        },
        {
            "source_record_id": "fdd000002:3",
            "title": "WAVE Audio File Format with LPCM audio",
            "fdd_id": "fdd000002",
            "puid": "fmt/141",
            "status": "version_scope_review",
        },
    ]
    review = [
        {
            "source_record_id": "fdd000001:2",
            "title": "WAVE Audio File Format",
            "source_url": "https://www.loc.gov/example.csv",
            "snapshot_sha256": "abc",
            "mapping_context": {"PRONOM_Note": "See fmt/6"},
        },
        {
            "source_record_id": "fdd000002:3",
            "title": "WAVE Audio File Format with LPCM audio",
            "snapshot_sha256": "abc",
        },
    ]

    mapping = build_bridge_mapping(verification, review, mapping_date="20260713")

    assert mapping["approved_rule_count"] == 1
    assert mapping["excluded_status_counts"] == {"version_scope_review": 1}
    rule = mapping["rules"][0]
    assert rule["fdd_id"] == "fdd000001"
    assert rule["puid"] == "fmt/6"
    assert rule["review_status"] == "approved_by_policy"
    assert rule["puid_verified"] is False


def test_approved_bridge_keeps_puid_unverified_but_reconciles_with_authorities(tmp_path):
    mapping = {
        "mapping_version": "loc_pronom_direct_single_authority_v1-20260713",
        "mapping_date": "20260713",
        "approval_policy": "loc_pronom_direct_single_authority_v1",
        "rules": [
            {
                "rule_id": "bridge:fdd000001:fmt/6",
                "review_status": "approved_by_policy",
                "title": "WAVE Audio File Format",
                "fdd_id": "fdd000001",
                "puid": "fmt/6",
                "approval_basis": ["authority confirmed"],
                "crosswalk_snapshot_sha256": "abc",
            }
        ],
    }
    path = tmp_path / "approved.json"
    path.write_text(json.dumps(mapping), encoding="utf-8")
    adapter = LocFddPronomBridgeAdapter(
        {"id": "loc_fdd_pronom_bridge_20260713", "type": "loc_fdd_pronom_bridge", "local_file": str(path)},
        tmp_path,
    )
    bridge = normalize_record(adapter.extract([_snapshot(path)])[0])

    claims = {(claim.kind, claim.value): claim.verified for claim in bridge.identifiers}
    assert claims[("loc", "fdd000001")] is True
    assert claims[("puid", "fmt/6")] is False

    loc = normalize_record(RawFormatRecord(
        source_id="loc_fdd_xml",
        source_type="loc_fdd_xml",
        source_record_id="fdd000001",
        name="WAVE Audio File Format",
        identifiers=[Identifier("loc", "fdd000001", "loc_fdd_xml", True, "fdd000001")],
    ))
    pronom = normalize_record(RawFormatRecord(
        source_id="pronom_registry",
        source_type="pronom_registry",
        source_record_id="fmt/6",
        name="WAVE Audio File Format",
        identifiers=[Identifier("puid", "fmt/6", "pronom_registry", True, "fmt/6")],
    ))

    registry = reconcile([loc, pronom, bridge])
    assert len(registry) == 1
    assert registry[0].canonical_id == "puid-fmt-6"
    verified_puids = [
        claim for claim in registry[0].identifier_claims
        if claim.get("kind") == "puid" and claim.get("value") == "fmt/6" and claim.get("verified")
    ]
    copied_puids = [
        claim for claim in registry[0].identifier_claims
        if claim.get("kind") == "puid" and claim.get("value") == "fmt/6" and not claim.get("verified")
    ]
    assert verified_puids
    assert copied_puids
