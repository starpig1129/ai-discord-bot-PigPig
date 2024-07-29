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
import os
import json
import faiss
import logging
import discord
from gpt.gpt_response_gen import generate_response
from gpt.claude_response import generate_claude_stream_response
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.docstore.in_memory import InMemoryDocstore
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

# 創建一個字典來存儲每個頻道的向量存儲
vector_stores = {}

def create_faiss_index():
    embedding_size = 384
    index = faiss.IndexFlatL2(embedding_size)
    docstore = InMemoryDocstore({})
    index_to_docstore_id = {}
    return FAISS(embeddings, index, docstore, index_to_docstore_id)

def load_and_index_dialogue_history(dialogue_history_file):
    if not os.path.exists(dialogue_history_file):
        return

    with open(dialogue_history_file, 'r', encoding='utf-8') as file:
        dialogue_history = json.load(file)

    for channel_id, messages in dialogue_history.items():
        if channel_id not in vector_stores:
            vector_stores[channel_id] = create_faiss_index()
        texts = [msg["content"] for msg in messages if msg["role"] == "user"]
        metadatas = [{"text": text} for text in texts]
        vector_stores[channel_id].add_texts(texts, metadatas)

def save_vector_store(stores, path):
    try:
        for channel_id, store in stores.items():
            channel_path = f"{path}_{channel_id}"
            faiss.write_index(store.index, channel_path)
        logging.info(f"FAISS 索引已保存到 {path}")
    except Exception as e:
        logging.error(f"保存 FAISS 索引時發生錯誤: {e}")
        raise

def load_vector_store(path):
    global vector_stores
    vector_stores = {}
    base_dir = os.path.dirname(path)
    base_name = os.path.basename(path)
    for file in os.listdir(base_dir):
        if file.startswith(base_name):
            channel_id = file.split('_')[-1]
            full_path = os.path.join(base_dir, file)
            vector_stores[channel_id] = create_faiss_index()
            vector_stores[channel_id].index = faiss.read_index(full_path)
            logging.info(f"FAISS 索引成功載入: {channel_id}")

def search_vector_database(query, channel_id):
    try:
        if channel_id not in vector_stores:
            return ''
        results = vector_stores[channel_id].similarity_search(query, k=5)
        related_data = [result.metadata['text'] for result in results]
        
        # 格式化相關資訊
        formatted_data = "Database:\n"
        for i, data in enumerate(related_data, 1):
            formatted_data += f"{i}. <{data}>\n"
        
        return formatted_data.strip()  # 移除最後的換行符
    except Exception as e:
        logging.error(f"Error in search_vector_database: {e}")
        return ''

def to_gpu(index):
    return faiss.index_cpu_to_all_gpus(index)

def to_cpu(index):
    return faiss.index_gpu_to_cpu(index)

async def gpt_message(message_to_edit, message, prompt):
    channel = message.channel
    channel_id = str(channel.id)
    
    # 從向量資料庫尋找相關資料
    related_data = search_vector_database(prompt, channel_id)
    print(related_data)
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
            claude_response = await generate_claude_stream_response(system_prompt,combined_prompt, history_dict, message_to_edit, channel)
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
                    responsesall = responsesall.replace('<|eot_id|>', "")
                    await current_message.edit(content=responsesall)
                    responses = ""  # 清空 responses 變數
            
            # 處理剩餘的文本
            responsesall = responsesall.replace('<|eot_id|>', "")
            if len(responsesall+responses) > 1900:
                current_message = await channel.send(responses)
            else:
                responsesall+=responses
                responsesall = responsesall.replace('<|eot_id|>', "")
                await current_message.edit(content=responsesall)
            thread.join()
            return message_result
    except Exception as e:
        logging.error(f"生成回應時發生錯誤: {e}")
        await message_to_edit.edit(content="抱歉，我不會講話了。")
        return None
# 在模塊加載時索引對話歷史並載入向量資料庫
load_vector_store('./data/vector_store')
load_and_index_dialogue_history('./data/dialogue_history.json')

__all__ = ['gpt_message', 'load_and_index_dialogue_history', 'save_vector_store', 'vector_stores']