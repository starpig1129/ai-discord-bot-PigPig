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

    def translate(self, guild_id: str, category: str, key: str, subkey: Optional[str] = None, **kwargs) -> str:
        """翻譯指定的文字

        Args:
            guild_id: 伺服器ID
            category: 翻譯類別 (例如: 'commands', 'errors')
            key: 翻譯鍵值 (例如: 'help', 'set_language')
            subkey: 子鍵值 (例如: 'name', 'description')
            **kwargs: 格式化參數

        Returns:
            str: 翻譯後的文字
        """
        lang = self.get_server_lang(str(guild_id))
        translations = self.translations.get(lang, {}).get('common', {})
        
        try:
            # 根據提供的路徑獲取翻譯
            result = translations
            for part in [category, key]:
                if part:
                    result = result.get(part, {})
            
            if subkey:
                result = result.get(subkey, subkey)
            
            # 如果結果是字符串，嘗試進行格式化
            if isinstance(result, str):
                try:
                    return result.format(**kwargs)
                except KeyError:
                    return result
            
            # 如果找不到翻譯，返回原始鍵值
            return key
            
        except Exception as e:
            self.logger.error(f"翻譯文字時出錯: {str(e)}")
            return key

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
    @commands.has_permissions(administrator=True)
    async def set_language(self, interaction: discord.Interaction, language: str):
        """設定伺服器的顯示語言"""
        guild_id = str(interaction.guild_id)
        
        if language not in self.supported_languages:
            await interaction.response.send_message(
                "不支援的語言選項。",
                ephemeral=True
            )
            return

        if self.save_server_lang(guild_id, language):
            lang_name = self.supported_languages[language]
            await interaction.response.send_message(
                f"已將伺服器語言設定為：{lang_name}",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "設定語言時發生錯誤，請稍後再試。",
                ephemeral=True
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
            f"目前伺服器使用的語言為：{lang_name}",
            ephemeral=True
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
