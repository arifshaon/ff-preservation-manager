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
        if ("file" in joined and "format" in joined and "extension" in joined) or "qnl format id" in joined:
            return i
    return 0


def _get(row: dict[str, str], candidates: list[str]) -> str:
    for cand in candidates:
        if cand in row and row[cand].strip():
            return row[cand].strip()
    # fuzzy fallback
    for key, value in row.items():
        for cand in candidates:
            if cand in key and value.strip():
                return value.strip()
    return ""


class QnlPolicyXlsxAdapter(SourceAdapter):
    """Adapter for the QNL file-format policy spreadsheet.

    This imports QNL content as an institutional policy overlay, not as the
    boundary of the canonical registry.
    """

    type_name = "qnl_policy_xlsx"

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
        for snap in snapshots:
            rows = _read_sheet_rows(snap.local_path)
            header_idx = self.config.get("header_row")
            if header_idx is None:
                header_idx = _find_header_row(rows)
            else:
                header_idx = int(header_idx) - 1
            headers = [_norm_header(h) for h in rows[header_idx]]
            for row_no, values in enumerate(rows[header_idx + 1:], start=header_idx + 2):
                row = {headers[i]: values[i] if i < len(values) else "" for i in range(len(headers)) if headers[i]}
                name = _get(row, ["file_format", "format", "file_format_name", "format_name", "name"])
                qnl_format_id = _get(row, ["qnl_format_id", "qnl_id"])
                extensions = split_multi(_get(row, ["extension", "extensions", "file_extension_s"] ))
                mime_types = split_multi(_get(row, ["mime_type", "mime", "mimetype"] ))
                pronom_url = _get(row, ["pronom", "pronom_url", "puid"])
                puids = re.findall(r"\b(?:fmt|x-fmt)/\d+\b", pronom_url)
                loc_url = _get(row, ["loc", "library_of_congress", "loc_url"])
                loc_ids = re.findall(r"\bfdd\d+\b", loc_url, flags=re.I)
                if not name and not qnl_format_id and not extensions:
                    continue
                records.append(RawFormatRecord(
                    source_id=self.source_id,
                    source_type=self.type_name,
                    source_record_id=qnl_format_id or f"qnl-row-{row_no}",
                    name=name,
                    category=_get(row, ["category", "format_category", "plan"]),
                    description=_get(row, ["description", "description_and_justification", "justification"]),
                    extensions=extensions,
                    mime_types=mime_types,
                    puids=puids,
                    loc_ids=loc_ids,
                    wikidata_ids=re.findall(r"\bQ\d{2,}\b", _get(row, ["wikidata", "wikidata_url"])),
                    urls={k: v for k, v in {
                        "pronom": pronom_url,
                        "loc": loc_url,
                        "wikidata": _get(row, ["wikidata", "wikidata_url"]),
                        "archive_team": _get(row, ["archiveteam", "archive_team"]),
                        "british_library": _get(row, ["british_library", "bl"]),
                    }.items() if v},
                    qnl={
                        "qnl_format_id": qnl_format_id,
                        "spreadsheet_risk_level": _get(row, ["qnl_risk_level", "risk_level", "risk"]),
                        "preservation_action": _get(row, ["qnl_preservation_action", "preservation_action", "action"]),
                        "proposed_preservation_plan": _get(row, ["qnl_proposed_preservation_plan", "proposed_preservation_plan", "plan"]),
                        "preferred_tools": _get(row, ["preferred_processing_and_conversion_tool_s", "preferred_tools", "tool_s"]),
                        "conversion_process": _get(row, ["conversion_process", "command", "process"]),
                        "source_file": snap.uri,
                        "source_row": row_no,
                    },
                    raw=row,
                ))
        return records
