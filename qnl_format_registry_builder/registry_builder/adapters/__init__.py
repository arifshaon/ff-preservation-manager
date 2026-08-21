from __future__ import annotations

from registry_builder.adapters.base import SourceAdapter
from registry_builder.adapters.standard_json import StandardJsonAdapter
from registry_builder.adapters.pronom_registry import PronomRegistryAdapter
from registry_builder.adapters.pronom_droid_xml import PronomDroidXmlAdapter
from registry_builder.adapters.loc_fdd_xml import LocFddXmlAdapter
from registry_builder.adapters.loc_fdd_xml_reviewed import LocFddXmlReviewedAdapter
from registry_builder.adapters.loc_fdd_mapping_csv import LocFddMappingCsvAdapter
from registry_builder.adapters.loc_fdd_pronom_bridge import LocFddPronomBridgeAdapter
from registry_builder.adapters.institution_policy_xlsx import InstitutionPolicyXlsxAdapter
from registry_builder.adapters.qnl_institution_format_evidence import QnlInstitutionFormatEvidenceAdapter
from registry_builder.adapters.qnl_policy_xlsx import QnlPolicyXlsxAdapter
from registry_builder.adapters.nara_digital_preservation_framework import NaraDigitalPreservationFrameworkAdapter
from registry_builder.adapters.nara_preservation_csv import NaraPreservationCsvAdapter
from registry_builder.adapters.wikidata_sparql import WikidataSparqlAdapter
from registry_builder.adapters.wikidata_sparql_evidence import WikidataSparqlEvidenceAdapter
from registry_builder.adapters.dpc_bit_list import DpcBitListAdapter
from registry_builder.plugins import build_registry, resolve_plugin

ADAPTERS: dict[str, type[SourceAdapter]] = build_registry(
    [
        StandardJsonAdapter,
        PronomRegistryAdapter,
        PronomDroidXmlAdapter,
        LocFddXmlAdapter,
        LocFddXmlReviewedAdapter,
        LocFddMappingCsvAdapter,
        LocFddPronomBridgeAdapter,
        InstitutionPolicyXlsxAdapter,
        QnlInstitutionFormatEvidenceAdapter,
        NaraDigitalPreservationFrameworkAdapter,
        WikidataSparqlAdapter,
        WikidataSparqlEvidenceAdapter,
        DpcBitListAdapter,
        # Deprecated compatibility aliases. Prefer source-level adapter names.
        NaraPreservationCsvAdapter,
        # Deprecated compatibility alias. Prefer institution_policy_xlsx.
        QnlPolicyXlsxAdapter,
    ],
    plugin_kind="source adapter",
)


def resolve_adapter(source_type: str) -> type[SourceAdapter]:
    return resolve_plugin(source_type, ADAPTERS, plugin_kind="source adapter", expected_base=SourceAdapter)
