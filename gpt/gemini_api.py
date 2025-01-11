import google.generativeai as genai
import os
import asyncio
from addons.settings import TOKENS
from threading import Thread

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

    try:
        response_stream = model.generate_content(full_prompt,
                                              safety_settings='BLOCK_NONE',
                                              stream=True)
        
        async def async_generator():
            try:
                # 使用事件循環來處理同步迭代器
                loop = asyncio.get_event_loop()
                iterator = iter(response_stream)
                while True:
                    try:
                        # 使用 lambda 來安全地獲取下一個值
                        chunk = await loop.run_in_executor(None, lambda: next(iterator, None))
                        if chunk is None:  # 迭代結束
                            break
                        if chunk and chunk.text:
                            yield chunk.text
                            await asyncio.sleep(0)
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
            except Exception as e:
                if isinstance(e, GeminiError):
                    raise
                raise GeminiError(f"Gemini API 生成過程錯誤: {str(e)}")

        # 不需要創建空的線程，因為已經使用異步生成器
        return None, async_generator()
    except Exception as e:
        raise GeminiError(f"Gemini API 初始化錯誤: {str(e)}")
