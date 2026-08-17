from __future__ import annotations

import json

import pytest

from preservation_risk_manager.data_access import JsonRegistryStore, RegistryAccessError, RegistryReader, load_storage_config


class FakeStore:
    def __init__(self, collections):
        self.collections = collections
        self.queries = []

    def query(self, collection, filt=None):
        filt = filt or {}
        self.queries.append((collection, dict(filt)))
        rows = self.collections.get(collection, [])
        return [row for row in rows if all(row.get(key) == value for key, value in filt.items())]


def test_load_storage_config_accepts_direct_storage_block(tmp_path):
    path = tmp_path / "storage.json"
    path.write_text(json.dumps({"type": "file", "path": "registry_store"}), encoding="utf-8")

    assert load_storage_config(path) == {"type": "file", "path": "registry_store"}


def test_load_storage_config_extracts_storage_from_pipeline_config(tmp_path):
    path = tmp_path / "pipeline-config.json"
    path.write_text(
        json.dumps({
            "storage": {"type": "mongodb", "database": "formats"},
            "sources": [],
        }),
        encoding="utf-8",
    )

    assert load_storage_config(path) == {"type": "mongodb", "database": "formats"}


def test_load_storage_config_rejects_non_object_storage_value(tmp_path):
    path = tmp_path / "bad-config.json"
    path.write_text(json.dumps({"storage": "mongodb://example"}), encoding="utf-8")

    with pytest.raises(RegistryAccessError, match="non-object 'storage' value"):
        load_storage_config(path)


def test_json_registry_store_auto_loads_sibling_criterion_claims_jsonl(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps([{"canonical_id": "fmt-pdf", "preferred_name": "PDF"}]),
        encoding="utf-8",
    )
    claims_path = tmp_path / "criterion_claims.jsonl"
    claims = [
        {
            "canonical_id": "fmt-pdf",
            "criterion_id": "sustainability.disclosure",
            "value": "public_specification",
            "source_id": "loc_fdd_xml",
            "mapping_rule_id": "loc.disclosure.v1",
        },
        {
            "canonical_id": "fmt-pdf",
            "criterion_id": "sustainability.adoption",
            "value": "high",
            "source_id": "loc_fdd_xml",
            "mapping_rule_id": "loc.adoption.v1",
        },
    ]
    claims_path.write_text("\n".join(json.dumps(row) for row in claims) + "\n", encoding="utf-8")

    store = JsonRegistryStore.from_registry_json(registry_path)

    assert store.query("canonical_formats", {"canonical_id": "fmt-pdf"}) == [
        {"canonical_id": "fmt-pdf", "preferred_name": "PDF"}
    ]
    assert store.query("criterion_claims", {"canonical_id": "fmt-pdf"}) == claims


def test_json_registry_store_accepts_explicit_criterion_claims_path(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps([{"canonical_id": "fmt-pdf"}]), encoding="utf-8")
    claims_dir = tmp_path / "claims"
    claims_dir.mkdir()
    claims_path = claims_dir / "claims.json"
    claims_path.write_text(
        json.dumps([
            {
                "canonical_id": "fmt-pdf",
                "criterion_id": "sustainability.disclosure",
                "value": "public_specification",
            }
        ]),
        encoding="utf-8",
    )

    store = JsonRegistryStore.from_registry_json(registry_path, criterion_claims_path=claims_path)

    assert len(store.query("criterion_claims", {"canonical_id": "fmt-pdf"})) == 1


def test_registry_reader_queries_store_contract():
    store = FakeStore({"canonical_formats": [{"canonical_id": "fmt/18", "name": "PDF"}]})
    reader = RegistryReader(store=store)

    assert reader.query("canonical_formats", {"canonical_id": "fmt/18"}) == [{"canonical_id": "fmt/18", "name": "PDF"}]
    assert store.queries == [("canonical_formats", {"canonical_id": "fmt/18"})]


def test_registry_reader_gets_canonical_format_by_known_id_field():
    store = FakeStore({"canonical_formats": [{"format_id": "format/pdf", "name": "PDF"}]})
    reader = RegistryReader(store=store)

    assert reader.get_canonical_format("format/pdf") == {"format_id": "format/pdf", "name": "PDF"}


def test_registry_reader_ignores_inactive_canonical_formats():
    store = FakeStore({
        "canonical_formats": [
            {"canonical_id": "fmt-old", "name": "Old", "current": False},
            {"canonical_id": "fmt-current", "name": "Current", "current": True},
            {"canonical_id": "fmt-legacy", "name": "Legacy Without Flag"},
        ]
    })
    reader = RegistryReader(store=store)

    assert [row["canonical_id"] for row in reader.list_canonical_formats()] == ["fmt-current", "fmt-legacy"]
    assert reader.get_canonical_format("fmt-old") is None


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


def test_registry_reader_reads_global_criterion_claims_only_for_global_scope():
    store = FakeStore({
        "criterion_claims": [
            {"canonical_id": "fmt-pdf", "source_id": "loc_fdd_xml", "criterion_id": "sustainability.disclosure"},
            {
                "canonical_id": "fmt-pdf",
                "source_id": "qnl_seed",
                "institution_id": "qnl",
                "source_independence": "institution_scoped",
                "criterion_id": "sustainability.disclosure",
            },
            {"canonical_id": "fmt-netcdf", "source_id": "loc_fdd_xml", "criterion_id": "sustainability.disclosure"},
        ]
    })
    reader = RegistryReader(store=store)

    assert reader.get_criterion_claims(canonical_id="fmt-pdf") == [
        {"canonical_id": "fmt-pdf", "source_id": "loc_fdd_xml", "criterion_id": "sustainability.disclosure"}
    ]


def test_registry_reader_reads_global_and_matching_institution_criterion_claims():
    store = FakeStore({
        "criterion_claims": [
            {"canonical_id": "fmt-pdf", "source_id": "loc_fdd_xml", "criterion_id": "sustainability.disclosure"},
            {
                "canonical_id": "fmt-pdf",
                "source_id": "qnl_seed",
                "institution_id": "qnl",
                "source_independence": "institution_scoped",
                "criterion_id": "sustainability.disclosure",
            },
            {
                "canonical_id": "fmt-pdf",
                "source_id": "other_seed",
                "institution_id": "other",
                "source_independence": "institution_scoped",
                "criterion_id": "sustainability.disclosure",
            },
        ]
    })
    reader = RegistryReader(store=store)

    assert reader.get_criterion_claims(canonical_id="fmt-pdf", institution_id="qnl") == [
        {"canonical_id": "fmt-pdf", "source_id": "loc_fdd_xml", "criterion_id": "sustainability.disclosure"},
        {
            "canonical_id": "fmt-pdf",
            "source_id": "qnl_seed",
            "institution_id": "qnl",
            "source_independence": "institution_scoped",
            "criterion_id": "sustainability.disclosure",
        },
    ]


def test_registry_reader_expands_strong_identifier_aliases_for_criterion_claims():
    store = FakeStore({
        "criterion_claims": [
            {"canonical_id": "puid-fmt-18", "source_id": "pronom_registry", "criterion_id": "sustainability.disclosure"},
            {"canonical_id": "loc-fdd000030", "source_id": "loc_fdd_xml", "criterion_id": "sustainability.adoption"},
            {"canonical_id": "fmt-pdf", "source_id": "qnl_seed", "institution_id": "qnl", "criterion_id": "sustainability.disclosure"},
            {"canonical_id": "extension-pdf", "source_id": "bad", "criterion_id": "sustainability.disclosure"},
        ]
    })
    reader = RegistryReader(store=store)
    format_doc = {
        "canonical_id": "fmt-pdf",
        "identifiers": {
            "puid": ["fmt/18"],
            "loc": ["fdd000030"],
            "extension": ["pdf"],
        },
    }

    assert reader.criterion_claim_canonical_ids(format_doc) == ["fmt-pdf", "puid-fmt-18", "loc-fdd000030"]
    assert reader.get_criterion_claims_for_format(format_doc) == [
        {"canonical_id": "puid-fmt-18", "source_id": "pronom_registry", "criterion_id": "sustainability.disclosure"},
        {"canonical_id": "loc-fdd000030", "source_id": "loc_fdd_xml", "criterion_id": "sustainability.adoption"},
    ]


def test_registry_reader_alias_lookup_includes_matching_institution_claims():
    store = FakeStore({
        "criterion_claims": [
            {"canonical_id": "puid-fmt-18", "source_id": "pronom_registry", "criterion_id": "sustainability.disclosure"},
            {"canonical_id": "fmt-pdf", "source_id": "qnl_seed", "institution_id": "qnl", "criterion_id": "sustainability.adoption"},
            {"canonical_id": "fmt-pdf", "source_id": "other_seed", "institution_id": "other", "criterion_id": "sustainability.adoption"},
        ]
    })
    reader = RegistryReader(store=store)
    format_doc = {"canonical_id": "fmt-pdf", "puids": ["fmt/18"]}

    assert reader.get_criterion_claims_for_format(format_doc, institution_id="qnl") == [
        {"canonical_id": "fmt-pdf", "source_id": "qnl_seed", "institution_id": "qnl", "criterion_id": "sustainability.adoption"},
        {"canonical_id": "puid-fmt-18", "source_id": "pronom_registry", "criterion_id": "sustainability.disclosure"},
    ]
