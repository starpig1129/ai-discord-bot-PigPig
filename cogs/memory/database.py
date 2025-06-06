"""記憶系統資料庫管理模組

提供 SQLite 資料庫的建立、連接、操作和管理功能。
實作執行緒安全的資料庫操作和連接池管理。
"""

import asyncio
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .exceptions import DatabaseError


class DatabaseManager:
    """資料庫管理器
    
    負責 SQLite 資料庫的建立、連接管理和基本 CRUD 操作。
    實作連接池和執行緒安全機制。
    """
    
    def __init__(self, db_path: Union[str, Path]):
        """初始化資料庫管理器
        
        Args:
            db_path: 資料庫檔案路徑
        """
        self.db_path = Path(db_path)
        self.logger = logging.getLogger(__name__)
        self._lock = threading.RLock()
        self._connections: Dict[int, sqlite3.Connection] = {}
        
        # 確保資料庫目錄存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 初始化資料庫
        self._initialize_database()
    
    def _initialize_database(self) -> None:
        """初始化資料庫結構"""
        try:
            with self.get_connection() as conn:
                self._create_tables(conn)
                self._create_indexes(conn)
                conn.commit()
            
            self.logger.info(f"資料庫初始化完成: {self.db_path}")
            
        except Exception as e:
            self.logger.error(f"資料庫初始化失敗: {e}")
            raise DatabaseError(f"資料庫初始化失敗: {e}")
    
    @contextmanager
    def get_connection(self):
        """取得資料庫連接 (上下文管理器)
        
        Yields:
            sqlite3.Connection: 資料庫連接
        """
        thread_id = threading.get_ident()
        
        with self._lock:
            if thread_id not in self._connections:
                try:
                    conn = sqlite3.connect(
                        str(self.db_path),
                        check_same_thread=False,
                        timeout=30.0
                    )
                    conn.row_factory = sqlite3.Row
                    # 啟用外鍵約束
                    conn.execute("PRAGMA foreign_keys = ON")
                    # 設定 WAL 模式提升並發性能
                    conn.execute("PRAGMA journal_mode = WAL")
                    # 設定同步模式
                    conn.execute("PRAGMA synchronous = NORMAL")
                    
                    self._connections[thread_id] = conn
                    
                except Exception as e:
                    raise DatabaseError(f"建立資料庫連接失敗: {e}")
            
            conn = self._connections[thread_id]
        
        try:
            yield conn
        except Exception as e:
            conn.rollback()
            raise DatabaseError(f"資料庫操作失敗: {e}")
    
    def _create_tables(self, conn: sqlite3.Connection) -> None:
        """建立資料表
        
        Args:
            conn: 資料庫連接
        """
        # 頻道表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                channel_id TEXT PRIMARY KEY,
                guild_id TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_active DATETIME DEFAULT CURRENT_TIMESTAMP,
                message_count INTEGER DEFAULT 0,
                vector_enabled BOOLEAN DEFAULT TRUE,
                config_profile TEXT DEFAULT 'auto',
                metadata TEXT
            )
        """)
        
        # 訊息表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                content TEXT NOT NULL,
                content_processed TEXT,
                timestamp DATETIME NOT NULL,
                message_type TEXT DEFAULT 'user',
                relevance_score REAL DEFAULT 0.0,
                metadata TEXT,
                FOREIGN KEY (channel_id) REFERENCES channels(channel_id) ON DELETE CASCADE
            )
        """)
        
        # 向量嵌入表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                embedding_id TEXT PRIMARY KEY,
                message_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                vector_data BLOB,
                model_version TEXT,
                dimension INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (message_id) REFERENCES messages(message_id) ON DELETE CASCADE,
                FOREIGN KEY (channel_id) REFERENCES channels(channel_id) ON DELETE CASCADE
            )
        """)
        
        # 系統配置表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_config (
                config_key TEXT PRIMARY KEY,
                config_value TEXT,
                config_type TEXT DEFAULT 'string',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 效能指標表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS performance_metrics (
                metric_id TEXT PRIMARY KEY,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                metric_type TEXT NOT NULL,
                value REAL NOT NULL,
                metadata TEXT
            )
        """)
    
    def _create_indexes(self, conn: sqlite3.Connection) -> None:
        """建立索引
        
        Args:
            conn: 資料庫連接
        """
        indexes = [
            # 訊息表索引
            "CREATE INDEX IF NOT EXISTS idx_messages_channel_id ON messages(channel_id)",
            "CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_messages_channel_timestamp ON messages(channel_id, timestamp)",
            
            # 嵌入表索引
            "CREATE INDEX IF NOT EXISTS idx_embeddings_channel_id ON embeddings(channel_id)",
            "CREATE INDEX IF NOT EXISTS idx_embeddings_message_id ON embeddings(message_id)",
            "CREATE INDEX IF NOT EXISTS idx_embeddings_model_version ON embeddings(model_version)",
            
            # 頻道表索引
            "CREATE INDEX IF NOT EXISTS idx_channels_guild_id ON channels(guild_id)",
            "CREATE INDEX IF NOT EXISTS idx_channels_last_active ON channels(last_active)",
            
            # 效能指標索引
            "CREATE INDEX IF NOT EXISTS idx_performance_metrics_type ON performance_metrics(metric_type)",
            "CREATE INDEX IF NOT EXISTS idx_performance_metrics_timestamp ON performance_metrics(timestamp)",
        ]
        
        for index_sql in indexes:
            conn.execute(index_sql)
    
    # 頻道操作方法
    def create_channel(
        self, 
        channel_id: str, 
        guild_id: str,
        vector_enabled: bool = True,
        config_profile: str = "auto"
    ) -> bool:
        """建立頻道記錄
        
        Args:
            channel_id: 頻道 ID
            guild_id: 伺服器 ID
            vector_enabled: 是否啟用向量搜尋
            config_profile: 配置檔案名稱
            
        Returns:
            bool: 是否成功建立
        """
        try:
            with self.get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO channels 
                    (channel_id, guild_id, vector_enabled, config_profile)
                    VALUES (?, ?, ?, ?)
                """, (channel_id, guild_id, vector_enabled, config_profile))
                conn.commit()
            
            self.logger.info(f"建立頻道記錄: {channel_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"建立頻道記錄失敗: {e}")
            raise DatabaseError(f"建立頻道記錄失敗: {e}", operation="create_channel", table="channels")
    
    def get_channel(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """取得頻道資訊
        
        Args:
            channel_id: 頻道 ID
            
        Returns:
            Optional[Dict[str, Any]]: 頻道資訊，若不存在則返回 None
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM channels WHERE channel_id = ?",
                    (channel_id,)
                )
                row = cursor.fetchone()
                
                if row:
                    return dict(row)
                return None
                
        except Exception as e:
            self.logger.error(f"取得頻道資訊失敗: {e}")
            raise DatabaseError(f"取得頻道資訊失敗: {e}", operation="get_channel", table="channels")
    
    def update_channel_activity(self, channel_id: str) -> bool:
        """更新頻道活動時間
        
        Args:
            channel_id: 頻道 ID
            
        Returns:
            bool: 是否成功更新
        """
        try:
            with self.get_connection() as conn:
                conn.execute("""
                    UPDATE channels 
                    SET last_active = CURRENT_TIMESTAMP,
                        message_count = message_count + 1
                    WHERE channel_id = ?
                """, (channel_id,))
                conn.commit()
            
            return True
            
        except Exception as e:
            self.logger.error(f"更新頻道活動時間失敗: {e}")
            raise DatabaseError(f"更新頻道活動時間失敗: {e}", operation="update_activity", table="channels")
    
    # 訊息操作方法
    def store_message(
        self,
        message_id: str,
        channel_id: str,
        user_id: str,
        content: str,
        timestamp: datetime,
        message_type: str = "user",
        content_processed: Optional[str] = None,
        metadata: Optional[str] = None
    ) -> bool:
        """儲存訊息
        
        Args:
            message_id: 訊息 ID
            channel_id: 頻道 ID
            user_id: 使用者 ID
            content: 訊息內容
            timestamp: 時間戳記
            message_type: 訊息類型
            content_processed: 處理後的內容
            metadata: 元資料
            
        Returns:
            bool: 是否成功儲存
        """
        try:
            with self.get_connection() as conn:
                # 確保頻道存在
                self._ensure_channel_exists(conn, channel_id)
                
                conn.execute("""
                    INSERT OR REPLACE INTO messages 
                    (message_id, channel_id, user_id, content, content_processed, 
                     timestamp, message_type, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (message_id, channel_id, user_id, content, content_processed,
                      timestamp, message_type, metadata))
                
                # 更新頻道活動
                conn.execute("""
                    UPDATE channels 
                    SET last_active = ?,
                        message_count = message_count + 1
                    WHERE channel_id = ?
                """, (timestamp, channel_id))
                
                conn.commit()
            
            self.logger.debug(f"儲存訊息: {message_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"儲存訊息失敗: {e}")
            raise DatabaseError(f"儲存訊息失敗: {e}", operation="store_message", table="messages")
    
    def get_messages(
        self,
        channel_id: str,
        limit: int = 100,
        before: Optional[datetime] = None,
        after: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """取得頻道訊息
        
        Args:
            channel_id: 頻道 ID
            limit: 返回數量限制
            before: 在此時間之前
            after: 在此時間之後
            
        Returns:
            List[Dict[str, Any]]: 訊息列表
        """
        try:
            with self.get_connection() as conn:
                query = "SELECT * FROM messages WHERE channel_id = ?"
                params = [channel_id]
                
                if before:
                    query += " AND timestamp < ?"
                    params.append(before)
                
                if after:
                    query += " AND timestamp > ?"
                    params.append(after)
                
                query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)
                
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            self.logger.error(f"取得頻道訊息失敗: {e}")
            raise DatabaseError(f"取得頻道訊息失敗: {e}", operation="get_messages", table="messages")
    
    def get_messages_by_ids(self, message_ids: List[str]) -> List[Dict[str, Any]]:
        """根據訊息 ID 批次查詢訊息
        
        Args:
            message_ids: 訊息 ID 列表
            
        Returns:
            List[Dict[str, Any]]: 訊息資料列表
        """
        if not message_ids:
            return []
        
        try:
            with self.get_connection() as conn:
                # 建立 IN 查詢的佔位符
                placeholders = ','.join('?' * len(message_ids))
                query = f"SELECT * FROM messages WHERE message_id IN ({placeholders})"
                
                cursor = conn.execute(query, message_ids)
                rows = cursor.fetchall()
                
                # 轉換為字典列表
                messages = [dict(row) for row in rows]
                
                # 記錄查詢結果統計
                self.logger.debug(f"批次查詢 {len(message_ids)} 個訊息 ID，找到 {len(messages)} 個結果")
                
                return messages
                
        except Exception as e:
            self.logger.error(f"批次查詢訊息失敗: {e}")
            raise DatabaseError(f"批次查詢訊息失敗: {e}", operation="get_messages_by_ids", table="messages")
    
    def _ensure_channel_exists(self, conn: sqlite3.Connection, channel_id: str) -> None:
        """確保頻道記錄存在
        
        Args:
            conn: 資料庫連接
            channel_id: 頻道 ID
        """
        cursor = conn.execute("SELECT 1 FROM channels WHERE channel_id = ?", (channel_id,))
        if not cursor.fetchone():
            # 建立基本頻道記錄
            conn.execute("""
                INSERT INTO channels (channel_id, guild_id)
                VALUES (?, ?)
            """, (channel_id, "unknown"))
    
    # 配置操作方法
    def set_config(self, key: str, value: str, config_type: str = "string") -> bool:
        """設定配置值
        
        Args:
            key: 配置鍵
            value: 配置值
            config_type: 配置類型
            
        Returns:
            bool: 是否成功設定
        """
        try:
            with self.get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO memory_config 
                    (config_key, config_value, config_type, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """, (key, value, config_type))
                conn.commit()
            
            return True
            
        except Exception as e:
            self.logger.error(f"設定配置失敗: {e}")
            raise DatabaseError(f"設定配置失敗: {e}", operation="set_config", table="memory_config")
    
    def get_config(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """取得配置值
        
        Args:
            key: 配置鍵
            default: 預設值
            
        Returns:
            Optional[str]: 配置值
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT config_value FROM memory_config WHERE config_key = ?",
                    (key,)
                )
                row = cursor.fetchone()
                
                if row:
                    return row[0]
                return default
                
        except Exception as e:
            self.logger.error(f"取得配置失敗: {e}")
            raise DatabaseError(f"取得配置失敗: {e}", operation="get_config", table="memory_config")
    
    # 效能指標方法
    def record_metric(
        self,
        metric_type: str,
        value: float,
        metadata: Optional[str] = None
    ) -> bool:
        """記錄效能指標
        
        Args:
            metric_type: 指標類型
            value: 指標值
            metadata: 元資料
            
        Returns:
            bool: 是否成功記錄
        """
        try:
            metric_id = f"{metric_type}_{datetime.now().isoformat()}"
            
            with self.get_connection() as conn:
                conn.execute("""
                    INSERT INTO performance_metrics 
                    (metric_id, metric_type, value, metadata)
                    VALUES (?, ?, ?, ?)
                """, (metric_id, metric_type, value, metadata))
                conn.commit()
            
            return True
            
        except Exception as e:
            self.logger.error(f"記錄效能指標失敗: {e}")
            raise DatabaseError(f"記錄效能指標失敗: {e}", operation="record_metric", table="performance_metrics")
    
    def cleanup_old_data(self, retention_days: int = 90) -> int:
        """清理舊資料
        
        Args:
            retention_days: 保留天數
            
        Returns:
            int: 清理的記錄數
        """
        try:
            cutoff_date = datetime.now().timestamp() - (retention_days * 24 * 3600)
            
            with self.get_connection() as conn:
                # 清理舊的效能指標
                cursor = conn.execute("""
                    DELETE FROM performance_metrics 
                    WHERE timestamp < datetime(?, 'unixepoch')
                """, (cutoff_date,))
                
                deleted_count = cursor.rowcount
                conn.commit()
            
            self.logger.info(f"清理 {deleted_count} 筆舊資料")
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"清理舊資料失敗: {e}")
            raise DatabaseError(f"清理舊資料失敗: {e}", operation="cleanup", table="performance_metrics")
    
    def close_connections(self) -> None:
        """關閉所有資料庫連接"""
        with self._lock:
            for conn in self._connections.values():
                try:
                    conn.close()
                except Exception as e:
                    self.logger.warning(f"關閉連接時發生錯誤: {e}")
            
            self._connections.clear()
        
        self.logger.info("所有資料庫連接已關閉")