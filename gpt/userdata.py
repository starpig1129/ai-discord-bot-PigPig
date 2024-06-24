import re
from pymongo import MongoClient
from gpt.gpt_response_gen import generate_response

async def manage_user_data(message_to_edit, message, user_id=None, user_data=None, action='read'):
    await message_to_edit.edit(content="翻翻豬腦...")
    
    # 連接到 MongoDB
    client = MongoClient("mongodb://localhost:27017/")
    db = client["user_data"]
    collection = db["users"]
    if user_id == "<@user_id>":
        user_id = message.author.id
    try:
        match = re.search(r'\d+', user_id)
        user_id = match.group()
    except:
        user_id = message.author.id
    print(user_id)
    if action == 'read':
        document = collection.find_one({"user_id": user_id})
        if document:      
            data = document["user_data"]
            print(f"user<@{user_id}>data:{(data)}")
            return f"userid<@{user_id}>是一位{(data)}"
        else:
            return "No data found for the user."

    elif action == 'save':
        await message_to_edit.edit(content="更新記憶...")
        document = collection.find_one({"user_id": user_id})
        if document:
            existing_data = document["user_data"]
            prompt = f"Current original data: {existing_data}\nnew data: {user_data}"
            system_prompt = 'Return user data based on original data and new data.'
            thread, streamer = await generate_response(prompt, system_prompt)
            new_data = ''
            for response in streamer:
                new_data += response
            # 等待生成器完成
            thread.join()
            collection.update_one({"user_id": user_id}, {"$set": {"user_data": new_data}})
            print("User data updated successfully.")
            return f"更新資料{new_data}"
        else:
            collection.insert_one({"user_id": user_id, "user_data": user_data})
            print("User data created successfully.")
            return f"記憶資料{user_data}"
    
    else:
        print("Invalid action. Use 'read' or 'save'.")
