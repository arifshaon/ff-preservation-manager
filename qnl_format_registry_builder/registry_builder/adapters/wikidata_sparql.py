from __future__ import annotations

import csv
import hashlib
import io
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from registry_builder.adapters.base import SourceAdapter
from registry_builder.models import RawFormatRecord, SourceSnapshot


DEFAULT_ENDPOINT = "https://query.wikidata.org/sparql"
DEFAULT_USER_AGENT = (
    "QNL-Format-Registry-Builder/0.1 "
    "(https://github.com/arifshaon/ff-preservation-manager)"
)

_PREFIXES = """\
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""

DEFAULT_QUERY_PARTS: dict[str, str] = {
    "core": (
        _PREFIXES
        + r"""
SELECT ?format ?qid ?puid ?formatLabel WHERE {
  ?format wdt:P2749 ?puid .
  BIND(REPLACE(STR(?format), "^.*/", "") AS ?qid)
  OPTIONAL {
    ?format rdfs:label ?formatLabel .
    FILTER(LANG(?formatLabel) = "en")
  }
}
ORDER BY ?puid ?format
""".strip()
    ),
    "loc_fdd": (
        _PREFIXES
        + r"""
SELECT ?format ?puid ?locFdd WHERE {
  ?format wdt:P2749 ?puid ;
          wdt:P3267 ?locFdd .
}
ORDER BY ?puid ?format ?locFdd
""".strip()
    ),
    "extension": (
        _PREFIXES
        + r"""
SELECT ?format ?puid ?extension WHERE {
  ?format wdt:P2749 ?puid ;
          wdt:P1195 ?extension .
}
ORDER BY ?puid ?format ?extension
""".strip()
    ),
    "mime_type": (
        _PREFIXES
        + r"""
SELECT ?format ?puid ?mimeType WHERE {
  ?format wdt:P2749 ?puid ;
          wdt:P1163 ?mimeType .
}
ORDER BY ?puid ?format ?mimeType
""".strip()
    ),
    "developer": (
        _PREFIXES
        + r"""
SELECT ?format ?puid ?developerQid ?developerLabel WHERE {
  ?format wdt:P2749 ?puid ;
          wdt:P178 ?developer .
  BIND(REPLACE(STR(?developer), "^.*/", "") AS ?developerQid)
  OPTIONAL {
    ?developer rdfs:label ?developerLabel .
    FILTER(LANG(?developerLabel) = "en")
  }
}
ORDER BY ?puid ?format ?developerQid
""".strip()
    ),
    "publication_date": (
        _PREFIXES
        + r"""
SELECT ?format ?puid ?publicationDate WHERE {
  ?format wdt:P2749 ?puid ;
          wdt:P577 ?publicationDate .
}
ORDER BY ?puid ?format ?publicationDate
""".strip()
    ),
    "inception_date": (
        _PREFIXES
        + r"""
SELECT ?format ?puid ?inceptionDate WHERE {
  ?format wdt:P2749 ?puid ;
          wdt:P571 ?inceptionDate .
}
ORDER BY ?puid ?format ?inceptionDate
""".strip()
    ),
}

# Backwards-compatible name for callers that inspect the primary/default query.
# Normal acquisition uses DEFAULT_QUERY_PARTS.
DEFAULT_FILE_FORMAT_QUERY = DEFAULT_QUERY_PARTS["core"]

_OUTPUT_COLUMNS = [
    "format",
    "qid",
    "puid",
    "formatLabel",
    "locFdd",
    "extension",
    "mimeType",
    "developerQid",
    "developerLabel",
    "publicationDate",
    "inceptionDate",
]


class WikidataSparqlAdapter(SourceAdapter):
    """Download Wikidata file-format crosswalk metadata without ingesting it.

    Default acquisition deliberately uses several small SPARQL queries and merges
    them locally. This avoids one large OPTIONAL/GROUP_CONCAT query that can hit
    the public Wikidata Query Service execution limit. The final CSV remains
    acquisition-only: ``extract`` returns no RawFormatRecord objects, so Wikidata
    cannot affect canonical identities, criterion claims, risk scores, or MongoDB.
    """

    type_name = "wikidata_sparql"

    @property
    def endpoint(self) -> str:
        return str(self.config.get("endpoint") or DEFAULT_ENDPOINT)

    @property
    def custom_query(self) -> str | None:
        query_file = self.config.get("query_file")
        if query_file:
            return Path(query_file).read_text(encoding="utf-8").strip()
        query = self.config.get("query")
        return str(query).strip() if query else None

    @property
    def query(self) -> str:
        return self.custom_query or DEFAULT_FILE_FORMAT_QUERY

    @property
    def user_agent(self) -> str:
        return str(self.config.get("user_agent") or DEFAULT_USER_AGENT)

    def _query_material(self) -> str:
        if self.custom_query:
            return self.custom_query
        return "\n\n".join(
            f"### {name}\n{query}" for name, query in DEFAULT_QUERY_PARTS.items()
        )

    def _query_sha256(self) -> str:
        return hashlib.sha256(self._query_material().encode("utf-8")).hexdigest()

    def _cache_key(self) -> str:
        mode = "custom" if self.custom_query else "partitioned-default"
        return (
            f"{self.endpoint}#query-sha256={self._query_sha256()}"
            f"&format=csv&mode={mode}"
        )

    def _request_csv(
        self,
        query: str,
        *,
        query_name: str,
        required_columns: set[str],
    ) -> tuple[bytes, dict[str, str]]:
        timeout = max(1, int(self.config.get("timeout_seconds", 90)))
        retries = max(0, int(self.config.get("retries", 3)))
        payload = urlencode({"query": query}).encode("utf-8")
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/csv",
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        }

        last_error: Exception | None = None
        last_body = ""
        for attempt in range(retries + 1):
            request = Request(self.endpoint, data=payload, headers=headers, method="POST")
            try:
                with urlopen(request, timeout=timeout) as response:
                    data = response.read()
                    response_headers = {
                        k.lower(): v for k, v in response.headers.items()
                    }
                self._validate_csv(data, required_columns=required_columns)
                return data, response_headers
            except HTTPError as exc:
                last_error = exc
                try:
                    last_body = exc.read().decode("utf-8", errors="replace").strip()
                except Exception:
                    last_body = ""
                retryable = exc.code in {429, 500, 502, 503, 504}
                if not retryable or attempt >= retries:
                    detail = f": {last_body[:500]}" if last_body else ""
                    raise RuntimeError(
                        f"Wikidata SPARQL query '{query_name}' failed with "
                        f"HTTP {exc.code}{detail}"
                    ) from exc

                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    delay = (
                        float(retry_after)
                        if retry_after is not None
                        else float(2**attempt)
                    )
                except ValueError:
                    delay = float(2**attempt)
                time.sleep(max(1.0, min(delay, 30.0)))

        assert last_error is not None
        raise last_error

    @staticmethod
    def _validate_csv(data: bytes, *, required_columns: set[str]) -> None:
        if not data:
            raise ValueError("Wikidata SPARQL response was empty")
        text = data.decode("utf-8-sig", errors="strict")
        reader = csv.reader(io.StringIO(text))
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(
                "Wikidata SPARQL response did not contain a CSV header"
            ) from exc
        if not required_columns.issubset(set(header)):
            raise ValueError(
                "Wikidata SPARQL response did not look like the expected CSV; "
                f"required columns={sorted(required_columns)}, received={header}"
            )

    @staticmethod
    def _read_rows(data: bytes) -> list[dict[str, str]]:
        text = data.decode("utf-8-sig")
        return [
            {str(k): str(v or "") for k, v in row.items()}
            for row in csv.DictReader(io.StringIO(text))
        ]

    @staticmethod
    def _row_count(data: bytes) -> int:
        return len(WikidataSparqlAdapter._read_rows(data))

    @staticmethod
    def _qid_from_uri(uri: str) -> str:
        return str(uri or "").rstrip("/").rsplit("/", 1)[-1]

    @staticmethod
    def _new_merged_row(format_uri: str, puid: str) -> dict[str, Any]:
        return {
            "format": format_uri,
            "qid": WikidataSparqlAdapter._qid_from_uri(format_uri),
            "puid": puid,
            "formatLabel": "",
            "locFdd": set(),
            "extension": set(),
            "mimeType": set(),
            "developers": {},
            "publicationDate": set(),
            "inceptionDate": set(),
        }

    @staticmethod
    def _ensure_merged_row(
        rows: dict[tuple[str, str], dict[str, Any]],
        format_uri: str,
        puid: str,
    ) -> dict[str, Any]:
        key = (format_uri, puid)
        if key not in rows:
            rows[key] = WikidataSparqlAdapter._new_merged_row(format_uri, puid)
        return rows[key]

    def _fetch_partitioned_default(self) -> tuple[bytes, dict[str, Any]]:
        merged: dict[tuple[str, str], dict[str, Any]] = {}
        part_stats: dict[str, Any] = {}

        specs = {
            "core": {"format", "qid", "puid", "formatLabel"},
            "loc_fdd": {"format", "puid", "locFdd"},
            "extension": {"format", "puid", "extension"},
            "mime_type": {"format", "puid", "mimeType"},
            "developer": {"format", "puid", "developerQid", "developerLabel"},
            "publication_date": {"format", "puid", "publicationDate"},
            "inception_date": {"format", "puid", "inceptionDate"},
        }

        for name, query in DEFAULT_QUERY_PARTS.items():
            data, headers = self._request_csv(
                query,
                query_name=name,
                required_columns=specs[name],
            )
            rows = self._read_rows(data)
            part_stats[name] = {
                "row_count": len(rows),
                "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
                "content_type": headers.get("content-type"),
            }

            for source_row in rows:
                format_uri = source_row.get("format", "")
                puid = source_row.get("puid", "")
                if not format_uri or not puid:
                    continue
                target = self._ensure_merged_row(merged, format_uri, puid)

                if name == "core":
                    target["qid"] = source_row.get("qid") or target["qid"]
                    if source_row.get("formatLabel"):
                        target["formatLabel"] = source_row["formatLabel"]
                elif name == "loc_fdd":
                    if source_row.get("locFdd"):
                        target["locFdd"].add(source_row["locFdd"])
                elif name == "extension":
                    if source_row.get("extension"):
                        target["extension"].add(source_row["extension"])
                elif name == "mime_type":
                    if source_row.get("mimeType"):
                        target["mimeType"].add(source_row["mimeType"])
                elif name == "developer":
                    qid = source_row.get("developerQid", "")
                    if qid:
                        label = source_row.get("developerLabel", "")
                        previous = target["developers"].get(qid, "")
                        target["developers"][qid] = previous or label
                elif name == "publication_date":
                    if source_row.get("publicationDate"):
                        target["publicationDate"].add(source_row["publicationDate"])
                elif name == "inception_date":
                    if source_row.get("inceptionDate"):
                        target["inceptionDate"].add(source_row["inceptionDate"])

        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=_OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()

        for target in sorted(
            merged.values(),
            key=lambda row: (str(row["puid"]), str(row["qid"]), str(row["format"])),
        ):
            developer_items = sorted(target["developers"].items())
            writer.writerow(
                {
                    "format": target["format"],
                    "qid": target["qid"],
                    "puid": target["puid"],
                    "formatLabel": target["formatLabel"],
                    "locFdd": "|".join(sorted(target["locFdd"])),
                    "extension": "|".join(sorted(target["extension"])),
                    "mimeType": "|".join(sorted(target["mimeType"])),
                    "developerQid": "|".join(qid for qid, _ in developer_items),
                    "developerLabel": "|".join(label for _, label in developer_items),
                    "publicationDate": "|".join(sorted(target["publicationDate"])),
                    "inceptionDate": "|".join(sorted(target["inceptionDate"])),
                }
            )

        csv_bytes = output.getvalue().encode("utf-8")
        self._validate_csv(
            csv_bytes,
            required_columns={"format", "qid", "puid"},
        )
        return csv_bytes, part_stats

    def acquire(self) -> list[SourceSnapshot]:
        query_sha256 = self._query_sha256()
        cache_key = self._cache_key()
        query_mode = "custom_single_query" if self.custom_query else "partitioned_default"
        metadata: dict[str, Any] = {
            "endpoint": self.endpoint,
            "query_sha256": query_sha256,
            "query_mode": query_mode,
            "result_format": "text/csv",
            "acquisition_only": True,
            "normalization_enabled": False,
        }

        if self.custom_query:
            metadata["query"] = self.custom_query
        else:
            metadata["queries"] = dict(DEFAULT_QUERY_PARTS)

        if self.offline:
            cached = self._cached_snapshot(
                uri=cache_key,
                suffix=".csv",
                note=f"wikidata_sparql; acquisition_only=true; mode={query_mode}",
                content_type="text/csv",
                metadata=metadata,
            )
            if cached is None:
                raise FileNotFoundError(
                    "Offline mode requested but no cached Wikidata snapshot exists "
                    f"for query set {query_sha256}"
                )
            cached.uri = self.endpoint
            return [cached]

        if self.custom_query:
            data, response_headers = self._request_csv(
                self.custom_query,
                query_name="custom",
                required_columns={"format", "qid", "puid"},
            )
            metadata["response_content_type"] = response_headers.get("content-type")
        else:
            data, part_stats = self._fetch_partitioned_default()
            metadata["query_parts"] = part_stats
            metadata["response_content_type"] = "text/csv; locally-merged=true"

        metadata["row_count"] = self._row_count(data)
        snapshot = self._store_snapshot_bytes(
            index_key=cache_key,
            uri=self.endpoint,
            data=data,
            suffix=".csv",
            note=f"wikidata_sparql; acquisition_only=true; mode={query_mode}",
            content_type="text/csv",
            metadata=metadata,
        )
        return [snapshot]

    def download_to(self, output_path: str | Path) -> SourceSnapshot:
        snapshots = self.acquire()
        if len(snapshots) != 1:
            raise RuntimeError(
                f"Expected one Wikidata snapshot, received {len(snapshots)}"
            )
        snapshot = snapshots[0]
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(Path(snapshot.local_path).read_bytes())
        snapshot.metadata = dict(snapshot.metadata)
        snapshot.metadata["download_path"] = str(output)
        return snapshot

    def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
        # Deliberately no ingestion yet. The Wikidata source must be studied and
        # its identifier authority/scope rules agreed before it participates in
        # normalization or reconciliation.
        return []
