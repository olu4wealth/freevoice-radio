"""YouTube channel scraper for Freevoice Radio.

Given a YouTube channel URL, fetches the list of videos (with metadata)
so they can be enqueued into the playlist.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import yt_dlp

VIDEO_ID_RE = re.compile(
    r"(?:youtu\.be/|youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|live/))([\w-]{11})"
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


class ChannelScraper:
    def __init__(self, max_videos: int = 10) -> None:
        self.max_videos = max(1, int(max_videos))

    def _ydl_opts(self) -> dict:
        return {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "playlistend": self.max_videos,
            "retries": 2,
            "socket_timeout": 30,
        }

    def fetch_videos(self, channel_url: str) -> list[ChannelVideo]:
        """Return up to max_videos from the given channel (or video) URL."""
        # A single video URL is not a channel, but users paste those too.
        single_id = video_id_from_url(channel_url)
        if single_id:
            track = self._fetch_single(single_id, channel_url)
            return [track] if track else []

        try:
            with yt_dlp.YoutubeDL(self._ydl_opts()) as ydl:
                info = ydl.extract_info(channel_url, download=False)
        except Exception as exc:
            print(f"[channel_scraper] error: {exc}")
            return []

        if not info:
            return []
        if "entries" not in info:
            track = self._entry_to_video(info)
            return [track] if track else []

        videos: list[ChannelVideo] = []
        seen: set[str] = set()
        for entry in info.get("entries") or []:
            if not entry:
                continue
            video = self._entry_to_video(entry)
            if not video or video.id in seen:
                continue
            seen.add(video.id)
            videos.append(video)
            if len(videos) >= self.max_videos:
                break
        return videos

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
        if video_id and len(video_id) == 11 and not video_id_from_url(url):
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
