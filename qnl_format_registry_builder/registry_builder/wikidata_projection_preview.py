from __future__ import annotations

import argparse
import json
from pathlib import Path

from registry_builder.utils import write_json, write_jsonl
from registry_builder.wikidata_projection import (
    project_wikidata_csv,
    projection_summary,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m registry_builder.wikidata_projection_preview",
        description=(
            "Project an acquired Wikidata policy-v3 CSV into source-native "
            "RawFormatRecord-shaped records without reconciliation or persistence."
        ),
    )
    parser.add_argument("--input", required=True, help="Acquired Wikidata CSV")
    parser.add_argument(
        "--out",
        default="out/wikidata-projection-preview.json",
        help="Summary JSON output",
    )
    parser.add_argument(
        "--records-out",
        help="Optional JSONL output containing every projected source-native record",
    )
    parser.add_argument(
        "--source-id",
        default="wikidata_file_formats",
        help="Source ID recorded on projected rows",
    )
    args = parser.parse_args()

    records = project_wikidata_csv(args.input, source_id=args.source_id)
    summary = projection_summary(records)
    summary["input_file"] = str(Path(args.input))
    summary["summary_file"] = str(Path(args.out))

    if args.records_out:
        write_jsonl(args.records_out, [record.to_dict() for record in records])
        summary["records_file"] = str(Path(args.records_out))

    write_json(args.out, summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
