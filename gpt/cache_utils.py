"""
Gemini API 快取工具模組

提供便捷的快取管理功能，支援 Discord 機器人的性能優化。
"""

import logging
import hashlib
from typing import Optional, Dict, Any, List
from gpt.gemini_api import get_cache_manager, GeminiError

logger = logging.getLogger(__name__)

class CacheHelper:
    """快取輔助工具類"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    @staticmethod
    def create_system_cache(system_prompt: str, 
                           ttl: str = "3600s",
                           display_name: str = None) -> Optional[Any]:
        """創建系統指令快取
        
        Args:
            system_prompt: 系統指令
            ttl: 存留時間
            display_name: 顯示名稱
            
        Returns:
            快取物件或 None
        """
        try:
            cache_mgr = get_cache_manager()
            if not cache_mgr:
                logger.warning("快取管理器未初始化")
                return None
            
            # 檢查是否已有相同的系統指令快取
            existing_cache = cache_mgr.find_cache_by_system_instruction(system_prompt)
            if existing_cache:
                logger.info("使用現有系統指令快取")
                return existing_cache
            
            # 創建新快取
            if display_name is None:
                # 創建基於內容的顯示名稱
                content_hash = hashlib.md5(system_prompt.encode()).hexdigest()[:8]
                display_name = f'discord_system_{content_hash}'
            
            cache = cache_mgr.create_cache(
                model='models/gemini-2.0-flash',
                system_instruction=system_prompt,
                contents=[],
                ttl=ttl,
                display_name=display_name
            )
            
            if cache:
                logger.info(f"成功創建系統指令快取: {display_name}")
            else:
                logger.warning("系統指令快取創建失敗")
                
            return cache
            
        except Exception as e:
            logger.error(f"創建系統指令快取失敗: {str(e)}")
            return None
    
    @staticmethod
    def create_conversation_cache(system_prompt: str,
                                conversation_history: List[Dict],
                                ttl: str = "1800s",
                                display_name: str = None) -> Optional[Any]:
        """創建對話歷史快取
        
        Args:
            system_prompt: 系統指令
            conversation_history: 對話歷史
            ttl: 存留時間（預設30分鐘）
            display_name: 顯示名稱
            
        Returns:
            快取物件或 None
        """
        try:
            cache_mgr = get_cache_manager()
            if not cache_mgr:
                logger.warning("快取管理器未初始化")
                return None
            
            # 為對話歷史創建內容摘要
            history_summary = ""
            for msg in conversation_history[-10:]:  # 只取最近10條對話
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')[:100]  # 限制長度
                history_summary += f"{role}: {content}\n"
            
            if display_name is None:
                # 創建基於內容的顯示名稱
                content_hash = hashlib.md5(
                    (system_prompt + history_summary).encode()
                ).hexdigest()[:8]
                display_name = f'discord_conv_{content_hash}'
            
            # 構建快取內容（包含系統指令和對話歷史摘要）
            cache_content = f"{system_prompt}\n\n=== 對話上下文 ===\n{history_summary}"
            
            cache = cache_mgr.create_cache(
                model='models/gemini-2.0-flash',
                system_instruction=cache_content,
                contents=[],
                ttl=ttl,
                display_name=display_name
            )
            
            if cache:
                logger.info(f"成功創建對話快取: {display_name}")
            else:
                logger.warning("對話快取創建失敗")
                
            return cache
            
        except Exception as e:
            logger.error(f"創建對話快取失敗: {str(e)}")
            return None
    
    @staticmethod
    def cleanup_old_caches() -> int:
        """清理舊的快取
        
        Returns:
            int: 清理的快取數量
        """
        try:
            cache_mgr = get_cache_manager()
            if not cache_mgr:
                return 0
                
            return cache_mgr.cleanup_expired_caches()
            
        except Exception as e:
            logger.error(f"清理快取失敗: {str(e)}")
            return 0
    
    @staticmethod
    def get_cache_statistics() -> Dict[str, Any]:
        """獲取快取統計資訊
        
        Returns:
            dict: 統計資訊
        """
        try:
            cache_mgr = get_cache_manager()
            if not cache_mgr:
                return {"error": "快取管理器未初始化"}
                
            stats = cache_mgr.get_cache_stats()
            
            # 添加額外的統計資訊
            stats['status'] = 'active'
            stats['last_cleanup'] = "未知"
            
            return stats
            
        except Exception as e:
            logger.error(f"獲取快取統計失敗: {str(e)}")
            return {"error": str(e)}

# 全域快取助手實例
cache_helper = CacheHelper()

def get_system_cache(system_prompt: str, ttl: str = "3600s") -> Optional[Any]:
    """便捷函數：獲取或創建系統指令快取"""
    return cache_helper.create_system_cache(system_prompt, ttl)

def get_conversation_cache(system_prompt: str, 
                          conversation_history: List[Dict],
                          ttl: str = "1800s") -> Optional[Any]:
    """便捷函數：獲取或創建對話快取"""
    return cache_helper.create_conversation_cache(system_prompt, conversation_history, ttl)

def cleanup_caches() -> int:
    """便捷函數：清理過期快取"""
    return cache_helper.cleanup_old_caches()

def get_cache_info() -> Dict[str, Any]:
    """便捷函數：獲取快取統計資訊"""
    return cache_helper.get_cache_statistics()