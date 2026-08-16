from __future__ import annotations

from preservation_risk_manager.evidence_packs import build_evidence_pack, evidence_hash


FORMAT_RECORD = {
    "canonical_id": "fmt/pdf",
    "format_name": "Portable Document Format",
    "puids": ["fmt/18"],
    "extensions": ["pdf"],
    "mime_types": ["application/pdf"],
    "evidence_claims": [
        {
            "claim_id": "loc-pdf-disclosure",
            "source_id": "loc_fdd",
            "criterion_id": "sustainability.disclosure",
            "value": "openly_documented",
        },
        {
            "claim_id": "draft-claim",
            "source_id": "manual",
            "criterion_id": "sustainability.adoption",
            "value": "unknown",
            "review_status": "draft",
        },
    ],
    "institution_evidence_claims": [
        {
            "claim_id": "qnl-pdf-workflow",
            "institution_id": "qnl",
            "criterion_id": "institution.workflow_integration",
            "value": "covered",
            "review_status": "approved",
        },
        {
            "claim_id": "other-institution-workflow",
            "institution_id": "other",
            "criterion_id": "institution.workflow_integration",
            "value": "uncovered",
            "review_status": "approved",
        },
        {
            "claim_id": "unscoped-workflow",
            "criterion_id": "institution.workflow_integration",
            "value": "covered",
            "review_status": "approved",
        },
    ],
    "migration_pathway_evidence": [
        {
            "pathway_id": "authority-pdf-to-pdfa",
            "source_id": "authority_source",
            "evidence_type": "authority_asserted_pathway",
            "from_format": "fmt/pdf",
            "to_format": "fmt/pdfa",
        }
    ],
    "local_migration_readiness": [
        {
            "readiness_id": "qnl-pdf-to-pdfa-tested",
            "institution_id": "qnl",
            "from_format": "fmt/pdf",
            "to_format": "fmt/pdfa",
            "readiness_status": "tested",
            "review_status": "approved",
        },
        {
            "readiness_id": "other-pdf-to-pdfa-tested",
            "institution_id": "other",
            "from_format": "fmt/pdf",
            "to_format": "fmt/pdfa",
            "readiness_status": "tested",
            "review_status": "approved",
        },
    ],
}


def test_global_evidence_pack_excludes_institution_local_fields():
    pack = build_evidence_pack(FORMAT_RECORD)

    assert pack["scope"] == "global"
    assert pack["format"]["format_id"] == "fmt/pdf"
    assert len(pack["global_evidence"]) == 1
    assert pack["global_evidence"][0]["claim_id"] == "loc-pdf-disclosure"
    assert len(pack["migration_pathway_evidence"]) == 1
    assert "institution_id" not in pack
    assert "institution_evidence" not in pack
    assert "local_migration_readiness" not in pack


def test_institution_pack_filters_evidence_by_institution_id():
    pack = build_evidence_pack(FORMAT_RECORD, institution_id="qnl")

    assert pack["scope"] == "institution"
    assert pack["institution_id"] == "qnl"
    assert [claim["claim_id"] for claim in pack["institution_evidence"]] == ["qnl-pdf-workflow"]
    assert [claim["readiness_id"] for claim in pack["local_migration_readiness"]] == ["qnl-pdf-to-pdfa-tested"]


def test_unscoped_institution_evidence_is_not_used_for_institution_pack():
    pack = build_evidence_pack(FORMAT_RECORD, institution_id="qnl")

    claim_ids = {claim["claim_id"] for claim in pack["institution_evidence"]}
    assert "unscoped-workflow" not in claim_ids


def test_migration_pathway_evidence_and_local_readiness_remain_separate():
    pack = build_evidence_pack(FORMAT_RECORD, institution_id="qnl")

    assert pack["migration_pathway_evidence"][0]["evidence_type"] == "authority_asserted_pathway"
    assert pack["local_migration_readiness"][0]["readiness_status"] == "tested"
    assert "readiness_status" not in pack["migration_pathway_evidence"][0]


def test_evidence_hash_is_stable_across_key_and_list_order():
    pack_a = build_evidence_pack(FORMAT_RECORD, institution_id="qnl")
    reordered = {
        **FORMAT_RECORD,
        "evidence_claims": list(reversed(FORMAT_RECORD["evidence_claims"])),
        "institution_evidence_claims": list(reversed(FORMAT_RECORD["institution_evidence_claims"])),
    }
    pack_b = build_evidence_pack(reordered, institution_id="qnl")

    assert pack_a["evidence_hash"] == pack_b["evidence_hash"]
    assert evidence_hash(pack_a) == pack_a["evidence_hash"]


def test_evidence_hash_changes_when_substantive_evidence_changes():
    pack_a = build_evidence_pack(FORMAT_RECORD, institution_id="qnl")
    changed = {
        **FORMAT_RECORD,
        "institution_evidence_claims": [
            {
                **FORMAT_RECORD["institution_evidence_claims"][0],
                "value": "uncovered",
            }
        ],
    }
    pack_b = build_evidence_pack(changed, institution_id="qnl")

    assert pack_a["evidence_hash"] != pack_b["evidence_hash"]


def test_include_unapproved_allows_draft_evidence_when_requested():
    pack = build_evidence_pack(FORMAT_RECORD, include_unapproved=True)

    claim_ids = {claim["claim_id"] for claim in pack["global_evidence"]}
    assert "draft-claim" in claim_ids


def test_global_pack_adds_only_global_criterion_claims():
    pack = build_evidence_pack(
        FORMAT_RECORD,
        criterion_claims=[
            {"claim_id": "loc-claim", "criterion_id": "sustainability.disclosure", "value": "public_specification"},
            {
                "claim_id": "qnl-claim",
                "institution_id": "qnl",
                "source_independence": "institution_scoped",
                "criterion_id": "sustainability.disclosure",
                "value": "public_specification",
            },
        ],
    )

    claim_ids = {claim.get("claim_id") for claim in pack["global_evidence"]}
    assert "loc-claim" in claim_ids
    assert "qnl-claim" not in claim_ids


def test_institution_pack_adds_global_and_matching_institution_criterion_claims():
    pack = build_evidence_pack(
        FORMAT_RECORD,
        institution_id="qnl",
        criterion_claims=[
            {"claim_id": "loc-claim", "criterion_id": "sustainability.disclosure", "value": "public_specification"},
            {
                "claim_id": "qnl-claim",
                "institution_id": "qnl",
                "source_independence": "institution_scoped",
                "criterion_id": "sustainability.disclosure",
                "value": "public_specification",
            },
            {
                "claim_id": "other-claim",
                "institution_id": "other",
                "source_independence": "institution_scoped",
                "criterion_id": "sustainability.disclosure",
                "value": "public_specification",
            },
        ],
    )

    global_claim_ids = {claim.get("claim_id") for claim in pack["global_evidence"]}
    institution_claim_ids = {claim.get("claim_id") for claim in pack["institution_evidence"]}
    assert "loc-claim" in global_claim_ids
    assert "qnl-claim" in institution_claim_ids
    assert "other-claim" not in global_claim_ids | institution_claim_ids


def test_normalized_criterion_claims_shadow_matching_legacy_institution_evidence():
    record = {
        **FORMAT_RECORD,
        "institution_evidence_claims": [
            {
                "claim_id": "legacy-qnl-netcdf-disclosure",
                "source_id": "qnl_seed",
                "source_record_id": "qnl-evidence-netcdf",
                "institution_id": "qnl",
                "criterion_id": "sustainability.disclosure",
                "evidence_value": "requires_specialist_review",
                "review_status": "approved",
            },
            {
                "claim_id": "legacy-qnl-netcdf-readiness",
                "source_id": "qnl_seed",
                "source_record_id": "qnl-evidence-netcdf",
                "institution_id": "qnl",
                "criterion_id": "institution.workflow_integration",
                "value": "not_covered",
                "review_status": "approved",
            },
        ],
    }

    pack = build_evidence_pack(
        record,
        institution_id="qnl",
        criterion_claims=[
            {
                "source_id": "qnl_seed",
                "source_record_id": "qnl-evidence-netcdf",
                "institution_id": "qnl",
                "source_independence": "institution_scoped",
                "criterion_id": "sustainability.disclosure",
                "value": "unknown",
                "review_status": "approved",
            }
        ],
    )

    claim_ids = {claim.get("claim_id") for claim in pack["institution_evidence"]}
    criteria = {claim.get("criterion_id") for claim in pack["institution_evidence"]}
    assert "legacy-qnl-netcdf-disclosure" not in claim_ids
    assert "institution.workflow_integration" in criteria
    assert sum(1 for claim in pack["institution_evidence"] if claim.get("criterion_id") == "sustainability.disclosure") == 1
