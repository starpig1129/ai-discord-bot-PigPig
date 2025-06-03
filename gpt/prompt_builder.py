import logging
from typing import Dict, List, Any, Optional

class PromptBuilder:
    """提示建構器"""
    
    def __init__(self):
        """初始化建構器"""
        self.logger = logging.getLogger(__name__)
        
        # 模組標題映射
        self.module_titles = {
            "base": "",  # 基礎模組不需要標題
            "personality": "1. Personality and Expression (表達風格)",
            "answering_principles": "2. Answering Principles",
            "language": "3. Language Requirements (語言要求)",
            "professionalism": "4. Professionalism",
            "interaction": "5. Interaction",
            "formatting": "6. Discord Markdown Formatting"
        }
    
    def build_system_prompt(self, config: dict, modules: List[str]) -> str:
        """
        建構完整的系統提示
        
        Args:
            config: 配置字典
            modules: 要包含的模組列表
            
        Returns:
            組合後的完整系統提示
        """
        try:
            prompt_parts = []
            
            # 依照指定順序組合模組
            module_order = config.get('composition', {}).get('module_order', modules)
            
            for module_name in module_order:
                if module_name in modules and module_name in config:
                    module_content = self._format_module_content(
                        config[module_name], 
                        module_name
                    )
                    if module_content:
                        prompt_parts.append(module_content)
            
            # 組合所有部分
            full_prompt = "\n\n".join(prompt_parts)
            
            self.logger.debug(f"Built system prompt with modules: {modules}")
            return full_prompt
            
        except Exception as e:
            self.logger.error(f"Failed to build system prompt: {e}")
            raise
    
    def _format_module_content(self, module_config: dict, module_name: str) -> str:
        """
        格式化模組內容
        
        Args:
            module_config: 模組配置字典
            module_name: 模組名稱
            
        Returns:
            格式化後的模組內容
        """
        if module_name == "base":
            # 基礎模組直接返回核心指令
            return module_config.get('core_instruction', '')
        
        content_parts = []
        
        # 處理不同類型的模組內容
        for key, value in module_config.items():
            if isinstance(value, list):
                # 列表項目格式化為項目符號
                formatted_items = [f"- {item}" for item in value]
                content_parts.extend(formatted_items)
            elif isinstance(value, str):
                # 字串直接添加
                content_parts.append(value)
            elif isinstance(value, dict):
                # 處理巢狀結構
                self._process_nested_content(value, content_parts)
        
        if content_parts:
            title = self._get_module_title(module_name)
            if title:
                return f"{title}:\n" + "\n".join(content_parts)
            else:
                return "\n".join(content_parts)
        
        return ""
    
    def _process_nested_content(self, nested_config: dict, content_parts: List[str]) -> None:
        """
        處理巢狀配置內容
        
        Args:
            nested_config: 巢狀配置字典
            content_parts: 內容部分列表（會被修改）
        """
        for sub_key, sub_value in nested_config.items():
            if isinstance(sub_value, list):
                sub_items = [f"- {item}" for item in sub_value]
                content_parts.extend(sub_items)
            elif isinstance(sub_value, str):
                content_parts.append(sub_value)
            elif isinstance(sub_value, dict):
                # 遞歸處理更深層的巢狀
                self._process_nested_content(sub_value, content_parts)
    
    def _get_module_title(self, module_name: str) -> str:
        """
        取得模組標題
        
        Args:
            module_name: 模組名稱
            
        Returns:
            模組標題
        """
        return self.module_titles.get(module_name, f"{module_name.title()}")
    
    def apply_language_replacements(self, prompt: str, lang: str, lang_manager) -> str:
        """
        套用語言替換（與現有翻譯系統整合）
        
        Args:
            prompt: 原始提示
            lang: 語言代碼
            lang_manager: 語言管理器實例
            
        Returns:
            套用語言替換後的提示
        """
        try:
            # 取得語言設定翻譯
            language_settings = lang_manager.translations[lang]["common"]["system"]["chat_bot"]["language"]
            
            # 執行替換
            modified_prompt = prompt.replace(
                "Always answer in Traditional Chinese",
                language_settings["answer_in"]
            ).replace(
                "Appropriately use Chinese idioms or playful expressions",
                language_settings["style"]
            ).replace(
                "使用 [標題](<URL>) 格式",
                language_settings["references"]
            )
            
            self.logger.debug(f"Applied language replacements for: {lang}")
            return modified_prompt
            
        except (KeyError, TypeError, AttributeError) as e:
            # 如果翻譯失敗，記錄警告但返回原始提示
            self.logger.warning(f"Language replacement failed for {lang}: {e}")
            return prompt
    
    def format_with_variables(self, prompt: str, variables: dict) -> str:
        """
        格式化變數替換
        
        Args:
            prompt: 包含變數的提示模板
            variables: 變數字典
            
        Returns:
            替換變數後的提示
        """
        try:
            return prompt.format(**variables)
        except KeyError as e:
            # 如果變數不存在，記錄警告但不中斷
            self.logger.warning(f"Missing variable in prompt formatting: {e}")
            return prompt
        except Exception as e:
            self.logger.error(f"Error in variable formatting: {e}")
            return prompt
    
    def compose_modules(self, config: dict, module_list: List[str]) -> str:
        """
        組合指定模組的提示內容
        
        Args:
            config: 配置字典
            module_list: 要組合的模組列表
            
        Returns:
            組合後的提示內容
        """
        return self.build_system_prompt(config, module_list)
    
    def validate_module_references(self, config: dict, modules: List[str]) -> List[str]:
        """
        驗證模組引用，返回缺失的模組列表
        
        Args:
            config: 配置字典
            modules: 要驗證的模組列表
            
        Returns:
            缺失的模組名稱列表
        """
        missing_modules = []
        
        for module in modules:
            if module not in config:
                missing_modules.append(module)
                self.logger.warning(f"Module '{module}' not found in configuration")
        
        return missing_modules
    
    def get_module_summary(self, config: dict, module_name: str) -> Optional[str]:
        """
        取得模組的摘要描述
        
        Args:
            config: 配置字典
            module_name: 模組名稱
            
        Returns:
            模組摘要，如果模組不存在則返回 None
        """
        if module_name not in config:
            return None
        
        module_config = config[module_name]
        
        # 嘗試從模組配置中提取摘要
        if isinstance(module_config, dict):
            # 計算項目數量
            item_count = 0
            for value in module_config.values():
                if isinstance(value, list):
                    item_count += len(value)
                elif isinstance(value, str):
                    item_count += 1
            
            return f"Module '{module_name}' with {item_count} configuration items"
        
        return f"Module '{module_name}'"
    
    def build_partial_prompt(self, config: dict, modules: List[str], max_length: Optional[int] = None) -> str:
        """
        建構部分提示（用於預覽或測試）
        
        Args:
            config: 配置字典
            modules: 模組列表
            max_length: 最大長度限制
            
        Returns:
            部分提示內容
        """
        full_prompt = self.build_system_prompt(config, modules)
        
        if max_length and len(full_prompt) > max_length:
            truncated = full_prompt[:max_length - 3] + "..."
            self.logger.debug(f"Truncated prompt from {len(full_prompt)} to {len(truncated)} characters")
            return truncated
        
        return full_prompt