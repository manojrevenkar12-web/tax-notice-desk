"""Record API responses from a seeded desk for the console's end-to-end tests (web/e2e/fixtures)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

os.environ.setdefault("TND_TODAY", "2026-12-07")
from tnd.desk.app import app  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "web" / "e2e" / "fixtures"


def main(person: str = "f-spree-p0") -> None:
    c = TestClient(app)
    OUT.mkdir(parents=True, exist_ok=True)
    people = c.get("/api/dev/people").json()
    session = c.post("/api/dev/sign-in", json={"person": person}).json()
    h = {"Authorization": f"Bearer {session['token']}"}
    inbox = c.get("/api/inbox", headers=h).json()
    pick = next(n for n in inbox if n["action"] == "objection_review" and n["deadline_status"] == "proposed")
    notice = c.get(f"/api/notices/{pick['id']}", headers=h).json()
    ops = c.post("/api/dev/sign-in", json={"person": "g-ops"}).json()
    monitor = c.get("/api/monitor", headers={"Authorization": f"Bearer {ops['token']}"}).json()
    for name, body in (("people", people), ("session", session), ("me", c.get("/api/me", headers=h).json()),
                       ("inbox", inbox), ("notice", notice), ("deadlines", c.get("/api/deadlines", headers=h).json()),
                       ("monitor", monitor)):
        (OUT / f"{name}.json").write_text(json.dumps(body, indent=1, ensure_ascii=False, default=str))
    print(f"recorded {len(inbox)} notices; detail {pick['id']}")


if __name__ == "__main__":
    main(*sys.argv[1:])
