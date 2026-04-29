from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable

_registry: dict[str, Callable] = {}


def register_constraint(type_name: str) -> Callable:
    """Decorator that registers a constraint plugin under *type_name*."""
    def decorator(fn: Callable) -> Callable:
        _registry[type_name] = fn
        return fn
    return decorator


def get_plugin(type_name: str) -> Callable | None:
    return _registry.get(type_name)


def discover_plugins() -> None:
    """Auto-discover plugins in projarvis.planner.l2.plugins via pkgutil."""
    from projarvis.planner.l2 import plugins
    for _, mod_name, _ in pkgutil.iter_modules(plugins.__path__, plugins.__name__ + "."):
        importlib.import_module(mod_name)
