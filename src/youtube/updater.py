"""Download and stage the latest yt-dlp wheel from PyPI."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.app_paths import app_dir
from src.ytdlp_runtime import current_ytdlp_info, staged_root, vendor_root

PYPI_URL = "https://pypi.org/pypi/yt-dlp/json"
USER_AGENT = "FreevoiceRadio/1.0"


@dataclass
class UpdateResult:
    version: str
    updated: bool
    message: str
    error: bool = False


def _fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)


def _wheel_for_release(data: dict) -> tuple[str, str, str]:
    version = str(data["info"]["version"])
    for item in data.get("urls", []):
        filename = str(item.get("filename") or "")
        if filename.startswith("yt_dlp-") and filename.endswith(".whl"):
            return version, str(item["url"]), str(item["digests"]["sha256"])
    raise RuntimeError("PyPI did not provide a yt-dlp wheel")


def _staged_version() -> Optional[str]:
    version_file = staged_root() / "yt_dlp" / "version.py"
    try:
        match = re.search(
            r'__version__\s*=\s*["\']([^"\']+)',
            version_file.read_text(encoding="utf-8"),
        )
        return match.group(1) if match else None
    except OSError:
        return None


def _extract_wheel(wheel_path: Path, stage: Path) -> None:
    with zipfile.ZipFile(wheel_path) as archive:
        names = archive.namelist()
        for name in names:
            normalized = name.replace("\\", "/")
            if normalized.startswith("/") or ".." in normalized.split("/"):
                raise RuntimeError("Unsafe path in yt-dlp wheel")
        for name in names:
            if name == "yt_dlp/" or name.startswith("yt_dlp/"):
                archive.extract(name, stage)
    if not (stage / "yt_dlp" / "__init__.py").is_file():
        raise RuntimeError("The downloaded wheel does not contain yt_dlp")


def install_update() -> UpdateResult:
    """Stage the latest yt-dlp package; it activates on the next launch."""
    version, package_path, external = current_ytdlp_info()
    data = _fetch_json(PYPI_URL)
    latest, wheel_url, expected_sha = _wheel_for_release(data)

    staged = _staged_version()
    if staged == latest and latest != version:
        return UpdateResult(
            latest,
            True,
            f"yt-dlp {latest} is already downloaded. Restart Freevoice Radio "
            "to activate it.",
        )
    if latest == version:
        return UpdateResult(
            latest,
            False,
            f"yt-dlp {latest} is up to date.",
        )

    root = Path(app_dir())
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ytdlp-", dir=root) as temp:
        temp_path = Path(temp)
        wheel_path = temp_path / "yt_dlp.whl"
        digest = hashlib.sha256()
        request = urllib.request.Request(
            wheel_url, headers={"User-Agent": USER_AGENT}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            with open(wheel_path, "wb") as handle:
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    digest.update(chunk)
                    handle.write(chunk)
        if digest.hexdigest().lower() != expected_sha.lower():
            raise RuntimeError("Downloaded yt-dlp wheel failed SHA-256 verification")

        extract_dir = temp_path / "extract"
        extract_dir.mkdir()
        _extract_wheel(wheel_path, extract_dir)
        target = staged_root()
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        os.replace(extract_dir, target)

    return UpdateResult(
        latest,
        True,
        f"yt-dlp {latest} downloaded. Restart Freevoice Radio to activate it.",
    )


def activate_after_restart() -> None:
    """Compatibility hook: activation happens in ytdlp_runtime.prepare_ytdlp."""
    # Kept intentionally empty; the bootstrap performs the swap before imports.
    _ = vendor_root
