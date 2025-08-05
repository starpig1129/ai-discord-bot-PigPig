# -*- coding: utf-8 -*-
import io
import json
import logging
import base64
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
            一個包含格式化後工具執行報告的列表（role=function 的 message 陣列）。
        """
        tool_execution_report: List[Dict[str, Any]] = []

        for action in action_list:
            tool_name = action.get("tool_name")
            parameters = action.get("parameters", {})

            if not tool_name or tool_name == "directly_answer":
                continue

            try:
                tool = self.tool_registry.get_tool(tool_name)
                result = await tool.execute(context, **parameters)

                # 圖像工具標準化輸出：不得在此即時發送，統一回傳附件描述給上游整合
                if tool_name in ("gen_img", "generate_image"):
                    try:
                        standardized_output = self._standardize_image_tool_output(result)
                        if standardized_output is not None:
                            result = standardized_output
                    except Exception as std_err:
                        logging.error(f"標準化圖片工具輸出失敗: {std_err}", exc_info=True)

                report = self._create_structured_report(tool_name, "success", result)
                tool_execution_report.append(report)
                try:
                    context.logger.info(
                        "tool_exec_ok | tool=%s status=%s preview=%s",
                        tool_name, "success",
                        str(result)[:200]
                    )
                except Exception:
                    # 觀測性記錄不可影響主流程
                    pass

            except Exception as e:
                error_message = f"執行工具 '{tool_name}' 時發生錯誤: {str(e)}"
                context.logger.error(f"執行工具 '{tool_name}' 時發生錯誤: {e}", exc_info=True)
                error_report = self._create_structured_report(
                    tool_name, "failure", error_message, error_type=type(e).__name__
                )
                # 為了上游行為一致性，仍採用快速失敗，但在返回前加入統一化格式的可觀測性
                try:
                    formatted = self._format_report_for_llm([error_report])
                    context.logger.info(
                        "tool_exec_fail_fast_return | tool=%s payload_name=%s content_preview=%s",
                        tool_name,
                        formatted[0].get("name"),
                        str(formatted[0].get("content", ""))[:200]
                    )
                except Exception:
                    pass
                return self._format_report_for_llm([error_report])

        formatted = self._format_report_for_llm(tool_execution_report)
        try:
            # 統一在正常返回前記錄格式化後的結構，降低上游解析差異風險
            name_preview = formatted[0]["name"] if formatted else ""
            content_preview = formatted[0]["content"][:200] if formatted else ""
            context.logger.info(
                "tool_exec_return | count=%d payload_name=%s content_preview=%s",
                len(formatted), name_preview, content_preview
            )
        except Exception:
            pass
        return formatted

    def _create_structured_report(self, tool_name: str, status: str, result: Any, error_type: Optional[str] = None) -> Dict[str, Any]:
        """
        創建一個結構化的工具執行報告。
        支援附件描述（attachments）以利上游在同一則訊息合併發送。
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
                        logging.warning(f"轉換 discord.File 失敗，將回退文字-only: {e}")

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
            logging.error(f"標準化圖片工具輸出時發生錯誤: {e}", exc_info=True)
            return None

    def _format_report_for_llm(self, report_data: List[Dict]) -> List[Dict]:
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
            norm = {
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