import os
import openai
from dotenv import load_dotenv
import asyncio
from threading import Thread

# 加载 .env 文件中的环境变量
load_dotenv()

# 设置 OpenAI API 密钥
openai.api_key = os.getenv("OPENAI_API_KEY")

class FakeThread:
    def __init__(self, target, *args, **kwargs):
        self._target = target
        self._args = args
        self._kwargs = kwargs
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def start(self):
        self.loop.run_until_complete(self._target(*self._args, **self._kwargs))

class Streamer:
    def __init__(self, tokenizer=None, skip_prompt=True):
        self.contents = []
        self.tokenizer = tokenizer
        self.skip_prompt = skip_prompt

    def write(self, content):
        self.contents.append(content)
        print(content, end='', flush=True)

async def generate_response_with_fake_thread(inst, system_prompt, streamer, dialogue_history=None):
    # 构建对话历史
    messages = [{'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': inst}]
    if dialogue_history is not None:
        messages = [{'role': 'system', 'content': system_prompt}] + dialogue_history + [{'role': 'user', 'content': inst}]

    # 调用 OpenAI API 生成回应
    response = openai.ChatCompletion.create(
        model="gpt-4",  # 使用你希望的模型名称
        messages=messages,
        max_tokens=8192,
        temperature=0.5,
        top_p=0.9,
        stream=True  # 启用流式输出
    )

    # 使用异步生成器逐步输出内容
    for chunk in response:
        if 'choices' in chunk and len(chunk['choices']) > 0:
            content = chunk['choices'][0]['delta'].get('content', '')
            streamer.write(content)

# 包装原本的generate_response函数
async def generate_response(inst, system_prompt, dialogue_history=None):
    streamer = Streamer()
    fake_thread = FakeThread(generate_response_with_fake_thread, inst, system_prompt, streamer, dialogue_history)
    fake_thread.start()
    return fake_thread, streamer