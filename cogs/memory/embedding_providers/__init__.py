# Package initializer for embedding providers
# This module will auto-import any provider modules placed in this package
# so that they can register themselves via register_embedding_provider.

import importlib
import pkgutil
from typing import List, Callable, Optional

# Ensure decorator is importable for provider modules (they will call it)
from ..vector.manager import register_embedding_provider  # noqa: F401
from addons.logging import get_logger
logger = get_logger(server_id="system", source=__name__)

def _import_all_providers() -> None:
    """
    Import all modules in this package so that registration decorators run.
    Provider modules should call register_embedding_provider when defined.
    """
    package = __name__
    for finder, name, ispkg in pkgutil.iter_modules(__path__):
        full_name = f"{package}.{name}"
        try:
            importlib.import_module(full_name)
            logger.debug(f"Imported embedding provider module: {full_name}")
        except Exception as e:
            logger.exception(f"Failed to import embedding provider {full_name}: {e}")

_import_all_providers()

def list_providers() -> List[str]:
    """Return registered embedding provider names."""
    try:
        from .. import vector_manager as _vm
        registry = getattr(_vm, "_embedding_providers", {})
        return list(registry.keys())
    except Exception:
        logger.exception("Failed to list embedding providers")
        return []

def get_provider_factory(name: str) -> Optional[Callable]:
    """Return the factory callable for a given provider name, or None if not found."""
    try:
        from .. import vector_manager as _vm
        registry = getattr(_vm, "_embedding_providers", {})
        return registry.get(name)
    except Exception:
        logger.exception(f"Failed to get provider factory {name}")
        return None