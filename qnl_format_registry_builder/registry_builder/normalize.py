from __future__ import annotations

from registry_builder.identifier_rules import (
    load_identifier_rules,
    is_verified_identifier,
    normalize_identifier_value,
)
from registry_builder.models import Identifier, RawFormatRecord


def _identifier_claims(record: RawFormatRecord, identifier_rules: dict | None = None) -> list[Identifier]:
    rules = identifier_rules or load_identifier_rules()
    claims: list[Identifier] = list(record.identifiers)

    # Backwards-compatible typed fields. New adapters should prefer the generic
    # `identifiers` collection so new identifier namespaces do not require model
    # changes.
    for value in record.extensions:
        claims.append(Identifier("extension", value, record.source_type, False, record.source_record_id))
    for value in record.mime_types:
        claims.append(Identifier("mime", value, record.source_type, False, record.source_record_id))
    for value in record.puids:
        claims.append(Identifier("puid", value, record.source_type, is_verified_identifier("puid", record.source_type, rules), record.source_record_id))
    for value in record.loc_ids:
        claims.append(Identifier("loc", value, record.source_type, is_verified_identifier("loc", record.source_type, rules), record.source_record_id))
    for value in record.nara_ids:
        claims.append(Identifier("nara", value, record.source_type, is_verified_identifier("nara", record.source_type, rules), record.source_record_id))
    for value in record.wikidata_ids:
        claims.append(Identifier("wikidata", value, record.source_type, is_verified_identifier("wikidata", record.source_type, rules), record.source_record_id))

    out: list[Identifier] = []
    index: dict[tuple[str, str, str, bool, str | None], int] = {}
    for claim in claims:
        kind = claim.kind.strip().lower()
        value = normalize_identifier_value(kind, claim.value)
        if not kind or not value:
            continue
        source = claim.source or record.source_type
        source_record_id = claim.source_record_id or record.source_record_id
        verified = bool(claim.verified) or is_verified_identifier(kind, record.source_type, rules)
        endorsed = bool(getattr(claim, "endorsed", True))
        key = (kind, value, source, verified, source_record_id)
        position = index.get(key)
        if position is None:
            index[key] = len(out)
            out.append(Identifier(kind, value, source, verified, source_record_id, endorsed))
        elif endorsed and not out[position].endorsed:
            # The same identifier reached us twice; an endorsement anywhere
            # settles it, so the conservative copy is replaced.
            out[position] = Identifier(kind, value, source, verified, source_record_id, True)
    return out


def normalize_record(record: RawFormatRecord, *, identifier_rules: dict | None = None) -> RawFormatRecord:
    record.identifiers = _identifier_claims(record, identifier_rules)

    # Keep compatibility fields populated from the generic collection. These are
    # convenience mirrors only; source adapters should not need new typed fields
    # for new identifier namespaces.
    by_kind: dict[str, list[str]] = {}
    for claim in record.identifiers:
        # Mirrors carry only endorsed claims, matching the canonical identifier
        # map. An unendorsed claim stays reachable through record.identifiers.
        if not claim.endorsed:
            continue
        by_kind.setdefault(claim.kind, [])
        if claim.value not in by_kind[claim.kind]:
            by_kind[claim.kind].append(claim.value)
    record.extensions = sorted(by_kind.get("extension", []))
    record.mime_types = sorted(by_kind.get("mime", []))
    record.puids = sorted(by_kind.get("puid", []))
    record.loc_ids = sorted(by_kind.get("loc", []))
    record.nara_ids = sorted(by_kind.get("nara", []))
    record.wikidata_ids = sorted(by_kind.get("wikidata", []))

    if record.name:
        record.name = " ".join(record.name.split())
    return record
