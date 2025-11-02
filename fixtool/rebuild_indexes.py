#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
維護腳本：重建所有頻道向量索引

用途:
  從命令列執行，載入設定與資料庫、初始化嵌入與向量管理元件，
  逐頻道重建向量索引，並輸出進度與彙總結果。

執行:
  python maintenance/rebuild_indexes.py
"""

import os
import sys
import time
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple

# 1) 載入 .env（若存在）
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # 若無 dotenv，仍允許繼續執行
    pass

# 確保可以以專案根目錄為基準導入 cogs 套件
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# 2) 匯入系統元件
from cogs.memory.config import MemoryConfig, MemoryProfile  # noqa: E402
from cogs.memory.database import DatabaseManager            # noqa: E402
from cogs.memory.embedding_service import EmbeddingService  # noqa: E402
from cogs.memory.vector_manager import VectorManager        # noqa: E402


def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("rebuild_indexes")
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(stream=sys.stdout)
    formatter = logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    # 避免重複加入 handler
    if not logger.handlers:
        logger.addHandler(handler)
    return logger


def _load_settings() -> Tuple[MemoryConfig, MemoryProfile, Dict[str, Any]]:
    """載入設定與目前記憶體配置檔案。"""
    cfg = MemoryConfig()  # 預設讀取 ./settings.json
    config_data = cfg.load_config()
    profile = cfg.get_current_profile()
    return cfg, profile, config_data


def _init_components(logger: logging.Logger) -> Tuple[DatabaseManager, MemoryProfile, EmbeddingService, VectorManager, Dict[str, Any]]:
    """初始化資料庫、嵌入服務與向量管理器。"""
    cfg, profile, config_data = _load_settings()

    memory_cfg = cfg.get_memory_config()
    db_path = memory_cfg.get("database_path", "data/memory/memory.db")

    logger.info(f"初始化資料庫: {db_path}")
    from main import bot
    dbm = DatabaseManager(db_path, bot=bot)

    if not profile.vector_enabled:
        logger.warning("目前配置檔案關閉了向量功能(vector_enabled=False)，將仍嘗試重建，但嵌入可能被跳過。")

    logger.info(f"初始化嵌入服務: 模型={profile.embedding_model}")
    emb = EmbeddingService(profile)

    # 依據 database_path 推導 indices 目錄（與 MemoryManager 的行為一致）
    indices_path = Path(db_path).parent / "indices"
    indices_path.mkdir(parents=True, exist_ok=True)

    logger.info(f"初始化向量管理器: 索引目錄={indices_path}")
    vman = VectorManager(profile, storage_path=indices_path)

    return dbm, profile, emb, vman, config_data


def _fetch_channel_items(dbm: DatabaseManager, channel_id: str, logger: logging.Logger) -> List[Tuple[str, str]]:
    """
    取得頻道資料以供嵌入：
      先取 conversation_segments，若沒有則回退 messages。

    回傳:
      List[(real_id, text)]
        - seg_*: 使用 segment_id 的字面值作為文字（如需更佳品質，可改成摘要或聚合文本）
        - msg_*: 使用 content_processed 或 content
    """
    items: List[Tuple[str, str]] = []
    with dbm.get_connection() as conn:
        # 先用片段
        seg_rows = conn.execute(
            "SELECT segment_id FROM conversation_segments WHERE channel_id = ? ORDER BY start_time ASC",
            (channel_id,),
        ).fetchall()
        if seg_rows:
            for r in seg_rows:
                seg_id = str(r["segment_id"])
                # 簡化：以 seg_id 作為文字；若專案有 segment 文本/摘要表，請改為實際文本
                items.append((f"seg_{seg_id}", seg_id))
            return items

        # 回退 messages
        msg_rows = conn.execute(
            "SELECT message_id, content_processed, content FROM messages WHERE channel_id = ? ORDER BY timestamp ASC",
            (channel_id,),
        ).fetchall()
        for r in msg_rows:
            msg_id = str(r["message_id"])
            text = r["content_processed"] or r["content"] or ""
            text = (text or "").strip()
            if not text:
                continue
            items.append((f"msg_{msg_id}", text))
    return items


def _iter_all_channel_ids(dbm: DatabaseManager, indices_path: Path, logger: logging.Logger) -> List[str]:
    """
    根據索引檔案或資料庫 channels 表列出候選頻道 ID。
    """
    channel_ids: List[str] = []
    if indices_path.exists():
        channel_ids = sorted([p.stem for p in indices_path.glob("*.index")])
    if not channel_ids:
        try:
            with dbm.get_connection() as conn:
                rows = conn.execute("SELECT channel_id FROM channels").fetchall()
                channel_ids = [str(r["channel_id"]) for r in rows]
        except Exception as e:
            logger.warning(f"無法從資料庫列出頻道: {e}")
            channel_ids = []
    return channel_ids


def _embed_in_batches(emb: EmbeddingService, texts: List[str], batch: int) -> List:
    """
    依批量產生嵌入，回傳與 texts 對齊的向量陣列(list of np.ndarray row)。
    EmbeddingService 應提供同步 API：embed_texts(texts) -> np.ndarray
    """
    vec_rows: List = []
    for i in range(0, len(texts), batch):
        chunk = texts[i:i + batch]
        # 依使用者規範，不以預設值吞錯，若失敗就丟出讓外層統計
        vec = emb.encode_batch(chunk)
        # 期望 vec shape 為 (N, dim)
        for row in vec:
            vec_rows.append(row)
    return vec_rows


def rebuild_all(logger: logging.Logger) -> Dict[str, Any]:
    """
    主流程：重建所有頻道索引，輸出進度與彙總。
    """
    start = time.time()
    dbm, profile, emb, vman, config_data = _init_components(logger)

    indices_path = vman.storage_path
    channel_ids = _iter_all_channel_ids(dbm, indices_path, logger)

    summary = {"total_channels": len(channel_ids), "success": 0, "failed": 0}
    per_channel: Dict[str, Any] = {}

    if not channel_ids:
        logger.info("沒有頻道可供重建索引。")
        return {"summary": summary, "channels": per_channel}

    for cid in channel_ids:
        added = 0
        skipped = 0
        failed = 0
        saved_ok = False

        try:
            print(f"[Rebuild] 正在重建頻道 {cid} 的索引...")
            
            # 先強制刪除舊的索引檔案和映射檔案，確保從零開始重建
            index_file = indices_path / f"{cid}.index"
            mapping_file = indices_path / f"{cid}.mapping"
            
            try:
                os.remove(index_file)
                logger.info(f"已刪除舊索引檔案: {index_file}")
            except FileNotFoundError:
                logger.debug(f"索引檔案不存在，跳過刪除: {index_file}")
            except Exception as e:
                logger.warning(f"刪除索引檔案時發生錯誤: {index_file}, 錯誤: {e}")
            
            try:
                os.remove(mapping_file)
                logger.info(f"已刪除舊映射檔案: {mapping_file}")
            except FileNotFoundError:
                logger.debug(f"映射檔案不存在，跳過刪除: {mapping_file}")
            except Exception as e:
                logger.warning(f"刪除映射檔案時發生錯誤: {mapping_file}, 錯誤: {e}")
            
            # 重新建立空索引（卸載後再建立）
            vman.unload_channel_index(cid)
            if not vman.create_channel_index(cid):
                raise RuntimeError("建立頻道索引失敗")

            items = _fetch_channel_items(dbm, cid, logger)
            if not items:
                print(f"[Rebuild] 頻道 {cid} 無資料可重建，跳過。")
                per_channel[cid] = {"added": 0, "skipped": skipped, "failed": failed, "saved": False, "note": "no_data"}
                summary["success"] += 1
                continue

            # 批次處理
            batch_size = max(8, int(getattr(profile, "batch_size", 50)))
            cur_texts: List[str] = []
            cur_ids: List[str] = []

            def _flush_batch():
                nonlocal added, failed, cur_texts, cur_ids
                if not cur_texts:
                    return
                try:
                    vecs = emb.encode_batch(cur_texts)
                    ok = vman.add_vectors(cid, vecs, cur_ids, batch_size=batch_size)
                    if ok:
                        added += len(cur_ids)
                    else:
                        failed += len(cur_ids)
                except Exception as e:
                    logger.error(f"頻道 {cid} 產生嵌入/寫入索引失敗: {e}")
                    failed += len(cur_ids)
                finally:
                    cur_texts, cur_ids = [], []

            for rid, text in items:
                if not text or not text.strip():
                    skipped += 1
                    continue
                cur_texts.append(text)
                cur_ids.append(rid)
                if len(cur_texts) >= batch_size:
                    _flush_batch()

            _flush_batch()

            # 儲存索引
            try:
                # 在同步腳本中建立事件迴圈會有衝突，優先使用 run until complete
                import asyncio
                try:
                    saved_ok = asyncio.run(vman.save_index(cid))
                except RuntimeError:
                    loop = asyncio.get_event_loop()
                    saved_ok = loop.run_until_complete(vman.save_index(cid))
            except Exception as e:
                logger.error(f"頻道 {cid} 儲存索引失敗: {e}")
                saved_ok = False

            per_channel[cid] = {"added": added, "skipped": skipped, "failed": failed, "saved": saved_ok}
            if failed == 0 and saved_ok:
                summary["success"] += 1
                print(f"[Rebuild] 頻道 {cid} 重建完成：新增 {added}，略過 {skipped}，儲存 {'成功' if saved_ok else '失敗'}")
            else:
                summary["failed"] += 1
                print(f"[Rebuild] 頻道 {cid} 重建部分失敗：新增 {added}，略過 {skipped}，失敗 {failed}，儲存 {'成功' if saved_ok else '失敗'}")

        except Exception as e:
            logger.error(f"重建頻道 {cid} 索引時發生錯誤: {e}", exc_info=True)
            per_channel[cid] = {"error": str(e)}
            summary["failed"] += 1

    elapsed = time.time() - start
    logger.info(f"索引重建完成，耗時 {elapsed:.2f}s，成功 {summary['success']}/{summary['total_channels']}，失敗 {summary['failed']}")
    return {"summary": summary, "channels": per_channel}


def main() -> None:
    logger = _setup_logger()
    logger.info("索引重建維護腳本啟動")
    try:
        result = rebuild_all(logger)
        # 以 JSON 輸出摘要，方便 CI/監控解析
        print(json.dumps(result["summary"], ensure_ascii=False))
    except Exception as e:
        logger.error(f"重建流程發生致命錯誤: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()