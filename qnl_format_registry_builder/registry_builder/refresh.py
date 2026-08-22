from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from typing import Any, Sequence

from registry_builder.pipeline import run_pipeline


def _load_config(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Registry configuration must contain a JSON object.")
    return data


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _selected_config(config: dict[str, Any], source_ids: list[str]) -> tuple[dict[str, Any], list[str]]:
    sources = config.get("sources") or []
    if not isinstance(sources, list):
        raise ValueError("Registry configuration sources must be an array.")
    available = [str(source.get("id") or "") for source in sources if isinstance(source, dict) and source.get("id")]
    unknown = sorted(set(source_ids) - set(available))
    if unknown:
        raise ValueError(
            "Unknown source ID(s): " + ", ".join(unknown) + ". Available: " + ", ".join(available)
        )

    selected = dict(config)
    selected["incremental_source_updates"] = True
    selected["sources"] = [
        ({**source, "enabled": str(source.get("id") or "") in source_ids} if isinstance(source, dict) else source)
        for source in sources
    ]
    return selected, available


def _compact_report(
    report: dict[str, Any],
    requested: list[str],
    *,
    base_config_path: str | None = None,
    base_config_sha256: str | None = None,
) -> dict[str, Any]:
    source_rows = [
        row for row in report.get("sources") or []
        if isinstance(row, dict) and str(row.get("source_id") or "") in set(requested)
    ]
    return {
        "status": report.get("status"),
        "run_id": report.get("run_id"),
        "started_at": report.get("started_at"),
        "finished_at": report.get("finished_at"),
        "base_config_path": base_config_path,
        "base_config_sha256": base_config_sha256,
        "incremental_source_updates": report.get("incremental_source_updates"),
        "requested_source_ids": requested,
        "refreshed_source_ids": sorted(
            str(row.get("source_id"))
            for row in source_rows
            if row.get("status") == "completed" and row.get("source_id")
        ),
        "source_results": source_rows,
        "raw_records_extracted": report.get("raw_records_extracted"),
        "prior_source_records_reused": report.get("stored_source_records_used_for_augmentation"),
        "active_source_records": report.get("active_source_records"),
        "canonical_formats": report.get("canonical_formats"),
        "change_detection": report.get("change_detection"),
        "risk_claim_materialization": report.get("risk_claim_materialization"),
        "criterion_mapping": {
            key: (report.get("criterion_mapping") or {}).get(key)
            for key in ("enabled", "claims_generated", "mapping_versions", "source_claim_status")
            if key in (report.get("criterion_mapping") or {})
        },
        "outputs": report.get("outputs") or [],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m registry_builder.refresh",
        description=(
            "Refresh selected configured evidence sources while reusing the latest successful evidence from all "
            "other sources. This is an incremental update, not a fresh registry installation."
        ),
    )
    parser.add_argument("--config", required=True, help="Existing reviewed registry-builder configuration.")
    parser.add_argument("--source", dest="source_ids", action="append", required=True, help="Source ID to refresh. Repeat as needed.")
    parser.add_argument("--workdir", default="work")
    parser.add_argument("--out", default="out")
    parser.add_argument("--offline", action="store_true", help="Replay cached snapshots only; cannot discover new upstream data.")
    parser.add_argument("--report", help="Optional path for the compact refresh report JSON.")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress messages on stderr.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    config_path = Path(args.config).expanduser().resolve()
    if not config_path.is_file():
        raise SystemExit(f"Config not found: {config_path}")
    config_hash = _sha256_file(config_path)
    config = _load_config(config_path)
    requested: list[str] = []
    for value in args.source_ids:
        source_id = str(value or "").strip()
        if source_id and source_id not in requested:
            requested.append(source_id)
    try:
        selected, _ = _selected_config(config, requested)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    # The temporary config is deliberately created beside the reviewed config so
    # every existing relative path (criteria, mappings, source files, etc.) keeps
    # exactly the same resolution semantics. It is deleted after the run.
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".refresh.json",
            prefix=".registry-",
            dir=config_path.parent,
            delete=False,
        ) as handle:
            json.dump(selected, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            temporary_path = Path(handle.name)

        def progress(event: dict[str, Any]) -> None:
            if args.quiet:
                return
            name = event.get("event")
            source_id = event.get("source_id")
            if name in {"source_started", "source_completed", "source_failed"}:
                print(
                    f"[refresh] {name}: {source_id or ''} "
                    f"{event.get('status') or event.get('error') or ''}".rstrip(),
                    file=sys.stderr,
                    flush=True,
                )
            elif name in {"change_detection_completed", "run_completed"}:
                print(f"[refresh] {name}: {json.dumps(event, default=str)}", file=sys.stderr, flush=True)

        report = run_pipeline(
            temporary_path,
            args.workdir,
            args.out,
            offline=bool(args.offline),
            progress=progress,
        )
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

    compact = _compact_report(
        report,
        requested,
        base_config_path=str(config_path),
        base_config_sha256=config_hash,
    )
    text = json.dumps(compact, indent=2, ensure_ascii=False, sort_keys=True)
    if args.report:
        report_path = Path(args.report).expanduser()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
