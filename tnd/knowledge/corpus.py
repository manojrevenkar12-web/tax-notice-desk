"""The knowledge the desk retrieves from: statutes paragraph by paragraph (with the version in force on a
given date), the firms' playbooks, and each client's history. Client history is tenant data and is only ever
retrieved for the firm that owns it."""

from __future__ import annotations

import datetime as dt
import functools
import re
from dataclasses import dataclass, field

import yaml

from .. import config

LAWS = {"ao_1977.md": "AO", "estg.md": "EStG", "gewstg.md": "GewStG", "kstg_1977.md": "KStG", "ustg_1980.md": "UStG"}
HEADING = re.compile(r"^#{3,6} (§ \d+[a-z]?)\b\s*(.*)$")


@dataclass
class Unit:
    id: str  # e.g. "AO § 122 (2)@2025-01-01"
    kind: str  # law | playbook | history
    ref: str  # e.g. "AO § 122"
    title: str
    text: str
    paragraph: str | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    stale_from: list[tuple[dt.date, str]] = field(default_factory=list)
    source: str = ""

    def current(self, on: dt.date) -> bool:
        return (self.valid_from is None or self.valid_from <= on) and (self.valid_to is None or on < self.valid_to)

    def staleness(self, on: dt.date) -> str | None:
        notes = [by for since, by in self.stale_from if since <= on]
        return "; ".join(notes) if notes else None


def _paragraphs(body: str) -> list[tuple[str | None, str]]:
    parts = re.split(r"\n(?=\(\d+[a-z]?\) )", "\n" + body.strip())
    out = []
    for p in parts:
        p = re.sub(r"\s+", " ", p).strip()
        if not p:
            continue
        m = re.match(r"\((\d+[a-z]?)\)", p)
        out.append((f"({m.group(1)})" if m else None, p))
    return out


def _chunks(text: str, size: int = 1400) -> list[str]:
    """Long paragraphs (EStG § 4 Abs. 5 runs to pages) are split at numbered items or sentences."""
    if len(text) <= size:
        return [text]
    parts = re.split(r"(?<=[.;:]) (?=\d+[a-z]?\. |[A-ZÄÖÜ])", text)
    out, cur = [], ""
    for p in parts:
        if cur and len(cur) + len(p) > size:
            out.append(cur)
            cur = text[:12] + " … " + p  # keep the paragraph number visible in every chunk
        else:
            cur = f"{cur} {p}".strip()
    if cur:
        out.append(cur)
    return out


@functools.cache
def law_units() -> tuple[Unit, ...]:
    amend = yaml.safe_load((config.CORPUS / "amendments.yaml").read_text())
    replaced: dict[tuple[str, str, str], list[dict]] = {}
    for a in amend["amended"]:
        replaced.setdefault((a["law"], a["section"], a["paragraph"]), []).append(a)
    stale: dict[tuple[str, str], list[tuple[dt.date, str]]] = {}
    for s in amend["changed_without_text"]:
        stale.setdefault((s["law"], s["section"]), []).append((dt.date.fromisoformat(s["from"]), s["by"]))
    units: list[Unit] = []
    used: set[tuple[str, str, str]] = set()
    titles: dict[str, str] = {}
    for fname, law in LAWS.items():
        text = (config.CORPUS / "laws" / fname).read_text()
        stand = re.search(r"Zuletzt geändert durch\s*\n:\s*(.+)", text)
        src = f"bundestag/gesetze, {law}, zuletzt geändert durch {stand.group(1).strip() if stand else '?'}"
        chunks = re.split(r"\n(?=#{3,6} § \d)", text)
        for ch in chunks:
            first, _, body = ch.partition("\n")
            m = HEADING.match(first.strip())
            if not m:
                continue
            sec, title = m.group(1), m.group(2).strip()
            if "(weggefallen)" in title or not body.strip():
                continue
            ref = f"{law} {sec}"
            titles[ref] = title
            for para, ptext in _paragraphs(body):
                used.add((law, sec, para or ""))
                versions = sorted(replaced.get((law, sec, para or ""), []), key=lambda a: a["from"])
                first_new = dt.date.fromisoformat(versions[0]["from"]) if versions else None
                base_id = f"{ref} {para or ''}".strip()
                for k, chunk in enumerate(_chunks(ptext)):
                    uid = f"{base_id}@corpus" + (f"#{k + 1}" if k else "")
                    units.append(Unit(uid, "law", ref, title, chunk, para, None, first_new, stale.get((law, sec), []),
                                      src))
                for i, v in enumerate(versions):
                    start = dt.date.fromisoformat(v["from"])
                    end = dt.date.fromisoformat(versions[i + 1]["from"]) if i + 1 < len(versions) else None
                    units.append(Unit(f"{base_id}@{v['from']}", "law", ref, title, " ".join(v["text"].split()), para,
                                      start, end, [], v["by"]))
    for (law, sec, para), versions in replaced.items():  # paragraphs inserted after the corpus was published
        if (law, sec, para) in used:
            continue
        versions = sorted(versions, key=lambda a: a["from"])
        for i, v in enumerate(versions):
            start = dt.date.fromisoformat(v["from"])
            end = dt.date.fromisoformat(versions[i + 1]["from"]) if i + 1 < len(versions) else None
            units.append(Unit(f"{law} {sec} {para}@{v['from']}", "law", f"{law} {sec}", titles.get(f"{law} {sec}", ""),
                              " ".join(v["text"].split()), para, start, end, [], v["by"]))
    return tuple(units)


@functools.cache
def playbook_units() -> tuple[Unit, ...]:
    out = []
    for f in sorted((config.CORPUS / "firm").glob("*.md")):
        text = f.read_text()
        title = text.splitlines()[0].lstrip("# ").strip()
        refs = re.findall(r"(?:AO|EStG|KStG|UStG|GewStG) § \d+[a-z]?", text)
        out.append(Unit(f"playbook:{f.stem}", "playbook", refs[0] if refs else "", title,
                        re.sub(r"\s+", " ", text), source=f"corpus/firm/{f.name}"))
    return tuple(out)


def history_units(rows: list[dict]) -> list[Unit]:
    out = []
    for r in rows:
        outcome = f"; objection: {r['outcome']}" if r.get("objection") else "; no objection"
        out.append(Unit(f"history:{r['client_id']}:{r['year']}:{r['kind']}", "history", "", f"{r['kind']} {r['year']}",
                        f"{r['year']} {r['kind']}: {r['text']}{outcome}", source="client file"))
    return out
