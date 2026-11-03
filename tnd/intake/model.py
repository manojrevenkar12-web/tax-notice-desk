"""Ask the model to read a notice the rules could not read with certainty. Its answer is used only if the
notice's own arithmetic then holds (tnd/intake/parse.verify): the model reads, the arithmetic decides."""

from __future__ import annotations

import copy
from typing import Any

from .. import config
from ..drafts import claude_cli
from .parse import Parsed, _spec, verify


def schema(kind: str) -> dict[str, Any]:
    fields = config.load("extraction")["fields"][kind]
    props: dict[str, Any] = {k: {"type": ["integer", "null"], "description": "cents; hebesatz as percent x 100"}
                             for k in fields}
    return {"type": "object", "properties": {"fields": {"type": "object", "properties": props}},
            "required": ["fields"]}


def read_with_model(p: Parsed, text: str) -> tuple[Parsed | None, dict[str, Any]]:
    cfg = config.load("extraction").get("model", {})
    if not cfg.get("enabled") or p.kind not in config.load("extraction")["fields"]:
        return None, {"calls": 0}
    labels = {k: _spec(v)["labels"] for k, v in config.load("extraction")["fields"][p.kind].items()}
    system = (config.ROOT / cfg["prompt"]).read_text()
    user = f"Kind of notice: {p.kind}\nFields and the usual labels: {labels}\n\nOCR text:\n{text[:6000]}"
    try:
        raw, key, replayed = claude_cli.ask(cfg["model"], system, user, schema(p.kind), [], cfg["budget_usd"])
    except claude_cli.CacheMiss:
        return None, {"calls": 0, "cache_miss": True}
    use = claude_cli.usage(raw)
    out = (raw.get("structured_output") or {}).get("fields") or {}
    q = copy.deepcopy(p)
    for k, v in out.items():
        if isinstance(v, int) and k in labels:
            q.fields[k] = v
            q.method[k] = "model"
    q.missing = [k for k, sp in config.load("extraction")["fields"][p.kind].items()
                 if k not in q.fields and not _spec(sp).get("optional")]
    q.source = "ocr"
    verify(q)
    meta = {"calls": 1, "cost_usd": use["cost_usd"], "replayed": replayed, "key": key, "accepted": q.verified}
    return (q if q.verified else None), meta
