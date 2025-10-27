# -*- coding: utf-8 -*-
import io
import json
import asyncio
import logging
import base64
from typing import Any, Dict, List, Optional, Union
from function import func
import asyncio

from gpt.tools.registry import tool_registry
from gpt.tools.tool_context import ToolExecutionContext


class ToolExecutor:
    """
    單一工具執行器：僅負責「執行單一工具」並產出結構化報告。
    並行與排程交由 AsyncToolScheduler 處理。
    """

    def __init__(self, bot):
        self.bot = bot
        self.tool_registry = tool_registry

    async def execute_tool(self, action: Dict[str, Any], context: ToolExecutionContext) -> Optional[Dict[str, Any]]:
        """
        執行單一工具並返回結構化報告(dict)。若 tool_name 無效或為 directly_answer，返回 None。

        Returns:
            - 成功或失敗的結構化報告 dict
            - None: 略過（例如 directly_answer）
        """
        tool_name: Optional[str] = action.get("tool_name")
        parameters: Dict[str, Any] = action.get("parameters", {}) or {}

        # 跳過「不需呼叫實際工具」的動作
        if not tool_name or tool_name == "directly_answer":
            return None

        try:
            tool = self.tool_registry.get_tool(tool_name)
            result = await tool.execute(context, **parameters)

            # 圖像工具輸出標準化（若可標準化則覆蓋）
            if tool_name in ("gen_img", "generate_image"):
                try:
                    standardized_output = self._standardize_image_tool_output(result)
                    if standardized_output is not None:
                        result = standardized_output
                except Exception as std_err:
                    await func.report_error(std_err, "image tool output standardization")

            report = self._create_structured_report(tool_name, "success", result)
            try:
                context.logger.info(
                    "tool_exec_ok | tool=%s status=%s preview=%s",
                    tool_name, "success",
                    str(result)[:200]
                )
            except Exception:
                pass
            return report

        except Exception as e:
            # 任何工具內部錯誤 → 轉為一致的 failure 報告
            await func.report_error(e, f"tool execution: {tool_name}")
            error_message = f"執行工具 '{tool_name}' 時發生錯誤: {str(e)}"
            try:
                context.logger.error(f"執行工具 '{tool_name}' 時發生錯誤: {e}", exc_info=True)
            except Exception:
                logging.error(f"執行工具錯誤（無法使用 context.logger）: {e}", exc_info=True)
            return self._create_structured_report(
                tool_name or "unknown_tool", "failure", error_message, error_type=type(e).__name__
            )

    def _create_structured_report(self, tool_name: str, status: str, result: Any, error_type: Optional[str] = None) -> Dict[str, Any]:
        """
        創建一個結構化的工具執行報告。
        支援附件描述（attachments）以利上游在同一則訊息合併發送。
        """
        report: Dict[str, Any] = {
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

    def _standardize_image_tool_output(self, result: Any) -> Optional[Dict[str, Any]]:
        """
        將圖片工具的輸出統一為結構化資料：
        - 若為 BytesIO：轉 base64 並包裝到 attachments。
        - 若為 dict 且包含 file/attachments：轉為 attachments 標準格式。
        - 其他型別：返回 None 代表不改動。
        """
        try:
            # 1) BytesIO → base64 附件
            if isinstance(result, io.BytesIO):
                result.seek(0)
                b64 = base64.b64encode(result.read()).decode("utf-8")
                return {
                    "text": None,
                    "attachments": [
                        {
                            "type": "image",
                            "filename": "generated_image.png",
                            "mime_type": "image/png",
                            "data_base64": b64,
                            "caption": "這張圖給你參考:"
                        }
                    ]
                }

            # 2) dict with discord.File 或 bytes 或現成 attachments
            if isinstance(result, dict):
                text = result.get("content") or result.get("text") or None
                attachments: List[Dict[str, Any]] = []

                # 已有標準 attachments
                if isinstance(result.get("attachments"), list):
                    return {
                        "text": text,
                        "attachments": result.get("attachments")
                    }

                # file: discord.File → 不在此層處理 discord 型別，轉換為 base64 需原始位元資料
                file_obj = result.get("file")
                if hasattr(file_obj, "fp"):  # 可能是 discord.File 且內含 fp
                    try:
                        fp = getattr(file_obj, "fp", None)
                        filename = getattr(file_obj, "filename", "generated_image")
                        if fp:
                            if hasattr(fp, "seek"):
                                fp.seek(0)
                            data = fp.read()
                            b64 = base64.b64encode(data).decode("utf-8")
                            attachments.append({
                                "type": "image",
                                "filename": filename,
                                "mime_type": "image/png",
                                "data_base64": b64,
                                "caption": None
                            })
                    except Exception as e:
                        asyncio.create_task(func.report_error(e, "discord.File conversion"))

                # 原始 bytes
                raw_bytes = result.get("image_bytes")
                if isinstance(raw_bytes, (bytes, bytearray)):
                    b64 = base64.b64encode(bytes(raw_bytes)).decode("utf-8")
                    attachments.append({
                        "type": "image",
                        "filename": "generated_image.png",
                        "mime_type": "image/png",
                        "data_base64": b64,
                        "caption": None
                    })

                if attachments:
                    return {
                        "text": text,
                        "attachments": attachments
                    }
                # 若沒有可轉換的附件，維持原狀
                return {"text": text} if text is not None else None

            # 其他型別：不動
            return None
        except Exception as e:
            asyncio.create_task(func.report_error(e, "image tool output standardization"))
            return None

    def _format_report_for_llm(self, report_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        將結構化的報告格式化為 LLM 需要的最終格式。
        保證：
          - 單工具：content 是單一 dict 的 JSON 字串
          - 多工具：content 是 list[dict] 的 JSON 字串
        """
        if not report_data:
            return []

        # 清理並保證基本鍵存在，避免上游 NameError/KeyError
        normalized: List[Dict[str, Any]] = []
        for rpt in report_data:
            norm: Dict[str, Any] = {
                "tool_name": rpt.get("tool_name", "unknown_tool"),
                "status": rpt.get("status", "failure"),
            }
            if norm["status"] == "success":
                norm["output"] = rpt.get("output", None)
            else:
                out = rpt.get("output") or {}
                norm["output"] = {
                    "error_type": out.get("error_type", "UnknownError"),
                    "error_message": str(out.get("error_message", "未知錯誤")),
                }
            normalized.append(norm)

        if len(normalized) == 1:
            report = normalized[0]
            content = json.dumps(report, ensure_ascii=False, indent=2)
            return [{
                "role": "function",
                "name": report.get("tool_name", "unknown_tool"),
                "content": content
            }]

        content = json.dumps(normalized, ensure_ascii=False, indent=2)
        return [{
            "role": "function",
            "name": "multi_tool_execution_summary",
            "content": content
        }]


class AsyncToolScheduler:
    """
    非同步工具排程器：負責並行執行多個工具呼叫，彙整並回傳 LLM 友善格式。
    - 使用 asyncio.gather 並行執行
    - 保持輸出與舊版 ToolExecutor.execute_tools 一致（role=function 的訊息列表）
    """

    def __init__(self, bot):
        self.bot = bot
        self.executor = ToolExecutor(bot)

    async def schedule_tools(self, action_list: List[Dict[str, Any]], context: ToolExecutionContext) -> List[Dict[str, Any]]:
        """
        並行執行 action_list 內的工具，並回傳已格式化給 LLM 的訊息列表。
        """
        # 建立要執行的 action 清單（過濾無效與 directly_answer）
        runnable_actions: List[Dict[str, Any]] = []
        for action in action_list or []:
            name = action.get("tool_name")
            if not name or name == "directly_answer":
                continue
            runnable_actions.append(action)

        if not runnable_actions:
            return []

        async def _run(action: Dict[str, Any]) -> Union[Dict[str, Any], Exception, None]:
            try:
                return await self.executor.execute_tool(action, context)
            except Exception as e:
                # 確保 gather 不會中止：返回例外以供後續統一處理
                await func.report_error(e, f"tool execution in scheduler: {action.get('tool_name')}")
                return e

        tasks = [asyncio.create_task(_run(a)) for a in runnable_actions]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        structured_reports: List[Dict[str, Any]] = []
        for idx, res in enumerate(results):
            if isinstance(res, Exception):
                # 理論上不會出現（因 _run 已捕捉），此處保底
                try:
                    tool_name = runnable_actions[idx].get("tool_name", "unknown_tool")
                except Exception:
                    tool_name = "unknown_tool"
                structured_reports.append(
                    self.executor._create_structured_report(
                        tool_name, "failure",
                        f"執行工具時發生未預期錯誤: {str(res)}",
                        error_type=type(res).__name__
                    )
                )
            elif res is None:
                # 略過（例如 directly_answer 或無效）
                continue
            else:
                structured_reports.append(res)

        formatted = self.executor._format_report_for_llm(structured_reports)
        try:
            name_preview = formatted[0]["name"] if formatted else ""
            content_preview = formatted[0]["content"][:200] if formatted else ""
            context.logger.info(
                "tool_schedule_return | count=%d payload_name=%s content_preview=%s",
                len(formatted), name_preview, content_preview
            )
        except Exception:
            pass
        return formatted