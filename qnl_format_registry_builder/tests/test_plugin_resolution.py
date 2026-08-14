import pytest

from registry_builder.adapters import resolve_adapter
from registry_builder.adapters.standard_json import StandardJsonAdapter
from registry_builder.storage import create_store, resolve_storage_backend
from registry_builder.storage.memory import MemoryRegistryStore


def test_adapter_resolves_registered_short_name():
    assert resolve_adapter("standard_json") is StandardJsonAdapter


def test_adapter_resolves_colon_plugin_path():
    assert resolve_adapter("registry_builder.adapters.standard_json:StandardJsonAdapter") is StandardJsonAdapter


def test_adapter_rejects_non_source_adapter_class():
    with pytest.raises(TypeError, match="not a subclass of SourceAdapter"):
        resolve_adapter("json:JSONDecoder")


def test_adapter_rejects_colonless_external_path():
    with pytest.raises(ValueError, match="package.module:ClassName"):
        resolve_adapter("registry_builder.adapters.standard_json.StandardJsonAdapter")


def test_adapter_reports_missing_plugin_dependency(tmp_path, monkeypatch):
    package = tmp_path / "broken_plugin"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "adapter.py").write_text(
        "import dependency_that_is_not_installed_for_plugin_test\n"
        "from registry_builder.adapters.base import SourceAdapter\n"
        "class BrokenAdapter(SourceAdapter):\n"
        "    type_name = 'broken'\n"
        "    def acquire(self): return []\n"
        "    def extract(self, snapshots): return []\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    with pytest.raises(ImportError, match="dependencies is missing"):
        resolve_adapter("broken_plugin.adapter:BrokenAdapter")


def test_adapter_reports_missing_plugin_attribute():
    with pytest.raises(ValueError, match="has no attribute 'MissingAdapter'"):
        resolve_adapter("registry_builder.adapters.standard_json:MissingAdapter")


def test_storage_resolves_registered_short_name():
    assert resolve_storage_backend("memory") is MemoryRegistryStore


def test_storage_resolves_colon_plugin_path():
    store = create_store({"type": "registry_builder.storage.memory:MemoryRegistryStore"})
    assert isinstance(store, MemoryRegistryStore)


def test_storage_rejects_non_store_class():
    with pytest.raises(TypeError, match="not a subclass of RegistryStore"):
        resolve_storage_backend("json:JSONDecoder")
