"""tax-notice-desk command line.

tnd build                  generate the simulated group and its mail (data/)
tnd warm                   OCR every scan once, in parallel (fixtures/ocr_cache)
tnd eval <split>           run the desk over a split and score it (reports/evals/<split>.json)
tnd release                evaluate on test and apply config/gates.yaml (reports/release.{json,md})
tnd heldout <set>          run a blind case set (first run kept)
tnd migrate [--down]       database migrations
tnd seed [split]           fresh database with the group and one split's results
tnd serve                  API and console
"""

from __future__ import annotations

import argparse
import json
import sys

from . import config


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tnd", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    w = sub.add_parser("warm")
    w.add_argument("--prune", action="store_true", help="delete cached OCR of files that no longer exist")
    e = sub.add_parser("eval")
    e.add_argument("split")
    e.add_argument("--no-model", action="store_true")
    e.add_argument("--limit", type=int)
    e.add_argument("--name", default="", help="write reports/evals/<split>-<name>.json, leave results alone")
    r = sub.add_parser("release")
    r.add_argument("--no-model", action="store_true")
    h = sub.add_parser("heldout")
    h.add_argument("set")
    h.add_argument("--no-worse", action="store_true", help="fail only if fewer cases pass than on the first run")
    h.add_argument("--no-model", action="store_true")
    m = sub.add_parser("migrate")
    m.add_argument("--down", action="store_true")
    s = sub.add_parser("seed")
    s.add_argument("split", nargs="?", default="dev")
    s.add_argument("--model", action="store_true", help="let the model word objection drafts")
    sv = sub.add_parser("serve")
    sv.add_argument("--port", type=int, default=8095)
    a = ap.parse_args(argv)

    if a.cmd == "build":
        from .sim.build import build

        print(build())
    elif a.cmd == "warm":
        from .intake.warm import warm

        print(warm(clean=a.prune))
    elif a.cmd == "eval":
        from .evals.run import evaluate

        rep = evaluate(a.split, not a.no_model, limit=a.limit, name=a.name)
        print(json.dumps(rep["metrics"], indent=1))
    elif a.cmd == "release":
        from .evals.gate import decide, render
        from .evals.run import evaluate

        rep = evaluate(config.load("gates")["split"], not a.no_model)
        d = decide(rep)
        (config.REPORTS / "release.json").write_text(json.dumps(d, indent=1))
        (config.REPORTS / "release.md").write_text(render(d, rep))
        print(render(d, rep))
        return 0 if d["ship"] else 1
    elif a.cmd == "heldout":
        from .evals.heldout import run

        first = config.REPORTS / "heldout" / a.set / "first_run.json"
        before = json.loads(first.read_text())["passed"] if first.exists() else None
        rep = run(a.set, not a.no_model)
        print(
            f"{a.set} ({rep['status']}): {rep['passed']}/{rep['cases']} cases pass; late deadlines "
            f"{rep['late_deadlines']}; recorded as {rep['recorded_as']}"
        )
        for f in rep["failures"]:
            print(" ", f["id"], f.get("error") or {k: v for k, v in f["checks"].items() if not v}, f.get("got"))
        if a.no_worse and before is not None and rep["passed"] < before:
            return 1
    elif a.cmd == "migrate":
        from .desk.db import migrate_down, migrate_up

        print(migrate_down() if a.down else migrate_up())
    elif a.cmd == "seed":
        from .desk.seed import seed

        print(seed(a.split, use_model=a.model))
    elif a.cmd == "serve":
        import uvicorn

        uvicorn.run("tnd.desk.app:app", host="127.0.0.1", port=a.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
