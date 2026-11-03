"""Drafts of an objection or a letter to the client. A template always exists; a model may reword it.
Whatever the source, the verifier checks the draft before a person sees it: every section it cites must be
one the desk retrieved or computed, every amount must be one on the notice or in the findings, and the
deadline and tax number must be the desk's. A draft that fails is replaced by the template."""

from __future__ import annotations

import re
from typing import Any

from .. import config
from . import claude_cli
from .explain import _eur

CITED = re.compile(r"§+\s*\d+[a-z]?(?:\s*Abs\.\s*\d+[a-z]?)?(?:\s*Satz\s*\d+)?(?:\s*Nr\.\s*\d+[a-z]?)?\s*"
                   r"(?:AO|EStG|KStG|UStG|GewStG|VwGO)")
AMOUNT = re.compile(r"-?\d{1,3}(?:\.\d{3})*,\d{2}\s?€")


def _sec(ref: str) -> str:
    """'§ 9 Abs. 1 EStG' and 'EStG § 9' -> 'EStG § 9'."""
    m = re.search(r"§+\s*(\d+[a-z]?)", ref)
    law = re.search(r"(AO|EStG|KStG|UStG|GewStG|VwGO)", ref)
    return f"{law.group(1) if law else ''} § {m.group(1) if m else ''}".strip()


def _de(iso: str | None) -> str:
    return f"{iso[8:10]}.{iso[5:7]}.{iso[:4]}" if iso else ""


def template(notice: dict[str, Any], kind: str = "objection") -> str:
    p = notice["parsed"]
    who = notice.get("client_name") or "unsere Mandantschaft"
    auth = p.get("authority") or "die Behörde"
    remedy = "Widerspruch" if p.get("remedy") == "Widerspruch" else "Einspruch"
    date = _de(p.get("date"))
    lines = []
    if kind == "objection":
        lines.append(f"An {auth}")
        lines.append(f"Steuernummer {p.get('steuernummer')} – {who}")
        lines.append(f"{remedy} gegen den Bescheid vom {date} für {p.get('tax_year')}")
        lines.append("")
        lines.append(f"namens und in Vollmacht unserer Mandantschaft legen wir gegen den oben genannten Bescheid "
                     f"{remedy} ein und begründen ihn wie folgt:")
        for i, item in enumerate(notice.get("explanation", []), 1):
            f = item["finding"]
            if f["type"] == "deviation" and not f.get("against"):
                continue
            src = ", ".join(item["sources"][:3])
            reason = (f"Der Bescheid enthält hierzu keine Begründung; wir bitten um Erläuterung der Abweichung."
                      if item.get("unexplained") else f"Begründung laut Bescheid: {item['office_says']}")
            lines.append(f"{i}. {item['what']}. {reason} Maßgeblich: {src}.")
        lines.append("")
        lines.append("Wir beantragen, den Bescheid entsprechend zu ändern, und die Aussetzung der Vollziehung in Höhe "
                     "des streitigen Betrags (§ 361 AO).")
    else:
        lines.append(f"Liebe Mandantschaft, der Bescheid vom {date} für {p.get('tax_year')} liegt vor.")
        for item in notice.get("explanation", []):
            lines.append(f"- {item['what']}.")
        lines.append("Wir melden uns, falls etwas zu tun ist.")
    return "\n".join(lines)


def allowed(notice: dict[str, Any]) -> tuple[set[str], set[str]]:
    secs = {"AO § 347", "AO § 355", "AO § 357", "AO § 361", "AO § 367", "VwGO § 70"}
    amounts: set[str] = set()
    for item in notice.get("explanation", []):
        secs |= {_sec(s) for s in item["sources"]}
        f = item["finding"]
        for k in ("filed", "stated", "expected"):
            if f.get(k) is not None:
                amounts.add(_eur(f[k]))
        if f.get("filed") is not None and f.get("stated") is not None:
            d = f["stated"] - f["filed"]
            amounts |= {_eur(d), _eur(abs(d)), "+" + _eur(d)}
    for v in notice["parsed"].get("fields", {}).values():
        amounts.add(_eur(v))
    if notice.get("tax_effect"):
        amounts |= {_eur(notice["tax_effect"]), _eur(abs(notice["tax_effect"]))}
    return secs, amounts


def verify(text: str, notice: dict[str, Any]) -> dict[str, Any]:
    secs, amounts = allowed(notice)
    cited = {_sec(c) for c in CITED.findall(text)} | {_sec(c) for c in re.findall(
        r"(?:AO|EStG|KStG|UStG|GewStG)\s*§+\s*\d+[a-z]?", text)}
    bad_secs = sorted(c for c in cited if c not in secs)
    bad_amounts = sorted({a.replace(" ", "") for a in AMOUNT.findall(text)} - {a.replace(" ", "") for a in amounts})
    p = notice["parsed"]
    problems = []
    if p.get("steuernummer") and p["steuernummer"] not in text:
        problems.append("tax number missing")
    due = (notice.get("deadline") or {}).get("due")
    for d in re.findall(r"\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4}", text):
        iso = d if "-" in d else f"{d[6:]}-{d[3:5]}-{d[:2]}"
        if iso not in {due, p.get("date"), p.get("messbescheid_date")}:
            problems.append(f"date {d} not from the notice or the register")
    ok = not bad_secs and not bad_amounts and not problems
    return {"ok": ok, "unknown_sections": bad_secs, "unknown_amounts": bad_amounts, "problems": problems}


def draft(notice: dict[str, Any], kind: str = "objection", use_model: bool = True) -> dict[str, Any]:
    base = template(notice, kind)
    cfg = config.load("drafts")
    out = {"kind": kind, "text": base, "written_by": "template", "verification": verify(base, notice), "model": None}
    if not (use_model and cfg["model"]["enabled"]):
        return out
    system = (config.ROOT / cfg["model"]["prompt"]).read_text()
    schema = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
    try:
        raw, key, replayed = claude_cli.ask(cfg["model"]["model"], system, base, schema, [], cfg["model"]["budget_usd"])
    except claude_cli.CacheMiss:
        return out
    text = (raw.get("structured_output") or {}).get("text") or ""
    v = verify(text, notice)
    meta = {"key": key, "replayed": replayed, "cost_usd": claude_cli.usage(raw)["cost_usd"], "verification": v}
    if text and v["ok"]:
        return {"kind": kind, "text": text, "written_by": cfg["model"]["model"], "verification": v, "model": meta}
    out["model"] = meta  # rejected: the template stays
    return out
