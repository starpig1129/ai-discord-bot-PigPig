"""LangChain tool for the bot to modify its own system prompt.

The LLM reads its current personality from the system-prompt context it
already has, generates a merged version, and calls this tool to write it.
Only the write side lives here — no extra LLM call is needed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.tools.structured import StructuredTool

from addons.logging import get_logger

if TYPE_CHECKING:
    from llm.schema import OrchestratorRequest

_logger = get_logger(server_id="Bot", source="llm.tools.system_prompt_tools")

__all__ = ["write_personality", "SystemPromptTools"]


async def write_personality(
    guild_id: str,
    channel_id: str,
    merged_prompt: str,
    scope: str,
    bot: Any,
    user_id: str,
) -> str:
    """Write a merged personality string to the system prompt store.

    Args:
        guild_id: Discord guild ID string.
        channel_id: Discord channel ID string.
        merged_prompt: The complete merged system prompt text.
        scope: "channel" or "server".
        bot: The discord.ext.commands.Bot instance.
        user_id: ID of the user requesting the change (for audit).

    Returns:
        A human-readable confirmation or error string.
    """
    from cogs.system_prompt.exceptions import ContentTooLongError, UnsafeContentError

    cog = bot.get_cog("SystemPromptManagerCog")
    if cog is None:
        return "Error: SystemPromptManagerCog is not loaded. Cannot save personality."

    manager = cog.get_system_prompt_manager()
    prompt_data: dict[str, Any] = {"prompt": merged_prompt, "enabled": True}

    try:
        if scope == "server":
            manager.set_server_prompt(guild_id, prompt_data, user_id)
            manager.cache.invalidate(guild_id)
            return "Personality updated successfully for the entire server."
        else:
            manager.set_channel_prompt(guild_id, channel_id, prompt_data, user_id)
            manager.cache.invalidate(guild_id, channel_id)
            return "Personality updated successfully for this channel."
    except ContentTooLongError as exc:
        return f"Error: The prompt is too long ({exc}). Please shorten your description."
    except UnsafeContentError as exc:
        return f"Error: The prompt contains unsafe content ({exc}). Please revise."
    except Exception as exc:
        _logger.error(f"write_personality failed: {exc}")
        return f"Error saving personality: {exc}"


class SystemPromptTools:
    """Container for the bot's self-modification tool."""

    def __init__(self, runtime: "OrchestratorRequest") -> None:
        """Initialize with the orchestrator runtime context.

        Args:
            runtime: The current OrchestratorRequest context.
        """
        self.runtime = runtime
        self.logger = getattr(runtime, "logger", _logger)

    def get_tools(self) -> list:
        """Return the list of self-modification tools.

        Returns:
            List containing the update_personality StructuredTool.
        """
        runtime = self.runtime

        async def update_personality(merged_prompt: str, scope: str = "channel") -> str:
            """Modify the bot's personality or system prompt for this channel or server.

            You already know your current personality from the system prompt in your
            context. Generate a COMPLETE merged version incorporating the user's
            requested changes (do not just write the delta), then call this tool.

            Args:
                merged_prompt: The complete merged system prompt text — your current
                    personality with the requested changes incorporated. Must be a
                    full system prompt, not just the changed part.
                scope: "channel" applies only to the current channel (any user may
                    do this). "server" applies to the entire server (admin only).

            Returns:
                Confirmation message or an error description.
            """
            message = getattr(runtime, "message", None)
            if message is None:
                return "Error: No message context available."

            guild = getattr(message, "guild", None)
            channel = getattr(message, "channel", None)
            author = getattr(message, "author", None)

            if guild is None or channel is None or author is None:
                return "Error: Cannot determine guild, channel, or author."

            guild_id = str(guild.id)
            channel_id = str(channel.id)
            user_id = str(author.id)
            bot = getattr(runtime, "bot", None)

            if scope == "server":
                from cogs.system_prompt.permissions import PermissionValidator
                validator = PermissionValidator(bot)
                if not validator.can_modify_server_prompt(author, guild):
                    return (
                        "Error: You need administrator permissions to modify the "
                        "server-level personality."
                    )

            return await write_personality(guild_id, channel_id, merged_prompt, scope, bot, user_id)

        _message_meta: dict[str, str] = {"target_agent_mode": "message"}
        return [
            StructuredTool.from_function(
                func=None,
                name="update_personality",
                metadata=_message_meta,
                coroutine=update_personality,
                description=update_personality.__doc__,
            )
        ]
