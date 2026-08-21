from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Any

from registry_builder.adapters.base import SourceAdapter
from registry_builder.models import Identifier, RawFormatRecord, SourceSnapshot

DEFAULT_LOC_FDD_MAPPING_DATE = "20260713"
DEFAULT_LOC_FDD_MAPPING_URL = (
    "https://www.loc.gov/preservation/digital/formats/mappings/"
    f"fdd-puid-qid-{DEFAULT_LOC_FDD_MAPPING_DATE}.csv"
)

_FDD_RE = re.compile(r"\bfdd\d{6}\b", re.I)
_PUID_RE = re.compile(r"\b(?:fmt|x-fmt)/\d+\b", re.I)
_QID_RE = re.compile(r"\bQ\d{2,}\b", re.I)
_CONTEXT_HEADER_RE = re.compile(r"(?:match|status|note|comment|granular|hierarch|exact)", re.I)
_TITLE_HEADER_RE = re.compile(r"(?:title|name|format)", re.I)


def _norm_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _ids(pattern: re.Pattern[str], text: str, *, upper: bool = False, lower: bool = False) -> list[str]:
    values = {match.group(0) for match in pattern.finditer(text or "")}
    if upper:
        return sorted(value.upper() for value in values)
    if lower:
        return sorted(value.lower() for value in values)
    return sorted(values)


def _first_value_for_headers(row: dict[str, Any], headers: tuple[str, ...]) -> str | None:
    """Return the first non-empty value using the caller's header priority order."""
    normalized_row = {_norm_header(key): value for key, value in row.items()}
    for header in headers:
        value = normalized_row.get(_norm_header(header))
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _identifier_column_text(row: dict[str, Any], kind: str) -> str:
    """Return text only from columns that own the requested identifier.

    The July 2026 LOC crosswalk uses `LC_Unique_ID`, `PRONOM_PUID`, and
    `Wikidata_Title_ID`. These explicit schema names are recognized first, with
    conservative fallbacks for future header variants. Free-text note columns
    are deliberately excluded so identifiers mentioned in explanatory prose do
    not become crosswalk assertions.
    """
    values: list[str] = []
    for key, value in row.items():
        if value is None or not str(value).strip():
            continue
        header = _norm_header(key)
        include = False
        if kind == "fdd":
            include = header in {
                "lcuniqueid",
                "lcuniqueidentifier",
                "fdd",
                "fddid",
                "fddidentifier",
            } or (
                "fdd" in header
                and not any(token in header for token in ("title", "name", "match", "status", "note", "comment"))
            )
        elif kind == "puid":
            include = header in {
                "pronompuid",
                "puid",
                "pronom",
                "pronomid",
                "pronomidentifier",
            } or (
                ("puid" in header or "pronom" in header)
                and not any(token in header for token in ("match", "status", "note", "comment"))
            )
        elif kind == "qid":
            include = header in {
                "wikidatatitleid",
                "wikidataqid",
                "qid",
                "wikidataid",
                "wikidataidentifier",
            } or (
                ("qid" in header or "wikidata" in header)
                and not any(token in header for token in ("match", "status", "note", "comment"))
            )
        if include:
            values.append(str(value))
    return " | ".join(values)


def _row_title(row: dict[str, Any]) -> str | None:
    # Prefer the actual LOC crosswalk schema. `Filename` must never win merely
    # because it contains the substring "name". Long name is the preferred
    # human-readable label; short name is retained only as a fallback.
    preferred = _first_value_for_headers(
        row,
        (
            "LC_Long_Name",
            "LC_Short_Name",
            "Long_Name",
            "Short_Name",
            "Format_Title",
            "Format_Name",
            "Title",
        ),
    )
    if preferred:
        return preferred

    for key, value in row.items():
        if not value:
            continue
        normalized = _norm_header(key)
        if normalized in {
            "filename",
            "file",
            "path",
            "filepath",
            "lcuniqueid",
            "lcuniqueidentifier",
            "fdd",
            "fddid",
            "fddidentifier",
            "puid",
            "pronompuid",
            "qid",
            "wikidataqid",
            "wikidatatitleid",
        }:
            continue
        if _TITLE_HEADER_RE.search(str(key)):
            text = str(value).strip()
            if text and not _FDD_RE.fullmatch(text) and not _PUID_RE.fullmatch(text) and not _QID_RE.fullmatch(text):
                return text
    return None


def _mapping_context(row: dict[str, Any]) -> dict[str, str]:
    return {
        str(key): str(value).strip()
        for key, value in row.items()
        if value is not None and str(value).strip() and _CONTEXT_HEADER_RE.search(str(key))
    }


def _entry_from_row(snapshot: SourceSnapshot, row: dict[str, Any], row_number: int, mapping_date: str) -> dict[str, Any]:
    fdd_ids = _ids(_FDD_RE, _identifier_column_text(row, "fdd"), lower=True)
    puids = _ids(_PUID_RE, _identifier_column_text(row, "puid"), lower=True)
    qids = _ids(_QID_RE, _identifier_column_text(row, "qid"), upper=True)
    primary_fdd = fdd_ids[0] if fdd_ids else None
    source_record_id = f"{primary_fdd or 'row'}:{row_number}"
    return {
        "source_record_id": source_record_id,
        "row_number": row_number,
        "mapping_date": mapping_date,
        "title": _row_title(row),
        "fdd_ids": fdd_ids,
        "puids": puids,
        "wikidata_qids": qids,
        "mapping_context": _mapping_context(row),
        "source_url": snapshot.uri,
        "snapshot_sha256": snapshot.sha256,
        "raw_row": {str(key): value for key, value in row.items()},
    }


def _entry_to_record(entry: dict[str, Any], *, source_id: str, source_type: str) -> RawFormatRecord:
    source_record_id = str(entry["source_record_id"])
    identifiers: list[Identifier] = []
    for value in entry.get("fdd_ids") or []:
        identifiers.append(Identifier("loc", value, source_type, True, source_record_id))
    for value in entry.get("puids") or []:
        identifiers.append(Identifier("puid", value, source_type, False, source_record_id))
    for value in entry.get("wikidata_qids") or []:
        identifiers.append(Identifier("wikidata", value, source_type, False, source_record_id))

    return RawFormatRecord(
        source_id=source_id,
        source_type=source_type,
        source_record_id=source_record_id,
        record_role="evidence_only",
        name=entry.get("title"),
        loc_ids=list(entry.get("fdd_ids") or []),
        puids=list(entry.get("puids") or []),
        wikidata_ids=list(entry.get("wikidata_qids") or []),
        identifiers=identifiers,
        urls={"loc_fdd_mapping": entry["source_url"]} if entry.get("source_url") else {},
        evidence=[{
            "type": "loc_fdd_puid_qid_crosswalk",
            "mapping_date": entry.get("mapping_date"),
            "row_number": entry.get("row_number"),
            "snapshot_sha256": entry.get("snapshot_sha256"),
            "identity_projection": False,
        }],
        native_fields={
            "mapping_date": entry.get("mapping_date"),
            "fdd_ids": list(entry.get("fdd_ids") or []),
            "puids": list(entry.get("puids") or []),
            "wikidata_qids": list(entry.get("wikidata_qids") or []),
            "mapping_context": dict(entry.get("mapping_context") or {}),
        },
        raw={
            "snapshot_sha256": entry.get("snapshot_sha256"),
            "row_number": entry.get("row_number"),
            "raw_row": dict(entry.get("raw_row") or {}),
        },
    )


class LocFddMappingCsvAdapter(SourceAdapter):
    """Acquire LOC's monthly FDD↔PRONOM↔Wikidata crosswalk as evidence only.

    LOC documents that some mappings are not exact because FDDs, PRONOM, and
    Wikidata may describe different levels of hierarchy/granularity. Therefore
    this adapter does not create canonical identities or automatically bridge
    LOC FDD records to PUID/QID records. It preserves the official crosswalk and
    any match/status context for a later reviewed mapping layer.
    """

    type_name = "loc_fdd_mapping_csv"

    def _mapping_date(self) -> str:
        return str(self.config.get("mapping_date") or DEFAULT_LOC_FDD_MAPPING_DATE)

    def _mapping_url(self) -> str:
        configured = self.config.get("mapping_url") or self.config.get("uri")
        if configured:
            return str(configured)
        return (
            "https://www.loc.gov/preservation/digital/formats/mappings/"
            f"fdd-puid-qid-{self._mapping_date()}.csv"
        )

    def acquire(self) -> list[SourceSnapshot]:
        local_file = self.config.get("local_file")
        metadata = {
            "source_location": "loc_fdd_mapping_csv" if not local_file else "local_file",
            "mapping_date": self._mapping_date(),
            "snapshot_policy": "cache",
            "snapshot_retained": True,
            "identity_projection": False,
            "mapping_page": "https://www.loc.gov/preservation/digital/formats/fdd/fdd_puid_qid.shtml",
        }
        if local_file:
            return [
                self.acquire_file_snapshot(
                    str(local_file),
                    suffix=".csv",
                    note="retrieval_mode=local_file; identity_projection=false",
                    metadata=metadata,
                )
            ]
        return [
            self.acquire_uri_snapshot(
                self._mapping_url(),
                suffix=".csv",
                note="retrieval_mode=loc_monthly_crosswalk; identity_projection=false",
                metadata=metadata,
            )
        ]

    def extract_entries(self, snapshots: list[SourceSnapshot]) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        mapping_date = self._mapping_date()
        for snapshot in snapshots:
            text = Path(snapshot.local_path).read_text(encoding="utf-8-sig", errors="replace")
            reader = csv.DictReader(io.StringIO(text))
            if not reader.fieldnames:
                raise ValueError("LOC FDD mapping CSV has no header row")
            for row_number, row in enumerate(reader, start=2):
                if not any(str(value or "").strip() for value in row.values()):
                    continue
                entries.append(_entry_from_row(snapshot, row, row_number, mapping_date))
        return entries

    def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
        return [
            _entry_to_record(entry, source_id=self.source_id, source_type=self.type_name)
            for entry in self.extract_entries(snapshots)
        ]
