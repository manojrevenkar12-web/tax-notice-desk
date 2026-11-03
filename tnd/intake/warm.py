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


def prune(pdfs: list[str]) -> int:
    """Drop cached OCR for files that no longer exist (the mail was regenerated)."""
    import hashlib

    keep = {hashlib.sha256(Path(p).read_bytes()).hexdigest()[:20] for p in pdfs}
    gone = 0
    for f in config.CACHE_OCR.glob("*.txt"):
        if f.name.split("-")[0] not in keep:
            f.unlink()
            gone += 1
    return gone


def warm(splits: tuple[str, ...] = ("dev", "test", "heldout"), clean: bool = False) -> dict[str, int]:
    pdfs = []
    for s in splits:
        for meta in sorted((config.DATA / s / "inbox").glob("*.json")):
            m = json.loads(meta.read_text())
            if m["channel"] in ("post", "municipal_post", "client_upload"):
                pdfs.append(str(meta.with_suffix(".pdf")))
    with ProcessPoolExecutor(max_workers=os.cpu_count() or 2, initializer=_init) as ex:
        out = list(ex.map(_one, pdfs, chunksize=4))
    return {"scans": len(out), "pruned": prune(pdfs) if clean else 0}
