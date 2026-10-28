"""Freevoice Radio - 24/7 local radio desktop app.

Entry point:  python main.py
"""

from __future__ import annotations

import os
import sys
import traceback

# Ensure the package root is importable when run as a script
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtCore import QLockFile
from PyQt6.QtNetwork import QLocalSocket
from PyQt6.QtWidgets import QApplication, QMessageBox

from src.app_paths import app_dir, config_path
from src.config import Config
from src.gui.main_window import MainWindow
from src.single_instance import instance_name, lock_path

LOG_NAME = "freevoice.log"


def _setup_logging() -> None:
    """Route print()/tracebacks to a log file in a windowed exe.

    A PyInstaller ``console=False`` build has no usable stdout/stderr (None
    or a null writer), so any print() would otherwise be lost or raise.  The
    log also captures Qt/ffmpeg diagnostics for troubleshooting.
    """
    if not getattr(sys, "frozen", False):
        return
    if os.environ.get("FREEVOICE_CONSOLE"):
        return
    try:
        stream = open(
            os.path.join(app_dir(), LOG_NAME), "a", encoding="utf-8", buffering=1
        )
    except OSError:
        return
    sys.stdout = stream
    sys.stderr = stream


def _install_exception_hook() -> None:
    def _hook(exc_type, exc_value, exc_tb) -> None:
        detail = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            print(detail, file=sys.stderr)
        except Exception:
            pass

    sys.excepthook = _hook


def main() -> None:
    _setup_logging()
    _install_exception_hook()

    app = QApplication(sys.argv)
    app.setApplicationName("Freevoice Radio")
    app.setOrganizationName("Freevoice")

    minimized_start = "--minimized" in sys.argv

    # Only one radio may play at a time.  A second launch wakes the existing
    # window through a local socket and exits.
    instance_lock = QLockFile(str(lock_path()))
    instance_lock.setStaleLockTime(30000)
    if not instance_lock.tryLock(500):
        socket = QLocalSocket()
        socket.connectToServer(instance_name())
        if socket.waitForConnected(2500):
            socket.write(b"show")
            socket.waitForBytesWritten(1000)
            socket.disconnectFromServer()
        sys.exit(0)

    try:
        config = Config(config_path=config_path())
        config.save()  # materialise config.json next to the exe on first run

        window = MainWindow(config)
        if minimized_start:
            window.hide()
        else:
            window.show()
    except Exception:
        detail = traceback.format_exc()
        print(detail)
        QMessageBox.critical(
            None,
            "Freevoice Radio - startup error",
            f"The app could not start.\n\n{detail}",
        )
        raise

    print(f"[startup] Freevoice Radio started ({app_dir()})")
    sys.exit(app.exec())


if __name__ == "__main__":
    if "--selftest" in sys.argv or "--selftest-loop" in sys.argv:
        _setup_logging()
        from src.selftest import run_loop_test, run_selftest

        if "--selftest-loop" in sys.argv:
            sys.exit(run_loop_test())
        sys.exit(run_selftest())
    main()
