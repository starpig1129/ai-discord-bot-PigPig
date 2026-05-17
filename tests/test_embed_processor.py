# tests/test_embed_processor.py
import pytest
from unittest.mock import MagicMock

def _make_embed(title=None, description=None, url=None, fields=None,
                image_url=None, thumbnail_url=None):
    """Helper: 建立 mock discord.Embed"""
    embed = MagicMock()
    embed.title = title
    embed.description = description
    embed.url = url
    embed.fields = fields or []
    embed.image = MagicMock(url=image_url) if image_url else None
    embed.thumbnail = MagicMock(url=thumbnail_url) if thumbnail_url else None
    return embed


def test_process_embed_text_only():
    from llm.utils.embed_processor import process_embed
    embed = _make_embed(title="Test Title", description="Some description", url="https://example.com")
    parts = process_embed(embed)
    assert len(parts) == 1
    assert parts[0]["type"] == "text"
    assert "Test Title" in parts[0]["text"]
    assert "Some description" in parts[0]["text"]
    assert "https://example.com" in parts[0]["text"]


def test_process_embed_with_fields():
    from llm.utils.embed_processor import process_embed
    field = MagicMock()
    field.name = "Key"
    field.value = "Value"
    embed = _make_embed(title="With Fields", fields=[field])
    parts = process_embed(embed)
    assert len(parts) == 1
    assert "Key" in parts[0]["text"]
    assert "Value" in parts[0]["text"]


def test_process_embed_with_image():
    from llm.utils.embed_processor import process_embed
    embed = _make_embed(title="Has Image", image_url="https://example.com/img.png")
    parts = process_embed(embed)
    assert len(parts) == 2
    text_parts = [p for p in parts if p["type"] == "text"]
    img_parts = [p for p in parts if p["type"] == "image_url"]
    assert len(text_parts) == 1
    assert len(img_parts) == 1
    assert img_parts[0]["image_url"]["url"] == "https://example.com/img.png"


def test_process_embed_empty_skipped():
    from llm.utils.embed_processor import process_embed
    embed = _make_embed()  # 無任何欄位
    parts = process_embed(embed)
    assert parts == []


def test_process_embed_thumbnail_included():
    from llm.utils.embed_processor import process_embed
    embed = _make_embed(description="Desc", thumbnail_url="https://example.com/thumb.png")
    parts = process_embed(embed)
    img_parts = [p for p in parts if p["type"] == "image_url"]
    assert any(p["image_url"]["url"] == "https://example.com/thumb.png" for p in img_parts)
