"""Identity for the single running Freevoice Radio instance."""

from __future__ import annotations

import hashlib
from pathlib import Path

from src.app_paths import config_path


def instance_name() -> str:
    key = str(Path(config_path()).resolve()).lower()
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
    return f"FreevoiceRadio-{digest}"


def lock_path() -> Path:
    return Path(config_path()).with_name("freevoice.lock")
