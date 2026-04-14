from addons.logging import get_logger
from typing import Optional, Any, TYPE_CHECKING, List, Dict

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
        def get_user_activity(target_user_id: Optional[str] = None) -> str:
            """
            Gets the current activity status of a user (game, stream, music, etc.).
            
            Use this tool when you want to know what a user is currently doing, playing, or listening to.
            If no target_user_id is provided, it checks the user who sent the message.
            
            Args:
                target_user_id: Optional ID of the user to check.
            """
            message = getattr(runtime, "message", None)
            if not message or not message.guild:
                return "No guild context available."

            # Determine target member
            target_member = None
            if target_user_id:
                try:
                    target_member = message.guild.get_member(int(target_user_id))
                except ValueError:
                    return f"Invalid user ID format: {target_user_id}"
            else:
                target_member = message.author

            if not target_member:
                return "User not found in this server."

            # Collect activities
            activities = target_member.activities
            if not activities:
                status_map = {
                    discord.Status.online: "Online",
                    discord.Status.idle: "Idle",
                    discord.Status.dnd: "Do Not Disturb",
                    discord.Status.offline: "Offline",
                    discord.Status.invisible: "Invisible"
                }
                status = status_map.get(target_member.status, str(target_member.status))
                return f"User {target_member.display_name} is currently {status} with no specific activities."

            import datetime
            def _format_duration(start_time):
                if not start_time: return ""
                try:
                    now = datetime.datetime.now(datetime.timezone.utc)
                    # Some activity.start are naive datetimes, some are aware
                    if start_time.tzinfo is None:
                        start_time = start_time.replace(tzinfo=datetime.timezone.utc)
                    diff = now - start_time
                    if diff.total_seconds() < 0: return ""
                    hours, remainder = divmod(int(diff.total_seconds()), 3600)
                    minutes, _ = divmod(remainder, 60)
                    duration_strs = []
                    if hours > 0: duration_strs.append(f"{hours}h")
                    if minutes > 0: duration_strs.append(f"{minutes}m")
                    return f" (for {' '.join(duration_strs)} so far)" if duration_strs else " (just started)"
                except Exception:
                    return ""

            activity_list = []
            for activity in activities:
                duration_str = _format_duration(getattr(activity, "start", None))
                if isinstance(activity, discord.Spotify):
                    activity_list.append(f"- Listening to Spotify: {activity.title} by {activity.artist}{duration_str}")
                elif isinstance(activity, discord.Game):
                    activity_list.append(f"- Playing Game: {activity.name}{duration_str}")
                elif isinstance(activity, discord.Streaming):
                    activity_list.append(f"- Streaming: {activity.name} (URL: {activity.url}){duration_str}")
                elif isinstance(activity, discord.CustomActivity):
                    emoji = str(activity.emoji) + " " if activity.emoji else ""
                    activity_list.append(f"- Custom Status: {emoji}{activity.name}")
                else:
                    # Generic activity fallback
                    type_name = activity.type.name.capitalize()
                    activity_list.append(f"- {type_name}: {activity.name}{duration_str}")

            return f"## Activity Status for {target_member.display_name}\n" + "\n".join(activity_list)

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

        return [get_user_activity, get_channel_participants]
