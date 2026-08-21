from __future__ import annotations

import csv

from registry_builder.wikidata_projection import (
    WIKIDATA_PROJECTION_VERSION,
    classify_wikidata_record,
    project_wikidata_csv,
    projection_summary,
)


FIELDS = [
    "format",
    "qid",
    "formatLabel",
    "formatDescription",
    "aliases",
    "instanceOfQid",
    "instanceOfLabel",
    "subclassOfQid",
    "subclassOfLabel",
    "puid",
    "locFdd",
    "naraFormatPlanId",
    "extension",
    "mimeType",
    "version",
    "identificationPattern",
    "developerQid",
    "developerLabel",
    "publicationDate",
    "inceptionDate",
    "partOfQid",
    "partOfLabel",
    "basedOnQid",
    "basedOnLabel",
    "replacesQid",
    "replacesLabel",
    "replacedByQid",
    "replacedByLabel",
    "describedByQid",
    "describedByLabel",
    "officialWebsite",
]


def _write(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            rendered = {field: "" for field in FIELDS}
            rendered.update(row)
            writer.writerow(rendered)


def test_classification_uses_direct_p31_not_p279_context():
    row = {
        "qid": "Q1",
        "instanceOfQid": "Q999",
        "subclassOfQid": "Q235557",
        "puid": "fmt/1",
    }

    classification = classify_wikidata_record(row)

    assert classification["role"] == "authority_linked_unclassified"
    assert classification["record_role"] == "evidence_only"
    assert classification["classification_basis_qids"] == []


def test_projection_preserves_source_identity_and_keeps_copied_authority_ids_unverified(tmp_path):
    source = tmp_path / "wikidata.csv"
    _write(
        source,
        [
            {
                "qid": "Q100",
                "formatLabel": "Example Format",
                "formatDescription": "Example description",
                "aliases": "EF|Example File",
                "instanceOfQid": "Q235557",
                "instanceOfLabel": "file format",
                "subclassOfQid": "Q777",
                "subclassOfLabel": "example parent",
                "puid": "fmt/1|fmt/2",
                "locFdd": "fdd000001",
                "naraFormatPlanId": "NF00001",
                "extension": "ef|example",
                "mimeType": "application/x-example",
                "version": "1.0|1.1",
                "identificationPattern": "45 58",
                "developerQid": "Q999",
                "developerLabel": "Example Developer",
                "officialWebsite": "https://example.test/format",
            }
        ],
    )

    records = project_wikidata_csv(source)
    assert len(records) == 1
    record = records[0]

    assert record.source_record_id == "Q100"
    assert record.record_role == "format_identity"
    assert record.category == "format"
    assert record.name == "Example Format"
    assert record.puids == ["fmt/1", "fmt/2"]
    assert record.loc_ids == ["fdd000001"]
    assert record.nara_ids == ["NF00001"]
    assert record.wikidata_ids == ["Q100"]

    claims = {(item.kind, item.value): item for item in record.identifiers}
    assert claims[("wikidata", "Q100")].verified is True
    assert claims[("puid", "fmt/1")].verified is False
    assert claims[("puid", "fmt/2")].verified is False
    assert claims[("loc", "fdd000001")].verified is False
    assert claims[("nara", "NF00001")].verified is False

    assert record.native_fields["projection_version"] == WIKIDATA_PROJECTION_VERSION
    assert record.native_fields["classification_uses_direct_p31_only"] is True
    assert record.native_fields["subclass_of_context"] == [
        {"qid": "Q777", "label": "example parent"}
    ]
    assert record.native_fields["copied_external_identifiers"]["verified"] is False
    assert record.native_fields["relations"]["developer"] == [
        {"qid": "Q999", "label": "Example Developer"}
    ]
    assert record.risk_assessments == []


def test_projection_assigns_conservative_roles_and_summary(tmp_path):
    source = tmp_path / "wikidata.csv"
    _write(
        source,
        [
            {
                "qid": "Q1",
                "formatLabel": "Direct Format",
                "instanceOfQid": "Q235557",
                "instanceOfLabel": "file format",
            },
            {
                "qid": "Q2",
                "formatLabel": "Format Family",
                "instanceOfQid": "Q26085352",
                "instanceOfLabel": "file format family",
            },
            {
                "qid": "Q3",
                "formatLabel": "Container",
                "instanceOfQid": "Q167772",
                "instanceOfLabel": "digital container format",
            },
            {
                "qid": "Q4",
                "formatLabel": "Word Binary Version",
                "instanceOfQid": "Q28858032",
                "instanceOfLabel": "Microsoft Word Binary File Format",
                "extension": "doc",
            },
            {
                "qid": "Q5",
                "formatLabel": "Video Codec",
                "instanceOfQid": "Q7927899",
                "instanceOfLabel": "video compression format",
                "mimeType": "video/example",
            },
            {
                "qid": "Q6",
                "formatLabel": "Authority-only concept",
                "instanceOfQid": "Q999999",
                "instanceOfLabel": "unknown class",
                "puid": "fmt/6",
            },
            {
                "qid": "Q7",
                "formatLabel": "Open-format concept",
                "instanceOfQid": "Q1056408",
                "instanceOfLabel": "open file format",
                "extension": "open",
            },
        ],
    )

    records = project_wikidata_csv(source)
    roles = {record.source_record_id: record.category for record in records}
    record_roles = {record.source_record_id: record.record_role for record in records}

    assert roles == {
        "Q1": "format",
        "Q2": "format_family",
        "Q3": "container",
        "Q4": "format_subclass",
        "Q5": "codec_or_encoding",
        "Q6": "authority_linked_unclassified",
        "Q7": "other_format_concept",
    }
    assert record_roles["Q1"] == "format_identity"
    assert record_roles["Q2"] == "format_identity"
    assert record_roles["Q3"] == "format_identity"
    assert record_roles["Q4"] == "format_identity"
    assert record_roles["Q5"] == "evidence_only"
    assert record_roles["Q6"] == "evidence_only"
    assert record_roles["Q7"] == "evidence_only"

    summary = projection_summary(records)
    assert summary["records_projected"] == 7
    assert summary["format_identity_records"] == 4
    assert summary["evidence_only_records"] == 3
    assert summary["records_with_copied_puid"] == 1
    assert summary["records_with_multiple_puids"] == 0
    assert summary["risk_assessments_generated"] == 0
    assert summary["identity_reconciliation_performed"] is False
    assert summary["mongo_writes"] == 0
