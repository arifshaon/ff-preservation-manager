from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

POLICY_ID = "loc_pronom_one_to_one_authority_v2"
APPROVABLE_STATUS = "bridge_candidate_authority_confirmed"
_BROAD_FORMAT_MARKERS = ("family", "generic", "unspecified", "all versions", "multiple versions")


def _is_broad_format_name(name: str | None) -> bool:
    text = str(name or "").strip().lower()
    return any(marker in text for marker in _BROAD_FORMAT_MARKERS)


def build_bridge_mapping(
    verification_results: list[dict[str, Any]],
    review_entries: list[dict[str, Any]],
    *,
    mapping_date: str,
) -> dict[str, Any]:
    review_by_id = {
        str(entry.get("source_record_id") or ""): entry
        for entry in review_entries
        if entry.get("source_record_id")
    }
    rules: list[dict[str, Any]] = []
    excluded = Counter()
    excluded_relationships: list[dict[str, Any]] = []

    eligible: list[dict[str, Any]] = []
    for result in verification_results:
        status = str(result.get("status") or "unknown")
        if status != APPROVABLE_STATUS:
            excluded[status] += 1
            continue
        title = str(result.get("title") or result.get("loc_preferred_name") or "")
        if _is_broad_format_name(title):
            excluded["broad_scope_review"] += 1
            excluded_relationships.append({
                "source_record_id": result.get("source_record_id"),
                "fdd_id": result.get("fdd_id"),
                "puid": result.get("puid"),
                "title": title,
                "status": "broad_scope_review",
                "reason": "LOC description is explicitly family/generic/broad and must not be projected as exact PRONOM identity.",
            })
            continue
        eligible.append(result)

    by_puid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in eligible:
        puid = str(result.get("puid") or "").strip().lower()
        if puid:
            by_puid[puid].append(result)

    many_to_one_puids = {puid for puid, rows in by_puid.items() if len(rows) > 1}

    for result in eligible:
        source_record_id = str(result.get("source_record_id") or "")
        review = review_by_id.get(source_record_id) or {}
        fdd_id = str(result.get("fdd_id") or "").strip().lower()
        puid = str(result.get("puid") or "").strip().lower()
        if not fdd_id or not puid:
            excluded["invalid_shape"] += 1
            continue
        if puid in many_to_one_puids:
            related_fdd_ids = sorted(
                str(row.get("fdd_id") or "").strip().lower()
                for row in by_puid[puid]
                if row.get("fdd_id")
            )
            excluded["many_to_one_scope_review"] += 1
            excluded_relationships.append({
                "source_record_id": source_record_id,
                "fdd_id": fdd_id,
                "puid": puid,
                "title": result.get("title") or review.get("title"),
                "status": "many_to_one_scope_review",
                "related_fdd_ids": related_fdd_ids,
                "reason": "More than one non-broad LOC FDD row claims the same PRONOM PUID; granularity must be reviewed before identity projection.",
            })
            continue
        rules.append({
            "rule_id": f"{POLICY_ID}:{fdd_id}:{puid}",
            "review_status": "approved_by_policy",
            "approval_policy": POLICY_ID,
            "approval_basis": [
                "LOC crosswalk has one PUID in the dedicated PRONOM_PUID field",
                "LOC mapping review classified the row as direct_single_candidate",
                "authoritative LOC FDD identity exists in the persistent registry",
                "authoritative PRONOM PUID identity exists in the persistent registry",
                "no conflicting or asymmetric version signal was detected",
                "LOC title is not explicitly family/generic/broad",
                "the PUID occurs in exactly one non-broad approvable LOC row in this policy set",
            ],
            "mapping_date": mapping_date,
            "source_record_id": source_record_id,
            "title": result.get("title") or review.get("title"),
            "fdd_id": fdd_id,
            "puid": puid,
            "loc_canonical_id_at_review": result.get("loc_canonical_id"),
            "pronom_canonical_id_at_review": result.get("pronom_canonical_id"),
            "crosswalk_source_url": review.get("source_url"),
            "crosswalk_snapshot_sha256": review.get("snapshot_sha256"),
            "mapping_context": dict(review.get("mapping_context") or {}),
            "identity_projection": True,
            "puid_verified": False,
        })

    rules.sort(key=lambda rule: (rule["fdd_id"], rule["puid"]))
    excluded_relationships.sort(key=lambda item: (str(item.get("status") or ""), str(item.get("puid") or ""), str(item.get("fdd_id") or "")))
    snapshot_hashes = sorted({
        str(rule.get("crosswalk_snapshot_sha256"))
        for rule in rules
        if rule.get("crosswalk_snapshot_sha256")
    })
    return {
        "mapping_version": f"{POLICY_ID}-{mapping_date}",
        "mapping_date": mapping_date,
        "approval_policy": POLICY_ID,
        "review_status": "approved_by_policy",
        "policy_notes": (
            "Machine-policy approval only; not a claim of individual human review. "
            "Only direct-single, non-broad, globally one-to-one LOC-to-PRONOM mappings confirmed against both authority records and without version-scope conflict are projected."
        ),
        "crosswalk_snapshot_sha256": snapshot_hashes[0] if len(snapshot_hashes) == 1 else snapshot_hashes,
        "approved_rule_count": len(rules),
        "excluded_status_counts": dict(sorted(excluded.items())),
        "excluded_relationship_count": len(excluded_relationships),
        "excluded_relationships": excluded_relationships,
        "rules": rules,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m registry_builder.loc_fdd_pronom_bridge_approve",
        description="Create a policy-approved LOC-to-PRONOM bridge mapping from reviewed verification results.",
    )
    parser.add_argument("--verification", required=True, help="Read-only verifier detail JSON")
    parser.add_argument("--review", required=True, help="LOC crosswalk review JSON")
    parser.add_argument("--mapping-date", default="20260713")
    parser.add_argument("--out", required=True, help="Output approved bridge mapping JSON")
    args = parser.parse_args()

    verification = json.loads(Path(args.verification).read_text(encoding="utf-8"))
    review = json.loads(Path(args.review).read_text(encoding="utf-8"))
    mapping = build_bridge_mapping(verification, review, mapping_date=args.mapping_date)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "ok",
        "output_file": str(out_path),
        "mapping_version": mapping["mapping_version"],
        "approved_rule_count": mapping["approved_rule_count"],
        "excluded_status_counts": mapping["excluded_status_counts"],
        "excluded_relationship_count": mapping["excluded_relationship_count"],
        "approval_policy": mapping["approval_policy"],
        "puid_ownership": "copied assertion remains verified=false; PRONOM remains authoritative",
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
