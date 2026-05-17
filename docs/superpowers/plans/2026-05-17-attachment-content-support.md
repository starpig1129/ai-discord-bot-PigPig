# Attachment & Embed Content Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 LLM 能理解使用者傳入的 PDF（圖片優先）、影片（關鍵幀採樣）和 Discord Embed，所有參數透過設定檔控制。

**Architecture:** 新增 `AttachmentConfig`（`addons/settings.py`）、`attachment_processor.py`、`embed_processor.py` 三個元件，`short_term.py` 中的 attachment 迴圈改為呼叫這兩個 processor；所有媒體轉換輸出標準 LangChain `image_url` content parts（base64 data URI），與現有 Ollama/Gemini sanitize 邏輯完全相容。

**Tech Stack:** Python 3.11+、`pdf2image`（已有）、`decord`（已有）、`Pillow`（已有）、`aiohttp`（已有）、`discord.py`、`pytest`、`pytest-asyncio`

---

## File Map

| 動作 | 路徑 | 職責 |
|------|------|------|
| 新增 | `base_configs/attachments.yaml` | 預設設定值 |
| 新增 | `addons/settings.py`（修改） | `AttachmentConfig` 及子 config 類別、`attachment_config` 實例 |
| 新增 | `llm/utils/attachment_processor.py` | 下載附件、按類型處理、輸出 content_parts |
| 新增 | `llm/utils/embed_processor.py` | Discord Embed → content_parts |
| 修改 | `llm/memory/short_term.py`（第 85–108 行） | 改用兩個 processor |
| 新增 | `tests/test_attachment_processor.py` | unit tests |
| 新增 | `tests/test_embed_processor.py` | unit tests |

---

## Task 1：建立設定檔與 `AttachmentConfig`

**Files:**
- Create: `base_configs/attachments.yaml`
- Modify: `addons/settings.py`
- Test: `tests/test_attachment_config.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_attachment_config.py
import pytest
from unittest.mock import patch

def test_attachment_config_defaults():
    """AttachmentConfig 應從 YAML 正確載入預設值"""
    from addons.settings import AttachmentConfig
    cfg = AttachmentConfig("base_configs/attachments.yaml")
    assert cfg.enabled is True
    assert cfg.image.max_dimension == 2048
    assert cfg.pdf.max_pages == 20
    assert cfg.pdf.dpi_full == 150
    assert cfg.pdf.dpi_medium == 100
    assert cfg.pdf.dpi_compressed == 72
    assert cfg.pdf.threshold_full == 5
    assert cfg.pdf.threshold_medium == 15
    assert cfg.pdf.notify_truncated is True
    assert cfg.video.max_frames == 16
    assert cfg.video.min_interval_sec == 2.0
    assert cfg.embeds.enabled is True
    assert cfg.embeds.include_images is True

def test_attachment_config_missing_file():
    """不存在的 YAML 應 fallback 為預設值，不拋出例外"""
    from addons.settings import AttachmentConfig
    cfg = AttachmentConfig("nonexistent_path/attachments.yaml")
    assert cfg.enabled is True
    assert cfg.pdf.max_pages == 20
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
cd /media/ubuntu/4TB-HDD/ziyue/PigPig-discord-LLM-bot
python -m pytest tests/test_attachment_config.py -v
```

預期輸出：`ImportError: cannot import name 'AttachmentConfig'`

- [ ] **Step 3: 建立 `base_configs/attachments.yaml`**

```yaml
# base_configs/attachments.yaml
attachments:
  enabled: true

  image:
    enabled: true
    max_dimension: 2048

  pdf:
    enabled: true
    max_pages: 20
    dpi_full: 150
    dpi_medium: 100
    dpi_compressed: 72
    threshold_full: 5
    threshold_medium: 15
    notify_truncated: true

  video:
    enabled: true
    max_frames: 16
    min_interval_sec: 2.0

  embeds:
    enabled: true
    include_images: true
```

- [ ] **Step 4: 在 `addons/settings.py` 新增 config 類別**

在 `MemoryConfig` 類別後、`try: base_config = ...` 之前插入：

```python
class _AttachmentImageConfig:
    def __init__(self, data: dict) -> None:
        self.enabled: bool = bool(data.get("enabled", True))
        self.max_dimension: int = int(data.get("max_dimension", 2048))


class _AttachmentPdfConfig:
    def __init__(self, data: dict) -> None:
        self.enabled: bool = bool(data.get("enabled", True))
        self.max_pages: int = int(data.get("max_pages", 20))
        self.dpi_full: int = int(data.get("dpi_full", 150))
        self.dpi_medium: int = int(data.get("dpi_medium", 100))
        self.dpi_compressed: int = int(data.get("dpi_compressed", 72))
        self.threshold_full: int = int(data.get("threshold_full", 5))
        self.threshold_medium: int = int(data.get("threshold_medium", 15))
        self.notify_truncated: bool = bool(data.get("notify_truncated", True))


class _AttachmentVideoConfig:
    def __init__(self, data: dict) -> None:
        self.enabled: bool = bool(data.get("enabled", True))
        self.max_frames: int = int(data.get("max_frames", 16))
        self.min_interval_sec: float = float(data.get("min_interval_sec", 2.0))


class _AttachmentEmbedsConfig:
    def __init__(self, data: dict) -> None:
        self.enabled: bool = bool(data.get("enabled", True))
        self.include_images: bool = bool(data.get("include_images", True))


class AttachmentConfig:
    """Configuration for attachment and embed processing (base_configs/attachments.yaml)."""

    def __init__(self, path: str = "base_configs/attachments.yaml") -> None:
        self.path = path
        data = _load_yaml_file(path)
        cfg = data.get("attachments", {})
        self.enabled: bool = bool(cfg.get("enabled", True))
        self.image = _AttachmentImageConfig(cfg.get("image", {}))
        self.pdf = _AttachmentPdfConfig(cfg.get("pdf", {}))
        self.video = _AttachmentVideoConfig(cfg.get("video", {}))
        self.embeds = _AttachmentEmbedsConfig(cfg.get("embeds", {}))
```

- [ ] **Step 5: 在 `addons/settings.py` 結尾新增實例與 `__all__` 項目**

在 `memory_config = MemoryConfig(...)` 的 try/except 區塊之後、`__all__` 之前插入：

```python
try:
    attachment_config = AttachmentConfig(f"{CONFIG_ROOT}/attachments.yaml")
except Exception as e:
    try:
        from function import func
        asyncio.create_task(func.report_error(e, "addons/settings.py/module_init"))
    except Exception:
        logger.error(f"Error initializing AttachmentConfig: {e}")
    attachment_config = AttachmentConfig(f"{CONFIG_ROOT}/attachments.yaml")
```

並將 `__all__` 更新為：

```python
__all__ = [
    "BaseConfig",
    "base_config",
    "LLMConfig",
    "llm_config",
    "UpdateConfig",
    "update_config",
    "MusicConfig",
    "music_config",
    "PromptConfig",
    "prompt_config",
    "MemoryConfig",
    "memory_config",
    "AttachmentConfig",
    "attachment_config",
]
```

- [ ] **Step 6: 執行測試確認通過**

```bash
python -m pytest tests/test_attachment_config.py -v
```

預期輸出：`2 passed`

- [ ] **Step 7: Commit**

```bash
git add base_configs/attachments.yaml addons/settings.py tests/test_attachment_config.py
git commit -m "feat: add AttachmentConfig with nested sub-configs for pdf/video/embeds"
```

---

## Task 2：建立 `embed_processor.py`

**Files:**
- Create: `llm/utils/embed_processor.py`
- Test: `tests/test_embed_processor.py`

- [ ] **Step 1: 寫失敗測試**

```python
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
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
python -m pytest tests/test_embed_processor.py -v
```

預期輸出：`ModuleNotFoundError: No module named 'llm.utils.embed_processor'`

- [ ] **Step 3: 建立 `llm/utils/embed_processor.py`**

```python
# llm/utils/embed_processor.py
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import discord


def process_embed(embed: "discord.Embed") -> list[dict]:
    """
    Convert a Discord Embed to LangChain content_parts.

    Text fields are serialized as a single structured text part.
    Images/thumbnails are appended as image_url parts.
    Empty embeds (no text, no images) return [].
    """
    from addons.settings import attachment_config

    if not attachment_config.embeds.enabled:
        return []

    lines: list[str] = []

    if embed.title:
        lines.append(f"[Embed: {embed.title}]")
    if embed.description:
        lines.append(embed.description)
    if embed.fields:
        lines.append("Fields:")
        for field in embed.fields:
            lines.append(f"  • {field.name}: {field.value}")
    if embed.url:
        lines.append(f"URL: {embed.url}")

    parts: list[dict] = []

    if lines:
        parts.append({"type": "text", "text": "\n".join(lines)})

    if attachment_config.embeds.include_images:
        if embed.image and embed.image.url:
            parts.append({"type": "image_url", "image_url": {"url": embed.image.url}})
        if embed.thumbnail and embed.thumbnail.url:
            parts.append({"type": "image_url", "image_url": {"url": embed.thumbnail.url}})

    return parts
```

- [ ] **Step 4: 執行測試確認通過**

```bash
python -m pytest tests/test_embed_processor.py -v
```

預期輸出：`5 passed`

- [ ] **Step 5: Commit**

```bash
git add llm/utils/embed_processor.py tests/test_embed_processor.py
git commit -m "feat: add embed_processor — Discord Embed to LangChain content_parts"
```

---

## Task 3：建立 `attachment_processor.py`（圖片 + PDF + 影片）

**Files:**
- Create: `llm/utils/attachment_processor.py`
- Test: `tests/test_attachment_processor.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_attachment_processor.py
import pytest
import asyncio
import base64
import io
from unittest.mock import AsyncMock, MagicMock, patch


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

    original = attachment_processor.attachment_config.enabled
    try:
        attachment_processor.attachment_config.enabled = False
        parts = await attachment_processor.process_attachment(att)
        assert parts == []
    finally:
        attachment_processor.attachment_config.enabled = original
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
python -m pytest tests/test_attachment_processor.py -v
```

預期輸出：`ModuleNotFoundError: No module named 'llm.utils.attachment_processor'`

- [ ] **Step 3: 建立 `llm/utils/attachment_processor.py`**

```python
# llm/utils/attachment_processor.py
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
    async with aiohttp.ClientSession(timeout=_DOWNLOAD_TIMEOUT) as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            return await resp.read()


def _pil_to_content_part(img: Image.Image) -> dict:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}


def _resize_if_needed(img: Image.Image, max_dim: int) -> Image.Image:
    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    return img


async def _process_image(data: bytes) -> list[dict]:
    cfg = attachment_config.image
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img = _resize_if_needed(img, cfg.max_dimension)
    return [_pil_to_content_part(img)]


async def _process_pdf(data: bytes, filename: str) -> list[dict]:
    from pdf2image import convert_from_bytes, pdfinfo_from_bytes

    cfg = attachment_config.pdf

    try:
        info = pdfinfo_from_bytes(data)
        total_pages: int = int(info.get("Pages", 0))
    except Exception:
        # pdfinfo unavailable; fallback: convert at low DPI to count
        preview = convert_from_bytes(data, dpi=72, fmt="jpeg")
        total_pages = len(preview)

    # Determine DPI
    if total_pages <= cfg.threshold_full:
        dpi = cfg.dpi_full
    elif total_pages <= cfg.threshold_medium:
        dpi = cfg.dpi_medium
    else:
        dpi = cfg.dpi_compressed

    # Determine page selection
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

    # Convert pages
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
    """
    Convert a Discord Attachment to LangChain content_parts.

    Returns [] if attachment processing is disabled globally.
    Returns a text fallback part on unsupported type or processing failure.
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
        from function import func
        asyncio.create_task(func.report_error(e, f"process_attachment failed for {filename}"))
        log.warning(f"Attachment processing failed for {filename}: {e}")
        return [{"type": "text", "text": f"[Attachment processing failed: {filename}]"}]
```

- [ ] **Step 4: 執行測試確認通過**

```bash
python -m pytest tests/test_attachment_processor.py -v
```

預期輸出：`6 passed`

- [ ] **Step 5: Commit**

```bash
git add llm/utils/attachment_processor.py tests/test_attachment_processor.py
git commit -m "feat: add attachment_processor — PDF/video/image to LangChain content_parts with dynamic compression"
```

---

## Task 4：整合進 `short_term.py`

**Files:**
- Modify: `llm/memory/short_term.py`（第 85–108 行）

- [ ] **Step 1: 替換 `short_term.py` 的 attachment 迴圈**

將第 85–108 行的現有 attachment 區塊：

```python
                if msg.attachments:
                    for attachment in msg.attachments:
                        if attachment.content_type:
                            if attachment.content_type.startswith('image/'):
                                # Standard LangChain format for both Gemini and Ollama
                                content_parts.append({
                                    "type": "image_url",
                                    "image_url": {"url": attachment.url}
                                })
                            elif attachment.content_type.startswith('video/'):
                                content_parts.append({
                                    "type": "text",
                                    "text": f"[Video Attachment: {attachment.filename}]"
                                })
                            elif attachment.content_type == 'application/pdf':
                                content_parts.append({
                                    "type": "text",
                                    "text": f"[PDF Attachment: {attachment.filename}]"
                                })
                            elif attachment.content_type.startswith('audio/'):
                                content_parts.append({
                                    "type": "text",
                                    "text": f"[Audio Attachment: {attachment.filename}]"
                                })
```

替換為：

```python
                if msg.attachments:
                    from llm.utils.attachment_processor import process_attachment
                    from addons.settings import attachment_config as _att_cfg
                    if _att_cfg.enabled:
                        for attachment in msg.attachments:
                            parts = await process_attachment(attachment)
                            content_parts.extend(parts)

```

- [ ] **Step 2: 在 `short_term.py` 的 embeds 區塊前加入 embed 處理**

在 Step 1 替換的程式碼之後、`# Create message` 注解之前插入：

```python
                if msg.embeds:
                    from llm.utils.embed_processor import process_embed
                    from addons.settings import attachment_config as _att_cfg
                    if _att_cfg.embeds.enabled:
                        for embed in msg.embeds:
                            parts = process_embed(embed)
                            content_parts.extend(parts)

```

- [ ] **Step 3: 執行既有測試確認無退化**

```bash
python -m pytest tests/ -v --ignore=tests/dashboard -x
```

預期輸出：所有測試 pass，無新失敗。

- [ ] **Step 4: Commit**

```bash
git add llm/memory/short_term.py
git commit -m "feat: integrate attachment_processor and embed_processor into short_term memory"
```

---

## Task 5：手動煙霧測試與收尾

- [ ] **Step 1: 確認 import 路徑無循環依賴**

```bash
python -c "from llm.utils.attachment_processor import process_attachment; print('OK')"
python -c "from llm.utils.embed_processor import process_embed; print('OK')"
python -c "from addons.settings import attachment_config; print(attachment_config.pdf.max_pages)"
```

預期輸出各行分別為 `OK`、`OK`、`20`

- [ ] **Step 2: 確認 `_resize_if_needed` 邊界條件**

```bash
python -c "
from PIL import Image
from llm.utils.attachment_processor import _resize_if_needed
# 剛好等於上限不縮放
img = Image.new('RGB', (2048, 1024))
r = _resize_if_needed(img, 2048)
assert r.size == (2048, 1024), f'Should not resize: {r.size}'
# 超過上限縮放
img2 = Image.new('RGB', (4096, 2048))
r2 = _resize_if_needed(img2, 2048)
assert r2.size == (2048, 1024), f'Wrong size: {r2.size}'
print('resize OK')
"
```

預期輸出：`resize OK`

- [ ] **Step 3: 執行全部測試**

```bash
python -m pytest tests/ -v --ignore=tests/dashboard
```

預期輸出：所有測試通過，無任何 error 或 warning。

- [ ] **Step 4: 最終 commit**

```bash
git add .
git commit -m "test: verify attachment_processor resize boundary conditions"
```

---

## 備註

- **`_download` 使用 15 秒 timeout**（與 orchestrator.py 的 `_IMAGE_FETCH_TIMEOUT_SECONDS` 一致）
- **圖片以 JPEG quality=85 編碼**，在品質和 token 體積間取得平衡
- **PDF 的 `pdfinfo_from_bytes`** 需要系統安裝 poppler（pdf2image 本身的依賴，已存在）
- **影片 fallback**：若 decord 不可用（ImportError），`process_attachment` 的 except 區塊會將其回報為處理失敗並輸出 text 佔位符
- **所有 base64 data URI 輸出**均與 `_sanitize_messages_for_model` 的 Ollama 路徑相容（Ollama 路徑只轉換 `http://` 開頭的 URL，data URI 直接穿透）
