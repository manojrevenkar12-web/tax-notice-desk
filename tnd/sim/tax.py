"""Tax arithmetic used only to make simulated notices internally consistent. The income tax tariff follows
§ 32a EStG for 2023-2025 as published; it is not validated against the BMF calculator and the desk never
uses it (the desk compares a notice with the return the firm filed, it does not recompute income tax)."""

from __future__ import annotations

import math

TARIFF = {  # year: (Grundfreibetrag, end zone 2, end zone 3, a2, a3, c3, c4, c5)
    2023: (10908, 15999, 62809, 979.18, 192.59, 966.53, 9972.98, 18307.73),
    2024: (11784, 17005, 66760, 954.80, 181.19, 991.21, 10636.31, 18971.06),
    2025: (12096, 17443, 68480, 932.30, 176.64, 1015.13, 10911.92, 19246.67),
}
SOLI_FREE = {2023: 17543, 2024: 18130, 2025: 19950}


def income_tax(zve_cents: int, year: int) -> int:
    x = math.floor(zve_cents / 100)
    gfb, e2, e3, a2, a3, c3, c4, c5 = TARIFF[year]
    if x <= gfb:
        t = 0.0
    elif x <= e2:
        y = (x - gfb) / 10000
        t = (a2 * y + 1400) * y
    elif x <= e3:
        z = (x - e2) / 10000
        t = (a3 * z + 2397) * z + c3
    elif x <= 277825:
        t = 0.42 * x - c4
    else:
        t = 0.45 * x - c5
    return math.floor(t) * 100


def soli(est_cents: int, year: int) -> int:
    free = SOLI_FREE[year] * 100
    if est_cents <= free:
        return 0
    return min(round(est_cents * 0.055), round((est_cents - free) * 0.119))


def church(est_cents: int, land: str) -> int:
    return round(est_cents * (0.08 if land in ("BY", "BW") else 0.09))


def messbetrag(gewinn: int, hinz: int, kuerz: int, person: bool) -> tuple[int, int, int]:
    """Gewerbeertrag rounded down to 100 €, Freibetrag for persons, Messzahl 3.5 % (§ 11 GewStG)."""
    ertrag = max(0, gewinn + hinz - kuerz)
    ertrag = ertrag // 10000 * 10000
    frei = min(ertrag, 2450000) if person else 0
    return ertrag, frei, (ertrag - frei) * 35 // 1000
