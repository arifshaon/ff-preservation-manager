from __future__ import annotations

from registry_builder.adapters.base import SourceAdapter
from registry_builder.adapters.standard_json import StandardJsonAdapter
from registry_builder.adapters.pronom_droid_xml import PronomDroidXmlAdapter
from registry_builder.adapters.loc_fdd_xml import LocFddXmlAdapter
from registry_builder.adapters.institution_policy_xlsx import InstitutionPolicyXlsxAdapter
from registry_builder.adapters.qnl_policy_xlsx import QnlPolicyXlsxAdapter

ADAPTERS: dict[str, type[SourceAdapter]] = {
    StandardJsonAdapter.type_name: StandardJsonAdapter,
    PronomDroidXmlAdapter.type_name: PronomDroidXmlAdapter,
    LocFddXmlAdapter.type_name: LocFddXmlAdapter,
    InstitutionPolicyXlsxAdapter.type_name: InstitutionPolicyXlsxAdapter,
    # Deprecated compatibility alias. Prefer institution_policy_xlsx.
    QnlPolicyXlsxAdapter.type_name: QnlPolicyXlsxAdapter,
}
