"""Find the statute paragraphs and playbook entries that explain a deviation, as in force on a date.

Lexical retrieval (BM25 over German word stems) plus two exact signals: sections the notice itself cites, and
the sections config/retrieval.yaml associates with the changed figure. Every hit says which version of the
text it is and whether the corpus is known to be outdated for that date.
"""

from __future__ import annotations

import datetime as dt
import functools
import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from .. import config
from .corpus import Unit, law_units, playbook_units

STOP = set("der die das und oder ein eine einer eines einem den dem des zu zur zum im in ist sind wird wurden wurde "
           "werden nicht nur für von mit bei auf als an aus nach soweit da dass sich auch so oder sowie ab bis".split())
CITE = re.compile(r"§\s*(\d+[a-z]?)\s*(?:Abs\.?\s*\d+[a-z]?\s*)?(?:Satz\s*\d+\s*)?(?:Nr\.?\s*\d+[a-z]?\s*)?"
                  r"(AO|EStG|KStG|UStG|GewStG)")


def stem(w: str) -> str:
    w = w.lower().replace("ä", "a").replace("ö", "o").replace("ü", "u").replace("ß", "ss")
    for suf in ("ungen", "ung", "heiten", "heit", "keiten", "keit", "lichen", "lich", "ischen", "isch", "en", "er",
                "es", "em", "e", "n", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def tokens(text: str) -> list[str]:
    return [stem(w) for w in re.findall(r"[A-Za-zÄÖÜäöüß]{3,}", text) if w.lower() not in STOP]


@dataclass
class Hit:
    unit: Unit
    score: float
    why: str
    stale: str | None

    def as_dict(self) -> dict:
        u = self.unit
        return {"id": u.id, "kind": u.kind, "ref": u.ref, "paragraph": u.paragraph, "title": u.title,
                "text": u.text[:700], "score": round(self.score, 3), "why": self.why, "stale": self.stale,
                "source": u.source, "valid_from": u.valid_from.isoformat() if u.valid_from else None}


@functools.cache
def _index() -> tuple[BM25Okapi, tuple[Unit, ...]]:
    units = law_units() + playbook_units()
    return BM25Okapi([tokens(f"{u.title} {u.text}") for u in units]), units


def search(query: str, on: dt.date, field: str | None = None, k: int = 5, extra: list[Unit] | None = None) -> list[Hit]:
    bm, units = _index()
    hints = config.load("retrieval")["field_hints"].get(field or "", [])
    weights = config.load("retrieval")["weights"]
    cited = {f"{law} § {sec}" for sec, law in CITE.findall(query)}
    q = tokens(query)
    scores = bm.get_scores(q)
    top = max(scores) if len(scores) and max(scores) > 0 else 1.0
    ranked: dict[str, Hit] = {}
    for u, s in zip(units, scores, strict=True):
        if u.kind == "law" and not u.current(on):
            continue
        score, why = s / top, "text"
        if u.ref in cited:
            score += weights["cited"]
            why = "cited on the notice"
        if u.ref in hints:
            score += weights["field_hint"]
            why = why if why != "text" else "figure that changed"
        if u.kind == "playbook":
            score *= weights["playbook"]
        if score <= 0:
            continue
        key = u.ref if u.kind == "law" else u.id
        if key not in ranked or score > ranked[key].score:
            ranked[key] = Hit(u, score, why, u.staleness(on))
    if extra:
        hb = BM25Okapi([tokens(u.text) for u in extra]) if extra else None
        if hb:
            hs = hb.get_scores(q)
            for u, s in zip(extra, hs, strict=True):
                if s > 0:
                    ranked[u.id] = Hit(u, weights["history"] * s / max(max(hs), 1e-9), "client history", None)
    return sorted(ranked.values(), key=lambda h: -h.score)[:k]
