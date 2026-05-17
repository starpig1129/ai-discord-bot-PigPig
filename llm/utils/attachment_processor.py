# llm/utils/attachment_processor.py
"""Convert Discord Attachments to LangChain content_parts (base64 data URIs).

Supported types:
- image/* — resized and encoded as JPEG base64 image_url parts
- application/pdf — rendered page-by-page via pdf2image
- video/* — key-frame sampled via decord

Unsupported types and processing failures each return a single ``text`` part
so the calling agent always receives well-formed content.
"""
from __future__ import annotations

import asyncio
import base64
import io
from typing import TYPE_CHECKING

import aiohttp
from PIL import Image

from addons.settings import attachment_config
from addons.logging import get_logger

if TYPE_CHECKING:
    import discord

log = get_logger(source=__name__, server_id="system")

_DOWNLOAD_TIMEOUT = aiohttp.ClientTimeout(total=15.0)


async def _download(url: str) -> bytes:
    """Download a URL and return the raw bytes.

    Args:
        url: HTTP/HTTPS URL to fetch.

    Returns:
        Raw response bytes.

    Raises:
        aiohttp.ClientResponseError: If the server returns a non-2xx status.
        aiohttp.ClientError: On network-level failures.
    """
    async with aiohttp.ClientSession(timeout=_DOWNLOAD_TIMEOUT) as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            return await resp.read()


def _pil_to_content_part(img: Image.Image) -> dict:
    """Encode a PIL Image as a LangChain ``image_url`` content part (JPEG base64).

    Args:
        img: PIL Image object in RGB mode.

    Returns:
        Dict with ``type`` == ``"image_url"`` and a ``data:image/jpeg;base64,…`` URL.
    """
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}


def _resize_if_needed(img: Image.Image, max_dim: int) -> Image.Image:
    """Proportionally resize *img* so its longest side does not exceed *max_dim*.

    Args:
        img: Source PIL Image.
        max_dim: Maximum allowed value for ``max(width, height)``.

    Returns:
        The original image if already within limits, otherwise a resized copy.
    """
    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    return img


async def _process_image(data: bytes) -> list[dict]:
    """Decode raw image bytes, optionally resize, and encode as a content part.

    Args:
        data: Raw image file bytes.

    Returns:
        A single-element list containing an ``image_url`` content part.
    """
    cfg = attachment_config.image
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img = _resize_if_needed(img, cfg.max_dimension)
    return [_pil_to_content_part(img)]


async def _process_pdf(data: bytes, filename: str) -> list[dict]:
    """Render PDF pages to images and encode each as a content part.

    Page count drives DPI selection:
    - <= threshold_full  → dpi_full
    - <= threshold_medium → dpi_medium
    - else               → dpi_compressed

    If total pages exceed ``max_pages``, the first and last ``max_pages // 2``
    pages are sampled and a truncation notice is prepended.

    Args:
        data: Raw PDF file bytes.
        filename: Original filename (used in log context).

    Returns:
        List of content parts — optionally a leading ``text`` truncation notice
        followed by one ``image_url`` part per selected page.
    """
    from pdf2image import convert_from_bytes, pdfinfo_from_bytes

    cfg = attachment_config.pdf

    try:
        info = pdfinfo_from_bytes(data)
        total_pages: int = int(info.get("Pages", 0))
    except Exception:
        preview = convert_from_bytes(data, dpi=72, fmt="jpeg")
        total_pages = len(preview)

    if total_pages <= cfg.threshold_full:
        dpi = cfg.dpi_full
    elif total_pages <= cfg.threshold_medium:
        dpi = cfg.dpi_medium
    else:
        dpi = cfg.dpi_compressed

    max_p = cfg.max_pages
    if total_pages <= max_p:
        selected_indices = list(range(total_pages))
        truncated = False
    else:
        half = max_p // 2
        front = list(range(half))
        back = list(range(total_pages - half, total_pages))
        selected_indices = front + back
        truncated = True

    pages = convert_from_bytes(data, dpi=dpi, fmt="jpeg")

    parts: list[dict] = []

    if truncated and cfg.notify_truncated:
        half = max_p // 2
        parts.append({
            "type": "text",
            "text": (
                f"[System: PDF truncated — showing {len(selected_indices)} of {total_pages} pages "
                f"(pages 1-{half} and {total_pages - half + 1}-{total_pages})]"
            ),
        })

    for i in selected_indices:
        if i < len(pages):
            parts.append(_pil_to_content_part(pages[i].convert("RGB")))

    return parts


async def _process_video(data: bytes, filename: str) -> list[dict]:
    """Sample key frames from a video and encode each as a content part.

    Frames are sampled at least ``min_interval_sec`` seconds apart.  If the
    resulting candidate count exceeds ``max_frames`` the candidates are
    uniformly subsampled.

    Args:
        data: Raw video file bytes.
        filename: Original filename (used in log context).

    Returns:
        List of ``image_url`` content parts, one per sampled frame.
    """
    from decord import VideoReader, cpu

    cfg = attachment_config.video

    with io.BytesIO(data) as f:
        vr = VideoReader(f, ctx=cpu(0))
        total_frames = len(vr)
        fps = vr.get_avg_fps() or 1.0

        min_frame_gap = max(1, int(cfg.min_interval_sec * fps))
        candidates = list(range(0, total_frames, min_frame_gap))

        if len(candidates) > cfg.max_frames:
            step = len(candidates) / cfg.max_frames
            indices = [candidates[int(i * step)] for i in range(cfg.max_frames)]
        else:
            indices = candidates

        frames = vr.get_batch(indices).asnumpy()

    parts = []
    for frame in frames:
        img = Image.fromarray(frame.astype("uint8")).convert("RGB")
        parts.append(_pil_to_content_part(img))
    return parts


async def process_attachment(attachment: "discord.Attachment") -> list[dict]:
    """Convert a Discord Attachment to a list of LangChain content_parts.

    Dispatches to type-specific processors based on ``attachment.content_type``.
    Returns an empty list if attachment processing is globally disabled.
    Returns a ``text`` fallback part for unsupported MIME types or on any
    processing failure so the caller always receives well-formed content.

    Args:
        attachment: A ``discord.Attachment`` (or compatible mock) with
            ``content_type``, ``filename``, and ``url`` attributes.

    Returns:
        List of dicts, each a LangChain content_part with ``"type"`` either
        ``"image_url"`` or ``"text"``.  Empty list when globally disabled.
    """
    if not attachment_config.enabled:
        return []

    content_type = attachment.content_type or ""
    filename = attachment.filename

    try:
        if content_type.startswith("image/") and attachment_config.image.enabled:
            data = await _download(attachment.url)
            return await _process_image(data)

        if content_type == "application/pdf" and attachment_config.pdf.enabled:
            data = await _download(attachment.url)
            return await _process_pdf(data, filename)

        if content_type.startswith("video/") and attachment_config.video.enabled:
            data = await _download(attachment.url)
            return await _process_video(data, filename)

        return [{"type": "text", "text": f"[Attachment: {filename} (unsupported type: {content_type})]"}]

    except Exception as e:
        try:
            from function import func
            asyncio.create_task(func.report_error(e, f"process_attachment failed for {filename}"))
        except Exception:
            pass
        log.warning(f"Attachment processing failed for {filename}: {e}")
        return [{"type": "text", "text": f"[Attachment processing failed: {filename}]"}]
