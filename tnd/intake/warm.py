"""Read every scan once, in parallel, so later runs replay OCR from fixtures/ocr_cache."""

from __future__ import annotations

import json
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from .. import config
from .read import read


def _one(pdf: str) -> str:
    return read(Path(pdf)).source  # the second pass runs only where the first one is not confirmed


def _init() -> None:
    os.environ["OMP_THREAD_LIMIT"] = "1"  # one tesseract thread per worker


def warm(splits: tuple[str, ...] = ("dev", "test", "heldout")) -> dict[str, int]:
    pdfs = []
    for s in splits:
        for meta in sorted((config.DATA / s / "inbox").glob("*.json")):
            m = json.loads(meta.read_text())
            if m["channel"] in ("post", "municipal_post", "client_upload"):
                pdfs.append(str(meta.with_suffix(".pdf")))
    with ProcessPoolExecutor(max_workers=os.cpu_count() or 2, initializer=_init) as ex:
        out = list(ex.map(_one, pdfs, chunksize=4))
    return {"scans": len(out)}
