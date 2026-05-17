# Attachment & Embed Content Support Design

**Date:** 2026-05-17  
**Branch:** jules  
**Scope:** 擴充 LLM 對使用者傳入附件的理解能力（輸入端），不含媒體輸出。

---

## 背景

目前 `short_term.py` 在將 Discord message 轉換為 LangChain `BaseMessage` 時，僅完整支援圖片附件（轉為 `image_url`）。影片、PDF 雖然在 `media.py` 已有基礎處理邏輯，但未接上 short_term memory 管線。Discord Embed 則完全未解析。

---

## 目標

1. 讓 LLM 能理解使用者上傳的 **PDF**（圖片優先）和**影片**（關鍵幀採樣）
2. 讓 LLM 能讀取訊息中的 **Discord Embeds**（結構化文字 + 內嵌圖片）
3. 所有處理參數透過設定檔控制，支援動態壓縮以控制 token 消耗
4. 不新增任何套件依賴（全部複用現有 `media.py` 的 `pdf2image`、`decord`）

---

## 不包含

- 音訊轉文字（STT）
- 媒體格式的輸出
- 其他文件格式（Word、Excel 等）

---

## 架構

### 新增元件

```
llm/utils/attachment_processor.py   ← 核心：附件 → content_parts
llm/utils/embed_processor.py        ← Embed → content_parts
base_configs/attachments.yaml       ← 預設設定
configs/attachments.yaml            ← 使用者覆寫
```

### 修改元件

```
addons/settings.py                  ← 新增 attachment_config 型別化物件
llm/memory/short_term.py            ← 改用 attachment_processor / embed_processor
```

---

## 設定檔（`base_configs/attachments.yaml`）

```yaml
attachments:
  enabled: true

  image:
    enabled: true
    max_dimension: 2048        # 超過此像素則等比縮放

  pdf:
    enabled: true
    max_pages: 20              # 硬上限（超出後均勻採樣）
    dpi_full: 150              # 頁數 ≤ threshold_full
    dpi_medium: 100            # 頁數 ≤ threshold_medium
    dpi_compressed: 72         # 頁數 > threshold_medium
    threshold_full: 5
    threshold_medium: 15
    notify_truncated: true     # 超出 max_pages 時在 context 告知 LLM

  video:
    enabled: true
    max_frames: 16             # 最多採樣幀數
    min_interval_sec: 2.0      # 相鄰幀最小間距（秒）

  embeds:
    enabled: true
    include_images: true       # 是否提取 embed 內的圖片
```

---

## `attachment_processor.py` 設計

### 介面

```python
async def process_attachment(attachment: discord.Attachment) -> list[dict]:
    """
    輸入：單一 Discord attachment
    輸出：LangChain content_parts 清單

    圖片 → [{"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}]
    PDF  → [{"type": "image_url", ...}, ...]  # 每頁（或採樣頁）一項
    影片 → [{"type": "image_url", ...}, ...]  # 關鍵幀，每幀一項
    其他 → [{"type": "text", "text": "[Attachment: filename (unsupported type)]"}]
    失敗 → [{"type": "text", "text": "[Attachment processing failed: filename]"}]
    """
```

### PDF 動態壓縮邏輯

| 頁數範圍 | DPI | 頁面選取 |
|---------|-----|---------|
| 1–5 頁 | 150 | 全部 |
| 6–15 頁 | 100 | 全部 |
| 16+ 頁 | 72 | 均勻採樣至 max_pages，超出時前 max_pages/2 頁 + 後 max_pages/2 頁 + 截斷通知 |

截斷通知格式（插入為 text part）：
```
[System: PDF truncated — showing 20 of 87 pages (pages 1-10 and 77-87)]
```

### 影片動態壓縮邏輯

- 總幀數 / max_frames → 採樣間距（幀數）
- 若採樣間距換算時間 < min_interval_sec，則以 min_interval_sec 為下限
- 使用 `decord.VideoReader`（現有 `media.py` 邏輯複用）

### 錯誤處理

每個 attachment 獨立 try/except，單一附件失敗不影響其他內容或訊息處理。

---

## `embed_processor.py` 設計

### 介面

```python
def process_embed(embed: discord.Embed) -> list[dict]:
    """
    輸入：單一 Discord Embed
    輸出：LangChain content_parts 清單
    """
```

### 輸出格式

文字欄位序列化為結構化文字（一個 text part）：

```
[Embed: {title}]
{description}
Fields:
  • {field.name}: {field.value}
URL: {url}
```

若 `include_images: true` 且 embed 含有 `image.url` 或 `thumbnail.url`，額外附加 image_url part：
```python
{"type": "image_url", "image_url": {"url": embed.image.url}}
```

空 embed（無任何文字欄位且無圖片）則跳過，不產生任何 part。

---

## `short_term.py` 改動

**改動範圍：~10 行**

現有 attachment 迴圈（約第 87–108 行）整個替換為：

```python
from llm.utils.attachment_processor import process_attachment
from llm.utils.embed_processor import process_embed
from addons.settings import attachment_config

# Attachments
if msg.attachments and attachment_config.enabled:
    for attachment in msg.attachments:
        parts = await process_attachment(attachment)
        content_parts.extend(parts)

# Embeds
if msg.embeds and attachment_config.embeds.enabled:
    for embed in msg.embeds:
        parts = process_embed(embed)
        content_parts.extend(parts)
```

---

## `addons/settings.py` 改動

遵循現有 `memory_config`、`llm_config` 模式，新增：

```python
attachment_config = load_config("attachments")
```

暴露為 `attachment_config.pdf.max_pages`、`attachment_config.video.max_frames` 等。

---

## 資料流

```
Discord Message
  ├─ attachments[]
  │    └─ attachment_processor.process_attachment()
  │         ├─ image/* → PIL 縮放 → base64 → image_url
  │         ├─ application/pdf → pdf2image → 動態壓縮 → [image_url, ...]
  │         ├─ video/* → decord 採樣 → [image_url, ...]
  │         └─ 其他 → text 佔位符
  └─ embeds[]
       └─ embed_processor.process_embed()
            ├─ 文字欄位 → 結構化 text
            └─ image/thumbnail → image_url
```

所有輸出皆為標準 LangChain content_parts，與現有 `_sanitize_messages_for_model` 的 Ollama/Gemini 處理邏輯完全相容（image_url 型別不變）。

---

## 風險與限制

| 風險 | 緩解 |
|------|------|
| 大型 PDF/影片下載耗時 | 沿用現有 `_IMAGE_FETCH_TIMEOUT_SECONDS = 15.0` 機制 |
| base64 圖片增加 token 消耗 | 動態壓縮 + max_pages/max_frames 設定上限 |
| decord 在部分環境不可用 | try/except fallback 為 text 佔位符 |
| Embed 圖片 URL 過期 | 獨立 try/except，失敗時跳過圖片但保留文字 |
