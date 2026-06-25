# File: `llm/utils/attachment_processor.py`

## Overview
Convert Discord Attachments to LangChain content_parts (base64 data URIs).

Supported types:
- image/* — resized and encoded as JPEG base64 image_url parts
- application/pdf — rendered page-by-page via pdf2image
- video/* — key-frame sampled via decord

Unsupported types and processing failures each return a single ``text`` part
so the calling agent always receives well-formed content.

## Classes

No classes defined in this file.

## Functions

### `_pil_to_content_part(img) -> dict`
Encode a PIL Image as a LangChain ``image_url`` content part (JPEG base64).

### `_resize_if_needed(img, max_dim) -> Image.Image`
Proportionally resize *img* so its longest side does not exceed *max_dim*.

### `_decode_image(data, max_dimension) -> Image.Image`
Synchronously decode and resize an image; intended for thread-pool execution.

### `_render_pdf(data, cfg) -> tuple[list, bool, list[int], int, int]`
Synchronously render PDF pages to PIL Images; intended for thread-pool execution.

### `_decode_video(data, cfg) -> list[Image.Image]`
Synchronously decode video key frames; intended for thread-pool execution.
