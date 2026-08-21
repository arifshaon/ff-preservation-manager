from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from registry_builder.adapters.base import SourceAdapter
from registry_builder.models import Identifier, RawFormatRecord, SourceSnapshot


class LocFddPronomBridgeAdapter(SourceAdapter):
    """Project only policy-approved LOC↔PRONOM bridge assertions.

    The LOC FDD identifier is authoritative because the bridge originates from
    an official LOC crosswalk. The copied PUID is deliberately unverified so
    PRONOM remains the authority for the PUID namespace. These records are used
    only after the corresponding LOC and PRONOM authority records have already
    been verified in the persistent registry.
    """

    type_name = "loc_fdd_pronom_bridge"

    def acquire(self) -> list[SourceSnapshot]:
        local_file = self.config.get("local_file") or self.config.get("uri")
        if not local_file:
            raise ValueError("loc_fdd_pronom_bridge requires local_file or uri")
        return [
            self.acquire_file_snapshot(
                str(local_file),
                suffix=".json",
                note="policy-approved LOC-PRONOM identity bridges",
                metadata={
                    "source_location": "approved_mapping_file",
                    "identity_projection": True,
                    "snapshot_policy": "cache",
                    "snapshot_retained": True,
                },
            )
        ]

    def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
        records: list[RawFormatRecord] = []
        for snapshot in snapshots:
            payload = json.loads(Path(snapshot.local_path).read_text(encoding="utf-8"))
            mapping_version = str(payload.get("mapping_version") or "")
            approval_policy = str(payload.get("approval_policy") or "")
            for rule in payload.get("rules") or []:
                if str(rule.get("review_status") or "") != "approved_by_policy":
                    continue
                fdd_id = str(rule.get("fdd_id") or "").strip().lower()
                puid = str(rule.get("puid") or "").strip().lower()
                if not fdd_id or not puid:
                    continue
                source_record_id = str(rule.get("rule_id") or rule.get("source_record_id") or f"{fdd_id}:{puid}")
                records.append(RawFormatRecord(
                    source_id=self.source_id,
                    source_type=self.type_name,
                    source_record_id=source_record_id,
                    record_role="format_identity",
                    name=rule.get("title"),
                    identifiers=[
                        Identifier("loc", fdd_id, "loc_fdd_mapping_csv", True, source_record_id),
                        Identifier("puid", puid, "loc_fdd_mapping_csv", False, source_record_id),
                    ],
                    urls={
                        "loc_fdd_mapping": str(rule.get("crosswalk_source_url") or "")
                    } if rule.get("crosswalk_source_url") else {},
                    evidence=[{
                        "type": "loc_fdd_pronom_approved_identity_bridge",
                        "mapping_version": mapping_version,
                        "approval_policy": approval_policy,
                        "approval_basis": list(rule.get("approval_basis") or []),
                        "mapping_date": rule.get("mapping_date"),
                        "crosswalk_snapshot_sha256": rule.get("crosswalk_snapshot_sha256"),
                        "identity_projection": True,
                        "puid_verified": False,
                    }],
                    native_fields={
                        "bridge_mapping": {
                            "fdd_id": fdd_id,
                            "puid": puid,
                            "mapping_version": mapping_version,
                            "approval_policy": approval_policy,
                            "mapping_context": dict(rule.get("mapping_context") or {}),
                            "loc_canonical_id_at_review": rule.get("loc_canonical_id_at_review"),
                            "pronom_canonical_id_at_review": rule.get("pronom_canonical_id_at_review"),
                        }
                    },
                    raw={
                        "snapshot_sha256": snapshot.sha256,
                        "rule": dict(rule),
                    },
                ))
        return records
