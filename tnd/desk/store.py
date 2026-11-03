"""Write what the pipeline concluded into the desk, as the runtime role, inside the firm's own scope."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..drafts.draft import draft
from .db import j, session


def store_document(nid: str, meta: dict, pdf: Path) -> None:
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    with session(None, "mailroom") as c:
        c.execute("insert into documents (id, firm_id, channel, received_at, meta, sha256, path) values "
                  "(%s, null, %s, %s, %s, %s, %s) on conflict (id) do nothing",
                  (nid, meta["channel"], meta["received_at"], j(meta), sha, str(pdf)))
        c.execute("insert into audit_log (firm_id, actor, action, subject) values (null, 'mailroom', 'received', %s)",
                  (nid,))


def route_document(nid: str, firm: str) -> None:
    with session(None, "mailroom") as c:
        c.execute("select route_document(%s, %s)", (nid, firm))
        c.execute("insert into audit_log (firm_id, actor, action, subject, detail) values (%s, 'desk', 'routed', %s, "
                  "%s)", (firm, nid, j({"firm": firm})))


def store_result(r: dict[str, Any], use_model: bool = False) -> None:
    firm = r["firm"]
    if not firm:
        return  # misrouted: stays with the mailroom
    route_document(r["id"], firm)
    p = r["parsed"]
    with session(firm) as c:
        name = None
        if r["client_id"]:
            row = c.execute("select name from clients where id = %s", (r["client_id"],)).fetchone()
            name = row["name"] if row else None
        c.execute(
            "insert into notices (id, firm_id, client_id, kind, tax_year, authority, notice_date, action, reasons, "
            "parsed, findings, explanation, tax_effect) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "on conflict (id) do nothing",
            (r["id"], firm, r["client_id"], r["kind"], p.get("tax_year"), p.get("authority"), p.get("date"),
             r["action"], j(r["reasons"]), j(p), j(r["findings"]), j(r["explanation"]), r.get("tax_effect") or 0))
        if r.get("deadline") and r["action"] not in ("duplicate", "close"):
            d = r["deadline"]
            c.execute("insert into deadlines (firm_id, notice_id, due, bekanntgabe, basis, rules, notes, later_possible, "
                      "proposed_by) values (%s,%s,%s,%s,%s,%s,%s,%s,'desk')",
                      (firm, r["id"], d["due"], d["bekanntgabe"], d["basis"], j(d["rules"]), j(d["notes"]),
                       d.get("later_possible")))
        if r["action"] in ("objection_review", "objection_required"):
            dr = draft({**r, "client_name": name}, "objection", use_model)
            c.execute("insert into drafts (firm_id, notice_id, kind, text, citations, verification, written_by) values "
                      "(%s,%s,'objection',%s,%s,%s,%s)",
                      (firm, r["id"], dr["text"], j(sorted({s for i in r["explanation"] for s in i["sources"]})),
                       j(dr["verification"]), dr["written_by"]))
        if r["action"] in ("inform_client", "objection_review", "objection_required"):
            c.execute("insert into outbox (firm_id, topic, payload) values (%s, 'client.notice_received', %s)",
                      (firm, j({"notice": r["id"], "client": r["client_id"], "action": r["action"]})))
        c.execute("insert into audit_log (firm_id, actor, action, subject, detail) values (%s,'desk','assessed',%s,%s)",
                  (firm, r["id"], j({"action": r["action"], "reasons": r["reasons"]})))
