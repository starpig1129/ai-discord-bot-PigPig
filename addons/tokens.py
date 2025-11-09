import os
import asyncio

from dotenv import load_dotenv

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
        os.environ["ANTHROPIC_API_KEY"] = os.getenv("ANTHROPIC_API_KEY", "")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", None)
        os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "")
        self.google_api_key = os.getenv("GOOGLE_API_KEY", None)
        os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY", "")
        self.tenor_api_key = os.getenv("TENOR_API_KEY", None)
        self.vector_store_api_key = os.getenv("VECTOR_STORE_API_KEY", None)
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
            "GEMINI_API_KEY": self.google_api_key,
        }

        for api_name, api_value in optional_api_keys.items():
            if not api_value:
                # 僅回報警告，不終止程式
                try:
                    from function import func
                    asyncio.create_task(
                        func.report_error(
                            Exception(f"警告：{api_name} 未設定，可能影響相關功能"),
                            "addons/tokens.py/_validate_environment_variables",
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
                from function import func
                asyncio.create_task(func.report_error(Exception(error_msg), "addons/tokens.py/_validate_environment_variables"))
            except Exception:
                print(error_msg)

            # 明確終止程式，避免繼續在缺少必要設定的情況下執行
            raise SystemExit(1)


try:
    tokens = TOKENS()
except SystemExit:
    # 若驗證失敗會拋出 SystemExit，允許其傳遞以終止程序
    raise
except Exception as e:
    try:
        from function import func
        asyncio.create_task(func.report_error(e, "addons/tokens.py/module_init"))
    except Exception:
        print(f"初始化 TOKENS 時發生錯誤: {e}")
    tokens = None

__all__ = ["TOKENS", "tokens"]