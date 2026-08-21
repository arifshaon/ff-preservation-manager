from __future__ import annotations

from registry_builder.adapters.loc_fdd_xml import LocFddXmlAdapter
from registry_builder.models import RawFormatRecord, SourceSnapshot


LOC_SUSTAINABILITY_TOP_LEVEL_FACTORS = (
    "disclosure",
    "adoption",
    "transparency",
    "self_documentation",
    "external_dependencies",
    "impact_of_patents",
    "technical_protection_mechanisms",
)


def normalize_loc_sustainability_structure(record: RawFormatRecord) -> RawFormatRecord:
    """Project LOC sustainability evidence using the official seven-factor model.

    LOC's sustainability framework defines seven top-level factors. Some FDD XML
    records also expose a ``documentation`` element near Disclosure. Documentation
    remains useful source-native evidence, but it is supporting detail for
    Disclosure rather than an eighth peer factor. Preserve it under
    ``native_fields.sustainability_factor_details.disclosure.documentation``.
    """

    factors = dict(record.native_fields.get("sustainability_factors") or {})
    documentation = factors.pop("documentation", None)
    official = {
        key: factors[key]
        for key in LOC_SUSTAINABILITY_TOP_LEVEL_FACTORS
        if factors.get(key)
    }

    if official:
        record.native_fields["sustainability_factors"] = official
    else:
        record.native_fields.pop("sustainability_factors", None)

    if documentation:
        details = dict(record.native_fields.get("sustainability_factor_details") or {})
        disclosure_details = dict(details.get("disclosure") or {})
        disclosure_details["documentation"] = documentation
        details["disclosure"] = disclosure_details
        record.native_fields["sustainability_factor_details"] = details

    for evidence in record.evidence:
        if "sustainability_factor_count" in evidence:
            evidence["sustainability_factor_count"] = len(official)
        if documentation:
            evidence["sustainability_supporting_evidence_count"] = 1
            evidence["sustainability_framework"] = "loc_seven_sustainability_factors"

    return record


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
    """LOC FDD XML adapter with reviewed identity and sustainability boundaries."""

    type_name = "loc_fdd_xml_reviewed"

    def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
        records: list[RawFormatRecord] = []
        for record in super().extract(snapshots):
            normalize_loc_sustainability_structure(record)
            contextualize_loc_xml_identifier_references(record)
            records.append(record)
        return records
