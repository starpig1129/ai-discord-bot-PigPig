import re
from datetime import datetime
from typing import Optional
from addons.logging import get_logger

import discord
from discord.ext import commands
from discord import app_commands
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, AIMessage
from langchain.agents.middleware import ModelCallLimitMiddleware

from function import func
from llm.model_manager import ModelManager
from .language_manager import LanguageManager

log = get_logger(source=__name__, server_id="system")


class SummarizerCog(commands.Cog):
    """Cog for conversation summarization using AI with source mapping and character limits."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.MAX_CHAR_COUNT = 15000
        self.EMBED_DESC_LIMIT = 4000
        self.lang_manager: Optional[LanguageManager] = None

    async def cog_load(self):
        """Initialize LanguageManager when the cog is loaded."""
        self.lang_manager = LanguageManager.get_instance(self.bot)

    def _split_text_robustly(self, text: str):
        """
        Split long text into multiple chunks safely, handling exceptionally long single lines.
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

    @app_commands.command(name="summarize", description="Summarize channel conversation with source tagging.")
    @app_commands.describe(
        limit="Maximum number of messages to search (default 100)",
        persona="Set AI's persona for the summary (e.g., A professional clerk)",
        only_me="Whether only you can see this summary (default False)"
    )
    async def summarize(self, interaction: discord.Interaction, limit: int = 100, persona: Optional[str] = None, only_me: bool = False):
        """Analyze and summarize recent channel conversation history using an AI agent."""
        guild_id = str(interaction.guild_id) if interaction.guild_id else "0"
        
        # Localize command description and parameters if possible
        if self.lang_manager:
            localized_desc = self.lang_manager.translate(guild_id, "commands", "summarize", "description")
            if localized_desc and localized_desc != "summarize":
                self.summarize.description = localized_desc

        await interaction.response.defer(ephemeral=only_me, thinking=True)

        try:
            log.info(f"Starting message fetch for channel {interaction.channel.name if hasattr(interaction.channel, 'name') else 'unknown'}, limit: {limit}.")
            history = [msg async for msg in interaction.channel.history(limit=limit)]
            dialogue_history_reversed = []
            source_mapping = {}
            current_char_count = 0
            human_msg_count = 0  # Only count messages from human users

            for msg in history:  # Iterate from newest to oldest
                if not msg.content:  # Skip messages with no text content (e.g., embeds only)
                    continue

                formatted_content = ""
                timestamp = msg.created_at.strftime('%Y-%m-%d %H:%M')

                if msg.author.bot:
                    # Concise placeholder for bot messages
                    formatted_content = f"({timestamp}) [Bot @{msg.author.display_name}'s message]"
                    # Bots as AIMessage for context
                    dialogue_history_reversed.append(AIMessage(content=formatted_content))
                else:
                    # Detailed format for human messages with MSG-ID
                    human_msg_count += 1
                    msg_id = f"MSG-{human_msg_count}"
                    source_mapping[msg_id] = msg.jump_url
                    formatted_content = f"[{msg_id}] ({timestamp}) {msg.content}"
                    # Humans as HumanMessage
                    dialogue_history_reversed.append(HumanMessage(content=formatted_content, name=msg.author.display_name))

                # Check character count limit
                content_len = len(formatted_content)
                if current_char_count + content_len > self.MAX_CHAR_COUNT:
                    log.warning(f"Reached character limit {self.MAX_CHAR_COUNT}. Stopping message collection.")
                    break

                current_char_count += content_len

            # Reverse to chronological order (oldest to newest)
            dialogue_history = list(reversed(dialogue_history_reversed))

            if not dialogue_history or human_msg_count == 0:
                no_msg_text = self.lang_manager.translate(guild_id, "commands", "summarize", "responses", "no_messages") if self.lang_manager else "No messages to summarize."
                await interaction.followup.send(no_msg_text, ephemeral=True)
                return

            # Localization for AI prompt
            if self.lang_manager:
                persona_instruction = ""
                if persona:
                    persona_instruction = self.lang_manager.translate(guild_id, "commands", "summarize", "ai", "persona_prefix", persona=persona)
                
                system_prompt_template = self.lang_manager.translate(guild_id, "commands", "summarize", "ai", "system_prompt")
                system_prompt = system_prompt_template.replace("{persona_instruction}", persona_instruction)
                user_instruction = self.lang_manager.translate(guild_id, "commands", "summarize", "ai", "user_instruction")
            else:
                # Fallback System Prompt (Traditional Chinese as original)
                system_prompt = f"Summarize the conversation clearly. Highlight core themes and action items. Tag sources with [MSG-ID]. {f'Persona: {persona}' if persona else ''}"
                user_instruction = "Start summary."

            log.info(f"Calling LLM for summary... (Analyzing {human_msg_count} human messages, {current_char_count} chars total)")

            # Initialize Agent
            model_name, fallback = ModelManager().get_model("summarize_model")
            model_instance = init_chat_model(model_name, max_retries=0)
            
            summarize_agent = create_agent(
                model=model_instance,
                tools=[],
                system_prompt=system_prompt,
                middleware=[
                    fallback,
                    ModelCallLimitMiddleware(run_limit=1, exit_behavior="end"),
                ]
            )

            # Append user instruction and ensure all messages are proper instances
            messages = dialogue_history + [HumanMessage(content=user_instruction)]

            # Invoke agent
            response = await summarize_agent.ainvoke({"messages": messages})

            full_summary = response["messages"][-1].content
            log.info("Summary generated, starting post-processing.")

            def replace_with_link(match):
                ids = re.findall(r'MSG-\d+', match.group(0))
                source_text = self.lang_manager.translate(guild_id, "commands", "summarize", "embed", "source") if self.lang_manager else "Source"
                links = [f"[[{source_text}-{msg_id.split('-')[1]}]]({source_mapping.get(msg_id)})" for msg_id in ids if source_mapping.get(msg_id)]
                return ' '.join(links) if links else match.group(0)

            processed_summary = re.sub(r'\[(MSG-\d+(?:,\s*MSG-\d+)*)\]', replace_with_link, full_summary)
            summary_chunks = self._split_text_robustly(processed_summary)
            
            title = self.lang_manager.translate(guild_id, "commands", "summarize", "embed", "title") if self.lang_manager else "Conversation Summary"
            main_embed = discord.Embed(
                title=title,
                description=summary_chunks[0],
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            
            if self.lang_manager:
                footer_text = self.lang_manager.translate(
                    guild_id, "commands", "summarize", "embed", "footer",
                    count=human_msg_count, limit=limit, current=current_char_count, max=self.MAX_CHAR_COUNT
                )
            else:
                footer_text = f"Analyzed {human_msg_count} messages. {current_char_count}/{self.MAX_CHAR_COUNT} chars."
                
            main_embed.set_footer(text=footer_text)
            await interaction.followup.send(embed=main_embed)
            
            if len(summary_chunks) > 1:
                log.info(f"Summary long, splitting into {len(summary_chunks)} messages.")
                for i, chunk in enumerate(summary_chunks[1:], 1):
                    continuation_embed = discord.Embed(description=chunk, color=discord.Color.blue())
                    if self.lang_manager:
                        cont_footer = self.lang_manager.translate(
                            guild_id, "commands", "summarize", "embed", "continuation_footer",
                            current=i+1, total=len(summary_chunks)
                        )
                    else:
                        cont_footer = f"Summary continuation... ({i+1}/{len(summary_chunks)})"
                    continuation_embed.set_footer(text=cont_footer)
                    await interaction.followup.send(embed=continuation_embed)

        except Exception as e:
            await func.report_error(e, "summarizing channel")
            error_text = self.lang_manager.translate(guild_id, "commands", "summarize", "responses", "error", error=str(e)) if self.lang_manager else f"Error: {e}"
            await interaction.followup.send(error_text, ephemeral=True)


async def setup(bot: commands.Bot):
    """Set up the SummarizerCog."""
    await bot.add_cog(SummarizerCog(bot))