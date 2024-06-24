import discord


def eatEmbed(keyword, title, address, rating) -> discord.Embed:
    embed = discord.Embed(
                title="今天吃什麼",
                description=f"吃 **{keyword}**",
                colour=discord.Colour.blue()
            )
    embed.add_field(name="商家", value=f"**{title}**")
    embed.add_field(name="地址", value=f"{address}", inline=False)
    embed.add_field(name="評價", value=f"{rating}", inline=False)
    return embed

def mapEmbed(map_url: str) -> discord.Embed:
    embed = discord.Embed(
            title="地圖",
            description="以下為此商家的地圖",
            colour=discord.Colour.green()   
        )

    embed.set_image(url=map_url)

    return map_url

def menuEmbed(menu_url) -> discord.Embed:
    embed = discord.Embed(
        title="菜單",
        colour=discord.Colour.green()
    )

    embed.set_image(url=menu_url)
    
    return embed