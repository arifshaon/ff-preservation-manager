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


def test_report_artifacts_include_csv_json_and_zip(tmp_path):
    response = {
        "status": "ok",
        "result": {
            "format": {"format_id": "puid-fmt-18", "label": "PDF 1.4", "puids": ["fmt/18"]},
            "risk_band": "Moderate",
            "analysis_status": "Assessed",
            "score": 4,
            "max_score": 10,
            "evidence_completeness": 1.0,
            "missing_count": 0,
            "abstention_count": 0,
            "criterion_claims_used": 3,
        },
    }
    report = report_document(
        framework={"framework_id": "test", "version": "1"},
        scope="global",
        institution_id=None,
        ai_mode="off",
        items=[{"input_format_id": "fmt/18", "resolved_puid": "fmt/18", "response": response}],
    )
    paths = write_report_artifacts(report, tmp_path)

    assert set(paths) == {"csv", "json", "zip"}
    loaded = json.loads((tmp_path / paths["json"]).read_text(encoding="utf-8"))
    assert loaded["input_count"] == 1
    assert loaded["summary"][0]["deterministic_risk_band"] == "Moderate"
    assert "fmt/18" in (tmp_path / paths["csv"]).read_text(encoding="utf-8-sig")
    with zipfile.ZipFile(tmp_path / paths["zip"]) as archive:
        assert sorted(archive.namelist()) == ["risk-report.csv", "risk-report.json"]
