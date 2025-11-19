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
        
        # 翻譯資料結構：lang -> nested dict
        self.translations: Dict[str, Dict[str, Any]] = {}
        
        # 快取系統
        self._translation_cache = TranslationCache(max_size=1000)
        
        # 語言選項
        self.supported_languages = {}
        
        # 載入翻譯並初始化
        self._load_translations()
        self.supported_languages = self._get_supported_languages()

    def _load_translations(self):
        """載入所有語言翻譯，支援多檔案結構"""
        lang_codes = ["zh_TW", "zh_CN", "en_US", "ja_JP"]
        
        for lang_code in lang_codes:
            self.translations[lang_code] = {}
            lang_dir = os.path.join("translations", lang_code)
            
            if not os.path.exists(lang_dir):
                self.logger.warning(f"Translation directory not found: {lang_dir}")
                continue
            
            # 遞迴載入所有 JSON 檔案
            self._load_directory(lang_code, lang_dir, self.translations[lang_code])
            
            self.logger.info(f"Loaded translations for {lang_code}")

    def _load_directory(self, lang_code: str, directory: str, target_dict: Dict[str, Any]):
        """遞迴載入目錄中的所有 JSON 檔案
        
        Args:
            lang_code: 語言代碼
            directory: 要載入的目錄路徑
            target_dict: 目標字典（用於存儲載入的資料）
        """
        try:
            for item in os.listdir(directory):
                item_path = os.path.join(directory, item)
                
                # 如果是目錄，遞迴處理
                if os.path.isdir(item_path):
                    # 創建對應的嵌套字典
                    if item not in target_dict:
                        target_dict[item] = {}
                    self._load_directory(lang_code, item_path, target_dict[item])
                
                # 如果是 JSON 檔案，載入內容
                elif item.endswith('.json'):
                    file_key = item[:-5]  # 移除 .json 副檔名
                    try:
                        with open(item_path, 'r', encoding='utf-8') as f:
                            content = json.load(f)
                            if isinstance(content, dict) and file_key in content and len(content) == 1:
                                target_dict[file_key] = content[file_key]
                            else:
                                target_dict[file_key] = content
                        self.logger.debug(f"Loaded translation file: {lang_code}/{os.path.relpath(item_path, os.path.join('translations', lang_code))}")
                    except Exception as e:
                        self.logger.error(f"Error loading translation file {item_path}: {e}")
                        asyncio.create_task(func.report_error(e, f"loading translation file {item_path}"))
        
        except Exception as e:
            self.logger.error(f"Error reading directory {directory}: {e}")
            asyncio.create_task(func.report_error(e, f"reading translation directory {directory}"))

    def _get_supported_languages(self) -> Dict[str, str]:
        """獲取支援的語言列表"""
        try:
            return {
                "zh_TW": self.translate("0", "system", "language_manager", "supported_languages", "zh_TW"),
                "zh_CN": self.translate("0", "system", "language_manager", "supported_languages", "zh_CN"),
                "en_US": self.translate("0", "system", "language_manager", "supported_languages", "en_US"),
                "ja_JP": self.translate("0", "system", "language_manager", "supported_languages", "ja_JP")
            }
        except:
            # 備用硬編碼選項
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
                        asyncio.create_task(func.report_error(inner_e, "clearing prompt cache after language change"))
            except Exception:
                # Non-fatal: if prompting subsystem isn't available, ignore
                pass

            return True
        except Exception as e:
            asyncio.create_task(func.report_error(e, "saving server language"))
            return False

    def _traverse_nested_dict(self, data: Dict[str, Any], keys: List[str]) -> Optional[Any]:
        """遍歷嵌套字典
        
        Args:
            data: 要遍歷的字典
            keys: 鍵的列表
            
        Returns:
            找到的值，如果找不到則返回 None
        """
        current = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current

    def translate(self, guild_id: str, *keys, **kwargs) -> str:
        """翻譯指定的文字
        
        標準調用方式:
        translate(guild_id, "commands", "botinfo", "fields", "basic_stats", "name")
        translate(guild_id, "system", "language_manager", "supported_languages", "zh_TW")
        translate(guild_id, "errors", "permission_denied")
        
        檔案結構映射:
        - translate(guild_id, "commands", "botinfo", "fields", "basic_stats", "name")
          → translations/zh_TW/commands/botinfo.json → ["fields"]["basic_stats"]["name"]
        
        - translate(guild_id, "system", "language_manager", "supported_languages", "zh_TW")
          → translations/zh_TW/system/language_manager.json → ["supported_languages"]["zh_TW"]
        
        Args:
            guild_id: 伺服器 ID
            *keys: 翻譯鍵的路徑（多個參數）
            **kwargs: 格式化參數
            
        Returns:
            str: 翻譯後的文字
        """
        try:
            # 處理初始化期間的特殊情況
            if not hasattr(self, 'translations') or not self.translations:
                return keys[-1] if keys else "LOADING..."
            
            # 獲取語言
            lang = self.get_server_lang(str(guild_id))
            
            # 驗證參數
            if not keys:
                self.logger.warning("translate() called with no keys")
                return "TRANSLATION_ERROR"
            
            # 生成快取鍵
            cache_key = f"{lang}:{':'.join(keys)}:{hash(str(sorted(kwargs.items())))}"
            
            # 檢查快取
            cached_result = self._translation_cache.get(cache_key)
            if cached_result:
                return self._format_result(cached_result, kwargs)
            
            # 獲取語言的翻譯資料
            if lang not in self.translations:
                self._log_missing_translation(guild_id, lang, list(keys))
                return f"[Translation not found: {'.'.join(keys)}]"
            
            # 遍歷嵌套字典
            result = self._traverse_nested_dict(self.translations[lang], list(keys))
            
            # 檢查結果
            if result is None:
                self._log_missing_translation(guild_id, lang, list(keys))
                return f"[Translation not found: {'.'.join(keys)}]"
            
            if not isinstance(result, str):
                self.logger.warning(f"Translation result is not a string: {'.'.join(keys)}")
                return str(result)
            
            # 快取結果
            self._translation_cache.put(cache_key, result)
            
            # 格式化並返回
            return self._format_result(result, kwargs)
            
        except Exception as e:
            self.logger.error(f"Error in translate(): {e}")
            asyncio.create_task(func.report_error(e, "translation"))
            return keys[-1] if keys else "TRANSLATION_ERROR"
    
    def _format_result(self, result: str, kwargs: Dict[str, Any]) -> str:
        """格式化翻譯結果
        
        Args:
            result: 翻譯結果
            kwargs: 格式化參數
            
        Returns:
            格式化後的字串
        """
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
    
    def _log_missing_translation(self, guild_id: str, lang: str, keys: List[str]):
        """記錄缺失的翻譯
        
        Args:
            guild_id: 伺服器 ID
            lang: 語言代碼
            keys: 翻譯鍵路徑
        """
        translation_key = ".".join(keys)
        
        # 提取 cog 名稱
        cog_name = keys[0] if keys else "unknown"
        
        # 記錄警告
        self.logger.warning(
            f"Translation key not found: "
            f"guild_id={guild_id}, "
            f"key='{translation_key}', "
            f"language='{lang}', "
            f"cog_name='{cog_name}'"
        )
        
        # 報告錯誤
        error_msg = (
            f"Missing translation: guild_id={guild_id}, "
            f"key='{translation_key}', language='{lang}', cog_name='{cog_name}'"
        )
        
        translation_error = MissingTranslationError(error_msg)
        asyncio.create_task(func.report_error(translation_error, "missing translation key"))
    
    def clear_cache(self):
        """清除翻譯快取"""
        self._translation_cache.clear()
        self.logger.info("Translation cache cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """獲取快取統計資訊"""
        return {
            "cache_size": self._translation_cache.size(),
            "max_cache_size": self._translation_cache._max_size,
            "supported_languages": len(self.supported_languages)
        }

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

async def setup(bot: commands.Bot):
    await bot.add_cog(LanguageManager(bot))
