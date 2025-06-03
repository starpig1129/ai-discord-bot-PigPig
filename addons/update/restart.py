"""
優雅重啟管理模組

負責管理 Bot 的重啟流程，確保服務平穩過渡。
"""

import os
import sys
import json
import asyncio
import logging
import subprocess
from datetime import datetime
from typing import Dict, Any, Optional


class GracefulRestartManager:
    """優雅重啟管理器"""
    
    def __init__(self, bot, restart_config: Optional[Dict[str, Any]] = None):
        """
        初始化重啟管理器
        
        Args:
            bot: Discord Bot 實例
            restart_config: 重啟配置
        """
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        
        # 預設重啟配置
        default_config = {
            "graceful_shutdown_timeout": 30,
            "restart_command": "python main.py",
            "pre_restart_delay": 5,
            "restart_flag_file": "data/restart_flag.json"
        }
        
        if restart_config:
            default_config.update(restart_config)
        
        self.restart_config = default_config
        
        # 確保 data 目錄存在
        os.makedirs("data", exist_ok=True)
    
    async def prepare_restart(self, reason: str = "update_restart") -> None:
        """
        準備重啟
        
        Args:
            reason: 重啟原因
        """
        try:
            self.logger.info("開始準備重啟...")
            
            # 1. 通知所有相關頻道即將重啟
            await self._notify_restart_preparation()
            
            # 2. 保存當前狀態
            await self._save_current_state(reason)
            
            # 3. 停止正在執行的任務
            await self._stop_background_tasks()
            
            # 4. 等待延遲時間
            if self.restart_config["pre_restart_delay"] > 0:
                self.logger.info(f"等待 {self.restart_config['pre_restart_delay']} 秒後重啟...")
                await asyncio.sleep(self.restart_config["pre_restart_delay"])
            
            self.logger.info("重啟準備完成")
            
        except Exception as e:
            self.logger.error(f"準備重啟時發生錯誤: {e}")
            raise e
    
    async def execute_restart(self, reason: str = "update_restart") -> None:
        """
        執行重啟
        
        Args:
            reason: 重啟原因
        """
        try:
            self.logger.info("開始執行重啟...")
            
            # 準備重啟
            await self.prepare_restart(reason)
            
            # 保存重啟標記
            restart_info = {
                "restart_time": datetime.now().isoformat(),
                "reason": reason,
                "restart_command": self.restart_config["restart_command"],
                "pid": os.getpid()
            }
            
            flag_file = self.restart_config["restart_flag_file"]
            with open(flag_file, "w", encoding='utf-8') as f:
                json.dump(restart_info, f, indent=2, ensure_ascii=False)
            
            self.logger.info("重啟標記已保存，準備關閉 Bot...")
            
            # 通知重啟開始
            await self._notify_restart_start()
            
            # 優雅關閉 Bot
            await self.bot.close()
            
            # 等待一小段時間確保 Bot 完全關閉
            await asyncio.sleep(2)
            
            # 執行重啟命令
            self._execute_restart_command()
            
        except Exception as e:
            self.logger.error(f"執行重啟時發生錯誤: {e}")
            await self._handle_restart_failure(e)
            raise e
    
    async def post_restart_check(self) -> bool:
        """
        重啟後健康檢查
        
        Returns:
            檢查是否通過
        """
        try:
            flag_file = self.restart_config["restart_flag_file"]
            
            # 檢查重啟標記
            if os.path.exists(flag_file):
                with open(flag_file, "r", encoding='utf-8') as f:
                    restart_info = json.load(f)
                
                self.logger.info("檢測到重啟標記，執行重啟後檢查...")
                
                # 基本健康檢查
                health_ok = await self._perform_health_check()
                
                if health_ok:
                    # 發送重啟成功通知
                    await self._notify_restart_success(restart_info)
                    
                    # 清理重啟標記
                    os.remove(flag_file)
                    self.logger.info("重啟後檢查完成，系統運行正常")
                    return True
                else:
                    # 發送重啟失敗通知
                    await self._notify_restart_failure(Exception("健康檢查失敗"))
                    return False
            else:
                # 正常啟動，不是重啟
                return True
                
        except Exception as e:
            self.logger.error(f"重啟後檢查時發生錯誤: {e}")
            await self._notify_restart_failure(e)
            return False
    
    async def _notify_restart_preparation(self) -> None:
        """通知重啟準備"""
        try:
            # 這裡可以向特定頻道或用戶發送通知
            # 由於即將重啟，保持簡單
            pass
        except Exception as e:
            self.logger.error(f"發送重啟準備通知時發生錯誤: {e}")
    
    async def _save_current_state(self, reason: str) -> None:
        """
        保存當前狀態
        
        Args:
            reason: 重啟原因
        """
        try:
            # 保存對話歷史
            if hasattr(self.bot, 'save_dialogue_history'):
                self.bot.save_dialogue_history()
            
            # 保存其他重要狀態
            state_info = {
                "timestamp": datetime.now().isoformat(),
                "reason": reason,
                "guild_count": len(self.bot.guilds),
                "user_count": len(self.bot.users)
            }
            
            with open("data/pre_restart_state.json", "w", encoding='utf-8') as f:
                json.dump(state_info, f, indent=2, ensure_ascii=False)
            
            self.logger.info("當前狀態已保存")
            
        except Exception as e:
            self.logger.error(f"保存當前狀態時發生錯誤: {e}")
    
    async def _stop_background_tasks(self) -> None:
        """停止背景任務"""
        try:
            # 停止所有正在運行的任務
            # 這裡可以添加具體的任務停止邏輯
            
            # 關閉數據庫連接等
            # 例如：await self.bot.db.close()
            
            self.logger.info("背景任務已停止")
            
        except Exception as e:
            self.logger.error(f"停止背景任務時發生錯誤: {e}")
    
    async def _notify_restart_start(self) -> None:
        """通知重啟開始"""
        try:
            # 發送重啟開始的最後通知
            pass
        except Exception as e:
            self.logger.error(f"發送重啟開始通知時發生錯誤: {e}")
    
    def _execute_restart_command(self) -> None:
        """執行重啟命令"""
        try:
            command = self.restart_config["restart_command"]
            self.logger.info(f"執行重啟命令: {command}")
            
            # 分離當前進程，在新進程中啟動
            if os.name == 'nt':  # Windows
                subprocess.Popen(command, shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:  # Unix/Linux
                subprocess.Popen(command.split(), start_new_session=True)
            
            # 退出當前進程
            sys.exit(0)
            
        except Exception as e:
            self.logger.error(f"執行重啟命令時發生錯誤: {e}")
            sys.exit(1)
    
    async def _perform_health_check(self) -> bool:
        """
        執行健康檢查
        
        Returns:
            健康檢查是否通過
        """
        try:
            # 檢查 Bot 是否正常連線
            if not self.bot.is_ready():
                self.logger.error("Bot 未就緒")
                return False
            
            # 檢查關鍵文件是否存在
            critical_files = ["settings.json", "bot.py", "main.py"]
            for file_path in critical_files:
                if not os.path.exists(file_path):
                    self.logger.error(f"關鍵文件不存在: {file_path}")
                    return False
            
            # 檢查是否能正常連接到 Discord
            try:
                latency = self.bot.latency
                if latency > 5.0:  # 延遲超過5秒認為異常
                    self.logger.warning(f"網路延遲較高: {latency:.2f}s")
                    return False
            except:
                self.logger.error("無法獲取網路延遲資訊")
                return False
            
            # 檢查記憶體使用情況（簡單檢查）
            try:
                import psutil
                process = psutil.Process()
                memory_percent = process.memory_percent()
                if memory_percent > 90:  # 記憶體使用超過90%
                    self.logger.warning(f"記憶體使用率過高: {memory_percent:.1f}%")
            except ImportError:
                # psutil 未安裝，跳過記憶體檢查
                pass
            except Exception as e:
                self.logger.warning(f"記憶體檢查失敗: {e}")
            
            self.logger.info("健康檢查通過")
            return True
            
        except Exception as e:
            self.logger.error(f"健康檢查時發生錯誤: {e}")
            return False
    
    async def _notify_restart_success(self, restart_info: Dict[str, Any]) -> None:
        """
        通知重啟成功
        
        Args:
            restart_info: 重啟資訊
        """
        try:
            # 使用通知系統發送重啟成功通知
            notifier_cog = self.bot.get_cog("UpdateManagerCog")
            if notifier_cog and hasattr(notifier_cog, 'notifier'):
                await notifier_cog.notifier.notify_restart_success(restart_info)
            
        except Exception as e:
            self.logger.error(f"發送重啟成功通知時發生錯誤: {e}")
    
    async def _notify_restart_failure(self, error: Exception) -> None:
        """
        通知重啟失敗
        
        Args:
            error: 錯誤物件
        """
        try:
            # 使用通知系統發送重啟失敗通知
            notifier_cog = self.bot.get_cog("UpdateManagerCog")
            if notifier_cog and hasattr(notifier_cog, 'notifier'):
                await notifier_cog.notifier.notify_update_error(error, "重啟過程中發生錯誤")
            
        except Exception as e:
            self.logger.error(f"發送重啟失敗通知時發生錯誤: {e}")
    
    async def _handle_restart_failure(self, error: Exception) -> None:
        """
        處理重啟失敗
        
        Args:
            error: 錯誤物件
        """
        try:
            self.logger.error(f"重啟失敗: {error}")
            
            # 嘗試恢復到重啟前的狀態
            await self._restore_pre_restart_state()
            
            # 發送錯誤通知
            await self._notify_restart_failure(error)
            
        except Exception as e:
            self.logger.error(f"處理重啟失敗時發生錯誤: {e}")
    
    async def _restore_pre_restart_state(self) -> None:
        """恢復重啟前的狀態"""
        try:
            state_file = "data/pre_restart_state.json"
            if os.path.exists(state_file):
                with open(state_file, "r", encoding='utf-8') as f:
                    state_info = json.load(f)
                
                self.logger.info(f"嘗試恢復到重啟前的狀態: {state_info['timestamp']}")
                
                # 這裡可以添加具體的狀態恢復邏輯
                # 例如恢復對話歷史、重新連接數據庫等
                
                # 清理狀態文件
                os.remove(state_file)
                
        except Exception as e:
            self.logger.error(f"恢復重啟前狀態時發生錯誤: {e}")
    
    def is_restart_pending(self) -> bool:
        """
        檢查是否有待處理的重啟
        
        Returns:
            是否有待處理的重啟
        """
        flag_file = self.restart_config["restart_flag_file"]
        return os.path.exists(flag_file)
    
    def get_restart_info(self) -> Optional[Dict[str, Any]]:
        """
        獲取重啟資訊
        
        Returns:
            重啟資訊字典，如果沒有則返回 None
        """
        flag_file = self.restart_config["restart_flag_file"]
        if os.path.exists(flag_file):
            try:
                with open(flag_file, "r", encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"讀取重啟資訊時發生錯誤: {e}")
        
        return None
    
    def cancel_restart(self) -> bool:
        """
        取消待處理的重啟
        
        Returns:
            取消是否成功
        """
        try:
            flag_file = self.restart_config["restart_flag_file"]
            if os.path.exists(flag_file):
                os.remove(flag_file)
                self.logger.info("已取消待處理的重啟")
                return True
            return False
        except Exception as e:
            self.logger.error(f"取消重啟時發生錯誤: {e}")
            return False