"""Amounts are integer cents. German notices write them in many ways; this reads them all."""

from __future__ import annotations

import re

_AMOUNT = re.compile(r"-?\s?(?:\d{1,3}(?:[.\s ]\d{3})+|\d+)(?:,\d{1,2})?(?:\s?-)?")


def parse_amount(text: str) -> int | None:
    """'1.234,56 €', 'EUR 1 234,56', '1234,5', '-12,00', '12,00-' -> cents. None if no amount."""
    t = text.replace("−", "-").replace("€", " ").replace("EUR", " ").replace("Euro", " ").strip()
    m = _AMOUNT.search(t)
    if not m:
        return None
    raw = m.group(0).strip()
    neg = raw.startswith("-") or raw.endswith("-")
    raw = raw.strip("-").strip()
    if "," in raw:
        whole, frac = raw.rsplit(",", 1)
        frac = (frac + "0")[:2]
    else:
        whole, frac = raw, "00"
    whole = re.sub(r"[.\s ]", "", whole)
    if not whole.isdigit():
        return None
    cents = int(whole) * 100 + int(frac)
    return -cents if neg else cents


def fmt(cents: int, style: str = "de") -> str:
    """Format cents the way a notice would: 'de' 1.234,56 €; 'de_plain' 1234,56; 'eur' EUR 1 234,56."""
    neg = cents < 0
    c = abs(cents)
    whole, frac = divmod(c, 100)
    if style == "de_plain":
        s = f"{whole},{frac:02d}"
    elif style == "eur":
        s = "EUR " + f"{whole:,}".replace(",", " ") + f",{frac:02d}"
    elif style == "trailing_minus":
        s = f"{whole:,}".replace(",", ".") + f",{frac:02d}" + ("-" if neg else "")
        return s
    else:
        s = f"{whole:,}".replace(",", ".") + f",{frac:02d} €"
    return ("-" if neg else "") + s


def euros(cents: int) -> str:
    return fmt(cents)
