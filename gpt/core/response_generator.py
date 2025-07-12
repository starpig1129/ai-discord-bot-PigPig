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
import asyncio
import math
import numpy as np
from threading import Thread
from transformers import AutoTokenizer, AutoModel, TextIteratorStreamer
import torch
from PIL import Image
from moviepy.editor import VideoFileClip
import tempfile
import librosa
import soundfile as sf
from typing import Type, Optional
from pydantic import BaseModel
from addons.settings import Settings, TOKENS
from gpt.llms.openai import generate_response as openai_generate, OpenAIError
from gpt.llms.gemini import generate_response as gemini_generate, GeminiError
from gpt.llms.claude import generate_response as claude_generate, ClaudeError

settings = Settings()
tokens = TOKENS()

# 全局變量用於本地模型
global_model = None
global_tokenizer = None

def get_model_and_tokenizer():
    global global_model, global_tokenizer
    return global_model, global_tokenizer

def get_video_chunk_content(video_path, flatten=True):
    """處理視頻內容，將其分割為幀和音頻片段。

    Args:
        video_path: 視頻文件路徑。
        flatten: 是否將內容展平為單一列表。

    Returns:
        包含視頻幀和音頻片段的列表。
    """
    video = VideoFileClip(video_path)
    logging.info(f'視頻時長: {video.duration}秒')
    
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as temp_audio_file:
        temp_audio_file_path = temp_audio_file.name
        video.audio.write_audiofile(temp_audio_file_path, codec="pcm_s16le", fps=16000)
        audio_np, sr = librosa.load(temp_audio_file_path, sr=16000, mono=True)
    
    num_units = math.ceil(video.duration)
    contents = []
    
    for i in range(num_units):
        frame = video.get_frame(i+1)
        image = Image.fromarray((frame).astype(np.uint8))
        audio = audio_np[sr*i:sr*(i+1)]
        if flatten:
            contents.extend(["<unit>", image, audio])
        else:
            contents.append(["<unit>", image, audio])
    
    return contents

def set_model_and_tokenizer(model=None, tokenizer=None, model_path=None):
    """初始化或設置全局模型和分詞器。

    Args:
        model: 預訓練模型實例。
        tokenizer: 分詞器實例。
        model_path: 模型路徑。

    Returns:
        tuple: (model, tokenizer) 元組。

    Raises:
        ValueError: 初始化失敗時拋出。
    """
    global global_model, global_tokenizer
    
    if model is not None and tokenizer is not None:
        global_model = model
        global_tokenizer = tokenizer
        return model, tokenizer
        
    if model_path is None:
        model_path = 'openbmb/MiniCPM-o-2_6'
        
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        model = AutoModel.from_pretrained(
            model_path,
            trust_remote_code=True,
            attn_implementation='sdpa',
            torch_dtype=torch.bfloat16
        ).eval().cuda()
        
        # 初始化 TTS 和其他模組
        model.init_tts()
        model.tts.float()  # 避免某些 PyTorch 版本的兼容性問題
        
        global_model = model
        global_tokenizer = tokenizer
        return model, tokenizer
    except Exception as e:
        raise ValueError(f"初始化 MiniCPM-o 模型時發生錯誤: {str(e)}")

class LocalModelError(Exception):
    pass

async def local_generate(inst, system_prompt, dialogue_history=None, image_input=None, audio_input=None, video_input=None):
    """使用本地模型生成回應。

    Args:
        inst: 用戶指令。
        system_prompt: 系統提示詞。
        dialogue_history: 對話歷史。
        image_input: 圖像輸入。
        audio_input: 音頻輸入。
        video_input: 視頻輸入路徑。

    Returns:
        tuple: (generation_thread, streamer) 元組。

    Raises:
        ValueError: 模型未設置或生成過程出錯時拋出。
    """
    global global_model, global_tokenizer
    
    try:
        model, tokenizer = get_model_and_tokenizer()
        if model is None or tokenizer is None:
            raise LocalModelError("本地模型未設置")

        if video_input is not None:
            # 使用流式處理方式處理視頻
            session_id = ''.join(str(x) for x in np.random.randint(0, 10, 6))  # 生成隨機會話ID
            
            # 1. 預填充系統提示詞
            sys_msg = model.get_sys_prompt(mode='omni', language='zh')
            model.streaming_prefill(
                session_id=session_id,
                msgs=[sys_msg],
                tokenizer=tokenizer
            )

            # 2. 預填充視頻內容
            contents = get_video_chunk_content(video_path=video_input, flatten=False)
            for content in contents:
                msgs = [{"role": "user", "content": content}]
                model.streaming_prefill(
                    session_id=session_id,
                    msgs=msgs,
                    tokenizer=tokenizer
                )

            # 3. 生成回應
            async def stream_generator():
                try:
                    res = model.streaming_generate(
                        session_id=session_id,
                        tokenizer=tokenizer,
                        temperature=0.6,
                        generate_audio=False
                    )

                    audios = []
                    text = ""

                    for r in res:
                        if hasattr(r, 'audio_wav'):
                            audio_wav = r.audio_wav
                            sampling_rate = r.sampling_rate
                            txt = r.text

                            audios.append(audio_wav)
                            text += txt
                            yield txt
                        else:
                            text += r['text']
                            yield r['text']
                    
                    if audios:
                        combined_audio = np.concatenate(audios)
                        sf.write("temp_audio.wav", combined_audio, samplerate=sampling_rate)
                        logging.info("音頻已保存至 temp_audio.wav")
                    
                    logging.info(f"完整文本: {text}")
                except Exception as e:
                    raise LocalModelError(f"流式生成過程錯誤: {str(e)}")

            return None, stream_generator()
        else:
            # 普通對話處理
            messages = []
            
            # 添加系統提示詞
            if audio_input is not None:
                messages.append(model.get_sys_prompt(mode='audio_assistant', language='zh'))
            else:
                messages.append({'role': 'system', 'content': system_prompt})
            
            # 添加歷史對話
            if dialogue_history is not None:
                messages.extend(dialogue_history)
            
            # 構建當前用戶消息的內容
            user_content = []
            if image_input is not None:
                user_content.append(image_input)
            if audio_input is not None:
                user_content.append(audio_input)
            user_content.append(inst)
            messages.append({'role': 'user', 'content': user_content})
            
            streamer = TextIteratorStreamer(tokenizer, skip_prompt=True)
            
            # 使用模型的 chat 方法進行對話
            generation_kwargs = dict(
                msgs=messages,
                tokenizer=tokenizer,
                streamer=streamer,
                max_new_tokens=8192,
                sampling=True,
                temperature=0.6,
                top_p=0.9,
                use_tts_template=audio_input is not None,
                generate_audio=False,
                output_audio_path='temp/temp_audio.wav' if audio_input is not None else None
            )
            
            # 創建一個有實際工作的線程
            generation_thread = Thread(target=model.chat, kwargs=generation_kwargs)
            generation_thread.daemon = True  # 設置為守護線程
            generation_thread.start()
            return generation_thread, streamer
    except Exception as e:
        if isinstance(e, LocalModelError):
            raise
        raise LocalModelError(f"本地模型錯誤: {str(e)}")

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

async def generate_response(
    inst: str,
    system_prompt: str,
    dialogue_history: Optional[list] = None,
    image_input: Optional[any] = None,
    audio_input: Optional[any] = None,
    video_input: Optional[any] = None,
    response_schema: Optional[Type[BaseModel]] = None
):
    last_error = None
    # 根據優先順序嘗試使用可用的模型
    for model_name in settings.model_priority:
        if is_model_available(model_name):
            try:
                generator_func = MODEL_GENERATORS[model_name]
                
                # 準備參數
                params = {
                    "inst": inst,
                    "system_prompt": system_prompt,
                    "dialogue_history": dialogue_history,
                    "image_input": image_input,
                    "audio_input": audio_input,
                    "video_input": video_input,
                }
                
                # 只有 gemini 模型支持 response_schema
                if model_name == "gemini":
                    if response_schema:
                        params["response_schema"] = response_schema

                thread, result = await generator_func(**params)

                # 如果提供了 response_schema，我們預期 result 是一個 Pydantic 物件，而不是生成器
                if response_schema and model_name == "gemini":
                    if isinstance(result, BaseModel):
                        logging.info(f"成功使用 {model_name} 模型生成並解析了結構化回應")
                        return thread, result
                    else:
                        raise ValueError(f"{model_name} 模型未能回傳預期的 Pydantic 物件")

                # --- 以下是處理流式生成器的邏輯 ---
                gen = result

                # 統一處理生成器回應
                async def unified_gen():
                    try:
                        if isinstance(gen, TextIteratorStreamer):
                            # 使用事件循環來處理同步迭代器
                            try:
                                loop = asyncio.get_running_loop()
                            except RuntimeError:
                                loop = asyncio.get_event_loop()
                            iterator = iter(gen)
                            while True:
                                try:
                                    # 在事件循環中執行同步操作
                                    chunk = await loop.run_in_executor(None, lambda: next(iterator, None))
                                    if chunk is None:
                                        break
                                    if chunk:
                                        yield chunk
                                except Exception as e:
                                    logging.error(f"迭代 TextIteratorStreamer 時發生錯誤: {str(e)}")
                                    raise ValueError(f"本地模型生成過程中發生錯誤: {str(e)}")
                        else:
                            async for chunk in gen:
                                if chunk:
                                    yield chunk
                    except (GeminiError, OpenAIError, ClaudeError, LocalModelError) as e:
                        logging.error(f"API 或本地模型錯誤: {str(e)}")
                        raise
                    except Exception as e:
                        logging.error(f"生成過程錯誤: {str(e)}")
                        raise ValueError(f"{model_name} 模型生成過程中發生錯誤: {str(e)}")

                try:
                    # 創建生成器實例並進行安全檢查
                    gen_instance = unified_gen()
                    try:
                        # 獲取第一個響應
                        first_response = await anext(gen_instance)
                        if not first_response:
                            raise ValueError(f"{model_name} 模型沒有生成有效回應")
                        
                        async def final_gen():
                            yield first_response
                            try:
                                async for item in gen_instance:
                                    if item:
                                        yield item
                            except StopAsyncIteration:
                                return
                            
                        logging.info(f"成功使用 {model_name} 模型生成回應")
                        # thread 可能為 None，這是正常的
                        return thread, final_gen()
                    except StopAsyncIteration:
                        raise ValueError(f"{model_name} 模型沒有生成有效回應")
                except (GeminiError, OpenAIError, ClaudeError, LocalModelError) as e:
                    last_error = e
                    logging.error(f"使用 {model_name} API 時發生錯誤: {str(e)}")
                    logging.info(f"嘗試切換到下一個可用模型")
                    continue
                except StopAsyncIteration:
                    # 將 StopAsyncIteration 轉換為更具體的錯誤
                    last_error = ValueError(f"{model_name} 模型沒有生成任何回應")
                    logging.error(str(last_error))
                    logging.info(f"嘗試切換到下一個可用模型")
                    await asyncio.sleep(0)  # 讓出控制權給事件循環
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
