"""向量遷移和兼容性工具

提供向量維度處理、模型遷移和數據轉換功能。
支援從舊的 SentenceTransformers 模型遷移到 Qwen3 模型。
"""

import logging
import sqlite3
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime
import asyncio
from function import func

from .config import MemoryProfile
from .database import DatabaseManager
from .embedding_service import EmbeddingService, embedding_service_manager
from .exceptions import VectorOperationError, DatabaseError


@dataclass
class MigrationInfo:
    """遷移資訊"""
    source_model: str
    target_model: str
    source_dimension: int
    target_dimension: int
    total_vectors: int
    migrated_vectors: int
    failed_vectors: int
    start_time: datetime
    end_time: Optional[datetime] = None
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_vectors == 0:
            return 0.0
        return self.migrated_vectors / self.total_vectors
    
    @property
    def duration_seconds(self) -> float:
        """遷移耗時（秒）"""
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time).total_seconds()


class VectorDimensionProcessor:
    """向量維度處理器
    
    處理不同模型之間的向量維度轉換。
    """
    
    def __init__(self):
        """初始化處理器"""
        self.logger = logging.getLogger(__name__)
    
    def pad_vectors(self, vectors: np.ndarray, target_dimension: int) -> np.ndarray:
        """填充向量到目標維度
        
        Args:
            vectors: 原始向量陣列
            target_dimension: 目標維度
            
        Returns:
            np.ndarray: 填充後的向量陣列
        """
        if vectors.shape[1] >= target_dimension:
            return vectors[:, :target_dimension]
        
        # 用零填充
        padding_size = target_dimension - vectors.shape[1]
        padding = np.zeros((vectors.shape[0], padding_size), dtype=vectors.dtype)
        return np.concatenate([vectors, padding], axis=1)
    
    def truncate_vectors(self, vectors: np.ndarray, target_dimension: int) -> np.ndarray:
        """截斷向量到目標維度
        
        Args:
            vectors: 原始向量陣列
            target_dimension: 目標維度
            
        Returns:
            np.ndarray: 截斷後的向量陣列
        """
        return vectors[:, :target_dimension]
    
    def interpolate_vectors(self, vectors: np.ndarray, target_dimension: int) -> np.ndarray:
        """插值向量到目標維度
        
        Args:
            vectors: 原始向量陣列
            target_dimension: 目標維度
            
        Returns:
            np.ndarray: 插值後的向量陣列
        """
        from scipy.interpolate import interp1d
        
        original_dimension = vectors.shape[1]
        if original_dimension == target_dimension:
            return vectors
        
        # 創建插值函數
        original_indices = np.linspace(0, 1, original_dimension)
        target_indices = np.linspace(0, 1, target_dimension)
        
        result_vectors = []
        for vector in vectors:
            f = interp1d(original_indices, vector, kind='linear')
            interpolated_vector = f(target_indices)
            result_vectors.append(interpolated_vector)
        
        return np.array(result_vectors)
    
    def pca_transform(self, vectors: np.ndarray, target_dimension: int) -> np.ndarray:
        """使用 PCA 降維或升維
        
        Args:
            vectors: 原始向量陣列
            target_dimension: 目標維度
            
        Returns:
            np.ndarray: 轉換後的向量陣列
        """
        from sklearn.decomposition import PCA
        from sklearn.preprocessing import StandardScaler
        
        original_dimension = vectors.shape[1]
        if original_dimension == target_dimension:
            return vectors
        
        if original_dimension > target_dimension:
            # 降維
            pca = PCA(n_components=target_dimension)
            return pca.fit_transform(vectors)
        else:
            # 升維：先標準化，然後填充
            scaler = StandardScaler()
            normalized_vectors = scaler.fit_transform(vectors)
            return self.pad_vectors(normalized_vectors, target_dimension)


class ModelMigrationManager:
    """模型遷移管理器
    
    管理從舊模型到新模型的向量數據遷移。
    """
    
    def __init__(self, db_manager: DatabaseManager):
        """初始化遷移管理器
        
        Args:
            db_manager: 資料庫管理器
        """
        self.logger = logging.getLogger(__name__)
        self.db_manager = db_manager
        self.dimension_processor = VectorDimensionProcessor()
    
    def get_migration_info(
        self, 
        source_profile: MemoryProfile, 
        target_profile: MemoryProfile
    ) -> MigrationInfo:
        """獲取遷移資訊
        
        Args:
            source_profile: 源配置檔案
            target_profile: 目標配置檔案
            
        Returns:
            MigrationInfo: 遷移資訊
        """
        # 統計需要遷移的向量數量
        total_vectors = self._count_vectors_to_migrate(source_profile.embedding_model)
        
        return MigrationInfo(
            source_model=source_profile.embedding_model,
            target_model=target_profile.embedding_model,
            source_dimension=source_profile.embedding_dimension,
            target_dimension=target_profile.embedding_dimension,
            total_vectors=total_vectors,
            migrated_vectors=0,
            failed_vectors=0,
            start_time=datetime.now()
        )
    
    def _count_vectors_to_migrate(self, source_model: str) -> int:
        """統計需要遷移的向量數量
        
        Args:
            source_model: 源模型名稱
            
        Returns:
            int: 向量數量
        """
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM embeddings WHERE model_version = ?",
                    (source_model,)
                )
                return cursor.fetchone()[0]
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Counting vectors to migrate failed"))
            self.logger.error(f"統計向量數量失敗: {e}", exc_info=True)
            return 0
    
    def migrate_vectors(
        self, 
        source_profile: MemoryProfile, 
        target_profile: MemoryProfile,
        strategy: str = "regenerate",
        batch_size: int = 100
    ) -> MigrationInfo:
        """遷移向量數據
        
        Args:
            source_profile: 源配置檔案
            target_profile: 目標配置檔案
            strategy: 遷移策略 ("regenerate", "transform", "pad", "truncate")
            batch_size: 批次大小
            
        Returns:
            MigrationInfo: 遷移結果
        """
        migration_info = self.get_migration_info(source_profile, target_profile)
        
        self.logger.info(
            f"開始向量遷移: {migration_info.source_model} -> {migration_info.target_model}"
        )
        self.logger.info(
            f"維度變化: {migration_info.source_dimension} -> {migration_info.target_dimension}"
        )
        self.logger.info(f"總向量數: {migration_info.total_vectors}")
        self.logger.info(f"遷移策略: {strategy}")
        
        try:
            if strategy == "regenerate":
                migration_info = self._regenerate_vectors(
                    migration_info, target_profile, batch_size
                )
            elif strategy == "transform":
                migration_info = self._transform_vectors(
                    migration_info, source_profile, target_profile, batch_size
                )
            elif strategy == "pad":
                migration_info = self._pad_vectors(migration_info, target_profile, batch_size)
            elif strategy == "truncate":
                migration_info = self._truncate_vectors(migration_info, target_profile, batch_size)
            else:
                raise ValueError(f"不支援的遷移策略: {strategy}")
            
            migration_info.end_time = datetime.now()
            
            self.logger.info(
                f"向量遷移完成: 成功 {migration_info.migrated_vectors}/{migration_info.total_vectors}, "
                f"成功率 {migration_info.success_rate:.2%}, "
                f"耗時 {migration_info.duration_seconds:.1f}秒"
            )
            
            return migration_info
            
        except Exception as e:
            migration_info.end_time = datetime.now()
            asyncio.create_task(func.report_error(e, "Vector migration failed"))
            self.logger.error(f"向量遷移失敗: {e}", exc_info=True)
            raise VectorOperationError(f"向量遷移失敗: {e}")
    
    def _regenerate_vectors(
        self, 
        migration_info: MigrationInfo, 
        target_profile: MemoryProfile,
        batch_size: int
    ) -> MigrationInfo:
        """重新生成向量（推薦策略）
        
        Args:
            migration_info: 遷移資訊
            target_profile: 目標配置檔案
            batch_size: 批次大小
            
        Returns:
            MigrationInfo: 更新的遷移資訊
        """
        # 獲取目標嵌入服務
        target_service = embedding_service_manager.get_service(target_profile)
        
        # 分批處理訊息
        offset = 0
        while offset < migration_info.total_vectors:
            try:
                # 從資料庫取得訊息批次
                messages = self._get_message_batch(
                    migration_info.source_model, offset, batch_size
                )
                
                if not messages:
                    break
                
                # 提取文本內容
                texts = []
                message_ids = []
                channel_ids = []
                
                for msg in messages:
                    content = msg.get('content_processed') or msg.get('content', '')
                    if content and content.strip():
                        texts.append(content)
                        message_ids.append(msg['message_id'])
                        channel_ids.append(msg['channel_id'])
                
                if texts:
                    # 生成新的嵌入向量
                    new_embeddings = target_service.encode_batch(texts)
                    
                    # 更新資料庫
                    self._update_embeddings_batch(
                        message_ids, channel_ids, new_embeddings, 
                        target_profile.embedding_model, target_profile.embedding_dimension
                    )
                    
                    migration_info.migrated_vectors += len(texts)
                else:
                    migration_info.failed_vectors += len(messages)
                
                offset += batch_size
                
                # 進度報告
                if migration_info.migrated_vectors % (batch_size * 10) == 0:
                    progress = migration_info.migrated_vectors / migration_info.total_vectors
                    self.logger.info(f"遷移進度: {progress:.1%}")
                
            except Exception as e:
                asyncio.create_task(func.report_error(e, f"Batch migration failed at offset {offset}"))
                self.logger.error(f"批次遷移失敗 (offset={offset}): {e}", exc_info=True)
                migration_info.failed_vectors += batch_size
                offset += batch_size
        
        return migration_info
    
    def _transform_vectors(
        self, 
        migration_info: MigrationInfo, 
        source_profile: MemoryProfile,
        target_profile: MemoryProfile,
        batch_size: int
    ) -> MigrationInfo:
        """轉換現有向量維度
        
        Args:
            migration_info: 遷移資訊
            source_profile: 源配置檔案
            target_profile: 目標配置檔案
            batch_size: 批次大小
            
        Returns:
            MigrationInfo: 更新的遷移資訊
        """
        offset = 0
        while offset < migration_info.total_vectors:
            try:
                # 從資料庫取得向量批次
                vectors_batch = self._get_vectors_batch(
                    migration_info.source_model, offset, batch_size
                )
                
                if not vectors_batch:
                    break
                
                # 提取向量數據
                embeddings = []
                embedding_ids = []
                
                for item in vectors_batch:
                    vector_data = np.frombuffer(item['vector_data'], dtype=np.float32)
                    vector_data = vector_data.reshape(1, -1)
                    embeddings.append(vector_data)
                    embedding_ids.append(item['id'])
                
                if embeddings:
                    # 合併向量
                    embeddings = np.vstack(embeddings)
                    
                    # 使用 PCA 轉換維度
                    transformed_embeddings = self.dimension_processor.pca_transform(
                        embeddings, target_profile.embedding_dimension
                    )
                    
                    # 更新資料庫中的向量
                    self._update_vectors_batch(
                        embedding_ids, transformed_embeddings,
                        target_profile.embedding_model, target_profile.embedding_dimension
                    )
                    
                    migration_info.migrated_vectors += len(embeddings)
                
                offset += batch_size
                
            except Exception as e:
                asyncio.create_task(func.report_error(e, f"Vector transformation failed at offset {offset}"))
                self.logger.error(f"向量轉換失敗 (offset={offset}): {e}", exc_info=True)
                migration_info.failed_vectors += batch_size
                offset += batch_size
        
        return migration_info
    
    def _pad_vectors(
        self, 
        migration_info: MigrationInfo, 
        target_profile: MemoryProfile,
        batch_size: int
    ) -> MigrationInfo:
        """填充向量到目標維度（快速但品質較低）"""
        # 類似 _transform_vectors，但使用填充策略
        return self._simple_dimension_change(
            migration_info, target_profile, batch_size, "pad"
        )
    
    def _truncate_vectors(
        self, 
        migration_info: MigrationInfo, 
        target_profile: MemoryProfile,
        batch_size: int
    ) -> MigrationInfo:
        """截斷向量到目標維度（快速但會丟失資訊）"""
        return self._simple_dimension_change(
            migration_info, target_profile, batch_size, "truncate"
        )
    
    def _simple_dimension_change(
        self, 
        migration_info: MigrationInfo, 
        target_profile: MemoryProfile,
        batch_size: int,
        method: str
    ) -> MigrationInfo:
        """簡單的維度變更方法"""
        offset = 0
        while offset < migration_info.total_vectors:
            try:
                vectors_batch = self._get_vectors_batch(
                    migration_info.source_model, offset, batch_size
                )
                
                if not vectors_batch:
                    break
                
                embeddings = []
                embedding_ids = []
                
                for item in vectors_batch:
                    vector_data = np.frombuffer(item['vector_data'], dtype=np.float32)
                    vector_data = vector_data.reshape(1, -1)
                    embeddings.append(vector_data)
                    embedding_ids.append(item['id'])
                
                if embeddings:
                    embeddings = np.vstack(embeddings)
                    
                    # 根據方法處理維度
                    if method == "pad":
                        transformed_embeddings = self.dimension_processor.pad_vectors(
                            embeddings, target_profile.embedding_dimension
                        )
                    elif method == "truncate":
                        transformed_embeddings = self.dimension_processor.truncate_vectors(
                            embeddings, target_profile.embedding_dimension
                        )
                    else:
                        raise ValueError(f"不支援的方法: {method}")
                    
                    self._update_vectors_batch(
                        embedding_ids, transformed_embeddings,
                        target_profile.embedding_model, target_profile.embedding_dimension
                    )
                    
                    migration_info.migrated_vectors += len(embeddings)
                
                offset += batch_size
                
            except Exception as e:
                asyncio.create_task(func.report_error(e, f"Dimension change failed at offset {offset}"))
                self.logger.error(f"維度變更失敗 (offset={offset}): {e}", exc_info=True)
                migration_info.failed_vectors += batch_size
                offset += batch_size
        
        return migration_info
    
    def _get_message_batch(self, source_model: str, offset: int, batch_size: int) -> List[Dict]:
        """取得訊息批次"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT m.message_id, m.channel_id, m.content, m.content_processed
                    FROM messages m
                    JOIN embeddings e ON m.message_id = e.message_id
                    WHERE e.model_version = ?
                    LIMIT ? OFFSET ?
                """, (source_model, batch_size, offset))
                
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Getting message batch failed"))
            self.logger.error(f"取得訊息批次失敗: {e}", exc_info=True)
            return []
    
    def _get_vectors_batch(self, source_model: str, offset: int, batch_size: int) -> List[Dict]:
        """取得向量批次"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT id, vector_data
                    FROM embeddings
                    WHERE model_version = ?
                    LIMIT ? OFFSET ?
                """, (source_model, batch_size, offset))
                
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Getting vectors batch failed"))
            self.logger.error(f"取得向量批次失敗: {e}", exc_info=True)
            return []
    
    def _update_embeddings_batch(
        self, 
        message_ids: List[str], 
        channel_ids: List[str],
        embeddings: np.ndarray,
        model_version: str,
        dimension: int
    ) -> None:
        """批次更新嵌入向量"""
        try:
            with self.db_manager.get_connection() as conn:
                # 刪除舊的嵌入
                placeholders = ','.join(['?'] * len(message_ids))
                conn.execute(
                    f"DELETE FROM embeddings WHERE message_id IN ({placeholders})",
                    message_ids
                )
                
                # 插入新的嵌入
                for i, (message_id, channel_id) in enumerate(zip(message_ids, channel_ids)):
                    vector_data = embeddings[i].tobytes()
                    
                    conn.execute("""
                        INSERT INTO embeddings
                        (message_id, channel_id, user_id, vector_data, model_version, dimension)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (message_id, channel_id, None, vector_data, model_version, dimension))
                
                conn.commit()
                
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Batch updating embeddings failed"))
            self.logger.error(f"批次更新嵌入失敗: {e}", exc_info=True)
            raise DatabaseError(f"批次更新嵌入失敗: {e}")
    
    def _update_vectors_batch(
        self,
        embedding_ids: List[str],
        embeddings: np.ndarray,
        model_version: str,
        dimension: int
    ) -> None:
        """批次更新向量數據"""
        try:
            with self.db_manager.get_connection() as conn:
                for i, embedding_id in enumerate(embedding_ids):
                    vector_data = embeddings[i].tobytes()
                    
                    conn.execute("""
                        UPDATE embeddings
                        SET vector_data = ?, model_version = ?, dimension = ?
                        WHERE id = ?
                    """, (vector_data, model_version, dimension, embedding_id))
                
                conn.commit()
                
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Batch updating vectors failed"))
            self.logger.error(f"批次更新向量失敗: {e}", exc_info=True)
            raise DatabaseError(f"批次更新向量失敗: {e}")
    
    def cleanup_old_vectors(self, old_model: str) -> int:
        """清理舊模型的向量數據
        
        Args:
            old_model: 舊模型名稱
            
        Returns:
            int: 清理的向量數量
        """
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM embeddings WHERE model_version = ?",
                    (old_model,)
                )
                deleted_count = cursor.rowcount
                conn.commit()
                
                self.logger.info(f"清理了 {deleted_count} 個舊向量 (模型: {old_model})")
                return deleted_count
                
        except Exception as e:
            asyncio.create_task(func.report_error(e, f"Cleaning up old vectors for model {old_model} failed"))
            self.logger.error(f"清理舊向量失敗: {e}", exc_info=True)
            raise DatabaseError(f"清理舊向量失敗: {e}")