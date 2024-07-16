from anthropic import Anthropic, AsyncAnthropic, HUMAN_PROMPT, AI_PROMPT
import requests
import logging
import os
# 初始化 Anthropic 客戶端
anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
async_anthropic = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
# 檢查 Claude API 的額度
def check_claude_api_quota():
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    if not ANTHROPIC_API_KEY:
        logging.warning("找不到 Anthropic API 金鑰")
        return None
    
    try:
        # 發送請求到 Anthropic 的額度檢查端點
        response = requests.get(
            "https://api.anthropic.com/v1/quota",
            headers={"Authorization": f"Bearer {ANTHROPIC_API_KEY}"}
        )
        response.raise_for_status()
        quota_info = response.json()
        
        # 返回剩餘額度信息
        return quota_info.get("remaining_quota")
    except Exception as e:
        logging.error(f"檢查 Claude API 額度時發生錯誤: {e}")
        return None
# 使用 Claude API 生成流式回應
async def generate_claude_stream_response(system_prompt,prompt, history, message_to_edit, channel):
    try:
        # 準備對話歷史
        messages = []
        for msg in history:
            role = HUMAN_PROMPT if msg["role"] == "user" else AI_PROMPT
            messages.append(f"{role} {msg['content']}")
        
        messages.append(f"{HUMAN_PROMPT}{system_prompt}{prompt}")
        full_prompt = "\n\n".join(messages)

        # 使用 Claude API 生成流式回應
        async with async_anthropic as client:
            response_stream = await client.completions.create(
                model="claude-3-5-sonnet-20240620",
                prompt=full_prompt,
                max_tokens_to_sample=1000,
                stream=True
            )

            full_response = ""
            current_message = message_to_edit
            buffer = ""
            message_result = ""
            buffer_size = 40  # 設置緩衝區大小

            async for completion in response_stream:
                if completion.stop_reason:
                    break
                chunk = completion.completion
                full_response += chunk
                buffer += chunk
                message_result += chunk
                if len(buffer) >= buffer_size:
                    # 檢查是否超過 1900 字符
                    if len(full_response+buffer)> 1900:
                        # 創建新消息
                        current_message = await channel.send("繼續輸出中...")
                        full_response = ""
                    await current_message.edit(content=full_response + buffer)
                    buffer = ""  # 清空緩衝區

            # 處理剩餘的文本
            if buffer:
                if len(full_response+buffer)> 1900:
                    current_message = await channel.send(buffer)
                else:
                    await current_message.edit(content=full_response + buffer)
        return message_result
    except Exception as e:
        logging.error(f"使用 Claude API 生成回應時發生錯誤: {e}")
        raise e