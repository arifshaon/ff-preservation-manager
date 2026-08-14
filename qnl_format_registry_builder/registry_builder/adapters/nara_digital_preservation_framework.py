from __future__ import annotations

import csv
import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

from registry_builder.adapters.base import SourceAdapter
from registry_builder.hazard import BAND_TO_SCORE
from registry_builder.models import RawFormatRecord, SourceSnapshot, utc_now_iso
from registry_builder.utils import read_uri, split_multi

logger = logging.getLogger(__name__)

_NARA_NATIVE_SCALE = "nara_file_format_risk_matrix"
_NARA_NATIVE_DIRECTION = "higher_is_safer"
_NARA_REPO_RAW_BASE = "https://raw.githubusercontent.com/usnationalarchives/digital-preservation"
_NARA_REPO_API_BASE = "https://api.github.com/repos/usnationalarchives/digital-preservation/contents"
_NARA_ACTION_DIR = "Digital_Preservation_Plan_Spreadsheet"
_NARA_RISK_DIR = "Digital_Preservation_Risk_Matrix"
_DEFAULT_NARA_RELEASE_DATE = "20260320"

DEFAULT_NARA_URIS = [
    f"{_NARA_REPO_RAW_BASE}/master/{_NARA_ACTION_DIR}/NARA_PreservationActionPlan_FileFormats_{_DEFAULT_NARA_RELEASE_DATE}.csv",
    f"{_NARA_REPO_RAW_BASE}/master/{_NARA_RISK_DIR}/NARA_File_Format_Risk_Matrix_{_DEFAULT_NARA_RELEASE_DATE}_Numbered.csv",
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


def _normalize_release_date(value: Any) -> str:
    text = re.sub(r"\D+", "", str(value or ""))
    if len(text) != 8:
        raise ValueError(f"NARA release_date must contain YYYYMMDD, got: {value!r}")
    return text


def _release_date_from_text(value: str) -> str | None:
    match = re.search(r"(20\d{6})", value)
    return match.group(1) if match else None


class NaraDigitalPreservationFrameworkAdapter(SourceAdapter):
    """Acquire and parse NARA Digital Preservation Framework data.

    This is a source-level adapter. It supports three release modes:

    - explicit_uris: use configured URIs exactly;
    - pinned: resolve the two dated NARA CSV filenames for a configured release;
    - latest: discover the latest dated CSV pair from NARA's GitHub contents API.
    """

    type_name = "nara_digital_preservation_framework"
    default_uris = DEFAULT_NARA_URIS

    def _github_ref(self) -> str:
        return str(self.config.get("github_ref") or self.config.get("ref") or "master")

    def _release_mode(self) -> str:
        mode = str(self.config.get("release_mode") or "").strip().lower()
        if not mode:
            return "explicit_uris" if self.config.get("uris") else "pinned"
        aliases = {"explicit": "explicit_uris", "uris": "explicit_uris", "date": "pinned"}
        return aliases.get(mode, mode)

    def _fallback_release_date(self) -> str:
        return _normalize_release_date(self.config.get("fallback_release_date") or _DEFAULT_NARA_RELEASE_DATE)

    def _release_index_path(self) -> Path:
        return self.snapshot_dir() / ".nara_release_index.json"

    def _load_release_index(self) -> dict[str, Any]:
        path = self._release_index_path()
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_release_index(self, index: dict[str, Any]) -> None:
        path = self._release_index_path()
        path.write_text(json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _raw_uri_for_path(self, path: str) -> str:
        return f"{_NARA_REPO_RAW_BASE}/{self._github_ref()}/{path}"

    def _pinned_sources(self, release_date: str, *, release_mode: str, resolution_error: str | None = None) -> list[dict[str, Any]]:
        action_path = f"{_NARA_ACTION_DIR}/NARA_PreservationActionPlan_FileFormats_{release_date}.csv"
        risk_path = f"{_NARA_RISK_DIR}/NARA_File_Format_Risk_Matrix_{release_date}_Numbered.csv"
        sources = [
            {
                "uri": self._raw_uri_for_path(action_path),
                "kind": "preservation_action_plan",
                "release_mode": release_mode,
                "release_date": release_date,
                "github_ref": self._github_ref(),
                "github_path": action_path,
            },
            {
                "uri": self._raw_uri_for_path(risk_path),
                "kind": "risk_matrix_numbered",
                "release_mode": release_mode,
                "release_date": release_date,
                "github_ref": self._github_ref(),
                "github_path": risk_path,
            },
        ]
        if resolution_error:
            for source in sources:
                source["release_resolution_error"] = resolution_error
        return sources

    def _explicit_sources(self) -> list[dict[str, Any]]:
        uris = list(self.config.get("uris") or [])
        if not uris:
            raise ValueError("NARA release_mode explicit_uris requires uris")
        inferred_dates = sorted({date for uri in uris if (date := _release_date_from_text(uri))})
        release_date = inferred_dates[0] if len(inferred_dates) == 1 else None
        return [
            {
                "uri": uri,
                "kind": "explicit_uri",
                "release_mode": "explicit_uris",
                "release_date": release_date,
                "github_ref": self._github_ref(),
                "github_path": None,
            }
            for uri in uris
        ]

    def _fetch_github_directory(self, directory: str) -> list[dict[str, Any]]:
        uri = f"{_NARA_REPO_API_BASE}/{directory}?ref={self._github_ref()}"
        data, _headers = read_uri(uri)
        payload = json.loads(data.decode("utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"Unexpected NARA GitHub directory response for {directory}: {payload!r}")
        return payload

    def _latest_sources_online(self) -> list[dict[str, Any]]:
        action_items = self._fetch_github_directory(_NARA_ACTION_DIR)
        risk_items = self._fetch_github_directory(_NARA_RISK_DIR)
        action_by_date: dict[str, dict[str, Any]] = {}
        risk_by_date: dict[str, dict[str, Any]] = {}
        for item in action_items:
            name = str(item.get("name") or "")
            match = re.fullmatch(r"NARA_PreservationActionPlan_FileFormats_(20\d{6})\.csv", name)
            if match:
                action_by_date[match.group(1)] = item
        for item in risk_items:
            name = str(item.get("name") or "")
            match = re.fullmatch(r"NARA_File_Format_Risk_Matrix_(20\d{6})_Numbered\.csv", name)
            if match:
                risk_by_date[match.group(1)] = item
        common_dates = sorted(set(action_by_date) & set(risk_by_date))
        if not common_dates:
            raise ValueError("Could not resolve latest NARA release: no matching action-plan and numbered-risk CSV release dates found")
        release_date = common_dates[-1]
        sources: list[dict[str, Any]] = []
        for kind, item in (
            ("preservation_action_plan", action_by_date[release_date]),
            ("risk_matrix_numbered", risk_by_date[release_date]),
        ):
            path = item.get("path")
            uri = item.get("download_url") or self._raw_uri_for_path(path)
            sources.append({
                "uri": uri,
                "kind": kind,
                "release_mode": "latest",
                "release_date": release_date,
                "github_ref": self._github_ref(),
                "github_path": path,
                "github_blob_sha": item.get("sha"),
                "github_html_url": item.get("html_url"),
            })
        index = self._load_release_index()
        index["latest"] = {
            "resolved_at": utc_now_iso(),
            "github_ref": self._github_ref(),
            "release_date": release_date,
            "sources": sources,
        }
        self._write_release_index(index)
        return sources

    def _latest_sources_offline(self, *, release_mode: str = "latest", resolution_error: str | None = None) -> list[dict[str, Any]]:
        latest = self._load_release_index().get("latest") or {}
        sources = latest.get("sources") or []
        if not sources:
            raise FileNotFoundError(
                "Offline NARA release_mode latest requires a cached .nara_release_index.json created by a previous online latest run"
            )
        out = []
        for source in sources:
            item = dict(source) | {"release_mode": release_mode}
            if resolution_error:
                item["release_resolution_error"] = resolution_error
            out.append(item)
        return out

    def _latest_sources_with_fallback(self) -> list[dict[str, Any]]:
        try:
            return self._latest_sources_online()
        except (HTTPError, URLError) as exc:
            error = f"{type(exc).__name__}: {exc}"
            if self._release_index_path().exists():
                logger.warning("NARA latest discovery failed (%s); using cached release index", exc)
                return self._latest_sources_offline(release_mode="latest_cached_fallback", resolution_error=error)
            fallback_date = self._fallback_release_date()
            logger.warning(
                "NARA latest discovery failed (%s); falling back to pinned %s",
                exc,
                fallback_date,
            )
            return self._pinned_sources(fallback_date, release_mode="latest_fallback", resolution_error=error)

    def _resolved_sources(self) -> list[dict[str, Any]]:
        mode = self._release_mode()
        if mode == "explicit_uris":
            return self._explicit_sources()
        if mode == "pinned":
            release_date = _normalize_release_date(self.config.get("release_date") or _DEFAULT_NARA_RELEASE_DATE)
            return self._pinned_sources(release_date, release_mode="pinned")
        if mode == "latest":
            return self._latest_sources_offline() if self.offline else self._latest_sources_with_fallback()
        raise ValueError("NARA release_mode must be one of: explicit_uris, pinned, latest")

    def acquire(self) -> list[SourceSnapshot]:
        snapshots: list[SourceSnapshot] = []
        for source in self._resolved_sources():
            uri = source["uri"]
            note = "; ".join(
                x for x in [
                    "retrieval_mode=published_csv",
                    f"nara_release_mode={source.get('release_mode')}",
                    f"nara_release_date={source.get('release_date')}" if source.get("release_date") else None,
                    f"nara_file_kind={source.get('kind')}",
                    "release_resolution_error=true" if source.get("release_resolution_error") else None,
                ] if x
            )
            snapshots.append(
                self.acquire_uri_snapshot(
                    uri,
                    suffix=Path(uri.split("?")[0]).suffix or ".csv",
                    note=note,
                    metadata={k: v for k, v in source.items() if k != "uri"},
                )
            )
        return snapshots

    def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
        records: list[RawFormatRecord] = []
        for snap in snapshots:
            metadata = snap.metadata or {}
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
                        "snapshot_changed": snap.changed,
                        "snapshot_from_cache": snap.from_cache,
                        "nara_release_mode": metadata.get("release_mode"),
                        "nara_release_date": metadata.get("release_date"),
                        "nara_file_kind": metadata.get("kind"),
                        "github_ref": metadata.get("github_ref"),
                        "github_path": metadata.get("github_path"),
                        "github_blob_sha": metadata.get("github_blob_sha"),
                        "release_resolution_error": metadata.get("release_resolution_error"),
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
