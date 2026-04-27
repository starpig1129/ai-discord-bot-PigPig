"""Tests for translation key completeness in system_prompt.json files."""
import json
import pytest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

REQUIRED_KEYS = [
    ("ui", "buttons", "reload_config"),
    ("ui", "buttons", "direct_edit"),
    ("ui", "menus", "edit_mode_title"),
    ("ui", "menus", "edit_mode_description"),
    ("messages", "success", "reload"),
    ("messages", "info", "reload_unavailable"),
]
LANGUAGES = ["zh_TW", "zh_CN", "en_US", "ja_JP"]


def _load(lang: str) -> dict:
    path = BASE / "translations" / lang / "commands" / "system_prompt.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _get(d: dict, keys: tuple):
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


@pytest.mark.parametrize("lang", LANGUAGES)
@pytest.mark.parametrize("key_path", REQUIRED_KEYS)
def test_required_key_exists(lang, key_path):
    data = _load(lang)
    value = _get(data, key_path)
    assert value is not None, f"Missing key {'.'.join(key_path)} in {lang}"
    assert isinstance(value, str) and len(value) > 0, (
        f"Empty key {'.'.join(key_path)} in {lang}"
    )
