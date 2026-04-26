"""Server context tools for LLM integration.

Provides tools for the AI agent to query Discord server, channel, and
member information at runtime. All tools are routed to the info_agent
via target_agent_mode = "info".
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import discord
from langchain_core.tools.structured import StructuredTool

from addons.logging import get_logger

if TYPE_CHECKING:
    from llm.schema import OrchestratorRequest

_logger = get_logger(server_id="Bot", source="llm.tools.server_context")


class ServerContextTools:
    """Container for Discord server/channel/user info query tools."""

    def __init__(self, runtime: "OrchestratorRequest") -> None:
        self.runtime = runtime
        self.logger = getattr(self.runtime, "logger", _logger)

    def get_tools(self) -> list:
        """Return server context query tools."""
        runtime = self.runtime

        def get_server_context() -> str:
            """Queries basic information about the current Discord server.

            Returns server name, member count, boost level, roles, channels.
            Use when you need to understand the server context.
            """
            message = getattr(runtime, "message", None)
            if not message or not message.guild:
                return "No server (guild) context available."

            guild: discord.Guild = message.guild
            lines = [
                f"## Server: {guild.name} (ID: {guild.id})",
                f"- Members: {guild.member_count}",
                f"- Boost Level: {guild.premium_tier} "
                f"({guild.premium_subscription_count} boosts)",
                f"- Owner: {guild.owner.display_name if guild.owner else 'Unknown'}",
                f"- Created: {guild.created_at.strftime('%Y-%m-%d') if guild.created_at else 'Unknown'}",
            ]

            roles = [r for r in guild.roles if r.name != "@everyone"]
            roles.sort(key=lambda r: r.position, reverse=True)
            role_names = [r.name for r in roles[:20]]
            remaining = max(0, len(roles) - 20)
            suffix = f" ...and {remaining} more" if remaining else ""
            lines.append(f"- Roles ({len(roles)}): {', '.join(role_names)}{suffix}")

            text_channels = sorted(
                [ch for ch in guild.channels if isinstance(ch, discord.TextChannel)],
                key=lambda c: c.position,
            )
            ch_names = [f"#{ch.name}" for ch in text_channels[:25]]
            remaining = max(0, len(text_channels) - 25)
            suffix = f" ...and {remaining} more" if remaining else ""
            lines.append(f"- Text Channels ({len(text_channels)}): {', '.join(ch_names)}{suffix}")

            voice_channels = [ch for ch in guild.channels if isinstance(ch, discord.VoiceChannel)]
            if voice_channels:
                vc_names = [f"🔊{ch.name}" for ch in voice_channels[:15]]
                lines.append(f"- Voice Channels ({len(voice_channels)}): {', '.join(vc_names)}")

            return "\n".join(lines)

        def get_channel_context(channel_name: Optional[str] = None) -> str:
            """Queries detailed info about a specific channel.

            If no channel_name is provided, returns info about the current channel.

            Args:
                channel_name: Optional channel name to look up.
            """
            message = getattr(runtime, "message", None)
            if not message or not message.guild:
                return "No server context available."

            guild: discord.Guild = message.guild
            target_channel = None

            if channel_name:
                search_name = channel_name.lstrip("#").lower()
                for ch in guild.channels:
                    if ch.name.lower() == search_name:
                        target_channel = ch
                        break
                if not target_channel:
                    return f"Channel '{channel_name}' not found in this server."
            else:
                target_channel = message.channel

            lines = [f"## Channel: #{target_channel.name} (ID: {target_channel.id})"]

            if hasattr(target_channel, "category") and target_channel.category:
                lines.append(f"- Category: {target_channel.category.name}")

            if isinstance(target_channel, discord.TextChannel):
                topic = target_channel.topic or "(no topic set)"
                lines.append(f"- Topic: {topic}")
                lines.append(f"- NSFW: {target_channel.nsfw}")
                if target_channel.slowmode_delay:
                    lines.append(f"- Slowmode: {target_channel.slowmode_delay}s")
                if hasattr(target_channel, "members"):
                    online = sum(
                        1 for m in target_channel.members
                        if not m.bot and m.status != discord.Status.offline
                    )
                    lines.append(f"- Online members with access: ~{online}")

            elif isinstance(target_channel, discord.VoiceChannel):
                lines.append(f"- Connected: {len(target_channel.members)} users")
                lines.append(f"- Bitrate: {target_channel.bitrate // 1000}kbps")
                lines.append(f"- User limit: {target_channel.user_limit or 'Unlimited'}")
                if target_channel.members:
                    names = [m.display_name for m in target_channel.members[:20]]
                    lines.append(f"- Users: {', '.join(names)}")

            return "\n".join(lines)

        def get_user_discord_info(user_id: Optional[str] = None) -> str:
            """Queries a member's Discord profile within this server.

            Returns join date, roles, nickname, current activity/status.
            If no user_id is provided, returns info about the message sender.

            Args:
                user_id: Optional Discord user ID. Defaults to message author.
            """
            message = getattr(runtime, "message", None)
            if not message or not message.guild:
                return "No server context available."

            guild: discord.Guild = message.guild
            member: Optional[discord.Member] = None

            if user_id:
                try:
                    member = guild.get_member(int(user_id))
                except (ValueError, TypeError):
                    return f"Invalid user ID format: {user_id}"
            else:
                member = (
                    message.author
                    if isinstance(message.author, discord.Member)
                    else guild.get_member(message.author.id)
                )

            if not member:
                return f"User {user_id or 'author'} not found in this server."

            lines = [
                f"## User: {member.display_name} ({member.name}#{member.discriminator})",
                f"- User ID: {member.id}",
            ]

            if member.joined_at:
                days_ago = (discord.utils.utcnow() - member.joined_at).days
                lines.append(f"- Joined: {member.joined_at.strftime('%Y-%m-%d')} ({days_ago} days ago)")

            if member.created_at:
                lines.append(f"- Account Created: {member.created_at.strftime('%Y-%m-%d')}")

            if member.nick:
                lines.append(f"- Server Nickname: {member.nick}")

            roles = [r.name for r in member.roles if r.name != "@everyone"]
            if roles:
                lines.append(f"- Roles: {', '.join(reversed(roles))}")

            status_map = {
                discord.Status.online: "🟢 Online",
                discord.Status.idle: "🌙 Idle",
                discord.Status.dnd: "⛔ Do Not Disturb",
                discord.Status.offline: "⚫ Offline",
            }
            lines.append(f"- Status: {status_map.get(member.status, str(member.status))}")

            if member.activities:
                for activity in member.activities[:3]:
                    if isinstance(activity, discord.Spotify):
                        lines.append(f"- 🎵 Spotify: {activity.title} by {activity.artist}")
                    elif isinstance(activity, discord.Game):
                        lines.append(f"- 🎮 Playing: {activity.name}")
                    elif isinstance(activity, discord.CustomActivity):
                        emoji = f"{activity.emoji} " if activity.emoji else ""
                        lines.append(f"- Custom Status: {emoji}{activity.name or ''}")
                    elif isinstance(activity, discord.Streaming):
                        lines.append(f"- 📺 Streaming: {activity.name}")
                    else:
                        lines.append(f"- {activity.type.name.capitalize()}: {activity.name}")

            if member.top_role and member.top_role.name != "@everyone":
                lines.append(f"- Top Role Color: {member.top_role.color}")

            return "\n".join(lines)

        _info_meta = {"target_agent_mode": "info"}
        return [
            StructuredTool.from_function(func=get_server_context, metadata=_info_meta),
            StructuredTool.from_function(func=get_channel_context, metadata=_info_meta),
            StructuredTool.from_function(func=get_user_discord_info, metadata=_info_meta),
        ]
