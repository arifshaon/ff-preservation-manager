from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from registry_builder.exporters.base import RegistryExporter


@dataclass
class SqliteExporter(RegistryExporter):
    """Placeholder SQLite exporter for the adapter-based export layer.

    Existing `registry_builder/db.py` currently contains SQLite export logic. The
    next refactor should move that code into this adapter and rename `db.py` to
    avoid confusing exports with storage backends.
    """

    config: dict[str, Any]

    def export(self, registry_view: list[dict[str, Any]], context: dict[str, Any]) -> None:
        raise NotImplementedError("Move existing SQLite export logic into this adapter during pipeline refactor.")
