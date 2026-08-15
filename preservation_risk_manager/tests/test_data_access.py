from __future__ import annotations

import pytest

from preservation_risk_manager.data_access import RegistryAccessError, RegistryReader


class FakeStore:
    def __init__(self, collections):
        self.collections = collections
        self.queries = []

    def query(self, collection, filt=None):
        filt = filt or {}
        self.queries.append((collection, dict(filt)))
        rows = self.collections.get(collection, [])
        return [row for row in rows if all(row.get(key) == value for key, value in filt.items())]


def test_registry_reader_queries_store_contract():
    store = FakeStore({"canonical_formats": [{"canonical_id": "fmt/18", "name": "PDF"}]})
    reader = RegistryReader(store=store)

    assert reader.query("canonical_formats", {"canonical_id": "fmt/18"}) == [{"canonical_id": "fmt/18", "name": "PDF"}]
    assert store.queries == [("canonical_formats", {"canonical_id": "fmt/18"})]


def test_registry_reader_gets_canonical_format_by_known_id_field():
    store = FakeStore({"canonical_formats": [{"format_id": "format/pdf", "name": "PDF"}]})
    reader = RegistryReader(store=store)

    assert reader.get_canonical_format("format/pdf") == {"format_id": "format/pdf", "name": "PDF"}


def test_registry_reader_can_be_created_from_injected_store_factory():
    created = []

    def factory(config):
        created.append(config)
        return FakeStore({"canonical_formats": [{"canonical_id": "fmt/18"}]})

    reader = RegistryReader(storage_config={"type": "memory"}, store_factory=factory)

    assert created == [{"type": "memory"}]
    assert reader.list_canonical_formats() == [{"canonical_id": "fmt/18"}]


def test_registry_reader_requires_store_or_storage_config():
    with pytest.raises(RegistryAccessError, match="requires either a store or storage_config"):
        RegistryReader()


def test_registry_reader_scopes_format_evidence_claims_to_institution():
    store = FakeStore({
        "format_evidence_claims": [
            {"canonical_id": "fmt/18", "institution_id": "qnl", "criterion_id": "institution.staff_expertise"},
            {"canonical_id": "fmt/18", "institution_id": "other", "criterion_id": "institution.staff_expertise"},
            {"canonical_id": "fmt/19", "institution_id": "qnl", "criterion_id": "institution.staff_expertise"},
        ]
    })
    reader = RegistryReader(store=store)

    assert reader.get_format_evidence_claims(canonical_id="fmt/18", institution_id="qnl") == [
        {"canonical_id": "fmt/18", "institution_id": "qnl", "criterion_id": "institution.staff_expertise"}
    ]
