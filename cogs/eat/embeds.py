import discord


def _rating_colour(rating: float) -> discord.Colour:
    """Return corresponding colour based on rating."""
    if rating >= 4.2:
        return discord.Colour.gold()
    if rating >= 3.5:
        return discord.Colour.blue()
    return discord.Colour.red()


def _price_label(price_level: int) -> str:
    """Convert price level (1-4) to $ symbols."""
    if price_level and 1 <= price_level <= 4:
        return "$" * price_level
    return ""


def eatEmbed(keyword: str, title: str, address: str, rating,
             photo_url: str = "", price_level: int = 0,
             opening_hours: list = None,
             lang_manager=None, guild_id: str = "0") -> discord.Embed:
    """Detailed Embed after selecting a restaurant.

    Supports both old (rating as string) and new (rating as float) formats.
    """
    try:
        rating_float = float(rating)
    except (TypeError, ValueError):
        rating_float = 0.0

    colour = _rating_colour(rating_float)
    rating_display = f"⭐ {rating_float}" if rating_float else str(rating)

    price_display = _price_label(price_level)
    
    if lang_manager:
        title_display = lang_manager.translate(guild_id, "commands", "eat", "embeds", "eat", "title")
        description = lang_manager.translate(guild_id, "commands", "eat", "embeds", "eat", "description", keyword=keyword)
        field_restaurant = lang_manager.translate(guild_id, "commands", "eat", "embeds", "eat", "fields", "restaurant")
        field_address = lang_manager.translate(guild_id, "commands", "eat", "embeds", "eat", "fields", "address")
        address_missing = lang_manager.translate(guild_id, "commands", "eat", "embeds", "eat", "fields", "address_missing")
        field_rating = lang_manager.translate(guild_id, "commands", "eat", "embeds", "eat", "fields", "rating")
        field_hours = lang_manager.translate(guild_id, "commands", "eat", "embeds", "eat", "fields", "hours")
    else:
        title_display = f"What to Eat Today"
        description = f"Eating **{keyword}**"
        field_restaurant = "Restaurant"
        field_address = "Address"
        address_missing = "Address not provided"
        field_rating = "Rating"
        field_hours = "Opening Hours"

    if price_display:
        description += f"　{price_display}"

    embed = discord.Embed(title=title_display, description=description, colour=colour)
    embed.add_field(name=field_restaurant, value=f"**{title}**")
    embed.add_field(name=field_address, value=address or address_missing, inline=False)
    embed.add_field(name=field_rating, value=rating_display, inline=False)

    if opening_hours:
        hours_text = opening_hours[0] if isinstance(opening_hours, list) else str(opening_hours)
        embed.add_field(name=field_hours, value=hours_text[:100], inline=False)

    if photo_url:
        embed.set_image(url=photo_url)

    return embed


def browseEmbed(results: list, current_index: int,
                lang_manager=None, guild_id: str = "0") -> discord.Embed:
    """Multi-result browsing Embed, showing current restaurant info and pagination progress."""
    if not results:
        title = lang_manager.translate(guild_id, "commands", "eat", "errors", "not_found") if lang_manager else "No restaurants found"
        return discord.Embed(title=title, colour=discord.Colour.red())

    place = results[current_index]
    name = place.get("name", "Unknown Restaurant")
    rating = place.get("rating", 0.0) or 0.0
    category = place.get("category", "")
    address = place.get("address", "")
    photo_url = place.get("photo_url", "")
    price_level = place.get("price_level", 0)
    opening_hours = place.get("opening_hours", [])

    colour = _rating_colour(rating)
    
    if lang_manager:
        rating_missing = lang_manager.translate(guild_id, "commands", "eat", "embeds", "browse", "rating_missing")
        title_text = lang_manager.translate(guild_id, "commands", "eat", "embeds", "browse", "title", current=current_index + 1, total=len(results))
        field_rating = lang_manager.translate(guild_id, "commands", "eat", "embeds", "browse", "fields", "rating")
        field_address = lang_manager.translate(guild_id, "commands", "eat", "embeds", "browse", "fields", "address")
        field_hours = lang_manager.translate(guild_id, "commands", "eat", "embeds", "browse", "fields", "hours")
        footer_text = lang_manager.translate(guild_id, "commands", "eat", "embeds", "browse", "footer")
    else:
        rating_missing = "Rating unknown"
        title_text = f"🔍 Search Results　{current_index + 1} / {len(results)}"
        field_rating = "Rating"
        field_address = "Address"
        field_hours = "Opening Hours"
        footer_text = "Use buttons to browse or select from the dropdown"

    rating_display = f"⭐ {rating}" if rating else rating_missing
    price_display = _price_label(price_level)

    description_parts = [f"**{name}**"]
    if category:
        description_parts.append(f"🍴 {category}")
    if price_display:
        description_parts.append(price_display)

    embed = discord.Embed(
        title=title_text,
        description="\n".join(description_parts),
        colour=colour,
    )
    embed.add_field(name=field_rating, value=rating_display, inline=True)
    if address:
        embed.add_field(name=field_address, value=address[:100], inline=False)
    if opening_hours:
        hours_text = opening_hours[0] if isinstance(opening_hours, list) and opening_hours else str(opening_hours)
        embed.add_field(name=field_hours, value=hours_text[:100], inline=False)

    if photo_url:
        embed.set_image(url=photo_url)

    embed.set_footer(text=footer_text)
    return embed


def loadingEmbed(keyword: str, lang_manager=None, guild_id: str = "0") -> discord.Embed:
    """Loading Embed for search in progress."""
    if lang_manager:
        title = lang_manager.translate(guild_id, "commands", "eat", "embeds", "loading", "title")
        description = lang_manager.translate(guild_id, "commands", "eat", "embeds", "loading", "description", keyword=keyword)
        footer = lang_manager.translate(guild_id, "commands", "eat", "embeds", "loading", "footer")
    else:
        title = "🔍 Searching..."
        description = f"Searching for \"**{keyword}**\" related restaurants, please wait..."
        footer = "Searching via API"

    embed = discord.Embed(
        title=title,
        description=description,
        colour=discord.Colour.greyple(),
    )
    embed.set_footer(text=footer)
    return embed


def mapEmbed(map_url: str, lang_manager=None, guild_id: str = "0") -> discord.Embed:
    """Embed for displaying restaurant map."""
    if lang_manager:
        title = lang_manager.translate(guild_id, "commands", "eat", "embeds", "map", "title")
        description = lang_manager.translate(guild_id, "commands", "eat", "embeds", "map", "description")
    else:
        title = "Map"
        description = "Here is the map for this restaurant"

    embed = discord.Embed(
        title=title,
        description=description,
        colour=discord.Colour.green(),
    )
    embed.set_image(url=map_url)
    return embed


def menuEmbed(menu_url: str, lang_manager=None, guild_id: str = "0") -> discord.Embed:
    """Embed for displaying restaurant menu."""
    if lang_manager:
        title = lang_manager.translate(guild_id, "commands", "eat", "embeds", "menu", "title")
    else:
        title = "Menu"

    embed = discord.Embed(
        title=title,
        colour=discord.Colour.green(),
    )
    embed.set_image(url=menu_url)
    return embed
