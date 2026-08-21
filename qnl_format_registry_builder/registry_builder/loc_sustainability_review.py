from __future__ import annotations

from collections import Counter
import argparse
import json
from pathlib import Path
from typing import Any


FACTOR_TO_CRITERION = {
    "disclosure": "sustainability.disclosure",
    "adoption": "sustainability.adoption",
    "transparency": "sustainability.transparency_readability",
    "self_documentation": "sustainability.self_documentation",
    "external_dependencies": "sustainability.external_dependencies",
    "impact_of_patents": "sustainability.ip_licensing",
    "technical_protection_mechanisms": "sustainability.tpm_encryption",
}


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if isinstance(value, dict):
                records.append(value)
    return records


def _read_claims(path: str | Path) -> list[dict[str, Any]]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    raise ValueError("criterion claims file must contain a JSON array")


def review_loc_sustainability_preview(
    raw_records: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    *,
    unmatched_sample_limit: int = 10,
) -> dict[str, Any]:
    claim_records_by_criterion: dict[str, set[str]] = {}
    claim_values_by_criterion: dict[str, Counter[str]] = {}
    for claim in claims:
        criterion = str(claim.get("criterion_id") or "")
        source_record_id = str(claim.get("source_record_id") or "")
        if criterion:
            claim_records_by_criterion.setdefault(criterion, set())
            claim_values_by_criterion.setdefault(criterion, Counter())
            if source_record_id:
                claim_records_by_criterion[criterion].add(source_record_id)
            claim_values_by_criterion[criterion][str(claim.get("value") or "unknown")] += 1

    factors: dict[str, Any] = {}
    for factor, criterion in FACTOR_TO_CRITERION.items():
        present: list[tuple[str, str]] = []
        for record in raw_records:
            source_record_id = str(record.get("source_record_id") or "")
            native = record.get("native_fields") or {}
            sustainability = native.get("sustainability_factors") or {}
            value = sustainability.get(factor) if isinstance(sustainability, dict) else None
            if value not in (None, ""):
                present.append((source_record_id, str(value)))

        claimed_ids = claim_records_by_criterion.get(criterion, set())
        unmatched = [(record_id, value) for record_id, value in present if record_id not in claimed_ids]
        factors[factor] = {
            "criterion_id": criterion,
            "records_with_factor": len(present),
            "records_with_claim": len({record_id for record_id, _ in present if record_id in claimed_ids}),
            "records_unmapped": len(unmatched),
            "coverage_percent": round((len(present) - len(unmatched)) * 100.0 / len(present), 2) if present else 0.0,
            "claim_value_counts": dict(sorted(claim_values_by_criterion.get(criterion, Counter()).items())),
            "unmapped_samples": [
                {"source_record_id": record_id, "source_value": value}
                for record_id, value in unmatched[:unmatched_sample_limit]
            ],
        }

    return {
        "status": "ok",
        "raw_record_count": len(raw_records),
        "criterion_claim_count": len(claims),
        "factor_count": len(FACTOR_TO_CRITERION),
        "factors": factors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review fresh LOC sustainability extraction against preview criterion claims.")
    parser.add_argument("--raw-records", required=True, help="Path to preview raw_records.jsonl")
    parser.add_argument("--claims", required=True, help="Path to preview criterion_claims.json")
    parser.add_argument("--out", help="Optional JSON review output path")
    parser.add_argument("--sample-limit", type=int, default=10, help="Unmapped sample count per factor")
    args = parser.parse_args(argv)

    report = review_loc_sustainability_preview(
        _read_jsonl(args.raw_records),
        _read_claims(args.claims),
        unmatched_sample_limit=max(0, args.sample_limit),
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
