from types import SimpleNamespace

from preservation_risk_manager import integration_cli as base_integration
from preservation_risk_manager.human_format_matches import human_puid_candidates
from preservation_risk_manager.human_renderer_multi import render_human_response
from preservation_risk_manager.integration_cli_human import _assess_human_puid_matches


class FakeReader:
    def __init__(self, rows):
        self.rows = list(rows)

    def list_canonical_formats(self):
        return list(self.rows)


def _pdf_rows():
    return [
        {
            "canonical_id": "fmt-pdf",
            "preferred_name": "PDF",
            "identifiers": {},
        },
        {
            "canonical_id": "nara-pdf14",
            "preferred_name": "PDF 1.4 source copy",
            "identifiers": {"puid": ["fmt/18"]},
        },
        {
            "canonical_id": "puid-fmt-18",
            "preferred_name": "PDF 1.4",
            "identifiers": {"puid": ["fmt/18"]},
        },
        {
            "canonical_id": "puid-fmt-276",
            "preferred_name": "PDF 1.7",
            "identifiers": {"puid": ["fmt/276"]},
        },
        {
            "canonical_id": "puid-fmt-999",
            "preferred_name": "Unrelated Image Format",
            "identifiers": {"puid": ["fmt/999"]},
        },
    ]


def test_generic_human_pdf_name_expands_to_distinct_puids_and_prefers_puid_records():
    reader = FakeReader(_pdf_rows())
    request = {
        "action": "assess_format",
        "format": "PDF",
        "scope": "global",
        "limit": 100,
    }
    identification = {
        "status": "resolved",
        "match_type": "name",
        "resolved_canonical_id": "fmt-pdf",
        "resolved_label": "PDF",
    }

    candidates = human_puid_candidates(reader, request, identification)

    assert [item["puid"] for item in candidates] == ["fmt/18", "fmt/276"]
    assert [item["canonical_id"] for item in candidates] == ["puid-fmt-18", "puid-fmt-276"]


def test_explicit_puid_does_not_use_human_fanout():
    reader = FakeReader(_pdf_rows())
    request = {
        "action": "assess_format",
        "format": "fmt/18",
        "scope": "global",
        "limit": 100,
    }
    identification = {
        "status": "resolved",
        "match_type": "authority_identifier",
        "resolved_canonical_id": "puid-fmt-18",
        "resolved_label": "PDF 1.4",
    }

    assert human_puid_candidates(reader, request, identification) == []


def test_human_ai_ambiguity_assesses_each_distinct_puid(monkeypatch):
    rows = [
        {
            "canonical_id": "puid-fmt-505",
            "preferred_name": "Adobe Flash",
            "version": "8",
            "identifiers": {"puid": ["fmt/505"]},
        },
        {
            "canonical_id": "puid-fmt-506",
            "preferred_name": "Adobe Flash",
            "version": "9",
            "identifiers": {"puid": ["fmt/506"]},
        },
    ]
    reader = FakeReader(rows)
    request = {
        "action": "assess_format",
        "format": "Adobe Flash",
        "scope": "global",
        "institution_id": None,
        "limit": 100,
    }
    identification = {
        "status": "ambiguous",
        "match_type": "ai_candidate_ambiguity",
        "matched_candidates": [
            {"canonical_id": "puid-fmt-505"},
            {"canonical_id": "puid-fmt-506"},
        ],
        "ai": {
            "status": "ambiguous",
            "candidate_canonical_ids": ["puid-fmt-505", "puid-fmt-506"],
        },
    }

    executed = []

    def fake_execute(_reader, _framework, candidate_request):
        executed.append(candidate_request["format"])
        return {
            "status": "ok",
            "request": dict(candidate_request),
            "result": {
                "format": {"format_id": candidate_request["format"], "label": candidate_request["format"]},
                "risk_band": "Moderate",
                "score": 5,
                "max_score": 10,
                "analysis_status": "Complete",
                "evidence_completeness": 1.0,
                "main_risk_factors": [],
                "missing_count": 0,
                "abstention_count": 0,
                "banding_enabled": True,
            },
        }

    monkeypatch.setattr(base_integration, "execute_request", fake_execute)
    monkeypatch.setattr(
        base_integration,
        "_apply_ai_risk_assessment",
        lambda _reader, _framework, _request, response, **kwargs: response,
    )

    framework = SimpleNamespace(
        framework_id="test",
        version="1",
        calibration_status="calibrated",
        banding_enabled=True,
    )
    response = _assess_human_puid_matches(
        reader,
        framework,
        request,
        identification,
        provider=object(),
        ai_mode="off",
        max_evidence_items=20,
    )

    assert response["human_multi_puid_assessment"] is True
    assert response["matched_puids"] == ["fmt/505", "fmt/506"]
    assert executed == ["puid-fmt-505", "puid-fmt-506"]


def test_multi_puid_human_renderer_shows_each_risk_assessment():
    def assessment(puid, label, band):
        return {
            "status": "ok",
            "request": {"action": "assess_format"},
            "matched_puid": puid,
            "matched_label": label,
            "result": {
                "format": {"format_id": puid, "label": label},
                "risk_band": band,
                "score": 5,
                "max_score": 10,
                "analysis_status": "Complete",
                "evidence_completeness": 1.0,
                "main_risk_factors": [],
                "missing_count": 0,
                "abstention_count": 0,
                "banding_enabled": True,
            },
        }

    response = {
        "status": "ok",
        "request": {"action": "assess_format", "format": "PDF"},
        "human_multi_puid_assessment": True,
        "assessments": [
            assessment("fmt/18", "PDF 1.4", "Moderate"),
            assessment("fmt/276", "PDF 1.7", "High"),
        ],
        "identification": {
            "method": "ai_fallback_ambiguous",
            "ai_attempted": True,
            "status": "ambiguous",
            "ai": {"status": "ambiguous", "confidence": 0.91, "rationale": "Multiple PDF versions match."},
        },
    }

    rendered = render_human_response(response)

    assert "2 matched PRONOM PUIDs" in rendered
    assert "fmt/18" in rendered
    assert "PDF 1.4" in rendered
    assert "Moderate" in rendered
    assert "fmt/276" in rendered
    assert "PDF 1.7" in rendered
    assert "High" in rendered
    assert "AI-assisted format identification" in rendered
