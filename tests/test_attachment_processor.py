# tests/test_attachment_processor.py
import asyncio
import base64
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


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
