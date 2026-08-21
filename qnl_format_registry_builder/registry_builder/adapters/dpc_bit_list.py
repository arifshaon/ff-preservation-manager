from __future__ import annotations

from datetime import date, datetime
import re
import zipfile
from pathlib import Path
from typing import Any

import yaml

from registry_builder.adapters.base import SourceAdapter
from registry_builder.models import RawFormatRecord, SourceSnapshot

DPC_2025_COMMIT = "3ad3fef626ea7c128ef8c323d92227e5cae2efc8"
DEFAULT_DPC_GITHUB_REF = DPC_2025_COMMIT
_DPC_ENTRY_RE = re.compile(r"(?:^|/)content/entries/([^/]+)/index\.en\.md$")

_DPC_SEMANTIC_LEVELS = {
    "lower-risk": "minimal",
    "lower risk": "minimal",
    "vulnerable": "moderate",
    "endangered": "high",
    "critically-endangered": "critical",
    "critically endangered": "critical",
    "practically-extinct": "critical",
    "practically extinct": "critical",
}


def _json_safe(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def _classification_label(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text.replace("-", " ").title()


def _semantic_level(value: Any) -> str | None:
    text = str(value or "").strip().lower().replace("_", "-")
    return _DPC_SEMANTIC_LEVELS.get(text) or _DPC_SEMANTIC_LEVELS.get(text.replace("-", " "))


def _front_matter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        raise ValueError("DPC Bit List entry does not start with YAML front matter")
    parts = text.split("---", 2)
    if len(parts) != 3:
        raise ValueError("DPC Bit List entry has malformed YAML front matter")
    metadata = yaml.safe_load(parts[1]) or {}
    if not isinstance(metadata, dict):
        raise ValueError("DPC Bit List front matter must decode to an object")
    return _json_safe(metadata), parts[2].strip()


def _entry_member_slug(member: str) -> str | None:
    match = _DPC_ENTRY_RE.search(member.replace("\\", "/"))
    return match.group(1) if match else None


def _split_semicolon_text(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return [item.strip() for item in text.split(";") if item.strip()]


def _entry_scope(categories: list[str]) -> str:
    normalized = {str(value).strip().lower() for value in categories}
    if "formats" in normalized:
        return "format_group"
    return "contextual"


def _entry_from_markdown(
    *,
    snapshot: SourceSnapshot,
    member: str,
    text: str,
    edition: str,
) -> dict[str, Any]:
    metadata, review_body = _front_matter(text)
    slug = _entry_member_slug(member)
    if not slug:
        raise ValueError(f"Not a DPC Bit List English entry path: {member}")

    categories = [str(value).strip() for value in (metadata.get("categories") or []) if str(value).strip()]
    threats = [str(value).strip() for value in (metadata.get("threats") or []) if str(value).strip()]
    classification = str(metadata.get("classification") or "").strip().lower() or None
    native_label = _classification_label(classification)
    semantic_level = _semantic_level(classification)
    source_record_id = str(metadata.get("id") or slug)
    source_url = f"https://bit-list.dpconline.org/entries/{slug}/"

    risk_assessment: dict[str, Any] = {
        "assessment_role": "external",
        "source_id": snapshot.source_id,
        "source_type": snapshot.source_type,
        "source_record_id": source_record_id,
        "source_label": f"DPC Global Bit List {edition}",
        "native_label": native_label,
        "native_scale": "dpc_global_bit_list_classification",
        "semantic_level": semantic_level,
        "scope_type": _entry_scope(categories),
        "scope_name": metadata.get("title") or slug,
        "scope_basis": "dpc_entry_scope_unreconciled",
        "native_assessment": {
            "classification": classification,
            "imminence": metadata.get("imminence"),
            "effort": metadata.get("effort"),
            "trends": metadata.get("trends") or [],
            "categories": categories,
            "threats": threats,
            "hazards": metadata.get("hazards"),
            "mitigations": metadata.get("mitigations"),
            "year_added": metadata.get("year-added"),
            "published": metadata.get("published"),
            "last_updated": metadata.get("last-updated"),
        },
    }
    risk_assessment = {key: value for key, value in risk_assessment.items() if value is not None}

    return {
        "source_record_id": source_record_id,
        "slug": slug,
        "title": metadata.get("title"),
        "description": metadata.get("description"),
        "examples": metadata.get("examples"),
        "categories": categories,
        "threats": threats,
        "classification": classification,
        "classification_label": native_label,
        "semantic_level": semantic_level,
        "imminence": metadata.get("imminence"),
        "effort": metadata.get("effort"),
        "trends": metadata.get("trends") or [],
        "hazards": _split_semicolon_text(metadata.get("hazards")),
        "mitigations": _split_semicolon_text(metadata.get("mitigations")),
        "year_added": metadata.get("year-added"),
        "published": metadata.get("published"),
        "last_updated": metadata.get("last-updated"),
        "aliases": metadata.get("aliases") or [],
        "comments": metadata.get("comments"),
        "case_studies": metadata.get("case-studies") or [],
        "review_body": review_body,
        "source_url": source_url,
        "source_file": member,
        "snapshot_sha256": snapshot.sha256,
        "edition": edition,
        "risk_assessment": risk_assessment,
        "raw_front_matter": metadata,
    }


def _entry_to_evidence_record(entry: dict[str, Any], *, source_id: str, source_type: str) -> RawFormatRecord:
    categories = entry.get("categories") or []
    return RawFormatRecord(
        source_id=source_id,
        source_type=source_type,
        source_record_id=str(entry.get("source_record_id") or entry.get("slug") or ""),
        record_role="evidence_only",
        name=entry.get("title"),
        category="; ".join(str(value) for value in categories) or None,
        description=entry.get("description"),
        urls={"dpc_bit_list": entry.get("source_url")} if entry.get("source_url") else {},
        risk_assessments=[dict(entry["risk_assessment"])] if entry.get("risk_assessment") else [],
        evidence=[{
            "type": "dpc_bit_list_entry",
            "edition": entry.get("edition"),
            "slug": entry.get("slug"),
            "source_file": entry.get("source_file"),
            "snapshot_sha256": entry.get("snapshot_sha256"),
        }],
        native_fields={
            "slug": entry.get("slug"),
            "categories": entry.get("categories") or [],
            "threats": entry.get("threats") or [],
            "classification": entry.get("classification"),
            "imminence": entry.get("imminence"),
            "effort": entry.get("effort"),
            "trends": entry.get("trends") or [],
            "hazards": entry.get("hazards") or [],
            "mitigations": entry.get("mitigations") or [],
            "examples": entry.get("examples"),
            "year_added": entry.get("year_added"),
            "published": entry.get("published"),
            "last_updated": entry.get("last_updated"),
        },
        raw={
            "snapshot_sha256": entry.get("snapshot_sha256"),
            "source_file": entry.get("source_file"),
            "raw_front_matter": entry.get("raw_front_matter") or {},
            "review_body": entry.get("review_body"),
            "comments": entry.get("comments"),
            "case_studies": entry.get("case_studies") or [],
        },
    )


class DpcBitListAdapter(SourceAdapter):
    """Acquire DPC Bit List entries as evidence-only source records.

    DPC entries are never canonical identity records. They are persisted as
    `evidence_only` records and may contribute source-native risk assessments
    only through reviewed external-risk mappings.
    """

    type_name = "dpc_bit_list"

    def _edition(self) -> str:
        return str(self.config.get("edition") or "2025")

    def _github_ref(self) -> str:
        configured = self.config.get("github_ref")
        if configured:
            return str(configured)
        if self._edition() == "2025":
            return DPC_2025_COMMIT
        return "main"

    def _archive_url(self) -> str:
        configured = self.config.get("archive_url")
        if configured:
            return str(configured)
        ref = self._github_ref()
        return (
            "https://github.com/Digital-Preservation-Coalition/bit-list/"
            f"archive/{ref}.zip"
        )

    def acquire(self) -> list[SourceSnapshot]:
        local_archive = self.config.get("local_archive") or self.config.get("local_file")
        metadata = {
            "source_location": "dpc_bit_list_github_archive" if not local_archive else "local_file",
            "snapshot_policy": "cache",
            "snapshot_retained": True,
            "github_ref": self._github_ref(),
            "edition": self._edition(),
            "identity_projection": False,
        }
        if local_archive:
            return [
                self.acquire_file_snapshot(
                    str(local_archive),
                    suffix=".zip",
                    note="retrieval_mode=local_archive; identity_projection=false",
                    metadata=metadata,
                )
            ]

        archive_url = self._archive_url()
        return [
            self.acquire_uri_snapshot(
                archive_url,
                suffix=".zip",
                note="retrieval_mode=github_archive; identity_projection=false",
                metadata=metadata,
            )
        ]

    def extract_entries(self, snapshots: list[SourceSnapshot]) -> list[dict[str, Any]]:
        edition = self._edition()
        entries: list[dict[str, Any]] = []
        for snapshot in snapshots:
            with zipfile.ZipFile(Path(snapshot.local_path)) as archive:
                members = [
                    member
                    for member in sorted(archive.namelist())
                    if _entry_member_slug(member)
                ]
                for member in members:
                    text = archive.read(member).decode("utf-8")
                    entries.append(
                        _entry_from_markdown(
                            snapshot=snapshot,
                            member=member,
                            text=text,
                            edition=edition,
                        )
                    )
        return entries

    def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
        return [
            _entry_to_evidence_record(entry, source_id=self.source_id, source_type=self.type_name)
            for entry in self.extract_entries(snapshots)
        ]
