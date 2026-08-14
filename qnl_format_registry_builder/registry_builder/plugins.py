from __future__ import annotations

import importlib
from functools import lru_cache
from typing import Any


def _registered_names(registry: dict[str, Any]) -> str:
    return ", ".join(sorted(registry))


@lru_cache(maxsize=None)
def resolve_dotted_path(spec: str) -> Any:
    """Resolve an external plugin spec in explicit ``module:ClassName`` form.

    The colon form is required because ``module.ClassName`` is ambiguous: it can
    mean either a module path or a class attribute. Importing a plugin executes
    that module's top-level code, so plugin config must be treated as trusted
    configuration.
    """
    module_name, sep, attr = spec.rpartition(":")
    if not sep or not module_name or not attr:
        raise ValueError(
            f"Plugin spec must be a registered short name or an explicit 'package.module:ClassName' path, got: {spec!r}"
        )

    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        # If the module being imported, or one of its parent packages, is absent,
        # the plugin path is wrong. If some other module is absent, the plugin
        # exists but one of its dependencies is missing.
        missing = exc.name or ""
        if missing == module_name or module_name.startswith(f"{missing}."):
            raise ValueError(f"Plugin module {module_name!r} not found for {spec!r}.") from exc
        raise ImportError(
            f"Plugin {spec!r} failed to import: {exc}. The plugin module exists but one of its dependencies is missing."
        ) from exc

    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise ValueError(f"Module {module_name!r} has no attribute {attr!r} for plugin {spec!r}.") from exc


def resolve_plugin(
    spec: str,
    registry: dict[str, Any],
    *,
    plugin_kind: str = "plugin",
    expected_base: type | None = None,
) -> Any:
    """Resolve and validate a built-in short name or external plugin class.

    Short names keep built-in configuration stable. ``module:Class`` specs let
    third-party adapters and storage backends be shipped outside this repository
    without editing core registry dictionaries. If ``expected_base`` is supplied,
    the resolved object must be a class and a subclass of that base.
    """
    if spec in registry:
        resolved = registry[spec]
    else:
        try:
            resolved = resolve_dotted_path(spec)
        except (ValueError, ImportError) as exc:
            registered = _registered_names(registry)
            raise type(exc)(
                f"{exc} Registered {plugin_kind} short names: [{registered}]. External plugins must use 'package.module:ClassName'."
            ) from exc

    if expected_base is not None:
        if not isinstance(resolved, type) or not issubclass(resolved, expected_base):
            raise TypeError(
                f"{plugin_kind} {spec!r} resolved to {resolved!r}, which is not a subclass of {expected_base.__name__}"
            )
    return resolved


def build_registry(classes: list[type], *, plugin_kind: str = "plugin") -> dict[str, type]:
    """Build a short-name registry and fail on duplicate ``type_name`` values."""
    registry: dict[str, type] = {}
    for cls in classes:
        type_name = getattr(cls, "type_name", None)
        if not type_name:
            raise ValueError(f"{plugin_kind} class {cls!r} must define type_name")
        if type_name in registry:
            raise ValueError(
                f"Duplicate {plugin_kind} type_name {type_name!r}: {registry[type_name].__name__} and {cls.__name__}"
            )
        registry[type_name] = cls
    return registry
