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
import io
import asyncio
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


class ActionDispatcher:
    """Handles Discord bot actions and tool execution."""

    def __init__(self, bot):
        self.bot = bot
        self.tool_registry = tool_registry

    @staticmethod
    def format_tool_result(tool_name: str, result: Any) -> Dict[str, Any]:
        """格式化工具結果為 Google Gemini API 官方標準格式
        
        根據 Google Gemini API 官方文檔，工具調用結果應使用 function 角色格式：
        - role: "function" (官方工具角色)
        - name: 工具名稱
        - content: 工具回應內容
        
        Args:
            tool_name: 工具名稱
            result: 工具執行結果
            
        Returns:
            Dict[str, Any]: 符合官方標準的工具結果格式
        """
        try:
            # 處理不同類型的工具結果
            if isinstance(result, (dict, list)):
                # 結構化資料轉為 JSON 字串
                content = json.dumps(result, ensure_ascii=False, indent=2)
            elif isinstance(result, io.BytesIO):
                # 圖片生成結果
                content = f"已生成圖片 (工具: {tool_name})"
            elif result is None:
                content = f"工具 {tool_name} 執行完成，無返回值"
            else:
                content = str(result)
            
            return {
                "role": "function",  # 官方工具角色標準
                "name": tool_name,   # 工具名稱
                "content": content   # 工具回應內容
            }
        except Exception as e:
            logging.error(f"格式化工具結果失敗 (工具: {tool_name}): {e}")
            return {
                "role": "function",
                "name": tool_name,
                "content": f"工具執行時發生錯誤: {str(e)}"
            }

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
        
        async def execute_action(message_to_edit: Any, dialogue_history: Dict,
                                 channel_id: int, original_prompt: str,
                                 message: Any):
            if channel_id not in dialogue_history:
                dialogue_history[channel_id] = []

            logger = self.bot.get_logger_for_guild(message_to_edit.guild.name)
            final_results = []
            logger.info(f"Executing actions: {action_list}")

            context = ToolExecutionContext(
                bot=self.bot,
                message=message,
                message_to_edit=message_to_edit,
                logger=logger
            )

            for action in action_list:
                tool_name = action.get("tool_name")
                parameters = action.get("parameters", {})

                if not tool_name or tool_name == "directly_answer":
                    continue

                try:
                    tool = self.tool_registry.get_tool(tool_name)
                    result = await tool.execute(context, **parameters)
                    if result is not None:
                        final_results.append(result)
                except KeyError:
                    logger.warning(f"Unknown tool requested: {tool_name}")
                except Exception as e:
                    logger.error(f"Error executing tool '{tool_name}': {e}", exc_info=True)
            
            # 處理結果
            for result, action in zip(final_results, action_list):
                tool_name = action["tool_name"]
                
                # 處理圖片生成的結果
                if tool_name == "gen_img" and isinstance(result, io.BytesIO):
                    # 確保緩衝區位於開始位置
                    result.seek(0)
                    # 創建 Discord File 對象並傳送
                    file = discord.File(result, filename="generated_image.png")
                    await message.channel.send(content=f"生成的圖片：", file=file)
                    # 使用官方標準格式化工具結果
                    formatted_result = self.format_tool_result(tool_name, result)
                    history_dict.append(formatted_result)
                else:
                    # 使用官方標準格式化所有其他工具結果
                    formatted_result = self.format_tool_result(tool_name, result)
                    history_dict.append(formatted_result)
            
            # 生成 GPT 回應
            gptresponses = await gpt_message(message_to_edit, message, original_prompt, history_dict, image_data)
            dialogue_history[channel_id].append({"role": "assistant", "content": gptresponses})
            logger.info(f'PigPig:{gptresponses}')
        
        return execute_action

    async def _get_action_list(self, prompt: str, history_dict: List[Dict],
                             image_data: List) -> List[Dict]:
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
