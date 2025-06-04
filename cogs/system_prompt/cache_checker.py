"""
快取一致性檢查工具

提供快取系統的一致性檢查和修復功能
"""

import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class CacheConsistencyChecker:
    """快取一致性檢查器"""
    
    def __init__(self, cache_manager):
        self.cache_manager = cache_manager
    
    def check_cache_consistency(self, guild_id: str, channel_id: str, 
                              expected_content: str) -> Dict[str, Any]:
        """
        檢查快取一致性
        
        Args:
            guild_id: 伺服器 ID
            channel_id: 頻道 ID
            expected_content: 期望的內容
            
        Returns:
            檢查結果
        """
        result = {
            'is_consistent': False,
            'cached_content': None,
            'expected_content': expected_content,
            'cache_key': None,
            'issues': []
        }
        
        try:
            # 生成快取鍵
            cache_key = self.cache_manager.get_cache_key(guild_id, channel_id)
            result['cache_key'] = cache_key
            
            # 取得快取內容
            cached_content = self.cache_manager.get(guild_id, channel_id)
            result['cached_content'] = cached_content
            
            if cached_content is None:
                result['issues'].append("快取中沒有內容")
            elif cached_content == expected_content:
                result['is_consistent'] = True
                logger.info(f"✅ 快取一致性檢查通過: {cache_key}")
            else:
                result['issues'].append("快取內容與期望內容不一致")
                logger.warning(f"⚠️ 快取一致性檢查失敗: {cache_key}")
        
        except Exception as e:
            error_msg = f"快取一致性檢查發生錯誤: {str(e)}"
            result['issues'].append(error_msg)
            logger.error(error_msg)
        
        return result
    
    def force_cache_refresh(self, guild_id: str, channel_id: str) -> bool:
        """
        強制重新整理快取
        
        Args:
            guild_id: 伺服器 ID
            channel_id: 頻道 ID
            
        Returns:
            是否成功
        """
        try:
            # 清除舊快取
            self.cache_manager.invalidate(guild_id, channel_id)
            logger.info(f"✅ 已清除快取: {guild_id}:{channel_id}")
            
            # 等待一小段時間確保清除完成
            time.sleep(0.1)
            
            return True
            
        except Exception as e:
            logger.error(f"強制重新整理快取失敗: {e}")
            return False
    
    def get_cache_statistics(self) -> Dict[str, Any]:
        """取得快取統計資訊"""
        try:
            cache_data = self.cache_manager.cache
            total_items = len(cache_data)
            
            # 統計快取項目
            expired_items = 0
            current_time = time.time()
            
            for key, (timestamp, content) in cache_data.items():
                if current_time - timestamp >= self.cache_manager.ttl:
                    expired_items += 1
            
            return {
                'total_items': total_items,
                'active_items': total_items - expired_items,
                'expired_items': expired_items,
                'ttl': self.cache_manager.ttl
            }
            
        except Exception as e:
            logger.error(f"取得快取統計失敗: {e}")
            return {'error': str(e)}
