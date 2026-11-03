"""Build the simulated group and its mail: data/group/* is what the firms know, data/<split>/inbox/* is what
arrives, data/<split>/truth.json is the answer key (read only by tnd/evals)."""

from __future__ import annotations

import json
import shutil
from concurrent.futures import ProcessPoolExecutor
from typing import Any

from .. import config
from .render import render
from .world import World


def _write(args: tuple[str, dict[str, Any]]) -> str:
    split, n = args
    folder = config.DATA / split / "inbox"
    files = render(n)
    (folder / f"{n['id']}.pdf").write_bytes(files["pdf"])
    if "xml" in files:
        (folder / f"{n['id']}.xml").write_bytes(files["xml"])
    (folder / f"{n['id']}.json").write_text(json.dumps({"id": n["id"], **n["meta"]}, indent=1))
    return n["id"]


def build(splits: tuple[str, ...] = ("dev", "test", "heldout")) -> dict[str, int]:
    w = World()
    out: dict[str, int] = {}
    jobs: list[tuple[str, dict[str, Any]]] = []
    for split in splits:
        notices = w.split(split)
        folder = config.DATA / split
        if folder.exists():
            shutil.rmtree(folder)
        (folder / "inbox").mkdir(parents=True)
        (folder / "truth.json").write_text(
            json.dumps({n["id"]: {**n["truth"], "doc": n["doc"]} for n in notices}, indent=1, ensure_ascii=False)
        )
        jobs += [(split, n) for n in notices]
        out[split] = len(notices)
    with ProcessPoolExecutor() as ex:
        list(ex.map(_write, jobs, chunksize=8))
    group = config.DATA / "group"
    group.mkdir(parents=True, exist_ok=True)
    clients = [
        {
            "id": c.id,
            "firm": c.firm,
            "kind": c.kind,
            "name": c.name,
            "steuernummer": c.steuernummer,
            "address": c.address,
            "land": c.land,
            "municipality": (w.munis[c.municipality]["name"] if c.municipality else None),
        }
        for c in w.clients
    ]
    filed = [
        {"client_id": c.id, "kind": k, "year": y, "fields": f}
        for c in w.clients
        for k, ys in c.filed.items()
        for y, f in ys.items()
        if (c.id, k, y) not in w.unfiled
    ]
    (group / "firms.json").write_text(json.dumps(w.firms, indent=1, ensure_ascii=False))
    (group / "clients.json").write_text(json.dumps(clients, indent=1, ensure_ascii=False))
    (group / "filed.json").write_text(json.dumps(filed, indent=1, ensure_ascii=False))
    (group / "onfile.json").write_text(json.dumps(w.onfile, indent=1, ensure_ascii=False))
    (group / "history.json").write_text(json.dumps(w.histories(), indent=1, ensure_ascii=False))
    return out
