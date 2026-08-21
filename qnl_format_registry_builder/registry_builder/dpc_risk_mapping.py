from __future__ import annotations

import argparse
from dataclasses import fields
import json
from pathlib import Path
from typing import Any

from registry_builder.adapters.dpc_bit_list import _entry_to_evidence_record
from registry_builder.external_risk_mapping import apply_external_risk_mappings, load_external_risk_mapping
from registry_builder.models import CanonicalFormat

_DEFAULT_MAPPING = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "external_risk_mappings"
    / "dpc_bit_list_2025.v1.approved.json"
)
_CANONICAL_FIELDS = {field.name for field in fields(CanonicalFormat)}


def _load_registry(path: str | Path) -> list[CanonicalFormat]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Registry JSON must contain a list of canonical format objects")
    return [
        CanonicalFormat(**{key: value for key, value in row.items() if key in _CANONICAL_FIELDS})
        for row in data
    ]


def _load_dpc_records(path: str | Path):
    entries = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError("DPC review JSON must contain a list of entries")
    return [
        _entry_to_evidence_record(
            entry,
            source_id=str((entry.get("risk_assessment") or {}).get("source_id") or "dpc_bit_list_2025"),
            source_type="dpc_bit_list",
        )
        for entry in entries
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m registry_builder.dpc_risk_mapping",
        description=(
            "Preview or apply reviewed DPC Bit List risk mappings to an existing "
            "canonical registry JSON export. DPC source-native assessments remain intact."
        ),
    )
    parser.add_argument("--registry", required=True, help="Existing registry.json export")
    parser.add_argument("--dpc-json", default="dpc-bit-list-2025.json", help="DPC structured review JSON")
    parser.add_argument("--mapping", default=str(_DEFAULT_MAPPING), help="Reviewed DPC mapping JSON")
    parser.add_argument("--out", help="Write enriched registry JSON; omit for preview only")
    parser.add_argument("--include-drafts", action="store_true")
    args = parser.parse_args()

    registry = _load_registry(args.registry)
    records = _load_dpc_records(args.dpc_json)
    mapping = load_external_risk_mapping(args.mapping)
    report = apply_external_risk_mappings(
        registry,
        records,
        mapping,
        include_drafts=args.include_drafts,
    )

    by_id = {fmt.canonical_id: fmt for fmt in registry}
    applied_with_names: list[dict[str, Any]] = []
    for item in report.get("applied", []):
        row = dict(item)
        row["targets"] = [
            {
                "canonical_id": canonical_id,
                "preferred_name": by_id[canonical_id].preferred_name if canonical_id in by_id else None,
            }
            for canonical_id in item.get("target_canonical_ids", [])
        ]
        applied_with_names.append(row)
    report["applied"] = applied_with_names
    report["registry_count"] = len(registry)
    report["dpc_evidence_record_count"] = len(records)
    report["mode"] = "apply" if args.out else "preview"

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps([fmt.to_dict() for fmt in registry], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        report["output_file"] = str(out_path)

    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
