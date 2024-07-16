import os
from openai import OpenAI
from dotenv import load_dotenv
import asyncio
from threading import Thread
import tiktoken
from queue import Queue

# 加載 .env 文件中的環境變量
load_dotenv()

# 初始化 OpenAI 客戶端
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 初始化 tokenizer
tokenizer = tiktoken.encoding_for_model("gpt-4o")

def num_tokens_from_messages(messages, model="gpt-4o"):
    """計算消息列表的 token 數量"""
    num_tokens = 0
    for message in messages:
        num_tokens += 4  # 每條消息的開始和結束標記
        for key, value in message.items():
            num_tokens += len(tokenizer.encode(value))
            if key == "name":
                num_tokens += -1  # 名字的 tokens 計算有所不同
    num_tokens += 2  # 對話的開始和結束標記
    return num_tokens

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

async def generate_response_with_fake_thread(inst, system_prompt, streamer, dialogue_history=None):
    messages = [{'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': inst}]
    if dialogue_history is not None:
        messages = [{'role': 'system', 'content': system_prompt}] + dialogue_history + [{'role': 'user', 'content': inst}]

    while num_tokens_from_messages(messages) > 127000:
        if len(messages) <= 2:
            raise ValueError("Message is too long even after trimming history")
        messages.pop(1)

    try:
        stream = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=4096,
            temperature=0.5,
            top_p=0.9,
            stream=True
        )

        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                streamer.write(chunk.choices[0].delta.content)
    except Exception as e:
        streamer.write(f"\nAn error occurred: {str(e)}")
    finally:
        streamer.finish()

async def generate_response(inst, system_prompt, dialogue_history=None):
    streamer = Streamer()
    fake_thread = FakeThread(generate_response_with_fake_thread, inst, system_prompt, streamer, dialogue_history)
    fake_thread.start()
    return fake_thread, streamer

# 使用示例
def main():
    thread, streamer = generate_response("Hello, how are you?", "You are a helpful assistant.")
    
    for content in streamer:
        print(content, end='', flush=True)
    
    thread.join()

if __name__ == "__main__":
    main()