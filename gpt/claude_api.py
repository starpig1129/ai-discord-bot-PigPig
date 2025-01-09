from addons.settings import TOKENS
from anthropic import AsyncAnthropic, HUMAN_PROMPT, AI_PROMPT
import asyncio
from threading import Thread
from queue import Queue
class ClaudeError(Exception):
    pass

# Initialize Anthropic client
tokens = TOKENS()
async_anthropic = AsyncAnthropic(api_key=tokens.anthropic_api_key)

async def generate_response(inst, system_prompt, dialogue_history=None, image_input=None):
    messages = []

    if dialogue_history:
        for msg in dialogue_history:
            role = HUMAN_PROMPT if msg["role"] == "user" else AI_PROMPT
            messages.append(f"{role} {msg['content']}")
    
    messages.append(f"{HUMAN_PROMPT}{system_prompt}{inst}")
    if image_input:
        messages.append(f"Image: {image_input}")
    full_prompt = "\n\n".join(messages)

    async def run_generation():
        try:
            async with async_anthropic as client:
                response_stream = await client.completions.create(
                    model="claude-3-5-sonnet-20240620",
                    prompt=full_prompt,
                    max_tokens_to_sample=1000,
                    stream=True
                )

                async for completion in response_stream:
                    if completion.stop_reason:
                        break
                    chunk = completion.completion
                    yield chunk
        except Exception as e:
            error_message = str(e)
            if "invalid_api_key" in error_message.lower():
                raise ClaudeError(f"Claude API 金鑰無效: {error_message}")
            elif "rate_limit" in error_message.lower():
                raise ClaudeError(f"Claude API 請求頻率超限: {error_message}")
            elif "quota_exceeded" in error_message.lower():
                raise ClaudeError(f"Claude API 配額超限: {error_message}")
            elif "model_not_found" in error_message.lower():
                raise ClaudeError(f"Claude API 模型不可用: {error_message}")
            else:
                raise ClaudeError(f"Claude API 錯誤: {error_message}")

    thread = Thread()
    thread.start()
    return thread, run_generation()
