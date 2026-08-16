from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
from pathlib import Path
import re
from typing import Any, Callable

from registry_builder.criteria import CriteriaError, CriteriaVocabulary
from registry_builder.models import utc_now_iso
from registry_builder.storage import create_store
from registry_builder.storage.base import RegistryStore

_ALLOWED_DIRECTNESS = {"explicit", "derived", "inferred"}
_ALLOWED_COVERS = {"full", "partial"}
_ALLOWED_CLAIM_REVIEW_STATUSES = {"unreviewed", "approved", "rejected", "superseded"}
_ALLOWED_TRANSFORMS = {"days_since_date"}
_TEXT_RULE_MATCH_KEYS = {"equals_any", "contains_any", "contains_all", "not_contains_any"}
_HAZARD_CONCLUSION_TOKENS = (
    "risk level",
    "numeric risk rating",
    "total numeric risk rating",
    "nara total",
    "overall risk",
    "risk band",
    "hazard band",
    "rating",
    "band",
)
_ACTION_DECISION_TOKENS = (
    "preservation action",
    "preservation plan",
    "preferred processing",
    "preferred tool",
    "transformation tool",
    "action",
    "tooling",
)
ProgressCallback = Callable[[dict[str, Any]], None]


class MappingError(ValueError):
    """Raised when criterion mapping configuration is invalid."""


def _load_json(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise MappingError(f"Mapping file must contain a JSON object: {path}")
    return data


def _load_storage_config(path: str | Path) -> dict[str, Any]:
    data = _load_json(path)
    storage = data.get("storage") if isinstance(data.get("storage"), dict) else data
    return dict(storage)


def load_mapping(path: str | Path) -> dict[str, Any]:
    return _load_json(path)


def load_mappings(path: str | Path) -> list[dict[str, Any]]:
    root = Path(path)
    if root.is_file():
        return [load_mapping(root)]
    return [load_mapping(item) for item in sorted(root.glob("*.json"))]


def create_store_from_storage_config(path: str | Path) -> RegistryStore:
    return create_store(_load_storage_config(path))


def _normalise_text(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", " ").replace("-", " ")


def _normalise_match_text(value: Any) -> str:
    if isinstance(value, list):
        value = " ".join(str(v) for v in value)
    text = re.sub(r"\s+", " ", str(value or "")).strip().lower()
    return text.replace("_", " ").replace("-", " ")


def _path_text(mapping: dict[str, Any]) -> str:
    return _normalise_text(mapping.get("from_field") or mapping.get("source_field") or "")


def _contains_guard_token(text: Any, tokens: tuple[str, ...]) -> bool:
    """Return true when a guard token occurs as a word/phrase.

    Guard tokens intentionally catch fields such as "Risk Level" and "Numeric
    Risk Rating". They must not catch unrelated words that merely contain the
    same letters, for example "operating" containing "rating".
    """
    normalized = _normalise_text(text)
    for token in tokens:
        normalized_token = _normalise_text(token)
        pattern = rf"(?<![a-z0-9]){re.escape(normalized_token)}(?![a-z0-9])"
        if re.search(pattern, normalized):
            return True
    return False


def _emit_progress(progress: ProgressCallback | None, event: str, **payload: Any) -> None:
    if progress is not None:
        progress({"event": event, **payload})


def _mapping_rule_id(source: dict[str, Any], rule: dict[str, Any]) -> str:
    if rule.get("id"):
        return str(rule["id"])
    source_name = source.get("source_id") or source.get("source_type") or "source"
    field = str(rule.get("from_field") or "field").replace(".", "_").replace(" ", "_")
    criterion = str(rule.get("criterion") or "criterion").replace(".", "_")
    return f"{source_name}.{criterion}.{field}.{source.get('criteria_version', 'v1')}"


def _claim_review_status(mapping: dict[str, Any], rule: dict[str, Any] | None = None) -> str:
    """Return the claim review status declared by mapping config.

    A mapping file must declare a root-level claim_review_status. Individual
    rules may override it, but the code must not silently invent a default.
    """
    status = (rule or {}).get("claim_review_status") or mapping.get("claim_review_status")
    if not status:
        source_label = mapping.get("source_id") or mapping.get("source_type") or "<unknown source>"
        raise MappingError(f"{source_label}: claim_review_status is required")
    return str(status)


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        normalized = text.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized)
        except ValueError:
            dt = None
        if dt is None:
            for fmt in ("%d %b %Y", "%d %B %Y", "%Y-%m-%d", "%Y/%m/%d"):
                try:
                    dt = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    pass
        if dt is None:
            try:
                dt = parsedate_to_datetime(text)
            except (TypeError, ValueError, IndexError, OverflowError):
                return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _days_since_date(source_value: Any, observed_at: str | None) -> int | None:
    source_dt = _parse_datetime(source_value)
    observed_dt = _parse_datetime(observed_at) or datetime.now(timezone.utc)
    if source_dt is None:
        return None
    return max(0, (observed_dt.date() - source_dt.date()).days)


def _matches_text_rule(source_value: Any, text_rule: dict[str, Any]) -> bool:
    haystack = _normalise_match_text(source_value)
    equals_any = text_rule.get("equals_any")
    if equals_any:
        normalized_values = {_normalise_match_text(value).strip(". ") for value in equals_any}
        if haystack.strip(". ") not in normalized_values:
            return False
    contains_all = text_rule.get("contains_all")
    if contains_all and not all(_normalise_match_text(pattern) in haystack for pattern in contains_all):
        return False
    contains_any = text_rule.get("contains_any")
    if contains_any and not any(_normalise_match_text(pattern) in haystack for pattern in contains_any):
        return False
    not_contains_any = text_rule.get("not_contains_any")
    if not_contains_any and any(_normalise_match_text(pattern) in haystack for pattern in not_contains_any):
        return False
    return bool(equals_any or contains_all or contains_any)


def _text_rule_value(rule: dict[str, Any], source_value: Any) -> Any | None:
    for text_rule in rule.get("text_rules") or []:
        if _matches_text_rule(source_value, text_rule):
            return text_rule.get("value")
    return None


def validate_mapping(mapping: dict[str, Any], criteria: CriteriaVocabulary) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    source_label = mapping.get("source_id") or mapping.get("source_type") or "<unknown source>"
    if not mapping.get("source_id") and not mapping.get("source_type"):
        errors.append("Mapping must declare source_id or source_type")
    if not mapping.get("mapping_version"):
        errors.append(f"{source_label}: mapping_version is required")
    claim_review_status = str(mapping.get("claim_review_status") or "")
    if not claim_review_status:
        errors.append(f"{source_label}: claim_review_status is required")
    elif claim_review_status not in _ALLOWED_CLAIM_REVIEW_STATUSES:
        errors.append(
            f"{source_label}: claim_review_status must be one of {sorted(_ALLOWED_CLAIM_REVIEW_STATUSES)}"
        )
    if str(mapping.get("criteria_version") or "") != criteria.criteria_version:
        errors.append(
            f"{source_label}: criteria_version must be {criteria.criteria_version!r}, got {mapping.get('criteria_version')!r}"
        )

    for rule in mapping.get("maps") or []:
        rule_id = _mapping_rule_id(mapping, rule)
        status = str(rule.get("mapping_status") or mapping.get("review_status") or "").lower()
        criterion_id = str(rule.get("criterion") or "")
        rule_claim_review_status = rule.get("claim_review_status")
        if rule_claim_review_status is not None and str(rule_claim_review_status) not in _ALLOWED_CLAIM_REVIEW_STATUSES:
            errors.append(
                f"{rule_id}: claim_review_status must be one of {sorted(_ALLOWED_CLAIM_REVIEW_STATUSES)}"
            )
        transform = rule.get("transform")
        if transform is not None and str(transform) not in _ALLOWED_TRANSFORMS:
            errors.append(f"{rule_id}: transform must be one of {sorted(_ALLOWED_TRANSFORMS)}")
        if not criterion_id:
            errors.append(f"{rule_id}: criterion is required")
            continue
        try:
            criterion = criteria.criterion(criterion_id)
        except CriteriaError as exc:
            errors.append(f"{rule_id}: {exc}")
            continue
        from_field = str(rule.get("from_field") or "")
        if not from_field:
            errors.append(f"{rule_id}: from_field is required")
        if "*" in from_field and "nara" in str(source_label).lower():
            errors.append(f"{rule_id}: NARA rubric mappings must be listed question-by-question, not by wildcard")
        directness = str(rule.get("directness") or "")
        if directness not in _ALLOWED_DIRECTNESS:
            errors.append(f"{rule_id}: directness must be one of {sorted(_ALLOWED_DIRECTNESS)}")
        covers = str(rule.get("covers") or "full")
        if covers not in _ALLOWED_COVERS:
            errors.append(f"{rule_id}: covers must be one of {sorted(_ALLOWED_COVERS)}")
        path_text = _path_text(rule)
        if _contains_guard_token(path_text, _HAZARD_CONCLUSION_TOKENS):
            errors.append(f"{rule_id}: hazard/risk conclusion fields cannot map to criterion_claims")
        if _contains_guard_token(path_text, _ACTION_DECISION_TOKENS) and criterion_id.startswith(("sustainability.", "technical.")):
            errors.append(f"{rule_id}: action/tooling fields cannot map to sustainability or technical criteria")
        if rule.get("when_present") is not None:
            try:
                criteria.validate_value(criterion_id, rule["when_present"])
            except CriteriaError as exc:
                errors.append(f"{rule_id}: {exc}")
            if rule["when_present"] == "public_specification":
                errors.append(f"{rule_id}: field presence cannot assert public_specification")
        for text_rule in rule.get("text_rules") or []:
            if not isinstance(text_rule, dict):
                errors.append(f"{rule_id}: text_rules entries must be objects")
                continue
            if not any(key in text_rule for key in _TEXT_RULE_MATCH_KEYS):
                errors.append(f"{rule_id}: text_rules entries must declare a match condition")
            if "value" not in text_rule:
                errors.append(f"{rule_id}: text_rules entries must declare value")
                continue
            try:
                criteria.validate_value(criterion_id, text_rule["value"])
            except CriteriaError as exc:
                errors.append(f"{rule_id}: text rule value: {exc}")
        for source_value, target_value in (rule.get("values") or {}).items():
            try:
                criteria.validate_value(criterion_id, target_value)
            except CriteriaError as exc:
                errors.append(f"{rule_id}: native value {source_value!r}: {exc}")
        if status in {"accepted", "approved"} and not (rule.get("decided_by") or mapping.get("decided_by")):
            errors.append(f"{rule_id}: accepted mappings must name decided_by")
        if criterion.kind == "temporal" and not (rule.get("transform") or rule.get("when_present") or rule.get("values")):
            warnings.append(f"{rule_id}: temporal criterion mapping should declare transform, values, or when_present")
    return errors, warnings


def validate_mappings(mappings: list[dict[str, Any]], criteria: CriteriaVocabulary) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for mapping in mappings:
        e, w = validate_mapping(mapping, criteria)
        errors.extend(e)
        warnings.extend(w)
    return errors, warnings


def _lookup_key(data: dict[str, Any], key: str) -> tuple[bool, Any]:
    """Return a mapping value using exact, Mongo-safe, or case-insensitive key lookup."""
    if key in data:
        return True, data[key]
    mongo_safe = key.replace(".", "\uff0e")
    if mongo_safe in data:
        return True, data[mongo_safe]
    mongo_unsafe = key.replace("\uff0e", ".")
    if mongo_unsafe in data:
        return True, data[mongo_unsafe]
    lowered = {str(k).lower(): k for k in data.keys()}
    found = lowered.get(key.lower()) or lowered.get(mongo_safe.lower()) or lowered.get(mongo_unsafe.lower())
    if found is not None:
        return True, data[found]
    return False, None


def _get_path(data: Any, path: str | None) -> Any:
    """Resolve a dotted path while allowing source-native keys that contain dots.

    Source rows often contain literal dotted labels, such as NARA question IDs
    (`1.1: ...`) or Mongo-normalized fullwidth dots (`1．1: ...`). At each level,
    the resolver first tries the whole remaining path as an exact dictionary key
    before consuming only the next dotted segment.
    """
    if not path:
        return None
    parts = str(path).split(".")
    current = data
    index = 0
    while index < len(parts):
        if not isinstance(current, dict):
            return None
        remaining = ".".join(parts[index:])
        found, value = _lookup_key(current, remaining)
        if found:
            return value
        found, value = _lookup_key(current, parts[index])
        if not found:
            return None
        current = value
        index += 1
    return current


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _matches_where(item: dict[str, Any], where: dict[str, Any] | None) -> bool:
    if not where:
        return True
    for path, expected in where.items():
        if _get_path(item, path) != expected:
            return False
    return True


def _source_matches(mapping: dict[str, Any], source_ref: dict[str, Any], source_record: dict[str, Any] | None) -> bool:
    expected_id = mapping.get("source_id")
    expected_type = mapping.get("source_type")
    source_id = source_ref.get("source_id") or (source_record or {}).get("source_id")
    source_type = source_ref.get("source_type") or (source_record or {}).get("source_type")
    if expected_id and expected_id != source_id:
        return False
    if expected_type and expected_type != source_type:
        return False
    return True


def _latest_source_record_index(records: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
    for record in records:
        source_id = str(record.get("source_id") or "")
        source_record_id = str(record.get("source_record_id") or "")
        if not source_id or not source_record_id:
            continue
        sort_key = str(record.get("run_id") or "")
        key = (source_id, source_record_id)
        if key not in indexed or sort_key >= indexed[key][0]:
            indexed[key] = (sort_key, record)
    return {key: record for key, (_, record) in indexed.items()}


def _iter_rule_items(canonical: dict[str, Any], source_record: dict[str, Any] | None, rule: dict[str, Any]) -> list[dict[str, Any]]:
    collection = rule.get("from_collection")
    if not collection:
        return [source_record or canonical]
    collection_items = _get_path(canonical, str(collection))
    if collection_items is None and source_record:
        collection_items = _get_path(source_record, str(collection))
    return [item for item in _as_list(collection_items) if isinstance(item, dict)]


def _source_value_from_item(item: dict[str, Any], rule: dict[str, Any]) -> Any:
    value = _get_path(item, str(rule.get("from_field") or ""))
    if value is None and rule.get("alternate_fields"):
        for field in rule.get("alternate_fields") or []:
            value = _get_path(item, str(field))
            if value is not None:
                break
    return value


def _claim_value(rule: dict[str, Any], source_value: Any, *, observed_at: str | None = None) -> Any | None:
    if source_value in (None, "", [], {}):
        return None
    transform = rule.get("transform")
    if transform == "days_since_date":
        return _days_since_date(source_value, observed_at)
    text_value = _text_rule_value(rule, source_value)
    if text_value is not None:
        return text_value
    if rule.get("when_present") is not None:
        return rule.get("when_present")
    values = rule.get("values") or {}
    if source_value in values:
        return values[source_value]
    text = str(source_value)
    if text in values:
        return values[text]
    for key, value in values.items():
        if str(key).strip().lower() == text.strip().lower():
            return value
    return None


def build_criterion_claims(
    canonical_formats: list[dict[str, Any]],
    source_records: list[dict[str, Any]],
    mappings: list[dict[str, Any]],
    criteria: CriteriaVocabulary,
    *,
    include_drafts: bool = False,
    observed_at: str | None = None,
    progress: ProgressCallback | None = None,
    progress_every: int = 500,
) -> list[dict[str, Any]]:
    observed_at = observed_at or utc_now_iso()
    source_index = _latest_source_record_index(source_records)
    claims: list[dict[str, Any]] = []
    total_formats = len(canonical_formats)
    total_mapping_rules = sum(len(mapping.get("maps") or []) for mapping in mappings)
    progress_every = max(1, int(progress_every or 500))
    _emit_progress(
        progress,
        "build_claims_started",
        canonical_formats=total_formats,
        source_records=len(source_records),
        mapping_rules=total_mapping_rules,
        include_drafts=include_drafts,
    )
    for processed, canonical in enumerate(canonical_formats, start=1):
        if canonical.get("current", True) is False:
            continue
        canonical_id = canonical.get("canonical_id") or canonical.get("format_id")
        if not canonical_id:
            continue
        source_refs = list(canonical.get("source_records") or []) or [{}]
        for source_ref in source_refs:
            source_key = (
                str(source_ref.get("source_id") or ""),
                str(source_ref.get("source_record_id") or ""),
            )
            source_record = source_index.get(source_key)
            for mapping in mappings:
                if not _source_matches(mapping, source_ref, source_record):
                    continue
                for rule in mapping.get("maps") or []:
                    status = str(rule.get("mapping_status") or mapping.get("review_status") or "").lower()
                    if not include_drafts and status not in {"accepted", "approved"}:
                        continue
                    rule_id = _mapping_rule_id(mapping, rule)
                    criterion_id = str(rule.get("criterion") or "")
                    for item in _iter_rule_items(canonical, source_record, rule):
                        if not _matches_where(item, rule.get("where")):
                            continue
                        source_value = _source_value_from_item(item, rule)
                        value = _claim_value(rule, source_value, observed_at=observed_at)
                        if value is None:
                            continue
                        criteria.validate_value(criterion_id, value)
                        directness = str(rule.get("directness") or "inferred")
                        source_independence = str(rule.get("source_independence") or "independent")
                        source_id = source_ref.get("source_id") or (source_record or {}).get("source_id") or mapping.get("source_id")
                        source_type = source_ref.get("source_type") or (source_record or {}).get("source_type") or mapping.get("source_type")
                        claim = {
                            "canonical_id": canonical_id,
                            "criterion_id": criterion_id,
                            "value": value,
                            "source_id": source_id,
                            "source_type": source_type,
                            "source_record_id": source_ref.get("source_record_id") or (source_record or {}).get("source_record_id"),
                            "source_field": rule.get("from_field"),
                            "source_value": source_value,
                            "native_vocabulary": mapping.get("native_vocabulary"),
                            "directness": directness,
                            "covers": rule.get("covers", "full"),
                            "source_independence": source_independence,
                            "criteria_version": mapping.get("criteria_version") or criteria.criteria_version,
                            "mapping_version": mapping.get("mapping_version"),
                            "mapping_rule_id": rule_id,
                            "review_status": _claim_review_status(mapping, rule),
                            "observed_at": observed_at,
                        }
                        for optional_key in ("confidence_reason", "covers_note", "rationale"):
                            if rule.get(optional_key):
                                claim[optional_key] = rule[optional_key]
                        if item.get("institution_id"):
                            claim["institution_id"] = item.get("institution_id")
                        if item.get("claim_id"):
                            claim["source_claim_id"] = item.get("claim_id")
                        claims.append(claim)
        if processed == total_formats or processed % progress_every == 0:
            _emit_progress(
                progress,
                "build_claims_progress",
                canonical_formats_processed=processed,
                canonical_formats=total_formats,
                claims_generated=len(claims),
            )
    _emit_progress(progress, "build_claims_completed", claims_generated=len(claims))
    return claims


def _claim_storage_key(record: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    return (
        str(record.get("canonical_id") or record.get("format_id") or ""),
        str(record.get("criterion_id") or ""),
        str(record.get("source_id") or record.get("source_type") or ""),
        str(record.get("source_record_id") or ""),
        str(record.get("mapping_rule_id") or ""),
        str(record.get("institution_id") or ""),
    )


def _mapping_matches_claim_source(mapping: dict[str, Any], claim: dict[str, Any]) -> bool:
    expected_id = mapping.get("source_id")
    expected_type = mapping.get("source_type")
    source_id = claim.get("source_id") or claim.get("source_type")
    source_type = claim.get("source_type")
    if expected_id and expected_id != source_id:
        return False
    if expected_type and expected_type != source_type:
        return False
    return bool(expected_id or expected_type)


def source_claims_to_supersede(
    store: RegistryStore,
    claims: list[dict[str, Any]],
    mappings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return current claims from mapped sources that are not produced by this backfill.

    This supports deliberate source-level replacement. It is intentionally opt-in
    so a small mapping file can be tested without retiring claims from a fuller
    mapping unless the caller passes --replace-source-claims.
    """
    active_keys = {_claim_storage_key(claim) for claim in claims}
    supersede: list[dict[str, Any]] = []
    for existing in store.query("criterion_claims"):
        if existing.get("current", True) is False:
            continue
        if _claim_storage_key(existing) in active_keys:
            continue
        if any(_mapping_matches_claim_source(mapping, existing) for mapping in mappings):
            supersede.append(existing)
    return supersede


def store_criterion_claims(
    store: RegistryStore,
    claims: list[dict[str, Any]],
    *,
    run_id: str | None = None,
    mappings: list[dict[str, Any]] | None = None,
    replace_source_claims: bool = False,
    progress: ProgressCallback | None = None,
    progress_every: int = 500,
) -> int:
    run_id = run_id or f"criterion-backfill-{utc_now_iso().replace(':', '').replace('+', 'Z')}"
    total_claims = len(claims)
    progress_every = max(1, int(progress_every or 500))
    superseded = source_claims_to_supersede(store, claims, mappings or []) if replace_source_claims else []
    if superseded:
        _emit_progress(progress, "supersede_claims_started", claims=len(superseded), run_id=run_id)
        for index, existing in enumerate(superseded, start=1):
            stored = deepcopy(existing)
            stored["current"] = False
            stored["superseded_by_run_id"] = run_id
            stored["superseded_reason"] = "source_replaced_by_backfill"
            store.save_criterion_claim(stored)
            if index == len(superseded) or index % progress_every == 0:
                _emit_progress(progress, "supersede_claims_progress", claims_superseded=index, claims=len(superseded))
        _emit_progress(progress, "supersede_claims_completed", claims_superseded=len(superseded), run_id=run_id)

    _emit_progress(progress, "write_claims_started", claims=total_claims, run_id=run_id)
    for index, claim in enumerate(claims, start=1):
        stored = deepcopy(claim)
        stored["run_id"] = run_id
        stored["current"] = True
        stored["last_seen_run_id"] = run_id
        store.save_criterion_claim(stored)
        if index == total_claims or index % progress_every == 0:
            _emit_progress(progress, "write_claims_progress", claims_written=index, claims=total_claims)
    _emit_progress(progress, "write_claims_completed", claims_written=total_claims, run_id=run_id)
    return len(superseded)


def backfill_criterion_claims(
    *,
    store: RegistryStore,
    criteria: CriteriaVocabulary,
    mappings: list[dict[str, Any]],
    dry_run: bool = False,
    include_drafts: bool = False,
    replace_source_claims: bool = False,
    progress: ProgressCallback | None = None,
    progress_every: int = 500,
) -> dict[str, Any]:
    _emit_progress(progress, "validate_mappings_started", mappings=len(mappings))
    errors, warnings = validate_mappings(mappings, criteria)
    if errors:
        _emit_progress(progress, "validate_mappings_failed", errors=len(errors))
        raise MappingError("Invalid criterion mappings: " + "; ".join(errors))
    _emit_progress(progress, "validate_mappings_completed", warnings=len(warnings))

    _emit_progress(progress, "load_canonical_formats_started")
    canonical_formats = store.get_current_registry_view()
    _emit_progress(progress, "load_canonical_formats_completed", canonical_formats=len(canonical_formats))

    _emit_progress(progress, "load_source_records_started")
    source_records = store.query("source_records")
    _emit_progress(progress, "load_source_records_completed", source_records=len(source_records))

    claims = build_criterion_claims(
        canonical_formats,
        source_records,
        mappings,
        criteria,
        include_drafts=include_drafts,
        progress=progress,
        progress_every=progress_every,
    )
    claims_superseded = 0
    if replace_source_claims:
        claims_superseded = len(source_claims_to_supersede(store, claims, mappings))
    if dry_run:
        _emit_progress(progress, "dry_run_skipping_write", claims=len(claims))
    else:
        claims_superseded = store_criterion_claims(
            store,
            claims,
            mappings=mappings,
            replace_source_claims=replace_source_claims,
            progress=progress,
            progress_every=progress_every,
        )
    by_criterion = Counter(claim["criterion_id"] for claim in claims)
    by_rule = Counter(str(claim.get("mapping_rule_id") or "unknown") for claim in claims)
    by_source = Counter(str(claim.get("source_id") or claim.get("source_type") or "unknown") for claim in claims)
    result = {
        "status": "dry_run" if dry_run else "completed",
        "claims_generated": len(claims),
        "claims_superseded": claims_superseded,
        "replace_source_claims": replace_source_claims,
        "criteria_version": criteria.criteria_version,
        "criteria": dict(sorted(by_criterion.items())),
        "mapping_rules": dict(sorted(by_rule.items())),
        "sources": dict(sorted(by_source.items())),
        "validation_warnings": warnings,
        "sample_claims": claims[:10],
    }
    _emit_progress(progress, "backfill_completed", status=result["status"], claims_generated=len(claims))
    return result


def projected_coverage(claims: list[dict[str, Any]]) -> dict[str, Any]:
    by_criterion: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in claims:
        by_criterion[str(claim["criterion_id"])].append(claim)
    projection: dict[str, Any] = {}
    for criterion_id, items in sorted(by_criterion.items()):
        formats = {str(item.get("canonical_id")) for item in items if item.get("canonical_id")}
        explicit_formats = {
            str(item.get("canonical_id"))
            for item in items
            if item.get("canonical_id") and item.get("directness") == "explicit"
        }
        sources_by_format: dict[str, set[str]] = defaultdict(set)
        for item in items:
            canonical_id = str(item.get("canonical_id") or "")
            source = str(item.get("source_id") or item.get("source_type") or "")
            if canonical_id and source:
                sources_by_format[canonical_id].add(source)
        projection[criterion_id] = {
            "formats_with_any_claim": len(formats),
            "formats_with_explicit_claim": len(explicit_formats),
            "formats_with_2plus_independent_sources": sum(1 for sources in sources_by_format.values() if len(sources) >= 2),
            "contributing_sources": sorted({source for sources in sources_by_format.values() for source in sources}),
        }
    return projection
