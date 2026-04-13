import json
import discord

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage

from cogs.eat.db.db import DB
from cogs.eat.embeds import eatEmbed, browseEmbed, loadingEmbed
from function import func
from llm.model_manager import ModelManager
from llm.model_circuit_breaker import get_model_circuit_breaker
from llm.utils.send_message import safe_edit_message
from addons.logging import get_logger

logger = get_logger(server_id="Bot", source="eat.views")

# ──────────────────────────────────────────────
# DislikeModal
# ──────────────────────────────────────────────

class DislikeModal(discord.ui.Modal, title="不喜歡的原因（選填）"):
    reason = discord.ui.TextInput(
        label="原因",
        placeholder="例如：太貴、不合口味、距離太遠...",
        required=False,
        max_length=200,
    )

    def __init__(self, db: DB, record_id: int, detail_view: "EatDetailView"):
        super().__init__()
        self.db = db
        self.record_id = record_id
        self.detail_view = detail_view

    async def on_submit(self, interaction: discord.Interaction):
        self.db.updateRecordRate(id=self.record_id, new_rate=-1)
        self.detail_view._rated = True
        self.detail_view.like_button.disabled = True
        self.detail_view.dislike_button.disabled = True
        await interaction.response.edit_message(view=self.detail_view)
        await interaction.followup.send("已記錄！下次將不推薦此類餐廳 🙏", ephemeral=True)


# ──────────────────────────────────────────────
# EatDetailView（選定餐廳後的操作）
# ──────────────────────────────────────────────

class EatDetailView(discord.ui.View):
    """選定單一餐廳後的互動 View。"""

    def __init__(self, result: dict, db: DB, record_id: int, discord_id: str,
                 provider, keyword: str, browse_results: list, browse_index: int):
        super().__init__(timeout=600)
        self.result = result
        self.db = db
        self.record_id = record_id
        self.discord_id = discord_id
        self.provider = provider
        self.keyword = keyword
        self.browse_results = browse_results
        self.browse_index = browse_index
        self._rated = False

    @discord.ui.button(label="地圖連結", emoji="🗺️", style=discord.ButtonStyle.secondary, row=0)
    async def map_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        maps_url = self.result.get("maps_url", "")
        name = self.result.get("name", "餐廳")
        if maps_url:
            await interaction.response.send_message(
                f"[{name} 的 Google Maps 連結]({maps_url})", ephemeral=True
            )
        else:
            await interaction.response.send_message("找不到地圖連結", ephemeral=True)

    @discord.ui.button(label="菜單", emoji="📋", style=discord.ButtonStyle.secondary, row=0)
    async def menu_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        photo_url = self.result.get("photo_url", "")
        if photo_url:
            embed = discord.Embed(title="菜單", colour=discord.Colour.green())
            embed.set_image(url=photo_url)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("找不到菜單圖片", ephemeral=True)

    @discord.ui.button(label="AI 美食評論", emoji="🍽️", style=discord.ButtonStyle.primary, row=0)
    async def review_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """使用 LangChain streaming 生成美食評論。"""
        try:
            system_prompt = (
                "You are a professional and witty food critic who excels at writing vivid and "
                "interesting reviews based on restaurant information. "
                "Interact with users in a humorous yet professional tone, providing valuable dining recommendations. "
                "Your reviews should include comprehensive analysis of food quality, atmosphere, and service standards. "
                "Always respond in Traditional Chinese and use emojis appropriately to add fun and engagement."
            )

            store_info_text = json.dumps({
                "restaurant_name": self.result.get("name", ""),
                "rating": f"{self.result.get('rating', 0)}/5.0",
                "category": self.result.get("category", ""),
                "address": self.result.get("address", ""),
                "reviews": self.result.get("reviews", []),
            }, ensure_ascii=False, indent=2)

            await interaction.response.defer(ephemeral=True)
            message_to_edit = await interaction.followup.send("📝 準備撰寫專業評論...", ephemeral=True)

            model_manager = ModelManager()
            try:
                model_priority_list = model_manager.get_model_priority_list("review_model")
            except ValueError as e:
                await func.report_error(e, "EatDetailView.review_button - no review_model configured")
                await safe_edit_message(message_to_edit, "❌ 評論模型未正確設定")
                return

            messages = [
                HumanMessage(content=(
                    f"以下是餐廳資訊：\n{store_info_text}\n\n"
                    "請根據上述資訊，撰寫一篇專業又風趣的繁體中文美食評論，適當加入 emoji。"
                ))
            ]

            circuit_breaker = get_model_circuit_breaker()
            responsesall = ""
            last_exception = None
            success = False

            for current_model in model_priority_list:
                if not circuit_breaker.is_available(current_model):
                    continue
                try:
                    model_instance = init_chat_model(current_model, max_retries=0)
                    review_agent = create_agent(
                        model=model_instance,
                        tools=[],
                        system_prompt=system_prompt,
                        middleware=[],
                    )
                    streamer = review_agent.astream(
                        {"messages": messages},
                        stream_mode="messages",
                    )
                    buffer_size = 40
                    responses = ""
                    responsesall = ""
                    async for token, metadata in streamer:
                        if hasattr(token, "content") and token.content:
                            responses += token.content
                            if len(responses) >= buffer_size:
                                responsesall += responses
                                await safe_edit_message(message_to_edit, responsesall)
                                responses = ""
                    responsesall += responses
                    responsesall = responsesall.strip()
                    if responsesall:
                        await safe_edit_message(message_to_edit, responsesall)
                        success = True
                        break
                    else:
                        raise ValueError("Empty response from model")
                except Exception as e:
                    last_exception = e
                    circuit_breaker.record_failure(current_model, e)

            if not success and last_exception:
                await safe_edit_message(message_to_edit, f"❌ 評論生成失敗: {str(last_exception)[:100]}")
                await func.report_error(last_exception, "EatDetailView.review_button - all models failed")

        except Exception as e:
            await func.report_error(e, "EatDetailView.review_button")

    @discord.ui.button(emoji="👍", style=discord.ButtonStyle.success, row=1)
    async def like_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._rated:
            await interaction.response.send_message("已經評分過了！", ephemeral=True)
            return
        self._rated = True
        self.db.updateRecordRate(id=self.record_id, new_rate=1)
        button.disabled = True
        self.dislike_button.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send("感謝回饋！往後將推薦類似商家 😊", ephemeral=True)

    @discord.ui.button(emoji="👎", style=discord.ButtonStyle.danger, row=1)
    async def dislike_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._rated:
            await interaction.response.send_message("已經評分過了！", ephemeral=True)
            return
        modal = DislikeModal(db=self.db, record_id=self.record_id, detail_view=self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="返回列表", emoji="↩️", style=discord.ButtonStyle.secondary, row=1)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """返回 EatBrowseView。"""
        view = EatBrowseView(
            results=self.browse_results,
            keyword=self.keyword,
            db=self.db,
            discord_id=self.discord_id,
            provider=self.provider,
            initial_index=self.browse_index,
        )
        embed = browseEmbed(self.browse_results, self.browse_index)
        await interaction.response.edit_message(embed=embed, view=view)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


# ──────────────────────────────────────────────
# EatBrowseView（多結果瀏覽主 View）
# ──────────────────────────────────────────────

class EatBrowseView(discord.ui.View):
    """多結果瀏覽 View，支援翻頁和下拉選擇。"""

    def __init__(self, results: list, keyword: str, db: DB,
                 discord_id: str, provider, initial_index: int = 0):
        super().__init__(timeout=300)
        self.results = results
        self.keyword = keyword
        self.db = db
        self.discord_id = discord_id
        self.provider = provider
        self.current_index = initial_index

        self._rebuild_select()
        self._update_nav_buttons()

    def _rebuild_select(self):
        """重建下拉選單（動態選項需每次重建）。"""
        # 移除舊的 Select（若存在）
        for child in list(self.children):
            if isinstance(child, discord.ui.Select):
                self.remove_item(child)

        options = []
        for i, place in enumerate(self.results[:25]):
            name = place.get("name", f"餐廳 {i+1}")
            rating = place.get("rating", 0)
            category = place.get("category", "")
            address = place.get("address", "")

            desc_parts = []
            if rating:
                desc_parts.append(f"⭐{rating}")
            if category:
                desc_parts.append(category)
            if address:
                desc_parts.append(address[:30])
            description = " | ".join(desc_parts)[:100]

            options.append(discord.SelectOption(
                label=name[:100],
                description=description or None,
                value=str(i),
                default=(i == self.current_index),
            ))

        if options:
            select = discord.ui.Select(
                placeholder="從下拉選單選擇餐廳...",
                options=options,
                row=0,
            )
            select.callback = self._select_callback
            self.add_item(select)

    async def _select_callback(self, interaction: discord.Interaction):
        select = next(c for c in self.children if isinstance(c, discord.ui.Select))
        self.current_index = int(select.values[0])
        self._rebuild_select()
        self._update_nav_buttons()
        embed = browseEmbed(self.results, self.current_index)
        await interaction.response.edit_message(embed=embed, view=self)

    def _update_nav_buttons(self):
        self.prev_button.disabled = (self.current_index == 0)
        self.next_button.disabled = (self.current_index >= len(self.results) - 1)

    @discord.ui.button(label="上一個", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_index -= 1
        self._rebuild_select()
        self._update_nav_buttons()
        embed = browseEmbed(self.results, self.current_index)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="下一個", emoji="▶️", style=discord.ButtonStyle.secondary, row=1)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_index += 1
        self._rebuild_select()
        self._update_nav_buttons()
        embed = browseEmbed(self.results, self.current_index)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="就這家！", emoji="✅", style=discord.ButtonStyle.success, row=2)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """確定選擇當前餐廳，切換到 EatDetailView。"""
        result = self.results[self.current_index]
        record_id = self.db.storeSearchRecord(
            discord_id=self.discord_id,
            title=result.get("name", ""),
            keyword=self.keyword,
            map_rate=str(result.get("rating", "")),
            tag=result.get("category", ""),
            map_address=result.get("address", ""),
        )
        detail_view = EatDetailView(
            result=result,
            db=self.db,
            record_id=record_id,
            discord_id=self.discord_id,
            provider=self.provider,
            keyword=self.keyword,
            browse_results=self.results,
            browse_index=self.current_index,
        )
        embed = eatEmbed(
            keyword=self.keyword,
            title=result.get("name", ""),
            address=result.get("address", ""),
            rating=result.get("rating", 0),
            photo_url=result.get("photo_url", ""),
            price_level=result.get("price_level", 0),
            opening_hours=result.get("opening_hours", []),
        )
        await interaction.response.edit_message(embed=embed, view=detail_view)

    @discord.ui.button(label="重新搜尋", emoji="🔄", style=discord.ButtonStyle.primary, row=2)
    async def regenerate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """重新用同一關鍵字搜尋，顯示 loading embed。"""
        # 禁用所有按鈕以防重複點擊，同時顯示 loading
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=loadingEmbed(self.keyword), view=self)
        try:
            new_results = await self.provider.search(self.keyword)
            if not new_results:
                await interaction.edit_original_response(
                    content=f"找不到「{self.keyword}」相關餐廳", embed=None, view=None
                )
                return
            
            # 將新結果「加入」原有列表，並過濾掉已存在的餐廳
            seen_names = {r.get("name", "") for r in self.results}
            added_count = 0
            for r in new_results:
                if r.get("name", "") not in seen_names:
                    self.results.append(r)
                    added_count += 1
            
            if added_count == 0:
                await interaction.followup.send("找不到更多不同的餐廳囉！", ephemeral=True)
                
            self.current_index = 0
            # 恢復按鈕（重建 select 同時更新導航按鈕狀態）
            for child in self.children:
                child.disabled = False
            self._rebuild_select()
            self._update_nav_buttons()
            embed = browseEmbed(self.results, 0)
            await interaction.edit_original_response(embed=embed, view=self)
        except Exception as e:
            await func.report_error(e, "EatBrowseView.regenerate_button")
            await interaction.edit_original_response(
                content=f"重新搜尋失敗：{str(e)[:100]}", embed=None, view=None
            )

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


# 向後相容的舊 class 別名
EatWhatView = EatBrowseView
