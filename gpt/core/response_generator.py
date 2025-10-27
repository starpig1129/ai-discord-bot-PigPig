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
# PR#2: 統一錯誤分類與集中式重試控制
from typing import Any, Dict, Tuple
from gpt.core.exceptions import LLMProviderError, is_retryable
from gpt.core.retry_controller import RetryController
from gpt.utils.sanitizer import mask_text
from function import func
import asyncio

settings = Settings()
tokens = TOKENS()

# 全局變量用於本地模型
global_model = None
global_tokenizer = None
_model_lock = asyncio.Lock()

async def get_model_and_tokenizer():
    """
    以執行緒安全的方式獲取或初始化模型和分詞器。
    """
    global global_model, global_tokenizer
    if global_model is None or global_tokenizer is None:
        async with _model_lock:
            # 再次檢查，因為在等待鎖的時候可能已經被其他協程初始化了
            if global_model is None or global_tokenizer is None:
                logging.info("正在初始化本地模型...")
                try:
                    # 這裡的 set_model_and_tokenizer 是一個同步函數，
                    # 需要在異步函數中以非阻塞方式運行。
                    loop = asyncio.get_running_loop()
                    model, tokenizer = await loop.run_in_executor(
                        None, set_model_and_tokenizer
                    )
                    global_model = model
                    global_tokenizer = tokenizer
                    logging.info("本地模型初始化成功。")
                except Exception as e:
                    await func.report_error(e, "local model initialization")
                    # 確保即使失敗也不會一直重試
                    global_model, global_tokenizer = None, None
                    raise
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
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logging.info(f"正在 {device} 上載入模型...")
        
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        model = AutoModel.from_pretrained(
            model_path,
            trust_remote_code=True,
            attn_implementation='sdpa',
            torch_dtype=torch.bfloat16
        ).eval().to(device)
        
        logging.info(f"模型成功載入到 {device}")

        # 初始化 TTS 和其他模組
        model.init_tts()
        model.tts.float()  # 避免某些 PyTorch 版本的兼容性問題
        
        global_model = model
        global_tokenizer = tokenizer
        return model, tokenizer
    except Exception as e:
        asyncio.create_task(func.func.report_error(e, "MiniCPM-o model initialization"))
        raise ValueError(f"初始化 MiniCPM-o 模型時發生錯誤: {str(e)}")

class LocalModelError(Exception):
    pass


async def _singleton_async_gen(payload: Dict[str, Any]):
    # 將單筆 dict 以單元素 async 生成器形式輸出，維持呼叫端流式相容
    yield payload


def _error_envelope_stream(payload: Dict[str, Any]):
    # 轉為 async 生成器，與既有回傳型別兼容
    return _singleton_async_gen(payload)

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
        model, tokenizer = await get_model_and_tokenizer()
        if model is None or tokenizer is None:
            raise LocalModelError("本地模型未設置或初始化失敗")

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
                    await func.func.report_error(e, "streaming generation")
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
        await func.func.report_error(e, "local model error")
        raise LocalModelError(f"本地模型錯誤: {str(e)}")

# 定義模型生成函數映射
MODEL_GENERATORS = {
    "openai": openai_generate,
    "gemini": gemini_generate,
    "claude": claude_generate,
    "local": local_generate
}

# 定義模型可用性檢查
async def is_model_available(model_name):
    if model_name == "openai":
        return tokens.openai_api_key is not None
    elif model_name == "gemini":
        return tokens.gemini_api_key is not None
    elif model_name == "claude":
        return tokens.anthropic_api_key is not None
    elif model_name == "local":
        # 使用異步版本的 get_model_and_tokenizer
        try:
            model, tokenizer = await get_model_and_tokenizer()
            return model is not None and tokenizer is not None
        except Exception:
            return False
    return False

async def generate_response(
    inst: str,
    system_prompt: str,
    dialogue_history: Optional[list] = None,
    image_input: Optional[any] = None,
    audio_input: Optional[any] = None,
    video_input: Optional[any] = None,
    response_schema: Optional[Type[BaseModel]] = None,
    retry: Optional[RetryController] = None,
    trace_id: Optional[str] = None,
):
    logging.info("--- 開始生成回應 ---")
    try:
        # 關鍵診斷：完整列印傳入 messages（避免洩露，遮罩部分內容長度）
        def _shorten(x, n=200):
            try:
                s = str(x)
                return s if len(s) <= n else s[:n] + "...(truncated)"
            except Exception:
                return "<non-str>"
        summary = []
        if isinstance(dialogue_history, list):
            for i, m in enumerate(dialogue_history):
                if isinstance(m, dict):
                    summary.append({
                        "idx": i,
                        "role": m.get("role"),
                        "name": m.get("name"),
                        "content_preview": _shorten(m.get("content"))
                    })
                else:
                    summary.append({"idx": i, "type": type(m).__name__, "preview": _shorten(m)})
        else:
            summary = _shorten(dialogue_history)
        logging.info("diagnostic.dialogue_history | count=%s detail=%s",
                     str(len(dialogue_history) if isinstance(dialogue_history, list) else 0),
                     summary)
    except Exception as _e:
        logging.warning("diagnostic.dialogue_history.log_fail err=%s", str(_e))
    # 預設 RetryController（如未提供）
    if retry is None:
        retry = RetryController(
            max_retries=2,
            base_delay=0.6,
            jitter=0.4,
            retryable_codes={
                "network_timeout",
                "connection_error",
                "dns_error",
                "rate_limited",
                "server_overload",
                "gateway_error",
                "provider_unavailable",
            },
            timeout_ceiling=6.0,
        )

    last_provider_err: Optional[LLMProviderError] = None
    last_generic_err: Optional[Exception] = None

    # 事件打點 helper
    def _event_provider_try(provider: str, model: str, attempt: int, trace: Optional[str]) -> None:
        logging.info(
            "provider_try | provider=%s model=%s attempt=%d trace_id=%s",
            mask_text(provider),
            mask_text(model),
            attempt,
            mask_text(trace or ""),
        )

    def _event_provider_retry(provider: str, attempt: int, delay_ms: float, code: str, trace: Optional[str]) -> None:
        logging.info(
            "provider_retry | provider=%s attempt=%d delay_ms=%.0f code=%s trace_id=%s",
            mask_text(provider),
            attempt,
            delay_ms,
            mask_text(code),
            mask_text(trace or ""),
        )

    def _event_provider_failover(fr: str, to: str, reason: str) -> None:
        logging.info(
            "provider_failover | from=%s to=%s reason=%s",
            mask_text(fr),
            mask_text(to),
            mask_text(reason),
        )

    def _event_provider_fail(provider: str, code: str, retriable: bool, status: Optional[int]) -> None:
        logging.error(
            "provider_fail | provider=%s code=%s retriable=%s status=%s",
            mask_text(provider),
            mask_text(code),
            str(retriable),
            str(status),
        )

    # 根據優先順序嘗試使用可用的模型
    for model_name in settings.model_priority:
        logging.info(f"正在檢查模型: {model_name}")
        if not await is_model_available(model_name):
            continue

        logging.info(f"模型 {model_name} 可用，正在嘗試使用...")
        provider_name = model_name  # 現有結構中 provider 與 model_name 對應
        try:
            generator_func = MODEL_GENERATORS[model_name]

            # 準備參數
            params: Dict[str, Any] = {
                "inst": inst,
                "system_prompt": system_prompt,
                "dialogue_history": dialogue_history,
                "image_input": image_input,
                "audio_input": audio_input,
                "video_input": video_input,
            }
            # 只有 gemini 模型支持 response_schema
            if model_name == "gemini" and response_schema:
                params["response_schema"] = response_schema

            attempt_counter = {"n": 0}

            async def _invoke_provider() -> Tuple[Optional[Thread], Any]:
                # 外層 run() 是同步重試控制，內層為實際呼叫
                # 這裡只回傳 thread 與 result，並讓上層統一處理流式或非流式
                attempt_counter["n"] += 1
                _event_provider_try(provider_name, model_name, attempt_counter["n"], trace_id)
                try:
                    thread, result = await generator_func(**params)
                    return thread, result
                except LLMProviderError as e:
                    # 統一錯誤類，交由 RetryController 判斷是否重試
                    raise
                except (GeminiError, OpenAIError, ClaudeError, LocalModelError) as e:
                    # 舊有 provider 專屬錯誤：暫時轉譯為 LLMProviderError（最小入侵）
                    # 嘗試分類為 retriable 的通用情境（未知時標記 malformed_response 並不可重試）
                    mapped = LLMProviderError(
                        code="gateway_error",
                        retriable=True,
                        status=None,
                        provider=provider_name,
                        details={"message": str(e), "type": type(e).__name__},
                        trace_id=trace_id or "",
                    )
                    raise mapped
                except Exception as e:
                    mapped = LLMProviderError(
                        code="malformed_response",
                        retriable=False,
                        status=None,
                        provider=provider_name,
                        details={"message": str(e), "type": type(e).__name__},
                        trace_id=trace_id or "",
                    )
                    raise mapped

            # 使用集中式重試控制執行 provider 呼叫
            def _on_try(attempt: int) -> None:
                # 已在 _invoke_provider 內打點 try，這裡保持最小行為
                pass

            def _on_retry(attempt: int, delay: float, code: str) -> None:
                _event_provider_retry(provider_name, attempt, delay * 1000.0, code, trace_id)

            try:
                thread, result = await retry.run_async(
                    _invoke_provider, on_try=_on_try, on_retry=_on_retry
                )
            except LLMProviderError as e:
                last_provider_err = e
                _event_provider_fail(provider_name, e.code, e.retriable, e.status)
                # 僅當該 provider 在重試後仍失敗才 failover
                # 準備切到下一個 provider
                continue

            # 成功路徑（保持相容）
            if response_schema and model_name == "gemini":
                if isinstance(result, BaseModel):
                    logging.info(f"成功使用 {model_name} 模型生成並解析了結構化回應")
                    return thread, result
                raise LLMProviderError(
                    code="malformed_response",
                    retriable=False,
                    status=None,
                    provider=provider_name,
                    details={"message": f"{model_name} 未回傳預期 Pydantic 物件"},
                    trace_id=trace_id or "",
                )

            # 為避免在失敗嘗試時輸出任何 token 導致後續重試被「附加」拼接，
            # 我們改為採用「延遲輸出」策略：在確認生成穩定前先暫存輸出，若立刻出錯則不對外輸出任何內容。
            gen = result

            async def unified_gen():
                # 附帶診斷資訊以便追蹤來源
                source_kind = "TextIteratorStreamer" if isinstance(gen, TextIteratorStreamer) else "async_gen"
                logging.info(
                    "unified_gen.start | provider=%s model=%s source=%s attempt=%d trace_id=%s gen_id=%s",
                    mask_text(provider_name),
                    mask_text(model_name),
                    source_kind,
                    attempt_counter["n"],
                    mask_text(trace_id or ""),
                    hex(id(gen)),
                )
                try:
                    if isinstance(gen, TextIteratorStreamer):
                        try:
                            loop = asyncio.get_running_loop()
                        except RuntimeError:
                            loop = asyncio.get_event_loop()
                        iterator = iter(gen)
                        while True:
                            try:
                                chunk = await loop.run_in_executor(None, lambda: next(iterator, None))
                                if chunk is None:
                                    break
                                if chunk:
                                    logging.debug(
                                        "unified_gen.yield | provider=%s attempt=%d len=%d trace_id=%s",
                                        mask_text(provider_name),
                                        attempt_counter["n"],
                                        len(chunk) if isinstance(chunk, str) else -1,
                                        mask_text(trace_id or ""),
                                    )
                                    yield chunk
                            except Exception as e:
                                await func.report_error(e, "TextIteratorStreamer iteration")
                                raise LLMProviderError(
                                    code="malformed_response",
                                    retriable=False,
                                    status=None,
                                    provider=provider_name,
                                    details={"message": str(e), "stage": "stream_iter"},
                                    trace_id=trace_id or "",
                                )
                    else:
                        async for chunk in gen:
                            if chunk:
                                logging.debug(
                                    "unified_gen.yield | provider=%s attempt=%d len=%d trace_id=%s",
                                    mask_text(provider_name),
                                    attempt_counter["n"],
                                    len(chunk) if isinstance(chunk, str) else -1,
                                    mask_text(trace_id or ""),
                                )
                                yield chunk
                except LLMProviderError:
                    raise
                except Exception as e:
                    await func.report_error(e, "generation process")
                    raise LLLMProviderError(
                        code="malformed_response",
                        retriable=False,
                        status=None,
                        provider=provider_name,
                        details={"message": str(e), "stage": "unified_gen"},
                        trace_id=trace_id or "",
                    )

            try:
                gen_instance = unified_gen()
                try:
                    # 延遲輸出策略：先嘗試抓第一個與第二個片段，確保生成穩定後再一次性對外輸出
                    first_response = await anext(gen_instance)
                    if not first_response:
                        raise LLMProviderError(
                            code="malformed_response",
                            retriable=False,
                            status=None,
                            provider=provider_name,
                            details={"message": f"{model_name} 首次回應為空"},
                            trace_id=trace_id or "",
                        )

                    # 嘗試抓第二個片段以確認生成器穩定性；若 StopAsyncIteration，表示單段輸出亦可視為成功
                    second_response = None
                    got_second = False
                    try:
                        second_response = await anext(gen_instance)
                        got_second = second_response is not None
                    except StopAsyncIteration:
                        got_second = False

                    async def final_gen():
                        # 僅在此處開始對外輸出，確保若稍早出錯不會遺留部分輸出
                        logging.info(
                            "final_gen.start | provider=%s attempt=%d trace_id=%s gen_id=%s",
                            mask_text(provider_name),
                            attempt_counter["n"],
                            mask_text(trace_id or ""),
                            hex(id(gen_instance)),
                        )
                        # 先 flush 暫存的 first / second
                        yield first_response
                        if got_second and second_response:
                            yield second_response
                        # 再繼續輸出剩餘的生成內容
                        try:
                            async for item in gen_instance:
                                if item:
                                    yield item
                        except StopAsyncIteration:
                            return

                    logging.info(f"成功使用 {model_name} 模型生成回應（延遲輸出策略已啟用）")
                    return thread, final_gen()
                except StopAsyncIteration:
                    # 在尚未開始對外輸出前就結束，視為無有效回應，乾淨失敗，不會殘留輸出導致拼接
                    raise LLMProviderError(
                        code="malformed_response",
                        retriable=False,
                        status=None,
                        provider=provider_name,
                        details={"message": f"{model_name} 沒有生成有效回應"},
                        trace_id=trace_id or "",
                    )
            except LLMProviderError as e:
                # 任何在延遲輸出前的錯誤都不會對外輸出 token，避免下次嘗試時「附加」拼接
                last_provider_err = e
                _event_provider_fail(provider_name, e.code, e.retriable, e.status)
                continue
        except Exception as e:
            # 初始化或參數準備等非 LLMProviderError 的未知錯誤
            last_generic_err = e
            func.report_error(e, f"initializing {model_name} model")
            continue
        finally:
            # 在此處理 failover 事件的 from->to 打點
            # 找出下一個 provider 名稱以利紀錄
            # 無狀態記錄上個 provider 名稱；為最小入侵，僅在可推導時記錄
            pass

    # 所有 provider 均失敗 → 結構化錯誤回傳（不以空字串或隱藏錯誤）
    if last_provider_err:
        safe_message = "Provider failed after retries."
        return None, _error_envelope_stream(
            {
                "error": True,
                "type": "ProviderError",
                "code": last_provider_err.code,
                "message": safe_message,
                "trace_id": last_provider_err.trace_id or trace_id,
                "details": {
                    "provider": last_provider_err.provider,
                    "status": last_provider_err.status,
                },
            }
        )
    if last_generic_err:
        return None, _error_envelope_stream(
            {
                "error": True,
                "type": "ProviderError",
                "code": "malformed_response",
                "message": "Provider failed unexpectedly.",
                "trace_id": trace_id,
                "details": {
                    "provider": "unknown",
                    "status": None,
                },
            }
        )

    return None, _error_envelope_stream(
        {
            "error": True,
            "type": "ProviderError",
            "code": "provider_unavailable",
            "message": "No available provider.",
            "trace_id": trace_id,
            "details": {"provider": "none", "status": None},
        }
    )
