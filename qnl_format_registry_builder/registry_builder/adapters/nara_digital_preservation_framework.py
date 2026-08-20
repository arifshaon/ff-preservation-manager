from __future__ import annotations

import csv
import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

from registry_builder.adapters.base import NETWORK_ERRORS, SourceAdapter, describe_network_error
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

# NARA publishes the risk matrix twice. Both files carry identical values in all
# 20 non-rubric columns — every aggregate score, band and total — and differ only
# in how the 27 individual rubric answers are written.
#
# The Numbered view stores each answer's *risk contribution*, and NARA's own
# weights file documents that in 26 of the 27 questions it fuses Unknown with the
# risk-increasing answer ("-1 = Yes or Unknown", "2 = Yes, -2 = No or Unknown").
# That is a sound scoring choice and a poor evidence record: read as evidence it
# asserts findings NARA explicitly declined to make. It also discards question
# 1.4 entirely, bucketing real specification years into a score.
#
# The Labeled view writes Yes/No/Unknown/N/A and keeps the years, so for
# everything this adapter consumes it is a strict superset. It is the primary row.
_NARA_PRIMARY_ROW_KIND = "risk_matrix_labeled"
_NARA_NUMBERED_ROW_KIND = "risk_matrix_numbered"
# Preference order; the numbered view stays supported for existing configs and
# for files already dropped in an input folder.
_NARA_RISK_MATRIX_KINDS = (_NARA_PRIMARY_ROW_KIND, _NARA_NUMBERED_ROW_KIND)

DEFAULT_NARA_URIS = [
    f"{_NARA_REPO_RAW_BASE}/master/{_NARA_ACTION_DIR}/NARA_PreservationActionPlan_FileFormats_{_DEFAULT_NARA_RELEASE_DATE}.csv",
    f"{_NARA_REPO_RAW_BASE}/master/{_NARA_RISK_DIR}/NARA_File_Format_Risk_Matrix_{_DEFAULT_NARA_RELEASE_DATE}_Labeled.csv",
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


def _kind_from_file_name(value: str) -> str | None:
    name = Path(value).name
    if re.search(r"PreservationActionPlan_FileFormats_20\d{6}\.csv$", name):
        return "preservation_action_plan"
    if re.search(r"File_Format_Risk_Matrix_20\d{6}_Labeled\.csv$", name):
        return _NARA_PRIMARY_ROW_KIND
    if re.search(r"File_Format_Risk_Matrix_20\d{6}_Numbered\.csv$", name):
        return _NARA_NUMBERED_ROW_KIND
    return None


def _row_kind(snapshot: SourceSnapshot) -> str:
    metadata = snapshot.metadata or {}
    return str(metadata.get("kind") or _kind_from_file_name(snapshot.uri) or "unknown")


def _group_key(row: dict[str, Any], row_no: int, kind: str) -> str:
    nara_id = _get(row, "NARA Format ID")
    if nara_id:
        return f"nara:{nara_id}"
    name = _get(row, "Format Name")
    if name:
        return f"name:{name.lower()}"
    return f"{kind}:row:{row_no}"


def _preferred_item(items: list[dict[str, Any]]) -> dict[str, Any]:
    for kind in (*_NARA_RISK_MATRIX_KINDS, "preservation_action_plan"):
        for item in items:
            if item.get("kind") == kind:
                return item
    return items[0]


def _merged_row(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge NARA's companion CSV rows into one source-native row.

    The numbered risk matrix is the primary row because approved criterion
    mappings use rubric-answer columns. The preservation action plan still
    contributes action/readiness/planning fields and is retained in raw/evidence.
    """
    merged: dict[str, Any] = {}
    # Both risk-matrix views use identical column names, so the labeled view is
    # applied last and wins: a rubric cell must read "Unknown" rather than a
    # score that cannot distinguish Unknown from a real answer.
    for kind in ("preservation_action_plan", _NARA_NUMBERED_ROW_KIND, _NARA_PRIMARY_ROW_KIND):
        for item in items:
            if item.get("kind") == kind:
                merged.update(item["row"])
    known = {"preservation_action_plan", *_NARA_RISK_MATRIX_KINDS}
    for item in items:
        if item.get("kind") not in known:
            merged.update(item["row"])
    return merged


def _specification_year(row: dict[str, Any]) -> int | None:
    """The year NARA records for rubric question 1.4.

    Only the labeled view carries this. The numbered view buckets it into a risk
    score (0 = 5 years or less, -2 = 6-15 years, -4 = 16+ years or Unknown), so
    the actual year — the input a specification-age term needs — is unrecoverable
    from it.
    """
    for key, value in row.items():
        if not str(key).startswith(("1.4", "1．4")):
            continue
        text = str(value or "").strip()
        if re.fullmatch(r"(19|20)\d{2}", text):
            return int(text)
        return None
    return None


def _specification_currency_bucket(year: int | None, release_date: str | None) -> str | None:
    """NARA's own age bands for question 1.4, recovered from the real year.

    The weights file defines them as "0 = 5 years old or less, -2 = 6-15 years,
    -4 = 16+ years or Unknown". Those bands are what the numbered view stores in
    place of the year; recomputing them from the labeled year restores the band
    without inheriting the "or Unknown" fusion.

    Ages are measured against the NARA release, not today, so the band matches
    the one NARA itself scored and does not drift as the file sits on disk.
    """
    if year is None or not release_date:
        return None
    try:
        released = int(str(release_date)[:4])
    except (TypeError, ValueError):
        return None
    age = released - year
    if age < 0:
        return None
    if age <= 5:
        return "5_years_or_less"
    if age <= 15:
        return "6_to_15_years"
    return "16_plus_years"


def _rubric_answers(row: dict[str, Any]) -> dict[str, Any]:
    answers: dict[str, Any] = {}
    for key, value in row.items():
        match = re.match(r"^(\d+[\.\uff0e]\d+):", str(key))
        if not match:
            continue
        question_id = match.group(1).replace("\uff0e", ".")
        answers[question_id] = value
    return answers


def _evidence_for_item(item: dict[str, Any]) -> dict[str, Any]:
    row = item["row"]
    snap: SourceSnapshot = item["snapshot"]
    metadata = item["metadata"]
    return {
        "type": "nara_preservation_framework_row",
        "retrieval_mode": "published_csv",
        "source_file": snap.uri,
        "source_row": item["row_no"],
        "snapshot_changed": snap.changed,
        "snapshot_from_cache": snap.from_cache,
        "source_location": metadata.get("source_location"),
        "nara_release_mode": metadata.get("release_mode"),
        "nara_release_date": metadata.get("release_date"),
        "nara_file_kind": item.get("kind"),
        "github_ref": metadata.get("github_ref"),
        "github_path": metadata.get("github_path"),
        "github_blob_sha": metadata.get("github_blob_sha"),
        "admin_supplied": metadata.get("admin_supplied"),
        "release_resolution_error": metadata.get("release_resolution_error"),
        "nara_preservation_action": _get(row, "NARA Preservation Action"),
        "nara_preservation_plan": _get(row, "NARA Proposed Preservation Plan"),
        "nara_preferred_tools": _get(row, "NARA Preferred Processing and Transformation Tool(s)"),
    }


class NaraDigitalPreservationFrameworkAdapter(SourceAdapter):
    """Acquire and parse NARA Digital Preservation Framework data.

    This is a source-level adapter. It supports four release modes:

    - explicit_uris: use configured URIs exactly;
    - pinned: resolve the two dated NARA CSV filenames for a configured release;
    - latest: discover the latest dated CSV pair from NARA's GitHub contents API;
    - local_files: use administrator-supplied CSV files as source material.
    """

    type_name = "nara_digital_preservation_framework"
    supports_input_dir = True
    inbox_hint = (
        "Drop the NARA release CSVs here, keeping their published filenames "
        "(e.g. NARA_PreservationActionPlan_FileFormats_20260320.csv and "
        "NARA_File_Format_Risk_Matrix_20260320_Labeled.csv). Kind and release "
        "date are inferred from the filename; a manifest.json is only needed "
        "for renamed files."
    )
    default_uris = DEFAULT_NARA_URIS

    def _github_ref(self) -> str:
        return str(self.config.get("github_ref") or self.config.get("ref") or "master")

    def _release_mode(self) -> str:
        mode = str(self.config.get("release_mode") or "").strip().lower()
        if not mode:
            return "explicit_uris" if self.config.get("uris") else "pinned"
        aliases = {
            "explicit": "explicit_uris",
            "uris": "explicit_uris",
            "date": "pinned",
            "file": "local_files",
            "files": "local_files",
            "local_file": "local_files",
            "manual": "local_files",
        }
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
        risk_path = f"{_NARA_RISK_DIR}/NARA_File_Format_Risk_Matrix_{release_date}_Labeled.csv"
        sources = [
            {
                "uri": self._raw_uri_for_path(action_path),
                "kind": "preservation_action_plan",
                "release_mode": release_mode,
                "release_date": release_date,
                "github_ref": self._github_ref(),
                "github_path": action_path,
                "source_location": "remote_uri",
            },
            {
                "uri": self._raw_uri_for_path(risk_path),
                "kind": _NARA_PRIMARY_ROW_KIND,
                "release_mode": release_mode,
                "release_date": release_date,
                "github_ref": self._github_ref(),
                "github_path": risk_path,
                "source_location": "remote_uri",
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
                "kind": _kind_from_file_name(uri) or "explicit_uri",
                "release_mode": "explicit_uris",
                "release_date": release_date,
                "github_ref": self._github_ref(),
                "github_path": None,
                "source_location": "remote_uri",
            }
            for uri in uris
        ]

    def _local_file_entries(self, *, fallback: bool = False) -> list[Any]:
        if fallback:
            return list(
                self.config.get("fallback_local_files")
                or self.config.get("manual_fallback_files")
                or self.config.get("fallback_files")
                or []
            )
        return list(self.config.get("local_files") or self.config.get("files") or [])

    def _local_file_sources(
        self,
        entries: list[Any] | None = None,
        *,
        release_mode: str = "local_files",
        resolution_error: str | None = None,
    ) -> list[dict[str, Any]]:
        entries = self._local_file_entries() if entries is None else entries
        if not entries:
            raise ValueError("NARA release_mode local_files requires local_files or files")
        sources: list[dict[str, Any]] = []
        for entry in entries:
            if isinstance(entry, str):
                path = entry
                item: dict[str, Any] = {}
            elif isinstance(entry, dict):
                item = dict(entry)
                path = item.get("path") or item.get("local_path") or item.get("file") or item.get("uri")
                if not path:
                    raise ValueError(f"NARA local file entry requires path/local_path/file/uri: {entry!r}")
            else:
                raise TypeError(f"NARA local file entries must be strings or objects, got {type(entry).__name__}")
            path_text = str(path)
            release_date = item.get("release_date") or _release_date_from_text(path_text)
            kind = item.get("kind") or _kind_from_file_name(path_text) or "local_file"
            source = {
                "uri": path_text,
                "kind": kind,
                "release_mode": release_mode,
                "release_date": _normalize_release_date(release_date) if release_date else None,
                "github_ref": item.get("github_ref") or self._github_ref(),
                "github_path": item.get("github_path"),
                "source_location": "local_file",
                "admin_supplied": True,
            }
            for key in ("github_blob_sha", "github_html_url", "note"):
                if item.get(key):
                    source[key] = item[key]
            if resolution_error:
                source["release_resolution_error"] = resolution_error
            sources.append(source)
        return sources

    def _fallback_local_file_sources(self, *, release_mode: str, resolution_error: str) -> list[dict[str, Any]] | None:
        entries = self._local_file_entries(fallback=True)
        if not entries:
            return None
        logger.warning("NARA latest discovery failed; using administrator-supplied local fallback files")
        return self._local_file_sources(entries, release_mode=release_mode, resolution_error=resolution_error)

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
            match = re.fullmatch(r"NARA_File_Format_Risk_Matrix_(20\d{6})_Labeled\.csv", name)
            if match:
                risk_by_date[match.group(1)] = item
        common_dates = sorted(set(action_by_date) & set(risk_by_date))
        if not common_dates:
            raise ValueError("Could not resolve latest NARA release: no matching action-plan and labeled-risk CSV release dates found")
        release_date = common_dates[-1]
        sources: list[dict[str, Any]] = []
        for kind, item in (
            ("preservation_action_plan", action_by_date[release_date]),
            (_NARA_PRIMARY_ROW_KIND, risk_by_date[release_date]),
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
                "source_location": "remote_uri",
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
            if resolution_error:
                fallback = self._fallback_local_file_sources(release_mode="latest_local_fallback", resolution_error=resolution_error)
                if fallback:
                    return fallback
            raise FileNotFoundError(
                "Offline NARA release_mode latest requires a cached .nara_release_index.json created by a previous online latest run or fallback_local_files"
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
            fallback = self._fallback_local_file_sources(release_mode="latest_local_fallback", resolution_error=error)
            if fallback:
                return fallback
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
            return self._latest_sources_offline(resolution_error="offline=true") if self.offline else self._latest_sources_with_fallback()
        if mode == "local_files":
            return self._local_file_sources()
        raise ValueError("NARA release_mode must be one of: explicit_uris, pinned, latest, local_files")

    def describe_local_file(self, path: Path) -> dict[str, Any]:
        """NARA filenames are self-describing: kind and release date are inferred.

        e.g. NARA_File_Format_Risk_Matrix_20260320_Labeled.csv
        """
        described = super().describe_local_file(path)
        release_date = described.get("release_date") or described.get("edition") or _release_date_from_text(path.name)
        if release_date:
            release_date = _normalize_release_date(release_date)
            described.setdefault("release_date", release_date)
            described.setdefault("edition", release_date)
            described.setdefault(
                "source_published_at",
                f"{release_date[0:4]}-{release_date[4:6]}-{release_date[6:8]}",
            )
        kind = described.get("kind") or _kind_from_file_name(path.name)
        if kind:
            described.setdefault("kind", kind)
        return described

    def acquire(self) -> list[SourceSnapshot]:
        """Policy-aware acquisition over NARA's release modes.

        Files dropped in input/<source_id>/ win outright: the configured release
        mode is not consulted and the network is not contacted, unless
        force_check_url is set — in which case a failed network fetch (404, 503,
        timeout) falls back to the dropped files with the failure recorded.
        """
        inbox = self.local_input_files()
        policy = self.acquisition_policy
        if policy == "local_only":
            snapshots = self._acquire_inbox(inbox)
        elif inbox and policy == "auto" and not self.force_check_url:
            logger.info(
                "NARA: using %d dropped file(s) from %s; network not contacted (set force_check_url to override)",
                len(inbox), self.input_dir(),
            )
            snapshots = self._acquire_inbox(inbox)
        else:
            try:
                snapshots = self._acquire_configured_sources()
            except NETWORK_ERRORS as exc:
                if not inbox:
                    raise
                reason = describe_network_error(exc)
                logger.warning("NARA: network fetch failed (%s); falling back to dropped input files", reason)
                snapshots = self._acquire_inbox(inbox, network_error=reason)
        self._log_currency(snapshots)
        return snapshots

    def _acquire_inbox(self, inbox: list[Path], *, network_error: str | None = None) -> list[SourceSnapshot]:
        if not inbox:
            raise FileNotFoundError(
                f"No NARA input files found under {self.input_dir()}; "
                "drop the release CSVs there or configure a network release_mode"
            )
        sources = self._local_file_sources(
            [self._inbox_entry(path) for path in inbox],
            release_mode="input_dir",
            resolution_error=network_error,
        )
        return self._acquire_sources(sources)

    def _inbox_entry(self, path: Path) -> dict[str, Any]:
        entry = {"path": str(path)}
        described = self.describe_local_file(path)
        for key in ("kind", "release_date"):
            if described.get(key):
                entry[key] = described[key]
        return entry

    def _acquire_configured_sources(self) -> list[SourceSnapshot]:
        return self._acquire_sources(self._resolved_sources())

    def _acquire_sources(self, sources: list[dict[str, Any]]) -> list[SourceSnapshot]:
        snapshots: list[SourceSnapshot] = []
        for source in sources:
            uri = source["uri"]
            note = "; ".join(
                x for x in [
                    "retrieval_mode=published_csv",
                    f"nara_release_mode={source.get('release_mode')}",
                    f"nara_release_date={source.get('release_date')}" if source.get("release_date") else None,
                    f"nara_file_kind={source.get('kind')}",
                    f"source_location={source.get('source_location')}" if source.get("source_location") else None,
                    "release_resolution_error=true" if source.get("release_resolution_error") else None,
                ] if x
            )
            metadata = {k: v for k, v in source.items() if k != "uri"}
            release_date = source.get("release_date")
            if release_date:
                metadata.setdefault("edition", str(release_date))
                metadata.setdefault(
                    "source_published_at",
                    f"{str(release_date)[0:4]}-{str(release_date)[4:6]}-{str(release_date)[6:8]}",
                )
            if source.get("source_location") == "local_file":
                snapshots.append(
                    self.acquire_file_snapshot(
                        uri,
                        suffix=Path(uri).suffix or ".csv",
                        note=note,
                        metadata=metadata,
                    )
                )
            else:
                snapshots.append(
                    self.acquire_uri_snapshot(
                        uri,
                        suffix=Path(uri.split("?")[0]).suffix or ".csv",
                        note=note,
                        metadata=metadata,
                    )
                )
        return snapshots

    def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for snap in snapshots:
            metadata = snap.metadata or {}
            kind = _row_kind(snap)
            with Path(snap.local_path).open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row_no, row in enumerate(reader, start=2):
                    nara_id = _get(row, "NARA Format ID")
                    name = _get(row, "Format Name")
                    extensions = split_multi(_get(row, "File Extension(s)"))
                    if not nara_id and not name and not extensions:
                        continue
                    item = {
                        "kind": kind,
                        "row": row,
                        "row_no": row_no,
                        "snapshot": snap,
                        "metadata": metadata,
                    }
                    grouped.setdefault(_group_key(row, row_no, kind), []).append(item)

        records: list[RawFormatRecord] = []
        for items in grouped.values():
            primary = _preferred_item(items)
            primary_kind = str(primary.get("kind") or "unknown")
            row = _merged_row(items)
            nara_id = _get(row, "NARA Format ID")
            pronom_url = _get(row, "PRONOM URL")
            loc_url = _get(row, "LOC URL")
            wikidata_url = _get(row, "WikiData URL", "Wikidata URL")
            evidence = [_evidence_for_item(item) for item in items]
            spec_year = _specification_year(row)
            rows_by_kind = {str(item.get("kind") or "unknown"): item["row"] for item in items}
            row_numbers_by_kind = {str(item.get("kind") or "unknown"): item["row_no"] for item in items}
            snapshot_sha256_by_kind = {
                str(item.get("kind") or "unknown"): item["snapshot"].sha256 for item in items
            }
            release_dates = sorted({
                str(item["metadata"].get("release_date"))
                for item in items
                if item.get("metadata") and item["metadata"].get("release_date")
            })

            spec_bracket = _specification_currency_bucket(spec_year, release_dates[-1] if release_dates else None)

            records.append(RawFormatRecord(
                source_id=self.source_id,
                source_type=self.type_name,
                source_record_id=nara_id or f"nara-row-{primary['row_no']}",
                name=_get(row, "Format Name"),
                category=_get(row, "Category/Plan(s)"),
                description=_get(row, "Description and Justification"),
                extensions=split_multi(_get(row, "File Extension(s)")),
                mime_types=split_multi(_get(row, "MIME type(s)")),
                puids=re.findall(r"\b(?:fmt|x-fmt)/\d+\b", pronom_url),
                loc_ids=re.findall(r"\bfdd\d+\b", loc_url, flags=re.I),
                nara_ids=[nara_id] if nara_id else [],
                wikidata_ids=re.findall(r"\bQ\d{2,}\b", wikidata_url),
                urls=_urls(row),
                hazard=_hazard(row, self.type_name),
                evidence=[x for x in evidence if any(v for v in x.values())],
                native_fields={
                    "primary_nara_file_kind": primary_kind,
                    "nara_file_kinds": sorted(rows_by_kind),
                    "nara_release_dates": release_dates,
                    "rubric_answers": _rubric_answers(row),
                    **({"specification_year": spec_year} if spec_year is not None else {}),
                    **({"specification_age_bracket": spec_bracket} if spec_bracket else {}),
                },
                raw={
                    "snapshot_sha256": primary["snapshot"].sha256,
                    "snapshot_sha256_by_kind": snapshot_sha256_by_kind,
                    "row": row,
                    "rows_by_kind": rows_by_kind,
                    "row_numbers_by_kind": row_numbers_by_kind,
                },
            ))
        return records
