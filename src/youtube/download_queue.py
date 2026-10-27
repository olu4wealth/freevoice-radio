"""Sequential download queue for Freevoice Radio.

One yt-dlp download runs at a time (YouTube throttles parallel downloads and
the conversions are CPU heavy).  Items can be cancelled, retried, removed and
the finished ones cleared.  The queue never blocks the GUI: each item runs in
its own :class:`DownloadThread`.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from src.youtube.downloader import DownloadThread, YouTubeDownloader, YouTubeTrack

QUEUED = "Queued"
RESOLVING = "Resolving"
DOWNLOADING = "Downloading"
CONVERTING = "Converting"
CANCELLING = "Cancelling"
DONE = "Done"
FAILED = "Failed"
CANCELLED = "Cancelled"

ACTIVE_STATUSES = (RESOLVING, DOWNLOADING, CONVERTING, CANCELLING)
FINISHED_STATUSES = (DONE, FAILED, CANCELLED)


@dataclass
class QueueItem:
    url: str
    title: str
    source: str          # url | channel | scheduler
    stream: bool
    uid: int
    status: str = QUEUED
    percent: int = 0
    detail: str = ""
    error: str = ""
    track: Optional[YouTubeTrack] = None

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES


class DownloadQueue(QObject):
    changed = pyqtSignal()                 # items added/removed
    item_updated = pyqtSignal(object)      # QueueItem
    item_finished = pyqtSignal(object, object)  # QueueItem, YouTubeTrack
    active_changed = pyqtSignal(bool)

    def __init__(self, downloader: YouTubeDownloader, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._downloader = downloader
        self.items: list[QueueItem] = []
        self._ids = itertools.count(1)
        self._thread: Optional[DownloadThread] = None
        self._current: Optional[QueueItem] = None
        self._cancel_requested = False
        self._remove_after_stop: Optional[QueueItem] = None
        self._stopping = False

    # ------------------------------------------------------------------
    # Queue management
    # ------------------------------------------------------------------
    def add(
        self,
        url: str,
        title: str = "",
        source: str = "url",
        stream: bool = False,
        front: bool = False,
    ) -> Optional[QueueItem]:
        url = (url or "").strip()
        if not url:
            return None
        for item in self.items:
            if item.url == url and (item.status in ACTIVE_STATUSES or item.status == QUEUED):
                return item

        item = QueueItem(
            url=url,
            title=title or "YouTube video",
            source=source,
            stream=stream,
            uid=next(self._ids),
        )
        if front:
            self.items.insert(0, item)
        else:
            self.items.append(item)
        self.changed.emit()
        self._start_next()
        return item

    def retry(self, item: QueueItem) -> None:
        if item.status not in (FAILED, CANCELLED):
            return
        item.status = QUEUED
        item.percent = 0
        item.detail = "Queued again"
        item.error = ""
        item.track = None
        self.item_updated.emit(item)
        self._start_next()

    def remove(self, item: QueueItem) -> None:
        if item is self._current and self._thread is not None:
            self._remove_after_stop = item
            self.cancel_current()
            return
        if item in self.items:
            self.items.remove(item)
            self.changed.emit()
            self._emit_active()

    def cancel_current(self) -> None:
        if self._thread is None or self._current is None:
            return
        self._cancel_requested = True
        self._current.status = CANCELLING
        self._current.detail = "Cancelling…"
        self.item_updated.emit(self._current)
        self._thread.cancel()

    def clear_finished(self) -> None:
        self.items = [item for item in self.items if item.status not in FINISHED_STATUSES]
        self.changed.emit()

    def stop(self) -> None:
        self._stopping = True
        if self._thread is not None:
            self._thread.cancel()
            self._thread.wait(3000)
            self._thread = None
        self._current = None
        self.items.clear()

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------
    def is_active(self) -> bool:
        return self._thread is not None

    def current_item(self) -> Optional[QueueItem]:
        return self._current if self._current and self._current.is_active else None

    def pending_count(self) -> int:
        return sum(1 for item in self.items if item.status == QUEUED)

    def active_count(self) -> int:
        return sum(1 for item in self.items if item.is_active)

    def item_by_uid(self, uid: int) -> Optional[QueueItem]:
        return next((item for item in self.items if item.uid == uid), None)

    # ------------------------------------------------------------------
    # Worker lifecycle
    # ------------------------------------------------------------------
    def _start_next(self) -> None:
        if self._thread is not None or self._stopping:
            return
        item = next((i for i in self.items if i.status == QUEUED), None)
        if item is None:
            self._emit_active()
            return

        self._current = item
        self._cancel_requested = False
        item.status = RESOLVING
        item.percent = 0
        item.detail = "Resolving video info…"
        self.item_updated.emit(item)

        thread = DownloadThread(self._downloader, item.url)
        thread.progress.connect(lambda data, it=item: self._on_progress(it, data))
        thread.status.connect(lambda message, it=item: self._on_status(it, message))
        thread.completed.connect(lambda track, it=item: self._on_completed(it, track))
        thread.error.connect(lambda message, it=item: self._on_error(it, message))
        thread.cancelled.connect(lambda it=item: self._on_cancelled(it))
        thread.finished.connect(lambda it=item: self._on_thread_finished(it))
        self._thread = thread
        self._emit_active()
        thread.start()

    def _on_progress(self, item: QueueItem, data: dict) -> None:
        phase = data.get("phase")
        if phase == "convert":
            item.status = CONVERTING
            item.percent = 100
            item.detail = "Converting audio…"
        elif phase == "done":
            item.status = CONVERTING
            item.percent = 100
            item.detail = "Finishing…"
        else:
            item.status = DOWNLOADING
            item.percent = int(data.get("percent") or 0)
            item.detail = f"{item.percent}%"
        self.item_updated.emit(item)

    def _on_status(self, item: QueueItem, message: str) -> None:
        item.detail = message
        self.item_updated.emit(item)

    def _on_completed(self, item: QueueItem, track: YouTubeTrack) -> None:
        item.status = DONE
        item.percent = 100
        item.detail = "Ready"
        item.error = ""
        item.track = track
        if track and track.title:
            item.title = track.title
        self.item_updated.emit(item)
        self.item_finished.emit(item, track)

    def _on_error(self, item: QueueItem, message: str) -> None:
        if self._cancel_requested:
            self._on_cancelled(item)
            return
        item.status = FAILED
        item.error = message
        item.detail = message
        self.item_updated.emit(item)

    def _on_cancelled(self, item: QueueItem) -> None:
        item.status = CANCELLED
        item.detail = "Cancelled"
        item.percent = 0
        self.item_updated.emit(item)

    def _on_thread_finished(self, item: QueueItem) -> None:
        thread = self._thread
        if thread is not None:
            thread.deleteLater()
        self._thread = None
        self._current = None
        self._cancel_requested = False

        if self._remove_after_stop is not None:
            removed = self._remove_after_stop
            self._remove_after_stop = None
            if removed in self.items:
                self.items.remove(removed)
            self.changed.emit()

        self._emit_active()
        if not self._stopping:
            # Let the finished thread settle before starting the next one.
            QTimer.singleShot(0, self._start_next)

    def _emit_active(self) -> None:
        self.active_changed.emit(self.is_active())
