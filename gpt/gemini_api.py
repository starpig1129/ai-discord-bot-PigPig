import google.generativeai as genai
import os
from addons.settings import TOKENS
from threading import Thread
from queue import Queue

# Initialize the Gemini model
tokens = TOKENS()
genai.configure(api_key=tokens.gemini_api_key)
model = genai.GenerativeModel("gemini-1.5-flash")

class GeminiError(Exception):
    pass

async def generate_response(prompt, system_prompt, dialogue_history=None, image_input=None):
    full_prompt = f"{system_prompt}\n{prompt}"

    if dialogue_history:
        history_content = "\n".join([f"{msg['role']}: {msg['content']}" for msg in dialogue_history])
        full_prompt = f"{system_prompt}\n{history_content}\nUser: {prompt}"

    if image_input:
        full_prompt += f"\nImage: {image_input}"

    def run_generation():
        try:
            response_stream = model.generate_content(full_prompt,
                                                  safety_settings='BLOCK_NONE',
                                                  stream=True)
            for chunk in response_stream:
                yield chunk.text
        except Exception as e:
            error_message = str(e)
            if "RESOURCE_PROJECT_INVALID" in error_message:
                raise GeminiError(f"Gemini API 項目設定錯誤: {error_message}")
            elif "PERMISSION_DENIED" in error_message:
                raise GeminiError(f"Gemini API 權限錯誤: {error_message}")
            elif "QUOTA_EXCEEDED" in error_message:
                raise GeminiError(f"Gemini API 配額超限: {error_message}")
            else:
                raise GeminiError(f"Gemini API 錯誤: {error_message}")

    thread = Thread()
    thread.start()
    return thread, run_generation()
