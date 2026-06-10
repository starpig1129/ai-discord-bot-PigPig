import sys
import unittest.mock

# Create a robust discord module mock *before* any other imports
mock_discord = unittest.mock.MagicMock()

class MockAllowedMentions:
    def __init__(self, **kwargs):
        pass

class MockEmbed:
    def __init__(self, **kwargs):
        pass

class MockColour:
    @classmethod
    def red(cls): return cls()
    @classmethod
    def green(cls): return cls()

class MockFile:
    def __init__(self, fp, filename=None):
        pass

mock_discord.AllowedMentions = MockAllowedMentions
mock_discord.Embed = MockEmbed
mock_discord.Colour = MockColour
mock_discord.File = MockFile
mock_discord.abc.Messageable = unittest.mock.MagicMock()
mock_discord.errors.NotFound = Exception

# Only cache the module if it doesn't already exist to avoid clobbering tests that need the real one
if 'discord' not in sys.modules:
    sys.modules['discord'] = mock_discord

import addons.settings
