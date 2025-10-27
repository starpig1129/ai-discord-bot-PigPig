import json, os
from typing import Dict, Any
from addons import Settings, TOKENS

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

if not os.path.exists(os.path.join(ROOT_DIR, "settings.json")):
    raise Exception("Settings file not set!")

tokens: TOKENS = TOKENS()
settings: Settings = Settings()
SETTINGS_BUFFER: dict[int, dict[str, Any]] = {}
def open_json(path: str) -> dict:
    try:
        with open(os.path.join(ROOT_DIR, path), encoding="utf8") as json_file:
            return json.load(json_file)
    except:
        return {}

def update_json(path: str, new_data: dict) -> None:
    data = open_json(path)
    if not data:
        return
    
    data.update(new_data)

    with open(os.path.join(ROOT_DIR, path), "w") as json_file:
        json.dump(data, json_file, indent=4)

async def get_settings(guild_id:int) -> dict[str, Any]:
    settings = SETTINGS_BUFFER.get(guild_id, None)
    if not settings:
            
        settings = SETTINGS_BUFFER[guild_id] = settings or {}
    return settings

class Function:
    def __init__(self):
        self.bot = None

    def set_bot(self, bot):
        self.bot = bot

    async def report_error(self, error: Exception, details: str = None):
        if not self.bot:
            print("錯誤：Function class中的bot實例未設置。")
            return

        import traceback
        import discord

        traceback_str = "".join(traceback.format_exception(type(error), error, error.__traceback__))

        embed = discord.Embed(
            title="錯誤報告",
            description=details or "發生了一個未處理的錯誤。",
            color=discord.Color.red()
        )

        embed.add_field(name="錯誤", value=f"```{type(error).__name__}: {error}```", inline=False)

        if len(traceback_str) > 1024:
            traceback_str = traceback_str[:1021] + "..."
        embed.add_field(name="追蹤記錄", value=f"```python\n{traceback_str}\n```", inline=False)
        embed.set_footer(text=f"時間: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")

        await self.bot._send_error_report(embed)

func = Function()