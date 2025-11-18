import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import asyncio
from functools import lru_cache
from typing import Optional, Dict, Any, List, Set, Tuple
from pathlib import Path
from addons.logging import get_logger
from function import func


class MissingTranslationError(Exception):
    """Custom exception for missing translation keys"""
    pass

log = get_logger(source=__name__, server_id="system")

class TranslationCache:
    """Multi-layer cache for translations with LRU eviction"""
    
    def __init__(self, max_size: int = 1000):
        self._cache: Dict[str, str] = {}
        self._max_size = max_size
        self._access_times: Dict[str, float] = {}
        self._access_counts: Dict[str, int] = {}
    
    def get(self, key: str) -> Optional[str]:
        """Get cached translation with LRU tracking"""
        if key in self._cache:
            import time
            self._access_times[key] = time.time()
            self._access_counts[key] = self._access_counts.get(key, 0) + 1
            return self._cache[key]
        return None
    
    def put(self, key: str, value: str):
        """Store translation in cache with LRU eviction"""
        if len(self._cache) >= self._max_size:
            self._evict_lru()
        
        self._cache[key] = value
        import time
        self._access_times[key] = time.time()
        self._access_counts[key] = self._access_counts.get(key, 0) + 1
    
    def _evict_lru(self):
        """Evict least recently used item"""
        if not self._cache:
            return
        
        lru_key = min(self._access_times.keys(), key=lambda k: self._access_times[k])
        del self._cache[lru_key]
        del self._access_times[lru_key]
        self._access_counts.pop(lru_key, None)
    
    def clear(self):
        """Clear all cached items"""
        self._cache.clear()
        self._access_times.clear()
        self._access_counts.clear()
    
    def size(self) -> int:
        """Get current cache size"""
        return len(self._cache)

class LanguageManager(commands.Cog):
    """Language Management System with modular translation support"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_dir = "data/serverconfig"
        # 確保配置目錄存在
        os.makedirs(self.config_dir, exist_ok=True)
        
        self.logger = log
        self.default_lang = "zh_TW"  # 預設使用繁體中文
        
        # 新的資料結構：lang -> file_key -> path -> value
        self.translations: Dict[str, Dict[str, Dict[str, Any]]] = {}
        
        # 檔案索引：lang -> path_pattern -> file_key
        self.file_index: Dict[str, Dict[str, str]] = {}
        
        # 快取系統：翻譯結果快取
        self._translation_cache = TranslationCache(max_size=1000)
        
        # 載入策略
        self._lazy_loading_enabled = True
        self._loaded_files: Set[Tuple[str, str]] = set()  # (lang, file_key)
        self._pending_loads: Set[Tuple[str, str]] = set()  # files waiting to be loaded
        
        # 語言選項
        self.supported_languages = {}
        
        # 載入翻譯並初始化
        self._load_translations()
        self.supported_languages = self._get_supported_languages()

    def _load_translations(self):
        """載入所有語言翻譯，支援新的模組化結構"""
        lang_codes = ["zh_TW", "zh_CN", "en_US", "ja_JP"]
        
        # 階段 1：載入通用檔案（快速啟動）
        self._load_common_files(lang_codes)
        
        # 階段 2：建立檔案索引
        for lang_code in lang_codes:
            self._build_file_index(lang_code)
        
        # 階段 3：排程延遲載入（如果啟用）
        if self._lazy_loading_enabled:
            self._schedule_lazy_loading()
    
    def _load_common_files(self, lang_codes: List[str]):
        """載入通用檔案，提供快速啟動"""
        for lang_code in lang_codes:
            if lang_code not in self.translations:
                self.translations[lang_code] = {}
            
            # 嘗試載入 common.json（向後相容性）
            common_file = os.path.join("translations", lang_code, "common.json")
            if os.path.exists(common_file):
                try:
                    with open(common_file, 'r', encoding='utf-8') as f:
                        translations = json.load(f)
                        self.translations[lang_code]["common"] = translations
                    self.logger.debug(f"Loaded common translations for {lang_code}")
                except Exception as e:
                    asyncio.create_task(func.report_error(e, f"loading common translation file {common_file}"))
            else:
                # 如果沒有新的 common.json，嘗試舊的格式
                self._load_legacy_common_file(lang_code)
    
    def _load_legacy_common_file(self, lang_code: str):
        """載入舊格式的翻譯檔案（向後相容性）"""
        legacy_file = os.path.join("translations", f"{lang_code}.json")
        if os.path.exists(legacy_file):
            try:
                with open(legacy_file, 'r', encoding='utf-8') as f:
                    translations = json.load(f)
                self.translations[lang_code]["common"] = translations
                self.logger.info(f"Loaded legacy translation file for {lang_code}")
            except Exception as e:
                asyncio.create_task(func.report_error(e, f"loading legacy translation file {legacy_file}"))
    
    def _build_file_index(self, lang_code: str) -> Dict[str, str]:
        """建立檔案索引，快速映射路徑到檔案"""
        if lang_code not in self.file_index:
            self.file_index[lang_code] = {}
        
        lang_dir = os.path.join("translations", lang_code)
        if not os.path.exists(lang_dir):
            return {}
        
        # 遞迴掃描所有 JSON 檔案
        for root, dirs, files in os.walk(lang_dir):
            for file in files:
                if not file.endswith('.json'):
                    continue
                
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, lang_dir)
                
                # 轉換路徑格式：path/to/file.json -> path/to/file
                file_key = relative_path[:-5]  # 移除 .json
                
                # 建立路徑映射
                path_parts = file_key.split(os.sep)
                
                # 為每個路徑層級建立索引，包括複合路徑
                for i in range(1, len(path_parts) + 1):
                    partial_key = "/".join(path_parts[:i])
                    self.file_index[lang_code][partial_key] = file_key
                
                # 標準路徑映射
                self.file_index[lang_code][file_key] = file_key
                
                self.logger.debug(f"Indexed translation file: {lang_code}/{file_key}")
        
        return self.file_index[lang_code]
    
    def _schedule_lazy_loading(self):
        """排程延遲載入"""
        asyncio.create_task(self._lazy_load_worker())
    
    async def _lazy_load_worker(self):
        """背景工作程序：按需載入翻譯檔案"""
        while True:
            try:
                # 檢查待載入佇列
                pending_files = list(self._pending_loads.copy())
                
                for lang, file_key in pending_files:
                    if (lang, file_key) not in self._loaded_files:
                        await self._load_translation_file_async(lang, file_key)
                        self._loaded_files.add((lang, file_key))
                        self._pending_loads.discard((lang, file_key))
                
                await asyncio.sleep(0.5)  # 每500ms檢查一次
            except Exception as e:
                self.logger.error(f"Error in lazy loading worker: {e}")
                await asyncio.sleep(1)  # 錯誤時延長等待時間

    def _resolve_translation_file(self, lang: str, *path_parts) -> Optional[str]:
        """Resolve translation key path to file path
        
        Args:
            lang: Language code
            *path_parts: Translation key path parts
            
        Returns:
            File path or None if not found
        """
        if not path_parts:
            return None
        
        # 檢查檔案索引
        if lang not in self.file_index:
            return None
        
        file_index = self.file_index[lang]
        
        # 嘗試完整路徑匹配
        full_path = "/".join(path_parts)
        
        # 向後相容性：直接檢查是否是檔案鍵
        if full_path in file_index:
            return file_index[full_path]
        
        # 嘗試部分路徑匹配
        for i in range(len(path_parts), 0, -1):
            partial_path = "/".join(path_parts[:i])
            if partial_path in file_index:
                return file_index[partial_path]
        
        return None
    
    def _load_translation_file(self, lang: str, file_path: str) -> Dict[str, Any]:
        """Load a single translation file with caching
        
        Args:
            lang: Language code
            file_path: Relative path to translation file
            
        Returns:
            Translation dictionary
        """
        full_path = os.path.join("translations", lang, f"{file_path}.json")
        
        if not os.path.exists(full_path):
            self.logger.warning(f"Translation file not found: {full_path}")
            return {}
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                translations = json.load(f)
            
            # 更新資料結構
            if lang not in self.translations:
                self.translations[lang] = {}
            
            self.translations[lang][file_path] = translations
            
            self.logger.debug(f"Loaded translation file: {lang}/{file_path}")
            return translations
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, f"loading translation file {full_path}"))
            return {}
    
    async def _load_translation_file_async(self, lang: str, file_path: str) -> Dict[str, Any]:
        """Asynchronously load a translation file"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._load_translation_file, lang, file_path)
    
    def _request_file_load(self, lang: str, file_path: str):
        """請求載入翻譯檔案（延遲載入）"""
        if (lang, file_path) not in self._loaded_files:
            self._pending_loads.add((lang, file_path))
    
    def _traverse_path(self, data: Dict[str, Any], path_parts: List[str]) -> Any:
        """Traverse nested dictionary using path parts"""
        result = data
        for part in path_parts:
            if isinstance(result, dict) and part in result:
                result = result[part]
            else:
                return None
        return result
    
    def _find_translation_with_fallback(self, lang: str, path_parts: List[str]) -> Tuple[bool, str]:
        """Find translation with multi-layer fallback mechanism
        
        Args:
            lang: Language code
            path_parts: Path parts to the translation key
            
        Returns:
            Tuple of (found: bool, translated_string: str)
        """
        if not path_parts:
            return False, "TRANSLATION_NOT_FOUND"
        
        # 1. 嘗試精確匹配
        result = self._exact_match_search(lang, path_parts)
        if result:
            return True, result
        
        # 2. 嘗試部分匹配
        result = self._partial_match_search(lang, path_parts)
        if result:
            return True, result
        
        # 3. 向 common.json 回退
        result = self._common_fallback_search(lang, path_parts)
        if result:
            return True, result
        
        # 4. 返回備用值
        return False, path_parts[-1] if path_parts else "TRANSLATION_NOT_FOUND"
    
    def _exact_match_search(self, lang: str, path_parts: List[str]) -> Optional[str]:
        """嘗試在對應檔案中進行精確匹配"""
        file_path = self._resolve_translation_file(lang, *path_parts)
        
        if file_path:
            # 確保檔案已載入
            if file_path not in self.translations.get(lang, {}):
                self._load_translation_file(lang, file_path)
            
            if file_path in self.translations.get(lang, {}):
                translation_data = self.translations[lang][file_path]
                result = self._traverse_path(translation_data, path_parts)
                if isinstance(result, str):
                    return result
        
        return None
    
    def _partial_match_search(self, lang: str, path_parts: List[str]) -> Optional[str]:
        """嘗試部分路徑匹配"""
        if lang not in self.translations:
            return None
        
        # 從最長路徑開始嘗試
        for i in range(len(path_parts) - 1, 0, -1):
            current_path = path_parts[:i]
            remaining_path = path_parts[i:]
            
            file_path = self._resolve_translation_file(lang, *current_path)
            if file_path and file_path in self.translations[lang]:
                translation_data = self.translations[lang][file_path]
                result = self._traverse_path(translation_data, remaining_path)
                if isinstance(result, str):
                    return result
        
        return None
    
    def _common_fallback_search(self, lang: str, path_parts: List[str]) -> Optional[str]:
        """向 common.json 回退搜尋"""
        if lang in self.translations and "common" in self.translations[lang]:
            translation_data = self.translations[lang]["common"]
            result = self._traverse_path(translation_data, path_parts)
            if isinstance(result, str):
                return result
        
        return None

    def _get_supported_languages(self) -> Dict[str, str]:
        """獲取支援的語言列表，使用翻譯系統或備用硬編碼選項"""
        try:
            return {
                "zh_TW": self.translate("0", "system", "language_manager", "supported_languages", "zh_TW"),
                "zh_CN": self.translate("0", "system", "language_manager", "supported_languages", "zh_CN"),
                "en_US": self.translate("0", "system", "language_manager", "supported_languages", "en_US"),
                "ja_JP": self.translate("0", "system", "language_manager", "supported_languages", "ja_JP")
            }
        except:
            # 備用硬編碼選項，避免初始化時的循環依賴
            return {
                "zh_TW": "繁體中文",
                "zh_CN": "简体中文",
                "en_US": "English",
                "ja_JP": "日本語"
            }

    def get_server_lang(self, guild_id: str) -> str:
        """獲取伺服器的語言設定"""
        config_path = os.path.join(self.config_dir, f"{guild_id}.json")
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    return config.get('language', self.default_lang)
            return self.default_lang
        except Exception as e:
            import asyncio
            asyncio.create_task(func.report_error(e, "getting server language"))
            return self.default_lang

    def save_server_lang(self, guild_id: str, lang: str) -> bool:
        """保存伺服器的語言設定"""
        config_path = os.path.join(self.config_dir, f"{guild_id}.json")
        try:
            config = {}
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)

            config['language'] = lang

            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)

            # Invalidate cached system prompts so language change takes effect immediately
            try:
                from llm.prompting import manager as prompt_manager_module
                pm_instances = getattr(prompt_manager_module, "_prompt_manager_instances", {})
                for pm in pm_instances.values():
                    try:
                        keys = pm.cache.get_cache_keys(prefix="system_prompt_")
                        for key in keys:
                            pm.cache.invalidate(key)
                        pm.logger.info(f"Cleared system_prompt cache due to language change for guild {guild_id}")
                    except Exception as inner_e:
                        import asyncio as _asyncio
                        _asyncio.create_task(func.report_error(inner_e, "clearing prompt cache after language change"))
            except Exception:
                # Non-fatal: if prompting subsystem isn't available, ignore
                pass

            return True
        except Exception as e:
            import asyncio
            asyncio.create_task(func.report_error(e, "saving server language"))
            return False

    def translate(self, guild_id: str, *args, **kwargs) -> str:
        """翻譯指定的文字，模組化翻譯檔案結構
        
        Maintains backward compatibility while implementing new features:
        - Multi-layer cache system
        - Lazy loading of translation files
        - Path resolution with fallback mechanism
        - Enhanced error logging for missing translations
        
        Args:
            guild_id: Server ID
            *args: Translation path, can be multiple parts (e.g., "commands", "play", "errors", "queue_full")
            **kwargs: Formatting parameters
            
        Returns:
            str: Translated text or formatted error message if translation not found
        """
        try:
            # 處理初始化期間的特殊情況
            if not hasattr(self, 'translations') or not self.translations:
                return args[-1] if args else "LOADING..."
            
            lang = self.get_server_lang(str(guild_id))
            
            # 構建查詢路徑
            path_parts = self._parse_path_parts(args)
            
            if not path_parts:
                return args[-1] if args else "TRANSLATION_ERROR"
            
            # 生成快取鍵
            cache_key = f"{lang}:{':'.join(path_parts)}:{hash(str(sorted(kwargs.items())))}"
            
            # 檢查快取
            cached_result = self._translation_cache.get(cache_key)
            if cached_result:
                return self._format_result(cached_result, kwargs)
            
            # 執行翻譯查找
            translation_found, result = self._find_translation_with_fallback(lang, path_parts)
            
            # Enhanced error logging for missing translations
            if not translation_found:
                self._log_missing_translation(guild_id, lang, path_parts, args)
                # Return formatted error message instead of fallback
                formatted_error = f"[Translation not found: {'.'.join(path_parts)}]"
                return self._format_result(formatted_error, kwargs)
            
            # 格式化結果
            formatted_result = self._format_result(result, kwargs)
            
            # 快取結果 (only cache successful translations)
            if translation_found:
                self._translation_cache.put(cache_key, result)
            
            return formatted_result
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "translation"))
            return args[-1] if args else "TRANSLATION_ERROR"
    
    def _parse_path_parts(self, args) -> List[str]:
        """Parse translation path from arguments"""
        path_parts = []
        
        for arg in args:
            if not arg:
                continue
            
            # 處理包含路徑分隔符的部分
            if '/' in arg:
                subparts = arg.split('/')
                path_parts.extend(subparts)
            else:
                path_parts.append(arg)
        
        return path_parts
    
    def _format_result(self, result: str, kwargs: Dict[str, Any]) -> str:
        """Format translation result with parameters"""
        if not isinstance(result, str):
            return str(result) if result is not None else "TRANSLATION_ERROR"
        
        if not kwargs:
            return result
        
        try:
            return result.format(**kwargs)
        except KeyError as e:
            self.logger.warning(f"Format error in translation: missing key {e}")
            return result
        except Exception as e:
            self.logger.error(f"Format error in translation: {e}")
            return result
    
    def clear_cache(self):
        """清除翻譯快取"""
        self._translation_cache.clear()
        self.logger.info("Translation cache cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring"""
        return {
            "cache_size": self._translation_cache.size(),
            "max_cache_size": self._translation_cache._max_size,
            "loaded_files": len(self._loaded_files),
            "pending_loads": len(self._pending_loads),
            "supported_languages": len(self.supported_languages)
        }
    
    def _preload_related_files(self, lang: str, path_parts: List[str]):
        """預載入相關檔案以提升效能"""
        # 請求載入可能需要的檔案
        file_path = self._resolve_translation_file(lang, *path_parts)
        if file_path:
            self._request_file_load(lang, file_path)
        
        # 預載入 common.json（如果尚未載入）
        if lang not in self._loaded_files or ("common" not in [f[1] for f in self._loaded_files if f[0] == lang]):
            self._request_file_load(lang, "common")
    
    def _log_missing_translation(self, guild_id: str, lang: str, path_parts: List[str], original_args: tuple):
        """Log detailed information about missing translations for debugging purposes
        
        Args:
            guild_id: The guild/server ID that triggered the translation request
            lang: The language code that was being used
            path_parts: The translation key path parts
            original_args: The original arguments passed to translate method
        """
        # Attempt to extract cog name from the original arguments
        cog_name = "unknown"
        if len(original_args) > 1 and isinstance(original_args[0], str):
            # Check if first argument looks like a cog name (common patterns)
            first_arg = original_args[0]
            if first_arg in ['commands', 'system', 'common', 'errors', 'botinfo', 'help']:
                cog_name = first_arg
            elif len(original_args) > 1:
                # Try second argument as potential cog name
                second_arg = original_args[1]
                if isinstance(second_arg, str) and len(second_arg) > 0:
                    cog_name = second_arg
        
        # Create the full translation key path
        translation_key = ".".join(path_parts)
        
        # Log the missing translation with detailed context
        self.logger.warning(
            f"Translation key not found: "
            f"guild_id={guild_id}, "
            f"key='{translation_key}', "
            f"language='{lang}', "
            f"cog_name='{cog_name}'"
        )
        
        # Also use func.report_error for consistency and traceability
        error_msg = (
            f"Missing translation: guild_id={guild_id}, "
            f"key='{translation_key}', language='{lang}', cog_name='{cog_name}'"
        )
        
        # Create and report the translation error for consistency
        translation_error = MissingTranslationError(error_msg)
        asyncio.create_task(func.report_error(translation_error, "missing translation key"))

    @app_commands.command(
        name="set_language",
        description="設定伺服器使用的語言"
    )
    @app_commands.describe(
        language="選擇要使用的語言"
    )
    @app_commands.choices(language=[
        app_commands.Choice(name="繁體中文", value="zh_TW"),
        app_commands.Choice(name="简体中文", value="zh_CN"),
        app_commands.Choice(name="English", value="en_US"),
        app_commands.Choice(name="日本語", value="ja_JP")
    ])
    async def set_language(self, interaction: discord.Interaction, language: str):
        """設定伺服器的顯示語言"""
        # 檢查使用者是否有管理員權限
        if not interaction.user.guild_permissions.administrator:
            error_message = self.translate(
                str(interaction.guild_id),
                "errors",
                "permission_denied"
            )
            await interaction.response.send_message(error_message)
            return
        
        guild_id = str(interaction.guild_id)
        
        if language not in self.supported_languages:
            await interaction.response.send_message(
                self.translate(guild_id, "commands", "set_language", "responses", "unsupported")
            )
            return

        if self.save_server_lang(guild_id, language):
            lang_name = self.supported_languages[language]
            await interaction.response.send_message(
                self.translate(guild_id, "commands", "set_language", "responses", "success", language=lang_name)
            )
        else:
            await interaction.response.send_message(
                self.translate(guild_id, "commands", "set_language", "responses", "error")
            )

    @app_commands.command(
        name="current_language",
        description="顯示目前伺服器使用的語言"
    )
    async def current_language(self, interaction: discord.Interaction):
        """顯示目前伺服器使用的語言"""
        guild_id = str(interaction.guild_id)
        current_lang = self.get_server_lang(guild_id)
        lang_name = self.supported_languages.get(current_lang, current_lang)
        
        await interaction.response.send_message(
            self.translate(
                guild_id,
                "commands",
                "current_language",
                "responses",
                "current",
                language=lang_name
            )
        )

    @staticmethod
    def get_instance(bot: commands.Bot) -> Optional['LanguageManager']:
        """獲取 LanguageManager 實例"""
        return bot.get_cog('LanguageManager')

    def localize_command(self, command: app_commands.Command, guild_id: str):
        """本地化命令的名稱和描述

        Args:
            command: Discord 命令
            guild_id: 伺服器ID
        """
        command_name = command.name
        translations = self.translations.get(self.get_server_lang(guild_id), {}).get('common', {}).get('commands', {}).get(command_name, {})
        
        if translations:
            if 'name' in translations:
                command.name = translations['name']
            if 'description' in translations:
                command.description = translations['description']
            
            # 本地化選項描述
            if hasattr(command, '_params'):
                for param in command._params.values():
                    if param.name in translations.get('options', {}):
                        param.description = translations['options'][param.name]

    def localize_choices(self, choices: list[app_commands.Choice], guild_id: str, command_name: str, option_name: str) -> list[app_commands.Choice]:
        """本地化選項的選擇項

        Args:
            choices: 選擇項列表
            guild_id: 伺服器ID
            command_name: 命令名稱
            option_name: 選項名稱

        Returns:
            本地化後的選擇項列表
        """
        translations = self.translations.get(self.get_server_lang(guild_id), {}).get('common', {}).get('commands', {}).get(command_name, {})
        choice_translations = translations.get('choices', {})
        
        if choice_translations:
            return [
                app_commands.Choice(
                    name=choice_translations.get(choice.value, choice.name),
                    value=choice.value
                )
                for choice in choices
            ]
        return choices

async def setup(bot: commands.Bot):
    await bot.add_cog(LanguageManager(bot))
