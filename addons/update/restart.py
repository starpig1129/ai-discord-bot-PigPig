"""
優雅重啟管理模組

負責管理 Bot 的重啟流程，確保服務平穩過渡。
包含詳細的診斷日誌和多重備用重啟機制。
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
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List


class GracefulRestartManager:
    """優雅重啟管理器 - 增強版"""
    
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
            "restart_flag_file": "data/restart_flag.json",
            "restart_diagnostics_file": "data/restart_diagnostics.json",
            "restart_attempts_limit": 3,
            "restart_success_timeout": 60,
            "enable_detailed_logging": True
        }
        
        if restart_config:
            default_config.update(restart_config)
        
        self.restart_config = default_config
        
        # 確保 data 目錄存在
        os.makedirs("data", exist_ok=True)
        os.makedirs("data/restart_logs", exist_ok=True)
        
        # 診斷資訊收集器
        self.diagnostics = RestartDiagnostics(self.logger)
    
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
            
            # 執行增強版重啟命令
            self._execute_enhanced_restart_command()
            
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
        """執行增強版重啟命令"""
        try:
            command = self.restart_config["restart_command"]
            self.logger.info(f"原始重啟命令: {command}")
            
            # Windows 環境使用增強版重啟
            if os.name == 'nt':
                if self.restart_config.get("enable_detailed_logging", True):
                    success = self._enhanced_windows_restart(command)
                    if not success:
                        self.logger.warning("增強版 Windows 重啟失敗，嘗試傳統方法...")
                        success = self._windows_restart(command)
                        if not success:
                            raise Exception("所有 Windows 重啟方法都失敗")
                else:
                    success = self._windows_restart(command)
                    if not success:
                        raise Exception("Windows 重啟失敗")
            else:  # Unix/Linux
                self._unix_restart(command)
            
            # 給新進程一些時間啟動
            self.logger.info("等待 5 秒確保新進程啟動...")
            time.sleep(5)
            
            # 退出當前進程
            self.logger.info("準備退出當前進程...")
            sys.exit(0)
            
        except Exception as e:
            self.logger.error(f"執行增強版重啟命令時發生錯誤: {e}")
            self.logger.error(f"錯誤類型: {type(e).__name__}")
            import traceback
            self.logger.error(f"錯誤堆疊: {traceback.format_exc()}")
            sys.exit(1)
    
    def _enhanced_windows_restart(self, command: str) -> bool:
        """增強版 Windows 重啟方法"""
        try:
            current_dir = os.getcwd()
            self.logger.info("=== 開始增強版 Windows 重啟流程 ===")
            
            # 創建增強版重啟管理器
            enhanced_manager = EnhancedWindowsRestartManager(self.logger, self.diagnostics)
            
            # 執行帶診斷的重啟
            success = enhanced_manager.execute_restart_with_diagnostics(command, current_dir)
            
            if success:
                self.logger.info("增強版重啟執行成功")
                return True
            else:
                self.logger.error("增強版重啟執行失敗")
                return False
                
        except Exception as e:
            self.logger.error(f"增強版 Windows 重啟過程發生錯誤: {e}")
            import traceback
            self.logger.error(f"錯誤堆疊: {traceback.format_exc()}")
            return False
    
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
class RestartDiagnostics:
    """重啟診斷工具類"""
    
    def __init__(self, logger):
        """
        初始化診斷工具
        
        Args:
            logger: 日誌記錄器
        """
        self.logger = logger
        self.diagnostics_data = {}
        
    def collect_system_info(self) -> Dict[str, Any]:
        """收集系統資訊"""
        try:
            system_info = {
                "timestamp": datetime.now().isoformat(),
                "platform": platform.platform(),
                "system": platform.system(),
                "machine": platform.machine(),
                "processor": platform.processor(),
                "python_version": platform.python_version(),
                "python_executable": sys.executable,
                "current_directory": os.getcwd(),
                "process_id": os.getpid(),
                "environment_variables": {
                    "VIRTUAL_ENV": os.environ.get('VIRTUAL_ENV'),
                    "PATH": os.environ.get('PATH', '')[:500] + "..." if len(os.environ.get('PATH', '')) > 500 else os.environ.get('PATH', ''),
                    "PYTHONPATH": os.environ.get('PYTHONPATH'),
                    "CONDA_DEFAULT_ENV": os.environ.get('CONDA_DEFAULT_ENV'),
                    "HOME": os.environ.get('HOME'),
                    "USER": os.environ.get('USER') or os.environ.get('USERNAME')
                }
            }
            
            # 檢查虛擬環境詳細資訊
            if system_info["environment_variables"]["VIRTUAL_ENV"]:
                venv_path = system_info["environment_variables"]["VIRTUAL_ENV"]
                python_exe_path = os.path.join(venv_path, 'Scripts', 'python.exe') if os.name == 'nt' else os.path.join(venv_path, 'bin', 'python')
                system_info["virtual_env_details"] = {
                    "path": venv_path,
                    "python_executable": python_exe_path,
                    "python_exists": os.path.exists(python_exe_path)
                }
            
            # 檢查 Python 路徑
            system_info["python_paths"] = {
                "which_python": shutil.which('python'),
                "which_python3": shutil.which('python3'),
                "sys_executable": sys.executable
            }
            
            self.diagnostics_data["system_info"] = system_info
            self.logger.info("系統資訊收集完成")
            return system_info
            
        except Exception as e:
            self.logger.error(f"收集系統資訊時發生錯誤: {e}")
            return {}
    
    def collect_restart_environment(self) -> Dict[str, Any]:
        """收集重啟環境資訊"""
        try:
            env_info = {
                "timestamp": datetime.now().isoformat(),
                "working_directory": os.getcwd(),
                "main_py_exists": os.path.exists("main.py"),
                "bot_py_exists": os.path.exists("bot.py"),
                "settings_json_exists": os.path.exists("settings.json"),
                "data_directory_exists": os.path.exists("data"),
                "file_permissions": {}
            }
            
            # 檢查重要文件的權限
            important_files = ["main.py", "bot.py", "settings.json"]
            for file_path in important_files:
                if os.path.exists(file_path):
                    try:
                        env_info["file_permissions"][file_path] = {
                            "readable": os.access(file_path, os.R_OK),
                            "writable": os.access(file_path, os.W_OK),
                            "executable": os.access(file_path, os.X_OK)
                        }
                    except Exception as e:
                        env_info["file_permissions"][file_path] = f"Error: {e}"
            
            # 檢查目錄權限
            try:
                env_info["directory_permissions"] = {
                    "current_dir_writable": os.access(os.getcwd(), os.W_OK),
                    "data_dir_writable": os.access("data", os.W_OK) if os.path.exists("data") else False
                }
            except Exception as e:
                env_info["directory_permissions"] = f"Error: {e}"
            
            self.diagnostics_data["restart_environment"] = env_info
            self.logger.info("重啟環境資訊收集完成")
            return env_info
            
        except Exception as e:
            self.logger.error(f"收集重啟環境資訊時發生錯誤: {e}")
            return {}
    
    def save_diagnostics(self, file_path: str = "data/restart_diagnostics.json") -> bool:
        """
        保存診斷資訊到文件
        
        Args:
            file_path: 診斷文件路徑
            
        Returns:
            保存是否成功
        """
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.diagnostics_data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"診斷資訊已保存到: {file_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"保存診斷資訊時發生錯誤: {e}")
            return False
    
    def load_diagnostics(self, file_path: str = "data/restart_diagnostics.json") -> Optional[Dict[str, Any]]:
        """
        從文件載入診斷資訊
        
        Args:
            file_path: 診斷文件路徑
            
        Returns:
            診斷資訊字典，失敗時返回 None
        """
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    diagnostics = json.load(f)
                
                self.logger.info(f"診斷資訊已從 {file_path} 載入")
                return diagnostics
            else:
                self.logger.warning(f"診斷文件不存在: {file_path}")
                return None
                
        except Exception as e:
            self.logger.error(f"載入診斷資訊時發生錯誤: {e}")
            return None


class EnhancedWindowsRestartManager:
    """增強版 Windows 重啟管理器"""
    
    def __init__(self, logger, diagnostics: RestartDiagnostics):
        """
        初始化增強版重啟管理器
        
        Args:
            logger: 日誌記錄器
            diagnostics: 診斷工具
        """
        self.logger = logger
        self.diagnostics = diagnostics
        self.restart_attempts = []
        
    def execute_restart_with_diagnostics(self, command: str, current_dir: str) -> bool:
        """
        執行帶診斷的重啟
        
        Args:
            command: 重啟命令
            current_dir: 當前目錄
            
        Returns:
            重啟是否成功
        """
        try:
            self.logger.info("=== 開始增強版重啟流程 ===")
            
            # 收集診斷資訊
            system_info = self.diagnostics.collect_system_info()
            env_info = self.diagnostics.collect_restart_environment()
            
            # 保存診斷資訊
            self.diagnostics.save_diagnostics()
            
            # 記錄詳細的環境資訊
            self._log_detailed_environment(system_info, env_info)
            
            # 準備多種重啟方法
            restart_methods = self._prepare_restart_methods(command, current_dir, system_info)
            
            # 依序嘗試每種重啟方法
            for i, method in enumerate(restart_methods, 1):
                self.logger.info(f"=== 嘗試重啟方法 {i}/{len(restart_methods)}: {method['name']} ===")
                
                attempt_result = self._attempt_restart_method(method, i)
                self.restart_attempts.append(attempt_result)
                
                if attempt_result["success"]:
                    self.logger.info(f"重啟方法 {i} 成功！")
                    self._save_restart_success_log(attempt_result)
                    return True
                else:
                    self.logger.warning(f"重啟方法 {i} 失敗: {attempt_result['error']}")
                    
                # 短暫延遲再嘗試下一種方法
                time.sleep(1)
            
            # 所有方法都失敗
            self.logger.error("所有重啟方法都失敗")
            self._save_restart_failure_log()
            return False
            
        except Exception as e:
            self.logger.error(f"增強版重啟流程發生錯誤: {e}")
            import traceback
            self.logger.error(f"錯誤堆疊: {traceback.format_exc()}")
            return False
    
    def _log_detailed_environment(self, system_info: Dict[str, Any], env_info: Dict[str, Any]) -> None:
        """記錄詳細的環境資訊"""
        self.logger.info("=== 系統環境診斷 ===")
        self.logger.info(f"作業系統: {system_info.get('platform', 'Unknown')}")
        self.logger.info(f"Python 版本: {system_info.get('python_version', 'Unknown')}")
        self.logger.info(f"Python 執行檔: {system_info.get('python_executable', 'Unknown')}")
        self.logger.info(f"當前目錄: {system_info.get('current_directory', 'Unknown')}")
        self.logger.info(f"進程 ID: {system_info.get('process_id', 'Unknown')}")
        
        # 虛擬環境資訊
        venv_info = system_info.get('virtual_env_details')
        if venv_info:
            self.logger.info(f"虛擬環境路徑: {venv_info.get('path', 'Unknown')}")
            self.logger.info(f"虛擬環境 Python: {venv_info.get('python_executable', 'Unknown')}")
            self.logger.info(f"虛擬環境 Python 存在: {venv_info.get('python_exists', False)}")
        else:
            self.logger.info("未檢測到虛擬環境")
        
        # Python 路徑
        python_paths = system_info.get('python_paths', {})
        self.logger.info(f"which python: {python_paths.get('which_python', 'Not found')}")
        self.logger.info(f"which python3: {python_paths.get('which_python3', 'Not found')}")
        
        # 文件權限
        file_perms = env_info.get('file_permissions', {})
        for file_path, perms in file_perms.items():
            if isinstance(perms, dict):
                self.logger.info(f"{file_path} 權限: R:{perms.get('readable', False)} W:{perms.get('writable', False)} X:{perms.get('executable', False)}")
            else:
                self.logger.warning(f"{file_path} 權限檢查失敗: {perms}")
    
    def _prepare_restart_methods(self, command: str, current_dir: str, system_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """準備多種重啟方法"""
        methods = []
        
        # 取得最佳的 Python 執行檔路徑
        best_python = self._get_best_python_executable(system_info)
        
        # 方法 1: 使用虛擬環境 Python + 延遲重啟批次檔
        if best_python:
            methods.append({
                "name": "虛擬環境 Python + 延遲批次檔",
                "type": "delayed_batch",
                "command": f'"{best_python}" main.py',
                "delay": 10
            })
        
        # 方法 2: PowerShell 腳本 + 延遲重啟
        methods.append({
            "name": "PowerShell 腳本延遲重啟",
            "type": "powershell_delayed",
            "command": f'"{best_python or "python"}" main.py' if best_python else command,
            "delay": 8
        })
        
        # 方法 3: 使用 START 命令在新視窗啟動
        methods.append({
            "name": "START 命令新視窗",
            "type": "start_new_window",
            "command": f'start "PigPig Bot" /D "{current_dir}" cmd /k "{best_python or "python"} main.py"' if best_python else f'start "PigPig Bot" /D "{current_dir}" cmd /k "{command}"'
        })
        
        # 方法 4: 使用 scheduled task (Windows 10+)
        methods.append({
            "name": "Windows 排程任務",
            "type": "scheduled_task",
            "command": f'"{best_python or "python"}" main.py' if best_python else command,
            "delay": 5
        })
        
        # 方法 5: 傳統批次檔案方法
        methods.append({
            "name": "傳統批次檔案",
            "type": "traditional_batch",
            "command": f'"{best_python or "python"}" main.py' if best_python else command
        })
        
        # 方法 6: 直接 subprocess 方法
        methods.append({
            "name": "直接 subprocess",
            "type": "direct_subprocess",
            "command": [best_python or "python", "main.py"] if best_python else command.split()
        })
        
        return methods
    
    def _get_best_python_executable(self, system_info: Dict[str, Any]) -> Optional[str]:
        """取得最佳的 Python 執行檔路徑"""
        # 優先使用虛擬環境的 Python
        venv_info = system_info.get('virtual_env_details')
        if venv_info and venv_info.get('python_exists'):
            return venv_info['python_executable']
        
        # 其次使用 sys.executable
        if system_info.get('python_executable'):
            return system_info['python_executable']
        
        # 最後使用 which python 的結果
        python_paths = system_info.get('python_paths', {})
        if python_paths.get('which_python'):
            return python_paths['which_python']
        
        return None
    
    def _attempt_restart_method(self, method: Dict[str, Any], method_number: int) -> Dict[str, Any]:
        """嘗試執行重啟方法"""
        attempt_result = {
            "method_number": method_number,
            "method_name": method["name"],
            "method_type": method["type"],
            "timestamp": datetime.now().isoformat(),
            "success": False,
            "error": None,
            "process_id": None,
            "details": {}
        }
        
        try:
            method_type = method["type"]
            
            if method_type == "delayed_batch":
                success, pid, details = self._execute_delayed_batch_restart(method)
            elif method_type == "powershell_delayed":
                success, pid, details = self._execute_powershell_delayed_restart(method)
            elif method_type == "start_new_window":
                success, pid, details = self._execute_start_new_window_restart(method)
            elif method_type == "scheduled_task":
                success, pid, details = self._execute_scheduled_task_restart(method)
            elif method_type == "traditional_batch":
                success, pid, details = self._execute_traditional_batch_restart(method)
            elif method_type == "direct_subprocess":
                success, pid, details = self._execute_direct_subprocess_restart(method)
            else:
                raise Exception(f"未知的重啟方法類型: {method_type}")
            
            attempt_result["success"] = success
            attempt_result["process_id"] = pid
            attempt_result["details"] = details
            
            if success:
                self.logger.info(f"重啟方法 {method_number} 執行成功，PID: {pid}")
            
        except Exception as e:
            attempt_result["error"] = str(e)
            self.logger.error(f"重啟方法 {method_number} 執行失敗: {e}")
            import traceback
            attempt_result["traceback"] = traceback.format_exc()
        
        return attempt_result
    
    def _execute_delayed_batch_restart(self, method: Dict[str, Any]) -> tuple:
        """執行延遲批次檔重啟"""
        try:
            current_dir = os.getcwd()
            batch_file = os.path.join(current_dir, f"restart_bot_delayed_{int(time.time())}.bat")
            delay = method.get("delay", 10)
            command = method["command"]
            
            # 創建延遲批次檔案內容
            batch_content = f"""@echo off
echo PigPig Discord Bot 延遲重啟腳本
echo 等待 {delay} 秒後重啟 Bot...
timeout /t {delay} /nobreak >nul
cd /d "{current_dir}"
echo 切換到工作目錄: {current_dir}
echo 執行重啟命令: {command}
{command}
if errorlevel 1 (
    echo 重啟失敗，按任意鍵關閉視窗...
    pause
) else (
    echo Bot 已結束，按任意鍵關閉視窗...
    pause
)
del "{batch_file}" 2>nul
"""
            
            # 寫入批次檔案
            with open(batch_file, 'w', encoding='utf-8') as f:
                f.write(batch_content)
            
            # 執行批次檔案
            process = subprocess.Popen(
                [batch_file],
                cwd=current_dir,
                creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL
            )
            
            details = {
                "batch_file": batch_file,
                "delay_seconds": delay,
                "command": command,
                "working_directory": current_dir
            }
            
            return True, process.pid, details
            
        except Exception as e:
            return False, None, {"error": str(e)}
    
    def _execute_powershell_delayed_restart(self, method: Dict[str, Any]) -> tuple:
        """執行 PowerShell 延遲重啟"""
        try:
            current_dir = os.getcwd()
            script_file = os.path.join(current_dir, f"restart_bot_delayed_{int(time.time())}.ps1")
            delay = method.get("delay", 8)
            command = method["command"]
            
            # 創建 PowerShell 腳本內容
            ps_content = f'''# PigPig Discord Bot PowerShell 延遲重啟腳本
Write-Host "PigPig Discord Bot 延遲重啟腳本" -ForegroundColor Cyan
Write-Host "等待 {delay} 秒後重啟 Bot..." -ForegroundColor Yellow
Start-Sleep -Seconds {delay}

Write-Host "切換到工作目錄: {current_dir}" -ForegroundColor Green
Set-Location "{current_dir}"

Write-Host "執行重啟命令: {command}" -ForegroundColor Green
try {{
    Invoke-Expression "{command}"
}} catch {{
    Write-Host "重啟失敗: $_" -ForegroundColor Red
    Read-Host "按任意鍵關閉視窗"
}}

# 清理腳本文件
try {{
    Remove-Item "{script_file}" -Force -ErrorAction SilentlyContinue
}} catch {{
    # 忽略清理錯誤
}}

Write-Host "Bot 已結束，按任意鍵關閉視窗..." -ForegroundColor Cyan
Read-Host
'''
            
            # 寫入 PowerShell 腳本
            with open(script_file, 'w', encoding='utf-8') as f:
                f.write(ps_content)
            
            # 執行 PowerShell 腳本
            ps_cmd = [
                "powershell.exe",
                "-WindowStyle", "Normal",
                "-ExecutionPolicy", "Bypass",
                "-File", script_file
            ]
            
            process = subprocess.Popen(
                ps_cmd,
                creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL
            )
            
            details = {
                "script_file": script_file,
                "delay_seconds": delay,
                "command": command,
                "powershell_command": " ".join(ps_cmd)
            }
            
            return True, process.pid, details
            
        except Exception as e:
            return False, None, {"error": str(e)}
    
    def _execute_start_new_window_restart(self, method: Dict[str, Any]) -> tuple:
        """執行 START 新視窗重啟"""
        try:
            command = method["command"]
            
            process = subprocess.Popen(
                command,
                shell=True,
                creationflags=subprocess.DETACHED_PROCESS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL
            )
            
            details = {
                "start_command": command,
                "shell": True
            }
            
            return True, process.pid, details
            
        except Exception as e:
            return False, None, {"error": str(e)}
    
    def _execute_scheduled_task_restart(self, method: Dict[str, Any]) -> tuple:
        """執行 Windows 排程任務重啟"""
        try:
            current_dir = os.getcwd()
            command = method["command"]
            delay = method.get("delay", 5)
            task_name = f"PigPigBotRestart_{int(time.time())}"
            
            # 創建排程任務命令
            # 注意：這需要管理員權限，所以可能會失敗
            schtasks_cmd = [
                "schtasks", "/create",
                "/tn", task_name,
                "/tr", f'cmd /c "cd /d {current_dir} && {command}"',
                "/sc", "once",
                "/st", f"{(datetime.now() + timedelta(seconds=delay)).strftime('%H:%M')}",
                "/f"  # 強制創建
            ]
            
            # 創建排程任務
            create_result = subprocess.run(schtasks_cmd, capture_output=True, text=True, timeout=10)
            
            if create_result.returncode == 0:
                # 排程任務創建成功
                details = {
                    "task_name": task_name,
                    "command": command,
                    "delay_seconds": delay,
                    "working_directory": current_dir,
                    "schtasks_output": create_result.stdout
                }
                
                # 啟動排程任務
                run_cmd = ["schtasks", "/run", "/tn", task_name]
                run_result = subprocess.run(run_cmd, capture_output=True, text=True, timeout=10)
                
                if run_result.returncode == 0:
                    # 延遲刪除排程任務
                    def cleanup_task():
                        time.sleep(delay + 60)  # 等待任務執行完成後再刪除
                        try:
                            subprocess.run(["schtasks", "/delete", "/tn", task_name, "/f"], 
                                        capture_output=True, timeout=10)
                        except:
                            pass
                    
                    threading.Thread(target=cleanup_task, daemon=True).start()
                    
                    return True, None, details  # 排程任務沒有直接的 PID
                else:
                    return False, None, {"error": f"啟動排程任務失敗: {run_result.stderr}"}
            else:
                return False, None, {"error": f"創建排程任務失敗: {create_result.stderr}"}
            
        except Exception as e:
            return False, None, {"error": str(e)}
    
    def _execute_traditional_batch_restart(self, method: Dict[str, Any]) -> tuple:
        """執行傳統批次檔重啟"""
        try:
            current_dir = os.getcwd()
            batch_file = os.path.join(current_dir, f"restart_bot_traditional_{int(time.time())}.bat")
            command = method["command"]
            
            batch_content = f"""@echo off
cd /d "{current_dir}"
echo 啟動 PigPig Discord Bot...
{command}
pause
del "{batch_file}" 2>nul
"""
            
            with open(batch_file, 'w', encoding='utf-8') as f:
                f.write(batch_content)
            
            process = subprocess.Popen(
                [batch_file],
                cwd=current_dir,
                creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL
            )
            
            details = {
                "batch_file": batch_file,
                "command": command,
                "working_directory": current_dir
            }
            
            return True, process.pid, details
            
        except Exception as e:
            return False, None, {"error": str(e)}
    
    def _execute_direct_subprocess_restart(self, method: Dict[str, Any]) -> tuple:
        """執行直接 subprocess 重啟"""
        try:
            command = method["command"]
            current_dir = os.getcwd()
            
            if isinstance(command, list):
                cmd_args = command
            else:
                cmd_args = command.split()
            
            process = subprocess.Popen(
                cmd_args,
                cwd=current_dir,
                creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL
            )
            
            details = {
                "command_args": cmd_args,
                "working_directory": current_dir
            }
            
            return True, process.pid, details
            
        except Exception as e:
            return False, None, {"error": str(e)}
    
    def _save_restart_success_log(self, attempt_result: Dict[str, Any]) -> None:
        """保存重啟成功日誌"""
        try:
            log_file = f"data/restart_logs/restart_success_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            success_log = {
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "successful_attempt": attempt_result,
                "all_attempts": self.restart_attempts
            }
            
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(success_log, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"重啟成功日誌已保存: {log_file}")
            
        except Exception as e:
            self.logger.error(f"保存重啟成功日誌時發生錯誤: {e}")
    
    def _save_restart_failure_log(self) -> None:
        """保存重啟失敗日誌"""
        try:
            log_file = f"data/restart_logs/restart_failure_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            failure_log = {
                "status": "failure",
                "timestamp": datetime.now().isoformat(),
                "all_attempts": self.restart_attempts,
                "failure_summary": {
                    "total_attempts": len(self.restart_attempts),
                    "failed_methods": [attempt["method_name"] for attempt in self.restart_attempts if not attempt["success"]],
                    "errors": [attempt["error"] for attempt in self.restart_attempts if attempt.get("error")]
                }
            }
            
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(failure_log, f, indent=2, ensure_ascii=False)
            
            self.logger.error(f"重啟失敗日誌已保存: {log_file}")
            self._log_manual_restart_instructions()
            
        except Exception as e:
            self.logger.error(f"保存重啟失敗日誌時發生錯誤: {e}")
    
    def _log_manual_restart_instructions(self) -> None:
        """記錄手動重啟指引"""
        self.logger.error("=" * 60)
        self.logger.error("自動重啟失敗！請手動重啟 Bot。")
        self.logger.error("=" * 60)
        self.logger.error("手動重啟步驟：")
        self.logger.error("1. 開啟命令提示字元 (cmd) 或 PowerShell")
        self.logger.error(f"2. 切換到 Bot 目錄：cd \"{os.getcwd()}\"")
        
        # 提供虛擬環境啟動指引
        venv_path = os.environ.get('VIRTUAL_ENV')
        if venv_path:
            venv_activate = os.path.join(venv_path, 'Scripts', 'activate.bat')
            if os.path.exists(venv_activate):
                self.logger.error(f"3. 啟動虛擬環境：\"{venv_activate}\"")
                self.logger.error("4. 執行 Bot：python main.py")
            else:
                self.logger.error("3. 執行 Bot：python main.py")
        else:
            self.logger.error("3. 執行 Bot：python main.py")
        
        self.logger.error("=" * 60)
        self.logger.error("如果問題持續發生，請檢查：")
        self.logger.error("- Python 環境是否正確設定")
        self.logger.error("- 虛擬環境是否正常運作")
        self.logger.error("- 是否有足夠的系統權限")
        self.logger.error("- 防毒軟體是否阻擋了執行")
        self.logger.error("=" * 60)