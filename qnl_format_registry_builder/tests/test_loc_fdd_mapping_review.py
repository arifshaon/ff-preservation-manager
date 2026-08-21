from registry_builder.loc_fdd_mapping_review import classify_entry, review_entries


def _entry(*, puids=None, qids=None, pronom_value="", pronom_note="", qid_value="", qid_note=""):
    return {
        "source_record_id": "fdd000001:2",
        "title": "Example Format",
        "fdd_ids": ["fdd000001"],
        "puids": puids or [],
        "wikidata_qids": qids or [],
        "mapping_context": {
            **({"PRONOM_Note": pronom_note} if pronom_note else {}),
            **({"Wikidata_Note": qid_note} if qid_note else {}),
        },
        "raw_row": {
            "PRONOM_PUID": pronom_value,
            "Wikidata_Title_ID": qid_value,
        },
    }


def test_clean_single_direct_mapping_is_candidate_not_approved_identity():
    reviewed = classify_entry(
        _entry(
            puids=["fmt/6"],
            qids=["Q217570"],
            pronom_value="fmt/6",
            pronom_note="See https://www.nationalarchives.gov.uk/PRONOM/fmt/6.",
            qid_value="Q217570",
            qid_note="See https://www.wikidata.org/wiki/Q217570.",
        )
    )
    assert reviewed["mapping_review"]["pronom"]["status"] == "direct_single_candidate"
    assert reviewed["mapping_review"]["wikidata"]["status"] == "direct_single_candidate"
    assert reviewed["mapping_review"]["pronom"]["identity_bridge_approved"] is False


def test_multiple_direct_puids_require_review():
    reviewed = classify_entry(
        _entry(
            puids=["fmt/414", "x-fmt/135", "x-fmt/136"],
            pronom_value="fmt/414; x-fmt/135; x-fmt/136",
            pronom_note="See PRONOM entries for multiple AIFF variants.",
        )
    )
    assert reviewed["mapping_review"]["pronom"]["status"] == "direct_multiple_review"


def test_note_only_non_equivalent_pronom_reference_is_contextual_only():
    reviewed = classify_entry(
        _entry(
            pronom_value="See note",
            pronom_note="Pronom's fmt/141 covers PCMWAVFORMAT but this is not precisely the same as LPCM WAV",
        )
    )
    result = reviewed["mapping_review"]["pronom"]
    assert result["status"] == "contextual_only"
    assert "not precisely" in result["review_signals"]
    assert result["identifiers"] == []


def test_explicit_no_match_is_no_mapping():
    reviewed = classify_entry(
        _entry(
            pronom_value="See note.",
            pronom_note="PRONOM has no corresponding entry as of March 2024.",
        )
    )
    assert reviewed["mapping_review"]["pronom"]["status"] == "no_mapping"


def test_single_direct_identifier_with_granularity_warning_requires_review():
    reviewed = classify_entry(
        _entry(
            puids=["fmt/353"],
            pronom_value="fmt/353",
            pronom_note="PRONOM does not distinguish TIFF versions.",
        )
    )
    assert reviewed["mapping_review"]["pronom"]["status"] == "direct_single_review"


def test_review_summary_never_approves_identity_bridges():
    reviewed, summary = review_entries(
        [
            _entry(puids=["fmt/6"], pronom_value="fmt/6"),
            _entry(puids=["fmt/1", "fmt/2"], pronom_value="fmt/1; fmt/2"),
        ]
    )
    assert len(reviewed) == 2
    assert summary["identity_bridges_approved"] == 0
    assert summary["review_policy"] == "classification_only_no_identity_projection"
