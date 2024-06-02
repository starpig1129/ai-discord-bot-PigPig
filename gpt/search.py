from gpt.internet.google_image import send_img
from gpt.internet.youtube import youtube_search
from gpt.internet.google_search import google_search
async def internet_search(message_to_edit, message, query, search_type):
    
    if search_type == "general":
        return await google_search(message_to_edit,message,query)
    elif search_type == "image":
        return await send_img(message_to_edit, message, query)
    elif search_type == "youtube":
        return await youtube_search(message_to_edit,message,query)
    else:
        raise ValueError(f"Unknown search type: {search_type}")