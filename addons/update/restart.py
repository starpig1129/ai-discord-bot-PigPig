"""
簡單可靠的重啟管理模組

採用直接、簡單但可靠的重啟機制，放棄複雜的進程分離方案。
使用系統級重啟命令和強制退出機制確保重啟成功。
"""

import os
import sys
import json
import asyncio
import logging
import subprocess
import shutil
import time
import platform
from datetime import datetime
from typing import Dict, Any, Optional


class SimpleRestartManager:
    """簡單可靠的重啟管理器"""
    
    def __init__(self, bot, restart_config: Optional[Dict[str, Any]] = None):
        """
        初始化重啟管理器
        
        Args:
            bot: Discord Bot 實例
            restart_config: 重啟配置
        """
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        
        # 簡化的重啟配置
        default_config = {
            "restart_flag_file": "data/restart_flag.json",
            "restart_delay": 3,  # 重啟前延遲秒數
            "shutdown_timeout": 10,  # Bot 關閉超時時間
        }
        
        if restart_config:
            default_config.update(restart_config)
        
        self.restart_config = default_config
        
        # 確保 data 目錄存在
        os.makedirs("data", exist_ok=True)
    
    async def execute_restart(self, reason: str = "update_restart") -> None:
        """
        執行簡單重啟流程
        
        Args:
            reason: 重啟原因
        """
        try:
            self.logger.info("=== 開始簡單重啟流程 ===")
            self.logger.info(f"重啟原因: {reason}")
            self.logger.info(f"當前進程 PID: {os.getpid()}")
            
            # 1. 保存重啟標記
            await self._save_restart_flag(reason)
            
            # 2. 通知即將重啟
            await self._notify_restart()
            
            # 3. 優雅關閉 Bot
            await self._shutdown_bot()
            
            # 4. 執行重啟命令
            self._execute_simple_restart()
            
        except Exception as e:
            self.logger.error(f"重啟流程失敗: {e}")
            await self._handle_restart_failure(e)
            raise e
    
    async def post_restart_check(self) -> bool:
        """
        重啟後檢查
        
        Returns:
            檢查是否通過
        """
        try:
            flag_file = self.restart_config["restart_flag_file"]
            
            if os.path.exists(flag_file):
                with open(flag_file, "r", encoding='utf-8') as f:
                    restart_info = json.load(f)
                
                self.logger.info("檢測到重啟標記，執行重啟後檢查...")
                self.logger.info(f"重啟原因: {restart_info.get('reason', 'unknown')}")
                self.logger.info(f"重啟時間: {restart_info.get('restart_time', 'unknown')}")
                
                # 簡單健康檢查
                if await self._simple_health_check():
                    await self._notify_restart_success(restart_info)
                    os.remove(flag_file)  # 清理重啟標記
                    self.logger.info("重啟成功，系統運行正常")
                    return True
                else:
                    await self._notify_restart_failure(Exception("健康檢查失敗"))
                    return False
            
            return True  # 正常啟動
            
        except Exception as e:
            self.logger.error(f"重啟後檢查失敗: {e}")
            await self._notify_restart_failure(e)
            return False
    
    async def _save_restart_flag(self, reason: str) -> None:
        """保存重啟標記"""
        try:
            restart_info = {
                "restart_time": datetime.now().isoformat(),
                "reason": reason,
                "pid": os.getpid(),
                "working_directory": os.getcwd(),
                "python_executable": sys.executable
            }
            
            flag_file = self.restart_config["restart_flag_file"]
            with open(flag_file, "w", encoding='utf-8') as f:
                json.dump(restart_info, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"重啟標記已保存: {flag_file}")
            
        except Exception as e:
            self.logger.error(f"保存重啟標記失敗: {e}")
            raise e
    
    async def _notify_restart(self) -> None:
        """通知即將重啟"""
        try:
            # 簡單的重啟通知
            self.logger.info("發送重啟通知...")
            
            # 可以在這裡添加向特定頻道發送通知的邏輯
            # 但保持簡單，避免複雜的通知機制導致重啟失敗
            
        except Exception as e:
            self.logger.warning(f"發送重啟通知失敗: {e}")
            # 通知失敗不應阻止重啟流程
    
    async def _shutdown_bot(self) -> None:
        """關閉 Bot"""
        try:
            self.logger.info("開始關閉 Discord Bot...")
            
            # 設置超時機制
            shutdown_timeout = self.restart_config["shutdown_timeout"]
            
            try:
                # 嘗試優雅關閉
                await asyncio.wait_for(self.bot.close(), timeout=shutdown_timeout)
                self.logger.info("Bot 已優雅關閉")
            except asyncio.TimeoutError:
                self.logger.warning(f"Bot 關閉超時 ({shutdown_timeout}s)，將強制關閉")
                # 超時後不做額外處理，直接進入重啟流程
            
            # 短暫等待確保資源釋放
            await asyncio.sleep(1)
            
        except Exception as e:
            self.logger.warning(f"關閉 Bot 時發生錯誤: {e}")
            # 關閉失敗不應阻止重啟流程
    
    def _execute_simple_restart(self) -> None:
        """執行簡單重啟"""
        try:
            self.logger.info("=== 開始執行簡單重啟 ===")
            
            current_dir = os.getcwd()
            python_exe = sys.executable
            
            self.logger.info(f"工作目錄: {current_dir}")
            self.logger.info(f"Python 執行檔: {python_exe}")
            
            # 等待延遲
            restart_delay = self.restart_config["restart_delay"]
            if restart_delay > 0:
                self.logger.info(f"等待 {restart_delay} 秒後重啟...")
                time.sleep(restart_delay)
            
            if os.name == 'nt':  # Windows
                success = self._windows_simple_restart(python_exe, current_dir)
            else:  # Unix/Linux
                success = self._unix_simple_restart(python_exe, current_dir)
            
            if success:
                self.logger.info("重啟命令執行成功，即將退出當前進程")
                # 強制退出當前進程
                os._exit(0)
            else:
                self.logger.error("重啟命令執行失敗")
                raise Exception("重啟命令執行失敗")
                
        except Exception as e:
            self.logger.error(f"執行重啟時發生錯誤: {e}")
            self._create_emergency_restart_file()
            raise e
    
    def _windows_simple_restart(self, python_exe: str, current_dir: str) -> bool:
        """Windows 簡單重啟方法"""
        try:
            self.logger.info("使用 Windows 簡單重啟方法")
            
            # 創建簡單的重啟批次檔
            batch_content = f"""@echo off
chcp 65001 >nul 2>&1
timeout /t 3 /nobreak >nul
cd /d "{current_dir}"
"{python_exe}" main.py
exit
"""
            
            batch_file = os.path.join(current_dir, "temp_restart.bat")
            
            with open(batch_file, 'w', encoding='utf-8') as f:
                f.write(batch_content)
            
            self.logger.info(f"重啟批次檔已創建: {batch_file}")
            
            # 使用 start 命令執行批次檔，並關閉當前視窗
            cmd = f'start "PigPig Bot Restart" /B "{batch_file}" && exit'
            
            self.logger.info(f"執行重啟命令: {cmd}")
            
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=current_dir,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                self.logger.info("Windows 重啟命令執行成功")
                
                # 延遲刪除批次檔
                import threading
                def cleanup_batch():
                    time.sleep(30)  # 等待30秒後清理
                    try:
                        if os.path.exists(batch_file):
                            os.remove(batch_file)
                    except:
                        pass
                
                cleanup_thread = threading.Thread(target=cleanup_batch, daemon=True)
                cleanup_thread.start()
                
                return True
            else:
                self.logger.error(f"Windows 重啟命令失敗: {result.stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"Windows 重啟方法失敗: {e}")
            return False
    
    def _unix_simple_restart(self, python_exe: str, current_dir: str) -> bool:
        """Unix/Linux 簡單重啟方法"""
        try:
            self.logger.info("使用 Unix/Linux 簡單重啟方法")
            
            # 創建簡單的重啟腳本
            script_content = f"""#!/bin/bash
sleep 3
cd "{current_dir}"
"{python_exe}" main.py
"""
            
            script_file = os.path.join(current_dir, "temp_restart.sh")
            
            with open(script_file, 'w', encoding='utf-8') as f:
                f.write(script_content)
            
            # 設置執行權限
            os.chmod(script_file, 0o755)
            
            self.logger.info(f"重啟腳本已創建: {script_file}")
            
            # 使用 nohup 在背景執行
            cmd = ["nohup", script_file]
            
            self.logger.info(f"執行重啟命令: {' '.join(cmd)}")
            
            process = subprocess.Popen(
                cmd,
                cwd=current_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True
            )
            
            self.logger.info(f"Unix/Linux 重啟進程已啟動，PID: {process.pid}")
            
            # 延遲刪除腳本檔
            import threading
            def cleanup_script():
                time.sleep(30)  # 等待30秒後清理
                try:
                    if os.path.exists(script_file):
                        os.remove(script_file)
                except:
                    pass
            
            cleanup_thread = threading.Thread(target=cleanup_script, daemon=True)
            cleanup_thread.start()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Unix/Linux 重啟方法失敗: {e}")
            return False
    
    async def _simple_health_check(self) -> bool:
        """簡單健康檢查"""
        try:
            # 檢查 Bot 是否就緒
            if not self.bot.is_ready():
                self.logger.error("Bot 未就緒")
                return False
            
            # 檢查基本連線
            try:
                latency = self.bot.latency
                if latency > 10.0:  # 延遲超過10秒認為異常
                    self.logger.warning(f"網路延遲過高: {latency:.2f}s")
                    return False
            except:
                self.logger.error("無法獲取網路延遲")
                return False
            
            self.logger.info("健康檢查通過")
            return True
            
        except Exception as e:
            self.logger.error(f"健康檢查失敗: {e}")
            return False
    
    async def _notify_restart_success(self, restart_info: Dict[str, Any]) -> None:
        """通知重啟成功"""
        try:
            self.logger.info("重啟成功")
            
            # 嘗試使用通知系統
            try:
                notifier_cog = self.bot.get_cog("UpdateManagerCog")
                if notifier_cog and hasattr(notifier_cog, 'notifier'):
                    await notifier_cog.notifier.notify_restart_success(restart_info)
            except Exception as e:
                self.logger.warning(f"發送重啟成功通知失敗: {e}")
            
        except Exception as e:
            self.logger.warning(f"處理重啟成功通知時發生錯誤: {e}")
    
    async def _notify_restart_failure(self, error: Exception) -> None:
        """通知重啟失敗"""
        try:
            self.logger.error(f"重啟失敗: {error}")
            
            # 嘗試使用通知系統
            try:
                notifier_cog = self.bot.get_cog("UpdateManagerCog")
                if notifier_cog and hasattr(notifier_cog, 'notifier'):
                    await notifier_cog.notifier.notify_update_error(error, "重啟失敗")
            except Exception as e:
                self.logger.warning(f"發送重啟失敗通知失敗: {e}")
            
        except Exception as e:
            self.logger.warning(f"處理重啟失敗通知時發生錯誤: {e}")
    
    async def _handle_restart_failure(self, error: Exception) -> None:
        """處理重啟失敗"""
        try:
            self.logger.error(f"重啟失敗，創建緊急重啟指示")
            await self._notify_restart_failure(error)
            self._create_emergency_restart_file()
            
        except Exception as e:
            self.logger.error(f"處理重啟失敗時發生錯誤: {e}")
    
    def _create_emergency_restart_file(self) -> None:
        """創建緊急重啟指示文件"""
        try:
            emergency_file = "EMERGENCY_RESTART_NEEDED.txt"
            
            content = f"""
=== PigPig Discord Bot 緊急重啟指示 ===

時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
自動重啟失敗，需要手動重啟 Bot。

手動重啟步驟:
1. 關閉當前 Bot 進程
2. 執行以下命令重啟:
   
   Windows:
   manual_restart.bat
   
   或直接執行:
   {sys.executable} main.py

3. 確認 Bot 正常啟動後刪除此文件

工作目錄: {os.getcwd()}
Python 執行檔: {sys.executable}

============================================
"""
            
            with open(emergency_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self.logger.info(f"緊急重啟指示已創建: {emergency_file}")
            
        except Exception as e:
            self.logger.error(f"創建緊急重啟指示失敗: {e}")
    
    def is_restart_pending(self) -> bool:
        """檢查是否有待處理的重啟"""
        flag_file = self.restart_config["restart_flag_file"]
        return os.path.exists(flag_file)
    
    def get_restart_info(self) -> Optional[Dict[str, Any]]:
        """獲取重啟資訊"""
        try:
            flag_file = self.restart_config["restart_flag_file"]
            if os.path.exists(flag_file):
                with open(flag_file, "r", encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.error(f"讀取重啟資訊失敗: {e}")
        
        return None
    
    def cancel_restart(self) -> bool:
        """取消重啟"""
        try:
            flag_file = self.restart_config["restart_flag_file"]
            if os.path.exists(flag_file):
                os.remove(flag_file)
                self.logger.info("重啟已取消")
                return True
        except Exception as e:
            self.logger.error(f"取消重啟失敗: {e}")
        
        return False


# 向後相容性別名
GracefulRestartManager = SimpleRestartManager