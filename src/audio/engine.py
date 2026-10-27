"""Audio engine for Freevoice Radio.

Orchestrates playback using a streaming backend (QtMultimedia).  Handles:

  * Loop modes: off / all / one, plus an independent shuffle toggle
  * Crossfade between tracks
  * Silence between tracks
  * Stream mode (temp files, removed after playback)
  * Volume control
  * Track-ended / playlist-changed callbacks

The engine deliberately does **no** audio conversion: the backend decodes
MP3/WAV/FLAC/M4A/OGG directly, so downloading a track no longer spawns a
multi-hundred-megabyte WAV next to it.
"""

from __future__ import annotations

import os
import random
import threading
from typing import Callable, Optional, Sequence

from PyQt6.QtCore import QTimer

from src.audio.backends import create_backend

AUDIO_EXTENSIONS = (".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".opus", ".webm")


class AudioEngine:
    def __init__(self, download_path: str = "downloads", audio_format: str = "mp3") -> None:
        self.backend = create_backend()
        self.backend.track_finished.connect(self._on_track_finished)
        self.backend.playback_error.connect(self._on_backend_error)

        self._playlist: list[str] = []
        self._stream_temp_files: set[str] = set()
        self._bad_paths: set[str] = set()
        self._index = -1

        self._loop_mode = "all"
        self._shuffle = False
        self._shuffle_bag: list[int] = []
        self._shuffle_filled = False
        self._gapless = True
        self._crossfade_enabled = False
        self._crossfade_seconds = 5
        self._silence_enabled = False
        self._silence_seconds = 2
        self._silence_playing = False

        self._is_playing = False
        self._is_paused = False
        self._lock = threading.RLock()

        self._on_track_changed: Optional[Callable[[str], None]] = None
        self._on_playback_stopped: Optional[Callable[[], None]] = None
        self._on_playlist_changed: Optional[Callable[[], None]] = None
        self._on_error: Optional[Callable[[str], None]] = None

        self._download_path = download_path
        self._audio_format = audio_format

    # ------------------------------------------------------------------
    # Playlist management
    # ------------------------------------------------------------------
    def playlist(self) -> list[str]:
        with self._lock:
            return list(self._playlist)

    def current_track(self) -> Optional[str]:
        with self._lock:
            if 0 <= self._index < len(self._playlist):
                return self._playlist[self._index]
            return None

    def set_playlist(self, paths: Sequence[str]) -> None:
        with self._lock:
            seen: set[str] = set()
            cleaned: list[str] = []
            for path in paths:
                if not path or not isinstance(path, str) or path in seen:
                    continue
                seen.add(path)
                cleaned.append(path)
            self._playlist = cleaned
            self._index = -1
            self._reset_shuffle()
            self._notify_playlist_changed()

    def add_track(self, path: str, stream: bool = False) -> bool:
        """Append a track.  Returns True if it was newly added."""
        with self._lock:
            if not path or not isinstance(path, str):
                print("[engine] add_track rejected: invalid path")
                return False
            if stream:
                self._stream_temp_files.add(path)
            if path in self._playlist:
                return False
            self._playlist.append(path)
            self._reset_shuffle()
            self._notify_playlist_changed()
            return True

    def remove_track(self, path: str) -> bool:
        with self._lock:
            if path not in self._playlist:
                return False
            index = self._playlist.index(path)
            self._remove_at(index)
            if index < self._index:
                self._index -= 1
            return True

    def clear_playlist(self) -> None:
        with self._lock:
            self._stop_locked()
            self._playlist.clear()
            self._index = -1
            self._reset_shuffle()
            self._delete_all_stream_files()
            self._bad_paths.clear()
            self._notify_playlist_changed()

    # ------------------------------------------------------------------
    # Playback control
    # ------------------------------------------------------------------
    def play(self) -> bool:
        with self._lock:
            if not self._playlist:
                return False
            if not (0 <= self._index < len(self._playlist)):
                self._index = 0
            if self._load_and_play(self._playlist[self._index]):
                return True
            # First entry was unplayable: skip to the next usable one.
            self._advance(1)
            return self._is_playing

    def play_track(self, path: str) -> bool:
        """Play ``path`` immediately, adding it to the playlist if needed."""
        with self._lock:
            if path not in self._playlist:
                self._playlist.append(path)
                self._notify_playlist_changed()
            self._index = self._playlist.index(path)
            self._reset_shuffle()
            if self._load_and_play(path):
                return True
            self._advance(1)
            return self._is_playing

    def pause(self) -> None:
        with self._lock:
            if self._is_playing and not self._is_paused:
                self.backend.pause()
                self._is_paused = True

    def resume(self) -> None:
        with self._lock:
            if self._is_paused:
                self.backend.play()
                self._is_paused = False

    def toggle_play_pause(self) -> None:
        if self.is_playing():
            self.pause()
        elif self._is_paused:
            self.resume()
        else:
            self.play()

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def next_track(self) -> None:
        with self._lock:
            self._advance(1)

    def prev_track(self) -> None:
        with self._lock:
            self._advance(-1)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    def is_playing(self) -> bool:
        return self._is_playing and not self._is_paused

    def is_paused(self) -> bool:
        return self._is_paused

    def position(self) -> float:
        return self.backend.get_position()

    def duration(self) -> float:
        return self.backend.get_duration()

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    def set_loop_mode(self, mode: str) -> None:
        """mode: 'off' | 'all' | 'one'  (legacy 'loop_*' values accepted)."""
        normalized = str(mode or "").lower()
        if normalized == "shuffle":
            # Legacy config value: Shuffle is an independent toggle now.
            self._shuffle = True
            normalized = "loop_all"
        mapping = {
            "loop_all": "all",
            "all": "all",
            "loop_one": "one",
            "one": "one",
            "off": "off",
        }
        self._loop_mode = mapping.get(normalized, "all")
        self._reset_shuffle()

    def loop_mode(self) -> str:
        return self._loop_mode

    def set_shuffle(self, enabled: bool) -> None:
        self._shuffle = bool(enabled)
        self._reset_shuffle()

    def shuffle_enabled(self) -> bool:
        return self._shuffle

    def set_gapless(self, enabled: bool) -> None:
        self._gapless = bool(enabled)

    def set_crossfade(self, enabled: bool, seconds: int = 5) -> None:
        self._crossfade_enabled = bool(enabled)
        self._crossfade_seconds = max(1, int(seconds))

    def set_silence(self, enabled: bool, seconds: int = 2) -> None:
        self._silence_enabled = bool(enabled)
        self._silence_seconds = max(1, int(seconds))

    def set_volume(self, volume: int) -> None:
        self.backend.set_volume(volume)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------
    def on_track_changed(self, callback: Callable[[str], None]) -> None:
        self._on_track_changed = callback

    def on_playback_stopped(self, callback: Callable[[], None]) -> None:
        self._on_playback_stopped = callback

    def on_playlist_changed(self, callback: Callable[[], None]) -> None:
        self._on_playlist_changed = callback

    def on_error(self, callback: Callable[[str], None]) -> None:
        self._on_error = callback

    # ------------------------------------------------------------------
    # Internal (call with self._lock held)
    # ------------------------------------------------------------------
    def _load_and_play(self, file_path: str) -> bool:
        if not file_path or not os.path.exists(file_path) or file_path in self._bad_paths:
            return False

        if (
            self._crossfade_enabled
            and self.backend.is_playing()
            and self.backend.has_source()
        ):
            started = self.backend.load_crossfade(
                file_path, self._crossfade_seconds * 1000
            )
        else:
            started = self.backend.load(file_path)

        if not started:
            return False

        self._is_playing = True
        self._is_paused = False
        self._silence_playing = False
        if self._on_track_changed:
            self._on_track_changed(file_path)
        return True

    def _advance(self, direction: int = 1) -> None:
        if not self._playlist:
            self._stop_locked()
            return

        for _ in range(len(self._playlist)):
            if direction > 0 and self._shuffle:
                index = self._pop_shuffle_index()
                if index is None:
                    self._stop_locked()
                    return
            else:
                index = self._index + direction
                if index >= len(self._playlist):
                    if self._loop_mode == "off":
                        self._stop_locked()
                        return
                    index = 0
                elif index < 0:
                    if self._loop_mode == "off":
                        self._stop_locked()
                        return
                    index = len(self._playlist) - 1

            self._index = index
            if self._load_and_play(self._playlist[index]):
                return

            # Unplayable entry: drop it and retry from the same spot.
            self._remove_at(index)
            self._index = index - 1 if direction > 0 else index
            if not self._playlist:
                self._stop_locked()
                return

        # Nothing in the playlist could be played.
        self._stop_locked()

    def _reset_shuffle(self) -> None:
        self._shuffle_bag.clear()
        self._shuffle_filled = False

    def _pop_shuffle_index(self) -> Optional[int]:
        """Pick the next shuffled track, without repeating until the playlist
        has been played through.

        Loop Off stops once every track has been played once; Loop All starts a
        new shuffled round; Loop One is handled when a track ends naturally.
        """
        count = len(self._playlist)
        if count == 0:
            return None

        if not self._shuffle_bag:
            if self._shuffle_filled and self._loop_mode == "off":
                return None
            candidates = [i for i in range(count) if i != self._index]
            if not candidates:
                return self._index if self._loop_mode != "off" else None
            random.shuffle(candidates)
            self._shuffle_bag = candidates
            self._shuffle_filled = True

        return self._shuffle_bag.pop()

    def _on_track_finished(self) -> None:
        """Called by the backend when the current track (or the silence
        gap) has finished."""
        with self._lock:
            if not self._is_playing:
                return

            if self._silence_playing:
                self._silence_playing = False
                self._advance(1)
                return

            finished_index = self._index
            finished_path = (
                self._playlist[finished_index]
                if 0 <= finished_index < len(self._playlist)
                else None
            )

            # Loop One repeats the same file; no stream cleanup yet.
            if (
                self._loop_mode == "one"
                and finished_path
                and os.path.exists(finished_path)
                and finished_path not in self._bad_paths
            ):
                self._load_and_play(finished_path)
                return

            # Stream mode: delete the temp file and forget the entry, then
            # make sure _advance(1) starts the following track.
            if finished_path and finished_path in self._stream_temp_files:
                self._delete_stream_file(finished_path)
                self._remove_at(finished_index)
                if not self._playlist:
                    self._stop_locked()
                    return
                self._index = finished_index - 1

            if self._silence_enabled:
                self._silence_playing = True
                self.backend.play_silence(self._silence_seconds)
                return

            self._advance(1)

    def _stop_locked(self) -> None:
        self._silence_playing = False
        self.backend.stop()
        was_active = self._is_playing or self._is_paused
        self._is_playing = False
        self._is_paused = False
        if was_active and self._on_playback_stopped:
            self._on_playback_stopped()

    def _remove_at(self, index: int) -> str:
        path = self._playlist.pop(index)
        self._stream_temp_files.discard(path)
        self._reset_shuffle()
        self._notify_playlist_changed()
        return path

    def _delete_stream_file(self, path: str) -> None:
        candidates = [path]
        if path.lower().endswith(".wav"):
            candidates.append(path[: -len(".wav")] + "_converted.wav")
        else:
            candidates.append(os.path.splitext(path)[0] + "_converted.wav")
        for candidate in candidates:
            try:
                if os.path.exists(candidate):
                    os.remove(candidate)
            except OSError:
                pass

    def _delete_all_stream_files(self) -> None:
        for path in list(self._stream_temp_files):
            self._delete_stream_file(path)
        self._stream_temp_files.clear()

    def _notify_playlist_changed(self) -> None:
        if self._on_playlist_changed:
            self._on_playlist_changed()

    def _on_backend_error(self, message: str) -> None:
        path = self.current_track()
        if path:
            self._bad_paths.add(path)
        if self._on_error:
            self._on_error(message)
        # Skip the broken track, but do it from the event loop: this
        # callback can fire from inside backend.load().
        if self._is_playing:
            QTimer.singleShot(0, self._advance_after_error)

    def _advance_after_error(self) -> None:
        with self._lock:
            if self._is_playing:
                self._advance(1)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------
    def quit(self) -> None:
        with self._lock:
            self._stop_locked()
            self._delete_all_stream_files()
        self.backend.quit()
