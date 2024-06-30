from transformers import AutoTokenizer, AutoModelForCausalLM,BitsAndBytesConfig,TextIteratorStreamer
from threading import Thread
import torch
from dotenv import load_dotenv
import os

load_dotenv()  # 加載 .env 文件中的環境變量

model_name = os.getenv("LLM_MODEL_NAME")
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype="float16",
    bnb_4bit_use_double_quant=False
)
# 加載分詞器
tokenizer = AutoTokenizer.from_pretrained(
    model_name, 
    use_fast=False,
    trust_remote_code=True
)
model = AutoModelForCausalLM.from_pretrained(
        model_name, 
        torch_dtype=torch.float16,
        quantization_config=bnb_config,
        device_map={"":0},
        attn_implementation='sdpa',
        trust_remote_code=True,
    )
model.config.use_cache = False  # 禁用cache以節省記憶體
model.bfloat16()
model.eval()


async def generate_response(inst, system_prompt,dialogue_history=None):
    # 增加系統提示與用戶指令到對話模板
    messages = [{'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': inst}]
    if dialogue_history is not None:
        messages = [{'role': 'system', 'content': system_prompt}]+dialogue_history+[{'role': 'user', 'content': inst}]    
    #print(messages)    
    streamer = TextIteratorStreamer(tokenizer,skip_prompt=True)
    input_ids = tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt").to(model.device)

    attention_mask = (input_ids != tokenizer.pad_token_id).long()

    generation_kwargs = dict(
        inputs=input_ids,
        attention_mask=attention_mask,
        pad_token_id=tokenizer.pad_token_id,
        streamer=streamer,
        max_new_tokens=8192,
        do_sample=True,
        temperature=0.5,
        top_p=0.9,
    )
    
    thread = Thread(target=model.generate, kwargs=generation_kwargs)
    thread.start()  # 启动线程
    return thread,streamer