"""Load an externally updated yt-dlp package from the app folder.

The frozen app ships with a working yt-dlp build for fallback.  Updates are
downloaded as wheels into ``vendor.next`` and activated at the next startup by
swapping the directory before any application module imports yt_dlp.
"""

from __future__ import annotations

import os
import shutil
import sys
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Optional

from src.app_paths import app_dir


class _VendorFinder:
    """Meta path finder that prefers the external package over the bundle."""

    def __init__(self, vendor_dir: Path) -> None:
        self.vendor_dir = vendor_dir

    def find_spec(self, fullname, path=None, target=None):  # noqa: ANN001
        if fullname != "yt_dlp" and not fullname.startswith("yt_dlp."):
            return None
        base = self.vendor_dir.joinpath(*fullname.split("."))
        init_file = base / "__init__.py"
        if init_file.is_file():
            return spec_from_file_location(
                fullname,
                init_file,
                submodule_search_locations=[str(base)],
            )
        module_file = base.with_suffix(".py")
        if module_file.is_file():
            return spec_from_file_location(fullname, module_file)
        return None


def vendor_root() -> Path:
    return Path(app_dir()) / "vendor"


def staged_root() -> Path:
    return Path(app_dir()) / "vendor.next"


def _activate_staged() -> None:
    staged = staged_root()
    target = vendor_root()
    if not (staged / "yt_dlp" / "__init__.py").is_file():
        return
    backup = Path(app_dir()) / "vendor.old"
    try:
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        if target.exists():
            os.replace(target, backup)
        os.replace(staged, target)
        shutil.rmtree(backup, ignore_errors=True)
        print("[yt-dlp] activated staged package")
    except OSError as exc:
        print(f"[yt-dlp] could not activate staged package: {exc}")
        if not target.exists() and backup.exists():
            try:
                os.replace(backup, target)
            except OSError:
                pass


def _external_version() -> Optional[str]:
    version_file = vendor_root() / "yt_dlp" / "version.py"
    try:
        text = version_file.read_text(encoding="utf-8")
        import re

        match = re.search(r'__version__\s*=\s*["\']([^"\']+)', text)
        return match.group(1) if match else None
    except OSError:
        return None


def prepare_ytdlp() -> bool:
    """Activate any staged update and prefer the external package."""
    _activate_staged()
    vendor = vendor_root()
    if (vendor / "yt_dlp" / "__init__.py").is_file():
        finder = _VendorFinder(vendor)
        sys.meta_path.insert(0, finder)
        try:
            import yt_dlp  # noqa: F401
            import yt_dlp.version
        except Exception as exc:
            print(f"[yt-dlp] external package failed ({exc}); using bundled")
            try:
                sys.meta_path.remove(finder)
            except ValueError:
                pass
            for name in list(sys.modules):
                if name == "yt_dlp" or name.startswith("yt_dlp."):
                    sys.modules.pop(name, None)
            bad = Path(app_dir()) / "vendor.failed"
            try:
                if bad.exists():
                    shutil.rmtree(bad, ignore_errors=True)
                os.replace(vendor, bad)
            except OSError:
                pass
        else:
            print(
                f"[yt-dlp] using external {yt_dlp.version.__version__} "
                f"({yt_dlp.__file__})"
            )
            return True

    try:
        import yt_dlp
        import yt_dlp.version
    except Exception as exc:
        print(f"[yt-dlp] import failed: {exc}")
        return False
    print(f"[yt-dlp] using bundled {yt_dlp.version.__version__} ({yt_dlp.__file__})")
    return True


def current_ytdlp_info() -> tuple[str, str, bool]:
    """Return (version, package path, is_external)."""
    try:
        import yt_dlp
        import yt_dlp.version

        path = str(getattr(yt_dlp, "__file__", "") or "")
        external = Path(path).resolve().is_relative_to(vendor_root().resolve())
        return yt_dlp.version.__version__, path, external
    except Exception:
        return "unavailable", "", False
