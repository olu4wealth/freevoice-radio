"""YouTube audio downloader for Freevoice Radio.

Uses yt-dlp to fetch audio-only streams from YouTube in two modes:

  * download  - save the audio to disk (MP3/WAV/FLAC/M4A) for offline looping
  * stream    - same download, but the file is treated as a temp file and is
                deleted by the audio engine once it has been played

The downloader reports real byte-based progress and tells the UI when the
post-processing (ffmpeg extraction) phase starts, so a large track no
longer looks frozen at 100%.
"""

from __future__ import annotations

import glob
import json
import os
import re
import threading
from dataclasses import dataclass
from typing import Callable, Optional

import yt_dlp
from PyQt6.QtCore import QThread, pyqtSignal

from src.app_paths import ffmpeg_dir

# Raw containers that may be left behind by the audio conversion.
SOURCE_EXTS = ("webm", "m4a", "mp4", "opus", "ogg", "aac")
AUDIO_EXTS = ("mp3", "wav", "flac", "m4a", "ogg", "opus", "aac")

# Maps YouTube video id -> file name inside the download folder.  Keeping
# this lets the app use readable title-based file names while still finding
# an already-downloaded video instantly.
INDEX_FILENAME = ".freevoice_index.json"

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class DownloadCancelled(Exception):
    """Raised inside a yt-dlp hook when the user cancels a download."""


@dataclass
class YouTubeTrack:
    id: str
    title: str
    artist: str
    duration: int          # seconds
    file_path: Optional[str] = None   # downloaded file (download mode)
    stream_url: Optional[str] = None  # direct URL (stream mode)
    thumbnail: Optional[str] = None
    source: str = "youtube"


class DownloadThread(QThread):
    progress = pyqtSignal(dict)
    status = pyqtSignal(str)
    completed = pyqtSignal(object)
    error = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, downloader: "YouTubeDownloader", url: str) -> None:
        super().__init__()
        self._downloader = downloader
        self._url = url
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    def run(self) -> None:
        try:
            self.status.emit("Resolving video info...")
            track = self._downloader.download(
                self._url,
                self.progress.emit,
                self.status.emit,
                cancel_event=self._cancel_event,
            )
            if track is not None and track.file_path:
                self.completed.emit(track)
            else:
                self.error.emit("Download failed: no audio file was produced")
        except DownloadCancelled:
            self.cancelled.emit()
        except Exception as exc:  # surfaced in the UI by the caller
            print(f"[yt-dlp] download thread error: {exc}")
            self.error.emit(str(exc))


class YouTubeDownloader:
    def __init__(self, download_path: str = "downloads", audio_format: str = "mp3") -> None:
        self.download_path = download_path
        self.audio_format = audio_format
        os.makedirs(download_path, exist_ok=True)
        self._lock = threading.Lock()
        self._on_progress: Optional[Callable[[str, float], None]] = None
        self._on_complete: Optional[Callable[[YouTubeTrack], None]] = None
        self._index_path = os.path.join(download_path, INDEX_FILENAME)
        self._index: dict[str, str] = self._load_index()

    # ------------------------------------------------------------------
    # Callbacks (kept for API compatibility)
    # ------------------------------------------------------------------
    def on_progress(self, callback: Callable[[str, float], None]) -> None:
        self._on_progress = callback

    def on_complete(self, callback: Callable[[YouTubeTrack], None]) -> None:
        self._on_complete = callback

    # ------------------------------------------------------------------
    # yt-dlp options
    # ------------------------------------------------------------------
    def _base_opts(self) -> dict:
        opts: dict = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,          # never pull an entire playlist by accident
            "noprogress": True,
            "retries": 3,
            "fragment_retries": 3,
            "socket_timeout": 30,
            "ignoreerrors": False,
        }
        location = ffmpeg_dir()
        if location:
            opts["ffmpeg_location"] = location
        return opts

    # ------------------------------------------------------------------
    # Resolve info (metadata only, no download)
    # ------------------------------------------------------------------
    def _extract_info(self, url: str) -> Optional[dict]:
        """Fetch video metadata (no media download)."""
        opts = self._base_opts()
        opts.update({"skip_download": True, "extract_flat": False, "playlistend": 1})
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    return None
                if "entries" in info:  # playlist/channel URL: take the first video
                    entries = [e for e in (info.get("entries") or []) if e]
                    if not entries:
                        return None
                    info = entries[0]
                return info
        except Exception as exc:
            print(f"[yt-dlp] resolve error: {exc}")
            return None

    def resolve_info(self, url: str) -> Optional[YouTubeTrack]:
        """Extract metadata for a YouTube URL without downloading."""
        info = self._extract_info(url)
        return self._info_to_track(info) if info else None

    # ------------------------------------------------------------------
    # Download audio
    # ------------------------------------------------------------------
    def download(
        self,
        url: str,
        progress_callback: Optional[Callable[[dict], None]] = None,
        status_callback: Optional[Callable[[str], None]] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> Optional[YouTubeTrack]:
        """Download audio-only from a YouTube URL and return a YouTubeTrack.

        Raises ``DownloadCancelled`` when ``cancel_event`` is set, and
        ``RuntimeError`` with a readable message on other failures.
        """

        def _status(message: str) -> None:
            if status_callback:
                status_callback(message)

        def _progress(data: dict) -> None:
            if progress_callback:
                progress_callback(data)

        def _check_cancel() -> None:
            if cancel_event is not None and cancel_event.is_set():
                raise DownloadCancelled()

        _status("Resolving video info...")
        info = self._extract_info(url)
        _check_cancel()
        if not info:
            raise RuntimeError(
                "Could not read this YouTube URL. Check the link, or update "
                "yt-dlp (the site changes often)."
            )
        track = self._info_to_track(info)

        os.makedirs(self.download_path, exist_ok=True)

        existing = self._find_audio_file(track.id)
        if existing:
            track.file_path = self._migrate_legacy_name(existing, track)
            _progress({"percent": 100, "downloaded": 1, "total": 1, "phase": "done"})
            _status("Already downloaded")
            return track

        # Name the file after the video title (collisions get " (2)").
        base = self._unique_basename(track.title, track.id)
        outtmpl = os.path.join(
            self.download_path, base.replace("%", "%%") + ".%(ext)s"
        )

        def _progress_hook(data: dict) -> None:
            _check_cancel()
            if data.get("status") != "downloading":
                return
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            downloaded = data.get("downloaded_bytes") or 0
            percent = int(downloaded * 100 / total) if total else 0
            _progress(
                {
                    "percent": max(0, min(percent, 100)),
                    "downloaded": downloaded,
                    "total": total,
                    "phase": "download",
                }
            )

        def _postprocessor_hook(data: dict) -> None:
            _check_cancel()
            if data.get("status") in ("started", "processing"):
                _progress(
                    {
                        "percent": 100,
                        "downloaded": 1,
                        "total": 1,
                        "phase": "convert",
                    }
                )
                _status(
                    f"Converting to {self.audio_format.upper()} (this can take a moment)..."
                )

        opts = self._base_opts()
        opts.update(
            {
                "format": "bestaudio/best",
                "outtmpl": outtmpl,
                "windowsfilenames": True,
                "progress_hooks": [_progress_hook],
                "postprocessor_hooks": [_postprocessor_hook],
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": self.audio_format,
                        "preferredquality": "192",
                    }
                ],
            }
        )

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except DownloadCancelled:
            raise
        except Exception as exc:
            raise RuntimeError(f"Download failed: {exc}") from exc

        _check_cancel()
        _progress({"percent": 100, "downloaded": 1, "total": 1, "phase": "done"})
        _status("Download complete")

        file_path = self._find_file_by_base(base)
        if not file_path:
            raise RuntimeError(
                "Download finished but no audio file was created. "
                "Is ffmpeg installed / bundled?"
            )

        self._remove_source_leftovers(base, file_path)
        self._index[track.id] = os.path.basename(file_path)
        self._save_index()

        track.file_path = file_path
        if self._on_complete:
            self._on_complete(track)
        return track

    # ------------------------------------------------------------------
    # File naming / lookup helpers
    # ------------------------------------------------------------------
    def _load_index(self) -> dict[str, str]:
        try:
            with open(self._index_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                return {
                    str(key): str(value)
                    for key, value in data.items()
                    if value and os.path.basename(str(value)) == str(value)
                }
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        return {}

    def _save_index(self) -> None:
        try:
            tmp = self._index_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(self._index, handle, indent=2, ensure_ascii=False)
            os.replace(tmp, self._index_path)
        except OSError as exc:
            print(f"[downloads] could not save index: {exc}")

    @staticmethod
    def _safe_title(title: str, fallback: str) -> str:
        """Turn a video title into a valid Windows file name."""
        text = _INVALID_FILENAME_CHARS.sub(" ", str(title or ""))
        text = re.sub(r"\s+", " ", text).strip(" .")
        if not text:
            text = fallback or "track"
        if text.upper().split(".")[0] in _RESERVED_NAMES:
            text = "_" + text
        # Keep paths comfortably below the Windows 260-char limit.
        return text[:120].rstrip(" .")

    def _unique_basename(self, title: str, video_id: str) -> str:
        """Return a title-based base name that does not clash on disk."""
        base = self._safe_title(title, video_id)
        used = {
            os.path.normcase(os.path.splitext(name)[0])
            for name in self._index.values()
        }
        candidate = base
        counter = 2
        known_exts = tuple(dict.fromkeys(AUDIO_EXTS + SOURCE_EXTS))
        while True:
            if os.path.normcase(candidate) not in used and not any(
                os.path.isfile(os.path.join(self.download_path, f"{candidate}.{ext}"))
                for ext in known_exts
            ):
                return candidate
            candidate = f"{base} ({counter})"
            counter += 1

    def _find_file_by_base(self, base: str) -> Optional[str]:
        for ext in (self.audio_format,) + AUDIO_EXTS:
            candidate = os.path.join(self.download_path, f"{base}.{ext}")
            if os.path.isfile(candidate) and os.path.getsize(candidate) > 0:
                return candidate
        pattern = glob.escape(os.path.join(self.download_path, base)) + ".*"
        for path in glob.glob(pattern):
            if not path.lower().endswith(AUDIO_EXTS):
                continue
            if os.path.isfile(path) and os.path.getsize(path) > 0:
                return path
        return None

    def _migrate_legacy_name(self, path: str, track: YouTubeTrack) -> str:
        """Rename an old ``<video-id>.mp3`` file to ``<title>.mp3``."""
        stem, ext = os.path.splitext(os.path.basename(path))
        if stem != track.id:
            return path
        new_base = self._unique_basename(track.title, track.id)
        if new_base == stem:
            return path
        new_path = os.path.join(self.download_path, new_base + ext)
        try:
            os.replace(path, new_path)
        except OSError:
            return path
        self._index[track.id] = os.path.basename(new_path)
        self._save_index()
        return new_path

    def forget_file(self, path: str) -> int:
        """Drop index entries that refer to ``path`` (after a file delete)."""
        name = os.path.basename(path)
        stale = [key for key, value in self._index.items() if value == name]
        for key in stale:
            self._index.pop(key, None)
        if stale:
            self._save_index()
        return len(stale)

    def _find_audio_file(self, video_id: str) -> Optional[str]:
        """Find the converted audio file for a video id."""
        if not video_id:
            return None

        indexed = self._index.get(video_id)
        if indexed:
            candidate = os.path.join(self.download_path, indexed)
            if os.path.isfile(candidate) and os.path.getsize(candidate) > 0:
                return candidate
            self._index.pop(video_id, None)

        # Legacy builds stored files as <video-id>.<ext>.
        for ext in (self.audio_format,) + AUDIO_EXTS:
            candidate = os.path.join(self.download_path, f"{video_id}.{ext}")
            if os.path.isfile(candidate) and os.path.getsize(candidate) > 0:
                return candidate
        pattern = glob.escape(os.path.join(self.download_path, video_id)) + ".*"
        for path in glob.glob(pattern):
            if not path.lower().endswith(AUDIO_EXTS):
                continue
            if os.path.isfile(path) and os.path.getsize(path) > 0:
                return path
        return None

    def _remove_source_leftovers(self, base: str, keep_path: str) -> None:
        """Delete the raw downloaded container once conversion succeeded."""
        pattern = glob.escape(os.path.join(self.download_path, base)) + ".*"
        for path in glob.glob(pattern):
            if os.path.normcase(path) == os.path.normcase(keep_path):
                continue
            ext = os.path.splitext(path)[1].lower().lstrip(".")
            if ext not in SOURCE_EXTS:
                continue
            try:
                os.remove(path)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Download in background thread (plain threading API, kept for compat)
    # ------------------------------------------------------------------
    def download_async(self, url: str) -> threading.Thread:
        def _run() -> None:
            try:
                self.download(url)
            except Exception as exc:
                print(f"[yt-dlp] async download error: {exc}")

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return thread

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _info_to_track(self, info: dict) -> YouTubeTrack:
        return YouTubeTrack(
            id=str(info.get("id", "")),
            title=info.get("title", "Unknown"),
            artist=info.get("uploader") or info.get("channel") or "Unknown",
            duration=int(info.get("duration", 0) or 0),
            thumbnail=info.get("thumbnail"),
            source="youtube",
        )
