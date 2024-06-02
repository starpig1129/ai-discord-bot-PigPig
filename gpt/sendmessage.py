from gpt.gpt_response_gen import generate_response
from zhconv import convert
system_prompt='''
                You(assistant) are a helpful, 
                respectful and honest AI chatbot named 🐖🐖. 
                You are talking in a funny way to a human(user).
                If you don't know the answer to a question, don't share false information.
                Use the information provided to answer the questions in <<>>.
                You are made by 星豬<@597028717948043274>
                Always answer in Traditional Chinese.
                '''
async def gpt_message(message_to_edit,message,prompt):
    try:
        responses = ""
        thread,streamer = await generate_response(prompt, system_prompt)
        buffer_size = 40  # 设置缓冲区大小
        responsesall = ""
        for response in streamer:
            print(response, end="", flush=True)
            responses += response

            if len(responses) >= buffer_size:
                responsesall+=responses
                #responsesall = convert(responsesall, 'zh-tw')
                await message_to_edit.edit(content=responsesall)  # 修改消息内容
                responses = ""  # 清空 responses 变量
        print("結束")
        # 处理剩余的文本
        responsesall+=responses
       # responsesall = convert(responsesall, 'zh-tw')
        responsesall = responsesall.replace('<|eot_id|>',"")
        await message_to_edit.edit(content=responsesall)  # 修改消息内容
        thread.join()
    except Exception as e:
        print(e)