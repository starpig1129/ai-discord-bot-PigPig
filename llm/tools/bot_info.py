"""Bot info tools for LLM integration.

Provides a tool for the AI agent to query the bot's own GitHub release
history to answer questions about recent updates and changelog.
All tools are routed to the info_agent via target_agent_mode = "info".
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools.structured import StructuredTool

from addons.logging import get_logger
from addons.settings import update_config
from addons.update.checker import VersionChecker

if TYPE_CHECKING:
    from llm.schema import OrchestratorRequest

_logger = get_logger(server_id="Bot", source="llm.tools.bot_info")


class BotInfoTools:
    """Container for bot self-information tools."""

    def __init__(self, runtime: "OrchestratorRequest") -> None:
        self.runtime = runtime
        self.logger = getattr(runtime, "logger", _logger)
        self._checker = VersionChecker(github_config=update_config.github)

    def get_tools(self) -> list:
        """Return bot info tools."""
        logger = self.logger
        checker = self._checker

        async def get_bot_changelog() -> str:
            """Fetches the bot's latest GitHub release notes to show recent updates.

            Returns the current version, latest version, whether an update is
            available, the release notes, and the published date.
            Use when the user asks what the bot was recently updated with.
            """
            try:
                info = await checker.check_for_updates()

                if "error" in info:
                    return f"無法取得更新資訊：{info['error']}"

                current = info.get("current_version", "unknown")
                latest = info.get("latest_version", "unknown")
                update_available = info.get("update_available", False)
                notes = info.get("release_notes", "").strip()
                published = info.get("published_at", "")[:10]  # YYYY-MM-DD

                lines = [
                    f"## 機器人版本資訊",
                    f"- 目前版本：{current}",
                    f"- 最新版本：{latest}",
                    f"- 有新版本可用：{'是' if update_available else '否'}",
                ]
                if published:
                    lines.append(f"- 發布日期：{published}")
                if notes:
                    lines.append(f"\n### 更新內容\n{notes}")
                else:
                    lines.append("\n（無更新說明）")

                return "\n".join(lines)

            except Exception as e:
                logger.warning(f"get_bot_changelog failed: {e}")
                return f"取得版本資訊時發生錯誤：{e}"

        _info_meta = {"target_agent_mode": "info"}
        return [
            StructuredTool.from_function(
                func=None,
                name="get_bot_changelog",
                metadata=_info_meta,
                coroutine=get_bot_changelog,
                description=get_bot_changelog.__doc__,
            )
        ]
