from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from registry_builder.adapters.wikidata_sparql import (
    CONDITIONAL_CONTEXT_CLASS_QIDS,
    CONDITIONAL_OPEN_FORMAT_CLASS_QID,
    CONDITIONAL_XML_FORMAT_CLASS_QID,
    REVIEWED_FORMAT_CLASS_QIDS,
    REVIEWED_FORMAT_PARENT_QIDS,
    WIKIDATA_POPULATION_POLICY_VERSION,
)
from registry_builder.models import Identifier, RawFormatRecord


WIKIDATA_PROJECTION_VERSION = "2026-08-21-v1-preview"
DIRECT_FILE_FORMAT_QID = "Q235557"
FILE_FORMAT_FAMILY_QID = "Q26085352"
DIGITAL_CONTAINER_FORMAT_QID = "Q167772"

IDENTITY_ROLES = {
    "format",
    "format_family",
    "format_subclass",
    "container",
}


def _split_pipe(value: str | None) -> list[str]:
    return [part.strip() for part in str(value or "").split("|") if part.strip()]


def _pairs(qids: list[str], labels: list[str]) -> list[dict[str, str]]:
    return [
        {
            "qid": qid,
            "label": labels[index] if index < len(labels) else "",
        }
        for index, qid in enumerate(qids)
    ]


def classify_wikidata_record(row: dict[str, str]) -> dict[str, Any]:
    """Classify one acquired Wikidata row without using transitive ontology inference.

    Classification uses only direct P31 values harvested in the frozen policy-v3
    acquisition. P279 remains source context and never changes the assigned role.
    The classification controls only the preview projection boundary; it does not
    itself create or merge canonical formats.
    """

    instance_qids = set(_split_pipe(row.get("instanceOfQid")))
    authority_linked = any(
        _split_pipe(row.get(field))
        for field in ("puid", "locFdd", "naraFormatPlanId")
    )

    if FILE_FORMAT_FAMILY_QID in instance_qids:
        role = "format_family"
        basis = [FILE_FORMAT_FAMILY_QID]
    elif DIGITAL_CONTAINER_FORMAT_QID in instance_qids:
        role = "container"
        basis = [DIGITAL_CONTAINER_FORMAT_QID]
    elif DIRECT_FILE_FORMAT_QID in instance_qids:
        role = "format"
        basis = [DIRECT_FILE_FORMAT_QID]
    else:
        reviewed_classes = sorted(instance_qids & set(REVIEWED_FORMAT_CLASS_QIDS))
        reviewed_parents = sorted(instance_qids & set(REVIEWED_FORMAT_PARENT_QIDS))
        context_classes = sorted(instance_qids & set(CONDITIONAL_CONTEXT_CLASS_QIDS))

        if reviewed_classes:
            role = "format"
            basis = reviewed_classes
        elif CONDITIONAL_XML_FORMAT_CLASS_QID in instance_qids:
            role = "format"
            basis = [CONDITIONAL_XML_FORMAT_CLASS_QID]
        elif reviewed_parents:
            role = "format_subclass"
            basis = reviewed_parents
        elif context_classes:
            role = "codec_or_encoding"
            basis = context_classes
        elif CONDITIONAL_OPEN_FORMAT_CLASS_QID in instance_qids:
            role = "other_format_concept"
            basis = [CONDITIONAL_OPEN_FORMAT_CLASS_QID]
        elif authority_linked:
            role = "authority_linked_unclassified"
            basis = []
        else:
            role = "other_format_concept"
            basis = []

    return {
        "role": role,
        "record_role": "format_identity" if role in IDENTITY_ROLES else "evidence_only",
        "classification_basis_qids": basis,
        "authority_linked": authority_linked,
    }


def project_wikidata_row(
    row: dict[str, str],
    *,
    source_id: str = "wikidata_file_formats",
    source_type: str = "wikidata_sparql",
) -> RawFormatRecord:
    qid = str(row.get("qid") or "").strip().upper()
    if not qid.startswith("Q") or not qid[1:].isdigit():
        raise ValueError(f"Invalid or missing Wikidata QID: {qid!r}")

    aliases = _split_pipe(row.get("aliases"))
    instance_qids = _split_pipe(row.get("instanceOfQid"))
    instance_labels = _split_pipe(row.get("instanceOfLabel"))
    subclass_qids = _split_pipe(row.get("subclassOfQid"))
    subclass_labels = _split_pipe(row.get("subclassOfLabel"))
    puids = _split_pipe(row.get("puid"))
    loc_ids = _split_pipe(row.get("locFdd"))
    nara_ids = _split_pipe(row.get("naraFormatPlanId"))
    extensions = _split_pipe(row.get("extension"))
    mime_types = _split_pipe(row.get("mimeType"))
    versions = _split_pipe(row.get("version"))
    identification_patterns = _split_pipe(row.get("identificationPattern"))
    official_websites = _split_pipe(row.get("officialWebsite"))

    classification = classify_wikidata_record(row)

    identifiers = [
        Identifier(
            kind="wikidata",
            value=qid,
            source=source_id,
            verified=True,
            source_record_id=qid,
        )
    ]
    identifiers.extend(
        Identifier("puid", value, source_id, False, qid) for value in puids
    )
    identifiers.extend(
        Identifier("loc", value, source_id, False, qid) for value in loc_ids
    )
    identifiers.extend(
        Identifier("nara", value, source_id, False, qid) for value in nara_ids
    )

    technical_evidence: list[dict[str, Any]] = []
    for property_id, predicate, values in (
        ("P1195", "extension", extensions),
        ("P1163", "mime_type", mime_types),
        ("P4152", "identification_pattern", identification_patterns),
    ):
        for value in values:
            technical_evidence.append(
                {
                    "evidence_type": "wikidata_property",
                    "property_id": property_id,
                    "predicate": predicate,
                    "value": value,
                    "source_record_id": qid,
                    "asserted_by": "wikidata",
                }
            )

    relations = {
        "developer": _pairs(
            _split_pipe(row.get("developerQid")),
            _split_pipe(row.get("developerLabel")),
        ),
        "part_of": _pairs(
            _split_pipe(row.get("partOfQid")),
            _split_pipe(row.get("partOfLabel")),
        ),
        "based_on": _pairs(
            _split_pipe(row.get("basedOnQid")),
            _split_pipe(row.get("basedOnLabel")),
        ),
        "replaces": _pairs(
            _split_pipe(row.get("replacesQid")),
            _split_pipe(row.get("replacesLabel")),
        ),
        "replaced_by": _pairs(
            _split_pipe(row.get("replacedByQid")),
            _split_pipe(row.get("replacedByLabel")),
        ),
        "described_by": _pairs(
            _split_pipe(row.get("describedByQid")),
            _split_pipe(row.get("describedByLabel")),
        ),
    }

    native_fields = {
        "projection_version": WIKIDATA_PROJECTION_VERSION,
        "population_policy_version": WIKIDATA_POPULATION_POLICY_VERSION,
        "wikidata_role": classification["role"],
        "classification_basis_qids": classification["classification_basis_qids"],
        "classification_uses_direct_p31_only": True,
        "aliases": aliases,
        "instance_of": _pairs(instance_qids, instance_labels),
        "subclass_of_context": _pairs(subclass_qids, subclass_labels),
        "copied_external_identifiers": {
            "puid": puids,
            "loc": loc_ids,
            "nara": nara_ids,
            "verified": False,
        },
        "technical": {
            "extensions": extensions,
            "mime_types": mime_types,
            "versions": versions,
            "identification_patterns": identification_patterns,
            "publication_dates": _split_pipe(row.get("publicationDate")),
            "inception_dates": _split_pipe(row.get("inceptionDate")),
            "official_websites": official_websites,
        },
        "relations": relations,
    }

    urls = {"wikidata": f"https://www.wikidata.org/wiki/{qid}"}
    if official_websites:
        urls["official"] = official_websites[0]

    name = str(row.get("formatLabel") or "").strip() or (aliases[0] if aliases else qid)

    return RawFormatRecord(
        source_id=source_id,
        source_type=source_type,
        source_record_id=qid,
        record_role=classification["record_role"],
        name=name,
        category=classification["role"],
        description=str(row.get("formatDescription") or "").strip() or None,
        extensions=extensions,
        mime_types=mime_types,
        puids=puids,
        loc_ids=loc_ids,
        nara_ids=nara_ids,
        wikidata_ids=[qid],
        identifiers=identifiers,
        urls=urls,
        evidence=technical_evidence,
        native_fields=native_fields,
        raw=dict(row),
        version=versions[0] if versions else None,
    )


def project_wikidata_csv(
    path: str | Path,
    *,
    source_id: str = "wikidata_file_formats",
    source_type: str = "wikidata_sparql",
) -> list[RawFormatRecord]:
    source = Path(path)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "qid" not in reader.fieldnames:
            raise ValueError(f"Wikidata CSV is missing required 'qid' column: {source}")

        records: list[RawFormatRecord] = []
        seen: set[str] = set()
        for line_number, raw in enumerate(reader, start=2):
            row = {str(key): str(value or "") for key, value in raw.items()}
            qid = str(row.get("qid") or "").strip().upper()
            if qid in seen:
                raise ValueError(f"Duplicate Wikidata QID {qid!r} at line {line_number}")
            record = project_wikidata_row(
                row,
                source_id=source_id,
                source_type=source_type,
            )
            seen.add(record.source_record_id or "")
            records.append(record)
    return records


def projection_summary(records: Iterable[RawFormatRecord]) -> dict[str, Any]:
    items = list(records)
    role_counts = Counter(str(record.native_fields.get("wikidata_role") or "") for record in items)
    record_role_counts = Counter(record.record_role for record in items)
    copied_puid_records = sum(1 for record in items if record.puids)
    copied_loc_records = sum(1 for record in items if record.loc_ids)
    copied_nara_records = sum(1 for record in items if record.nara_ids)
    multiple_puid_records = sum(1 for record in items if len(record.puids) > 1)

    return {
        "status": "ok",
        "projection_version": WIKIDATA_PROJECTION_VERSION,
        "population_policy_version": WIKIDATA_POPULATION_POLICY_VERSION,
        "records_projected": len(items),
        "roles": dict(sorted(role_counts.items())),
        "record_roles": dict(sorted(record_role_counts.items())),
        "format_identity_records": record_role_counts.get("format_identity", 0),
        "evidence_only_records": record_role_counts.get("evidence_only", 0),
        "records_with_copied_puid": copied_puid_records,
        "records_with_copied_loc_id": copied_loc_records,
        "records_with_copied_nara_id": copied_nara_records,
        "records_with_multiple_puids": multiple_puid_records,
        "risk_assessments_generated": 0,
        "criterion_claims_generated": 0,
        "identity_reconciliation_performed": False,
        "mongo_writes": 0,
    }
