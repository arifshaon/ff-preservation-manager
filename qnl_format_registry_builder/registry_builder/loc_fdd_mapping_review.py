from __future__ import annotations

import argparse
from collections import Counter
import json
import re
from pathlib import Path
from typing import Any

_NO_MATCH_PATTERNS = (
    "no relevant match",
    "no corresponding entry",
    "no corresponding",
    "no match",
    "does not have an entry",
    "does not have a entry",
    "not found",
)

_REVIEW_PATTERNS = (
    "not precisely",
    "not exactly",
    "not equivalent",
    "does not distinguish",
    "superclass",
    "subtype",
    "subtypes",
    "related format",
    "see related",
    "broader",
    "narrower",
    "family",
)


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _contains_any(text: str, patterns: tuple[str, ...]) -> list[str]:
    lowered = text.lower()
    return [pattern for pattern in patterns if pattern in lowered]


def _namespace_fields(namespace: str) -> tuple[str, str, tuple[str, ...]]:
    if namespace == "pronom":
        return "puids", "PRONOM_Note", ("PRONOM_PUID", "PUID", "PRONOM")
    if namespace == "wikidata":
        return "wikidata_qids", "Wikidata_Note", ("Wikidata_Title_ID", "Wikidata_QID", "QID")
    raise ValueError(f"Unsupported LOC mapping namespace: {namespace}")


def _raw_value(entry: dict[str, Any], candidates: tuple[str, ...]) -> str:
    raw = entry.get("raw_row") or {}
    normalized = {re.sub(r"[^a-z0-9]+", "", str(key).lower()): value for key, value in raw.items()}
    for candidate in candidates:
        key = re.sub(r"[^a-z0-9]+", "", candidate.lower())
        value = normalized.get(key)
        if value is not None and _text(value):
            return _text(value)
    return ""


def classify_namespace_mapping(entry: dict[str, Any], namespace: str) -> dict[str, Any]:
    """Classify one LOC crosswalk namespace conservatively for human review.

    This classifier never declares an identity equivalence. A single identifier
    in LOC's dedicated mapping column is only a direct-mapping candidate. Notes
    indicating hierarchy/granularity mismatch, one-to-many mappings, or note-only
    references remain review/contextual evidence.
    """

    ids_field, note_field, raw_candidates = _namespace_fields(namespace)
    identifiers = [str(value) for value in (entry.get(ids_field) or []) if str(value).strip()]
    context = entry.get("mapping_context") or {}
    note = _text(context.get(note_field))
    raw_value = _raw_value(entry, raw_candidates)
    combined = " | ".join(value for value in (raw_value, note) if value)

    no_match_signals = _contains_any(combined, _NO_MATCH_PATTERNS)
    review_signals = _contains_any(combined, _REVIEW_PATTERNS)
    raw_lower = _lower(raw_value)
    note_only_signal = raw_lower.startswith("see note") or raw_lower.startswith("see notes") or "see related" in raw_lower

    if len(identifiers) > 1:
        status = "direct_multiple_review"
        reason = "LOC dedicated mapping column contains multiple identifiers; do not treat as one exact identity."
    elif len(identifiers) == 1 and review_signals:
        status = "direct_single_review"
        reason = "LOC provides one direct identifier, but explanatory text signals possible hierarchy or granularity mismatch."
    elif len(identifiers) == 1:
        status = "direct_single_candidate"
        reason = "LOC dedicated mapping column provides one identifier with no detected mismatch signal; still requires authority-side confirmation before identity bridging."
    elif no_match_signals:
        status = "no_mapping"
        reason = "LOC explanatory text explicitly indicates that no corresponding/relevant mapping is available."
    elif note_only_signal or note:
        status = "contextual_only"
        reason = "No identifier is asserted in LOC's dedicated mapping column; explanatory note is contextual evidence only."
    else:
        status = "unmapped"
        reason = "LOC provides no direct identifier or explanatory mapping note for this namespace."

    return {
        "namespace": namespace,
        "status": status,
        "identifiers": identifiers,
        "raw_mapping_value": raw_value or None,
        "note": note or None,
        "review_signals": review_signals,
        "no_match_signals": no_match_signals,
        "identity_bridge_approved": False,
        "reason": reason,
    }


def classify_entry(entry: dict[str, Any]) -> dict[str, Any]:
    reviewed = dict(entry)
    reviewed["mapping_review"] = {
        "pronom": classify_namespace_mapping(entry, "pronom"),
        "wikidata": classify_namespace_mapping(entry, "wikidata"),
    }
    return reviewed


def review_entries(entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    reviewed = [classify_entry(entry) for entry in entries]
    pronom_counts = Counter(item["mapping_review"]["pronom"]["status"] for item in reviewed)
    wikidata_counts = Counter(item["mapping_review"]["wikidata"]["status"] for item in reviewed)
    summary = {
        "row_count": len(reviewed),
        "pronom_status_counts": dict(sorted(pronom_counts.items())),
        "wikidata_status_counts": dict(sorted(wikidata_counts.items())),
        "identity_bridges_approved": 0,
        "review_policy": "classification_only_no_identity_projection",
    }
    return reviewed, summary


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m registry_builder.loc_fdd_mapping_review",
        description="Classify LOC FDD-PUID-QID crosswalk mappings conservatively without approving identity bridges.",
    )
    parser.add_argument("--input", default="loc-fdd-puid-qid-20260713.json", help="Structured LOC crosswalk JSON")
    parser.add_argument("--out", default="loc-fdd-puid-qid-20260713.review.json", help="Review JSON output")
    args = parser.parse_args()

    input_path = Path(args.input)
    entries = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError("LOC crosswalk review input must be a JSON array")

    reviewed, summary = review_entries(entries)
    out_path = Path(args.out)
    out_path.write_text(json.dumps(reviewed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "input_file": str(input_path), "output_file": str(out_path), **summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
