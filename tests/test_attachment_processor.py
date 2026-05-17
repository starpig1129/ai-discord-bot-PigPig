# tests/test_attachment_processor.py
import asyncio
import base64
import io
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from PIL import Image


def _make_jpeg_pil() -> Image.Image:
    return Image.new("RGB", (100, 80), color=(0, 255, 0))


def _make_attachment(content_type: str, filename: str, url: str = "https://example.com/file"):
    att = MagicMock()
    att.content_type = content_type
    att.filename = filename
    att.url = url
    return att


def _fake_jpeg_bytes() -> bytes:
    from PIL import Image
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_process_image_returns_image_url():
    from llm.utils.attachment_processor import process_attachment
    att = _make_attachment("image/jpeg", "photo.jpg")

    with patch("llm.utils.attachment_processor._download", new=AsyncMock(return_value=_fake_jpeg_bytes())):
        parts = await process_attachment(att)

    assert len(parts) == 1
    assert parts[0]["type"] == "image_url"
    assert parts[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")


@pytest.mark.asyncio
async def test_process_unsupported_returns_text():
    from llm.utils.attachment_processor import process_attachment
    att = _make_attachment("audio/mpeg", "song.mp3")

    parts = await process_attachment(att)

    assert len(parts) == 1
    assert parts[0]["type"] == "text"
    assert "song.mp3" in parts[0]["text"]
    assert "unsupported" in parts[0]["text"]


@pytest.mark.asyncio
async def test_process_download_failure_returns_error_text():
    from llm.utils.attachment_processor import process_attachment
    att = _make_attachment("image/png", "broken.png")

    with patch("llm.utils.attachment_processor._download", new=AsyncMock(side_effect=Exception("network error"))):
        parts = await process_attachment(att)

    assert len(parts) == 1
    assert parts[0]["type"] == "text"
    assert "broken.png" in parts[0]["text"]
    assert "failed" in parts[0]["text"].lower()


@pytest.mark.asyncio
async def test_image_resized_when_over_max_dimension():
    from llm.utils.attachment_processor import _resize_if_needed
    from PIL import Image
    large = Image.new("RGB", (4096, 2048))
    result = _resize_if_needed(large, max_dim=2048)
    assert max(result.size) == 2048


def test_resize_not_applied_when_under_limit():
    from llm.utils.attachment_processor import _resize_if_needed
    from PIL import Image
    small = Image.new("RGB", (800, 600))
    result = _resize_if_needed(small, max_dim=2048)
    assert result.size == (800, 600)


@pytest.mark.asyncio
async def test_disabled_config_returns_empty():
    from llm.utils import attachment_processor
    att = _make_attachment("image/jpeg", "photo.jpg")

    mock_cfg = MagicMock()
    mock_cfg.enabled = False
    with patch("llm.utils.attachment_processor.attachment_config", mock_cfg):
        parts = await attachment_processor.process_attachment(att)
    assert parts == []


# --- _process_pdf tests ---


@pytest.mark.asyncio
async def test_process_pdf_normal_path():
    """_process_pdf 正常路徑：3 頁 PDF → 3 個 image_url parts"""
    from llm.utils.attachment_processor import _process_pdf

    mock_pages = [_make_jpeg_pil(), _make_jpeg_pil(), _make_jpeg_pil()]

    mock_pdf2image = MagicMock()
    mock_pdf2image.pdfinfo_from_bytes.return_value = {"Pages": 3}
    mock_pdf2image.convert_from_bytes.return_value = mock_pages

    mock_cfg_obj = MagicMock()
    mock_cfg_obj.pdf.threshold_full = 5
    mock_cfg_obj.pdf.threshold_medium = 15
    mock_cfg_obj.pdf.dpi_full = 150
    mock_cfg_obj.pdf.dpi_medium = 100
    mock_cfg_obj.pdf.dpi_compressed = 72
    mock_cfg_obj.pdf.max_pages = 20
    mock_cfg_obj.pdf.notify_truncated = True

    with patch.dict(sys.modules, {"pdf2image": mock_pdf2image}), \
         patch("llm.utils.attachment_processor.attachment_config", mock_cfg_obj):
        parts = await _process_pdf(b"fake_pdf", "test.pdf")

    assert len(parts) == 3
    assert all(p["type"] == "image_url" for p in parts)
    assert all(p["image_url"]["url"].startswith("data:image/jpeg;base64,") for p in parts)


@pytest.mark.asyncio
async def test_process_pdf_truncation():
    """_process_pdf 截斷路徑：25 頁 → 20 頁 + 截斷通知"""
    from llm.utils.attachment_processor import _process_pdf

    mock_pages = [_make_jpeg_pil() for _ in range(25)]
    mock_pdf2image = MagicMock()
    mock_pdf2image.pdfinfo_from_bytes.return_value = {"Pages": 25}
    mock_pdf2image.convert_from_bytes.return_value = mock_pages

    mock_cfg_obj = MagicMock()
    mock_cfg_obj.pdf.threshold_full = 5
    mock_cfg_obj.pdf.threshold_medium = 15
    mock_cfg_obj.pdf.dpi_full = 150
    mock_cfg_obj.pdf.dpi_medium = 100
    mock_cfg_obj.pdf.dpi_compressed = 72
    mock_cfg_obj.pdf.max_pages = 20
    mock_cfg_obj.pdf.notify_truncated = True

    with patch.dict(sys.modules, {"pdf2image": mock_pdf2image}), \
         patch("llm.utils.attachment_processor.attachment_config", mock_cfg_obj):
        parts = await _process_pdf(b"fake_pdf", "big.pdf")

    # 1 text truncation notice + 20 image parts
    assert len(parts) == 21
    assert parts[0]["type"] == "text"
    assert "truncated" in parts[0]["text"]
    assert all(p["type"] == "image_url" for p in parts[1:])


@pytest.mark.asyncio
async def test_process_pdf_zero_pages_returns_text():
    """_process_pdf 0 頁時回傳 text 佔位符"""
    from llm.utils.attachment_processor import _process_pdf

    mock_pdf2image = MagicMock()
    mock_pdf2image.pdfinfo_from_bytes.return_value = {"Pages": 0}
    mock_pdf2image.convert_from_bytes.return_value = []

    mock_cfg_obj = MagicMock()
    mock_cfg_obj.pdf.threshold_full = 5
    mock_cfg_obj.pdf.threshold_medium = 15
    mock_cfg_obj.pdf.dpi_full = 150
    mock_cfg_obj.pdf.dpi_medium = 100
    mock_cfg_obj.pdf.dpi_compressed = 72
    mock_cfg_obj.pdf.max_pages = 20
    mock_cfg_obj.pdf.notify_truncated = True

    with patch.dict(sys.modules, {"pdf2image": mock_pdf2image}), \
         patch("llm.utils.attachment_processor.attachment_config", mock_cfg_obj):
        parts = await _process_pdf(b"empty.pdf", "empty.pdf")

    assert len(parts) == 1
    assert parts[0]["type"] == "text"
    assert "empty.pdf" in parts[0]["text"]


# --- _process_video test ---


@pytest.mark.asyncio
async def test_process_video_samples_frames():
    """_process_video 正常路徑：均勻採樣幀"""
    from llm.utils.attachment_processor import _process_video

    fake_frames = np.zeros((3, 100, 100, 3), dtype=np.uint8)

    mock_vr = MagicMock()
    mock_vr.__len__ = MagicMock(return_value=30)
    mock_vr.get_avg_fps.return_value = 30.0
    mock_vr.get_batch.return_value = MagicMock(asnumpy=MagicMock(return_value=fake_frames))

    mock_decord = MagicMock()
    mock_decord.VideoReader.return_value = mock_vr
    mock_decord.cpu.return_value = None

    mock_cfg_obj = MagicMock()
    mock_cfg_obj.video.max_frames = 3
    mock_cfg_obj.video.min_interval_sec = 0.0

    with patch.dict(sys.modules, {"decord": mock_decord}), \
         patch("llm.utils.attachment_processor.attachment_config", mock_cfg_obj):
        parts = await _process_video(b"fake_video", "test.mp4")

    assert len(parts) == 3
    assert all(p["type"] == "image_url" for p in parts)


# --- per-type enabled flag tests ---


@pytest.mark.asyncio
async def test_pdf_disabled_returns_text_placeholder():
    """pdf.enabled=False 時應回傳 unsupported text，不嘗試解析"""
    from llm.utils.attachment_processor import process_attachment

    att = _make_attachment("application/pdf", "doc.pdf")
    mock_cfg = MagicMock()
    mock_cfg.enabled = True
    mock_cfg.image.enabled = True
    mock_cfg.pdf.enabled = False
    mock_cfg.video.enabled = True

    with patch("llm.utils.attachment_processor.attachment_config", mock_cfg):
        parts = await process_attachment(att)

    assert len(parts) == 1
    assert parts[0]["type"] == "text"
    assert "doc.pdf" in parts[0]["text"]
    assert "unsupported" in parts[0]["text"]


@pytest.mark.asyncio
async def test_video_disabled_returns_text_placeholder():
    """video.enabled=False 時應回傳 unsupported text"""
    from llm.utils.attachment_processor import process_attachment

    att = _make_attachment("video/mp4", "clip.mp4")
    mock_cfg = MagicMock()
    mock_cfg.enabled = True
    mock_cfg.image.enabled = True
    mock_cfg.pdf.enabled = True
    mock_cfg.video.enabled = False

    with patch("llm.utils.attachment_processor.attachment_config", mock_cfg):
        parts = await process_attachment(att)

    assert len(parts) == 1
    assert parts[0]["type"] == "text"
    assert "clip.mp4" in parts[0]["text"]
    assert "unsupported" in parts[0]["text"]
