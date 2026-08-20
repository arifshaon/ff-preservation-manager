from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from registry_builder.adapters.base import SourceAdapter
from registry_builder.models import RawFormatRecord, SourceSnapshot, utc_now_iso


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

# Population membership is deliberately explicit. The earlier unrestricted
# P31/P279* traversal reached large Wikimedia-module/template branches and made
# the acquisition population depend on remote ontology changes. Discovery now
# unions direct core classes, reviewed specialist classes, bounded evidence-
# gated XML/parent/context routes, and authority-linked QIDs. P279 is still
# harvested later as source context; it does not decide population membership
# transitively.
WIKIDATA_POPULATION_POLICY_VERSION = "2026-08-20-v3"

# Direct P31 classes whose instances are genuinely file-format concepts but are
# not consistently modelled as direct instances of Q235557. Labels are comments
# only: QIDs are policy.
REVIEWED_FORMAT_CLASS_QIDS: tuple[str, ...] = (
    "Q1572121",    # image file format
    "Q1351368",    # archive file format
    "Q336705",     # document file format
    "Q138827382",  # disk image format
    "Q654383",     # raw image format
    "Q105599390",  # raster-graphics file format
    "Q55281818",   # font file format
    "Q1955133",    # music file format
    "Q167772",     # digital container format
    "Q115729440",  # patch format
    "Q682626",     # audio file format
    "Q18359031",   # video file format
    "Q105599400",  # vector graphics file format
    "Q2026749",    # package format
    "Q17560478",   # executable file format
    "Q5090461",    # chemical file format
    "Q133897645",  # GIS project file
    "Q81986407",   # e-book file format
    "Q17560541",   # exe extension associated executable fileformat
)
_REVIEWED_FORMAT_CLASS_VALUES = " ".join(
    f"wd:{qid}" for qid in REVIEWED_FORMAT_CLASS_QIDS
)

# XML-based format is intentionally not an unconditional allowlist class. It is
# broad enough to need direct format evidence.
CONDITIONAL_XML_FORMAT_CLASS_QID = "Q20155966"

# Some preservation-relevant version/variant records are modelled as direct
# instances of a particular parent format, family, or software-associated parent
# rather than a reusable file-format class. These parents are therefore a
# separate evidence-gated discovery route and are NOT promoted to format classes.
REVIEWED_FORMAT_PARENT_QIDS: tuple[str, ...] = (
    "Q2597575",   # Renoise Song
    "Q497118",    # Parchive
    "Q28858032",  # Microsoft Word Binary File Format
    "Q3502441",   # Excel Binary File Format
    "Q594447",    # Small Web Format family
    "Q125650",    # PDF/VT
    "Q34739013",  # Softdisk Family Tree
    "Q34746188",  # STATISTICA
    "Q53756508",  # git packfile index
    "Q28009469",  # Python bytecode
    "Q45989477",  # WebP Extended
)
_REVIEWED_FORMAT_PARENT_VALUES = " ".join(
    f"wd:{qid}" for qid in REVIEWED_FORMAT_PARENT_QIDS
)

# Context classes can describe preservation-relevant encodings/codecs that are
# useful to acquire but must not later be treated automatically as canonical
# file formats.
CONDITIONAL_CONTEXT_CLASS_QIDS: tuple[str, ...] = (
    "Q7927899",  # video compression format
)
_CONDITIONAL_CONTEXT_CLASS_VALUES = " ".join(
    f"wd:{qid}" for qid in CONDITIONAL_CONTEXT_CLASS_QIDS
)

# The broad "open file format" class contains a mix of useful formats and
# protocol/standard concepts. Acquire only evidence-bearing records and exclude
# known ambiguous co-classifications.
CONDITIONAL_OPEN_FORMAT_CLASS_QID = "Q1056408"
CONDITIONAL_OPEN_FORMAT_EXCLUDED_CLASS_QIDS: tuple[str, ...] = (
    "Q16937237",  # domain application protocol
    "Q385853",    # de facto standard
)
_CONDITIONAL_OPEN_FORMAT_EXCLUDED_VALUES = " ".join(
    f"wd:{qid}" for qid in CONDITIONAL_OPEN_FORMAT_EXCLUDED_CLASS_QIDS
)

_EVIDENCE_PROPERTY_VALUES = """
    wdt:P2748
    wdt:P3266
    wdt:P11167
    wdt:P1195
    wdt:P1163
    wdt:P4152
""".strip()

# Population discovery is deliberately separated from property harvesting.
# Each population query is keyset-paginated by entity URI, then the merged QID
# set is frozen for the acquisition session. Property queries use VALUES batches
# over that frozen set rather than repeating population-selection logic.
POPULATION_QUERY_TEMPLATES: dict[str, str] = {
    "direct_file_formats": (
        _PREFIXES
        + """
SELECT DISTINCT ?format WHERE {
  ?format wdt:P31 wd:Q235557 .
  __AFTER_FILTER__
}
ORDER BY ?format
LIMIT __LIMIT__
""".strip()
    ),
    "file_format_families": (
        _PREFIXES
        + """
SELECT DISTINCT ?format WHERE {
  ?format wdt:P31 wd:Q26085352 .
  __AFTER_FILTER__
}
ORDER BY ?format
LIMIT __LIMIT__
""".strip()
    ),
    "reviewed_format_classes": (
        _PREFIXES
        + f"""
SELECT DISTINCT ?format WHERE {{
  VALUES ?class {{ {_REVIEWED_FORMAT_CLASS_VALUES} }}
  ?format wdt:P31 ?class .
  __AFTER_FILTER__
}}
ORDER BY ?format
LIMIT __LIMIT__
""".strip()
    ),
    "conditional_xml_formats": (
        _PREFIXES
        + f"""
SELECT DISTINCT ?format WHERE {{
  ?format wdt:P31 wd:{CONDITIONAL_XML_FORMAT_CLASS_QID} .
  VALUES ?evidenceProperty {{
    {_EVIDENCE_PROPERTY_VALUES}
  }}
  ?format ?evidenceProperty ?evidence .
  __AFTER_FILTER__
}}
ORDER BY ?format
LIMIT __LIMIT__
""".strip()
    ),
    "conditional_format_parents": (
        _PREFIXES
        + f"""
SELECT DISTINCT ?format WHERE {{
  VALUES ?parent {{ {_REVIEWED_FORMAT_PARENT_VALUES} }}
  ?format wdt:P31 ?parent .
  VALUES ?evidenceProperty {{
    {_EVIDENCE_PROPERTY_VALUES}
  }}
  ?format ?evidenceProperty ?evidence .
  __AFTER_FILTER__
}}
ORDER BY ?format
LIMIT __LIMIT__
""".strip()
    ),
    "conditional_context_classes": (
        _PREFIXES
        + f"""
SELECT DISTINCT ?format WHERE {{
  VALUES ?class {{ {_CONDITIONAL_CONTEXT_CLASS_VALUES} }}
  ?format wdt:P31 ?class .
  VALUES ?evidenceProperty {{
    {_EVIDENCE_PROPERTY_VALUES}
  }}
  ?format ?evidenceProperty ?evidence .
  __AFTER_FILTER__
}}
ORDER BY ?format
LIMIT __LIMIT__
""".strip()
    ),
    "conditional_open_formats": (
        _PREFIXES
        + f"""
SELECT DISTINCT ?format WHERE {{
  ?format wdt:P31 wd:{CONDITIONAL_OPEN_FORMAT_CLASS_QID} .
  VALUES ?evidenceProperty {{
    {_EVIDENCE_PROPERTY_VALUES}
  }}
  ?format ?evidenceProperty ?evidence .
  FILTER NOT EXISTS {{
    VALUES ?excludedClass {{ {_CONDITIONAL_OPEN_FORMAT_EXCLUDED_VALUES} }}
    ?format wdt:P31 ?excludedClass .
  }}
  __AFTER_FILTER__
}}
ORDER BY ?format
LIMIT __LIMIT__
""".strip()
    ),
    "pronom_linked": (
        _PREFIXES
        + """
SELECT DISTINCT ?format WHERE {
  ?format wdt:P2748 ?puid .
  __AFTER_FILTER__
}
ORDER BY ?format
LIMIT __LIMIT__
""".strip()
    ),
    "loc_linked": (
        _PREFIXES
        + """
SELECT DISTINCT ?format WHERE {
  ?format wdt:P3266 ?locFdd .
  __AFTER_FILTER__
}
ORDER BY ?format
LIMIT __LIMIT__
""".strip()
    ),
    "nara_linked": (
        _PREFIXES
        + """
SELECT DISTINCT ?format WHERE {
  ?format wdt:P11167 ?naraFormatPlanId .
  __AFTER_FILTER__
}
ORDER BY ?format
LIMIT __LIMIT__
""".strip()
    ),
}

DEFAULT_QUERY_PARTS: dict[str, str] = {
    "core": (
        _PREFIXES
        + """
SELECT DISTINCT ?format ?qid ?formatLabel ?formatDescription WHERE {
  VALUES ?format { __VALUES__ }
  BIND(REPLACE(STR(?format), "^.*/", "") AS ?qid)
  OPTIONAL {
    ?format rdfs:label ?formatLabel .
    FILTER(LANG(?formatLabel) = "en")
  }
  OPTIONAL {
    ?format schema:description ?formatDescription .
    FILTER(LANG(?formatDescription) = "en")
  }
}
ORDER BY ?qid
""".strip()
    ),
    "aliases": (
        _PREFIXES
        + """
SELECT DISTINCT ?format ?alias WHERE {
  VALUES ?format { __VALUES__ }
  ?format skos:altLabel ?alias .
  FILTER(LANG(?alias) = "en")
}
ORDER BY ?format ?alias
""".strip()
    ),
    "classification": (
        _PREFIXES
        + """
SELECT DISTINCT ?format ?predicate ?value ?valueLabel WHERE {
  VALUES ?format { __VALUES__ }
  VALUES ?predicate { wdt:P31 wdt:P279 }
  ?format ?predicate ?value .
  OPTIONAL {
    ?value rdfs:label ?valueLabel .
    FILTER(LANG(?valueLabel) = "en")
  }
}
ORDER BY ?format ?predicate ?value
""".strip()
    ),
    "identifiers": (
        _PREFIXES
        + """
SELECT DISTINCT ?format ?predicate ?value WHERE {
  VALUES ?format { __VALUES__ }
  VALUES ?predicate { wdt:P2748 wdt:P3266 wdt:P11167 }
  ?format ?predicate ?value .
}
ORDER BY ?format ?predicate ?value
""".strip()
    ),
    "technical_literals": (
        _PREFIXES
        + """
SELECT DISTINCT ?format ?predicate ?value WHERE {
  VALUES ?format { __VALUES__ }
  VALUES ?predicate {
    wdt:P1195
    wdt:P1163
    wdt:P348
    wdt:P4152
    wdt:P577
    wdt:P571
    wdt:P856
  }
  ?format ?predicate ?value .
}
ORDER BY ?format ?predicate ?value
""".strip()
    ),
    "item_relations": (
        _PREFIXES
        + """
SELECT DISTINCT ?format ?predicate ?value ?valueLabel WHERE {
  VALUES ?format { __VALUES__ }
  VALUES ?predicate {
    wdt:P178
    wdt:P361
    wdt:P144
    wdt:P1365
    wdt:P1366
    wdt:P1343
  }
  ?format ?predicate ?value .
  OPTIONAL {
    ?value rdfs:label ?valueLabel .
    FILTER(LANG(?valueLabel) = "en")
  }
}
ORDER BY ?format ?predicate ?value
""".strip()
    ),
}

DEFAULT_FILE_FORMAT_QUERY = POPULATION_QUERY_TEMPLATES["direct_file_formats"]

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

_QID_RE = re.compile(r"^Q\d+$")


class WikidataSparqlAdapter(SourceAdapter):
    """Download Wikidata file-format metadata without ingesting it.

    Default acquisition is staged:
      1. discover and freeze the file-format QID population;
      2. harvest properties in bounded VALUES batches;
      3. cache each completed batch so an interrupted acquisition can resume;
      4. merge locally into one review CSV.

    ``extract`` deliberately returns no RawFormatRecord objects, so Wikidata
    cannot alter canonical identities, criterion claims, risk scores, or MongoDB
    at this stage.
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

    @property
    def batch_size(self) -> int:
        return max(1, min(int(self.config.get("batch_size", 200)), 1000))

    @property
    def population_page_size(self) -> int:
        return max(1, min(int(self.config.get("population_page_size", 500)), 5000))

    @property
    def restart(self) -> bool:
        return bool(self.config.get("restart", False))

    def _query_material(self) -> str:
        if self.custom_query:
            return self.custom_query
        pieces = [
            f"### population:{name}\n{query}"
            for name, query in POPULATION_QUERY_TEMPLATES.items()
        ]
        pieces.extend(
            f"### batch:{name}\n{query}" for name, query in DEFAULT_QUERY_PARTS.items()
        )
        pieces.append("### population-policy\n" + WIKIDATA_POPULATION_POLICY_VERSION)
        pieces.append("### reviewed-format-classes\n" + "\n".join(REVIEWED_FORMAT_CLASS_QIDS))
        pieces.append("### conditional-xml-format-class\n" + CONDITIONAL_XML_FORMAT_CLASS_QID)
        pieces.append("### reviewed-format-parents\n" + "\n".join(REVIEWED_FORMAT_PARENT_QIDS))
        pieces.append("### conditional-context-classes\n" + "\n".join(CONDITIONAL_CONTEXT_CLASS_QIDS))
        pieces.append("### conditional-open-format-class\n" + CONDITIONAL_OPEN_FORMAT_CLASS_QID)
        pieces.append(
            "### conditional-open-format-exclusions\n"
            + "\n".join(CONDITIONAL_OPEN_FORMAT_EXCLUDED_CLASS_QIDS)
        )
        pieces.append("### output-columns\n" + "\n".join(_OUTPUT_COLUMNS))
        return "\n\n".join(pieces)

    def _query_sha256(self) -> str:
        return hashlib.sha256(self._query_material().encode("utf-8")).hexdigest()

    def _cache_key(self) -> str:
        mode = "custom" if self.custom_query else "staged-values-batching-v3"
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
    def _format_uri(qid: str) -> str:
        return f"http://www.wikidata.org/entity/{qid}"

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
    def _add_value(target: dict[str, Any], field: str, value: str) -> None:
        if not value:
            return
        slot = target.get(field)
        if isinstance(slot, set):
            slot.add(value)

    @staticmethod
    def _render_population_query(
        template: str,
        *,
        after_uri: str | None,
        limit: int,
    ) -> str:
        after_filter = ""
        if after_uri:
            after_filter = f"FILTER(STR(?format) > {json.dumps(after_uri)})"
        return (
            template.replace("__AFTER_FILTER__", after_filter)
            .replace("__LIMIT__", str(limit))
        )

    @staticmethod
    def _render_batch_query(template: str, qids: list[str]) -> str:
        if not qids:
            raise ValueError("Cannot render a Wikidata batch query without QIDs")
        invalid = [qid for qid in qids if not _QID_RE.fullmatch(qid)]
        if invalid:
            raise ValueError(f"Invalid Wikidata QID(s) in batch: {invalid[:5]}")
        values = " ".join(f"wd:{qid}" for qid in qids)
        return template.replace("__VALUES__", values)

    def _session_manifest_path(self) -> Path:
        return self.snapshot_dir() / ".wikidata_acquisition_session.json"

    def _load_session_manifest(self) -> dict[str, Any] | None:
        path = self._session_manifest_path()
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return data if isinstance(data, dict) else None

    def _write_session_manifest(self, manifest: dict[str, Any]) -> None:
        path = self._session_manifest_path()
        path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _load_resume_population(
        self,
        manifest: dict[str, Any] | None,
    ) -> tuple[list[str], dict[str, Any]] | None:
        if self.restart or not manifest or manifest.get("complete") is not False:
            return None
        if manifest.get("query_sha256") != self._query_sha256():
            return None
        if int(manifest.get("batch_size", 0)) != self.batch_size:
            return None
        if int(manifest.get("population_page_size", 0)) != self.population_page_size:
            return None
        population_path = Path(str(manifest.get("population_path") or ""))
        if not population_path.exists():
            return None
        data = population_path.read_bytes()
        if hashlib.sha256(data).hexdigest() != manifest.get("population_sha256"):
            return None
        rows = self._read_rows(data)
        qids = sorted(
            {
                row.get("qid", "")
                for row in rows
                if _QID_RE.fullmatch(row.get("qid", ""))
            },
            key=lambda value: int(value[1:]),
        )
        if not qids:
            return None
        return qids, manifest

    def _discover_population(self) -> tuple[list[str], dict[str, Any]]:
        qids: set[str] = set()
        discovery_stats: dict[str, Any] = {}

        for population_name, template in POPULATION_QUERY_TEMPLATES.items():
            after_uri: str | None = None
            pages = 0
            rows_seen = 0
            while True:
                query = self._render_population_query(
                    template,
                    after_uri=after_uri,
                    limit=self.population_page_size,
                )
                data, headers = self._request_csv(
                    query,
                    query_name=f"population:{population_name}:page:{pages + 1}",
                    required_columns={"format"},
                )
                rows = self._read_rows(data)
                pages += 1
                rows_seen += len(rows)
                page_uris = sorted(
                    {
                        row.get("format", "")
                        for row in rows
                        if row.get("format", "")
                    }
                )
                for uri in page_uris:
                    qid = self._qid_from_uri(uri)
                    if _QID_RE.fullmatch(qid):
                        qids.add(qid)

                if len(rows) < self.population_page_size or not page_uris:
                    discovery_stats[population_name] = {
                        "pages": pages,
                        "rows_seen": rows_seen,
                        "content_type": headers.get("content-type"),
                    }
                    break

                next_after = page_uris[-1]
                if next_after == after_uri:
                    raise RuntimeError(
                        f"Wikidata population pagination for '{population_name}' "
                        "did not advance"
                    )
                after_uri = next_after

        ordered_qids = sorted(qids, key=lambda value: int(value[1:]))
        if not ordered_qids:
            raise RuntimeError("Wikidata population discovery returned no file-format QIDs")

        output = io.StringIO(newline="")
        writer = csv.DictWriter(
            output,
            fieldnames=["format", "qid"],
            lineterminator="\n",
        )
        writer.writeheader()
        for qid in ordered_qids:
            writer.writerow({"format": self._format_uri(qid), "qid": qid})
        population_bytes = output.getvalue().encode("utf-8")
        population_sha256 = hashlib.sha256(population_bytes).hexdigest()

        session_id = uuid.uuid4().hex
        policy_metadata = {
            "population_policy_version": WIKIDATA_POPULATION_POLICY_VERSION,
            "reviewed_format_class_qids": list(REVIEWED_FORMAT_CLASS_QIDS),
            "conditional_xml_format_class_qid": CONDITIONAL_XML_FORMAT_CLASS_QID,
            "reviewed_format_parent_qids": list(REVIEWED_FORMAT_PARENT_QIDS),
            "conditional_context_class_qids": list(CONDITIONAL_CONTEXT_CLASS_QIDS),
            "conditional_open_format_class_qid": CONDITIONAL_OPEN_FORMAT_CLASS_QID,
            "conditional_open_format_excluded_class_qids": list(
                CONDITIONAL_OPEN_FORMAT_EXCLUDED_CLASS_QIDS
            ),
        }
        population_snapshot = self._store_snapshot_bytes(
            index_key=(
                f"{self.endpoint}#wikidata-population-session={session_id}"
                f"&sha256={population_sha256}"
            ),
            uri=self.endpoint,
            data=population_bytes,
            suffix=".population.csv",
            note="wikidata_sparql; population_snapshot=true",
            content_type="text/csv",
            metadata={
                "session_id": session_id,
                **policy_metadata,
                "population_sha256": population_sha256,
                "row_count": len(ordered_qids),
                "discovery": discovery_stats,
            },
        )
        manifest = {
            "version": 3,
            "session_id": session_id,
            "started_at": utc_now_iso(),
            "complete": False,
            "query_sha256": self._query_sha256(),
            **policy_metadata,
            "batch_size": self.batch_size,
            "population_page_size": self.population_page_size,
            "population_path": population_snapshot.local_path,
            "population_sha256": population_sha256,
            "population_count": len(ordered_qids),
            "population_discovery": discovery_stats,
        }
        self._write_session_manifest(manifest)
        return ordered_qids, manifest

    def _get_or_start_population(self) -> tuple[list[str], dict[str, Any], bool]:
        manifest = self._load_session_manifest()
        resumed = self._load_resume_population(manifest)
        if resumed is not None:
            qids, resumed_manifest = resumed
            return qids, resumed_manifest, True
        qids, new_manifest = self._discover_population()
        return qids, new_manifest, False

    @staticmethod
    def _batch_cache_key(
        *,
        endpoint: str,
        session_id: str,
        part_name: str,
        batch_index: int,
        qids: list[str],
        query: str,
    ) -> str:
        batch_material = "\n".join(qids)
        batch_sha = hashlib.sha256(batch_material.encode("utf-8")).hexdigest()
        query_sha = hashlib.sha256(query.encode("utf-8")).hexdigest()
        return (
            f"{endpoint}#wikidata-session={session_id}"
            f"&part={part_name}&batch={batch_index:05d}"
            f"&batch-sha256={batch_sha}&query-sha256={query_sha}"
        )

    def _fetch_batch_part(
        self,
        *,
        session_id: str,
        part_name: str,
        batch_index: int,
        qids: list[str],
        query: str,
        required_columns: set[str],
    ) -> tuple[bytes, dict[str, Any]]:
        cache_key = self._batch_cache_key(
            endpoint=self.endpoint,
            session_id=session_id,
            part_name=part_name,
            batch_index=batch_index,
            qids=qids,
            query=query,
        )
        cached = self._cached_snapshot(
            uri=cache_key,
            suffix=".csv",
            note=(
                f"wikidata_sparql; batch_cache=true; part={part_name}; "
                f"batch={batch_index}"
            ),
            content_type="text/csv",
            metadata={
                "session_id": session_id,
                "part_name": part_name,
                "batch_index": batch_index,
                "batch_size": len(qids),
            },
        )
        if cached is not None:
            data = Path(cached.local_path).read_bytes()
            self._validate_csv(data, required_columns=required_columns)
            return data, {
                "from_cache": True,
                "row_count": self._row_count(data),
                "snapshot_path": cached.local_path,
            }

        data, headers = self._request_csv(
            query,
            query_name=f"{part_name}:batch:{batch_index}",
            required_columns=required_columns,
        )
        snapshot = self._store_snapshot_bytes(
            index_key=cache_key,
            uri=self.endpoint,
            data=data,
            suffix=f".{part_name}.batch-{batch_index:05d}.csv",
            note=(
                f"wikidata_sparql; batch_cache=true; part={part_name}; "
                f"batch={batch_index}"
            ),
            content_type=headers.get("content-type") or "text/csv",
            metadata={
                "session_id": session_id,
                "part_name": part_name,
                "batch_index": batch_index,
                "batch_size": len(qids),
                "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
            },
        )
        return data, {
            "from_cache": False,
            "row_count": self._row_count(data),
            "snapshot_path": snapshot.local_path,
            "content_type": headers.get("content-type"),
        }

    @staticmethod
    def _merge_source_row(
        target: dict[str, Any],
        *,
        part_name: str,
        source_row: dict[str, str],
    ) -> None:
        if part_name == "core":
            if source_row.get("qid"):
                target["qid"] = source_row["qid"]
            if source_row.get("formatLabel"):
                target["formatLabel"] = source_row["formatLabel"]
            if source_row.get("formatDescription"):
                target["formatDescription"] = source_row["formatDescription"]
            return

        if part_name == "aliases":
            WikidataSparqlAdapter._add_value(
                target, "aliases", source_row.get("alias", "")
            )
            return

        predicate = source_row.get("predicate", "")
        mapping = _PROPERTY_TO_FIELD.get(predicate)
        if mapping is None:
            return
        value_field, label_field = mapping
        value = source_row.get("value", "")
        if value_field.endswith("Qid"):
            value = WikidataSparqlAdapter._qid_from_uri(value)
        if label_field:
            if value:
                pairs = target["_paired_labels"].setdefault(value_field, {})
                pairs[value] = pairs.get(value, "") or source_row.get(
                    "valueLabel", ""
                )
        else:
            WikidataSparqlAdapter._add_value(target, value_field, value)

    @staticmethod
    def _render_merged_csv(merged: dict[str, dict[str, Any]]) -> bytes:
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=_OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()

        paired_label_fields = {
            label_field
            for _, label_field in _PROPERTY_TO_FIELD.values()
            if label_field
        }
        value_to_label = {
            value_field: label_field
            for value_field, label_field in _PROPERTY_TO_FIELD.values()
            if label_field
        }

        for target in sorted(
            merged.values(),
            key=lambda row: int(str(row["qid"])[1:])
            if _QID_RE.fullmatch(str(row["qid"]))
            else 10**18,
        ):
            rendered: dict[str, str] = {}
            paired_labels = target.get("_paired_labels", {})
            for column in _OUTPUT_COLUMNS:
                if column in paired_labels:
                    pairs = sorted(paired_labels[column].items())
                    rendered[column] = "|".join(value for value, _ in pairs)
                    label_field = value_to_label.get(column)
                    if label_field:
                        rendered[label_field] = "|".join(
                            label for _, label in pairs
                        )
                    continue
                if column in paired_label_fields and column in rendered:
                    continue
                value = target[column]
                if isinstance(value, set):
                    rendered[column] = "|".join(sorted(value))
                else:
                    rendered[column] = str(value or "")
            writer.writerow(rendered)

        return output.getvalue().encode("utf-8")

    def _fetch_staged_default(self) -> tuple[bytes, dict[str, Any]]:
        qids, manifest, resumed = self._get_or_start_population()
        session_id = str(manifest["session_id"])

        merged: dict[str, dict[str, Any]] = {
            self._format_uri(qid): self._new_merged_row(self._format_uri(qid), qid)
            for qid in qids
        }

        specs = {
            "core": {"format", "qid", "formatLabel", "formatDescription"},
            "aliases": {"format", "alias"},
            "classification": {"format", "predicate", "value", "valueLabel"},
            "identifiers": {"format", "predicate", "value"},
            "technical_literals": {"format", "predicate", "value"},
            "item_relations": {"format", "predicate", "value", "valueLabel"},
        }
        part_stats: dict[str, Any] = {}
        total_batches = (len(qids) + self.batch_size - 1) // self.batch_size

        for part_name, template in DEFAULT_QUERY_PARTS.items():
            part_rows = 0
            cache_hits = 0
            network_fetches = 0
            completed_batches = 0

            for batch_index, start in enumerate(
                range(0, len(qids), self.batch_size),
                start=1,
            ):
                batch_qids = qids[start : start + self.batch_size]
                query = self._render_batch_query(template, batch_qids)
                data, batch_meta = self._fetch_batch_part(
                    session_id=session_id,
                    part_name=part_name,
                    batch_index=batch_index,
                    qids=batch_qids,
                    query=query,
                    required_columns=specs[part_name],
                )
                rows = self._read_rows(data)
                part_rows += len(rows)
                cache_hits += int(bool(batch_meta.get("from_cache")))
                network_fetches += int(not bool(batch_meta.get("from_cache")))
                completed_batches += 1

                for source_row in rows:
                    format_uri = source_row.get("format", "")
                    target = merged.get(format_uri)
                    if target is None:
                        continue
                    self._merge_source_row(
                        target,
                        part_name=part_name,
                        source_row=source_row,
                    )

            part_stats[part_name] = {
                "batches": completed_batches,
                "expected_batches": total_batches,
                "row_count": part_rows,
                "cache_hits": cache_hits,
                "network_fetches": network_fetches,
                "template_sha256": hashlib.sha256(
                    template.encode("utf-8")
                ).hexdigest(),
            }

        csv_bytes = self._render_merged_csv(merged)
        self._validate_csv(csv_bytes, required_columns={"format", "qid"})

        manifest["output_row_count"] = self._row_count(csv_bytes)
        manifest["query_parts"] = part_stats
        self._write_session_manifest(manifest)

        return csv_bytes, {
            "session_id": session_id,
            "resumed": resumed,
            "population_count": len(qids),
            "population_sha256": manifest.get("population_sha256"),
            "population_discovery": manifest.get("population_discovery"),
            "population_policy_version": manifest.get("population_policy_version"),
            "reviewed_format_class_qids": manifest.get("reviewed_format_class_qids"),
            "conditional_xml_format_class_qid": manifest.get(
                "conditional_xml_format_class_qid"
            ),
            "reviewed_format_parent_qids": manifest.get("reviewed_format_parent_qids"),
            "conditional_context_class_qids": manifest.get(
                "conditional_context_class_qids"
            ),
            "conditional_open_format_class_qid": manifest.get(
                "conditional_open_format_class_qid"
            ),
            "conditional_open_format_excluded_class_qids": manifest.get(
                "conditional_open_format_excluded_class_qids"
            ),
            "batch_size": self.batch_size,
            "population_page_size": self.population_page_size,
            "total_batches": total_batches,
            "parts": part_stats,
        }

    def acquire(self) -> list[SourceSnapshot]:
        query_sha256 = self._query_sha256()
        cache_key = self._cache_key()
        query_mode = (
            "custom_single_query"
            if self.custom_query
            else "staged_population_values_batches_v3"
        )
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
            metadata["population_policy_version"] = WIKIDATA_POPULATION_POLICY_VERSION
            metadata["reviewed_format_class_qids"] = list(REVIEWED_FORMAT_CLASS_QIDS)
            metadata["conditional_xml_format_class_qid"] = (
                CONDITIONAL_XML_FORMAT_CLASS_QID
            )
            metadata["reviewed_format_parent_qids"] = list(REVIEWED_FORMAT_PARENT_QIDS)
            metadata["conditional_context_class_qids"] = list(
                CONDITIONAL_CONTEXT_CLASS_QIDS
            )
            metadata["conditional_open_format_class_qid"] = (
                CONDITIONAL_OPEN_FORMAT_CLASS_QID
            )
            metadata["conditional_open_format_excluded_class_qids"] = list(
                CONDITIONAL_OPEN_FORMAT_EXCLUDED_CLASS_QIDS
            )
            metadata["population_queries"] = dict(POPULATION_QUERY_TEMPLATES)
            metadata["batch_query_templates"] = dict(DEFAULT_QUERY_PARTS)
            metadata["batch_size"] = self.batch_size
            metadata["population_page_size"] = self.population_page_size

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
                    "Offline mode requested but no cached final Wikidata snapshot "
                    f"exists for query set {query_sha256}"
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
            data, staged_stats = self._fetch_staged_default()
            metadata["staged_acquisition"] = staged_stats
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
        if not self.custom_query:
            manifest = self._load_session_manifest()
            staged = metadata.get("staged_acquisition") or {}
            if (
                manifest
                and manifest.get("complete") is False
                and manifest.get("session_id") == staged.get("session_id")
            ):
                manifest["complete"] = True
                manifest["completed_at"] = utc_now_iso()
                manifest["final_snapshot_path"] = snapshot.local_path
                manifest["final_snapshot_sha256"] = snapshot.sha256
                self._write_session_manifest(manifest)
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
