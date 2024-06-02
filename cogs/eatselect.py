from discord.ext import commands
import discord.app_commands as app_commands
import discord
from dotenv import load_dotenv
import random
import os
from cogs.eat.db.db import DB
from cogs.eat.embeds import eatEmbed
from cogs.eat.providers.googlemap_crawler import GoogleMapCrawler
from cogs.eat.train.train import Train
from cogs.eat.views import EatWhatView
class eatselect(commands.Cog):      
    def __init__(self, bot):
        self.db = DB()
        self.train = Train(db=self.db)
        self.bot = bot  
    @commands.hybrid_command(name="eat")
    @app_commands.describe(keyword="輸入關鍵字來尋找推薦的餐廳，如果留空則隨機推薦")
    async def eat(self,ctx: commands.Context, keyword: str = "_"):
        predict = None
        
        if keyword == "_":
            keywords_list = self.db.getKeywords()
            if len(keywords_list) == 0:
                await ctx.send("你沒有輸入任何文字!")
                return
            else:
                keyword = keywords_list[round(random.randint(0, len(keywords_list)-1))][0]
                predict = self.train.predict(discord_id=str(ctx.guild.id))
        else:
            if len(self.db.checkKeyword(keyword=keyword)) == 0:
                self.db.storeKeyword(keyword)

        map = GoogleMapCrawler()
        
        try:
            if predict is not None:
                (title_pred, rate_pred, tag_pred, address_pred) = map.search(predict)
                embed = eatEmbed(keyword=predict, title=title_pred)
                if len(self.db.checkKeyword(keyword=tag_pred)) == 0:
                    self.db.storeKeyword(tag_pred)
                
                id = self.db.storeSearchRecord(str(ctx.guild.id), title=title_pred, keyword=predict, map_rate=rate_pred, tag=tag_pred, map_address=address_pred)
            else:
                (title, rate, tag, address) = map.search(keyword)
                embed = eatEmbed(keyword=keyword, title=title,address=address,rating=rate)
                if len(self.db.checkKeyword(keyword=tag)) == 0:
                    self.db.storeKeyword(tag)
                
                id = self.db.storeSearchRecord(str(ctx.guild.id), title=title, keyword=keyword, map_rate=rate, tag=tag, map_address=address)

            print(f"Debug: Search record id: {id}")

            await ctx.send(embed=embed, view=EatWhatView(db=self.db, record_id=id, discord_id=str(ctx.guild.id)))

            self.train.genModel(str(ctx.guild.id))
        except Exception as e:
            print(e)
            await ctx.send(f"原本想推薦你吃 {keyword if predict is None else predict}，但很抱歉系統出錯了QQ")
async def setup(bot):
    await bot.add_cog(eatselect(bot))