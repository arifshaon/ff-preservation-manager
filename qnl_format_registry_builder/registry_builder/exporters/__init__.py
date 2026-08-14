from __future__ import annotations

from registry_builder.exporters.csv_exporter import CsvExporter
from registry_builder.exporters.json_exporter import JsonExporter
from registry_builder.exporters.jsonl_exporter import JsonlExporter
from registry_builder.exporters.markdown_reporter import MarkdownReportExporter
from registry_builder.exporters.sqlite_exporter import SqliteExporter

EXPORTERS = {
    "json": JsonExporter,
    "jsonl": JsonlExporter,
    "csv": CsvExporter,
    "sqlite": SqliteExporter,
    "markdown_report": MarkdownReportExporter,
}


def create_exporter(config):
    export_type = config["type"]
    exporter_cls = EXPORTERS.get(export_type)
    if exporter_cls is None:
        raise ValueError(f"No exporter registered for type: {export_type}")
    return exporter_cls(config)
