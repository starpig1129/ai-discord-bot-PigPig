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
from PIL import Image

from gpt.core.response_generator import generate_response
from gpt.core.message_sender import (
    gpt_message,
    build_intelligent_context,
    search_relevant_memory,
    format_intelligent_context,
    format_memory_context_structured
)
from gpt.utils.media import process_attachment_data


class ActionHandler:
    """Handles Discord bot actions and tool execution."""

    def __init__(self, bot):
        self.bot = bot
        self.system_prompt = self._load_system_prompt()
        self.tool_func_dict = {
            'internet_search': self.internet_search,
            'directly_answer': gpt_message,
            'calculate': self.calculate_math,
            'gen_img': self.generate_image,
            'schedule_management': self.schedule_management,
            'send_reminder': self.send_reminder,
            'manage_user_data': self.manage_user_data
        }

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

    @staticmethod
    def _load_system_prompt() -> str:
        with open('./choseAct_system_prompt.txt', 'r') as f:
            return f.read()

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
            "content": msg.content,
            "user_id": str(msg.author.id) if msg.author != message.guild.me else str(message.guild.me.id)
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
            logger.info(action_list)
            
            for action in action_list:
                tool_name = action["tool_name"]
                parameters = action["parameters"]
                
                if tool_name in self.tool_func_dict:
                    tool_func = self.tool_func_dict[tool_name]
                    try:
                        if tool_name == "directly_answer":
                            continue
                        elif isinstance(parameters, str):
                            result = await tool_func(message_to_edit, message, 
                                                   parameters)
                        else:
                            result = await tool_func(message_to_edit, message, 
                                                   **parameters)
                        if result is not None and tool_name != "directly_answer":
                            final_results.append(result)
                    except Exception as e:
                        logger.info(f"Error executing {tool_name}: {str(e)}")
                else:
                    logger.info(f"Unknown tool: {tool_name}")
            
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
            thread, gen = await generate_response(
                inst=prompt,
                system_prompt=self.system_prompt,
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

    async def internet_search(self, message_to_edit: Any, message: Any, 
                            query: str, search_type: str) -> Optional[str]:
        internet_search_cog = self.bot.get_cog("InternetSearchCog")
        return (await internet_search_cog.internet_search(
            message, query, search_type, message_to_edit) 
            if internet_search_cog else "Search is disabled")

    async def calculate_math(self, message_to_edit: Any, message: Any, 
                           expression: str) -> Optional[str]:
        math_cog = self.bot.get_cog("MathCalculatorCog")
        return (await math_cog.calculate_math(expression, message_to_edit)
                if math_cog else "Math is disabled")

    async def generate_image(self, message_to_edit: Any, message: Any, 
                           prompt: str) -> Optional[str]:
        """Generate or edit images using Gemini API or local model."""
        image_gen_cog = self.bot.get_cog("ImageGenerationCog")
        if not image_gen_cog:
            return "Image generation is disabled"

        try:
            # 獲取圖片輸入（如果有）
            input_images = []
            if message.attachments:
                for attachment in message.attachments:
                    if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                        async with image_gen_cog.session.get(attachment.url) as response:
                            image_data = await response.read()
                        img = Image.open(io.BytesIO(image_data))
                        input_images.append(img)

            # 獲取對話歷史
            history = image_gen_cog._get_conversation_history(message.channel.id)
            
            # 嘗試使用 Gemini API
            try:
                image_buffer, response_text = await image_gen_cog.generate_with_gemini(prompt, input_images, history)
                
                # 更新對話歷史
                image_gen_cog._update_conversation_history(message.channel.id, "user", prompt, input_images)
                
                content = "使用 Gemini API 的回應："
                if response_text:
                    content += f"\n{response_text}"
                
                if message_to_edit:
                    await message_to_edit.edit(content=content)

                if image_buffer:
                    # 如果有圖片，添加到歷史記錄
                    image_gen_cog._update_conversation_history(
                        message.channel.id,
                        "assistant",
                        response_text if response_text else "已生成圖片",
                        [image_buffer]
                    )
                    return image_buffer
                elif response_text:
                    return response_text

            except Exception as e:
                print(f"Gemini API 錯誤：{str(e)}")
                
            # 如果 Gemini 失敗，嘗試使用本地模型
            if message_to_edit:
                await message_to_edit.edit(content="切換到本地模型...")
            
            image = await image_gen_cog.generate_with_local_model(message.channel, prompt)
            if image:
                return image
                
            return "所有圖片生成方式都失敗了，請稍後再試。"
            
        except Exception as e:
            print(f"圖片生成過程出現錯誤：{str(e)}")
            return "生成圖片時發生錯誤。"

    async def schedule_management(self, message_to_edit: Any, message: Any, 
                                action: str = "query", query_type: str = "next",
                                time: Optional[str] = None, 
                                date: Optional[str] = None,
                                description: Optional[str] = None
                                ) -> Optional[str]:
        schedule_cog = self.bot.get_cog("ScheduleManager")
        if not schedule_cog:
            return "Schedule is disabled"
            
        if action == "query":
            return await schedule_cog.query_schedule(
                message.author.id, query_type, time)
        elif action == "create":
            return await schedule_cog.create_schedule(message.author.id)
        elif action == "update":
            return await schedule_cog.update_schedule(
                message.author.id, date, time, description)
        return "Invalid schedule operation"

    async def send_reminder(self, message_to_edit: Any, message: Any,
                          time_str: str, reminder_message: str) -> Optional[str]:
        reminder_cog = self.bot.get_cog("ReminderCog")
        return (await reminder_cog.set_reminder(
            message.channel, message.author, time_str, reminder_message,
            message_to_edit) if reminder_cog else "Reminder is disabled")

    async def manage_user_data(self, message_to_edit: Any, message: Any,
                             user_id: Optional[int] = None, 
                             user_data: Optional[Dict] = None,
                             action: str = "read") -> Optional[str]:
        user_data_cog = self.bot.get_cog("UserDataCog")
        return (await user_data_cog.manage_user_data_message(
            message, user_id, user_data, action, message_to_edit)
            if user_data_cog else "User data management is disabled")
