"""對話片段搜尋增強器

實現智慧背景知識整合系統的對話片段搜尋功能，
增強現有記憶管理器的搜尋能力，加入參與者相關性評分。
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import re

from .memory_manager import MemoryManager, SearchQuery, SearchType
from .user_manager import UserInfo


@dataclass
class EnhancedSegment:
    """增強的對話片段"""
    content: str
    user_id: str
    timestamp: str
    relevance_score: float
    is_participant_related: bool
    user_display_name: str = ""
    channel_id: str = ""
    message_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return {
            "content": self.content,
            "user_id": self.user_id,
            "timestamp": self.timestamp,
            "relevance_score": self.relevance_score,
            "is_participant_related": self.is_participant_related,
            "user_display_name": self.user_display_name,
            "channel_id": self.channel_id,
            "message_id": self.message_id,
            "metadata": self.metadata
        }


@dataclass
class SearchContext:
    """搜尋上下文"""
    query: str
    channel_id: str
    participant_context: Dict[str, UserInfo]
    time_range: Optional[Dict[str, Any]] = None
    search_options: Dict[str, Any] = field(default_factory=dict)


class ConversationSegmentEnhancer:
    """對話片段增強器
    
    負責增強現有記憶管理器的搜尋功能，加入參與者相關性評分、
    時間相關性分析和內容質量評估。
    """
    
    def __init__(self, memory_manager: MemoryManager):
        """初始化對話片段增強器
        
        Args:
            memory_manager: 記憶管理器實例
        """
        self.memory_manager = memory_manager
        self.logger = logging.getLogger(__name__)
        
        # 搜尋配置
        self.default_limit = 10
        self.default_threshold = 0.5
        self.participant_score_boost = 0.2  # 參與者相關性加成
        self.recency_score_boost = 0.1      # 時間相關性加成
        
    async def search_enhanced_segments(self, 
                                     search_context: SearchContext) -> List[EnhancedSegment]:
        """增強的對話片段搜尋
        
        Args:
            search_context: 搜尋上下文
            
        Returns:
            List[EnhancedSegment]: 增強的對話片段列表
        """
        try:
            # 取得搜尋選項
            search_options = search_context.search_options
            limit = search_options.get('limit', self.default_limit)
            threshold = search_options.get('threshold', self.default_threshold)
            search_type = search_options.get('search_type', SearchType.HYBRID)
            
            # 建立搜尋查詢
            search_query = SearchQuery(
                text=search_context.query,
                channel_id=search_context.channel_id,
                search_type=search_type,
                limit=limit * 2,  # 取得更多結果以便後續篩選
                threshold=threshold,
                time_range=search_context.time_range
            )
            
            # 執行搜尋
            search_result = await self.memory_manager.search_memory(search_query)
            
            if not search_result or not search_result.messages:
                self.logger.info(f"搜尋無結果 (channel: {search_context.channel_id})")
                return []
            
            # 增強處理結果
            enhanced_segments = self._enhance_search_results(
                search_result, search_context
            )
            
            # 重新排序和篩選
            ranked_segments = self._rank_segments_by_relevance(
                enhanced_segments, search_context
            )
            
            # 限制最終結果數量
            return ranked_segments[:limit]
            
        except Exception as e:
            self.logger.error(f"搜尋增強對話片段失敗: {e}")
            return []
    
    def _enhance_search_results(self, 
                               search_result, 
                               search_context: SearchContext) -> List[EnhancedSegment]:
        """增強搜尋結果
        
        Args:
            search_result: 原始搜尋結果
            search_context: 搜尋上下文
            
        Returns:
            List[EnhancedSegment]: 增強的片段列表
        """
        enhanced_segments = []
        participant_ids = set(search_context.participant_context.keys())
        
        for i, message_data in enumerate(search_result.messages):
            try:
                # 基本資訊提取
                user_id = str(message_data.get("user_id", ""))
                content = message_data.get("content", "")
                timestamp = message_data.get("timestamp", "")
                channel_id = str(message_data.get("channel_id", ""))
                message_id = str(message_data.get("message_id", ""))
                
                # 相關性分數
                relevance_score = (search_result.relevance_scores[i] 
                                 if i < len(search_result.relevance_scores) else 0.0)
                
                # 參與者相關性
                is_participant_related = user_id in participant_ids
                
                # 取得使用者顯示名稱
                user_display_name = ""
                if user_id in search_context.participant_context:
                    user_info = search_context.participant_context[user_id]
                    user_display_name = user_info.display_name or f"User_{user_id}"
                
                # 建立增強片段
                segment = EnhancedSegment(
                    content=content,
                    user_id=user_id,
                    timestamp=timestamp,
                    relevance_score=relevance_score,
                    is_participant_related=is_participant_related,
                    user_display_name=user_display_name,
                    channel_id=channel_id,
                    message_id=message_id,
                    metadata=message_data.get("metadata", {})
                )
                
                enhanced_segments.append(segment)
                
            except Exception as e:
                self.logger.warning(f"處理搜尋結果項目失敗: {e}")
                continue
        
        return enhanced_segments
    
    def _rank_segments_by_relevance(self, 
                                   segments: List[EnhancedSegment], 
                                   search_context: SearchContext) -> List[EnhancedSegment]:
        """按相關性重新排序片段
        
        Args:
            segments: 片段列表
            search_context: 搜尋上下文
            
        Returns:
            List[EnhancedSegment]: 排序後的片段列表
        """
        try:
            def calculate_enhanced_score(segment: EnhancedSegment) -> float:
                """計算增強相關性分數"""
                base_score = segment.relevance_score
                
                # 參與者相關性加成
                participant_boost = (self.participant_score_boost 
                                   if segment.is_participant_related else 0)
                
                # 時間相關性加成
                recency_boost = self._calculate_recency_boost(segment.timestamp)
                
                # 內容質量加成
                quality_boost = self._calculate_content_quality_boost(
                    segment.content, search_context.query
                )
                
                # 計算最終分數
                enhanced_score = base_score + participant_boost + recency_boost + quality_boost
                
                # 更新片段的相關性分數
                segment.relevance_score = enhanced_score
                
                return enhanced_score
            
            # 排序片段
            sorted_segments = sorted(segments, key=calculate_enhanced_score, reverse=True)
            
            return sorted_segments
            
        except Exception as e:
            self.logger.error(f"排序片段失敗: {e}")
            return segments
    
    def _calculate_recency_boost(self, timestamp_str: str) -> float:
        """計算時間相關性加成
        
        Args:
            timestamp_str: 時間戳字串
            
        Returns:
            float: 時間相關性分數
        """
        try:
            if not timestamp_str:
                return 0.0
            
            # 解析時間戳
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            except ValueError:
                # 嘗試其他格式
                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            
            # 計算時間差（天數）
            now = datetime.now(timestamp.tzinfo)
            days_ago = (now - timestamp).days
            
            # 時間越近分數越高（最近7天內有加成）
            if days_ago <= 7:
                return self.recency_score_boost * (1.0 - days_ago / 7.0)
            else:
                return 0.0
                
        except Exception as e:
            self.logger.debug(f"計算時間相關性失敗: {e}")
            return 0.0
    
    def _calculate_content_quality_boost(self, content: str, query: str) -> float:
        """計算內容質量加成
        
        Args:
            content: 訊息內容
            query: 搜尋查詢
            
        Returns:
            float: 內容質量分數
        """
        try:
            if not content or not query:
                return 0.0
            
            quality_score = 0.0
            
            # 內容長度加成（適中長度的內容通常更有意義）
            content_length = len(content)
            if 20 <= content_length <= 200:
                quality_score += 0.05
            elif content_length > 200:
                quality_score += 0.02
            
            # 關鍵詞匹配度加成
            query_words = set(re.findall(r'\w+', query.lower()))
            content_words = set(re.findall(r'\w+', content.lower()))
            
            if query_words:
                match_ratio = len(query_words.intersection(content_words)) / len(query_words)
                quality_score += match_ratio * 0.1
            
            # 特殊內容類型檢測
            if self._is_meaningful_content(content):
                quality_score += 0.03
            
            return min(quality_score, 0.2)  # 限制最大加成
            
        except Exception as e:
            self.logger.debug(f"計算內容質量失敗: {e}")
            return 0.0
    
    def _is_meaningful_content(self, content: str) -> bool:
        """檢測是否為有意義的內容
        
        Args:
            content: 訊息內容
            
        Returns:
            bool: 是否為有意義的內容
        """
        try:
            # 過濾掉純表情符號、單字回應等
            if len(content.strip()) < 10:
                return False
            
            # 檢測是否包含問號（問題通常更有意義）
            if '?' in content or '？' in content:
                return True
            
            # 檢測是否包含關鍵詞
            meaningful_keywords = [
                '計劃', '專案', '會議', '時間', '安排', '討論',
                '問題', '解決', '建議', '想法', '目標', '進度'
            ]
            
            content_lower = content.lower()
            for keyword in meaningful_keywords:
                if keyword in content_lower:
                    return True
            
            return False
            
        except Exception:
            return False
    
    async def search_by_user(self, 
                           user_id: str, 
                           channel_id: str,
                           limit: int = 10) -> List[EnhancedSegment]:
        """根據使用者 ID 搜尋相關片段
        
        Args:
            user_id: 使用者 ID
            channel_id: 頻道 ID
            limit: 結果數量限制
            
        Returns:
            List[EnhancedSegment]: 搜尋結果
        """
        try:
            # 建立使用者相關搜尋查詢
            search_query = SearchQuery(
                text="",  # 空查詢，主要按使用者篩選
                channel_id=channel_id,
                search_type=SearchType.RECENT,
                limit=limit,
                user_filter=user_id
            )
            
            search_result = await self.memory_manager.search_memory(search_query)
            
            if not search_result or not search_result.messages:
                return []
            
            # 轉換為增強片段
            enhanced_segments = []
            for i, message_data in enumerate(search_result.messages):
                if str(message_data.get("user_id", "")) == str(user_id):
                    segment = EnhancedSegment(
                        content=message_data.get("content", ""),
                        user_id=str(message_data.get("user_id", "")),
                        timestamp=message_data.get("timestamp", ""),
                        relevance_score=1.0,  # 使用者匹配給高分
                        is_participant_related=True,
                        user_display_name="",
                        channel_id=str(message_data.get("channel_id", "")),
                        message_id=str(message_data.get("message_id", "")),
                        metadata=message_data.get("metadata", {})
                    )
                    enhanced_segments.append(segment)
            
            return enhanced_segments[:limit]
            
        except Exception as e:
            self.logger.error(f"根據使用者搜尋失敗: {e}")
            return []
    
    async def search_by_time_range(self, 
                                 channel_id: str,
                                 start_time: datetime,
                                 end_time: datetime,
                                 limit: int = 20) -> List[EnhancedSegment]:
        """根據時間範圍搜尋片段
        
        Args:
            channel_id: 頻道 ID
            start_time: 開始時間
            end_time: 結束時間
            limit: 結果數量限制
            
        Returns:
            List[EnhancedSegment]: 搜尋結果
        """
        try:
            time_range = {
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            }
            
            search_query = SearchQuery(
                text="",
                channel_id=channel_id,
                search_type=SearchType.RECENT,
                limit=limit,
                time_range=time_range
            )
            
            search_result = await self.memory_manager.search_memory(search_query)
            
            if not search_result or not search_result.messages:
                return []
            
            # 轉換為增強片段
            enhanced_segments = []
            for i, message_data in enumerate(search_result.messages):
                segment = EnhancedSegment(
                    content=message_data.get("content", ""),
                    user_id=str(message_data.get("user_id", "")),
                    timestamp=message_data.get("timestamp", ""),
                    relevance_score=0.8,  # 時間匹配給中等分數
                    is_participant_related=False,
                    user_display_name="",
                    channel_id=str(message_data.get("channel_id", "")),
                    message_id=str(message_data.get("message_id", "")),
                    metadata=message_data.get("metadata", {})
                )
                enhanced_segments.append(segment)
            
            return enhanced_segments
            
        except Exception as e:
            self.logger.error(f"根據時間範圍搜尋失敗: {e}")
            return []
    
    def get_segment_summary(self, segments: List[EnhancedSegment]) -> Dict[str, Any]:
        """取得片段摘要統計
        
        Args:
            segments: 片段列表
            
        Returns:
            Dict[str, Any]: 摘要統計
        """
        try:
            if not segments:
                return {"total": 0}
            
            # 基本統計
            total_segments = len(segments)
            participant_related = sum(1 for s in segments if s.is_participant_related)
            
            # 分數統計
            scores = [s.relevance_score for s in segments]
            avg_score = sum(scores) / len(scores) if scores else 0.0
            max_score = max(scores) if scores else 0.0
            
            # 使用者統計
            users = set(s.user_id for s in segments if s.user_id)
            
            # 時間範圍
            timestamps = [s.timestamp for s in segments if s.timestamp]
            time_range = None
            if timestamps:
                try:
                    sorted_times = sorted(timestamps)
                    time_range = {
                        "earliest": sorted_times[0],
                        "latest": sorted_times[-1]
                    }
                except Exception:
                    pass
            
            return {
                "total": total_segments,
                "participant_related": participant_related,
                "unique_users": len(users),
                "avg_relevance_score": round(avg_score, 3),
                "max_relevance_score": round(max_score, 3),
                "time_range": time_range
            }
            
        except Exception as e:
            self.logger.error(f"產生片段摘要失敗: {e}")
            return {"total": 0, "error": str(e)}


# 輔助函數
def create_search_context(query: str, 
                         channel_id: str,
                         participant_context: Dict[str, UserInfo],
                         **kwargs) -> SearchContext:
    """建立搜尋上下文
    
    Args:
        query: 搜尋查詢
        channel_id: 頻道 ID
        participant_context: 參與者上下文
        **kwargs: 其他選項
        
    Returns:
        SearchContext: 搜尋上下文物件
    """
    return SearchContext(
        query=query,
        channel_id=channel_id,
        participant_context=participant_context,
        time_range=kwargs.get('time_range'),
        search_options=kwargs.get('search_options', {})
    )