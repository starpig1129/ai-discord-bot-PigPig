# MIT License
# Copyright (c) 2024 starpig1129

"""Simplified message sender module for Discord bot GPT responses.

This module handles message generation with language conversion, 
channel-level system prompts, and basic message reply functionality.
"""

import asyncio
import logging
from typing import Any, List, Optional, Union, Tuple, AsyncIterator, Iterator

import discord
import opencc

from function import func


# Constants
_ALLOWED_MENTIONS = discord.AllowedMentions(
    users=True,
    roles=False,
    everyone=False,
    replied_user=True
)

_BUFFER_SIZE = 20  # Stream buffer size for message updates
_HARD_LIMIT = 2000  # Hard limit for Discord message length
_MAX_RETRIES = 3  # Maximum number of retry attempts


# Logger
_logger = logging.getLogger(__name__)


# Language converters (compiled once)
_CONVERTERS = {
    'zh_TW': opencc.OpenCC('s2twp'),  # Simplified to Traditional Chinese
    'zh_CN': opencc.OpenCC('tw2sp'),  # Traditional to Simplified Chinese
    'en_US': None,  # English doesn't need conversion
    'ja_JP': None,  # Japanese doesn't need conversion
}


def get_converter(lang: str) -> Optional[opencc.OpenCC]:
    """Gets appropriate converter based on language.
    
    Args:
        lang: Language code (e.g., 'zh_TW', 'zh_CN', 'en_US', 'ja_JP').
    
    Returns:
        OpenCC converter instance or None if conversion is not needed.
    """
    return _CONVERTERS.get(lang, _CONVERTERS['zh_TW'])


def _sanitize_response(text: str) -> str:
    """Sanitizes response text to prevent accidental Discord mentions.
    
    Args:
        text: Text content to sanitize.
    
    Returns:
        Sanitized safe text with @everyone and @here replaced.
    """
    if not text:
        return text
    
    # Replace @everyone and @here with safe versions
    sanitized = text.replace('@everyone', '＠everyone')
    sanitized = sanitized.replace('@here', '＠here')
    
    return sanitized


async def safe_edit_message(
    message: discord.Message,
    content: str,
    max_retries: int = _MAX_RETRIES
) -> None:
    """Safely edits a Discord message with retry logic.
    
    Args:
        message: Discord message to edit.
        content: New content for the message.
        max_retries: Maximum number of retry attempts.
        
    Raises:
        discord.errors.HTTPException: If all retry attempts fail.
    """
    for attempt in range(max_retries):
        try:
            sanitized_content = _sanitize_response(content)
            await message.edit(
                content=sanitized_content,
                allowed_mentions=_ALLOWED_MENTIONS
            )
            return
        except discord.errors.NotFound:
            _logger.warning(
                'Message not found during edit attempt %d',
                attempt + 1
            )
            return
        except discord.errors.HTTPException as exc:
            if attempt < max_retries - 1:
                await asyncio.sleep(0.5 * (attempt + 1))
            else:
                raise exc


async def _safe_send_message(
    channel: discord.abc.Messageable,
    content: str,
    files: Optional[List[discord.File]] = None,
    max_retries: int = _MAX_RETRIES
) -> discord.Message:
    """Safely sends a Discord message with retry logic.
    
    Args:
        channel: Discord channel to send message to.
        content: Message content.
        files: Optional list of files to attach.
        max_retries: Maximum number of retry attempts.
    
    Returns:
        Sent Discord message.
        
    Raises:
        discord.errors.HTTPException: If all retry attempts fail.
    """
    for attempt in range(max_retries):
        try:
            sanitized_content = _sanitize_response(content)
            return await channel.send(
                content=sanitized_content,
                files=files,
                allowed_mentions=_ALLOWED_MENTIONS
            )
        except discord.errors.HTTPException as exc:
            if attempt < max_retries - 1:
                await asyncio.sleep(0.5 * (attempt + 1))
            else:
                raise exc


def _get_processing_message(
    message: discord.Message,
    lang_manager,
    message_type: str = 'processing'
) -> str:
    """Gets localized processing message.
    
    Args:
        message: Discord message containing guild information.
        lang_manager: Language manager instance for translations.
        message_type: Type of processing message ('processing' or 'continuation').
        
    Returns:
        Localized processing message string.
    """
    default_messages = {
        'processing': '處理中...',
        'continuation': '繼續輸出中...'
    }
    
    if not (message and message.guild and lang_manager):
        return default_messages.get(message_type, '處理中...')
    
    try:
        return lang_manager.translate(
            str(message.guild.id),
            'system',
            'chat_bot',
            'responses',
            message_type
        )
    except Exception:
        _logger.exception(
            'LanguageManager.translate failed, using default %s message',
            message_type
        )
        return default_messages.get(message_type, '處理中...')


async def _process_token_stream(
    streamer: AsyncIterator,
    converter: Optional[opencc.OpenCC],
    current_message: discord.Message,
    channel: discord.abc.Messageable,
    message: discord.Message,
    lang_manager
) -> Tuple[str, discord.Message]:
    """Processes token stream and updates Discord messages.
    
    Args:
        streamer: Token stream (async or sync iterator).
        converter: OpenCC converter for language conversion.
        current_message: Current Discord message being edited.
        channel: Discord channel for sending messages.
        message: Original Discord message for context.
        lang_manager: Language manager for translations.
        
    Returns:
        Tuple of (full message result, final Discord message).
    """
    responses = ''  # Small buffer for incoming tokens
    responsesall = ''  # Accumulated text for current message block
    message_result = ''  # Full result as returned to caller
    
    async def process_item(token, metadata):
        nonlocal responses, responsesall, message_result, current_message
        
        print(token,end='',flush=True)
        # 提取文字 token
        if hasattr(token, "content") and token.content:
            token_str = str(token.content)
            responses += token_str
            message_result += token_str
            
            # 達到緩衝區大小時更新
            if len(responses) >= _BUFFER_SIZE:
                responsesall += responses
                converted = (converter.convert(responsesall) 
                            if converter else responsesall)
                
                # 處理訊息長度限制
                if len(converted) > _HARD_LIMIT:
                    processing_msg = _get_processing_message(
                        message, lang_manager, 'continuation'
                    )
                    current_message = await _safe_send_message(
                        channel, processing_msg
                    )
                    responsesall = ''
                    converted = ''

                if converted and (len(converted) != 0) <= _HARD_LIMIT:
                    await safe_edit_message(current_message, converted)
                
                responses = ''  # 清空緩衝區
                await asyncio.sleep(0)
    

    async for token, metadata in streamer:
        await process_item(token, metadata)
    
    # Handle remaining buffered tokens
    if responses:
        responsesall += responses
    
    return responsesall,current_message


async def send_message(
    bot: Any,
    message_to_edit: Optional[discord.Message],
    message: discord.Message,
    streamer: AsyncIterator,
) -> str:
    """Consumes a token stream and updates Discord messages with buffering.
    
    This function is compatible with both synchronous and asynchronous iterables
    returned by agent.stream(...). It accumulates tokens in a small buffer and
    periodically edits the current Discord message. When the message grows beyond
    a hard limit, it creates a new continuation message.
    
    Args:
        message_to_edit: Optional existing message to edit. If None, creates new.
        message: Original Discord message for context and channel information.
        streamer: Token stream iterator (async or sync).
        
    Returns:
        Full message result string.
    """
    channel = message.channel
    
    # Get language converter for this server
    converter = None
    lang = 'zh_TW'  # Default language
    lang_manager = None
    
    if message and message.guild:
        lang_manager = bot.get_cog('LanguageManager')
        if lang_manager:
            guild_id = str(message.guild.id)
            lang = lang_manager.get_server_lang(guild_id)
            converter = get_converter(lang)
            _logger.info('Using language: %s for guild: %s', lang, guild_id)
    
    # Ensure there's an initial message to edit
    current_message = message_to_edit
    if current_message is None:
        processing_message = _get_processing_message(
            message,
            lang_manager,
            'processing'
        )
        current_message = await _safe_send_message(channel, processing_message)
    
    try:
        # Process token stream
        responsesall, current_message = await _process_token_stream(
            streamer,
            converter,
            current_message,
            channel,
            message,
            lang_manager
        )

        return responsesall

    except Exception as exc:
        await func.report_error(exc, 'Error generating GPT response')
        _logger.error('Error generating GPT response: %s', exc)
        
        error_message = f'抱歉，生成回應時發生錯誤: {exc}'
        try:
            if message_to_edit:
                try:
                    await safe_edit_message(message_to_edit, error_message)
                except discord.errors.NotFound:
                    await _safe_send_message(channel, error_message)
            else:
                await _safe_send_message(channel, error_message)
        except Exception as send_exc:
            _logger.error('Failed to send error message: %s', send_exc)

        return error_message