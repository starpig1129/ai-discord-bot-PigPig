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
        
        # 延遲初始化使用者管理器（避免循環導入）
        self._user_manager = None
        
        # 確保資料庫目錄存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 初始化資料庫
        self._initialize_database()
    
    @property
    def user_manager(self):
        """取得使用者管理器（延遲初始化）"""
        if self._user_manager is None:
            from .user_manager import SQLiteUserManager
            self._user_manager = SQLiteUserManager(self)
        return self._user_manager
    
    def _initialize_database(self) -> None:
        """初始化資料庫結構"""
        try:
            with self.get_connection() as conn:
                # 建立資料表和索引
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
        
        # 使用者基本資料表 (新增)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                display_name TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_active DATETIME DEFAULT CURRENT_TIMESTAMP,
                user_data TEXT,
                preferences TEXT
            )
        """)
        
        # 使用者詳細檔案表 (新增)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                profile_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                profile_data TEXT,
                interaction_history TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
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
            
            # 使用者表索引 (新增)
            "CREATE INDEX IF NOT EXISTS idx_users_last_active ON users(last_active)",
            "CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id)",
            
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
                
                query += " ORDER BY timestamp DESC"
                
                if limit is not None:
                    query += " LIMIT ?"
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

    def add_messages(self, messages: List[Dict[str, Any]]) -> bool:
        """批次儲存訊息

        Args:
            messages: 訊息資料字典的列表

        Returns:
            bool: 是否成功儲存
        """
        if not messages:
            return True

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 準備訊息資料
                message_data = [
                    (
                        msg['message_id'], msg['channel_id'], msg['user_id'],
                        msg['content'], msg.get('content_processed'), msg['timestamp'],
                        msg.get('message_type', 'user'), msg.get('metadata')
                    )
                    for msg in messages
                ]
                
                # 批次插入訊息
                cursor.executemany("""
                    INSERT OR REPLACE INTO messages
                    (message_id, channel_id, user_id, content, content_processed,
                     timestamp, message_type, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, message_data)

                # 批次更新頻道活動
                channel_updates = {}
                for msg in messages:
                    channel_id = msg['channel_id']
                    if channel_id not in channel_updates:
                        channel_updates[channel_id] = {'count': 0, 'last_active': msg['timestamp']}
                    channel_updates[channel_id]['count'] += 1
                    if msg['timestamp'] > channel_updates[channel_id]['last_active']:
                        channel_updates[channel_id]['last_active'] = msg['timestamp']

                for channel_id, update in channel_updates.items():
                    self._ensure_channel_exists(conn, channel_id)
                    cursor.execute("""
                        UPDATE channels
                        SET last_active = ?,
                            message_count = message_count + ?
                        WHERE channel_id = ?
                    """, (update['last_active'], update['count'], channel_id))

                conn.commit()
                self.logger.debug(f"成功批次儲存 {len(messages)} 條訊息")
                return True

        except Exception as e:
            self.logger.error(f"批次儲存訊息失敗: {e}")
            raise DatabaseError(f"批次儲存訊息失敗: {e}", operation="add_messages", table="messages")
    
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
            List[Dict[str, Any]]: 訊息列表
        """
        if not keywords:
            return []
        
        try:
            with self.get_connection() as conn:
                # 基礎查詢
                query = "SELECT * FROM messages WHERE channel_id = ?"
                params: List[Any] = [channel_id]
                
                # 時間範圍過濾
                if before:
                    query += " AND timestamp < ?"
                    params.append(before)
                if after:
                    query += " AND timestamp > ?"
                    params.append(after)
                
                # 關鍵字過濾
                keyword_clauses = " AND ".join(["(content LIKE ? OR content_processed LIKE ?)" for _ in keywords])
                query += f" AND ({keyword_clauses})"
                for keyword in keywords:
                    like_pattern = f"%{keyword}%"
                    params.extend([like_pattern, like_pattern])
                
                # 排序和限制
                query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)
                
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()
                
                # 計算匹配分數並排序
                messages = [dict(row) for row in rows]
                for msg in messages:
                    msg['match_score'] = self._calculate_keyword_match_score(msg['content'], keywords)
                
                messages.sort(key=lambda x: x['match_score'], reverse=True)
                
                return messages
                
        except Exception as e:
            self.logger.error(f"關鍵字搜尋失敗: {e}")
            raise DatabaseError(f"關鍵字搜尋失敗: {e}", operation="search_by_keywords", table="messages")

    def _calculate_keyword_match_score(self, content: str, keywords: List[str]) -> float:
        """計算內容與關鍵字的匹配分數"""
        score = 0.0
        content_lower = content.lower()
        for keyword in keywords:
            if keyword.lower() in content_lower:
                score += 1.0
        return score / len(keywords) if keywords else 0.0

    def _ensure_channel_exists(self, conn: sqlite3.Connection, channel_id: str) -> None:
        """確保頻道存在，若不存在則建立"""
        cursor = conn.execute("SELECT 1 FROM channels WHERE channel_id = ?", (channel_id,))
        if cursor.fetchone() is None:
            # 假設 guild_id 可以從某處獲取，或設為預設值
            # 這裡我們暫時設為 'unknown'，實際應用中可能需要更複雜的邏輯
            conn.execute(
                "INSERT OR IGNORE INTO channels (channel_id, guild_id) VALUES (?, ?)",
                (channel_id, 'unknown')
            )

    # 配置操作方法
    def set_config(self, key: str, value: str, config_type: str = "string") -> bool:
        """設定配置值
        
        Args:
            key: 配置鍵
            value: 配置值
            config_type: 值類型
            
        Returns:
            bool: 是否成功設定
        """
        try:
            with self.get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO memory_config (config_key, config_value, config_type)
                    VALUES (?, ?, ?)
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
            Optional[str]: 配置值或預設值
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("SELECT config_value FROM memory_config WHERE config_key = ?", (key,))
                row = cursor.fetchone()
                if row:
                    return row['config_value']
                return default
        except Exception as e:
            self.logger.error(f"取得配置失敗: {e}")
            raise DatabaseError(f"取得配置失敗: {e}", operation="get_config", table="memory_config")

    # 效能指標操作
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
                    INSERT INTO performance_metrics (metric_id, metric_type, value, metadata)
                    VALUES (?, ?, ?, ?)
                """, (metric_id, metric_type, value, metadata))
                conn.commit()
            return True
        except Exception as e:
            self.logger.error(f"記錄效能指標失敗: {e}")
            raise DatabaseError(f"記錄效能指標失敗: {e}", operation="record_metric", table="performance_metrics")

    # 資料清理
    def cleanup_old_data(self, retention_days: int = 90) -> int:
        """清理舊資料
        
        Args:
            retention_days: 資料保留天數
            
        Returns:
            int: 刪除的訊息數量
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            deleted_count = 0
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE timestamp < ?",
                    (cutoff_date,)
                )
                count_row = cursor.fetchone()
                if count_row:
                    deleted_count = count_row[0]
                
                if deleted_count > 0:
                    conn.execute("DELETE FROM messages WHERE timestamp < ?", (cutoff_date,))
                    conn.commit()
                    self.logger.info(f"已清理 {deleted_count} 則舊訊息")
            
            return deleted_count
        except Exception as e:
            self.logger.error(f"清理舊資料失敗: {e}")
            raise DatabaseError(f"清理舊資料失敗: {e}", operation="cleanup", table="messages")

    # 統計資訊
    def get_channel_count(self) -> int:
        """取得頻道總數"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM channels")
                return cursor.fetchone()[0]
        except Exception as e:
            self.logger.error(f"取得頻道總數失敗: {e}")
            raise DatabaseError(f"取得頻道總數失敗: {e}", operation="get_count", table="channels")

    def get_message_count(self, channel_id: Optional[str] = None) -> int:
        """取得訊息總數
        
        Args:
            channel_id: (可選) 頻道 ID，若提供則返回該頻道的訊息數
            
        Returns:
            int: 訊息總數
        """
        try:
            with self.get_connection() as conn:
                if channel_id:
                    cursor = conn.execute("SELECT COUNT(*) FROM messages WHERE channel_id = ?", (channel_id,))
                else:
                    cursor = conn.execute("SELECT COUNT(*) FROM messages")
                return cursor.fetchone()[0]
        except Exception as e:
            self.logger.error(f"取得訊息總數失敗: {e}")
            raise DatabaseError(f"取得訊息總數失敗: {e}", operation="get_count", table="messages")

    def get_database_stats(self) -> Dict[str, Any]:
        """取得資料庫統計資訊"""
        try:
            with self.get_connection() as conn:
                stats = {}
                stats['channels'] = self.get_channel_count()
                stats['messages'] = self.get_message_count()
                
                # 取得資料庫檔案大小
                db_size = self.db_path.stat().st_size
                stats['db_size_mb'] = round(db_size / (1024 * 1024), 2)
                
                # 取得 WAL 檔案大小
                wal_path = self.db_path.with_suffix('.db-wal')
                if wal_path.exists():
                    wal_size = wal_path.stat().st_size
                    stats['wal_size_mb'] = round(wal_size / (1024 * 1024), 2)
                
                return stats
        except Exception as e:
            self.logger.error(f"取得資料庫統計資訊失敗: {e}")
            raise DatabaseError(f"取得資料庫統計資訊失敗: {e}", operation="get_stats")

    def get_all_message_ids(self) -> List[str]:
        """取得資料庫中所有訊息的 ID
        
        Returns:
            List[str]: 所有訊息 ID 的列表
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("SELECT message_id FROM messages")
                # 使用 cursor.fetchall() 取得所有結果
                rows = cursor.fetchall()
                # 從每行中提取第一個元素（message_id）
                return [row[0] for row in rows]
        except Exception as e:
            self.logger.error(f"取得所有訊息 ID 失敗: {e}")
            raise DatabaseError(f"取得所有訊息 ID 失敗: {e}", operation="get_all_message_ids", table="messages")

    def close_connections(self) -> None:
        """關閉所有資料庫連接"""
        with self._lock:
            for thread_id, conn in self._connections.items():
                try:
                    conn.close()
                except Exception as e:
                    self.logger.warning(f"關閉執行緒 {thread_id} 的連接時發生錯誤: {e}")
            self._connections.clear()
            self.logger.info("所有資料庫連接已關閉")

    # 對話片段操作
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
    ) -> str:
        """建立對話片段並返回其 ID
        
        Args:
            segment_id: 片段 ID
            channel_id: 頻道 ID
            start_time: 開始時間
            end_time: 結束時間
            message_count: 訊息數量
            semantic_coherence_score: 語義連貫性分數
            activity_level: 活躍度等級
            segment_summary: 片段摘要
            vector_data: 向量資料
            metadata: 元資料
            
        Returns:
            str: 新建立的片段 ID
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
            return segment_id
            
        except Exception as e:
            self.logger.error(f"建立對話片段失敗: {e}")
            raise DatabaseError(f"建立對話片段失敗: {e}", operation="create_segment", table="conversation_segments")

    def create_segment_with_messages(
        self,
        segment_data: Dict[str, Any],
        messages_data: List[Dict[str, Any]]
    ) -> str:
        """
        以原子操作建立對話片段、其包含的訊息以及它們之間的關聯。

        Args:
            segment_data: 包含對話片段主記錄所需資料的字典。
            messages_data: 要儲存並關聯到此片段的訊息資料字典列表。

        Returns:
            str: 成功建立的對話片段 ID。

        Raises:
            DatabaseError: 如果資料庫操作失敗。
        """
        segment_id = segment_data.get("segment_id")
        if not segment_id:
            raise ValueError("segment_data 中必須包含 'segment_id'")

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # 1. 批次儲存訊息 (如果有的話)
                if messages_data:
                    message_tuples = [
                        (
                            msg['message_id'], msg['channel_id'], msg['user_id'],
                            msg['content'], msg.get('content_processed'), msg['timestamp'],
                            msg.get('message_type', 'user'), msg.get('metadata')
                        )
                        for msg in messages_data
                    ]
                    cursor.executemany("""
                        INSERT OR IGNORE INTO messages
                        (message_id, channel_id, user_id, content, content_processed,
                         timestamp, message_type, metadata)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, message_tuples)
                    self.logger.debug(f"[{segment_id}] 原子操作：插入或忽略了 {len(messages_data)} 條訊息。")

                # 2. 建立對話片段主記錄
                cursor.execute("""
                    INSERT INTO conversation_segments (
                        segment_id, channel_id, start_time, end_time, message_count,
                        semantic_coherence_score, activity_level, segment_summary,
                        vector_data, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    segment_id,
                    segment_data['channel_id'],
                    segment_data['start_time'],
                    segment_data['end_time'],
                    segment_data['message_count'],
                    segment_data.get('semantic_coherence_score', 0.0),
                    segment_data.get('activity_level', 0.0),
                    segment_data.get('segment_summary'),
                    segment_data.get('vector_data'),
                    segment_data.get('metadata')
                ))
                self.logger.debug(f"[{segment_id}] 原子操作：插入了 conversation_segments 主記錄。")

                # 3. 批次建立訊息與片段的關聯
                message_ids = [msg['message_id'] for msg in messages_data]
                if message_ids:
                    message_links = [
                        (segment_id, message_id, i)
                        for i, message_id in enumerate(message_ids)
                    ]
                    cursor.executemany("""
                        INSERT INTO segment_messages (segment_id, message_id, position_in_segment)
                        VALUES (?, ?, ?)
                    """, message_links)
                    self.logger.debug(f"[{segment_id}] 原子操作：插入了 {len(message_links)} 條 segment_messages 關聯。")

                # 提交交易
                conn.commit()
                self.logger.info(f"原子性地建立了片段 {segment_id} 並儲存/關聯了 {len(messages_data)} 條訊息。")
                return segment_id

        except Exception as e:
            self.logger.error(f"原子性建立片段 {segment_id} 失敗: {e}", exc_info=True)
            # get_connection() 的上下文管理器會自動 rollback
            raise DatabaseError(f"原子性建立片段失敗: {e}", operation="create_segment_with_messages")

    def get_conversation_segments(
        self,
        channel_id: str,
        limit: int = 50,
        before: Optional[datetime] = None,
        after: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """取得對話片段
        
        Args:
            channel_id: 頻道 ID
            limit: 返回數量限制
            before: 在此時間之前
            after: 在此時間之後
            
        Returns:
            List[Dict[str, Any]]: 對話片段列表
        """
        try:
            with self.get_connection() as conn:
                query = "SELECT * FROM conversation_segments WHERE channel_id = ?"
                params = [channel_id]
                if before:
                    query += " AND end_time < ?"
                    params.append(before)
                if after:
                    query += " AND start_time > ?"
                    params.append(after)
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
        position: int
    ) -> bool:
        """將訊息新增到片段
        
        Args:
            segment_id: 片段 ID
            message_id: 訊息 ID
            position: 在片段中的位置
            
        Returns:
            bool: 是否成功新增
        """
        if not message_id:
            self.logger.error("新增訊息到片段失敗：無效的 message_id")
            return False
            
        try:
            with self.get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO segment_messages
                    (segment_id, message_id, position_in_segment)
                    VALUES (?, ?, ?)
                """, (segment_id, message_id, position))
                conn.commit()
            
            self.logger.debug(f"訊息 {message_id} 已新增到片段 {segment_id}")
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
                    SELECT m.* FROM messages m
                    JOIN segment_messages sm ON m.message_id = sm.message_id
                    WHERE sm.segment_id = ?
                    ORDER BY sm.position_in_segment
                """, (segment_id,))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            self.logger.error(f"取得片段訊息失敗: {e}")
            raise DatabaseError(f"取得片段訊息失敗: {e}", operation="get_segment_messages", table="segment_messages")
    def get_segment_to_message_map(self, segment_ids: List[str]) -> Dict[str, List[str]]:
        """根據片段 ID 列表，取得 segment_id 到 message_id 列表的映射
        
        Args:
            segment_ids: 片段 ID 列表
            
        Returns:
            Dict[str, List[str]]: segment_id 到 message_id 列表的映射
        """
        if not segment_ids:
            return {}
        
        try:
            with self.get_connection() as conn:
                placeholders = ','.join('?' * len(segment_ids))
                query = f"""
                    SELECT segment_id, message_id
                    FROM segment_messages
                    WHERE segment_id IN ({placeholders})
                    ORDER BY position_in_segment
                """
                cursor = conn.execute(query, segment_ids)
                rows = cursor.fetchall()
                
                result_map = {seg_id: [] for seg_id in segment_ids}
                for row in rows:
                    result_map[row['segment_id']].append(row['message_id'])
                
                self.logger.debug(f"從 {len(segment_ids)} 個片段 ID 中查詢到 {len(result_map)} 個映射")
                return result_map
                
        except Exception as e:
            self.logger.error(f"查詢 segment-to-message map 失敗: {e}")
            raise DatabaseError(f"查詢 segment-to-message map 失敗: {e}", operation="get_segment_to_message_map", table="segment_messages")


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
            raise DatabaseError(f"更新片段連貫性分數失敗: {e}", operation="update_segment_coherence", table="conversation_segments")

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
                    WHERE channel_id = ? AND start_time < ? AND end_time > ?
                    ORDER BY start_time
                """, (channel_id, end_time, start_time))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            self.logger.error(f"取得重疊片段失敗: {e}")
            raise DatabaseError(f"取得重疊片段失敗: {e}", operation="get_overlapping_segments", table="conversation_segments")

    def get_all_valid_segment_ids(self) -> List[str]:
        """
        從 conversation_segments 表中獲取所有有效的 segment_id。

        Returns:
            List[str]: 所有 segment_id 的列表。
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("SELECT segment_id FROM conversation_segments")
                rows = cursor.fetchall()
                return [row['segment_id'] for row in rows]
        except Exception as e:
            self.logger.error(f"獲取所有有效的 segment_id 失敗: {e}")
            raise DatabaseError(f"獲取所有有效的 segment_id 失敗: {e}", operation="get_all_valid_segment_ids", table="conversation_segments")