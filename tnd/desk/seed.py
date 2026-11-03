"""Load the simulated group into a fresh desk database, then store the pipeline's results for one split."""

from __future__ import annotations

import json
from typing import Any

import psycopg

from .. import config
from .db import j, migrate_down, migrate_up, owner_url
from .store import store_document, store_result

PEOPLE = [("clerk", "Sachbearbeitung"), ("clerk", "Fristenkontrolle"), ("advisor", "Steuerberatung")]
NAMES = ["Katrin Albers", "Stefan Brenner", "Dr. Miriam Cohn", "Ole Dietz", "Selin Ekinci", "Dr. Frank Gerber",
         "Ines Hahn", "Jan Ivanov", "Dr. Petra Jansen", "Lars Kühn", "Mona Lorenz", "Dr. Rainer Moll"]


def people(firms: list[dict]) -> list[dict[str, Any]]:
    out = []
    n = 0
    for f in firms:
        for role, _ in PEOPLE:
            out.append({"id": f"{f['id']}-p{n % 3}", "firm_id": f["id"], "name": NAMES[n % len(NAMES)], "role": role})
            n += 1
    out.append({"id": "g-mailroom", "firm_id": None, "name": "Poststelle der Gruppe", "role": "mailroom"})
    out.append({"id": "g-ops", "firm_id": None, "name": "Group operations", "role": "group_ops"})
    return out


def seed(split: str | None = "dev", url: str | None = None, use_model: bool = False) -> dict[str, int]:
    url = url or owner_url()
    migrate_down(url)
    migrate_up(url)
    g = config.DATA / "group"
    firms = json.loads((g / "firms.json").read_text())
    with psycopg.connect(url, autocommit=False) as c:
        for f in firms:
            c.execute("insert into firms values (%s,%s,%s,%s)", (f["id"], f["name"], f["city"], f["land"]))
        for p in people(firms):
            c.execute("insert into people values (%s,%s,%s,%s)", (p["id"], p["firm_id"], p["name"], p["role"]))
        for cl in json.loads((g / "clients.json").read_text()):
            c.execute("insert into clients values (%s,%s,%s,%s,%s,%s,%s,%s)",
                      (cl["id"], cl["firm"], cl["kind"], cl["name"], cl["steuernummer"], cl["address"], cl["land"],
                       cl["municipality"]))
        firm_of = {cl["id"]: cl["firm"] for cl in json.loads((g / "clients.json").read_text())}
        for r in json.loads((g / "filed.json").read_text()):
            c.execute("insert into filed_returns values (%s,%s,%s,%s,%s)",
                      (firm_of[r["client_id"]], r["client_id"], r["kind"], r["year"], j(r["fields"])))
        for r in json.loads((g / "onfile.json").read_text()):
            c.execute("insert into onfile (firm_id, client_id, kind, year, date, messbetrag) values (%s,%s,%s,%s,%s,%s)",
                      (r["firm"], r["client_id"], r["kind"], r["year"], r["date"], r["messbetrag"]))
        for r in json.loads((g / "history.json").read_text()):
            c.execute("insert into history (firm_id, client_id, year, kind, reason, text, objection, outcome) values "
                      "(%s,%s,%s,%s,%s,%s,%s,%s)", (r["firm"], r["client_id"], r["year"], r["kind"], r["reason"],
                                                     r["text"], r["objection"], r["outcome"]))
        c.commit()
    n = 0
    if split:
        results = json.loads((config.DATA / split / "results.json").read_text())
        folder = config.DATA / split / "inbox"
        for nid, r in results.items():
            meta = json.loads((folder / f"{nid}.json").read_text())
            store_document(nid, meta, folder / f"{nid}.pdf")
            store_result(r, use_model)
            n += 1
    return {"firms": len(firms), "notices": n}
