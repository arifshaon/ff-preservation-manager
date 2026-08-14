from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable

from registry_builder.hazard import BAND_TO_SCORE, reconcile_hazard
from registry_builder.models import CanonicalFormat, Identifier, RawFormatRecord, utc_now_iso
from registry_builder.utils import slugify

_STRONG_IDENTIFIER_KINDS = {"puid", "loc", "nara"}


def _verified_identifiers(record: RawFormatRecord, kind: str | None = None) -> list[Identifier]:
    identifiers = [x for x in record.identifiers if x.verified]
    if kind:
        identifiers = [x for x in identifiers if x.kind == kind]
    return identifiers


def _all_identifiers(record: RawFormatRecord, kind: str | None = None) -> list[Identifier]:
    identifiers = list(record.identifiers)
    if kind:
        identifiers = [x for x in identifiers if x.kind == kind]
    return identifiers


def _institution_policy(record: RawFormatRecord) -> dict:
    return record.institution_policy or record.qnl or {}


def _weak_match_key(record: RawFormatRecord) -> tuple[str, str] | None:
    """Return a conservative weak match key.

    Weak keys never create a canonical identity on their own when a verified
    strong identifier is present. They are used only to bridge an institutional
    row to one uniquely matching external authority group.
    """
    if record.name and record.extensions:
        return ("name_ext", f"{record.name.lower()}|{','.join(record.extensions)}")
    return None


def strongest_key(record: RawFormatRecord) -> tuple[str, str]:
    """Return the strongest safe matching key for a raw record.

    Strong one-to-one identifiers may group records only when the identifier was
    verified by its owning authority. Weak identifiers such as MIME types and
    extensions are not primary grouping keys because they can describe broad
    format classes or families.
    """
    for kind in ("puid", "loc", "nara"):
        verified = _verified_identifiers(record, kind)
        if verified:
            return (kind, verified[0].value)
    weak = _weak_match_key(record)
    if weak:
        return weak
    if record.name:
        return ("name", record.name.lower())
    return ("source_record", f"{record.source_id}:{record.source_record_id}")


def canonical_id_for(key: tuple[str, str], name: str | None) -> str:
    kind, value = key
    if kind == "puid":
        return "puid-" + value.replace("/", "-")
    if kind in {"loc", "nara"}:
        return kind + "-" + slugify(value)
    return "fmt-" + slugify(name or value)


def _risk_to_score(value: str | None) -> float | None:
    if not value:
        return None
    text = re.sub(r"\s+", " ", value).strip().lower()
    if not text:
        return None
    if "high" in text:
        return BAND_TO_SCORE["High"]
    if "moderate" in text or "medium" in text:
        return BAND_TO_SCORE["Moderate"]
    if "low" in text:
        return BAND_TO_SCORE["Low"]
    return None


def _hazard_score_from_dict(data: dict) -> float | None:
    for key in ("rating", "score", "hazard_rating", "risk_score", "external_rating", "normalized_rating"):
        value = data.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                pass
    for key in ("band", "risk_level", "hazard_band", "external_band", "external_risk_level"):
        score = _risk_to_score(data.get(key))
        if score is not None:
            return score
    return None


def _first_score(values: list[float | None]) -> float | None:
    return next((x for x in values if x is not None), None)


def _local_risk_score(policy: dict) -> float | None:
    for key in ("local_risk_level", "risk_level", "spreadsheet_risk_level"):
        score = _risk_to_score(policy.get(key))
        if score is not None:
            return score
    return None


def _hazard_assessment(cf: CanonicalFormat) -> dict:
    external_score = _first_score([_hazard_score_from_dict(x) for x in cf.external_hazard])
    institution_score = _first_score([_local_risk_score(x) for x in cf.institution_policy_overlays])
    result = reconcile_hazard(external_score, institution_score)
    result["computed_at"] = utc_now_iso()
    result["basis_notes"] = "Hazard is reconciled from external and institutional estimators; scores are not added."
    return result


def _safe_weak_aliases(groups: dict[tuple[str, str], list[RawFormatRecord]]) -> dict[tuple[str, str], tuple[str, str]]:
    """Return weak-key aliases that are safe enough for institutional/external bridging.

    A weak key may alias to a verified strong group only when:

    - at least two groups share the same name+extension key;
    - the matching records come from more than one source;
    - exactly one of the candidate groups has a verified strong identifier.

    This lets an institutional row such as "Comma Separated Values + csv" attach
    to the corresponding NARA NF record while avoiding ambiguous merges where
    two authority records share the same weak key.
    """
    weak_index: dict[tuple[str, str], list[tuple[tuple[str, str], RawFormatRecord]]] = defaultdict(list)
    for group_key, items in groups.items():
        for record in items:
            weak = _weak_match_key(record)
            if weak:
                weak_index[weak].append((group_key, record))

    aliases: dict[tuple[str, str], tuple[str, str]] = {}
    for refs in weak_index.values():
        group_keys: list[tuple[str, str]] = []
        sources: set[str] = set()
        for group_key, record in refs:
            sources.add(record.source_id)
            if group_key not in group_keys:
                group_keys.append(group_key)
        if len(group_keys) < 2 or len(sources) < 2:
            continue
        strong_group_keys = [key for key in group_keys if key[0] in _STRONG_IDENTIFIER_KINDS]
        if len(strong_group_keys) != 1:
            continue
        target = strong_group_keys[0]
        for group_key in group_keys:
            if group_key != target:
                aliases[group_key] = target
    return aliases


def reconcile(records: Iterable[RawFormatRecord]) -> list[CanonicalFormat]:
    groups: dict[tuple[str, str], list[RawFormatRecord]] = defaultdict(list)
    alias_keys: dict[tuple[str, str], tuple[str, str]] = {}

    for record in records:
        key = strongest_key(record)
        groups[key].append(record)
        for identifier in _verified_identifiers(record):
            if identifier.kind in _STRONG_IDENTIFIER_KINDS:
                alias_keys[(identifier.kind, identifier.value)] = key

    for weak_key, target_key in _safe_weak_aliases(groups).items():
        alias_keys.setdefault(weak_key, target_key)

    collapsed: dict[tuple[str, str], list[RawFormatRecord]] = defaultdict(list)
    for key, items in groups.items():
        target = alias_keys.get(key, key)
        collapsed[target].extend(items)

    canonical: list[CanonicalFormat] = []
    for key, items in collapsed.items():
        name = next((r.name for r in items if r.name), None) or key[1]
        cf = CanonicalFormat(
            canonical_id=canonical_id_for(key, name),
            preferred_name=name,
            category=next((r.category for r in items if r.category), None),
            description=next((r.description for r in items if r.description), None),
            provenance={"created_at": utc_now_iso(), "reconciliation_key": {"kind": key[0], "value": key[1]}},
        )
        for r in items:
            for identifier in _all_identifiers(r):
                cf.add_identifier(
                    identifier.kind,
                    identifier.value,
                    source=identifier.source,
                    verified=identifier.verified,
                    source_record_id=identifier.source_record_id,
                )
            cf.source_records.append({
                "source_id": r.source_id,
                "source_type": r.source_type,
                "source_record_id": r.source_record_id,
                "urls": r.urls,
            })
            policy = _institution_policy(r)
            if policy:
                cf.institution_policy_overlays.append(policy)
            if r.hazard:
                cf.external_hazard.append(r.hazard | {"source_id": r.source_id})
            if r.readiness:
                cf.readiness.append(r.readiness | {"source_id": r.source_id})
            if r.trend:
                cf.trend.append(r.trend | {"source_id": r.source_id})
        cf.hazard_assessment = _hazard_assessment(cf)
        canonical.append(cf)
    return sorted(canonical, key=lambda x: x.preferred_name.lower())
