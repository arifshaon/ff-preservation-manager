from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from registry_builder.adapters.dpc_bit_list import (
    DEFAULT_DPC_GITHUB_REF,
    DpcBitListAdapter,
)


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _write_csv(path: Path, entries: list[dict[str, Any]]) -> None:
    fields = [
        "source_record_id",
        "slug",
        "title",
        "description",
        "examples",
        "categories",
        "threats",
        "classification",
        "classification_label",
        "semantic_level",
        "imminence",
        "effort",
        "trends",
        "hazards",
        "mitigations",
        "year_added",
        "published",
        "last_updated",
        "source_url",
        "source_file",
        "snapshot_sha256",
        "edition",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for entry in entries:
            writer.writerow({field: _csv_value(entry.get(field)) for field in fields})


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m registry_builder.dpc_bit_list_download",
        description=(
            "Acquire the DPC Global Bit List source repository and write a "
            "structured review dataset without creating registry records."
        ),
    )
    parser.add_argument("--out", default="dpc-bit-list-2025.json", help="JSON review dataset")
    parser.add_argument("--csv", help="Optional CSV review dataset; defaults to the JSON stem with .csv")
    parser.add_argument("--workdir", default="work", help="Snapshot/cache work directory")
    parser.add_argument("--edition", default="2025")
    parser.add_argument("--github-ref", default=DEFAULT_DPC_GITHUB_REF)
    parser.add_argument("--archive-url", help="Override the DPC GitHub archive URL")
    parser.add_argument("--local-archive", help="Use a local DPC repository ZIP as source material")
    parser.add_argument("--offline", action="store_true", help="Reuse a previously cached archive snapshot")
    args = parser.parse_args()

    source_config: dict[str, Any] = {
        "id": f"dpc_bit_list_{args.edition}",
        "type": "dpc_bit_list",
        "edition": args.edition,
        "github_ref": args.github_ref,
        "offline": args.offline,
    }
    if args.archive_url:
        source_config["archive_url"] = args.archive_url
    if args.local_archive:
        source_config["local_archive"] = args.local_archive

    adapter = DpcBitListAdapter(source_config, Path(args.workdir))
    snapshots = adapter.acquire()
    entries = adapter.extract_entries(snapshots)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    csv_path = Path(args.csv) if args.csv else out_path.with_suffix(".csv")
    _write_csv(csv_path, entries)

    snapshot = snapshots[0] if snapshots else None
    classification_counts: dict[str, int] = {}
    scope_counts: dict[str, int] = {}
    for entry in entries:
        classification = str(entry.get("classification") or "unclassified")
        classification_counts[classification] = classification_counts.get(classification, 0) + 1
        scope = str((entry.get("risk_assessment") or {}).get("scope_type") or "unknown")
        scope_counts[scope] = scope_counts.get(scope, 0) + 1

    result = {
        "status": "ok",
        "source_id": source_config["id"],
        "source_type": "dpc_bit_list",
        "edition": args.edition,
        "github_ref": args.github_ref,
        "output_file": str(out_path),
        "csv_file": str(csv_path),
        "snapshot_file": snapshot.local_path if snapshot else None,
        "sha256": snapshot.sha256 if snapshot else None,
        "changed": snapshot.changed if snapshot else None,
        "from_cache": snapshot.from_cache if snapshot else None,
        "entry_count": len(entries),
        "classification_counts": dict(sorted(classification_counts.items())),
        "scope_counts": dict(sorted(scope_counts.items())),
        "acquisition_only": True,
        "registry_records_created": 0,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
