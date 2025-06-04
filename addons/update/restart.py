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
import shutil
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
            self.logger.info(f"原始重啟命令: {command}")
            
            # Windows 環境特殊處理
            if os.name == 'nt':
                success = self._windows_restart(command)
                if not success:
                    raise Exception("Windows 重啟失敗")
            else:  # Unix/Linux
                self._unix_restart(command)
            
            # 給新進程一些時間啟動
            self.logger.info("等待 3 秒確保新進程啟動...")
            import time
            time.sleep(3)
            
            # 退出當前進程
            self.logger.info("準備退出當前進程...")
            sys.exit(0)
            
        except Exception as e:
            self.logger.error(f"執行重啟命令時發生錯誤: {e}")
            self.logger.error(f"錯誤類型: {type(e).__name__}")
            import traceback
            self.logger.error(f"錯誤堆疊: {traceback.format_exc()}")
            sys.exit(1)
    
    def _windows_restart(self, command: str) -> bool:
        """Windows 專用重啟方法"""
        try:
            current_dir = os.getcwd()
            self.logger.info(f"當前工作目錄: {current_dir}")
            
            # 檢測虛擬環境
            venv_path = os.environ.get('VIRTUAL_ENV')
            if venv_path:
                self.logger.info(f"檢測到虛擬環境: {venv_path}")
                python_exe = os.path.join(venv_path, 'Scripts', 'python.exe')
                if os.path.exists(python_exe):
                    command = f'"{python_exe}" main.py'
                    self.logger.info(f"使用虛擬環境 Python: {command}")
                else:
                    self.logger.warning(f"虛擬環境 Python 不存在: {python_exe}")
            
            # 記錄環境資訊
            self.logger.info(f"PATH: {os.environ.get('PATH', 'N/A')[:200]}...")
            self.logger.info(f"PYTHON 路徑: {shutil.which('python')}")
            
            # 方法 1: 創建 PowerShell 腳本重啟
            script_path = self.create_windows_restart_script()
            if script_path and self.execute_powershell_restart(script_path):
                return True
            
            # 方法 2: 創建批次檔案重啟
            if self._create_restart_batch(command, current_dir):
                return True
                
            # 方法 3: 使用 subprocess 多種方式
            return self._subprocess_restart_methods(command, current_dir)
            
        except Exception as e:
            self.logger.error(f"Windows 重啟過程發生錯誤: {e}")
            return False
    
    def _create_restart_batch(self, command: str, current_dir: str) -> bool:
        """創建批次檔案進行重啟"""
        try:
            batch_file = os.path.join(current_dir, "restart_bot.bat")
            
            # 創建批次檔案內容
            batch_content = f"""@echo off
cd /d "{current_dir}"
echo Starting PigPig Discord Bot...
{command}
pause
"""
            
            # 寫入批次檔案
            with open(batch_file, 'w', encoding='utf-8') as f:
                f.write(batch_content)
            
            self.logger.info(f"批次檔案已創建: {batch_file}")
            
            # 執行批次檔案
            process = subprocess.Popen(
                [batch_file],
                cwd=current_dir,
                creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL
            )
            
            self.logger.info(f"批次檔案重啟成功，PID: {process.pid}")
            
            # 延遲刪除批次檔案（讓它有時間執行）
            import threading
            def delayed_cleanup():
                import time
                time.sleep(10)
                try:
                    if os.path.exists(batch_file):
                        os.remove(batch_file)
                        self.logger.info("批次檔案已清理")
                except:
                    pass
            
            thread = threading.Thread(target=delayed_cleanup, daemon=True)
            thread.start()
            
            return True
            
        except Exception as e:
            self.logger.error(f"批次檔案重啟失敗: {e}")
            return False
    
    def _subprocess_restart_methods(self, command: str, current_dir: str) -> bool:
        """使用 subprocess 的多種重啟方法"""
        restart_methods = [
            # 方法 1: 使用 cmd /c 在新控制台啟動
            {
                "cmd": ['cmd', '/c', f'cd /d "{current_dir}" && {command}'],
                "flags": subprocess.CREATE_NEW_CONSOLE,
                "shell": False
            },
            # 方法 2: 使用 start 命令
            {
                "cmd": f'start "PigPig Bot" cmd /k "cd /d {current_dir} && {command}"',
                "flags": subprocess.DETACHED_PROCESS,
                "shell": True
            },
            # 方法 3: 直接執行
            {
                "cmd": command,
                "flags": subprocess.CREATE_NEW_CONSOLE,
                "shell": True
            }
        ]
        
        for i, method in enumerate(restart_methods, 1):
            try:
                self.logger.info(f"嘗試重啟方法 {i}: {method['cmd']}")
                
                process = subprocess.Popen(
                    method["cmd"],
                    shell=method["shell"],
                    cwd=current_dir,
                    creationflags=method["flags"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL
                )
                
                self.logger.info(f"重啟方法 {i} 執行成功，PID: {process.pid}")
                return True
                
            except Exception as method_error:
                self.logger.error(f"重啟方法 {i} 失敗: {method_error}")
                continue
        
        return False
    
    def _unix_restart(self, command: str) -> None:
        """Unix/Linux 重啟方法"""
        self.logger.info(f"Unix/Linux 系統重啟命令: {command}")
        subprocess.Popen(command.split(), start_new_session=True)
    
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
    def create_windows_restart_script(self) -> str:
            """
            創建 Windows PowerShell 重啟腳本
            
            Returns:
                腳本檔案路徑
            """
            try:
                current_dir = os.getcwd()
                script_path = os.path.join(current_dir, "restart_bot.ps1")
                
                # 檢測虛擬環境
                venv_path = os.environ.get('VIRTUAL_ENV')
                if venv_path:
                    python_exe = os.path.join(venv_path, 'Scripts', 'python.exe')
                    if not os.path.exists(python_exe):
                        python_exe = "python.exe"
                else:
                    python_exe = "python.exe"
                
                # PowerShell 腳本內容
                ps_content = f'''# PigPig Discord Bot 重啟腳本
    Write-Host "等待 5 秒後重啟 Bot..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5

    Write-Host "切換到工作目錄..." -ForegroundColor Green
    Set-Location "{current_dir}"

    Write-Host "啟動 PigPig Discord Bot..." -ForegroundColor Green
    try {{
        & "{python_exe}" main.py
    }} catch {{
        Write-Host "啟動失敗，嘗試使用 python 命令..." -ForegroundColor Red
        & python main.py
    }}

    Write-Host "Bot 已結束，按任意鍵關閉視窗..." -ForegroundColor Cyan
    Read-Host
    '''
                
                # 寫入 PowerShell 腳本
                with open(script_path, 'w', encoding='utf-8') as f:
                    f.write(ps_content)
                
                self.logger.info(f"PowerShell 重啟腳本已創建: {script_path}")
                return script_path
                
            except Exception as e:
                self.logger.error(f"創建 PowerShell 腳本失敗: {e}")
                return ""
    
    def execute_powershell_restart(self, script_path: str) -> bool:
        """
        執行 PowerShell 重啟腳本
        
        Args:
            script_path: PowerShell 腳本路徑
            
        Returns:
            執行是否成功
        """
        try:
            # 方法 1: 使用 PowerShell 執行
            ps_cmd = [
                "powershell.exe", 
                "-WindowStyle", "Normal",
                "-ExecutionPolicy", "Bypass",
                "-File", script_path
            ]
            
            process = subprocess.Popen(
                ps_cmd,
                creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL
            )
            
            self.logger.info(f"PowerShell 重啟腳本執行成功，PID: {process.pid}")
            return True
            
        except Exception as e:
            self.logger.error(f"PowerShell 重啟失敗: {e}")
            
            # 方法 2: 備用 - 使用 cmd 執行 PowerShell
            try:
                cmd_ps = f'powershell.exe -WindowStyle Normal -ExecutionPolicy Bypass -File "{script_path}"'
                process = subprocess.Popen(
                    cmd_ps,
                    shell=True,
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                
                self.logger.info(f"CMD PowerShell 重啟執行成功，PID: {process.pid}")
                return True
                
            except Exception as e2:
                self.logger.error(f"CMD PowerShell 重啟也失敗: {e2}")
                return False