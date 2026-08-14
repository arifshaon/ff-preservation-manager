from __future__ import annotations

from registry_builder.adapters.institution_policy_xlsx import (
    InstitutionPolicyXlsxAdapter,
    _candidate_headers,
    _field,
    _find_header_row,
    _get,
    _norm_header,
    _read_sheet_rows,
    _resolve_field_map,
)


class QnlPolicyXlsxAdapter(InstitutionPolicyXlsxAdapter):
    """Deprecated compatibility alias for QNL's institutional policy workbook.

    New configurations should use `institution_policy_xlsx` with
    `institution_id`, `institution_name`, and a source-specific `field_map`.
    This alias remains so existing QNL configs do not break immediately.
    """

    type_name = "qnl_policy_xlsx"
