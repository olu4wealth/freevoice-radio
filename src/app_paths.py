"""Filesystem helpers that work both from source and from a frozen build.

Keeping these in one place avoids the classic PyInstaller trap: when the
app is frozen, ``__file__`` points inside the temporary ``_MEIPASS``
directory, so anything written next to it disappears on exit.  User data
(config, downloads) must live next to the executable instead.
"""

from __future__ import annotations

import os
import shutil
import sys


def is_frozen() -> bool:
    """True when running from a PyInstaller build."""
    return bool(getattr(sys, "frozen", False))


def app_dir() -> str:
    """Directory that holds user data (config.json, downloads/).

    * source run  -> the project folder (freevoice-radio/)
    * frozen run  -> the folder containing the .exe
    """
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_dir() -> str:
    """Directory holding bundled read-only resources (qss, ffmpeg, ...)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return meipass
    return app_dir()


def config_path() -> str:
    return os.path.join(app_dir(), "config.json")


def resolve_path(path: str | None, base: str | None = None) -> str | None:
    """Make a config path absolute (relative paths are app-dir relative)."""
    if not path:
        return path
    expanded = os.path.expandvars(os.path.expanduser(str(path)))
    if os.path.isabs(expanded):
        return os.path.normpath(expanded)
    return os.path.normpath(os.path.join(base or app_dir(), expanded))


def _candidate_ffmpeg_dirs() -> list[str]:
    candidates = [resource_dir(), app_dir(), os.path.dirname(resource_dir())]
    # A source checkout that keeps the binaries in dist/ or tools/.
    for sub in ("dist", "bin", os.path.join("tools", "ffmpeg")):
        candidates.append(os.path.join(app_dir(), sub))
    seen: set[str] = set()
    unique: list[str] = []
    for folder in candidates:
        if folder and folder not in seen:
            seen.add(folder)
            unique.append(folder)
    return unique


def find_ffmpeg() -> str | None:
    """Return a usable ffmpeg executable path, or None.

    Checked in order: bundled/copied binaries next to the app, then PATH.
    """
    exe_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    for folder in _candidate_ffmpeg_dirs():
        candidate = os.path.join(folder, exe_name)
        if os.path.isfile(candidate):
            return candidate
    found = shutil.which("ffmpeg")
    return found or None


def ffmpeg_dir() -> str | None:
    """Directory to hand to yt-dlp's ``ffmpeg_location`` option."""
    found = find_ffmpeg()
    return os.path.dirname(found) if found else None
