"""YouTube channel scraper for Freevoice Radio.

Given a YouTube channel URL, fetches the list of videos (with metadata)
so they can be enqueued into the download queue.

YouTube returns *tab playlists* (Videos / Live / Shorts) for a channel root
URL.  We normalise the URL to the Videos tab and also handle the tab entries
defensively, so the result is always actual videos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, urlunparse

import yt_dlp

VIDEO_ID_RE = re.compile(
    r"(?:youtu\.be/|youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|live/))([\w-]{11})"
)

# Path suffixes that are already a specific channel tab.
_TAB_SUFFIXES = (
    "/videos",
    "/streams",
    "/shorts",
    "/playlists",
    "/featured",
    "/about",
    "/community",
    "/podcasts",
)


@dataclass
class ChannelVideo:
    id: str
    title: str
    url: str
    duration: int       # seconds
    upload_date: Optional[str]  # YYYYMMDD or None
    thumbnail: Optional[str]


def video_id_from_url(url: str) -> Optional[str]:
    """Extract a YouTube video id from a watch/short/youtu.be URL."""
    if not url:
        return None
    match = VIDEO_ID_RE.search(url)
    return match.group(1) if match else None


def watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def normalize_channel_url(url: str) -> str:
    """Point a channel root URL at its Videos tab.

    ``youtube.com/@name``, ``/channel/UC…``, ``/c/…`` and ``/user/…`` are
    normalised to ``…/videos``.  Playlist, video and tab URLs are unchanged.
    """
    if not url:
        return url
    url = url.strip()
    if video_id_from_url(url):
        return url
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url

    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if "youtube.com" not in host:
        return url

    path = parsed.path.rstrip("/")
    if path.endswith(_TAB_SUFFIXES):
        return url

    if path.startswith(("/@", "/channel/", "/c/", "/user/")) or not path:
        return urlunparse(
            (
                parsed.scheme or "https",
                parsed.netloc,
                path + "/videos",
                "",
                "",
                "",
            )
        )
    return url


class ChannelScraper:
    def __init__(self, max_videos: int = 10) -> None:
        self.max_videos = max(1, int(max_videos))

    def _ydl_opts(self, limit: int) -> dict:
        return {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "playlistend": limit,
            "retries": 2,
            "socket_timeout": 30,
        }

    def fetch_videos(
        self, channel_url: str, max_videos: Optional[int] = None
    ) -> list[ChannelVideo]:
        """Return up to ``max_videos`` newest videos from a channel.

        Already-live/upcoming entries are skipped; the caller filters out
        videos that are already downloaded.
        """
        limit = max(1, int(max_videos if max_videos is not None else self.max_videos))

        # A single video URL is not a channel, but users paste those too.
        single_id = video_id_from_url(channel_url)
        if single_id:
            track = self._fetch_single(single_id, channel_url)
            return [track] if track else []

        url = normalize_channel_url(channel_url)
        info = self._extract(url, limit)
        if not info:
            return []

        entries = [entry for entry in (info.get("entries") or []) if entry]
        # A channel root can return tab playlists instead of videos.  Follow
        # the Videos tab if that happened.
        if entries and all(
            entry.get("_type") == "playlist" for entry in entries if entry
        ):
            tab_url = self._videos_tab_url(entries)
            if tab_url:
                info = self._extract(tab_url, limit)
                entries = [entry for entry in (info.get("entries") or []) if entry]

        if "entries" not in info:
            track = self._entry_to_video(info)
            return [track] if track else []

        videos: list[ChannelVideo] = []
        seen: set[str] = set()
        for entry in entries:
            video = self._entry_to_video(entry)
            if not video or video.id in seen:
                continue
            seen.add(video.id)
            videos.append(video)
            if len(videos) >= limit:
                break
        return videos

    def _extract(self, url: str, limit: int) -> Optional[dict]:
        try:
            with yt_dlp.YoutubeDL(self._ydl_opts(limit)) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception as exc:
            print(f"[channel_scraper] error: {exc}")
            return None

    @staticmethod
    def _videos_tab_url(entries: list[dict]) -> Optional[str]:
        for entry in entries:
            title = (entry.get("title") or "").lower()
            candidate = entry.get("webpage_url") or entry.get("url") or ""
            if "video" in title or "/videos" in candidate:
                return candidate or None
        return None

    def _fetch_single(self, video_id: str, original_url: str) -> Optional[ChannelVideo]:
        url = watch_url(video_id)
        title, duration, upload_date, thumbnail = "Unknown", 0, None, None
        try:
            with yt_dlp.YoutubeDL(
                {"quiet": True, "no_warnings": True, "skip_download": True}
            ) as ydl:
                info = ydl.extract_info(url, download=False) or {}
            title = info.get("title") or title
            duration = int(info.get("duration") or 0)
            upload_date = info.get("upload_date")
            thumbnail = info.get("thumbnail")
        except Exception as exc:
            print(f"[channel_scraper] single video metadata error: {exc}")
        return ChannelVideo(
            id=video_id,
            title=title,
            url=url,
            duration=duration,
            upload_date=upload_date,
            thumbnail=thumbnail,
        )

    def _entry_to_video(self, entry: dict) -> Optional[ChannelVideo]:
        video_id = str(entry.get("id") or "")
        url = entry.get("url") or entry.get("webpage_url") or ""

        # extract_flat often returns just the id in `url`.
        if not video_id and url:
            video_id = video_id_from_url(url) or ""
        if not re.fullmatch(r"[\w-]{11}", video_id):
            # Playlist/tab/channel entries are not videos.
            return None
        if not video_id_from_url(url):
            url = watch_url(video_id)
        if not video_id or not url:
            return None

        live_status = entry.get("live_status")
        if live_status in ("is_live", "is_upcoming"):
            return None

        return ChannelVideo(
            id=video_id,
            title=entry.get("title") or "Unknown",
            url=url,
            duration=int(entry.get("duration") or 0),
            upload_date=entry.get("upload_date"),
            thumbnail=entry.get("thumbnail"),
        )
