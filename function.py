import json
import os
from addons.logging import get_logger

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# Module-level logger
log = get_logger(server_id="Bot", source=__name__)


class Function:
    def __init__(self):
        self.bot = None

    def set_bot(self, bot):
        self.bot = bot

    async def report_error(self, error: Exception, details: str = None):
        if not self.bot:
            log.error("Function.bot instance is not set; cannot send error report.", action="report_error")
            return
        import traceback
        import discord
        
        # Only pass exception parameter if error is actually an Exception object
        if isinstance(error, BaseException):
            log.error(message=f"error: {error} details: {details}", exception=error, action="report_error")
            traceback_str = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        else:
            # If error is not an Exception (e.g., a string), log without exception parameter
            log.error(message=f"error: {error} details: {details}", action="report_error")
            traceback_str = f"No traceback available (error is {type(error).__name__}, not Exception)"


        embed = discord.Embed(
            title="錯誤報告",
            description=details or "發生了一個未處理的錯誤。",
            color=discord.Color.red()
        )

        error_field_value = f"```{type(error).__name__}: {error}```"
        if len(error_field_value) > 1024:
            error_field_value = error_field_value[:1021] + "...```"
        embed.add_field(name="錯誤", value=error_field_value, inline=False)

        if len(traceback_str) > 1024:
            traceback_str = traceback_str[:1021] + "..."
        traceback_field_value = f"```python\n{traceback_str}\n```"
        if len(traceback_field_value) > 1024:
            # 重新計算截斷長度
            max_content_len = 1024 - len("```python\n\n```")
            traceback_str = traceback_str[:max_content_len - 3] + "..." if max_content_len > 3 else "..."
            traceback_field_value = f"```python\n{traceback_str}\n```"
        embed.add_field(name="追蹤記錄", value=traceback_field_value, inline=False)
        embed.set_footer(text=f"時間: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")

        await self.bot.send_error_report(embed)

    def open_json(self, path: str) -> dict:
        try:
            with open(os.path.join(ROOT_DIR, path), encoding="utf8") as json_file:
                return json.load(json_file)
        except:
            return {}

    def update_json(self, path: str, new_data: dict) -> None:
        data = self.open_json(path)
        if not data:
            return
        
        data.update(new_data)

        with open(os.path.join(ROOT_DIR, path), "w") as json_file:
            json.dump(data, json_file, indent=4)
func = Function()