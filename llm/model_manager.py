"""ModelManager: 讀取 config/llm.yaml 並依據 agent_type 回傳 ModelFallbackMiddleware。"""
from __future__ import annotations

import asyncio
from typing import List, Optional, Any

from langchain.agents.middleware import ModelFallbackMiddleware

from addons import settings
from function import func


class ModelManager:
    """管理 LLM 模型優先順序，從設定檔取得並建立 ModelFallbackMiddleware"""

    def __init__(self) -> None:
        self._load_config()

    def _load_config(self) -> None:
        try:
            # 從 addons.settings 的 llm_config 取得 model_priorities
            self.priorities = settings.llm_config.model_priorities or {}
        except Exception as e:
            try:
                asyncio.create_task(func.report_error(e, "llm/model_manager.py/_load_config"))
            except Exception:
                print(f"llm/model_manager.py: failed to load llm_config: {e}")
            self.priorities = {}

    def _resolve_priority_list(self, agent_type: str) -> List[str]:
        """將設定檔中指定的 agent_type 轉成 provider:model 字串清單，順序保留"""
        try:
            if not self.priorities:
                return []
            # 支援 dict 或 list 結構
            entries = self.priorities.get(agent_type) if isinstance(self.priorities, dict) else None
            if entries is None and isinstance(self.priorities, list):
                # 如果 model_priorities 是 list，嘗試搜尋 list 中的 dict 項
                for item in self.priorities:
                    if isinstance(item, dict) and agent_type in item:
                        entries = item[agent_type]
                        break
            if entries is None:
                return []
            result: List[str] = []
            # entries 預期為 list of dicts: [{google: [..]}, {ollama: [..]}, ...]
            for provider_entry in entries:
                if isinstance(provider_entry, dict):
                    for provider, models in provider_entry.items():
                        if models is None:
                            continue
                        for model in models:
                            result.append(f"{provider}:{model}")
            return result
        except Exception as e:
            try:
                asyncio.create_task(func.report_error(e, "llm/model_manager.py/_resolve_priority_list"))
            except Exception:
                print(f"llm/model_manager.py/_resolve_priority_list error: {e}")
            return []

    def get_model(self, agent_type: str) -> Optional[Any]:
        """公開方法，回傳 ModelFallbackMiddleware 或 None

        Args:
            agent_type: 如 'info_model' 或 'message_model'

        Returns:
            ModelFallbackMiddleware 或 None（找不到設定或建立失敗時）
        """
        try:
            priorities = self._resolve_priority_list(agent_type)
            if not priorities:
                return None
            return priorities[0], ModelFallbackMiddleware(*priorities[1:])  # type: ignore[return-value]
        except Exception as e:
            try:
                asyncio.create_task(func.report_error(e, "llm/model_manager.py/get_model"))
            except Exception:
                print(f"llm/model_manager.py/get_model error: {e}")
            return None


__all__ = ["ModelManager"]