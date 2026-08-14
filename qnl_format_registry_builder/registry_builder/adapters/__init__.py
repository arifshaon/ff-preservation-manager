from __future__ import annotations

from registry_builder.adapters.base import SourceAdapter
from registry_builder.adapters.standard_json import StandardJsonAdapter
from registry_builder.adapters.pronom_registry import PronomRegistryAdapter
from registry_builder.adapters.pronom_droid_xml import PronomDroidXmlAdapter
from registry_builder.adapters.loc_fdd_xml import LocFddXmlAdapter
from registry_builder.adapters.institution_policy_xlsx import InstitutionPolicyXlsxAdapter
from registry_builder.adapters.qnl_policy_xlsx import QnlPolicyXlsxAdapter
from registry_builder.adapters.nara_digital_preservation_framework import NaraDigitalPreservationFrameworkAdapter
from registry_builder.adapters.nara_preservation_csv import NaraPreservationCsvAdapter

ADAPTERS: dict[str, type[SourceAdapter]] = {
    StandardJsonAdapter.type_name: StandardJsonAdapter,
    PronomRegistryAdapter.type_name: PronomRegistryAdapter,
    PronomDroidXmlAdapter.type_name: PronomDroidXmlAdapter,
    LocFddXmlAdapter.type_name: LocFddXmlAdapter,
    InstitutionPolicyXlsxAdapter.type_name: InstitutionPolicyXlsxAdapter,
    NaraDigitalPreservationFrameworkAdapter.type_name: NaraDigitalPreservationFrameworkAdapter,
    # Deprecated compatibility aliases. Prefer source-level adapter names.
    NaraPreservationCsvAdapter.type_name: NaraPreservationCsvAdapter,
    # Deprecated compatibility alias. Prefer institution_policy_xlsx.
    QnlPolicyXlsxAdapter.type_name: QnlPolicyXlsxAdapter,
}
