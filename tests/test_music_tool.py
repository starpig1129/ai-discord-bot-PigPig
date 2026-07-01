import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from llm.tools.music import MusicTools
from llm.schema import OrchestratorRequest

@pytest.fixture
def mock_runtime():
    runtime = MagicMock(spec=OrchestratorRequest)
    bot = MagicMock()
    cog = MagicMock()
    bot.get_cog.return_value = cog
    runtime.bot = bot

    msg = MagicMock()
    guild = MagicMock()
    guild.id = 123
    author = MagicMock(spec=discord.Member)
    author.voice = MagicMock()
    author.voice.channel = MagicMock()
    author.voice.channel.connect = AsyncMock()
    msg.guild = guild
    msg.author = author
    msg.channel = MagicMock()

    runtime.message = msg
    return runtime, bot, cog

@pytest.mark.asyncio
async def test_music_tools_play_success(mock_runtime):
    runtime, bot, cog = mock_runtime

    dummy_interaction = MagicMock()
    cog._create_dummy_interaction = AsyncMock(return_value=dummy_interaction)
    cog._handle_search = AsyncMock(return_value=True)
    cog._handle_single_video = AsyncMock(return_value=True)
    cog._handle_playlist = AsyncMock(return_value=True)

    tools = MusicTools(runtime).get_tools()
    play_music = tools[0]

    # Test normal search
    res = await play_music.ainvoke({"query": "some song"})
    assert "Searched and added" in res

    # Test single video URL
    res = await play_music.ainvoke({"query": "https://youtube.com/watch?v=123"})
    assert "Added video" in res

    # Test playlist
    res = await play_music.ainvoke({"query": "https://youtube.com/playlist?list=123"})
    assert "Added playlist" in res
