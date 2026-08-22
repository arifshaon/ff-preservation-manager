from __future__ import annotations

from preservation_risk_manager.answer_derivation import evidence_items
from preservation_risk_manager.source_evidence import build_ai_source_evidence


class FakeReader:
    def __init__(self, rows):
        self.rows = rows

    def query(self, collection, filt=None):
        if collection != "source_records":
            return []
        filt = filt or {}
        return [row for row in self.rows if all(row.get(k) == v for k, v in filt.items())]


def test_linked_new_source_native_risk_is_available_to_ai_but_not_deterministic_scoring():
    format_doc = {
        "canonical_id": "puid-fmt-276",
        "identifiers": {"puid": ["fmt/276"]},
        "source_records": [
            {"source_id": "new_preservation_source", "source_record_id": "NEW-PDF17"}
        ],
    }
    rows = [
        {
            "source_id": "new_preservation_source",
            "source_type": "new_preservation_source",
            "source_record_id": "NEW-PDF17",
            "run_id": "run-1",
            "puids": ["fmt/276"],
            "risk_assessments": [
                {
                    "native_label": "Severe",
                    "native_score": 8,
                    "native_scale": "new_native_scale",
                    "scope_type": "exact_format",
                    "scope_name": "PDF 1.7",
                }
            ],
        }
    ]

    source_evidence = build_ai_source_evidence(FakeReader(rows), format_doc)
    risk_item = next(
        item for item in source_evidence
        if item.get("evidence_kind") == "source_native_risk_assessment"
    )

    assert risk_item["source_id"] == "new_preservation_source"
    assert risk_item["native_label"] == "Severe"
    assert risk_item["native_scale"] == "new_native_scale"
    assert risk_item["scope_type"] == "exact_format"
    assert risk_item["link_basis"]["direct_source_record"] is True

    pack = {
        "global_evidence": [],
        "institution_evidence": [],
        "ai_source_evidence": source_evidence,
    }
    assert evidence_items(pack) == []
