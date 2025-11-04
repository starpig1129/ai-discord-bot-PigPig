import os
import yaml
import asyncio
import sys
from dotenv import load_dotenv

from function import func
class TOKENS:
    def __init__(self) -> None:
        load_dotenv()
        self.token = os.getenv("TOKEN")
        self.client_id = os.getenv("CLIENT_ID")
        self.client_secret_id = os.getenv("CLIENT_SECRET_ID")
        self.sercet_key = os.getenv("SERCET_KEY")
        raw_bug_report_channel_id = os.getenv("BUG_REPORT_CHANNEL_ID")
        self.bug_report_channel_id = int(raw_bug_report_channel_id) if raw_bug_report_channel_id not in (None, "") else None
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY",None)
        self.openai_api_key = os.getenv("OPENAI_API_KEY",None)
        self.gemini_api_key = os.getenv("GEMINI_API_KEY",None)
        self.tenor_api_key = os.getenv("TENOR_API_KEY",None)

        self.bot_owner_id = int(os.getenv("BOT_OWNER_ID", 0))

                # 驗證環境變數
        self._validate_environment_variables()

    def _validate_environment_variables(self) -> None:
        """驗證所有必要的環境變數是否存在且有效"""
        missing_vars = []
        invalid_vars = []

        # 檢查必要環境變數
        required_vars = {
            "TOKEN": self.token,
            "CLIENT_ID": self.client_id,
            "CLIENT_SECRET_ID": self.client_secret_id,
            "SERCET_KEY": self.sercet_key,
            "BUG_REPORT_CHANNEL_ID": os.getenv("BUG_REPORT_CHANNEL_ID"),
            "BOT_OWNER_ID": os.getenv("BOT_OWNER_ID")
        }

        for var_name, var_value in required_vars.items():
            if not var_value:
                missing_vars.append(var_name)
            elif var_name == "BUG_REPORT_CHANNEL_ID":
                try:
                    int(var_value)
                except (ValueError, TypeError):
                    invalid_vars.append(f"{var_name} (必須為有效的整數)")

        # 檢查 API 金鑰（可選但建議設定）
        optional_api_keys = {
            "ANTHROPIC_API_KEY": self.anthropic_api_key,
            "OPENAI_API_KEY": self.openai_api_key,
            "GEMINI_API_KEY": self.gemini_api_key
        }

        for api_name, api_value in optional_api_keys.items():
            if not api_value:
                print(f"警告：{api_name} 未設定，可能影響相關功能")

        # 如果有缺失或無效的環境變數，終止程式
        if missing_vars or invalid_vars:
            error_msg = "環境變數驗證失敗：\n"

            if missing_vars:
                error_msg += f"缺失的環境變數：{', '.join(missing_vars)}\n"

            if invalid_vars:
                error_msg += f"無效的環境變數：{', '.join(invalid_vars)}\n"

            error_msg += "\n請檢查 .env 檔案並設定所有必要的環境變數。"

            print(error_msg)
            sys.exit(1)

def _load_yaml_file(path: str) -> dict:
    """安全讀取 YAML 檔案，失敗時回報錯誤並回傳空 dict"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        return data
    except Exception as e:
        try:
            # 使用一致的錯誤回報機制
            asyncio.create_task(func.report_error(e, "addons/settings.py/_load_yaml_file"))
        except Exception:
            # 若無法使用 func.report_error 則 fallback 到 stdout（不得發生，但保險處理）
            print(f"載入 YAML 檔案失敗 ({path}): {e}")
        return {}

class BaseConfig:
    """對應 config/base.yaml 的設定物件"""
    def __init__(self, path: str = "config/base.yaml") -> None:
        self.path = path
        data = _load_yaml_file(path)
        # 直接對應常用欄位，若未設定則使用合理預設（非用來逃避錯誤）
        self.prefix: str = data.get("prefix", "/")
        self.activity: list = data.get("activity", [])
        self.ipc_server: dict = data.get("ipc_server", {})
        self.version: str = data.get("version", "")
        self.music_temp_base: str = data.get("music_temp_base", "./temp/music")
        self.logging: dict = data.get("logging", {})

class LLMConfig:
    """對應 config/llm.yaml 的設定物件"""
    def __init__(self, path: str = "config/llm.yaml") -> None:
        self.path = path
        self.data: dict = _load_yaml_file(path)

class UpdateConfig:
    """對應 config/update.yaml 的設定物件"""
    def __init__(self, path: str = "config/update.yaml") -> None:
        self.path = path
        data = _load_yaml_file(path)
        self.auto_update: dict = data.get("auto_update", {})
        self.security: dict = data.get("security", {})
        self.restart: dict = data.get("restart", {})
        self.github: dict = data.get("github", {})

# 快速示範：根據 config 目錄現有檔名建立實例（使用時可移動到適當初始化位置）
# from addons.settings import BaseConfig, LLMConfig, UpdateConfig
# base_cfg = BaseConfig("config/base.yaml")
# llm_cfg = LLMConfig("config/llm.yaml")
# update_cfg = UpdateConfig("config/update.yaml")
