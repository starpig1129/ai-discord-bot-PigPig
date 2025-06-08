"""Discord Bot Cogs 模組

本模組包含 PigPig Discord LLM Bot 的所有功能擴展（Cogs），
包括記憶系統、音樂播放、圖片生成、數學計算等功能。

主要子模組：
- memory: 永久頻道記憶系統
- music: 音樂播放系統
- eat: 餐廳推薦系統
- system_prompt: 系統提示管理
"""

__version__ = "1.0.0"

# 導出主要模組（可選，根據需要調整）
__all__ = [
    "memory",
    "music", 
    "eat",
    "system_prompt"
]