import os
import json
import faiss
import logging
import discord
from gpt.gpt_response_gen import generate_response
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.docstore.in_memory import InMemoryDocstore
import requests
import logging
from anthropic import Anthropic, AsyncAnthropic, HUMAN_PROMPT, AI_PROMPT
# 初始化 Anthropic 客戶端
anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
async_anthropic = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

system_prompt='''
                You(assistant) are a helpful, 
                respectful and honest AI chatbot named 🐖🐖. 
                You are talking in a funny way to a human(user).
                If you don't know the answer to a question, don't share false information.
                Use the information provided to answer the questions in <<>>.
                You are made by 星豬<@597028717948043274>
                Always answer in Traditional Chinese.
                '''
# 初始化 Hugging Face 嵌入模型
hf_embeddings_model = "sentence-transformers/all-MiniLM-L6-v2"
embeddings = HuggingFaceEmbeddings(model_name=hf_embeddings_model)

# 創建或載入 FAISS 索引
def create_faiss_index():
    embedding_size = 384
    index = faiss.IndexFlatL2(embedding_size)
    docstore = InMemoryDocstore({})
    index_to_docstore_id = {}
    return FAISS(embeddings, index, docstore, index_to_docstore_id)

vector_store = create_faiss_index()

def load_and_index_dialogue_history(dialogue_history_file):
    if not os.path.exists(dialogue_history_file):
        return

    with open(dialogue_history_file, 'r', encoding='utf-8') as file:
        dialogue_history = json.load(file)

    for channel_id, messages in dialogue_history.items():
        texts = [msg["content"] for msg in messages if msg["role"] == "user"]
        metadatas = [{"text": text} for text in texts]
        vector_store.add_texts(texts, metadatas)

def save_vector_store(vector_store, path):
    try:
        faiss.write_index(vector_store.index, path)
        logging.info(f"FAISS 索引已保存到 {path}")
    except Exception as e:
        logging.error(f"保存 FAISS 索引時發生錯誤: {e}")
        raise

def load_vector_store(path):
    if os.path.exists(path):
        vector_store.index = faiss.read_index(path)
        logging.info("FAISS 索引成功載入")
    else:
        logging.info("向量資料庫文件不存在，將創建新的資料庫")

def search_vector_database(query):
    try:
        results = vector_store.similarity_search(query, k=5)
        related_data = "\n".join([result.metadata['text'] for result in results])
        return related_data
    except:
        return ''

def to_gpu(index):
    return faiss.index_cpu_to_all_gpus(index)

def to_cpu(index):
    return faiss.index_gpu_to_cpu(index)

# 檢查 Claude API 的額度
def check_claude_api_quota():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logging.warning("找不到 Anthropic API 金鑰")
        return None
    
    try:
        # 發送請求到 Anthropic 的額度檢查端點
        response = requests.get(
            "https://api.anthropic.com/v1/quota",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        response.raise_for_status()
        quota_info = response.json()
        
        # 返回剩餘額度信息
        return quota_info.get("remaining_quota")
    except Exception as e:
        logging.error(f"檢查 Claude API 額度時發生錯誤: {e}")
        return None

# 使用 Claude API 生成流式回應
async def generate_claude_stream_response(prompt, history, message_to_edit, channel):
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

async def gpt_message(message_to_edit, message, prompt):
    channel = message.channel
    
    # 從向量資料庫尋找相關資料
    related_data = search_vector_database(prompt)
    
    # 讀取該訊息頻道最近的歷史紀錄
    history = []
    async for msg in channel.history(limit=5):
        history.append(msg)
    history.reverse()
    history = history[:-2]
    history_dict = [{"role": "user" if msg.author != message.guild.me else "assistant", "content": msg.content} for msg in history]
    
    # 組合資料
    combined_prompt = f"information:<<{related_data}>>user: {prompt}"
    
    try:
        # 嘗試使用 Claude API
        try:
            claude_response = await generate_claude_stream_response(combined_prompt, history_dict, message_to_edit, channel)
            return claude_response
        except Exception as e:
            logging.error(f"Claude API 錯誤: {e}")
            logging.warning("無法使用 Claude API，切換到原有的回應邏輯")
            
        # 如果 Claude API 失敗，使用原有的回應邏輯
        responses = ""
        responsesall = ""
        message_result = ""
        thread, streamer = await generate_response(combined_prompt, system_prompt, history_dict)
        buffer_size = 40  # 設置緩衝區大小
        current_message = message_to_edit
        
        for response in streamer:
            print(response, end="", flush=True)
            responses += response
            message_result += response
            if len(responses) >= buffer_size:
                # 檢查是否超過 2000 字符
                if len(responsesall+responses) > 1900:
                    # 創建新消息
                    current_message = await channel.send("繼續輸出中...")
                    responsesall = ""
                responsesall += responses
                
                await current_message.edit(content=responsesall)
                responses = ""  # 清空 responses 變數
        
        # 處理剩餘的文本
        responsesall = responsesall.replace('<|eot_id|>', "")
        if len(responsesall+responses) > 1900:
            current_message = await channel.send(responses)
        else:
            await current_message.edit(content=responsesall+responses)
        thread.join()
        return message_result
    except Exception as e:
        logging.error(f"生成回應時發生錯誤: {e}")
        await message_to_edit.edit(content="抱歉，我不會講話了。")
        return None
# 在模塊加載時索引對話歷史並載入向量資料庫
load_vector_store('./data/vector_store')
load_and_index_dialogue_history('./data/dialogue_history.json')