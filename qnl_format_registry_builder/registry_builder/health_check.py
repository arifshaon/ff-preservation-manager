"""Post-run checks that the registry holds the properties it is supposed to.

`validate` checks a registry's structure. This checks the *invariants* that make
one-source-at-a-time ingestion trustworthy, each of which corresponds to a way
the pipeline has actually gone wrong:

- claims must point at canonicals that exist       (they used to dangle)
- reconciliation must not depend on ingestion order (it used to)
- adding an authority must not undo merges          (it used to)
- unendorsed claims must not act as identifiers     (they used to)
- unresolved ambiguity must be reported, not silent

Run it after ingesting a source. It reads the store and the exports; it never
writes anything.
"""

from __future__ import annotations

import random
from typing import Any

from registry_builder.collision_report import build_collision_report
from registry_builder.models import CanonicalFormat


def _check(name: str, passed: bool, detail: str, **extra: Any) -> dict[str, Any]:
    return {"check": name, "status": "pass" if passed else "FAIL", "detail": detail, **extra}


def _skipped(name: str, detail: str) -> dict[str, Any]:
    """A check that could not run reports SKIP, never pass.

    Reporting an unrun check as passing is worse than not having the check:
    it answers "did this hold?" with "yes" when the answer is "nobody looked".
    """
    return {"check": name, "status": "SKIP", "detail": detail}


def check_claims_point_at_live_canonicals(
    registry: list[dict[str, Any]],
    claims: list[dict[str, Any]],
) -> dict[str, Any]:
    live = {row.get("canonical_id") for row in registry}
    stale: dict[str, int] = {}
    for claim in claims:
        if claim.get("canonical_id") not in live:
            source = str(claim.get("source_id") or "unknown")
            stale[source] = stale.get(source, 0) + 1
    total = sum(stale.values())
    return _check(
        "claims_point_at_live_canonicals",
        total == 0,
        f"{total} of {len(claims)} claim(s) reference a canonical_id that is not in the registry",
        stale_by_source=stale,
    )


def check_every_source_is_represented(
    registry: list[dict[str, Any]],
    claims: list[dict[str, Any]],
) -> dict[str, Any]:
    """Every source contributing records should still have claims in the export."""
    record_sources = {
        str(ref.get("source_id"))
        for row in registry
        for ref in (row.get("source_records") or [])
        if ref.get("source_id")
    }
    claim_sources = {str(c.get("source_id")) for c in claims if c.get("source_id")}
    missing = sorted(record_sources - claim_sources)
    return _check(
        "every_source_is_represented",
        not missing,
        (
            "sources with records but no exported claims: " + ", ".join(missing)
            if missing
            else f"all {len(record_sources)} contributing source(s) have claims"
        ),
        sources_with_records=sorted(record_sources),
        missing_from_claims=missing,
    )


def check_reconciliation_is_order_independent(
    source_records: list[Any],
    reconcile_fn,
    *,
    shuffles: int = 3,
) -> dict[str, Any]:
    """Re-reconcile the same records in different orders and compare assignments."""
    if not source_records:
        return _skipped(
            "reconciliation_is_order_independent",
            "no stored source records were loaded; pass --storage-config pointing at the config you ran",
        )

    def assignment(records):
        return {
            (ref["source_id"], ref["source_record_id"]): fmt.canonical_id
            for fmt in reconcile_fn(records)
            for ref in fmt.source_records
        }

    baseline = assignment(list(source_records))
    worst = 0
    for seed in range(shuffles):
        shuffled = list(source_records)
        random.Random(seed).shuffle(shuffled)
        other = assignment(shuffled)
        worst = max(worst, sum(1 for key in baseline if baseline[key] != other.get(key)))
    return _check(
        "reconciliation_is_order_independent",
        worst == 0,
        f"{worst} record(s) landed on a different canonical when re-run in a shuffled order"
        f" (over {shuffles} shuffles of {len(source_records)} records)",
        records_tested=len(source_records),
    )


def check_unendorsed_claims_are_not_identifiers(registry: list[dict[str, Any]]) -> dict[str, Any]:
    """An unendorsed claim is evidence; it must not appear as one of the format's ids."""
    leaked: list[dict[str, Any]] = []
    for row in registry:
        identifiers = row.get("identifiers") or {}
        for claim in row.get("identifier_claims") or []:
            if claim.get("endorsed") is not False:
                continue
            if claim.get("value") in (identifiers.get(claim.get("kind")) or []):
                leaked.append({
                    "canonical_id": row.get("canonical_id"),
                    "kind": claim.get("kind"),
                    "value": claim.get("value"),
                })
    unendorsed = sum(
        1 for row in registry for c in (row.get("identifier_claims") or []) if c.get("endorsed") is False
    )
    return _check(
        "unendorsed_claims_are_not_identifiers",
        not leaked,
        f"{len(leaked)} unendorsed claim(s) leaked into the identifier map"
        f" ({unendorsed} unendorsed claim(s) retained as evidence)",
        unendorsed_claims=unendorsed,
        leaked=leaked[:10],
    )


def summarise_cross_authority_merges(registry: list[dict[str, Any]]) -> dict[str, Any]:
    """Not pass/fail — the number to watch as sources are added."""
    pairs: dict[str, int] = {}
    multi = 0
    for row in registry:
        sources = sorted({str(r.get("source_id")) for r in (row.get("source_records") or []) if r.get("source_id")})
        if len(sources) > 1:
            multi += 1
            for i, left in enumerate(sources):
                for right in sources[i + 1:]:
                    pairs[f"{left} + {right}"] = pairs.get(f"{left} + {right}", 0) + 1
    return {
        "canonical_formats": len(registry),
        "canonicals_with_multiple_sources": multi,
        "merges_by_source_pair": dict(sorted(pairs.items())),
    }


def run_health_check(
    registry: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    *,
    source_records: list[Any] | None = None,
    reconcile_fn=None,
    canonical_objects: list[CanonicalFormat] | None = None,
    shuffles: int = 3,
) -> dict[str, Any]:
    checks = [
        check_claims_point_at_live_canonicals(registry, claims),
        check_every_source_is_represented(registry, claims),
        check_unendorsed_claims_are_not_identifiers(registry),
    ]
    if source_records is not None and reconcile_fn is not None:
        checks.append(
            check_reconciliation_is_order_independent(source_records, reconcile_fn, shuffles=shuffles)
        )
    else:
        checks.append(_skipped(
            "reconciliation_is_order_independent",
            "not run; pass --storage-config to enable it",
        ))

    failed = [c for c in checks if c["status"] == "FAIL"]
    skipped = [c for c in checks if c["status"] == "SKIP"]
    report: dict[str, Any] = {
        "status": "FAIL" if failed else ("incomplete" if skipped else "ok"),
        "checks": checks,
        "merges": summarise_cross_authority_merges(registry),
    }
    if canonical_objects is not None:
        collisions = build_collision_report(canonical_objects, sample_limit=5)
        # Ambiguity is expected; the point is that it is counted rather than silent.
        report["needs_review"] = {
            "heuristic_identifier_bridges": collisions["summary"]["heuristic_identifier_bridges"],
            "ambiguous_identifier_citations": collisions["summary"]["ambiguous_identifier_citations"],
            "verified_strong_identifier_conflicts": collisions["summary"]["verified_strong_identifier_conflicts"],
        }
    return report


def format_health_check(report: dict[str, Any]) -> str:
    lines = [f"registry health: {report['status']}", ""]
    for check in report["checks"]:
        lines.append(f"  [{check['status']:4s}] {check['check']}")
        lines.append(f"         {check['detail']}")
    merges = report["merges"]
    lines += ["", f"  canonical formats: {merges['canonical_formats']}",
              f"  canonicals drawing on more than one source: {merges['canonicals_with_multiple_sources']}"]
    for pair, count in merges["merges_by_source_pair"].items():
        lines.append(f"      {pair}: {count}")
    if "needs_review" in report:
        lines += ["", "  needs review (expected, but must not be silent):"]
        for key, value in report["needs_review"].items():
            lines.append(f"      {key}: {value}")
    return "\n".join(lines)
