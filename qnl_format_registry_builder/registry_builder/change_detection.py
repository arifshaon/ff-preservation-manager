from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from typing import Any

_BULK_CHANGE_MIN_COUNT = 25
_BULK_CHANGE_FRACTION = 0.25


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)


def _change_id(run_id: str, change_type: str, canonical_id: str, field: str | None = None) -> str:
    seed = "|".join([run_id, change_type, canonical_id, field or ""])
    return "chg-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def _bulk_change_id(run_id: str, change_type: str, collapsed_type: str) -> str:
    seed = "|".join([run_id, change_type, collapsed_type])
    return "chg-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def _by_id(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(record.get("canonical_id")): record for record in records if record.get("canonical_id")}


def _hazard(record: dict[str, Any] | None) -> dict[str, Any]:
    if not record:
        return {}
    return record.get("hazard_assessment") or {}


def _divergent(record: dict[str, Any] | None) -> bool:
    """Return true only for actual external-vs-institutional divergence.

    `review_required` is deliberately not used here. Many non-divergent states
    require review, including no_estimator_available, low confidence, missing
    evidence, or other data-quality issues. A divergence event should mean either
    an explicit institutional override, or that both an external and institutional
    estimator are present and their bands disagree.
    """
    hazard = _hazard(record)
    if hazard.get("basis") == "institution_override":
        return True
    external_band = hazard.get("external_band")
    institution_band = hazard.get("institution_band")
    return bool(external_band and institution_band and external_band != institution_band)


def _identifiers(record: dict[str, Any] | None) -> dict[str, list[str]]:
    if not record:
        return {}
    identifiers = record.get("identifiers") or {}
    return {str(k): sorted(str(x) for x in v) for k, v in sorted(identifiers.items())}


def _source_ids(record: dict[str, Any] | None) -> list[str]:
    if not record:
        return []
    source_ids = []
    for source_record in record.get("source_records", []) or []:
        source_id = source_record.get("source_id")
        if source_id and source_id not in source_ids:
            source_ids.append(source_id)
    return sorted(source_ids)


def _source_record_keys(record: dict[str, Any] | None) -> set[tuple[str, str]]:
    """Stable provenance keys used to follow a source record across canonical IDs."""
    if not record:
        return set()
    keys: set[tuple[str, str]] = set()
    for source_record in record.get("source_records", []) or []:
        source_id = str(source_record.get("source_id") or "").strip()
        source_record_id = str(source_record.get("source_record_id") or "").strip()
        if source_id and source_record_id:
            keys.add((source_id, source_record_id))
    return keys


def _serialized_source_record_keys(keys: set[tuple[str, str]]) -> list[dict[str, str]]:
    return [
        {"source_id": source_id, "source_record_id": source_record_id}
        for source_id, source_record_id in sorted(keys)
    ]


def _canonical_transition_map(
    previous_by_id: dict[str, dict[str, Any]],
    current_by_id: dict[str, dict[str, Any]],
) -> dict[str, str]:
    """Map disappeared canonical IDs to an unambiguous current canonical owner.

    Canonical IDs can legitimately change when a later authority introduces a
    stronger reconciliation key (for example a NARA-keyed record becoming owned
    by a PRONOM PUID). If the exact same `(source_id, source_record_id)` provenance
    now occurs under exactly one different current canonical ID, this is an
    identity transition, not an upstream source removal.
    """
    current_index: dict[tuple[str, str], set[str]] = defaultdict(set)
    for canonical_id, record in current_by_id.items():
        for key in _source_record_keys(record):
            current_index[key].add(canonical_id)

    transitions: dict[str, str] = {}
    for previous_id in sorted(set(previous_by_id) - set(current_by_id)):
        candidates: set[str] = set()
        for key in _source_record_keys(previous_by_id[previous_id]):
            candidates.update(current_index.get(key, set()))
        candidates.discard(previous_id)
        if len(candidates) == 1:
            transitions[previous_id] = next(iter(candidates))
    return transitions


def _summary(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if not record:
        return None
    hazard = _hazard(record)
    return {
        "canonical_id": record.get("canonical_id"),
        "preferred_name": record.get("preferred_name"),
        "category": record.get("category"),
        "identifiers": _identifiers(record),
        "source_ids": _source_ids(record),
        "hazard_band": hazard.get("band"),
        "hazard_basis": hazard.get("basis"),
        "review_required": hazard.get("review_required"),
        "external_rating_native": hazard.get("external_rating_native"),
        "external_rating_native_direction": hazard.get("external_rating_native_direction"),
    }


def _action(change_type: str) -> str:
    actions = {
        "record_added": "Review the newly observed canonical format and decide whether an institutional policy overlay or readiness assessment is needed.",
        "record_removed": "Confirm whether the upstream source intentionally removed the format or whether the source adapter/configuration changed.",
        "canonical_rekeyed": "Confirm the canonical identity transition is expected; the same source record is retained under a stronger or otherwise preferred canonical key.",
        "canonical_merged": "Review the canonical merge and confirm that the contributing source records genuinely describe the same format identity.",
        "preferred_name_changed": "Review the naming change and update local documentation or aliases if needed.",
        "category_changed": "Review whether the category change affects method profiles, readiness, or policy grouping.",
        "identifiers_changed": "Review identifier changes before using them for automated matching or policy decisions.",
        "hazard_band_changed": "Review the preservation hazard assessment and consider whether institutional policy should be updated.",
        "hazard_basis_changed": "Review the source mix behind the hazard basis and confirm whether the change is expected.",
        "external_rating_native_changed": "Review the native external rating movement; it may indicate deterioration or improvement within the same band.",
        "divergence_opened": "Review the new external-vs-institutional divergence and decide whether to keep the institutional override or revise policy.",
        "divergence_resolved": "Confirm the resolved divergence and close any associated review action.",
        "source_coverage_changed": "Review the source-level change first. A broad upstream source/configuration shift may need adapter or source validation before per-format review.",
    }
    return actions.get(change_type, "Review this registry change.")


def _event(
    *,
    run_id: str,
    created_at: str,
    change_type: str,
    canonical_id: str,
    previous: Any = None,
    current: Any = None,
    field: str | None = None,
    severity: str = "review",
) -> dict[str, Any]:
    event = {
        "change_id": _change_id(run_id, change_type, canonical_id, field),
        "run_id": run_id,
        "created_at": created_at,
        "change_type": change_type,
        "canonical_id": canonical_id,
        "severity": severity,
        "recommended_actions": [_action(change_type)],
    }
    if field:
        event["field"] = field
    if previous is not None:
        event["previous"] = previous
    if current is not None:
        event["current"] = current
    return event


def _field_change(
    *,
    run_id: str,
    created_at: str,
    canonical_id: str,
    change_type: str,
    field: str,
    previous: Any,
    current: Any,
    severity: str = "review",
) -> dict[str, Any] | None:
    if previous == current:
        return None
    return _event(
        run_id=run_id,
        created_at=created_at,
        change_type=change_type,
        canonical_id=canonical_id,
        field=field,
        previous=previous,
        current=current,
        severity=severity,
    )


def _collapse_bulk_changes(
    changes: list[dict[str, Any]],
    *,
    run_id: str,
    created_at: str,
    registry_size: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if registry_size <= 0:
        return changes, []
    counts = Counter(change["change_type"] for change in changes)
    threshold = max(_BULK_CHANGE_MIN_COUNT, int(registry_size * _BULK_CHANGE_FRACTION))
    bulk_types = {change_type for change_type, count in counts.items() if count >= threshold}
    if not bulk_types:
        return changes, []

    bulk_events: list[dict[str, Any]] = []
    for change_type in sorted(bulk_types):
        affected = [change for change in changes if change["change_type"] == change_type]
        sample_ids = [change.get("canonical_id") for change in affected[:25] if change.get("canonical_id")]
        source_counter: Counter[str] = Counter()
        for change in affected:
            for side in ("previous", "current"):
                summary = change.get(side)
                if isinstance(summary, list):
                    summaries = [item for item in summary if isinstance(item, dict)]
                elif isinstance(summary, dict):
                    summaries = [summary]
                else:
                    summaries = []
                for item in summaries:
                    for source_id in item.get("source_ids", []) or []:
                        source_counter[source_id] += 1
        bulk_events.append({
            "change_id": _bulk_change_id(run_id, "source_coverage_changed", change_type),
            "run_id": run_id,
            "created_at": created_at,
            "change_type": "source_coverage_changed",
            "collapsed_change_type": change_type,
            "affected_count": len(affected),
            "affected_fraction": round(len(affected) / registry_size, 4),
            "registry_size": registry_size,
            "sample_canonical_ids": sample_ids,
            "dominant_source_ids": dict(source_counter.most_common(10)),
            "severity": "review",
            "recommended_actions": [_action("source_coverage_changed")],
            "note": "Bulk per-format changes were collapsed to keep actionable format-level changes visible.",
        })
    kept = [change for change in changes if change["change_type"] not in bulk_types]
    return kept + bulk_events, bulk_events


def detect_registry_changes(
    previous_registry: list[dict[str, Any]],
    current_registry: list[dict[str, Any]],
    *,
    run_id: str,
    created_at: str,
) -> dict[str, Any]:
    """Compare two current registry views and return typed change events.

    The first run against an empty store establishes a baseline and intentionally
    does not generate one `record_added` event per format. Subsequent runs compare
    deterministic canonical IDs and selected evidence fields. Provenance is used
    to distinguish a true source removal from a canonical re-key/merge caused by
    stronger reconciliation evidence.
    """
    previous_by_id = _by_id(previous_registry)
    current_by_id = _by_id(current_registry)
    if not previous_by_id:
        return {
            "run_kind": "baseline",
            "previous_canonical_formats": 0,
            "current_canonical_formats": len(current_by_id),
            "changes": [],
            "change_counts": {},
            "bulk_changes": [],
            "baseline_note": "No previous current registry view was available; this run establishes the baseline.",
        }

    changes: list[dict[str, Any]] = []
    previous_ids = set(previous_by_id)
    current_ids = set(current_by_id)
    transitions = _canonical_transition_map(previous_by_id, current_by_id)
    transitioned_previous_ids = set(transitions)
    transition_targets = set(transitions.values())

    # Group transitions by their current canonical owner so multiple old IDs
    # collapsing into one current identity are reported as one merge event.
    by_target: dict[str, list[str]] = defaultdict(list)
    for previous_id, current_id in transitions.items():
        by_target[current_id].append(previous_id)

    for current_id in sorted(by_target):
        previous_group = sorted(by_target[current_id])
        current_record = current_by_id[current_id]
        shared_keys: set[tuple[str, str]] = set()
        for previous_id in previous_group:
            shared_keys.update(
                _source_record_keys(previous_by_id[previous_id])
                & _source_record_keys(current_record)
            )

        is_merge = len(previous_group) > 1 or current_id in previous_ids
        change_type = "canonical_merged" if is_merge else "canonical_rekeyed"
        previous_summary: Any
        if len(previous_group) == 1:
            previous_summary = _summary(previous_by_id[previous_group[0]])
        else:
            previous_summary = [_summary(previous_by_id[item]) for item in previous_group]
        event = _event(
            run_id=run_id,
            created_at=created_at,
            change_type=change_type,
            canonical_id=current_id,
            previous=previous_summary,
            current=_summary(current_record),
            severity="review" if is_merge else "info",
        )
        event["previous_canonical_ids"] = previous_group
        event["current_canonical_id"] = current_id
        event["shared_source_records"] = _serialized_source_record_keys(shared_keys)
        changes.append(event)

    for canonical_id in sorted((current_ids - previous_ids) - transition_targets):
        changes.append(_event(
            run_id=run_id,
            created_at=created_at,
            change_type="record_added",
            canonical_id=canonical_id,
            current=_summary(current_by_id[canonical_id]),
            severity="review",
        ))

    for canonical_id in sorted((previous_ids - current_ids) - transitioned_previous_ids):
        changes.append(_event(
            run_id=run_id,
            created_at=created_at,
            change_type="record_removed",
            canonical_id=canonical_id,
            previous=_summary(previous_by_id[canonical_id]),
            severity="review",
        ))

    for canonical_id in sorted(previous_ids & current_ids):
        previous = previous_by_id[canonical_id]
        current = current_by_id[canonical_id]
        previous_hazard = _hazard(previous)
        current_hazard = _hazard(current)
        candidates = [
            _field_change(run_id=run_id, created_at=created_at, canonical_id=canonical_id, change_type="preferred_name_changed", field="preferred_name", previous=previous.get("preferred_name"), current=current.get("preferred_name"), severity="info"),
            _field_change(run_id=run_id, created_at=created_at, canonical_id=canonical_id, change_type="category_changed", field="category", previous=previous.get("category"), current=current.get("category"), severity="review"),
            _field_change(run_id=run_id, created_at=created_at, canonical_id=canonical_id, change_type="identifiers_changed", field="identifiers", previous=_identifiers(previous), current=_identifiers(current), severity="review"),
            _field_change(run_id=run_id, created_at=created_at, canonical_id=canonical_id, change_type="hazard_band_changed", field="hazard_assessment.band", previous=previous_hazard.get("band"), current=current_hazard.get("band"), severity="review"),
            _field_change(run_id=run_id, created_at=created_at, canonical_id=canonical_id, change_type="hazard_basis_changed", field="hazard_assessment.basis", previous=previous_hazard.get("basis"), current=current_hazard.get("basis"), severity="review"),
            _field_change(run_id=run_id, created_at=created_at, canonical_id=canonical_id, change_type="external_rating_native_changed", field="hazard_assessment.external_rating_native", previous=previous_hazard.get("external_rating_native"), current=current_hazard.get("external_rating_native"), severity="review"),
        ]
        changes.extend(change for change in candidates if change is not None)

        previously_divergent = _divergent(previous)
        currently_divergent = _divergent(current)
        if not previously_divergent and currently_divergent:
            changes.append(_event(run_id=run_id, created_at=created_at, change_type="divergence_opened", canonical_id=canonical_id, previous=_summary(previous), current=_summary(current), severity="review"))
        elif previously_divergent and not currently_divergent:
            changes.append(_event(run_id=run_id, created_at=created_at, change_type="divergence_resolved", canonical_id=canonical_id, previous=_summary(previous), current=_summary(current), severity="info"))

    raw_counts = Counter(change["change_type"] for change in changes)
    registry_size = max(len(previous_by_id), len(current_by_id))
    collapsed_changes, bulk_events = _collapse_bulk_changes(
        changes,
        run_id=run_id,
        created_at=created_at,
        registry_size=registry_size,
    )
    counts = Counter(change["change_type"] for change in collapsed_changes)
    return {
        "run_kind": "change",
        "previous_canonical_formats": len(previous_by_id),
        "current_canonical_formats": len(current_by_id),
        "changes": collapsed_changes,
        "change_counts": dict(sorted(counts.items())),
        "raw_change_counts": dict(sorted(raw_counts.items())),
        "bulk_changes": bulk_events,
    }


def compact_change_summary(change_report: dict[str, Any], *, sample_limit: int = 25) -> dict[str, Any]:
    changes = change_report.get("changes", []) or []
    return {
        "run_kind": change_report.get("run_kind"),
        "previous_canonical_formats": change_report.get("previous_canonical_formats", 0),
        "current_canonical_formats": change_report.get("current_canonical_formats", 0),
        "total_changes": len(changes),
        "change_counts": change_report.get("change_counts", {}),
        "raw_change_counts": change_report.get("raw_change_counts", {}),
        "bulk_changes": change_report.get("bulk_changes", []),
        "baseline_note": change_report.get("baseline_note"),
        "sample_changes": changes[:sample_limit],
    }
