from google import genai
from google.genai.types import Tool, GenerateContentConfig, GoogleSearch
import asyncio
from addons.settings import TOKENS
import numpy as np
from PIL import Image
from moviepy.editor import VideoFileClip
from gpt.vision_tool import image_to_base64
import io
import tempfile
import logging

# Initialize the Gemini model
tokens = TOKENS()

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    client = genai.Client(api_key=tokens.gemini_api_key)
    model_id = "gemini-2.0-flash"
    
    google_search_tool = Tool(
        google_search = GoogleSearch()
    )
    
    logger.info("Gemini API 客戶端初始化成功")
except Exception as e:
    logger.error(f"Gemini API 客戶端初始化失敗: {e}")
    raise

class GeminiError(Exception):
    pass

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

def _upload_media_files(media_inputs, media_type):
    """統一處理多媒體檔案上傳
    
    Args:
        media_inputs: 媒體輸入（單個物件或列表）
        media_type: 媒體類型 ('image', 'audio', 'video')
        
    Returns:
        list: 上傳後的檔案物件列表
    """
    uploaded_files = []
    temp_files = []
    
    try:
        # 統一處理為列表
        if not isinstance(media_inputs, list):
            media_inputs = [media_inputs]
        
        for i, media_data in enumerate(media_inputs):
            # 儲存到臨時檔案
            temp_path = _save_media_to_temp_file(media_data, media_type, i)
            temp_files.append(temp_path)
            
            # 上傳到 Gemini Files API
            uploaded_file = client.files.upload(file=temp_path)
            uploaded_files.append(uploaded_file)
            
            logger.info(f"已上傳{media_type} {i+1} 到 Gemini Files API")
            
    except Exception as e:
        logger.error(f"{media_type}上傳失敗: {str(e)}")
        raise
    finally:
        # 清理臨時檔案
        import os
        for temp_path in temp_files:
            try:
                os.unlink(temp_path)
            except Exception as cleanup_error:
                logger.warning(f"清理臨時檔案失敗: {cleanup_error}")
    
    return uploaded_files

async def _build_conversation_contents(inst, dialogue_history=None, image_input=None, audio_input=None, video_input=None):
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
    # 按優先級處理多媒體（影片 > 音訊 > 圖片）
    if video_input:
        current_parts.append({"text": inst})
        try:
            # 使用統一的多媒體處理函數
            uploaded_videos = _upload_media_files(video_input, 'video')
            for uploaded_video in uploaded_videos:
                current_parts.append(uploaded_video)
            logger.info("影片已添加到對話內容中")
        except Exception as e:
            logger.error(f"影片處理失敗，使用降級方案: {str(e)}")
            # 降級：修改文字提示
            current_parts[0] = {"text": f"{inst}\n\n注意: 影片處理發生錯誤，無法直接分析影片內容"}
            
    elif audio_input:
        current_parts.append({"text": f"請分析這個音訊檔案: {inst}"})
        try:
            # 使用統一的多媒體處理函數
            uploaded_audios = _upload_media_files(audio_input, 'audio')
            for uploaded_audio in uploaded_audios:
                current_parts.append(uploaded_audio)
            logger.info("音訊已添加到對話內容中")
        except Exception as e:
            logger.error(f"音訊處理失敗: {str(e)}")
            current_parts[0] = {"text": f"{inst}\n\n注意: 音訊處理發生錯誤，無法分析音訊內容"}
        
    elif image_input:
        current_parts.append({"text": inst})
        try:
            # 使用統一的多媒體處理函數
            uploaded_images = _upload_media_files(image_input, 'image')
            for uploaded_image in uploaded_images:
                current_parts.append(uploaded_image)
            logger.info("圖片已添加到對話內容中")
        except Exception as e:
            logger.error(f"圖片處理失敗，使用降級方案: {str(e)}")
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

async def generate_response(inst, system_prompt, dialogue_history=None, image_input=None, audio_input=None, video_input=None):
    """根據 Gemini API 官方最佳實踐生成回應。
    
    主要改進:
    1. 使用 system_instruction 參數而非將系統提示詞混合到用戶訊息中
    2. 採用官方推薦的 client.files.upload() 處理多媒體檔案
    3. 使用簡化的 contents 格式，符合官方範例
    4. 遵循 Google Code Style Guide
    
    Args:
        inst: 用戶輸入訊息
        system_prompt: 系統提示詞（將使用 system_instruction 參數）
        dialogue_history: 多輪對話歷史列表
        image_input: 圖片輸入（支援單張或多張圖片）
        audio_input: 音頻輸入（目前不支援）
        video_input: 視頻輸入
        
    Returns:
        tuple: (None, async_generator) 用於流式回應
    """
    try:
        # 處理多媒體檔案和建構內容
        contents = []
        
        # 統一處理多媒體輸入
        media_files = []
        
        # 按優先級處理多媒體（影片 > 音訊 > 圖片）
        if video_input:
            try:
                uploaded_videos = _upload_media_files(video_input, 'video')
                media_files.extend(uploaded_videos)
                contents.append(inst)
                contents.extend(uploaded_videos)
                logger.info("影片上傳成功，使用官方 Files API")
            except Exception as e:
                logger.error(f"影片上傳失敗，降級處理: {str(e)}")
                # 降級到結構化內容格式
                contents = await _build_conversation_contents(inst, dialogue_history, image_input, audio_input, video_input)
        
        elif audio_input:
            try:
                uploaded_audios = _upload_media_files(audio_input, 'audio')
                media_files.extend(uploaded_audios)
                contents.append("請分析這個音訊檔案: " + inst)
                contents.extend(uploaded_audios)
                logger.info("音訊上傳成功，使用官方 Files API")
            except Exception as e:
                logger.error(f"音訊上傳失敗，降級處理: {str(e)}")
                contents.append(f"{inst}\n\n注意: 音訊處理發生錯誤，無法分析音訊內容")
        
        elif image_input:
            try:
                uploaded_images = _upload_media_files(image_input, 'image')
                media_files.extend(uploaded_images)
                contents.append(inst)
                contents.extend(uploaded_images)
                logger.info("圖片上傳成功，使用官方 Files API")
            except Exception as e:
                logger.error(f"圖片上傳失敗，降級處理: {str(e)}")
                # 降級到結構化內容格式
                contents = await _build_conversation_contents(inst, dialogue_history, image_input, audio_input, video_input)
        
        # 純文字輸入
        else:
            # 如果有對話歷史，需要使用結構化格式
            if dialogue_history:
                contents = await _build_conversation_contents(inst, dialogue_history, image_input, audio_input, video_input)
            else:
                contents.append(inst)
        
        # 建構生成配置
        config = GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[google_search_tool],
            response_modalities=["TEXT"],
        )

        response_stream = client.models.generate_content_stream(
            model=model_id,
            contents=contents,
            config=config
        )
        
        async def async_generator():
            try:
                # 使用正確的同步迭代方式處理 Gemini 回應流
                accumulated_text = ""
                chunk_count = 0
                
                try:
                    for chunk in response_stream:
                        chunk_count += 1
                        if chunk and hasattr(chunk, 'text') and chunk.text:
                            chunk_text = chunk.text.strip()
                            if chunk_text:
                                accumulated_text += chunk_text
                                yield chunk_text
                                await asyncio.sleep(0.01)  # 小幅延遲避免過快輸出
                        elif chunk is None:
                            break
                except StopIteration:
                    # 正常迭代結束
                    pass
                except Exception as stream_error:
                    error_message = str(stream_error)
                    
                    # 檢查特定錯誤類型
                    if "Response not read" in error_message or "400 Bad Request" in error_message:
                        # 嘗試獲取已累積的文字作為降級方案
                        if accumulated_text:
                            yield accumulated_text
                            return
                        else:
                            # 如果沒有累積文字，嘗試非流式呼叫
                            try:
                                # 重新建立配置進行非流式調用
                                from google.genai.types import GenerateContentConfig
                                fallback_config = GenerateContentConfig(
                                    system_instruction=system_prompt,
                                    tools=[google_search_tool],
                                    response_modalities=["TEXT"],
                                )
                                
                                fallback_response = client.models.generate_content(
                                    model=model_id,
                                    contents=contents,
                                    config=fallback_config,
                                    stream=False  # 非流式
                                )
                                
                                if fallback_response and fallback_response.text:
                                    yield fallback_response.text
                                    return
                                else:
                                    raise GeminiError(f"Gemini API 流式和非流式回應都失敗: {error_message}")
                                    
                            except Exception as fallback_error:
                                raise GeminiError(f"Gemini API 降級處理失敗: {fallback_error}")
                    
                    elif "RESOURCE_PROJECT_INVALID" in error_message:
                        raise GeminiError(f"Gemini API 項目設定錯誤: {error_message}")
                    elif "PERMISSION_DENIED" in error_message:
                        raise GeminiError(f"Gemini API 權限錯誤: {error_message}")
                    elif "QUOTA_EXCEEDED" in error_message:
                        raise GeminiError(f"Gemini API 配額超限: {error_message}")
                    else:
                        # 對於其他錯誤，如果有累積文字就返回
                        if accumulated_text:
                            yield accumulated_text
                            return
                        else:
                            raise GeminiError(f"Gemini API 錯誤: {error_message}")
                
                # 確保至少有一些輸出
                if not accumulated_text:
                    raise GeminiError("Gemini API 沒有生成任何回應內容")
                    
            except Exception as e:
                if isinstance(e, GeminiError):
                    raise
                raise GeminiError(f"Gemini API 生成過程錯誤: {str(e)}")

        # 返回異步生成器
        return None, async_generator()
    except Exception as e:
        raise GeminiError(f"Gemini API 初始化錯誤: {str(e)}")
