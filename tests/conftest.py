import json
import os

import psycopg
import pytest

from tnd import config

OWNER = os.environ.get("TND_TEST_OWNER_URL", "postgresql://postgres@127.0.0.1:5544/tnd_test")
APP = os.environ.get("TND_TEST_APP_URL", "postgresql://tnd_app:tnd_app@127.0.0.1:5544/tnd_test")


def _db() -> bool:
    try:
        with psycopg.connect(OWNER, connect_timeout=3):
            return True
    except psycopg.OperationalError:
        return False


@pytest.fixture(scope="session")
def world():
    if not (config.DATA / "group" / "clients.json").exists():
        from tnd.sim.build import build

        build(("dev",))


@pytest.fixture(scope="session")
def desk(world):
    """A desk database with the group and a handful of electronic notices from dev, processed by the pipeline."""
    if not _db():
        pytest.skip("PostgreSQL not available (set TND_TEST_OWNER_URL)")
    os.environ["TND_OWNER_URL"] = OWNER
    os.environ["TND_APP_URL"] = APP
    from tnd.desk.seed import seed
    from tnd.desk.store import store_document, store_result
    from tnd.pipeline import Group, process

    seed(None, OWNER)
    g = Group.load()
    folder = config.DATA / "dev" / "inbox"
    metas = sorted(
        (json.loads(p.read_text()) for p in folder.glob("*.json")), key=lambda m: (m["received_at"], m["id"])
    )
    picked: dict[str, list[dict]] = {}
    for m in metas:
        if m["channel"] != "portal":
            continue
        out = process(g, m["id"], folder, m, use_model=False)
        if out["firm"] and len(picked.setdefault(out["action"], [])) < 3:
            store_document(m["id"], m, folder / f"{m['id']}.pdf")
            store_result(out, use_model=False)
            picked[out["action"]].append(out)
    return picked
