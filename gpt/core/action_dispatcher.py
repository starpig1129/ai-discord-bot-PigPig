# MIT License
# Copyright (c) 2024 starpig1129

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import json
import logging
import asyncio
import re
import discord
from datetime import datetime
from typing import Any, Dict, List, Optional

from gpt.core.response_generator import generate_response
from gpt.core.message_sender import (
    gpt_message,
    build_intelligent_context,
    search_relevant_memory,
    format_intelligent_context,
    format_memory_context_structured
)
from gpt.tools.registry import tool_registry
from gpt.tools.tool_context import ToolExecutionContext
from gpt.utils.media import process_attachment_data
from gpt.core.tool_executor import ToolExecutor


class ActionDispatcher:
    """處理 Discord 機器人動作和工具執行。"""

    def __init__(self, bot):
        self.bot = bot
        self.tool_registry = tool_registry
        self.tool_executor = ToolExecutor(bot)
        self._tool_routing_rules = [
            (re.compile(r"(算一下|計算|算|\+)"), [{"tool_name": "math", "parameters": {"expression": None}}]),
            (re.compile(r"(天氣|氣溫|下雨)"), [{"tool_name": "internet_search", "parameters": {"query": None}}]),
            (re.compile(r"(提醒我|設定提醒)"), [{"tool_name": "reminder", "parameters": {"time": None, "thing_to_remind": None}}]),
        ]

    def _rule_based_router(self, prompt: str) -> Optional[List[Dict]]:
        """
        基於規則的輕量級工具路由。
        如果匹配成功，返回工具列表；否則返回 None。
        """
        for pattern, tool_config in self._tool_routing_rules:
            match = pattern.search(prompt)
            if match:
                # 簡單提取參數的邏輯，這裡可以根據需要擴展
                action_list = []
                for tool in tool_config:
                    # 複製一份，避免修改原始設定
                    action = tool.copy()
                    action["parameters"] = action["parameters"].copy()
                    
                    # 嘗試填充參數，如果沒有特定邏輯，就將整個 prompt 作為主要參數
                    if "expression" in action["parameters"]:
                        action["parameters"]["expression"] = prompt
                    elif "query" in action["parameters"]:
                        action["parameters"]["query"] = prompt
                    elif "thing_to_remind" in action["parameters"]:
                         action["parameters"]["thing_to_remind"] = prompt

                    action_list.append(action)
                logging.info(f"規則路由匹配成功: {pattern.pattern} -> {action_list}")
                return action_list
        return None

    async def choose_act(self, prompt: str, message: Any,
                        message_to_edit: Any) -> Any:
        prompt = f"time:[{datetime.now().isoformat(timespec='seconds')}]{prompt}"
        # 初始化變數
        history = []
        image_data = []
        
        # 處理當前訊息的附件
        if message.attachments:
            await message_to_edit.edit(content="我看看...")
            current_image_data = await process_attachment_data(message)
            if isinstance(current_image_data, list):
                image_data.extend(current_image_data)
            else:
                prompt += f"\n{current_image_data}"
        
        # 讀取歷史訊息
        async for msg in message.channel.history(limit=10):
            if msg.id != message.id:
                history.append(msg)
                if msg.attachments:
                    msg_image_data = await process_attachment_data(msg)
                    if isinstance(msg_image_data, list):
                        image_data.extend(msg_image_data)
                    else:
                        prompt += f"\n{msg_image_data}"
        
        history.reverse()
        history = history[:-2]  # 移除當前訊息與第一個使用者訊息(會由其他地方加入)
        history_dict = [{
            "role": "user" if msg.author != message.guild.me else "assistant",
            "content": f"[{msg.author.display_name}<@{msg.author.id}>]: {msg.content}"
        } for msg in history]

        user_id = str(message.author.id)
        # 智慧上下文與記憶搜尋
        intelligent_context_task = asyncio.create_task(
            build_intelligent_context(prompt, history_dict, user_id)
        )
        memory_search_task = asyncio.create_task(
            search_relevant_memory(self.bot, message.channel.id, prompt)
        )

        intelligent_context = await intelligent_context_task
        memory_context = await memory_search_task

        enhanced_history = []
        if memory_context:
            formatted_memory = format_memory_context_structured(memory_context)
            if formatted_memory:
                enhanced_history.append(formatted_memory)

        if intelligent_context:
            formatted_context = format_intelligent_context(intelligent_context)
            if formatted_context:
                enhanced_history.append(formatted_context)
        
        final_dialogue_history = enhanced_history + history_dict
        
        action_list = await self._get_action_list(prompt, final_dialogue_history,
                                               image_data)
        
        async def execute_action(message_to_edit: Any, original_prompt: str,
                                 message: Any):
            logger = self.bot.get_logger_for_guild(message_to_edit.guild.name)
            logger.info(f"準備執行的動作: {action_list}")

            context = ToolExecutionContext(
                bot=self.bot,
                message=message,
                message_to_edit=message_to_edit,
                logger=logger
            )

            # 使用 ToolExecutor 執行工具
            tool_results = await self.tool_executor.execute_tools(action_list, context)
            
            # 將工具執行結果添加到歷史紀錄中
            if tool_results:
                history_dict.extend(tool_results)
            
            # 生成最終回應
            gpt_response = await gpt_message(message_to_edit, message, original_prompt, history_dict, image_data)
            logger.info(f'PigPig 回應: {gpt_response}')
            return gpt_response
        
        return execute_action

    async def _get_action_list(self, prompt: str, history_dict: List[Dict],
                             image_data: List) -> List[Dict]:
        # 1. 嘗試規則路由
        routed_action = self._rule_based_router(prompt)
        if routed_action:
            return routed_action

        # 2. 如果規則路由未命中，則呼叫 LLM
        try:
            tools_string = self.tool_registry.get_tools_string_for_prompt()
            
            instruction_prompt = """
### Instructions for Tool Usage
You are a multi-functional Discord bot assistant capable of analyzing user requests, selecting the most suitable tool(s) from a predefined set,
and providing helpful responses. Below is a list of the available tools and how to use them effectively.
You are an expert at choosing the correct tool for a user's request.
You must respond in a JSON array of objects, where each object represents a tool call.
The JSON must be an array, even if there is only one tool call.
### Example Tool Use Syntax
```json
[
    {
        "tool_name": "tool name",
        "parameters": {
            "parameter_name_1": "value",
            "parameter_name_2": "value"
        }
    },
    {
        "tool_name": "another_tool_name",
        "parameters": {
            "parameter_name_1": "value",
            "parameter_name_2": "value"
        }
    }
]
```
Based on the user's request and the available tools, select the appropriate tool(s)."""

            full_system_prompt = f"{instruction_prompt}\n\n# Available Tools:\n{tools_string}"
            
            thread, gen = await generate_response(
                inst=prompt,
                system_prompt=full_system_prompt,
                dialogue_history=history_dict,
                image_input=image_data
            )
            responses = []
            async for chunk in gen:
                responses.append(chunk)
            
            full_response = ''.join(responses)
            json_string = self._extract_json_from_response(full_response)
            return (json.loads(json_string) if json_string
                   else self._get_default_action_list(prompt))
        except json.JSONDecodeError:
            return self._get_default_action_list(prompt)
        except Exception as e:
            logging.error(f"Action list error: {str(e)}")
            return self._get_default_action_list(prompt)

    @staticmethod
    def _extract_json_from_response(response: str) -> str:
        json_start = response.find("[")
        json_end = response.rfind("]") + 1
        return (response[json_start:json_end] 
                if json_start != -1 and json_end != -1 else "")

    @staticmethod
    def _get_default_action_list(prompt: str) -> List[Dict]:
        return [{"tool_name": "directly_answer", "parameters": {"prompt": prompt}}]
