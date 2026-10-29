"""Configuration manager for Freevoice Radio.

Handles reading/writing config.json with defaults, validation,
and typed accessors for all app settings.
"""

from __future__ import annotations

import json
import os
from typing import Any

from src.app_paths import app_dir, resolve_path

DEFAULT_CONFIG: dict[str, Any] = {
    "youtube_mode": "download",
    "download_path": "downloads",
    "audio_format": "original",
    "audio_quality": "128",
    "local_folder": None,
    "playlist": [],
    "excluded": [],
    "resume_track": "",
    "resume_position": 0.0,
    "loop_mode": "loop_all",
    "shuffle": False,
    "autoplay": True,
    "gapless": True,
    "crossfade_enabled": False,
    "crossfade_seconds": 5,
    "silence_between_tracks": False,
    "silence_seconds": 2,
    "volume": 70,
    "system_tray": True,
    "close_action": "ask",
    "theme": "dark",
    "channels": [],
    "scheduler_enabled": True,
    "scheduler_interval_minutes": 60,
}


class Config:
    def __init__(self, config_path: str = "config.json") -> None:
        self.config_path = config_path
        self._data: dict[str, Any] = dict(DEFAULT_CONFIG)
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.config_path):
            try:
                # utf-8-sig tolerates a BOM added by Notepad/PowerShell.
                with open(self.config_path, "r", encoding="utf-8-sig") as f:
                    user_cfg = json.load(f)
                self._data = {**DEFAULT_CONFIG, **user_cfg}
                # Older builds used "shuffle" as a loop mode; it is now an
                # independent toggle so Repeat and Shuffle can both be used.
                if self._data.get("loop_mode") == "shuffle":
                    self._data["loop_mode"] = "loop_all"
                    self._data["shuffle"] = True
                # Auto-download is opt-in.  Old channels were polled and
                # downloaded automatically; require an explicit choice now.
                for channel in self._data.get("channels", []):
                    if "auto_download" not in channel:
                        channel["auto_download"] = False
                        channel["enabled"] = False
            except (json.JSONDecodeError, OSError, ValueError):
                self._data = dict(DEFAULT_CONFIG)

    def save(self) -> bool:
        """Write the config to disk.  Returns False if it could not be saved."""
        folder = os.path.dirname(os.path.abspath(self.config_path))
        try:
            if folder:
                os.makedirs(folder, exist_ok=True)
            tmp = self.config_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.config_path)
            return True
        except OSError as exc:
            print(f"[config] could not save {self.config_path}: {exc}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
    # ------------------------------------------------------------------
    # Typed properties
    # ------------------------------------------------------------------
    @property
    def youtube_mode(self) -> str:
        return self._data["youtube_mode"]

    @youtube_mode.setter
    def youtube_mode(self, value: str) -> None:
        self._data["youtube_mode"] = value

    @property
    def download_path(self) -> str:
        """Absolute download folder (relative values are app-dir relative)."""
        resolved = resolve_path(self._data.get("download_path") or "downloads")
        return resolved or os.path.join(app_dir(), "downloads")

    @download_path.setter
    def download_path(self, value: str) -> None:
        self._data["download_path"] = value

    @property
    def audio_format(self) -> str:
        value = str(self._data.get("audio_format") or "original").lower()
        return value if value in ("original", "mp3", "wav", "flac", "m4a") else "original"

    @audio_format.setter
    def audio_format(self, value: str) -> None:
        value = str(value or "original").lower()
        self._data["audio_format"] = (
            value if value in ("original", "mp3", "wav", "flac", "m4a") else "original"
        )

    @property
    def audio_quality(self) -> str:
        """MP3 bitrate in kbps (96/128/160/192/256/320)."""
        value = str(self._data.get("audio_quality") or "128")
        return value if value in ("96", "128", "160", "192", "256", "320") else "128"

    @audio_quality.setter
    def audio_quality(self, value: str) -> None:
        value = str(value or "128")
        self._data["audio_quality"] = (
            value if value in ("96", "128", "160", "192", "256", "320") else "128"
        )

    @property
    def local_folder(self) -> str | None:
        return self._data["local_folder"]

    @local_folder.setter
    def local_folder(self, value: str | None) -> None:
        self._data["local_folder"] = value

    @property
    def loop_mode(self) -> str:
        return self._data["loop_mode"]

    @loop_mode.setter
    def loop_mode(self, value: str) -> None:
        self._data["loop_mode"] = value

    @property
    def shuffle(self) -> bool:
        return bool(self._data.get("shuffle", False))

    @shuffle.setter
    def shuffle(self, value: bool) -> None:
        self._data["shuffle"] = bool(value)

    @property
    def autoplay(self) -> bool:
        return bool(self._data.get("autoplay", True))

    @autoplay.setter
    def autoplay(self, value: bool) -> None:
        self._data["autoplay"] = bool(value)

    @property
    def resume_track(self) -> str:
        return str(self._data.get("resume_track") or "")

    @resume_track.setter
    def resume_track(self, value: str) -> None:
        self._data["resume_track"] = value or ""

    @property
    def resume_position(self) -> float:
        try:
            return max(0.0, float(self._data.get("resume_position") or 0.0))
        except (TypeError, ValueError):
            return 0.0

    @resume_position.setter
    def resume_position(self, value: float) -> None:
        self._data["resume_position"] = max(0.0, float(value or 0.0))

    @property
    def gapless(self) -> bool:
        return self._data["gapless"]

    @gapless.setter
    def gapless(self, value: bool) -> None:
        self._data["gapless"] = value

    @property
    def crossfade_enabled(self) -> bool:
        return self._data["crossfade_enabled"]

    @crossfade_enabled.setter
    def crossfade_enabled(self, value: bool) -> None:
        self._data["crossfade_enabled"] = value

    @property
    def crossfade_seconds(self) -> int:
        return self._data["crossfade_seconds"]

    @crossfade_seconds.setter
    def crossfade_seconds(self, value: int) -> None:
        self._data["crossfade_seconds"] = value

    @property
    def silence_between_tracks(self) -> bool:
        return self._data["silence_between_tracks"]

    @silence_between_tracks.setter
    def silence_between_tracks(self, value: bool) -> None:
        self._data["silence_between_tracks"] = value

    @property
    def silence_seconds(self) -> int:
        return self._data["silence_seconds"]

    @silence_seconds.setter
    def silence_seconds(self, value: int) -> None:
        self._data["silence_seconds"] = value

    @property
    def volume(self) -> int:
        return self._data["volume"]

    @volume.setter
    def volume(self, value: int) -> None:
        self._data["volume"] = max(0, min(100, value))

    @property
    def system_tray(self) -> bool:
        return self._data["system_tray"]

    @system_tray.setter
    def system_tray(self, value: bool) -> None:
        self._data["system_tray"] = value

    @property
    def close_action(self) -> str:
        """What the window's close button does: ask | tray | quit."""
        action = str(self._data.get("close_action") or "ask").lower()
        return action if action in ("ask", "tray", "quit") else "ask"

    @close_action.setter
    def close_action(self, value: str) -> None:
        action = str(value or "ask").lower()
        self._data["close_action"] = action if action in ("ask", "tray", "quit") else "ask"

    # ------------------------------------------------------------------
    # Playlist exclusions ("removed from playlist, keep on disk")
    # ------------------------------------------------------------------
    @property
    def excluded(self) -> set[str]:
        return {
            os.path.normcase(os.path.normpath(os.path.abspath(path)))
            for path in self._data.get("excluded", [])
            if path
        }

    @excluded.setter
    def excluded(self, paths) -> None:
        seen: set[str] = set()
        cleaned: list[str] = []
        for path in paths or []:
            if not path:
                continue
            absolute = os.path.normpath(os.path.abspath(str(path)))
            key = os.path.normcase(absolute)
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(absolute)
        self._data["excluded"] = cleaned

    def is_excluded(self, path: str) -> bool:
        if not path:
            return False
        key = os.path.normcase(os.path.normpath(os.path.abspath(path)))
        return key in self.excluded

    def exclude(self, path: str) -> None:
        if not path or self.is_excluded(path):
            return
        self._data.setdefault("excluded", []).append(
            os.path.normpath(os.path.abspath(path))
        )

    def include(self, path: str) -> None:
        if not path:
            return
        key = os.path.normcase(os.path.normpath(os.path.abspath(path)))
        current = self._data.get("excluded", [])
        self._data["excluded"] = [
            item
            for item in current
            if os.path.normcase(os.path.normpath(os.path.abspath(item))) != key
        ]

    @property
    def theme(self) -> str:
        return self._data["theme"]

    @theme.setter
    def theme(self, value: str) -> None:
        self._data["theme"] = value

    @property
    def channels(self) -> list[dict]:
        return self._data["channels"]

    @channels.setter
    def channels(self, value: list[dict]) -> None:
        self._data["channels"] = value

    @property
    def scheduler_enabled(self) -> bool:
        return self._data["scheduler_enabled"]

    @scheduler_enabled.setter
    def scheduler_enabled(self, value: bool) -> None:
        self._data["scheduler_enabled"] = value

    @property
    def scheduler_interval_minutes(self) -> int:
        return self._data["scheduler_interval_minutes"]

    @scheduler_interval_minutes.setter
    def scheduler_interval_minutes(self, value: int) -> None:
        self._data["scheduler_interval_minutes"] = value

    # ------------------------------------------------------------------
    # Playlist helpers
    # ------------------------------------------------------------------
    @property
    def playlist(self) -> list[dict]:
        """Persisted playlist entries: {path, title, artist, duration, source}."""
        entries = self._data.get("playlist")
        if not isinstance(entries, list):
            return []
        return [e for e in entries if isinstance(e, dict) and e.get("path")]

    @playlist.setter
    def playlist(self, entries: list[dict]) -> None:
        cleaned = []
        for entry in entries or []:
            if isinstance(entry, str):
                entry = {"path": entry}
            if not isinstance(entry, dict) or not entry.get("path"):
                continue
            cleaned.append(
                {
                    "path": entry["path"],
                    "title": entry.get("title") or os.path.basename(entry["path"]),
                    "artist": entry.get("artist") or "Unknown",
                    "duration": int(entry.get("duration") or 0),
                    "source": entry.get("source") or "local",
                }
            )
        self._data["playlist"] = cleaned

    # ------------------------------------------------------------------
    # Channel helpers
    # ------------------------------------------------------------------
    def add_channel(self, channel: dict) -> None:
        self._data["channels"].append(channel)

    def remove_channel(self, channel_id: str) -> None:
        self._data["channels"] = [
            c
            for c in self._data["channels"]
            if c.get("id") != channel_id and c.get("url") != channel_id
        ]

    def get_channel(self, channel_id: str) -> dict | None:
        for c in self._data["channels"]:
            if c.get("id") == channel_id:
                return c
        return None