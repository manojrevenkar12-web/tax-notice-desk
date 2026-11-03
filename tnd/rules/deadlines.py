"""When a notice counts as received and when the objection period ends.

The rules and their sources are in config/rules.yaml. Every result says which rule produced it, and where
the law is not settled the earlier date is kept: a register that is a day early costs nothing, a day late
can cost the client the objection.
"""

from __future__ import annotations

import calendar
import datetime as dt
import functools
from dataclasses import dataclass, field

import holidays

from .. import config


@functools.cache
def _holidays(land: str, year: int) -> frozenset[dt.date]:
    return frozenset(holidays.Germany(subdiv=land, years=year).keys())


def free_day(day: dt.date, lands: tuple[str, ...]) -> bool:
    """Saturday, Sunday, or a statutory holiday; with several Länder only a holiday in all of them counts."""
    if day.weekday() >= 5:
        return True
    if config.load("rules")["remedy"]["holidays_where"] == "both":
        return all(day in _holidays(land, day.year) for land in lands)
    return any(day in _holidays(land, day.year) for land in lands)


def roll_forward(day: dt.date, lands: tuple[str, ...]) -> dt.date:
    """AO § 108 Abs. 3."""
    while free_day(day, lands):
        day += dt.timedelta(days=1)
    return day


def add_months(day: dt.date, months: int) -> dt.date:
    """BGB § 188 Abs. 2 and 3: same day number in the later month, or its last day."""
    m = day.month - 1 + months
    y, m = day.year + m // 12, m % 12 + 1
    return dt.date(y, m, min(day.day, calendar.monthrange(y, m)[1]))


@dataclass
class Deadline:
    bekanntgabe: dt.date
    due: dt.date
    basis: str  # remedy | authority
    rules: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    later_possible: dt.date | None = None  # a later date the client could argue, never used for the register

    def as_dict(self) -> dict:
        return {
            "bekanntgabe": self.bekanntgabe.isoformat(),
            "due": self.due.isoformat(),
            "basis": self.basis,
            "rules": self.rules,
            "notes": self.notes,
            "later_possible": self.later_possible.isoformat() if self.later_possible else None,
        }


def _version(versions: list[dict], day: dt.date) -> dict:
    current = versions[0]
    for v in versions:
        if dt.date.fromisoformat(v["from"]) <= day:
            current = v
    return current


def bekanntgabe(
    channel: str,
    posted: dt.date,
    lands: tuple[str, ...],
    provided: dt.date | None = None,
    notified: dt.date | None = None,
    postmark: dt.date | None = None,
) -> tuple[dt.date, list[str], list[str], dt.date | None]:
    cfg = config.load("rules")["bekanntgabe"]
    rules: list[str] = []
    notes: list[str] = []
    later = None
    if channel in ("portal", "municipal_digital"):
        start_day = provided or notified or posted
        v = _version(cfg["portal"], start_day)
        start = (notified or start_day) if v["counts_from"] == "notification" else (provided or start_day)
        if v["counts_from"] == "notification" and notified is None:
            start = start_day
            notes.append("no notification date: counted from the date the notice was made available")
        day = start + dt.timedelta(days=v["days"])
        rules.append(v["source"])
        if not cfg["weekend_shift"]["portal"] and free_day(day, lands):
            later = roll_forward(day, lands)
            notes.append(
                "presumed day falls on a weekend or holiday; whether it moves is not settled for § 122a AO, "
                "the register keeps the earlier date"
            )
        return day, rules, notes, later
    v = _version(cfg["post"], posted)
    day = posted + dt.timedelta(days=v["days"])
    rules.append(v["source"])
    if cfg["weekend_shift"]["post"] and free_day(day, lands):
        day = roll_forward(day, lands)
        rules.append("AO § 108 Abs. 3; BFH III B 85/13")
    if postmark and postmark > posted:
        later_day = postmark + dt.timedelta(days=v["days"])
        later = roll_forward(later_day, lands)
        notes.append(
            f"envelope postmarked {postmark:%d.%m.%Y}: the presumption may be rebutted (BFH IX B 95/25); "
            "the register keeps the date from the notice"
        )
    return day, rules, notes, later


def objection_deadline(
    channel: str,
    posted: dt.date,
    lands: tuple[str, ...],
    instructions: bool,
    remedy: str | None,
    provided: dt.date | None = None,
    notified: dt.date | None = None,
    postmark: dt.date | None = None,
) -> Deadline:
    rcfg = config.load("rules")["remedy"]
    bk, rules, notes, later = bekanntgabe(channel, posted, lands, provided, notified, postmark)
    if not instructions:
        months = rcfg["without_instructions_months"]
        rules.append("AO § 356 Abs. 2")
        notes.append("no instructions on how to object: the period is one year; act within a month anyway")
    elif remedy == "Widerspruch":
        months = rcfg["municipal_widerspruch_months"]
        rules.append("VwGO § 70 Abs. 1")
    else:
        months = rcfg["default_months"]
        rules.append("AO § 355 Abs. 1")
    due = roll_forward(add_months(bk, months), lands)
    rules.append("AO § 108 Abs. 1, 3; BGB §§ 187, 188")
    later_due = roll_forward(add_months(later, months), lands) if later else None
    return Deadline(bk, due, "remedy", rules, notes, later_due if later_due and later_due > due else None)


def authority_deadline(due: dt.date, posted: dt.date) -> Deadline:
    """A date the office set in a letter: kept as written (an extension under § 108 Abs. 3 is not relied on)."""
    return Deadline(posted, due, "authority", ["date set by the authority"], [])


def from_receipt(received: dt.date, lands: tuple[str, ...], remedy: str | None) -> Deadline:
    """The notice date could not be read: count the month from the day the notice arrived, the earliest day the
    period can plausibly start. A person reads the date and corrects the register."""
    due = roll_forward(add_months(received, 1), lands)
    return Deadline(
        received,
        due,
        "remedy",
        [
            "notice date not read: counted from the day it arrived",
            "VwGO § 70 Abs. 1" if remedy == "Widerspruch" else "AO § 355 Abs. 1",
        ],
        ["read the notice date and correct the deadline"],
    )
