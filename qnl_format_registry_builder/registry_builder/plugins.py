from __future__ import annotations

import importlib
from typing import Any


def resolve_dotted_path(spec: str) -> Any:
    """Resolve ``module:ClassName`` or ``module.ClassName`` plugin specs."""
    module_name, sep, attr = spec.rpartition(":")
    if not sep:
        module_name, sep, attr = spec.rpartition(".")
    if not module_name or not attr:
        raise ValueError(
            f"Plugin spec must be a registered short name or a dotted path such as 'package.module:ClassName', got: {spec!r}"
        )
    module = importlib.import_module(module_name)
    return getattr(module, attr)


def resolve_plugin(spec: str, registry: dict[str, Any], *, plugin_kind: str = "plugin") -> Any:
    """Resolve a short registered name or a dotted external plugin class path.

    Short names keep built-in configuration stable. Dotted paths let third-party
    adapters and storage backends be shipped outside this repository without
    editing core registry dictionaries.
    """
    if spec in registry:
        return registry[spec]
    try:
        return resolve_dotted_path(spec)
    except Exception as exc:
        registered = ", ".join(sorted(registry))
        raise ValueError(
            f"Could not resolve {plugin_kind} {spec!r}. Use one of the registered short names [{registered}] "
            "or a dotted path like 'mypkg.module:ClassName'."
        ) from exc
