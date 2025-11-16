import re
import logging
from datetime import datetime

import discord
from discord.ext import commands
from discord import app_commands
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, AIMessage
from langchain.agents.middleware import ModelCallLimitMiddleware

from function import func
from llm.model_manager import ModelManager
from utils.logger import LoggerMixin

# REMOVED: logging.basicConfig() to prevent standard Python logging format
# All logging now uses the unified structured logging system from main.py


class SummarizerCog(commands.Cog, LoggerMixin):
    """一個專門用於處理對話摘要功能的 Cog，整合了訊息數與字元數雙重限制。"""

    def __init__(self, bot: commands.Bot):
        LoggerMixin.__init__(self, "SummarizerCog")
        self.bot = bot
        self.MAX_CHAR_COUNT = 15000
        self.EMBED_DESC_LIMIT = 4000

    def _split_text_robustly(self, text: str):
        """
        將長文本安全地分割成多個區塊，能處理單行超長的問題。
        """
        limit = self.EMBED_DESC_LIMIT
        final_chunks = []
        current_chunk = ""
        safe_lines = []
        for line in text.split('\n'):
            if len(line) > limit:
                start = 0
                while start < len(line):
                    end = start + limit
                    safe_lines.append(line[start:end])
                    start = end
            else:
                safe_lines.append(line)
        for line in safe_lines:
            if len(current_chunk) + len(line) + 1 > limit:
                if current_chunk:
                    final_chunks.append(current_chunk)
                current_chunk = line
            else:
                current_chunk = "\n".join([current_chunk, line]) if current_chunk else line
        if current_chunk:
            final_chunks.append(current_chunk)
        return final_chunks if final_chunks else [""]

    @app_commands.command(name="summarize", description="使用 AI 總結頻道對話，並標註訊息來源。")
    @app_commands.describe(
        limit="要搜尋的訊息數量上限 (預設 100)",
        persona="設定 AI 的總結人設 (例如：一位專業的會議記錄員)",
        only_me="是否只有你看得到這則摘要 (預設為否，即公開)"
    )
    async def summarize(self, interaction: discord.Interaction, limit: int = 100, persona: str = None, only_me: bool = False):
        await interaction.response.defer(ephemeral=only_me, thinking=True)

        try:
            logging.info(f"開始為頻道 {interaction.channel.name} 擷取最多 {limit} 則訊息。")
            history = [msg async for msg in interaction.channel.history(limit=limit)]
            dialogue_history_reversed = []
            source_mapping = {}
            current_char_count = 0
            human_msg_count = 0  # 只計算人類訊息的數量

            for msg in history:  # 迴圈從新到舊
                if not msg.content:  # 忽略沒有文字內容的訊息 (例如只有 embed)
                    continue

                formatted_content = ""
                timestamp = msg.created_at.strftime('%Y-%m-%d %H:%M')

                if msg.author.bot:
                    # 對於機器人，使用簡潔的佔位符
                    formatted_content = f"({timestamp}) [Bot @{msg.author.display_name}'s message]"
                    # 將機器人訊息視為 AIMessage（作為上下文）
                    dialogue_history_reversed.append(AIMessage(content=formatted_content))
                else:
                    # 對於人類，使用包含 MSG-ID 的詳細格式
                    human_msg_count += 1
                    msg_id = f"MSG-{human_msg_count}"
                    source_mapping[msg_id] = msg.jump_url
                    formatted_content = f"[{msg_id}] ({timestamp}) {msg.content}"
                    # 將人類訊息視為 HumanMessage
                    dialogue_history_reversed.append(HumanMessage(content=formatted_content,name = msg.author.display_name))

                # 檢查字元數限制
                content_len = len(formatted_content)
                if current_char_count + content_len > self.MAX_CHAR_COUNT:
                    logging.warning(f"達到字元數上限 {self.MAX_CHAR_COUNT}。停止收集訊息。")
                    break

                current_char_count += content_len

            # 將歷史紀錄反轉為正確的時間順序（從舊到新）
            dialogue_history = list(reversed(dialogue_history_reversed))

            if not dialogue_history or human_msg_count == 0:
                await interaction.followup.send("在指定的範圍內找不到任何可以總結的真人對話訊息。", ephemeral=True)
                return

            system_prompt = f"""
            你是一位專業的對話摘要助理。你的任務是分析我接下來在對話歷史中提供的 Discord 紀錄，並生成一份精簡的摘要。對話歷史中 `[Bot ... message]` 代表機器人發送的訊息，僅作為上下文參考，不應成為摘要的重點。

            你的職責：
            1.  識別人類對話中的核心主題、重要問題、達成的共識或決策。
            2.  提取需要後續追蹤的行動項目。
            3.  忽略閒聊、打招呼或與主題無關的內容。
            4.  摘要必須以清晰的條列式清單（使用-）呈現。
            5.  【非常重要】對於摘要中的每一點，你必須在結尾附上其資訊來源的訊息ID（僅限人類訊息）。格式為 `[MSG-ID]`。
            6.  【輸出長度】請盡量將總結全文的總長度控制在 5000 字元以內，以符合顯示限制。
            {f"請注意：本次摘要請使用「{persona}」的語氣和角度來撰寫。" if persona else ""}
            """
            user_instruction = "請根據我提供的對話歷史紀錄，開始進行摘要。"
            logging.info(f"正在調用語言模型生成摘要... (分析 {human_msg_count} 則人類訊息，總輸入 {current_char_count} 字元)")

            # 建立 agent（維持 create_agent，但傳入 SystemMessage 作為系統角色）
            model, fallback = ModelManager().get_model("summarize_model")
            summarize_agent = create_agent(
                model=model,
                tools=[],
                system_prompt=system_prompt,
                middleware=[
                            fallback,
                            ModelCallLimitMiddleware(run_limit=1, exit_behavior="end"),
                                
                            ]
            )

            # 最後追加使用者指令，並確保所有訊息皆為 HumanMessage/AIMessage 的實例
            messages = dialogue_history + [HumanMessage(content=user_instruction)]

            # 新版 langchain 傳遞 message 物件實例給 agent
            response = await summarize_agent.ainvoke({"messages": messages})

            full_summary = response["messages"][-1].content
            logging.info("摘要生成完畢，開始進行後處理。")

            def replace_with_link(match):
                ids = re.findall(r'MSG-\d+', match.group(0))
                links = [f"[[來源-{msg_id.split('-')[1]}]]({source_mapping.get(msg_id)})" for msg_id in ids if source_mapping.get(msg_id)]
                return ' '.join(links) if links else match.group(0)

            processed_summary = re.sub(r'\[(MSG-\d+(?:,\s*MSG-\d+)*)\]', replace_with_link, full_summary)
            summary_chunks = self._split_text_robustly(processed_summary)
            main_embed = discord.Embed(
                title="📄 對話摘要",
                description=summary_chunks[0],
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            footer_text = (
                f"已分析最近的 {human_msg_count} 則訊息 (在 {limit} 則的搜尋範圍內)。\n"
                f"總輸入字元數: {current_char_count}/{self.MAX_CHAR_COUNT}"
            )
            main_embed.set_footer(text=footer_text)
            await interaction.followup.send(embed=main_embed)
            if len(summary_chunks) > 1:
                logging.info(f"摘要過長，將其分割成 {len(summary_chunks)} 則訊息發送。")
                for i, chunk in enumerate(summary_chunks[1:], 1):
                    continuation_embed = discord.Embed(description=chunk, color=discord.Color.blue())
                    continuation_embed.set_footer(text=f"摘要接續... (第 {i+1}/{len(summary_chunks)} 頁)")
                    await interaction.followup.send(embed=continuation_embed)

        except Exception as e:
            await func.report_error(e, "summarizing channel")
            await interaction.followup.send(f"❌ 糟糕，發生了一個未預期的錯誤，請聯繫管理員。\n`{e}`", ephemeral=True)


async def setup(bot: commands.Bot):
    """將 Cog 加入 Bot 的設置函式。"""
    await bot.add_cog(SummarizerCog(bot))