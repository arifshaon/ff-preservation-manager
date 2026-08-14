from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile
import re
import xml.etree.ElementTree as ET
from typing import Any

from registry_builder.adapters.base import SourceAdapter
from registry_builder.models import RawFormatRecord, SourceSnapshot, utc_now_iso
from registry_builder.utils import ensure_dir, read_uri, sha256_bytes, split_multi

_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _col_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    value = 0
    for ch in letters:
        value = value * 26 + (ord(ch.upper()) - ord("A") + 1)
    return value - 1


def _read_shared_strings(zf: ZipFile) -> list[str]:
    try:
        data = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(data)
    strings: list[str] = []
    for si in root.findall("a:si", _NS):
        parts = []
        for t in si.iterfind(".//a:t", _NS):
            parts.append(t.text or "")
        strings.append("".join(parts))
    return strings


def _sheet_paths(zf: ZipFile) -> list[str]:
    return sorted([p for p in zf.namelist() if p.startswith("xl/worksheets/sheet") and p.endswith(".xml")])


def _read_sheet_rows(xlsx_path: str) -> list[list[str]]:
    with ZipFile(xlsx_path) as zf:
        shared = _read_shared_strings(zf)
        sheet_path = _sheet_paths(zf)[0]
        root = ET.fromstring(zf.read(sheet_path))
        rows: list[list[str]] = []
        for row in root.findall(".//a:sheetData/a:row", _NS):
            values: dict[int, str] = {}
            for c in row.findall("a:c", _NS):
                ref = c.attrib.get("r", "A1")
                idx = _col_index(ref)
                typ = c.attrib.get("t")
                v = c.find("a:v", _NS)
                is_elem = c.find("a:is", _NS)
                text = ""
                if typ == "s" and v is not None and v.text is not None:
                    si = int(v.text)
                    text = shared[si] if 0 <= si < len(shared) else ""
                elif typ == "inlineStr" and is_elem is not None:
                    text = "".join(t.text or "" for t in is_elem.iterfind(".//a:t", _NS))
                elif v is not None and v.text is not None:
                    text = v.text
                values[idx] = text.strip()
            if values:
                width = max(values) + 1
                rows.append([values.get(i, "") for i in range(width)])
        return rows


def _norm_header(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _find_header_row(rows: list[list[str]]) -> int:
    for i, row in enumerate(rows[:30]):
        joined = " | ".join(row).lower()
        if ("file" in joined and "format" in joined and "extension" in joined) or "format id" in joined:
            return i
    return 0


def _get(row: dict[str, str], candidates: list[str]) -> str:
    """Return an exact mapped/header value only.

    Substring matching is intentionally forbidden. Source-specific mappings
    belong in config, and missing declared columns raise before extraction.
    """
    for cand in candidates:
        if cand in row and row[cand].strip():
            return row[cand].strip()
    return ""


def _candidate_headers(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(x) for x in value]
    raise TypeError(f"field_map values must be a string or list of strings, got {type(value).__name__}")


def _resolve_field_map(config: dict[str, Any], raw_headers: list[str]) -> dict[str, str]:
    """Resolve configured logical fields to normalized workbook headers.

    All missing configured fields are reported together. This matters for
    first-run usability: a user should not have to fix one header, rerun, then
    discover the next missing header.
    """
    normalized_headers = {_norm_header(h): h for h in raw_headers if _norm_header(h)}
    field_map: dict[str, str] = {}
    missing: list[tuple[str, list[str]]] = []

    for field, header_spec in config.get("field_map", {}).items():
        raw_candidates = _candidate_headers(header_spec)
        candidates = [_norm_header(h) for h in raw_candidates]
        match = next((candidate for candidate in candidates if candidate in normalized_headers), None)
        if match is None:
            missing.append((field, raw_candidates))
            continue
        field_map[field] = match

    if missing:
        available = ", ".join(sorted(normalized_headers))
        missing_lines = [
            f"- {field}: requested one of {', '.join(repr(h) for h in candidates)}"
            for field, candidates in missing
        ]
        raise ValueError(
            "Configured institutional field_map columns were not found:\n"
            + "\n".join(missing_lines)
            + f"\nAvailable normalized headers: {available}"
        )

    return field_map


def _field(row: dict[str, str], field_map: dict[str, str], field: str, defaults: list[str], aliases: tuple[str, ...] = ()) -> str:
    for field_name in (field, *aliases):
        mapped = field_map.get(field_name)
        if mapped:
            return row.get(mapped, "").strip()
    return _get(row, defaults)


class InstitutionPolicyXlsxAdapter(SourceAdapter):
    """Adapter for institution-specific file-format policy spreadsheets.

    This adapter imports local institutional decisions as an overlay attached to
    canonical file-format records. It is not QNL-specific: QNL is one profile
    supplied through configuration.
    """

    type_name = "institution_policy_xlsx"

    def acquire(self) -> list[SourceSnapshot]:
        snapshot_dir = ensure_dir(self.workdir / "snapshots" / self.source_id)
        snapshots: list[SourceSnapshot] = []
        for uri in self.config.get("uris", []):
            data, headers = read_uri(uri)
            digest = sha256_bytes(data)
            local_path = snapshot_dir / f"{digest}.xlsx"
            local_path.write_bytes(data)
            snapshots.append(SourceSnapshot(
                source_id=self.source_id,
                source_type=self.type_name,
                uri=uri,
                acquired_at=utc_now_iso(),
                sha256=digest,
                local_path=str(local_path),
                content_type=headers.get("content-type"),
            ))
        return snapshots

    def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
        records: list[RawFormatRecord] = []
        institution_id = self.config.get("institution_id") or self.source_id
        institution_name = self.config.get("institution_name") or institution_id
        institution_format_id_prefix = self.config.get("institution_format_id_prefix")

        for snap in snapshots:
            rows = _read_sheet_rows(snap.local_path)
            header_idx = self.config.get("header_row")
            if header_idx is None:
                header_idx = _find_header_row(rows)
            else:
                header_idx = int(header_idx) - 1
            raw_headers = rows[header_idx]
            headers = [_norm_header(h) for h in raw_headers]
            field_map = _resolve_field_map(self.config, raw_headers)
            for row_no, values in enumerate(rows[header_idx + 1:], start=header_idx + 2):
                row = {headers[i]: values[i] if i < len(values) else "" for i in range(len(headers)) if headers[i]}
                name = _field(row, field_map, "name", ["digital_file", "file_format", "file_format_name", "format_name", "name"])
                institution_format_id = _field(row, field_map, "institution_format_id", ["institution_format_id", "format_id", "local_format_id"], aliases=("source_id",))
                extensions = split_multi(_field(row, field_map, "extensions", ["file_extension_s", "extension", "extensions"]))
                mime_types = split_multi(_field(row, field_map, "mime_types", ["mime_type_s", "mime_type", "mime", "mimetype"]))
                category = _field(row, field_map, "category", ["category_plan_s", "category_plan", "category", "format_category", "plan"], aliases=("categories",))
                description = _field(row, field_map, "description", ["description", "description_and_justification", "description_justification", "justification"])
                pronom_url = _field(row, field_map, "pronom_url", ["pronom", "pronom_url", "puid"])
                puids = re.findall(r"\b(?:fmt|x-fmt)/\d+\b", pronom_url)
                loc_url = _field(row, field_map, "loc_url", ["loc", "library_of_congress", "loc_url"])
                loc_ids = re.findall(r"\bfdd\d+\b", loc_url, flags=re.I)
                if not name and not institution_format_id and not extensions:
                    continue

                policy = {
                    "institution_id": institution_id,
                    "institution_name": institution_name,
                    "institution_format_id": institution_format_id,
                    "institution_format_id_prefix": institution_format_id_prefix,
                    "local_risk_level": _field(row, field_map, "risk_level", ["local_risk_level", "risk_level", "risk", "qnl_risk_level"]),
                    "local_preservation_action": _field(row, field_map, "preservation_action", ["local_preservation_action", "preservation_action", "action", "qnl_preservation_action"]),
                    "local_preservation_plan": _field(row, field_map, "proposed_preservation_plan", ["local_preservation_plan", "proposed_preservation_plan", "plan", "qnl_proposed_preservation_plan"]),
                    "local_preferred_tools": _field(row, field_map, "preferred_tools", ["local_preferred_tools", "preferred_processing_and_conversion_tool_s", "preferred_tools", "tool_s"]),
                    "local_conversion_process": _field(row, field_map, "conversion_process", ["local_conversion_process", "conversion_process", "command", "process"]),
                    "source_file": snap.uri,
                    "source_row": row_no,
                    "source_adapter": self.type_name,
                }

                records.append(RawFormatRecord(
                    source_id=self.source_id,
                    source_type=self.type_name,
                    source_record_id=institution_format_id or f"{institution_id}-row-{row_no}",
                    name=name,
                    category=category,
                    description=description,
                    extensions=extensions,
                    mime_types=mime_types,
                    puids=puids,
                    loc_ids=loc_ids,
                    wikidata_ids=re.findall(r"\bQ\d{2,}\b", _field(row, field_map, "wikidata_url", ["wikidata", "wikidata_url"])),
                    urls={k: v for k, v in {
                        "pronom": pronom_url,
                        "loc": loc_url,
                        "wikidata": _field(row, field_map, "wikidata_url", ["wikidata", "wikidata_url"]),
                        "archive_team": _field(row, field_map, "archive_team_url", ["archiveteam", "archive_team"]),
                        "british_library": _field(row, field_map, "british_library_url", ["british_library", "bl"]),
                    }.items() if v},
                    institution_policy=policy,
                    raw=row,
                ))
        return records
