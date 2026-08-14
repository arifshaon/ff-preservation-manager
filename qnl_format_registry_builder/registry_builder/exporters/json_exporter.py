from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from registry_builder.exporters.base import RegistryExporter


@dataclass
class JsonExporter(RegistryExporter):
    """Placeholder JSON exporter for the adapter-based export layer.

    The current pipeline still writes JSON directly. The next refactor should move
    that logic here so exports are configuration-driven.
    """

    config: dict[str, Any]

    def export(self, registry_view: list[dict[str, Any]], context: dict[str, Any]) -> None:
        raise NotImplementedError("Move existing JSON export logic into this adapter during pipeline refactor.")
