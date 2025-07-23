# -*- coding: utf-8 -*-
import io
import json
import logging
import discord
from typing import Any, Dict, List, Optional

from gpt.tools.registry import tool_registry
from gpt.tools.tool_context import ToolExecutionContext

class ToolExecutor:
    """
    統一處理工具的選擇、並行執行和結果格式化。
    """

    def __init__(self, bot):
        self.bot = bot
        self.tool_registry = tool_registry

    async def execute_tools(self, action_list: List[Dict], context: ToolExecutionContext) -> List[Dict]:
        """
        根據動作列表執行工具。
        未來將擴展以支持並行執行。

        Args:
            action_list: 從 LLM 獲取的工具調用列表。
            context: 工具執行的上下文。

        Returns:
            一個包含格式化後工具結果的列表。
        """
        final_results = []
        
        # 目前為循序執行，未來可改為並行
        for action in action_list:
            tool_name = action.get("tool_name")
            parameters = action.get("parameters", {})

            if not tool_name or tool_name == "directly_answer":
                continue

            try:
                tool = self.tool_registry.get_tool(tool_name)
                result = await tool.execute(context, **parameters)
                
                # 處理圖片生成的特殊情況
                if tool_name == "gen_img" and isinstance(result, io.BytesIO):
                    result.seek(0)
                    file = discord.File(result, filename="generated_image.png")
                    await context.message.channel.send(content="這張圖給你參考:", file=file)
                
                formatted_result = self._format_tool_result(tool_name, result)
                final_results.append(formatted_result)

            except KeyError:
                context.logger.warning(f"偵測到未知的工具: {tool_name}")
                error_result = self._format_tool_result(tool_name, f"錯誤: 找不到名為 '{tool_name}' 的工具。")
                final_results.append(error_result)
            except Exception as e:
                context.logger.error(f"執行工具 '{tool_name}' 時發生錯誤: {e}", exc_info=True)
                error_result = self._format_tool_result(tool_name, f"執行工具 '{tool_name}' 時發生內部錯誤: {e}")
                final_results.append(error_result)
        
        return final_results

    def _format_tool_result(self, tool_name: str, result: Any) -> Dict[str, Any]:
        """
        將工具結果格式化為 Google Gemini API 的標準格式。
        """
        try:
            if isinstance(result, (dict, list)):
                content = json.dumps(result, ensure_ascii=False, indent=2)
            elif isinstance(result, io.BytesIO):
                content = f"已成功生成圖片 (工具: {tool_name})"
            elif result is None:
                content = f"工具 {tool_name} 執行完畢，沒有返回內容。"
            else:
                content = str(result)
            
            return {
                "role": "function",
                "name": tool_name,
                "content": content
            }
        except Exception as e:
            logging.error(f"格式化工具 '{tool_name}' 的結果時失敗: {e}")
            return {
                "role": "function",
                "name": tool_name,
                "content": f"格式化工具結果時發生錯誤: {str(e)}"
            }