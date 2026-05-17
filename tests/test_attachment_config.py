# tests/test_attachment_config.py
import pytest
from unittest.mock import patch

def test_attachment_config_defaults():
    """AttachmentConfig 應從 YAML 正確載入預設值"""
    from addons.settings import AttachmentConfig
    cfg = AttachmentConfig("base_configs/attachments.yaml")
    assert cfg.enabled is True
    assert cfg.image.enabled is True
    assert cfg.image.max_dimension == 2048
    assert cfg.pdf.max_pages == 20
    assert cfg.pdf.dpi_full == 150
    assert cfg.pdf.dpi_medium == 100
    assert cfg.pdf.dpi_compressed == 72
    assert cfg.pdf.threshold_full == 5
    assert cfg.pdf.threshold_medium == 15
    assert cfg.pdf.notify_truncated is True
    assert cfg.pdf.enabled is True
    assert cfg.video.enabled is True
    assert cfg.video.max_frames == 16
    assert cfg.video.min_interval_sec == 2.0
    assert cfg.embeds.enabled is True
    assert cfg.embeds.include_images is True

def test_attachment_config_missing_file():
    """不存在的 YAML 應 fallback 為預設值，不拋出例外"""
    from addons.settings import AttachmentConfig
    cfg = AttachmentConfig("nonexistent_path/attachments.yaml")
    assert cfg.enabled is True
    assert cfg.pdf.max_pages == 20
