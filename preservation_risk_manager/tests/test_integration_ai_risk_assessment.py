from types import SimpleNamespace

import preservation_risk_manager.integration_cli as integration_cli


class FakeProvider:
    def describe(self):
        return {"provider": "fake", "model": "fake-model"}


class FakeReader:
    def get_criterion_claims_for_format(self, format_doc, *, institution_id=None):
        assert format_doc["canonical_id"] == "fmt-swf"
        assert institution_id is None
        return [{"canonical_id": "fmt-swf", "criterion_id": "q", "value": "unknown"}]


def test_query_json_parser_accepts_ai_risk_mode_with_identification():
    args = integration_cli._build_parser().parse_args([
        "query-json",
        "--framework", "framework.json",
        "--registry-json", "registry.json",
        "--request", "request.json",
        "--enable-ai-identification",
        "--ai-config", "ai.json",
        "--ai-mode", "fill-gaps",
    ])

    assert args.enable_ai_identification is True
    assert args.ai_mode == "fill-gaps"
    assert args.ai_config == "ai.json"
    assert args.max_ai_evidence_items == 20


def test_ai_risk_assessment_runs_after_canonical_resolution(monkeypatch):
    class FakeResolver:
        def __init__(self, reader):
            self.reader = reader

        def resolve(self, token):
            assert token == "fmt-swf"
            return SimpleNamespace(
                resolved=True,
                format_doc={"canonical_id": "fmt-swf", "preferred_name": "Shockwave Flash"},
            )

    monkeypatch.setattr(integration_cli, "FormatResolver", FakeResolver)
    monkeypatch.setattr(
        integration_cli,
        "build_evidence_pack",
        lambda format_doc, institution_id, criterion_claims: {
            "format": format_doc,
            "scope": "global",
            "global_evidence": criterion_claims,
        },
    )
    monkeypatch.setattr(
        integration_cli,
        "derive_answers",
        lambda framework, pack: {
            "answers": {"q": "unknown"},
            "scoring_answers": {"q": "unknown"},
            "derivation": {"q": {"status": "missing_evidence", "answer_id": "unknown"}},
        },
    )

    ai_called = {"value": False}

    def fake_derive_answers_with_ai(provider, framework, pack, deterministic, *, max_evidence_items):
        ai_called["value"] = True
        assert deterministic["answers"]["q"] == "unknown"
        assert max_evidence_items == 12
        return {
            "answers": {"q": "low_risk"},
            "scoring_answers": {"q": "low_risk"},
            "ai_summary": {"accepted_answers": 1},
            "ai_audit": {"q": {"status": "accepted"}},
        }

    monkeypatch.setattr(integration_cli, "derive_answers_with_ai", fake_derive_answers_with_ai)
    monkeypatch.setattr(
        integration_cli,
        "score_answers",
        lambda framework, answers: {
            "analysed_band": "Low" if answers.get("q") == "low_risk" else None,
            "answer_seen": answers.get("q"),
        },
    )
    monkeypatch.setattr(integration_cli, "evidence_hash", lambda pack: "evidence-hash")

    response = {
        "status": "ok",
        "scope": "global",
        "institution_id": None,
        "result": {"analysis_status": "Not Assessed"},
    }
    output = integration_cli._apply_ai_risk_assessment(
        FakeReader(),
        object(),
        {"action": "assess_format", "format": "fmt-swf", "scope": "global"},
        response,
        provider=FakeProvider(),
        ai_mode="fill-gaps",
        max_evidence_items=12,
    )

    assert ai_called["value"] is True
    assert output["result"]["analysis_status"] == "Not Assessed"
    ai_result = output["ai_risk_assessment"]
    assert ai_result["status"] == "ok"
    assert ai_result["ai_mode"] == "fill-gaps"
    assert ai_result["criterion_claims_used"] == 1
    assert ai_result["deterministic_analysis"]["answer_seen"] == "unknown"
    assert ai_result["analysis"]["answer_seen"] == "low_risk"
    assert ai_result["analysis"]["analysed_band"] == "Low"


def test_ai_risk_failure_retains_deterministic_baseline(monkeypatch):
    class FakeResolver:
        def __init__(self, reader):
            pass

        def resolve(self, token):
            return SimpleNamespace(resolved=True, format_doc={"canonical_id": "fmt-swf"})

    monkeypatch.setattr(integration_cli, "FormatResolver", FakeResolver)
    monkeypatch.setattr(
        integration_cli,
        "build_evidence_pack",
        lambda format_doc, institution_id, criterion_claims: {"format": format_doc, "scope": "global"},
    )
    monkeypatch.setattr(
        integration_cli,
        "derive_answers",
        lambda framework, pack: {"answers": {"q": "unknown"}, "scoring_answers": {"q": "unknown"}},
    )
    monkeypatch.setattr(
        integration_cli,
        "score_answers",
        lambda framework, answers: {"analysed_band": None, "answer_seen": answers.get("q")},
    )
    monkeypatch.setattr(
        integration_cli,
        "derive_answers_with_ai",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("AI unavailable")),
    )

    output = integration_cli._apply_ai_risk_assessment(
        FakeReader(),
        object(),
        {"action": "assess_format", "format": "fmt-swf", "scope": "global"},
        {"status": "ok", "scope": "global", "institution_id": None},
        provider=FakeProvider(),
        ai_mode="fill-gaps",
        max_evidence_items=20,
    )

    ai_result = output["ai_risk_assessment"]
    assert ai_result["status"] == "error_deterministic_retained"
    assert ai_result["deterministic_analysis"]["answer_seen"] == "unknown"
    assert ai_result["error_type"] == "RuntimeError"
