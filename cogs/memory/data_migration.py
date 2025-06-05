"""記憶系統資料轉移工具

支援從舊版本記憶系統轉移資料到新的 SQLite + FAISS 混合架構。
提供自動探測、批次轉移、進度監控和資料驗證功能。
"""

import asyncio
import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, Callable
from dataclasses import dataclass, asdict
from enum import Enum

from .database import DatabaseManager
from .memory_manager import MemoryManager
from .exceptions import MemorySystemError


class DataSourceType(Enum):
    """資料來源類型"""
    JSON_DIALOGUE_HISTORY = "json_dialogue_history"
    SQLITE_DATABASE = "sqlite_database"
    MONGODB_COLLECTION = "mongodb_collection"
    CSV_EXPORT = "csv_export"
    VECTOR_STORE = "vector_store"
    UNKNOWN = "unknown"


@dataclass
class DataSource:
    """資料來源描述"""
    path: Path
    source_type: DataSourceType
    size_bytes: int
    estimated_records: int
    metadata: Dict[str, Any]
    last_modified: datetime


@dataclass
class MigrationProgress:
    """轉移進度資訊"""
    total_sources: int
    completed_sources: int
    total_records: int
    processed_records: int
    failed_records: int
    current_source: Optional[str]
    start_time: datetime
    estimated_completion: Optional[datetime]
    errors: List[str]


@dataclass
class MigrationReport:
    """轉移報告"""
    migration_id: str
    start_time: datetime
    end_time: Optional[datetime]
    total_sources: int
    successful_sources: int
    total_records: int
    migrated_records: int
    failed_records: int
    errors: List[str]
    warnings: List[str]
    performance_metrics: Dict[str, float]


class DataDetector:
    """舊資料自動探測器"""
    
    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.logger = logging.getLogger(__name__)
    
    async def detect_legacy_data(self) -> List[DataSource]:
        """自動探測舊版資料來源
        
        Returns:
            List[DataSource]: 發現的資料來源列表
        """
        sources = []
        
        # 探測常見的資料目錄
        search_paths = [
            self.base_path / "data",
            self.base_path / "database",
            self.base_path / "memory",
            self.base_path / "dialogues",
            self.base_path / "conversations",
            self.base_path / "chat_history",
            self.base_path,  # 根目錄
        ]
        
        for search_path in search_paths:
            if search_path.exists():
                sources.extend(await self._scan_directory(search_path))
        
        self.logger.info(f"探測到 {len(sources)} 個可能的資料來源")
        return sources
    
    async def _scan_directory(self, directory: Path) -> List[DataSource]:
        """掃描目錄中的資料檔案
        
        Args:
            directory: 要掃描的目錄
            
        Returns:
            List[DataSource]: 發現的資料來源
        """
        sources = []
        
        try:
            for file_path in directory.rglob("*"):
                if file_path.is_file():
                    source = await self._analyze_file(file_path)
                    if source:
                        sources.append(source)
        except Exception as e:
            self.logger.warning(f"掃描目錄 {directory} 時發生錯誤: {e}")
        
        return sources
    
    async def _analyze_file(self, file_path: Path) -> Optional[DataSource]:
        """分析檔案類型和內容
        
        Args:
            file_path: 檔案路徑
            
        Returns:
            Optional[DataSource]: 資料來源資訊，若不是有效資料則返回 None
        """
        try:
            # 跳過太小的檔案
            if file_path.stat().st_size < 100:
                return None
            
            file_extension = file_path.suffix.lower()
            file_name = file_path.name.lower()
            
            # 分析檔案類型
            source_type = DataSourceType.UNKNOWN
            estimated_records = 0
            metadata = {}
            
            if file_extension == ".json":
                source_type, estimated_records, metadata = await self._analyze_json_file(file_path)
            elif file_extension in [".db", ".sqlite", ".sqlite3"]:
                source_type, estimated_records, metadata = await self._analyze_sqlite_file(file_path)
            elif file_extension == ".csv":
                source_type, estimated_records, metadata = await self._analyze_csv_file(file_path)
            elif "dialogue" in file_name or "conversation" in file_name or "chat" in file_name:
                # 可能是對話歷史檔案
                if file_extension == ".json":
                    source_type = DataSourceType.JSON_DIALOGUE_HISTORY
                    estimated_records = await self._estimate_json_records(file_path)
            
            if source_type == DataSourceType.UNKNOWN:
                return None
            
            return DataSource(
                path=file_path,
                source_type=source_type,
                size_bytes=file_path.stat().st_size,
                estimated_records=estimated_records,
                metadata=metadata,
                last_modified=datetime.fromtimestamp(file_path.stat().st_mtime)
            )
            
        except Exception as e:
            self.logger.debug(f"分析檔案 {file_path} 時發生錯誤: {e}")
            return None
    
    async def _analyze_json_file(self, file_path: Path) -> Tuple[DataSourceType, int, Dict[str, Any]]:
        """分析 JSON 檔案
        
        Args:
            file_path: JSON 檔案路徑
            
        Returns:
            Tuple[DataSourceType, int, Dict[str, Any]]: 檔案類型、記錄數、元資料
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                # 讀取前幾行以判斷格式
                first_chunk = f.read(1024)
                f.seek(0)
                
                if '"message_id"' in first_chunk and '"content"' in first_chunk:
                    # 可能是對話歷史檔案
                    data = json.load(f)
                    if isinstance(data, list):
                        return (
                            DataSourceType.JSON_DIALOGUE_HISTORY,
                            len(data),
                            {"format": "message_list", "has_message_id": True}
                        )
                    elif isinstance(data, dict) and "messages" in data:
                        return (
                            DataSourceType.JSON_DIALOGUE_HISTORY,
                            len(data["messages"]),
                            {"format": "object_with_messages", "has_message_id": True}
                        )
                
        except Exception as e:
            self.logger.debug(f"分析 JSON 檔案 {file_path} 失敗: {e}")
        
        return DataSourceType.UNKNOWN, 0, {}
    
    async def _analyze_sqlite_file(self, file_path: Path) -> Tuple[DataSourceType, int, Dict[str, Any]]:
        """分析 SQLite 檔案
        
        Args:
            file_path: SQLite 檔案路徑
            
        Returns:
            Tuple[DataSourceType, int, Dict[str, Any]]: 檔案類型、記錄數、元資料
        """
        try:
            conn = sqlite3.connect(str(file_path))
            cursor = conn.cursor()
            
            # 取得所有表格
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            metadata = {"tables": tables}
            total_records = 0
            
            # 檢查是否有常見的訊息表格
            message_tables = []
            for table in tables:
                if any(keyword in table.lower() for keyword in ["message", "chat", "dialogue", "conversation"]):
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    total_records += count
                    message_tables.append({"table": table, "count": count})
            
            metadata["message_tables"] = message_tables
            conn.close()
            
            if message_tables:
                return DataSourceType.SQLITE_DATABASE, total_records, metadata
            
        except Exception as e:
            self.logger.debug(f"分析 SQLite 檔案 {file_path} 失敗: {e}")
        
        return DataSourceType.UNKNOWN, 0, {}
    
    async def _analyze_csv_file(self, file_path: Path) -> Tuple[DataSourceType, int, Dict[str, Any]]:
        """分析 CSV 檔案
        
        Args:
            file_path: CSV 檔案路徑
            
        Returns:
            Tuple[DataSourceType, int, Dict[str, Any]]: 檔案類型、記錄數、元資料
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                # 讀取第一行檢查標題
                first_line = f.readline().strip()
                if any(keyword in first_line.lower() for keyword in ["message", "content", "timestamp", "user"]):
                    # 計算行數
                    f.seek(0)
                    line_count = sum(1 for _ in f) - 1  # 減去標題行
                    
                    return (
                        DataSourceType.CSV_EXPORT,
                        line_count,
                        {"headers": first_line.split(","), "encoding": "utf-8"}
                    )
                    
        except Exception as e:
            self.logger.debug(f"分析 CSV 檔案 {file_path} 失敗: {e}")
        
        return DataSourceType.UNKNOWN, 0, {}
    
    async def _estimate_json_records(self, file_path: Path) -> int:
        """估算 JSON 檔案中的記錄數
        
        Args:
            file_path: JSON 檔案路徑
            
        Returns:
            int: 估算的記錄數
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # 簡單計算 JSON 物件數量
                return content.count('{')
        except:
            return 0


class DataMigrator:
    """資料轉移執行器"""
    
    def __init__(self, memory_manager: MemoryManager):
        self.memory_manager = memory_manager
        self.logger = logging.getLogger(__name__)
        self.progress_callback: Optional[Callable[[MigrationProgress], None]] = None
        self._stop_migration = False
    
    def set_progress_callback(self, callback: Callable[[MigrationProgress], None]):
        """設定進度回調函數
        
        Args:
            callback: 進度更新回調函數
        """
        self.progress_callback = callback
    
    async def migrate_data(
        self,
        sources: List[DataSource],
        dry_run: bool = False,
        backup: bool = True
    ) -> MigrationReport:
        """執行資料轉移
        
        Args:
            sources: 要轉移的資料來源列表
            dry_run: 是否為乾運行（僅預覽，不實際轉移）
            backup: 是否建立備份
            
        Returns:
            MigrationReport: 轉移報告
        """
        migration_id = f"migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        start_time = datetime.now()
        
        # 初始化進度
        progress = MigrationProgress(
            total_sources=len(sources),
            completed_sources=0,
            total_records=sum(source.estimated_records for source in sources),
            processed_records=0,
            failed_records=0,
            current_source=None,
            start_time=start_time,
            estimated_completion=None,
            errors=[]
        )
        
        report = MigrationReport(
            migration_id=migration_id,
            start_time=start_time,
            end_time=None,
            total_sources=len(sources),
            successful_sources=0,
            total_records=progress.total_records,
            migrated_records=0,
            failed_records=0,
            errors=[],
            warnings=[],
            performance_metrics={}
        )
        
        try:
            # 建立備份
            if backup and not dry_run:
                await self._create_backup()
            
            # 處理每個資料來源
            for source in sources:
                if self._stop_migration:
                    break
                
                progress.current_source = str(source.path)
                self._update_progress(progress)
                
                try:
                    migrated_count = await self._migrate_source(source, dry_run)
                    progress.processed_records += migrated_count
                    progress.completed_sources += 1
                    report.migrated_records += migrated_count
                    report.successful_sources += 1
                    
                    self.logger.info(f"成功轉移資料來源 {source.path}: {migrated_count} 筆記錄")
                    
                except Exception as e:
                    error_msg = f"轉移資料來源 {source.path} 失敗: {e}"
                    self.logger.error(error_msg)
                    progress.errors.append(error_msg)
                    report.errors.append(error_msg)
                    progress.failed_records += source.estimated_records
                
                self._update_progress(progress)
            
            report.end_time = datetime.now()
            report.performance_metrics = {
                "total_time_seconds": (report.end_time - report.start_time).total_seconds(),
                "records_per_second": report.migrated_records / max(1, (report.end_time - report.start_time).total_seconds())
            }
            
            self.logger.info(f"資料轉移完成: {report.migrated_records}/{report.total_records} 筆記錄")
            
        except Exception as e:
            error_msg = f"資料轉移過程發生錯誤: {e}"
            self.logger.error(error_msg)
            report.errors.append(error_msg)
            report.end_time = datetime.now()
        
        return report
    
    async def _migrate_source(self, source: DataSource, dry_run: bool) -> int:
        """轉移單一資料來源
        
        Args:
            source: 資料來源
            dry_run: 是否為乾運行
            
        Returns:
            int: 轉移的記錄數
        """
        if source.source_type == DataSourceType.JSON_DIALOGUE_HISTORY:
            return await self._migrate_json_dialogue_history(source, dry_run)
        elif source.source_type == DataSourceType.SQLITE_DATABASE:
            return await self._migrate_sqlite_database(source, dry_run)
        elif source.source_type == DataSourceType.CSV_EXPORT:
            return await self._migrate_csv_export(source, dry_run)
        else:
            raise ValueError(f"不支援的資料來源類型: {source.source_type}")
    
    async def _migrate_json_dialogue_history(self, source: DataSource, dry_run: bool) -> int:
        """轉移 JSON 對話歷史檔案
        
        Args:
            source: JSON 資料來源
            dry_run: 是否為乾運行
            
        Returns:
            int: 轉移的記錄數
        """
        migrated_count = 0
        
        try:
            with open(source.path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 解析資料格式
            messages = []
            if isinstance(data, list):
                messages = data
            elif isinstance(data, dict) and "messages" in data:
                messages = data["messages"]
            
            # 轉換每條訊息
            for message_data in messages:
                try:
                    # 轉換為標準格式
                    converted_message = await self._convert_legacy_message(message_data)
                    
                    if not dry_run:
                        # 儲存到新系統
                        success = await self.memory_manager.store_message_from_dict(converted_message)
                        if success:
                            migrated_count += 1
                    else:
                        migrated_count += 1
                        
                except Exception as e:
                    self.logger.warning(f"轉換訊息失敗: {e}")
                    continue
            
        except Exception as e:
            raise MemorySystemError(f"讀取 JSON 檔案失敗: {e}")
        
        return migrated_count
    
    async def _migrate_sqlite_database(self, source: DataSource, dry_run: bool) -> int:
        """轉移 SQLite 資料庫
        
        Args:
            source: SQLite 資料來源
            dry_run: 是否為乾運行
            
        Returns:
            int: 轉移的記錄數
        """
        migrated_count = 0
        
        try:
            conn = sqlite3.connect(str(source.path))
            conn.row_factory = sqlite3.Row
            
            # 處理每個訊息表格
            for table_info in source.metadata.get("message_tables", []):
                table_name = table_info["table"]
                
                cursor = conn.execute(f"SELECT * FROM {table_name}")
                
                for row in cursor:
                    try:
                        # 轉換資料庫記錄
                        converted_message = await self._convert_sqlite_record(dict(row))
                        
                        if not dry_run:
                            success = await self.memory_manager.store_message_from_dict(converted_message)
                            if success:
                                migrated_count += 1
                        else:
                            migrated_count += 1
                            
                    except Exception as e:
                        self.logger.warning(f"轉換資料庫記錄失敗: {e}")
                        continue
            
            conn.close()
            
        except Exception as e:
            raise MemorySystemError(f"讀取 SQLite 資料庫失敗: {e}")
        
        return migrated_count
    
    async def _migrate_csv_export(self, source: DataSource, dry_run: bool) -> int:
        """轉移 CSV 匯出檔案
        
        Args:
            source: CSV 資料來源
            dry_run: 是否為乾運行
            
        Returns:
            int: 轉移的記錄數
        """
        migrated_count = 0
        
        try:
            import csv
            
            with open(source.path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    try:
                        # 轉換 CSV 記錄
                        converted_message = await self._convert_csv_record(row)
                        
                        if not dry_run:
                            success = await self.memory_manager.store_message_from_dict(converted_message)
                            if success:
                                migrated_count += 1
                        else:
                            migrated_count += 1
                            
                    except Exception as e:
                        self.logger.warning(f"轉換 CSV 記錄失敗: {e}")
                        continue
            
        except Exception as e:
            raise MemorySystemError(f"讀取 CSV 檔案失敗: {e}")
        
        return migrated_count
    
    async def _convert_legacy_message(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """轉換舊版本訊息格式到新格式
        
        Args:
            message_data: 舊版本訊息資料
            
        Returns:
            Dict[str, Any]: 新格式訊息資料
        """
        # 標準化欄位映射
        field_mapping = {
            "id": "message_id",
            "msg_id": "message_id",
            "message_id": "message_id",
            "channel": "channel_id",
            "channel_id": "channel_id",
            "user": "user_id",
            "user_id": "user_id",
            "author": "user_id",
            "content": "content",
            "message": "content",
            "text": "content",
            "timestamp": "timestamp",
            "time": "timestamp",
            "created_at": "timestamp",
            "type": "message_type",
            "message_type": "message_type"
        }
        
        converted = {}
        
        # 映射已知欄位
        for old_key, new_key in field_mapping.items():
            if old_key in message_data:
                converted[new_key] = message_data[old_key]
        
        # 確保必要欄位存在
        if "message_id" not in converted:
            converted["message_id"] = f"legacy_{hash(str(message_data))}"
        
        if "channel_id" not in converted:
            converted["channel_id"] = "unknown_channel"
        
        if "user_id" not in converted:
            converted["user_id"] = "unknown_user"
        
        if "content" not in converted:
            converted["content"] = str(message_data)
        
        if "timestamp" not in converted:
            converted["timestamp"] = datetime.now()
        elif isinstance(converted["timestamp"], str):
            try:
                converted["timestamp"] = datetime.fromisoformat(converted["timestamp"].replace('Z', '+00:00'))
            except:
                converted["timestamp"] = datetime.now()
        
        if "message_type" not in converted:
            converted["message_type"] = "user"
        
        return converted
    
    async def _convert_sqlite_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """轉換 SQLite 記錄到新格式
        
        Args:
            record: SQLite 記錄
            
        Returns:
            Dict[str, Any]: 新格式訊息資料
        """
        return await self._convert_legacy_message(record)
    
    async def _convert_csv_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """轉換 CSV 記錄到新格式
        
        Args:
            record: CSV 記錄
            
        Returns:
            Dict[str, Any]: 新格式訊息資料
        """
        return await self._convert_legacy_message(record)
    
    async def _create_backup(self) -> None:
        """建立當前資料的備份"""
        try:
            backup_dir = Path("data/backups/memory_migration")
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = backup_dir / f"memory_backup_{timestamp}.db"
            
            # 複製當前資料庫
            db_manager = self.memory_manager.db_manager
            
            # 簡單的檔案複製備份
            import shutil
            if db_manager.db_path.exists():
                shutil.copy2(db_manager.db_path, backup_file)
                self.logger.info(f"已建立資料備份: {backup_file}")
            
        except Exception as e:
            self.logger.warning(f"建立備份失敗: {e}")
    
    def _update_progress(self, progress: MigrationProgress) -> None:
        """更新轉移進度
        
        Args:
            progress: 進度資訊
        """
        if self.progress_callback:
            self.progress_callback(progress)
    
    def stop_migration(self) -> None:
        """停止轉移過程"""
        self._stop_migration = True
        self.logger.info("收到停止轉移指令")


class MigrationValidator:
    """轉移資料驗證器"""
    
    def __init__(self, memory_manager: MemoryManager):
        self.memory_manager = memory_manager
        self.logger = logging.getLogger(__name__)
    
    async def validate_migration(self, report: MigrationReport) -> Dict[str, Any]:
        """驗證轉移結果
        
        Args:
            report: 轉移報告
            
        Returns:
            Dict[str, Any]: 驗證結果
        """
        validation_result = {
            "is_valid": True,
            "checks": {},
            "warnings": [],
            "errors": []
        }
        
        try:
            # 檢查資料庫完整性
            db_check = await self._validate_database_integrity()
            validation_result["checks"]["database_integrity"] = db_check
            
            # 檢查記錄數量
            count_check = await self._validate_record_counts(report)
            validation_result["checks"]["record_counts"] = count_check
            
            # 檢查資料格式
            format_check = await self._validate_data_format()
            validation_result["checks"]["data_format"] = format_check
            
            # 檢查向量索引
            vector_check = await self._validate_vector_indexes()
            validation_result["checks"]["vector_indexes"] = vector_check
            
            # 彙總結果
            if not all(check.get("passed", False) for check in validation_result["checks"].values()):
                validation_result["is_valid"] = False
            
        except Exception as e:
            validation_result["is_valid"] = False
            validation_result["errors"].append(f"驗證過程發生錯誤: {e}")
        
        return validation_result
    
    async def _validate_database_integrity(self) -> Dict[str, Any]:
        """驗證資料庫完整性"""
        try:
            with self.memory_manager.db_manager.get_connection() as conn:
                # 檢查外鍵約束
                conn.execute("PRAGMA foreign_key_check")
                fk_errors = conn.fetchall()
                
                # 檢查索引
                conn.execute("PRAGMA integrity_check")
                integrity_result = conn.fetchone()[0]
                
                return {
                    "passed": len(fk_errors) == 0 and integrity_result == "ok",
                    "foreign_key_errors": len(fk_errors),
                    "integrity_check": integrity_result
                }
        except Exception as e:
            return {
                "passed": False,
                "error": str(e)
            }
    
    async def _validate_record_counts(self, report: MigrationReport) -> Dict[str, Any]:
        """驗證記錄數量"""
        try:
            stats = await self.memory_manager.get_stats()
            
            # 簡單的數量驗證
            expected_ratio = 0.8  # 至少 80% 的記錄應該成功轉移
            actual_ratio = report.migrated_records / max(1, report.total_records)
            
            return {
                "passed": actual_ratio >= expected_ratio,
                "expected_records": report.total_records,
                "migrated_records": report.migrated_records,
                "success_ratio": actual_ratio,
                "total_in_db": stats.total_messages
            }
        except Exception as e:
            return {
                "passed": False,
                "error": str(e)
            }
    
    async def _validate_data_format(self) -> Dict[str, Any]:
        """驗證資料格式"""
        try:
            # 抽樣檢查部分記錄的格式
            with self.memory_manager.db_manager.get_connection() as conn:
                cursor = conn.execute("SELECT * FROM messages LIMIT 10")
                sample_records = cursor.fetchall()
                
                format_errors = 0
                for record in sample_records:
                    record_dict = dict(record)
                    
                    # 檢查必要欄位
                    required_fields = ["message_id", "channel_id", "user_id", "content", "timestamp"]
                    for field in required_fields:
                        if field not in record_dict or record_dict[field] is None:
                            format_errors += 1
                            break
                
                return {
                    "passed": format_errors == 0,
                    "sample_size": len(sample_records),
                    "format_errors": format_errors
                }
        except Exception as e:
            return {
                "passed": False,
                "error": str(e)
            }
    
    async def _validate_vector_indexes(self) -> Dict[str, Any]:
        """驗證向量索引"""
        try:
            if not self.memory_manager.vector_enabled:
                return {
                    "passed": True,
                    "note": "向量搜尋未啟用，跳過檢查"
                }
            
            # 檢查向量索引狀態
            vector_manager = self.memory_manager.vector_manager
            if vector_manager:
                # 簡單檢查是否有向量資料
                with self.memory_manager.db_manager.get_connection() as conn:
                    cursor = conn.execute("SELECT COUNT(*) FROM embeddings")
                    embedding_count = cursor.fetchone()[0]
                
                return {
                    "passed": True,
                    "embedding_count": embedding_count
                }
            else:
                return {
                    "passed": False,
                    "error": "向量管理器未初始化"
                }
        except Exception as e:
            return {
                "passed": False,
                "error": str(e)
            }