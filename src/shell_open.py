"""Show a file in its folder without spawning explorer.exe ourselves.

Launching ``explorer.exe`` directly from a PyInstaller bundle can fail with
``0xc0000142`` ("application was unable to start correctly") because the
child inherits the app's DLL search environment.  ShellExecute (used by
``QDesktopServices``) asks the existing shell to open the folder instead, so
no new Explorer process is started from the app.
"""

from __future__ import annotations

import os
import subprocess


def _launch_explorer_clean(path: str) -> bool:
    """Fallback: start Explorer with a cleaned environment.

    The ``0xc0000142`` error happens when Explorer inherits the bundled
    app's DLL search paths.  Stripping ``_internal``/PyInstaller entries and
    using a neutral working directory avoids that.
    """
    explorer = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "explorer.exe")
    if not os.path.isfile(explorer):
        return False

    env = os.environ.copy()
    parts = []
    for part in env.get("PATH", "").split(os.pathsep):
        lowered = part.lower()
        if not part:
            continue
        if "_internal" in lowered or "_mei" in lowered or "freevoice" in lowered:
            continue
        parts.append(part)
    env["PATH"] = os.pathsep.join(parts)
    for key in (
        "PYTHONHOME",
        "PYTHONPATH",
        "QT_PLUGIN_PATH",
        "QT_QPA_PLATFORM_PLUGIN_PATH",
    ):
        env.pop(key, None)

    try:
        subprocess.Popen(
            [explorer, "/select,", os.path.normpath(path)],
            cwd=os.path.expanduser("~"),
            env=env,
            close_fds=True,
        )
        return True
    except OSError as exc:
        print(f"[shell] could not start Explorer: {exc}")
        return False


def reveal_in_explorer(path: str) -> bool:
    """Open the folder containing ``path`` in the system file manager."""
    if not path:
        return False
    path = os.path.normpath(os.path.abspath(path))
    if not os.path.exists(path):
        return False
    folder = os.path.dirname(path)

    # Preferred: ShellExecute asks the running Explorer to open the folder.
    try:
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices

        if QDesktopServices.openUrl(QUrl.fromLocalFile(folder)):
            return True
    except Exception as exc:
        print(f"[shell] QDesktopServices failed: {exc}")

    # Fallback: Explorer with a clean environment (fixes 0xc0000142).
    if os.name == "nt" and _launch_explorer_clean(path):
        return True

    if os.name == "nt":
        try:
            os.startfile(folder)  # noqa: S606 - ShellExecute, not explorer.exe
            return True
        except OSError as exc:
            print(f"[shell] could not open {folder}: {exc}")

    return False
