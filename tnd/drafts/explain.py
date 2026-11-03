"""Explain each finding to the person deciding: what changed, why the office says it changed, which law and
which playbook entry apply (as in force for that year), and what happened with this client before.

The explanation is built from retrieved text and the computed findings; nothing in it is generated. Drafts
of an objection, which a model may word, are in tnd/drafts/draft.py and are verified before anyone sees them.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from .. import config
from ..intake.parse import Parsed, _spec
from ..knowledge.corpus import history_units
from ..knowledge.retrieve import search
from ..rules.checks import Finding


def label(kind: str | None, fld: str | None) -> str:
    spec = config.load("extraction")["fields"].get(kind or "", {}).get(fld or "")
    return _spec(spec)["labels"][0] if spec else (fld or "")


def _eur(c: int | None) -> str:
    if c is None:
        return "–"
    return f"{c / 100:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _de(iso: str) -> str:
    return f"{iso[8:10]}.{iso[5:7]}.{iso[:4]}"


def german(f: Finding) -> str:
    """The finding in the words of a German letter (the desk's own computation, nothing generated)."""
    x = f.extra
    if f.type == "interest":
        return (
            f"Zinsen nach § 233a AO: festgesetzt {_eur(f.stated)}, nachgerechnet {_eur(f.expected)} (Zinslauf ab "
            f"{_de(x['start'])}, {x.get('months')} volle Monate auf {_eur(x.get('base'))}, 0,15 % je Monat)"
        )
    if f.type == "wrong_hebesatz":
        return (
            f"Hebesatz: angesetzt {(f.stated or 0) // 100} %, die Gemeinde {x.get('municipality')} erhebt für "
            f"{x.get('year')} {(f.expected or 0) // 100} %"
        )
    if f.type == "stale_messbetrag":
        return (
            f"Messbetrag: angesetzt {_eur(f.stated)}, der zuletzt festgesetzte Gewerbesteuermessbetrag beträgt "
            f"{_eur(f.expected)}"
        )
    if f.type == "arithmetic":
        return f"Rechenfehler: Messbetrag mal Hebesatz ergibt {_eur(f.expected)}, festgesetzt sind {_eur(f.stated)}"
    if f.type == "estimate":
        return "Die Besteuerungsgrundlagen wurden geschätzt (§ 162 AO); die Steuererklärung wird nachgereicht"
    return f.detail


def explain(
    p: Parsed, findings: list[Finding], history: list[dict], on: dt.date, deadline: dict | None, use_model: bool = True
) -> list[dict[str, Any]]:
    text = " ".join(p.explanations)
    hist_units = history_units(history)
    year_end = dt.date((p.tax_year or on.year), 12, 31)
    items = []
    for f in findings:
        if f.type == "deviation" and not f.primary:
            continue
        if f.type == "deviation":
            diff = (f.stated or 0) - (f.filed or 0)
            what = (
                f"{label(p.kind, f.field)}: erklärt {_eur(f.filed)}, festgesetzt {_eur(f.stated)} "
                f"({'+' if diff > 0 else ''}{_eur(diff)}, {'zu Lasten' if f.against else 'zugunsten'} des Mandanten)"
            )
            query = f"{text} {label(p.kind, f.field)}"
            fld = f.field
        else:
            what = german(f)
            query = f"{f.detail} {' '.join(f.sources)} {text}"
            fld = None
        hits = search(query, year_end, fld, k=3, extra=hist_units)
        law = [h for h in hits if h.unit.kind == "law"]
        prior = [h for h in hits if h.unit.kind == "history"]
        items.append(
            {
                "finding": f.as_dict(),
                "what": what,
                "office_says": text or None,
                "unexplained": f.type == "deviation" and (not text or "weichen von der Steuererklärung ab" in text),
                "law": [h.as_dict() for h in law],
                "playbook": [h.as_dict() for h in hits if h.unit.kind == "playbook"],
                "history": [h.as_dict() for h in prior],
                # what the draft may cite: the best match, sections the notice itself cites, and the rule's own sources
                "sources": sorted(
                    {h.unit.ref for h in law[:1]} | {h.unit.ref for h in law if h.why != "text"} | set(f.sources)
                ),
            }
        )
    return items
