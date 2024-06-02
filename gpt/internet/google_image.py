import os
import random
import time
import discord
import requests
import cv2
import glob
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from skimage.metrics import structural_similarity as ssim

async def send_img(message_to_edit,message, query):
    await message_to_edit.edit(content="尋找中...")
    print('圖片搜尋:', query)

    url = f"https://www.google.com.hk/search?q={query}&tbm=isch"

    chrome_options = Options()
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    service = Service('./chromedriver-linux64/chromedriver')
    driver = webdriver.Chrome(options=chrome_options, service=service)

    try:
        driver.get(url)
        driver.maximize_window()
        time.sleep(2)

        image_elements = driver.find_elements(By.CLASS_NAME, 'ob5Hkd')
        num_elements = len(image_elements)

        base_weight = 1.5  # 可以調整這個值來改變機率分布
        weights = [base_weight ** i for i in range(num_elements)]
        total_weight = sum(weights)
        probabilities = [weight / total_weight for weight in weights]

        chosen_element = random.choices(image_elements, weights=probabilities)[0]
        chosen_element.click()

        time.sleep(2)
        # 取得選擇的圖片元素和跳轉URL元素
        smail_pic_elements = driver.find_elements(By.CLASS_NAME, 'sFlh5c.pT0Scc')
        goto_url_elements = driver.find_elements(By.CLASS_NAME, 'umNKYc')

        # 根據元素數量選擇適當的元素
        if len(smail_pic_elements) > 1 and len(goto_url_elements) > 1:
            smail_pic = smail_pic_elements[1]
            goto_url_elements[1].click()
        elif len(smail_pic_elements) > 0 and len(goto_url_elements) > 0:
            smail_pic = smail_pic_elements[0]
            goto_url_elements[0].click()
        else:
            raise Exception("無法找到圖片元素或跳轉URL元素")

        src = smail_pic.get_attribute('src')
        with open(f'./gpt/img/need.jpg', 'wb') as f:
            f.write(requests.get(src).content)

        time.sleep(1)
        driver.switch_to.window(driver.window_handles[-1])

        all_img = driver.find_elements(By.TAG_NAME, 'img')
        for idx, img in enumerate(all_img):
            try:
                img_url = img.get_attribute('src')
                response = requests.get(img_url)
                if response.status_code == 200:
                    with open(f'./gpt/img/image_{idx}.jpg', 'wb') as f:
                        f.write(response.content)
            except:
                pass

        need = cv2.imread('./gpt/img/need.jpg', cv2.IMREAD_GRAYSCALE)
        directory = './gpt/img/'
        jpg_files = glob.glob(os.path.join(directory, '*.jpg'))

        similarity_dict = {}
        for jpg_file in jpg_files:
            if "need" not in jpg_file:
                img2 = cv2.imread(jpg_file, cv2.IMREAD_GRAYSCALE)
                try:
                    img2 = cv2.resize(img2, (need.shape[1], need.shape[0]))
                    ssim_value, _ = ssim(need, img2, full=True)
                    similarity_dict[jpg_file] = ssim_value
                except:
                    pass

        max_file = max(similarity_dict, key=similarity_dict.get)
        with open(max_file, 'rb') as file:
            picture = discord.File(file, filename='./gpt/image.jpg')
            await message_to_edit.reference.resolved.reply(file=picture)
            await message_to_edit.delete()

        for file in os.listdir(directory):
            if file.endswith('.jpg'):
                os.remove(os.path.join(directory, file))

    except Exception as e:
        print(f"圖片下載失敗: {e}")
        await message_to_edit.edit(content="圖片下載失敗")
    finally:
        driver.quit()

    return None