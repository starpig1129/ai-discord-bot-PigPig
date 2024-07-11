# test.py
import torch
import io
from PIL import Image
from transformers import AutoModel, AutoTokenizer
from gpt.gpt_response_gen import generate_response
import aiohttp
from dotenv import load_dotenv
import os

load_dotenv()  # 加載 .env 文件中的環境變量

global_VQA = None
global_VQAtokenizer = None

def get_VQA_and_tokenizer():
    global global_VQA, global_VQAtokenizer
    return global_VQA, global_VQAtokenizer

def set_VQA_and_tokenizer(model, tokenizer):
    global global_VQA, global_VQAtokenizer
    global_VQA = model
    global_VQAtokenizer = tokenizer
    return model, tokenizer
async def vqa_answer(message_to_edit,message, prompt):
    vqares=""
    if message.attachments:
        await message_to_edit.edit(content="我看看")
        image_data_list = []
        for attachment in message.attachments:
            if attachment.filename.endswith(('.png', '.jpg', '.jpeg', '.gif')):
                async with aiohttp.ClientSession() as session:
                    async with session.get(attachment.url) as response:
                        image_data = await response.read()
                        image_data_list.append(image_data)
        if image_data_list:
            for n_img, image_data in enumerate(image_data_list):
                image_data = Image.open(io.BytesIO(image_data)).convert('RGB')
                msgs = [{'role': 'user', 'content': prompt}]
                res = global_VQA.chat(
                    image=image_data,
                    msgs=msgs,
                    tokenizer=global_VQAtokenizer,
                    sampling=True,
                    num_beams=3,
                    temperature=0.7,
                    top_p=0.8,
                    top_k=100,
                    repetition_penalty=1.05,
                )
                vqares+=f'img{n_img}:'+res
        print('-'*20)
        print(vqares)
        print('-'*20)
        return vqares
    else:
        return ''