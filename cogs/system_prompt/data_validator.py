"""
系統提示數據驗證助手

提供額外的數據一致性檢查和驗證功能
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class SystemPromptDataValidator:
    """系統提示數據驗證器"""
    
    def __init__(self, data_dir: str = "data/channel_configs"):
        self.data_dir = Path(data_dir)
    
    def validate_config_consistency(self, guild_id: str, channel_id: str) -> Dict[str, Any]:
        """
        驗證配置一致性
        
        Args:
            guild_id: 伺服器 ID
            channel_id: 頻道 ID
            
        Returns:
            驗證結果
        """
        result = {
            'guild_id': guild_id,
            'channel_id': channel_id,
            'is_consistent': True,
            'issues': [],
            'file_exists': False,
            'channel_config': None,
            'modules': None
        }
        
        try:
            config_file = self.data_dir / f"{guild_id}.json"
            result['file_exists'] = config_file.exists()
            
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                system_prompts = config.get('system_prompts', {})
                channels = system_prompts.get('channels', {})
                
                if channel_id in channels:
                    channel_config = channels[channel_id]
                    result['channel_config'] = channel_config
                    
                    modules = channel_config.get('modules', {})
                    result['modules'] = modules
                    
                    # 檢查數據完整性
                    if not channel_config.get('updated_at'):
                        result['issues'].append("缺少 updated_at 時間戳")
                        result['is_consistent'] = False
                    
                    if modules and not isinstance(modules, dict):
                        result['issues'].append("模組數據格式不正確")
                        result['is_consistent'] = False
                    
                    logger.info(f"驗證結果: 頻道 {channel_id} 配置一致性 = {result['is_consistent']}")
                else:
                    result['issues'].append(f"頻道 {channel_id} 配置不存在")
                    result['is_consistent'] = False
            else:
                result['issues'].append("配置檔案不存在")
                result['is_consistent'] = False
        
        except Exception as e:
            error_msg = f"驗證過程發生錯誤: {str(e)}"
            result['issues'].append(error_msg)
            result['is_consistent'] = False
            logger.error(error_msg)
        
        return result
    
    def fix_inconsistent_data(self, guild_id: str, channel_id: str) -> bool:
        """
        修復不一致的數據
        
        Args:
            guild_id: 伺服器 ID
            channel_id: 頻道 ID
            
        Returns:
            是否修復成功
        """
        try:
            validation_result = self.validate_config_consistency(guild_id, channel_id)
            
            if validation_result['is_consistent']:
                logger.info("數據已一致，無需修復")
                return True
            
            # 執行修復邏輯
            config_file = self.data_dir / f"{guild_id}.json"
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # 修復缺少的時間戳
                system_prompts = config.get('system_prompts', {})
                channels = system_prompts.get('channels', {})
                
                if channel_id in channels:
                    channel_config = channels[channel_id]
                    
                    from datetime import datetime
                    if not channel_config.get('updated_at'):
                        channel_config['updated_at'] = datetime.now().isoformat()
                        logger.info("修復：添加缺少的 updated_at 時間戳")
                    
                    # 保存修復後的配置
                    with open(config_file, 'w', encoding='utf-8') as f:
                        json.dump(config, f, ensure_ascii=False, indent=2)
                    
                    logger.info("數據修復完成")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"修復數據時發生錯誤: {e}")
            return False
    
    def get_module_comparison(self, guild_id: str, channel_id: str, 
                            expected_modules: Dict[str, str]) -> Dict[str, Any]:
        """
        比較期望的模組與實際存儲的模組
        
        Args:
            guild_id: 伺服器 ID
            channel_id: 頻道 ID
            expected_modules: 期望的模組數據
            
        Returns:
            比較結果
        """
        result = {
            'is_match': False,
            'expected': expected_modules,
            'actual': None,
            'differences': []
        }
        
        try:
            validation_result = self.validate_config_consistency(guild_id, channel_id)
            actual_modules = validation_result.get('modules', {})
            result['actual'] = actual_modules
            
            # 比較模組
            if actual_modules == expected_modules:
                result['is_match'] = True
            else:
                # 找出差異
                for module_name, expected_content in expected_modules.items():
                    if module_name not in actual_modules:
                        result['differences'].append(f"缺少模組: {module_name}")
                    elif actual_modules[module_name] != expected_content:
                        result['differences'].append(
                            f"模組內容不一致: {module_name}"
                        )
                
                for module_name in actual_modules:
                    if module_name not in expected_modules:
                        result['differences'].append(f"額外模組: {module_name}")
        
        except Exception as e:
            result['differences'].append(f"比較過程發生錯誤: {str(e)}")
        
        return result
