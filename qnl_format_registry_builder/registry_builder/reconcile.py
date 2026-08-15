from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Iterable

from registry_builder.hazard import BAND_TO_SCORE, reconcile_hazard
from registry_builder.identifier_rules import load_identifier_rules, strong_identifier_kinds, strong_identifier_order
from registry_builder.models import CanonicalFormat, Identifier, RawFormatRecord, utc_now_iso
from registry_builder.utils import slugify

_NATIVE_GAP_SCALE = "nara_file_format_risk_matrix"
_NATIVE_GAP_DIRECTION = "higher_is_safer"


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


def _has_unverified_strong_identifier(record: RawFormatRecord, *, strong_kinds: set[str]) -> bool:
    """Return True when a record carries a strong namespace claim that is not verified.

    A copied workbook PUID/LOC/NARA ID is useful evidence, but it is not safe as
    an identity bridge. If such a claim is present, weak name/extension matching
    must not silently merge the row into an authority record because that recreates
    the JPEG 1.00 / JFIF 1.02 class of false-positive merge by another route.
    """
    return any(identifier.kind in strong_kinds and not identifier.verified for identifier in record.identifiers)


def _group_has_unverified_strong_identifier(items: list[RawFormatRecord], *, strong_kinds: set[str]) -> bool:
    return any(_has_unverified_strong_identifier(record, strong_kinds=strong_kinds) for record in items)


def _institution_policy(record: RawFormatRecord) -> dict:
    return record.institution_policy or record.qnl or {}


def _institution_evidence_claims(record: RawFormatRecord) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for sequence, claim in enumerate(record.institution_evidence or [], start=1):
        stored = dict(claim)
        stored.setdefault("source_id", record.source_id)
        stored.setdefault("source_type", record.source_type)
        stored.setdefault("source_record_id", record.source_record_id)
        stored.setdefault("derived_by", "human")
        stored.setdefault("review_status", "approved")
        stored.setdefault("claim_sequence", sequence)
        if not stored.get("claim_id"):
            criterion = stored.get("criterion_id") or f"claim-{sequence}"
            stored["claim_id"] = "|".join(str(x or "") for x in (record.source_id, record.source_record_id, criterion, sequence))
        claims.append(stored)
    return claims


def _weak_match_key(record: RawFormatRecord) -> tuple[str, str] | None:
    """Return a conservative weak match key.

    Weak keys never create a canonical identity on their own when a verified
    strong identifier is present. They are used only to bridge an institutional
    row to one uniquely matching external authority group.
    """
    if record.name and record.extensions:
        return ("name_ext", f"{record.name.lower()}|{','.join(record.extensions)}")
    return None


def strongest_key(record: RawFormatRecord, *, strong_kinds: list[str] | set[str] | None = None) -> tuple[str, str]:
    """Return the strongest safe matching key for a raw record.

    Strong one-to-one identifiers may group records only when the identifier was
    verified by its owning authority. Weak identifiers such as MIME types and
    extensions are not primary grouping keys because they can describe broad
    format classes or families. Strong identifier namespaces are configurable.
    """
    strong_order = list(strong_kinds) if strong_kinds is not None else strong_identifier_order(load_identifier_rules())
    for kind in strong_order:
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
    if kind in {"name", "name_ext", "source_record"}:
        return "fmt-" + slugify(name or value)
    return kind + "-" + slugify(value)


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


def _float_value(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _hazard_score_from_dict(data: dict) -> float | None:
    # Native external ratings are source-scale values. They must not be treated
    # as normalized hazard scores unless an adapter explicitly emits a normalized
    # field such as rating/normalized_rating or a Low/Moderate/High band.
    for key in ("rating", "score", "hazard_rating", "risk_score", "external_rating", "normalized_rating"):
        parsed = _float_value(data.get(key))
        if parsed is not None:
            return parsed
    for key in ("band", "risk_level", "hazard_band", "external_band", "external_risk_level"):
        score = _risk_to_score(data.get(key))
        if score is not None:
            return score
    return None


def _local_risk_score(policy: dict) -> float | None:
    for key in ("local_risk_level", "risk_level", "spreadsheet_risk_level"):
        score = _risk_to_score(policy.get(key))
        if score is not None:
            return score
    return None


def _first_hazard_with_score(hazards: list[dict]) -> dict | None:
    return next((hazard for hazard in hazards if _hazard_score_from_dict(hazard) is not None), None)


def _first_hazard_with_native_rating(hazards: list[dict]) -> dict | None:
    return next((hazard for hazard in hazards if _native_rating(hazard) is not None), None)


def _first_policy_with_score(policies: list[dict]) -> dict | None:
    return next((policy for policy in policies if _local_risk_score(policy) is not None), None)


def _native_rating(data: dict | None) -> float | None:
    if not data:
        return None
    for key in ("external_rating_native", "external_native_rating", "native_rating"):
        parsed = _float_value(data.get(key))
        if parsed is not None:
            return parsed
    return None


def _native_scale(data: dict | None) -> str | None:
    if not data:
        return None
    value = data.get("external_rating_native_scale") or data.get("native_scale")
    return str(value) if value else None


def _native_direction(data: dict | None) -> str | None:
    if not data:
        return None
    value = data.get("external_rating_native_direction") or data.get("native_direction")
    return str(value) if value else None


def _native_gap_to_institution_band(native_rating: float | None, institution_score: float | None) -> float | None:
    """Return distance from NARA native rating to the institution's band.

    This calculation is intentionally limited to NARA's native scale. Other
    external sources may use different thresholds/directions; their adapters
    should emit normalized ratings/bands and may add their own explanatory fields.
    """
    if native_rating is None or institution_score is None:
        return None
    if institution_score == BAND_TO_SCORE["Low"]:
        return round(max(0.0, 23.0 - native_rating), 3)
    if institution_score == BAND_TO_SCORE["High"]:
        return round(max(0.0, native_rating - (-23.0)), 3)
    if institution_score == BAND_TO_SCORE["Moderate"]:
        if native_rating >= 23.0:
            return round(native_rating - 23.0, 3)
        if native_rating <= -23.0:
            return round(-23.0 - native_rating, 3)
        return 0.0
    return None


def _copy_external_native_fields(result: dict, external_hazard: dict | None, institution_score: float | None) -> None:
    native = _native_rating(external_hazard)
    if native is None:
        return
    result["external_rating_native"] = native
    result["external_native_rating"] = native
    direction = _native_direction(external_hazard)
    scale = _native_scale(external_hazard)
    if direction:
        result["external_rating_native_direction"] = direction
    if scale:
        result["external_rating_native_scale"] = scale
    if external_hazard.get("external_native_band") or external_hazard.get("native_band"):
        result["external_native_band"] = external_hazard.get("external_native_band") or external_hazard.get("native_band")
    if external_hazard.get("native_rating_band"):
        result["external_native_rating_band"] = external_hazard.get("native_rating_band")
    if scale == _NATIVE_GAP_SCALE and direction == _NATIVE_GAP_DIRECTION:
        native_gap = _native_gap_to_institution_band(native, institution_score)
        if native_gap is not None:
            result["external_native_gap_to_institution_band"] = native_gap
            result["external_native_gap_note"] = (
                "Distance from NARA native rating to the nearest threshold for the institution's band; "
                "not used as the normalized reconciliation score."
            )


def _hazard_assessment(cf: CanonicalFormat) -> dict:
    external_hazard = _first_hazard_with_score(cf.external_hazard)
    native_hazard = _first_hazard_with_native_rating(cf.external_hazard)
    institution_policy = _first_policy_with_score(cf.institution_policy_overlays)
    external_score = _hazard_score_from_dict(external_hazard or {})
    institution_score = _local_risk_score(institution_policy or {})
    result = reconcile_hazard(external_score, institution_score)
    _copy_external_native_fields(result, native_hazard or external_hazard, institution_score)
    result["computed_at"] = utc_now_iso()
    result["basis_notes"] = "Hazard is reconciled from external and institutional estimators; scores are not added."
    return result


def _safe_weak_aliases(groups: dict[tuple[str, str], list[RawFormatRecord]], *, strong_kinds: set[str]) -> dict[tuple[str, str], tuple[str, str]]:
    """Return weak-key aliases that are safe enough for institutional/external bridging.

    A weak key may alias to a verified strong group only when:

    - at least two groups share the same name+extension key;
    - the matching records come from more than one source;
    - exactly one of the candidate groups has a verified strong identifier;
    - the group being aliased does not contain unverified strong identifiers.

    This lets a plain institutional row such as "Comma Separated Values + csv"
    attach to the corresponding authority record while avoiding false merges when
    a workbook row carries a copied-but-unverified PUID/LOC/NARA identifier.
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
        strong_group_keys = [key for key in group_keys if key[0] in strong_kinds]
        if len(strong_group_keys) != 1:
            continue
        target = strong_group_keys[0]
        for group_key in group_keys:
            if group_key == target:
                continue
            if _group_has_unverified_strong_identifier(groups[group_key], strong_kinds=strong_kinds):
                continue
            aliases[group_key] = target
    return aliases


def _safe_claimed_strong_identifier_aliases(
    groups: dict[tuple[str, str], list[RawFormatRecord]],
    *,
    strong_kinds: set[str],
) -> dict[tuple[str, str], tuple[str, str]]:
    """Return no aliases for copied strong identifiers.

    Unverified strong identifiers from non-authority sources are retained as
    evidence claims, but they are not identity bridges. A copied workbook PUID
    must not collapse a local row into PRONOM unless a verified authority source
    supplied that identifier on the same record group through normal verified
    identifier reconciliation.
    """
    return {}


def reconcile(records: Iterable[RawFormatRecord], *, identifier_rules: dict[str, dict[str, Any]] | None = None) -> list[CanonicalFormat]:
    rules = identifier_rules or load_identifier_rules()
    strong_order = strong_identifier_order(rules)
    strong_kinds = strong_identifier_kinds(rules)
    groups: dict[tuple[str, str], list[RawFormatRecord]] = defaultdict(list)
    alias_keys: dict[tuple[str, str], tuple[str, str]] = {}

    for record in records:
        key = strongest_key(record, strong_kinds=strong_order)
        groups[key].append(record)
        for identifier in _verified_identifiers(record):
            if identifier.kind in strong_kinds:
                alias_keys[(identifier.kind, identifier.value)] = key

    for weak_key, target_key in _safe_weak_aliases(groups, strong_kinds=strong_kinds).items():
        alias_keys.setdefault(weak_key, target_key)

    for claimed_key, target_key in _safe_claimed_strong_identifier_aliases(groups, strong_kinds=strong_kinds).items():
        alias_keys.setdefault(claimed_key, target_key)

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
            for claim in _institution_evidence_claims(r):
                if claim not in cf.institution_evidence_claims:
                    cf.institution_evidence_claims.append(claim)
            if r.hazard:
                cf.external_hazard.append(r.hazard | {"source_id": r.source_id})
            if r.readiness:
                cf.readiness.append(r.readiness | {"source_id": r.source_id})
            if r.trend:
                cf.trend.append(r.trend | {"source_id": r.source_id})
        cf.hazard_assessment = _hazard_assessment(cf)
        canonical.append(cf)
    return sorted(canonical, key=lambda x: x.preferred_name.lower())
