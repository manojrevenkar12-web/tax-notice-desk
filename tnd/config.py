"""Settings live in config/*.yaml; code reads them through here."""

from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = Path(os.environ.get("TND_DATA", ROOT / "data"))
REPORTS = ROOT / "reports"
CORPUS = ROOT / "corpus"
CACHE_OCR = ROOT / "fixtures" / "ocr_cache"  # committed: CI replays OCR instead of running tesseract


@functools.cache
def load(name: str) -> dict[str, Any]:
    with open(CONFIG / f"{name}.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def clear() -> None:
    load.cache_clear()
