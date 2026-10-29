"""QtMultimedia player for live HLS audio via the localhost proxy."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer

from src.youtube.live import LiveStreamInfo
from src.youtube.live_proxy import LiveProxyServer


class LivePlayer(QObject):
    state_changed = pyqtSignal()
    error = pyqtSignal(str)
    ended = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)
        self._proxy: Optional[LiveProxyServer] = None
        self._info: Optional[LiveStreamInfo] = None
        self._stopping = False
        self._pause_requested = False

        self._player.errorOccurred.connect(self._on_error)
        self._player.playbackStateChanged.connect(self._on_state)
        self._player.mediaStatusChanged.connect(self._on_status)

    @property
    def info(self) -> Optional[LiveStreamInfo]:
        return self._info

    def play_info(self, info: LiveStreamInfo) -> None:
        self.stop()
        self._info = info
        self._pause_requested = False
        self._proxy = LiveProxyServer(info.stream_url, info.http_headers)
        self._player.setSource(QUrl(self._proxy.local_url))
        self._player.play()

    def stop(self) -> None:
        self._stopping = True
        try:
            self._player.stop()
            self._player.setSource(QUrl())
        finally:
            self._stopping = False
        self._pause_requested = False
        if self._proxy is not None:
            self._proxy.stop()
            self._proxy = None

    def pause(self) -> None:
        if self.is_playing():
            self._pause_requested = True
            self._player.pause()

    def resume(self) -> None:
        if self._proxy is not None:
            self._pause_requested = False
            self._player.play()

    def toggle(self) -> None:
        if self.is_playing():
            self.pause()
        elif self.is_paused():
            self.resume()
        elif self._proxy is not None:
            self._pause_requested = False
            self._player.play()

    def is_playing(self) -> bool:
        return (
            self._player.playbackState()
            == QMediaPlayer.PlaybackState.PlayingState
        )

    def is_paused(self) -> bool:
        return self._pause_requested and (
            self._player.playbackState()
            == QMediaPlayer.PlaybackState.PausedState
        )

    def position(self) -> float:
        return self._player.position() / 1000.0

    def set_volume(self, volume: int) -> None:
        self._audio.setVolume(max(0.0, min(1.0, volume / 100.0)))

    def _on_error(self, _error, message: str) -> None:
        if not self._stopping:
            self.error.emit(message or "Live stream error")

    def _on_state(self, _state) -> None:
        self.state_changed.emit()

    def _on_status(self, status) -> None:
        if self._stopping or self._player.source().isEmpty():
            return
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.ended.emit()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self.error.emit("The live stream could not be opened")
