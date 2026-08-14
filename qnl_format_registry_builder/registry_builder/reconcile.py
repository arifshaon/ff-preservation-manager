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
    if record.extensions and record.name:
        return ("name_ext", f"{record.name.lower()}|{','.join(record.extensions)}")
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
    for key in ("rating", "score", "hazard_rating", "risk_score"):
        value = data.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                pass
    for key in ("band", "risk_level", "hazard_band"):
        score = _risk_to_score(data.get(key))
        if score is not None:
            return score
    return None


def _first_score(values: list[float | None]) -> float | None:
    return next((x for x in values if x is not None), None)


def _hazard_assessment(cf: CanonicalFormat) -> dict:
    external_score = _first_score([_hazard_score_from_dict(x) for x in cf.external_hazard])
    qnl_score = _first_score([_risk_to_score(x.get("spreadsheet_risk_level")) for x in cf.qnl_policy_overlay])
    result = reconcile_hazard(external_score, qnl_score)
    result["computed_at"] = utc_now_iso()
    result["basis_notes"] = "Hazard is reconciled from external and QNL estimators; scores are not added."
    return result


def reconcile(records: Iterable[RawFormatRecord]) -> list[CanonicalFormat]:
    groups: dict[tuple[str, str], list[RawFormatRecord]] = defaultdict(list)
    alias_keys: dict[tuple[str, str], tuple[str, str]] = {}

    for record in records:
        key = strongest_key(record)
        groups[key].append(record)
        for identifier in _verified_identifiers(record):
            if identifier.kind in _STRONG_IDENTIFIER_KINDS:
                alias_keys[(identifier.kind, identifier.value)] = key

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
            if r.qnl:
                cf.qnl_policy_overlay.append(r.qnl)
            if r.hazard:
                cf.external_hazard.append(r.hazard | {"source_id": r.source_id})
            if r.readiness:
                cf.readiness.append(r.readiness | {"source_id": r.source_id})
            if r.trend:
                cf.trend.append(r.trend | {"source_id": r.source_id})
        cf.hazard_assessment = _hazard_assessment(cf)
        canonical.append(cf)
    return sorted(canonical, key=lambda x: x.preferred_name.lower())
