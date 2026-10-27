"""Playback self-tests for Freevoice Radio.

Run from the project folder::

    python -m src.selftest            # play a real downloaded file
    python -m src.selftest --loop     # verify end-of-track auto-advance

The frozen executable exposes the same checks via
``Freevoice Radio.exe --selftest`` / ``--selftest-loop``.
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys
import tempfile
import time

from PyQt6.QtWidgets import QApplication

from src.app_paths import app_dir, find_ffmpeg
from src.audio.engine import AudioEngine


def _ensure_app() -> QApplication:
    return QApplication.instance() or QApplication(sys.argv[:1])


def _spin(app: QApplication, seconds: float) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)


def find_sample(explicit: str | None = None) -> str | None:
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    for folder in (
        app_dir(),
        os.path.join(app_dir(), "downloads"),
        os.path.join(app_dir(), "dist", "downloads"),
    ):
        for pattern in ("*.mp3", "*.m4a", "*.flac", "*.ogg", "*.wav"):
            candidates.extend(sorted(glob.glob(os.path.join(folder, pattern))))
    for path in candidates:
        if not path:
            continue
        if not os.path.isfile(path):
            continue
        if path.endswith("_converted.wav"):
            continue  # legacy artefact from the old pygame implementation
        return path
    return None


def run_selftest(audio_file: str | None = None, seconds: float = 3.0,
                 audible: bool = False) -> int:
    app = _ensure_app()
    sample = find_sample(audio_file)
    if not sample:
        print("SELFTEST FAIL: no audio file available to play")
        return 1

    engine = AudioEngine()
    backend_name = type(engine.backend).__name__
    errors: list[str] = []
    engine.on_error(errors.append)
    engine.set_volume(70 if audible else 0)

    played: list[str] = []
    engine.on_track_changed(played.append)
    engine.set_playlist([sample])
    started = engine.play()
    _spin(app, seconds)

    playing = engine.is_playing()
    position = engine.position()
    duration = engine.duration()
    engine.quit()

    ok = bool(started and playing and position > 0.5 and not errors)
    print(f"SELFTEST backend={backend_name}")
    print(f"SELFTEST file={sample}")
    print(
        "SELFTEST playing=%s position=%.2fs duration=%.1fs errors=%s"
        % (playing, position, duration, errors)
    )
    print(f"SELFTEST tracks_started={len(played)}")
    print("SELFTEST PASS" if ok else "SELFTEST FAIL")
    return 0 if ok else 1


def _make_tone(path: str, seconds: int = 2, frequency: int = 440) -> bool:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return False
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration={seconds}",
        "-ac", "2", path,
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return os.path.isfile(path) and os.path.getsize(path) > 0


def run_loop_test(seconds: float = 5.0) -> int:
    """Verify that a finished track advances to the next one and loops."""
    app = _ensure_app()
    folder = tempfile.mkdtemp(prefix="freevoice_selftest_")
    first = os.path.join(folder, "a_first.mp3")
    second = os.path.join(folder, "b_second.mp3")
    if not (_make_tone(first, 2, 440) and _make_tone(second, 2, 660)):
        print("SELFTEST LOOP SKIP: ffmpeg not available to generate test tones")
        return 0

    engine = AudioEngine()
    engine.set_volume(0)
    engine.set_loop_mode("loop_all")
    engine.set_silence(False)
    engine.set_crossfade(False)

    changes: list[str] = []
    engine.on_track_changed(changes.append)
    engine.set_playlist([first, second])
    engine.play()

    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)

    engine.quit()
    names = [os.path.basename(path) for path in changes]
    ok = (
        len(changes) >= 3
        and names[0] == "a_first.mp3"
        and names[1] == "b_second.mp3"
        and names[2] == "a_first.mp3"
    )
    print(f"SELFTEST LOOP sequence={names}")
    print("SELFTEST LOOP PASS" if ok else "SELFTEST LOOP FAIL")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if "--loop" in args:
        return run_loop_test()
    explicit = next((a for a in args if not a.startswith("-")), None)
    return run_selftest(explicit, audible="--audible" in args)


if __name__ == "__main__":
    raise SystemExit(main())
