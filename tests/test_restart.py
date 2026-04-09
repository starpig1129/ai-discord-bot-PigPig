import os
import shlex
import subprocess
import sys
import types
import importlib.util
from pathlib import Path

# Stub external modules that require production environment variables
project_root = Path(__file__).resolve().parent.parent
fake_addons = types.ModuleType("addons")
fake_addons.__path__ = [str(project_root / "addons")]


class _DummyLogger:
    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None


fake_logging = types.ModuleType("addons.logging")
fake_logging.get_logger = lambda **kwargs: _DummyLogger()

fake_settings = types.ModuleType("addons.settings")
fake_settings.base_config = {}

fake_addons.logging = fake_logging
fake_addons.settings = fake_settings

sys.modules["addons"] = fake_addons
sys.modules["addons.logging"] = fake_logging
sys.modules["addons.settings"] = fake_settings

fake_function = types.ModuleType("function")
fake_function.func = types.SimpleNamespace(report_error=lambda *args, **kwargs: None)
sys.modules["function"] = fake_function

fake_update = types.ModuleType("addons.update")
fake_update.__path__ = [str(project_root / "addons" / "update")]
sys.modules["addons.update"] = fake_update

restart_path = project_root / "addons" / "update" / "restart.py"
spec = importlib.util.spec_from_file_location("addons.update.restart", restart_path)
restart_module = importlib.util.module_from_spec(spec)
sys.modules["addons.update.restart"] = restart_module
spec.loader.exec_module(restart_module)
SimpleRestartManager = restart_module.SimpleRestartManager


def test_windows_simple_restart_escapes_paths(monkeypatch, tmp_path):
    manager = SimpleRestartManager(bot=None)

    current_dir = tmp_path / "dir%with&chars"
    current_dir.mkdir()
    python_exe = current_dir / "py%thon&exe.exe"

    popen_calls = {}

    class DummyProcess:
        def __init__(self) -> None:
            self.pid = 12345

    def fake_popen(args, **kwargs):
        popen_calls["args"] = args
        popen_calls["kwargs"] = kwargs
        return DummyProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setenv("COMSPEC", "cmd.exe")

    assert manager._windows_simple_restart(str(python_exe), str(current_dir))

    batch_file = current_dir / "temp_restart.bat"
    content = batch_file.read_text(encoding="utf-8")
    assert str(current_dir).replace("%", "%%") in content
    assert str(python_exe).replace("%", "%%") in content

    args = popen_calls["args"]
    assert args[:5] == ["cmd.exe", "/c", "start", '""', "/B"]
    batch_arg = args[-1]
    assert batch_arg.startswith('"') and batch_arg.endswith('"')
    assert "%%" in batch_arg
    assert popen_calls["kwargs"]["shell"] is False


def test_unix_simple_restart_quotes_paths(monkeypatch, tmp_path):
    manager = SimpleRestartManager(bot=None)

    current_dir = tmp_path / "dir with spaces and'quotes"
    current_dir.mkdir()
    python_exe = current_dir / "py thon'exe"

    popen_calls = {}

    class DummyProcess:
        pid = 6789

    def fake_popen(cmd, **kwargs):
        popen_calls["cmd"] = cmd
        popen_calls["kwargs"] = kwargs
        return DummyProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    assert manager._unix_simple_restart(str(python_exe), str(current_dir))

    script_file = current_dir / "temp_restart.sh"
    content = script_file.read_text(encoding="utf-8")
    assert shlex.quote(str(current_dir)) in content
    assert shlex.quote(str(python_exe)) in content

    assert popen_calls["cmd"] == ["nohup", str(script_file)]
    assert popen_calls["kwargs"]["start_new_session"] is True
