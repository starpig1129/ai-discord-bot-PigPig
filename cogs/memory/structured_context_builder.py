"""結構化上下文建構器

實現智慧背景知識整合系統的結構化上下文建構功能，
將使用者資訊和對話片段整合為清晰的 Discord 格式輸出。
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import re
from dataclasses import dataclass

from .user_manager import UserInfo
from .conversation_segment_enhancer import EnhancedSegment


@dataclass
class ContextSection:
    """上下文區塊"""
    title: str
    content: str
    priority: int = 0  # 優先級，數字越大越重要
    
    def __str__(self) -> str:
        return f"{self.title}\n{self.content}"


class StructuredContextBuilder:
    """結構化上下文建構器
    
    負責將使用者資訊和對話片段整合為結構化的上下文，
    以 Discord 友好的格式提供給 GPT 模型。
    """
    
    def __init__(self):
        """初始化結構化上下文建構器"""
        self.logger = logging.getLogger(__name__)
        
        # 格式配置
        self.max_segments_display = 5
        self.max_content_length = 150
        self.max_user_data_length = 100
        self.max_total_length = 2000  # 總上下文長度限制
        
        # 表情符號配置
        self.emoji_config = {
            "participants": "📋",
            "history": "💬",
            "high_relevance": "🔥",
            "medium_relevance": "📝",
            "low_relevance": "💡",
            "participant_related": "👤",
            "recent": "🕐",
            "important": "⭐"
        }
    
    def build_enhanced_context(self,
                              user_info: Dict[str, UserInfo],
                              conversation_segments: List[EnhancedSegment],
                              current_message=None,
                              options: Optional[Dict[str, Any]] = None) -> str:
        """建構增強的結構化上下文
        
        Args:
            user_info: 使用者資訊字典
            conversation_segments: 對話片段列表
            current_message: 當前訊息（可選）
            options: 建構選項（可選）
            
        Returns:
            str: 結構化上下文字串
        """
        try:
            if options is None:
                options = {}
            
            context_sections = []
            
            # 1. 對話參與者資訊
            if user_info:
                participant_section = self._build_participant_section(user_info, options)
                if participant_section:
                    context_sections.append(participant_section)
            
            # 2. 相關歷史對話
            if conversation_segments:
                conversation_section = self._build_conversation_section(
                    conversation_segments, user_info, options
                )
                if conversation_section:
                    context_sections.append(conversation_section)
            
            # 3. 當前對話狀態（如果提供）
            if current_message and options.get('include_current_context', False):
                current_section = self._build_current_section(current_message, options)
                if current_section:
                    context_sections.append(current_section)
            
            # 按優先級排序
            context_sections.sort(key=lambda x: x.priority, reverse=True)
            
            # 組合最終結果
            final_context = self._combine_sections(context_sections, options)
            
            return final_context
            
        except Exception as e:
            self.logger.error(f"建構結構化上下文失敗: {e}")
            return ""
    
    def _build_participant_section(self, 
                                  user_info: Dict[str, UserInfo],
                                  options: Dict[str, Any]) -> Optional[ContextSection]:
        """建構參與者資訊區塊
        
        Args:
            user_info: 使用者資訊字典
            options: 建構選項
            
        Returns:
            ContextSection: 參與者資訊區塊
        """
        try:
            if not user_info:
                return None
            
            emoji = self.emoji_config["participants"]
            title = f"{emoji} **對話參與者資訊**"
            
            lines = []
            
            # 按最後活躍時間排序
            sorted_users = sorted(
                user_info.items(),
                key=lambda x: x[1].last_active or datetime.min,
                reverse=True
            )
            
            for user_id, info in sorted_users:
                user_line = self._format_user_info(info, options)
                if user_line:
                    lines.append(user_line)
            
            if not lines:
                return None
            
            content = "\n".join(lines)
            
            return ContextSection(
                title=title,
                content=content,
                priority=2  # 高優先級
            )
            
        except Exception as e:
            self.logger.error(f"建構參與者資訊區塊失敗: {e}")
            return None
    
    def _format_user_info(self, user_info: UserInfo, options: Dict[str, Any]) -> str:
        """格式化使用者資訊
        
        Args:
            user_info: 使用者資訊
            options: 格式選項
            
        Returns:
            str: 格式化的使用者資訊
        """
        try:
            # 基本資訊：使用 Discord 標籤
            user_line = f"• <@{user_info.user_id}>"
            
            # 顯示名稱
            if user_info.display_name:
                user_line += f" ({user_info.display_name})"
            
            # 最後活躍時間
            if user_info.last_active:
                time_str = self._format_relative_time(user_info.last_active)
                user_line += f" | 最後活躍: {time_str}"
            
            # 使用者資料摘要
            if user_info.user_data and options.get('include_user_data', True):
                data_preview = self._truncate_text(
                    user_info.user_data, 
                    self.max_user_data_length
                )
                user_line += f"\n  └─ 資料: {data_preview}"
            
            # 偏好設定（如果需要）
            if (user_info.preferences and 
                options.get('include_preferences', False)):
                prefs_str = self._format_preferences(user_info.preferences)
                if prefs_str:
                    user_line += f"\n  └─ 偏好: {prefs_str}"
            
            return user_line
            
        except Exception as e:
            self.logger.error(f"格式化使用者資訊失敗: {e}")
            return ""
    
    def _build_conversation_section(self, 
                                   segments: List[EnhancedSegment],
                                   user_info: Dict[str, UserInfo],
                                   options: Dict[str, Any]) -> Optional[ContextSection]:
        """建構對話歷史區塊
        
        Args:
            segments: 對話片段列表
            user_info: 使用者資訊字典
            options: 建構選項
            
        Returns:
            ContextSection: 對話歷史區塊
        """
        try:
            if not segments:
                return None
            
            emoji = self.emoji_config["history"]
            title = f"{emoji} **相關歷史對話**"
            
            lines = []
            max_display = options.get('max_segments', self.max_segments_display)
            
            for segment in segments[:max_display]:
                line = self._format_conversation_segment(segment, user_info, options)
                if line:
                    lines.append(line)
            
            if not lines:
                return None
            
            content = "\n".join(lines)
            
            # 如果有更多結果，顯示統計
            if len(segments) > max_display:
                content += f"\n*...還有 {len(segments) - max_display} 條相關對話*"
            
            return ContextSection(
                title=title,
                content=content,
                priority=1  # 中等優先級
            )
            
        except Exception as e:
            self.logger.error(f"建構對話歷史區塊失敗: {e}")
            return None
    
    def _format_conversation_segment(self, 
                                   segment: EnhancedSegment,
                                   user_info: Dict[str, UserInfo],
                                   options: Dict[str, Any]) -> str:
        """格式化對話片段
        
        Args:
            segment: 對話片段
            user_info: 使用者資訊字典
            options: 格式選項
            
        Returns:
            str: 格式化的對話片段
        """
        try:
            # 相關性指示器
            relevance_emoji = self._get_relevance_emoji(segment.relevance_score)
            
            # 參與者指示器
            participant_emoji = (self.emoji_config["participant_related"] 
                               if segment.is_participant_related else "")
            
            # 時間指示器
            time_emoji = self._get_time_emoji(segment.timestamp)
            
            # 格式化內容
            content = self._truncate_text(segment.content, self.max_content_length)
            
            # 使用者標籤
            user_tag = f"<@{segment.user_id}>" if segment.user_id else "未知使用者"
            
            # 時間格式化
            time_str = self._format_timestamp(segment.timestamp)
            
            # 組合最終格式
            line = f"{relevance_emoji}{participant_emoji}{time_emoji} `[{time_str}]` {user_tag}: {content}"
            
            return line
            
        except Exception as e:
            self.logger.error(f"格式化對話片段失敗: {e}")
            return ""
    
    def _get_relevance_emoji(self, score: float) -> str:
        """取得相關性表情符號
        
        Args:
            score: 相關性分數
            
        Returns:
            str: 表情符號
        """
        if score > 0.8:
            return self.emoji_config["high_relevance"]
        elif score > 0.6:
            return self.emoji_config["medium_relevance"]
        else:
            return self.emoji_config["low_relevance"]
    
    def _get_time_emoji(self, timestamp_str: str) -> str:
        """取得時間相關表情符號
        
        Args:
            timestamp_str: 時間戳字串
            
        Returns:
            str: 表情符號
        """
        try:
            if not timestamp_str:
                return ""
            
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            now = datetime.now(timestamp.tzinfo)
            hours_ago = (now - timestamp).total_seconds() / 3600
            
            # 最近24小時內的對話標記為最近
            if hours_ago <= 24:
                return self.emoji_config["recent"]
            
            return ""
            
        except Exception:
            return ""
    
    def _format_relative_time(self, timestamp: datetime) -> str:
        """格式化相對時間
        
        Args:
            timestamp: 時間戳
            
        Returns:
            str: 相對時間字串
        """
        try:
            now = datetime.now(timestamp.tzinfo)
            diff = now - timestamp
            
            if diff.days > 7:
                return timestamp.strftime('%Y-%m-%d')
            elif diff.days > 0:
                return f"{diff.days}天前"
            elif diff.seconds > 3600:
                hours = diff.seconds // 3600
                return f"{hours}小時前"
            else:
                minutes = diff.seconds // 60
                return f"{minutes}分鐘前"
                
        except Exception:
            return "未知時間"
    
    def _format_timestamp(self, timestamp_str: str) -> str:
        """格式化時間戳
        
        Args:
            timestamp_str: 時間戳字串
            
        Returns:
            str: 格式化的時間字串
        """
        try:
            if not timestamp_str:
                return "未知時間"
            
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            return timestamp.strftime('%m-%d %H:%M')
            
        except Exception:
            return timestamp_str[:16] if len(timestamp_str) > 16 else timestamp_str
    
    def _truncate_text(self, text: str, max_length: int) -> str:
        """截斷文字
        
        Args:
            text: 原始文字
            max_length: 最大長度
            
        Returns:
            str: 截斷後的文字
        """
        if not text:
            return ""
        
        if len(text) <= max_length:
            return text
        
        return text[:max_length - 3] + "..."
    
    def _combine_sections(self, 
                         sections: List[ContextSection],
                         options: Dict[str, Any]) -> str:
        """組合上下文區塊
        
        Args:
            sections: 上下文區塊列表
            options: 組合選項
            
        Returns:
            str: 最終的結構化上下文
        """
        try:
            if not sections:
                return ""
            
            # 組合所有區塊
            combined_content = "\n\n".join(str(section) for section in sections)
            
            # 檢查長度限制
            max_length = options.get('max_total_length', self.max_total_length)
            if len(combined_content) > max_length:
                # 截斷處理
                combined_content = self._truncate_context(combined_content, max_length)
            
            return combined_content
            
        except Exception as e:
            self.logger.error(f"組合上下文區塊失敗: {e}")
            return ""
    
    def _truncate_context(self, context: str, max_length: int) -> str:
        """截斷上下文
        
        Args:
            context: 原始上下文
            max_length: 最大長度
            
        Returns:
            str: 截斷後的上下文
        """
        if len(context) <= max_length:
            return context
        
        # 嘗試在段落邊界截斷
        truncated = context[:max_length - 50]
        last_paragraph = truncated.rfind('\n\n')
        
        if last_paragraph > max_length * 0.7:  # 如果截斷位置合理
            return truncated[:last_paragraph] + "\n\n*[內容過長已截斷]*"
        else:
            return truncated + "\n*[內容過長已截斷]*"


# 輔助函數
def create_context_options(**kwargs) -> Dict[str, Any]:
    """建立上下文建構選項
    
    Args:
        **kwargs: 選項參數
        
    Returns:
        Dict[str, Any]: 選項字典
    """
    default_options = {
        'include_user_data': True,
        'include_preferences': False,
        'include_current_context': False,
        'max_segments': 5,
        'max_total_length': 2000
    }
    
    default_options.update(kwargs)
    return default_options