"""Deadline arithmetic for the simulator's answer key, written separately from tnd/rules so that the two
can disagree. Day by day, no shortcuts: slower and easier to check by hand."""

from __future__ import annotations

import calendar
import datetime as dt
import functools

import holidays


@functools.cache
def _hol(land: str, year: int) -> frozenset[dt.date]:
    return frozenset(holidays.Germany(subdiv=land, years=year).keys())


def is_free(day: dt.date, lands: tuple[str, ...]) -> bool:
    """Saturday, Sunday, or a holiday in every one of the given Länder."""
    if day.weekday() >= 5:
        return True
    return all(day in _hol(land, day.year) for land in lands)


def next_working(day: dt.date, lands: tuple[str, ...]) -> dt.date:
    while is_free(day, lands):
        day += dt.timedelta(days=1)
    return day


def plus_months(day: dt.date, months: int) -> dt.date:
    """BGB §§ 187, 188: the period ends on the day of the later month with the same number; if that month is
    shorter, on its last day."""
    y, m = day.year, day.month + months
    while m > 12:
        y, m = y + 1, m - 12
    last = calendar.monthrange(y, m)[1]
    return dt.date(y, m, min(day.day, last))


def received(channel: str, posted: dt.date, provided: dt.date | None, notified: dt.date | None,
             lands: tuple[str, ...]) -> dt.date:
    """When the notice counts as received, following the versions in docs/NOTICE_RULES.md."""
    if channel in ("post", "client_upload", "municipal_post"):
        days = 3 if posted < dt.date(2025, 1, 1) else 4
        day = posted
        for _ in range(days):
            day += dt.timedelta(days=1)
        return next_working(day, lands)
    if channel in ("portal", "municipal_digital"):
        # the version follows the day the notice was made available (EGAO transitional rule)
        made = provided or notified
        assert made is not None
        if made >= dt.date(2026, 1, 1):
            start, days = made, 4
        else:
            start, days = (notified or made), (3 if made < dt.date(2025, 1, 1) else 4)
        return start + dt.timedelta(days=days)  # no weekend shift for § 122a: the earlier date is kept
    raise ValueError(channel)


def deadline(bekanntgabe: dt.date, months: int, lands: tuple[str, ...]) -> dt.date:
    return next_working(plus_months(bekanntgabe, months), lands)


def full_months(start: dt.date, end: dt.date) -> int:
    """Full months from start (inclusive) to end (inclusive)."""
    n = 0
    while plus_months(start, n + 1) - dt.timedelta(days=1) <= end:
        n += 1
    return n
