"""Resolve a YouTube live video/channel into a playable HLS audio URL."""

from __future__ import annotations

import re
import urllib.request
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse, urlunparse

import yt_dlp
from PyQt6.QtCore import QThread, pyqtSignal


class NotLiveError(Exception):
    """The requested item is not currently broadcasting live."""


@dataclass
class LiveStreamInfo:
    id: str
    title: str
    artist: str
    watch_url: str
    stream_url: str
    http_headers: dict[str, str] = field(default_factory=dict)
    thumbnail: Optional[str] = None
    thumbnail_data: Optional[bytes] = None
    is_live: bool = True


def normalize_live_url(url: str) -> str:
    """Turn channel roots/tabs into their /live endpoint."""
    url = (url or "").strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if "youtube.com" not in host:
        return url
    path = parsed.path.rstrip("/")
    if path.endswith("/live"):
        return url
    for tab in ("/videos", "/streams", "/shorts", "/featured"):
        if path.endswith(tab):
            path = path[: -len(tab)]
            break
    if path.startswith(("/@", "/channel/", "/c/", "/user/")) or not path:
        path += "/live"
        return urlunparse(
            (parsed.scheme or "https", parsed.netloc, path, "", "", "")
        )
    return url


def _pick_stream(info: dict) -> Optional[str]:
    stream = info.get("url")
    if stream:
        return str(stream)
    formats = info.get("formats") or []
    audio = [
        fmt
        for fmt in formats
        if fmt.get("acodec") not in (None, "none")
        and fmt.get("vcodec") in (None, "none")
        and fmt.get("url")
    ]
    audio.sort(
        key=lambda fmt: (
            1 if "m3u8" in str(fmt.get("protocol", "")) else 0,
            fmt.get("abr") or fmt.get("tbr") or 0,
        ),
        reverse=True,
    )
    return str(audio[0]["url"]) if audio else None


def _fetch_thumbnail(url: Optional[str], headers: dict[str, str]) -> Optional[bytes]:
    if not url:
        return None
    try:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=10) as response:
            data = response.read(4 * 1024 * 1024)
        return data or None
    except Exception:
        return None


def resolve_live(url: str) -> LiveStreamInfo:
    """Resolve a live watch/channel URL. Raises NotLiveError when offline."""
    source_url = normalize_live_url(url)
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "format": "bestaudio/best",
        "socket_timeout": 30,
        "retries": 2,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(source_url, download=False)
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc
    if not info:
        raise RuntimeError("YouTube returned no stream information")
    if info.get("entries"):
        info = next((entry for entry in info["entries"] if entry), info)

    live = bool(info.get("is_live")) or info.get("live_status") == "is_live"
    if not live:
        raise NotLiveError("This channel is not live right now")
    stream_url = _pick_stream(info)
    if not stream_url:
        raise RuntimeError("No live audio stream was found")
    headers = {
        str(key): str(value)
        for key, value in (info.get("http_headers") or {}).items()
    }
    thumbnail = info.get("thumbnail")
    return LiveStreamInfo(
        id=str(info.get("id") or ""),
        title=str(info.get("title") or "YouTube Live"),
        artist=str(info.get("uploader") or info.get("channel") or "YouTube Live"),
        watch_url=str(info.get("webpage_url") or source_url),
        stream_url=stream_url,
        http_headers=headers,
        thumbnail=thumbnail,
        thumbnail_data=_fetch_thumbnail(thumbnail, headers),
        is_live=True,
    )


class LiveResolveThread(QThread):
    """Resolve a live URL off the GUI thread."""

    ready = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, url: str, parent=None) -> None:
        super().__init__(parent)
        self._url = url

    def run(self) -> None:
        try:
            info = resolve_live(self._url)
        except NotLiveError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"Could not open live stream: {exc}")
        else:
            self.ready.emit(info)
