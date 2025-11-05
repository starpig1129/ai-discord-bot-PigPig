import discord
import asyncio
import json
from typing import Dict, Any, List
from cogs.eat.db.db import DB
from cogs.eat.providers.googlemap_crawler import GoogleMapCrawler
from cogs.eat.embeds import mapEmbed, menuEmbed
from cogs.eat.train.train import Train
from cogs.eat.embeds import eatEmbed
import random
from function import func
from llm.orchestrator import generate_response
from llm.utils.send_message import safe_edit_message
map = GoogleMapCrawler()
class EatWhatView(discord.ui.View):
    def __init__(self,result,predict:str,keyword:str, db: DB, record_id: int, discord_id:str):
        super().__init__()
        self.result = result
        self.predict = predict
        self.keyword = keyword
        self.db = db
        self.record_id = record_id
        self.self_rate = 0.5
        self.discord_id = discord_id

        # self.add_item(discord.ui.Button(label="測試按鈕"))

    # TODO: 按下特定按鈕時要會紀錄喜好值


    @discord.ui.button(label="地圖", emoji="🗺️")
    async def map(self, interation: discord.Interaction, button: discord.ui.Button):
        #embed = mapEmbed(self.result[4])
        await interation.response.send_message(self.result[4])

    @discord.ui.button(label="菜單", emoji="📰")
    async def menu(self, interation: discord.Interaction, button: discord.ui.Button):
        embed = menuEmbed(self.result[6])
        await interation.response.send_message(embed=embed)

    @discord.ui.button(emoji="👍")
    async def like(self, interation: discord.Interaction, button: discord.ui.Button):
        self.self_rate = 1
        self.db.updateRecordRate(id=self.record_id, new_rate=self.self_rate)
        train = Train(db=self.db)
        train.genModel(self.discord_id)
        await interation.response.send_message(content="感謝您的意見，往後將會推薦類似商家", ephemeral=True)

    @discord.ui.button(emoji="👎")
    async def dislike(self, interation: discord.Interaction, button: discord.ui.Button):
        self.self_rate = -1
        self.db.updateRecordRate(id=self.record_id, new_rate=self.self_rate)
        train = Train(db=self.db)
        train.genModel(self.discord_id)
        await interation.response.send_message(content="感謝您的意見，下次將不會推薦類似商家", ephemeral=True)
        
   
    @discord.ui.button(style=discord.ButtonStyle.primary, emoji="🔄")
    async def regenerate(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
            embed = eatEmbed(keyword='...', title='某家神奇的店', address='在哪呢', rating='超頂')
            await interaction.edit_original_response(content="尋找中...", embed=embed, view=self)
            self.self_rate = -0.5
            self.db.updateRecordRate(id=self.record_id, new_rate=self.self_rate)
            train = Train(db=self.db)
            train.genModel(self.discord_id)
            if self.predict is not None:
                keywords_list = self.db.getKeywords()
                self.keyword = keywords_list[round(random.randint(0, len(keywords_list)-1))][0]
                self.predict = train.predict(discord_id=str(self.discord_id))
                self.keyword = self.predict
            self.result = map.search(self.keyword)
            (title, rate, tag, address, url,reviews,menu) = self.result
            embed = eatEmbed(keyword=self.keyword, title=title, address=address, rating=rate)
            if len(self.db.checkKeyword(keyword=tag)) == 0:
                self.db.storeKeyword(tag)
            id = self.db.storeSearchRecord(str(self.discord_id), title=title, keyword=self.keyword, map_rate=rate, tag=tag, map_address=address)
            print(f"Debug: Search record id: {id}")
            await interaction.edit_original_response(content="更新推荐：", embed=embed, view=EatWhatView(result = self.result,predict=self.predict,keyword=self.keyword,db=self.db, record_id=id, discord_id=str(self.discord_id)))
        except Exception as e:
            await func.report_error(e, "cogs/eat/views.py/regenerate")
    @discord.ui.button(label="查看評論", emoji="📰")
    async def review(self, interaction: discord.Interaction, button: discord.ui.Button):
        """美食評論功能按鈕 - 已升級至 Google Gemini API 官方標準
        
        主要改進：
        1. 使用官方 role + parts 格式建構對話歷史
        2. 採用 function 角色格式化店家資訊（符合工具調用標準）
        3. 改用 async for 處理串流回應
        4. 加強錯誤處理和中文註解
        """
        try:
            # === Google Gemini API 官方標準系統提示 (優化為英文) ===
            system_prompt = '''You are a professional and witty food critic who excels at writing vivid and interesting reviews based on restaurant information.
                            Interact with users in a humorous yet professional tone, providing valuable dining recommendations.
                            Your reviews should include comprehensive analysis of food quality, atmosphere, and service standards.
                            Always respond in Traditional Chinese and use emojis appropriately to add fun and engagement.'''
            
            # === 結構化店家資訊（符合官方格式標準） ===
            store_info = {
                "restaurant_name": self.result[0],
                "rating": f"{self.result[1]}/5.0",
                "category": self.result[2],
                "address": f"{self.result[3]}",
                "reviews": self.result[5],
                "data_source": "google_maps_crawler"
            }
            
            # === 使用官方 function 角色格式建構對話歷史 ===
            # 符合新的工具調用和智慧上下文建構標準
            dialogue_history = [
                {
                    "role": "function",
                    "name": "restaurant_data_retrieval",
                    "content": json.dumps({
                        "restaurant_info": store_info,
                        "analysis_type": "comprehensive_review",
                        "review_style": "professional_humorous"
                    }, ensure_ascii=False, indent=2)
                }
            ]
            
            # 發送初始訊息，用於後續即時更新
            await interaction.response.send_message("🍽️ AI 美食評論家正在分析中...", ephemeral=True)
            message_to_edit = await interaction.followup.send("📝 準備撰寫專業評論...", ephemeral=True)
            
            # === 使用新的 Google Gemini API 官方格式標準生成評論 ===
            # 符合升級後的 generate_response 函數規範
            thread, streamer = await generate_response(
                inst="Based on the provided restaurant information, write a professional and witty food review.",
                system_prompt=system_prompt,
                dialogue_history=dialogue_history
            )
            
            # === 優化的串流回應處理 ===
            buffer_size = 40  # 設置緩衝區大小，提供流暢的即時顯示
            responses = ""
            responsesall = ""
            
            # 使用 async for 處理串流回應（符合新的非同步處理標準）
            async for response in streamer:
                print(response, end="", flush=True)  # 終端輸出調試
                responses += response

                # 達到緩衝區大小時即時更新 Discord 訊息
                if len(responses) >= buffer_size:
                    responsesall += responses
                    await safe_edit_message(message_to_edit, responsesall)
                    responses = ""  # 清空緩衝區

            # 處理剩餘的回應內容並清理特殊標記
            responsesall += responses
            responsesall = responsesall.replace('<|eot_id|>', "").strip()
            await safe_edit_message(message_to_edit, responsesall)
            
            # 等待執行緒完成（向後相容性處理）
            if thread:
                thread.join()
        except Exception as e:
            await func.report_error(e, "cogs/eat/views.py/review")