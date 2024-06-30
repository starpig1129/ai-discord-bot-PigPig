from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup

async def google_search(message_to_edit,message,query):
    await message_to_edit.edit(content="尋找中...")
    # 設置Chrome瀏覽器選項
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    # 指定chromedriver的路徑
    service = Service('./chromedriver-linux64/chromedriver')
    print('google_search:',query)
    # 使用with語句來確保資源被正確關閉
    with webdriver.Chrome(options=chrome_options, service=service) as driver:
        url = f"https://www.google.com/search?q={query}"
        driver.get(url)
        html = driver.page_source

    soup = BeautifulSoup(html, 'html.parser')
    search_results = soup.select('.g') 
    search = ""
    for result in search_results[:5]:
        title_element = result.select_one('h3')
        title = title_element.text if title_element else 'No Title'
        snippet_element = result.select_one('.VwiC3b')
        snippet = snippet_element.text if snippet_element else 'No Snippet'
        search += f"{title}\n{snippet}\n"

    return search
