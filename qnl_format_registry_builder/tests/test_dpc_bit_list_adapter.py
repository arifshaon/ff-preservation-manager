from __future__ import annotations

import zipfile
from pathlib import Path

from registry_builder.adapters import resolve_adapter
from registry_builder.adapters.dpc_bit_list import DPC_2025_COMMIT, DpcBitListAdapter
from registry_builder.models import SourceSnapshot
from registry_builder.reconcile import reconcile


_SAMPLE_ENTRY = """---
id: PDF-ENTRY
title: PDF
description: Documents presented in PDF format, including variants and versions.
examples: PDF 1.7; PDF 2.0; PDF/A
categories:
  - Formats
threats:
  - Data Types/File-Formats
classification: vulnerable
imminence: 1
effort: 2
trends:
  - year: 2024
    trend: no-change
    classification: vulnerable
hazards: Lack of validation; encryption; poor storage.
mitigations: Format validation; preservation planning; version control.
year-added: 2017
published: 2017-11-30
last-updated: 2024-11-07
---
**2024 Interim Review**

These risks remain on the same basis as before.
"""


def _snapshot_for_zip(path: Path) -> SourceSnapshot:
    return SourceSnapshot(
        source_id="dpc_bit_list_2025",
        source_type="dpc_bit_list",
        uri="https://example.test/bit-list-main.zip",
        acquired_at="2026-08-21T00:00:00+00:00",
        sha256="abc123",
        local_path=str(path),
        content_type="application/zip",
        metadata={"edition": "2025", "identity_projection": False},
    )


def test_dpc_adapter_is_registered():
    assert resolve_adapter("dpc_bit_list") is DpcBitListAdapter


def test_dpc_2025_defaults_to_pinned_commit(tmp_path):
    adapter = DpcBitListAdapter(
        {"id": "dpc_bit_list_2025", "type": "dpc_bit_list", "edition": "2025"},
        tmp_path,
    )
    assert adapter._github_ref() == DPC_2025_COMMIT
    assert DPC_2025_COMMIT in adapter._archive_url()


def test_dpc_archive_extracts_structured_source_native_risk_entry(tmp_path):
    archive_path = tmp_path / "bit-list.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("bit-list-main/content/entries/pdf/index.en.md", _SAMPLE_ENTRY)
        archive.writestr("bit-list-main/content/entries/_index.en.md", "---\ntitle: Entries\n---\n")

    adapter = DpcBitListAdapter(
        {"id": "dpc_bit_list_2025", "type": "dpc_bit_list", "edition": "2025"},
        tmp_path,
    )
    entries = adapter.extract_entries([_snapshot_for_zip(archive_path)])

    assert len(entries) == 1
    entry = entries[0]
    assert entry["source_record_id"] == "PDF-ENTRY"
    assert entry["slug"] == "pdf"
    assert entry["title"] == "PDF"
    assert entry["classification"] == "vulnerable"
    assert entry["classification_label"] == "Vulnerable"
    assert entry["semantic_level"] == "moderate"
    assert entry["imminence"] == 1
    assert entry["effort"] == 2
    assert entry["published"] == "2017-11-30"
    assert entry["last_updated"] == "2024-11-07"
    assert entry["hazards"] == ["Lack of validation", "encryption", "poor storage."]
    assert entry["mitigations"] == ["Format validation", "preservation planning", "version control."]
    assessment = entry["risk_assessment"]
    assert assessment["assessment_role"] == "external"
    assert assessment["source_label"] == "DPC Global Bit List 2025"
    assert assessment["native_label"] == "Vulnerable"
    assert assessment["semantic_level"] == "moderate"
    assert assessment["scope_type"] == "format_group"
    assert assessment["scope_basis"] == "dpc_entry_scope_unreconciled"


def test_dpc_pipeline_projection_is_evidence_only_and_creates_no_canonical_format(tmp_path):
    archive_path = tmp_path / "bit-list.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("bit-list-main/content/entries/pdf/index.en.md", _SAMPLE_ENTRY)

    adapter = DpcBitListAdapter(
        {"id": "dpc_bit_list_2025", "type": "dpc_bit_list", "edition": "2025"},
        tmp_path,
    )
    snapshot = _snapshot_for_zip(archive_path)

    records = adapter.extract([snapshot])
    assert len(records) == 1
    record = records[0]
    assert record.record_role == "evidence_only"
    assert record.name == "PDF"
    assert record.risk_assessments[0]["native_label"] == "Vulnerable"
    assert reconcile(records) == []
