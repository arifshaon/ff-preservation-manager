from __future__ import annotations

import json

from registry_builder.adapters.qnl_institution_format_evidence import QnlInstitutionFormatEvidenceAdapter
from registry_builder.normalize import normalize_record
from registry_builder.pipeline import run_pipeline
from registry_builder.storage.file import FileRegistryStore


def _write_qnl_evidence(path):
    path.write_text(
        json.dumps(
            {
                "schema_version": "0.1.0",
                "criterion_set": "qnl_preservation_sustainability_criteria_0.1",
                "institution_id": "qnl",
                "institution_name": "Qatar National Library",
                "records": [
                    {
                        "source_record_id": "qnl-evidence-pdf",
                        "format": {
                            "name": "PDF",
                            "category": "Document",
                            "puids": ["fmt/18"],
                            "loc_ids": ["fdd000030"],
                            "extensions": ["pdf"],
                            "mime_types": ["application/pdf"],
                        },
                        "claims": [
                            {
                                "criterion_group": "institution",
                                "criterion_id": "institution.workflow_integration",
                                "evidence_value": "integrated",
                                "risk_direction": "lowers_risk",
                                "statement": "PDF is integrated into QNL preservation workflows.",
                                "date_observed": "2026-08-15",
                            }
                        ],
                    },
                    {
                        "source_record_id": "qnl-evidence-netcdf",
                        "format": {
                            "name": "netCDF",
                            "category": "Dataset",
                            "extensions": ["nc", "cdf"],
                            "mime_types": ["application/x-netcdf"],
                        },
                        "claims": [
                            {
                                "criterion_group": "institution",
                                "criterion_id": "institution.staff_expertise",
                                "evidence_value": "no_current_institutional_expertise",
                                "risk_direction": "raises_risk_for_qnl",
                                "statement": "QNL does not currently have institutional expertise for netCDF.",
                                "date_observed": "2026-08-15",
                            }
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def test_qnl_institution_format_evidence_extracts_claims(tmp_path):
    source_path = tmp_path / "qnl_evidence.json"
    _write_qnl_evidence(source_path)
    adapter = QnlInstitutionFormatEvidenceAdapter(
        {
            "id": "qnl_institution_format_evidence_2026_seed",
            "type": "qnl_institution_format_evidence",
            "uris": [str(source_path)],
        },
        tmp_path / "work",
    )

    snapshots = adapter.acquire()
    records = [normalize_record(record) for record in adapter.extract(snapshots)]

    assert len(records) == 2
    pdf = next(record for record in records if record.source_record_id == "qnl-evidence-pdf")
    assert pdf.name == "PDF"
    assert pdf.puids == ["fmt/18"]
    assert pdf.loc_ids == ["fdd000030"]
    assert pdf.extensions == ["pdf"]
    assert pdf.mime_types == ["application/pdf"]
    assert len(pdf.institution_evidence) == 1
    assert pdf.institution_evidence[0]["institution_id"] == "qnl"
    assert pdf.institution_evidence[0]["derived_by"] == "human"
    assert pdf.institution_evidence[0]["review_status"] == "approved"
    assert pdf.institution_evidence[0]["criterion_id"] == "institution.workflow_integration"

    netcdf = next(record for record in records if record.source_record_id == "qnl-evidence-netcdf")
    assert netcdf.name == "netCDF"
    assert netcdf.extensions == ["cdf", "nc"]
    assert netcdf.institution_evidence[0]["evidence_value"] == "no_current_institutional_expertise"
    assert netcdf.institution_evidence[0]["risk_direction"] == "raises_risk_for_qnl"


def test_pipeline_carries_qnl_evidence_into_canonical_registry(tmp_path):
    source_path = tmp_path / "qnl_evidence.json"
    _write_qnl_evidence(source_path)
    store_path = tmp_path / "registry_store"
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "storage": {"type": "file", "path": str(store_path)},
                "exports": {"enabled": False},
                "method_profiles": {"enabled": False},
                "sources": [
                    {
                        "id": "qnl_institution_format_evidence_2026_seed",
                        "type": "qnl_institution_format_evidence",
                        "enabled": True,
                        "required": True,
                        "uris": [str(source_path)],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = run_pipeline(config_path, tmp_path / "work", tmp_path / "output")

    assert report["canonical_formats"] == 2
    store = FileRegistryStore({"type": "file", "path": str(store_path)})
    current = store.get_current_registry_view()
    pdf = next(record for record in current if record["preferred_name"] == "PDF")
    netcdf = next(record for record in current if record["preferred_name"] == "netCDF")

    assert pdf["institution_evidence_claims"][0]["criterion_id"] == "institution.workflow_integration"
    assert pdf["institution_evidence_claims"][0]["risk_direction"] == "lowers_risk"
    assert netcdf["institution_evidence_claims"][0]["criterion_id"] == "institution.staff_expertise"
    assert netcdf["institution_evidence_claims"][0]["risk_direction"] == "raises_risk_for_qnl"
