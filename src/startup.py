"""Optional Windows startup registration for Freevoice Radio."""

from __future__ import annotations

import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Freevoice Radio"


def startup_command() -> str:
    """Command written to the HKCU Run key."""
    if not getattr(sys, "frozen", False):
        executable = Path(sys.executable)
        pythonw = executable.with_name("pythonw.exe")
        if pythonw.exists():
            executable = pythonw
        script = Path(__file__).resolve().parent.parent / "main.py"
        return f'"{executable}" "{script}" --minimized'
    return f'"{Path(sys.executable)}" --minimized'


def is_startup_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return bool(value)
    except OSError:
        return False


def set_startup_enabled(enabled: bool) -> bool:
    """Create or remove the per-user Run entry. Returns True on success."""
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            if enabled:
                winreg.SetValueEx(
                    key, VALUE_NAME, 0, winreg.REG_SZ, startup_command()
                )
            else:
                try:
                    winreg.DeleteValue(key, VALUE_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError as exc:
        print(f"[startup] could not update Run key: {exc}")
        return False
