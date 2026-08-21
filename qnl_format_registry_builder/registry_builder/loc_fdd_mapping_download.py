from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from registry_builder.adapters.loc_fdd_mapping_csv import (
    DEFAULT_LOC_FDD_MAPPING_DATE,
    LocFddMappingCsvAdapter,
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
        "row_number",
        "mapping_date",
        "title",
        "fdd_ids",
        "puids",
        "wikidata_qids",
        "mapping_context",
        "source_url",
        "snapshot_sha256",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for entry in entries:
            writer.writerow({field: _csv_value(entry.get(field)) for field in fields})


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m registry_builder.loc_fdd_mapping_download",
        description=(
            "Acquire LOC's monthly FDD-PUID-QID CSV and write a structured review dataset. "
            "The crosswalk remains evidence-only until mapping granularity is reviewed."
        ),
    )
    parser.add_argument("--out", default=f"loc-fdd-puid-qid-{DEFAULT_LOC_FDD_MAPPING_DATE}.json")
    parser.add_argument("--csv", help="Optional CSV review output; defaults to the JSON stem with .csv")
    parser.add_argument("--workdir", default="work")
    parser.add_argument("--mapping-date", default=DEFAULT_LOC_FDD_MAPPING_DATE)
    parser.add_argument("--mapping-url", help="Override the LOC monthly crosswalk URL")
    parser.add_argument("--local-file", help="Use a local crosswalk CSV as source material")
    parser.add_argument("--offline", action="store_true", help="Reuse a cached snapshot")
    args = parser.parse_args()

    source_config: dict[str, Any] = {
        "id": f"loc_fdd_mapping_{args.mapping_date}",
        "type": "loc_fdd_mapping_csv",
        "mapping_date": args.mapping_date,
        "offline": args.offline,
    }
    if args.mapping_url:
        source_config["mapping_url"] = args.mapping_url
    if args.local_file:
        source_config["local_file"] = args.local_file

    adapter = LocFddMappingCsvAdapter(source_config, Path(args.workdir))
    snapshots = adapter.acquire()
    entries = adapter.extract_entries(snapshots)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    csv_path = Path(args.csv) if args.csv else out_path.with_suffix(".csv")
    _write_csv(csv_path, entries)

    snapshot = snapshots[0] if snapshots else None
    context_columns = sorted({key for entry in entries for key in (entry.get("mapping_context") or {})})
    result = {
        "status": "ok",
        "source_id": source_config["id"],
        "source_type": "loc_fdd_mapping_csv",
        "mapping_date": args.mapping_date,
        "mapping_url": adapter._mapping_url(),
        "output_file": str(out_path),
        "csv_file": str(csv_path),
        "snapshot_file": snapshot.local_path if snapshot else None,
        "sha256": snapshot.sha256 if snapshot else None,
        "changed": snapshot.changed if snapshot else None,
        "from_cache": snapshot.from_cache if snapshot else None,
        "row_count": len(entries),
        "rows_with_fdd": sum(1 for entry in entries if entry.get("fdd_ids")),
        "rows_with_puid": sum(1 for entry in entries if entry.get("puids")),
        "rows_with_qid": sum(1 for entry in entries if entry.get("wikidata_qids")),
        "distinct_fdd_ids": len({value for entry in entries for value in entry.get("fdd_ids") or []}),
        "distinct_puids": len({value for entry in entries for value in entry.get("puids") or []}),
        "distinct_qids": len({value for entry in entries for value in entry.get("wikidata_qids") or []}),
        "mapping_context_columns": context_columns,
        "identity_projection": False,
        "canonical_registry_records_created": 0,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
