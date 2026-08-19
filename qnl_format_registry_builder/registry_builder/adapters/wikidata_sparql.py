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
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX schema: <http://schema.org/>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
"""

# Primary population: items modelled as file formats (including instances of
# subclasses of Q235557). The P2748 UNION keeps PRONOM-linked file-format/family
# items even where Wikidata classification is incomplete.
_POPULATION = """\
{
  ?format wdt:P31/wdt:P279* wd:Q235557 .
}
UNION
{
  ?format wdt:P2748 ?_populationPuid .
}
"""

DEFAULT_QUERY_PARTS: dict[str, str] = {
    "core": (
        _PREFIXES
        + f"""
SELECT DISTINCT ?format ?qid ?formatLabel ?formatDescription WHERE {{
  {_POPULATION}
  BIND(REPLACE(STR(?format), "^.*/", "") AS ?qid)
  OPTIONAL {{
    ?format rdfs:label ?formatLabel .
    FILTER(LANG(?formatLabel) = "en")
  }}
  OPTIONAL {{
    ?format schema:description ?formatDescription .
    FILTER(LANG(?formatDescription) = "en")
  }}
}}
ORDER BY ?qid
""".strip()
    ),
    "aliases": (
        _PREFIXES
        + f"""
SELECT DISTINCT ?format ?alias WHERE {{
  {_POPULATION}
  ?format skos:altLabel ?alias .
  FILTER(LANG(?alias) = "en")
}}
ORDER BY ?format ?alias
""".strip()
    ),
    "classification": (
        _PREFIXES
        + f"""
SELECT DISTINCT ?format ?predicate ?value ?valueLabel WHERE {{
  {_POPULATION}
  VALUES ?predicate {{ wdt:P31 wdt:P279 }}
  ?format ?predicate ?value .
  OPTIONAL {{
    ?value rdfs:label ?valueLabel .
    FILTER(LANG(?valueLabel) = "en")
  }}
}}
ORDER BY ?format ?predicate ?value
""".strip()
    ),
    "identifiers": (
        _PREFIXES
        + f"""
SELECT DISTINCT ?format ?predicate ?value WHERE {{
  {_POPULATION}
  VALUES ?predicate {{ wdt:P2748 wdt:P3266 wdt:P11167 }}
  ?format ?predicate ?value .
}}
ORDER BY ?format ?predicate ?value
""".strip()
    ),
    "technical_literals": (
        _PREFIXES
        + f"""
SELECT DISTINCT ?format ?predicate ?value WHERE {{
  {_POPULATION}
  VALUES ?predicate {{
    wdt:P1195
    wdt:P1163
    wdt:P348
    wdt:P4152
    wdt:P577
    wdt:P571
    wdt:P856
  }}
  ?format ?predicate ?value .
}}
ORDER BY ?format ?predicate ?value
""".strip()
    ),
    "item_relations": (
        _PREFIXES
        + f"""
SELECT DISTINCT ?format ?predicate ?value ?valueLabel WHERE {{
  {_POPULATION}
  VALUES ?predicate {{
    wdt:P178
    wdt:P361
    wdt:P144
    wdt:P1365
    wdt:P1366
    wdt:P1343
  }}
  ?format ?predicate ?value .
  OPTIONAL {{
    ?value rdfs:label ?valueLabel .
    FILTER(LANG(?valueLabel) = "en")
  }}
}}
ORDER BY ?format ?predicate ?value
""".strip()
    ),
}

DEFAULT_FILE_FORMAT_QUERY = DEFAULT_QUERY_PARTS["core"]

_PROPERTY_TO_FIELD = {
    "http://www.wikidata.org/prop/direct/P31": ("instanceOfQid", "instanceOfLabel"),
    "http://www.wikidata.org/prop/direct/P279": ("subclassOfQid", "subclassOfLabel"),
    "http://www.wikidata.org/prop/direct/P2748": ("puid", None),
    "http://www.wikidata.org/prop/direct/P3266": ("locFdd", None),
    "http://www.wikidata.org/prop/direct/P11167": ("naraFormatPlanId", None),
    "http://www.wikidata.org/prop/direct/P1195": ("extension", None),
    "http://www.wikidata.org/prop/direct/P1163": ("mimeType", None),
    "http://www.wikidata.org/prop/direct/P348": ("version", None),
    "http://www.wikidata.org/prop/direct/P4152": ("identificationPattern", None),
    "http://www.wikidata.org/prop/direct/P577": ("publicationDate", None),
    "http://www.wikidata.org/prop/direct/P571": ("inceptionDate", None),
    "http://www.wikidata.org/prop/direct/P856": ("officialWebsite", None),
    "http://www.wikidata.org/prop/direct/P178": ("developerQid", "developerLabel"),
    "http://www.wikidata.org/prop/direct/P361": ("partOfQid", "partOfLabel"),
    "http://www.wikidata.org/prop/direct/P144": ("basedOnQid", "basedOnLabel"),
    "http://www.wikidata.org/prop/direct/P1365": ("replacesQid", "replacesLabel"),
    "http://www.wikidata.org/prop/direct/P1366": ("replacedByQid", "replacedByLabel"),
    "http://www.wikidata.org/prop/direct/P1343": ("describedByQid", "describedByLabel"),
}

_OUTPUT_COLUMNS = [
    "format",
    "qid",
    "formatLabel",
    "formatDescription",
    "aliases",
    "instanceOfQid",
    "instanceOfLabel",
    "subclassOfQid",
    "subclassOfLabel",
    "puid",
    "locFdd",
    "naraFormatPlanId",
    "extension",
    "mimeType",
    "version",
    "identificationPattern",
    "developerQid",
    "developerLabel",
    "publicationDate",
    "inceptionDate",
    "partOfQid",
    "partOfLabel",
    "basedOnQid",
    "basedOnLabel",
    "replacesQid",
    "replacesLabel",
    "replacedByQid",
    "replacedByLabel",
    "describedByQid",
    "describedByLabel",
    "officialWebsite",
]


class WikidataSparqlAdapter(SourceAdapter):
    """Download Wikidata file-format metadata without ingesting it.

    The default acquisition uses several statement-oriented SPARQL queries and
    merges them locally. The final CSV is one row per Wikidata item, with
    multi-valued properties pipe-delimited. ``extract`` deliberately returns no
    RawFormatRecord objects, so Wikidata cannot alter canonical identities,
    criterion claims, risk scores, or MongoDB at this stage.
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
        mode = "custom" if self.custom_query else "partitioned-default-v2"
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
                    body = exc.read().decode("utf-8", errors="replace").strip()
                except Exception:
                    body = ""
                retryable = exc.code in {429, 500, 502, 503, 504}
                if not retryable or attempt >= retries:
                    detail = f": {body[:500]}" if body else ""
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
    def _new_merged_row(format_uri: str, qid: str = "") -> dict[str, Any]:
        row: dict[str, Any] = {
            "format": format_uri,
            "qid": qid or WikidataSparqlAdapter._qid_from_uri(format_uri),
            "formatLabel": "",
            "formatDescription": "",
        }
        for column in _OUTPUT_COLUMNS:
            if column not in row:
                row[column] = set()
        row["_paired_labels"] = {}
        return row

    @staticmethod
    def _ensure_merged_row(
        rows: dict[str, dict[str, Any]],
        format_uri: str,
        *,
        qid: str = "",
    ) -> dict[str, Any] | None:
        if not format_uri:
            return None
        if format_uri not in rows:
            rows[format_uri] = WikidataSparqlAdapter._new_merged_row(format_uri, qid)
        elif qid:
            rows[format_uri]["qid"] = qid
        return rows[format_uri]

    @staticmethod
    def _add_value(target: dict[str, Any], field: str, value: str) -> None:
        if not value:
            return
        slot = target.get(field)
        if isinstance(slot, set):
            slot.add(value)

    def _fetch_partitioned_default(self) -> tuple[bytes, dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        part_stats: dict[str, Any] = {}

        specs = {
            "core": {"format", "qid", "formatLabel", "formatDescription"},
            "aliases": {"format", "alias"},
            "classification": {"format", "predicate", "value", "valueLabel"},
            "identifiers": {"format", "predicate", "value"},
            "technical_literals": {"format", "predicate", "value"},
            "item_relations": {"format", "predicate", "value", "valueLabel"},
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
                if name == "core":
                    target = self._ensure_merged_row(
                        merged,
                        format_uri,
                        qid=source_row.get("qid", ""),
                    )
                    if target is None:
                        continue
                    if source_row.get("formatLabel"):
                        target["formatLabel"] = source_row["formatLabel"]
                    if source_row.get("formatDescription"):
                        target["formatDescription"] = source_row["formatDescription"]
                    continue

                # Non-core query results are only accepted for items established
                # by the core population query.
                target = merged.get(format_uri)
                if target is None:
                    continue

                if name == "aliases":
                    self._add_value(target, "aliases", source_row.get("alias", ""))
                    continue

                predicate = source_row.get("predicate", "")
                mapping = _PROPERTY_TO_FIELD.get(predicate)
                if mapping is None:
                    continue
                value_field, label_field = mapping
                value = source_row.get("value", "")
                if value_field.endswith("Qid"):
                    value = self._qid_from_uri(value)
                if label_field:
                    if value:
                        pairs = target["_paired_labels"].setdefault(value_field, {})
                        pairs[value] = pairs.get(value, "") or source_row.get(
                            "valueLabel", ""
                        )
                else:
                    self._add_value(target, value_field, value)

        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=_OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for target in sorted(
            merged.values(),
            key=lambda row: (str(row["qid"]), str(row["format"])),
        ):
            rendered: dict[str, str] = {}
            paired_labels = target.get("_paired_labels", {})
            paired_label_fields = {
                label_field
                for value_field, label_field in _PROPERTY_TO_FIELD.values()
                if label_field
            }
            for column in _OUTPUT_COLUMNS:
                if column in paired_labels:
                    pairs = sorted(paired_labels[column].items())
                    rendered[column] = "|".join(value for value, _ in pairs)
                    label_field = _PROPERTY_TO_FIELD[
                        next(
                            predicate
                            for predicate, fields in _PROPERTY_TO_FIELD.items()
                            if fields[0] == column
                        )
                    ][1]
                    if label_field:
                        rendered[label_field] = "|".join(label for _, label in pairs)
                    continue
                if column in paired_label_fields and column in rendered:
                    continue
                value = target[column]
                if isinstance(value, set):
                    rendered[column] = "|".join(sorted(value))
                else:
                    rendered[column] = str(value or "")
            writer.writerow(rendered)

        csv_bytes = output.getvalue().encode("utf-8")
        self._validate_csv(
            csv_bytes,
            required_columns={"format", "qid"},
        )
        return csv_bytes, part_stats

    def acquire(self) -> list[SourceSnapshot]:
        query_sha256 = self._query_sha256()
        cache_key = self._cache_key()
        query_mode = "custom_single_query" if self.custom_query else "partitioned_default_v2"
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
                required_columns={"format", "qid"},
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
        return []
