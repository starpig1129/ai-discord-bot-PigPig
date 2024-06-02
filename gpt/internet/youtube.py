from langchain_community.tools import YouTubeSearchTool
import random
import re
youtubeser = YouTubeSearchTool()
async def youtube_search(message_to_edit,message,query):
    try:
        await message_to_edit.edit(content="youtube搜尋中")
        results = re.findall(r'https?://[^\s\']+', youtubeser.run(query))
        await message_to_edit.edit(content=random.choice(results))
        return None
    except Exception as e:
        print('youtube_search:',e)
        await message_to_edit.edit(content="搜尋失敗請換一下關鍵詞")