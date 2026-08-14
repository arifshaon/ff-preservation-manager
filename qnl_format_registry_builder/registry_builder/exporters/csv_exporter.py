from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from registry_builder.exporters.base import RegistryExporter


@dataclass
class CsvExporter(RegistryExporter):
    """Placeholder CSV exporter for the adapter-based export layer."""

    config: dict[str, Any]

    def export(self, registry_view: list[dict[str, Any]], context: dict[str, Any]) -> None:
        raise NotImplementedError("Move existing CSV export logic into this adapter during pipeline refactor.")
