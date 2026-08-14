from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from registry_builder.exporters.base import RegistryExporter


@dataclass
class JsonlExporter(RegistryExporter):
    """Placeholder JSONL exporter for the adapter-based export layer."""

    config: dict[str, Any]

    def export(self, registry_view: list[dict[str, Any]], context: dict[str, Any]) -> None:
        raise NotImplementedError("Move existing JSONL export logic into this adapter during pipeline refactor.")
