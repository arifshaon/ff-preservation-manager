from pathlib import Path
import json

from registry_builder.pipeline import run_pipeline


def test_pipeline_can_apply_criterion_mapping_in_memory(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    config = {
        "pipeline_version": "0.1.0",
        "incremental_source_updates": True,
        "storage": {"type": "memory"},
        "exports": {"enabled": True},
        "method_profiles": {"enabled": False},
        "criterion_mapping": {
            "enabled": True,
            "mode": "apply",
            "criteria": str(repo_root / "config" / "criteria" / "v1.json"),
            "mappings": str(repo_root / "config" / "criterion_mappings" / "qnl_institution_format_evidence.v1.json"),
            "include_drafts": False,
            "scope": "all",
        },
        "identifier_kinds": {
            "puid": {"strength": "strong", "verified_from": ["qnl_institution_format_evidence"]},
            "loc": {"strength": "strong", "verified_from": ["qnl_institution_format_evidence"]},
            "nara": {"strength": "strong", "verified_from": []},
            "wikidata": {"strength": "weak", "verified_from": []},
        },
        "sources": [
            {
                "id": "qnl_institution_format_evidence_2026_seed",
                "type": "qnl_institution_format_evidence",
                "enabled": True,
                "required": True,
                "institution_id": "qnl",
                "institution_name": "Qatar National Library",
                "uris": [str(repo_root / "examples" / "qnl_institution_format_evidence.seed.json")],
            }
        ],
    }
    config_path = tmp_path / "pipeline.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    report = run_pipeline(config_path, tmp_path / "work", tmp_path / "out")

    assert report["criterion_mapping"]["enabled"] is True
    assert report["criterion_mapping"]["claims_generated"] > 0
    assert "sustainability.disclosure" in report["criterion_mapping"]["claims_by_criterion"]
    exported_claims = tmp_path / "out" / "criterion_claims.json"
    assert exported_claims.exists()
    claims = json.loads(exported_claims.read_text(encoding="utf-8"))
    assert all("confidence" not in claim for claim in claims)
    assert any(claim["criterion_id"] == "sustainability.disclosure" for claim in claims)


def test_pipeline_leaves_criterion_mapping_disabled_by_default(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    config = {
        "pipeline_version": "0.1.0",
        "storage": {"type": "memory"},
        "exports": {"enabled": False},
        "method_profiles": {"enabled": False},
        "identifier_kinds": {
            "puid": {"strength": "strong", "verified_from": ["qnl_institution_format_evidence"]},
            "loc": {"strength": "strong", "verified_from": ["qnl_institution_format_evidence"]},
        },
        "sources": [
            {
                "id": "qnl_institution_format_evidence_2026_seed",
                "type": "qnl_institution_format_evidence",
                "enabled": True,
                "required": True,
                "uris": [str(repo_root / "examples" / "qnl_institution_format_evidence.seed.json")],
            }
        ],
    }
    config_path = tmp_path / "pipeline.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    report = run_pipeline(config_path, tmp_path / "work", tmp_path / "out")

    assert report["criterion_mapping"] == {"enabled": False, "claims_generated": 0}


def test_sequential_source_runs_export_claims_from_every_source(tmp_path):
    """Ingesting sources one run at a time must not shrink the claims export.

    criterion_claims.jsonl is what the risk manager reads; after run N it must
    hold the store's current claims across all sources, not just run N's.
    """
    repo_root = Path(__file__).resolve().parents[1]
    store_path = tmp_path / "store"

    def _config(source_id, mapping_file, source_file):
        return {
            "pipeline_version": "0.1.0",
            "incremental_source_updates": True,
            "storage": {"type": "file", "path": str(store_path)},
            "exports": {"enabled": True},
            "method_profiles": {"enabled": False},
            "criterion_mapping": {
                "enabled": True,
                "mode": "apply",
                "criteria": str(repo_root / "config" / "criteria" / "v1.json"),
                "mappings": str(mapping_file),
                "include_drafts": False,
                "scope": "all",
            },
            "identifier_kinds": {
                "puid": {"strength": "strong", "verified_from": []},
                "loc": {"strength": "strong", "verified_from": []},
                "nara": {"strength": "strong", "verified_from": []},
                "wikidata": {"strength": "weak", "verified_from": []},
            },
            "sources": [
                {
                    "id": source_id,
                    "type": "standard_json",
                    "enabled": True,
                    "required": True,
                    "uris": [str(source_file)],
                }
            ],
        }

    def _mapping(source_id):
        path = tmp_path / f"{source_id}.mapping.json"
        path.write_text(json.dumps({
            "source_id": source_id,
            "source_type": "standard_json",
            "criteria_version": "v1",
            "mapping_version": "test",
            "review_status": "approved",
            "claim_review_status": "approved",
            "decided_by": "test-suite",
            "native_vocabulary": f"{source_id}_native",
            "maps": [{
                "id": f"{source_id}.disclosure.v1",
                "criterion": "sustainability.disclosure",
                "from_collection": "evidence",
                "from_field": "disclosure",
                "values": {"open": "public_specification"},
                "directness": "explicit",
                "mapping_status": "accepted",
            }],
        }), encoding="utf-8")
        return path

    def _source(source_id, name):
        path = tmp_path / f"{source_id}.json"
        path.write_text(json.dumps({
            "records": [{
                "id": f"{source_id}-r1",
                "name": name,
                "evidence": [{"disclosure": "open"}],
            }],
        }), encoding="utf-8")
        return path

    first = tmp_path / "first.json"
    first.write_text(json.dumps(_config("source_a", _mapping("source_a"), _source("source_a", "Format A"))), encoding="utf-8")
    run_pipeline(first, tmp_path / "work_a", tmp_path / "out_a")

    second = tmp_path / "second.json"
    second.write_text(json.dumps(_config("source_b", _mapping("source_b"), _source("source_b", "Format B"))), encoding="utf-8")
    report = run_pipeline(second, tmp_path / "work_b", tmp_path / "out_b")

    exported = [
        json.loads(line)
        for line in (tmp_path / "out_b" / "criterion_claims.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    by_source = {claim["source_id"] for claim in exported}

    assert by_source == {"source_a", "source_b"}
    assert report["criterion_claims_exported"] == len(exported) == 2
    # the second run itself only generated source_b claims
    assert report["criterion_mapping"]["claims_generated"] == 1


def test_claims_follow_their_record_when_a_later_source_reshapes_canonicals(tmp_path):
    """A claim must point at the canonical its source record is in *now*.

    Ingesting one source at a time means an early source's records can be
    merged onto another authority's canonical later. The claim written during
    the earlier run would otherwise keep pointing at a canonical_id that no
    longer exists.
    """
    repo_root = Path(__file__).resolve().parents[1]
    store_path = tmp_path / "store"

    def _mapping(source_id, source_type):
        path = tmp_path / f"mapping.{source_id}.json"
        path.write_text(json.dumps({
            "source_id": source_id,
            "source_type": source_type,
            "criteria_version": "v1",
            "mapping_version": "test",
            "review_status": "approved",
            "claim_review_status": "approved",
            "decided_by": "test-suite",
            "native_vocabulary": f"{source_id}_native",
            "maps": [{
                "id": f"{source_id}.disclosure.v1",
                "criterion": "sustainability.disclosure",
                "from_collection": "evidence",
                "from_field": "disclosure",
                "values": {"open": "public_specification"},
                "directness": "explicit",
                "mapping_status": "accepted",
            }],
        }), encoding="utf-8")
        return path

    # Run 2 maps only the incoming source, so the institution's stored claim is
    # not regenerated — the remap is the only thing that can correct it.
    mapping = _mapping("institution", "standard_json")
    pronom_mapping = _mapping("pronom_droid_xml", "pronom_droid_xml")

    # An institutional row citing a PUID nobody has published yet.
    institution = tmp_path / "institution.json"
    institution.write_text(json.dumps({"records": [{
        "id": "row-1", "name": "Portable Document Format",
        "identifiers": {"puid": ["fmt/18"]},
        "evidence": [{"disclosure": "open"}],
    }]}), encoding="utf-8")

    # PRONOM, arriving later, verifies that PUID and takes ownership of it.
    # A real PRONOM adapter type is needed here: verification is decided by
    # source_type, so a second standard_json source would never own the PUID.
    pronom = tmp_path / "DROID_SignatureFile_V120.xml"
    pronom.write_text(
        '<FFSignatureFile><FileFormatCollection>'
        '<FileFormat Name="Acrobat PDF 1.4 - Portable Document Format" PUID="fmt/18">'
        "<Extension>pdf</Extension></FileFormat>"
        "</FileFormatCollection></FFSignatureFile>",
        encoding="utf-8",
    )

    def _config(source_id, source_type, source_file, mappings):
        return {
            "pipeline_version": "0.1.0",
            "incremental_source_updates": True,
            "storage": {"type": "file", "path": str(store_path)},
            "exports": {"enabled": True},
            "method_profiles": {"enabled": False},
            "criterion_mapping": {
                "enabled": True, "mode": "apply",
                "criteria": str(repo_root / "config" / "criteria" / "v1.json"),
                "mappings": str(mappings), "include_drafts": False, "scope": "all",
            },
            "identifier_kinds": {
                "puid": {"strength": "strong", "verified_from": ["pronom_droid_xml"]},
                "loc": {"strength": "strong", "verified_from": []},
                "nara": {"strength": "strong", "verified_from": []},
                "wikidata": {"strength": "weak", "verified_from": []},
            },
            "sources": [{
                "id": source_id, "type": source_type,
                "enabled": True, "required": True, "uris": [str(source_file)],
            }],
        }

    first = tmp_path / "first.json"
    first.write_text(json.dumps(_config("institution", "standard_json", institution, mapping)), encoding="utf-8")
    run_pipeline(first, tmp_path / "work_a", tmp_path / "out_a")

    claims_a = [json.loads(l) for l in (tmp_path / "out_a" / "criterion_claims.jsonl").read_text().splitlines()]
    assert len(claims_a) == 1
    standalone_id = claims_a[0]["canonical_id"]
    assert not standalone_id.startswith("puid-"), "PUID is unverified while only the institution has it"

    second = tmp_path / "second.json"
    second.write_text(json.dumps(_config("pronom_droid_xml", "pronom_droid_xml", pronom, pronom_mapping)), encoding="utf-8")
    report = run_pipeline(second, tmp_path / "work_b", tmp_path / "out_b")

    registry_ids = {r["canonical_id"] for r in json.loads((tmp_path / "out_b" / "registry.json").read_text())}
    exported = [json.loads(l) for l in (tmp_path / "out_b" / "criterion_claims.jsonl").read_text().splitlines()]

    assert standalone_id not in registry_ids, "the institution row should now be merged onto PRONOM's canonical"
    assert exported, "the institution claim must survive the merge"
    for claim in exported:
        assert claim["canonical_id"] in registry_ids, "no claim may point at a canonical that no longer exists"
    moved = [c for c in exported if c.get("remapped_from_canonical_id")]
    assert [c["remapped_from_canonical_id"] for c in moved] == [standalone_id]
    assert report["criterion_claims_remapped"] == 1
