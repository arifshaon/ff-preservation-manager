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

# Acquisition query only.  Deliberately anchored on PRONOM ID (P2749), because
# the first use of Wikidata in this project is as a cross-registry metadata
# source for formats that can be joined back to the authoritative PUID path.
# Multi-valued properties are aggregated so the CSV has one row per QID/PUID
# instead of a Cartesian product of extensions, MIME types and developers.
DEFAULT_FILE_FORMAT_QUERY = r"""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT
  ?format
  ?qid
  ?puid
  (SAMPLE(?formatLabelValue) AS ?formatLabel)
  (GROUP_CONCAT(DISTINCT ?locFdd; separator="|") AS ?locFdd)
  (GROUP_CONCAT(DISTINCT ?extension; separator="|") AS ?extension)
  (GROUP_CONCAT(DISTINCT ?mimeType; separator="|") AS ?mimeType)
  (GROUP_CONCAT(DISTINCT ?developerQid; separator="|") AS ?developerQid)
  (GROUP_CONCAT(DISTINCT ?developerLabelValue; separator="|") AS ?developerLabel)
  (GROUP_CONCAT(DISTINCT ?publicationDateValue; separator="|") AS ?publicationDate)
  (GROUP_CONCAT(DISTINCT ?inceptionDateValue; separator="|") AS ?inceptionDate)
WHERE {
  ?format wdt:P2749 ?puid .
  BIND(REPLACE(STR(?format), "^.*/", "") AS ?qid)

  OPTIONAL {
    ?format rdfs:label ?formatLabelValue .
    FILTER(LANG(?formatLabelValue) = "en")
  }
  OPTIONAL { ?format wdt:P3267 ?locFdd . }
  OPTIONAL { ?format wdt:P1195 ?extension . }
  OPTIONAL { ?format wdt:P1163 ?mimeType . }
  OPTIONAL {
    ?format wdt:P178 ?developer .
    BIND(REPLACE(STR(?developer), "^.*/", "") AS ?developerQid)
    OPTIONAL {
      ?developer rdfs:label ?developerLabelValue .
      FILTER(LANG(?developerLabelValue) = "en")
    }
  }
  OPTIONAL {
    ?format wdt:P577 ?publicationDate .
    BIND(STR(?publicationDate) AS ?publicationDateValue)
  }
  OPTIONAL {
    ?format wdt:P571 ?inceptionDate .
    BIND(STR(?inceptionDate) AS ?inceptionDateValue)
  }
}
GROUP BY ?format ?qid ?puid
ORDER BY ?puid
""".strip()


class WikidataSparqlAdapter(SourceAdapter):
    """Download Wikidata file-format crosswalk metadata without ingesting it.

    This adapter is intentionally acquisition-only at this stage.  It snapshots
    the raw CSV returned by the Wikidata Query Service and can copy that snapshot
    to a stable user-facing file.  ``extract`` returns no RawFormatRecord objects
    so enabling or invoking this adapter cannot change canonical identities,
    criterion claims, risk scores, or MongoDB state until a later reviewed
    normalization/reconciliation design is implemented.
    """

    type_name = "wikidata_sparql"

    @property
    def endpoint(self) -> str:
        return str(self.config.get("endpoint") or DEFAULT_ENDPOINT)

    @property
    def query(self) -> str:
        query_file = self.config.get("query_file")
        if query_file:
            return Path(query_file).read_text(encoding="utf-8").strip()
        return str(self.config.get("query") or DEFAULT_FILE_FORMAT_QUERY).strip()

    @property
    def user_agent(self) -> str:
        return str(self.config.get("user_agent") or DEFAULT_USER_AGENT)

    def _query_sha256(self) -> str:
        return hashlib.sha256(self.query.encode("utf-8")).hexdigest()

    def _cache_key(self) -> str:
        return f"{self.endpoint}#query-sha256={self._query_sha256()}&format=csv"

    def _request_csv(self) -> tuple[bytes, dict[str, str]]:
        timeout = max(1, int(self.config.get("timeout_seconds", 90)))
        retries = max(0, int(self.config.get("retries", 3)))
        payload = urlencode({"query": self.query}).encode("utf-8")
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/csv",
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        }

        last_error: Exception | None = None
        for attempt in range(retries + 1):
            request = Request(self.endpoint, data=payload, headers=headers, method="POST")
            try:
                with urlopen(request, timeout=timeout) as response:
                    data = response.read()
                    response_headers = {k.lower(): v for k, v in response.headers.items()}
                self._validate_csv(data)
                return data, response_headers
            except HTTPError as exc:
                last_error = exc
                if exc.code not in {429, 502, 503, 504} or attempt >= retries:
                    raise
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    delay = float(retry_after) if retry_after is not None else float(2 ** attempt)
                except ValueError:
                    delay = float(2 ** attempt)
                time.sleep(max(1.0, min(delay, 30.0)))

        assert last_error is not None
        raise last_error

    @staticmethod
    def _validate_csv(data: bytes) -> None:
        if not data:
            raise ValueError("Wikidata SPARQL response was empty")
        text = data.decode("utf-8-sig", errors="strict")
        reader = csv.reader(io.StringIO(text))
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError("Wikidata SPARQL response did not contain a CSV header") from exc
        required = {"format", "qid", "puid"}
        if not required.issubset(set(header)):
            raise ValueError(
                "Wikidata SPARQL response did not look like the expected CSV; "
                f"required columns={sorted(required)}, received={header}"
            )

    @staticmethod
    def _row_count(data: bytes) -> int:
        text = data.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text))
        try:
            next(reader)
        except StopIteration:
            return 0
        return sum(1 for _ in reader)

    def acquire(self) -> list[SourceSnapshot]:
        query_sha256 = self._query_sha256()
        cache_key = self._cache_key()
        metadata: dict[str, Any] = {
            "endpoint": self.endpoint,
            "query_sha256": query_sha256,
            "query": self.query,
            "result_format": "text/csv",
            "acquisition_only": True,
            "normalization_enabled": False,
        }

        if self.offline:
            cached = self._cached_snapshot(
                uri=cache_key,
                suffix=".csv",
                note="wikidata_sparql; acquisition_only=true",
                content_type="text/csv",
                metadata=metadata,
            )
            if cached is None:
                raise FileNotFoundError(
                    "Offline mode requested but no cached Wikidata snapshot exists "
                    f"for query {query_sha256}"
                )
            cached.uri = self.endpoint
            return [cached]

        data, response_headers = self._request_csv()
        metadata["row_count"] = self._row_count(data)
        metadata["response_content_type"] = response_headers.get("content-type")
        snapshot = self._store_snapshot_bytes(
            index_key=cache_key,
            uri=self.endpoint,
            data=data,
            suffix=".csv",
            note="wikidata_sparql; acquisition_only=true",
            content_type=response_headers.get("content-type") or "text/csv",
            metadata=metadata,
        )
        return [snapshot]

    def download_to(self, output_path: str | Path) -> SourceSnapshot:
        snapshots = self.acquire()
        if len(snapshots) != 1:
            raise RuntimeError(f"Expected one Wikidata snapshot, received {len(snapshots)}")
        snapshot = snapshots[0]
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(Path(snapshot.local_path).read_bytes())
        snapshot.metadata = dict(snapshot.metadata)
        snapshot.metadata["download_path"] = str(output)
        return snapshot

    def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
        # Deliberately no ingestion yet.  The Wikidata source must be studied and
        # its identifier authority/scope rules agreed before it participates in
        # normalization or reconciliation.
        return []
