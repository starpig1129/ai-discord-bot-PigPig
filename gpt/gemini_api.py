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

async def generate_response(inst, system_prompt, dialogue_history=None, image_input=None, audio_input=None, video_input=None):
    full_prompt = f"{system_prompt}\n{inst}"

    if dialogue_history:
        history_content = "\n".join([f"{msg['role']}: {msg['content']}" for msg in dialogue_history])
        full_prompt = f"{system_prompt}\n{history_content}\nUser: {inst}"

    try:
        content_parts = []
        if video_input:
            # 從視頻中提取關鍵幀並分析
            frames = extract_video_frames(video_input)
            frame_descriptions = []
            
            for i, frame in enumerate(frames, 1):
                frame_prompt = f"Analyzing frame {i} from video"
                response = client.models.generate_content([frame_prompt, frame], stream=False)
                if response.text:
                    frame_descriptions.append(f"Frame {i}: {response.text}")
            
            # 將所有幀的描述添加到提示中
            full_prompt += "\nVideo frame analysis:\n" + "\n".join(frame_descriptions)
        elif audio_input:
            full_prompt += f"\nAudio input is not supported by Gemini API"
        elif image_input:
            if isinstance(image_input, list):
                # 處理多個圖片輸入
                
                for i, img in enumerate(image_input, 1):
                    content_parts.append({
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": image_to_base64(img)
                        }
                    })
    except Exception as e:
        raise GeminiError(f"Gemini API 影像處理錯誤: {str(e)}")
    try:
        content_parts.append(full_prompt)

        response_stream = client.models.generate_content_stream(
        model=model_id,
        contents=content_parts,
        config=GenerateContentConfig(
            tools=[google_search_tool],
            response_modalities=["TEXT"],
            )
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

        # 不需要創建空的線程，因為已經使用異步生成器
        return None, async_generator()
    except Exception as e:
        raise GeminiError(f"Gemini API 初始化錯誤: {str(e)}")
