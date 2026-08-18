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
_VERSION_TOKEN_RE = re.compile(
    r"\b("
    r"\d+\.\d+(?:\.\d+)?"
    r"|\d{2,4}[a-z]"
    r"|(?:pdf|iso)?/?[a-z]-\d+[a-z]?"
    r"|\d{2,4}-\d{2,4}"
    r")\b",
    re.I,
)
_COPIED_IDENTIFIER_HEURISTIC_REASON = (
    "Copied identifier bridged to a single verified authority group, but only one side carries "
    "an explicit version discriminator."
)
_BROAD_FORMAT_MARKERS = ("family", "generic", "unspecified", "all versions", "multiple versions")


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
    return any(identifier.kind in strong_kinds and not identifier.verified for identifier in record.identifiers)


def _group_has_unverified_strong_identifier(items: list[RawFormatRecord], *, strong_kinds: set[str]) -> bool:
    return any(_has_unverified_strong_identifier(record, strong_kinds=strong_kinds) for record in items)


def version_tokens(name: str | None) -> frozenset[str]:
    if not name:
        return frozenset()
    return frozenset(match.group(1).lower() for match in _VERSION_TOKEN_RE.finditer(name))


def _names_conflict(a: str | None, b: str | None) -> bool:
    left = version_tokens(a)
    right = version_tokens(b)
    return bool(left and right and left != right)


def _names_have_asymmetric_version_signal(a: str | None, b: str | None) -> bool:
    left = version_tokens(a)
    right = version_tokens(b)
    return bool((left and not right) or (right and not left))


def _groups_name_conflict(left: list[RawFormatRecord], right: list[RawFormatRecord]) -> bool:
    return any(_names_conflict(a.name, b.name) for a in left for b in right)


def _groups_have_asymmetric_version_signal(left: list[RawFormatRecord], right: list[RawFormatRecord]) -> bool:
    return any(_names_have_asymmetric_version_signal(a.name, b.name) for a in left for b in right)


def _is_broad_format_name(name: str | None) -> bool:
    text = str(name or "").strip().lower()
    return any(marker in text for marker in _BROAD_FORMAT_MARKERS)


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
    if record.name and record.extensions:
        return ("name_ext", f"{record.name.lower()}|{','.join(record.extensions)}")
    return None


def strongest_key(record: RawFormatRecord, *, strong_kinds: list[str] | set[str] | None = None) -> tuple[str, str]:
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
    strong_order: list[str],
) -> tuple[dict[tuple[str, str], tuple[str, str]], dict[tuple[str, str], dict[str, str]]]:
    strong_kinds = set(strong_order)
    verified_targets: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
    for group_key, items in groups.items():
        for record in items:
            for identifier in _verified_identifiers(record):
                if identifier.kind in strong_kinds:
                    verified_targets[(identifier.kind, identifier.value)].add(group_key)

    aliases: dict[tuple[str, str], tuple[str, str]] = {}
    alias_confidence: dict[tuple[str, str], dict[str, str]] = {}
    for group_key, items in groups.items():
        selected_target: tuple[str, str] | None = None
        selected_kind: str | None = None
        for kind in strong_order:
            targets: set[tuple[str, str]] = set()
            copied_values = {
                identifier.value
                for record in items
                for identifier in _all_identifiers(record, kind)
                if not identifier.verified
            }
            for value in copied_values:
                matching = verified_targets.get((kind, value), set())
                if len(matching) == 1:
                    targets.update(matching)
                elif len(matching) > 1:
                    targets.update(matching)
            targets.discard(group_key)
            if not targets:
                continue
            if len(targets) != 1:
                selected_target = None
                selected_kind = kind
                break
            selected_target = next(iter(targets))
            selected_kind = kind
            break

        if selected_target is None:
            continue
        if selected_kind == "puid" and any(_is_broad_format_name(record.name) for record in items):
            continue
        if _groups_name_conflict(items, groups[selected_target]):
            continue
        aliases[group_key] = selected_target
        if _groups_have_asymmetric_version_signal(items, groups[selected_target]):
            alias_confidence[group_key] = {
                "confidence": "heuristic",
                "confidence_reason": _COPIED_IDENTIFIER_HEURISTIC_REASON,
            }
    return aliases, alias_confidence


def _preferred_record_for_key(items: list[RawFormatRecord], key: tuple[str, str]) -> RawFormatRecord:
    kind, value = key
    for record in items:
        if any(identifier.kind == kind and identifier.value == value and identifier.verified for identifier in record.identifiers):
            return record
    return items[0]


def _identifier_claim_dict(
    identifier: Identifier,
    *,
    confidence: str | None = None,
    confidence_reason: str | None = None,
) -> dict[str, Any]:
    claim: dict[str, Any] = {
        "kind": identifier.kind,
        "value": identifier.value,
        "source": identifier.source,
        "verified": bool(identifier.verified),
        "source_record_id": identifier.source_record_id,
    }
    if confidence:
        claim["confidence"] = confidence
    if confidence_reason:
        claim["confidence_reason"] = confidence_reason
    return claim


def _source_ref(record: RawFormatRecord) -> dict[str, Any]:
    cross_references = [
        {"kind": identifier.kind, "value": identifier.value}
        for identifier in record.identifiers
        if not identifier.verified
    ]
    ref: dict[str, Any] = {
        "source_id": record.source_id,
        "source_type": record.source_type,
        "source_record_id": record.source_record_id,
        "urls": record.urls,
    }
    if cross_references:
        ref["identifier_cross_references"] = cross_references
    return ref


def _append_source_ref(cf: CanonicalFormat, ref: dict[str, Any]) -> None:
    source_key = (str(ref.get("source_id") or ""), str(ref.get("source_record_id") or ""))
    for existing in cf.source_records:
        existing_key = (str(existing.get("source_id") or ""), str(existing.get("source_record_id") or ""))
        if existing_key != source_key:
            continue
        for key in ("relationship", "evidence_scope", "related_puids", "identifier_cross_references"):
            if ref.get(key) is not None:
                existing[key] = ref[key]
        return
    cf.source_records.append(ref)


def _attach_explicit_puid_source_relationships(canonical: list[CanonicalFormat], records: list[RawFormatRecord]) -> None:
    owners: dict[str, CanonicalFormat] = {}
    for cf in canonical:
        for claim in cf.identifier_claims:
            if claim.get("kind") == "puid" and claim.get("verified"):
                owners[str(claim.get("value"))] = cf

    for record in records:
        puids = sorted({
            identifier.value
            for identifier in record.identifiers
            if identifier.kind == "puid" and not identifier.verified and identifier.value in owners
        })
        if not puids:
            continue
        multi = len(puids) > 1
        for puid in puids:
            target = owners[puid]
            if not multi and _names_conflict(record.name, target.preferred_name):
                continue
            if not multi and _is_broad_format_name(record.name):
                continue
            ref = _source_ref(record)
            ref.update({
                "relationship": "explicit_puid_cross_reference",
                "evidence_scope": "multi_puid_source_record" if multi else "exact_puid_cross_reference",
                "related_puids": puids,
            })
            _append_source_ref(target, ref)


def reconcile(records: Iterable[RawFormatRecord], *, identifier_rules: dict[str, dict[str, Any]] | None = None) -> list[CanonicalFormat]:
    rules = identifier_rules or load_identifier_rules()
    strong_order = strong_identifier_order(rules)
    strong_kinds = strong_identifier_kinds(rules)
    record_list = list(records)
    groups: dict[tuple[str, str], list[RawFormatRecord]] = defaultdict(list)
    alias_keys: dict[tuple[str, str], tuple[str, str]] = {}
    alias_confidence: dict[tuple[str, str], dict[str, str]] = {}
    record_keys: dict[int, tuple[str, str]] = {}

    for record in record_list:
        key = strongest_key(record, strong_kinds=strong_order)
        record_keys[id(record)] = key
        groups[key].append(record)
        for identifier in _verified_identifiers(record):
            if identifier.kind in strong_kinds:
                alias_keys[(identifier.kind, identifier.value)] = key

    for weak_key, target_key in _safe_weak_aliases(groups, strong_kinds=strong_kinds).items():
        alias_keys.setdefault(weak_key, target_key)

    claimed_aliases, claimed_alias_confidence = _safe_claimed_strong_identifier_aliases(groups, strong_order=strong_order)
    for claimed_key, target_key in claimed_aliases.items():
        existing_target = alias_keys.get(claimed_key)
        if existing_target is None or existing_target == claimed_key:
            alias_keys[claimed_key] = target_key
            if claimed_key in claimed_alias_confidence:
                alias_confidence[claimed_key] = claimed_alias_confidence[claimed_key]

    collapsed: dict[tuple[str, str], list[RawFormatRecord]] = defaultdict(list)
    for key, items in groups.items():
        target = alias_keys.get(key, key)
        collapsed[target].extend(items)

    canonical: list[CanonicalFormat] = []
    for key, items in collapsed.items():
        preferred = _preferred_record_for_key(items, key)
        name = preferred.name or next((r.name for r in items if r.name), None) or key[1]
        cf = CanonicalFormat(
            canonical_id=canonical_id_for(key, name),
            preferred_name=name,
            category=preferred.category or next((r.category for r in items if r.category), None),
            description=preferred.description or next((r.description for r in items if r.description), None),
            version=preferred.version or next((r.version for r in items if r.version), None),
            provenance={"created_at": utc_now_iso(), "reconciliation_key": {"kind": key[0], "value": key[1]}},
        )
        for r in items:
            original_key = record_keys.get(id(r), key)
            confidence = alias_confidence.get(original_key)
            for identifier in _all_identifiers(r):
                claim_confidence = None
                confidence_reason = None
                if confidence and identifier.kind in strong_kinds and not identifier.verified:
                    claim_confidence = confidence["confidence"]
                    confidence_reason = confidence["confidence_reason"]

                # Keep copied strong identifiers in provenance claims, but do
                # not put them in CanonicalFormat.identifiers. The latter is the
                # exact resolver identity index; the former records what another
                # authority/source claimed without creating duplicate PUID/LOC/
                # NARA ownership.
                if identifier.kind in strong_kinds and not identifier.verified:
                    claim = _identifier_claim_dict(
                        identifier,
                        confidence=claim_confidence,
                        confidence_reason=confidence_reason,
                    )
                    if claim not in cf.identifier_claims:
                        cf.identifier_claims.append(claim)
                    continue

                cf.add_identifier(
                    identifier.kind,
                    identifier.value,
                    source=identifier.source,
                    verified=identifier.verified,
                    source_record_id=identifier.source_record_id,
                    confidence=claim_confidence,
                    confidence_reason=confidence_reason,
                )
            _append_source_ref(cf, _source_ref(r))
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

    _attach_explicit_puid_source_relationships(canonical, record_list)
    return sorted(canonical, key=lambda x: x.preferred_name.lower())