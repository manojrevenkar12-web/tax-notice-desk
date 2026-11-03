"""One notice through the desk: read, route, deduplicate, set the deadline, check, decide, explain.

Pure with respect to its inputs: the group's records (clients, filed returns, Messbescheide on file, client
histories) and the layout memory learned from corrections. The desk service stores what comes out; the
evaluation runs the same function over a split and compares it with the answer key.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from . import config
from .drafts.explain import explain
from .intake.model import read_with_model
from .intake.parse import Parsed, extract
from .intake.read import Reading, read, second_read
from .rules import checks
from .rules.deadlines import authority_deadline, objection_deadline
from .rules.decide import decide

ASSESSED = ("est", "kst", "ust", "gewst_mess")


@dataclass
class Group:
    firms: dict[str, dict]
    clients: dict[str, dict]
    by_taxno: dict[str, str]
    filed: dict[tuple[str, str, int], dict[str, int]]
    onfile: dict[tuple[str, int], list[dict]]
    history: dict[str, list[dict]]
    seen: dict[tuple, str] = field(default_factory=dict)
    memory: dict[str, dict[str, list[str]]] = field(default_factory=dict)  # authority -> field -> learned labels

    @classmethod
    def load(cls, folder: Path | None = None) -> Group:
        g = folder or config.DATA / "group"
        firms = {f["id"]: f for f in json.loads((g / "firms.json").read_text())}
        clients = {c["id"]: c for c in json.loads((g / "clients.json").read_text())}
        filed = {(r["client_id"], r["kind"], r["year"]): r["fields"] for r in json.loads((g / "filed.json").read_text())}
        onfile: dict[tuple[str, int], list[dict]] = {}
        for r in json.loads((g / "onfile.json").read_text()):
            onfile.setdefault((r["client_id"], r["year"]), []).append(r)
        history: dict[str, list[dict]] = {}
        for r in json.loads((g / "history.json").read_text()):
            history.setdefault(r["client_id"], []).append(r)
        return cls(firms, clients, {digits(c["steuernummer"]): c["id"] for c in clients.values()}, filed, onfile,
                   history)


def digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def _lev1(a: str, b: str) -> bool:
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    return SequenceMatcher(None, a, b).ratio() >= 1 - 1.5 / max(len(a), len(b))


def route(g: Group, p: Parsed, text: str) -> tuple[str | None, str]:
    """The client a notice belongs to: by tax number, tolerating one OCR error if the name confirms it."""
    d = digits(p.steuernummer)
    if d and d in g.by_taxno:
        return g.by_taxno[d], "tax number"
    low = text.lower()
    named = [cid for cid, c in g.clients.items() if c["name"].lower() in low]
    if d:
        near = [cid for t, cid in g.by_taxno.items() if _lev1(t, d)]
        both = [c for c in near if c in named]
        if len(both) == 1:
            return both[0], "tax number with one unclear digit, confirmed by name"
    found = [cid for t, cid in g.by_taxno.items() if t in digits(text)]
    if len(found) == 1 and found[0] in named:
        return found[0], "tax number found in text, confirmed by name"
    return None, "unknown tax number"


def municipality(p: Parsed, text: str) -> str | None:
    names = list(config.load("municipal")["hebesatz"])
    head = " ".join(text.splitlines()[:3]) + " " + (p.authority or "")
    best, score = None, 0.0
    for n in names:
        if n.lower() in text.lower():
            return n
        r = SequenceMatcher(None, n.lower(), head.lower()[: len(n) + 4]).ratio()
        if r > score:
            best, score = n, r
    return best if score >= 0.8 else None


def lands(g: Group, client: dict | None, firm: dict | None, muni: str | None, kind: str | None) -> tuple[str, ...]:
    firm_land = firm["land"] if firm else "BE"
    if kind == "gewst" and muni:
        return (firm_land, config.load("municipal")["land"].get(muni, firm_land))
    return (firm_land, client["land"] if client else firm_land)


def _date(s: str | None) -> dt.date | None:
    return dt.date.fromisoformat(s) if s else None


def read_notice(pdf: Path, xml: Path | None, memory: dict[str, list[str]] | None, authority_hint: str | None = None
                ) -> tuple[Reading, Parsed, dict[str, Any]]:
    r = read(pdf, xml)
    p = extract(r, memory)
    trail: dict[str, Any] = {"passes": ["first"], "model": {"calls": 0}}
    if r.source == "ocr" and not p.verified:
        alt = extract(Reading(second_read(pdf), "ocr"), memory)
        trail["passes"].append("second OCR")
        if alt.verified and alt.kind:
            alt.authority = alt.authority or p.authority
            p = alt
        elif alt.kind and p.kind and alt.kind == p.kind:  # values both passes agree on, then the arithmetic again
            merged = Parsed(**{**p.as_dict(), "fields": dict(p.fields), "method": dict(p.method)})
            for k, v in alt.fields.items():
                if k not in merged.fields:
                    merged.fields[k], merged.method[k] = v, "second OCR"
            from .intake.parse import _spec, verify
            spec = config.load("extraction")["fields"].get(merged.kind or "", {})
            merged.missing = [k for k, sp in spec.items() if k not in merged.fields and not _spec(sp).get("optional")]
            verify(merged)
            if merged.verified:
                p = merged
                trail["passes"].append("merged")
    if r.source == "ocr" and not p.verified and p.kind:
        q, meta = read_with_model(p, r.text)
        trail["model"] = meta
        if q is not None:
            p = q
            trail["passes"].append("model")
    return r, p, trail


def process(g: Group, nid: str, folder: Path, meta: dict[str, Any], use_model: bool = True) -> dict[str, Any]:
    pdf, xml = folder / f"{nid}.pdf", folder / f"{nid}.xml"
    first = read(pdf, xml if xml.exists() else None)
    muni_guess = municipality(extract(first), first.text) if "hebesatz" in first.text.lower() else None
    memory = g.memory.get(muni_guess or "", {})
    r, p, trail = read_notice(pdf, xml if xml.exists() else None, memory)
    cid, how = route(g, p, r.text)
    client = g.clients.get(cid) if cid else None
    firm = g.firms.get(client["firm"]) if client else None
    muni = municipality(p, r.text) if p.kind == "gewst" else None
    out: dict[str, Any] = {
        "id": nid, "channel": meta["channel"], "received_at": meta["received_at"], "kind": p.kind,
        "client_id": cid, "firm": client["firm"] if client else None, "routing": how, "parsed": p.as_dict(),
        "read": trail, "municipality": muni, "findings": [], "deadline": None, "explanation": [],
    }
    key = (cid, p.kind, p.tax_year, p.date) if cid and p.kind else None
    dup = g.seen.get(key) if key else None
    if key and not dup:
        g.seen[key] = nid
    # deadline
    posted = _date(p.date) or _date(meta.get("received_at"))
    lnd = lands(g, client, firm, muni, p.kind)
    if posted:
        if p.kind in ("request", "reminder") and p.due:
            dl = authority_deadline(dt.date.fromisoformat(p.due), posted)
        else:
            if meta["channel"] == "client_upload":  # how the original arrived is unknown: take the earlier date
                options = [objection_deadline(ch, posted, lnd, p.appeal_instructions, p.remedy, posted, posted)
                           for ch in ("post", "portal")]
                dl = min(options, key=lambda x: x.due)
                dl.notes.append("forwarded copy: the original's channel is unknown; the earlier of the postal and the "
                                "electronic deadline is kept")
            else:
                dl = objection_deadline(meta["channel"], posted, lnd, p.appeal_instructions, p.remedy,
                                        _date(meta.get("provided_at")), _date(meta.get("notified_at")),
                                        _date(meta.get("postmark")))
        out["deadline"] = dl.as_dict()
    # checks
    findings: list[checks.Finding] = []
    filed = g.filed.get((cid, p.kind, p.tax_year)) if cid and p.kind in ASSESSED and p.tax_year else None
    effect = 0
    if p.verified and p.kind in ASSESSED:
        if filed is None and not p.estimate:
            findings.append(checks.Finding("no_return", detail="no filed return on record for this year"))
        if filed is not None:
            findings += checks.compare(p.kind, p.fields, filed)
            effect = checks.tax_effect(p.kind, p.fields, filed)
        if out["deadline"] and p.kind in ("est", "kst", "ust"):
            f = checks.check_interest(p.kind, p.tax_year or 0, p.fields,
                                      dt.date.fromisoformat(out["deadline"]["bekanntgabe"]))
            if f:
                findings.append(f)
    if p.verified and p.kind == "gewst":
        mb = None
        files = sorted(g.onfile.get((cid, p.tax_year or 0), []), key=lambda x: x["date"]) if cid else []
        if files:
            mb = files[-1]["messbetrag"]
        findings += checks.check_gewst(p.fields, muni, p.tax_year or 0, mb)
    if p.estimate:
        findings.append(checks.Finding("estimate", detail="estimated because no return was filed (AO § 162)",
                                       sources=["AO § 162"]))
    out["findings"] = [f.as_dict() for f in findings]
    no_return_only = [f for f in findings if f.type == "no_return"]
    d = decide(p.kind, p.verified or p.kind in ("request", "reminder", "audit"), cid is not None, dup,
               [f for f in findings if f.type != "no_return"], effect, p.estimate,
               filed is not None or bool(no_return_only) is False)
    if no_return_only and d.action not in ("duplicate", "misrouted"):
        d.action, d.reasons = "review", ["no filed return on record to compare with"]
    out["action"], out["reasons"], out["tax_effect"], out["duplicate_of"] = d.action, d.reasons, effect, dup
    out["vorbehalt"], out["vorlaeufig"] = p.vorbehalt, p.vorlaeufig
    if d.action in ("objection_review", "objection_required", "inform_client") and findings:
        on = _date(p.date) or dt.date.today()
        out["explanation"] = explain(p, findings, g.history.get(cid or "", []), on, out["deadline"], use_model)
    return out
