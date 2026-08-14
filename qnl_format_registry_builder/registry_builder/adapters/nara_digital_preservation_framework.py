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

DEFAULT_NARA_URIS = [
    "https://raw.githubusercontent.com/usnationalarchives/digital-preservation/master/Digital_Preservation_Plan_Spreadsheet/NARA_PreservationActionPlan_FileFormats_20260320.csv",
    "https://raw.githubusercontent.com/usnationalarchives/digital-preservation/master/Digital_Preservation_Risk_Matrix/NARA_File_Format_Risk_Matrix_20260320_Numbered.csv",
]


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


def _nara_band_from_native_rating(rating: float | None) -> str | None:
    """Map NARA's native numeric rating to a hazard band.

    NARA's native direction is inverted relative to intuitive hazard scoring:
    higher means safer. The normalized band/rating below is used for current
    Low/Moderate/High reconciliation; the native numeric value is retained for
    trend/change detection and threshold-distance reporting.
    """
    if rating is None:
        return None
    if rating >= 23:
        return "Low"
    if rating <= -23:
        return "High"
    return "Moderate"


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


def _hazard(row: dict[str, Any], source_type: str) -> dict[str, Any]:
    risk_level = _get(row, "NARA Risk Level", "Risk Level")
    native_numeric = _float(_get(row, "Numeric Risk Rating", "TOTAL Numeric Risk Rating"))
    nara_total = _float(_get(row, "NARA TOTAL"))

    native_band_from_rating = _nara_band_from_native_rating(native_numeric)
    text_band = _risk_band(risk_level)
    band = native_band_from_rating or text_band
    rating = BAND_TO_SCORE[band] if band else _risk_rating(risk_level)

    hazard: dict[str, Any] = {}
    if band:
        hazard["external_band"] = band
        hazard["band"] = band
    if rating is not None:
        hazard["rating"] = rating
        hazard["normalized_rating"] = rating
    if risk_level:
        hazard["native_band"] = risk_level
        hazard["external_native_band"] = risk_level
    if native_numeric is not None:
        hazard["native_rating"] = native_numeric
        hazard["external_rating_native"] = native_numeric
        hazard["external_native_rating"] = native_numeric
        hazard["nara_native_numeric_risk_rating"] = native_numeric
        hazard["native_scale"] = _NARA_NATIVE_SCALE
        hazard["external_rating_native_scale"] = _NARA_NATIVE_SCALE
        hazard["native_direction"] = _NARA_NATIVE_DIRECTION
        hazard["external_rating_native_direction"] = _NARA_NATIVE_DIRECTION
        hazard["native_direction_note"] = "NARA native numeric rating is retained separately; higher means safer."
        if native_band_from_rating:
            hazard["native_rating_band"] = native_band_from_rating
    if nara_total is not None:
        hazard["nara_total"] = nara_total
    if hazard:
        hazard["source"] = "NARA Digital Preservation Framework"
        hazard["source_type"] = source_type
    return hazard


class NaraDigitalPreservationFrameworkAdapter(SourceAdapter):
    """Acquire and parse NARA Digital Preservation Framework data.

    This is a source-level adapter. Its current implemented retrieval mode is
    NARA's published CSV files from the public GitHub/raw dataset. Future modes
    such as API, linked-data, or HTML extraction should be added inside this
    source adapter rather than exposed as separate source concepts.
    """

    type_name = "nara_digital_preservation_framework"
    default_uris = DEFAULT_NARA_URIS

    def _uris(self) -> list[str]:
        return list(self.config.get("uris") or self.default_uris)

    def acquire(self) -> list[SourceSnapshot]:
        snapshot_dir = ensure_dir(self.workdir / "snapshots" / self.source_id)
        snapshots: list[SourceSnapshot] = []
        for uri in self._uris():
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
                note="retrieval_mode=published_csv",
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
                        "retrieval_mode": "published_csv",
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
                        hazard=_hazard(row, self.type_name),
                        evidence=[x for x in evidence if any(v for v in x.values())],
                        raw={"snapshot_sha256": snap.sha256, "row": row},
                    ))
        return records
