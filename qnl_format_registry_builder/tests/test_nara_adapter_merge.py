from __future__ import annotations

from pathlib import Path

from registry_builder.adapters.nara_digital_preservation_framework import NaraDigitalPreservationFrameworkAdapter
from registry_builder.models import SourceSnapshot


def _snapshot(path: Path, *, kind: str) -> SourceSnapshot:
    return SourceSnapshot(
        source_id="nara_digital_preservation_framework",
        source_type="nara_digital_preservation_framework",
        uri=str(path),
        acquired_at="2026-08-17T00:00:00+00:00",
        sha256=f"sha-{kind}",
        local_path=str(path),
        changed=False,
        from_cache=False,
        metadata={
            "kind": kind,
            "release_mode": "pinned",
            "release_date": "20260320",
            "source_location": "local_file",
        },
    )


def test_nara_extract_merges_action_plan_and_risk_matrix_rows_by_format_id(tmp_path):
    action_csv = tmp_path / "NARA_PreservationActionPlan_FileFormats_20260320.csv"
    risk_csv = tmp_path / "NARA_File_Format_Risk_Matrix_20260320_Numbered.csv"

    action_csv.write_text(
        "NARA Format ID,Format Name,File Extension(s),MIME type(s),NARA Preservation Action,NARA Proposed Preservation Plan,NARA Preferred Processing and Transformation Tool(s)\n"
        "NF00001,Example Format,ex,application/example,Transform,Plan A,Tool A\n",
        encoding="utf-8",
    )
    risk_csv.write_text(
        "NARA Format ID,Format Name,File Extension(s),MIME type(s),NARA Risk Level,Numeric Risk Rating,1.2: Does the format have a published open specification?,3.2: Is there an internal signature in an authoritative format registry that can be used to identify a file in this format?\n"
        "NF00001,Example Format,ex,application/example,Low,25,2,2\n",
        encoding="utf-8",
    )

    adapter = NaraDigitalPreservationFrameworkAdapter(
        {"id": "nara_digital_preservation_framework"},
        tmp_path,
    )

    records = adapter.extract([
        _snapshot(action_csv, kind="preservation_action_plan"),
        _snapshot(risk_csv, kind="risk_matrix_numbered"),
    ])

    assert len(records) == 1
    record = records[0]
    assert record.source_record_id == "NF00001"
    assert record.name == "Example Format"
    assert record.hazard["band"] == "Low"
    assert record.native_fields["primary_nara_file_kind"] == "risk_matrix_numbered"
    assert record.native_fields["nara_file_kinds"] == ["preservation_action_plan", "risk_matrix_numbered"]
    assert record.native_fields["rubric_answers"] == {"1.2": "2", "3.2": "2"}
    assert record.raw["row"]["NARA Preservation Action"] == "Transform"
    assert record.raw["row"]["1.2: Does the format have a published open specification?"] == "2"
    assert sorted(record.raw["rows_by_kind"]) == ["preservation_action_plan", "risk_matrix_numbered"]
    assert len(record.evidence) == 2
