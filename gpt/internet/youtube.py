from youtube_search import YoutubeSearch
import random

async def youtube_search(message_to_edit, message, query):
    try:
        # 使用 youtube-search-python 進行搜索
        results = YoutubeSearch(query, max_results=5).to_dict()

        if not results:
            return "未找到相關影片，請嘗試其他關鍵詞。"

        selected_result = random.choice(results)
        title = selected_result['title']
        channel = selected_result['channel']
        views = selected_result['views']
        link = f"https://www.youtube.com{selected_result['url_suffix']}"

        video_description = (f"YoutubeSearch的結果：\n"
                             f"標題: {title}\n"
                             f"發布者: {channel}\n"
                             f"觀看次數: {views}\n"
                             f"連結: {link}")
        print(video_description)
        return video_description  # 返回影片的相關介紹
    except Exception as e:
        print('youtube_search:', e)
        return "搜尋失敗，請換一下關鍵詞。"

