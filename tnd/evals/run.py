"""Run the desk over a split in arrival order and score it against the answer key.

A simulated clerk handles what the desk sends to review: for a town's notice it corrects the fields, and the
desk learns the label that town uses (layout memory). That is the feedback loop the numbers below measure.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from collections import Counter
from typing import Any

from .. import config
from ..pipeline import Group, process
from ..sim.render import muni_style

CRITICAL = ("closed_but_needed_action", "late_deadlines", "verified_wrong_values", "missed_required_objection",
            "wrong_client")


def _clerk_learns(g: Group, out: dict, truth: dict) -> int:
    """The clerk corrects a town notice the desk could not read; the desk remembers the town's labels."""
    doc = truth["doc"]
    if doc["authority"]["kind"] != "gemeinde":
        return 0
    style = muni_style(doc["authority"]["id"])
    muni = out.get("municipality") or doc["authority"]["name"]
    mem = g.memory.setdefault(muni, {})
    fixed = 0
    for fld, lab in style["labels"].items():
        got = out["parsed"]["fields"].get(fld)
        if got != doc["fields"].get(fld):
            fixed += 1
        if lab not in mem.get(fld, []):
            mem.setdefault(fld, []).insert(0, lab)
    return fixed


def evaluate(split: str, use_model: bool = True, write: bool = True, limit: int | None = None) -> dict[str, Any]:
    folder = config.DATA / split / "inbox"
    truth = json.loads((config.DATA / split / "truth.json").read_text())
    metas = [json.loads(p.read_text()) for p in folder.glob("*.json")]
    metas.sort(key=lambda m: (m["received_at"], m["id"]))
    if limit:
        metas = metas[:limit]
    g = Group.load()
    rows, t0 = [], time.time()
    muni_seen: Counter[str] = Counter()
    learning = []
    for m in metas:
        t1 = time.time()
        out = process(g, m["id"], folder, m, use_model)
        out["ms"] = round((time.time() - t1) * 1000)
        tr = truth[m["id"]]
        if tr["doc"]["authority"]["kind"] == "gemeinde" and tr["action"] not in ("duplicate", "misrouted"):
            name = tr["doc"]["authority"]["name"]
            muni_seen[name] += 1
            needed = out["action"] == "review"
            learning.append({"municipality": name, "occurrence": muni_seen[name], "review": needed})
            if needed:
                out["clerk_fixed"] = _clerk_learns(g, out, tr)
        rows.append((out, tr))
    report = score(rows, learning)
    report.update(split=split, notices=len(rows), seconds=round(time.time() - t0, 1),
                  model_calls=sum(o["read"]["model"].get("calls", 0) for o, _ in rows),
                  model_cost_usd=round(sum(o["read"]["model"].get("cost_usd", 0) for o, _ in rows), 4),
                  versions={k: config.load(k).get("version") for k in ("rules", "extraction")})
    if write:
        out_dir = config.REPORTS / "evals"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{split}.json").write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str))
        (config.DATA / split / "results.json").write_text(
            json.dumps({o["id"]: o for o, _ in rows}, indent=1, ensure_ascii=False, default=str))
    return report


def score(rows: list[tuple[dict, dict]], learning: list[dict]) -> dict[str, Any]:
    c: Counter[str] = Counter()
    confusion: Counter[str] = Counter()
    examples: dict[str, list[str]] = {}
    ret_hit = ret_tot = 0
    err_tp = err_fn = err_fp = 0
    by_channel: dict[str, Counter[str]] = {}

    def ex(key: str, nid: str) -> None:
        examples.setdefault(key, [])
        if len(examples[key]) < 8:
            examples[key].append(nid)

    for out, tr in rows:
        nid = out["id"]
        ch = by_channel.setdefault(out["channel"], Counter())
        ch["notices"] += 1
        c["notices"] += 1
        confusion[f"{tr['action']} -> {out['action']}"] += 1
        if out["action"] == tr["action"]:
            c["action_right"] += 1
            ch["action_right"] += 1
        else:
            ex("wrong_action", nid)
        if out["action"] == "review":
            c["review"] += 1
            ch["review"] += 1
        if tr["action"] == "close":
            c["truth_close"] += 1
            if out["action"] == "close":
                c["auto_closed"] += 1
        if out["action"] == "close" and tr["action"] != "close":
            c["closed_but_needed_action"] += 1
            ex("closed_but_needed_action", nid)
        if tr["action"] == "objection_required" and out["action"] in ("close", "inform_client"):
            c["missed_required_objection"] += 1
            ex("missed_required_objection", nid)
        if tr["client_id"] is not None and out["client_id"] not in (None, tr["client_id"]):
            c["wrong_client"] += 1
            ex("wrong_client", nid)
        if tr["action"] not in ("duplicate", "misrouted"):
            c["kind_total"] += 1
            if out["kind"] == tr["kind"]:
                c["kind_right"] += 1
            # values
            p = out["parsed"]
            want = tr["doc"]["fields"]
            if p["verified"] and out["kind"] == tr["kind"]:
                wrong = [k for k, v in p["fields"].items() if k in want and want[k] != v]
                if wrong:
                    c["verified_wrong_values"] += 1
                    ex("verified_wrong_values", nid)
            # deadline
            if out["deadline"]:
                c["deadline_total"] += 1
                due, want_due = out["deadline"]["due"], tr["deadline"]
                if due == want_due:
                    c["deadline_exact"] += 1
                elif due > want_due:
                    c["late_deadlines"] += 1
                    ex("late_deadlines", nid)
                else:
                    c["early_deadlines"] += 1
                    ex("early_deadlines", nid)
            else:
                c["deadline_missing"] += 1
                ex("deadline_missing", nid)
            # errors on the face of the notice
            want_err = {e["type"] for e in tr["errors"]}
            got_err = {f["type"] for f in out["findings"]} & {"wrong_hebesatz", "stale_messbetrag", "arithmetic",
                                                               "interest"}
            if out["parsed"]["verified"]:
                err_tp += len(want_err & got_err)
                err_fn += len(want_err - got_err)
                err_fp += len(got_err - want_err)
                if got_err - want_err:
                    ex("false_error", nid)
            # retrieval for explained deviations
            for d in tr["deviations"]:
                if not d["reason"]:
                    continue
                items = [i for i in out.get("explanation", []) if i["finding"].get("field") == d["field"]]
                if not items:
                    continue
                ret_tot += 1
                if any(cite in items[0]["sources"] for cite in d["cite"]):
                    ret_hit += 1
    first = [x for x in learning if x["occurrence"] == 1]
    later = [x for x in learning if x["occurrence"] > 1]

    def rate(a: int, b: int) -> float | None:
        return round(a / b, 4) if b else None

    return {
        "counts": dict(c),
        "metrics": {
            "action_accuracy": rate(c["action_right"], c["notices"]),
            "review_rate": rate(c["review"], c["notices"]),
            "auto_close_rate": rate(c["auto_closed"], c["truth_close"]),
            "kind_accuracy": rate(c["kind_right"], c["kind_total"]),
            "deadline_exact": rate(c["deadline_exact"], c["deadline_total"]),
            "late_deadlines": c["late_deadlines"],
            "closed_but_needed_action": c["closed_but_needed_action"],
            "missed_required_objection": c["missed_required_objection"],
            "verified_wrong_values": c["verified_wrong_values"],
            "wrong_client": c["wrong_client"],
            "error_recall": rate(err_tp, err_tp + err_fn),
            "error_precision": rate(err_tp, err_tp + err_fp),
            "retrieval_recall_at_3": rate(ret_hit, ret_tot),
            "town_review_first_notice": rate(sum(x["review"] for x in first), len(first)),
            "town_review_later_notices": rate(sum(x["review"] for x in later), len(later)),
        },
        "by_channel": {k: {"notices": v["notices"], "action_accuracy": rate(v["action_right"], v["notices"]),
                           "review_rate": rate(v["review"], v["notices"])} for k, v in sorted(by_channel.items())},
        "confusion": dict(sorted(confusion.items())),
        "examples": examples,
        "ran_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
    }
