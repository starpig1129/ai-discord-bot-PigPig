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
from gpt.gpt_response_gen import generate_response
from gpt.sendmessage import gpt_message
from datetime import datetime
import os
import logging

class ActionHandler:
    def __init__(self, bot):
        self.bot = bot
        self.system_prompt = self.load_system_prompt()
        self.tool_func_dict = {
            "internet_search": self.internet_search,
            "directly_answer": gpt_message,
            "calculate": self.calculate_math,
            "gen_img": self.generate_image,
            "schedule_management": self.schedule_management,
            "send_reminder": self.send_reminder,
            "manage_user_data": self.manage_user_data
        }

    @staticmethod
    def load_system_prompt():
        with open('./choseAct_system_prompt.txt', 'r') as f:
            return f.read()

    async def choose_act(self, prompt, message, message_to_edit):
        prompt = f"time:[{datetime.now().isoformat(timespec='seconds')}]{prompt}"
        
        # 處理圖片附件
        if message.attachments:
            for attachment in message.attachments:
                if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                    prompt += f"\nImage URL: {attachment.url}"
        
        action_list = await self.get_action_list(prompt)
        
        async def execute_action(message_to_edit, dialogue_history, channel_id, original_prompt,message):
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
                        elif type(parameters) == str:
                            result = await tool_func(message_to_edit, message, parameters)
                        else:
                            result = await tool_func(message_to_edit, message, **parameters)
                        if result is not None and tool_name != "directly_answer":
                            final_results.append(result)
                    except Exception as e:
                        logger.info(f"執行 {tool_name} 時發生錯誤: {str(e)}")
                else:
                    logger.info(f"未知的工具函數: {tool_name}")
            
            integrated_results = "\n".join(final_results)
            final_prompt = f'<<information:\n{integrated_results}>>\n{original_prompt}'
            gptresponses = await gpt_message(message_to_edit, message, final_prompt)
            dialogue_history[channel_id].append({"role": "assistant", "content": gptresponses})
            logger.info(f'PigPig:{gptresponses}')
        
        return execute_action

    async def get_action_list(self, prompt: str):
        try:
            thread, gen = await generate_response(prompt, self.system_prompt)
            responses = []
            async for chunk in gen:
                responses.append(chunk)
            
            full_response = ''.join(responses)
            json_string = self.extract_json_from_response(full_response)
            return json.loads(json_string) if json_string else self.get_default_action_list(prompt)
        except json.JSONDecodeError:
            return self.get_default_action_list(prompt)
        except Exception as e:
            logging.error(f"獲取動作列表時發生錯誤: {str(e)}")
            return self.get_default_action_list(prompt)

    @staticmethod
    def extract_json_from_response(response: str) -> str:
        json_start = response.find("[")
        json_end = response.rfind("]") + 1
        return response[json_start:json_end] if json_start != -1 and json_end != -1 else ""

    @staticmethod
    def get_default_action_list(prompt: str):
        return [{"tool_name": "directly_answer", "parameters": {"prompt": prompt}}]

    # Tool functions
    async def internet_search(self, message_to_edit, message, query, search_type):
        
        internet_search_cog = self.bot.get_cog("InternetSearchCog")
        return await internet_search_cog.internet_search(message, query, search_type,message_to_edit) if internet_search_cog else "搜索功能未啟用"

    async def calculate_math(self, message_to_edit, message, expression):
        
        math_cog = self.bot.get_cog("MathCalculatorCog")
        return await math_cog.calculate_math(expression,message_to_edit) if math_cog else "數學計算功能未啟用"

    async def generate_image(self, message_to_edit, message, prompt, n_steps=10):
        image_gen_cog = self.bot.get_cog("ImageGenerationCog")
        return await image_gen_cog.generate_image(message.channel, prompt, n_steps,message_to_edit) if image_gen_cog else "圖片生成功能未啟用"

    async def schedule_management(self, message_to_edit, message, action: str = "query", query_type="next", time=None, date=None, description=None):
        schedule_cog = self.bot.get_cog("ScheduleManager")
        if action == "query":
            return await schedule_cog.query_schedule(message.author.id, query_type, time) if schedule_cog else "課表查詢功能未啟用"
        elif action == "create":
            return await schedule_cog.create_schedule(message.author.id) if schedule_cog else "課表創建功能未啟用"
        elif action == "update":
            return await schedule_cog.update_schedule(message.author.id, date, time, description) if schedule_cog else "課表更新功能未啟用"
        else:
            return "無效的行程表操作。"

    async def send_reminder(self, message_to_edit, message, time_str, reminder_message):
        reminder_cog = self.bot.get_cog("ReminderCog")
        return await reminder_cog.set_reminder(message.channel, message.author, time_str, reminder_message,message_to_edit) if reminder_cog else "提醒功能未啟用"

    async def manage_user_data(self, message_to_edit, message, user_id=None, user_data=None, action="read"):
        user_data_cog = self.bot.get_cog("UserDataCog")
        return await user_data_cog.manage_user_data_message(message, user_id, user_data, action,message_to_edit) if user_data_cog else "用戶數據管理功能未啟用"
