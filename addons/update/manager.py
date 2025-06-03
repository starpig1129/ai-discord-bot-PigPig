"""
核心更新管理器模組

整合所有更新相關功能，提供統一的更新管理介面。
"""

import os
import json
import zipfile
import shutil
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from discord.ext import tasks

from .checker import VersionChecker
from .downloader import UpdateDownloader
from .security import UpdatePermissionChecker, BackupManager, ConfigProtector
from .notifier import DiscordNotifier
from .restart import GracefulRestartManager
from ..settings import UpdateSettings


class UpdateStatusTracker:
    """更新狀態追蹤器"""
    
    def __init__(self):
        self.current_status = "idle"  # idle|checking|downloading|updating|restarting
        self.progress = 0
        self.current_operation = ""
        self.start_time = None
        self.last_check_time = None
        self.error_message = None
    
    def update_status(self, status: str, progress: int = 0, operation: str = ""):
        """更新狀態"""
        self.current_status = status
        self.progress = progress
        self.current_operation = operation
        self.error_message = None
        
        if status in ["checking", "downloading", "updating"]:
            if not self.start_time:
                self.start_time = datetime.now()
        elif status == "idle":
            self.start_time = None
    
    def set_error(self, error_message: str):
        """設定錯誤狀態"""
        self.current_status = "error"
        self.error_message = error_message
        self.start_time = None
    
    def reset(self):
        """重置狀態"""
        self.current_status = "idle"
        self.progress = 0
        self.current_operation = ""
        self.start_time = None
        self.error_message = None


class UpdateLogger:
    """更新日誌管理器"""
    
    def __init__(self, log_dir: str = "data/update_logs"):
        self.log_dir = log_dir
        self.logger = logging.getLogger(__name__)
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, "update_history.json")
        self.current_log = None
    
    def start_log(self, event_type: str, trigger_type: str, user_id: Optional[int] = None):
        """開始記錄更新事件"""
        self.current_log = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "trigger_type": trigger_type,
            "user_id": user_id,
            "status": "pending",
            "details": {},
            "error_message": None
        }
    
    def update_log(self, **kwargs):
        """更新日誌內容"""
        if self.current_log:
            if "details" in kwargs:
                self.current_log["details"].update(kwargs["details"])
                del kwargs["details"]
            self.current_log.update(kwargs)
    
    def finish_log(self, status: str, error_message: Optional[str] = None):
        """完成日誌記錄"""
        if self.current_log:
            self.current_log["status"] = status
            if error_message:
                self.current_log["error_message"] = error_message
            
            self._write_log()
            self.current_log = None
    
    def _write_log(self):
        """寫入日誌檔案"""
        logs = []
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, "r", encoding='utf-8') as f:
                    logs = json.load(f)
            except:
                logs = []
        
        logs.append(self.current_log)
        
        # 保留最近100條記錄
        if len(logs) > 100:
            logs = logs[-100:]
        
        try:
            with open(self.log_file, "w", encoding='utf-8') as f:
                json.dump(logs, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"寫入日誌時發生錯誤: {e}")


class UpdateManager:
    """核心更新管理器"""
    
    def __init__(self, bot):
        """
        初始化更新管理器
        
        Args:
            bot: Discord Bot 實例
        """
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        
        # 載入配置
        self.update_settings = UpdateSettings()
        self.config = {
            "auto_update": self.update_settings.auto_update,
            "notification": self.update_settings.notification,
            "security": self.update_settings.security,
            "restart": self.update_settings.restart,
            "github": self.update_settings.github
        }
        
        # 初始化各個組件
        self.version_checker = VersionChecker(self.config["github"])
        self.downloader = UpdateDownloader()
        self.permission_checker = UpdatePermissionChecker()
        self.backup_manager = BackupManager()
        self.config_protector = ConfigProtector()
        self.notifier = DiscordNotifier(bot)
        self.restart_manager = GracefulRestartManager(bot, self.config["restart"])
        self.status_tracker = UpdateStatusTracker()
        self.update_logger = UpdateLogger()
        
        # 更新鎖，防止同時進行多個更新
        self._update_lock = asyncio.Lock()
        
        # 啟動自動檢查（如果啟用）
        if self.config["auto_update"]["enabled"]:
            self._start_auto_check()
    
    
    async def check_for_updates(self) -> Dict[str, Any]:
        """檢查更新"""
        self.status_tracker.update_status("checking", operation="正在查詢最新版本...")
        self.status_tracker.last_check_time = datetime.now()
        
        try:
            result = await self.version_checker.check_for_updates()
            self.status_tracker.update_status("idle")
            return result
        except Exception as e:
            self.status_tracker.set_error(str(e))
            raise e
    
    async def execute_update(self, interaction=None, force: bool = False) -> Dict[str, Any]:
        """
        執行更新流程
        
        Args:
            interaction: Discord 互動物件
            force: 是否強制更新
            
        Returns:
            更新結果字典
        """
        async with self._update_lock:
            user_id = interaction.user.id if interaction else None
            self.update_logger.start_log("update_start", "discord_command" if interaction else "auto", user_id)
            
            start_time = datetime.now()
            backup_id = None
            
            try:
                # 1. 檢查更新
                self.status_tracker.update_status("checking", 0, "檢查是否有可用更新...")
                update_info = await self.check_for_updates()
                
                if not update_info.get("update_available") and not force:
                    result = {"success": False, "error": "沒有可用更新"}
                    self.update_logger.finish_log("skipped", "沒有可用更新")
                    return result
                
                # 記錄版本資訊
                self.update_logger.update_log(
                    old_version=update_info["current_version"],
                    new_version=update_info["latest_version"]
                )
                
                # 2. 創建備份
                if self.config["security"]["backup_enabled"]:
                    self.status_tracker.update_status("updating", 10, "創建系統備份...")
                    await self.notifier.notify_update_progress("創建備份", 10)
                    
                    backup_id = self.backup_manager.create_backup(
                        self.config["security"]["protected_files"]
                    )
                    self.update_logger.update_log(details={"backup_id": backup_id})
                    self.logger.info(f"備份創建成功: {backup_id}")
                
                # 3. 下載更新
                self.status_tracker.update_status("downloading", 20, "下載更新檔案...")
                
                async def download_progress(progress):
                    actual_progress = 20 + int(progress * 0.4)  # 20-60%
                    self.status_tracker.update_status("downloading", actual_progress, 
                                                    f"下載進度：{progress}%")
                    await self.notifier.notify_update_progress("下載更新", actual_progress)
                
                download_path = await self.downloader.download_update(
                    update_info["download_url"], download_progress
                )
                
                # 4. 執行更新
                self.status_tracker.update_status("updating", 60, "安裝更新...")
                await self.notifier.notify_update_progress("安裝更新", 60)
                
                success = await self._install_update(download_path, update_info["latest_version"])
                
                if success:
                    # 5. 清理舊備份
                    if self.config["security"]["backup_enabled"]:
                        self.backup_manager.cleanup_old_backups(
                            self.config["security"]["max_backups"]
                        )
                    
                    # 6. 清理下載檔案
                    self.downloader.cleanup_downloads(keep_latest=2)
                    
                    # 計算更新時間
                    duration = (datetime.now() - start_time).total_seconds()
                    
                    # 通知更新完成
                    result = {
                        "success": True,
                        "old_version": update_info["current_version"],
                        "new_version": update_info["latest_version"],
                        "duration": duration,
                        "backup_id": backup_id,
                        "restart_required": True
                    }
                    
                    self.update_logger.finish_log("success")
                    await self.notifier.notify_update_complete(result)
                    
                    # 7. 執行重啟
                    self.status_tracker.update_status("restarting", 90, "準備重啟...")
                    await self.notifier.notify_update_progress("準備重啟", 90)
                    
                    # 延遲一下讓通知發送完成
                    await asyncio.sleep(2)
                    
                    # 執行重啟
                    await self.restart_manager.execute_restart("update_restart")
                    
                    return result
                else:
                    raise Exception("更新安裝失敗")
                    
            except Exception as e:
                self.logger.error(f"更新過程中發生錯誤: {e}")
                
                # 嘗試回滾
                if backup_id and self.config["security"]["backup_enabled"]:
                    try:
                        self.logger.info(f"嘗試回滾到備份: {backup_id}")
                        if self.backup_manager.rollback_to_backup(backup_id):
                            self.logger.info("回滾成功")
                        else:
                            self.logger.error("回滾失敗")
                    except Exception as rollback_error:
                        self.logger.error(f"回滾時發生錯誤: {rollback_error}")
                
                # 記錄錯誤
                self.update_logger.finish_log("failed", str(e))
                self.status_tracker.set_error(str(e))
                await self.notifier.notify_update_error(e)
                
                return {
                    "success": False, 
                    "error": str(e),
                    "backup_id": backup_id
                }
    
    async def _install_update(self, download_path: str, version: str) -> bool:
        """
        安裝更新
        
        Args:
            download_path: 下載檔案路徑
            version: 版本號
            
        Returns:
            安裝是否成功
        """
        try:
            self.logger.info(f"開始安裝更新: {version}")
            
            # 創建臨時目錄
            temp_dir = "temp/update"
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            os.makedirs(temp_dir, exist_ok=True)
            
            # 解壓更新檔案
            with zipfile.ZipFile(download_path, 'r') as zip_file:
                zip_file.extractall(temp_dir)
            
            # 查找解壓後的目錄
            version_clean = version.replace('v', '')
            possible_dirs = [
                f"PigPig-discord-LLM-bot-{version_clean}",
                f"PigPig-discord-LLM-bot-{version}",
                "PigPig-discord-LLM-bot-main"
            ]
            
            source_dir = None
            for dir_name in possible_dirs:
                potential_path = os.path.join(temp_dir, dir_name)
                if os.path.exists(potential_path):
                    source_dir = potential_path
                    break
            
            if not source_dir:
                # 檢查是否直接解壓到 temp_dir
                items = os.listdir(temp_dir)
                if len(items) == 1 and os.path.isdir(os.path.join(temp_dir, items[0])):
                    source_dir = os.path.join(temp_dir, items[0])
                else:
                    raise Exception("無法找到解壓後的源代碼目錄")
            
            self.logger.info(f"找到源代碼目錄: {source_dir}")
            
            # 獲取保護檔案列表
            protected_files = set(self.config["security"]["protected_files"])
            protected_files.add("temp")  # 保護臨時目錄
            protected_files.add("data/backups")  # 保護備份目錄
            
            # 刪除舊檔案（除了保護檔案）
            current_items = set(os.listdir("."))
            for item in current_items:
                if item not in protected_files and not item.startswith('.'):
                    item_path = os.path.join(".", item)
                    try:
                        if os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                        else:
                            os.remove(item_path)
                        self.logger.debug(f"已刪除舊項目: {item}")
                    except Exception as e:
                        self.logger.warning(f"刪除舊項目失敗 {item}: {e}")
            
            # 複製新檔案
            for item in os.listdir(source_dir):
                if item not in protected_files:
                    source_item = os.path.join(source_dir, item)
                    dest_item = os.path.join(".", item)
                    
                    try:
                        if os.path.isdir(source_item):
                            shutil.copytree(source_item, dest_item, dirs_exist_ok=True)
                        else:
                            shutil.copy2(source_item, dest_item)
                        self.logger.debug(f"已複製新項目: {item}")
                    except Exception as e:
                        self.logger.warning(f"複製新項目失敗 {item}: {e}")
            
            # 清理臨時目錄
            shutil.rmtree(temp_dir, ignore_errors=True)
            
            # 驗證安裝
            if self._verify_installation():
                self.logger.info("更新安裝成功")
                return True
            else:
                raise Exception("安裝驗證失敗")
                
        except Exception as e:
            self.logger.error(f"安裝更新時發生錯誤: {e}")
            # 清理可能的臨時檔案
            if os.path.exists("temp/update"):
                shutil.rmtree("temp/update", ignore_errors=True)
            raise e
    
    def _verify_installation(self) -> bool:
        """驗證安裝是否成功"""
        try:
            # 檢查關鍵檔案是否存在
            critical_files = ["bot.py", "main.py", "requirements.txt"]
            for file_path in critical_files:
                if not os.path.exists(file_path):
                    self.logger.error(f"關鍵檔案不存在: {file_path}")
                    return False
            
            # 檢查配置檔案是否完整
            if not self.config_protector.verify_configs():
                self.logger.error("配置檔案驗證失敗")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"驗證安裝時發生錯誤: {e}")
            return False
    
    def _start_auto_check(self):
        """啟動自動檢查"""
        @tasks.loop(seconds=self.config["auto_update"]["check_interval"])
        async def auto_check():
            try:
                self.logger.info("執行自動更新檢查...")
                update_info = await self.check_for_updates()
                
                if (update_info.get("update_available") and 
                    self.config["auto_update"]["require_owner_confirmation"]):
                    await self.notifier.notify_update_available(update_info)
                    
            except Exception as e:
                self.logger.error(f"自動檢查更新時發生錯誤: {e}")
                await self.notifier.notify_update_error(e, "自動檢查更新")
        
        auto_check.start()
        self.logger.info(f"自動檢查已啟動，間隔: {self.config['auto_update']['check_interval']}秒")
    
    def get_status(self) -> Dict[str, Any]:
        """獲取更新系統狀態"""
        return {
            "status": self.status_tracker.current_status,
            "progress": self.status_tracker.progress,
            "operation": self.status_tracker.current_operation,
            "error": self.status_tracker.error_message,
            "last_check": self.status_tracker.last_check_time.isoformat() if self.status_tracker.last_check_time else None,
            "auto_update_enabled": self.config["auto_update"]["enabled"],
            "current_version": self.version_checker.get_current_version()
        }
    
    async def post_restart_initialization(self):
        """重啟後初始化"""
        try:
            # 執行重啟後檢查
            await self.restart_manager.post_restart_check()
        except Exception as e:
            self.logger.error(f"重啟後初始化失敗: {e}")