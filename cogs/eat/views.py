import discord
import asyncio
from cogs.eat.db.db import DB
from cogs.eat.providers.googlemap_crawler import GoogleMapCrawler
from cogs.eat.embeds import mapEmbed, menuEmbed
from cogs.eat.train.train import Train
from cogs.eat.embeds import eatEmbed
import random
from gpt.gpt_response_gen import generate_response
map = GoogleMapCrawler('/media/e806/4T/ziyue/dcbot/chromedriver-linux64/chromedriver')
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
            print('EatWatchView regenerate:',e)
    @discord.ui.button(label="查看評論", emoji="📰")
    async def review(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            system_prompt = '''You are a food critic and make a complete evaluation and explanation of the store based on the information provided.
                            You are talking in a funny way to a human(user).
                            Always answer in Traditional Chinese.'''  # 设置系统提示（如果需要）
            prompt=f''' 店名:{self.result[0]}
                        評價:{self.result[1]},滿分為5
                        分類:{self.result[2]}
                        地址:淡水區{self.result[3]}
                        評論:{self.result[5]}'''
            # 发送初始消息，用于后续编辑
            await interaction.response.send_message("評價中...", ephemeral=True)
            message_to_edit = await interaction.followup.send("...", ephemeral=True)
            # 生成文字
            thread, streamer = await generate_response(prompt, system_prompt)
            buffer_size = 40  # 设置缓冲区大小
            responses = ""
            responsesall = ""
            for response in streamer:
                print(response, end="", flush=True)
                responses += response

                if len(responses) >= buffer_size:
                    responsesall+=responses
                    #responsesall = convert(responsesall, 'zh-tw')
                    await message_to_edit.edit(content=responsesall)  # 修改消息内容
                    responses = ""  # 清空 responses 变量

            # 处理剩余的文本
            responsesall+=responses
            # responsesall = convert(responsesall, 'zh-tw')
            responsesall = responsesall.replace('<|eot_id|>',"")
            await message_to_edit.edit(content=responsesall)  # 修改消息内容
            thread.join()
        except Exception as e:
            print(e)