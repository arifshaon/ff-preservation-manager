from __future__ import annotations

from registry_builder.adapters.nara_digital_preservation_framework import NaraDigitalPreservationFrameworkAdapter


class NaraPreservationCsvAdapter(NaraDigitalPreservationFrameworkAdapter):
    """Deprecated compatibility alias for NARA CSV retrieval.

    New configurations should use `nara_digital_preservation_framework`, which
    is the source-level adapter. CSV is only the currently implemented retrieval
    mode for the NARA Digital Preservation Framework source.
    """

    type_name = "nara_preservation_csv"
