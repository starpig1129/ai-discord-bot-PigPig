"""ModelManager: 讀取 config/llm.yaml 並依據 agent_type 回傳 ModelFallbackMiddleware。"""
from __future__ import annotations

import asyncio
from typing import List, Tuple
import logging

from langchain.agents.middleware import ModelFallbackMiddleware

from addons import settings
from function import func
from utils.logger import LoggerMixin


class ModelManager(LoggerMixin):
    """管理 LLM 模型優先順序，從設定檔取得並建立 ModelFallbackMiddleware"""

    def __init__(self) -> None:
        LoggerMixin.__init__(self, "model_manager")
        self._load_config()

    def _load_config(self) -> None:
        try:
            # 從 addons.settings 的 llm_config 取得 model_priorities
            self.priorities = settings.llm_config.model_priorities or {}
            self.info("Model priorities loaded successfully", category="CONFIGURATION")
        except Exception as e:
            self.error(f"Failed to load llm_config: {e}", category="CONFIGURATION", function_name="_load_config", exc_info=e)
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
            self.error(f"Failed to resolve priority list for agent_type '{agent_type}': {e}", category="CONFIGURATION", function_name="_resolve_priority_list", exc_info=e)
            try:
                asyncio.create_task(func.report_error(e, "llm/model_manager.py/_resolve_priority_list"))
            except Exception:
                print(f"llm/model_manager.py/_resolve_priority_list error: {e}")
            return []

    def get_model(self, agent_type: str) -> Tuple[str, ModelFallbackMiddleware]:
        """公開方法，回傳 (primary_model, ModelFallbackMiddleware)。

        若找不到對應的 model_priorities，會丟出 ValueError 以避免呼叫端誤解包 None。
        同時在發生錯誤時會使用 func.report_error 上報錯誤以便集中化日誌管理。
        """
        # 先解析 priorities 並記錄，便於後續排查
        priorities = self._resolve_priority_list(agent_type)

        if not priorities:
            err = ValueError(f"No model priorities configured for agent_type '{agent_type}'")
            self.error(f"No model priorities configured for agent_type '{agent_type}'", category="CONFIGURATION", function_name="get_model", guild_id=None, user_id=None)
            try:
                # 非同步上報錯誤，不要阻塞呼叫流程
                asyncio.create_task(func.report_error(err, "llm/model_manager.py/get_model"))
            except Exception:
                logging.exception("Failed to schedule func.report_error for missing model priorities")
            # 明確丟出例外，讓呼叫端能夠判斷並處理
            raise err

        try:
            primary = priorities[0]
            fallback_mw = ModelFallbackMiddleware(*priorities[1:])  # type: ignore[arg-type]
            self.info(f"Successfully created model fallback middleware for agent_type '{agent_type}' with primary: {primary}", category="MODEL_MANAGEMENT", function_name="get_model")
            return primary, fallback_mw
        except Exception as e:
            self.error(f"Failed to create ModelFallbackMiddleware for agent_type '{agent_type}': {e}", category="MODEL_MANAGEMENT", function_name="get_model", exc_info=e)
            try:
                asyncio.create_task(func.report_error(e, "llm/model_manager.py/get_model"))
            except Exception:
                logging.exception("Failed to schedule func.report_error for ModelFallbackMiddleware error")
            # 保留原始例外以便上層取得詳細錯誤資訊
            raise


__all__ = ["ModelManager"]