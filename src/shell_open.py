"""Show a file in its folder without starting explorer.exe from the app.

Starting ``explorer.exe`` as a child of a PyInstaller app can fail with
``0xc0000142`` because the child inherits the bundle's DLL search paths.
This module drives the *already running* Windows shell instead:

1. ``Shell.Application.Explore`` via COM (in a worker thread, with a timeout)
2. the same call in a hidden PowerShell process
3. give up and let the caller show the folder path in-app

No code path starts ``explorer.exe``.
"""

from __future__ import annotations

import base64
import ctypes
import os
import queue
import subprocess
import threading
from ctypes import wintypes


# ----------------------------------------------------------------------
# COM structs
# ----------------------------------------------------------------------
class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


_IID_NULL = _GUID(0, 0, 0, (ctypes.c_ubyte * 8)())
_IID_IDISPATCH = _GUID(
    0x00020400,
    0x0000,
    0x0000,
    (ctypes.c_ubyte * 8)(0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46),
)
_CLSID_SHELL = _GUID(
    0x13709620,
    0xC279,
    0x11CE,
    (ctypes.c_ubyte * 8)(0xA4, 0x9E, 0x44, 0x45, 0x53, 0x54, 0x00, 0x00),
)

_CLSCTX_SERVER = 0x5
_COINIT_APARTMENTTHREADED = 0x2
_DISPATCH_METHOD = 1
_VT_BSTR = 8


class _VARIANT(ctypes.Structure):
    class _Value(ctypes.Union):
        _fields_ = [
            ("bstrVal", ctypes.c_void_p),
            ("padding", ctypes.c_ubyte * 8),
        ]

    _anonymous_ = ("value",)
    _fields_ = [
        ("vt", ctypes.c_ushort),
        ("wReserved1", ctypes.c_ushort),
        ("wReserved2", ctypes.c_ushort),
        ("wReserved3", ctypes.c_ushort),
        ("value", _Value),
    ]


class _DISPPARAMS(ctypes.Structure):
    _fields_ = [
        ("rgvarg", ctypes.POINTER(_VARIANT)),
        ("rgdispidNamedArgs", ctypes.POINTER(ctypes.c_long)),
        ("cArgs", ctypes.c_uint),
        ("cNamedArgs", ctypes.c_uint),
    ]


def _explore_with_shell_com(folder: str) -> bool:
    ole32 = ctypes.windll.ole32
    oleaut32 = ctypes.windll.oleaut32

    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(_GUID),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_GUID),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    ole32.CoCreateInstance.restype = ctypes.c_long
    oleaut32.SysAllocString.argtypes = [wintypes.LPCWSTR]
    oleaut32.SysAllocString.restype = ctypes.c_void_p
    oleaut32.SysFreeString.argtypes = [ctypes.c_void_p]

    initialized = ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
    should_uninit = initialized in (0, 1)  # S_OK / S_FALSE

    shell = ctypes.c_void_p()
    result = ole32.CoCreateInstance(
        ctypes.byref(_CLSID_SHELL),
        None,
        _CLSCTX_SERVER,
        ctypes.byref(_IID_IDISPATCH),
        ctypes.byref(shell),
    )
    if result != 0 or not shell.value:
        print(f"[shell] Shell.Application unavailable: 0x{result & 0xFFFFFFFF:08X}")
        return False

    try:
        vtable = ctypes.cast(
            shell, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
        ).contents
        release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])
        get_ids = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_void_p,
            ctypes.POINTER(_GUID),
            ctypes.POINTER(wintypes.LPWSTR),
            ctypes.c_uint,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.c_long),
        )(vtable[5])
        invoke = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_void_p,
            ctypes.c_long,
            ctypes.POINTER(_GUID),
            wintypes.DWORD,
            wintypes.WORD,
            ctypes.POINTER(_DISPPARAMS),
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )(vtable[6])

        names = (wintypes.LPWSTR * 1)(ctypes.c_wchar_p("Explore"))
        dispid = ctypes.c_long()
        result = get_ids(
            shell, ctypes.byref(_IID_NULL), names, 1, 0, ctypes.byref(dispid)
        )
        if result != 0:
            print(f"[shell] Explore lookup failed: 0x{result & 0xFFFFFFFF:08X}")
            return False

        bstr = oleaut32.SysAllocString(os.path.normpath(folder))
        if not bstr:
            return False
        try:
            argument = _VARIANT()
            argument.vt = _VT_BSTR
            argument.bstrVal = bstr
            arguments = (_VARIANT * 1)(argument)
            params = _DISPPARAMS(
                ctypes.cast(arguments, ctypes.POINTER(_VARIANT)), None, 1, 0
            )
            result = invoke(
                shell,
                dispid,
                ctypes.byref(_IID_NULL),
                0,
                _DISPATCH_METHOD,
                ctypes.byref(params),
                None,
                None,
                None,
            )
            if result != 0:
                print(f"[shell] Explore failed: 0x{result & 0xFFFFFFFF:08X}")
                return False
            return True
        finally:
            oleaut32.SysFreeString(bstr)
    finally:
        release(shell)
        if should_uninit:
            ole32.CoUninitialize()


# ----------------------------------------------------------------------
# Hidden PowerShell fallback
# ----------------------------------------------------------------------
def _clean_env() -> dict[str, str]:
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
    return env


def _explore_with_powershell(folder: str) -> bool:
    powershell = os.path.join(
        os.environ.get("WINDIR", r"C:\Windows"),
        "System32",
        "WindowsPowerShell",
        "v1.0",
        "powershell.exe",
    )
    if not os.path.isfile(powershell):
        return False

    quoted = folder.replace("'", "''")
    script = (
        "$shell = New-Object -ComObject Shell.Application; "
        f"$shell.Explore('{quoted}')"
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        process = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-WindowStyle",
                "Hidden",
                "-EncodedCommand",
                encoded,
            ],
            cwd=os.path.expanduser("~"),
            env=_clean_env(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=4,
            check=False,
        )
        return process.returncode == 0
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"[shell] PowerShell explore failed: {exc}")
        return False


def _run_with_timeout(function, seconds: float) -> bool:
    result: queue.Queue[bool] = queue.Queue()

    def worker() -> None:
        try:
            result.put(bool(function()))
        except Exception as exc:
            print(f"[shell] explore error: {exc}")
            result.put(False)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(seconds)
    if result.empty():
        print("[shell] explore timed out")
        return False
    return result.get_nowait()


def reveal_in_explorer(path: str) -> bool:
    """Open the folder containing ``path`` using the running Windows shell."""
    if not path:
        return False
    path = os.path.normpath(os.path.abspath(path))
    if not os.path.exists(path):
        return False
    folder = os.path.dirname(path)

    if os.name == "nt":
        if _run_with_timeout(lambda: _explore_with_shell_com(folder), 3.0):
            return True
        if _explore_with_powershell(folder):
            return True
        return False

    try:
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices

        return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(folder)))
    except Exception as exc:
        print(f"[shell] could not open folder: {exc}")
        return False
