"""用於處理Discord管理代理人功能的Cog。"""

import discord
from discord import app_commands
from discord.ext import commands
import logging
from datetime import datetime
from typing import Optional, Literal, Dict, Any, Union
import json
import re
import os

from gpt.gpt_response_gen import generate_response, get_model_and_tokenizer

class DiscordManagerAgent(commands.Cog):
    """Discord管理代理人系統。"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.security = SecurityManager()
        self.parser = InstructionParser()

    SUPPORTED_OPERATIONS = {
        "channel": ["create", "delete", "modify", "move"],
        "role": ["create", "delete", "modify", "assign"],
        "voice": ["move", "disconnect", "limit"],
        "category": ["create", "delete", "organize"],
        "permissions": ["set", "sync", "audit"]
    }

    @commands.hybrid_command(
        name="manage",
        description="使用自然語言管理Discord伺服器"
    )
    @app_commands.describe(
        instruction="要執行的管理指令",
    )
    @commands.has_permissions(manage_guild=True)
    async def manage_command(
        self,
        ctx: commands.Context,
        instruction: str
    ):
        """使用自然語言管理Discord伺服器。"""
        processing_msg = None
        try:
            # 顯示處理中訊息
            processing_msg = await ctx.reply("🤔 正在分析您的指令...")

            # 驗證操作權限
            if not self.security.validate_operation(ctx.author, instruction):
                await processing_msg.edit(content="⛔ 您沒有足夠的權限執行此操作")
                return

            # 使用LLM解析指令
            parsed = await self.parser.parse(instruction)
            if not parsed:
                await processing_msg.edit(content="❓ 無法理解該指令，請使用更清楚的描述")
                return

            # 更新狀態訊息
            await processing_msg.edit(content="⚙️ 正在執行操作...")

            # 執行相應操作
            result = await self.execute_operation(ctx, parsed)
            
            # 記錄審計日誌
            self.security.audit_log(parsed, ctx.author, result)

            await processing_msg.edit(content=f"✅ 操作完成: {result}")

        except Exception as e:
            self.logger.error(f"執行管理指令時發生錯誤: {str(e)}")
            error_msg = f"❌ 執行指令時發生錯誤: {str(e)}"
            if processing_msg:
                await processing_msg.edit(content=error_msg)
            else:
                await ctx.reply(error_msg)

    async def execute_operation(self, ctx: commands.Context, parsed_instruction: dict):
        """
        執行解析後的指令。

        Args:
            ctx: Discord指令上下文
            parsed_instruction: 解析後的指令內容
        """
        action = parsed_instruction["action"]
        target_type = parsed_instruction["target_type"]
        params = parsed_instruction["additional_params"]

        if target_type == "channel":
            return await self._handle_channel_operation(ctx, action, params)
        elif target_type == "role":
            return await self._handle_role_operation(ctx, action, params)
        elif target_type == "voice":
            return await self._handle_voice_operation(ctx, action, params)
        elif target_type == "category":
            return await self._handle_category_operation(ctx, action, params)
        elif target_type == "permissions":
            return await self._handle_permission_operation(ctx, action, params)
        else:
            raise ValueError(f"不支援的操作類型: {target_type}")

    async def _handle_channel_operation(self, ctx, action, params):
        """處理頻道相關操作。"""
        if action == "create":
            channel_type = params.get("type", "text")
            create_func = (ctx.guild.create_voice_channel if channel_type == "voice" 
                         else ctx.guild.create_text_channel)
            
            channel = await create_func(
                name=params["name"],
                category=await self._get_category(ctx, params.get("category")),
                overwrites=await self._get_overwrites(ctx, params.get("permissions", {}))
            )
            return f"已建立頻道 {channel.name}"
            
        elif action == "delete":
            channel = await self._get_channel(ctx, params["name"])
            if channel:
                await channel.delete()
                return f"已刪除頻道 {channel.name}"
            return f"找不到頻道 {params['name']}"
            
        elif action == "modify":
            channel = await self._get_channel(ctx, params["name"])
            if channel:
                await channel.edit(**params.get("settings", {}))
                return f"已修改頻道 {channel.name} 的設定"
            return f"找不到頻道 {params['name']}"
            
        elif action == "move":
            channel = await self._get_channel(ctx, params["name"])
            new_category = await self._get_category(ctx, params["category"])
            if channel and new_category:
                await channel.move(category=new_category)
                return f"已將頻道 {channel.name} 移動到分類 {new_category.name}"
            return "找不到指定的頻道或分類"

    async def _handle_role_operation(self, ctx, action, params):
        """處理身分組相關操作。"""
        if action == "create":
            color = params.get("color")
            if isinstance(color, str):
                try:
                    color = int(color.strip("#"), 16)
                except ValueError:
                    color = 0

            role = await ctx.guild.create_role(
                name=params["name"],
                color=discord.Color(color) if color else discord.Color.default(),
                permissions=discord.Permissions(**params.get("permissions", {}))
            )
            return f"已建立身分組 {role.name}"
            
        elif action == "delete":
            role = await self._get_role(ctx, params["name"])
            if role:
                await role.delete()
                return f"已刪除身分組 {role.name}"
            return f"找不到身分組 {params['name']}"
            
        elif action == "modify":
            role = await self._get_role(ctx, params["name"])
            if role:
                await role.edit(**params.get("settings", {}))
                return f"已修改身分組 {role.name} 的設定"
            return f"找不到身分組 {params['name']}"
            
        elif action == "assign":
            role = await self._get_role(ctx, params["role_name"])
            member = await self._get_member(ctx, params["userid"])
            if role and member:
                await member.add_roles(role)
                return f"已將身分組 {role.name} 指派給 {member.mention}"
            return "找不到指定的身分組或成員"

    async def _handle_voice_operation(self, ctx, action, params):
        """處理語音頻道相關操作。"""
        if action == "move":
            member = await self._get_member(ctx, params["userid"])
            channel = await self._get_channel(ctx, params["channel_name"], 
                                           channel_type="voice")
            if member and channel:
                await member.move_to(channel)
                return f"已將 {member.mention} 移動到 {channel.name}"
            return "找不到指定的成員或語音頻道"
            
        elif action == "disconnect":
            member = await self._get_member(ctx, params["userid"])
            if member:
                await member.move_to(None)
                return f"已將 {member.mention} 從語音頻道中斷連接"
            return f"找不到成員 {params['userid']}"
            
        elif action == "limit":
            channel = await self._get_channel(ctx, params["channel_name"], channel_type="voice")
            if channel:
                await channel.edit(user_limit=params.get("limit", 0))
                return f"已設定 {channel.name} 的使用者數量限制為 {params.get('limit', '無限制')}"
            return f"找不到語音頻道 {params['channel_name']}"

    async def _handle_category_operation(self, ctx, action, params):
        """處理分類相關操作。"""
        if action == "create":
            category = await ctx.guild.create_category(
                name=params["name"],
                overwrites=await self._get_overwrites(ctx, params.get("permissions", {}))
            )
            return f"已建立分類 {category.name}"
            
        elif action == "delete":
            category = await self._get_category(ctx, params["name"])
            if category:
                await category.delete()
                return f"已刪除分類 {category.name}"
            return f"找不到分類 {params['name']}"
            
        elif action == "organize":
            category = await self._get_category(ctx, params["name"])
            if not category:
                return f"找不到分類 {params['name']}"
                
            channels = [await self._get_channel(ctx, name) 
                       for name in params.get("channels", [])]
            channels = [c for c in channels if c]  # 移除None值
            
            for channel in channels:
                await channel.move(category=category)
            return f"已將 {len(channels)} 個頻道移動到分類 {category.name}"

    async def _handle_permission_operation(self, ctx, action, params):
        """處理權限相關操作。"""
        if action == "set":
            target = await self._get_channel(ctx, params.get("channel_name")) or \
                    await self._get_role(ctx, params.get("role_name"))
            if not target:
                return "找不到指定的目標"
            overwrites = await self._get_overwrites(ctx, params.get("permissions", {}))
            await target.edit(overwrites=overwrites)
            return f"已設定 {target.name} 的權限"

    # 輔助方法
    async def _get_channel(self, ctx, name: str, 
                          channel_type: str = None) -> Optional[discord.abc.GuildChannel]:
        """獲取指定名稱的頻道。"""
        for channel in ctx.guild.channels:
            if channel.name.lower() == name.lower():
                if not channel_type or channel_type == str(channel.type):
                    return channel
        return None

    async def _get_role(self, ctx, name: str) -> Optional[discord.Role]:
        """獲取指定名稱的身分組。"""
        return discord.utils.get(ctx.guild.roles, name=name)

    async def _get_member(self, ctx, user_identifier: str) -> Optional[discord.Member]:
        """獲取指定成員。

        Args:
            ctx: Discord指令上下文
            user_identifier: 使用者識別碼，可以是 ID 或 @ 提及格式

        Returns:
            Optional[discord.Member]: 找到的成員物件，若未找到則返回 None
        """
        # 處理 @ 提及格式
        mention_match = re.match(r'<@!?(\d+)>', user_identifier)
        if mention_match:
            user_id = int(mention_match.group(1))
            return ctx.guild.get_member(user_id)
        
        # 處理純數字 ID
        if user_identifier.isdigit():
            return ctx.guild.get_member(int(user_identifier))
        
        return None

    async def _get_category(self, ctx, name: str) -> Optional[discord.CategoryChannel]:
        """獲取指定名稱的分類。"""
        if not name:
            return None
        return discord.utils.get(ctx.guild.categories, name=name)

    async def _get_overwrites(self, ctx, permissions: Dict) -> Dict:
        """將權限字典轉換為Discord權限設定。"""
        overwrites = {}
        for target_name, perms in permissions.items():
            target = await self._get_role(ctx, target_name) or \
                    await self._get_member(ctx, target_name)
            if target:
                overwrites[target] = discord.PermissionOverwrite(**perms)
        return overwrites

class SecurityManager:
    """安全管理器"""

    def validate_operation(self, member, operation):
        """驗證操作權限。"""
        required_permissions = {
            "channel": discord.Permissions(manage_channels=True),
            "role": discord.Permissions(manage_roles=True),
            "voice": discord.Permissions(move_members=True),
            "category": discord.Permissions(manage_channels=True),
            "permissions": discord.Permissions(manage_permissions=True)
        }

        for perm_name, required_perm in required_permissions.items():
            if perm_name in operation.lower():
                return member.guild_permissions >= required_perm

        return member.guild_permissions.administrator

    def audit_log(self, operation, member, result):
        """記錄審計日誌。"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "member_id": member.id,
            "member_name": member.name,
            "result": result
        }
        
        try:
            os.makedirs("logs", exist_ok=True)
            with open("logs/agent_audit.log", "a", encoding="utf-8") as f:
                json.dump(log_entry, f, ensure_ascii=False)
                f.write("\n")
        except Exception as e:
            logging.error(f"寫入審計日誌時發生錯誤: {str(e)}")

class InstructionParser:
    """使用LLM的智能指令解析器"""

    def __init__(self):
        self.system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        """載入系統提示。"""
        try:
            with open("gpt/discord_agent_prompt.txt", "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logging.error(f"載入系統提示時發生錯誤: {str(e)}")
            return ""

    async def parse(self, instruction: str) -> Optional[Dict[str, Any]]:
        """使用LLM解析自然語言指令。"""
        try:
            # 獲取當前已加載的模型
            model, tokenizer = get_model_and_tokenizer()
            if model is None or tokenizer is None:
                raise ValueError("模型尚未加載，請等待模型加載完成")

            thread, gen = await generate_response(
                instruction,
                self.system_prompt,
            )

            response = ""
            async for chunk in gen:
                response += chunk

            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start != -1 and json_end != -1:
                json_str = response[json_start:json_end]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    logging.error(f"無法解析JSON回應: {json_str}")
                    return None
            else:
                logging.error(f"回應中找不到有效的JSON: {response}")
                return None

        except Exception as e:
            logging.error(f"解析指令時發生錯誤: {str(e)}")
            return None
        finally:
            if thread is not None:
                thread.join()

async def setup(bot: commands.Bot):
    """設置Cog。"""
    await bot.add_cog(DiscordManagerAgent(bot))
