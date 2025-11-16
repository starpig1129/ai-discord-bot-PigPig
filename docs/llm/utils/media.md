# Media Processing Utilities

## Overview

The `media.py` module provides comprehensive media processing utilities for the LLM system. It handles image standardization, video frame extraction, PDF processing, and attachment processing for various media formats.

## Constants

### `MAX_NUM_FRAMES = 16`

**Description:**
Maximum number of frames to extract from videos (can be reduced if CUDA OOM occurs).

### `TARGET_IMAGE_SIZE = (224, 224)`

**Description:**
Target size for standardized images after processing.

## Core Functions

### `standardize_image(image, target_size=TARGET_IMAGE_SIZE)`

**Parameters:**
- `image`: PIL Image object to standardize
- `target_size`: Target dimensions tuple (width, height)

**Returns:**
- `PIL.Image`: Resized image to target dimensions

**Description:**
Resizes an image to the specified target dimensions for consistent processing.

### `is_valid_image(img, expected_size=TARGET_IMAGE_SIZE)`

**Parameters:**
- `img`: PIL Image object to validate
- `expected_size`: Expected dimensions tuple

**Returns:**
- `bool`: True if image matches expected size

**Description:**
Validates that an image meets the expected dimensions after standardization.

### `image_to_base64(pil_image)`

**Parameters:**
- `pil_image`: PIL Image object to convert

**Returns:**
- `str`: Base64-encoded image string (JPEG format)

**Description:**
Converts a PIL Image to base64-encoded JPEG string for transmission or storage.

**Process:**
1. **BytesIO Buffer**: Creates in-memory buffer
2. **JPEG Conversion**: Saves image as JPEG format
3. **Base64 Encoding**: Encodes bytes to UTF-8 string

## Video Processing

### `async def encode_video(video_data)`

**Parameters:**
- `video_data`: Raw video file data as bytes

**Returns:**
- `List[PIL.Image]`: List of extracted and standardized frames

**Description:**
Extracts frames from video data and standardizes them for processing.

**Frame Extraction Process:**
1. **Video Reading**: Uses decord.VideoReader for efficient video processing
2. **FPS Calculation**: Calculates frames per second for uniform sampling
3. **Frame Selection**: Samples frames at regular intervals
4. **Frame Limiting**: Respects MAX_NUM_FRAMES limit
5. **Standardization**: Converts frames to standardized images

**Sampling Algorithm:**
```python
def uniform_sample(l, n):
    gap = len(l) / n
    idxs = [int(i * gap + gap / 2) for i in range(n)]
    return [l[i] for i in idxs]
```

**Video Formats Supported:**
- `.mp4`, `.avi`, `.mov`, `.webm`, `.mkv`, `.flv`, `.wmv`, `.m4v`

## PDF Processing

### `safe_process_pdf(file_data)`

**Parameters:**
- `file_data`: Raw PDF file data as bytes

**Returns:**
- `List[PIL.Image]`: List of standardized page images

**Description:**
Safely converts PDF pages to standardized images using pdf2image.

**Processing Pipeline:**
1. **PDF Conversion**: Uses pdf2image to convert pages to images
2. **Standardization**: Resizes all pages to target dimensions
3. **Error Handling**: Returns empty list on conversion failures

## Attachment Processing

### `async def process_attachment_data(message)`

**Parameters:**
- `message`: Discord message object containing attachments

**Returns:**
- `List[PIL.Image]` or `str`: List of processed images or error message

**Description:**
Processes all attachments in a Discord message and extracts valid images/frames.

**Supported Formats:**

**Images:**
- `.png`, `.jpg`, `.jpeg`, `.gif`, `.bmp`, `.tiff`, `.webp`

**Videos:**
- `.mp4`, `.avi`, `.mov`, `.webm`, `.mkv`, `.flv`, `.wmv`, `.m4v`

**Documents:**
- `.pdf` (converted to images)

**Processing Workflow:**

1. **HTTP Session**: Uses aiohttp for async file downloads
2. **Format Detection**: Identifies file type by extension
3. **Image Processing**: Direct standardization for image files
4. **PDF Conversion**: Converts PDF pages to images
5. **Video Processing**: Extracts frames from video files
6. **Validation**: Ensures all processed images meet size requirements

**Error Handling:**
- **Download Failures**: Reported via `func.report_error()`
- **Format Errors**: Unsupported formats are logged and skipped
- **Processing Errors**: Individual file failures don't stop other files
- **Size Validation**: Invalid images after standardization are filtered

**Return Information:**
```python
# Success case
return all_image_data

# Error case  
return "沒有找到可處理的圖像、影片或PDF附件，或處理過程中出現錯誤。"
```

**Processed File Tracking:**
```python
processed_files = []  # Records processing summary
processed_files.append(f"圖片: {attachment.filename}")
processed_files.append(f"PDF: {attachment.filename} (處理了 {len(valid_pdf_images)} 頁)")
processed_files.append(f"影片: {attachment.filename} (處理了 {len(valid_video_frames)} 幀)")
```

## Logging Configuration

### `logging.basicConfig(level=logging.INFO)`

**Description:**
Sets up basic logging configuration for media processing operations.

**Log Levels:**
- **INFO**: Successful processing operations
- **WARNING**: Invalid images, unsupported formats
- **ERROR**: Processing failures (reported via func.report_error)

## Integration

The media utilities are used by:
- **LLM tools** for multimodal processing
- **Image generation tools** for base64 conversion
- **Video analysis tools** for frame extraction
- **Document processing tools** for PDF handling

## Dependencies

- `io`: For in-memory buffer operations
- `logging`: For operation monitoring
- `PIL`: For image processing and manipulation
- `pdf2image`: For PDF to image conversion
- `decord`: For video frame extraction
- `aiohttp`: For async HTTP operations
- `base64`: For image encoding
- `asyncio`: For async operations
- `function.func`: For error reporting

## Performance Considerations

**Memory Management:**
- **BytesIO**: Efficient in-memory buffer usage
- **Frame Limiting**: Prevents memory exhaustion from long videos
- **Validation**: Filters invalid images early

**Async Processing:**
- **aiohttp**: Non-blocking HTTP requests
- **Concurrent Processing**: Multiple attachments processed efficiently
- **Error Isolation**: Individual failures don't stop processing

**Format Optimization:**
- **JPEG Conversion**: Efficient image compression
- **Frame Sampling**: Intelligent video frame selection
- **Size Standardization**: Consistent processing dimensions

## Usage Examples

**Basic Image Processing:**
```python
from PIL import Image
from llm.utils.media import standardize_image, image_to_base64

# Load and standardize image
image = Image.open("photo.jpg")
standardized = standardize_image(image)

# Convert to base64
base64_image = image_to_base64(standardized)
```

**Video Frame Extraction:**
```python
import asyncio
from llm.utils.media import encode_video

async def extract_frames():
    with open("video.mp4", "rb") as f:
        video_data = f.read()
    
    frames = await encode_video(video_data)
    print(f"Extracted {len(frames)} frames")
    return frames

# Run extraction
frames = asyncio.run(extract_frames())
```

**PDF Processing:**
```python
from llm.utils.media import safe_process_pdf

with open("document.pdf", "rb") as f:
    pdf_data = f.read()

pages = safe_process_pdf(pdf_data)
print(f"Converted {len(pages)} PDF pages")
```

**Attachment Processing:**
```python
import asyncio
from llm.utils.media import process_attachment_data

async def process_message_attachments(message):
    result = await process_attachment_data(message)
    if isinstance(result, list):
        print(f"Processed {len(result)} images/videos")
        return result
    else:
        print(f"Error: {result}")
        return []

# Process Discord message attachments
processed_media = asyncio.run(process_message_attachments(message))