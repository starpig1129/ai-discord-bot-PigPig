# 暴露 addons 的主要型別與單例，使用延遲匯入避免循環依賴
from .settings import base_config, llm_config, update_config
from .tokens import TOKENS, tokens

__all__ = [
    "base_config",
    "llm_config",
    "update_config",
    "TOKENS",
    "tokens",
]