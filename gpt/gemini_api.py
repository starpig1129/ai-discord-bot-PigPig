from google import genai
from google.genai.types import Tool, GenerateContentConfig, GoogleSearch
import asyncio
from addons.settings import TOKENS
import numpy as np
from PIL import Image
from moviepy.editor import VideoFileClip
from gpt.vision_tool import image_to_base64

# Initialize the Gemini model
tokens = TOKENS()
client = genai.Client(api_key=tokens.gemini_api_key)
model_id = "gemini-2.0-flash"

google_search_tool = Tool(
    google_search = GoogleSearch()
)

class GeminiError(Exception):
    pass

def extract_video_frames(video_path, num_frames=5):
    """從視頻中提取關鍵幀。
    
    Args:
        video_path: 視頻文件路徑。
        num_frames: 要提取的幀數量。
        
    Returns:
        list: PIL Image 對象列表。
    """
    video = VideoFileClip(video_path)
    duration = video.duration
    frame_times = np.linspace(0, duration, num_frames + 2)[1:-1]  # 去除開頭和結尾
    
    frames = []
    for t in frame_times:
        frame = video.get_frame(t)
        image = Image.fromarray(frame.astype(np.uint8))
        frames.append(image)
    
    video.close()
    return frames

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
    
    # 處理多媒體輸入
    if video_input:
        # 從視頻中提取關鍵幀並分析
        try:
            frames = extract_video_frames(video_input)
            frame_descriptions = []
            
            for i, frame in enumerate(frames, 1):
                frame_prompt = f"分析視頻第 {i} 幀"
                # 對每個幀進行單獨分析
                frame_response = client.models.generate_content(
                    model=model_id,
                    contents=[{
                        "role": "user", 
                        "parts": [
                            {"text": frame_prompt},
                            {
                                "inlineData": {
                                    "mimeType": "image/jpeg",
                                    "data": image_to_base64(frame)
                                }
                            }
                        ]
                    }],
                    stream=False
                )
                if frame_response.text:
                    frame_descriptions.append(f"第 {i} 幀: {frame_response.text}")
            
            # 將視頻分析結果添加到文字內容中
            video_analysis = "視頻幀分析結果:\n" + "\n".join(frame_descriptions)
            current_parts.append({"text": f"{inst}\n\n{video_analysis}"})
            
        except Exception as e:
            raise GeminiError(f"視頻處理錯誤: {str(e)}")
            
    elif audio_input:
        # 音頻輸入目前不支援，添加說明
        current_parts.append({"text": f"{inst}\n\n注意: Gemini API 目前不支援音頻輸入"})
        
    elif image_input:
        # 處理圖片輸入
        current_parts.append({"text": inst})
        
        if isinstance(image_input, list):
            # 處理多張圖片
            for img in image_input:
                current_parts.append({
                    "inlineData": {
                        "mimeType": "image/jpeg",
                        "data": image_to_base64(img)
                    }
                })
        else:
            # 處理單張圖片
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
    2. 採用官方推薦的結構化對話格式 (role + parts)
    3. 正確組織多媒體內容結構
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
        # 建構結構化內容格式
        contents = await _build_conversation_contents(inst, dialogue_history, image_input, audio_input, video_input)
        
        # 建構生成配置，使用官方推薦的 system_instruction 參數
        config = GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[google_search_tool],
            response_modalities=["TEXT"],
        )

        response_stream = client.models.generate_content_stream(
            model=model_id,
            contents=contents,  # 使用結構化的對話內容
            config=config
        )
        
        async def async_generator():
            try:
                # 使用事件循環來處理同步迭代器
                loop = asyncio.get_event_loop()
                iterator = response_stream
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

        # 返回異步生成器
        return None, async_generator()
    except Exception as e:
        raise GeminiError(f"Gemini API 初始化錯誤: {str(e)}")
