"""Get text and, when it exists, structured data out of an incoming file.

Electronic notices carry their data (a portal data file, or XML embedded in the PDF): those values are
taken as they are. Everything else is read from the PDF's text layer, or from OCR for scans. OCR results are
cached by file hash, so a document is read once.
"""

from __future__ import annotations

import hashlib
import io
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import pytesseract
from PIL import Image, ImageFilter
from pypdf import PdfReader

from .. import config

OCR_VERSION = 2  # bump when preprocessing changes; the cache is keyed by it


@dataclass
class Reading:
    text: str
    source: str  # data | text | ocr
    data: dict | None = None  # structured values from a data file
    alt_text: str | None = None  # a second OCR pass, for agreement checks
    warnings: list[str] = field(default_factory=list)


def parse_xml(raw: bytes) -> dict:
    root = ET.fromstring(raw)
    out: dict = {"kind": root.get("art"), "tax_year": int(root.get("jahr") or 0), "fields": {}}
    for child in root:
        if child.tag == "Wert":
            out["fields"][child.get("name")] = int(child.text or 0)
        elif child.tag == "Steuernummer":
            out["steuernummer"] = child.text
        elif child.tag == "Datum":
            out["date"] = child.text
        elif child.tag == "Behoerde":
            out["authority"] = child.text
        elif child.tag == "Frist":
            out["due"] = child.text
        elif child.tag == "Vorbehalt":
            out["vorbehalt"] = child.text == "ja"
    return out


def _ocr(pdf: Path, psm: int) -> str:
    cfg = config.load("extraction")["ocr"]
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()[:20]
    cache = config.CACHE_OCR / f"{digest}-{psm}-v{OCR_VERSION}.txt"
    if cache.exists():
        return cache.read_text()
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["pdftoppm", "-r", str(cfg["dpi"]), "-gray", "-png", "-singlefile", str(pdf), f"{d}/p"],
                       check=True)
        img = Image.open(f"{d}/p.png").filter(ImageFilter.MedianFilter(3))  # scanner speckles break OCR
        text = pytesseract.image_to_string(img, lang=cfg["lang"], config=f"--psm {psm}")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(text)
    return text


def normalise(text: str) -> str:
    """Undo the usual OCR damage in numbers without touching words."""
    t = text.replace(" ", " ").replace("’", "'").replace("‚", ",")
    t = re.sub(r"(\d)\s*,\s+(\d{2})\b", r"\1,\2", t)          # '15 544, 37' -> '15 544,37'
    t = re.sub(r"(\d)\s+,(\d{2})\b", r"\1,\2", t)
    t = re.sub(r"(?<=\d)[Oo](?=[\d,.])", "0", t)
    t = re.sub(r"(?<=[\d.])[lI|](?=[\d,])", "1", t)
    t = re.sub(r"(\d{1,2})\. (\d{1,2})\. ?(\d{4})", r"\1.\2.\3", t)  # '18.09. 2026'
    t = re.sub(r"(\d)\.(\d{2})(?=\s?(?:€|EUR)|-?\s*$)", r"\1,\2", t, flags=re.M)  # '119.175.80 €'
    return t


def read(pdf: Path, xml: Path | None = None) -> Reading:
    data = parse_xml(xml.read_bytes()) if xml and xml.exists() else None
    reader = PdfReader(io.BytesIO(pdf.read_bytes()))
    if data is None:
        for name, contents in (reader.attachments or {}).items():
            if name.endswith(".xml"):
                data = parse_xml(contents[0])
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    if len(text.strip()) > 80:
        return Reading(normalise(text), "data" if data else "text", data)
    return Reading(normalise(_ocr(pdf, config.load("extraction")["ocr"]["psm"])), "ocr", data)


def second_read(pdf: Path) -> str:
    """An independent OCR pass (different page segmentation) to confirm values read the first time."""
    return normalise(_ocr(pdf, 6))
