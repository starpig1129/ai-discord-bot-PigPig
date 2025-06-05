"""記憶系統基礎測試腳本

用於測試記憶系統基礎架構的功能性測試。
"""

import asyncio
import logging
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# 添加專案根目錄到 Python 路徑
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cogs.memory.memory_manager import MemoryManager, SearchQuery, SearchType
from cogs.memory.database import DatabaseManager
from cogs.memory.config import MemoryConfig, HardwareDetector
from cogs.memory.exceptions import MemorySystemError


class MockDiscordMessage:
    """模擬 Discord 訊息物件"""
    
    def __init__(self, message_id: str, channel_id: str, user_id: str, content: str):
        self.id = message_id
        self.content = content
        self.created_at = datetime.now()
        
        # 模擬頻道物件
        self.channel = type('Channel', (), {'id': channel_id})()
        
        # 模擬作者物件
        self.author = type('Author', (), {
            'id': user_id,
            'bot': False,
            'display_name': f'TestUser{user_id}'
        })()
        
        # 模擬其他屬性
        self.attachments = []
        self.embeds = []
        self.reference = None


async def test_hardware_detection():
    """測試硬體檢測功能"""
    print("=== 測試硬體檢測 ===")
    
    try:
        detector = HardwareDetector()
        hardware = detector.detect_hardware()
        
        print(f"檢測到的硬體規格:")
        print(f"  RAM: {hardware.ram_gb:.1f} GB")
        print(f"  CPU 核心: {hardware.cpu_cores}")
        print(f"  GPU 可用: {'是' if hardware.gpu_available else '否'}")
        if hardware.gpu_available:
            print(f"  GPU 記憶體: {hardware.gpu_memory_gb:.1f} GB")
        print(f"  平台: {hardware.platform}")
        
        return True
        
    except Exception as e:
        print(f"硬體檢測測試失敗: {e}")
        return False


async def test_database_operations():
    """測試資料庫操作"""
    print("\n=== 測試資料庫操作 ===")
    
    try:
        # 使用臨時資料庫
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_memory.db"
            db_manager = DatabaseManager(db_path)
            
            # 測試頻道建立
            success = db_manager.create_channel("123456", "789012", True, "test_profile")
            assert success, "頻道建立失敗"
            print("✓ 頻道建立成功")
            
            # 測試頻道查詢
            channel_info = db_manager.get_channel("123456")
            assert channel_info is not None, "頻道查詢失敗"
            assert channel_info['channel_id'] == "123456", "頻道 ID 不匹配"
            print("✓ 頻道查詢成功")
            
            # 測試訊息儲存
            success = db_manager.store_message(
                message_id="msg001",
                channel_id="123456",
                user_id="user001",
                content="這是一條測試訊息",
                timestamp=datetime.now(),
                message_type="user"
            )
            assert success, "訊息儲存失敗"
            print("✓ 訊息儲存成功")
            
            # 測試訊息查詢
            messages = db_manager.get_messages("123456", limit=10)
            assert len(messages) > 0, "訊息查詢失敗"
            assert messages[0]['message_id'] == "msg001", "訊息 ID 不匹配"
            print("✓ 訊息查詢成功")
            
            # 測試配置操作
            success = db_manager.set_config("test_key", "test_value", "string")
            assert success, "配置設定失敗"
            
            config_value = db_manager.get_config("test_key")
            assert config_value == "test_value", "配置值不匹配"
            print("✓ 配置操作成功")
            
            # 清理連接
            db_manager.close_connections()
            
        return True
        
    except Exception as e:
        print(f"資料庫操作測試失敗: {e}")
        return False


async def test_memory_manager():
    """測試記憶管理器"""
    print("\n=== 測試記憶管理器 ===")
    
    try:
        # 建立臨時配置檔案
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            import json
            config = {
                "memory_system": {
                    "enabled": True,
                    "auto_detection": True,
                    "vector_enabled": False,  # 第一階段不測試向量功能
                    "database_path": f.name.replace('.json', '_memory.db'),
                    "performance": {
                        "max_concurrent_queries": 5,
                        "query_timeout_seconds": 30,
                        "batch_size": 50
                    }
                }
            }
            json.dump(config, f)
            config_path = f.name
        
        try:
            # 初始化記憶管理器
            manager = MemoryManager(config_path)
            success = await manager.initialize()
            assert success, "記憶管理器初始化失敗"
            print("✓ 記憶管理器初始化成功")
            
            # 測試頻道初始化
            success = await manager.initialize_channel("test_channel", "test_guild")
            assert success, "頻道初始化失敗"
            print("✓ 頻道初始化成功")
            
            # 測試訊息儲存
            mock_message = MockDiscordMessage("msg001", "test_channel", "user001", "這是測試訊息")
            success = await manager.store_message(mock_message)
            assert success, "訊息儲存失敗"
            print("✓ 訊息儲存成功")
            
            # 測試上下文取得
            context = await manager.get_context("test_channel", limit=10)
            assert len(context) > 0, "上下文取得失敗"
            print("✓ 上下文取得成功")
            
            # 測試關鍵字搜尋
            search_query = SearchQuery(
                text="測試",
                channel_id="test_channel",
                search_type=SearchType.KEYWORD,
                limit=5
            )
            
            result = await manager.search_memory(search_query)
            assert result is not None, "搜尋失敗"
            assert result.search_method in ["keyword", "semantic_not_implemented"], "搜尋方法不正確"
            print("✓ 關鍵字搜尋成功")
            
            # 測試統計資料
            stats = await manager.get_stats()
            assert stats is not None, "統計資料取得失敗"
            print("✓ 統計資料取得成功")
            
            # 清理
            await manager.cleanup()
            
        finally:
            # 清理臨時檔案
            Path(config_path).unlink(missing_ok=True)
            Path(config['memory_system']['database_path']).unlink(missing_ok=True)
        
        return True
        
    except Exception as e:
        print(f"記憶管理器測試失敗: {e}")
        return False


async def test_configuration_system():
    """測試配置系統"""
    print("\n=== 測試配置系統 ===")
    
    try:
        # 測試預設配置
        config = MemoryConfig()
        default_config = config._get_default_config()
        assert "memory_system" in default_config, "預設配置格式錯誤"
        print("✓ 預設配置載入成功")
        
        # 測試配置檔案選擇
        profile = config.get_current_profile()
        assert profile is not None, "配置檔案選擇失敗"
        assert profile.name in ["high_performance", "medium_performance", "low_performance"], "配置檔案名稱錯誤"
        print(f"✓ 配置檔案選擇成功: {profile.name}")
        
        return True
        
    except Exception as e:
        print(f"配置系統測試失敗: {e}")
        return False


async def main():
    """主測試函數"""
    print("開始記憶系統基礎架構測試...\n")
    
    # 設定日誌
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    tests = [
        ("硬體檢測", test_hardware_detection),
        ("資料庫操作", test_database_operations),
        ("配置系統", test_configuration_system),
        ("記憶管理器", test_memory_manager),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            success = await test_func()
            if success:
                passed += 1
                print(f"✅ {test_name} 測試通過")
            else:
                print(f"❌ {test_name} 測試失敗")
        except Exception as e:
            print(f"❌ {test_name} 測試發生例外: {e}")
    
    print(f"\n測試完成: {passed}/{total} 項測試通過")
    
    if passed == total:
        print("🎉 所有基礎架構測試通過！")
        return True
    else:
        print("⚠️  部分測試失敗，請檢查錯誤訊息")
        return False


if __name__ == "__main__":
    asyncio.run(main())