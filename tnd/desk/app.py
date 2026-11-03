"""The desk's HTTP API. Every request runs in a transaction bound to the caller's firm; the database's
row-level security, constraints and triggers hold the rules even if this code is wrong."""

from __future__ import annotations

import datetime as dt
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import config
from ..drafts.draft import verify as verify_draft
from ..rules.checks import compare
from .auth import Principal, mint, verify
from .db import j, session

app = FastAPI(title="tax-notice-desk", version="1")


@app.exception_handler(psycopg.errors.RaiseException)
async def _db_rule(_: Request, e: Exception) -> JSONResponse:
    return JSONResponse({"title": "Refused by the database", "detail": str(e).splitlines()[0]}, status_code=409)


@app.exception_handler(psycopg.errors.CheckViolation)
async def _db_check(_: Request, e: Exception) -> JSONResponse:
    return JSONResponse({"title": "Refused by the database", "detail": str(e).splitlines()[0]}, status_code=409)


def me(authorization: str = Header(default="")) -> Principal:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "sign in first")
    try:
        return verify(authorization.removeprefix("Bearer "))
    except Exception as e:  # noqa: BLE001 - any token problem is a 401
        raise HTTPException(401, "invalid or expired token") from e


def need(p: Principal, action: str) -> None:
    if not p.can(action):
        raise HTTPException(403, f"your role ({p.role}) may not {action.replace('_', ' ')}")


def audit(c: psycopg.Connection[Any], p: Principal, action: str, subject: str, detail: dict | None = None) -> None:
    c.execute(
        "insert into audit_log (firm_id, actor, on_behalf_of, action, subject, detail) values (%s,%s,%s,%s,%s,%s)",
        (p.firm, p.actor or p.person, p.person if p.actor else None, action, subject, j(detail or {})),
    )


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


class SignIn(BaseModel):
    person: str


@app.get("/api/dev/people")
def dev_people() -> list[dict]:
    if os.environ.get("TND_ENV") == "production":
        raise HTTPException(404)
    with psycopg.connect(os.environ.get("TND_OWNER_URL", config.load("desk")["database"]["owner_url"])) as c:
        rows = c.execute(
            "select p.id, p.name, p.role, p.firm_id, f.name from people p left join firms f on "
            "f.id = p.firm_id order by p.firm_id nulls last, p.id"
        ).fetchall()
    return [{"id": r[0], "name": r[1], "role": r[2], "firm": r[3], "firm_name": r[4]} for r in rows]


@app.post("/api/dev/sign-in")
def dev_sign_in(body: SignIn) -> dict:
    people = {p["id"]: p for p in dev_people()}
    p = people.get(body.person)
    if not p:
        raise HTTPException(404, "no such person")
    pr = Principal(p["id"], p["firm"], p["role"])
    return {"token": mint(pr), "person": p}


def today() -> str:
    """The desk's date: TND_TODAY for a replayed month, otherwise the real one."""
    return os.environ.get("TND_TODAY") or dt.date.today().isoformat()


@app.get("/api/me")
def whoami(p: Principal = Depends(me)) -> dict:
    with session(p.firm) as c:
        firm = c.execute("select name, city from firms where id = %s", (p.firm,)).fetchone() if p.firm else None
    return {
        "person": p.person,
        "firm": p.firm,
        "role": p.role,
        "actor": p.actor,
        "today": today(),
        "firm_name": firm["name"] if firm else "Group",
        "city": firm["city"] if firm else "",
    }


def _firm(p: Principal) -> str:
    if not p.firm:
        raise HTTPException(403, "this view belongs to a firm")
    need(p, "read")
    return p.firm


@app.get("/api/inbox")
def inbox(status: str = "open", p: Principal = Depends(me)) -> list[dict]:
    firm = _firm(p)
    with session(firm) as c:
        rows = c.execute(
            "select n.id, n.kind, n.tax_year, n.authority, n.notice_date, n.action, n.reasons, n.status, n.tax_effect, "
            "n.client_id, cl.name as client, d.due, d.status as deadline_status, d.id as deadline_id, "
            "(n.parsed->>'verified')::boolean as verified, docs.channel "
            "from notices n left join clients cl on cl.id = n.client_id "
            "left join deadlines d on d.notice_id = n.id and d.status <> 'cancelled' "
            "join documents docs on docs.id = n.id "
            "where n.status = %s order by d.due nulls last, n.id",
            (status,),
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/notices/{nid}")
def notice(nid: str, p: Principal = Depends(me)) -> dict:
    firm = _firm(p)
    with session(firm) as c:
        n = c.execute(
            "select n.*, cl.name as client, cl.steuernummer, cl.kind as client_kind from notices n "
            "left join clients cl on cl.id = n.client_id where n.id = %s",
            (nid,),
        ).fetchone()
        if not n:
            raise HTTPException(404, "no such notice in your firm")
        filed = None
        if n["client_id"] and n["tax_year"]:
            row = c.execute(
                "select fields from filed_returns where client_id=%s and kind=%s and year=%s",
                (n["client_id"], n["kind"], n["tax_year"]),
            ).fetchone()
            filed = row["fields"] if row else None
        deadlines = c.execute("select * from deadlines where notice_id = %s order by id", (nid,)).fetchall()
        drafts = c.execute("select * from drafts where notice_id = %s order by id", (nid,)).fetchall()
        doc = c.execute("select channel, received_at, meta from documents where id = %s", (nid,)).fetchone()
        history = (
            c.execute(
                "select year, kind, text, objection, outcome from history where client_id = %s order by year desc",
                (n["client_id"],),
            ).fetchall()
            if n["client_id"]
            else []
        )
    return {
        **dict(n),
        "filed": filed,
        "deadlines": [dict(d) for d in deadlines],
        "drafts": [dict(d) for d in drafts],
        "document": dict(doc) if doc else None,
        "history": [dict(h) for h in history],
    }


@app.get("/api/notices/{nid}/page.png")
def page(nid: str, p: Principal = Depends(me)) -> Response:
    firm = _firm(p)
    with session(firm) as c:
        row = c.execute("select path from documents where id = %s", (nid,)).fetchone()
    if not row:
        raise HTTPException(404)
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["pdftoppm", "-r", "90", "-png", "-singlefile", row["path"], f"{d}/p"], check=True)
        png = Path(f"{d}/p.png").read_bytes()
    return Response(png, media_type="image/png")


class Correction(BaseModel):
    field: str = Field(pattern=r"^[a-z_0-9]+$")
    value: int
    label: str | None = Field(default=None, max_length=80)


@app.post("/api/notices/{nid}/fields")
def correct(nid: str, body: Correction, p: Principal = Depends(me)) -> dict:
    firm = _firm(p)
    need(p, "correct")
    with session(firm) as c:
        n = c.execute(
            "select parsed, kind, authority, client_id, tax_year from notices where id = %s and status='open'", (nid,)
        ).fetchone()
        if not n:
            raise HTTPException(404, "no open notice with this id in your firm")
        parsed = n["parsed"]
        old = parsed["fields"].get(body.field)
        parsed["fields"][body.field] = body.value
        parsed.setdefault("method", {})[body.field] = "person"
        cid = c.execute(
            "insert into corrections (firm_id, notice_id, field, old_value, new_value, label, by_person) "
            "values (%s,%s,%s,%s,%s,%s,%s) returning id",
            (firm, nid, body.field, old, body.value, body.label, p.person),
        ).fetchone()["id"]  # type: ignore[index]
        if body.label and n["authority"]:
            c.execute(
                "insert into layout_memory (authority, field, label, learned_from) values (%s,%s,%s,%s) "
                "on conflict do nothing",
                (n["authority"], body.field, body.label, cid),
            )
        findings = None
        if n["client_id"] and n["tax_year"]:
            row = c.execute(
                "select fields from filed_returns where client_id=%s and kind=%s and year=%s",
                (n["client_id"], n["kind"], n["tax_year"]),
            ).fetchone()
            if row:
                findings = [f.as_dict() for f in compare(n["kind"], parsed["fields"], row["fields"])]
        c.execute(
            "update notices set parsed = %s" + (", findings = %s" if findings is not None else "") + " where id = %s",
            ((j(parsed), j(findings), nid) if findings is not None else (j(parsed), nid)),
        )
        audit(c, p, "corrected", nid, {"field": body.field, "old": old, "new": body.value})
    return {"ok": True, "correction": cid}


class Decide(BaseModel):
    outcome: str = Field(
        pattern=r"^(close|inform_client|task_done|duplicate|objection_filed|no_objection|"
        r"return_to_mailroom)$"
    )
    note: str | None = Field(default=None, max_length=2000)


@app.post("/api/notices/{nid}/decision")
def decide(nid: str, body: Decide, p: Principal = Depends(me)) -> dict:
    firm = _firm(p)
    simple = body.outcome in config.load("desk")["simple_decisions"]
    need(p, "decide_simple" if simple else "decide_objection")
    with session(firm) as c:
        n = c.execute("select action from notices where id = %s and status = 'open'", (nid,)).fetchone()
        if not n:
            raise HTTPException(404, "no open notice with this id in your firm")
        open_dl = c.execute(
            "select count(*) as k from deadlines where notice_id=%s and status='proposed'", (nid,)
        ).fetchone()["k"]  # type: ignore[index]
        if open_dl and body.outcome != "duplicate":
            raise HTTPException(409, "confirm the deadline first (a second person checks every deadline)")
        if body.outcome == "objection_filed":
            ok = c.execute(
                "select count(*) as k from drafts where notice_id=%s and status='released'", (nid,)
            ).fetchone()["k"]  # type: ignore[index]
            if not ok:
                raise HTTPException(409, "release the objection draft first")
        c.execute(
            "update notices set status='done', outcome=%s, decided_by=%s, decided_at=now() where id=%s",
            (body.outcome, p.person, nid),
        )
        c.execute("update deadlines set status='done' where notice_id=%s and status='confirmed'", (nid,))
        audit(c, p, "decided", nid, {"outcome": body.outcome, "note": body.note})
    return {"ok": True, "status": "done", "outcome": body.outcome}


@app.get("/api/deadlines")
def deadlines(p: Principal = Depends(me)) -> list[dict]:
    firm = _firm(p)
    with session(firm) as c:
        rows = c.execute(
            "select d.*, n.kind, n.action, n.authority, cl.name as client from deadlines d "
            "join notices n on n.id = d.notice_id left join clients cl on cl.id = n.client_id "
            "where d.status in ('proposed','confirmed') order by d.due, d.id"
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/deadlines/{did}/confirm")
def confirm(did: int, p: Principal = Depends(me)) -> dict:
    firm = _firm(p)
    need(p, "confirm_deadline")
    with session(firm) as c:
        row = c.execute(
            "update deadlines set status='confirmed', confirmed_by=%s, confirmed_at=now() where id=%s and "
            "status='proposed' returning id, due",
            (p.person, did),
        ).fetchone()
        if not row:
            raise HTTPException(404, "no proposed deadline with this id in your firm")
        audit(c, p, "deadline_confirmed", str(did), {"due": row["due"]})
    return {"ok": True, "id": did, "status": "confirmed"}


class Release(BaseModel):
    text: str | None = Field(default=None, max_length=20000)


@app.post("/api/drafts/{did}/release")
def release(did: int, body: Release, p: Principal = Depends(me)) -> dict:
    firm = _firm(p)
    need(p, "release_draft")
    with session(firm) as c:
        d = c.execute(
            "select d.*, n.parsed, n.findings, n.explanation, n.tax_effect from drafts d join notices n on "
            "n.id = d.notice_id where d.id = %s and d.status='draft'",
            (did,),
        ).fetchone()
        if not d:
            raise HTTPException(404, "no open draft with this id in your firm")
        text = body.text or d["text"]
        dl = c.execute(
            "select due from deadlines where notice_id=%s order by id desc limit 1", (d["notice_id"],)
        ).fetchone()
        v = verify_draft(
            text,
            {
                "parsed": d["parsed"],
                "explanation": d["explanation"],
                "tax_effect": d["tax_effect"],
                "deadline": {"due": str(dl["due"]) if dl else None},
            },
        )
        if not v["ok"]:
            raise HTTPException(422, {"title": "The draft cites something the desk cannot back", **v})
        c.execute(
            "update drafts set text=%s, verification=%s, status='released', released_by=%s, released_at=now() "
            "where id=%s",
            (text, j(v), p.person, did),
        )
        audit(c, p, "draft_released", str(did), {"notice": d["notice_id"]})
    return {"ok": True, "verification": v}


@app.get("/api/monitor")
def monitor(p: Principal = Depends(me)) -> dict:
    """Per firm numbers for group operations; a firm sees its own."""
    if p.role != "group_ops":
        _firm(p)
    with session(p.firm, "group_ops" if p.role == "group_ops" else "firm") as c:
        acts = c.execute("select * from firm_metrics()").fetchall()
        dls = c.execute("select * from deadline_metrics()").fetchall()
        cors = c.execute("select * from correction_metrics()").fetchall()
        firms = c.execute("select id, name, city from firms order by id").fetchall()
    keep = (lambda r: True) if p.role == "group_ops" else (lambda r: r["firm_id"] == p.firm)
    quality: dict[str, Any] = {}
    ev = config.REPORTS / "evals"
    for s in ("test", "heldout"):
        f = ev / f"{s}.json"
        if f.exists():
            import json

            quality[s] = json.loads(f.read_text())["metrics"]
    return {
        "firms": [dict(f) for f in firms if keep({"firm_id": f["id"]})],
        "actions": [dict(r) for r in acts if keep(r)],
        "deadlines": [dict(r) for r in dls if keep(r)],
        "corrections": [dict(r) for r in cors if keep(r)],
        "quality": quality,
        "as_of": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
    }


WEB = config.ROOT / "web" / "dist"
if WEB.exists():
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        target = WEB / path
        return FileResponse(target if path and target.is_file() else WEB / "index.html")


__all__ = ["app", "Path"]
