from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from registry_builder.adapters import resolve_adapter
from registry_builder.identifier_rules import load_identifier_rules
from registry_builder.models import SourceSnapshot, utc_now_iso
from registry_builder.pipeline import _storage_config, load_config
from registry_builder.storage import create_store
from registry_builder.storage.base import RegistryStore
from registry_builder.wikidata_refresh import (
    DEFAULT_CONFIG,
    PRODUCTION_ADAPTER_TYPE,
    _load_refresh_config,
    run_wikidata_refresh,
)
from registry_builder.wikidata_relationship_backfill import (
    WIKIDATA_SOURCE_ID,
    _current_source_claims,
    _resolve_relative,
)


_AUTHORITY_FIELDS = (
    ("puid", "puid"),
    ("locFdd", "loc"),
    ("naraFormatPlanId", "nara"),
)
_FINGERPRINT_COLLECTIONS = (
    "runs",
    "source_snapshots",
    "source_records",
    "canonical_formats",
    "source_relationship_claims",
)


def _split_pipe(value: str | None) -> list[str]:
    return [part.strip() for part in str(value or "").split("|") if part.strip()]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _collection_fingerprint(store: RegistryStore) -> str:
    digest = hashlib.sha256()
    for collection in _FINGERPRINT_COLLECTIONS:
        rows = store.query(collection)
        rendered = sorted(
            json.dumps(row, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
            for row in rows
        )
        digest.update(collection.encode("utf-8"))
        digest.update(b"\n")
        for row in rendered:
            digest.update(row.encode("utf-8"))
            digest.update(b"\n")
    return digest.hexdigest()


def build_remove_one_relationship_snapshot(
    input_csv: str | Path,
    output_csv: str | Path,
    *,
    eligible_qids: set[str] | None = None,
) -> tuple[SourceSnapshot, dict[str, Any]]:
    """Clone a Wikidata CSV and remove one resolvable single authority assertion.

    The selected row must contain exactly one copied PRONOM/LOC/NARA identifier in
    total. When ``eligible_qids`` is supplied, the row must also belong to that
    set. The production simulation supplies only QIDs that currently own exactly
    one governed relationship claim, making the expected one-edge removal
    deterministic even if an authority namespace ever contains duplicate owners.
    """

    source = Path(input_csv)
    target = Path(output_csv)
    target.parent.mkdir(parents=True, exist_ok=True)

    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = [{str(k): str(v or "") for k, v in row.items()} for row in reader]

    if "qid" not in fieldnames:
        raise ValueError(f"Wikidata CSV is missing required 'qid' column: {source}")
    missing = [field for field, _ in _AUTHORITY_FIELDS if field not in fieldnames]
    if missing:
        raise ValueError(
            "Wikidata CSV is missing authority field(s) required for simulation: "
            + ", ".join(missing)
        )

    mutation: dict[str, Any] | None = None
    for row in rows:
        authority_values: list[tuple[str, str, str]] = []
        for field, kind in _AUTHORITY_FIELDS:
            authority_values.extend((field, kind, value) for value in _split_pipe(row.get(field)))
        if len(authority_values) != 1:
            continue
        qid = str(row.get("qid") or "").strip()
        if not qid:
            continue
        if eligible_qids is not None and qid not in eligible_qids:
            continue
        field, kind, value = authority_values[0]
        row[field] = ""
        mutation = {
            "qid": qid,
            "field": field,
            "identifier_kind": kind,
            "identifier_value_removed": value,
        }
        break

    if mutation is None:
        qualifier = " with exactly one current governed relationship" if eligible_qids is not None else ""
        raise ValueError(
            "No Wikidata row with exactly one copied PRONOM/LOC/NARA identifier"
            + qualifier
            + " was available for the changed-source simulation"
        )

    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    digest = _sha256_file(target)
    snapshot = SourceSnapshot(
        source_id=WIKIDATA_SOURCE_ID,
        source_type=PRODUCTION_ADAPTER_TYPE,
        uri=f"simulation://remove-one-authority/{mutation['qid']}",
        acquired_at=utc_now_iso(),
        sha256=digest,
        local_path=str(target),
        content_type="text/csv",
        note="read-only changed-source simulation",
        changed=True,
        from_cache=False,
        metadata={
            "simulation": True,
            "simulation_mode": "remove_one_copied_authority_identifier",
            **mutation,
        },
    )
    return snapshot, mutation


def run_wikidata_changed_source_simulation(
    *,
    store: RegistryStore,
    source_config: dict[str, Any],
    workdir: str | Path,
    output_csv: str | Path,
    identifier_rules: dict[str, dict[str, Any]] | None = None,
    require_verified_baseline: bool = True,
    max_unmatched_authority_claims: int = 0,
    drift_gates: dict[str, Any] | None = None,
    base_snapshots: list[SourceSnapshot] | None = None,
) -> dict[str, Any]:
    """Run a deterministic changed-source preflight with no registry writes."""

    source = dict(source_config)
    source.setdefault("id", WIKIDATA_SOURCE_ID)
    source.setdefault("type", PRODUCTION_ADAPTER_TYPE)
    source["offline"] = True

    adapter_cls = resolve_adapter(PRODUCTION_ADAPTER_TYPE)
    adapter = adapter_cls(source, Path(workdir))
    acquired = list(base_snapshots) if base_snapshots is not None else adapter.acquire()
    if len(acquired) != 1:
        raise ValueError(
            "Wikidata changed-source simulation requires exactly one cached final snapshot; "
            f"received {len(acquired)}"
        )
    base_snapshot = acquired[0]

    current_claims = _current_source_claims(store)
    relationship_counts = Counter(
        str(row.get("source_record_id") or "")
        for row in current_claims
        if row.get("source_record_id")
    )
    eligible_qids = {
        qid for qid, count in relationship_counts.items()
        if qid and count == 1
    }
    if not eligible_qids:
        raise ValueError(
            "No current Wikidata QID has exactly one governed relationship claim; "
            "cannot construct deterministic one-edge simulation"
        )

    before_fingerprint = _collection_fingerprint(store)
    simulated_snapshot, mutation = build_remove_one_relationship_snapshot(
        base_snapshot.local_path,
        output_csv,
        eligible_qids=eligible_qids,
    )

    preflight = run_wikidata_refresh(
        store=store,
        source_config=source,
        workdir=workdir,
        identifier_rules=identifier_rules,
        apply=False,
        require_verified_baseline=require_verified_baseline,
        max_unmatched_authority_claims=max_unmatched_authority_claims,
        drift_gates=drift_gates,
        snapshots=[simulated_snapshot],
    )
    after_fingerprint = _collection_fingerprint(store)

    baseline = preflight.get("baseline_verification") or {}
    preview = preflight.get("preview") or {}
    turnover = preflight.get("claim_turnover") or {}
    errors: list[str] = []

    if preflight.get("status") != "ready" or not preflight.get("gate_passed"):
        errors.append(
            "Changed-source simulation preflight did not reach ready state: "
            + "; ".join(str(item) for item in (preflight.get("gate_errors") or []))
        )
    if int(preflight.get("records_acquired") or 0) != int(baseline.get("wikidata_source_records") or 0):
        errors.append("Simulation unexpectedly changed the Wikidata population count")
    if int(turnover.get("added") or 0) != 0:
        errors.append(f"Simulation expected 0 relationship additions, got {turnover.get('added')}")
    if int(turnover.get("removed") or 0) != 1:
        errors.append(f"Simulation expected exactly 1 relationship removal, got {turnover.get('removed')}")
    if int(turnover.get("turnover") or 0) != 1:
        errors.append(f"Simulation expected claim turnover 1, got {turnover.get('turnover')}")
    expected_edges = int(baseline.get("wikidata_relationship_claims") or 0) - 1
    if int(preview.get("relationship_edges") or 0) != expected_edges:
        errors.append(
            f"Simulation expected {expected_edges} relationship edges, "
            f"got {preview.get('relationship_edges')}"
        )
    if int(preview.get("canonical_formats") or 0) != int(baseline.get("canonical_formats") or 0):
        errors.append("Simulation changed the canonical format count")
    if int(preview.get("unmatched_authority_claims") or 0) != 0:
        errors.append(
            f"Simulation produced unmatched authority claims: {preview.get('unmatched_authority_claims')}"
        )
    for key in (
        "identity_merges_performed",
        "canonical_formats_created",
        "canonical_identifiers_promoted",
    ):
        if int(preview.get(key) or 0) != 0:
            errors.append(f"Simulation violated identity invariant {key}: {preview.get(key)}")
    if before_fingerprint != after_fingerprint:
        errors.append("Registry fingerprint changed during read-only simulation")

    return {
        "status": "ok" if not errors else "failed",
        "errors": errors,
        "simulation_mode": "remove_one_copied_authority_identifier",
        "registry_writes_performed": 0 if before_fingerprint == after_fingerprint else None,
        "registry_fingerprint_unchanged": before_fingerprint == after_fingerprint,
        "eligible_single_relationship_qids": len(eligible_qids),
        "base_snapshot": {
            "local_path": base_snapshot.local_path,
            "sha256": base_snapshot.sha256,
        },
        "simulated_snapshot": {
            "local_path": simulated_snapshot.local_path,
            "sha256": simulated_snapshot.sha256,
        },
        "mutation": mutation,
        "preflight": preflight,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m registry_builder.wikidata_refresh_simulation",
        description=(
            "Run a deterministic changed-Wikidata-source simulation against the current "
            "registry. This command is preflight-only and has no apply/write mode."
        ),
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--workdir", default="work")
    parser.add_argument(
        "--out-csv",
        default="out/wikidata-refresh-simulated-change.csv",
        help="Location for the mutated simulation-only Wikidata CSV",
    )
    parser.add_argument("--out")
    args = parser.parse_args()

    config = _load_refresh_config(args.config)
    pipeline_config_path = _resolve_relative(config["_config_path"], config["storage_config"])
    pipeline_config = load_config(pipeline_config_path)
    rules = load_identifier_rules(pipeline_config.get("identifier_kinds"))

    source_config = dict(config.get("source") or {})
    source_config.setdefault("id", WIKIDATA_SOURCE_ID)
    source_config.setdefault("type", PRODUCTION_ADAPTER_TYPE)
    source_config["offline"] = True

    store = create_store(_storage_config(pipeline_config))
    try:
        report = run_wikidata_changed_source_simulation(
            store=store,
            source_config=source_config,
            workdir=args.workdir,
            output_csv=args.out_csv,
            identifier_rules=rules,
            require_verified_baseline=bool(config.get("require_verified_baseline", True)),
            max_unmatched_authority_claims=int(
                config.get("max_unmatched_authority_claims", 0)
            ),
            drift_gates=dict(config.get("drift_gates") or {}),
        )
    finally:
        store.close()

    text = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)

    if report.get("status") != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
