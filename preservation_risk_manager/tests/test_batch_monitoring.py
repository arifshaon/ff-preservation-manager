from types import SimpleNamespace

import preservation_risk_manager.batch_monitoring as batch_monitoring


class _Framework:
    framework_id = "test-framework"
    version = "1"
    calibration_status = "draft_unvalidated"
    banding_enabled = False


class _Resolution:
    def __init__(self, token):
        self.format_doc = {
            "canonical_id": "puid-" + token.replace("/", "-"),
            "preferred_name": "Format " + token,
            "puids": [token],
        }
        self.resolved = True


class _Identification:
    def __init__(self, token):
        self.resolved = True
        self.resolution = _Resolution(token)

    def to_dict(self):
        return {"status": "resolved"}


class _Resolver:
    def __init__(self, reader, plugin=None):
        pass

    def resolve(self, token):
        return _Identification(token)


def _governed_response(token):
    governed = {
        "assessed": True,
        "semantic_level": "low",
        "semantic_label": "Low concern",
        "selected_scope_types": ["exact_format"],
        "contributors": [{"source_label": "NARA", "semantic_level": "low", "scope_type": "exact_format"}],
        "contextual_contributors": [],
    }
    return {
        "status": "ok",
        "result": {
            "format": {"format_id": "puid-" + token.replace("/", "-"), "label": "Format " + token, "puids": [token]},
            "analysis_status": "Partially Assessed",
            "evidence_completeness": 0.5,
            "external_risk_context": {"policy_synthesized_risk": governed},
        },
    }


def test_batch_off_uses_governed_database_result_without_ai(monkeypatch):
    monkeypatch.setattr(batch_monitoring, "IdentificationResolver", _Resolver)
    monkeypatch.setattr(
        batch_monitoring.base,
        "execute_request",
        lambda reader, framework, request: _governed_response(request["format"].replace("puid-", "").replace("fmt-", "fmt/")),
    )
    monkeypatch.setattr(
        batch_monitoring.base,
        "_apply_ai_risk_assessment",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("AI must not run in off mode")),
    )

    report = batch_monitoring.run_batch_assessment(
        reader=object(),
        framework=_Framework(),
        format_ids=["fmt/18", "", "fmt/19"],
        ai_mode="off",
    )

    assert report["input_count"] == 2
    assert [row["input_format_id"] for row in report["summary"]] == ["fmt/18", "fmt/19"]
    assert all(row["governed_risk_level"] == "low" for row in report["summary"])
    assert all(row["ai_risk_level"] is None for row in report["summary"])


def test_batch_synthesize_keeps_governed_and_adds_ai_result(monkeypatch):
    monkeypatch.setattr(batch_monitoring, "IdentificationResolver", _Resolver)

    def execute(reader, framework, request):
        token = request["format"].replace("puid-", "").replace("fmt-", "fmt/")
        return _governed_response(token)

    calls = []

    def apply_ai(reader, framework, request, response, **kwargs):
        calls.append((request["format"], kwargs["ai_mode"]))
        response = dict(response)
        response["ai_synthesis"] = {
            "status": "ok",
            "overall_synthesized_risk": {
                "semantic_level": "moderate",
                "semantic_label": "Moderate concern",
                "confidence": 0.75,
                "governed_baseline_relation": "higher_concern",
                "quality_warnings": [],
            },
            "external_capability": {"web_search_used": False, "sources": []},
        }
        response["ai_risk_assessment"] = {"status": "synthesis_only", "ai_mode": "synthesize"}
        return response

    monkeypatch.setattr(batch_monitoring.base, "execute_request", execute)
    monkeypatch.setattr(batch_monitoring.base, "_apply_ai_risk_assessment", apply_ai)

    report = batch_monitoring.run_batch_assessment(
        reader=object(),
        framework=_Framework(),
        format_ids=["fmt/276"],
        ai_mode="synthesize",
        provider=object(),
    )

    assert calls == [("puid-fmt-276", "synthesize")]
    row = report["summary"][0]
    assert row["governed_risk_level"] == "low"
    assert row["ai_risk_level"] == "moderate"
    assert row["ai_confidence"] == 0.75
    assert row["ai_relation_to_governed"] == "higher_concern"
