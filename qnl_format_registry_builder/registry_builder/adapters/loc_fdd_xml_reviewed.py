from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from registry_builder.adapters.loc_fdd_xml import (
    LocFddXmlAdapter,
    _record_from_xml,
    _snapshot_is_zip,
    _text_content,
    _xml_payloads,
)
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

_REVIEWED_SUSTAINABILITY_FACTOR_ALIASES = {
    "disclosure": {"disclosure"},
    "documentation": {"documentation", "formatdocumentation", "specificationdocumentation"},
    "adoption": {"adoption"},
    "transparency": {"transparency"},
    "self_documentation": {"selfdocumentation", "selfdocumenting", "selfdoc"},
    "external_dependencies": {"externaldependencies", "externaldependency"},
    "impact_of_patents": {
        "impactofpatents",
        "impactofpatent",
        "licensingandpatents",
        "licensingpatents",
        "patents",
        "patentclaims",
    },
    "technical_protection_mechanisms": {
        "techprotection",
        "technicalprotectionmechanisms",
        "technicalprotectionconsiderations",
        "technicalprotection",
        "technicalprotectionmechanism",
    },
}
_REVIEWED_FACTOR_LABEL_ELEMENT_NAMES = {
    "label",
    "name",
    "type",
    "factor",
    "factorname",
    "heading",
    "title",
    "term",
}


def _normalized_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _reviewed_factor_key(value: str) -> str | None:
    """Return a sustainability key only for an exact known LOC factor label.

    The base LOC parser intentionally accepts several historical XML shapes, but
    substring matching is too permissive for reviewed sustainability projection:
    prose such as "see Technical Protection Considerations" can occur inside an
    unrelated parent element and must not cause the whole parent subtree to be
    captured as the technical-protection factor. Reviewed projection therefore
    uses exact normalized labels only.
    """

    normalized = _normalized_label(value)
    if not normalized:
        return None
    for factor_key, aliases in _REVIEWED_SUSTAINABILITY_FACTOR_ALIASES.items():
        if normalized in aliases:
            return factor_key
    return None


def _strip_leading_factor_label(text: str, label: str) -> str:
    if not text or not label:
        return text.strip()
    pattern = re.compile(rf"^\s*{re.escape(label)}\s*[:|–—-]?\s*", flags=re.I)
    return pattern.sub("", text, count=1).strip()


def extract_reviewed_loc_sustainability_factors(root: ET.Element) -> dict[str, str]:
    """Extract LOC factor prose without free-text substring classification.

    Supported shapes are deliberately conservative:
    * an element whose tag itself is an exact known factor label;
    * an element with an attribute value that is an exact factor label; or
    * a structured label/name/type child whose complete text is an exact factor
      label, with the surrounding element supplying the factor prose.

    Arbitrary descendant prose is never interpreted as a factor label.
    """

    factors: dict[str, str] = {}

    # Direct factor elements such as <disclosure> or the real LOC
    # <techProtection> tag.
    for elem in root.iter():
        factor_key = _reviewed_factor_key(elem.tag.split("}", 1)[-1])
        if not factor_key:
            continue
        text = _text_content(elem)
        if text:
            factors.setdefault(factor_key, text)

    # Generic factor containers such as <factor type="Disclosure">...</factor>
    # or <factor><label>Disclosure</label>...</factor>.
    for elem in root.iter():
        factor_key: str | None = None
        label_text = ""

        for attr_value in elem.attrib.values():
            possible = _reviewed_factor_key(str(attr_value))
            if possible:
                factor_key = possible
                label_text = str(attr_value)
                break

        if factor_key is None:
            for child in list(elem):
                child_name = _normalized_label(child.tag.split("}", 1)[-1])
                if child_name not in _REVIEWED_FACTOR_LABEL_ELEMENT_NAMES:
                    continue
                child_text = _text_content(child)
                possible = _reviewed_factor_key(child_text)
                if possible:
                    factor_key = possible
                    label_text = child_text
                    break

        if factor_key:
            text = _strip_leading_factor_label(_text_content(elem), label_text)
            if text:
                factors.setdefault(factor_key, text)

    return factors


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


def _reviewed_record_from_xml(
    snapshot: SourceSnapshot,
    source_file: str,
    data: bytes,
) -> RawFormatRecord | None:
    record = _record_from_xml(snapshot, source_file, data)
    if record is None:
        return None

    root = ET.fromstring(data.decode("utf-8", errors="replace"))
    reviewed_factors = extract_reviewed_loc_sustainability_factors(root)
    if reviewed_factors:
        record.native_fields["sustainability_factors"] = reviewed_factors
    else:
        record.native_fields.pop("sustainability_factors", None)

    for evidence in record.evidence:
        if "sustainability_factor_count" in evidence or reviewed_factors:
            evidence["sustainability_factor_count"] = len(reviewed_factors)
        evidence["sustainability_extraction"] = "reviewed_exact_factor_labels_v1"

    normalize_loc_sustainability_structure(record)
    contextualize_loc_xml_identifier_references(record)
    return record


class LocFddXmlReviewedAdapter(LocFddXmlAdapter):
    """LOC FDD XML adapter with reviewed identity and sustainability boundaries."""

    type_name = "loc_fdd_xml_reviewed"

    def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
        records: list[RawFormatRecord] = []
        interval = self._progress_interval()
        for snapshot in snapshots:
            try:
                payloads = _xml_payloads(snapshot)
                total = len(payloads)
                if _snapshot_is_zip(snapshot):
                    self._progress(f"Extracting {total} reviewed LOC FDD XML record(s) from ZIP snapshot")
                else:
                    self._progress(f"Extracting {total} reviewed LOC FDD XML record(s) from source snapshot")

                for index, (source_file, data) in enumerate(payloads, start=1):
                    record = _reviewed_record_from_xml(snapshot, source_file, data)
                    if record:
                        records.append(record)
                    if index == 1 or index % interval == 0 or index == total:
                        self._progress(f"Extracted {index}/{total} reviewed LOC FDD XML record(s)")
            finally:
                self._delete_temporary_snapshot(snapshot)
        return records