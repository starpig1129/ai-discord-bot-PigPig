from addons.settings import TOKENS
from anthropic import AsyncAnthropic, HUMAN_PROMPT, AI_PROMPT
import asyncio
from threading import Thread
from queue import Queue

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

    thread = Thread()
    thread.start()
    return thread, run_generation()
