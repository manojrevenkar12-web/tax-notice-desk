"""Classify a notice and read its values, then check the values against each other.

A value is only trusted when the notice's own arithmetic holds with it (or it came from a data file, or two
independent OCR passes agree on it). Untrusted values go to a person; they are never used to close a notice.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from .. import config
from .read import Reading

MONEY = re.compile(r"(?<![\d/])(-?\s?(?:EUR\s)?-?\d{1,3}(?:[.\s]\d{3})*(?:\d)*,\d{2}(?:\s?(?:€|EUR))?-?)")
DATE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
TAXNO = re.compile(r"\b(\d{2,3})\s?/\s?(\d{3,4})\s?/\s?(\d{4,5})\b")
TOKENS = re.compile(r"\d{3}(?:,0{1,2})?\s*(?:%|v\.?\s?H\.?)|-?\s?(?:EUR\s)?-?\d{1,3}(?:[.\s]\d{3})*,\d{2}(?:\s?(?:€|EUR))?-?")
SECTION_HEADS = ("Festsetzung", "Abrechnung Einkommensteuer", "Abrechnung Solidaritätszuschlag",
                 "Abrechnung Kirchensteuer", "Abrechnung Körperschaftsteuer", "Abrechnung Umsatzsteuer",
                 "Erläuterungen", "Rechtsbehelfsbelehrung", "Ermittlung der Besteuerungsgrundlagen")


@dataclass
class Parsed:
    kind: str | None
    fields: dict[str, int] = field(default_factory=dict)
    method: dict[str, str] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    steuernummer: str | None = None
    date: str | None = None
    authority: str | None = None
    tax_year: int | None = None
    vorbehalt: bool = False
    vorlaeufig: list[str] = field(default_factory=list)
    estimate: bool = False
    appeal_instructions: bool = False
    remedy: str | None = None
    explanations: list[str] = field(default_factory=list)
    due: str | None = None
    messbescheid_date: str | None = None
    source: str = "text"
    verified: bool = False
    failed_checks: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def money(s: str) -> int | None:
    m = MONEY.search(s)
    if not m:
        return None
    raw = m.group(1).replace("EUR", "").replace("€", "").strip()
    neg = raw.startswith("-") or raw.endswith("-")
    raw = raw.strip("-").strip()
    whole, frac = raw.rsplit(",", 1)
    whole = re.sub(r"[.\s]", "", whole)
    if not whole.isdigit():
        return None
    v = int(whole) * 100 + int(frac)
    return -v if neg else v


def iso(d: str) -> str | None:
    m = DATE.search(d)
    if not m:
        return None
    try:
        return dt.date(int(m[3]), int(m[2]), int(m[1])).isoformat()
    except ValueError:
        return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()


def find(line: str, label: str, fuzzy_min: float) -> int | None:
    """End position of the label in the line, tolerating OCR noise; the label must end at a word boundary."""
    low, lab = line.lower(), label.lower()
    i = low.find(lab)
    while i >= 0:
        end = i + len(lab)
        if end >= len(low) or not low[end].isalpha():
            return end
        i = low.find(lab, i + 1)
    if fuzzy_min >= 1 or len(lab) < 8:
        return None
    starts = [0] + [m.end() for m in re.finditer(r"\s+", low)]
    best, pos = 0.0, None
    for s in starts:
        for extra in (0, 1, -1, 2, -2):
            e = s + len(lab) + extra
            if e > len(low) or (e < len(low) and low[e].isalpha()):
                continue
            r = SequenceMatcher(None, low[s:e], lab).ratio()
            if r > best:
                best, pos = r, e
    if best >= fuzzy_min and pos is not None:
        return pos
    return None


def contains(text: str, phrase: str, fuzzy_min: float) -> bool:
    return any(find(line, phrase, fuzzy_min) is not None for line in text.splitlines()) or phrase in _norm(text)


def classify(text: str) -> str | None:
    cfg = config.load("extraction")
    low = _norm(text)
    head = "\n".join(text.splitlines()[:25])
    for rule in cfg["classify"]:
        hay = low if rule["kind"] in ("request", "reminder") else _norm(head) + " " + low
        if all(p in hay or contains(text, p, cfg["fuzzy_min"]) for p in rule["all"]) and not any(
            p in hay for p in rule.get("none", [])
        ):
            return str(rule["kind"])
    return None


def _spec(spec: Any) -> dict[str, Any]:
    if isinstance(spec, list):
        return {"labels": spec}
    return dict(spec)


def _is_head(line: str, head: str, fuzzy_min: float) -> bool:
    """A section heading: the line starts with it and carries no amount."""
    if MONEY.search(line):
        return False
    stripped = line.strip(" .,;:'\"|-_")
    return find(stripped[: len(head) + 3], head, fuzzy_min) is not None


def _heads(lines: list[str], fuzzy_min: float) -> list[tuple[int, str | None]]:
    out: list[tuple[int, str | None]] = []
    for i, line in enumerate(lines):
        named = next((h for h in SECTION_HEADS if _is_head(line, h, fuzzy_min)), None)
        if named:
            out.append((i, named))
        elif _is_head(line, "Abrechnung", fuzzy_min):
            out.append((i, None))  # an "Abrechnung ..." heading the OCR garbled
    return out


ABRECHNUNG_ORDER = ["Abrechnung Einkommensteuer", "Abrechnung Solidaritätszuschlag", "Abrechnung Kirchensteuer"]


def _region(lines: list[str], section: str | None, fuzzy_min: float) -> list[str]:
    if not section:
        return lines
    heads = _heads(lines, fuzzy_min)
    idx = next((k for k, (_, h) in enumerate(heads) if h == section), None)
    if idx is None and section in ABRECHNUNG_ORDER:
        abr = [k for k, (_, h) in enumerate(heads) if h is None or (h or "").startswith("Abrechnung")]
        if len(abr) == len(ABRECHNUNG_ORDER):  # three Abrechnung blocks in the fixed order of the form
            idx = abr[ABRECHNUNG_ORDER.index(section)]
    if idx is None:
        return []
    start = heads[idx][0] + 1
    end = heads[idx + 1][0] if idx + 1 < len(heads) else len(lines)
    return lines[start:end]


def _value_after(lines: list[str], label: str, percent: bool, fuzzy_min: float) -> int | None:
    for i, line in enumerate(lines):
        pos = find(line, label, fuzzy_min)
        if pos is None:
            continue
        rest = line[pos:]
        for n, cand in enumerate((rest, lines[i + 1] if i + 1 < len(lines) else "")):
            cand = DATE.sub(" ", cand)
            if percent:
                pat = r"(?<![\d.])(\d{3})(?:,0{1,2})?\s*(?:%|v\.?\s?H\.?)" + ("?" if n == 0 else "")
                m = re.search(pat, cand)
                if m:
                    return int(m.group(1)) * 100
            else:
                v = money(cand[:90])
                if v is not None:
                    return v
            if rest.strip() and cand is rest and re.search(r"\d", rest) is None and len(rest.strip()) > 25:
                break
    return None


def _table(lines: list[str], specs: dict[str, dict], fuzzy_min: float) -> dict[str, int]:
    """A header line naming several fields, values in the same order on the next line."""
    out: dict[str, int] = {}
    for i, line in enumerate(lines[:-1]):
        hits = []
        for key, sp in specs.items():
            for lab in sp["labels"]:
                p = find(line, lab, fuzzy_min)
                if p is not None:
                    hits.append((p - len(lab), key, sp.get("percent", False)))
                    break
        if len(hits) < 2 or MONEY.search(line):
            continue
        hits.sort()
        seen: set[int] = set()
        hits = [h for h in hits if not (h[0] in seen or seen.add(h[0]))]  # type: ignore[func-returns-value]
        flat = [m.group(0) for m in TOKENS.finditer(DATE.sub(" ", lines[i + 1]))]
        if len(flat) != len(hits):
            continue
        for (_, key, pct), raw in zip(hits, flat, strict=True):
            if pct:
                m = re.match(r"(\d{3})", raw.strip())
                if m:
                    out[key] = int(m.group(1)) * 100
            else:
                mv = money(raw)
                if mv is not None:
                    out[key] = mv
    return out


def extract(r: Reading, learned: dict[str, list[str]] | None = None) -> Parsed:
    cfg = config.load("extraction")
    fz = cfg["fuzzy_min"]
    text = r.text
    lines = [ln for ln in text.splitlines() if ln.strip()]
    d = r.data or {}
    kind = d.get("kind") or classify(text)
    p = Parsed(kind=kind, source=r.source)
    p.authority = d.get("authority") or (lines[0].strip() if lines else None)
    m = TAXNO.search(text)
    p.steuernummer = d.get("steuernummer") or (f"{m[1]}/{m[2]}/{m[3]}" if m else None)
    dm = re.search(r"Datum\W{0,3}(\d{1,2}\.\d{1,2}\.\d{4})", text)
    p.date = d.get("date") or (iso(dm.group(1)) if dm else None)
    ym = re.search(r"(?:Kalenderjahr|für)\s+(\d{4})", text)
    p.tax_year = d.get("tax_year") or (int(ym.group(1)) if ym else None)
    low = _norm(text)
    p.vorbehalt = d.get("vorbehalt", False) or ("§ 164" in text and "vorbehalt" in low)
    p.vorlaeufig = re.findall(r"vorläufig hinsichtlich:?\s*(.+?)\.(?:\s|$)", text, flags=re.S)
    p.estimate = kind == "est" and ("§ 162" in text or "geschätzt" in low) and "geschätzt" in low
    p.appeal_instructions = contains(text, "Rechtsbehelfsbelehrung", fz) and ("monat" in low)
    p.remedy = "Widerspruch" if "widerspruch" in low else ("Einspruch" if "einspruch" in low else None)
    ex = _region(lines, "Erläuterungen", fz)
    p.explanations = [" ".join(ex).strip()] if ex else []
    due = re.search(r"(?:bis zum|beginnt am|spätestens bis zum)\s+(\d{1,2}\.\d{1,2}\.\d{4})", text)
    p.due = d.get("due") or (iso(due.group(1)) if due else None)
    mb = re.search(r"messbescheid\w*\s+des\s+finanzamt\w*\s+vom\s+(\d{1,2}\.\d{1,2}\.\d{4})", text, re.I)
    p.messbescheid_date = iso(mb.group(1)) if mb else None
    if not kind:
        p.missing = ["kind"]
        return p
    specs = {k: _spec(v) for k, v in cfg["fields"].get(kind, {}).items()}
    if d.get("fields"):
        p.fields = {k: v for k, v in d["fields"].items() if k in specs or k == "hebesatz"}
        p.method = {k: "data" for k in p.fields}
    else:
        merged = {k: {**sp, "labels": list((learned or {}).get(k, [])) + list(sp["labels"])} for k, sp in specs.items()}
        table = _table(lines, merged, fz)
        for key, v in table.items():  # a header row naming several fields: its columns decide
            p.fields[key], p.method[key] = v, "table"
        for key, sp in specs.items():
            if key in p.fields:
                continue
            labels = list((learned or {}).get(key, [])) + list(sp["labels"])
            region = _region(lines, sp.get("section"), fz)
            for lab in labels:
                v = _value_after(region, lab, sp.get("percent", False), fz)
                if v is not None:
                    p.fields[key] = v
                    p.method[key] = "learned" if lab in (learned or {}).get(key, []) else "label"
                    break
    p.missing = [k for k, sp in specs.items() if k not in p.fields and not sp.get("optional")]
    verify(p)
    return p


def _close(a: int, b: int, tol: int = 1) -> bool:
    return abs(a - b) <= tol


def verify(p: Parsed) -> None:
    """The notice's own arithmetic, with the values as read. Data files are trusted as delivered."""
    f, fails = p.fields, []
    g = f.get
    if p.missing:
        fails.append("missing:" + ",".join(p.missing))
    elif p.kind == "est":
        if g("summe_einkuenfte") != g("einkuenfte_nsa", 0) + g("einkuenfte_gewerbe", 0) + g("einkuenfte_vuv", 0):
            fails.append("summe")
        if g("zve") != max(0, f["summe_einkuenfte"] - f["sonderausgaben"] - f["agb"]) // 100 * 100:
            fails.append("zve")
        if not _close(f["rest_est"], f["est"] - f["lst_est"] - f["vz_est"]):
            fails.append("rest_est")
        if not _close(f["rest_soli"], f["soli"] - f["lst_soli"]) or not _close(f["rest_kist"], f["kist"] - f["lst_kist"]):
            fails.append("rest_soli_kist")
    elif p.kind == "kst":
        if not _close(f["kst"], f["einkommen"] * 15 // 100, 100) or not _close(f["soli"], round(f["kst"] * 0.055), 2):
            fails.append("kst")
        if not _close(f["rest_kst"], f["kst"] - f["vz_kst"]):
            fails.append("rest_kst")
    elif p.kind == "ust":
        if not _close(f["ust"], f["umsatz_19"] * 19 // 100 + f["umsatz_7"] * 7 // 100, 2):
            fails.append("ust")
        if not _close(f["zahllast"], f["ust"] - f["vorsteuer"]) or not _close(f["rest_ust"], f["zahllast"] - f["vz_ust"]):
            fails.append("rest_ust")
    elif p.kind == "gewst_mess":
        ertrag = max(0, f["gewinn"] + f["hinzurechnungen"] - f["kuerzungen"]) // 10000 * 10000
        if f["gewerbeertrag"] != ertrag or f["messbetrag"] != (ertrag - f["freibetrag"]) * 35 // 1000:
            fails.append("messbetrag")
    elif p.kind == "gewst":
        if not _close(f["rest_gewst"], f["gewst"] - f["vz_gewst"]):
            fails.append("rest_gewst")
        if not 20000 <= f["hebesatz"] <= 90000:
            fails.append("hebesatz_range")
    p.failed_checks = fails
    p.verified = p.source == "data" or not fails
