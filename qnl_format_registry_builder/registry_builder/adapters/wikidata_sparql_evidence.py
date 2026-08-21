from __future__ import annotations

from registry_builder.adapters.wikidata_sparql import (
    WIKIDATA_POPULATION_POLICY_VERSION,
    WikidataSparqlAdapter,
)
from registry_builder.models import RawFormatRecord, SourceSnapshot


WIKIDATA_EVIDENCE_PROJECTION_VERSION = "2026-08-21-v2-evidence-only"
WIKIDATA_RELATIONSHIP_PROJECTION_VERSION = "2026-08-21-v1-authority-cross-reference"
WIKIDATA_RECORD_SOURCE_TYPE = "wikidata_sparql"


class WikidataSparqlEvidenceAdapter(WikidataSparqlAdapter):
    """Production Wikidata adapter with a hard evidence-only identity boundary.

    Acquisition is inherited unchanged from :class:`WikidataSparqlAdapter`,
    including frozen policy-v3 population discovery, VALUES batching, resumable
    snapshots and offline replay. Extraction projects the acquired CSV into the
    source-native model but forces every record to ``evidence_only``.

    Wikidata QIDs remain verified *source identities*. PRONOM/LOC/NARA values
    copied from Wikidata remain unverified assertions. The adapter never creates
    canonical identity, promotes copied identifiers, or generates risk/criterion
    claims. Canonical cross-registry attachment is handled separately through
    governed ``source_relationship_claims``.
    """

    type_name = "wikidata_sparql_evidence"

    def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
        # Lazy import avoids a module-import cycle: wikidata_projection imports
        # policy constants from the acquisition adapter.
        from registry_builder.wikidata_projection import project_wikidata_csv

        records: list[RawFormatRecord] = []
        seen_qids: set[str] = set()

        for snapshot in snapshots:
            projected = project_wikidata_csv(
                snapshot.local_path,
                source_id=self.source_id,
                source_type=WIKIDATA_RECORD_SOURCE_TYPE,
            )
            for record in projected:
                qid = str(record.source_record_id or "")
                if not qid:
                    raise ValueError("Projected Wikidata record is missing source_record_id")
                if qid in seen_qids:
                    raise ValueError(
                        f"Duplicate Wikidata QID {qid!r} across extraction snapshots"
                    )
                seen_qids.add(qid)

                # Production identity boundary. Semantic wikidata_role remains in
                # native_fields/category, but no Wikidata row participates in
                # canonical identity grouping.
                record.record_role = "evidence_only"
                record.risk_assessments = []

                native = dict(record.native_fields or {})
                native.update(
                    {
                        "population_policy_version": WIKIDATA_POPULATION_POLICY_VERSION,
                        "identity_projection": False,
                        "identifier_promotion": False,
                        "evidence_projection_version": WIKIDATA_EVIDENCE_PROJECTION_VERSION,
                        "relationship_projection_version": WIKIDATA_RELATIONSHIP_PROJECTION_VERSION,
                        "production_adapter_type": self.type_name,
                    }
                )
                record.native_fields = native
                records.append(record)

        return records
