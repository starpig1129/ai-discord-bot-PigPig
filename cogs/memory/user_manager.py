"""SQLite 使用者管理器

實現智慧背景知識整合系統的使用者資訊管理功能，
支援從 MongoDB 遷移到 SQLite，並提供高效的使用者資料查詢和管理。
"""

import sqlite3
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from contextlib import contextmanager
import asyncio

from .exceptions import DatabaseError
from function import func


@dataclass
class UserInfo:
    """使用者資訊資料類別"""
    user_id: str
    display_name: str = ""
    user_data: Optional[str] = None
    last_active: Optional[datetime] = None
    profile_data: Optional[Dict] = None
    preferences: Optional[Dict] = None
    created_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        data = asdict(self)
        # 處理 datetime 物件
        if self.last_active:
            data['last_active'] = self.last_active.isoformat()
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserInfo':
        """從字典建立 UserInfo 實例"""
        # 處理 datetime 字串
        if data.get('last_active'):
            try:
                data['last_active'] = datetime.fromisoformat(data['last_active'])
            except (ValueError, TypeError):
                data['last_active'] = None
        
        if data.get('created_at'):
            try:
                data['created_at'] = datetime.fromisoformat(data['created_at'])
            except (ValueError, TypeError):
                data['created_at'] = None
        
        return cls(**data)


class SQLiteUserManager:
    """SQLite 使用者管理器
    
    負責管理 Discord 使用者的資訊，包括基本資料、檔案、偏好設定等。
    支援從 MongoDB 的資料遷移和高效的批量查詢操作。
    """
    
    def __init__(self, db_manager):
        """初始化使用者管理器
        
        Args:
            db_manager: 資料庫管理器實例
        """
        self.db_manager = db_manager
        self.logger = logging.getLogger(__name__)
        self._user_cache = {}  # 簡單的記憶體快取
        self._cache_size_limit = 1000  # 快取大小限制
        
        self._ensure_user_tables()
    
    def _ensure_user_tables(self):
        """確保使用者相關表格存在"""
        try:
            with self.db_manager.get_connection() as conn:
                # 建立 users 表格
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
                
                # 建立 user_profiles 表格
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_profiles (
                        profile_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        profile_data TEXT,
                        interaction_history TEXT,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(user_id)
                            ON DELETE CASCADE
                    )
                """)
                
                # 建立索引
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_users_user_id 
                    ON users(user_id)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_users_last_active 
                    ON users(last_active)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id 
                    ON user_profiles(user_id)
                """)
                
                conn.commit()
                self.logger.info("使用者資料表初始化完成")
                
        except Exception as e:
            asyncio.create_task(func.report_error(e, "使用者資料表建立失敗"))
            raise DatabaseError(f"建立使用者資料表失敗: {e}")
    
    async def get_user_info(self, user_id: str, use_cache: bool = True) -> Optional[UserInfo]:
        """取得使用者完整資訊
        
        Args:
            user_id: 使用者 ID
            use_cache: 是否使用快取
            
        Returns:
            UserInfo 物件或 None
        """
        # 檢查快取
        if use_cache and user_id in self._user_cache:
            return self._user_cache[user_id]
        
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT u.user_id, u.display_name, u.user_data,
                           u.last_active, u.preferences, u.created_at, up.profile_data
                    FROM users u
                    LEFT JOIN user_profiles up ON u.user_id = up.user_id
                    WHERE u.user_id = ?
                """, (user_id,))
                
                row = cursor.fetchone()
                if row:
                    # 解析 JSON 資料
                    preferences = None
                    if row[4]:
                        try:
                            preferences = json.loads(row[4])
                        except json.JSONDecodeError:
                            self.logger.warning(f"無法解析使用者 {user_id} 的偏好設定")
                    
                    profile_data = None
                    if row[6]:
                        try:
                            profile_data = json.loads(row[6])
                        except json.JSONDecodeError:
                            self.logger.warning(f"無法解析使用者 {user_id} 的檔案資料")
                    
                    # 處理時間欄位
                    last_active = None
                    if row[3]:
                        try:
                            last_active = datetime.fromisoformat(row[3])
                        except (ValueError, TypeError):
                            pass
                    
                    created_at = None
                    if row[5]:
                        try:
                            created_at = datetime.fromisoformat(row[5])
                        except (ValueError, TypeError):
                            pass
                    
                    user_info = UserInfo(
                        user_id=row[0],
                        display_name=row[1] or "",
                        user_data=row[2],
                        last_active=last_active,
                        preferences=preferences,
                        created_at=created_at,
                        profile_data=profile_data
                    )
                    
                    # 更新快取
                    if use_cache:
                        self._update_cache(user_id, user_info)
                    
                    return user_info
                
                return None
                
        except Exception as e:
            await func.report_error(e, f"使用者資訊檢索失敗 (使用者: {user_id})")
            return None
    
    async def get_multiple_users(self, user_ids: List[str], use_cache: bool = True) -> Dict[str, UserInfo]:
        """批量取得使用者資訊
        
        Args:
            user_ids: 使用者 ID 列表
            use_cache: 是否使用快取
            
        Returns:
            Dict[str, UserInfo]: 使用者 ID 對應的 UserInfo 字典
        """
        result = {}
        uncached_ids = []
        
        # 檢查快取
        if use_cache:
            for user_id in user_ids:
                if user_id in self._user_cache:
                    result[user_id] = self._user_cache[user_id]
                else:
                    uncached_ids.append(user_id)
        else:
            uncached_ids = user_ids
        
        # 查詢未快取的使用者
        if uncached_ids:
            try:
                placeholders = ','.join('?' for _ in uncached_ids)
                with self.db_manager.get_connection() as conn:
                    cursor = conn.execute(f"""
                        SELECT u.user_id, u.display_name, u.user_data,
                               u.last_active, u.preferences, u.created_at, up.profile_data
                        FROM users u
                        LEFT JOIN user_profiles up ON u.user_id = up.user_id
                        WHERE u.user_id IN ({placeholders})
                    """, uncached_ids)
                    
                    for row in cursor.fetchall():
                        # 解析資料（與 get_user_info 相同的邏輯）
                        preferences = None
                        if row[4]:
                            try:
                                preferences = json.loads(row[4])
                            except json.JSONDecodeError:
                                pass
                        
                        profile_data = None
                        if row[6]:
                            try:
                                profile_data = json.loads(row[6])
                            except json.JSONDecodeError:
                                pass
                        
                        last_active = None
                        if row[3]:
                            try:
                                last_active = datetime.fromisoformat(row[3])
                            except (ValueError, TypeError):
                                pass
                        
                        created_at = None
                        if row[5]:
                            try:
                                created_at = datetime.fromisoformat(row[5])
                            except (ValueError, TypeError):
                                pass
                        
                        user_info = UserInfo(
                            user_id=row[0],
                            display_name=row[1] or "",
                            user_data=row[2],
                            last_active=last_active,
                            preferences=preferences,
                            created_at=created_at,
                            profile_data=profile_data
                        )
                        
                        result[row[0]] = user_info
                        
                        # 更新快取
                        if use_cache:
                            self._update_cache(row[0], user_info)
                            
            except Exception as e:
                await func.report_error(e, "多使用者資訊檢索失敗")
        
        return result
    
    async def update_user_data(self, user_id: str, user_data: str, 
                              display_name: str = None, 
                              preferences: Dict = None) -> bool:
        """更新使用者資料
        
        Args:
            user_id: 使用者 ID
            user_data: 使用者資料
            display_name: 顯示名稱
            preferences: 偏好設定
            
        Returns:
            bool: 是否成功更新
        """
        try:
            with self.db_manager.get_connection() as conn:
                # 檢查使用者是否存在
                cursor = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
                exists = cursor.fetchone()
                
                preferences_json = json.dumps(preferences, ensure_ascii=False) if preferences else None
                
                if exists:
                    # 更新現有使用者
                    conn.execute("""
                        UPDATE users 
                        SET user_data = ?, 
                            display_name = COALESCE(?, display_name), 
                            preferences = COALESCE(?, preferences),
                            last_active = CURRENT_TIMESTAMP
                        WHERE user_id = ?
                    """, (user_data, display_name, preferences_json, user_id))
                else:
                    # 建立新使用者
                    conn.execute("""
                        INSERT INTO users (user_id, display_name, user_data, preferences)
                        VALUES (?, ?, ?, ?)
                    """, (user_id, display_name, user_data, preferences_json))
                
                conn.commit()
                
                # 清除快取
                if user_id in self._user_cache:
                    del self._user_cache[user_id]
                
                self.logger.info(f"使用者資料更新成功: {user_id}")
                return True
                
        except Exception as e:
            await func.report_error(e, f"使用者資料更新失敗 (使用者: {user_id})")
            return False
    
    async def update_user_activity(self, user_id: str, display_name: str = None) -> bool:
        """更新使用者活躍時間
        
        Args:
            user_id: 使用者 ID
            display_name: 顯示名稱（可選）
            
        Returns:
            bool: 是否成功更新
        """
        try:
            with self.db_manager.get_connection() as conn:
                # 確保使用者記錄存在
                cursor = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
                exists = cursor.fetchone()
                
                if exists:
                    # 更新活躍時間
                    conn.execute("""
                        UPDATE users 
                        SET last_active = CURRENT_TIMESTAMP,
                            display_name = COALESCE(?, display_name)
                        WHERE user_id = ?
                    """, (display_name, user_id))
                else:
                    # 建立新使用者記錄
                    conn.execute("""
                        INSERT INTO users (user_id, display_name)
                        VALUES (?, ?)
                    """, (user_id, display_name))
                
                conn.commit()
                
                # 清除快取
                if user_id in self._user_cache:
                    del self._user_cache[user_id]
                
                return True
                
        except Exception as e:
            await func.report_error(e, f"使用者活動更新失敗 (使用者: {user_id})")
            return False
    
    async def search_users_by_display_name(self, name_pattern: str, limit: int = 10) -> List[UserInfo]:
        """根據顯示名稱搜尋使用者
        
        Args:
            name_pattern: 名稱模式（支援 LIKE 搜尋）
            limit: 結果數量限制
            
        Returns:
            List[UserInfo]: 搜尋結果列表
        """
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT u.user_id, u.display_name, u.user_data,
                           u.last_active, u.preferences, u.created_at, up.profile_data
                    FROM users u
                    LEFT JOIN user_profiles up ON u.user_id = up.user_id
                    WHERE u.display_name LIKE ?
                    ORDER BY u.last_active DESC
                    LIMIT ?
                """, (f"%{name_pattern}%", limit))
                
                results = []
                for row in cursor.fetchall():
                    # 解析資料（與 get_user_info 相同的邏輯）
                    preferences = None
                    if row[4]:
                        try:
                            preferences = json.loads(row[4])
                        except json.JSONDecodeError:
                            pass
                    
                    profile_data = None
                    if row[6]:
                        try:
                            profile_data = json.loads(row[6])
                        except json.JSONDecodeError:
                            pass
                    
                    last_active = None
                    if row[3]:
                        try:
                            last_active = datetime.fromisoformat(row[3])
                        except (ValueError, TypeError):
                            pass
                    
                    created_at = None
                    if row[5]:
                        try:
                            created_at = datetime.fromisoformat(row[5])
                        except (ValueError, TypeError):
                            pass
                    
                    user_info = UserInfo(
                        user_id=row[0],
                        display_name=row[1] or "",
                        user_data=row[2],
                        last_active=last_active,
                        preferences=preferences,
                        created_at=created_at,
                        profile_data=profile_data
                    )
                    results.append(user_info)
                
                return results
                
        except Exception as e:
            await func.report_error(e, f"使用者搜尋失敗 (模式: {name_pattern})")
            return []
    
    async def get_user_statistics(self) -> Dict[str, Any]:
        """取得使用者統計資訊
        
        Returns:
            Dict[str, Any]: 統計資訊
        """
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT 
                        COUNT(*) as total_users,
                        COUNT(CASE WHEN user_data IS NOT NULL THEN 1 END) as users_with_data,
                        COUNT(CASE WHEN last_active > datetime('now', '-7 days') THEN 1 END) as active_users_7d,
                        COUNT(CASE WHEN last_active > datetime('now', '-30 days') THEN 1 END) as active_users_30d
                    FROM users
                """)
                
                row = cursor.fetchone()
                return {
                    "total_users": row[0],
                    "users_with_data": row[1],
                    "active_users_7d": row[2],
                    "active_users_30d": row[3],
                    "cache_size": len(self._user_cache)
                }
                
        except Exception as e:
            await func.report_error(e, "使用者統計資訊檢索失敗")
            return {}
    
    async def migrate_from_mongodb(self, mongodb_collection) -> int:
        """從 MongoDB 遷移資料到 SQLite
        
        Args:
            mongodb_collection: MongoDB 集合物件
            
        Returns:
            int: 成功遷移的使用者數量
        """
        try:
            self.logger.info("開始從 MongoDB 遷移使用者資料...")
            
            # 取得所有 MongoDB 資料
            mongodb_users = list(mongodb_collection.find({}))
            total_users = len(mongodb_users)
            
            if total_users == 0:
                self.logger.info("MongoDB 中沒有使用者資料需要遷移")
                return 0
            
            migrated_count = 0
            failed_count = 0
            
            for user_doc in mongodb_users:
                try:
                    user_id = user_doc.get('user_id')
                    user_data = user_doc.get('user_data')
                    
                    if user_id and user_data:
                        success = await self.update_user_data(user_id, user_data)
                        if success:
                            migrated_count += 1
                        else:
                            failed_count += 1
                    else:
                        self.logger.warning(f"跳過無效的使用者記錄: {user_doc.get('_id')}")
                        failed_count += 1
                        
                except Exception as e:
                    await func.report_error(e, f"MongoDB 使用者遷移失敗 (ID: {user_doc.get('_id')})")
                    failed_count += 1
            
            self.logger.info(f"MongoDB 遷移完成: {migrated_count} 成功, {failed_count} 失敗, 總計 {total_users}")
            return migrated_count
            
        except Exception as e:
            await func.report_error(e, "MongoDB 使用者遷移失敗")
            return 0
    
    def _update_cache(self, user_id: str, user_info: UserInfo):
        """更新記憶體快取
        
        Args:
            user_id: 使用者 ID
            user_info: 使用者資訊
        """
        try:
            # 檢查快取大小限制
            if len(self._user_cache) >= self._cache_size_limit:
                # 移除最舊的快取項目
                oldest_key = next(iter(self._user_cache))
                del self._user_cache[oldest_key]
            
            self._user_cache[user_id] = user_info
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "使用者快取更新失敗"))
    
    def clear_cache(self):
        """清除記憶體快取"""
        self._user_cache.clear()
        self.logger.info("使用者快取已清除")
    
    async def cleanup_inactive_users(self, days: int = 365) -> int:
        """清理非活躍使用者資料
        
        Args:
            days: 非活躍天數閾值
            
        Returns:
            int: 清理的使用者數量
        """
        try:
            with self.db_manager.get_connection() as conn:
                # 查詢要清理的使用者
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM users 
                    WHERE last_active < datetime('now', '-{} days')
                    OR last_active IS NULL
                """.format(days))
                
                count = cursor.fetchone()[0]
                
                if count > 0:
                    # 刪除非活躍使用者
                    conn.execute("""
                        DELETE FROM users 
                        WHERE last_active < datetime('now', '-{} days')
                        OR last_active IS NULL
                    """.format(days))
                    
                    conn.commit()
                    self.logger.info(f"已清理 {count} 個非活躍使用者")
                
                # 清除快取
                self.clear_cache()
                
                return count
                
        except Exception as e:
            await func.report_error(e, "非活躍使用者清理失敗")
            return 0


# 輔助函數
def extract_participant_ids(message, conversation_history: List[Dict]) -> set:
    """提取對話參與者 ID
    
    Args:
        message: Discord 訊息物件
        conversation_history: 對話歷史
        
    Returns:
        set: 參與者 ID 集合
    """
    participant_ids = {str(message.author.id)}
    
    # 從 @mentions 提取
    if hasattr(message, 'mentions'):
        for mention in message.mentions:
            participant_ids.add(str(mention.id))
    
    # 從近期對話歷史提取
    for msg in conversation_history[-10:]:  # 最近10條訊息
        if isinstance(msg, dict) and 'user_id' in msg:
            participant_ids.add(str(msg['user_id']))
        elif hasattr(msg, 'author'):
            participant_ids.add(str(msg.author.id))
    
    return participant_ids