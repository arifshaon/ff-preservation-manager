from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Any
import zipfile
import xml.etree.ElementTree as ET

from registry_builder.criteria import CriteriaVocabulary
from registry_builder.criterion_mapping import build_criterion_claims, load_mappings
from registry_builder.storage.base import RegistryStore


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _string_values(value: Any) -> list[str]:
    return [str(item).strip() for item in _as_list(value) if str(item).strip()]


def _flatten_fields(value: Any, *, prefix: str = "", limit: int = 3) -> set[str]:
    if limit < 0:
        return set()
    out: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            out.add(path)
            out.update(_flatten_fields(item, prefix=path, limit=limit - 1))
    elif isinstance(value, list):
        for item in value[:5]:
            out.update(_flatten_fields(item, prefix=prefix, limit=limit - 1))
    return out


def _add_distinct(counter: dict[str, Counter], field: str, value: Any) -> None:
    if value in (None, "", [], {}):
        return
    if isinstance(value, (dict, list)):
        return
    counter[field][str(value)] += 1


def _walk_values(value: Any, *, prefix: str = "", counter: dict[str, Counter], limit: int = 3) -> None:
    if limit < 0:
        return
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            _add_distinct(counter, path, item)
            _walk_values(item, prefix=path, counter=counter, limit=limit - 1)
    elif isinstance(value, list):
        for item in value[:100]:
            _walk_values(item, prefix=prefix, counter=counter, limit=limit - 1)


def _source_inventory(source_records: list[dict[str, Any]], *, source: str | None = None) -> dict[str, Any]:
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in source_records:
        source_key = str(record.get("source_id") or record.get("source_type") or "unknown")
        if source and source not in {source_key, str(record.get("source_type") or "")}:
            continue
        by_source[source_key].append(record)

    inventory: dict[str, Any] = {}
    for source_key, records in sorted(by_source.items()):
        field_paths: set[str] = set()
        distinct: dict[str, Counter] = defaultdict(Counter)
        source_types = sorted({str(record.get("source_type") or "") for record in records if record.get("source_type")})
        for record in records:
            for section in ("native_fields", "raw", "evidence", "institution_evidence", "hazard", "readiness", "trend"):
                value = record.get(section)
                if value is None:
                    continue
                field_paths.update(_flatten_fields(value, prefix=section))
                _walk_values(value, prefix=section, counter=distinct)
        inventory[source_key] = {
            "source_types": source_types,
            "record_count": len(records),
            "field_paths_sample": sorted(field_paths)[:200],
            "distinct_values": {
                field: dict(values.most_common(25))
                for field, values in sorted(distinct.items())
                if values
            },
        }
    return inventory


def _criterion_claim_inventory(store: RegistryStore) -> dict[str, Any]:
    all_claims = store.query("criterion_claims")
    existing = [claim for claim in all_claims if claim.get("current", True) is not False]
    by_criterion = Counter(str(claim.get("criterion_id") or "unknown") for claim in existing)
    by_source = Counter(str(claim.get("source_id") or claim.get("source_type") or "unknown") for claim in existing)
    return {
        "existing_claims": len(existing),
        "inactive_claims": len(all_claims) - len(existing),
        "by_criterion": dict(sorted(by_criterion.items())),
        "by_source": dict(sorted(by_source.items())),
    }


def _qnl_inventory(canonical_formats: list[dict[str, Any]]) -> dict[str, Any]:
    claims = []
    for record in canonical_formats:
        claims.extend(record.get("institution_evidence_claims") or [])
    by_institution = Counter(str(claim.get("institution_id") or "unknown") for claim in claims)
    by_criterion = Counter(str(claim.get("criterion_id") or "unknown") for claim in claims)
    return {
        "institution_evidence_claims": len(claims),
        "by_institution": dict(sorted(by_institution.items())),
        "by_criterion": dict(sorted(by_criterion.items())),
        "sample_claims": claims[:10],
    }


def _excluded_fields_from_mappings(mappings: list[dict[str, Any]]) -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = {}
    for mapping in mappings:
        source = str(mapping.get("source_id") or mapping.get("source_type") or "unknown")
        excluded = []
        for item in mapping.get("excluded_from_criteria") or []:
            if isinstance(item, dict):
                excluded.append({"field": str(item.get("field") or ""), "reason": str(item.get("reason") or "")})
            else:
                excluded.append({"field": str(item), "reason": "excluded by mapping config"})
        if excluded:
            out[source] = excluded
    return out


def _puid_alias(value: str) -> str | None:
    normalized = value.strip().lower().replace("/", "-")
    if not normalized:
        return None
    if normalized.startswith("puid-"):
        return normalized
    return f"puid-{normalized}"


def _loc_alias(value: str) -> str | None:
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized.startswith("loc-"):
        return normalized
    return f"loc-{normalized}"


def _nara_alias(value: str) -> str | None:
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized.startswith("nara-"):
        return normalized
    return f"nara-{normalized}"


def _identifier_values(format_doc: dict[str, Any], kind: str) -> list[str]:
    values: list[str] = []
    direct_key = {"puid": "puids", "loc": "loc_ids", "nara": "nara_ids"}.get(kind)
    if direct_key:
        values.extend(_string_values(format_doc.get(direct_key)))
    identifiers = format_doc.get("identifiers") or {}
    if isinstance(identifiers, dict):
        values.extend(_string_values(identifiers.get(kind)))
    elif isinstance(identifiers, list):
        for item in identifiers:
            if not isinstance(item, dict):
                continue
            if str(item.get("kind") or item.get("type") or "") == kind:
                values.extend(_string_values(item.get("value")))
    out: list[str] = []
    for value in values:
        if value not in out:
            out.append(value)
    return out


def _strong_aliases(format_doc: dict[str, Any]) -> set[str]:
    aliases: set[str] = set()
    for field in ("canonical_id", "format_id", "id"):
        value = format_doc.get(field)
        if value is not None and str(value).strip():
            aliases.add(str(value).strip())
    for value in _identifier_values(format_doc, "puid"):
        alias = _puid_alias(value)
        if alias:
            aliases.add(alias)
    for value in _identifier_values(format_doc, "loc"):
        alias = _loc_alias(value)
        if alias:
            aliases.add(alias)
    for value in _identifier_values(format_doc, "nara"):
        alias = _nara_alias(value)
        if alias:
            aliases.add(alias)
    return aliases


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, item: str) -> str:
        self.parent.setdefault(item, item)
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def _alias_group_index(canonical_formats: list[dict[str, Any]]) -> dict[str, str]:
    uf = _UnionFind()
    for record in canonical_formats:
        aliases = sorted(_strong_aliases(record))
        if not aliases:
            continue
        first = aliases[0]
        uf.find(first)
        for alias in aliases[1:]:
            uf.union(first, alias)
    grouped: dict[str, set[str]] = defaultdict(set)
    for alias in list(uf.parent):
        grouped[uf.find(alias)].add(alias)
    representatives: dict[str, str] = {}
    for aliases in grouped.values():
        fmt_candidates = sorted(alias for alias in aliases if alias.startswith("fmt-"))
        representative = fmt_candidates[0] if fmt_candidates else sorted(aliases)[0]
        for alias in aliases:
            representatives[alias] = representative
    return representatives


def _claim_format_group(claim: dict[str, Any], alias_index: dict[str, str]) -> str:
    canonical_id = str(claim.get("canonical_id") or claim.get("format_id") or "")
    return alias_index.get(canonical_id, canonical_id)


def _claim_source_id(claim: dict[str, Any]) -> str:
    return str(claim.get("source_id") or claim.get("source_type") or "")


def _is_institution_scoped_claim(claim: dict[str, Any]) -> bool:
    if claim.get("institution_id"):
        return True
    return str(claim.get("source_independence") or "").lower() == "institution_scoped"


def _alias_aware_projected_coverage(
    claims: list[dict[str, Any]],
    canonical_formats: list[dict[str, Any]],
) -> dict[str, Any]:
    alias_index = _alias_group_index(canonical_formats)
    by_criterion: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in claims:
        by_criterion[str(claim["criterion_id"])].append(claim)
    projection: dict[str, Any] = {}
    for criterion_id, items in sorted(by_criterion.items()):
        formats = {
            _claim_format_group(item, alias_index)
            for item in items
            if item.get("canonical_id") or item.get("format_id")
        }
        explicit_formats = {
            _claim_format_group(item, alias_index)
            for item in items
            if (item.get("canonical_id") or item.get("format_id")) and item.get("directness") == "explicit"
        }
        sources_by_format: dict[str, set[str]] = defaultdict(set)
        for item in items:
            if _is_institution_scoped_claim(item):
                continue
            format_group = _claim_format_group(item, alias_index)
            source = _claim_source_id(item)
            if format_group and source:
                sources_by_format[format_group].add(source)
        projection[criterion_id] = {
            "formats_with_any_claim": len(formats),
            "formats_with_explicit_claim": len(explicit_formats),
            "formats_with_2plus_independent_sources": sum(1 for sources in sources_by_format.values() if len(sources) >= 2),
            "contributing_sources": sorted({_claim_source_id(item) for item in items if _claim_source_id(item)}),
            "identity_normalization": "strong_identifier_aliases",
        }
    return projection


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1].lower() if "}" in tag else tag.lower()


def _loc_raw_xml_probe(store: RegistryStore) -> dict[str, Any]:
    snapshots = [
        snapshot for snapshot in store.query("source_snapshots")
        if snapshot.get("source_type") == "loc_fdd_xml" or snapshot.get("source_id") == "loc_fdd_xml"
    ]
    factor_terms = {
        "disclosure",
        "adoption",
        "transparency",
        "self-documentation",
        "self documentation",
        "external dependencies",
        "impact of patents",
        "technical protection",
    }
    found_terms: Counter[str] = Counter()
    files_checked = 0
    missing_paths = 0
    for snapshot in snapshots[:5]:
        local_path = snapshot.get("local_path")
        if not local_path or not Path(local_path).exists():
            missing_paths += 1
            continue
        path = Path(local_path)
        payloads: list[tuple[str, bytes]] = []
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as zf:
                names = [name for name in sorted(zf.namelist()) if name.lower().endswith(".xml")]
                for name in names[:200]:
                    payloads.append((name, zf.read(name)))
        elif path.suffix.lower() == ".xml":
            payloads.append((str(path), path.read_bytes()))
        for _name, data in payloads:
            files_checked += 1
            try:
                root = ET.fromstring(data)
            except ET.ParseError:
                continue
            for elem in root.iter():
                text = " ".join(x for x in [_local_name(elem.tag), elem.text or ""] if x).lower()
                for term in factor_terms:
                    if term in text:
                        found_terms[term] += 1
    status = "not_checked"
    if files_checked:
        status = "present_in_raw_xml" if found_terms else "not_found_in_sampled_raw_xml"
    elif snapshots:
        status = "source_snapshots_found_but_local_paths_unavailable"
    return {
        "status": status,
        "snapshots_seen": len(snapshots),
        "missing_local_paths": missing_paths,
        "raw_xml_files_checked": files_checked,
        "factor_terms_found": dict(sorted(found_terms.items())),
        "adapter_gap": (
            "LOC sustainability factors are checked from available snapshots so audit can reveal whether mapping coverage is blocked by acquisition, extraction, or mapping."
        ),
    }


def run_criterion_evidence_audit(
    store: RegistryStore,
    *,
    criteria: CriteriaVocabulary | None = None,
    mappings_path: str | Path | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    canonical_formats = store.get_current_registry_view()
    source_records = store.query("source_records")
    mappings = load_mappings(mappings_path) if mappings_path else []
    report: dict[str, Any] = {
        "status": "ok",
        "canonical_formats": len(canonical_formats),
        "source_records": len(source_records),
        "source_field_inventory": _source_inventory(source_records, source=source),
        "qnl_institution_evidence": _qnl_inventory(canonical_formats),
        "existing_criterion_claims": _criterion_claim_inventory(store),
        "excluded_fields": _excluded_fields_from_mappings(mappings),
        "loc_raw_xml_probe": _loc_raw_xml_probe(store),
    }
    if criteria and mappings:
        projected_claims = build_criterion_claims(
            canonical_formats,
            source_records,
            mappings,
            criteria,
            include_drafts=True,
        )
        accepted_claims = build_criterion_claims(
            canonical_formats,
            source_records,
            mappings,
            criteria,
            include_drafts=False,
        )
        report["projected_coverage"] = _alias_aware_projected_coverage(projected_claims, canonical_formats)
        report["accepted_mapping_coverage"] = _alias_aware_projected_coverage(accepted_claims, canonical_formats)
        report["coverage_identity_normalization"] = "strong_identifier_aliases"
        report["projected_claims"] = len(projected_claims)
        report["accepted_claims"] = len(accepted_claims)
        report["projected_sample_claims"] = projected_claims[:10]
    return report
