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
        # Ensure config directory exists
        os.makedirs(self.config_dir, exist_ok=True)
        
        self.logger = log
        self.default_lang = "zh_TW"  # Default to Traditional Chinese
        
        # Translation data structure: lang -> nested dict
        self.translations: Dict[str, Dict[str, Any]] = {}
        
        # Cache system
        self._translation_cache = TranslationCache(max_size=1000)
        
        # Language options
        self.supported_languages = {}
        
        # Load translations and initialize
        self._load_translations()
        self.supported_languages = self._get_supported_languages()

    def _load_translations(self):
        """Load all language translations, supporting multi-file structure."""
        lang_codes = ["zh_TW", "zh_CN", "en_US", "ja_JP"]
        
        for lang_code in lang_codes:
            self.translations[lang_code] = {}
            lang_dir = os.path.join("translations", lang_code)
            
            if not os.path.exists(lang_dir):
                self.logger.warning(f"Translation directory not found: {lang_dir}")
                continue
            
            # Recursively load all JSON files
            self._load_directory(lang_code, lang_dir, self.translations[lang_code])
            
            self.logger.info(f"Loaded translations for {lang_code}")

    def _load_directory(self, lang_code: str, directory: str, target_dict: Dict[str, Any]):
        """Recursively load all JSON files in a directory.
        
        Args:
            lang_code: Language code.
            directory: Directory path to load.
            target_dict: Target dictionary to store loaded data.
        """
        try:
            for item in os.listdir(directory):
                item_path = os.path.join(directory, item)
                
                # If directory, process recursively
                if os.path.isdir(item_path):
                    # Create corresponding nested dictionary
                    if item not in target_dict:
                        target_dict[item] = {}
                    self._load_directory(lang_code, item_path, target_dict[item])
                
                # If JSON file, load content
                elif item.endswith('.json'):
                    file_key = item[:-5]  # Remove .json extension
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
        """Get the list of supported languages."""
        try:
            return {
                "zh_TW": self.translate("0", "system", "language_manager", "supported_languages", "zh_TW"),
                "zh_CN": self.translate("0", "system", "language_manager", "supported_languages", "zh_CN"),
                "en_US": self.translate("0", "system", "language_manager", "supported_languages", "en_US"),
                "ja_JP": self.translate("0", "system", "language_manager", "supported_languages", "ja_JP")
            }
        except:
            # Fallback hardcoded options
            return {
                "zh_TW": "繁體中文",
                "zh_CN": "简体中文",
                "en_US": "English",
                "ja_JP": "日本語"
            }

    def get_server_lang(self, guild_id: str) -> str:
        """Get the server's language setting."""
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
        """Save the server's language setting."""
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
        """Traverse a nested dictionary.
        
        Args:
            data: The dictionary to traverse.
            keys: List of keys.
            
        Returns:
            The value found, or None if not found.
        """
        current = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current

    def translate(self, guild_id: str, *keys, **kwargs) -> str:
        """Translate specified text.
        
        Standard calling convention:
        translate(guild_id, "commands", "botinfo", "fields", "basic_stats", "name")
        translate(guild_id, "system", "language_manager", "supported_languages", "zh_TW")
        translate(guild_id, "errors", "permission_denied")
        
        File structure mapping:
        - translate(guild_id, "commands", "botinfo", "fields", "basic_stats", "name")
          → translations/zh_TW/commands/botinfo.json → ["fields"]["basic_stats"]["name"]
        
        - translate(guild_id, "system", "language_manager", "supported_languages", "zh_TW")
          → translations/zh_TW/system/language_manager.json → ["supported_languages"]["zh_TW"]
        
        Args:
            guild_id: Server ID.
            *keys: Path of translation keys (multiple arguments).
            **kwargs: Formatting arguments.
            
        Returns:
            str: Translated text.
        """
        try:
            # Handle special cases during initialization
            if not hasattr(self, 'translations') or not self.translations:
                return keys[-1] if keys else "LOADING..."
            
            # Get language
            lang = self.get_server_lang(str(guild_id))
            
            # Validate parameters
            if not keys:
                self.logger.warning("translate() called with no keys")
                return "TRANSLATION_ERROR"
            
            # Generate cache key
            cache_key = f"{lang}:{':'.join(keys)}:{hash(str(sorted(kwargs.items())))}"
            
            # Check cache
            cached_result = self._translation_cache.get(cache_key)
            if cached_result:
                return self._format_result(cached_result, kwargs)
            
            # Get translation data for the language
            if lang not in self.translations:
                self._log_missing_translation(guild_id, lang, list(keys))
                return f"[Translation not found: {'.'.join(keys)}]"
            
            # Traverse nested dictionary
            result = self._traverse_nested_dict(self.translations[lang], list(keys))
            
            # Check results
            if result is None:
                self._log_missing_translation(guild_id, lang, list(keys))
                return f"[Translation not found: {'.'.join(keys)}]"
            
            if not isinstance(result, str):
                self.logger.warning(f"Translation result is not a string: {'.'.join(keys)}")
                return str(result)
            
            # Cache result
            self._translation_cache.put(cache_key, result)
            
            # Format and return
            return self._format_result(result, kwargs)
            
        except Exception as e:
            self.logger.error(f"Error in translate(): {e}")
            asyncio.create_task(func.report_error(e, "translation"))
            return keys[-1] if keys else "TRANSLATION_ERROR"
    
    def _format_result(self, result: str, kwargs: Dict[str, Any]) -> str:
        """Format translation result.
        
        Args:
            result: Translation result.
            kwargs: Formatting parameters.
            
        Returns:
            Formatted string.
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
        """Log missing translations.
        
        Args:
            guild_id: Server ID.
            lang: Language code.
            keys: Translation key path.
        """
        translation_key = ".".join(keys)
        
        # Extract cog name
        cog_name = keys[0] if keys else "unknown"
        
        # Log warning
        self.logger.warning(
            f"Translation key not found: "
            f"guild_id={guild_id}, "
            f"key='{translation_key}', "
            f"language='{lang}', "
            f"cog_name='{cog_name}'"
        )
        
        # Report error
        error_msg = (
            f"Missing translation: guild_id={guild_id}, "
            f"key='{translation_key}', language='{lang}', cog_name='{cog_name}'"
        )
        
        translation_error = MissingTranslationError(error_msg)
        asyncio.create_task(func.report_error(translation_error, "missing translation key"))
    
    def clear_cache(self):
        """Clear translation cache."""
        self._translation_cache.clear()
        self.logger.info("Translation cache cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "cache_size": self._translation_cache.size(),
            "max_cache_size": self._translation_cache._max_size,
            "supported_languages": len(self.supported_languages)
        }

    @app_commands.command(
        description="Set the language used by the server"
    )
    @app_commands.describe(
        language="Select the language to use"
    )
    @app_commands.choices(language=[
        app_commands.Choice(name="繁體中文", value="zh_TW"),
        app_commands.Choice(name="简体中文", value="zh_CN"),
        app_commands.Choice(name="English", value="en_US"),
        app_commands.Choice(name="日本語", value="ja_JP")
    ])
    async def set_language(self, interaction: discord.Interaction, language: str):
        """Set the display language of the server."""
        # Check if user has administrator permissions
        if not interaction.user.guild_permissions.administrator:
            error_message = self.translate(
                str(interaction.guild_id),
                "errors",
                "permission_denied"
            )
            await interaction.response.send_message(error_message, ephemeral=True)
            return
        
        guild_id = str(interaction.guild_id)
        
        if language not in self.supported_languages:
            await interaction.response.send_message(
                self.translate(guild_id, "commands", "set_language", "responses", "unsupported"),
                ephemeral=True
            )
            return

        if self.save_server_lang(guild_id, language):
            lang_name = self.supported_languages[language]
            await interaction.response.send_message(
                self.translate(guild_id, "commands", "set_language", "responses", "success", language=lang_name),
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                self.translate(guild_id, "commands", "set_language", "responses", "error"),
                ephemeral=True
            )

    @app_commands.command(
        description="Display the current language used by the server"
    )
    async def current_language(self, interaction: discord.Interaction):
        """Display the current language used by the server."""
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
            ),
            ephemeral=True
        )

    @staticmethod
    def get_instance(bot: commands.Bot) -> Optional['LanguageManager']:
        """Get LanguageManager instance."""
        return bot.get_cog('LanguageManager')

async def setup(bot: commands.Bot):
    await bot.add_cog(LanguageManager(bot))
