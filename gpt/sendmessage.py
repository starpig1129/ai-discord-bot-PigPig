import os
import json
import faiss
from gpt.gpt_response_gen import generate_response
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
# 創建或加載 FAISS 索引
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
    vector_store.save(path)

def load_vector_store(path):
    if os.path.exists(path):
        vector_store.index = faiss.read_index(path)
        vector_store.index = faiss.index_cpu_to_all_gpus(vector_store.index)  # 使用 GPU 加速
    else:
        print("向量資料庫文件不存在，將創建新的資料庫")

def search_vector_database(query):
    try:
        results = vector_store.similarity_search(query, k=5)
        related_data = "\n".join([result.metadata['text'] for result in results])
        return related_data
    except:
        return ''

async def gpt_message(message_to_edit,message,prompt):
    
    channel = message.channel
        
    # 從向量資料庫尋找相關資料
    related_data = search_vector_database(prompt)  # 使用 LangChain 搜尋相關資料
    # 讀取該訊息頻道最近的歷史紀錄
    history = []
    async for msg in channel.history(limit=10):
        history.append(msg)
    history.reverse()
    history = history[:-2]
    history_dict = [{"role": "user" if msg.author != message.guild.me else "assistant", "content": msg.content} for msg in history]
    # 組合資料
    combined_prompt = f"Information:<<{related_data}>>User: {prompt}"
    try:
        responses = ""
        thread,streamer = await generate_response(combined_prompt, system_prompt,history_dict)
        buffer_size = 40  # 设置缓冲区大小
        responsesall = ""
        for response in streamer:
            print(response, end="", flush=True)
            responses += response

            if len(responses) >= buffer_size:
                responsesall+=responses
                await message_to_edit.edit(content=responsesall)  # 修改消息内容
                responses = ""  # 清空 responses 变量
        print("結束")
        # 处理剩余的文本
        responsesall+=responses
        responsesall = responsesall.replace('<|eot_id|>',"")
        await message_to_edit.edit(content=responsesall)  # 修改消息内容
        thread.join()
        return responsesall
    except Exception as e:
        print(e)
# 在模塊加載時索引對話歷史並載入向量資料庫
load_vector_store('./data/vector_store')
load_and_index_dialogue_history('./data/dialogue_history.json')