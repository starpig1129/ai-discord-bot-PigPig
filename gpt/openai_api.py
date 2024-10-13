from addons.settings import TOKENS
from openai import OpenAI
import asyncio
from threading import Thread
from queue import Queue
import tiktoken

# Initialize OpenAI client
tokens = TOKENS()
client = OpenAI(api_key=tokens.openai_api_key)

# Initialize tokenizer
tokenizer = tiktoken.encoding_for_model("gpt-4o-mini")

def num_tokens_from_messages(messages, model="gpt-4o-mini"):
    """Calculate the number of tokens in a list of messages"""
    num_tokens = 0
    for message in messages:
        num_tokens += 4  # Start and end tokens for each message
        for key, value in message.items():
            num_tokens += len(tokenizer.encode(value))
            if key == "name":
                num_tokens += -1  # Token calculation differs for names
    num_tokens += 2  # Start and end tokens for the conversation
    return num_tokens


async def generate_response(inst, system_prompt, dialogue_history=None, image_input=None):

    messages = [{'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': inst}]
    if dialogue_history is not None:
        messages = [{'role': 'system', 'content': system_prompt}] + dialogue_history + [{'role': 'user', 'content': inst}]

    if image_input:
        messages.append({'role': 'user', 'content': f"Image: {image_input}"})

    while num_tokens_from_messages(messages) > 127000:
        if len(messages) <= 2:
            raise ValueError("Message is too long even after trimming history")
        messages.pop(1)

    async def run_generation():
        stream = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=4096,
            temperature=0.5,
            top_p=0.9,
            stream=True
        )

        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content

    thread = Thread()
    thread.start()
    return thread, run_generation()
