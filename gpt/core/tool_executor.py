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
        根據動作列表執行工具，並產生結構化的執行報告。
        實現了「快速失敗」機制，任何工具執行失敗都會立即中止並回報錯誤。

        Args:
            action_list: 從 LLM 獲取的工具調用列表。
            context: 工具執行的上下文。

        Returns:
            一個包含格式化後工具執行報告的列表。
        """
        tool_execution_report = []

        for action in action_list:
            tool_name = action.get("tool_name")
            parameters = action.get("parameters", {})

            if not tool_name or tool_name == "directly_answer":
                continue

            try:
                tool = self.tool_registry.get_tool(tool_name)
                result = await tool.execute(context, **parameters)

                if tool_name == "gen_img" and isinstance(result, io.BytesIO):
                    result.seek(0)
                    file = discord.File(result, filename="generated_image.png")
                    await context.message.channel.send(content="這張圖給你參考:", file=file)
                    result = "成功生成並發送了一張圖片。"

                report = self._create_structured_report(tool_name, "success", result)
                tool_execution_report.append(report)

            except Exception as e:
                error_message = f"執行工具 '{tool_name}' 時發生錯誤: {str(e)}"
                context.logger.error(f"執行工具 '{tool_name}' 時發生錯誤: {e}", exc_info=True)
                
                # 快速失敗：立即建立錯誤報告並返回
                error_report = self._create_structured_report(
                    tool_name, "failure", error_message, error_type=type(e).__name__
                )
                # 返回單一的錯誤報告，以便上層處理
                return self._format_report_for_llm([error_report])
        
        return self._format_report_for_llm(tool_execution_report)

    def _create_structured_report(self, tool_name: str, status: str, result: Any, error_type: Optional[str] = None) -> Dict[str, Any]:
        """
        創建一個結構化的工具執行報告。
        """
        report = {
            "tool_name": tool_name,
            "status": status,
        }
        if status == "success":
            report["output"] = result
        else:
            report["output"] = {
                "error_type": error_type,
                "error_message": str(result)
            }
        return report

    def _format_report_for_llm(self, report_data: List[Dict]) -> List[Dict]:
        """
        將結構化的報告格式化為 LLM 需要的最終格式。
        """
        if not report_data:
            return []
            
        # 對於單一工具調用，直接格式化
        if len(report_data) == 1:
            report = report_data[0]
            content = json.dumps(report, ensure_ascii=False, indent=2)
            return [{
                "role": "function",
                "name": report["tool_name"],
                "content": content
            }]
        
        # 對於多個工具調用，將所有報告捆綁在一個 content 中
        content = json.dumps(report_data, ensure_ascii=False, indent=2)
        # 使用一個通用的名稱來代表多工具執行的結果
        return [{
            "role": "function",
            "name": "multi_tool_execution_summary",
            "content": content
        }]