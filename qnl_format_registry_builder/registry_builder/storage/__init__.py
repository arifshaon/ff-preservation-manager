from __future__ import annotations

from registry_builder.storage.file import FileRegistryStore
from registry_builder.storage.memory import MemoryRegistryStore
from registry_builder.storage.mongo import MongoRegistryStore

STORAGE_BACKENDS = {
    "memory": MemoryRegistryStore,
    "file": FileRegistryStore,
    "json_file": FileRegistryStore,
    "mongodb": MongoRegistryStore,
}


def create_store(config):
    storage_type = config.get("type", "memory")
    store_cls = STORAGE_BACKENDS.get(storage_type)
    if store_cls is None:
        raise ValueError(f"No storage backend registered for type: {storage_type}")
    return store_cls(config)
