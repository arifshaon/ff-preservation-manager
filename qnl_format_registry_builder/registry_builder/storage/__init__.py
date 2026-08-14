from __future__ import annotations

from registry_builder.plugins import resolve_plugin
from registry_builder.storage.file import FileRegistryStore
from registry_builder.storage.memory import MemoryRegistryStore
from registry_builder.storage.mongo import MongoRegistryStore

STORAGE_BACKENDS = {
    "memory": MemoryRegistryStore,
    "file": FileRegistryStore,
    "json_file": FileRegistryStore,
    "mongodb": MongoRegistryStore,
}


def resolve_storage_backend(storage_type: str):
    return resolve_plugin(storage_type, STORAGE_BACKENDS, plugin_kind="storage backend")


def create_store(config):
    storage_type = config.get("type", "memory")
    store_cls = resolve_storage_backend(storage_type)
    return store_cls(config)
