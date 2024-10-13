import google.generativeai as genai
import os
from addons.settings import TOKENS
import asyncio
from asyncio import Queue

# Initialize the Gemini model
tokens = TOKENS()
genai.configure(api_key=tokens.gemini_api_key)
model = genai.GenerativeModel("gemini-1.5-flash")

class Streamer:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.is_finished = False

    async def write(self, content):
        await self.queue.put(content)

    async def finish(self):
        self.is_finished = True
        await self.queue.put(None)  # End marker

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self.queue.get()
        if item is None:
            raise StopAsyncIteration
        return item

async def generate_response(prompt, system_prompt, dialogue_history=None, image_input=None):
    streamer = Streamer()
    full_prompt = f"{system_prompt}\n{prompt}"

    if dialogue_history:
        history_content = "\n".join([f"{msg['role']}: {msg['content']}" for msg in dialogue_history])
        full_prompt = f"{system_prompt}\n{history_content}\nUser: {prompt}"

    if image_input:
        full_prompt += f"\nImage: {image_input}"

    async def run_generation():
        try:
            response_stream = model.generate_content(full_prompt,
                                                    safety_settings = 'BLOCK_NONE',
                                                    stream=True)
            async for chunk in response_stream:
                await streamer.write(chunk.text)
        except Exception as e:
            await streamer.write(f"\nAn error occurred: {str(e)}")
        finally:
            await streamer.finish()

    task = asyncio.create_task(run_generation())
    return task, streamer

# Example usage
if __name__ == "__main__":
    async def main():
        task, streamer = await generate_response("Write a story about a magic backpack.", "System prompt here")
        async for content in streamer:
            print(content, end='', flush=True)
        await task

    asyncio.run(main())
