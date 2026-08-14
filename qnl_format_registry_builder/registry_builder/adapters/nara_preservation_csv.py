from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

from registry_builder.adapters.base import SourceAdapter
from registry_builder.hazard import BAND_TO_SCORE
from registry_builder.models import RawFormatRecord, SourceSnapshot, utc_now_iso
from registry_builder.utils import ensure_dir, read_uri, sha256_bytes, split_multi

_NARA_NATIVE_SCALE = "nara_file_format_risk_matrix"
_NARA_NATIVE_DIRECTION = "higher_is_safer"


def _get(row: dict[str, Any], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _float(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _risk_band(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"\s+", " ", value).strip().lower()
    if "high" in text:
        return "High"
    if "moderate" in text or "medium" in text:
        return "Moderate"
    if "low" in text:
        return "Low"
    return None


def _risk_rating(value: str | None) -> float | None:
    band = _risk_band(value)
    if not band:
        return None
    return BAND_TO_SCORE[band]


def _urls(row: dict[str, Any]) -> dict[str, str]:
    return {k: v for k, v in {
        "specification": _get(row, "Specification/Standard URL"),
        "pronom": _get(row, "PRONOM URL"),
        "loc": _get(row, "LOC URL"),
        "british_library": _get(row, "British Library URL"),
        "wikidata": _get(row, "WikiData URL", "Wikidata URL"),
        "archive_team": _get(row, "ArchiveTeam URL"),
        "forensics_wiki": _get(row, "ForensicsWiki URL"),
        "wikipedia": _get(row, "Wikipedia URL"),
        "docs_fileformat": _get(row, "docs.fileformat.com"),
        "other": _get(row, "Other URL"),
    }.items() if v}


def _hazard(row: dict[str, Any]) -> dict[str, Any]:
    risk_level = _get(row, "NARA Risk Level", "Risk Level")
    band = _risk_band(risk_level)
    rating = _risk_rating(risk_level)
    native_numeric = _float(_get(row, "Numeric Risk Rating", "TOTAL Numeric Risk Rating"))
    nara_total = _float(_get(row, "NARA TOTAL"))

    hazard: dict[str, Any] = {}
    if band:
        hazard["external_band"] = band
        hazard["band"] = band
    if rating is not None:
        hazard["rating"] = rating
        hazard["normalized_rating"] = rating
    if risk_level:
        hazard["native_band"] = risk_level
    if native_numeric is not None:
        hazard["native_rating"] = native_numeric
        hazard["nara_native_numeric_risk_rating"] = native_numeric
        hazard["native_scale"] = _NARA_NATIVE_SCALE
        hazard["native_direction"] = _NARA_NATIVE_DIRECTION
        hazard["native_direction_note"] = "NARA native numeric rating is retained separately; higher means safer."
    if nara_total is not None:
        hazard["nara_total"] = nara_total
    if hazard:
        hazard["source"] = "NARA Digital Preservation Framework"
        hazard["source_type"] = NaraPreservationCsvAdapter.type_name
    return hazard


class NaraPreservationCsvAdapter(SourceAdapter):
    """Parse NARA Digital Preservation Framework CSV files.

    The adapter accepts both the Preservation Action Plan CSV and the numbered
    Risk Matrix CSV. If both are configured as source URIs, records reconcile by
    verified NARA Format ID. Native NARA numeric ratings are preserved separately
    from the normalized Low/Moderate/High rating used by the current reconciler.
    """

    type_name = "nara_preservation_csv"

    def acquire(self) -> list[SourceSnapshot]:
        snapshot_dir = ensure_dir(self.workdir / "snapshots" / self.source_id)
        snapshots: list[SourceSnapshot] = []
        for uri in self.config.get("uris", []):
            data, headers = read_uri(uri)
            digest = sha256_bytes(data)
            suffix = Path(uri.split("?")[0]).suffix or ".csv"
            local_path = snapshot_dir / f"{digest}{suffix}"
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
            with Path(snap.local_path).open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row_no, row in enumerate(reader, start=2):
                    nara_id = _get(row, "NARA Format ID")
                    name = _get(row, "Format Name")
                    extensions = split_multi(_get(row, "File Extension(s)"))
                    if not nara_id and not name and not extensions:
                        continue

                    pronom_url = _get(row, "PRONOM URL")
                    loc_url = _get(row, "LOC URL")
                    wikidata_url = _get(row, "WikiData URL", "Wikidata URL")
                    action = _get(row, "NARA Preservation Action")
                    plan = _get(row, "NARA Proposed Preservation Plan")
                    tools = _get(row, "NARA Preferred Processing and Transformation Tool(s)")

                    evidence = [{
                        "type": "nara_preservation_framework_row",
                        "source_file": snap.uri,
                        "source_row": row_no,
                        "nara_preservation_action": action,
                        "nara_preservation_plan": plan,
                        "nara_preferred_tools": tools,
                    }]

                    records.append(RawFormatRecord(
                        source_id=self.source_id,
                        source_type=self.type_name,
                        source_record_id=nara_id or f"nara-row-{row_no}",
                        name=name,
                        category=_get(row, "Category/Plan(s)"),
                        description=_get(row, "Description and Justification"),
                        extensions=extensions,
                        mime_types=split_multi(_get(row, "MIME type(s)")),
                        puids=re.findall(r"\b(?:fmt|x-fmt)/\d+\b", pronom_url),
                        loc_ids=re.findall(r"\bfdd\d+\b", loc_url, flags=re.I),
                        nara_ids=[nara_id] if nara_id else [],
                        wikidata_ids=re.findall(r"\bQ\d{2,}\b", wikidata_url),
                        urls=_urls(row),
                        hazard=_hazard(row),
                        evidence=[x for x in evidence if any(v for v in x.values())],
                        raw={"snapshot_sha256": snap.sha256, "row": row},
                    ))
        return records
