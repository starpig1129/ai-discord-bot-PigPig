"""
安全控制模組

負責權限驗證、備份管理和回滾機制。
"""

import os
import json
import shutil
from addons.logging import get_logger
import discord
from datetime import datetime
from typing import List, Optional
from dotenv import load_dotenv
from function import func
import asyncio

# module-level logger
log = get_logger(server_id="Bot", source=__name__)
logger = log


class UpdatePermissionChecker:
    """更新權限檢查器"""
    
    def __init__(self):
        """初始化權限檢查器"""
        load_dotenv()
        self.bot_owner_id = int(os.getenv("BOT_OWNER_ID", 0))
        self.logger = get_logger(server_id="Bot", source=__name__)
        
        if self.bot_owner_id == 0:
            self.logger.warning("BOT_OWNER_ID 未設定或無效，更新功能將無法使用")
    
    def check_update_permission(self, user_id: int) -> bool:
        """
        檢查更新權限 - 僅限 Bot 擁有者
        
        Args:
            user_id: 使用者 ID
            
        Returns:
            是否有更新權限
        """
        return user_id == self.bot_owner_id
    
    def check_status_permission(self, interaction: discord.Interaction) -> bool:
        """
        檢查狀態查看權限 - 管理員或擁有者
        
        Args:
            interaction: Discord 互動物件
            
        Returns:
            是否有查看狀態權限
        """
        if not interaction.guild:
            # DM 中只有擁有者可以查看
            return interaction.user.id == self.bot_owner_id
        
        return (interaction.user.guild_permissions.administrator or 
                interaction.user.id == self.bot_owner_id)
    
    def get_bot_owner_id(self) -> int:
        """
        獲取 Bot 擁有者 ID
        
        Returns:
            Bot 擁有者 ID
        """
        return self.bot_owner_id


class BackupManager:
    """備份管理器"""
    
    def __init__(self, backup_dir: str = "data/backups"):
        """
        初始化備份管理器
        
        Args:
            backup_dir: 備份目錄路徑
        """
        self.backup_dir = backup_dir
        self.logger = get_logger(server_id="Bot", source=__name__)
        os.makedirs(backup_dir, exist_ok=True)
    
    def create_backup(self, protected_files: Optional[List[str]] = None) -> str:
        """
        創建當前版本備份
        
        Args:
            protected_files: 需要保護的檔案列表
            
        Returns:
            備份 ID
            
        Raises:
            Exception: 備份過程中的錯誤
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_id = f"backup_{timestamp}"
        backup_path = os.path.join(self.backup_dir, backup_id)
        
        if protected_files is None:
            protected_files = [
                "settings.json",
                ".env",
                "data/schedule/",
                "data/dialogue_history.json",
                "data/channel_configs/",
                "data/user_data/",
                "data/update_logs/",
                "cogs/",
                "gpt/",
                "addons/",
                "bot.py",
                "main.py",
                "function.py",
                "update.py"
            ]
        
        try:
            os.makedirs(backup_path, exist_ok=True)
            
            # 記錄備份資訊
            backup_info = {
                "backup_id": backup_id,
                "timestamp": timestamp,
                "protected_files": protected_files,
                "created_at": datetime.now().isoformat()
            }
            
            backed_up_items = []
            
            for item in protected_files:
                if os.path.exists(item):
                    dest_path = os.path.join(backup_path, item)
                    
                    if os.path.isdir(item):
                        # 備份目錄，但排除備份目錄本身以避免無限遞歸
                        self._backup_directory_safely(item, dest_path, backup_path)
                        backed_up_items.append(f"dir:{item}")
                    else:
                        # 備份檔案
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                        shutil.copy2(item, dest_path)
                        backed_up_items.append(f"file:{item}")
                else:
                    self.logger.warning(f"備份項目不存在，跳過: {item}")
            
            backup_info["backed_up_items"] = backed_up_items
            
            # 儲存備份資訊
            info_path = os.path.join(backup_path, "backup_info.json")
            with open(info_path, 'w', encoding='utf-8') as f:
                json.dump(backup_info, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"備份創建成功: {backup_id}")
            return backup_id
            
        except Exception as e:
            self.logger.error(f"創建備份時發生錯誤: {e}")
            asyncio.create_task(func.report_error(e, "addons/update/security.py/create_backup"))
            # 清理失敗的備份
            if os.path.exists(backup_path):
                shutil.rmtree(backup_path, ignore_errors=True)
            raise Exception(f"備份創建失敗: {e}")
    
    def _backup_directory_safely(self, source_dir: str, dest_dir: str, backup_root: str) -> None:
        """
        安全地備份目錄，避免備份目錄本身造成無限遞歸
        
        Args:
            source_dir: 來源目錄路徑
            dest_dir: 目標目錄路徑
            backup_root: 備份根目錄路徑
        """
        # 正規化路徑以進行比較
        source_abs = os.path.abspath(source_dir)
        backup_abs = os.path.abspath(self.backup_dir)
        
        # 確保目標目錄存在
        os.makedirs(os.path.dirname(dest_dir), exist_ok=True)
        
        def should_skip_item(item_path: str) -> bool:
            """檢查是否應該跳過該項目"""
            item_abs = os.path.abspath(item_path)
            
            # 跳過備份目錄本身以避免無限遞歸
            if item_abs.startswith(backup_abs):
                return True
            
            # 跳過臨時目錄
            if 'temp' in item_path.lower() or '__pycache__' in item_path:
                return True
                
            return False
        
        try:
            if not os.path.exists(source_dir):
                self.logger.warning(f"來源目錄不存在: {source_dir}")
                return
            
            # 創建目標目錄
            os.makedirs(dest_dir, exist_ok=True)
            
            # 遞歷並複製目錄內容
            for root, dirs, files in os.walk(source_dir):
                # 計算相對路徑
                rel_path = os.path.relpath(root, source_dir)
                if rel_path == '.':
                    target_root = dest_dir
                else:
                    target_root = os.path.join(dest_dir, rel_path)
                
                # 檢查是否應該跳過當前目錄
                if should_skip_item(root):
                    dirs.clear()  # 不遞歸進入此目錄
                    continue
                
                # 創建目標目錄
                os.makedirs(target_root, exist_ok=True)
                
                # 複製檔案
                for file in files:
                    source_file = os.path.join(root, file)
                    target_file = os.path.join(target_root, file)
                    
                    if not should_skip_item(source_file):
                        try:
                            shutil.copy2(source_file, target_file)
                        except Exception as e:
                            self.logger.warning(f"複製檔案失敗 {source_file}: {e}")
                            asyncio.create_task(func.report_error(e, f"addons/update/security.py/_backup_directory_safely/copy/{source_file}"))
                
                # 過濾要遞歸的目錄
                dirs[:] = [d for d in dirs if not should_skip_item(os.path.join(root, d))]
                
        except Exception as e:
            self.logger.error(f"備份目錄時發生錯誤 {source_dir}: {e}")
            asyncio.create_task(func.report_error(e, f"addons/update/security.py/_backup_directory_safely/{source_dir}"))
            raise
    
    def rollback_to_backup(self, backup_id: str) -> bool:
        """
        回滾到指定備份
        
        Args:
            backup_id: 備份 ID
            
        Returns:
            回滾是否成功
        """
        backup_path = os.path.join(self.backup_dir, backup_id)
        info_path = os.path.join(backup_path, "backup_info.json")
        
        if not os.path.exists(backup_path):
            self.logger.error(f"備份不存在: {backup_id}")
            return False
        
        if not os.path.exists(info_path):
            self.logger.error(f"備份資訊檔案不存在: {backup_id}")
            return False
        
        try:
            # 讀取備份資訊
            with open(info_path, 'r', encoding='utf-8') as f:
                backup_info = json.load(f)
            
            backed_up_items = backup_info.get("backed_up_items", [])
            
            # 執行回滾
            for item in backed_up_items:
                try:
                    parts = item.split(":", 1)
                    if len(parts) != 2:
                        self.logger.warning(f"備份項目格式錯誤，跳過: {item}")
                        continue
                    
                    item_type, item_path = parts
                    
                    # 驗證路徑不為空
                    if not item_path or not item_path.strip():
                        self.logger.warning(f"備份項目路徑為空，跳過: {item}")
                        continue
                    
                    source_path = os.path.join(backup_path, item_path)
                    
                    if not os.path.exists(source_path):
                        self.logger.warning(f"備份中的項目不存在，跳過: {item_path}")
                        continue
                        
                except ValueError as e:
                    self.logger.error(f"解析備份項目時發生錯誤，跳過: {item} - {e}")
                    asyncio.create_task(func.report_error(e, f"addons/update/security.py/rollback_to_backup/parse/{item}"))
                    continue
                
                # 驗證目標路徑的安全性
                normalized_item_path = os.path.normpath(item_path)
                if os.path.isabs(normalized_item_path) or '..' in normalized_item_path:
                    self.logger.warning(f"不安全的路徑，跳過: {item_path}")
                    continue
                
                # 刪除現有項目
                if os.path.exists(item_path):
                    try:
                        if os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                        else:
                            os.remove(item_path)
                        self.logger.debug(f"已刪除現有項目: {item_path}")
                    except Exception as e:
                        self.logger.error(f"刪除現有項目失敗 {item_path}: {e}")
                        asyncio.create_task(func.report_error(e, f"addons/update/security.py/rollback_to_backup/delete/{item_path}"))
                        continue
                
                # 恢復備份項目
                try:
                    if item_type == "dir":
                        shutil.copytree(source_path, item_path)
                        self.logger.debug(f"已恢復目錄: {item_path}")
                    else:
                        # 確保父目錄存在
                        parent_dir = os.path.dirname(item_path)
                        if parent_dir:
                            os.makedirs(parent_dir, exist_ok=True)
                        shutil.copy2(source_path, item_path)
                        self.logger.debug(f"已恢復檔案: {item_path}")
                except Exception as e:
                    self.logger.error(f"恢復備份項目失敗 {item_path}: {e}")
                    asyncio.create_task(func.report_error(e, f"addons/update/security.py/rollback_to_backup/restore/{item_path}"))
                    continue
            
            self.logger.info(f"回滾到備份成功: {backup_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"回滾過程中發生錯誤: {e}")
            asyncio.create_task(func.report_error(e, f"addons/update/security.py/rollback_to_backup/{backup_id}"))
            return False
    
    def list_backups(self) -> List[dict]:
        """
        列出所有可用的備份
        
        Returns:
            備份資訊列表
        """
        backups = []
        
        try:
            if not os.path.exists(self.backup_dir):
                return backups
            
            for backup_name in os.listdir(self.backup_dir):
                backup_path = os.path.join(self.backup_dir, backup_name)
                info_path = os.path.join(backup_path, "backup_info.json")
                
                if os.path.isdir(backup_path) and os.path.exists(info_path):
                    try:
                        with open(info_path, 'r', encoding='utf-8') as f:
                            backup_info = json.load(f)
                        backups.append(backup_info)
                    except Exception as e:
                        self.logger.warning(f"讀取備份資訊失敗 {backup_name}: {e}")
                        asyncio.create_task(func.report_error(e, f"addons/update/security.py/list_backups/read_info/{backup_name}"))
            
            # 按時間排序，最新的在前面
            backups.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            
        except Exception as e:
            self.logger.error(f"列出備份時發生錯誤: {e}")
            asyncio.create_task(func.report_error(e, "addons/update/security.py/list_backups"))
        
        return backups
    
    def cleanup_old_backups(self, max_backups: int = 5) -> None:
        """
        清理過期備份
        
        Args:
            max_backups: 最大保留備份數量
        """
        try:
            backups = self.list_backups()
            
            if len(backups) <= max_backups:
                return
            
            # 刪除過期備份
            for backup_info in backups[max_backups:]:
                backup_id = backup_info.get("backup_id")
                if backup_id:
                    backup_path = os.path.join(self.backup_dir, backup_id)
                    if os.path.exists(backup_path):
                        shutil.rmtree(backup_path)
                        self.logger.info(f"已刪除過期備份: {backup_id}")
                        
        except Exception as e:
            self.logger.error(f"清理備份時發生錯誤: {e}")
            asyncio.create_task(func.report_error(e, "addons/update/security.py/cleanup_old_backups"))
    
    def get_backup_size(self, backup_id: str) -> int:
        """
        獲取備份大小
        
        Args:
            backup_id: 備份 ID
            
        Returns:
            備份大小（bytes）
        """
        backup_path = os.path.join(self.backup_dir, backup_id)
        
        if not os.path.exists(backup_path):
            return 0
        
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(backup_path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    if os.path.exists(filepath):
                        total_size += os.path.getsize(filepath)
        except Exception as e:
            self.logger.error(f"計算備份大小時發生錯誤: {e}")
            asyncio.create_task(func.report_error(e, f"addons/update/security.py/get_backup_size/{backup_id}"))
        
        return total_size


class ConfigProtector:
    """配置檔案保護器"""
    
    def __init__(self):
        """初始化配置保護器"""
        self.logger = get_logger(server_id="Bot", source=__name__)
        self.protected_files = [
            "settings.json", ".env", "data/dialogue_history.json",
            "data/channel_configs/", "data/user_data/", "data/update_config.json"
        ]
    
    def backup_configs(self, backup_path: str) -> bool:
        """
        備份配置檔案
        
        Args:
            backup_path: 備份路徑
            
        Returns:
            備份是否成功
        """
        try:
            os.makedirs(backup_path, exist_ok=True)
            
            for config_file in self.protected_files:
                if os.path.exists(config_file):
                    dest_path = os.path.join(backup_path, config_file)
                    
                    if os.path.isdir(config_file):
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                        shutil.copytree(config_file, dest_path, dirs_exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                        shutil.copy2(config_file, dest_path)
            
            return True
            
        except Exception as e:
            self.logger.error(f"備份配置檔案時發生錯誤: {e}")
            asyncio.create_task(func.report_error(e, "addons/update/security.py/backup_configs"))
            return False
    
    def restore_configs(self, backup_path: str) -> bool:
        """
        恢復配置檔案
        
        Args:
            backup_path: 備份路徑
            
        Returns:
            恢復是否成功
        """
        try:
            for config_file in self.protected_files:
                source_path = os.path.join(backup_path, config_file)
                
                if os.path.exists(source_path):
                    if os.path.isdir(source_path):
                        if os.path.exists(config_file):
                            shutil.rmtree(config_file)
                        shutil.copytree(source_path, config_file)
                    else:
                        os.makedirs(os.path.dirname(config_file), exist_ok=True)
                        shutil.copy2(source_path, config_file)
            
            return True
            
        except Exception as e:
            self.logger.error(f"恢復配置檔案時發生錯誤: {e}")
            asyncio.create_task(func.report_error(e, "addons/update/security.py/restore_configs"))
            return False
    
    def verify_configs(self) -> bool:
        """
        驗證配置檔案完整性
        
        Returns:
            驗證是否通過
        """
        try:
            # 檢查關鍵配置檔案是否存在
            critical_files = ["settings.json", ".env"]
            
            for file_path in critical_files:
                if not os.path.exists(file_path):
                    self.logger.error(f"關鍵配置檔案不存在: {file_path}")
                    return False
            
            # 驗證 JSON 檔案格式
            json_files = ["settings.json", "data/update_config.json"]
            
            for file_path in json_files:
                if os.path.exists(file_path):
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            json.load(f)
                    except json.JSONDecodeError as e:
                        self.logger.error(f"JSON 檔案格式錯誤 {file_path}: {e}")
                        asyncio.create_task(func.report_error(e, f"addons/update/security.py/verify_configs/json_decode/{file_path}"))
                        return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"驗證配置檔案時發生錯誤: {e}")
            asyncio.create_task(func.report_error(e, "addons/update/security.py/verify_configs"))
            return False