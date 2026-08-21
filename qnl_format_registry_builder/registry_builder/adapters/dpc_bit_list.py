from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any

import yaml

from registry_builder.adapters.base import SourceAdapter
from registry_builder.models import RawFormatRecord, SourceSnapshot

DEFAULT_DPC_GITHUB_REF = "main"
DEFAULT_DPC_ARCHIVE_URL = (
    "https://github.com/Digital-Preservation-Coalition/bit-list/"
    "archive/refs/heads/main.zip"
)
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
    return metadata, parts[2].strip()


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


class DpcBitListAdapter(SourceAdapter):
    """Acquire the DPC Global Bit List source repository.

    The DPC repository is the primary machine-readable source. The adapter is
    deliberately acquisition-only for the registry pipeline until explicit
    DPC-entry-to-format/family mappings are reviewed. `extract_entries()` exposes
    structured Bit List entries for review and mapping work; `extract()` returns
    no RawFormatRecord objects so broad Bit List concepts cannot accidentally
    become canonical file formats.
    """

    type_name = "dpc_bit_list"

    def _edition(self) -> str:
        return str(self.config.get("edition") or "2025")

    def _github_ref(self) -> str:
        return str(self.config.get("github_ref") or DEFAULT_DPC_GITHUB_REF)

    def _archive_url(self) -> str:
        configured = self.config.get("archive_url")
        if configured:
            return str(configured)
        ref = self._github_ref()
        if ref == "main":
            return DEFAULT_DPC_ARCHIVE_URL
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
            "acquisition_only": True,
        }
        if local_archive:
            return [
                self.acquire_file_snapshot(
                    str(local_archive),
                    suffix=".zip",
                    note="retrieval_mode=local_archive; acquisition_only=true",
                    metadata=metadata,
                )
            ]

        archive_url = self._archive_url()
        return [
            self.acquire_uri_snapshot(
                archive_url,
                suffix=".zip",
                note="retrieval_mode=github_archive; acquisition_only=true",
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
        # Preserve source acquisition without projecting broad DPC entries into
        # canonical format identity. A reviewed mapping layer will consume the
        # structured entries exposed by extract_entries().
        return []
