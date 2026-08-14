from __future__ import annotations

from registry_builder.models import Identifier, RawFormatRecord
from registry_builder.utils import normalize_extension, normalize_mime, normalize_identifier


_AUTHORITY_BY_IDENTIFIER = {
    "puid": {"pronom_droid_xml", "wikidata"},
    "loc": {"loc_fdd_xml"},
    "nara": {"nara_lod", "nara_json", "nara"},
    "wikidata": {"wikidata"},
}


def _is_verified(kind: str, source_type: str) -> bool:
    return source_type in _AUTHORITY_BY_IDENTIFIER.get(kind, set())


def _normalise_identifier(kind: str, value: str) -> str:
    if kind == "extension":
        return normalize_extension(value)
    if kind == "mime":
        return normalize_mime(value)
    if kind == "loc":
        return normalize_identifier(value).lower()
    if kind == "wikidata":
        return normalize_identifier(value).upper()
    return normalize_identifier(value)


def _identifier_claims(record: RawFormatRecord) -> list[Identifier]:
    claims: list[Identifier] = list(record.identifiers)
    for value in record.extensions:
        claims.append(Identifier("extension", value, record.source_type, False, record.source_record_id))
    for value in record.mime_types:
        claims.append(Identifier("mime", value, record.source_type, False, record.source_record_id))
    for value in record.puids:
        claims.append(Identifier("puid", value, record.source_type, _is_verified("puid", record.source_type), record.source_record_id))
    for value in record.loc_ids:
        claims.append(Identifier("loc", value, record.source_type, _is_verified("loc", record.source_type), record.source_record_id))
    for value in record.nara_ids:
        claims.append(Identifier("nara", value, record.source_type, _is_verified("nara", record.source_type), record.source_record_id))
    for value in record.wikidata_ids:
        claims.append(Identifier("wikidata", value, record.source_type, _is_verified("wikidata", record.source_type), record.source_record_id))

    out: list[Identifier] = []
    seen: set[tuple[str, str, str, bool, str | None]] = set()
    for claim in claims:
        kind = claim.kind.strip().lower()
        value = _normalise_identifier(kind, claim.value)
        if not kind or not value:
            continue
        source = claim.source or record.source_type
        source_record_id = claim.source_record_id or record.source_record_id
        verified = bool(claim.verified)
        key = (kind, value, source, verified, source_record_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(Identifier(kind, value, source, verified, source_record_id))
    return out


def normalize_record(record: RawFormatRecord) -> RawFormatRecord:
    record.extensions = sorted({normalize_extension(x) for x in record.extensions if normalize_extension(x)})
    record.mime_types = sorted({normalize_mime(x) for x in record.mime_types if normalize_mime(x)})
    record.puids = sorted({normalize_identifier(x) for x in record.puids if normalize_identifier(x)})
    record.loc_ids = sorted({normalize_identifier(x).lower() for x in record.loc_ids if normalize_identifier(x)})
    record.nara_ids = sorted({normalize_identifier(x) for x in record.nara_ids if normalize_identifier(x)})
    record.wikidata_ids = sorted({normalize_identifier(x).upper() for x in record.wikidata_ids if normalize_identifier(x)})
    record.identifiers = _identifier_claims(record)
    if record.name:
        record.name = " ".join(record.name.split())
    return record
