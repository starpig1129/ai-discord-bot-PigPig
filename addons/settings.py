import os
import yaml
import asyncio
import sys
from dotenv import load_dotenv
from function import func

# 載入 .env
load_dotenv()


class TOKENS:
    def __init__(self) -> None:
        self.token = os.getenv("TOKEN")
        self.client_id = os.getenv("CLIENT_ID")
        self.client_secret_id = os.getenv("CLIENT_SECRET_ID")
        self.sercet_key = os.getenv("SERCET_KEY")
        raw_bug_report_channel_id = os.getenv("BUG_REPORT_CHANNEL_ID")
        self.bug_report_channel_id = int(raw_bug_report_channel_id) if raw_bug_report_channel_id not in (None, "") else None
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", None)
        self.openai_api_key = os.getenv("OPENAI_API_KEY", None)
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", None)
        self.tenor_api_key = os.getenv("TENOR_API_KEY", None)

        bot_owner_raw = os.getenv("BOT_OWNER_ID")
        try:
            self.bot_owner_id = int(bot_owner_raw) if bot_owner_raw not in (None, "") else 0
        except (ValueError, TypeError):
            self.bot_owner_id = 0

        # 驗證環境變數
        self._validate_environment_variables()

    def _validate_environment_variables(self) -> None:
        """驗證所有必要的環境變數是否存在且有效，若失敗則使用 func.report_error 回報並終止程式"""
        missing_vars = []
        invalid_vars = []

        # 必要環境變數（直接檢查實際使用的值）
        required_vars = {
            "TOKEN": self.token,
            "CLIENT_ID": self.client_id,
            "CLIENT_SECRET_ID": self.client_secret_id,
            "SERCET_KEY": self.sercet_key,
            "BUG_REPORT_CHANNEL_ID": os.getenv("BUG_REPORT_CHANNEL_ID"),
            "BOT_OWNER_ID": os.getenv("BOT_OWNER_ID"),
        }

        for var_name, var_value in required_vars.items():
            if not var_value:
                missing_vars.append(var_name)
            elif var_name == "BUG_REPORT_CHANNEL_ID":
                try:
                    int(var_value)
                except (ValueError, TypeError):
                    invalid_vars.append(f"{var_name} (必須為有效的整數)")

        # 可選但建議的 API 金鑰
        optional_api_keys = {
            "ANTHROPIC_API_KEY": self.anthropic_api_key,
            "OPENAI_API_KEY": self.openai_api_key,
            "GEMINI_API_KEY": self.gemini_api_key,
        }

        for api_name, api_value in optional_api_keys.items():
            if not api_value:
                # 僅回報警告，不終止程式
                try:
                    asyncio.create_task(
                        func.report_error(
                            Exception(f"警告：{api_name} 未設定，可能影響相關功能"),
                            "addons/settings.py/_validate_environment_variables",
                        )
                    )
                except Exception:
                    # fallback 到 stdout（保險處理）
                    print(f"警告：{api_name} 未設定，可能影響相關功能")

        # 若有缺失或無效的環境變數，使用 func.report_error 回報後終止
        if missing_vars or invalid_vars:
            error_msg = "環境變數驗證失敗：\n"
            if missing_vars:
                error_msg += f"缺失的環境變數：{', '.join(missing_vars)}\n"
            if invalid_vars:
                error_msg += f"無效的環境變數：{', '.join(invalid_vars)}\n"
            error_msg += "\n請檢查 .env 檔案並設定所有必要的環境變數。"

            try:
                asyncio.create_task(func.report_error(Exception(error_msg), "addons/settings.py/_validate_environment_variables"))
            except Exception:
                print(error_msg)

            # 明確終止程式，避免繼續在缺少必要設定的情況下執行
            raise SystemExit(1)


def _load_yaml_file(path: str) -> dict:
    """安全讀取 YAML 檔案，失敗時使用 func.report_error 回報並回傳空 dict"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data
    except Exception as e:
        try:
            asyncio.create_task(func.report_error(e, "addons/settings.py/_load_yaml_file"))
        except Exception:
            print(f"載入 YAML 檔案失敗 ({path}): {e}")
        return {}


class BaseConfig:
    """對應 config/base.yaml 的設定物件"""

    def __init__(self, path: str = "config/base.yaml") -> None:
        self.path = path
        data = _load_yaml_file(path)
        self.prefix: str = data.get("prefix", "/")
        self.activity: list = data.get("activity", [])
        self.ipc_server: dict = data.get("ipc_server", {})
        self.version: str = data.get("version", "")
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
        self.notifications: dict = data.get("notifications", {})
        self.restart: dict = data.get("restart", {})
        self.github: dict = data.get("github", {})


# 在模組層級建立預設實例，方便使用 from addons.settings import llm_config 直接載入
try:
    tokens = TOKENS()
except SystemExit:
    # 若驗證失敗會拋出 SystemExit，允許其傳遞以終止程序
    raise
except Exception as e:
    try:
        asyncio.create_task(func.report_error(e, "addons/settings.py/module_init"))
    except Exception:
        print(f"初始化 TOKENS 時發生錯誤: {e}")
    tokens = None

try:
    base_config = BaseConfig("config/base.yaml")
except Exception as e:
    try:
        asyncio.create_task(func.report_error(e, "addons/settings.py/module_init"))
    except Exception:
        print(f"初始化 BaseConfig 時發生錯誤: {e}")
    base_config = BaseConfig()

try:
    llm_config = LLMConfig("config/llm.yaml")
except Exception as e:
    try:
        asyncio.create_task(func.report_error(e, "addons/settings.py/module_init"))
    except Exception:
        print(f"初始化 LLMConfig 時發生錯誤: {e}")
    llm_config = LLMConfig()

try:
    update_config = UpdateConfig("config/update.yaml")
except Exception as e:
    try:
        asyncio.create_task(func.report_error(e, "addons/settings.py/module_init"))
    except Exception:
        print(f"初始化 UpdateConfig 時發生錯誤: {e}")
    update_config = UpdateConfig()

__all__ = [
    "TOKENS",
    "tokens",
    "BaseConfig",
    "base_config",
    "LLMConfig",
    "llm_config",
    "UpdateConfig",
    "update_config",
]
