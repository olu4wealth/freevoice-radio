"""Background scheduler for Freevoice Radio.

Polls enabled YouTube channels on a configurable interval and
auto-enqueues new videos into the playlist.  Runs in a separate
thread so it never blocks the GUI.
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Optional

import schedule


class ChannelUpdater:
    def __init__(
        self,
        config,
        channel_scraper,
        youtube_downloader=None,
        audio_engine=None,
        on_new_track: Optional[Callable[[str], None]] = None,
        on_videos_found: Optional[Callable[[list, str], None]] = None,
    ) -> None:
        self.config = config
        self.scraper = channel_scraper
        self.downloader = youtube_downloader
        self.engine = audio_engine
        # NOTE: these callbacks are invoked from the scheduler thread.  The
        # GUI passes Qt signals' .emit here so the slot runs on the GUI thread.
        self._on_new_track = on_new_track
        self._on_videos_found = on_videos_found

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._scheduled_jobs: list = []

    # ------------------------------------------------------------------
    # Start / stop
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._schedule_jobs()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        for job in self._scheduled_jobs:
            try:
                schedule.cancel_job(job)
            except Exception:
                pass
        self._scheduled_jobs.clear()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------
    def _schedule_jobs(self) -> None:
        if not self.config.scheduler_enabled:
            return
        interval = max(1, int(self.config.scheduler_interval_minutes))
        job = schedule.every(interval).minutes.do(self._run_maintenance)
        self._scheduled_jobs.append(job)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                schedule.run_pending()
            except Exception as exc:  # keep the scheduler alive
                print(f"[scheduler] loop error: {exc}")
            if self._stop_event.wait(5):
                break

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------
    def _poll_all_channels(self) -> None:
        if not self.config.scheduler_enabled:
            return
        for channel in list(self.config.channels):
            if not channel.get("enabled", False):
                continue
            self._poll_channel(channel)
        self.config.save()

    def _poll_channel(self, channel: dict) -> None:
        channel_url = channel.get("url") or ""
        if not channel_url:
            return
        try:
            videos = self.scraper.fetch_videos(channel_url)
        except Exception as exc:
            print(f"[scheduler] error fetching {channel_url}: {exc}")
            return

        if not videos:
            return

        channel["last_checked"] = datetime.now().strftime("%Y%m%d%H%M%S")

        max_videos = int(channel.get("max_videos_per_fetch") or 10)
        new_videos = []
        for video in videos[:max_videos]:
            if self._stop_event.is_set():
                break
            # Never queue something that is already on disk.
            if self.downloader is not None and self.downloader._find_audio_file(
                video.id
            ):
                continue
            new_videos.append(video)

        if new_videos and self._on_videos_found is not None:
            # The GUI enqueues these into the download queue.
            self._on_videos_found(new_videos, channel_url)
            print(f"[scheduler] queued {len(new_videos)} video(s) from {channel_url}")

    # ------------------------------------------------------------------
    # Auto-cleanup: delete old downloaded files not in the playlist
    # ------------------------------------------------------------------
    def _cleanup_old_downloads(self, max_age_hours: int = 48) -> None:
        """Delete downloaded files older than max_age_hours that are not
        currently in the playlist.  Keeps disk usage bounded."""
        download_path = self.config.download_path
        if not download_path or not os.path.isdir(download_path):
            return

        playlist_paths = {os.path.normcase(p) for p in self.engine.playlist()}
        cutoff = datetime.now() - timedelta(hours=max_age_hours)

        removed = 0
        for name in os.listdir(download_path):
            path = os.path.join(download_path, name)
            if not os.path.isfile(path):
                continue
            if os.path.normcase(path) in playlist_paths:
                continue
            try:
                modified = datetime.fromtimestamp(os.path.getmtime(path))
                if modified < cutoff:
                    os.remove(path)
                    removed += 1
            except OSError:
                pass

        if removed:
            print(f"[scheduler] cleaned up {removed} old download(s)")

    def _run_maintenance(self) -> None:
        """Run all periodic maintenance tasks."""
        self._poll_all_channels()
        self._cleanup_old_downloads()
