from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class RegistryExporter(ABC):
    """Export adapter interface.

    Exporters generate optional output artifacts from the queryable registry
    view. They must not update storage or become a second source of truth.
    """

    @abstractmethod
    def export(self, registry_view: list[dict[str, Any]], context: dict[str, Any]) -> None:
        """Write an export using the supplied registry view and run context."""
