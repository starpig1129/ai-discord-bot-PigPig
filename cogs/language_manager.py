import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import logging
from typing import Optional, Dict, Any

class LanguageManager(commands.Cog):
    """語言管理系統"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_dir = "data/serverconfig"
        # 確保配置目錄存在
        os.makedirs(self.config_dir, exist_ok=True)
        
        self.logger = logging.getLogger(__name__)
        self.default_lang = "zh_TW"  # 預設使用繁體中文
        self.supported_languages = {
            "zh_TW": "繁體中文",
            "zh_CN": "简体中文",
            "en_US": "English",
            "ja_JP": "日本語"
        }
        self.translations: Dict[str, Dict[str, Dict[str, str]]] = {}
        self._load_translations()

    def _load_translations(self):
        """載入所有語言翻譯"""
        for lang_code in self.supported_languages.keys():
            self.translations[lang_code] = {}
            lang_dir = os.path.join("translations", lang_code)
            
            if not os.path.exists(lang_dir):
                self.logger.warning(f"找不到語言目錄：{lang_dir}")
                continue
                
            for file in os.listdir(lang_dir):
                if not file.endswith('.json'):
                    continue
                    
                try:
                    file_path = os.path.join(lang_dir, file)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        translations = json.load(f)
                        
                    category = file[:-5]  # 移除 .json 後綴
                    self.translations[lang_code][category] = translations
                        
                except Exception as e:
                    self.logger.error(f"載入翻譯文件時出錯 {file_path}: {str(e)}")

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
            self.logger.error(f"讀取語言設定時出錯: {str(e)}")
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
            return True
        except Exception as e:
            self.logger.error(f"保存語言設定時出錯: {str(e)}")
            return False

    def translate(self, guild_id: str, *args, **kwargs) -> str:
        """翻譯指定的文字

        Args:
            guild_id: 伺服器ID
            *args: 翻譯路徑，可以是多個部分（例如："commands", "play", "errors", "queue_full"）
            **kwargs: 格式化參數

        Returns:
            str: 翻譯後的文字
        """
        try:
            lang = self.get_server_lang(str(guild_id))
            translations = self.translations.get(lang, {}).get('common', {})
            
            self.logger.debug(f"Translating with lang={lang}, args={args}, kwargs={kwargs}")
            
            # 從參數構建翻譯路徑
            result = translations
            path = []
            
            for part in args:
                if not part:
                    continue
                    
                if '/' in part:
                    # 處理包含路徑分隔符的部分
                    subparts = part.split('/')
                    path.extend(subparts)
                else:
                    path.append(part)
            
            # 沿著路徑獲取翻譯
            for part in path:
                if not isinstance(result, dict):
                    self.logger.warning(f"無法繼續遍歷路徑 {'/'.join(path)}, 當前結果不是字典: {result}")
                    return path[-1]
                result = result.get(part, {})
            
            # 如果結果是字符串，進行格式化
            if isinstance(result, str):
                try:
                    return result.format(**kwargs)
                except KeyError as e:
                    self.logger.error(f"格式化翻譯時出錯，缺少參數: {e}")
                    return result
            
            # 如果找不到翻譯，返回最後一個路徑部分
            self.logger.warning(f"未找到翻譯: {'/'.join(path)}")
            return path[-1] if path else "TRANSLATION_NOT_FOUND"
            
        except Exception as e:
            self.logger.error(f"翻譯文字時出錯: {str(e)}")
            return args[-1] if args else "TRANSLATION_ERROR"

    @app_commands.command(
        name="set_language",
        description="設定伺服器使用的語言"
    )
    @app_commands.describe(
        language="選擇要使用的語言"
    )
    @app_commands.choices(language=[
        app_commands.Choice(name=name, value=code)
        for code, name in {
            "zh_TW": "繁體中文",
            "zh_CN": "简体中文",
            "en_US": "English",
            "ja_JP": "日本語"
        }.items()
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
