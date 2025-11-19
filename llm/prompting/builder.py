from addons.logging import get_logger
from typing import List, Optional, Union
import asyncio
from function import func
class PromptBuilder:
    """提示建構器"""
    
    def __init__(self):
        """初始化建構器"""
        self.logger = get_logger(server_id="Bot", source="llm.prompting.builder")
        
        # Module title mapping — align keys with YAML module names
        self.module_titles = {
            "base": "",
            "identity": "Identity and Role",
            "response_principles": "Response Principles",
            "language": "Language Requirements (語言要求)",
            "output_format": "Output Format Rules",
            "input_parsing": "Input Parsing",
            "memory_system": "Memory System",
            "information_handling": "Information Handling",
            "error_handling": "Error Handling",
            "interaction": "Interaction",
            "professional_personality": "Professional Personality"
        }
    
    def build_system_prompt(self, config: dict, modules: List[str]) -> str:
        """
        建構完整的系統提示
        
        追加診斷日誌：記錄 module_order、requested modules，以及每個模組是否存在於配置中。
        
        Args:
            config: 配置字典
            modules: 要包含的模組列表
            
        Returns:
            組合後的完整系統提示
        """
        try:
            prompt_parts = []
            
            # 依照指定順序組合模組（假設 caller 已確保 modules 為 list）
            module_order = config.get('composition', {}).get('module_order', modules)
            
            for module_name in module_order:
                if module_name in modules and module_name in config:
                    module_content = self._format_module_content(config[module_name], module_name)
                    if module_content:
                        prompt_parts.append(module_content)
            
            # 組合所有部分並回傳
            full_prompt = "\n\n".join(prompt_parts)
            return full_prompt
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "building system prompt"))
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
    
    def apply_language_replacements(self, prompt: str, lang: str, lang_manager, mappings: Optional[dict] = None) -> str:
        """
        Resolve explicit language placeholders and apply language mappings.

        Strategy:
        - Resolve placeholders of the form {{lang.<path>}} using LanguageManager translations.
        - Also handle single-brace forms {lang.<path>} which may appear after Python .format processing.
        - If mappings (YAML) are provided, apply them deterministically (exact replace) after placeholder resolution.
        - Keep behavior safe: any resolution error is reported via func.report_error and the original prompt is returned.

        Args:
            prompt: original prompt text
            lang: language code (e.g., "zh_TW")
            lang_manager: LanguageManager instance
            mappings: optional dict mapping source strings to translation paths
                      (e.g. {"Always answer in Traditional Chinese": "system.chat_bot.language.answer_in"})

        Returns:
            prompt with replacements applied
        """
        try:
            import re

            # translations are stored under 'common' category in LanguageManager
            translations_root = lang_manager.translations.get(lang, {}).get('common', {})

            def resolve_path(path: str) -> Optional[str]:
                """Resolve dotted path against translations_root, return string or None."""
                value = translations_root
                for part in path.split('.'):
                    if not isinstance(value, dict):
                        return None
                    value = value.get(part)
                    if value is None:
                        return None
                return value if isinstance(value, str) else None

            # Enhanced replacement function to handle both {lang.xxx} and {{lang.xxx}} patterns
            def placeholder_repl_path(path: str) -> str:
                # Try direct path resolution first
                resolved = resolve_path(path)
                if resolved:
                    return resolved
                
                # Try with 'system.' prefix if not already present
                if not path.startswith("system."):
                    resolved = resolve_path("system." + path)
                    if resolved:
                        return resolved
                
                # Try extracting just the language parts from system.chat_bot.language.xxx
                if "system.chat_bot.language." in path:
                    # Extract the specific language attribute (e.g., "answer_in" from "system.chat_bot.language.answer_in")
                    lang_attr = path.replace("system.chat_bot.language.", "")
                    resolved = resolve_path(f"system.chat_bot.language.{lang_attr}")
                    if resolved:
                        return resolved
                
                # If cannot resolve, return empty string to avoid leaving raw placeholders
                self.logger.debug(f"Could not resolve language path: {path}")
                return ""

            # 1) Replace double-brace placeholders like {{lang.system.chat_bot.language.answer_in}}
            double_brace_pattern = re.compile(r"\{\{\s*lang\.([^\}]+)\s*\}\}")
            new_prompt = double_brace_pattern.sub(lambda m: placeholder_repl_path(m.group(1).strip()), prompt)

            # 2) Replace single-brace placeholders like {lang.system.chat_bot.language.answer_in}
            #    (these may appear after .format() has processed double braces)
            single_brace_pattern = re.compile(r"\{\s*lang\.([^\}]+)\s*\}")
            new_prompt = single_brace_pattern.sub(lambda m: placeholder_repl_path(m.group(1).strip()), new_prompt)

            # 3) If YAML mappings provided, perform deterministic exact replacements using resolved values
            if mappings:
                for src, path in mappings.items():
                    try:
                        # prefer exact dotted path resolution; allow both with and without leading 'system.'
                        value = resolve_path(path) or (resolve_path("system." + path) if not path.startswith("system.") else None)
                        if isinstance(value, str) and value:
                            if src in new_prompt:
                                new_prompt = new_prompt.replace(src, value)
                    except Exception:
                        # continue on individual mapping failure
                        continue

            # 4) Return the processed prompt (if nothing changed, original content remains)
            if new_prompt != prompt:
                self.logger.debug(f"Applied language placeholder replacements for lang={lang}")
            else:
                self.logger.debug(f"No language placeholders found for lang={lang}")

            return new_prompt

        except Exception as e:
            asyncio.create_task(func.report_error(e, "applying language replacements"))
            return prompt
    
    def format_with_variables(self, prompt: str, variables: dict, lang_manager=None, guild_id: Union[str, None] = None) -> str:
        """
        格式化變數替換
        
        Args:
            prompt: 包含變數的提示模板
            variables: 變數字典
            lang_manager: LanguageManager instance for language replacements
            guild_id: Server ID for language-specific translations
            
        Returns:
            替換變數後的提示
        """
        try:
            # 首先確保 'lang' 變數存在，如果沒有則設置為預設值
            if 'lang' not in variables:
                variables = variables.copy()  # 創建副本避免修改原始字典
                variables['lang'] = getattr(lang_manager, 'default_lang', 'zh_TW') if lang_manager else 'zh_TW'
                self.logger.debug(f"Added missing 'lang' variable with default value: {variables['lang']}")
            
            processed_prompt = prompt
            
            # 先應用語言占位符替換（在變數替換之前）
            if lang_manager and guild_id:
                try:
                    # 獲取該伺服器的語言
                    server_lang = lang_manager.get_server_lang(guild_id)
                    
                    # 獲取語言映射（如果存在）
                    mappings = variables.get('language_replacements', {}).get('mappings', {})
                    
                    # 應用語言占位符替換
                    processed_prompt = self.apply_language_replacements(
                        processed_prompt, server_lang, lang_manager, mappings
                    )
                    self.logger.debug(f"Applied language replacements, prompt length changed from {len(prompt)} to {len(processed_prompt)}")
                except Exception as lang_e:
                    self.logger.warning(f"Language replacement failed: {lang_e}")
            
            formatted_prompt = processed_prompt
            
            # 記錄替換過程以便調試
            replacements_made = []
            
            for key, value in variables.items():
                # 將變數轉為字符串，確保替換成功
                str_value = str(value)
                
                # 創建完整的占位符格式
                placeholder = f"{{{key}}}"
                
                # 進行安全替換
                if placeholder in formatted_prompt:
                    formatted_prompt = formatted_prompt.replace(placeholder, str_value)
                    replacements_made.append(f"{placeholder} -> {str_value}")
            
            if replacements_made:
                self.logger.debug(f"Safe variable replacements completed ({len(replacements_made)} replacements): {replacements_made}")
            
            # 檢查是否還有未替換的占位符
            remaining_placeholders = []
            import re
            remaining_pattern = re.compile(r'\{(?!lang\.)([^{}]+)\}')
            matches = remaining_pattern.findall(formatted_prompt)
            if matches:
                remaining_placeholders.extend(matches)
                self.logger.warning(f"Found unresolved placeholders: {remaining_placeholders}, using prompt without these replacements")
                
                # 如果有未替換的占位符，嘗試使用更安全的 .format() 方法
                # 但是只替換確實存在的變數
                try:
                    safe_variables = {k: v for k, v in variables.items() if f"{{{k}}}" in formatted_prompt}
                    formatted_prompt = formatted_prompt.format(**safe_variables)
                    self.logger.debug(f"Fallback .format() successful with safe variables: {list(safe_variables.keys())}")
                except Exception as format_e:
                    self.logger.warning(f"Fallback .format() failed: {format_e}")
                    # 如果 .format() 失敗，保持原始的替換結果
            
            self.logger.debug(f"Final prompt length: {len(formatted_prompt)}")
            return formatted_prompt
            
        except KeyError as e:
            # 如果變數不存在，記錄警告但不中斷
            self.logger.warning(f"Missing variable in prompt formatting: {e}")
            return prompt
        except Exception as e:
            asyncio.create_task(func.report_error(e, "formatting prompt with variables"))
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