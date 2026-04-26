"""User stats tools for LLM integration.

Provides tools for the AI agent to retrieve user statistics as a text card
(for embedding in conversation) or generate a PNG stats image with word cloud
(sent as a Discord file attachment).
"""
from __future__ import annotations

import io
import asyncio
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

import discord
from langchain_core.tools.structured import StructuredTool

from addons.logging import get_logger
from function import func

if TYPE_CHECKING:
    from llm.schema import OrchestratorRequest

_logger = get_logger(server_id="Bot", source="llm.tools.user_stats")

# Font paths for CJK support in word cloud / Pillow rendering
_FONT_PATHS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto/NotoSansCJK-Regular.ttc",
]

# zh_TW fallback strings used when LanguageManager cog is unavailable
_ZH_TW_FALLBACK: Dict[str, str] = {
    "card.title": "📊 {name} 統計資料",
    "card.total_messages": "總訊息數: {total}",
    "card.most_active": "最活躍時段: {peak}",
    "card.peak_detail": "{period} {h}:00-{h_end}:00 ({count} 則)",
    "card.streak": "連續活躍: {streak} 天",
    "card.top_channels": "常用頻道: {channels}",
    "card.top_words": "常用詞彙: {words}",
    "card.top_emojis": "常用表情: {emojis}",
    "card.first_message": "初次發言: {date} ({days_ago})",
    "card.days_ago": "{days} 天前",
    "periods.morning": "早上",
    "periods.noon": "中午",
    "periods.afternoon": "下午",
    "periods.evening": "晚上",
    "periods.midnight": "深夜",
    "periods.dawn": "凌晨",
    "image.header": "總計: {total} 則  |  連續: {streak} 天",
    "image.top_channels": "常用頻道:",
    "image.activity_by_hour": "活躍時段:",
    "image.top_emojis": "常用表情: {emojis}",
}


def _find_cjk_font() -> Optional[str]:
    """Find the first available CJK font path on the system."""
    import os
    for path in _FONT_PATHS:
        if os.path.isfile(path):
            return path
    return None


def _make_t(bot: Any, guild_id: str) -> Callable[..., str]:
    """Build a translate helper bound to guild_id and the user_stats namespace.

    Falls back to zh_TW hardcoded strings when LanguageManager is unavailable.
    """
    lang_mgr = bot.get_cog("LanguageManager") if bot else None

    def t(*keys: str, **kwargs: Any) -> str:
        if lang_mgr is not None:
            return lang_mgr.translate(str(guild_id), "system", "user_stats", *keys, **kwargs)
        # Fallback: zh_TW hardcoded
        tmpl = _ZH_TW_FALLBACK.get(".".join(keys), keys[-1] if keys else "")
        try:
            return tmpl.format(**kwargs) if kwargs else tmpl
        except (KeyError, IndexError):
            return tmpl

    return t


class UserStatsTools:
    """Container for user statistics query and image generation tools."""

    def __init__(self, runtime: "OrchestratorRequest") -> None:
        self.runtime = runtime
        self.logger = getattr(self.runtime, "logger", _logger)

    def _get_stats_storage(self) -> Any:
        """Retrieve StatsStorage from StatsCog."""
        bot = getattr(self.runtime, "bot", None)
        if not bot:
            return None
        cog = bot.get_cog("StatsCog")
        if not cog:
            return None
        return getattr(cog, "stats_storage", None)

    def get_tools(self) -> list:
        """Return user stats tools."""
        runtime = self.runtime
        get_storage = self._get_stats_storage

        async def get_user_stats(user_id: Optional[str] = None) -> str:
            """Retrieves user activity statistics for this server.

            Sends a PNG stats image (word cloud + activity chart) to the channel,
            and returns a brief text summary for use in conversation.
            Call this whenever a user asks about their stats, activity, message count,
            word cloud, or usage history.

            Args:
                user_id: Optional Discord user ID. Defaults to message sender.

            Returns:
                A short text summary of the user's stats.
            """
            storage = get_storage()
            if not storage:
                return "Stats system is not available."

            message = getattr(runtime, "message", None)
            if not message or not message.guild:
                return "No server context available."

            effective_id = user_id or str(message.author.id)
            guild_id = str(message.guild.id)

            stats = await storage.get_user_stats(effective_id, guild_id)
            if not stats:
                return f"No stats found for user {effective_id} in this server."

            display_name = f"User {effective_id}"
            avatar_url = None
            try:
                member = message.guild.get_member(int(effective_id))
                if member:
                    display_name = member.display_name
                    avatar_url = (
                        member.display_avatar.url if member.display_avatar else None
                    )
            except (ValueError, TypeError):
                pass

            bot_obj = getattr(runtime, "bot", None)
            t = _make_t(bot_obj, guild_id)
            total = stats.get("total_messages", 0)
            streak = stats.get("streak_days", 0)

            # Pre-resolve image labels before entering executor
            image_labels = {
                "header": t("image", "header", total=f"{total:,}", streak=streak),
                "top_channels": t("image", "top_channels"),
                "activity_by_hour": t("image", "activity_by_hour"),
                "top_emojis_prefix": t("image", "top_emojis", emojis="").rstrip(),
            }

            # Generate and send the PNG image
            try:
                loop = asyncio.get_running_loop()
                image_bytes = await loop.run_in_executor(
                    None,
                    _generate_stats_image_sync,
                    display_name,
                    stats,
                    avatar_url,
                    image_labels,
                )
                await message.channel.send(
                    file=discord.File(
                        io.BytesIO(image_bytes),
                        filename=f"stats_{effective_id}.png",
                    )
                )
            except Exception as e:
                try:
                    await func.report_error(e, "get_user_stats image send failed")
                except Exception:
                    pass
                _logger.error("get_user_stats image failed: %s", e)

            # Always return text summary regardless of image success/failure
            return _format_text_card(display_name, stats, t)

        _info_meta = {"target_agent_mode": "info"}
        return [
            StructuredTool.from_function(coroutine=get_user_stats, metadata=_info_meta),
        ]


# ======================================================================
# Formatting helpers
# ======================================================================


def _format_text_card(
    display_name: str,
    stats: Dict[str, Any],
    t: Callable[..., str],
) -> str:
    """Format user stats into a readable text card using localized strings."""
    total = stats.get("total_messages", 0)
    streak = stats.get("streak_days", 0)
    first_msg = stats.get("first_message_at")

    # Most active hour
    active_hours: Dict[str, int] = stats.get("active_hours", {})
    peak_hour = ""
    if active_hours:
        sorted_hours = sorted(active_hours.items(), key=lambda x: x[1], reverse=True)
        h, count = sorted_hours[0]
        h_int = int(h)
        period_key = _hour_to_period_key(h_int)
        period = t("periods", period_key)
        peak_hour = t("card", "peak_detail", period=period, h=h_int, h_end=h_int + 1, count=f"{count:,}")

    # Top channels
    top_channels: Dict[str, int] = stats.get("top_channels", {})
    ch_lines = ""
    if top_channels:
        sorted_ch = sorted(top_channels.items(), key=lambda x: x[1], reverse=True)[:5]
        total_ch = sum(top_channels.values()) or 1
        ch_parts = [f"{name} ({count * 100 // total_ch}%)" for name, count in sorted_ch]
        ch_lines = ", ".join(ch_parts)

    # Top words
    top_words: Dict[str, int] = stats.get("top_words", {})
    words_line = ""
    if top_words:
        sorted_w = sorted(top_words.items(), key=lambda x: x[1], reverse=True)[:8]
        words_line = "、".join(w for w, _ in sorted_w)

    # Top emojis
    top_emojis: Dict[str, int] = stats.get("top_emojis", {})
    emoji_line = ""
    if top_emojis:
        sorted_e = sorted(top_emojis.items(), key=lambda x: x[1], reverse=True)[:6]
        emoji_line = "、".join(f"{e} × {c}" for e, c in sorted_e)

    # First message date
    first_msg_str = ""
    if first_msg:
        try:
            dt = datetime.fromisoformat(first_msg.replace("Z", "+00:00"))
            days_ago = (datetime.now(timezone.utc) - dt).days
            days_ago_str = t("card", "days_ago", days=days_ago)
            first_msg_str = t("card", "first_message", date=dt.strftime("%Y-%m-%d"), days_ago=days_ago_str)
        except (ValueError, TypeError):
            first_msg_str = str(first_msg)

    lines = [
        t("card", "title", name=display_name),
        "────────────",
        t("card", "total_messages", total=f"{total:,}"),
    ]
    if peak_hour:
        lines.append(t("card", "most_active", peak=peak_hour))
    lines.append(t("card", "streak", streak=streak))
    if ch_lines:
        lines.append(t("card", "top_channels", channels=ch_lines))
    if words_line:
        lines.append(t("card", "top_words", words=words_line))
    if emoji_line:
        lines.append(t("card", "top_emojis", emojis=emoji_line))
    if first_msg_str:
        lines.append(first_msg_str)

    return "\n".join(lines)


def _hour_to_period_key(hour: int) -> str:
    """Return a translation key for the time-of-day period (0-23)."""
    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 14:
        return "noon"
    elif 14 <= hour < 18:
        return "afternoon"
    elif 18 <= hour < 22:
        return "evening"
    elif 22 <= hour or hour < 2:
        return "midnight"
    else:
        return "dawn"


def _generate_stats_image_sync(
    display_name: str,
    stats: Dict[str, Any],
    avatar_url: Optional[str],
    labels: Dict[str, str],
) -> bytes:
    """Generate a PNG stats image with word cloud.

    Args:
        labels: Pre-resolved localized strings (header, top_channels,
                activity_by_hour, top_emojis_prefix).

    Returns raw PNG bytes.
    """
    import re
    from PIL import Image, ImageDraw, ImageFont

    W, H = 800, 640
    # Catppuccin Mocha palette
    C_BASE     = (30, 30, 46)
    C_SURFACE0 = (49, 50, 68)
    C_SURFACE1 = (69, 71, 90)
    C_TEXT     = (205, 214, 244)
    C_SUBTEXT  = (147, 153, 178)
    C_BLUE     = (137, 180, 250)
    C_GREEN    = (166, 227, 161)
    C_MAUVE    = (203, 166, 247)

    img = Image.new("RGB", (W, H), C_BASE)
    draw = ImageDraw.Draw(img)

    font_path = _find_cjk_font()

    def _font(size: int) -> ImageFont.FreeTypeFont:
        try:
            return ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()
        except Exception:
            return ImageFont.load_default()

    f_title   = _font(26)
    f_section = _font(13)
    f_body    = _font(14)
    f_small   = _font(12)
    f_tiny    = _font(10)

    # Remove supplementary-plane emoji that NotoSansCJK cannot render
    _EMOJI_RE = re.compile(r"[\U0001F000-\U0010FFFF]")

    def _strip(s: str) -> str:
        return _EMOJI_RE.sub("", s).strip()

    # ── Header bar ────────────────────────────────────────────────
    HEADER_H = 68
    draw.rectangle([0, 0, W, HEADER_H], fill=C_SURFACE0)
    draw.rectangle([0, 0, 5, HEADER_H], fill=C_BLUE)   # accent stripe

    draw.text((18, 10), _strip(display_name) or display_name, fill=C_BLUE, font=f_title)
    draw.text((18, 46), _strip(labels.get("header", "")), fill=C_SUBTEXT, font=f_section)

    y = HEADER_H + 14

    # ── Middle: two columns ───────────────────────────────────────
    COL_X     = 390   # right column start
    MID_TOP   = y
    MID_BOT   = y + 145

    # Left column – top channels with inline mini-bars
    top_channels: Dict[str, int] = stats.get("top_channels", {})
    ch_label = _strip(labels.get("top_channels", "Top Channels")).rstrip(":")
    draw.text((18, y), ch_label, fill=C_MAUVE, font=f_section)
    y_ch = y + 20
    if top_channels:
        sorted_ch = sorted(top_channels.items(), key=lambda x: x[1], reverse=True)[:5]
        total_ch  = sum(top_channels.values()) or 1
        max_ch    = sorted_ch[0][1] or 1
        TRACK_W   = 140
        for name, count in sorted_ch:
            pct = count * 100 // total_ch
            bw  = int((count / max_ch) * TRACK_W)
            draw.rectangle([18, y_ch + 5, 18 + TRACK_W, y_ch + 13], fill=C_SURFACE1)
            draw.rectangle([18, y_ch + 5, 18 + bw,      y_ch + 13], fill=C_BLUE)
            label_x = 18 + TRACK_W + 8
            draw.text((label_x, y_ch), f"#{name}  {pct}%", fill=C_TEXT, font=f_small)
            y_ch += 22

    # Right column – 24-hour activity bar chart
    chart_label = _strip(labels.get("activity_by_hour", "Activity")).rstrip(":")
    draw.text((COL_X, MID_TOP), chart_label, fill=C_MAUVE, font=f_section)

    active_hours: Dict[str, int] = stats.get("active_hours", {})
    if active_hours:
        CHART_Y0  = MID_TOP + 20
        AVAIL_W   = W - COL_X - 18
        BAR_W     = max(8, AVAIL_W // 24 - 1)
        BAR_MAX_H = 90
        max_val   = max(active_hours.values()) or 1
        for h in range(24):
            val = active_hours.get(str(h), 0)
            bh  = int((val / max_val) * BAR_MAX_H)
            bx  = COL_X + h * (BAR_W + 1)
            if bh > 0:
                draw.rectangle(
                    [bx, CHART_Y0 + BAR_MAX_H - bh, bx + BAR_W, CHART_Y0 + BAR_MAX_H],
                    fill=C_GREEN,
                )
            if h % 6 == 0:
                draw.text((bx, CHART_Y0 + BAR_MAX_H + 2), str(h), fill=C_SUBTEXT, font=f_tiny)

    y = MID_BOT

    # Horizontal divider
    draw.line([(10, y), (W - 10, y)], fill=C_SURFACE1, width=1)
    y += 10

    # ── Word cloud ────────────────────────────────────────────────
    FOOTER_H = 28
    wc_h     = max(80, H - y - FOOTER_H - 8)
    top_words: Dict[str, int] = stats.get("top_words", {})
    if top_words:
        try:
            from wordcloud import WordCloud

            wc_kwargs: dict = dict(
                width=W - 36,
                height=wc_h,
                background_color=None,
                mode="RGBA",
                colormap="Blues",
                max_words=60,
                min_font_size=11,
                prefer_horizontal=1.0,
            )
            if font_path:
                wc_kwargs["font_path"] = font_path

            wc     = WordCloud(**wc_kwargs).generate_from_frequencies(top_words)
            wc_img = wc.to_image()
            img.paste(wc_img, (18, y), wc_img if wc_img.mode == "RGBA" else None)
        except Exception as e:
            draw.text((18, y + 10), f"(wordcloud: {e})", fill=C_SUBTEXT, font=f_small)

    # ── Footer: top emojis ────────────────────────────────────────
    top_emojis: Dict[str, int] = stats.get("top_emojis", {})
    if top_emojis:
        sorted_e   = sorted(top_emojis.items(), key=lambda x: x[1], reverse=True)[:8]
        emoji_text = "  ".join(f"{e}x{c}" for e, c in sorted_e)
        prefix     = labels.get("top_emojis_prefix", "")
        footer     = f"{prefix}: {emoji_text}" if prefix else emoji_text
        draw.text((18, H - FOOTER_H + 6), _strip(footer), fill=C_SUBTEXT, font=f_small)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
