from __future__ import annotations

from registry_builder.adapters.loc_fdd_xml import LocFddXmlAdapter
from registry_builder.models import RawFormatRecord, SourceSnapshot


def contextualize_loc_xml_identifier_references(record: RawFormatRecord) -> RawFormatRecord:
    """Keep LOC-embedded PUID/QID strings as context, not identity assertions.

    LOC FDD XML prose can mention PRONOM PUIDs and Wikidata QIDs. Those strings
    remain useful source-native evidence, but the official LOC monthly
    FDD-PUID-QID crosswalk is the reviewed source for cross-registry mapping.
    Therefore this projection removes XML-prose PUID/QID values from the typed
    identifier fields before normalization/reconciliation and preserves them in
    ``native_fields.contextual_identifier_references`` instead.
    """

    contextual = dict(record.native_fields.get("contextual_identifier_references") or {})
    if record.puids:
        contextual["puid"] = sorted(set(record.puids))
    if record.wikidata_ids:
        contextual["wikidata"] = sorted(set(record.wikidata_ids))
    if contextual:
        record.native_fields["contextual_identifier_references"] = contextual

    record.puids = []
    record.wikidata_ids = []
    record.identifiers = [
        claim
        for claim in record.identifiers
        if str(claim.kind).strip().lower() not in {"puid", "wikidata"}
    ]

    # Preserve the established source vocabulary for criterion mappings and LOC
    # identifier ownership even though a stricter adapter type is used to acquire
    # and project the source.
    record.source_type = "loc_fdd_xml"
    return record


class LocFddXmlReviewedAdapter(LocFddXmlAdapter):
    """LOC FDD XML adapter with reviewed cross-registry identity boundaries."""

    type_name = "loc_fdd_xml_reviewed"

    def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
        return [
            contextualize_loc_xml_identifier_references(record)
            for record in super().extract(snapshots)
        ]
