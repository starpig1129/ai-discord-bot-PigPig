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

class DislikeModal(discord.ui.Modal):
    reason = discord.ui.TextInput(
        max_length=200,
        required=False
    )

    def __init__(self, db: DB, record_id: int, detail_view: "EatDetailView",
                 lang_manager=None, guild_id: str = "0"):
        self.db = db
        self.record_id = record_id
        self.detail_view = detail_view
        self.lang_manager = lang_manager
        self.guild_id = guild_id
        
        title = "Reason for dislike (optional)"
        label = "Reason"
        placeholder = "e.g., Too expensive, don't like the taste, too far away..."
        
        if lang_manager:
            title = lang_manager.translate(guild_id, "commands", "eat", "views", "dislike_modal", "title")
            label = lang_manager.translate(guild_id, "commands", "eat", "views", "dislike_modal", "label")
            placeholder = lang_manager.translate(guild_id, "commands", "eat", "views", "dislike_modal", "placeholder")
            
        super().__init__(title=title)
        self.reason.label = label
        self.reason.placeholder = placeholder

    async def on_submit(self, interaction: discord.Interaction):
        self.db.updateRecordRate(id=self.record_id, new_rate=-1)
        self.detail_view._rated = True
        self.detail_view.like_button.disabled = True
        self.detail_view.dislike_button.disabled = True
        await interaction.response.edit_message(view=self.detail_view)
        
        success_msg = "Recorded! We won't recommend this type of restaurant next time 🙏"
        if self.lang_manager:
            success_msg = self.lang_manager.translate(self.guild_id, "commands", "eat", "views", "dislike_modal", "success")
            
        await interaction.followup.send(success_msg, ephemeral=True)


# ──────────────────────────────────────────────
# EatDetailView (Operations after selecting a restaurant)
# ──────────────────────────────────────────────

class EatDetailView(discord.ui.View):
    """Interactive View after selecting a single restaurant."""

    def __init__(self, result: dict, db: DB, record_id: int, discord_id: str,
                 provider, keyword: str, browse_results: list, browse_index: int,
                 lang_manager=None, guild_id: str = "0"):
        super().__init__(timeout=600)
        self.result = result
        self.db = db
        self.record_id = record_id
        self.discord_id = discord_id
        self.provider = provider
        self.keyword = keyword
        self.browse_results = browse_results
        self.browse_index = browse_index
        self.lang_manager = lang_manager
        self.guild_id = guild_id
        self._rated = False
        self._update_labels()

    def _update_labels(self):
        if self.lang_manager:
            self.map_button.label = self.lang_manager.translate(self.guild_id, "commands", "eat", "views", "detail", "buttons", "map")
            self.menu_button.label = self.lang_manager.translate(self.guild_id, "commands", "eat", "views", "detail", "buttons", "menu")
            self.review_button.label = self.lang_manager.translate(self.guild_id, "commands", "eat", "views", "detail", "buttons", "review")
            self.back_button.label = self.lang_manager.translate(self.guild_id, "commands", "eat", "views", "detail", "buttons", "back")

    @discord.ui.button(label="Map", emoji="🗺️", style=discord.ButtonStyle.secondary, row=0)
    async def map_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        maps_url = self.result.get("maps_url", "")
        name = self.result.get("name", "Restaurant")
        if maps_url:
            await interaction.response.send_message(
                f"[{name} Google Maps Link]({maps_url})", ephemeral=True
            )
        else:
            msg = self.lang_manager.translate(self.guild_id, "commands", "eat", "views", "detail", "responses", "map_not_found") if self.lang_manager else "Map link not found"
            await interaction.response.send_message(msg, ephemeral=True)

    @discord.ui.button(label="Menu", emoji="📋", style=discord.ButtonStyle.secondary, row=0)
    async def menu_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        photo_url = self.result.get("photo_url", "")
        if photo_url:
            title = self.lang_manager.translate(self.guild_id, "commands", "eat", "embeds", "menu", "title") if self.lang_manager else "Menu"
            embed = discord.Embed(title=title, colour=discord.Colour.green())
            embed.set_image(url=photo_url)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            msg = self.lang_manager.translate(self.guild_id, "commands", "eat", "views", "detail", "responses", "menu_not_found") if self.lang_manager else "Menu image not found"
            await interaction.response.send_message(msg, ephemeral=True)

    @discord.ui.button(label="AI Review", emoji="🍽️", style=discord.ButtonStyle.primary, row=0)
    async def review_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Generate food reviews using LangChain streaming."""
        try:
            if self.lang_manager:
                system_prompt = self.lang_manager.translate(self.guild_id, "commands", "eat", "views", "detail", "ai", "system_prompt")
                user_prompt_template = self.lang_manager.translate(self.guild_id, "commands", "eat", "views", "detail", "ai", "user_prompt")
                preparing_msg = self.lang_manager.translate(self.guild_id, "commands", "eat", "views", "detail", "responses", "review_preparing")
                config_error_msg = self.lang_manager.translate(self.guild_id, "commands", "eat", "views", "detail", "responses", "review_config_error")
            else:
                system_prompt = (
                    "You are a professional and witty food critic who excels at writing vivid and "
                    "interesting reviews based on restaurant information. "
                    "Interact with users in a humorous yet professional tone, providing valuable dining recommendations. "
                    "Your reviews should include comprehensive analysis of food quality, atmosphere, and service standards. "
                    "Always respond in Traditional Chinese and use emojis appropriately to add fun and engagement."
                )
                user_prompt_template = "Below is the restaurant information:\n{info}\n\nPlease write a professional and witty food review in Traditional Chinese based on the above information, adding appropriate emojis."
                preparing_msg = "📝 Preparing professional review..."
                config_error_msg = "❌ Review model not correctly configured"

            store_info_text = json.dumps({
                "restaurant_name": self.result.get("name", ""),
                "rating": f"{self.result.get('rating', 0)}/5.0",
                "category": self.result.get("category", ""),
                "address": self.result.get("address", ""),
                "reviews": self.result.get("reviews", []),
            }, ensure_ascii=False, indent=2)

            await interaction.response.defer(ephemeral=True)
            message_to_edit = await interaction.followup.send(preparing_msg, ephemeral=True)

            model_manager = ModelManager()
            try:
                model_priority_list = model_manager.get_model_priority_list("review_model")
            except ValueError as e:
                await func.report_error(e, "EatDetailView.review_button - no review_model configured")
                await safe_edit_message(message_to_edit, config_error_msg)
                return

            messages = [
                HumanMessage(content=user_prompt_template.format(info=store_info_text))
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
                error_msg = self.lang_manager.translate(self.guild_id, "commands", "eat", "views", "detail", "responses", "review_failed", error=str(last_exception)[:100]) if self.lang_manager else f"❌ Review generation failed: {str(last_exception)[:100]}"
                await safe_edit_message(message_to_edit, error_msg)
                await func.report_error(last_exception, "EatDetailView.review_button - all models failed")

        except Exception as e:
            await func.report_error(e, "EatDetailView.review_button")

    @discord.ui.button(emoji="👍", style=discord.ButtonStyle.success, row=1)
    async def like_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._rated:
            msg = self.lang_manager.translate(self.guild_id, "commands", "eat", "views", "detail", "responses", "already_rated") if self.lang_manager else "Already rated!"
            await interaction.response.send_message(msg, ephemeral=True)
            return
        self._rated = True
        self.db.updateRecordRate(id=self.record_id, new_rate=1)
        button.disabled = True
        self.dislike_button.disabled = True
        await interaction.response.edit_message(view=self)
        msg = self.lang_manager.translate(self.guild_id, "commands", "eat", "views", "detail", "responses", "rate_success") if self.lang_manager else "Thanks for your feedback! We will recommend similar places in the future 😊"
        await interaction.followup.send(msg, ephemeral=True)

    @discord.ui.button(emoji="👎", style=discord.ButtonStyle.danger, row=1)
    async def dislike_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._rated:
            msg = self.lang_manager.translate(self.guild_id, "commands", "eat", "views", "detail", "responses", "already_rated") if self.lang_manager else "Already rated!"
            await interaction.response.send_message(msg, ephemeral=True)
            return
        modal = DislikeModal(db=self.db, record_id=self.record_id, detail_view=self, lang_manager=self.lang_manager, guild_id=self.guild_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Back to List", emoji="↩️", style=discord.ButtonStyle.secondary, row=1)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """返回 EatBrowseView。"""
        view = EatBrowseView(
            results=self.browse_results,
            keyword=self.keyword,
            db=self.db,
            discord_id=self.discord_id,
            provider=self.provider,
            initial_index=self.browse_index,
            lang_manager=self.lang_manager,
            guild_id=self.guild_id
        )
        embed = browseEmbed(self.browse_results, self.browse_index, lang_manager=self.lang_manager, guild_id=self.guild_id)
        await interaction.response.edit_message(embed=embed, view=view)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


# ──────────────────────────────────────────────
# EatBrowseView (Main multi-result browsing View)
# ──────────────────────────────────────────────

class EatBrowseView(discord.ui.View):
    """Multi-result browsing View, supporting pagination and dropdown selection."""

    def __init__(self, results: list, keyword: str, db: DB,
                 discord_id: str, provider, initial_index: int = 0,
                 lang_manager=None, guild_id: str = "0"):
        super().__init__(timeout=300)
        self.results = results
        self.keyword = keyword
        self.db = db
        self.discord_id = discord_id
        self.provider = provider
        self.current_index = initial_index
        self.lang_manager = lang_manager
        self.guild_id = guild_id
        self._max_viewed_index = initial_index  # Only allow users to see "explored" items in the menu
        self._is_fetching = False  # Track fetching state after button click

        self._update_labels()
        self._rebuild_select()
        self._update_nav_buttons()

    def _update_labels(self):
        if self.lang_manager:
            self.prev_button.label = self.lang_manager.translate(self.guild_id, "commands", "eat", "views", "browse", "buttons", "prev")
            self.next_button.label = self.lang_manager.translate(self.guild_id, "commands", "eat", "views", "browse", "buttons", "next")
            self.confirm_button.label = self.lang_manager.translate(self.guild_id, "commands", "eat", "views", "browse", "buttons", "confirm")
            self.regenerate_button.label = self.lang_manager.translate(self.guild_id, "commands", "eat", "views", "browse", "buttons", "regenerate")

        # Start background prefetch task (only for items not yet detailed)
        self._prefetch_task = None
        if any(not r.get("is_detailed", True) for r in self.results):
            self._prefetch_task = asyncio.create_task(self._background_prefetch())

    async def _background_prefetch(self):
        """Complete detailed restaurant info in the background one by one."""
        # For performance, we only prefetch the first 10-15 candidates
        limit = min(15, len(self.results))
        for i in range(limit):
            if self.results[i].get("is_detailed", False):
                continue
            
            url = self.results[i].get("maps_url", "")
            if url:
                try:
                    # Time-consuming operation (Selenium navigation)
                    detail = await self.provider.async_fetch_detail(url)
                    if detail:
                        # Update data in cache, preserving original order
                        self.results[i].update(detail)
                        self.results[i]["is_detailed"] = True
                        logger.info(f"Background prefetch completed: {self.results[i].get('name')}")
                except Exception as e:
                    logger.warning(f"Background prefetch failed ({url}): {e}")
            
            # Small delay to avoid excessive competition for WebDriver lock
            await asyncio.sleep(1)

    def _rebuild_select(self):
        """Rebuild dropdown menu (dynamic options must be rebuilt each time)."""
        # Remove old Select (if exists)
        for child in list(self.children):
            if isinstance(child, discord.ui.Select):
                self.remove_item(child)

        # Decide display range (only show explored items or current item)
        # Based on user request: "Search results should only be added to list when re-searching"
        # So we only loop up to _max_viewed_index
        viewable_results = self.results[:self._max_viewed_index + 1]
        
        start_idx = 0
        if len(viewable_results) > 25:
            start_idx = max(0, self.current_index - 12)
            if start_idx + 25 > len(viewable_results):
                start_idx = len(viewable_results) - 25

        options = []
        for i in range(start_idx, min(start_idx + 25, len(viewable_results))):
            place = viewable_results[i]
            name = place.get("name", f"Restaurant {i+1}")
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
            placeholder = self.lang_manager.translate(self.guild_id, "commands", "eat", "views", "browse", "placeholder") if self.lang_manager else "Select a restaurant from the dropdown menu..."
            select = discord.ui.Select(
                placeholder=placeholder,
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
        embed = browseEmbed(self.results, self.current_index, lang_manager=self.lang_manager, guild_id=self.guild_id)
        await interaction.response.edit_message(embed=embed, view=self)

    def _update_nav_buttons(self):
        self.prev_button.disabled = (self.current_index == 0)
        self.next_button.disabled = (self.current_index >= len(self.results) - 1)

    @discord.ui.button(label="Previous", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_index -= 1
        self._rebuild_select()
        self._update_nav_buttons()
        embed = browseEmbed(self.results, self.current_index, lang_manager=self.lang_manager, guild_id=self.guild_id)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Next", emoji="▶️", style=discord.ButtonStyle.secondary, row=1)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_index += 1
        self._rebuild_select()
        self._update_nav_buttons()
        embed = browseEmbed(self.results, self.current_index, lang_manager=self.lang_manager, guild_id=self.guild_id)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Choose this!", emoji="✅", style=discord.ButtonStyle.success, row=2)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm selection of current restaurant, switch to EatDetailView."""
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
            lang_manager=self.lang_manager,
            guild_id=self.guild_id
        )
        embed = eatEmbed(
            keyword=self.keyword,
            title=result.get("name", ""),
            address=result.get("address", ""),
            rating=result.get("rating", 0),
            photo_url=result.get("photo_url", ""),
            price_level=result.get("price_level", 0),
            opening_hours=result.get("opening_hours", []),
            lang_manager=self.lang_manager,
            guild_id=self.guild_id
        )
        await interaction.response.edit_message(embed=embed, view=detail_view)

    @discord.ui.button(label="Next Recommendation", emoji="🔄", style=discord.ButtonStyle.primary, row=2)
    async def regenerate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Switch to next result. If data is not ready, perform real-time fetch."""
        if not self.results:
            return

        next_index = (self.current_index + 1) % len(self.results)
        
        # Unlock next entry only when user clicks "Re-search"
        if next_index > self._max_viewed_index:
            self._max_viewed_index = next_index

        self.current_index = next_index
        target_res = self.results[self.current_index]

        # Check if real-time fetch is needed (if background task hasn't finished)
        if not target_res.get("is_detailed", False):
            await interaction.response.edit_message(embed=loadingEmbed(target_res.get("name", "餐廳"), lang_manager=self.lang_manager, guild_id=self.guild_id), view=None)
            self._is_fetching = True
            try:
                url = target_res.get("maps_url", "")
                detail = await self.provider.async_fetch_detail(url)
                if detail:
                    self.results[self.current_index].update(detail)
                    self.results[self.current_index]["is_detailed"] = True
            except Exception as e:
                logger.error(f"Real-time detail fetch failed: {e}")
            self._is_fetching = False
            # Update after fetching
            self._rebuild_select()
            self._update_nav_buttons()
            embed = browseEmbed(self.results, self.current_index, lang_manager=self.lang_manager, guild_id=self.guild_id)
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            # Data ready, update directly
            self._rebuild_select()
            self._update_nav_buttons()
            embed = browseEmbed(self.results, self.current_index, lang_manager=self.lang_manager, guild_id=self.guild_id)
            await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


# Legacy class aliases for backward compatibility
EatWhatView = EatBrowseView
