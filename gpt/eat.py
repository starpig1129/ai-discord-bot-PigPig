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
db = DB()
train = Train(db=db)
map = GoogleMapCrawler()
async def eat_search(message_to_edit,message, keyword: str = "_"):
            predict = None
            await message_to_edit.edit(content="覓食中")
            if keyword == "_":
                keywords_list = db.getKeywords()
                if len(keywords_list) == 0:
                    await message_to_edit.edit(content="沒有這種食物喔")
                    return
                else:
                    keyword = keywords_list[round(random.randint(0, len(keywords_list)-1))][0]
                    predict = train.predict(discord_id=str(message.guild.id))
            else:
                if len(db.checkKeyword(keyword=keyword)) == 0:
                    db.storeKeyword(keyword)

            
            
            try:
                if predict is not None:
                    result = map.search(predict)
                    (title_pred, rate_pred, tag_pred, address_pred, url,reviews,menu) = result
                    embed = eatEmbed(keyword=predict, title=title_pred,address=address_pred,rating=rate_pred)
                    if len(db.checkKeyword(keyword=tag_pred)) == 0:
                        db.storeKeyword(tag_pred)
                    
                    id = db.storeSearchRecord(str(message.guild.id), title=title_pred, keyword=predict, map_rate=rate_pred, tag=tag_pred, map_address=address_pred)
                else:
                    result = map.search(keyword)
                    (title, rate, tag, address, url,reviews,menu) = result
                    embed = eatEmbed(keyword=keyword, title=title,address=address,rating=rate)
                    if len(db.checkKeyword(keyword=tag)) == 0:
                        db.storeKeyword(tag)
                    
                    id = db.storeSearchRecord(str(message.guild.id), title=title, keyword=keyword, map_rate=rate, tag=tag, map_address=address)

                print(f"Debug: Search record id: {id}")

                await message_to_edit.edit(embed=embed, view=EatWhatView(result = result,predict=predict,keyword=keyword,db=db, record_id=id, discord_id=str(message.guild.id)))

                train.genModel(str(message.guild.id))
            except Exception as e:
                print(e)
                await message_to_edit.edit(content=f"原本想推薦你吃 {keyword if predict is None else predict}，但很抱歉系統出錯了QQ")