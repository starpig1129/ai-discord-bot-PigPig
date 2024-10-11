from addons.settings import TOKENS
from anthropic import AsyncAnthropic, HUMAN_PROMPT, AI_PROMPT
import asyncio
from threading import Thread
from queue import Queue

# Initialize Anthropic client
tokens = TOKENS()
async_anthropic = AsyncAnthropic(api_key=tokens.anthropic_api_key)

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

async def generate_response(inst, system_prompt, dialogue_history=None, image_input=None):
    streamer = Streamer()
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
                    streamer.write(chunk)
        except Exception as e:
            streamer.write(f"\nAn error occurred: {str(e)}")
        finally:
            streamer.finish()

    thread = Thread(target=lambda: asyncio.run(run_generation()))
    thread.start()
    return thread, streamer

# Example usage
if __name__ == "__main__":
    import asyncio
    async def main():
        thread, streamer = await generate_response("Hello, how are you?", "You are a helpful assistant.")
        for content in streamer:
            print(content, end='', flush=True)
        thread.join()

    asyncio.run(main())
