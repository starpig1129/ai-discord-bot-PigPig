# MIT License

# Copyright (c) 2024 starpig1129

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import logging
from threading import Thread
from transformers import AutoTokenizer, AutoModelForCausalLM, TextIteratorStreamer
import torch
from addons.settings import Settings, TOKENS
from gpt.openai_api import generate_response as openai_generate, OpenAIError
from gpt.gemini_api import generate_response as gemini_generate, GeminiError
from gpt.claude_api import generate_response as claude_generate, ClaudeError

settings = Settings()
tokens = TOKENS()

# 全局變量用於本地模型
global_model = None
global_tokenizer = None

def get_model_and_tokenizer():
    global global_model, global_tokenizer
    return global_model, global_tokenizer

def set_model_and_tokenizer(model, tokenizer):
    global global_model, global_tokenizer
    global_model = model
    global_tokenizer = tokenizer
    return model, tokenizer

async def local_generate(inst, system_prompt, dialogue_history=None, image_input=None):
    global global_model, global_tokenizer
    
    model, tokenizer = get_model_and_tokenizer()
    if model is None or tokenizer is None:
        raise ValueError("本地模型未設置")

    messages = [{'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': inst}]
    if dialogue_history is not None:
        messages = [{'role': 'system', 'content': system_prompt}] + dialogue_history + [{'role': 'user', 'content': inst}]
    
    streamer = TextIteratorStreamer(tokenizer, skip_prompt=True)
    input_ids = tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt").to(model.device)
    attention_mask = (input_ids != tokenizer.pad_token_id).long()

    generation_kwargs = dict(
        inputs=input_ids,
        attention_mask=attention_mask,
        pad_token_id=tokenizer.pad_token_id,
        streamer=streamer,
        max_new_tokens=8192,
        do_sample=True,
        temperature=0.6,
        top_p=0.9,
    )
    
    thread = Thread(target=model.generate, kwargs=generation_kwargs)
    thread.start()
    return thread, streamer

# 定義模型生成函數映射
MODEL_GENERATORS = {
    "openai": openai_generate,
    "gemini": gemini_generate,
    "claude": claude_generate,
    "local": local_generate
}

# 定義模型可用性檢查
def is_model_available(model_name):
    if model_name == "openai":
        return tokens.openai_api_key is not None
    elif model_name == "gemini":
        return tokens.gemini_api_key is not None
    elif model_name == "claude":
        return tokens.anthropic_api_key is not None
    elif model_name == "local":
        model, tokenizer = get_model_and_tokenizer()
        return model is not None and tokenizer is not None
    return False

async def generate_response(inst, system_prompt, dialogue_history=None, image_input=None):
    last_error = None
    # 根據優先順序嘗試使用可用的模型
    for model_name in settings.model_priority:
        if is_model_available(model_name):
            try:
                generator = MODEL_GENERATORS[model_name]
                thread, gen = await generator(inst, system_prompt, dialogue_history, image_input)
                
                # 嘗試獲取第一個響應來檢測錯誤
                try:
                    if isinstance(gen, TextIteratorStreamer):
                        # 對於本地模型的 TextIteratorStreamer
                        first_response = next(iter(gen))
                        def combined_gen():
                            yield first_response
                            yield from gen
                        logging.info(f"成功使用 {model_name} 模型生成回應")
                        return thread, combined_gen()
                    else:
                        # 對於其他 API 的異步生成器
                        async def combined_gen():
                            try:
                                async for item in gen:
                                    yield item
                            except Exception as e:
                                if isinstance(e, (GeminiError, OpenAIError, ClaudeError)):
                                    raise
                                raise ValueError(f"{model_name} 模型生成過程中發生錯誤: {str(e)}")
                        
                        # 創建生成器實例並測試第一個響應
                        gen_instance = combined_gen()
                        try:
                            # 使用 anext() 替代 __anext__() 以提高可讀性
                            first_response = await anext(gen_instance)
                            async def final_gen():
                                yield first_response
                                async for item in gen_instance:
                                    yield item
                            logging.info(f"成功使用 {model_name} 模型生成回應")
                            return thread, final_gen()
                        except StopAsyncIteration:
                            raise ValueError(f"{model_name} 模型沒有生成任何回應")
                except (GeminiError, OpenAIError, ClaudeError) as e:
                    last_error = e
                    logging.error(f"使用 {model_name} 模型時發生錯誤: {str(e)}")
                    logging.info(f"嘗試切換到下一個可用模型")
                    continue
                except Exception as e:
                    last_error = e
                    logging.error(f"使用 {model_name} 模型時發生未知錯誤: {str(e)}")
                    logging.info(f"嘗試切換到下一個可用模型")
                    continue
            except Exception as e:
                last_error = e
                logging.error(f"初始化 {model_name} 模型時發生錯誤: {str(e)}")
                logging.info(f"嘗試切換到下一個可用模型")
                continue
    
    # 如果所有模型都失敗了，拋出最後一個錯誤
    if last_error:
        raise type(last_error)(f"所有模型都失敗了。最後的錯誤: {str(last_error)}")
    else:
        raise ValueError("沒有可用的模型")
