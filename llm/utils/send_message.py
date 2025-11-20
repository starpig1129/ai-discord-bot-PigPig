# MIT License
# Copyright (c) 2024 starpig1129

"""Simplified message sender module for Discord bot GPT responses.

This module handles message generation with language conversion, 
channel-level system prompts, and basic message reply functionality.
"""

import asyncio
from addons.logging import get_logger
import time
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

_UPDATE_INTERVAL = 0.5  # Update message rate limit
_HARD_LIMIT = 2000  # Hard limit for Discord message length
_MAX_RETRIES = 3  # Maximum number of retry attempts


# Logger
_logger = get_logger(server_id="Bot", source="llm.send_message")


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
) -> bool:
    """Safely edits a Discord message with retry logic.
    
    Args:
        message: Discord message to edit.
        content: New content for the message.
        max_retries: Maximum number of retry attempts.
        
    Returns:
        True if message was successfully edited, False if content was empty or other issues.
        
    Raises:
        discord.errors.HTTPException: If all retry attempts fail.
    """
    # Ensure content is not empty after sanitization
    sanitized_content = _sanitize_response(content)
    if not sanitized_content or not sanitized_content.strip():
        _logger.warning('Attempted to edit message with empty content')
        return False
        
    for attempt in range(max_retries):
        try:
            await message.edit(
                content=sanitized_content,
                allowed_mentions=_ALLOWED_MENTIONS
            )
            return True
        except discord.errors.NotFound:
            _logger.warning(
                f'Message not found during edit attempt {attempt + 1}'
            )
            return False
        except discord.errors.HTTPException as exc:
            if attempt < max_retries - 1:
                await asyncio.sleep(0.5 * (attempt + 1))
            else:
                raise exc
    
    # This should never be reached, but for type safety
    return False


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
        ValueError: If content is empty after sanitization.
    """
    # Ensure content is not empty after sanitization
    sanitized_content = _sanitize_response(content)
    if not sanitized_content or not sanitized_content.strip():
        _logger.warning('Attempted to send message with empty content')
        raise ValueError('Cannot send empty message content')
    
    # Convert files list to sequence for Discord API
    files_sequence = files if files is not None else []
    
    for attempt in range(max_retries):
        try:
            return await channel.send(
                content=sanitized_content,
                files=files_sequence,
                allowed_mentions=_ALLOWED_MENTIONS
            )
        except discord.errors.HTTPException as exc:
            if attempt < max_retries - 1:
                await asyncio.sleep(0.5 * (attempt + 1))
            else:
                raise exc
    
    # This should never be reached, but for type safety
    raise RuntimeError('Failed to send message after all retry attempts')


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
        _logger.error(
            f'LanguageManager.translate failed, using default {message_type} message'
        )
        return default_messages.get(message_type, '處理中...')


async def _process_token_stream(
    streamer: AsyncIterator,
    converter: Optional[opencc.OpenCC],
    current_message: discord.Message,
    channel: discord.abc.Messageable,
    message: discord.Message,
    lang_manager,
    update_interval: float = _UPDATE_INTERVAL,
    tools: Optional[List[Any]] = None
) -> Tuple[str, discord.Message]:
    """Processes token stream and updates Discord messages based on time interval.
    
    Args:
        streamer: Token stream (async or sync iterator).
        converter: OpenCC converter for language conversion.
        current_message: Current Discord message being edited.
        channel: Discord channel for sending messages.
        message: Original Discord message for context.
        lang_manager: Language manager for translations.
        update_interval: Time interval (seconds) between message updates.
        
    Returns:
        Tuple of (full message result with markers, final Discord message).
    """
    message_result = ''  # Full accumulated result (including ALL tokens and markers)
    display_content = ''  # Filtered content for Discord (only between markers)
    current_block = ''  # Current message block content for Discord
    last_update_time = 0  # Initialize to 0 to allow immediate first update
    pending_content = ''  # Content waiting to be sent to Discord
    is_capturing = False  # Flag to track if we're between <som> and <eom>
    
    # Tool execution tracking
    tool_call_chunks = []
    
    async def _execute_tool_calls(chunks: List[Any]):
        """Reconstructs and executes tool calls from chunks."""
        if not chunks or not tools:
            return
            
        # Simple reconstruction of tool calls from chunks
        # This depends on the structure of AIMessageChunk
        # We assume standard LangChain chunk structure
        
        # Group chunks by index to handle multiple tool calls
        tool_calls_by_index = {}
        
        for chunk in chunks:
            if hasattr(chunk, "index"):
                idx = chunk.index
                if idx not in tool_calls_by_index:
                    tool_calls_by_index[idx] = {"name": "", "args": ""}
                
                if hasattr(chunk, "name") and chunk.name:
                    tool_calls_by_index[idx]["name"] += chunk.name
                if hasattr(chunk, "args") and chunk.args:
                    tool_calls_by_index[idx]["args"] += chunk.args
        
        for idx, call_data in tool_calls_by_index.items():
            name = call_data["name"]
            args_str = call_data["args"]
            
            # Find matching tool
            tool = next((t for t in tools if t.name == name), None)
            if tool:
                try:
                    # Update status to "Executing tool..."
                    if current_message:
                        tool_msg = lang_manager.translate(
                            str(message.guild.id) if message.guild else "0",
                            "system", "chat_bot", "responses", "tool_executing",
                            tool_name=name
                        ) if lang_manager else f"🛠️ 正在執行工具: {name}..."
                        
                        await safe_edit_message(current_message, tool_msg)

                    # Parse args if needed, but most tools accept string or dict
                    # If args_str is JSON, we might need to parse it, but LangChain tools often handle it
                    # For simplicity, we try to parse as JSON if it looks like it
                    import json
                    try:
                        args = json.loads(args_str)
                    except:
                        args = args_str
                        
                    _logger.info(f"Executing tool {name} with args: {args}")
                    # Execute tool - fire and forget
                    if asyncio.iscoroutinefunction(tool.invoke) or asyncio.iscoroutinefunction(tool._run):
                         await tool.invoke(args)
                    else:
                         # Run sync tool in thread if needed, but invoke handles it usually
                         await tool.invoke(args)
                except Exception as e:
                    _logger.error(f"Failed to execute tool {name}: {e}")
            else:
                _logger.warning(f"Tool {name} not found in provided tools list")
    
    async def should_update() -> bool:
        """Check if enough time has passed since last update."""
        return time.time() - last_update_time >= update_interval
    
    async def update_message():
        """Update Discord message with current content."""
        nonlocal last_update_time, pending_content, current_block, current_message
        
        if not pending_content:
            return
        
        current_block += pending_content
        converted = (converter.convert(current_block)
                    if converter else current_block)
        
        # Ensure converted content is not empty after sanitization
        if not converted or not converted.strip():
            _logger.warning('Update message skipped - converted content is empty')
            pending_content = ''
            return
        
        # Check if message exceeds Discord limit
        if len(converted) > _HARD_LIMIT:
            # Send continuation message
            processing_msg = _get_processing_message(
                message, lang_manager, 'continuation'
            )
            try:
                current_message = await _safe_send_message(
                    channel, processing_msg
                )
                current_block = pending_content  # Start new block with pending content
                converted = (converter.convert(current_block)
                            if converter else current_block)
                # Re-check converted content after language conversion
                if not converted or not converted.strip():
                    _logger.warning('Continuation message skipped - converted content is empty')
                    pending_content = ''
                    return
            except Exception as e:
                _logger.error(f'Failed to send continuation message: {e}')
                pending_content = ''
                return
        
        # Update the message only if we have valid content
        if converted and converted.strip():
            success = await safe_edit_message(current_message, converted)
            if not success:
                _logger.warning('Failed to edit message with current content')
        
        pending_content = ''
        last_update_time = time.time()
    
    # Buffer for handling split tags
    tag_buffer = ''
    
    def extract_display_content(token_str: str) -> str:
        """Extract content that should be displayed on Discord.
        
        Args:
            token_str: Current token string.
            
        Returns:
            Content to display (empty if outside markers or contains only markers).
        """
        nonlocal is_capturing, tag_buffer
        
        # Prepend any buffered content
        current_str = tag_buffer + token_str
        tag_buffer = ''
        
        display_str = ''
        i = 0
        while i < len(current_str):
            # Check for potential start of a tag
            if current_str[i] == '<':
                # Check if it's a complete tag
                if current_str[i:].startswith('<som>'):
                    is_capturing = True
                    i += 5
                    continue
                elif current_str[i:].startswith('<eom>'):
                    is_capturing = False
                    i += 5
                    continue
                
                # Check if it could be a partial tag
                remaining = current_str[i:]
                if '<som>'.startswith(remaining) or '<eom>'.startswith(remaining):
                    # It's a partial tag, buffer it and stop processing this chunk
                    tag_buffer = remaining
                    break
            
            # If we are capturing, append the character
            if is_capturing:
                display_str += current_str[i]
            i += 1
            
        return display_str

    try:
        async for token, metadata in streamer:
            # Extract text token
            if hasattr(token, "content") and token.content:
                token_str = str(token.content)
                
                # Always accumulate to message_result (complete output)
                message_result += token_str
                
                # Extract display content (filtered for Discord)
                display_str = extract_display_content(token_str)
                
                if display_str:
                    display_content += display_str
                    pending_content += display_str
                    
                    # Update message if enough time has passed
                    if await should_update():
                        await update_message()
                
                # Check if we have finished capturing (eom encountered)
                # We can check is_capturing flag, but we need to be careful about
                # the state transition. If we were capturing and now we are not,
                # and the buffer is empty (meaning we fully processed <eom>), then we are done.
                if not is_capturing and not tag_buffer and '<eom>' in message_result:
                     pass # We don't break immediately to allow tool calls to be processed if they come after
            
            # Capture tool call chunks
            if hasattr(token, "tool_call_chunks") and token.tool_call_chunks:
                tool_call_chunks.extend(token.tool_call_chunks)
        
        # Execute any captured tool calls
        if tool_call_chunks:
            await _execute_tool_calls(tool_call_chunks)
        
        # Send any remaining content
        if pending_content:
            await update_message()
            
        # Fallback: If no content was displayed but we have raw result,
        # it means the model likely forgot the <som> tags.
        if not display_content and message_result and message_result.strip():
            _logger.warning("Model output content without <som> tags. Applying fallback.")
            pending_content = message_result
            await update_message()
            
        # Check if we have any content after all processing
        # Allow either text content OR tool calls (or both)
        has_text_content = message_result and message_result.strip()
        has_tool_calls = len(tool_call_chunks) > 0
        
        if not has_text_content and not has_tool_calls:
            raise ValueError("Generated response is empty and no tools were called")
        
        # If we only have tool calls but no text content, delete the "processing" message
        if has_tool_calls and not has_text_content:
            try:
                if current_message:
                    await current_message.delete()
                    _logger.info("Deleted processing message after tool-only response")
            except Exception as e:
                _logger.warning(f"Failed to delete processing message: {e}")
        
        return message_result, current_message
    
    except Exception as exc:
        _logger.error(f'Error in token stream processing: {exc}')
        # Try to send any accumulated content before raising
        if pending_content:
            try:
                await update_message()
            except Exception as update_exc:
                _logger.error(f'Failed to send final update: {update_exc}')
        raise



async def send_message(
    bot: Any,
    message_to_edit: Optional[discord.Message],
    message: discord.Message,
    streamer: AsyncIterator,
    update_interval: float = _UPDATE_INTERVAL,
    raise_exception: bool = False,
    tools: Optional[List[Any]] = None
) -> str:
    """Consumes a token stream and updates Discord messages with time-based updates.
    
    This function processes tokens from the stream and updates Discord messages
    at regular intervals to avoid rate limiting. When the message grows beyond
    the Discord character limit, it creates a new continuation message.
    
    Args:
        bot: Discord bot instance.
        message_to_edit: Optional existing message to edit. If None, creates new.
        message: Original Discord message for context and channel information.
        streamer: Token stream iterator (async or sync).
        update_interval: Time interval (seconds) between message updates.
        raise_exception: If True, raise exception on failure instead of sending error message.
        
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
            _logger.info(f'Using language: {lang} for guild: {guild_id}')
    
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
        # Process token stream with time-based updates
        message_result, current_message = await _process_token_stream(
            streamer,
            converter,
            current_message,
            channel,
            message,
            lang_manager,
            update_interval,
            tools
        )

        return message_result

    except Exception as exc:
        if raise_exception:
            raise exc
            
        await func.report_error(exc, 'Error generating GPT response')
        _logger.error(f'Error generating GPT response: {exc}')
        
        error_message = '不知道該怎麼回覆你了...'  # Default error message
        
        try:
            if message_to_edit:
                try:
                    success = await safe_edit_message(message_to_edit, error_message)
                    if not success:
                        await _safe_send_message(channel, error_message)
                except discord.errors.NotFound:
                    await _safe_send_message(channel, error_message)
            else:
                await _safe_send_message(channel, error_message)
        except Exception as send_exc:
            _logger.error(f'Failed to send error message: {send_exc}')

        return error_message
