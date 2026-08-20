from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

DIRECT_FILE_FORMAT_QID = "Q235557"
TECHNICAL_SIGNAL_FIELDS = ("extension", "mimeType", "identificationPattern")
AUTHORITY_FIELDS = ("puid", "locFdd", "naraFormatPlanId")


def _split_pipe(value: str | None) -> list[str]:
    return [part for part in str(value or "").split("|") if part]


def _load_rows(path: str | Path) -> tuple[list[str], dict[str, dict[str, str]]]:
    source = Path(path)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {source}")
        if "qid" not in reader.fieldnames:
            raise ValueError(f"CSV is missing required 'qid' column: {source}")

        rows: dict[str, dict[str, str]] = {}
        for line_number, raw in enumerate(reader, start=2):
            row = {str(key): str(value or "") for key, value in raw.items()}
            qid = row.get("qid", "").strip()
            if not qid:
                raise ValueError(f"CSV row {line_number} has no QID: {source}")
            if qid in rows:
                raise ValueError(f"Duplicate QID {qid!r} in {source}")
            rows[qid] = row

        return list(reader.fieldnames), rows


def _has_any(row: dict[str, str], fields: tuple[str, ...]) -> bool:
    return any(bool(str(row.get(field, "")).strip()) for field in fields)


def _is_direct_file_format(row: dict[str, str]) -> bool:
    return DIRECT_FILE_FORMAT_QID in set(_split_pipe(row.get("instanceOfQid")))


def _is_useful_non_direct(row: dict[str, str]) -> bool:
    return (
        not _is_direct_file_format(row)
        and (
            _has_any(row, AUTHORITY_FIELDS)
            or _has_any(row, TECHNICAL_SIGNAL_FIELDS)
        )
    )


def _class_pairs(row: dict[str, str]) -> list[tuple[str, str]]:
    qids = _split_pipe(row.get("instanceOfQid"))
    labels = _split_pipe(row.get("instanceOfLabel"))
    pairs: list[tuple[str, str]] = []
    for index, qid in enumerate(qids):
        label = labels[index] if index < len(labels) else ""
        pairs.append((qid, label))
    if not pairs:
        pairs.append(("", ""))
    return pairs


def compare_populations(
    old_path: str | Path,
    new_path: str | Path,
) -> dict[str, Any]:
    old_fields, old_rows = _load_rows(old_path)
    new_fields, new_rows = _load_rows(new_path)

    old_qids = set(old_rows)
    new_qids = set(new_rows)
    retained_qids = old_qids & new_qids
    added_qids = new_qids - old_qids
    removed_qids = old_qids - new_qids

    old_useful = {
        qid for qid, row in old_rows.items() if _is_useful_non_direct(row)
    }
    old_useful_retained = old_useful & new_qids
    old_useful_missing = old_useful - new_qids

    class_counter: Counter[tuple[str, str]] = Counter()
    for qid in old_useful_missing:
        for pair in _class_pairs(old_rows[qid]):
            class_counter[pair] += 1

    return {
        "old_fields": old_fields,
        "new_fields": new_fields,
        "old_rows": old_rows,
        "new_rows": new_rows,
        "retained_qids": retained_qids,
        "added_qids": added_qids,
        "removed_qids": removed_qids,
        "old_useful_non_direct_qids": old_useful,
        "old_useful_non_direct_retained_qids": old_useful_retained,
        "old_useful_non_direct_missing_qids": old_useful_missing,
        "missing_class_counter": class_counter,
        "summary": {
            "old_population_count": len(old_qids),
            "new_population_count": len(new_qids),
            "retained_count": len(retained_qids),
            "added_count": len(added_qids),
            "removed_count": len(removed_qids),
            "old_useful_non_direct_count": len(old_useful),
            "old_useful_non_direct_retained_count": len(old_useful_retained),
            "old_useful_non_direct_missing_count": len(old_useful_missing),
        },
    }


def _qid_sort_key(qid: str) -> tuple[int, str]:
    if qid.startswith("Q") and qid[1:].isdigit():
        return int(qid[1:]), qid
    return 10**20, qid


def _write_rows(
    path: Path,
    fieldnames: list[str],
    rows: dict[str, dict[str, str]],
    qids: set[str],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for qid in sorted(qids, key=_qid_sort_key):
            writer.writerow(rows[qid])


def write_comparison_outputs(
    result: dict[str, Any],
    output_dir: str | Path,
    prefix: str,
) -> dict[str, str]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    paths = {
        "summary": destination / f"{prefix}.summary.json",
        "added": destination / f"{prefix}.added.csv",
        "removed": destination / f"{prefix}.removed.csv",
        "old_useful_non_direct_retained": (
            destination / f"{prefix}.old-useful-nondirect-retained.csv"
        ),
        "old_useful_non_direct_missing": (
            destination / f"{prefix}.old-useful-nondirect-missing.csv"
        ),
        "missing_class_census": destination / f"{prefix}.missing-class-census.csv",
    }

    summary = dict(result["summary"])
    summary["definition"] = {
        "direct_file_format_qid": DIRECT_FILE_FORMAT_QID,
        "authority_fields": list(AUTHORITY_FIELDS),
        "technical_signal_fields": list(TECHNICAL_SIGNAL_FIELDS),
        "useful_non_direct": (
            "not direct P31=Q235557 and has at least one authority identifier "
            "or technical signal"
        ),
    }
    paths["summary"].write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    _write_rows(
        paths["added"],
        result["new_fields"],
        result["new_rows"],
        result["added_qids"],
    )
    _write_rows(
        paths["removed"],
        result["old_fields"],
        result["old_rows"],
        result["removed_qids"],
    )
    _write_rows(
        paths["old_useful_non_direct_retained"],
        result["old_fields"],
        result["old_rows"],
        result["old_useful_non_direct_retained_qids"],
    )
    _write_rows(
        paths["old_useful_non_direct_missing"],
        result["old_fields"],
        result["old_rows"],
        result["old_useful_non_direct_missing_qids"],
    )

    with paths["missing_class_census"].open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "instanceOfQid",
                "instanceOfLabel",
                "missing_record_count",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        for (class_qid, class_label), count in sorted(
            result["missing_class_counter"].items(),
            key=lambda item: (-item[1], item[0][0], item[0][1]),
        ):
            writer.writerow(
                {
                    "instanceOfQid": class_qid,
                    "instanceOfLabel": class_label,
                    "missing_record_count": count,
                }
            )

    return {name: str(path) for name, path in paths.items()}


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m registry_builder.wikidata_population_compare",
        description=(
            "Compare two acquisition-only Wikidata file-format CSV snapshots "
            "by QID and identify useful non-direct records lost by a "
            "population-policy change."
        ),
    )
    parser.add_argument("--old", required=True, help="Old Wikidata acquisition CSV")
    parser.add_argument("--new", required=True, help="New Wikidata acquisition CSV")
    parser.add_argument(
        "--out-dir",
        default="wikidata-population-comparison",
        help="Directory for comparison outputs",
    )
    parser.add_argument(
        "--prefix",
        default="wikidata-population",
        help="Filename prefix for comparison outputs",
    )
    args = parser.parse_args()

    result = compare_populations(args.old, args.new)
    outputs = write_comparison_outputs(result, args.out_dir, args.prefix)
    print(
        json.dumps(
            {"status": "ok", **result["summary"], "outputs": outputs},
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
