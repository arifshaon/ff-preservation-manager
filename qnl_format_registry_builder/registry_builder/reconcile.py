from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from registry_builder.models import RawFormatRecord, CanonicalFormat, utc_now_iso
from registry_builder.utils import slugify


def strongest_key(record: RawFormatRecord) -> tuple[str, str]:
    """Return the strongest available matching key for a raw record.

    Priority is identifier-led. QNL spreadsheet rows are deliberately not treated
    as the canonical universe; they are overlays attached to a canonical record.
    """
    if record.puids:
        return ("puid", record.puids[0])
    if record.loc_ids:
        return ("loc", record.loc_ids[0])
    if record.nara_ids:
        return ("nara", record.nara_ids[0])
    if record.mime_types:
        return ("mime", record.mime_types[0])
    if record.extensions and record.name:
        return ("name_ext", f"{record.name.lower()}|{','.join(record.extensions)}")
    if record.name:
        return ("name", record.name.lower())
    if record.extensions:
        return ("extension", ",".join(record.extensions))
    return ("source_record", f"{record.source_id}:{record.source_record_id}")


def canonical_id_for(key: tuple[str, str], name: str | None) -> str:
    kind, value = key
    if kind == "puid":
        return "puid-" + value.replace("/", "-")
    if kind in {"loc", "nara", "mime"}:
        return kind + "-" + slugify(value)
    return "fmt-" + slugify(name or value)


def reconcile(records: Iterable[RawFormatRecord]) -> list[CanonicalFormat]:
    groups: dict[tuple[str, str], list[RawFormatRecord]] = defaultdict(list)
    alias_keys: dict[tuple[str, str], tuple[str, str]] = {}

    # First pass: group by strongest key. This is intentionally conservative.
    for record in records:
        key = strongest_key(record)
        groups[key].append(record)
        for puid in record.puids:
            alias_keys[("puid", puid)] = key
        for loc in record.loc_ids:
            alias_keys[("loc", loc)] = key
        for nara in record.nara_ids:
            alias_keys[("nara", nara)] = key

    # Second pass: collapse groups that share a stronger identifier discovered in aliases.
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
            for ext in r.extensions:
                cf.add_identifier("extension", ext)
            for mime in r.mime_types:
                cf.add_identifier("mime", mime)
            for puid in r.puids:
                cf.add_identifier("puid", puid)
            for loc in r.loc_ids:
                cf.add_identifier("loc", loc)
            for nara in r.nara_ids:
                cf.add_identifier("nara", nara)
            for wd in r.wikidata_ids:
                cf.add_identifier("wikidata", wd)
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
        canonical.append(cf)
    return sorted(canonical, key=lambda x: x.preferred_name.lower())
