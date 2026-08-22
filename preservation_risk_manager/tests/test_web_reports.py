import json
import zipfile

from preservation_risk_manager.web_reports import (
    combine_format_id_inputs,
    parse_format_ids,
    report_document,
    write_report_artifacts,
)


def test_parse_format_ids_accepts_text_csv_and_deduplicates():
    assert parse_format_ids('fmt/18\n[fmt 19]\n"x-fmt 123"\nfmt/18') == [
        "fmt/18",
        "fmt/19",
        "x-fmt/123",
    ]

    csv_text = "name,puid,notes\nPDF 1.4,fmt/18,test\nPDF 1.5,fmt/19,test\nPDF duplicate,fmt/18,test\n"
    assert parse_format_ids(csv_text, filename="formats.csv") == ["fmt/18", "fmt/19"]

    combined = combine_format_id_inputs(
        entered_text="fmt/18\nfmt/20",
        uploaded_text=csv_text,
        uploaded_filename="formats.csv",
    )
    assert combined == ["fmt/18", "fmt/20", "fmt/19"]


def _response_with_governed_and_ai():
    governed = {
        "assessed": True,
        "semantic_level": "low",
        "semantic_label": "Low concern",
        "selected_scope_types": ["exact_format"],
        "contributors": [
            {"source_label": "NARA", "source_id": "nara", "scope_type": "exact_format", "native_label": "Low Risk", "semantic_level": "low"}
        ],
        "contextual_contributors": [
            {"source_label": "DPC", "source_id": "dpc", "scope_type": "format_group", "native_label": "Vulnerable", "semantic_level": "moderate"}
        ],
        "unmapped_assessments": [],
    }
    ai = {
        "assessed": True,
        "semantic_level": "low",
        "semantic_label": "Low concern",
        "confidence": 0.82,
        "governed_baseline_relation": "same",
        "rationale": "The exact-format evidence supports Low concern.",
        "uncertainty": "Broader PDF risks remain contextual.",
        "quality_warnings": [],
        "considerations": [
            {"finding": "NARA rates the exact format Low.", "basis": "registry_evidence", "risk_effect": "reduces_concern"}
        ],
    }
    return {
        "status": "ok",
        "result": {
            "format": {"format_id": "puid-fmt-18", "label": "PDF 1.4", "puids": ["fmt/18"]},
            "risk_band": None,
            "analysis_status": "Partially Assessed",
            "evidence_completeness": 0.7,
            "missing_count": 3,
            "criterion_claims_used": 3,
            "external_risk_context": {
                "policy_synthesized_risk": governed,
                "assessments": governed["contributors"] + governed["contextual_contributors"],
            },
        },
        "ai_synthesis": {
            "status": "ok",
            "overall_synthesized_risk": ai,
            "external_capability": {
                "web_search_used": True,
                "sources": [{"ref": "W001", "url": "https://example.org/pdf", "title": "PDF source"}],
            },
        },
        "ai_risk_assessment": {"status": "synthesis_only", "ai_mode": "synthesize"},
    }


def test_report_artifacts_include_curator_html_csv_json_and_zip(tmp_path):
    response = _response_with_governed_and_ai()
    report = report_document(
        framework={"framework_id": "test", "version": "1"},
        scope="global",
        institution_id=None,
        ai_mode="synthesize",
        items=[{"input_format_id": "fmt/18", "resolved_puid": "fmt/18", "response": response}],
    )
    paths = write_report_artifacts(report, tmp_path)

    assert set(paths) == {"html", "csv", "json", "zip"}
    loaded = json.loads((tmp_path / paths["json"]).read_text(encoding="utf-8"))
    assert loaded["input_count"] == 1
    row = loaded["summary"][0]
    assert row["governed_risk_level"] == "low"
    assert row["governed_selected_scope"] == "exact_format"
    assert row["governed_headline_sources"] == "NARA"
    assert row["governed_context_sources"] == "DPC"
    assert row["ai_risk_level"] == "low"
    assert row["ai_confidence"] == 0.82
    assert row["ai_relation_to_governed"] == "same"
    assert row["ai_web_search_used"] is True
    assert row["framework_evidence_completeness_pct"] == 70.0
    assert "fmt/18" in (tmp_path / paths["csv"]).read_text(encoding="utf-8-sig")
    html = (tmp_path / paths["html"]).read_text(encoding="utf-8")
    assert "Governed risk" in html
    assert "AI-assisted risk" in html
    assert "NARA" in html
    assert "https://example.org/pdf" in html
    with zipfile.ZipFile(tmp_path / paths["zip"]) as archive:
        assert sorted(archive.namelist()) == ["risk-report.csv", "risk-report.html", "risk-report.json"]
