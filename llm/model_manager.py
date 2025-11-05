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
from langchain.chat_models import BaseChatModel
from function import func
from addons.settings import llm_config


class ModelManager:
    """Manage discovery and access to available LLM providers.
 
    This manager additionally loads model/provider priority configuration from
    the project's LLM config (via addons.settings.llm_config) and exposes helper
    methods that select providers according to that priority. On provider
    invocation failures the manager will attempt the next provider in the
    configured order and report errors via func.report_error.
    """
 
    def __init__(self) -> None:
        """Initialize manager, load providers and priorities."""
        self.providers: Dict[str, BaseProvider] = {}
        # model_priorities is loaded from addons.settings.llm_config and kept as-is.
        # The config structure is expected to be a mapping from agent_type -> list
        # (each list element typically a dict like {"google": ["gemini-pro"]}).
        self.model_priorities = llm_config.model_priorities or {}
        self._load_providers()
 
    def _load_providers(self) -> None:
        """Discover and instantiate provider classes in llm.provider."""
        try:
            package_path = provider_pkg.__path__
        except Exception as e:
            asyncio.create_task(
                func.report_error(e, "llm.providers: unable to access llm.provider package")
            )
            return
 
        for finder, name, ispkg in pkgutil.iter_modules(package_path):
            module_name = f"{provider_pkg.__name__}.{name}"
            try:
                module = importlib.import_module(module_name)
            except Exception as e:
                asyncio.create_task(
                    func.report_error(e, f"llm.providers: failed to import module {module_name}")
                )
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
 
                # store by provider name (e.g. "google", "openai")
                self.providers[name_key] = instance
 
    def list_providers(self) -> List[str]:
        """Return list of loaded provider names."""
        return list(self.providers.keys())
 
    def get_model(self, agent_type: str) -> Optional[BaseChatModel]:
        """Return an instantiated chat model according to configured priorities.
 
        The method consults llm_config.model_priorities for the given agent_type and
        attempts providers in order. For each configured provider entry it will:
          - locate the provider instance by name (from self.providers)
          - if the entry lists specific model names, prefer a provider whose
            provider.model_name matches one of those
          - call provider.get_chat_model() if available to obtain the underlying
            chat model (this is required for some providers like Google)
 
        On provider or model invocation errors the exception is reported via
        func.report_error and the next provider is tried. If no provider can be
        returned, None is returned.
        """
        # Safely obtain priority list for agent_type from loaded config
        try:
            priorities = {}
            if isinstance(self.model_priorities, dict):
                priorities = self.model_priorities
            else:
                # Defensive: if model_priorities is not a mapping, try to use it as-is
                # but treat as empty mapping for our purposes.
                priorities = {}
        except Exception as e:
            asyncio.create_task(func.report_error(e, "llm.providers: invalid model_priorities"))
            priorities = {}
 
        entries = priorities.get(agent_type) or []
 
        # Helper to attempt a provider instance and return its chat model (or None)
        def _attempt_provider(provider_name: str, allowed_models: Optional[List[str]] = None):
            prov = self.providers.get(provider_name)
            if prov is None:
                # provider not loaded
                asyncio.create_task(
                    func.report_error(
                        ValueError(f"provider '{provider_name}' not loaded"),
                        f"llm.providers:get_provider - provider '{provider_name}' not available",
                    )
                )
                return None
            # If allowed_models specified, check the provider's model_name
            try:
                model_name = getattr(prov, "model_name", None)
            except Exception as e:
                asyncio.create_task(func.report_error(e, f"llm.providers:get_provider reading model_name for {provider_name}"))
                return None
 
            if allowed_models:
                # allowed_models might be a single string or list depending on YAML parsing.
                if isinstance(allowed_models, str):
                    allowed = [allowed_models]
                else:
                    allowed = list(allowed_models)
                if model_name not in allowed:
                    # skip this provider as model name not allowed
                    return None
 
            # Prefer provider.get_chat_model() when available
            try:
                getter = getattr(prov, "get_chat_model", None)
                if callable(getter):
                    return getter()
                return prov
            except Exception as e:
                asyncio.create_task(func.report_error(e, f"llm.providers:get_provider failed to obtain chat model from {provider_name}"))
                return None
 
        # Iterate configured entries in order
        for entry in entries:
            # Each entry is typically a dict like {"google": ["gemini-pro"]} or {"ollama": None}
            if isinstance(entry, dict):
                for provider_name, models in entry.items():
                    result = _attempt_provider(provider_name, models)
                    if result is not None:
                        return result
            elif isinstance(entry, str):
                # Direct provider name specified
                result = _attempt_provider(entry, None)
                if result is not None:
                    return result
            else:
                # unexpected entry type; report and continue
                asyncio.create_task(func.report_error(ValueError(f"invalid priority entry: {entry}"), "llm.providers:get_provider"))
 
        # No configured priorities matched or none configured for this agent_type.
        # Fallback to any loaded provider in the default load order.
        for provider_name in self.list_providers():
            result = _attempt_provider(provider_name, None)
            if result is not None:
                return result
 
        # nothing found
        return None