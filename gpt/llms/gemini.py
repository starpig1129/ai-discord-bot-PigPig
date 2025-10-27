from google import genai
from google.genai import types
from google.genai.types import Tool, GenerateContentConfig, GoogleSearch
import asyncio
import tempfile
import logging
import hashlib
import time
import pathlib
import httpx
from typing import Optional, Any, List, Type
from pydantic import BaseModel
from addons.settings import TOKENS
from gpt.utils.media import image_to_base64
from gpt.caching.gemini_cache import GeminiCacheManager
from gpt.core.exceptions import LLMProviderError  # PR#2: 統一錯誤類導入
from function import func

# Sentinel for safely terminating async iteration from executor threads
_SENTINEL = object()

# Initialize the Gemini model
tokens = TOKENS()

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    client = genai.Client(api_key=tokens.gemini_api_key)
    model_id = "gemini-2.5-flash"
    logger.info("Gemini API 客戶端初始化成功")
except Exception as e:
    asyncio.create_task(func.report_error(e, "Gemini API client initialization"))
    raise

class GeminiError(Exception):
    pass


def _map_httpx_error(e: Exception, trace_id: str) -> LLMProviderError:
    code = "connection_error"
    retriable = True
    status = None
    if isinstance(e, httpx.TimeoutException):
        code = "network_timeout"
        retriable = True
    elif isinstance(e, httpx.ConnectError):
        code = "connection_error"
        retriable = True
    elif isinstance(e, httpx.HTTPStatusError):
        status = int(getattr(e.response, "status_code", 0) or 0)
        if status == 429:
            code = "rate_limited"
            retriable = True
        elif 500 <= status < 600:
            code = "gateway_error"
            retriable = True
        elif status in (401, 403):
            code = "auth_failed"
            retriable = False
        else:
            code = "invalid_request"
            retriable = False
    return LLMProviderError(
        code=code,
        retriable=retriable,
        status=status,
        provider="gemini",
        details={"original_error": str(e), "type": type(e).__name__},
        trace_id=trace_id,
    )


def _map_httpx_error(e: Exception, trace_id: str) -> "LLMProviderError":
    from gpt.core.exceptions import LLMProviderError
    code = "connection_error"
    retriable = True
    status = None
    if isinstance(e, httpx.TimeoutException):
        code = "network_timeout"
        retriable = True
    elif isinstance(e, httpx.ConnectError):
        code = "connection_error"
        retriable = True
    elif isinstance(e, httpx.HTTPStatusError):
        status = int(getattr(e.response, "status_code", 0) or 0)
        if status == 429:
            code = "rate_limited"
            retriable = True
        elif 500 <= status < 600:
            code = "gateway_error"
            retriable = True
        elif status == 401 or status == 403:
            code = "auth_failed"
            retriable = False
        else:
            code = "invalid_request"
            retriable = False
    return LLMProviderError(
        code=code,
        retriable=retriable,
        status=status,
        provider="gemini",
        details={"original_error": str(e), "type": type(e).__name__},
        trace_id=trace_id,
    )


cache_manager: Optional[GeminiCacheManager] = None
def initialize_cache_manager(max_cache_count: int = 50):
    global cache_manager
    if cache_manager is None:
        cache_manager = GeminiCacheManager(client, max_cache_count)
        logger.info(f"全域快取管理器初始化完成，最大快取數量: {max_cache_count}")
    return cache_manager

async def get_cache_manager() -> Optional[GeminiCacheManager]:
    global cache_manager
    if cache_manager is None:
        cache_manager = initialize_cache_manager()
    return cache_manager

def _download_and_process_pdf(pdf_url_or_path: str) -> pathlib.Path:
    """下載並處理 PDF 檔案
    
    Args:
        pdf_url_or_path: PDF 檔案的 URL 或本地路徑
        
    Returns:
        pathlib.Path: 本地 PDF 檔案路徑
        
    Raises:
        Exception: 如果下載或處理失敗
    """
    try:
        # 檢查是否為 URL
        if pdf_url_or_path.startswith(('http://', 'https://')):
            # 從 URL 下載 PDF
            logger.info(f"正在從 URL 下載 PDF: {pdf_url_or_path}")
            
            # 產生暫存檔案名稱
            url_hash = hashlib.md5(pdf_url_or_path.encode()).hexdigest()[:8]
            temp_filename = f"pdf_{url_hash}_{int(time.time())}.pdf"
            file_path = pathlib.Path(tempfile.gettempdir()) / temp_filename
            
            # 使用 httpx 下載檔案
            with httpx.Client(timeout=30.0) as client:
                response = client.get(pdf_url_or_path)
                response.raise_for_status()
                
                # 驗證內容類型
                content_type = response.headers.get('content-type', '').lower()
                if 'pdf' not in content_type and not pdf_url_or_path.lower().endswith('.pdf'):
                    logger.warning(f"檔案可能不是 PDF 格式，Content-Type: {content_type}")
                
                # 寫入檔案
                file_path.write_bytes(response.content)
                logger.info(f"PDF 下載成功，儲存至: {file_path}")
                
        else:
            # 本地檔案路徑
            file_path = pathlib.Path(pdf_url_or_path)
            if not file_path.exists():
                raise FileNotFoundError(f"PDF 檔案不存在: {pdf_url_or_path}")
            if not file_path.suffix.lower() == '.pdf':
                raise ValueError(f"檔案不是 PDF 格式: {pdf_url_or_path}")
                
        return file_path
        
    except httpx.RequestError as e:
        raise Exception(f"下載 PDF 檔案失敗: {str(e)}")
    except httpx.HTTPStatusError as e:
        raise Exception(f"HTTP 錯誤 {e.response.status_code}: 無法下載 PDF 檔案")
    except Exception as e:
        asyncio.create_task(func.report_error(e, "PDF processing"))
        raise Exception(f"處理 PDF 檔案失敗: {str(e)}")

async def _upload_pdf_files(pdf_inputs) -> List[Any]:
    """處理 PDF 檔案上傳（異步版本）
    
    Args:
        pdf_inputs: PDF 輸入（URL、本地路徑或列表）
        
    Returns:
        list: 上傳後的檔案物件列表
    """
    uploaded_files = []
    temp_files = []
    
    try:
        # 統一處理為列表
        if not isinstance(pdf_inputs, list):
            pdf_inputs = [pdf_inputs]
        
        # 並行處理：先下載並準備所有 PDF 檔案
        for i, pdf_input in enumerate(pdf_inputs):
            logger.info(f"正在處理 PDF {i+1}/{len(pdf_inputs)}")
            
            # 下載並處理 PDF（保持同步，因為涉及檔案系統操作）
            local_pdf_path = _download_and_process_pdf(pdf_input)
            temp_files.append(local_pdf_path)
        
        # 使用 asyncio.to_thread() 並行上傳所有 PDF 檔案
        async def upload_single_pdf(pdf_path, index):
            """上傳單個 PDF 檔案的異步包裝函數"""
            try:
                # 將同步的上傳操作轉為異步
                uploaded_file = await asyncio.to_thread(client.files.upload, file=pdf_path)
                logger.info(f"PDF {index+1} 已成功上傳到 Gemini Files API")
                return uploaded_file
            except Exception as e:
                await func.report_error(e, f"PDF upload failed for index {index+1}")
                raise
        
        # 並行上傳所有 PDF 檔案
        upload_tasks = [
            upload_single_pdf(pdf_path, i)
            for i, pdf_path in enumerate(temp_files)
        ]
        
        # 等待所有上傳完成
        uploaded_files = await asyncio.gather(*upload_tasks)
        logger.info(f"所有 PDF 檔案已並行上傳完成，共 {len(uploaded_files)} 個")
            
    except Exception as e:
        await func.report_error(e, "PDF upload failed")
        raise
    finally:
        # 清理暫存檔案（如果是下載的）
        import os
        for temp_path in temp_files:
            try:
                # 只清理暫存目錄中的檔案，避免誤刪用戶檔案
                if str(temp_path).startswith(tempfile.gettempdir()):
                    os.unlink(temp_path)
                    logger.debug(f"已清理暫存 PDF 檔案: {temp_path}")
            except Exception as cleanup_error:
                asyncio.create_task(func.report_error(cleanup_error, "Failed to clean up temporary PDF file"))
    
    return uploaded_files

def _save_media_to_temp_file(media_data, media_type, index=0):
    """將媒體資料儲存到臨時檔案並返回檔案路徑
    
    Args:
        media_data: 媒體資料物件（PIL Image、音訊資料、影片資料等）
        media_type: 媒體類型 ('image', 'audio', 'video')
        index: 索引號（用於多個檔案）
        
    Returns:
        str: 臨時檔案路徑
    """
    if media_type == 'image':
        # 處理 PIL Image 物件
        suffix = f"_image_{index}.jpg"
        temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        media_data.save(temp_file.name, format='JPEG', quality=85)
        temp_file.close()
        return temp_file.name
        
    elif media_type == 'audio':
        # 處理音訊資料
        suffix = f"_audio_{index}.mp3"
        temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        
        if isinstance(media_data, bytes):
            # 如果是 bytes 資料
            temp_file.write(media_data)
        elif hasattr(media_data, 'read'):
            # 如果是檔案物件
            temp_file.write(media_data.read())
        else:
            # 其他類型的音訊資料
            temp_file.write(str(media_data).encode())
            
        temp_file.close()
        return temp_file.name
        
    elif media_type == 'video':
        # 處理影片資料
        suffix = f"_video_{index}.mp4"
        temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        
        if isinstance(media_data, bytes):
            # 如果是 bytes 資料
            temp_file.write(media_data)
        elif hasattr(media_data, 'read'):
            # 如果是檔案物件
            temp_file.write(media_data.read())
        elif isinstance(media_data, str):
            # 如果意外是檔案路徑，直接返回
            return media_data
        else:
            # 其他類型的影片資料
            temp_file.write(str(media_data).encode())
            
        temp_file.close()
        return temp_file.name
        
    else:
        raise ValueError(f"不支援的媒體類型: {media_type}")

async def _upload_media_files(media_inputs, media_type):
    """統一處理多媒體檔案上傳（異步版本）
    
    Args:
        media_inputs: 媒體輸入（單個物件或列表）
        media_type: 媒體類型 ('image', 'audio', 'video', 'pdf')
        
    Returns:
        list: 上傳後的檔案物件列表
    """
    # PDF 檔案使用專用的處理函數
    if media_type == 'pdf':
        return await _upload_pdf_files(media_inputs)
    
    uploaded_files = []
    temp_files = []
    
    try:
        # 統一處理為列表
        if not isinstance(media_inputs, list):
            media_inputs = [media_inputs]
        
        # 並行處理：先創建所有臨時檔案
        for i, media_data in enumerate(media_inputs):
            temp_path = _save_media_to_temp_file(media_data, media_type, i)
            temp_files.append(temp_path)
        
        # 使用 asyncio.to_thread() 並行上傳所有檔案
        async def upload_single_file(temp_path, index):
            """上傳單個檔案的異步包裝函數"""
            try:
                # 將同步的上傳操作轉為異步
                uploaded_file = await asyncio.to_thread(client.files.upload, file=temp_path)
                logger.info(f"已上傳{media_type} {index+1} 到 Gemini Files API")
                return uploaded_file
            except Exception as e:
                await func.report_error(e, f"{media_type} upload failed for index {index+1}")
                raise
        
        # 並行上傳所有檔案
        upload_tasks = [
            upload_single_file(temp_path, i)
            for i, temp_path in enumerate(temp_files)
        ]
        
        # 等待所有上傳完成
        uploaded_files = await asyncio.gather(*upload_tasks)
        logger.info(f"所有 {media_type} 檔案已並行上傳完成，共 {len(uploaded_files)} 個")
        
    except Exception as e:
        await func.report_error(e, f"{media_type} upload failed")
        raise
    finally:
        # 清理臨時檔案
        import os
        for temp_path in temp_files:
            try:
                os.unlink(temp_path)
            except Exception as cleanup_error:
                asyncio.create_task(func.report_error(cleanup_error, "Failed to clean up temporary media file"))
    
    return uploaded_files

async def _build_conversation_contents(inst, dialogue_history=None, image_input=None, audio_input=None, video_input=None, pdf_input=None):
    """建構符合官方規範的對話內容結構。
    
    根據 Gemini API 官方文檔建議，使用結構化的對話格式：
    - 每個訊息包含 role 和 parts
    - parts 陣列包含文字、圖片等內容
    
    Args:
        inst: 當前用戶輸入
        dialogue_history: 對話歷史
        image_input: 圖片輸入
        audio_input: 音頻輸入
        video_input: 視頻輸入
        pdf_input: PDF 檔案輸入
        
    Returns:
        list: 符合官方格式的對話內容列表
    """
    contents = []
    
    # 處理多輪對話歷史
    if dialogue_history:
        for msg in dialogue_history:
            # 根據 Google Gemini API 官方標準處理不同角色
            if msg['role'].lower() == 'function':
                # 工具調用結果使用 model 角色，並特殊格式化
                tool_name = msg.get('name', 'unknown_tool')
                tool_content = msg.get('content', '')
                
                # 格式化工具結果為可讀的形式
                formatted_content = f"[工具結果 - {tool_name}]\n{tool_content}"
                
                contents.append({
                    "role": "model",
                    "parts": [{"text": formatted_content}]
                })
            elif msg['role'].lower() in ['user', 'human']:
                contents.append({
                    "role": "user",
                    "parts": [{"text": msg['content']}]
                })
            elif msg['role'].lower() in ['assistant', 'model']:
                contents.append({
                    "role": "model",
                    "parts": [{"text": msg['content']}]
                })
            elif msg['role'].lower() == 'tool':
                # 處理舊格式的工具結果（向後相容性）
                tool_name = msg.get('user_id', 'unknown_tool')
                tool_content = msg.get('content', '')
                formatted_content = f"[工具結果 - {tool_name}]\n{tool_content}"
                
                contents.append({
                    "role": "model",
                    "parts": [{"text": formatted_content}]
                })
    
    # 建構當前用戶輸入的 parts
    current_parts = []
    
    # 處理多媒體輸入 - 使用統一的處理方式
    # 按優先級處理多媒體（PDF > 影片 > 音訊 > 圖片）
    if pdf_input:
        current_parts.append({"text": inst})
        try:
            # 使用統一的多媒體處理函數
            uploaded_pdfs = await _upload_media_files(pdf_input, 'pdf')
            for f in uploaded_pdfs:
                current_parts.append({'file_data': {'file_uri': f.uri, 'mime_type': f.mime_type}})
            logger.info("PDF 檔案已添加到對話內容中")
        except Exception as e:
            await func.report_error(e, "PDF processing in conversation build")
            # 降級：修改文字提示
            current_parts[0] = {"text": f"{inst}\n\n注意: PDF 處理發生錯誤，無法直接分析 PDF 內容"}
            
    elif video_input:
        current_parts.append({"text": inst})
        try:
            # 使用統一的多媒體處理函數
            uploaded_videos = await _upload_media_files(video_input, 'video')
            for f in uploaded_videos:
                current_parts.append({'file_data': {'file_uri': f.uri, 'mime_type': f.mime_type}})
            logger.info("影片已添加到對話內容中")
        except Exception as e:
            await func.report_error(e, "video processing in conversation build")
            # 降級：修改文字提示
            current_parts[0] = {"text": f"{inst}\n\n注意: 影片處理發生錯誤，無法直接分析影片內容"}
            
    elif audio_input:
        current_parts.append({"text": f"請分析這個音訊檔案: {inst}"})
        try:
            # 使用統一的多媒體處理函數
            uploaded_audios = await _upload_media_files(audio_input, 'audio')
            for f in uploaded_audios:
                current_parts.append({'file_data': {'file_uri': f.uri, 'mime_type': f.mime_type}})
            logger.info("音訊已添加到對話內容中")
        except Exception as e:
            await func.report_error(e, "audio processing in conversation build")
            current_parts[0] = {"text": f"{inst}\n\n注意: 音訊處理發生錯誤，無法分析音訊內容"}
        
    elif image_input:
        current_parts.append({"text": inst})
        try:
            # 使用統一的多媒體處理函數
            uploaded_images = await _upload_media_files(image_input, 'image')
            for f in uploaded_images:
                current_parts.append({'file_data': {'file_uri': f.uri, 'mime_type': f.mime_type}})
            logger.info("圖片已添加到對話內容中")
        except Exception as e:
            await func.report_error(e, "image processing in conversation build")
            # 降級：使用 inlineData 格式
            if isinstance(image_input, list):
                for img in image_input:
                    current_parts.append({
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": image_to_base64(img)
                        }
                    })
            else:
                current_parts.append({
                    "inlineData": {
                        "mimeType": "image/jpeg",
                        "data": image_to_base64(image_input)
                    }
                })
    else:
        # 純文字輸入
        current_parts.append({"text": inst})
    
    # 添加當前用戶輸入
    contents.append({
        "role": "user",
        "parts": current_parts
    })
    
    return contents

async def _create_context_hash(
    system_prompt: str,
    image_input: Optional[Any] = None,
    audio_input: Optional[Any] = None,
    video_input: Optional[Any] = None,
    pdf_input: Optional[Any] = None
) -> str:
    """為給定的上下文生成一個穩定的、基於內容的哈希值，用於快取。

    Args:
        system_prompt (str): 系統提示。
        image_input: 圖片輸入。
        audio_input: 音訊輸入。
        video_input: 影片輸入。
        pdf_input: PDF 輸入。

    Returns:
        str: 生成的 SHA256 哈希值。
    """
    hasher = hashlib.sha256()

    # 1. 哈希文字輸入
    hasher.update(system_prompt.encode('utf-8'))

    # 2. 定義一個內部函數來處理不同媒體類型的內容哈希
    def hash_media_content(media_input, media_type):
        if not media_input:
            return

        # 確保輸入是列表以便統一處理
        inputs = media_input if isinstance(media_input, list) else [media_input]
        
        for item in inputs:
            content = b''
            try:
                if media_type == 'pdf':
                    # 對 PDF，下載並讀取其內容
                    pdf_path = _download_and_process_pdf(item)
                    content = pdf_path.read_bytes()
                    # 如果是臨時檔案，使用後清理
                    if str(pdf_path).startswith(tempfile.gettempdir()):
                        import os
                        os.unlink(pdf_path)
                elif media_type == 'image':
                    # 對 PIL 圖片，轉換為 bytes
                    import io
                    from PIL import Image
                    if isinstance(item, Image.Image):
                        buf = io.BytesIO()
                        item.save(buf, format='PNG') # 使用無損格式以保證哈希穩定
                        content = buf.getvalue()
                elif media_type in ['audio', 'video']:
                    # 對音訊/影片，處理 bytes、路徑或類檔案物件
                    if isinstance(item, bytes):
                        content = item
                    elif isinstance(item, str) and pathlib.Path(item).exists():
                        content = pathlib.Path(item).read_bytes()
                    elif hasattr(item, 'read'):
                        content = item.read()
                        if hasattr(item, 'seek'): # 重置指標
                            item.seek(0)

                if content:
                    hasher.update(content)
            except Exception as e:
                asyncio.create_task(func.report_error(e, f"hashing media content for {media_type}"))

    # 順序執行哈希操作以保證 hasher 的狀態一致性
    await asyncio.to_thread(hash_media_content, image_input, 'image')
    await asyncio.to_thread(hash_media_content, audio_input, 'audio')
    await asyncio.to_thread(hash_media_content, video_input, 'video')
    await asyncio.to_thread(hash_media_content, pdf_input, 'pdf')

    return hasher.hexdigest()

async def generate_response(inst: str,
                            system_prompt: str,
                            response_schema: Optional[Type[BaseModel]] = None,
                            dialogue_history=None,
                            image_input=None,
                            audio_input=None,
                            video_input=None,
                            pdf_input=None,
                            use_cache=True,
                            cache_ttl="3600s"):
    """
    帶有通用快取功能的 Gemini API 回應生成器。
    此函數現在會為所有輸入類型的組合嘗試使用快取。
    """
    cache_mgr = await get_cache_manager()
    cache_key = None
    generation_config_args = {}
    is_streaming = not bool(response_schema)
    tool_list = None

    if response_schema:
        generation_config_args["response_mime_type"] = "application/json"
        generation_config_args["response_schema"] = response_schema
    else:
        generation_config_args["response_modalities"] = ["TEXT"]
        tool_list = [
            types.Tool(url_context=types.UrlContext()),
            types.Tool(code_execution=types.ToolCodeExecution()),
            types.Tool(googleSearch=types.GoogleSearch()),
        ]
            
    # 步驟 1: 如果啟用快取，為當前請求生成唯一的內容哈希
    if use_cache and cache_mgr:
        cache_key = await _create_context_hash(
            system_prompt=system_prompt,
            image_input=image_input,
            audio_input=audio_input,
            video_input=video_input,
            pdf_input=pdf_input
        )
        # 嘗試獲取快取
        cache = await cache_mgr.get_cache_by_key(cache_key)
        
        # <<< 步驟 3: 如果快取未命中，則動態創建它
        if cache is None:
            try:
                # 3a. 準備要快取的靜態內容（上傳檔案）
                logger.info(f"快取未命中 ({cache_key})。準備上傳靜態上下文檔案...")
                contents = await _build_conversation_contents(
                    inst=inst,
                    dialogue_history=dialogue_history,
                    image_input=image_input,
                    audio_input=audio_input,
                    video_input=video_input, 
                    pdf_input=pdf_input    
                )
                cache_args = {
                    "cache_key": cache_key,
                    "model": model_id,
                    "system_instruction": system_prompt,
                    "contents": contents,
                    "ttl": cache_ttl,
                    "display_name": f"Cache for {cache_key[:16]}",
                }
                if response_schema is None:
                    cache_args["tools"] = tool_list

                # 3b. 檢查 token 數量是否足夠
                token_count_response = await asyncio.to_thread(
                    client.models.count_tokens,
                    contents=contents,
                    model=model_id
                )
                total_tokens = token_count_response.total_tokens
                
                min_tokens_for_caching = 1024  # Gemini API 的最低要求

                if total_tokens >= min_tokens_for_caching:
                    # 3c. 呼叫管理器來創建並註冊這個新的快取
                    logger.info(f"內容 token ({total_tokens}) 足夠，正在創建快取...")
                    cache = cache_mgr.create_and_register_cache(
                        **cache_args
                    )
                else:
                    logger.warning(
                        f"內容 token ({total_tokens}) 過少，"
                        f"未達到快取所需的最小數量 ({min_tokens_for_caching})。"
                        "將跳過快取創建。"
                    )
                    cache = None # 確保在 token 不足時，後續流程不會使用快取

            except Exception as e:
                await func.report_error(e, "dynamic cache creation")
                cache = None # 確保出錯時 cache 為 None

    # <<< 步驟 4: 根據是否有可用的快取，準備 API 請求
    response_object = None
    if use_cache and cache:
        try:
            # --- 快取模式 ---
            logger.info(f"正在嘗試使用快取模式，快取名稱: {cache.name}")
            
            # 4a. 構建「動態」對話內容
            contents = await _build_conversation_contents(
                inst=inst,
                dialogue_history=dialogue_history,
                image_input=None, audio_input=None, video_input=None, pdf_input=None
            )
            config = types.GenerateContentConfig(cached_content=cache.name, **generation_config_args)

            api_kwargs = {
                "model": model_id,
                "contents": contents,
                "config": config
            }
            if response_schema:
                logger.info("使用快取模式生成結構化回應")
                response_object = await asyncio.to_thread(client.models.generate_content, **api_kwargs)
            else:
                logger.info("使用快取模式生成流式回應")
                response_object = await asyncio.to_thread(client.models.generate_content_stream, **api_kwargs)
        
        except Exception as e:
            await func.report_error(e, "cached content generation")
            # 清理 response_object，確保進入非快取模式
            response_object = None

    # 如果未使用快取或快取模式失敗，則進入非快取模式
    if response_object is None:
        if tool_list is not None:
            generation_config_args["tools"] = tool_list
        # --- 傳統（非快取）模式 ---
        logger.info("使用傳統（非快取）模式生成回應")
        
        # 4c. 構建包含所有內容的完整請求
        contents = await _build_conversation_contents(
            inst, 
            dialogue_history, 
            image_input, 
            audio_input, 
            video_input, 
            pdf_input
        )
        config = GenerateContentConfig(system_instruction=system_prompt, **generation_config_args)
        
        if is_streaming:
            response_object = await asyncio.to_thread(client.models.generate_content_stream, model=model_id, contents=contents, config=config)
        else:
            response_object = await asyncio.to_thread(client.models.generate_content, model=model_id, contents=contents, config=config)

    try:
        if is_streaming:
            # --- 流式回應處理 ---
            logger.info("正在處理流式回應...")
            async def async_generator():
                try:
                    accumulated_text = ""
                    chunk_count = 0

                    try:
                        # 使用執行緒執行阻塞的同步迭代，以免阻塞 asyncio 事件迴圈
                        loop = asyncio.get_running_loop()
                        sync_iterator = iter(response_object)

                        # 在本地定義同步輔助函式以捕獲 StopIteration 並返回哨兵值
                        def _sync_next_chunk(iterator):
                            try:
                                return next(iterator)
                            except StopIteration:
                                return _SENTINEL

                        while True:
                            chunk = await loop.run_in_executor(None, _sync_next_chunk, sync_iterator)
                            if chunk is _SENTINEL:
                                break

                            chunk_count += 1
                            if chunk and hasattr(chunk, 'text') and chunk.text:
                                chunk_text = chunk.text.strip()
                                if chunk_text:
                                    accumulated_text += chunk_text
                                    yield chunk_text
                            elif chunk is None:
                                break
                    except Exception as stream_error:
                        error_message = str(stream_error)

                        if "Response not read" in error_message or "400 Bad Request" in error_message:
                            if accumulated_text:
                                yield accumulated_text
                                return
                            else:
                                # 降級到非流式調用
                                try:
                                    if cache and use_cache:
                                        fallback_config = types.GenerateContentConfig(
                                            cached_content=cache.name,
                                            tools=tool_list
                                        )
                                        # 使用快取中繼資料中儲存的模型，確保一致性
                                        fallback_response = await asyncio.to_thread(
                                            client.models.generate_content,
                                            model=cache.model,
                                            contents=contents,
                                            config=fallback_config
                                        )
                                    else:
                                        fallback_config = GenerateContentConfig(
                                            system_instruction=system_prompt,
                                            tools=tool_list,
                                            response_modalities=["TEXT"],
                                        )
                                        fallback_response = await asyncio.to_thread(
                                            client.models.generate_content,
                                            model=model_id,
                                            contents=contents,
                                            config=fallback_config
                                        )

                                    if fallback_response and fallback_response.text:
                                        yield fallback_response.text
                                        return
                                    else:
                                        raise GeminiError(f"Gemini API 流式和非流式回應都失敗: {error_message}")
                                except Exception as fallback_error:
                                    await func.report_error(fallback_error, "Gemini API fallback failed")
                                    raise GeminiError(f"Gemini API 降級處理失敗: {fallback_error}")

                        elif "RESOURCE_PROJECT_INVALID" in error_message:
                            raise GeminiError(f"Gemini API 項目設定錯誤: {error_message}")
                        elif "PERMISSION_DENIED" in error_message:
                            raise GeminiError(f"Gemini API 權限錯誤: {error_message}")
                        elif "QUOTA_EXCEEDED" in error_message:
                            raise GeminiError(f"Gemini API 配額超限: {error_message}")
                        else:
                            if accumulated_text:
                                yield accumulated_text
                                return
                            else:
                                raise GeminiError(f"Gemini API 錯誤: {error_message}")

                    if not accumulated_text:
                        raise GeminiError("Gemini API 沒有生成任何回應內容")

                except Exception as e:
                    await func.report_error(e, "streaming generation")
                    raise GeminiError(f"流式生成失敗: {e}") from e
            return None, async_generator()
        else:
            # --- 結構化回應處理 ---
            logger.info(f"收到結構化回應: {response_object.text[:500]}...")
            try:
                parsed_data = response_object.parsed
                return None, parsed_data
            except (AttributeError, IndexError) as e:
                raise GeminiError(f"無法從 API 回應中提取 JSON 物件: {e}\n原始回應: {response_object.text}")
    except Exception as e:
        await func.report_error(e, "processing Gemini response")
        raise GeminiError(f"處理 Gemini 回應失敗: {e}") from e
