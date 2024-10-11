import google.generativeai as genai
import os
from addons.settings import TOKENS
from threading import Thread
from queue import Queue

# Initialize the Gemini model
tokens = TOKENS()
genai.configure(api_key=tokens.gemini_api_key)
model = genai.GenerativeModel("gemini-1.5-flash")

class Streamer:
    def __init__(self):
        self.queue = Queue()
        self.is_finished = False

    def write(self, content):
        self.queue.put(content)

    def finish(self):
        self.is_finished = True
        self.queue.put(None)  # End marker

    def __iter__(self):
        return self

    def __next__(self):
        item = self.queue.get()
        if item is None:
            raise StopIteration
        return item

async def generate_response(prompt, system_prompt, dialogue_history=None, image_input=None):
    streamer = Streamer()
    full_prompt = f"{system_prompt}\n{prompt}"

    if dialogue_history:
        history_content = "\n".join([f"{msg['role']}: {msg['content']}" for msg in dialogue_history])
        full_prompt = f"{system_prompt}\n{history_content}\nUser: {prompt}"

    if image_input:
        full_prompt += f"\nImage: {image_input}"

    def run_generation():
        try:
            response_stream = model.generate_content(full_prompt, stream=True)
            for chunk in response_stream:
                streamer.write(chunk)
        except Exception as e:
            streamer.write(f"\nAn error occurred: {str(e)}")
        finally:
            streamer.finish()

    thread = Thread(target=run_generation)
    thread.start()
    return thread, streamer

# Example usage
if __name__ == "__main__":
    import asyncio
    async def main():
        thread, streamer = await generate_response("Write a story about a magic backpack.", "System prompt here")
        for content in streamer:
            print(content, end='', flush=True)
        thread.join()

    asyncio.run(main())
