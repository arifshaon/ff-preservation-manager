from __future__ import annotations

import csv
import json

import pytest

from registry_builder.wikidata_population_compare import (
    compare_populations,
    write_comparison_outputs,
)


FIELDS = [
    "qid",
    "instanceOfQid",
    "instanceOfLabel",
    "puid",
    "locFdd",
    "naraFormatPlanId",
    "extension",
    "mimeType",
    "identificationPattern",
]


def _write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            rendered = {field: "" for field in FIELDS}
            rendered.update(row)
            writer.writerow(rendered)


def test_compare_populations_tracks_useful_non_direct_records(tmp_path):
    old = tmp_path / "old.csv"
    new = tmp_path / "new.csv"

    _write_csv(
        old,
        [
            {
                "qid": "Q1",
                "instanceOfQid": "Q235557",
                "instanceOfLabel": "file format",
                "extension": "one",
            },
            {
                "qid": "Q2",
                "instanceOfQid": "Q999",
                "instanceOfLabel": "specialist format class",
                "extension": "two",
            },
            {
                "qid": "Q3",
                "instanceOfQid": "Q998",
                "instanceOfLabel": "authority-linked class",
                "puid": "fmt/3",
            },
            {
                "qid": "Q4",
                "instanceOfQid": "Q997",
                "instanceOfLabel": "no useful evidence",
            },
        ],
    )
    _write_csv(
        new,
        [
            {
                "qid": "Q1",
                "instanceOfQid": "Q235557",
                "instanceOfLabel": "file format",
                "extension": "one",
            },
            {
                "qid": "Q3",
                "instanceOfQid": "Q998",
                "instanceOfLabel": "authority-linked class",
                "puid": "fmt/3",
            },
            {
                "qid": "Q5",
                "instanceOfQid": "Q235557",
                "instanceOfLabel": "file format",
                "mimeType": "application/example",
            },
        ],
    )

    result = compare_populations(old, new)

    assert result["summary"] == {
        "old_population_count": 4,
        "new_population_count": 3,
        "retained_count": 2,
        "added_count": 1,
        "removed_count": 2,
        "old_useful_non_direct_count": 2,
        "old_useful_non_direct_retained_count": 1,
        "old_useful_non_direct_missing_count": 1,
    }
    assert result["added_qids"] == {"Q5"}
    assert result["removed_qids"] == {"Q2", "Q4"}
    assert result["old_useful_non_direct_qids"] == {"Q2", "Q3"}
    assert result["old_useful_non_direct_retained_qids"] == {"Q3"}
    assert result["old_useful_non_direct_missing_qids"] == {"Q2"}
    assert result["missing_class_counter"][("Q999", "specialist format class")] == 1


def test_write_comparison_outputs_preserves_rows_and_writes_census(tmp_path):
    old = tmp_path / "old.csv"
    new = tmp_path / "new.csv"
    _write_csv(
        old,
        [
            {
                "qid": "Q20",
                "instanceOfQid": "Q900|Q901",
                "instanceOfLabel": "class A|class B",
                "mimeType": "application/x-example",
            }
        ],
    )
    _write_csv(new, [])

    result = compare_populations(old, new)
    paths = write_comparison_outputs(result, tmp_path / "out", "policy-v1")

    summary = json.loads((tmp_path / "out" / "policy-v1.summary.json").read_text())
    assert summary["old_useful_non_direct_missing_count"] == 1
    assert summary["definition"]["direct_file_format_qid"] == "Q235557"

    missing_rows = list(
        csv.DictReader(
            (tmp_path / "out" / "policy-v1.old-useful-nondirect-missing.csv").open(
                encoding="utf-8"
            )
        )
    )
    assert missing_rows[0]["qid"] == "Q20"
    assert missing_rows[0]["mimeType"] == "application/x-example"

    census = list(
        csv.DictReader(
            (tmp_path / "out" / "policy-v1.missing-class-census.csv").open(
                encoding="utf-8"
            )
        )
    )
    assert census == [
        {
            "instanceOfQid": "Q900",
            "instanceOfLabel": "class A",
            "missing_record_count": "1",
        },
        {
            "instanceOfQid": "Q901",
            "instanceOfLabel": "class B",
            "missing_record_count": "1",
        },
    ]
    assert set(paths) == {
        "summary",
        "added",
        "removed",
        "old_useful_non_direct_retained",
        "old_useful_non_direct_missing",
        "missing_class_census",
    }


def test_compare_rejects_duplicate_qids(tmp_path):
    old = tmp_path / "old.csv"
    new = tmp_path / "new.csv"
    _write_csv(old, [{"qid": "Q1"}, {"qid": "Q1"}])
    _write_csv(new, [])

    with pytest.raises(ValueError, match="Duplicate QID"):
        compare_populations(old, new)
