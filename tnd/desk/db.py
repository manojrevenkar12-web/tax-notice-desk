"""Database access. The service connects as tnd_app, which RLS confines to one firm per transaction
(app.firm_id) and which can neither delete rows nor change the schema. Migrations run as the owner."""

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .. import config

MIGRATIONS = Path(__file__).parent / "migrations"
TABLES = ["firms", "people", "clients", "filed_returns", "onfile", "history", "documents", "notices", "deadlines",
          "drafts", "corrections", "layout_memory", "audit_log", "outbox"]


def owner_url() -> str:
    return os.environ.get("TND_OWNER_URL", config.load("desk")["database"]["owner_url"])


def app_url() -> str:
    return os.environ.get("TND_APP_URL", config.load("desk")["database"]["app_url"])


def _q(pw: str) -> str:
    return "'" + pw.replace("'", "''") + "'"


def migrate_up(url: str | None = None) -> list[str]:
    url = url or owner_url()
    done = []
    with psycopg.connect(url, autocommit=True) as c:
        c.execute("create table if not exists schema_migrations (name text primary key, at timestamptz default now())")
        have = {r[0] for r in c.execute("select name from schema_migrations")}
        for f in sorted(MIGRATIONS.glob("*.up.sql")):
            name = f.name.removesuffix(".up.sql")
            if name in have:
                continue
            with c.transaction():
                c.execute(f.read_text())
                c.execute("insert into schema_migrations (name) values (%s)", (name,))
            done.append(name)
        roles(c)
    return done


def migrate_down(url: str | None = None) -> list[str]:
    url = url or owner_url()
    done = []
    with psycopg.connect(url, autocommit=True) as c:
        c.execute("create table if not exists schema_migrations (name text primary key, at timestamptz default now())")
        have = {r[0] for r in c.execute("select name from schema_migrations")}
        for f in sorted(MIGRATIONS.glob("*.down.sql"), reverse=True):
            name = f.name.removesuffix(".down.sql")
            if name not in have:
                continue
            with c.transaction():
                c.execute(f.read_text())
                c.execute("delete from schema_migrations where name = %s", (name,))
            done.append(name)
    return done


def roles(c: psycopg.Connection[Any]) -> None:
    pw = os.environ.get("TND_APP_PASSWORD", "tnd_app")
    for role, opts in (("tnd_app", f"login password {_q(pw)} nobypassrls"), ("tnd_reporting", "nologin bypassrls")):
        if not c.execute("select 1 from pg_roles where rolname = %s", (role,)).fetchone():
            c.execute(f"create role {role} {opts}")
        else:
            c.execute(f"alter role {role} {opts}")
    c.execute(f"grant usage on schema public to tnd_app, tnd_reporting")
    c.execute(f"grant select, insert, update on {', '.join(TABLES)} to tnd_app")
    c.execute("revoke delete, truncate on all tables in schema public from tnd_app")
    c.execute("grant usage, select on all sequences in schema public to tnd_app")
    c.execute("grant select on clients, notices, deadlines, corrections to tnd_reporting")
    c.execute("grant select, update on documents to tnd_reporting")
    for fn in ("firm_metrics()", "deadline_metrics()", "correction_metrics()", "route_taxno(text)",
               "route_document(text, text)"):
        c.execute(f"alter function {fn} owner to tnd_reporting")
        c.execute(f"grant execute on function {fn} to tnd_app")


@contextlib.contextmanager
def session(firm: str | None, scope: str = "firm", url: str | None = None) -> Iterator[psycopg.Connection[Any]]:
    """A transaction bound to one firm (or to the mailroom or group operations scope)."""
    with psycopg.connect(url or app_url(), row_factory=dict_row) as c:  # type: ignore[arg-type]
        with c.transaction():
            c.execute("select set_config('app.firm_id', %s, true), set_config('app.scope', %s, true)",
                      (firm or "", scope))
            yield c


def j(v: Any) -> Jsonb:
    return Jsonb(json.loads(json.dumps(v, default=str)))
