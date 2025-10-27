"""智慧文本分割服務模組

實作基於時間間隔和語義相似性的智慧對話分割系統。
使用動態時間間隔計算和 Qwen3 模型進行語義分析。
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union
from enum import Enum

import numpy as np

from .config import MemoryProfile
from .database import DatabaseManager
from .embedding_service import EmbeddingService
from .exceptions import MemorySystemError, VectorOperationError
from function import func
import asyncio


class SegmentationStrategy(Enum):
    """分割策略枚舉"""
    TIME_ONLY = "time_only"          # 僅基於時間間隔
    SEMANTIC_ONLY = "semantic_only"  # 僅基於語義相似性
    HYBRID = "hybrid"                # 混合策略（預設）
    ADAPTIVE = "adaptive"            # 自適應策略


@dataclass
class ActivityMetrics:
    """對話活躍度指標"""
    messages_per_hour: float = 0.0
    unique_users: int = 0
    average_message_length: float = 0.0
    response_time_seconds: float = 0.0
    peak_activity_score: float = 0.0
    
    def calculate_activity_level(self) -> float:
        """計算活躍度等級
        
        Returns:
            float: 活躍度分數 (0.0-1.0)
        """
        # 基於多個指標計算綜合活躍度
        msg_score = min(self.messages_per_hour / 60.0, 1.0)  # 標準化到每分鐘1條
        user_score = min(self.unique_users / 10.0, 1.0)      # 標準化到10個用戶
        length_score = min(self.average_message_length / 100.0, 1.0)  # 標準化到100字元
        
        # 加權平均
        activity_score = (
            msg_score * 0.4 +
            user_score * 0.3 +
            length_score * 0.2 +
            self.peak_activity_score * 0.1
        )
        
        return min(activity_score, 1.0)


@dataclass
class SegmentationConfig:
    """分割配置參數"""
    enabled: bool = True
    strategy: SegmentationStrategy = SegmentationStrategy.HYBRID
    
    # 時間間隔參數
    min_interval_minutes: int = 5
    max_interval_minutes: int = 120
    base_interval_minutes: int = 30
    activity_multiplier: float = 0.2
    
    # 語義相似性參數
    similarity_threshold: float = 0.6
    min_messages_per_segment: int = 3
    max_messages_per_segment: int = 50
    
    # 處理參數
    batch_size: int = 20
    async_processing: bool = True
    background_segmentation: bool = True
    
    # 品質控制參數
    coherence_threshold: float = 0.5
    merge_small_segments: bool = True
    split_large_segments: bool = True


@dataclass
class ConversationSegment:
    """對話片段資料類別"""
    segment_id: str
    channel_id: str
    start_time: datetime
    end_time: datetime
    message_ids: List[str] = field(default_factory=list)
    semantic_coherence_score: float = 0.0
    activity_level: float = 0.0
    segment_summary: Optional[str] = None
    vector_representation: Optional[np.ndarray] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration_minutes(self) -> float:
        """片段持續時間（分鐘）"""
        return (self.end_time - self.start_time).total_seconds() / 60.0
    
    @property
    def message_count(self) -> int:
        """訊息數量"""
        return len(self.message_ids)


class TextSegmentationService:
    """智慧文本分割服務
    
    提供基於時間間隔和語義相似性的對話分割功能。
    整合 Qwen3 模型進行語義分析和相似度計算。
    """
    
    def __init__(
        self,
        db_manager: DatabaseManager,
        embedding_service: EmbeddingService,
        config: SegmentationConfig,
        profile: MemoryProfile
    ):
        """初始化分割服務
        
        Args:
            db_manager: 資料庫管理器
            embedding_service: 嵌入服務
            config: 分割配置
            profile: 記憶體配置檔案
        """
        self.logger = logging.getLogger(__name__)
        self.db_manager = db_manager
        self.embedding_service = embedding_service
        self.config = config
        self.profile = profile
        
        # 初始化內部狀態
        self._active_segments: Dict[str, ConversationSegment] = {}
        self._processing_lock = asyncio.Lock()
        
        self.logger.info(f"文本分割服務已初始化，策略: {config.strategy.value}")
    
    async def process_new_message(
        self,
        message_id: str,
        channel_id: str,
        content: str,
        timestamp: datetime,
        user_id: str
    ) -> Optional[ConversationSegment]:
        """處理新訊息並執行分割邏輯
        
        Args:
            message_id: 訊息 ID
            channel_id: 頻道 ID
            content: 訊息內容
            timestamp: 時間戳記
            user_id: 使用者 ID
            
        Returns:
            Optional[ConversationSegment]: 新建立的片段（如果有）
        """
        if not self.config.enabled:
            return None
        
        try:
            async with self._processing_lock:
                # 檢查是否需要分割
                should_segment = await self._should_create_new_segment(
                    channel_id, timestamp, content
                )
                
                if should_segment:
                    # 完成當前片段
                    completed_segment = await self._finalize_current_segment(channel_id)
                    
                    # 開始新片段
                    await self._start_new_segment(channel_id, message_id, timestamp)
                    
                    return completed_segment
                else:
                    # 將訊息加入當前片段
                    await self._add_message_to_current_segment(
                        channel_id, message_id, timestamp
                    )
                    
                    return None
                    
        except Exception as e:
            await func.func.report_error(e, f"message segmentation for {channel_id}")
            raise MemorySystemError(f"分割處理失敗: {e}")
    
    async def _should_create_new_segment(
        self,
        channel_id: str,
        timestamp: datetime,
        content: str
    ) -> bool:
        """判斷是否應該建立新片段
        
        Args:
            channel_id: 頻道 ID
            timestamp: 當前時間戳記
            content: 訊息內容
            
        Returns:
            bool: 是否需要分割
        """
        current_segment = self._active_segments.get(channel_id)
        
        # 如果沒有活躍片段，需要建立新片段
        if not current_segment:
            return True
        
        # 基於策略判斷分割條件
        if self.config.strategy == SegmentationStrategy.TIME_ONLY:
            return await self._check_time_threshold(current_segment, timestamp)
        elif self.config.strategy == SegmentationStrategy.SEMANTIC_ONLY:
            return await self._check_semantic_threshold(current_segment, content)
        elif self.config.strategy == SegmentationStrategy.HYBRID:
            return await self._check_hybrid_threshold(current_segment, timestamp, content)
        elif self.config.strategy == SegmentationStrategy.ADAPTIVE:
            return await self._check_adaptive_threshold(current_segment, timestamp, content)
        
        return False
    
    async def _check_time_threshold(
        self,
        current_segment: ConversationSegment,
        timestamp: datetime
    ) -> bool:
        """檢查時間間隔閾值
        
        Args:
            current_segment: 當前片段
            timestamp: 新訊息時間戳記
            
        Returns:
            bool: 是否超過時間閾值
        """
        time_diff = timestamp - current_segment.end_time
        
        # 計算動態時間間隔
        dynamic_interval = await self._calculate_dynamic_interval(
            current_segment.channel_id
        )
        
        return time_diff.total_seconds() > dynamic_interval.total_seconds()
    
    async def _check_semantic_threshold(
        self,
        current_segment: ConversationSegment,
        content: str
    ) -> bool:
        """檢查語義相似性閾值
        
        Args:
            current_segment: 當前片段
            content: 新訊息內容
            
        Returns:
            bool: 是否低於語義相似性閾值
        """
        try:
            # 取得當前片段的代表性文本
            segment_text = await self._get_segment_representative_text(current_segment)
            
            if not segment_text:
                return False
            
            # 計算語義相似度
            similarity = await self._calculate_semantic_similarity(
                segment_text, content
            )
            
            # 如果相似度低於閾值，需要分割
            return similarity < self.config.similarity_threshold
            
        except Exception as e:
            await func.func.report_error(e, "semantic threshold check")
            return False
    
    async def _check_hybrid_threshold(
        self,
        current_segment: ConversationSegment,
        timestamp: datetime,
        content: str
    ) -> bool:
        """檢查混合分割閾值
        
        Args:
            current_segment: 當前片段
            timestamp: 新訊息時間戳記
            content: 訊息內容
            
        Returns:
            bool: 是否需要分割
        """
        # 時間條件
        time_threshold_met = await self._check_time_threshold(current_segment, timestamp)
        
        # 語義條件
        semantic_threshold_met = await self._check_semantic_threshold(current_segment, content)
        
        # 片段大小條件
        size_threshold_met = (
            current_segment.message_count >= self.config.max_messages_per_segment
        )
        
        # 混合決策：時間間隔 OR 語義差異 OR 片段過大
        return time_threshold_met or semantic_threshold_met or size_threshold_met
    
    async def _check_adaptive_threshold(
        self,
        current_segment: ConversationSegment,
        timestamp: datetime,
        content: str
    ) -> bool:
        """檢查自適應分割閾值
        
        Args:
            current_segment: 當前片段
            timestamp: 新訊息時間戳記
            content: 訊息內容
            
        Returns:
            bool: 是否需要分割
        """
        # 先執行混合檢查
        hybrid_result = await self._check_hybrid_threshold(
            current_segment, timestamp, content
        )
        
        if not hybrid_result:
            return False
        
        # 自適應調整：基於片段品質和活躍度
        activity_metrics = await self._calculate_activity_metrics(
            current_segment.channel_id, timestamp
        )
        
        activity_level = activity_metrics.calculate_activity_level()
        
        # 高活躍度時更寬鬆的分割條件
        if activity_level > 0.7:
            return True
        
        # 低活躍度時更嚴格的分割條件
        if activity_level < 0.3 and current_segment.message_count < self.config.min_messages_per_segment:
            return False
        
        return hybrid_result

    async def _batch_segment_channel_text(self, messages_to_process: List[Dict[str, Any]]) -> List[ConversationSegment]:
        """
        批次處理訊息並進行分割，採用獨立的、原子性的儲存邏輯。
        """
        if not self.config.enabled or not messages_to_process:
            return []

        self.logger.info(f"[重構] 開始批次分割 {len(messages_to_process)} 條訊息...")
        
        completed_segments_info = []
        messages_by_channel = {}
        for msg in messages_to_process:
            messages_by_channel.setdefault(msg['channel_id'], []).append(msg)

        for channel_id, messages in messages_by_channel.items():
            self.logger.debug(f"[重構] 正在處理頻道 {channel_id} 的 {len(messages)} 條訊息...")
            messages.sort(key=lambda m: m['timestamp'])

            current_segment_messages = []
            
            for message in messages:
                if not current_segment_messages:
                    current_segment_messages.append(message)
                    continue

                # 使用與即時處理相同的邏輯判斷是否分割
                # 為了判斷，需要一個臨時的 ConversationSegment 物件
                temp_segment_obj = ConversationSegment(
                    segment_id="temp",
                    channel_id=channel_id,
                    start_time=current_segment_messages[0]['timestamp'],
                    end_time=current_segment_messages[-1]['timestamp'],
                    message_ids=[m['message_id'] for m in current_segment_messages]
                )

                should_segment = await self._should_create_new_segment(
                    channel_id, message['timestamp'], message['content']
                )

                if should_segment:
                    # 完成當前片段並準備儲存
                    self.logger.debug(f"[重構] 發現分割點。完成片段，包含 {len(current_segment_messages)} 條訊息。")
                    completed_segments_info.append({
                        "channel_id": channel_id,
                        "messages": list(current_segment_messages)
                    })
                    # 用觸發分割的訊息重新初始化新片段
                    current_segment_messages = [message]
                    self.logger.debug(f"[重構] 新片段已開始，以訊息 {message['message_id']} 為起點。")
                else:
                    # 將訊息加入當前片段
                    current_segment_messages.append(message)

            # 處理迴圈結束後剩餘的最後一個片段
            if current_segment_messages:
                self.logger.debug(f"[重構] 處理剩餘的最後一個片段，包含 {len(current_segment_messages)} 條訊息。")
                completed_segments_info.append({
                    "channel_id": channel_id,
                    "messages": list(current_segment_messages)
                })

        # 原子性地儲存所有已完成的片段
        if not completed_segments_info:
            self.logger.info("[重構] 批次分割未產生任何新片段。")
            return []

        self.logger.info(f"[重構] 批次分割完成，共生成 {len(completed_segments_info)} 個片段，準備進行原子性儲存...")
        
        try:
            for seg_info in completed_segments_info:
                messages_in_seg = seg_info['messages']
                channel_id = seg_info['channel_id']
                
                segment_id = f"seg_{channel_id}_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:8]}"
                
                segment_data = {
                    "segment_id": segment_id,
                    "channel_id": channel_id,
                    "start_time": messages_in_seg[0]['timestamp'],
                    "end_time": messages_in_seg[-1]['timestamp'],
                    "message_count": len(messages_in_seg),
                    # 其他屬性可以在此處或之後計算並更新
                    "semantic_coherence_score": 0.0,
                    "activity_level": 0.0,
                    "segment_summary": None,
                    "vector_data": None,
                    "metadata": "{'source': 'batch'}"
                }

                # 呼叫重構後的原子性儲存函式
                await asyncio.to_thread(
                    self.db_manager.create_segment_with_messages,
                    segment_data=segment_data,
                    messages_data=messages_in_seg
                )
            
            self.logger.info(f"[重構] 成功原子性地儲存了 {len(completed_segments_info)} 個片段。")
            # 注意：此處返回的不是 ConversationSegment 物件，因為它們是異步建立的。
            # 如果需要返回物件，需要從資料庫重新查詢，但目前對於呼叫者來說非必要。
            return [] # 返回空列表以符合原始函式簽章

        except Exception as e:
            await func.func.report_error(e, "batch segment saving")
            raise MemorySystemError(f"批次儲存失敗: {e}")
    
    async def _calculate_dynamic_interval(self, channel_id: str) -> timedelta:
        """計算動態時間間隔
        
        Args:
            channel_id: 頻道 ID
            
        Returns:
            timedelta: 動態計算的時間間隔
        """
        try:
            # 取得最近的活躍度指標
            activity_metrics = await self._calculate_activity_metrics(
                channel_id, datetime.now()
            )
            
            activity_level = activity_metrics.calculate_activity_level()
            
            # 基於活躍度調整間隔
            # 高活躍度 -> 短間隔，低活躍度 -> 長間隔
            interval_minutes = (
                self.config.base_interval_minutes * 
                (1.0 - activity_level * self.config.activity_multiplier)
            )
            
            # 限制在最小和最大值之間
            interval_minutes = max(
                self.config.min_interval_minutes,
                min(interval_minutes, self.config.max_interval_minutes)
            )
            
            return timedelta(minutes=interval_minutes)
            
        except Exception as e:
            await func.func.report_error(e, f"dynamic interval calculation for {channel_id}")
            return timedelta(minutes=self.config.base_interval_minutes)
    
    async def _calculate_activity_metrics(
        self,
        channel_id: str,
        current_time: datetime,
        window_hours: int = 2
    ) -> ActivityMetrics:
        """計算對話活躍度指標
        
        Args:
            channel_id: 頻道 ID
            current_time: 當前時間
            window_hours: 分析時間窗口（小時）
            
        Returns:
            ActivityMetrics: 活躍度指標
        """
        try:
            start_time = current_time - timedelta(hours=window_hours)
            
            # 取得時間窗口內的訊息
            messages = self.db_manager.get_messages(
                channel_id=channel_id,
                after=start_time,
                before=current_time,
                limit=1000
            )
            
            if not messages:
                return ActivityMetrics()
            
            # 計算指標
            unique_users = len(set(msg['user_id'] for msg in messages))
            total_length = sum(len(msg['content']) for msg in messages)
            average_length = total_length / len(messages)
            messages_per_hour = len(messages) / window_hours
            
            # 計算回應時間（簡化版）
            response_times = []
            for i in range(1, len(messages)):
                if messages[i]['user_id'] != messages[i-1]['user_id']:
                    time_diff = (
                        datetime.fromisoformat(messages[i]['timestamp']) -
                        datetime.fromisoformat(messages[i-1]['timestamp'])
                    ).total_seconds()
                    if time_diff < 3600:  # 1小時內的回應
                        response_times.append(time_diff)
            
            avg_response_time = (
                sum(response_times) / len(response_times) 
                if response_times else 0.0
            )
            
            # 計算峰值活躍度（每15分鐘最高訊息數）
            peak_activity = 0
            for i in range(0, window_hours * 4):  # 15分鐘間隔
                window_start = start_time + timedelta(minutes=i * 15)
                window_end = window_start + timedelta(minutes=15)
                
                window_messages = [
                    msg for msg in messages
                    if window_start <= datetime.fromisoformat(msg['timestamp']) < window_end
                ]
                peak_activity = max(peak_activity, len(window_messages))
            
            peak_score = min(peak_activity / 20.0, 1.0)  # 標準化到20條訊息
            
            return ActivityMetrics(
                messages_per_hour=messages_per_hour,
                unique_users=unique_users,
                average_message_length=average_length,
                response_time_seconds=avg_response_time,
                peak_activity_score=peak_score
            )
            
        except Exception as e:
            await func.func.report_error(e, f"activity metrics calculation for {channel_id}")
            return ActivityMetrics()
    
    async def _calculate_semantic_similarity(
        self,
        text1: str,
        text2: str
    ) -> float:
        """計算兩段文本的語義相似度
        
        Args:
            text1: 第一段文本
            text2: 第二段文本
            
        Returns:
            float: 相似度分數 (0.0-1.0)
        """
        try:
            # 使用 Qwen3 嵌入模型計算向量（非同步）
            embedding1 = await self.embedding_service.encode_text_async(text1)
            embedding2 = await self.embedding_service.encode_text_async(text2)
            
            if embedding1 is None or embedding2 is None:
                return 0.0
            
            # 計算餘弦相似度
            similarity = np.dot(embedding1, embedding2) / (
                np.linalg.norm(embedding1) * np.linalg.norm(embedding2)
            )
            
            return float(similarity)
            
        except Exception as e:
            await func.func.report_error(e, "semantic similarity calculation")
            return 0.0
    
    async def _get_segment_representative_text(
        self,
        segment: ConversationSegment
    ) -> Optional[str]:
        """取得片段的代表性文本
        
        Args:
            segment: 對話片段
            
        Returns:
            Optional[str]: 代表性文本
        """
        try:
            if not segment.message_ids:
                return None
            
            # 取得片段中的訊息
            messages = self.db_manager.get_messages_by_ids(segment.message_ids)
            
            if not messages:
                return None
            
            # 簡單策略：取最近幾條訊息的內容
            recent_messages = sorted(
                messages,
                key=lambda x: x['timestamp'],
                reverse=True
            )[:5]  # 取最近5條
            
            combined_text = " ".join(msg['content'] for msg in recent_messages)
            return combined_text[:500]  # 限制長度
            
        except Exception as e:
            await func.func.report_error(e, f"representative text retrieval for segment {segment.segment_id}")
            return None
    
    async def _finalize_current_segment(self, channel_id: str) -> Optional[ConversationSegment]:
        """完成當前片段
        
        Args:
            channel_id: 頻道 ID
            
        Returns:
            Optional[ConversationSegment]: 完成的片段
        """
        current_segment = self._active_segments.get(channel_id)
        
        if not current_segment:
            return None
        
        try:
            # 計算片段的語義連貫性
            coherence_score = await self._calculate_segment_coherence(current_segment)
            current_segment.semantic_coherence_score = coherence_score
            
            # 計算片段向量表示
            vector_representation = await self._calculate_segment_vector(current_segment)
            current_segment.vector_representation = vector_representation
            
            # 生成片段摘要（可選）
            if len(current_segment.message_ids) >= self.config.min_messages_per_segment:
                summary = await self._generate_segment_summary(current_segment)
                current_segment.segment_summary = summary
            
            # 儲存到資料庫
            await self._save_segment_to_database(current_segment)
            
            # 從活躍片段中移除
            del self._active_segments[channel_id]
            
            self.logger.debug(
                f"完成片段 {current_segment.segment_id}，"
                f"訊息數: {current_segment.message_count}，"
                f"連貫性: {coherence_score:.3f}"
            )
            
            return current_segment
            
        except Exception as e:
            await func.func.report_error(e, f"segment finalization for channel {channel_id}")
            return None
    
    async def _start_new_segment(
        self,
        channel_id: str,
        first_message_id: str,
        timestamp: datetime
    ) -> None:
        """開始新片段
        
        Args:
            channel_id: 頻道 ID
            first_message_id: 第一條訊息 ID
            timestamp: 時間戳記
        """
        segment_id = f"seg_{channel_id}_{int(timestamp.timestamp())}_{uuid.uuid4().hex[:8]}"
        
        new_segment = ConversationSegment(
            segment_id=segment_id,
            channel_id=channel_id,
            start_time=timestamp,
            end_time=timestamp,
            message_ids=[first_message_id]
        )
        
        self._active_segments[channel_id] = new_segment
        
        self.logger.debug(f"開始新片段: {segment_id}")
    
    async def _add_message_to_current_segment(
        self,
        channel_id: str,
        message_id: str,
        timestamp: datetime
    ) -> None:
        """將訊息加入當前片段
        
        Args:
            channel_id: 頻道 ID
            message_id: 訊息 ID
            timestamp: 時間戳記
        """
        current_segment = self._active_segments.get(channel_id)
        
        if current_segment:
            current_segment.message_ids.append(message_id)
            current_segment.end_time = timestamp
            
            # 此處不應有資料庫操作。
            # 所有資料庫寫入都應在 _finalize_current_segment 中原子性地完成。
            # self.logger.debug(f"訊息 {message_id} 已在記憶體中加入片段 {current_segment.segment_id}")
    
    async def _calculate_segment_coherence(self, segment: ConversationSegment) -> float:
        """計算片段的語義連貫性分數
        
        Args:
            segment: 對話片段
            
        Returns:
            float: 連貫性分數 (0.0-1.0)
        """
        try:
            if len(segment.message_ids) < 2:
                return 1.0
            
            # 取得片段中的訊息
            messages = self.db_manager.get_messages_by_ids(segment.message_ids)
            
            if len(messages) < 2:
                return 1.0
            
            # 計算相鄰訊息之間的相似度
            similarities = []
            sorted_messages = sorted(messages, key=lambda x: x['timestamp'])
            
            for i in range(len(sorted_messages) - 1):
                similarity = await self._calculate_semantic_similarity(
                    sorted_messages[i]['content'],
                    sorted_messages[i + 1]['content']
                )
                similarities.append(similarity)
            
            # 計算平均相似度作為連貫性分數
            return sum(similarities) / len(similarities) if similarities else 0.0
            
        except Exception as e:
            await func.func.report_error(e, f"segment coherence calculation for {segment.segment_id}")
            return 0.0
    
    async def _calculate_segment_vector(
        self,
        segment: ConversationSegment
    ) -> Optional[np.ndarray]:
        """計算片段的向量表示
        
        Args:
            segment: 對話片段
            
        Returns:
            Optional[np.ndarray]: 片段向量
        """
        try:
            # 取得片段代表性文本
            representative_text = await self._get_segment_representative_text(segment)
            
            if not representative_text:
                return None
            
            # 計算向量表示（非同步）
            vector = await self.embedding_service.encode_text_async(representative_text)
            return vector
            
        except Exception as e:
            await func.func.report_error(e, f"segment vector calculation for {segment.segment_id}")
            return None
    
    async def _generate_segment_summary(self, segment: ConversationSegment) -> Optional[str]:
        """生成片段摘要
        
        Args:
            segment: 對話片段
            
        Returns:
            Optional[str]: 片段摘要
        """
        try:
            # 簡化版摘要：取第一條和最後一條訊息的部分內容
            messages = self.db_manager.get_messages_by_ids(segment.message_ids)
            
            if not messages:
                return None
            
            sorted_messages = sorted(messages, key=lambda x: x['timestamp'])
            
            first_content = sorted_messages[0]['content'][:50]
            last_content = sorted_messages[-1]['content'][:50]
            
            summary = f"開始: {first_content}... 結束: {last_content}..."
            return summary
            
        except Exception as e:
            await func.func.report_error(e, f"segment summary generation for {segment.segment_id}")
            return None
    
    async def _save_segment_to_database(self, segment: ConversationSegment) -> None:
        """使用原子性操作儲存片段及其關聯訊息到資料庫。
        
        Args:
            segment: 要儲存的片段。
        """
        try:
            self.logger.info(f"開始原子性儲存片段 {segment.segment_id}，包含 {segment.message_count} 條訊息。")
            vector_data = segment.vector_representation.tobytes() if segment.vector_representation is not None else None

            # 準備片段資料
            segment_data = {
                "segment_id": segment.segment_id,
                "channel_id": segment.channel_id,
                "start_time": segment.start_time,
                "end_time": segment.end_time,
                "message_count": segment.message_count,
                "semantic_coherence_score": segment.semantic_coherence_score,
                "activity_level": segment.activity_level,
                "segment_summary": segment.segment_summary,
                "vector_data": vector_data,
                "metadata": str(segment.metadata) if segment.metadata else None
            }

            # 準備訊息關聯資料
            message_links = [
                {"message_id": msg_id, "position": i}
                for i, msg_id in enumerate(segment.message_ids)
            ]

            # 呼叫原子性的資料庫方法
            await asyncio.to_thread(
                self.db_manager.create_segment_with_messages,
                segment_data=segment_data,
                message_links=message_links
            )

            self.logger.info(f"片段 {segment.segment_id} 已成功透過原子性操作儲存。")

        except Exception as e:
            await func.func.report_error(e, f"database save for segment {segment.segment_id}")
            # 即使失敗，也不再需要手動清理，因為交易會自動回滾
            raise MemorySystemError(f"儲存片段失敗: {e}")
    
    async def get_segments_for_timerange(
        self,
        channel_id: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[ConversationSegment]:
        """取得指定時間範圍的片段
        
        Args:
            channel_id: 頻道 ID
            start_time: 開始時間
            end_time: 結束時間
            
        Returns:
            List[ConversationSegment]: 片段列表
        """
        try:
            segments_data = self.db_manager.get_conversation_segments(
                channel_id=channel_id,
                start_time=start_time,
                end_time=end_time
            )
            
            segments = []
            for data in segments_data:
                # 反序列化向量資料
                vector_representation = None
                if data['vector_data']:
                    try:
                        vector_representation = np.frombuffer(
                            data['vector_data'], 
                            dtype=np.float32
                        )
                    except Exception as e:
                        await func.func.report_error(e, f"vector deserialization for segment {data['segment_id']}")
                        pass
                
                # 取得片段中的訊息 ID
                segment_messages = self.db_manager.get_segment_messages(data['segment_id'])
                message_ids = [msg['message_id'] for msg in segment_messages]
                
                segment = ConversationSegment(
                    segment_id=data['segment_id'],
                    channel_id=data['channel_id'],
                    start_time=datetime.fromisoformat(data['start_time']),
                    end_time=datetime.fromisoformat(data['end_time']),
                    message_ids=message_ids,
                    semantic_coherence_score=data['semantic_coherence_score'],
                    activity_level=data['activity_level'],
                    segment_summary=data['segment_summary'],
                    vector_representation=vector_representation
                )
                
                segments.append(segment)
            
            return segments
            
        except Exception as e:
            await func.func.report_error(e, f"timerange segment retrieval for {channel_id}")
            return []
    
    async def cleanup_old_segments(self, retention_days: int = 90) -> int:
        """清理舊片段
        
        Args:
            retention_days: 保留天數
            
        Returns:
            int: 清理的片段數量
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            
            # 這裡需要在資料庫中新增相應的清理方法
            # 暫時返回 0
            self.logger.info(f"清理 {cutoff_date} 之前的舊片段")
            return 0
            
        except Exception as e:
            await func.func.report_error(e, "old segment cleanup")
            return 0


# 全域服務管理器
_segmentation_service: Optional[TextSegmentationService] = None


def initialize_segmentation_service(
    db_manager: DatabaseManager,
    embedding_service: EmbeddingService,
    config: SegmentationConfig,
    profile: MemoryProfile
) -> TextSegmentationService:
    """初始化分割服務
    
    Args:
        db_manager: 資料庫管理器
        embedding_service: 嵌入服務
        config: 分割配置
        profile: 記憶體配置檔案
        
    Returns:
        TextSegmentationService: 分割服務實例
    """
    global _segmentation_service
    
    _segmentation_service = TextSegmentationService(
        db_manager=db_manager,
        embedding_service=embedding_service,
        config=config,
        profile=profile
    )
    
    return _segmentation_service


def get_segmentation_service() -> Optional[TextSegmentationService]:
    """取得分割服務實例
    
    Returns:
        Optional[TextSegmentationService]: 分割服務實例
    """
    return _segmentation_service