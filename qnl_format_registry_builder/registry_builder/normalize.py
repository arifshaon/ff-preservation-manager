from __future__ import annotations

from registry_builder.models import RawFormatRecord
from registry_builder.utils import normalize_extension, normalize_mime, normalize_identifier


def normalize_record(record: RawFormatRecord) -> RawFormatRecord:
    record.extensions = sorted({normalize_extension(x) for x in record.extensions if normalize_extension(x)})
    record.mime_types = sorted({normalize_mime(x) for x in record.mime_types if normalize_mime(x)})
    record.puids = sorted({normalize_identifier(x) for x in record.puids if normalize_identifier(x)})
    record.loc_ids = sorted({normalize_identifier(x).lower() for x in record.loc_ids if normalize_identifier(x)})
    record.nara_ids = sorted({normalize_identifier(x) for x in record.nara_ids if normalize_identifier(x)})
    record.wikidata_ids = sorted({normalize_identifier(x).upper() for x in record.wikidata_ids if normalize_identifier(x)})
    if record.name:
        record.name = " ".join(record.name.split())
    return record
