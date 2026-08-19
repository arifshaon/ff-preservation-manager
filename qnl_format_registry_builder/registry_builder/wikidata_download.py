from __future__ import annotations

import argparse
from http.client import HTTPException
import json
from pathlib import Path
import socket
import sys
import time
from urllib.error import URLError

from registry_builder.adapters.wikidata_sparql import (
    DEFAULT_ENDPOINT,
    DEFAULT_USER_AGENT,
    WikidataSparqlAdapter,
)


class _TransportRetryingWikidataSparqlAdapter(WikidataSparqlAdapter):
    """Retry a single SPARQL part when the HTTP body is interrupted mid-transfer.

    The underlying adapter already retries retryable HTTP status responses. This
    wrapper adds transport-level retries for cases such as IncompleteRead,
    RemoteDisconnected, connection resets, socket timeouts, and URLError. Because
    the retry happens around ``_request_csv``, only the failing query part is
    repeated; already-merged earlier parts remain in memory for the current run.
    """

    def _request_csv(
        self,
        query: str,
        *,
        query_name: str,
        required_columns: set[str],
    ) -> tuple[bytes, dict[str, str]]:
        retries = max(0, int(self.config.get("transport_retries", 5)))
        base_delay = max(0.0, float(self.config.get("transport_backoff_seconds", 2.0)))

        for attempt in range(retries + 1):
            try:
                return super()._request_csv(
                    query,
                    query_name=query_name,
                    required_columns=required_columns,
                )
            except (HTTPException, URLError, ConnectionError, TimeoutError, socket.timeout, OSError) as exc:
                if attempt >= retries:
                    raise RuntimeError(
                        f"Wikidata SPARQL query '{query_name}' failed after "
                        f"{retries + 1} transport attempt(s): "
                        f"{type(exc).__name__}: {exc}"
                    ) from exc

                delay = min(base_delay * (2**attempt), 30.0)
                print(
                    f"[wikidata] query '{query_name}' transfer interrupted "
                    f"({type(exc).__name__}: {exc}); retrying "
                    f"{attempt + 1}/{retries} in {delay:.1f}s...",
                    file=sys.stderr,
                    flush=True,
                )
                if delay:
                    time.sleep(delay)

        raise AssertionError("unreachable")


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
    parser.add_argument("--query-file", help="Optional SPARQL query file; otherwise use the built-in partitioned file-format acquisition")
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument("--retries", type=int, default=3, help="Retries for retryable HTTP status responses such as 429/5xx")
    parser.add_argument("--transport-retries", type=int, default=5, help="Retries for interrupted/partial HTTP transfers")
    parser.add_argument("--transport-backoff-seconds", type=float, default=2.0, help="Initial exponential backoff for interrupted transfers")
    parser.add_argument("--offline", action="store_true", help="Reuse the cached snapshot for the same query set; do not contact Wikidata")
    args = parser.parse_args()

    source_config = {
        "id": "wikidata_file_formats",
        "type": "wikidata_sparql",
        "endpoint": args.endpoint,
        "user_agent": args.user_agent,
        "timeout_seconds": args.timeout_seconds,
        "retries": args.retries,
        "transport_retries": args.transport_retries,
        "transport_backoff_seconds": args.transport_backoff_seconds,
        "offline": args.offline,
    }
    if args.query_file:
        source_config["query_file"] = args.query_file

    adapter = _TransportRetryingWikidataSparqlAdapter(source_config, Path(args.workdir))
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
        "query_mode": snapshot.metadata.get("query_mode"),
        "query_parts": snapshot.metadata.get("query_parts"),
        "from_cache": snapshot.from_cache,
        "changed": snapshot.changed,
        "acquisition_only": True,
        "registry_records_created": 0,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
