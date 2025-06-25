import discord
from discord.ext import commands
from discord import app_commands
import re
from datetime import datetime
import logging

# 假設你的新 gemini_api.py 位於 gpt/ 目錄下
try:
    from gpt.gemini_api import generate_response, GeminiError
except ImportError:
    class GeminiError(Exception):
        pass
    async def generate_response(*args, **kwargs):
        raise NotImplementedError("gpt.gemini_api 模組未找到")

# 設定日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class SummarizerCog(commands.Cog):
    """一個專門用於處理對話摘要功能的 Cog，整合了訊息數與字元數雙重限制。"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.MAX_CHAR_COUNT = 15000

    @app_commands.command(name="summarize", description="使用 AI 總結頻道對話，並標註訊息來源。")
    @app_commands.describe(
        limit="要搜尋的訊息數量上限 (預設 100)",
        persona="設定 AI 的總結人設 (例如：一位專業的會議記錄員)",
        only_me="是否只有你看得到這則摘要 (預設為否，即公開)"
    )
    async def summarize(self, interaction: discord.Interaction, limit: int = 100, persona: str = None, only_me: bool = False):
        """
        一個使用 AI 總結對話並能點擊來源的斜線命令。
        """
        await interaction.response.defer(ephemeral=only_me, thinking=True)

        try:

            logging.info(f"開始為頻道 {interaction.channel.name} 擷取最多 {limit} 則訊息。")
            
            history = [msg async for msg in interaction.channel.history(limit=limit)]

            messages_to_process = []
            current_char_count = 0
            
            for msg in history:
                if not msg.author.bot and msg.content:
                    msg_len = len(msg.content)
                    if current_char_count + msg_len > self.MAX_CHAR_COUNT:
                        logging.warning(f"達到字元數上限 {self.MAX_CHAR_COUNT}。停止收集訊息。")
                        break
                    
                    messages_to_process.append(msg)
                    current_char_count += msg_len

            messages_to_process.reverse()
            
            if not messages_to_process:
                await interaction.followup.send("在指定的範圍內找不到任何可以總結的真人對話訊息。", ephemeral=True)
                return

            dialogue_history = []
            source_mapping = {}
            msg_count = 0

            for msg_count, msg in enumerate(messages_to_process, 1):
                msg_id = f"MSG-{msg_count}"
                source_mapping[msg_id] = msg.jump_url
                
                formatted_content = (
                    f"[{msg_id}] ({msg.created_at.strftime('%Y-%m-%d %H:%M')}) "
                    f"{msg.author.display_name}: {msg.content}"
                )
                
                dialogue_history.append({
                    'role': 'user',
                    'content': formatted_content
                })

            system_prompt = f"""
            你是一位專業的對話摘要助理。你的任務是分析我接下來在對話歷史中提供的 Discord 紀錄，並生成一份精簡的摘要。

            你的職責：
            1.  識別對話中的核心主題、重要問題、達成的共識或決策。
            2.  提取需要後續追蹤的行動項目。
            3.  忽略閒聊、打招呼或與主題無關的內容。
            4.  摘要必須以清晰的條列式清單（使用-）呈現。
            5.  【非常重要】對於摘要中的每一點，你必須在結尾附上其資訊來源的訊息ID。格式為 `[MSG-ID]`。如果一個摘要點來自多則訊息，請全部列出，例如 `[MSG-5, MSG-8, MSG-12]`。

            {f"請注意：本次摘要請使用「{persona}」的語氣和角度來撰寫。" if persona else ""}
            """
            
            user_instruction = "請根據我提供的對話歷史紀錄，開始進行摘要。"

            logging.info(f"正在調用語言模型生成摘要... (實際處理 {msg_count} 則訊息，共 {current_char_count} 字元)")
            
            thread, generator = await generate_response(
                inst=user_instruction,
                system_prompt=system_prompt,
                dialogue_history=dialogue_history
            )

            full_summary = ""
            async for chunk in generator:
                full_summary += chunk

            if not full_summary:
                raise ValueError("模型沒有生成任何回應。")

            logging.info("摘要生成完畢，開始進行後處理。")

            def replace_with_link(match):
                ids = re.findall(r'MSG-\d+', match.group(0))
                links = [f"[[來源-{msg_id.split('-')[1]}]]({source_mapping.get(msg_id)})" for msg_id in ids if source_mapping.get(msg_id)]
                return ' '.join(links) if links else match.group(0)

            processed_summary = re.sub(r'\[(MSG-\d+(?:,\s*MSG-\d+)*)\]', replace_with_link, full_summary)

            embed = discord.Embed(
                title="📄 對話摘要",
                description=processed_summary,
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            
            footer_text = (
                f"已分析最近的 {msg_count} 則訊息 (在 {limit} 則的搜尋範圍內)。\n"
                f"總字元數: {current_char_count}/{self.MAX_CHAR_COUNT}"
            )
            embed.set_footer(text=footer_text)
            
            await interaction.followup.send(embed=embed)

        except GeminiError as e:
            logging.error(f"模型 API 錯誤: {e}")
            await interaction.followup.send(f"❌ Gemini 模型服務出錯了：\n`{e}`", ephemeral=True)
        except Exception as e:
            logging.error(f"執行 /summarize 命令時發生未知錯誤: {e}", exc_info=True)
            await interaction.followup.send(f"❌ 糟糕，發生了一個未預期的錯誤，請聯繫管理員。\n`{e}`", ephemeral=True)

async def setup(bot: commands.Bot):
    """將 Cog 加入 Bot 的設置函式。"""
    await bot.add_cog(SummarizerCog(bot))