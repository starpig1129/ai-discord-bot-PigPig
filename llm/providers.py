"""Provider manager for dynamic discovery of LLM providers.

This module discovers provider modules under the llm.provider package and
instantiates classes that inherit from BaseProvider.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil
import asyncio

from typing import Dict, List, Optional

import llm.provider as provider_pkg
from llm.provider.base import BaseProvider
from langchain_core.chat_models import BaseChatModel
from function import func


class ProviderManager:
    """Manage discovery and access to available LLM providers."""

    def __init__(self):
        """Initialize manager and load providers."""
        self.providers: Dict[str, BaseProvider] = {}
        self._load_providers()

    def _load_providers(self) -> None:
        """Discover and instantiate provider classes in llm.provider."""
        try:
            package_path = provider_pkg.__path__
        except Exception as e:
            asyncio.create_task(func.report_error(e, "llm.providers: unable to access llm.provider package"))
            return

        for finder, name, ispkg in pkgutil.iter_modules(package_path):
            module_name = f"{provider_pkg.__name__}.{name}"
            try:
                module = importlib.import_module(module_name)
            except Exception as e:
                asyncio.create_task(func.report_error(e, f"llm.providers: failed to import module {module_name}"))
                continue

            for _, obj in inspect.getmembers(module, inspect.isclass):
                if obj is BaseProvider:
                    continue
                if not issubclass(obj, BaseProvider):
                    continue
                # Ensure the class was defined in this module to avoid duplicates.
                if obj.__module__ != module.__name__:
                    continue

                try:
                    instance = obj()
                except Exception as e:
                    asyncio.create_task(
                        func.report_error(
                            e,
                            f"llm.providers: failed to instantiate provider {obj.__name__} in {module_name}",
                        )
                    )
                    continue

                try:
                    name_key = instance.provider_name
                except Exception as e:
                    asyncio.create_task(
                        func.report_error(e, f"llm.providers: provider {obj.__name__} missing provider_name")
                    )
                    continue

                if not isinstance(name_key, str) or not name_key:
                    asyncio.create_task(
                        func.report_error(
                            ValueError("invalid provider_name"),
                            f"llm.providers: provider {obj.__name__} has invalid provider_name",
                        )
                    )
                    continue

                self.providers[name_key] = instance

    def get_provider(self, name: str) -> Optional[BaseProvider]:
        """Return provider instance by name or None if not found."""
        return self.providers.get(name)

    def list_providers(self) -> List[str]:
        """Return list of loaded provider names."""
        return list(self.providers.keys())