"""Run a held-out case set once and keep what happened.

Each case (or each group of cases sharing `group:`) gets its own small world: the firm, the client, the filed
return, the base notices on file. The notice text is printed into a PDF with a text layer and goes through the
same pipeline as everything else. The first run of a set is written to reports/heldout/<set>/first_run.json and
never rewritten; later runs go to latest_run.json.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .. import config
from ..pipeline import Group, digits, process


def text_pdf(text: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = A4[1] - 50
    for line in text.splitlines():
        if y < 40:
            c.showPage()
            y = A4[1] - 50
        c.setFont("Helvetica", 8.5)
        c.drawString(45, y, line)
        y -= 11.5
    c.showPage()
    c.save()
    return buf.getvalue()


def _group(cases: list[dict]) -> Group:
    firms: dict[str, dict] = {}
    clients: dict[str, dict] = {}
    filed: dict[tuple[str, str, int], dict[str, int]] = {}
    onfile: dict[tuple[str, int], list[dict]] = {}
    history: dict[str, list[dict]] = {}
    for c in cases:
        fid = f"f-{c['firm']['land'].lower()}"
        firms[fid] = {"id": fid, "name": "Kanzlei", "city": "", "land": c["firm"]["land"]}
        cl = c["client"]
        cid = f"c-{digits(cl['steuernummer'])}"
        clients[cid] = {
            "id": cid,
            "firm": fid,
            "kind": cl.get("kind", "person"),
            "name": cl["name"],
            "steuernummer": cl["steuernummer"],
            "land": cl.get("land", c["firm"]["land"]),
            "municipality": cl.get("municipality"),
        }
        if c.get("filed"):
            f = c["filed"]
            filed[(cid, f["kind"], int(f["year"]))] = f["fields"]
        for o in c.get("onfile") or []:
            onfile.setdefault((cid, int(o["year"])), []).append({**o, "client_id": cid})
        if c.get("history"):
            history[cid] = [{**h, "client_id": cid, "reason": None} for h in c["history"]]
    return Group(firms, clients, {digits(v["steuernummer"]): k for k, v in clients.items()}, filed, onfile, history)


def run_case(g: Group, case: dict, folder: Path, use_model: bool) -> dict[str, Any]:
    d = case["document"]
    nid = case["id"]
    (folder / f"{nid}.pdf").write_bytes(text_pdf(d["text"]))
    meta = {"id": nid, "channel": d["channel"], "received_at": str(d.get("received_at") or d["posted"])}
    for k in ("provided_at", "notified_at", "postmark"):
        if d.get(k):
            meta[k] = str(d[k])
    out = process(g, nid, folder, meta, use_model)
    exp = case["expect"]
    got_errors = sorted(
        {f["type"] for f in out["findings"]} & {"wrong_hebesatz", "stale_messbetrag", "arithmetic", "interest"}
    )
    checks = {
        "kind": out["kind"] == exp.get("kind", out["kind"]),
        "action": out["action"] == exp["action"],
        "deadline": (out["deadline"] or {}).get("due") == (str(exp["deadline"]) if exp.get("deadline") else None)
        if "deadline" in exp
        else True,
        "errors": got_errors == sorted(exp.get("errors") or []),
        "fields": all(out["parsed"]["fields"].get(k) == v for k, v in (exp.get("fields") or {}).items()),
    }
    late = bool(exp.get("deadline") and out["deadline"] and out["deadline"]["due"] > str(exp["deadline"]))
    return {
        "id": nid,
        "pass": all(checks.values()),
        "checks": checks,
        "late_deadline": late,
        "closed_but_needed_action": out["action"] == "close" and exp["action"] != "close",
        "expected": {k: (str(v) if isinstance(v, dt.date) else v) for k, v in exp.items()},
        "got": {
            "kind": out["kind"],
            "action": out["action"],
            "deadline": (out["deadline"] or {}).get("due"),
            "errors": got_errors,
            "reasons": out["reasons"],
            "fields": {k: out["parsed"]["fields"].get(k) for k in (exp.get("fields") or {})},
        },
        "why": case.get("why", ""),
    }


def run(name: str, use_model: bool = True) -> dict[str, Any]:
    folder = config.ROOT / "heldout" / name
    cases = yaml.safe_load((folder / "cases.yaml").read_text())
    status = (folder / "STATUS").read_text().strip()
    groups: dict[str, list[dict]] = defaultdict(list)
    for c in cases:
        groups[str(c.get("group") or c["id"])].append(c)
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        for _, members in groups.items():
            g = _group(members)
            for c in members:
                try:
                    results.append(run_case(g, c, Path(tmp), use_model))
                except Exception as e:  # a case the desk cannot even process is a failure, recorded as such
                    results.append({"id": c["id"], "pass": False, "error": f"{type(e).__name__}: {e}"})
    report = {
        "set": name,
        "status": status,
        "ran_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "cases": len(results),
        "passed": sum(r["pass"] for r in results),
        "late_deadlines": sum(r.get("late_deadline", False) for r in results),
        "closed_but_needed_action": sum(r.get("closed_but_needed_action", False) for r in results),
        "by_check": {
            k: sum(r.get("checks", {}).get(k, False) for r in results)
            for k in ("kind", "action", "deadline", "errors", "fields")
        },
        "failures": [r for r in results if not r["pass"]],
    }
    out = config.REPORTS / "heldout" / name
    out.mkdir(parents=True, exist_ok=True)
    first = out / "first_run.json"
    target = out / "latest_run.json" if first.exists() else first
    target.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str))
    report["recorded_as"] = target.name
    return report
