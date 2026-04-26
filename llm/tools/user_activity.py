from addons.logging import get_logger
from typing import TYPE_CHECKING

import discord
from langchain_core.tools import tool

if TYPE_CHECKING:
    from llm.schema import OrchestratorRequest

# Module-level logger
_logger = get_logger(server_id="Bot", source="llm.tools.user_activity")

class UserActivityTools:
    """Tools for inspecting user activities and status."""

    def __init__(self, runtime: "OrchestratorRequest"):
        self.runtime = runtime
        self.logger = getattr(self.runtime, "logger", _logger)

    def get_tools(self) -> list:
        runtime = self.runtime

        @tool
        def get_channel_participants() -> str:
            """
            Gets a list of active users in the current channel (voice or text).
            
            Use this tool to see who else is present in the conversation context.
            For voice channels, it lists connected members.
            For text channels, it lists members who recently typed or are online.
            """
            message = getattr(runtime, "message", None)
            if not message or not message.channel:
                return "No channel context available."

            channel = message.channel
            
            # Voice Channel Logic
            if isinstance(channel, discord.VoiceChannel):
                members = channel.members
                if not members:
                    return "The voice channel is currently empty."
                
                member_list = [f"- {m.display_name}" for m in members]
                return f"## Users in Voice Channel '{channel.name}'\n" + "\n".join(member_list)
            
            # Text Channel Logic (Active/Online members)
            # Note: Getting "active" users in text is tricky. We'll list online members with access.
            # To avoid spam, we limit to a reasonable number.
            elif hasattr(channel, "members"):
                # Filter for non-bot humans who are not offline
                active_members = [
                    m for m in channel.members 
                    if not m.bot and m.status != discord.Status.offline
                ]
                # Sort by status (Online > Idle > DND)
                active_members.sort(key=lambda m: (
                    0 if m.status == discord.Status.online else
                    1 if m.status == discord.Status.idle else
                    2
                ))
                
                count = len(active_members)
                display_members = active_members[:20] # Limit to 20
                
                member_list = []
                for m in display_members:
                    status_icon = "🟢" if m.status == discord.Status.online else "🌙" if m.status == discord.Status.idle else "⛔"
                    
                    device_info = []
                    if getattr(m, "mobile_status", discord.Status.offline) != discord.Status.offline:
                        device_info.append("Mobile")
                    if getattr(m, "desktop_status", discord.Status.offline) != discord.Status.offline:
                        device_info.append("Desktop")
                    if getattr(m, "web_status", discord.Status.offline) != discord.Status.offline:
                        device_info.append("Web")
                        
                    dev_str = f" [{'/'.join(device_info)}]" if device_info else ""
                    member_list.append(f"- {status_icon} {m.display_name}{dev_str}")
                
                footer = f"\n...and {count - 20} more." if count > 20 else ""
                return f"## Active Users in '{channel.name}' ({count} total)\n" + "\n".join(member_list) + footer
            
            return "Cannot determine participants for this channel type."

        return [get_channel_participants]
