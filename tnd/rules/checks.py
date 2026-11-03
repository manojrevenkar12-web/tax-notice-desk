"""What the desk checks on a notice, after reading it: who it is for, how it differs from the return the firm
filed, whether the town's and the office's arithmetic holds, and whether the interest is right."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from dataclasses import field as dfield
from decimal import Decimal
from typing import Any

from .. import config
from .deadlines import add_months

# Fields a notice and the filed return share, by kind; the others are derived or payment figures.
BASES = {
    "est": ["einkuenfte_nsa", "einkuenfte_gewerbe", "einkuenfte_vuv", "sonderausgaben", "agb", "zve", "est", "soli",
            "kist", "lst_est", "vz_est"],
    "kst": ["einkommen", "kst", "soli", "vz_kst"],
    "ust": ["umsatz_19", "umsatz_7", "vorsteuer", "ust", "zahllast", "vz_ust"],
    "gewst_mess": ["gewinn", "hinzurechnungen", "kuerzungen", "gewerbeertrag", "freibetrag", "messbetrag"],
}
# Which way a field moving up hurts the client.
UP_IS_AGAINST = {"einkuenfte_nsa", "einkuenfte_gewerbe", "einkuenfte_vuv", "zve", "est", "soli", "kist", "einkommen",
                 "kst", "umsatz_19", "umsatz_7", "ust", "zahllast", "gewinn", "hinzurechnungen", "gewerbeertrag",
                 "messbetrag"}
DOWN_IS_AGAINST = {"sonderausgaben", "agb", "vorsteuer", "kuerzungen", "freibetrag", "lst_est", "vz_est", "vz_kst",
                   "vz_ust"}
PRIMARY = {  # the figures an office changes; the rest follow from them
    "est": {"einkuenfte_nsa", "einkuenfte_gewerbe", "einkuenfte_vuv", "sonderausgaben", "agb"},
    "kst": {"einkommen"},
    "ust": {"umsatz_19", "umsatz_7", "vorsteuer"},
    "gewst_mess": {"gewinn", "hinzurechnungen", "kuerzungen"},
}
REST = {"est": ("rest_est", "rest_soli", "rest_kist"), "kst": ("rest_kst", "soli"), "ust": ("rest_ust",)}


@dataclass
class Finding:
    type: str  # deviation | wrong_hebesatz | stale_messbetrag | arithmetic | interest | estimate | no_return | ...
    field: str | None = None
    filed: int | None = None
    stated: int | None = None
    expected: int | None = None
    against: bool | None = None
    primary: bool = True
    detail: str = ""
    sources: list[str] = dfield(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def compare(kind: str, notice: dict[str, int], filed: dict[str, int]) -> list[Finding]:
    tol = config.load("rules")["tolerance_cents"]
    out = []
    for k in BASES.get(kind, []):
        if k not in notice or k not in filed:
            continue
        a, b = notice[k], filed[k]
        if abs(a - b) <= tol:
            continue
        against = (a > b) if k in UP_IS_AGAINST else (a < b) if k in DOWN_IS_AGAINST else None
        out.append(Finding("deviation", k, b, a, None, against, k in PRIMARY.get(kind, set()),
                           f"{k}: filed {b / 100:.2f}, assessed {a / 100:.2f}"))
    return out


def tax_effect(kind: str, notice: dict[str, int], filed: dict[str, int]) -> int:
    keys = REST.get(kind, ())
    if not keys or not all(k in notice and k in filed for k in keys):
        return 0
    return sum(notice[k] for k in keys) - sum(filed[k] for k in keys)


def interest(kind: str, tax_year: int, base: int, wirksam: dt.date) -> tuple[int, dict]:
    """AO §§ 233a, 238, 239: from 15 months after the tax year, 0.15 % per full month on the difference rounded
    down to 50 €, rounded down to full euros, nothing below 10 €."""
    c = config.load("rules")["interest"]
    start = add_months(dt.date(tax_year, 12, 31) + dt.timedelta(days=1), c["starts_after_months"])
    if wirksam < start or base == 0:
        return 0, {"start": start.isoformat(), "months": 0}
    months = 0
    while add_months(start, months + 1) - dt.timedelta(days=1) <= wirksam:
        months += 1
    rate = Decimal(c["rate_per_month"][-1]["rate"])
    rounded = abs(base) // c["base_round_down_to_cents"] * c["base_round_down_to_cents"]
    euros = int(Decimal(rounded) / 100 * rate * months)  # rounded down to full euros
    cents = euros * 100
    if cents < c["minimum_cents"]:
        cents = 0
    return (cents if base > 0 else -cents), {"start": start.isoformat(), "months": months, "base": rounded,
                                             "rate": str(rate), "sources": ["AO § 233a", "AO § 238", "AO § 239"]}


def check_interest(kind: str, tax_year: int, fields: dict[str, int], wirksam: dt.date) -> Finding | None:
    key = {"est": ("zinsen_est", "rest_est"), "kst": ("zinsen_kst", "rest_kst"), "ust": ("zinsen_ust", "rest_ust")}
    if kind not in key or kind not in config.load("rules")["interest"]["taxes"]:
        return None
    zkey, rkey = key[kind]
    if rkey not in fields:
        return None
    expected, calc = interest(kind, tax_year, fields[rkey], wirksam)
    stated = fields.get(zkey, 0)
    if abs(stated - expected) <= 100:
        return None
    return Finding("interest", zkey, None, stated, expected, abs(stated) > abs(expected), True,
                   f"interest from {calc['start']} for {calc.get('months')} full months on "
                   f"{calc.get('base', 0) / 100:.2f}: {expected / 100:.2f}, notice says {stated / 100:.2f}",
                   ["AO § 233a", "AO § 238", "AO § 239"])


def check_gewst(fields: dict[str, int], municipality: str | None, tax_year: int,
                messbetrag_on_file: int | None) -> list[Finding]:
    out: list[Finding] = []
    reg = config.load("municipal")["hebesatz"]
    stated_h = fields.get("hebesatz")
    if municipality and municipality in reg and stated_h is not None:
        expected_h = reg[municipality].get(tax_year)
        if expected_h is not None and stated_h != expected_h * 100:
            out.append(Finding("wrong_hebesatz", "hebesatz", None, stated_h, expected_h * 100, stated_h > expected_h * 100,
                               True, f"{municipality} levies {expected_h} % for {tax_year}; the notice applies "
                               f"{stated_h // 100} %", ["GewStG § 16"]))
    if messbetrag_on_file is not None and fields.get("messbetrag") is not None and fields["messbetrag"] != messbetrag_on_file:
        out.append(Finding("stale_messbetrag", "messbetrag", None, fields["messbetrag"], messbetrag_on_file,
                           fields["messbetrag"] > messbetrag_on_file, True,
                           f"the latest Messbescheid on file sets {messbetrag_on_file / 100:.2f}; the town used "
                           f"{fields['messbetrag'] / 100:.2f}", ["AO § 175 Abs. 1 Satz 1 Nr. 1", "AO § 182"]))
    if all(k in fields for k in ("messbetrag", "hebesatz", "gewst")):
        expected = fields["messbetrag"] * fields["hebesatz"] // 10000
        if abs(expected - fields["gewst"]) > 100:
            out.append(Finding("arithmetic", "gewst", None, fields["gewst"], expected, fields["gewst"] > expected, True,
                               f"{fields['messbetrag'] / 100:.2f} × {fields['hebesatz'] // 100} % = {expected / 100:.2f}, "
                               f"the notice says {fields['gewst'] / 100:.2f}", ["GewStG § 16 Abs. 1"]))
    return out
