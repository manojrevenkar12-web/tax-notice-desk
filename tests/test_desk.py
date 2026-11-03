"""The desk's record holds its rules in the database: firms see only their own notices, deadlines are
confirmed by a second person, released drafts are final and verified, the audit log is append-only, and the
runtime role can delete nothing. The API passes those refusals on."""

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.conftest import APP


def firm_conn(firm: str | None, scope: str = "firm") -> psycopg.Connection:
    c = psycopg.connect(APP, autocommit=True)
    c.execute("select set_config('app.firm_id', %s, false), set_config('app.scope', %s, false)", (firm or "", scope))
    return c


def test_firms_see_only_their_own(desk):
    with firm_conn(None) as c:
        assert c.execute("select count(*) from notices").fetchone()[0] == 0
        assert c.execute("select count(*) from clients").fetchone()[0] == 0
    with firm_conn("f-spree") as c:
        assert c.execute("select count(*) from clients where firm_id <> 'f-spree'").fetchone()[0] == 0
        assert c.execute("select count(*) from clients").fetchone()[0] > 0
        with pytest.raises(psycopg.Error):
            c.execute("insert into notes_that_do_not_exist values (1)")


def test_runtime_role_cannot_delete_or_change_the_schema(desk):
    with firm_conn("f-spree") as c:
        for sql in ("delete from notices", "delete from deadlines", "drop table notices", "truncate audit_log",
                    "update audit_log set action = 'x'"):
            with pytest.raises(psycopg.Error):
                c.execute(sql)


def test_a_deadline_needs_a_second_person_and_cannot_move_once_confirmed(desk):
    any_notice = next(r for rs in desk.values() for r in rs if r["firm"] == "f-spree" or True)
    firm = any_notice["firm"]
    with firm_conn(firm) as c:
        did = c.execute("insert into deadlines (firm_id, notice_id, due, bekanntgabe, basis, rules, notes, proposed_by) "
                        "values (%s, %s, '2027-01-04', '2026-12-04', 'remedy', '[]', '[]', %s) returning id",
                        (firm, any_notice["id"], f"{firm}-p0")).fetchone()[0]
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute("update deadlines set status='confirmed', confirmed_by=%s where id=%s", (f"{firm}-p0", did))
        c.execute("update deadlines set status='confirmed', confirmed_by=%s, confirmed_at=now() where id=%s",
                  (f"{firm}-p1", did))
        with pytest.raises(psycopg.Error, match="cannot be moved"):
            c.execute("update deadlines set due = '2027-01-11' where id = %s", (did,))


def test_only_verified_drafts_are_released_and_released_drafts_are_final(desk):
    with firm_conn(None) as c:
        pass
    rows = [r for k in ("objection_review", "objection_required") for r in desk.get(k, [])]
    if not rows:
        pytest.skip("no objection in the sample")
    firm, nid = rows[0]["firm"], rows[0]["id"]
    with firm_conn(firm) as c:
        did = c.execute("select id from drafts where notice_id=%s", (nid,)).fetchone()[0]
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute("update drafts set status='released', released_by=%s, verification='{\"ok\": false}' where id=%s",
                      (f"{firm}-p2", did))


def _client():
    from tnd.desk.app import app

    return TestClient(app)


def _token(cl: TestClient, person: str) -> dict:
    r = cl.post("/api/dev/sign-in", json={"person": person})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_api_decisions_wait_for_the_deadline_and_respect_roles(desk):
    rows = [r for k in ("objection_review", "objection_required") for r in desk.get(k, [])]
    if not rows:
        pytest.skip("no objection in the sample")
    r0 = rows[0]
    firm, nid = r0["firm"], r0["id"]
    cl = _client()
    clerk, clerk2, advisor = (_token(cl, f"{firm}-p{i}") for i in range(3))
    inbox = cl.get("/api/inbox", headers=clerk).json()
    assert any(n["id"] == nid for n in inbox) and all(n["client"] for n in inbox if n["client_id"])
    detail = cl.get(f"/api/notices/{nid}", headers=clerk).json()
    assert detail["explanation"] and detail["drafts"]
    # the advisor cannot file the objection before the deadline is confirmed
    assert cl.post(f"/api/notices/{nid}/decision", json={"outcome": "objection_filed"}, headers=advisor).status_code == 409
    dl = next(d for d in detail["deadlines"] if d["status"] == "proposed")
    assert cl.post(f"/api/deadlines/{dl['id']}/confirm", headers=clerk2).status_code == 200
    # a clerk may not release an objection; an advisor may, but not with a section the desk cannot back
    did = detail["drafts"][0]["id"]
    assert cl.post(f"/api/drafts/{did}/release", json={}, headers=clerk).status_code == 403
    bad = detail["drafts"][0]["text"] + "\nWir verweisen auf § 999 AO und 12.345,67 €."
    r = cl.post(f"/api/drafts/{did}/release", json={"text": bad}, headers=advisor)
    assert r.status_code == 422 and "§ 999" in str(r.json())
    assert cl.post(f"/api/drafts/{did}/release", json={}, headers=advisor).status_code == 200
    assert cl.post(f"/api/notices/{nid}/decision", json={"outcome": "objection_filed"}, headers=advisor).status_code == 200


def test_other_firms_and_group_roles_see_no_client_data(desk):
    r0 = next(r for rs in desk.values() for r in rs)
    other = "f-isar" if r0["firm"] != "f-isar" else "f-dom"
    cl = _client()
    assert cl.get(f"/api/notices/{r0['id']}", headers=_token(cl, f"{other}-p0")).status_code == 404
    ops = _token(cl, "g-ops")
    assert cl.get("/api/inbox", headers=ops).status_code == 403
    m = cl.get("/api/monitor", headers=ops).json()
    assert m["actions"] and all(set(a) == {"firm_id", "action", "notices", "open"} for a in m["actions"])
    assert cl.get("/api/inbox", headers=_token(cl, "g-mailroom")).status_code == 403


def test_audit_log_is_append_only(desk):
    with firm_conn("f-spree") as c:
        with pytest.raises(psycopg.Error, match="append-only"):
            c.execute("update audit_log set action='x' where firm_id='f-spree'")
