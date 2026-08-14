from __future__ import annotations

import pytest

from registry_builder.exporters import EXPORTERS, create_exporter


def test_exporter_registry_contains_expected_adapter_types():
    assert {"json", "jsonl", "csv", "sqlite", "markdown_report"}.issubset(EXPORTERS)


def test_create_exporter_rejects_unknown_type():
    with pytest.raises(ValueError):
        create_exporter({"type": "unknown"})
