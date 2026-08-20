from pathlib import Path

from registry_builder.criteria import load_criteria
from registry_builder.criterion_mapping import load_mapping, validate_mapping


ROOT = Path(__file__).resolve().parents[1]
MAPPING_DIR = ROOT / "config" / "criterion_mappings"


def _criteria():
    return load_criteria(ROOT / "config" / "criteria" / "v1.json")


def test_full_nara_draft_mapping_config_validates_against_criteria_vocabulary():
    criteria = _criteria()
    mapping = load_mapping(MAPPING_DIR / "nara_digital_preservation_framework.v1.draft.json")

    errors, warnings = validate_mapping(mapping, criteria)

    assert errors == []
    assert warnings == []
    assert len(mapping["maps"]) == 27
    assert {rule["mapping_status"] for rule in mapping["maps"]} == {"needs_review"}


def test_short_nara_approved_mapping_example_validates_against_criteria_vocabulary():
    criteria = _criteria()
    mapping = load_mapping(MAPPING_DIR / "nara_digital_preservation_framework.v1.approved.json")

    errors, warnings = validate_mapping(mapping, criteria)

    assert errors == []
    assert warnings == []
    assert mapping["review_status"] == "approved"
    assert mapping["claim_review_status"] == "approved"
    assert 1 <= len(mapping["maps"]) < 27
    assert {rule["mapping_status"] for rule in mapping["maps"]} == {"accepted"}
    assert all(rule.get("decided_by") for rule in mapping["maps"])
    assert all(rule.get("decided_at") for rule in mapping["maps"])


def test_nara_mapping_keeps_conclusions_and_decisions_out_of_criterion_rules():
    mapping = load_mapping(MAPPING_DIR / "nara_digital_preservation_framework.v1.draft.json")

    mapped_fields = {rule["from_field"] for rule in mapping["maps"]}
    forbidden_fragments = [
        "Risk Level",
        "Numeric Risk Rating",
        "NARA TOTAL",
        "TOTAL Disclosure Score",
        "TOTAL Adoption Score",
        "TOTAL Transparency Score",
        "TOTAL Self-Documentation Score",
        "TOTAL External Hardware Dependencies Score",
        "TOTAL External Software Dependencies Score",
        "TOTAL Impact of Patents Score",
        "TOTAL Technical Protection Mechanisms Score",
        "Preservation Action",
        "Proposed Preservation Plan",
        "Preferred Processing and Transformation Tool",
        "Transfer Guidance",
        "Feasibility Score",
    ]

    assert all(
        fragment not in field
        for field in mapped_fields
        for fragment in forbidden_fragments
    )
    excluded_fields = {item["field"] for item in mapping.get("excluded_from_criteria", [])}
    assert "Risk Level" in excluded_fields
    assert "TOTAL Numeric Risk Rating" in excluded_fields
    assert "NARA Preservation Action" in excluded_fields
    assert "Feasibility Score" in excluded_fields


def test_labeled_rules_never_read_a_numeric_rubric_value():
    """The rules must not silently keep working against the numbered view.

    Numeric keys would still *match* numbered input and quietly reintroduce the
    Unknown fusion, so their absence is the guard.
    """
    import json
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "config" / "criterion_mappings"
    for name in ("nara_digital_preservation_framework.v1.draft.json",
                 "nara_digital_preservation_framework.v1.approved.json"):
        mapping = json.loads((root / name).read_text(encoding="utf-8"))
        for rule in mapping["maps"]:
            numeric = [k for k in (rule.get("values") or {}) if re.fullmatch(r"-\d+", str(k))]
            assert not numeric, f"{name}:{rule['id']} still maps numeric rubric values {numeric}"


def test_every_labeled_rule_treats_unassessed_markers_as_unknown():
    """An answer NARA did not decide must never become a finding.

    NARA writes three markers for a cell it did not decide: `Unknown`, `0` (the
    labeled view's unassessed marker, written as FALSE in the numbered view) and
    `FALSE` itself in older exports.

    `N/A` is deliberately excluded. It is not an unassessed marker: most of the
    questions carrying it are conditional ("If the format requires compression,
    can it be lossy?"), where "not applicable" is a real and informative answer.
    """
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "config" / "criterion_mappings"
    for name in ("nara_digital_preservation_framework.v1.draft.json",
                 "nara_digital_preservation_framework.v1.approved.json"):
        mapping = json.loads((root / name).read_text(encoding="utf-8"))
        for rule in mapping["maps"]:
            if rule.get("nara_question_id") == "1.4":
                continue  # reads a recomputed age bracket, not raw rubric labels
            values = rule.get("values") or {}
            for marker in ("Unknown", "0", "FALSE"):
                assert values.get(marker) == "unknown", (
                    f"{name}:{rule['id']} maps {marker!r} to {values.get(marker)!r}, "
                    "so an unassessed answer would read as a decision"
                )


def test_not_applicable_is_only_a_real_answer_on_conditional_questions():
    """Where N/A means something other than unknown, the question must warrant it."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "config" / "criterion_mappings"
    mapping = json.loads(
        (root / "nara_digital_preservation_framework.v1.draft.json").read_text(encoding="utf-8")
    )
    for rule in mapping["maps"]:
        value = (rule.get("values") or {}).get("N/A")
        if not value or value == "unknown":
            continue
        question = rule.get("from_field", "")
        conditional = ": If " in question or ", if " in question.lower()
        non_committal = value in {"not_applicable", "none_or_not_applicable", "limited_or_unknown"}
        assert conditional or non_committal, (
            f"{rule['id']} reads N/A as {value!r} on a question that is neither conditional "
            "nor answered non-committally"
        )


def test_provisional_mapping_does_not_claim_reviewed_approval():
    """Promoted-but-unreviewed rules must be distinguishable from reviewed ones.

    The approved mapping carries a real committee attribution. Rules promoted to
    unblock work have not been through that review, so they must not inherit it:
    their claims are emitted as `unreviewed`, which downstream still consumes but
    can filter or re-examine before a decision rests on them.
    """
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "config" / "criterion_mappings"
    approved = json.loads((root / "nara_digital_preservation_framework.v1.approved.json").read_text(encoding="utf-8"))
    provisional = json.loads((root / "nara_digital_preservation_framework.v1.provisional.json").read_text(encoding="utf-8"))

    assert provisional["claim_review_status"] == "unreviewed"
    assert provisional["decided_by"] != approved["decided_by"]

    reviewed_questions = {rule.get("nara_question_id") for rule in approved["maps"]}
    by_status = {"approved": set(), "unreviewed": set()}
    for rule in provisional["maps"]:
        status = rule.get("claim_review_status") or provisional["claim_review_status"]
        by_status.setdefault(status, set()).add(rule.get("nara_question_id"))

    # Exactly the genuinely reviewed questions keep approved status.
    assert by_status["approved"] == reviewed_questions
    assert by_status["unreviewed"] == {
        rule.get("nara_question_id") for rule in provisional["maps"]
    } - reviewed_questions
    for rule in provisional["maps"]:
        if rule.get("nara_question_id") in reviewed_questions:
            assert rule.get("decided_by") == approved["decided_by"]
        else:
            assert "decided_by" not in rule
