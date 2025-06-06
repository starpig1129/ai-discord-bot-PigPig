import json
import time
import discord
import re
from discord.ext import commands
from discord import app_commands
from threading import Thread
from google import genai
from transformers import TextIteratorStreamer
from gpt.gpt_response_gen import get_model_and_tokenizer
from addons.settings import TOKENS
from typing import Optional
from .language_manager import LanguageManager

def extract_json_from_response(response:str):
    match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        last_brace_pos = response.rfind('}')
        if last_brace_pos != -1:
            json_str = response[:last_brace_pos+1]
        else:
            json_str = response
    return json_str
            
async def call_local_model(messages):
    model, tokenizer = get_model_and_tokenizer()
    if model is None or tokenizer is None:
        raise ValueError("Model or tokenizer is not set. Please load the model first.")

    # Implement the logic to generate response from your local model
    streamer = TextIteratorStreamer(tokenizer, skip_prompt=True)
    input_ids = tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt").to(model.device)

    attention_mask = (input_ids != tokenizer.pad_token_id).long()

    generation_kwargs = dict(
        inputs=input_ids,
        attention_mask=attention_mask,
        pad_token_id=tokenizer.pad_token_id,
        streamer=streamer,
        max_new_tokens=8192,
        do_sample=True,
        temperature=0.6,
        top_p=0.9,
    )

    thread = Thread(target=model.generate, kwargs=generation_kwargs)
    thread.start()

    generated_text = ''
    for new_text in streamer:
        generated_text += new_text

    return generated_text.replace('<|eot_id|>','')

def call_gemini_model(messages):
    tokens = TOKENS()
    genai.configure(api_key=tokens.gemini_api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    full_prompt = "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])
    streamer = model.generate_content(full_prompt,
                                    safety_settings = 'BLOCK_NONE',
                                    stream=True)
    generated_text = ''
    for new_text in streamer:
        generated_text += new_text.text
    return generated_text

async def generate_response(prompt, system_prompt, user_prompt):

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
        {
            "role": "assistant",
            "content": "Thank you! I will now think step by step following my instructions, starting at the beginning after decomposing the problem."
        }
    ]

    steps = []
    step_count = 1
    total_thinking_time = 0
    current_model = 'advanced' 

    while True:
        start_time = time.time()

        # Prepare the input for the model
        inst = messages[-1]['content']

        if current_model == 'basic':
            # Use your local model
            response = await call_local_model(messages)
            json_str = extract_json_from_response(response)
            print('--'*10)
            print(json_str)
            # Assume the response is in JSON format
            step_data = json.loads(json_str)
        else:
            # Use the Gemini API
            response = call_gemini_model(messages)
            json_str = extract_json_from_response(response)
            print('--'*10)
            print(json_str)
            # Assume the response is in JSON format
            step_data = json.loads(json_str)

        end_time = time.time()
        thinking_time = end_time - start_time
        total_thinking_time += thinking_time

        steps.append(
            (
                f"Step {step_count}: {step_data['title']}",
                step_data['content'],
                thinking_time
            )
        )

        # Append the assistant's response to messages and dialogue_history
        assistant_message = {"role": "assistant", "content": json.dumps(step_data)}
        messages.append(assistant_message)

        # Update current_model based on 'model_selection'
        current_model = step_data.get('model_selection', current_model)

        if step_data.get('next_action') == 'final_answer':
            break

        step_count += 1

        # Yield intermediate steps
        yield steps, None

    # Prepare for final answer
    messages.append({
        "role": "user",
        "content": "Please provide the final answer based on your reasoning above."
    })

    start_time = time.time()

    inst = messages[-1]['content']

    if current_model == 'basic':
        # Use your local model for the final answer
        response = await call_local_model(messages)
        json_str = extract_json_from_response(response)
        print('--'*10)
        print(json_str)
        try:
            final_data = json.loads(json_str)
        except:
            final_data = json_str
    else:
        response = call_gemini_model(messages)
        json_str = extract_json_from_response(response)
        print('--'*10)
        print(json_str)
        
        try:
            final_data = json.loads(json_str)
        except:
            final_data = json_str

    end_time = time.time()
    thinking_time = end_time - start_time
    total_thinking_time += thinking_time

    steps.append(("Final Answer", final_data, thinking_time))

    yield steps, total_thinking_time

class CoTCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lang_manager: Optional[LanguageManager] = None

    async def cog_load(self):
        """當 Cog 載入時初始化語言管理器"""
        self.lang_manager = LanguageManager.get_instance(self.bot)

    def get_system_prompt(self, guild_id: str) -> str:
        """根據伺服器語言設定獲取適當的系統提示"""
        if not self.lang_manager:
            return """You are an expert AI assistant with advanced reasoning capabilities. Your task is to provide detailed, step-by-step explanations of your thought process. For each step:

1. Provide a clear, concise title describing the current reasoning phase.
2. Elaborate on your thought process in the content section.
3. Decide whether to continue reasoning or provide a final answer.
4. Decide whether to use the basic model or the advanced model for the next reasoning step.

Response Format:
Use JSON with keys: 'title', 'content', 'next_action' (values: 'continue' or 'final_answer'), 'model_selection' (values:'advanced')

Key Instructions:
- Employ at least 5 distinct reasoning steps.
- Acknowledge your limitations as an AI and explicitly state what you can and cannot do.
- Actively explore and evaluate alternative answers or approaches.
- Critically assess your own reasoning; identify potential flaws or biases.
- When re-examining, employ a fundamentally different approach or perspective.
- Utilize at least 3 diverse methods to derive or verify your answer.
- Incorporate relevant domain knowledge and best practices in your reasoning.
- Quantify certainty levels for each step and the final conclusion when applicable.
- Consider potential edge cases or exceptions to your reasoning.
- Provide clear justifications for eliminating alternative hypotheses."""
        
        return self.lang_manager.translate(
            guild_id, "system", "cot_ai", "prompts", "system_prompt"
        )

    def get_user_prompt(self, question: str, guild_id: str) -> str:
        """根據伺服器語言設定格式化用戶提示"""
        if not self.lang_manager:
            return f"Please analyze this question using step-by-step reasoning: {question}"
        
        return self.lang_manager.translate(
            guild_id, "system", "cot_ai", "prompts", "user_prompt_template",
            question=question
        )

    def get_error_message(self, error_type: str, guild_id: str, error: str) -> str:
        """根據語言設定獲取錯誤訊息"""
        if not self.lang_manager:
            return f"Error occurred while processing request: {error}"
        
        return self.lang_manager.translate(
            guild_id, "system", "cot_ai", "errors", error_type, error=error
        )

    @app_commands.command(
        name="cot_ai",
        description="Chain of Thought reasoning (may take longer)"
    )
    @app_commands.describe(
        prompt='The prompt to process.'
    )
    async def cot(
        self,
        interaction: discord.Interaction,
        prompt: str
    ):
        """
        This command uses Chain of Thought reasoning to answer a prompt.
        """
        if not self.lang_manager:
            self.lang_manager = LanguageManager.get_instance(self.bot)
        
        guild_id = str(interaction.guild_id)
        MAX_MESSAGE_LENGTH = 1900  # 最大訊息字數限制

        # 獲取翻譯的處理中訊息
        processing_msg = self.lang_manager.translate(
            guild_id, "commands", "cot_ai", "responses", "processing"
        ) if self.lang_manager else "Processing your request..."
        
        await interaction.response.send_message(processing_msg)
        
        try:
            # 獲取適當語言的系統提示和用戶提示
            system_prompt = self.get_system_prompt(guild_id)
            user_prompt = self.get_user_prompt(prompt, guild_id)
            
            async for steps, total_thinking_time in generate_response(prompt, system_prompt, user_prompt):
                response_text = ""
                for title, content, thinking_time in steps:
                    # 獲取翻譯的思考時間格式
                    thinking_time_text = self.lang_manager.translate(
                        guild_id, "commands", "cot_ai", "responses", "thinking_time", time=f"{thinking_time:.2f}s"
                    ) if self.lang_manager else f"思考時間：{thinking_time:.2f}s"
                    
                    response_text += f"**{title}**({thinking_time_text})\n"

                # 如果是最終答案，額外發送訊息
                final_answer_text = self.lang_manager.translate(
                    guild_id, "commands", "cot_ai", "responses", "final_answer"
                ) if self.lang_manager else "**最終答案：**"
                
                if title == final_answer_text or "Final Answer" in title:
                    # 如果文字超過字數限制，進行分段發送
                    if len(content) > MAX_MESSAGE_LENGTH:
                        # 分段發送
                        while len(content) > MAX_MESSAGE_LENGTH:
                            part = content[:MAX_MESSAGE_LENGTH]
                            await interaction.followup.send(part)
                            content = content[MAX_MESSAGE_LENGTH:]

                        # 發送最後剩餘的文字
                        if content:
                            await interaction.followup.send(content)
                    else:
                        await interaction.followup.send(content)
                    
                    response_text = ""  # 重置 response_text，避免重複發送
                else:
                    # 正常情況下，只更新訊息
                    if len(response_text) > MAX_MESSAGE_LENGTH:
                        # 如果 response_text 太長，分段發送
                        chunks = [response_text[i:i+MAX_MESSAGE_LENGTH] for i in range(0, len(response_text), MAX_MESSAGE_LENGTH)]
                        for chunk in chunks:
                            await interaction.edit_original_response(content=chunk)
                    else:
                        # 不超過限制，直接更新
                        await interaction.edit_original_response(content=response_text)

        except json.JSONDecodeError as e:
            error_msg = self.get_error_message("json_decode_error", guild_id, str(e))
            await interaction.edit_original_response(content=error_msg)
        except ValueError as e:
            error_msg = self.get_error_message("model_not_available", guild_id, str(e))
            await interaction.edit_original_response(content=error_msg)
        except Exception as e:
            error_msg = self.get_error_message("general_error", guild_id, str(e))
            await interaction.edit_original_response(content=error_msg)



async def setup(bot):
    await bot.add_cog(CoTCommands(bot))
