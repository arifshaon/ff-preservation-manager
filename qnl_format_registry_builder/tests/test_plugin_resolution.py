from registry_builder.adapters import resolve_adapter
from registry_builder.adapters.standard_json import StandardJsonAdapter
from registry_builder.storage import create_store, resolve_storage_backend
from registry_builder.storage.memory import MemoryRegistryStore


def test_adapter_resolves_registered_short_name():
    assert resolve_adapter("standard_json") is StandardJsonAdapter


def test_adapter_resolves_dotted_path():
    assert resolve_adapter("registry_builder.adapters.standard_json:StandardJsonAdapter") is StandardJsonAdapter


def test_storage_resolves_registered_short_name():
    assert resolve_storage_backend("memory") is MemoryRegistryStore


def test_storage_resolves_dotted_path():
    store = create_store({"type": "registry_builder.storage.memory:MemoryRegistryStore"})
    assert isinstance(store, MemoryRegistryStore)
