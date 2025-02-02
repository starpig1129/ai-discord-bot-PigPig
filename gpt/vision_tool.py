import io
import logging
from PIL import Image
from pdf2image import convert_from_bytes
from decord import VideoReader, cpu
import aiohttp
import base64
MAX_NUM_FRAMES = 16  # if cuda OOM set a smaller number
TARGET_IMAGE_SIZE = (224, 224)  # 設置目標圖像大小

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def standardize_image(image, target_size=TARGET_IMAGE_SIZE):
    return image.resize(target_size)

def is_valid_image(img, expected_size=TARGET_IMAGE_SIZE):
    return img.size == expected_size
def image_to_base64(pil_image):
    # 建立一個BytesIO物件
    buffered = io.BytesIO()
    
    # 將PIL Image存成PNG格式到BytesIO
    pil_image.save(buffered, format="JPEG")
    
    # 取得bytes
    img_bytes = buffered.getvalue()
    
    # 轉換成base64字串
    img_base64 = base64.b64encode(img_bytes).decode('utf-8')
    
    return img_base64

async def encode_video(video_data):
    def uniform_sample(l, n):
        gap = len(l) / n
        idxs = [int(i * gap + gap / 2) for i in range(n)]
        return [l[i] for i in idxs]

    try:
        with io.BytesIO(video_data) as video_file:
            vr = VideoReader(video_file, ctx=cpu(0))
            sample_fps = round(vr.get_avg_fps() / 1)  # FPS
            frame_idx = [i for i in range(0, len(vr), sample_fps)]
            if len(frame_idx) > MAX_NUM_FRAMES:
                frame_idx = uniform_sample(frame_idx, MAX_NUM_FRAMES)
            frames = vr.get_batch(frame_idx).asnumpy()
            frames = [standardize_image(Image.fromarray(v.astype('uint8'))) for v in frames]
        logger.info(f'Extracted and standardized {len(frames)} frames from video')
        return frames
    except Exception as e:
        logger.error(f"Error in video encoding: {str(e)}")
        return []

def safe_process_pdf(file_data):
    try:
        pdf_images = convert_from_bytes(file_data)
        return [standardize_image(img) for img in pdf_images]
    except Exception as e:
        logger.warning(f"Error processing PDF page: {str(e)}")
        return []

async def process_attachment_data(message):
    try:
        
        all_image_data = []
        processed_files = []  # 用於記錄處理的文件

        supported_image_formats = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp')
        supported_video_formats = ('.mp4', '.avi', '.mov', '.webm', '.mkv', '.flv', '.wmv', '.m4v')

        async with aiohttp.ClientSession() as session:
            for attachment in message.attachments:
                try:
                    async with session.get(attachment.url) as response:
                        file_data = await response.read()

                    if attachment.filename.lower().endswith(supported_image_formats):
                        image = Image.open(io.BytesIO(file_data)).convert('RGB')
                        standardized_image = standardize_image(image)
                        if is_valid_image(standardized_image):
                            all_image_data.append(standardized_image)
                            processed_files.append(f"圖片: {attachment.filename}")
                            logger.info(f"Processed image: {attachment.filename}")
                        else:
                            logger.warning(f"Invalid image size after standardization: {attachment.filename}")

                    elif attachment.filename.lower().endswith('.pdf'):
                        pdf_images = safe_process_pdf(file_data)
                        valid_pdf_images = [img for img in pdf_images if is_valid_image(img)]
                        all_image_data.extend(valid_pdf_images)
                        processed_files.append(f"PDF: {attachment.filename} (處理了 {len(valid_pdf_images)} 頁)")
                        logger.info(f"Processed PDF: {attachment.filename}, extracted {len(valid_pdf_images)} valid pages")

                    elif attachment.filename.lower().endswith(supported_video_formats):
                        video_frames = await encode_video(file_data)
                        valid_video_frames = [frame for frame in video_frames if is_valid_image(frame)]
                        all_image_data.extend(valid_video_frames)
                        processed_files.append(f"影片: {attachment.filename} (處理了 {len(valid_video_frames)} 幀)")
                        logger.info(f"Processed video: {attachment.filename}, extracted {len(valid_video_frames)} valid frames")

                    else:
                        logger.warning(f"Unsupported file format: {attachment.filename}")

                except Exception as e:
                    logger.error(f"Error processing {attachment.filename}: {str(e)}")

        if not all_image_data:
            return "沒有找到可處理的圖像、影片或PDF附件，或處理過程中出現錯誤。"

        else:
            return all_image_data

    except Exception as e:
        logger.error(f"Error in VQA processing: {str(e)}")
        return f"處理過程中出現錯誤: {str(e)}"