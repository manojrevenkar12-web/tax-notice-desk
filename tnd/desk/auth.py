"""Tokens for people, and for AI tools acting for a person (RFC 8693 'act' claim): the person is the subject,
the tool the actor, and the desk records both. A token never grants more than the person's role."""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass

import jwt

from .. import config


@dataclass(frozen=True)
class Principal:
    person: str
    firm: str | None
    role: str
    actor: str | None = None

    def can(self, action: str) -> bool:
        return action in config.load("desk")["permissions"].get(self.role, [])


def _secret() -> str:
    s = os.environ.get("TND_JWT_SECRET")
    if s:
        return s
    if os.environ.get("TND_ENV") == "production":
        raise RuntimeError("TND_JWT_SECRET must be set in production")
    return str(config.load("desk")["auth"]["dev_secret"])


def mint(p: Principal) -> str:
    cfg = config.load("desk")["auth"]
    now = dt.datetime.now(dt.UTC)
    claims = {
        "sub": p.person,
        "firm": p.firm,
        "role": p.role,
        "iss": cfg["issuer"],
        "iat": now,
        "exp": now + dt.timedelta(minutes=cfg["token_minutes"]),
    }
    if p.actor:
        claims["act"] = {"sub": p.actor}
    return jwt.encode(claims, _secret(), algorithm="HS256")


def verify(token: str) -> Principal:
    c = jwt.decode(token, _secret(), algorithms=["HS256"], issuer=config.load("desk")["auth"]["issuer"])
    return Principal(c["sub"], c.get("firm"), c["role"], (c.get("act") or {}).get("sub"))
