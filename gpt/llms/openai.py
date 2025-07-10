from addons.settings import TOKENS
from openai import OpenAI
import asyncio
import tiktoken
import numpy as np
from PIL import Image
from moviepy.editor import VideoFileClip

class OpenAIError(Exception):
    pass

# Initialize OpenAI client
tokens = TOKENS()

# Initialize tokenizer
tokenizer = tiktoken.encoding_for_model("gpt-4o-mini")

def num_tokens_from_messages(messages, model="gpt-4o-mini"):
    """Calculate the number of tokens in a list of messages"""
    num_tokens = 0
    for message in messages:
        num_tokens += 4  # Start and end tokens for each message
        for key, value in message.items():
            num_tokens += len(tokenizer.encode(value))
            if key == "name":
                num_tokens += -1  # Token calculation differs for names
    num_tokens += 2  # Start and end tokens for the conversation
    return num_tokens


def extract_video_frames(video_path, num_frames=5):
    """從視頻中提取關鍵幀。
    
    Args:
        video_path: 視頻文件路徑。
        num_frames: 要提取的幀數量。
        
    Returns:
        list: 關鍵幀描述列表。
    """
    video = VideoFileClip(video_path)
    duration = video.duration
    frame_times = np.linspace(0, duration, num_frames + 2)[1:-1]  # 去除開頭和結尾
    
    frames = []
    for t in frame_times:
        frame = video.get_frame(t)
        image = Image.fromarray(frame.astype(np.uint8))
        frames.append(f"Frame at {t:.1f}s: A video frame showing {image.size[0]}x{image.size[1]} pixels")
    
    video.close()
    return frames

async def generate_response(inst, system_prompt, dialogue_history=None, image_input=None, audio_input=None, video_input=None):

    try:
        messages = [{'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': inst}]
        if dialogue_history is not None:
            messages = [{'role': 'system', 'content': system_prompt}] + dialogue_history + [{'role': 'user', 'content': inst}]

        if video_input:
            # 從視頻中提取關鍵幀並添加描述
            frames = extract_video_frames(video_input)
            frame_descriptions = "\n".join(frames)
            messages.append({'role': 'user', 'content': f"Video analysis:\n{frame_descriptions}"})
        elif audio_input:
            messages.append({'role': 'user', 'content': f"Audio input is not supported by OpenAI API"})
        elif image_input:
            # 處理圖片輸入 - 使用 OpenAI Vision API 格式
            if isinstance(image_input, list):
                # 處理多張圖片
                content = [{"type": "text", "text": inst}]
                for img in image_input:
                    from gpt.utils.media import image_to_base64
                    img_base64 = image_to_base64(img)
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{img_base64}"
                        }
                    })
                messages[-1] = {'role': 'user', 'content': content}
            else:
                # 處理單張圖片
                from gpt.utils.media import image_to_base64
                img_base64 = image_to_base64(image_input)
                messages[-1] = {
                    'role': 'user',
                    'content': [
                        {"type": "text", "text": inst},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{img_base64}"
                            }
                        }
                    ]
                }
    except Exception as e:
        raise OpenAIError(f"OpenAI API 影像處理錯誤: {str(e)}")

    while num_tokens_from_messages(messages) > 127000:
        if len(messages) <= 2:
            raise ValueError("Message is too long even after trimming history")
        messages.pop(1)

    async def run_generation():
        try:
            client = OpenAI(api_key=tokens.openai_api_key)
            # 檢查是否有圖片輸入，決定使用的模型
            model_name = "gpt-4o" if image_input else "gpt-4o-mini"
            
            stream = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    max_tokens=4096,
                    temperature=0.5,
                    top_p=0.9,
                    stream=True
                )
            )

            async for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content
                    await asyncio.sleep(0)
        except Exception as e:
            error_message = str(e)
            if "invalid_api_key" in error_message.lower():
                raise OpenAIError(f"OpenAI API 金鑰無效: {error_message}")
            elif "rate_limit" in error_message.lower():
                raise OpenAIError(f"OpenAI API 請求頻率超限: {error_message}")
            elif "insufficient_quota" in error_message.lower():
                raise OpenAIError(f"OpenAI API 配額不足: {error_message}")
            else:
                raise OpenAIError(f"OpenAI API 錯誤: {error_message}")

    # 不需要創建空的線程，因為 OpenAI 的流式處理已經是異步的
    return None, run_generation()
