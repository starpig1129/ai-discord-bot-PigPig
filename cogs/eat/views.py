import json
import asyncio
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
        self._max_viewed_index = initial_index  # 僅讓使用者在選單看到「已探索」的項目
        self._is_fetching = False  # 標記按鈕點擊後的抓取狀態

        self._rebuild_select()
        self._update_nav_buttons()

        # 啟動背景預取任務（僅針對標記為未詳細的項目）
        self._prefetch_task = None
        if any(not r.get("is_detailed", True) for r in self.results):
            self._prefetch_task = asyncio.create_task(self._background_prefetch())

    async def _background_prefetch(self):
        """在後台逐一補全餐廳的詳細資訊。"""
        # 為了效能，我們只預取前 10-15 個候選者
        limit = min(15, len(self.results))
        for i in range(limit):
            if self.results[i].get("is_detailed", False):
                continue
            
            url = self.results[i].get("maps_url", "")
            if url:
                try:
                    # 這裡是耗時的操作（Selenium 導航）
                    detail = await self.provider.async_fetch_detail(url)
                    if detail:
                        # 更新快取中的資料，保留原有的排序
                        self.results[i].update(detail)
                        self.results[i]["is_detailed"] = True
                        logger.info(f"背景已完成預取：{self.results[i].get('name')}")
                except Exception as e:
                    logger.warning(f"背景預取失敗 ({url}): {e}")
            
            # 給予一點間隔避免過度競爭 WebDriver 鎖
            await asyncio.sleep(1)

    def _rebuild_select(self):
        """重建下拉選單（動態選項需每次重建）。"""
        # 移除舊的 Select（若存在）
        for child in list(self.children):
            if isinstance(child, discord.ui.Select):
                self.remove_item(child)

        # 決定顯示的範圍（僅顯示已探索過或當前正在看的項目）
        # 根據使用者要求：「搜尋結果應該要在使用者按下重新搜尋 才會添加到清單」
        # 所以我們只循環到 _max_viewed_index
        viewable_results = self.results[:self._max_viewed_index + 1]
        
        start_idx = 0
        if len(viewable_results) > 25:
            start_idx = max(0, self.current_index - 12)
            if start_idx + 25 > len(viewable_results):
                start_idx = len(viewable_results) - 25

        options = []
        for i in range(start_idx, min(start_idx + 25, len(viewable_results))):
            place = viewable_results[i]
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
                label=f"{i+1}. {name}"[:100],
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

    @discord.ui.button(label="下一個推薦", emoji="🔄", style=discord.ButtonStyle.primary, row=2)
    async def regenerate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """切換到下一個結果。如果資料尚未準備好，則進行即時抓取。"""
        if not self.results:
            return

        next_index = (self.current_index + 1) % len(self.results)
        
        # 使用者點擊「重新搜尋」才解鎖下一筆
        if next_index > self._max_viewed_index:
            self._max_viewed_index = next_index

        self.current_index = next_index
        target_res = self.results[self.current_index]

        # 檢查是否需要即時抓取詳細資訊（如果背景任務還沒跑完）
        if not target_res.get("is_detailed", False):
            await interaction.response.edit_message(embed=loadingEmbed(target_res.get("name", "餐廳")), view=None)
            self._is_fetching = True
            try:
                url = target_res.get("maps_url", "")
                detail = await self.provider.async_fetch_detail(url)
                if detail:
                    self.results[self.current_index].update(detail)
                    self.results[self.current_index]["is_detailed"] = True
            except Exception as e:
                logger.error(f"即時抓取詳細資訊失敗: {e}")
            self._is_fetching = False
            # 抓完後更新
            self._rebuild_select()
            self._update_nav_buttons()
            embed = browseEmbed(self.results, self.current_index)
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            # 資料已就緒，直接更新
            self._rebuild_select()
            self._update_nav_buttons()
            embed = browseEmbed(self.results, self.current_index)
            await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


# 向後相容的舊 class 別名
EatWhatView = EatBrowseView
