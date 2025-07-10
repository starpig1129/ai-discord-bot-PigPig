from addons.settings import TOKENS
from anthropic import AsyncAnthropic, HUMAN_PROMPT, AI_PROMPT
import asyncio
import numpy as np
from PIL import Image
import base64
from io import BytesIO
import math
import numpy as np
from PIL import Image
from moviepy.editor import VideoFileClip
from addons.settings import TOKENS
class ClaudeError(Exception):
    pass
tokens = TOKENS()
def extract_video_frames(video_path, num_frames=5):
    """從視頻中提取關鍵幀。
    
    Args:
        video_path: 視頻文件路徑。
        num_frames: 要提取的幀數量。
        
    Returns:
        list: 包含 base64 編碼的圖像列表。
    """
    video = VideoFileClip(video_path)
    duration = video.duration
    frame_times = np.linspace(0, duration, num_frames + 2)[1:-1]  # 去除開頭和結尾
    
    frames = []
    for t in frame_times:
        frame = video.get_frame(t)
        image = Image.fromarray(frame.astype(np.uint8))
        
        # 將圖像轉換為 base64
        buffered = BytesIO()
        image.save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        frames.append(img_str)
    
    video.close()
    return frames

async def generate_response(inst, system_prompt, dialogue_history=None, image_input=None, audio_input=None, video_input=None):
    messages = []

    if dialogue_history:
        for msg in dialogue_history:
            role = HUMAN_PROMPT if msg["role"] == "user" else AI_PROMPT
            messages.append(f"{role} {msg['content']}")
    
    messages.append(f"{HUMAN_PROMPT}{system_prompt}{inst}")
    if video_input:
        # 從視頻中提取關鍵幀
        frames = extract_video_frames(video_input)
        for i, frame in enumerate(frames, 1):
            messages.append(f"Frame {i} from video: <image>{frame}</image>")
    elif audio_input:
        messages.append(f"Audio input is not supported by Claude API")
    elif image_input:
        messages.append(f"Image: {image_input}")
    full_prompt = "\n\n".join(messages)

    async def run_generation():
        try:
            async with AsyncAnthropic(api_key=tokens.anthropic_api_key) as client:
                response_stream = await client.completions.create(
                    model="claude-3-5-sonnet-20240620",
                    prompt=full_prompt,
                    max_tokens_to_sample=1000,
                    stream=True
                )

                async for completion in response_stream:
                    if completion.stop_reason:
                        break
                    if completion.completion:
                        yield completion.completion
                        await asyncio.sleep(0)
        except Exception as e:
            error_message = str(e)
            if "invalid_api_key" in error_message.lower():
                raise ClaudeError(f"Claude API 金鑰無效: {error_message}")
            elif "rate_limit" in error_message.lower():
                raise ClaudeError(f"Claude API 請求頻率超限: {error_message}")
            elif "quota_exceeded" in error_message.lower():
                raise ClaudeError(f"Claude API 配額超限: {error_message}")
            elif "model_not_found" in error_message.lower():
                raise ClaudeError(f"Claude API 模型不可用: {error_message}")
            else:
                raise ClaudeError(f"Claude API 錯誤: {error_message}")

    try:
        # 不需要創建空的線程，因為 Claude API 已經是異步的
        return None, run_generation()
    except Exception as e:
        raise ClaudeError(f"Claude API 初始化錯誤: {str(e)}")
