import os
from anthropic import AsyncAnthropic, HUMAN_PROMPT, AI_PROMPT
from dotenv import load_dotenv
import asyncio
from threading import Thread
from queue import Queue

# 加載 .env 文件中的環境變量
load_dotenv()

# 初始化 Anthropic 客戶端
async_anthropic = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

class FakeThread:
    def __init__(self, target, *args, **kwargs):
        self._target = target
        self._args = args
        self._kwargs = kwargs
        self.thread = Thread(target=self._run)
        self.is_finished = False

    def _run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._target(*self._args, **self._kwargs))
        self.is_finished = True

    def start(self):
        self.thread.start()

    def join(self):
        self.thread.join()

class Streamer:
    def __init__(self):
        self.queue = Queue()
        self.is_finished = False

    def write(self, content):
        self.queue.put(content)

    def finish(self):
        self.is_finished = True
        self.queue.put(None)  # 结束标记

    def __iter__(self):
        return self

    def __next__(self):
        item = self.queue.get()
        if item is None:
            raise StopIteration
        return item

async def generate_claude_response_with_fake_thread(inst, system_prompt, streamer, dialogue_history=None):
    messages = []
    if dialogue_history:
        for msg in dialogue_history:
            role = HUMAN_PROMPT if msg["role"] == "user" else AI_PROMPT
            messages.append(f"{role} {msg['content']}")
    
    messages.append(f"{HUMAN_PROMPT}{system_prompt}{inst}")
    full_prompt = "\n\n".join(messages)

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

async def generate_claude_response(inst, system_prompt, dialogue_history=None):
    streamer = Streamer()
    fake_thread = FakeThread(generate_claude_response_with_fake_thread, inst, system_prompt, streamer, dialogue_history)
    fake_thread.start()
    return fake_thread, streamer

# 使用示例
def main():
    thread, streamer = asyncio.run(generate_claude_response("Hello, how are you?", "You are a helpful assistant."))
    
    for content in streamer:
        print(content, end='', flush=True)
    
    thread.join()

if __name__ == "__main__":
    main()