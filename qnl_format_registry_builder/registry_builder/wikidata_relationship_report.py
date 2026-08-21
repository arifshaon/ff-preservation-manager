from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SUMMARY_FIELDS = (
    "status",
    "preview_version",
    "projection_version",
    "read_only",
    "canonical_formats",
    "wikidata_records",
    "wikidata_qids_with_relationships",
    "canonical_formats_with_wikidata_relationships",
    "relationship_edges",
    "matched_authority_claims",
    "matched_authority_claims_by_kind",
    "unmatched_authority_claims",
    "unmatched_authority_claims_by_kind",
    "qid_outcomes",
    "qids_with_relationships_by_wikidata_role",
    "identity_merges_performed",
    "canonical_formats_created",
    "canonical_identifiers_promoted",
    "risk_assessments_generated",
    "criterion_claims_generated",
    "mongo_writes",
)


def compact_relationship_report(result: dict[str, Any]) -> dict[str, Any]:
    """Return only decision metrics from a full relationship preview result."""

    return {field: result.get(field) for field in SUMMARY_FIELDS}


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m registry_builder.wikidata_relationship_report",
        description=(
            "Print a compact decision summary from a previously written "
            "Wikidata relationship-preview JSON file."
        ),
    )
    parser.add_argument(
        "--input",
        default="out/wikidata-relationship-preview.json",
        help="Full relationship-preview JSON file",
    )
    args = parser.parse_args()

    path = Path(args.input)
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError(f"Relationship preview must be a JSON object: {path}")

    summary = compact_relationship_report(result)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
