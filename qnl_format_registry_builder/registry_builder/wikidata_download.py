from __future__ import annotations

import argparse
import json
from pathlib import Path

from registry_builder.adapters.wikidata_sparql import (
    DEFAULT_ENDPOINT,
    DEFAULT_USER_AGENT,
    WikidataSparqlAdapter,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m registry_builder.wikidata_download",
        description=(
            "Download Wikidata file-format metadata to CSV without ingesting it "
            "into the registry."
        ),
    )
    parser.add_argument("--out", default="wikidata-file-formats.csv", help="CSV file to write")
    parser.add_argument("--workdir", default="work", help="Snapshot/cache work directory")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--query-file", help="Optional SPARQL query file; otherwise use the built-in file-format query")
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--offline", action="store_true", help="Reuse the cached snapshot for the same query; do not contact Wikidata")
    args = parser.parse_args()

    source_config = {
        "id": "wikidata_file_formats",
        "type": "wikidata_sparql",
        "endpoint": args.endpoint,
        "user_agent": args.user_agent,
        "timeout_seconds": args.timeout_seconds,
        "retries": args.retries,
        "offline": args.offline,
    }
    if args.query_file:
        source_config["query_file"] = args.query_file

    adapter = WikidataSparqlAdapter(source_config, Path(args.workdir))
    snapshot = adapter.download_to(args.out)
    result = {
        "status": "ok",
        "source_id": snapshot.source_id,
        "source_type": snapshot.source_type,
        "endpoint": snapshot.uri,
        "output_file": str(Path(args.out)),
        "snapshot_file": snapshot.local_path,
        "sha256": snapshot.sha256,
        "row_count": snapshot.metadata.get("row_count"),
        "query_sha256": snapshot.metadata.get("query_sha256"),
        "from_cache": snapshot.from_cache,
        "changed": snapshot.changed,
        "acquisition_only": True,
        "registry_records_created": 0,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
