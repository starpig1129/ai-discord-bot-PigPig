#!/usr/bin/env python3
"""
Lightweight CLI wrapper for update system

This script provides a lightweight CLI interface that delegates core functionality
to the new update architecture in addons.update.* modules.

Usage:
    python update.py -c           # Check version
    python update.py -l           # Install latest version
    python update.py -v <version> # Install specific version
    python update.py -b           # Install beta version
"""

import os
import sys
import argparse
import asyncio
from typing import Optional

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import from new architecture
from addons.update.manager import UpdateManager
from addons.update.security import UpdatePermissionChecker
from addons.update.checker import VersionChecker
from addons.update.downloader import UpdateDownloader
from addons.settings import update_config
from function import func
from addons.logging import get_logger


class UpdateCLI:
    """Lightweight CLI wrapper for update operations"""
    
    def __init__(self):
        """Initialize CLI wrapper"""
        self.config = update_config
        self.bot_owner_id = 0
        self._init_bot_owner_id()
        
        # Initialize components from new architecture
        self.github_config = self.config.github
        self.version_checker = VersionChecker(self.github_config)
        self.permission_checker = UpdatePermissionChecker()
        
        self.permission_checker = UpdatePermissionChecker()
        
        # Setup logging
        self.logger = get_logger(server_id="system", source="update_cli")
    
    def _init_bot_owner_id(self):
        """Initialize bot owner ID from environment"""
        try:
            from dotenv import load_dotenv
            load_dotenv()
            self.bot_owner_id = int(os.getenv("BOT_OWNER_ID", "0"))
        except Exception:
            self.bot_owner_id = 0
    

    def check_version(self, with_message: bool = False) -> str:
        """
        Check current version status
        
        Args:
            with_message: Whether to print message
            
        Returns:
            Latest version string
        """
        try:
            # Create a simple bot-like object for compatibility
            class BotObject:
                def __init__(self):
                    self.user: Optional[object] = None
                    
                class UserObject:
                    def __init__(self, user_id: int):
                        self.id = user_id
            
            bot = BotObject()
            
            # Check if we have permission (always allowed for CLI)
            if self.bot_owner_id == 0:
                # Create a temporary UpdateManager to get version info
                temp_manager = UpdateManager(bot)
                current_version = temp_manager.version_checker.get_current_version()
            else:
                # Use permission checker if bot owner is configured
                bot.user = BotObject.UserObject(self.bot_owner_id)
                if self.permission_checker.check_update_permission(self.bot_owner_id):
                    temp_manager = UpdateManager(bot)
                    current_version = temp_manager.version_checker.get_current_version()
                else:
                    current_version = "v3.0.0"  # Fallback
            
            # Get latest version asynchronously
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(self.version_checker.check_for_updates())
                latest_version = result.get("latest_version", current_version)
            finally:
                loop.close()
            
            if with_message:
                if latest_version == current_version:
                    self.logger.info(f"Your PigPig Bot is up-to-date! - {latest_version}")
                else:
                    msg = (
                        f"Your PigPig Bot is not up-to-date! The latest version is {latest_version} "
                        f"and you are currently running version {current_version}. "
                        f"Run `python update.py -l` to update your bot!"
                    )
                    self.logger.warning(msg)
                    print(f"\033[93m{msg}\033[0m")
            
            return latest_version
            
        except Exception as e:
            if with_message:
                self.logger.error(f"Error checking version: {e}")
                print(f"\033[91mError checking version: {e}\033[0m")
            return "v3.0.0"  # Fallback version
    
    def install_version(self, version: Optional[str] = None, is_latest: bool = False, 
                       is_beta: bool = False) -> bool:
        """
        Install specified version
        
        Args:
            version: Version to install
            is_latest: Whether to install latest version
            is_beta: Whether to install beta version
            
        Returns:
            Installation success status
        """
        try:
            # Check permissions
            if self.bot_owner_id == 0:
                print("\033[93mWarning: BOT_OWNER_ID not configured. Update functionality may be restricted.\033[0m")
            else:
                if not self.permission_checker.check_update_permission(self.bot_owner_id):
                    self.logger.error("No permission to update. Bot owner ID required.")
                    print(f"\033[91mError: No permission to update. Bot owner ID required.\033[0m")
                    return False
            
            # Determine target version
            if is_beta:
                target_version = "refs/heads/beta"
            elif is_latest:
                target_version = self.check_version(with_message=False)
            elif version:
                target_version = version
            else:
                print("\033[91mError: No version specified\033[0m")
                return False
            
            # Get download URL
            download_url = f"https://github.com/starpig1129/ai-discord-bot-PigPig/archive/{target_version}.zip"
            
            # Show download info
            print(f"Downloading PigPig Bot version: {target_version}")
            
            # Download the update
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                downloader = UpdateDownloader()
                
                async def progress_callback(progress):
                    print(f"Download progress: {progress}%")
                
                download_path = loop.run_until_complete(
                    downloader.download_update(download_url, progress_callback)
                )
                
                print("Download completed")
                
                # Create temporary bot for installation
                class BotObject2:
                    def __init__(self):
                        self.user: Optional[object] = None
                    
                    class UserObject2:
                        def __init__(self, user_id: int):
                            self.id = user_id
                
                bot = BotObject2()
                if self.bot_owner_id > 0:
                    bot.user = BotObject2.UserObject2(self.bot_owner_id)
                
                # Use UpdateManager for installation
                manager = UpdateManager(bot)
                
                # Execute installation
                print("Installing update...")
                
                # Execute update with force flag
                result = loop.run_until_complete(
                    manager.execute_update(force=True)
                )
                
                if result.get("success"):
                    print(f"\033[92mVersion {target_version} installed successfully! "
                          f"Run `python main.py` to start your bot\033[0m")
                    return True
                else:
                    self.logger.error(f"Update failed: {result.get('error', 'Unknown error')}")
                    print(f"\033[91mUpdate failed: {result.get('error', 'Unknown error')}\033[0m")
                    return False
                    
            finally:
                loop.close()
                
        except Exception as e:
            self.logger.error(f"Error during installation: {e}")
            print(f"\033[91mError during installation: {e}\033[0m")
            # Report error using the new architecture
            asyncio.create_task(func.report_error(e, "update.py/install_version"))
            return False
    
    def parse_args(self) -> argparse.Namespace:
        """Parse command line arguments"""
        parser = argparse.ArgumentParser(
            description='Update script for PigPig Discord Bot - Lightweight CLI wrapper'
        )
        
        parser.add_argument(
            '-c', '--check',
            action='store_true',
            help='Check the current version of the PigPig Bot'
        )
        
        parser.add_argument(
            '-v', '--version',
            type=str,
            help='Install the specified version of the PigPig Bot'
        )
        
        parser.add_argument(
            '-l', '--latest',
            action='store_true',
            help='Install the latest version of the PigPig Bot from Github'
        )
        
        parser.add_argument(
            '-b', '--beta',
            action='store_true',
            help='Install the beta version of the PigPig Bot from Github'
        )
        
        return parser.parse_args()
    
    def run(self) -> int:
        """Main execution method"""
        try:
            args = self.parse_args()
            
            # Version check only
            if args.check:
                self.check_version(with_message=True)
                return 0
            
            # Install specific version
            elif args.version:
                success = self.install_version(version=args.version)
                return 0 if success else 1
            
            # Install latest version
            elif args.latest:
                success = self.install_version(is_latest=True)
                return 0 if success else 1
            
            # Install beta version
            elif args.beta:
                success = self.install_version(is_beta=True)
                return 0 if success else 1
            
            # No arguments provided
            else:
                print(f"\033[91mNo arguments provided. Run `python update.py -h` for help.\033[0m")
                return 1
                
        except KeyboardInterrupt:
            print("\n\033[93mUpdate cancelled by user\033[0m")
            return 1
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            self.logger.error(error_msg)
            print(f"\033[91m{error_msg}\033[0m")
            asyncio.create_task(func.report_error(e, "update.py/run"))
            return 1


def main():
    """Main entry point"""
    cli = UpdateCLI()
    exit_code = cli.run()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()