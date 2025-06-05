"""向量搜尋功能測試模組

測試嵌入服務、向量管理和搜尋引擎功能。
"""

import asyncio
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from .config import MemoryProfile
from .embedding_service import EmbeddingService, EmbeddingServiceManager
from .vector_manager import VectorManager
from .search_engine import SearchEngine, SearchQuery, SearchType, TimeRange
from .exceptions import VectorOperationError


class TestEmbeddingService(unittest.TestCase):
    """測試嵌入服務"""
    
    def setUp(self):
        """設置測試環境"""
        self.profile = MemoryProfile(
            name="test_profile",
            min_ram_gb=1.0,
            gpu_required=False,
            vector_enabled=True,
            embedding_dimension=384,
            cache_size_mb=128,
            batch_size=10,
            max_concurrent_queries=5,
            embedding_model="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        )
        
        # 使用較小的模型進行測試
        self.test_profile = MemoryProfile(
            name="test_mini",
            min_ram_gb=1.0,
            gpu_required=False,
            vector_enabled=True,
            embedding_dimension=384,
            cache_size_mb=64,
            batch_size=5,
            embedding_model="sentence-transformers/all-MiniLM-L6-v2"
        )
    
    @patch('cogs.memory.embedding_service.SentenceTransformer')
    def test_embedding_service_initialization(self, mock_transformer):
        """測試嵌入服務初始化"""
        # 模擬 SentenceTransformer
        mock_model = Mock()
        mock_model.encode.return_value = np.random.random((1, 384)).astype('float32')
        mock_transformer.return_value = mock_model
        
        service = EmbeddingService(self.test_profile)
        
        # 測試基本屬性
        self.assertIsNotNone(service.profile)
        self.assertEqual(service.profile.embedding_dimension, 384)
        self.assertIn(service._device, ["cpu", "cuda", "mps"])
    
    @patch('cogs.memory.embedding_service.SentenceTransformer')
    def test_text_encoding(self, mock_transformer):
        """測試文本編碼功能"""
        # 模擬模型輸出
        mock_model = Mock()
        test_embedding = np.random.random((1, 384)).astype('float32')
        mock_model.encode.return_value = test_embedding
        mock_transformer.return_value = mock_model
        
        service = EmbeddingService(self.test_profile)
        
        # 測試單一文本編碼
        result = service.encode_text("測試文本")
        self.assertEqual(result.shape, (384,))
        self.assertEqual(result.dtype, np.float32)
    
    @patch('cogs.memory.embedding_service.SentenceTransformer')
    def test_batch_encoding(self, mock_transformer):
        """測試批次編碼功能"""
        # 模擬模型輸出
        mock_model = Mock()
        test_embeddings = np.random.random((3, 384)).astype('float32')
        mock_model.encode.return_value = test_embeddings
        mock_transformer.return_value = mock_model
        
        service = EmbeddingService(self.test_profile)
        
        # 測試批次編碼
        texts = ["文本一", "文本二", "文本三"]
        result = service.encode_batch(texts)
        
        self.assertEqual(result.shape, (3, 384))
        self.assertEqual(result.dtype, np.float32)
    
    def test_service_manager(self):
        """測試服務管理器"""
        manager = EmbeddingServiceManager()
        
        # 測試服務創建和快取
        with patch('cogs.memory.embedding_service.SentenceTransformer'):
            service1 = manager.get_service(self.test_profile)
            service2 = manager.get_service(self.test_profile)
            
            # 應該返回相同的實例
            self.assertIs(service1, service2)


class TestVectorManager(unittest.TestCase):
    """測試向量管理器"""
    
    def setUp(self):
        """設置測試環境"""
        self.profile = MemoryProfile(
            name="test_profile",
            min_ram_gb=1.0,
            gpu_required=False,
            vector_enabled=True,
            embedding_dimension=128,  # 使用較小的維度進行測試
            cache_size_mb=64,
            batch_size=10
        )
        
        # 創建臨時目錄
        self.temp_dir = tempfile.mkdtemp()
        self.storage_path = Path(self.temp_dir)
    
    def test_vector_manager_initialization(self):
        """測試向量管理器初始化"""
        manager = VectorManager(self.profile, self.storage_path)
        
        self.assertEqual(manager.profile, self.profile)
        self.assertEqual(manager.storage_path, self.storage_path)
        self.assertIsInstance(manager._indices, dict)
    
    def test_channel_index_creation(self):
        """測試頻道索引創建"""
        manager = VectorManager(self.profile, self.storage_path)
        
        channel_id = "test_channel_123"
        success = manager.create_channel_index(channel_id)
        
        self.assertTrue(success)
        self.assertIn(channel_id, manager._indices)
    
    def test_vector_operations(self):
        """測試向量操作"""
        manager = VectorManager(self.profile, self.storage_path)
        channel_id = "test_channel_123"
        
        # 創建索引
        manager.create_channel_index(channel_id)
        
        # 準備測試向量
        test_vectors = np.random.random((5, 128)).astype('float32')
        message_ids = [f"msg_{i}" for i in range(5)]
        
        # 測試新增向量
        success = manager.add_vectors(channel_id, test_vectors, message_ids)
        self.assertTrue(success)
        
        # 測試搜尋
        query_vector = np.random.random(128).astype('float32')
        results = manager.search_similar(channel_id, query_vector, k=3)
        
        self.assertIsInstance(results, list)
        self.assertLessEqual(len(results), 3)
        
        # 檢查結果格式
        for message_id, score in results:
            self.assertIsInstance(message_id, str)
            self.assertIsInstance(score, float)
    
    def test_index_statistics(self):
        """測試索引統計"""
        manager = VectorManager(self.profile, self.storage_path)
        channel_id = "test_channel_123"
        
        # 創建索引並添加向量
        manager.create_channel_index(channel_id)
        test_vectors = np.random.random((3, 128)).astype('float32')
        message_ids = ["msg_1", "msg_2", "msg_3"]
        manager.add_vectors(channel_id, test_vectors, message_ids)
        
        # 測試統計
        stats = manager.get_index_stats(channel_id)
        
        self.assertIn("total_vectors", stats)
        self.assertIn("dimension", stats)
        self.assertEqual(stats["dimension"], 128)


class TestSearchEngine(unittest.TestCase):
    """測試搜尋引擎"""
    
    def setUp(self):
        """設置測試環境"""
        self.profile = MemoryProfile(
            name="test_profile",
            min_ram_gb=1.0,
            gpu_required=False,
            vector_enabled=True,
            embedding_dimension=128,
            cache_size_mb=64,
            batch_size=10
        )
        
        # 創建模擬的組件
        self.mock_embedding_service = Mock()
        self.mock_vector_manager = Mock()
        
        # 模擬嵌入服務
        self.mock_embedding_service.encode_text.return_value = np.random.random(128).astype('float32')
        self.mock_embedding_service.get_embedding_dimension.return_value = 128
        
        # 模擬向量管理器
        self.mock_vector_manager.search_similar.return_value = [
            ("msg_1", 0.95),
            ("msg_2", 0.87),
            ("msg_3", 0.76)
        ]
    
    def test_search_engine_initialization(self):
        """測試搜尋引擎初始化"""
        engine = SearchEngine(
            self.profile,
            self.mock_embedding_service,
            self.mock_vector_manager,
            enable_cache=True
        )
        
        self.assertEqual(engine.profile, self.profile)
        self.assertIsNotNone(engine.cache)
    
    def test_semantic_search(self):
        """測試語義搜尋"""
        engine = SearchEngine(
            self.profile,
            self.mock_embedding_service,
            self.mock_vector_manager,
            enable_cache=False
        )
        
        # 創建搜尋查詢
        query = SearchQuery(
            text="測試查詢",
            channel_id="test_channel",
            search_type=SearchType.SEMANTIC,
            limit=5
        )
        
        # 執行搜尋
        result = engine.search(query)
        
        self.assertIsNotNone(result)
        self.assertEqual(result.search_method, "semantic")
        self.assertGreater(result.search_time_ms, 0)
    
    def test_similarity_calculation(self):
        """測試相似度計算"""
        engine = SearchEngine(
            self.profile,
            self.mock_embedding_service,
            self.mock_vector_manager
        )
        
        # 模擬相同文本的嵌入
        same_embedding = np.array([1.0, 0.0, 0.0])
        self.mock_embedding_service.encode_batch.return_value = np.array([same_embedding, same_embedding])
        
        similarity = engine.calculate_similarity("文本A", "文本A")
        
        # 相同文本應該有高相似度
        self.assertGreater(similarity, 0.9)
    
    def test_search_cache(self):
        """測試搜尋快取"""
        engine = SearchEngine(
            self.profile,
            self.mock_embedding_service,
            self.mock_vector_manager,
            enable_cache=True
        )
        
        query = SearchQuery(
            text="快取測試",
            channel_id="test_channel",
            search_type=SearchType.SEMANTIC
        )
        
        # 第一次搜尋
        result1 = engine.search(query)
        self.assertFalse(result1.cache_hit)
        
        # 第二次搜尋應該命中快取
        result2 = engine.search(query)
        self.assertTrue(result2.cache_hit)


class TestIntegration(unittest.TestCase):
    """整合測試"""
    
    def setUp(self):
        """設置測試環境"""
        self.profile = MemoryProfile(
            name="integration_test",
            min_ram_gb=1.0,
            gpu_required=False,
            vector_enabled=True,
            embedding_dimension=128,
            cache_size_mb=64,
            batch_size=5
        )
        
        self.temp_dir = tempfile.mkdtemp()
        self.storage_path = Path(self.temp_dir)
    
    @patch('cogs.memory.embedding_service.SentenceTransformer')
    def test_end_to_end_workflow(self, mock_transformer):
        """測試端到端工作流程"""
        # 模擬嵌入模型
        mock_model = Mock()
        
        def mock_encode(texts, **kwargs):
            if isinstance(texts, str):
                texts = [texts]
            return np.random.random((len(texts), 128)).astype('float32')
        
        mock_model.encode = mock_encode
        mock_transformer.return_value = mock_model
        
        # 創建組件
        embedding_service = EmbeddingService(self.profile)
        vector_manager = VectorManager(self.profile, self.storage_path)
        search_engine = SearchEngine(
            self.profile,
            embedding_service,
            vector_manager,
            enable_cache=False
        )
        
        channel_id = "integration_test_channel"
        
        # 1. 創建頻道索引
        success = vector_manager.create_channel_index(channel_id)
        self.assertTrue(success)
        
        # 2. 添加一些測試訊息
        test_messages = [
            "這是第一條測試訊息",
            "這是關於程式設計的訊息",
            "今天天氣很好",
            "我喜歡使用 Python 程式語言",
            "向量搜尋功能很有用"
        ]
        
        message_ids = [f"msg_{i}" for i in range(len(test_messages))]
        
        # 生成嵌入並添加到索引
        embeddings = embedding_service.encode_batch(test_messages)
        success = vector_manager.add_vectors(channel_id, embeddings, message_ids)
        self.assertTrue(success)
        
        # 3. 執行搜尋
        query = SearchQuery(
            text="程式設計",
            channel_id=channel_id,
            search_type=SearchType.SEMANTIC,
            limit=3
        )
        
        result = search_engine.search(query)
        
        # 驗證結果
        self.assertGreater(len(result.messages), 0)
        self.assertEqual(len(result.relevance_scores), len(result.messages))
        self.assertGreater(result.search_time_ms, 0)
        self.assertEqual(result.search_method, "semantic")


def run_vector_search_tests():
    """執行向量搜尋測試"""
    print("開始執行向量搜尋功能測試...")
    
    # 設置日誌
    logging.basicConfig(level=logging.INFO)
    
    # 創建測試套件
    test_suite = unittest.TestSuite()
    
    # 添加測試類別
    test_classes = [
        TestEmbeddingService,
        TestVectorManager, 
        TestSearchEngine,
        TestIntegration
    ]
    
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)
    
    # 執行測試
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    # 輸出結果
    if result.wasSuccessful():
        print(f"\n✅ 所有測試通過！執行了 {result.testsRun} 個測試")
    else:
        print(f"\n❌ 測試失敗！{len(result.failures)} 個失敗，{len(result.errors)} 個錯誤")
        
        for test, error in result.failures + result.errors:
            print(f"  - {test}: {error}")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    run_vector_search_tests()