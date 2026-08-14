import pytest

from registry_builder.adapters.standard_json import StandardJsonAdapter


def test_adapter_reuses_unchanged_snapshot_and_reports_status(tmp_path):
    source = tmp_path / "source.json"
    source.write_text('{"records": []}', encoding="utf-8")
    config = {"id": "source", "uris": [str(source)]}

    first = StandardJsonAdapter(config, tmp_path / "work").acquire()[0]
    second = StandardJsonAdapter(config, tmp_path / "work").acquire()[0]

    assert first.changed is True
    assert first.from_cache is False
    assert second.changed is False
    assert second.from_cache is False
    assert first.sha256 == second.sha256
    assert first.local_path == second.local_path


def test_offline_mode_uses_cached_snapshot_without_source_access(tmp_path):
    source = tmp_path / "source.json"
    source.write_text('{"records": []}', encoding="utf-8")
    config = {"id": "source", "uris": [str(source)]}
    first = StandardJsonAdapter(config, tmp_path / "work").acquire()[0]

    source.unlink()
    offline = StandardJsonAdapter({**config, "offline": True}, tmp_path / "work").acquire()[0]

    assert offline.changed is False
    assert offline.from_cache is True
    assert offline.sha256 == first.sha256
    assert offline.local_path == first.local_path


def test_offline_mode_fails_loudly_without_cached_snapshot(tmp_path):
    config = {"id": "source", "uris": [str(tmp_path / "missing.json")], "offline": True}

    with pytest.raises(FileNotFoundError):
        StandardJsonAdapter(config, tmp_path / "work").acquire()
