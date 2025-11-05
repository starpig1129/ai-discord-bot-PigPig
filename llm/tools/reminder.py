# MIT License
# Copyright (c) 2024 starpig1129

from typing import Optional

from langchain.tools import tool, ToolRuntime
from typing import Any
from cogs.remind import ReminderCog
from function import func

@tool
async def set_reminder(
    time_str: str,
    message: str,
    context: ToolRuntime,
    user_id: Optional[int] = None,
) -> str:
    """為 LLM 工具封裝的提醒設定接口。

    - 使用 context 作為第一參數。
    - 依賴 ReminderCog 的 _set_reminder_logic 執行詳細排程與驗證。
    - 所有錯誤以 func.report_error 上報。
    """
    logger = context.logger
    bot = context.bot

    cog: Optional[ReminderCog] = bot.get_cog("ReminderCog")
    if not cog:
        msg = "Error: ReminderCog is not loaded."
        logger.error(msg)
        return msg

    # 決定目標使用者
    try:
        if user_id is None:
            # 若沒有指定 user_id，使用發起者
            target_user_id = context.message.author.id
        else:
            target_user_id = user_id

        try:
            target_user = await bot.fetch_user(target_user_id)
        except Exception:
            # fetch_user 可能失敗，使用 fallback 名稱
            target_user = None

        channel = getattr(context.message, "channel", None)
        guild_id = None
        if getattr(context.message, "guild", None):
            guild_id = str(context.message.guild.id)
        else:
            guild_id = "@me"

        logger.info("Setting reminder", extra={"target_user_id": target_user_id, "guild": guild_id})

        result = await cog._set_reminder_logic(
            channel=channel,
            target_user=target_user,
            time_str=time_str,
            message=message,
            guild_id=guild_id,
            interaction=None,
        )
        logger.info("Reminder scheduled", extra={"result": result})
        return result
    except Exception as e:  # pragma: no cover - orchestrator logic
        await func.report_error(e, f"set_reminder failed for user {user_id}")
        return f"Error: Failed to set reminder: {e}"