import pytest

from registry_builder.criteria import CriteriaError, CriteriaVocabulary, derive_confidence


CRITERIA = {
    "criteria_version": "v1",
    "criteria": {
        "sustainability.disclosure": {
            "kind": "ordinal",
            "values": ["public_specification", "partial_specification", "undocumented"],
            "null_value": "unknown",
        },
        "technical.container_complexity": {
            "kind": "nominal",
            "values": ["flat", "compound"],
            "null_value": "unknown",
        },
        "source.currency": {
            "kind": "temporal",
            "unit": "days_since_update",
            "null_value": "unknown",
        },
    },
}


def test_criteria_vocabulary_validates_values_and_distance():
    vocab = CriteriaVocabulary(CRITERIA)

    vocab.validate_value("sustainability.disclosure", "public_specification")
    vocab.validate_value("sustainability.disclosure", "unknown")
    assert vocab.ordinal_distance("sustainability.disclosure", "public_specification", "partial_specification") == 1
    assert vocab.ordinal_distance("sustainability.disclosure", "public_specification", "undocumented") == 2
    assert vocab.ordinal_distance("sustainability.disclosure", "unknown", "undocumented") is None


def test_criteria_vocabulary_rejects_unknown_value():
    vocab = CriteriaVocabulary(CRITERIA)

    with pytest.raises(CriteriaError, match="not allowed"):
        vocab.validate_value("sustainability.disclosure", "low_risk")


def test_confidence_is_derived_from_directness_and_independence():
    assert derive_confidence(directness="explicit", source_independence="independent") == "high"
    assert derive_confidence(directness="explicit", source_independence="source_derived") == "medium"
    assert derive_confidence(directness="derived", source_independence="independent") == "medium"
    assert derive_confidence(directness="inferred", source_independence="independent") == "weak"
