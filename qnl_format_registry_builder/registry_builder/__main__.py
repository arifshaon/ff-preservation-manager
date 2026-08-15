from __future__ import annotations

import argparse
import json
from pathlib import Path

from registry_builder.collision_report import build_collision_report
from registry_builder.pipeline import run_pipeline
from registry_builder.validate import validate_registry
from registry_builder.models import CanonicalFormat


def _load_registry(path: str | Path) -> list[CanonicalFormat]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    return [CanonicalFormat(**row) for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser(prog="registry-builder")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run the registry-building pipeline")
    run.add_argument("--config", required=True)
    run.add_argument("--workdir", default="work")
    run.add_argument("--out", default="out")
    run.add_argument("--offline", action="store_true", help="Use cached source snapshots only; do not fetch remote sources")

    val = sub.add_parser("validate", help="Validate a generated registry.json")
    val.add_argument("--registry", required=True)

    collision = sub.add_parser("collision-report", help="Report identifier collisions and heuristic bridges")
    collision.add_argument("--registry", required=True)
    collision.add_argument("--sample-limit", type=int, default=50)

    args = parser.parse_args()

    if args.command == "run":
        report = run_pipeline(args.config, args.workdir, args.out, offline=args.offline)
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif args.command == "validate":
        registry = _load_registry(args.registry)
        errors, warnings = validate_registry(registry)
        print(json.dumps({"errors": errors, "warnings": warnings}, indent=2))
        if errors:
            raise SystemExit(1)
    elif args.command == "collision-report":
        registry = _load_registry(args.registry)
        report = build_collision_report(registry, sample_limit=args.sample_limit)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        if report.get("status") == "error":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
