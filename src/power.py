"""Keep Windows awake while audio is playing.

Uses SetThreadExecutionState with ES_SYSTEM_REQUIRED.  The display is allowed
to turn off normally, but the system idle timer keeps resetting while audio is
active.  The call is made on the GUI thread and released there as well.
"""

from __future__ import annotations

import ctypes
import sys

_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


class SleepInhibitor:
    def __init__(self) -> None:
        self._held = False
        self._kernel32 = None
        if sys.platform == "win32":
            try:
                self._kernel32 = ctypes.windll.kernel32
                self._kernel32.SetThreadExecutionState.argtypes = [
                    ctypes.c_ulong
                ]
                self._kernel32.SetThreadExecutionState.restype = ctypes.c_ulong
            except Exception as exc:
                print(f"[power] sleep inhibitor unavailable: {exc}")
                self._kernel32 = None

    @property
    def held(self) -> bool:
        return self._held

    def set_playing(self, playing: bool) -> None:
        if self._kernel32 is None:
            return
        if playing and not self._held:
            result = self._kernel32.SetThreadExecutionState(
                _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED
            )
            if result:
                self._held = True
                print("[power] sleep inhibited while playing")
        elif not playing and self._held:
            self._kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
            self._held = False
            print("[power] sleep inhibition released")

    def release(self) -> None:
        self.set_playing(False)
