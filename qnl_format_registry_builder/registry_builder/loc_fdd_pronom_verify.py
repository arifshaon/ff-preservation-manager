from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from registry_builder.reconcile import version_tokens
from registry_builder.storage import create_store


_LOC_AUTHORITY_SOURCES = {"loc_fdd_xml"}
_PRONOM_AUTHORITY_SOURCES = {"pronom_registry", "pronom_droid_xml"}
_BROAD_FORMAT_MARKERS = ("family", "generic", "unspecified", "all versions", "multiple versions")


def _is_broad_format_name(name: str | None) -> bool:
    text = str(name or "").strip().lower()
    return any(marker in text for marker in _BROAD_FORMAT_MARKERS)


def _has_verified_claim(
    record: dict[str, Any] | None,
    *,
    kind: str,
    value: str,
    authority_sources: set[str],
) -> bool:
    if not record:
        return False
    for claim in record.get("identifier_claims") or []:
        if str(claim.get("kind") or "").strip().lower() != kind:
            continue
        if str(claim.get("value") or "").strip() != value:
            continue
        if not bool(claim.get("verified")):
            continue
        if str(claim.get("source") or "") not in authority_sources:
            continue
        return True
    return False


def verify_pronom_candidate(entry: dict[str, Any], store) -> dict[str, Any] | None:
    review = ((entry.get("mapping_review") or {}).get("pronom") or {})
    if review.get("status") != "direct_single_candidate":
        return None

    fdd_ids = list(entry.get("fdd_ids") or [])
    puids = list(entry.get("puids") or [])
    if len(fdd_ids) != 1 or len(puids) != 1:
        return {
            "source_record_id": entry.get("source_record_id"),
            "status": "candidate_shape_invalid",
            "fdd_ids": fdd_ids,
            "puids": puids,
        }

    fdd_id = str(fdd_ids[0])
    puid = str(puids[0])
    loc_record = store.find_by_identifier("loc", fdd_id)
    pronom_record = store.find_by_identifier("puid", puid)

    result: dict[str, Any] = {
        "source_record_id": entry.get("source_record_id"),
        "title": entry.get("title"),
        "fdd_id": fdd_id,
        "puid": puid,
        "loc_canonical_id": (loc_record or {}).get("canonical_id"),
        "loc_preferred_name": (loc_record or {}).get("preferred_name"),
        "pronom_canonical_id": (pronom_record or {}).get("canonical_id"),
        "pronom_preferred_name": (pronom_record or {}).get("preferred_name"),
        "identity_bridge_approved": False,
    }

    if not loc_record:
        result["status"] = "loc_target_missing"
        return result
    if not pronom_record:
        result["status"] = "pronom_target_missing"
        return result

    loc_authority = _has_verified_claim(
        loc_record,
        kind="loc",
        value=fdd_id,
        authority_sources=_LOC_AUTHORITY_SOURCES,
    )
    pronom_authority = _has_verified_claim(
        pronom_record,
        kind="puid",
        value=puid,
        authority_sources=_PRONOM_AUTHORITY_SOURCES,
    )
    result["loc_authority_confirmed"] = loc_authority
    result["pronom_authority_confirmed"] = pronom_authority
    if not loc_authority or not pronom_authority:
        result["status"] = "authority_claim_missing"
        return result

    loc_name = str(entry.get("title") or loc_record.get("preferred_name") or "")
    if _is_broad_format_name(loc_name):
        result["status"] = "broad_scope_review"
        result["scope_reason"] = "LOC description is explicitly family/generic/broad and is not eligible for automatic exact-identity projection."
        return result

    loc_tokens = version_tokens(loc_name)
    pronom_tokens = version_tokens(str(pronom_record.get("preferred_name") or ""))
    result["loc_version_tokens"] = sorted(loc_tokens)
    result["pronom_version_tokens"] = sorted(pronom_tokens)

    if loc_tokens and pronom_tokens and loc_tokens != pronom_tokens:
        result["status"] = "version_conflict_review"
        return result
    if bool(loc_tokens) != bool(pronom_tokens):
        result["status"] = "version_scope_review"
        return result

    if loc_record.get("canonical_id") == pronom_record.get("canonical_id"):
        result["status"] = "already_reconciled_authoritatively"
        return result

    result["status"] = "bridge_candidate_authority_confirmed"
    return result


def verify_review_entries(entries: list[dict[str, Any]], store) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    results = [
        result
        for entry in entries
        if (result := verify_pronom_candidate(entry, store)) is not None
    ]

    one_to_one_eligible_statuses = {
        "bridge_candidate_authority_confirmed",
        "already_reconciled_authoritatively",
    }
    by_puid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        if result.get("status") in one_to_one_eligible_statuses and result.get("puid"):
            by_puid[str(result["puid"])].append(result)

    for puid, rows in by_puid.items():
        if len(rows) <= 1:
            continue
        related_fdd_ids = sorted(str(row.get("fdd_id") or "") for row in rows if row.get("fdd_id"))
        for row in rows:
            row["pre_scope_status"] = row.get("status")
            row["status"] = "many_to_one_scope_review"
            row["related_fdd_ids"] = related_fdd_ids
            row["scope_reason"] = "More than one non-broad LOC FDD row maps to the same PRONOM PUID; granularity must be reviewed before exact-identity projection."

    counts = Counter(str(result.get("status") or "unknown") for result in results)
    summary = {
        "candidate_count": len(results),
        "status_counts": dict(sorted(counts.items())),
        "identity_bridges_approved": 0,
        "verification_policy": "read_only_authority_and_scope_confirmation_no_identity_projection",
    }
    return results, summary


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m registry_builder.loc_fdd_pronom_verify",
        description=(
            "Verify LOC direct-single PRONOM crosswalk candidates against the current persistent registry. "
            "This command is read-only and never approves or writes identity bridges."
        ),
    )
    parser.add_argument("--review", required=True, help="LOC crosswalk review JSON")
    parser.add_argument("--config", default="config/sources.qnl.loc-only.json", help="Registry config containing storage settings")
    parser.add_argument("--out", default="loc-fdd-pronom-verification.json", help="Verification detail JSON")
    args = parser.parse_args()

    review_entries = json.loads(Path(args.review).read_text(encoding="utf-8"))
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    store = create_store(config.get("storage") or {})
    try:
        results, summary = verify_review_entries(review_entries, store)
    finally:
        store.close()

    out_path = Path(args.out)
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    payload = {
        "status": "ok",
        "review_file": args.review,
        "config_file": args.config,
        "output_file": str(out_path),
        **summary,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
