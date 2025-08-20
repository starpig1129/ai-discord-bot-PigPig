# MIT License
# Copyright (c) 2024 starpig1129

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import json
import logging
import asyncio
import os
import re
import discord
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union, Literal

from gpt.core.response_generator import generate_response
from gpt.core.message_sender import (
    gpt_message,
    build_intelligent_context,
    search_relevant_memory,
    format_intelligent_context,
    format_memory_context_structured
)
from gpt.tools.registry import tool_registry
from gpt.tools.tool_context import ToolExecutionContext
from gpt.utils.media import process_attachment_data
from gpt.core.tool_executor import AsyncToolScheduler

# 新增：嚴格工具 JSON 解析與驗證的 feature flag（可由環境變數覆寫）
ENABLE_STRICT_TOOL_JSON: bool = os.getenv("ENABLE_STRICT_TOOL_JSON", "true").lower() in {"1", "true", "yes", "on"}

# 新增：導入 schemas 與 sanitizer（縮小 try/except 範圍並加強可觀測性）
from gpt.utils.sanitizer import mask_text, mask_json

schemas_import_failed: bool = False
try:
    # 僅嘗試匯入嚴格模型，避免過度捕捉
    from gpt.core.schemas import ToolCall, ToolSelection, PydanticValidationError  # type: ignore
except Exception as _schemas_exc:  # 精準記錄匯入失敗
    ToolCall = None  # type: ignore
    ToolSelection = None  # type: ignore
    try:
        from pydantic import ValidationError as PydanticValidationError  # type: ignore
    except Exception:
        # 極端情況：pydantic 也不可用，回退為通用 Exception
        class PydanticValidationError(Exception):  # type: ignore
            pass
    # 打點匯入失敗，包含 pydantic 版本與遮罩後的 traceback 簡述
    import pydantic
    import traceback
    logger = logging.getLogger(__name__)
    tb_summary = ''.join(traceback.format_exception_only(type(_schemas_exc), _schemas_exc)).strip()
    logger.warning(
        "schemas_import_error | pydantic_version=%s detail=%s",
        mask_text(getattr(pydantic, '__version__', 'unknown')),
        mask_text(tb_summary),
    )
    schemas_import_failed = True


class ActionDispatcher:
    """處理 Discord 機器人動作和工具執行。"""

    @staticmethod
    def _lenient_parse_tool_calls(payload: Optional[Union[dict, list]]) -> List[Dict[str, Any]]:
        """寬鬆解析：從 payload 提取 list[{'tool_name': str, 'parameters': dict}]。"""
        results: List[Dict[str, Any]] = []
        if payload is None:
            return results
        # 標準化為列表
        items: List[Any]
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            # 支援 {'tools': [...]}
            tools = payload.get("tools")
            items = tools if isinstance(tools, list) else [payload]
        else:
            return results

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            name = item.get("tool_name") or item.get("name")
            params = item.get("parameters") or item.get("args") or item.get("arguments")
            if isinstance(name, str):
                name = name.strip()
            if not name:
                continue
            if not isinstance(params, dict):
                continue
            results.append({"tool_name": name, "parameters": params})
        return results

    def __init__(self, bot):
        self.bot = bot
        self.tool_registry = tool_registry
        self._tool_routing_rules = [
            (re.compile(r"(算一下|計算|算|\+)"), [{"tool_name": "math", "parameters": {"expression": None}}]),
            (re.compile(r"(天氣|氣溫|下雨)"), [{"tool_name": "internet_search", "parameters": {"query": None}}]),
            (re.compile(r"(提醒我|設定提醒)"), [{"tool_name": "reminder", "parameters": {"time": None, "thing_to_remind": None}}]),
        ]

    def _rule_based_router(self, prompt: str) -> Optional[List[Dict]]:
        """
        基於規則的輕量級工具路由。
        如果匹配成功，返回工具列表；否則返回 None。
        """
        for pattern, tool_config in self._tool_routing_rules:
            match = pattern.search(prompt)
            if match:
                # 簡單提取參數的邏輯，這裡可以根據需要擴展
                action_list = []
                for tool in tool_config:
                    # 複製一份，避免修改原始設定
                    action = tool.copy()
                    action["parameters"] = action["parameters"].copy()
                    
                    # 嘗試填充參數，如果沒有特定邏輯，就將整個 prompt 作為主要參數
                    if "expression" in action["parameters"]:
                        action["parameters"]["expression"] = prompt
                    elif "query" in action["parameters"]:
                        action["parameters"]["query"] = prompt
                    elif "thing_to_remind" in action["parameters"]:
                         action["parameters"]["thing_to_remind"] = prompt

                    action_list.append(action)
                logging.info(f"規則路由匹配成功: {pattern.pattern} -> {action_list}")
                return action_list
        return None

    async def choose_act(self, prompt: str, message: Any,
                        message_to_edit: Any) -> Any:
        prompt = f"time:[{datetime.now().isoformat(timespec='seconds')}]{prompt}"
        # 初始化變數
        history = []
        image_data = []
        
        # 處理當前訊息的附件
        if message.attachments:
            await message_to_edit.edit(content="我看看...")
            current_image_data = await process_attachment_data(message)
            if isinstance(current_image_data, list):
                image_data.extend(current_image_data)
            else:
                prompt += f"\n{current_image_data}"
        
        # 讀取歷史訊息
        async for msg in message.channel.history(limit=10):
            if msg.id != message.id:
                history.append(msg)
                if msg.attachments:
                    msg_image_data = await process_attachment_data(msg)
                    if isinstance(msg_image_data, list):
                        image_data.extend(msg_image_data)
                    else:
                        prompt += f"\n{msg_image_data}"
        
        history.reverse()
        history = history[:-2]  # 移除當前訊息與第一個使用者訊息(會由其他地方加入)
        history_dict = [{
            "role": "user" if msg.author != message.guild.me else "assistant",
            "content": f"[{msg.author.display_name}<@{msg.author.id}>]: {msg.content}"
        } for msg in history]

        user_id = str(message.author.id)
        # 智慧上下文與記憶搜尋
        intelligent_context_task = asyncio.create_task(
            build_intelligent_context(prompt, history_dict, user_id)
        )
        memory_search_task = asyncio.create_task(
            search_relevant_memory(self.bot, message.channel.id, prompt)
        )

        intelligent_context = await intelligent_context_task
        memory_context = await memory_search_task

        enhanced_history = []
        if memory_context:
            formatted_memory = format_memory_context_structured(memory_context)
            if formatted_memory:
                enhanced_history.append(formatted_memory)

        if intelligent_context:
            formatted_context = format_intelligent_context(intelligent_context)
            if formatted_context:
                enhanced_history.append(formatted_context)
        
        final_dialogue_history = enhanced_history + history_dict
        
        action_list = await self._get_action_list(prompt, final_dialogue_history, image_data)

        logger = self.bot.get_logger_for_guild(message.guild.name)
        logger.info(f"準備執行的動作: {action_list}")

        context = ToolExecutionContext(
            bot=self.bot,
            message=message,
            message_to_edit=message_to_edit,
            logger=logger
        )

        # 執行工具並獲取結果（並行）
        scheduler = AsyncToolScheduler(self.bot)
        tool_results = await scheduler.schedule_tools(action_list, context)

        # 統一處理工具執行結果，無論成功或失敗
        async def execute_action(message_to_edit: Any, original_prompt: str, message: Any):
            # 格式化工具執行結果以供 LLM 理解
            if tool_results:
                formatted_summary = self._format_tool_results_summary(tool_results)
                logger.info(f"格式化後的工具執行摘要: {formatted_summary}") # 新增日誌
                # 將工具結果加入歷史紀錄
                final_dialogue_history.append(formatted_summary)

            # 生成最終回應
            gpt_response = await gpt_message(message_to_edit, message, original_prompt, final_dialogue_history, image_data)
            logger.info(f'PigPig 回應: {gpt_response}')
            return gpt_response

        return execute_action

    async def _get_action_list(self, prompt: str, history_dict: List[Dict],
                             image_data: List) -> List[Dict]:
        """從 LLM 或規則路由產出 action_list。

        嚴格模式下導入：
        - 受控 JSON 擷取（優先 fenced code block，再回退啟發式）
        - Pydantic schema 驗證
        - 可觀測性與遮罩
        - 失敗時區分 fallback 決策，不以空值掩蓋
        """
        # 1. 規則路由
        routed_action = self._rule_based_router(prompt)
        if routed_action:
            return routed_action

        # 2. 呼叫 LLM
        try:
            tools_string = self.tool_registry.get_tools_string_for_prompt()
            instruction_prompt = """
### Instructions for Tool Usage
You are a multi-functional Discord bot assistant capable of analyzing user requests, selecting the most suitable tool(s) from a predefined set,
and providing helpful responses. Below is a list of the available tools and how to use them effectively.
You are an expert at choosing the correct tool for a user's request.
You must respond in a JSON array of objects, where each object represents a tool call.
The JSON must be an array, even if there is only one tool call.
### Example Tool Use Syntax
```json
[
    {
        "tool_name": "tool name",
        "parameters": { "parameter_name_1": "value", "parameter_name_2": "value" }
    }
]
```
Based on the user's request and the available tools, select the appropriate tool(s)."""
            full_system_prompt = f"{instruction_prompt}\n\n# Available Tools:\n{tools_string}"

            logger = logging.getLogger(__name__)
            trace_id = f"ad-{int(datetime.now().timestamp()*1000)}"
            model = "unknown"
            provider = "unknown"

            # 標記開始
            logger.info(
                "llm_tool_select_start | model=%s provider=%s trace_id=%s",
                mask_text(model), mask_text(provider), mask_text(trace_id)
            )

            thread, gen = await generate_response(
                inst=prompt,
                system_prompt=full_system_prompt,
                dialogue_history=history_dict,
                image_input=image_data
            )
            responses: List[str] = []
            async for chunk in gen:
                responses.append(chunk)
            full_response = ''.join(responses)

            if not ENABLE_STRICT_TOOL_JSON:
                # 舊行為：寬鬆擷取 + 直接 json.loads
                try:
                    json_string = self._extract_json_from_response_legacy(full_response)
                    if json_string:
                        parsed = json.loads(json_string)
                        logger.info("json_parse_ok | parsed_from=legacy span_preview=%s",
                                    mask_text(json_string))
                        if isinstance(parsed, list):
                            return parsed
                        if isinstance(parsed, dict) and "tools" in parsed:
                            return parsed.get("tools", [])
                    # 失敗即回退既有預設
                    logger.warning("json_parse_fail | reason=%s span_preview=%s",
                                   mask_text("legacy_extract_empty"), mask_text(full_response))
                    return self._get_default_action_list(prompt)
                except Exception as e:
                    logger.error("json_parse_fail | reason=%s span_preview=%s",
                                 mask_text(str(e)), mask_text(full_response))
                    return self._get_default_action_list(prompt)

            # 嚴格模式：受控擷取與驗證
            payload, parsed_from, masked_span = self._extract_json_from_response(full_response)
            if payload is None:
                # 擷取失敗 → fallback 決策
                logger.warning("json_parse_fail | reason=%s span_preview=%s",
                               mask_text("extract_none"), mask_text(masked_span))
                decision = self._decide_fallback(None, "extract_none")
                logger.info("fallback_default_action | decision=%s reason=%s",
                            decision, mask_text("extract_none"))
                return self._fallback_action_list(decision)

            logger.info("json_parse_ok | parsed_from=%s span_preview=%s",
                        parsed_from, mask_text(masked_span))

            try:
                selection = self._validate_tool_selection(payload, model, provider, trace_id)
                tools_count = len(selection.tool_calls)
                logger.info("llm_tool_select_ok | tools_count=%d", tools_count)
                # 嚴格通過 → 映射回舊介面
                normalized: List[Dict[str, Any]] = []
                for call in selection.tool_calls:
                    normalized.append({"tool_name": call.name, "parameters": call.arguments})
                return normalized
            except PydanticValidationError as ve:
                # 嚴格驗證失敗 → 記錄並嘗試寬鬆解析
                logger.warning("llm_tool_select_strict_fail | reason=%s", mask_text(str(ve)))
                lenient = ActionDispatcher._lenient_parse_tool_calls(payload)
                if lenient:
                    logger.info("llm_tool_select_lenient_ok | tools_count=%d", len(lenient))
                    return lenient
                logger.warning("llm_tool_select_lenient_empty")
                decision = self._decide_fallback(payload, "schema_validation_error")
                logger.info("fallback_default_action | decision=%s reason=%s",
                            decision, mask_text("schema_validation_error"))
                return self._fallback_action_list(decision)
            except ValueError as ve:
                # 嚴格前置正規化失敗 → 記錄並嘗試寬鬆解析
                logger.warning("llm_tool_select_strict_fail | reason=%s", mask_text(str(ve)))
                lenient = ActionDispatcher._lenient_parse_tool_calls(payload)
                if lenient:
                    logger.info("llm_tool_select_lenient_ok | tools_count=%d", len(lenient))
                    return lenient
                logger.warning("llm_tool_select_lenient_empty")
                decision = self._decide_fallback(payload, "normalize_error")
                logger.info("fallback_default_action | decision=%s reason=%s",
                            decision, mask_text("normalize_error"))
                return self._fallback_action_list(decision)

        except Exception as e:
            logging.error("Action list error: %s", str(e), exc_info=True)
            return self._get_default_action_list(prompt)

    @staticmethod
    def _extract_json_from_response_legacy(response: str) -> str:
        """舊版簡單擷取，保留以利 feature flag 回退。"""
        json_start = response.find("[")
        json_end = response.rfind("]") + 1
        return (response[json_start:json_end] if json_start != -1 and json_end != -1 else "")

    @staticmethod
    def _extract_json_from_response(response_text: str) -> Tuple[Optional[Union[dict, list]], str, str]:
        """受控擷取 JSON：優先 ```json 圍欄，其次括號配對啟發式。

        Returns:
            (payload, parsed_from, masked_raw_span)
            失敗時返回 (None, "none", masked_span)
        """
        preview = mask_text(response_text)
        # 優先尋找 fenced code block ```json ... ```
        fenced_matches = list(re.finditer(r"```(?:json)?\s*(.*?)```", response_text, flags=re.DOTALL | re.IGNORECASE))
        for m in fenced_matches:
            block = m.group(1).strip()
            try:
                return json.loads(block), "fenced_code", mask_text(block)
            except Exception:
                pass

        # 其次：嘗試用方括號界定的最長匹配
        l_idx = response_text.find("[")
        r_idx = response_text.rfind("]")
        if l_idx != -1 and r_idx != -1 and r_idx > l_idx:
            span = response_text[l_idx:r_idx + 1]
            try:
                return json.loads(span), "json_block", mask_text(span)
            except Exception:
                # 繼續嘗試大括號（支援 {"tools":[...]} 外層）
                pass

        l_idx = response_text.find("{")
        r_idx = response_text.rfind("}")
        if l_idx != -1 and r_idx != -1 and r_idx > l_idx:
            span = response_text[l_idx:r_idx + 1]
            try:
                return json.loads(span), "json_block", mask_text(span)
            except Exception:
                return (None, "none", mask_text(span))

        return (None, "none", preview)

    @staticmethod
    def _normalize_payload_to_list(payload: Union[dict, list]) -> List[dict]:
        """正規化 payload 至 list[dict]。支援 {'tools':[...]} 或直接 list。"""
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            tools = payload.get("tools")
            if isinstance(tools, list):
                return tools
        raise ValueError("payload must be a list of tools or a dict with 'tools' list")

    @staticmethod
    def _validate_tool_selection(payload: Union[dict, list], model: str, provider: str, trace_id: str):
        """使用 Pydantic 嚴格驗證工具選擇結構。"""
        if ToolSelection is None:
            # 嚴格模型不可用也視為嚴格失敗，交由上層走寬鬆解析
            raise ValueError("ToolSelection model not available")

        items = ActionDispatcher._normalize_payload_to_list(payload)
        tool_calls = []
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"tool item at index {idx} is not an object")
            tool_name = item.get("tool_name")
            parameters = item.get("parameters")
            if tool_name is None or not isinstance(tool_name, str) or not tool_name.strip():
                raise ValueError(f"invalid or missing 'tool_name' at index {idx}")
            if not isinstance(parameters, dict):
                raise ValueError(f"'parameters' must be a dict at index {idx}")

            # 建立 ToolCall
            tool_calls.append(
                ToolCall(
                    id=f"{trace_id}-{idx}",
                    name=tool_name.strip(),
                    arguments=parameters,
                    confidence=None,
                    rationale=None,
                    raw_text_span=None,
                    selection_index=idx,
                )
            )

        selection = ToolSelection(
            model=model,
            provider=provider,
            tool_calls=tool_calls,
            selection_strategy="greedy",
            parsed_from="json_block",  # 以保守值標記；實際來源已於 log 內呈現
            parse_confidence=0.5,
            trace_id=trace_id,
        )
        return selection

    @staticmethod
    def _decide_fallback(parsed_json: Optional[Union[dict, list]], failure_reason: str) -> Literal["no_tool_safe_answer", "directly_answer"]:
        """保守決策：預設 no_tool_safe_answer；未引入語義判斷以避免誤答。"""
        # TODO: 未來可根據 LLM 回覆語義、用戶意圖與安全規則來動態調整
        return "no_tool_safe_answer"

    @staticmethod
    def _fallback_action_list(decision: Literal["no_tool_safe_answer", "directly_answer"]) -> List[Dict[str, Any]]:
        """將 fallback 決策映射為與 ToolExecutor 相容的 action_list。"""
        if decision == "directly_answer":
            return [{"tool_name": "directly_answer", "parameters": {}}]
        # no_tool_safe_answer：避免直接回答，由上游路徑處理
        return [{"tool_name": "directly_answer", "parameters": {"no_tool_safe_answer": True}}]

    def _format_tool_results_summary(self, tool_results: List[Dict]) -> Dict[str, Any]:
        """
        將工具執行結果格式化為易於 LLM 理解的 Markdown 摘要。
        嚴格解析與保護：任何單筆解析失敗都僅標示該筆為「解析失敗」，不覆蓋其他成功結果。
        """
        success_reports: List[str] = []
        failure_reports: List[str] = []

        for idx, result in enumerate(tool_results):
            raw_content = result.get("content", "")
            raw_name = result.get("name", "")
            try:
                content_data = json.loads(raw_content) if isinstance(raw_content, str) and raw_content else []
                # 正規化為 list[dict]
                reports = content_data if isinstance(content_data, list) else [content_data]
                normalized_reports: List[Dict[str, Any]] = []
                for rep in reports:
                    if not isinstance(rep, dict):
                        continue
                    tool_name = rep.get("tool_name", raw_name or "unknown_tool")
                    status = rep.get("status", "failure")
                    output = rep.get("output", None)

                    if status == "success":
                        preview = str(output)[:200]
                        success_reports.append(f"- `{tool_name}`: {preview}")
                    else:
                        # 失敗結構標準化
                        err_msg = ""
                        if isinstance(output, dict):
                            err_msg = str(output.get("error_message", "未知錯誤"))
                        else:
                            err_msg = "未知錯誤"
                        failure_reports.append(f"- `{tool_name}`: 錯誤 - `{err_msg}`")
                # 觀測性：記錄每則工具結果的摘要
                logging.info(
                    "tool_summary_item | idx=%d name=%s parsed=%s",
                    idx, raw_name, "ok"
                )
            except json.JSONDecodeError as e:
                logging.error("tool_summary_parse_error | idx=%d name=%s err=%s preview=%s",
                              idx, raw_name, str(e), str(raw_content)[:200])
                failure_reports.append(f"- `{raw_name or 'unknown_tool'}`: 解析結果時發生錯誤。")
            except Exception as e:
                logging.error("tool_summary_unexpected_error | idx=%d name=%s err=%s preview=%s",
                              idx, raw_name, str(e), str(raw_content)[:200])
                failure_reports.append(f"- `{raw_name or 'unknown_tool'}`: 解析結果處理時發生未知錯誤。")

        summary_parts: List[str] = ["### 工具執行摘要"]
        if success_reports:
            summary_parts.append("\n**✅ 成功執行的工具:**")
            summary_parts.extend(success_reports)

        if failure_reports:
            summary_parts.append("\n**❌ 失敗的工具:**")
            summary_parts.extend(failure_reports)

        final_summary = "\n".join(summary_parts)

        return {
            "role": "function",
            "name": "tool_execution_summary",
            "content": final_summary
        }

    @staticmethod
    def _get_default_action_list(prompt: str) -> List[Dict]:
        return [{"tool_name": "directly_answer", "parameters": {"prompt": prompt}}]
