import aiohttp
import re
from bs4 import BeautifulSoup

async def fetch_page_content(message_to_edit, message):
    await message_to_edit.edit(content="造訪網站...")
    url_regex = r'(https?://\S+)'
    urls = re.findall(url_regex, message.content)
    if not urls:
        return "未找到有效的URL"
    
    all_texts = []
    error_messages = []
    
    try:
        async with aiohttp.ClientSession() as session:
            for url in urls:
                try:
                    async with session.get(url, timeout=10) as response:
                        if response.status == 200:
                            html = await response.text()
                            soup = BeautifulSoup(html, 'html.parser')

                            # 抓取 <body> 標籤內的內容
                            body_content = soup.body
                            if body_content:
                                # 移除不需要的元素，例如導航欄和頁腳
                                for element in body_content(['header', 'footer', 'nav', 'aside', 'form', 'button', 'script', 'style']):
                                    element.decompose()

                                # 抓取純文本內容
                                text = body_content.get_text(separator='\n', strip=True)
                                all_texts.append(text)
                            else:
                                error_msg = f"Failed to find body content in {url}"
                                error_messages.append(error_msg)
                                print(error_msg)
                        else:
                            error_msg = f"Failed to fetch page content from {url}, status code: {response.status}"
                            error_messages.append(error_msg)
                            print(error_msg)
                except aiohttp.ClientError as e:
                    error_msg = f"HTTP error while fetching {url}: {str(e)}"
                    error_messages.append(error_msg)
                    print(error_msg)
                except Exception as e:
                    error_msg = f"Unexpected error while fetching {url}: {str(e)}"
                    error_messages.append(error_msg)
                    print(error_msg)
        
        combined_text = "\n\n".join(all_texts)
        combined_errors = "\n".join(error_messages)
        
        result = combined_text if combined_text else "未能抓取到任何有效内容"
        if combined_errors:
            result += f"\n\nErrors:\n{combined_errors}"
        
        await message_to_edit.edit(content="抓取完成")
        print(result)
        return result
    
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(error_msg)
        return error_msg
