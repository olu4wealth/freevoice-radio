"""Audio backends for Freevoice Radio.

The playback backend is built on QtMultimedia (``QMediaPlayer``).  Unlike
``pygame.mixer.Sound`` -- which decodes an entire file into RAM and dies
with "Out of memory" on long radio sets -- QtMultimedia streams from disk
and decodes on the fly, so a multi-hour MP3 uses almost no memory.

Two players are kept so consecutive tracks can crossfade.  The backend is
a ``QObject`` and emits Qt signals, which means the engine's callbacks run
on the GUI thread and no polling thread is needed.
"""

from __future__ import annotations

import os
import time
from typing import Callable, Optional

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal


MIN_FADE_MS = 50


class MediaBackend(QObject):
    """Streaming audio backend with crossfade support."""

    track_finished = pyqtSignal()
    playback_error = pyqtSignal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

        from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer

        self._players: list[QMediaPlayer] = []
        self._outputs: list[QAudioOutput] = []
        for _ in range(2):
            player = QMediaPlayer(self)
            output = QAudioOutput(self)
            player.setAudioOutput(output)
            self._players.append(player)
            self._outputs.append(output)

        self._active = 0
        self._volume = 70  # 0-100
        self._on_finished: Optional[Callable[[], None]] = None
        self._is_active_started = False
        self._fade: Optional[dict] = None
        self._temp_files: list[str] = []

        self._silence_timer = QTimer(self)
        self._silence_timer.setSingleShot(True)
        self._silence_timer.timeout.connect(self._on_silence_done)

        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(40)
        self._fade_timer.timeout.connect(self._tick_fade)

        for index, player in enumerate(self._players):
            player.mediaStatusChanged.connect(
                lambda status, i=index: self._on_media_status(i, status)
            )
            player.errorOccurred.connect(
                lambda error, message, i=index: self._on_error(i, error, message)
            )
            self._outputs[index].setVolume(self._volume / 100.0)

    # ------------------------------------------------------------------
    # Properties / state
    # ------------------------------------------------------------------
    @property
    def _player(self):
        return self._players[self._active]

    @property
    def _output(self):
        return self._outputs[self._active]

    @property
    def _target_volume(self) -> float:
        return self._volume / 100.0

    def is_playing(self) -> bool:
        from PyQt6.QtMultimedia import QMediaPlayer

        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def is_paused(self) -> bool:
        from PyQt6.QtMultimedia import QMediaPlayer

        return self._player.playbackState() == QMediaPlayer.PlaybackState.PausedState

    def has_source(self) -> bool:
        return not self._player.source().isEmpty()

    def get_position(self) -> float:
        return self._player.position() / 1000.0

    def get_duration(self) -> float:
        duration = self._player.duration()
        return duration / 1000.0 if duration and duration > 0 else 0.0

    def set_position(self, seconds: float) -> None:
        """Seek within the current track."""
        if self._player.source().isEmpty():
            return
        duration = self._player.duration()
        position = max(0, int(seconds * 1000))
        if duration and duration > 0:
            position = min(position, duration)
        self._player.setPosition(position)

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------
    def load(self, file_path: str, autoplay: bool = True) -> bool:
        """Point the active player at ``file_path`` and (optionally) play."""
        if not file_path or not os.path.exists(file_path):
            self.playback_error.emit(f"Audio file not found: {file_path}")
            return False
        if not os.path.isfile(file_path):
            self.playback_error.emit(f"Not an audio file: {file_path}")
            return False

        self._silence_timer.stop()
        self._fade_timer.stop()
        self._fade = None
        self._stop_players(clear=True)

        player = self._players[self._active]
        self._outputs[self._active].setVolume(self._target_volume)
        player.setSource(QUrl.fromLocalFile(os.path.abspath(file_path)))
        if autoplay:
            player.play()
            self._is_active_started = True
        return True

    def load_crossfade(self, file_path: str, fade_ms: int = 5000) -> bool:
        """Start ``file_path`` on the spare player while the current track
        fades out over ``fade_ms`` milliseconds."""
        if not file_path or not os.path.exists(file_path):
            self.playback_error.emit(f"Audio file not found: {file_path}")
            return False
        if fade_ms < MIN_FADE_MS or not self.is_playing():
            return self.load(file_path)

        old_index = self._active
        new_index = 1 - old_index
        new_player = self._players[new_index]

        new_player.stop()
        new_player.setSource(QUrl.fromLocalFile(os.path.abspath(file_path)))
        self._outputs[new_index].setVolume(0.0)
        new_player.play()

        self._fade = {
            "old": old_index,
            "new": new_index,
            "started": time.monotonic(),
            "duration": fade_ms / 1000.0,
        }
        self._fade_timer.start()
        return True

    def _tick_fade(self) -> None:
        fade = self._fade
        if not fade:
            self._fade_timer.stop()
            return

        elapsed = time.monotonic() - fade["started"]
        progress = min(1.0, elapsed / max(fade["duration"], 0.001))
        # Read the live volume so slider moves during a fade still apply.
        target = self._target_volume
        self._outputs[fade["old"]].setVolume(target * (1.0 - progress))
        self._outputs[fade["new"]].setVolume(target * progress)

        if progress >= 1.0:
            self._fade_timer.stop()
            self._players[fade["old"]].stop()
            self._active = fade["new"]
            self._outputs[fade["new"]].setVolume(target)
            self._fade = None
            self._is_active_started = True

    def play(self) -> None:
        if self._player.source().isEmpty():
            return
        self._silence_timer.stop()
        self._player.play()
        self._is_active_started = True

    def pause(self) -> None:
        self._player.pause()

    def stop(self) -> None:
        self._silence_timer.stop()
        self._fade_timer.stop()
        self._fade = None
        self._stop_players(clear=True)
        self._is_active_started = False

    def _stop_players(self, clear: bool = False) -> None:
        for index, player in enumerate(self._players):
            player.stop()
            if clear:
                player.setSource(QUrl())
            self._outputs[index].setVolume(self._target_volume)
        self._is_active_started = False

    def set_volume(self, volume: int) -> None:
        """volume: 0-100."""
        self._volume = max(0, min(100, int(volume)))
        if self._fade:
            # The fade timer owns the volumes until it finishes.
            return
        for output in self._outputs:
            output.setVolume(self._target_volume)

    def set_muted(self, muted: bool) -> None:
        for output in self._outputs:
            output.setMuted(muted)

    # ------------------------------------------------------------------
    # Silence between tracks
    # ------------------------------------------------------------------
    def play_silence(self, seconds: float) -> None:
        """Emit ``track_finished`` after ``seconds`` of silence."""
        self._stop_players(clear=True)
        self._is_active_started = True
        self._silence_timer.start(max(1, int(seconds * 1000)))

    def _on_silence_done(self) -> None:
        self._is_active_started = False
        self._emit_finished()

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------
    def set_endevent_callback(self, callback: Callable[[], None]) -> None:
        self._on_finished = callback

    def _emit_finished(self) -> None:
        if self._on_finished:
            self._on_finished()
        self.track_finished.emit()

    def _on_media_status(self, index: int, status) -> None:
        from PyQt6.QtMultimedia import QMediaPlayer

        if status != QMediaPlayer.MediaStatus.EndOfMedia:
            return
        if index != self._active:
            # The faded-out player reached the end of its audio; ignore.
            return
        if not self._is_active_started:
            return
        self._is_active_started = False
        self._emit_finished()

    def _on_error(self, index: int, error, message: str) -> None:
        from PyQt6.QtMultimedia import QMediaPlayer

        if error == QMediaPlayer.Error.NoError:
            return
        # Errors from a player that is being faded out are harmless.
        if self._fade and index == self._fade["old"]:
            return
        self.playback_error.emit(message or "Unknown playback error")

    # ------------------------------------------------------------------
    # Compatibility / cleanup
    # ------------------------------------------------------------------
    def pump_events(self) -> None:
        """No-op: QtMultimedia delivers its signals through the event loop."""

    def get_position_seconds(self) -> float:
        return self.get_position()

    def quit(self) -> None:
        self._silence_timer.stop()
        self._fade_timer.stop()
        self._fade = None
        self._stop_players(clear=True)
        for path in list(self._temp_files):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
        self._temp_files.clear()


class NullBackend(QObject):
    """Fallback used when QtMultimedia is unavailable.

    Keeps the app usable (playlist, downloads, settings) and reports a
    clear error instead of crashing at start-up.
    """

    track_finished = pyqtSignal()
    playback_error = pyqtSignal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._on_finished: Optional[Callable[[], None]] = None
        self._reported = False

    def _unavailable(self) -> bool:
        if not self._reported:
            self._reported = True
            self.playback_error.emit(
                "Audio playback is unavailable: this build is missing the "
                "QtMultimedia (ffmpeg) plugins. Playlists and downloads still work."
            )
        return False

    def load(self, file_path: str, autoplay: bool = True) -> bool:
        return self._unavailable()

    def load_crossfade(self, file_path: str, fade_ms: int = 5000) -> bool:
        return self._unavailable()

    def play(self) -> None:
        self._unavailable()

    def pause(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def is_playing(self) -> bool:
        return False

    def is_paused(self) -> bool:
        return False

    def has_source(self) -> bool:
        return False

    def get_position(self) -> float:
        return 0.0

    def get_duration(self) -> float:
        return 0.0

    def set_position(self, seconds: float) -> None:
        pass

    def set_volume(self, volume: int) -> None:
        pass

    def set_muted(self, muted: bool) -> None:
        pass

    def play_silence(self, seconds: float) -> None:
        QTimer.singleShot(max(1, int(seconds * 1000)), self.track_finished.emit)

    def set_endevent_callback(self, callback: Callable[[], None]) -> None:
        self._on_finished = callback

    def pump_events(self) -> None:
        pass

    def quit(self) -> None:
        pass


def create_backend() -> QObject:
    """Create the best backend available on this machine."""
    try:
        from PyQt6.QtMultimedia import QMediaPlayer  # noqa: F401

        return MediaBackend()
    except Exception as exc:  # pragma: no cover - depends on install
        print(f"[audio] QtMultimedia unavailable ({exc}); using null backend")
        return NullBackend()
