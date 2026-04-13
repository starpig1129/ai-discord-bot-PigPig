import discord


def _rating_colour(rating: float) -> discord.Colour:
    """依評分返回對應顏色。"""
    if rating >= 4.2:
        return discord.Colour.gold()
    if rating >= 3.5:
        return discord.Colour.blue()
    return discord.Colour.red()


def _price_label(price_level: int) -> str:
    """將 Foursquare 價格等級（1-4）轉換為 $ 符號。"""
    if price_level and 1 <= price_level <= 4:
        return "$" * price_level
    return ""


def eatEmbed(keyword: str, title: str, address: str, rating,
             photo_url: str = "", price_level: int = 0,
             opening_hours: list = None) -> discord.Embed:
    """選定餐廳後的詳細 Embed。

    支援舊版（rating 為字串）和新版（rating 為 float）兩種格式。
    """
    try:
        rating_float = float(rating)
    except (TypeError, ValueError):
        rating_float = 0.0

    colour = _rating_colour(rating_float)
    rating_display = f"⭐ {rating_float}" if rating_float else str(rating)

    price_display = _price_label(price_level)
    title_display = f"今天吃什麼"
    description = f"吃 **{keyword}**"
    if price_display:
        description += f"　{price_display}"

    embed = discord.Embed(title=title_display, description=description, colour=colour)
    embed.add_field(name="商家", value=f"**{title}**")
    embed.add_field(name="地址", value=address or "地址未提供", inline=False)
    embed.add_field(name="評價", value=rating_display, inline=False)

    if opening_hours:
        hours_text = opening_hours[0] if isinstance(opening_hours, list) else str(opening_hours)
        embed.add_field(name="營業時間", value=hours_text[:100], inline=False)

    if photo_url:
        embed.set_image(url=photo_url)

    return embed


def browseEmbed(results: list, current_index: int) -> discord.Embed:
    """多結果瀏覽 Embed，顯示當前餐廳資訊和翻頁進度。"""
    if not results:
        return discord.Embed(title="找不到餐廳", colour=discord.Colour.red())

    place = results[current_index]
    name = place.get("name", "未知餐廳")
    rating = place.get("rating", 0.0) or 0.0
    category = place.get("category", "")
    address = place.get("address", "")
    photo_url = place.get("photo_url", "")
    price_level = place.get("price_level", 0)
    opening_hours = place.get("opening_hours", [])

    colour = _rating_colour(rating)
    rating_display = f"⭐ {rating}" if rating else "評分未知"
    price_display = _price_label(price_level)

    description_parts = [f"**{name}**"]
    if category:
        description_parts.append(f"🍴 {category}")
    if price_display:
        description_parts.append(price_display)

    embed = discord.Embed(
        title=f"🔍 搜尋結果　{current_index + 1} / {len(results)}",
        description="\n".join(description_parts),
        colour=colour,
    )
    embed.add_field(name="評價", value=rating_display, inline=True)
    if address:
        embed.add_field(name="地址", value=address[:100], inline=False)
    if opening_hours:
        hours_text = opening_hours[0] if isinstance(opening_hours, list) and opening_hours else str(opening_hours)
        embed.add_field(name="營業時間", value=hours_text[:100], inline=False)

    if photo_url:
        embed.set_image(url=photo_url)

    embed.set_footer(text="使用下方按鈕翻頁，或從下拉選單直接選擇餐廳")
    return embed


def loadingEmbed(keyword: str) -> discord.Embed:
    """搜尋進行中的 loading Embed。"""
    embed = discord.Embed(
        title="🔍 搜尋中...",
        description=f"正在搜尋「**{keyword}**」相關餐廳，請稍候...",
        colour=discord.Colour.greyple(),
    )
    embed.set_footer(text="透過 Foursquare Places API 搜尋中")
    return embed


def mapEmbed(map_url: str) -> discord.Embed:
    embed = discord.Embed(
        title="地圖",
        description="以下為此商家的地圖",
        colour=discord.Colour.green(),
    )
    embed.set_image(url=map_url)
    return embed


def menuEmbed(menu_url: str) -> discord.Embed:
    embed = discord.Embed(
        title="菜單",
        colour=discord.Colour.green(),
    )
    embed.set_image(url=menu_url)
    return embed
