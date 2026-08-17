from __future__ import annotations

import json

import pytest

from preservation_risk_manager.ai.base import AIProvider, AIProviderCapabilities, AIResponse
from preservation_risk_manager.ai.review import review_answers_with_ai
from preservation_risk_manager.answer_derivation import derive_answers
from preservation_risk_manager.cli import main
from preservation_risk_manager.data_access import JsonRegistryStore, RegistryReader
from preservation_risk_manager.evidence_packs import build_evidence_pack
from preservation_risk_manager.frameworks import RiskFramework
from preservation_risk_manager.training_corpus import (
    TIER_A,
    TIER_B,
    TIER_C,
    CorpusSettings,
    TrainingCorpusError,
    assign_splits,
    build_input_evidence,
    build_training_corpus,
    generate_examples,
    is_nara_claim,
    run_quality_gates,
    split_formats,
)


FRAMEWORK_DATA = {
    "framework_id": "corpus_test",
    "version": "1.0.0",
    "unknown_answer_id": "unknown",
    "scale": {
        "direction": "higher_is_risk",
        "min_completeness_for_band": 0.5,
        "bands": [
            {"band": "Low", "min_score": 0, "max_score": 2},
            {"band": "High", "min_score": 3, "max_score": 10},
        ],
    },
    "questions": [
        {
            "id": "q_disclosure",
            "label": "Is the specification disclosed?",
            "evidence_fields": ["sustainability.disclosure"],
            "evidence_value_map": {
                "public_specification": "public_specification",
                "undocumented": "limited_or_unclear_specification",
            },
            "answers": [
                {"id": "public_specification", "points": 0},
                {"id": "limited_or_unclear_specification", "points": 3},
                {"id": "unknown", "points": 1, "abstention": True},
            ],
        },
        {
            "id": "q_adoption",
            "label": "How widely adopted is the format?",
            "evidence_fields": ["sustainability.adoption"],
            "evidence_value_map": {"widely_adopted": "widely_adopted", "niche": "niche_or_declining"},
            "answers": [
                {"id": "widely_adopted", "points": 0},
                {"id": "niche_or_declining", "points": 3},
                {"id": "unknown", "points": 1, "abstention": True},
            ],
        },
    ],
}


def _framework() -> RiskFramework:
    return RiskFramework.from_dict(FRAMEWORK_DATA)


def _claim(canonical_id, criterion, value, source_id, source_value, **extra):
    claim = {
        "canonical_id": canonical_id,
        "criterion_id": criterion,
        "value": value,
        "source_id": source_id,
        "source_type": source_id,
        "source_field": f"raw.{criterion}",
        "source_value": source_value,
        # RegistryReader dedupes claims on (canonical_id, criterion, source,
        # source_record_id, ...). Without a distinct record ID two claims from
        # one source collapse into one and never reach the derivation.
        "source_record_id": f"{canonical_id}:{criterion}:{source_id}:{value}",
        "review_status": "approved",
        "current": True,
    }
    claim.update(extra)
    return claim


def _format(canonical_id, name):
    return {"canonical_id": canonical_id, "preferred_name": name, "current": True}


def _registry(format_count: int = 12):
    """Registry where every format carries a NARA label and independent evidence."""
    formats = []
    claims = []
    for index in range(format_count):
        canonical_id = f"fmt-{index:03d}"
        formats.append(_format(canonical_id, f"Format {index}"))
        # Alternating labels keep the answer distribution non-degenerate.
        nara_value = "public_specification" if index % 2 == 0 else "undocumented"
        claims.append(
            _claim(canonical_id, "sustainability.disclosure", nara_value,
                   "nara_digital_preservation_framework", "2")
        )
        claims.append(
            _claim(canonical_id, "sustainability.disclosure", nara_value,
                   "loc_fdd_xml", f"LOC statement {index}")
        )
        # A second criterion, evidenced by both sources, so Tier B has NARA
        # evidence to retain and q_adoption is answerable in its own right.
        adoption = "widely_adopted" if index % 3 else "niche"
        claims.append(
            _claim(canonical_id, "sustainability.adoption", adoption,
                   "nara_digital_preservation_framework", "1")
        )
        claims.append(
            _claim(canonical_id, "sustainability.adoption", adoption,
                   "loc_fdd_xml", f"LOC adoption {index}")
        )
    return formats, claims


def _reader(formats, claims):
    return RegistryReader(
        store=JsonRegistryStore({"canonical_formats": formats, "criterion_claims": claims})
    )


def _settings(**overrides):
    base = {
        "corpus_version": "test",
        "min_test_examples_per_question": 1,
        "abstention_share": 0.12,
        "abstention_tolerance": 0.06,
    }
    base.update(overrides)
    return CorpusSettings(**base)


# --- tier semantics -------------------------------------------------------


def test_is_nara_claim_matches_source_id_and_type():
    assert is_nara_claim({"source_id": "nara_digital_preservation_framework"})
    assert is_nara_claim({"source_type": "NARA_Something"})
    assert not is_nara_claim({"source_id": "loc_fdd_xml"})


def test_tier_a_withholds_every_nara_claim():
    framework = _framework()
    question = framework.question_by_id("q_disclosure")
    _, claims = _registry(1)
    result = build_input_evidence(claims, question, TIER_A)
    assert result
    assert not any(is_nara_claim(claim) for claim in result)


def test_tier_b_withholds_only_this_questions_nara_answer():
    framework = _framework()
    question = framework.question_by_id("q_disclosure")
    _, claims = _registry(1)
    result = build_input_evidence(claims, question, TIER_B)
    nara = [claim for claim in result if is_nara_claim(claim)]
    # NARA's disclosure answer is gone; its adoption answer is retained.
    assert [claim["criterion_id"] for claim in nara] == ["sustainability.adoption"]


def test_tier_c_supplies_no_evidence():
    framework = _framework()
    question = framework.question_by_id("q_disclosure")
    _, claims = _registry(1)
    assert build_input_evidence(claims, question, TIER_C) == []


def test_unknown_tier_is_rejected():
    framework = _framework()
    with pytest.raises(TrainingCorpusError):
        build_input_evidence([], framework.question_by_id("q_disclosure"), "Z")


def test_unknown_tier_rejected_in_settings():
    with pytest.raises(TrainingCorpusError):
        CorpusSettings(corpus_version="v", tiers=("A", "Q"))


# --- prompt fidelity ------------------------------------------------------


class CapturingProvider(AIProvider):
    """Captures the request the inference path would send, then abstains."""

    provider_name = "capture"
    capabilities = AIProviderCapabilities(structured_output=True)

    def __init__(self):
        self.prompts: list[str] = []

    @property
    def model_name(self):
        return "capture-model"

    def generate(self, request):
        self.prompts.append(request.messages[1].content)
        return AIResponse(
            provider=self.provider_name,
            model=self.model_name,
            structured={
                "question_id": json.loads(request.messages[1].content.split("\n\n", 1)[1])["question"]["id"],
                "answer_id": "unknown",
                "confidence": 0.0,
                "rationale": "",
                "evidence_refs": [],
                "uncertainty": "",
            },
        )


def test_corpus_prompt_matches_the_inference_prompt_exactly():
    """A corpus whose prompts drift from review-all trains for the wrong task."""
    framework = _framework()
    formats, claims = _registry(1)
    reader = _reader(formats, claims)
    examples, _ = generate_examples(reader, framework, _settings(tiers=(TIER_A,)))
    example = next(item for item in examples if item.meta["question_id"] == "q_disclosure")

    # Reproduce the same input through the real review-all inference path.
    non_nara = [claim for claim in claims if not is_nara_claim(claim)]
    pack = build_evidence_pack(formats[0], criterion_claims=non_nara)
    provider = CapturingProvider()
    review_answers_with_ai(provider, framework, pack, derive_answers(framework, pack))

    assert example.prompt in provider.prompts


# --- example construction -------------------------------------------------


def test_examples_carry_schema_conformant_targets_and_meta():
    framework = _framework()
    formats, claims = _registry(2)
    reader = _reader(formats, claims)
    examples, stats = generate_examples(reader, framework, _settings(tiers=(TIER_A,)))
    assert examples
    example = examples[0]
    assert set(example.target) == {
        "question_id", "answer_id", "confidence", "rationale", "evidence_refs", "uncertainty",
    }
    assert example.target["evidence_refs"]
    assert 0.0 <= example.target["confidence"] <= 1.0
    assert example.meta["tier"] == TIER_A
    assert example.meta["label_source"] == "nara_rubric"
    assert example.meta["corpus_version"] == "test"
    assert stats["formats_with_labels"] == 2

    record = example.to_record()
    assert [message["role"] for message in record["messages"]] == ["system", "user", "assistant"]
    assert json.loads(record["messages"][2]["content"])["answer_id"] == example.target["answer_id"]


def test_tier_a_examples_never_cite_nara_evidence():
    framework = _framework()
    formats, claims = _registry(6)
    reader = _reader(formats, claims)
    examples, _ = generate_examples(reader, framework, _settings(tiers=(TIER_A,)))
    for example in examples:
        assert not any(source.startswith("nara") for source in example.input_source_ids)
        for citation in example.meta["citations"]:
            assert not str(citation["source_id"]).startswith("nara")


def test_label_requires_a_clean_derivation():
    """A conflicted NARA derivation must not become a label."""
    framework = _framework()
    formats = [_format("fmt-x", "Conflicted")]
    claims = [
        _claim("fmt-x", "sustainability.disclosure", "public_specification",
               "nara_digital_preservation_framework", "2"),
        _claim("fmt-x", "sustainability.disclosure", "undocumented",
               "nara_digital_preservation_framework", "0"),
        _claim("fmt-x", "sustainability.disclosure", "public_specification", "loc_fdd_xml", "LOC"),
    ]
    reader = _reader(formats, claims)
    examples, stats = generate_examples(reader, framework, _settings(tiers=(TIER_A,)))
    assert examples == []
    assert stats["formats_without_nara_label"] == 1


def test_example_is_skipped_when_no_visible_evidence_supports_the_label():
    """Without surviving evidence the example would teach answering from nothing."""
    framework = _framework()
    formats = [_format("fmt-y", "NARA only")]
    claims = [
        _claim("fmt-y", "sustainability.disclosure", "public_specification",
               "nara_digital_preservation_framework", "2"),
    ]
    reader = _reader(formats, claims)
    examples, stats = generate_examples(reader, framework, _settings(tiers=(TIER_A,)))
    assert examples == []
    assert stats["tier_A_rejected"] == 1


def test_tier_b_duplicate_of_tier_a_is_dropped():
    """Leave-one-out earns a row only when it leaves different evidence."""
    framework = _framework()
    formats = [_format("fmt-z", "Only disclosure")]
    claims = [
        _claim("fmt-z", "sustainability.disclosure", "public_specification",
               "nara_digital_preservation_framework", "2"),
        _claim("fmt-z", "sustainability.disclosure", "public_specification", "loc_fdd_xml", "LOC"),
    ]
    reader = _reader(formats, claims)
    examples, stats = generate_examples(reader, framework, _settings(tiers=(TIER_A, TIER_B)))
    assert [example.meta["tier"] for example in examples] == [TIER_A]
    assert stats["tier_B_duplicate_of_tier_a"] == 1


# --- splitting ------------------------------------------------------------


def test_split_is_by_format_and_deterministic():
    ids = [f"fmt-{index:03d}" for index in range(100)]
    first = split_formats(ids, _settings())
    second = split_formats(ids, _settings())
    assert first == second
    assert not first["train"] & first["test"]
    assert not first["train"] & first["val"]
    assert not first["test"] & first["val"]
    assert len(first["test"]) == 15
    assert len(first["val"]) == 10


def test_split_seed_changes_membership():
    ids = [f"fmt-{index:03d}" for index in range(100)]
    assert split_formats(ids, _settings())["test"] != split_formats(ids, _settings(split_seed=7))["test"]


def test_evaluation_splits_contain_only_tier_a():
    framework = _framework()
    formats, claims = _registry(40)
    reader = _reader(formats, claims)
    examples, _ = generate_examples(reader, framework, _settings(tiers=(TIER_A, TIER_B)))
    splits, info = assign_splits(examples, _settings())
    assert all(example.meta["tier"] == TIER_A for example in splits["test"])
    assert all(example.meta["tier"] == TIER_A for example in splits["val"])
    assert info["eval_tier"] == TIER_A


# --- quality gates --------------------------------------------------------


def test_gates_pass_on_a_well_formed_corpus(tmp_path):
    framework = _framework()
    formats, claims = _registry(60)
    reader = _reader(formats, claims)
    result = build_training_corpus(reader, framework, _settings(), tmp_path)
    assert result["status"] == "ok", result["quality_gates"]["failed"]
    assert result["quality_gates"]["passed"] is True


def test_leakage_gate_detects_nara_evidence_in_tier_a():
    framework = _framework()
    formats, claims = _registry(4)
    reader = _reader(formats, claims)
    examples, _ = generate_examples(reader, framework, _settings(tiers=(TIER_A,)))
    examples[0].input_source_ids = ("nara_digital_preservation_framework",)
    splits = {"train": examples, "val": [], "test": []}
    report = run_quality_gates(splits, framework, _settings())
    gate = next(check for check in report["checks"] if check["gate"] == "tier_a_contains_no_nara_evidence")
    assert gate["passed"] is False
    assert gate["detail"]["count"] == 1


def test_citation_gate_detects_unresolvable_reference():
    framework = _framework()
    formats, claims = _registry(4)
    reader = _reader(formats, claims)
    examples, _ = generate_examples(reader, framework, _settings(tiers=(TIER_A,)))
    examples[0].target["evidence_refs"] = ["E999"]
    report = run_quality_gates({"train": examples, "val": [], "test": []}, framework, _settings())
    gate = next(check for check in report["checks"] if check["gate"] == "citations_resolve_to_supplied_evidence")
    assert gate["passed"] is False
    assert gate["detail"]["violations"][0]["refs"] == ["E999"]


def test_degenerate_answer_distribution_fails_the_build():
    """A single-valued question lets a majority-class predictor score perfectly."""
    framework = _framework()
    formats = [_format(f"fmt-{index}", f"F{index}") for index in range(20)]
    claims = []
    for index in range(20):
        claims.append(_claim(f"fmt-{index}", "sustainability.disclosure", "public_specification",
                             "nara_digital_preservation_framework", "2"))
        claims.append(_claim(f"fmt-{index}", "sustainability.disclosure", "public_specification",
                             "loc_fdd_xml", "LOC"))
    reader = _reader(formats, claims)
    examples, _ = generate_examples(reader, framework, _settings(tiers=(TIER_A,)))
    report = run_quality_gates({"train": examples, "val": [], "test": []}, framework, _settings())
    gate = next(check for check in report["checks"] if check["gate"] == "answer_distribution_not_degenerate")
    assert gate["passed"] is False
    assert gate["detail"]["degenerate"]["q_disclosure"]["share"] == 1.0


def test_abstention_only_questions_are_reported_separately():
    """A question with no derivable label is a coverage gap, not a thin sample."""
    framework = _framework()
    formats, claims = _registry(30)
    # Remove NARA adoption claims so q_adoption can never be labelled.
    claims = [claim for claim in claims if claim["criterion_id"] != "sustainability.adoption"]
    reader = _reader(formats, claims)
    settings = _settings()
    result_examples, _ = generate_examples(reader, framework, settings)
    report = run_quality_gates(
        {"train": result_examples, "val": [], "test": result_examples}, framework, settings
    )
    gate = next(
        check for check in report["checks"]
        if check["gate"] == "every_bound_question_has_minimum_test_examples"
    )
    assert "q_adoption" not in gate["detail"]["below_minimum"]


def test_abstention_examples_are_built_and_within_band(tmp_path):
    framework = _framework()
    formats, claims = _registry(60)
    reader = _reader(formats, claims)
    result = build_training_corpus(reader, framework, _settings(), tmp_path)
    assert result["counts"]["by_tier"].get(TIER_C, 0) > 0
    gate = next(
        check for check in result["quality_gates"]["checks"]
        if check["gate"] == "abstention_share_within_band"
    )
    assert gate["passed"] is True
    assert result["construction"]["abstention_built"] == result["construction"]["abstention_target"]


def test_abstention_examples_stay_out_of_evaluation_splits(tmp_path):
    framework = _framework()
    formats, claims = _registry(60)
    reader = _reader(formats, claims)
    build_training_corpus(reader, framework, _settings(), tmp_path)
    for split in ("test", "val"):
        rows = [json.loads(line) for line in (tmp_path / "test" / f"{split}.jsonl").read_text().splitlines()]
        assert all(row["meta"]["tier"] == TIER_A for row in rows)


# --- outputs and CLI ------------------------------------------------------


def test_build_writes_versioned_outputs(tmp_path):
    framework = _framework()
    formats, claims = _registry(60)
    reader = _reader(formats, claims)
    result = build_training_corpus(reader, framework, _settings(corpus_version="2026-09"), tmp_path)
    out = tmp_path / "2026-09"
    assert (out / "train.jsonl").is_file()
    assert (out / "val.jsonl").is_file()
    assert (out / "test.jsonl").is_file()
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["corpus_version"] == "2026-09"
    assert manifest["evidence_view"] == "raw_source_only"
    assert manifest["counts"]["total"] == result["counts"]["total"]
    report = json.loads((out / "leakage_report.json").read_text())
    assert {check["gate"] for check in report["checks"]} >= {
        "tier_a_contains_no_nara_evidence",
        "citations_resolve_to_supplied_evidence",
        "no_format_in_two_splits",
    }


def test_records_never_leak_meta_into_the_model_messages(tmp_path):
    framework = _framework()
    formats, claims = _registry(20)
    reader = _reader(formats, claims)
    build_training_corpus(reader, framework, _settings(), tmp_path)
    rows = [json.loads(line) for line in (tmp_path / "test" / "train.jsonl").read_text().splitlines()]
    assert rows
    for row in rows:
        assert set(row) == {"messages", "meta"}
        for message in row["messages"]:
            assert "corpus_version" not in message["content"]
            assert "label_source" not in message["content"]


def test_cli_builds_corpus_and_reports_gate_failure(tmp_path, capsys):
    framework_path = tmp_path / "framework.json"
    framework_path.write_text(json.dumps(FRAMEWORK_DATA), encoding="utf-8")
    formats, claims = _registry(60)
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps({"canonical_formats": formats, "criterion_claims": claims}), encoding="utf-8"
    )
    exit_code = main([
        "build-training-corpus",
        "--framework", str(framework_path),
        "--registry-json", str(registry_path),
        "--out", str(tmp_path / "corpus"),
        "--corpus-version", "2026-09",
        "--min-test-examples-per-question", "1",
        "--abstention-tolerance", "0.06",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "ok"
    assert (tmp_path / "corpus" / "2026-09" / "manifest.json").is_file()


def test_cli_fails_the_build_when_a_gate_is_violated(tmp_path, capsys):
    """A degenerate corpus must exit non-zero rather than be trained on."""
    framework_path = tmp_path / "framework.json"
    framework_path.write_text(json.dumps(FRAMEWORK_DATA), encoding="utf-8")
    formats = [_format(f"fmt-{index}", f"F{index}") for index in range(40)]
    claims = []
    for index in range(40):
        claims.append(_claim(f"fmt-{index}", "sustainability.disclosure", "public_specification",
                             "nara_digital_preservation_framework", "2"))
        claims.append(_claim(f"fmt-{index}", "sustainability.disclosure", "public_specification",
                             "loc_fdd_xml", "LOC"))
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps({"canonical_formats": formats, "criterion_claims": claims}), encoding="utf-8"
    )
    exit_code = main([
        "build-training-corpus",
        "--framework", str(framework_path),
        "--registry-json", str(registry_path),
        "--out", str(tmp_path / "corpus"),
        "--corpus-version", "bad",
        "--min-test-examples-per-question", "1",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["status"] == "quality_gates_failed"
    assert "answer_distribution_not_degenerate" in payload["quality_gates"]["failed"]
    # The corpus is still written so a failed build can be inspected.
    assert (tmp_path / "corpus" / "bad" / "leakage_report.json").is_file()


def test_cli_rejects_an_unknown_tier(tmp_path):
    framework_path = tmp_path / "framework.json"
    framework_path.write_text(json.dumps(FRAMEWORK_DATA), encoding="utf-8")
    with pytest.raises(SystemExit):
        main([
            "build-training-corpus",
            "--framework", str(framework_path),
            "--registry-json", str(tmp_path / "registry.json"),
            "--out", str(tmp_path / "corpus"),
            "--corpus-version", "v",
            "--tiers", "A,Z",
        ])
