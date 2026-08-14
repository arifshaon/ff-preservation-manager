from __future__ import annotations

import argparse
import json
from pathlib import Path

from registry_builder.pipeline import run_pipeline
from registry_builder.validate import validate_registry
from registry_builder.models import CanonicalFormat


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

    args = parser.parse_args()

    if args.command == "run":
        report = run_pipeline(args.config, args.workdir, args.out, offline=args.offline)
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif args.command == "validate":
        rows = json.loads(Path(args.registry).read_text(encoding="utf-8"))
        registry = [CanonicalFormat(**row) for row in rows]
        errors, warnings = validate_registry(registry)
        print(json.dumps({"errors": errors, "warnings": warnings}, indent=2))
        if errors:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
