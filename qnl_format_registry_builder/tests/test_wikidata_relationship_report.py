from registry_builder.wikidata_relationship_report import compact_relationship_report


def test_compact_relationship_report_excludes_large_record_arrays():
    result = {
        "status": "ok",
        "preview_version": "preview-v1",
        "projection_version": "projection-v1",
        "read_only": True,
        "canonical_formats": 3372,
        "wikidata_records": 15479,
        "wikidata_qids_with_relationships": 2000,
        "canonical_formats_with_wikidata_relationships": 1800,
        "relationship_edges": 2400,
        "matched_authority_claims": 2500,
        "matched_authority_claims_by_kind": {"puid": 2000, "loc": 250, "nara": 250},
        "unmatched_authority_claims": 20,
        "unmatched_authority_claims_by_kind": {"puid": 10, "loc": 5, "nara": 5},
        "qid_outcomes": {"single_target_cross_reference": 1800},
        "qids_with_relationships_by_wikidata_role": {"format": 1700},
        "identity_merges_performed": 0,
        "canonical_formats_created": 0,
        "canonical_identifiers_promoted": 0,
        "risk_assessments_generated": 0,
        "criterion_claims_generated": 0,
        "mongo_writes": 0,
        "relationships": [{"very": "large"}],
        "records": [{"very": "large"}],
        "multi_target_samples": [{"large": "sample"}],
    }

    summary = compact_relationship_report(result)

    assert summary["canonical_formats"] == 3372
    assert summary["wikidata_records"] == 15479
    assert summary["mongo_writes"] == 0
    assert "relationships" not in summary
    assert "records" not in summary
    assert "multi_target_samples" not in summary
