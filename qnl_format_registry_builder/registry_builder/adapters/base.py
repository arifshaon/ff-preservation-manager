from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from registry_builder.models import RawFormatRecord, SourceSnapshot


class SourceAdapter(ABC):
    type_name: str = "base"

    def __init__(self, source_config: dict[str, Any], workdir: Path):
        self.config = source_config
        self.workdir = workdir
        self.source_id = source_config["id"]

    @abstractmethod
    def acquire(self) -> list[SourceSnapshot]:
        """Retrieve or access source material and return immutable local snapshots."""

    @abstractmethod
    def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
        """Parse snapshots and return raw source records in the internal interchange model."""
