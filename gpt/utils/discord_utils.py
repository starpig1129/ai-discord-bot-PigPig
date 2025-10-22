# -*- coding: utf-8 -*-
import logging
from typing import Optional, Callable, Awaitable

import discord

from gpt.core.retry_controller import RetryController
from gpt.utils.sanitizer import mask_text

logger = logging.getLogger(__name__)

# 安全策略：限制提及權限以防止濫用
ALLOWED_MENTIONS = discord.AllowedMentions(users=True, roles=False, everyone=False, replied_user=True)

# Deprecated shim: keep backward compatibility for callers still importing safe_edit_message
# Deprecated: use safe_edit instead. This thin wrapper will be kept for at least two releases.
# Behavior: no extra retry/backoff or error swallowing; it simply delegates to safe_edit.
_deprecation_warned = False

async def safe_edit_message(
    message: discord.Message,
    content: str,
    trace_id: Optional[str] = None,
    retry: Optional[RetryController] = None,
) -> discord.Message:
    global _deprecation_warned
    if not _deprecation_warned:
        # INFO level to avoid excessive noise; only log once per process.
        logger.info("safe_edit_message is deprecated; please migrate to safe_edit. This shim will be removed in a future release.")
        _deprecation_warned = True
    # Delegate to the new API without altering semantics
    return await safe_edit(message, content, trace_id=trace_id, retry=retry)

# 可重試錯誤分類：
# - HTTP 429（速率限制）
# - 網路類錯誤（連線重置、逾時等；discord.py 多屬於 HTTPException/request 異常）
# 不可重試：
# - Forbidden（權限不足）
# - NotFound（資源不存在）
RetryableExc = (discord.HTTPException,)
NonRetryableExc = (discord.Forbidden, discord.NotFound)


def _summarize(content: str) -> str:
    if content is None:
        return "None"
    masked = mask_text(content, max_len=120)
    return f"len={len(content)}, sample={masked}"


async def _run_with_retry(
    fn: Callable[[], Awaitable[discord.Message]],
    retry: Optional[RetryController],
    trace_id: Optional[str],
    op: str,
) -> discord.Message:
    async def _exec() -> discord.Message:
        try:
            return await fn()
        except NonRetryableExc:
            # 不可重試，直接拋出
            raise
        except RetryableExc as e:
            # 交由 RetryController 判斷是否可重試；若未提供 retry，直接拋出
            if retry is None:
                raise
            # 包裝成 LLMProviderError 以沿用 RetryController 的判斷邏輯不合適；
            # 這裡改為直接讓 run_async 捕獲原始例外，並由呼叫者提供 on_try/on_retry 打點
            raise e

    if retry is None:
        return await _exec()

    def _on_try(attempt: int) -> None:
        logger.debug(f"[{op}] try#{attempt} trace_id={trace_id}")

    def _on_retry(attempt: int, delay: float, code: str) -> None:
        # 我們沒有標準化的錯誤碼，沿用 code 欄位。呼叫端主要關注打點即可。
        logger.warning(f"[{op}] retry#{attempt} in {delay:.2f}s code={code} trace_id={trace_id}")

    # 使用 RetryController 執行
    return await retry.run_async(_exec, on_try=_on_try, on_retry=_on_retry)


async def safe_send(
    channel: discord.abc.Messageable,
    content: str,
    trace_id: Optional[str] = None,
    retry: Optional[RetryController] = None,
    allowed_mentions: Optional[discord.AllowedMentions] = None,
) -> discord.Message:
    """安全發送訊息：統一處理速率限制與網路錯誤的退避重試。"""
    if content is None or (isinstance(content, str) and content.strip() == ""):
        raise ValueError("safe_send: content 不可為空")

    summary = _summarize(content)
    logger.debug(f"[safe_send] trace_id={trace_id} {summary}")

    async def _call() -> discord.Message:
        if allowed_mentions is not None:
            return await channel.send(content=content, allowed_mentions=allowed_mentions)
        else:
            return await channel.send(content=content)

    try:
        return await _run_with_retry(_call, retry, trace_id, "send")
    except discord.Forbidden:
        logger.error(f"[safe_send] Forbidden trace_id={trace_id} channel={getattr(channel, 'id', None)}")
        raise
    except discord.NotFound:
        logger.error(f"[safe_send] NotFound trace_id={trace_id} channel={getattr(channel, 'id', None)}")
        raise


async def safe_edit(
    message: discord.Message,
    content: str,
    trace_id: Optional[str] = None,
    retry: Optional[RetryController] = None,
    allowed_mentions: Optional[discord.AllowedMentions] = None,
) -> discord.Message:
    """安全編輯訊息：統一處理 429/網路重試，Forbidden/NotFound 視為不可重試並拋出。"""
    if content is None or (isinstance(content, str) and content.strip() == ""):
        raise ValueError("safe_edit: content 不可為空")

    summary = _summarize(content)
    logger.debug(f"[safe_edit] trace_id={trace_id} msg_id={getattr(message, 'id', None)} {summary}")

    async def _call() -> discord.Message:
        if allowed_mentions is not None:
            return await message.edit(content=content, allowed_mentions=allowed_mentions)
        else:
            return await message.edit(content=content)

    try:
        return await _run_with_retry(_call, retry, trace_id, "edit")
    except discord.Forbidden:
        logger.error(f"[safe_edit] Forbidden trace_id={trace_id} msg_id={getattr(message, 'id', None)}")
        raise
    except discord.NotFound:
        logger.error(f"[safe_edit] NotFound trace_id={trace_id} msg_id={getattr(message, 'id', None)}")
        raise


async def safe_create_next_block(
    channel: discord.abc.Messageable,
    content: str,
    reference_message_id: Optional[int] = None,
    trace_id: Optional[str] = None,
    retry: Optional[RetryController] = None,
    allowed_mentions: Optional[discord.AllowedMentions] = None,
) -> discord.Message:
    """建立下一段訊息區塊（rollover），維持統一的退避/錯誤行為。"""
    if content is None or (isinstance(content, str) and content.strip() == ""):
        raise ValueError("safe_create_next_block: content 不可為空")

    summary = _summarize(content)
    logger.info(f"[safe_create_next_block] trace_id={trace_id} ref={reference_message_id} {summary}")

    async def _call() -> discord.Message:
        # 在同一 channel 中建立新訊息；可視需求補上 reference 或 thread 參數
        if allowed_mentions is not None:
            return await channel.send(content=content, allowed_mentions=allowed_mentions)
        else:
            return await channel.send(content=content)

    try:
        return await _run_with_retry(_call, retry, trace_id, "create_next_block")
    except discord.Forbidden:
        logger.error(f"[safe_create_next_block] Forbidden trace_id={trace_id} channel={getattr(channel, 'id', None)}")
        raise
    except discord.NotFound:
        logger.error(f"[safe_create_next_block] NotFound trace_id={trace_id} channel={getattr(channel, 'id', None)}")
        raise