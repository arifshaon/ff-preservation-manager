"""The one acquisition convention every source follows.

A dropped file in input/<source_id>/ wins outright and the network is never
contacted; force_check_url opts back into a fetch; network failures (404, 503,
timeouts) fall back to local files, then to cached snapshots, and record why;
and every acquisition reports how old the data is.
"""

import io
import json
import urllib.error
from pathlib import Path

import pytest

from registry_builder.adapters.base import SourceAdapter
from registry_builder.models import SourceSnapshot, snapshot_currency


class InboxAdapter(SourceAdapter):
    """Minimal adapter using the base acquire() contract."""

    type_name = "inbox_test"

    def __init__(self, config, workdir, *, network_payload=b"network-data", network_exc=None):
        super().__init__(config, workdir)
        self.network_payload = network_payload
        self.network_exc = network_exc
        self.network_calls = 0

    def network_acquire(self):
        self.network_calls += 1
        if self.network_exc is not None:
            raise self.network_exc
        return [
            self._store_snapshot_bytes(
                index_key="https://example.org/data",
                uri="https://example.org/data",
                data=self.network_payload,
                suffix=".json",
                note=None,
                content_type="application/json",
                metadata={"acquisition_mode": "network"},
            )
        ]

    def extract(self, snapshots):
        return []


def _adapter(tmp_path, *, drop=None, network_exc=None, **config):
    input_root = tmp_path / "input"
    if drop is not None:
        inbox = input_root / "inbox_test"
        inbox.mkdir(parents=True, exist_ok=True)
        for name, content in drop.items():
            (inbox / name).write_text(content, encoding="utf-8")
    return InboxAdapter(
        {"id": "inbox_test", "input_root": str(input_root), **config},
        tmp_path / "work",
        network_exc=network_exc,
    )


def _http_error(code):
    return urllib.error.HTTPError("https://example.org/data", code, "err", {}, io.BytesIO(b""))


def test_dropped_file_wins_and_network_is_never_contacted(tmp_path):
    adapter = _adapter(tmp_path, drop={"data.json": "local-data"})

    snapshots = adapter.acquire()

    assert adapter.network_calls == 0
    assert len(snapshots) == 1
    assert snapshots[0].acquisition_mode == "local"
    assert Path(snapshots[0].local_path).read_text() == "local-data"


def test_no_local_files_means_network(tmp_path):
    adapter = _adapter(tmp_path)

    snapshots = adapter.acquire()

    assert adapter.network_calls == 1
    assert snapshots[0].acquisition_mode == "network"


def test_force_check_url_fetches_despite_local_files(tmp_path):
    adapter = _adapter(tmp_path, drop={"data.json": "local-data"}, force_check_url=True)

    snapshots = adapter.acquire()

    assert adapter.network_calls == 1
    assert snapshots[0].acquisition_mode == "network"


@pytest.mark.parametrize("code", [404, 503])
def test_force_check_url_falls_back_to_local_on_http_error(tmp_path, code):
    adapter = _adapter(
        tmp_path,
        drop={"data.json": "local-data"},
        force_check_url=True,
        network_exc=_http_error(code),
    )

    snapshots = adapter.acquire()

    assert snapshots[0].acquisition_mode == "local"
    assert snapshots[0].metadata["network_error"] == f"http_{code}"
    assert snapshots[0].metadata["network_fallback"] is True


def test_network_failure_without_local_files_replays_cache(tmp_path):
    # First run online populates the snapshot cache.
    adapter = _adapter(tmp_path)
    first = adapter.acquire()
    assert first[0].acquisition_mode == "network"

    # Second run: the provider now returns 503.
    broken = _adapter(tmp_path, network_exc=_http_error(503))
    snapshots = broken.acquire()

    assert snapshots[0].from_cache is True
    assert snapshots[0].acquisition_mode == "cache"
    assert snapshots[0].metadata["network_error"] == "http_503"
    assert snapshots[0].sha256 == first[0].sha256


def test_network_failure_with_no_fallback_raises(tmp_path):
    adapter = _adapter(tmp_path, network_exc=_http_error(404))

    with pytest.raises(urllib.error.HTTPError):
        adapter.acquire()


def test_local_only_policy_fails_loudly_without_files(tmp_path):
    adapter = _adapter(tmp_path, acquisition_policy="local_only")

    with pytest.raises(FileNotFoundError):
        adapter.acquire()


def test_offline_maps_to_cache_only(tmp_path):
    online = _adapter(tmp_path)
    online.acquire()

    offline = _adapter(tmp_path, offline=True)
    snapshots = offline.acquire()

    assert offline.network_calls == 0
    assert snapshots[0].acquisition_mode == "cache"


def test_readme_manifest_and_sidecars_are_not_source_data(tmp_path):
    adapter = _adapter(tmp_path, drop={
        "data.json": "local-data",
        "README.md": "instructions",
        "manifest.json": "{}",
        "data.json.meta.json": "{}",
    })

    files = adapter.local_input_files()

    assert [f.name for f in files] == ["data.json"]


def test_manifest_and_sidecar_supply_publication_provenance(tmp_path):
    adapter = _adapter(tmp_path, drop={
        "old.json": "old",
        "new.json": "new",
        "manifest.json": json.dumps({
            "published_at": "2024-01-01",
            "edition": "2024",
            "files": {"new.json": {"edition": "2025"}},
        }),
        "new.json.meta.json": json.dumps({"published_at": "2025-06-30"}),
    })

    by_name = {Path(s.metadata["local_source_path"]).name: s for s in adapter.acquire()}

    assert by_name["old.json"].source_published_at == "2024-01-01"
    assert by_name["old.json"].edition == "2024"
    # sidecar > manifest per-file > manifest folder-level
    assert by_name["new.json"].source_published_at == "2025-06-30"
    assert by_name["new.json"].edition == "2025"


def test_currency_report_says_how_old_the_data_is(tmp_path):
    snapshot = SourceSnapshot(
        source_id="s", source_type="t", uri="u",
        acquired_at="2026-08-18T00:00:00+00:00",
        sha256="x", local_path="p",
        acquisition_mode="local",
        source_published_at="2026-06-20",
        edition="20260620",
    )

    from datetime import datetime, timezone
    now = datetime(2026, 8, 19, tzinfo=timezone.utc)
    currency = snapshot_currency(snapshot, now=now)

    assert currency["acquired_age_days"] == 1
    assert currency["published_age_days"] == 60
    assert currency["edition"] == "20260620"
    assert currency["acquisition_mode"] == "local"


def test_unparseable_publication_date_reports_none_not_crash(tmp_path):
    snapshot = SourceSnapshot(
        source_id="s", source_type="t", uri="u",
        acquired_at="2026-08-18T00:00:00+00:00",
        sha256="x", local_path="p",
        source_published_at="Spring 2026",
    )

    assert snapshot_currency(snapshot)["published_age_days"] is None


# ---------------------------------------------------------------------------
# Migrated adapters
# ---------------------------------------------------------------------------

NARA_ACTION_CSV = (
    "NARA Format ID,Format Name,File Extension(s),PUID,Wikidata QID\n"
    "fmt-s-1,Test Format,.tst,fmt/999,Q999\n"
)
NARA_RISK_CSV = (
    "NARA Format ID,Format Name,File Extension(s)\n"
    "fmt-s-1,Test Format,.tst\n"
)


def _nara_adapter(tmp_path, **config):
    from registry_builder.adapters.nara_digital_preservation_framework import (
        NaraDigitalPreservationFrameworkAdapter,
    )

    return NaraDigitalPreservationFrameworkAdapter(
        {
            "id": "nara_digital_preservation_framework",
            "type": "nara_digital_preservation_framework",
            "input_root": str(tmp_path / "input"),
            **config,
        },
        tmp_path / "work",
    )


def _drop_nara_release(tmp_path):
    inbox = tmp_path / "input" / "nara_digital_preservation_framework"
    inbox.mkdir(parents=True)
    (inbox / "NARA_PreservationActionPlan_FileFormats_20260320.csv").write_text(NARA_ACTION_CSV, encoding="utf-8")
    (inbox / "NARA_File_Format_Risk_Matrix_20260320_Numbered.csv").write_text(NARA_RISK_CSV, encoding="utf-8")
    return inbox


def test_nara_dropped_release_wins_and_infers_provenance_from_filenames(tmp_path):
    _drop_nara_release(tmp_path)
    adapter = _nara_adapter(tmp_path, release_mode="latest")  # network mode configured but never used

    snapshots = adapter.acquire()

    assert len(snapshots) == 2
    by_kind = {s.metadata["kind"]: s for s in snapshots}
    assert set(by_kind) == {"preservation_action_plan", "risk_matrix_numbered"}
    for snapshot in snapshots:
        assert snapshot.acquisition_mode == "local"
        assert snapshot.edition == "20260320"
        assert snapshot.source_published_at == "2026-03-20"
        assert snapshot.metadata["release_mode"] == "input_dir"

    records = adapter.extract(snapshots)
    assert any(r.nara_ids == ["fmt-s-1"] for r in records)


def test_nara_local_only_policy_without_dropped_files_fails_loudly(tmp_path):
    adapter = _nara_adapter(tmp_path, acquisition_policy="local_only")

    with pytest.raises(FileNotFoundError):
        adapter.acquire()


def test_nara_pinned_release_sets_publication_provenance(tmp_path, monkeypatch):
    # No inbox: pinned network mode runs; patch read_uri so no network happens.
    import registry_builder.adapters.base as base_mod

    def fake_read_uri(uri, *args, **kwargs):
        text = NARA_ACTION_CSV if "PreservationActionPlan" in uri else NARA_RISK_CSV
        return text.encode(), {"content-type": "text/csv"}

    monkeypatch.setattr(base_mod, "read_uri", fake_read_uri)
    adapter = _nara_adapter(tmp_path, release_mode="pinned", release_date="20260320")

    snapshots = adapter.acquire()

    assert {s.acquisition_mode for s in snapshots} == {"network"}
    assert {s.edition for s in snapshots} == {"20260320"}
    assert {s.source_published_at for s in snapshots} == {"2026-03-20"}


def test_wikidata_dropped_sparql_result_is_used_without_network(tmp_path):
    from registry_builder.adapters.wikidata_sparql import WikidataSparqlAdapter

    inbox = tmp_path / "input" / "wikidata_sparql"
    inbox.mkdir(parents=True)
    payload = {"results": {"bindings": [{
        "item": {"type": "uri", "value": "http://www.wikidata.org/entity/Q42332"},
        "itemLabel": {"type": "literal", "value": "PDF"},
        "puids": {"type": "literal", "value": "fmt/18"},
    }]}}
    (inbox / "wikidata.json").write_text(json.dumps(payload), encoding="utf-8")
    (inbox / "manifest.json").write_text(json.dumps({"published_at": "2026-08-01"}), encoding="utf-8")

    adapter = WikidataSparqlAdapter(
        {"id": "wikidata_sparql", "input_root": str(tmp_path / "input")},
        tmp_path / "work",
    )

    snapshots = adapter.acquire()

    assert len(snapshots) == 1
    assert snapshots[0].acquisition_mode == "local"
    assert snapshots[0].source_published_at == "2026-08-01"

    records = adapter.extract(snapshots)
    assert [r.puids for r in records] == [["fmt/18"]]
    assert records[0].wikidata_ids == ["Q42332"]


def test_init_source_inbox_creates_folders_only_for_supporting_adapters(tmp_path, capsys):
    from registry_builder.__main__ import cmd_init_source_inbox

    config = {
        "sources": [
            {"id": "wikidata_sparql", "type": "wikidata_sparql", "enabled": True},
            {"id": "nara", "type": "nara_digital_preservation_framework", "enabled": True},
            {"id": "pronom_registry", "type": "pronom_registry", "enabled": True},
            {"id": "off", "type": "wikidata_sparql", "enabled": False},
        ]
    }
    config_path = tmp_path / "sources.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    class Args:
        pass

    args = Args()
    args.config = str(config_path)
    result = cmd_init_source_inbox(args)

    by_id = {row["source_id"]: row for row in result["sources"]}
    assert by_id["wikidata_sparql"]["status"] == "ready"
    assert by_id["nara"]["status"] == "ready"
    assert by_id["pronom_registry"]["status"] == "not_supported"
    assert by_id["off"]["status"] == "skipped_disabled"
    assert (tmp_path / "input" / "wikidata_sparql" / "README.md").exists()
    assert not (tmp_path / "input" / "pronom_registry").exists()
