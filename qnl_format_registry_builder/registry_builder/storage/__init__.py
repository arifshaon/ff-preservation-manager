from __future__ import annotations

from registry_builder.plugins import build_registry, resolve_plugin
from registry_builder.storage.base import RegistryStore
from registry_builder.storage.file import FileRegistryStore
from registry_builder.storage.memory import MemoryRegistryStore
from registry_builder.storage.mongo import MongoRegistryStore

STORAGE_BACKENDS: dict[str, type[RegistryStore]] = build_registry(
    [
        ("memory", MemoryRegistryStore),
        ("file", FileRegistryStore),
        ("json_file", FileRegistryStore),
        ("mongodb", MongoRegistryStore),
    ],
    plugin_kind="storage backend",
)


def resolve_storage_backend(storage_type: str) -> type[RegistryStore]:
    return resolve_plugin(storage_type, STORAGE_BACKENDS, plugin_kind="storage backend", expected_base=RegistryStore)


def create_store(config):
    storage_type = config.get("type", "memory")
    store_cls = resolve_storage_backend(storage_type)
    return store_cls(config)
