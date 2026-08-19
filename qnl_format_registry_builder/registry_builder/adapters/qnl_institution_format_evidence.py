from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from registry_builder.adapters.base import SourceAdapter
from registry_builder.models import RawFormatRecord, SourceSnapshot
from registry_builder.utils import split_multi


_FORMAT_IDENTIFIER_FIELDS = {
    "puid": "puids",
    "puids": "puids",
    "loc": "loc_ids",
    "loc_id": "loc_ids",
    "loc_ids": "loc_ids",
    "nara": "nara_ids",
    "nara_id": "nara_ids",
    "nara_ids": "nara_ids",
    "extension": "extensions",
    "extensions": "extensions",
    "mime": "mime_types",
    "mime_type": "mime_types",
    "mime_types": "mime_types",
}

_CLAIM_FIELDS = {
    "criterion_id",
    "criterion_group",
    "evidence_value",
    "statement",
    "source",
    "evidence_owner",
    "date_observed",
    "review_due",
    "review_status",
    "derived_by",
    "risk_direction",
    "applicability",
    "notes",
}


def _as_list(value: Any) -> list[str]:
    return [str(x).strip() for x in split_multi(value) if str(x).strip()]


def _format_descriptor_from_record(record: dict[str, Any]) -> dict[str, Any]:
    data = dict(record.get("format") or {})
    for source_key, target_key in _FORMAT_IDENTIFIER_FIELDS.items():
        if source_key in record and target_key not in data:
            data[target_key] = record[source_key]
    if "format_name" in record and "name" not in data:
        data["name"] = record["format_name"]
    return data


def _format_identity(format_data: dict[str, Any]) -> tuple[str, str]:
    for field in ("puids", "loc_ids", "nara_ids", "mime_types", "extensions"):
        values = _as_list(format_data.get(field))
        if values:
            return field[:-1], values[0]
    name = str(format_data.get("name") or "").strip()
    return "name", name or "unnamed"


def _record_id(source_id: str, institution_id: str, format_data: dict[str, Any]) -> str:
    kind, value = _format_identity(format_data)
    return f"{source_id}:{institution_id}:{kind}:{value}"


def _claim_id(source_id: str, institution_id: str, source_record_id: str, criterion_id: str, sequence: int) -> str:
    return "|".join([source_id, institution_id, source_record_id, criterion_id or f"claim-{sequence}", str(sequence)])


def _claim_from_raw(
    raw_claim: dict[str, Any],
    *,
    source_id: str,
    institution_id: str,
    institution_name: str,
    source_record_id: str,
    sequence: int,
    package: dict[str, Any],
) -> dict[str, Any]:
    claim = {k: v for k, v in raw_claim.items() if v not in (None, "")}
    criterion_id = str(claim.get("criterion_id") or "").strip()
    claim.setdefault("institution_id", institution_id)
    claim.setdefault("institution_name", institution_name)
    claim.setdefault("derived_by", "human")
    claim.setdefault("review_status", "approved")
    claim.setdefault("evidence_owner", package.get("default_evidence_owner") or "QNL Digital Curation, Preservation, and Access")
    claim.setdefault("source", package.get("default_source") or "QNL institutional preservation evidence")
    claim.setdefault("schema_version", package.get("schema_version"))
    claim.setdefault("criterion_set", package.get("criterion_set"))
    claim.setdefault("source_record_id", source_record_id)
    claim.setdefault("claim_sequence", sequence)
    claim.setdefault("claim_id", _claim_id(source_id, institution_id, source_record_id, criterion_id, sequence))
    return claim


def _records_from_json_package(package: dict[str, Any], *, source_id: str, type_name: str) -> list[RawFormatRecord]:
    institution_id = str(package.get("institution_id") or "qnl")
    institution_name = str(package.get("institution_name") or "Qatar National Library")
    rows: list[RawFormatRecord] = []
    for record in package.get("records", []):
        format_data = _format_descriptor_from_record(record)
        source_record_id = str(record.get("source_record_id") or _record_id(source_id, institution_id, format_data))
        claims = [
            _claim_from_raw(
                dict(claim),
                source_id=source_id,
                institution_id=institution_id,
                institution_name=institution_name,
                source_record_id=source_record_id,
                sequence=idx,
                package=package,
            )
            for idx, claim in enumerate(record.get("claims", []), start=1)
        ]
        rows.append(RawFormatRecord(
            source_id=source_id,
            source_type=type_name,
            source_record_id=source_record_id,
            name=format_data.get("name") or record.get("name") or record.get("format_name"),
            category=format_data.get("category") or record.get("category"),
            description=record.get("description"),
            extensions=_as_list(format_data.get("extensions")),
            mime_types=_as_list(format_data.get("mime_types")),
            puids=_as_list(format_data.get("puids")),
            loc_ids=_as_list(format_data.get("loc_ids")),
            nara_ids=_as_list(format_data.get("nara_ids")),
            urls=record.get("urls", {}) or {},
            institution_evidence=claims,
            evidence=[{
                "type": "qnl_institution_format_evidence",
                "institution_id": institution_id,
                "source_record_id": source_record_id,
                "claim_count": len(claims),
            }],
            raw=record,
        ))
    return rows


def _records_from_csv_text(text: str, *, source_id: str, type_name: str, package_defaults: dict[str, Any]) -> list[RawFormatRecord]:
    institution_id = str(package_defaults.get("institution_id") or "qnl")
    institution_name = str(package_defaults.get("institution_name") or "Qatar National Library")
    grouped: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {"format": {}, "claims": []})
    reader = csv.DictReader(text.splitlines())
    for row_number, row in enumerate(reader, start=2):
        format_data = _format_descriptor_from_record(row)
        key = _format_identity(format_data)
        grouped[key]["format"].update({k: v for k, v in format_data.items() if v not in (None, "")})
        grouped[key]["source_rows"] = grouped[key].get("source_rows", []) + [row_number]
        claim = {k: row.get(k) for k in _CLAIM_FIELDS if row.get(k) not in (None, "")}
        claim["source_row"] = row_number
        grouped[key]["claims"].append(claim)

    package = dict(package_defaults)
    package.setdefault("institution_id", institution_id)
    package.setdefault("institution_name", institution_name)
    rows: list[dict[str, Any]] = []
    for item in grouped.values():
        rows.append({"format": item["format"], "claims": item["claims"], "raw_source_rows": item.get("source_rows", [])})
    return _records_from_json_package(package | {"records": rows}, source_id=source_id, type_name=type_name)


class QnlInstitutionFormatEvidenceAdapter(SourceAdapter):
    """Read QNL criterion-level evidence about preservation risks by format.

    This adapter imports local QNL evidence, not policy decisions. It gives the
    future preservation-risk analysis layer QNL-specific context for questions
    about software availability, staff expertise, workflow support, scale/cost,
    and other sustainability criteria.
    """

    type_name = "qnl_institution_format_evidence"

    inbox_hint = (
        "Drop institution format-evidence CSV or JSON package file(s) here. "
        "Record when the evidence was compiled in manifest.json as "
        "{\"published_at\": \"YYYY-MM-DD\"}."
    )

    def network_acquire(self) -> list[SourceSnapshot]:
        uris: list[str] = []
        for item in self.config.get("local_files", []):
            uris.append(str(item.get("path") if isinstance(item, dict) else item))
        uris.extend(str(x) for x in self.config.get("uris", []))
        path = self.config.get("path")
        if path:
            uris.append(str(path))
        snapshots: list[SourceSnapshot] = []
        for uri in uris:
            suffix = Path(uri.split("?")[0]).suffix or ".json"
            snapshots.append(self.acquire_uri_snapshot(
                uri,
                suffix=suffix,
                note="retrieval_mode=qnl_institution_format_evidence",
                metadata={
                    "institution_id": self.config.get("institution_id", "qnl"),
                    "source_location": "qnl_institution_format_evidence",
                },
            ))
        return snapshots

    def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
        rows: list[RawFormatRecord] = []
        defaults = {
            "institution_id": self.config.get("institution_id", "qnl"),
            "institution_name": self.config.get("institution_name", "Qatar National Library"),
            "default_evidence_owner": self.config.get("default_evidence_owner"),
            "default_source": self.config.get("default_source"),
            "criterion_set": self.config.get("criterion_set"),
        }
        for snap in snapshots:
            path = Path(snap.local_path)
            if path.suffix.lower() == ".csv":
                rows.extend(_records_from_csv_text(path.read_text(encoding="utf-8-sig"), source_id=self.source_id, type_name=self.type_name, package_defaults=defaults))
                continue
            package = json.loads(path.read_text(encoding="utf-8"))
            merged_package = defaults | package
            rows.extend(_records_from_json_package(merged_package, source_id=self.source_id, type_name=self.type_name))
        return rows
