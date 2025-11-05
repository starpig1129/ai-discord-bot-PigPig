# MIT License
# Copyright (c) 2024 starpig1129

from typing import Optional, Any

from langchain.tools import tool, ToolRuntime
from typing import Any
from function import func

@tool
async def manage_user_data(
    action: str,
    user_id: int,
    context: ToolRuntime,
    user_data: Optional[str] = None,
) -> str:
    """管理使用者資料的工具封裝（read / save）。

    - context 必須為第一參數。
    - read: 回傳使用者資料（由 UserDataCog 處理）。
    - save: 將資料存入並與既有資料合併。
    - 所有錯誤使用 func.report_error 上報，保證日誌一致性。
    """
    logger = context.logger
    cog = context.bot.get_cog("UserDataCog")

    if not cog:
        msg = "Error: UserDataCog is not loaded."
        logger.error(msg)
        return msg

    try:
        if action == "read":
            logger.info("Reading user data", extra={"user_id": user_id})
            return await cog._read_user_data(str(user_id), context)

        if action == "save":
            if user_data is None:
                return "Error: 'user_data' is required when action is 'save'."

            logger.info("Saving user data", extra={"user_id": user_id})
            try:
                user = await context.bot.fetch_user(user_id)
                display_name = getattr(user, "display_name", f"User_{user_id}")
            except Exception:
                display_name = f"User_{user_id}"

            return await cog._save_user_data(str(user_id), display_name, user_data, context)

        return "Error: Invalid action. Please use 'read' or 'save'."
    except Exception as e:  # pragma: no cover - external logic
        await func.report_error(e, f"Managing user data for {user_id} failed")
        return f"An unexpected error occurred: {e}"