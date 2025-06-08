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
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                user_id TEXT,
                vector_data BLOB NOT NULL,
                model_version TEXT NOT NULL,
                dimension INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (message_id) REFERENCES messages(message_id) ON DELETE CASCADE
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
        
        # 對話片段表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversation_segments (
                segment_id TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL,
                start_time DATETIME NOT NULL,
                end_time DATETIME NOT NULL,
                message_count INTEGER NOT NULL,
                semantic_coherence_score REAL DEFAULT 0.0,
                activity_level REAL DEFAULT 0.0,
                segment_summary TEXT,
                vector_data BLOB,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT,
                FOREIGN KEY (channel_id) REFERENCES channels(channel_id) ON DELETE CASCADE
            )
        """)
        
        # 片段訊息關聯表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS segment_messages (
                segment_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                position_in_segment INTEGER NOT NULL,
                semantic_contribution_score REAL DEFAULT 0.0,
                PRIMARY KEY (segment_id, message_id),
                FOREIGN KEY (segment_id) REFERENCES conversation_segments(segment_id) ON DELETE CASCADE,
                FOREIGN KEY (message_id) REFERENCES messages(message_id) ON DELETE CASCADE
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
            
            # 對話片段索引
            "CREATE INDEX IF NOT EXISTS idx_conversation_segments_channel_id ON conversation_segments(channel_id)",
            "CREATE INDEX IF NOT EXISTS idx_conversation_segments_start_time ON conversation_segments(start_time)",
            "CREATE INDEX IF NOT EXISTS idx_conversation_segments_end_time ON conversation_segments(end_time)",
            "CREATE INDEX IF NOT EXISTS idx_conversation_segments_time_range ON conversation_segments(channel_id, start_time, end_time)",
            "CREATE INDEX IF NOT EXISTS idx_conversation_segments_coherence ON conversation_segments(semantic_coherence_score)",
            
            # 片段訊息關聯索引
            "CREATE INDEX IF NOT EXISTS idx_segment_messages_segment_id ON segment_messages(segment_id)",
            "CREATE INDEX IF NOT EXISTS idx_segment_messages_message_id ON segment_messages(message_id)",
            "CREATE INDEX IF NOT EXISTS idx_segment_messages_position ON segment_messages(segment_id, position_in_segment)",
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
    
    def search_messages_by_keywords(
        self,
        channel_id: str,
        keywords: List[str],
        limit: int = 10,
        before: Optional[datetime] = None,
        after: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """根據關鍵字搜尋訊息
        
        Args:
            channel_id: 頻道 ID
            keywords: 關鍵字列表
            limit: 返回數量限制
            before: 在此時間之前
            after: 在此時間之後
            
        Returns:
            List[Dict[str, Any]]: 匹配的訊息列表，包含匹配分數
        """
        if not keywords:
            return []
        
        try:
            with self.get_connection() as conn:
                # 建立基本查詢
                query_parts = ["SELECT *, 0 as match_score FROM messages WHERE channel_id = ?"]
                params = [channel_id]
                
                # 添加關鍵字搜尋條件
                keyword_conditions = []
                for keyword in keywords:
                    # 搜尋原始內容和處理後內容
                    keyword_conditions.append(
                        "(content LIKE ? OR content_processed LIKE ?)"
                    )
                    keyword_param = f"%{keyword}%"
                    params.extend([keyword_param, keyword_param])
                
                if keyword_conditions:
                    query_parts.append("AND (" + " OR ".join(keyword_conditions) + ")")
                
                # 添加時間過濾
                if before:
                    query_parts.append("AND timestamp < ?")
                    params.append(before)
                
                if after:
                    query_parts.append("AND timestamp > ?")
                    params.append(after)
                
                # 排序和限制
                query_parts.append("ORDER BY timestamp DESC LIMIT ?")
                params.append(limit)
                
                query = " ".join(query_parts)
                
                self.logger.debug(f"關鍵字搜尋查詢: {query}")
                self.logger.debug(f"搜尋參數: 關鍵字={keywords}, 頻道={channel_id}")
                
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()
                
                # 轉換為字典並計算匹配分數
                messages = []
                for row in rows:
                    message_dict = dict(row)
                    
                    # 計算關鍵字匹配分數
                    content = message_dict.get('content', '') or ''
                    content_processed = message_dict.get('content_processed', '') or ''
                    
                    match_score = self._calculate_keyword_match_score(
                        content, content_processed, keywords
                    )
                    message_dict['match_score'] = match_score
                    
                    messages.append(message_dict)
                
                # 按匹配分數排序
                messages.sort(key=lambda x: x['match_score'], reverse=True)
                
                self.logger.info(f"關鍵字搜尋完成: 找到 {len(messages)} 個結果")
                return messages
                
        except Exception as e:
            self.logger.error(f"關鍵字搜尋失敗: {e}")
            raise DatabaseError(f"關鍵字搜尋失敗: {e}", operation="search_messages_by_keywords", table="messages")
    
    def _calculate_keyword_match_score(
        self,
        content: str,
        content_processed: str,
        keywords: List[str]
    ) -> float:
        """計算關鍵字匹配分數
        
        Args:
            content: 原始內容
            content_processed: 處理後內容
            keywords: 關鍵字列表
            
        Returns:
            float: 匹配分數 (0.0-1.0)
        """
        if not keywords:
            return 0.0
        
        # 合併內容進行搜尋
        combined_content = f"{content} {content_processed}".lower()
        
        if not combined_content.strip():
            return 0.0
        
        total_score = 0.0
        content_length = len(combined_content)
        
        for keyword in keywords:
            keyword_lower = keyword.lower()
            
            # 計算關鍵字出現次數
            count = combined_content.count(keyword_lower)
            if count > 0:
                # 基礎分數：出現次數 / 內容長度
                base_score = min(count * len(keyword_lower) / content_length, 0.5)
                
                # 完整匹配加分
                if keyword_lower in combined_content:
                    base_score += 0.3
                
                # 開頭匹配加分
                if combined_content.startswith(keyword_lower):
                    base_score += 0.2
                
                total_score += base_score
        
        # 正規化分數
        return min(total_score / len(keywords), 1.0)
    
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
    
    def get_channel_count(self) -> int:
        """取得頻道總數
        
        Returns:
            int: 頻道總數
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(DISTINCT channel_id) FROM channels")
                result = cursor.fetchone()
                return result[0] if result else 0
                
        except Exception as e:
            self.logger.error(f"取得頻道總數失敗: {e}")
            return 0
    
    def get_message_count(self, channel_id: Optional[str] = None) -> int:
        """取得訊息總數
        
        Args:
            channel_id: 指定頻道 ID（可選）
            
        Returns:
            int: 訊息總數
        """
        try:
            with self.get_connection() as conn:
                if channel_id:
                    cursor = conn.execute(
                        "SELECT COUNT(*) FROM messages WHERE channel_id = ?",
                        (channel_id,)
                    )
                else:
                    cursor = conn.execute("SELECT COUNT(*) FROM messages")
                
                result = cursor.fetchone()
                return result[0] if result else 0
                
        except Exception as e:
            self.logger.error(f"取得訊息總數失敗: {e}")
            return 0
    
    def get_database_stats(self) -> Dict[str, Any]:
        """取得資料庫統計資訊
        
        Returns:
            Dict[str, Any]: 統計資訊
        """
        try:
            with self.get_connection() as conn:
                stats = {}
                
                # 基本計數統計
                cursor = conn.execute("SELECT COUNT(DISTINCT channel_id) FROM channels")
                stats['total_channels'] = cursor.fetchone()[0]
                
                cursor = conn.execute("SELECT COUNT(*) FROM messages")
                stats['total_messages'] = cursor.fetchone()[0]
                
                # 活躍統計（最近30天）
                cursor = conn.execute("""
                    SELECT COUNT(DISTINCT channel_id)
                    FROM messages
                    WHERE timestamp > datetime('now', '-30 days')
                """)
                stats['active_channels_30d'] = cursor.fetchone()[0]
                
                # 訊息類型統計
                cursor = conn.execute("""
                    SELECT message_type, COUNT(*)
                    FROM messages
                    GROUP BY message_type
                """)
                message_type_stats = dict(cursor.fetchall())
                stats['message_types'] = message_type_stats
                
                # 資料庫大小（近似值）
                cursor = conn.execute("SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()")
                result = cursor.fetchone()
                stats['database_size_bytes'] = result[0] if result else 0
                
                return stats
                
        except Exception as e:
            self.logger.error(f"取得資料庫統計失敗: {e}")
            return {
                'total_channels': 0,
                'total_messages': 0,
                'active_channels_30d': 0,
                'message_types': {},
                'database_size_bytes': 0
            }

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
    
    # 對話片段操作方法
    def create_conversation_segment(
        self,
        segment_id: str,
        channel_id: str,
        start_time: datetime,
        end_time: datetime,
        message_count: int,
        semantic_coherence_score: float = 0.0,
        activity_level: float = 0.0,
        segment_summary: Optional[str] = None,
        vector_data: Optional[bytes] = None,
        metadata: Optional[str] = None
    ) -> bool:
        """建立對話片段
        
        Args:
            segment_id: 片段 ID
            channel_id: 頻道 ID
            start_time: 開始時間
            end_time: 結束時間
            message_count: 訊息數量
            semantic_coherence_score: 語義連貫性分數
            activity_level: 活躍度
            segment_summary: 片段摘要
            vector_data: 向量資料
            metadata: 元資料
            
        Returns:
            bool: 是否成功建立
        """
        try:
            with self.get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO conversation_segments 
                    (segment_id, channel_id, start_time, end_time, message_count,
                     semantic_coherence_score, activity_level, segment_summary,
                     vector_data, metadata, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (segment_id, channel_id, start_time, end_time, message_count,
                      semantic_coherence_score, activity_level, segment_summary,
                      vector_data, metadata))
                conn.commit()
            
            self.logger.debug(f"建立對話片段: {segment_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"建立對話片段失敗: {e}")
            raise DatabaseError(f"建立對話片段失敗: {e}", operation="create_segment", table="conversation_segments")
    
    def get_conversation_segments(
        self,
        channel_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """取得對話片段
        
        Args:
            channel_id: 頻道 ID
            start_time: 開始時間篩選
            end_time: 結束時間篩選
            limit: 返回數量限制
            
        Returns:
            List[Dict[str, Any]]: 片段列表
        """
        try:
            with self.get_connection() as conn:
                query = "SELECT * FROM conversation_segments WHERE channel_id = ?"
                params = [channel_id]
                
                if start_time:
                    query += " AND end_time >= ?"
                    params.append(start_time)
                
                if end_time:
                    query += " AND start_time <= ?"
                    params.append(end_time)
                
                query += " ORDER BY start_time DESC LIMIT ?"
                params.append(limit)
                
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            self.logger.error(f"取得對話片段失敗: {e}")
            raise DatabaseError(f"取得對話片段失敗: {e}", operation="get_segments", table="conversation_segments")
    
    def add_message_to_segment(
        self,
        segment_id: str,
        message_id: str,
        position_in_segment: int,
        semantic_contribution_score: float = 0.0
    ) -> bool:
        """將訊息新增到片段
        
        Args:
            segment_id: 片段 ID
            message_id: 訊息 ID
            position_in_segment: 在片段中的位置
            semantic_contribution_score: 語義貢獻分數
            
        Returns:
            bool: 是否成功新增
        """
        try:
            with self.get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO segment_messages 
                    (segment_id, message_id, position_in_segment, semantic_contribution_score)
                    VALUES (?, ?, ?, ?)
                """, (segment_id, message_id, position_in_segment, semantic_contribution_score))
                conn.commit()
            
            return True
            
        except Exception as e:
            self.logger.error(f"新增訊息到片段失敗: {e}")
            raise DatabaseError(f"新增訊息到片段失敗: {e}", operation="add_message_to_segment", table="segment_messages")
    
    def get_segment_messages(self, segment_id: str) -> List[Dict[str, Any]]:
        """取得片段中的訊息
        
        Args:
            segment_id: 片段 ID
            
        Returns:
            List[Dict[str, Any]]: 訊息列表
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT m.*, sm.position_in_segment, sm.semantic_contribution_score
                    FROM messages m
                    JOIN segment_messages sm ON m.message_id = sm.message_id
                    WHERE sm.segment_id = ?
                    ORDER BY sm.position_in_segment
                """, (segment_id,))
                rows = cursor.fetchall()
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            self.logger.error(f"取得片段訊息失敗: {e}")
            raise DatabaseError(f"取得片段訊息失敗: {e}", operation="get_segment_messages", table="segment_messages")
    
    def update_segment_coherence(self, segment_id: str, coherence_score: float) -> bool:
        """更新片段語義連貫性分數
        
        Args:
            segment_id: 片段 ID
            coherence_score: 連貫性分數
            
        Returns:
            bool: 是否成功更新
        """
        try:
            with self.get_connection() as conn:
                conn.execute("""
                    UPDATE conversation_segments 
                    SET semantic_coherence_score = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE segment_id = ?
                """, (coherence_score, segment_id))
                conn.commit()
            
            return True
            
        except Exception as e:
            self.logger.error(f"更新片段連貫性分數失敗: {e}")
            raise DatabaseError(f"更新片段連貫性分數失敗: {e}", operation="update_coherence", table="conversation_segments")
    
    def get_overlapping_segments(
        self,
        channel_id: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict[str, Any]]:
        """取得重疊的對話片段
        
        Args:
            channel_id: 頻道 ID
            start_time: 開始時間
            end_time: 結束時間
            
        Returns:
            List[Dict[str, Any]]: 重疊的片段列表
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT * FROM conversation_segments
                    WHERE channel_id = ? 
                    AND NOT (end_time <= ? OR start_time >= ?)
                    ORDER BY start_time
                """, (channel_id, start_time, end_time))
                rows = cursor.fetchall()
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            self.logger.error(f"取得重疊片段失敗: {e}")
            raise DatabaseError(f"取得重疊片段失敗: {e}", operation="get_overlapping_segments", table="conversation_segments")
        self.logger.info("所有資料庫連接已關閉")