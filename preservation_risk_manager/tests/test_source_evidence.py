from types import SimpleNamespace

from preservation_risk_manager.ai.risk_analysis import question_evidence
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


def test_source_family_evidence_is_ai_only_and_linked_by_puid():
    format_doc = {
        "canonical_id": "puid-fmt-505",
        "identifiers": {"puid": ["fmt/505"]},
        "source_records": [{"source_id": "pronom_registry", "source_record_id": "fmt/505"}],
    }
    rows = [
        {
            "source_id": "pronom_registry",
            "source_type": "pronom_registry",
            "source_record_id": "fmt/505",
            "run_id": "run-2",
            "puids": ["fmt/505"],
            "description": "SWF version 8 description",
        },
        {
            "source_id": "loc_fdd_xml",
            "source_type": "loc_fdd_xml",
            "source_record_id": "fdd000629",
            "run_id": "run-2",
            "puids": ["fmt/505", "fmt/506"],
            "native_fields": {"sustainability_factors": {"adoption": "Legacy format no longer supported"}},
        },
        {
            "source_id": "loc_fdd_xml",
            "source_type": "loc_fdd_xml",
            "source_record_id": "fdd999999",
            "run_id": "run-2",
            "puids": ["fmt/999"],
            "native_fields": {"sustainability_factors": {"adoption": "Other format"}},
        },
    ]

    source_evidence = build_ai_source_evidence(FakeReader(rows), format_doc)
    source_record_ids = {item.get("source_record_id") for item in source_evidence}
    assert "fmt/505" in source_record_ids
    assert "fdd000629" in source_record_ids
    assert "fdd999999" not in source_record_ids

    family_item = next(
        item for item in source_evidence
        if item.get("source_record_id") == "fdd000629"
        and item.get("evidence_field") == "sustainability.adoption"
    )
    assert family_item["link_basis"]["direct_source_record"] is False
    assert family_item["link_basis"]["shared_strong_identifiers"] == [{"kind": "puid", "value": "fmt/505"}]

    pack = {"global_evidence": [], "ai_source_evidence": source_evidence}
    assert evidence_items(pack) == []
    question = SimpleNamespace(evidence_fields=("sustainability.adoption",))
    referenced = question_evidence(question, pack, {}, max_items=20)
    assert referenced
    assert all(item["evidence"].get("evidence_field") == "sustainability.adoption" for item in referenced)
