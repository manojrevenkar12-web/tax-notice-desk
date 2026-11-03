"""The simulated group: firms, their clients, the returns they filed, what is on file, client histories, and
the notices that arrive in each split, each with its answer key.

The answer key (truth) says what a careful advisor would conclude about each notice. Only tnd/evals reads it.
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass, field
from typing import Any

from .. import config
from . import calendar as cal
from . import tax

FIRST = ["Anna", "Jonas", "Leonie", "Felix", "Marie", "Paul", "Sophie", "Lukas", "Emma", "Elias", "Hannah", "Ben",
         "Mia", "Noah", "Lea", "Finn", "Lina", "Tim", "Clara", "Moritz", "Ida", "Jakob", "Greta", "David", "Aylin",
         "Mehmet", "Olga", "Piotr", "Sara", "Tobias"]
LAST = ["Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker", "Hoffmann", "Schulz",
        "Koch", "Richter", "Klein", "Wolf", "Neumann", "Schwarz", "Zimmermann", "Krüger", "Hartmann", "Lange",
        "Werner", "Krause", "Lehmann", "Köhler", "Yilmaz", "Nowak", "Kaya", "Brandt", "Vogel", "Seidel"]
TRADES = ["Elektrotechnik", "Gebäudereinigung", "Softwareentwicklung", "Gastronomie", "Holzbau", "Logistik",
          "Messebau", "Physiotherapie-Bedarf", "Werbetechnik", "Kfz-Service", "Feinkost", "Medientechnik"]
STREETS = ["Hauptstraße", "Lindenallee", "Bahnhofstraße", "Am Markt", "Gartenweg", "Schillerstraße", "Ringstraße",
           "Kirchgasse", "Mühlenweg", "Parkstraße"]
TAXNO = {"BE": (2, 3, 5), "BY": (3, 3, 5), "NW": (3, 4, 4), "SN": (3, 3, 5), "BB": (3, 3, 5)}
FA_PREFIX = {"BE": "27", "BY": "143", "NW": "214", "SN": "231", "BB": "048"}
CITY_OF_LAND = {"BE": "Berlin", "BY": "München", "NW": "Köln", "SN": "Leipzig", "BB": "Potsdam"}


def eur(x: float) -> int:
    """Whole euros in cents."""
    return int(round(x)) * 100


@dataclass
class Client:
    id: str
    firm: str
    kind: str  # person | trader | company
    name: str
    steuernummer: str
    address: str
    land: str
    church: bool
    municipality: str | None = None  # for GewSt
    filed: dict[str, dict[int, dict[str, int]]] = field(default_factory=dict)  # kind -> year -> fields


class World:
    def __init__(self, seed: int | None = None) -> None:
        self.cfg = config.load("world")
        self.rng = random.Random(seed if seed is not None else self.cfg["seed"])
        self.firms = self.cfg["firms"]
        self.munis = {m["id"]: m for m in self.cfg["municipalities"]}
        self.clients: list[Client] = []
        self.taxnos: set[str] = set()
        self.onfile: list[dict[str, Any]] = []  # Messbescheide the firms already processed
        self.history: list[dict[str, Any]] = []  # earlier years' notices and what came of them
        self.seq = 0
        self.used: set[tuple[str, str, int]] = set()
        self.unfiled: set[tuple[str, str, int]] = set()
        for f in self.firms:
            for i in range(f["clients"]):
                self.clients.append(self._client(f, i))

    # ----------------------------------------------------------------- clients and their returns
    def _taxno(self, land: str) -> str:
        while True:
            a, b, c = TAXNO[land]
            prefix = FA_PREFIX[land]
            parts = [prefix[:a].ljust(a, str(self.rng.randint(0, 9)))]
            parts.append("".join(str(self.rng.randint(0, 9)) for _ in range(b)))
            parts.append("".join(str(self.rng.randint(0, 9)) for _ in range(c)))
            s = "/".join(parts)
            if s not in self.taxnos:
                self.taxnos.add(s)
                return s

    def _client(self, firm: dict, i: int) -> Client:
        rng, wc = self.rng, self.cfg["clients"]
        land = firm["land"]
        r = rng.random()
        kind = "company" if r < wc["company_share"] else ("trader" if rng.random() < wc["trader_share"] else "person")
        last = rng.choice(LAST)
        if kind == "company":
            name = f"{last} {rng.choice(TRADES)} GmbH"
        else:
            name = f"{rng.choice(FIRST)} {last}"
        muni = None
        if kind != "person":
            local = [m for m in self.munis.values() if m["land"] == land]
            if land == "BE":
                local = [self.munis["berlin"]]
            other = [m for m in self.munis.values() if m not in local]
            muni = (rng.choice(other) if rng.random() < wc["other_municipality_share"] else rng.choice(local))["id"]
        c = Client(
            id=f"{firm['id']}-c{i:02d}",
            firm=firm["id"],
            kind=kind,
            name=name,
            steuernummer=self._taxno(land),
            address=f"{rng.choice(STREETS)} {rng.randint(1, 120)}, {CITY_OF_LAND[land]}",
            land=land,
            church=rng.random() < wc["church_tax_share"],
            municipality=muni,
        )
        for year in (2023, 2024, 2025):
            self._returns(c, year)
        return c

    def _returns(self, c: Client, year: int) -> None:
        """The returns the firm filed for the client (what the firm's software computed)."""
        rng = self.rng
        if c.kind in ("person", "trader"):
            nsa = eur(rng.uniform(28000, 105000)) if (c.kind == "person" or rng.random() < 0.3) else 0
            gew = eur(rng.uniform(18000, 170000)) if c.kind == "trader" else 0
            vuv = eur(rng.uniform(-9000, 24000)) if rng.random() < 0.4 else 0
            sa = eur(rng.uniform(1800, 9000))
            agb = eur(rng.uniform(0, 4000)) if rng.random() < 0.3 else 0
            f = self._est_fields(c, year, nsa, gew, vuv, sa, agb, None)
            c.filed.setdefault("est", {})[year] = f
            if c.kind == "trader":
                self._business(c, year, gew)
        else:
            einkommen = eur(rng.uniform(30000, 900000))
            kst = einkommen * 15 // 100
            soli_k = round(kst * 0.055)
            vz = kst * rng.choice([0, 50, 80, 100]) // 100 // 100 * 100
            c.filed.setdefault("kst", {})[year] = {
                "einkommen": einkommen, "kst": kst, "soli": soli_k, "vz_kst": vz, "rest_kst": kst - vz}
            self._business(c, year, einkommen)
        if c.kind != "person":
            u19 = eur(rng.uniform(60000, 1500000))
            u7 = eur(rng.uniform(0, 200000)) if rng.random() < 0.3 else 0
            ust = u19 * 19 // 100 + u7 * 7 // 100
            vst = int(ust * rng.uniform(0.2, 0.7)) // 100 * 100
            zl = ust - vst
            vz = zl - eur(rng.uniform(-3000, 3000)) if zl > 300000 else zl
            c.filed.setdefault("ust", {})[year] = {
                "umsatz_19": u19, "umsatz_7": u7, "ust": ust, "vorsteuer": vst, "zahllast": zl,
                "vz_ust": vz, "rest_ust": zl - vz}

    def _est_fields(self, c: Client, year: int, nsa: int, gew: int, vuv: int, sa: int, agb: int,
                    credits: tuple[int, int, int, int] | None) -> dict[str, int]:
        summe = nsa + gew + vuv
        zve = max(0, summe - sa - agb) // 100 * 100
        est = tax.income_tax(zve, year)
        so = tax.soli(est, year)
        ki = tax.church(est, c.land) if c.church else 0
        if credits is None:
            rng = self.rng
            share = nsa / summe if summe > 0 else 0
            lst = int(est * share * rng.uniform(0.85, 1.05)) // 100 * 100
            vz = int((est - lst) * rng.uniform(0.4, 1.0)) // 100 * 100 if gew else 0
            lst_s = round(so * share)
            lst_k = round(ki * share)
            credits = (lst, vz, lst_s, lst_k)
        lst, vz, lst_s, lst_k = credits
        return {"einkuenfte_nsa": nsa, "einkuenfte_gewerbe": gew, "einkuenfte_vuv": vuv, "summe_einkuenfte": summe,
                "sonderausgaben": sa, "agb": agb, "zve": zve, "est": est, "soli": so, "kist": ki,
                "lst_est": lst, "vz_est": vz, "rest_est": est - lst - vz,
                "lst_soli": lst_s, "rest_soli": so - lst_s, "lst_kist": lst_k, "rest_kist": ki - lst_k}

    def _business(self, c: Client, year: int, gewinn: int) -> None:
        rng = self.rng
        hinz = eur(rng.uniform(0, 30000)) if rng.random() < 0.4 else 0
        kuerz = eur(rng.uniform(0, 12000)) if rng.random() < 0.2 else 0
        ertrag, frei, mb = tax.messbetrag(gewinn, hinz, kuerz, c.kind != "company")
        c.filed.setdefault("gewst_mess", {})[year] = {
            "gewinn": gewinn, "hinzurechnungen": hinz, "kuerzungen": kuerz, "gewerbeertrag": ertrag,
            "freibetrag": frei, "messbetrag": mb}

    # ----------------------------------------------------------------- notices
    def _id(self) -> str:
        self.seq += 1
        return f"n{self.seq:05d}"

    def _working_days(self, start: dt.date, end: dt.date, land: str) -> list[dt.date]:
        days, d = [], start
        while d <= end:
            if not cal.is_free(d, (land,)):
                days.append(d)
            d += dt.timedelta(days=1)
        return days

    def split(self, name: str) -> list[dict[str, Any]]:
        """All notices arriving in one split, each with its truth."""
        rng, mail = self.rng, self.cfg["mail"]
        s = self.cfg["splits"][name]
        start, end = dt.date.fromisoformat(s["start"]), dt.date.fromisoformat(s["end"])
        notices: list[dict[str, Any]] = []
        kinds = list(mail["kinds"])
        weights = [mail["kinds"][k] for k in kinds]
        for c in self.clients:
            firm = next(f for f in self.firms if f["id"] == c.firm)
            n = int(mail["per_client"]) + (1 if rng.random() < mail["per_client"] % 1 else 0)
            for _ in range(n):
                for _attempt in range(20):
                    kind = rng.choices(kinds, weights)[0]
                    year = self._year(c, kind)
                    if self._fits(c, kind) and self._free_year(c, kind, year):
                        break
                else:
                    continue
                days = self._working_days(start, end - dt.timedelta(days=5), firm["land"])
                posted = rng.choice(days)
                notices.append(self._notice(c, firm, kind, year, posted))
                if rng.random() < mail["duplicate_copy"] and notices[-1]["meta"]["channel"] == "portal":
                    notices.append(self._copy(notices[-1], firm))
        for _ in range(max(1, int(len(notices) * mail["unknown_client"]))):
            firm = rng.choice(self.firms)
            c = self._client(firm, 99)
            while c.kind == "company":
                c = self._client(firm, 99)
            c.id = "unknown"
            days = self._working_days(start, end - dt.timedelta(days=5), firm["land"])
            n = self._notice(c, firm, "est", 2024, rng.choice(days))
            n["truth"]["action"] = "misrouted"
            n["truth"]["client_id"] = None
            n["truth"]["firm"] = None
            notices.append(n)
        notices.sort(key=lambda x: (x["meta"]["received_at"], x["id"]))
        return notices

    def _free_year(self, c: Client, kind: str, year: int) -> bool:
        """One assessment per client, tax and year in a split's lifetime; a year that is estimated has no return."""
        key = (c.id, "est" if kind == "estimate" else kind, year)
        if kind in ("request", "reminder", "audit", "vz_est"):
            return True
        if key in self.used:
            return False
        self.used.add(key)
        if kind == "estimate":
            self.unfiled.add(key)
        return True

    def _copy(self, original: dict[str, Any], firm: dict) -> dict[str, Any]:
        """The client forwards the paper copy of a notice the firm already received electronically."""
        import copy

        n = copy.deepcopy(original)
        n["id"] = self._id()
        arrive = dt.date.fromisoformat(original["meta"]["received_at"]) + dt.timedelta(days=self.rng.randint(2, 9))
        n["meta"] = {"channel": "client_upload", "received_at": arrive.isoformat(), "quality": "fair"}
        n["truth"] = {**n["truth"], "action": "duplicate", "duplicate_of": original["id"]}
        return n

    def _fits(self, c: Client, kind: str) -> bool:
        if kind in ("est", "vz_est", "estimate"):
            return c.kind in ("person", "trader")
        if kind == "kst":
            return c.kind == "company"
        if kind in ("ust", "gewst_mess", "gewst"):
            return c.kind != "person"
        return True

    def _year(self, c: Client, kind: str) -> int:
        years = self.cfg["mail"]["tax_years"]
        return self.rng.choices(list(years), list(years.values()))[0]

    def _authority(self, c: Client, kind: str) -> dict[str, Any]:
        if kind == "gewst":
            m = self.munis[c.municipality or "berlin"]
            return {"kind": "gemeinde", "name": m["name"], "land": m["land"], "id": m["id"]}
        fa = self.cfg["finanzaemter"][c.land]
        return {"kind": "finanzamt", "name": fa[sum(map(ord, c.id)) % len(fa)], "land": c.land}

    def _channel(self, authority: dict, posted: dt.date) -> str:
        rng, ch = self.rng, self.cfg["channels"]
        if authority["kind"] == "gemeinde":
            return "municipal_digital" if rng.random() < self.munis[authority["id"]]["digital_share"] else "municipal_post"
        share = ch["diva_share_from_2027"] if posted >= dt.date(2027, 1, 1) else ch["diva_share_until_2026"]
        return "portal" if rng.random() < share else "post"

    def _notice(self, c: Client, firm: dict, kind: str, year: int, posted: dt.date) -> dict[str, Any]:
        rng, mail = self.rng, self.cfg["mail"]
        auth = self._authority(c, kind)
        channel = self._channel(auth, posted)
        lands = (firm["land"], auth["land"])
        meta: dict[str, Any] = {"channel": channel}
        provided = notified = None
        if channel in ("portal", "municipal_digital"):
            provided = posted
            notified = posted + dt.timedelta(days=1 if rng.random() < 0.15 else 0)
            meta.update(provided_at=provided.isoformat(), notified_at=notified.isoformat(),
                        received_at=notified.isoformat())
        else:
            arrive = posted + dt.timedelta(days=rng.randint(1, 4))
            arrive = cal.next_working(arrive, (firm["land"],))
            meta.update(received_at=arrive.isoformat(), stamp=arrive.isoformat())
            if rng.random() < mail["postmark_late"]:
                meta["postmark"] = (posted + dt.timedelta(days=rng.randint(3, 5))).isoformat()
            else:
                meta["postmark"] = posted.isoformat()
            meta["quality"] = rng.choices(list(self.cfg["channels"]["scan_quality"]),
                                          list(self.cfg["channels"]["scan_quality"].values()))[0]
        bekannt = cal.received(channel, posted, provided, notified, lands)
        no_rbb = rng.random() < mail["no_appeal_notice"]
        months = 12 if no_rbb else 1
        doc: dict[str, Any] = {
            "kind": kind, "authority": auth, "date": posted.isoformat(), "tax_year": year,
            "addressee": {"name": c.name, "address": c.address, "steuernummer": c.steuernummer},
            "agent": {"name": firm["name"], "city": firm["city"]},
            "fields": {}, "explanations": [], "vorbehalt": False, "vorlaeufig": [],
            "appeal_instructions": not no_rbb, "remedy": "Einspruch",
        }
        truth: dict[str, Any] = {
            "client_id": c.id, "firm": c.firm, "kind": kind, "tax_year": year, "bekanntgabe": bekannt.isoformat(),
            "deadline": cal.deadline(bekannt, months, lands).isoformat(), "deviations": [], "errors": [],
            "action": "close", "deadline_basis": "remedy",
        }
        if kind == "gewst":
            m = self.munis[auth["id"]]
            doc["remedy"] = m["remedy"]
        build = getattr(self, f"_k_{kind}")
        build(c, firm, year, doc, truth, bekannt)
        if kind in ("est", "kst", "ust", "gewst_mess", "estimate"):
            doc["vorbehalt"] = rng.random() < mail["vorbehalt"]
            if rng.random() < mail["vorlaeufig"]:
                doc["vorlaeufig"] = rng.sample(
                    ["Abziehbarkeit der Beiträge zu Rentenversicherungen (§ 10 Abs. 1 Nr. 2 EStG)",
                     "Höhe des Grundfreibetrags", "Verfassungsmäßigkeit des Solidaritätszuschlags"], 1)
        truth["no_appeal_instructions"] = no_rbb
        return {"id": self._id(), "meta": meta, "doc": doc, "truth": truth}

    # --- deviations shared by assessments
    def _deviate(self, kind: str, filed: dict[str, int], truth: dict, doc: dict) -> dict[str, int]:
        """Pick the office's changes; returns the changed base figures (not yet recomputed)."""
        rng, cfg = self.rng, self.cfg["deviations"]
        assessed = dict(filed)
        if rng.random() >= cfg.get(kind, 0):
            return assessed
        reasons = self.cfg["reasons"][kind]
        favour = rng.random() < cfg["in_favour_share"]
        def usable(r: dict) -> bool:
            f = r["field"]
            return f in filed and (filed[f] != 0 or f in ("hinzurechnungen", "kuerzungen", "sonderausgaben"))

        pool = [r for r in reasons if (not r["against"]) == favour and usable(r)] or \
            [r for r in reasons if usable(r)]
        if not pool:
            return assessed
        picks = rng.sample(pool, k=min(len(pool), 2 if rng.random() < 0.2 else 1))
        for r in picks:
            fld = r["field"]
            amount = eur(rng.uniform(300, 6500))
            # "against" the client: more income, less deduction, less input VAT
            deduction = fld in ("sonderausgaben", "agb", "vorsteuer", "kuerzungen")
            sign = 1 if r["against"] else -1
            delta = -amount * sign if deduction else amount * sign
            if deduction:
                delta = max(delta, -assessed[fld])
                if delta == 0:
                    continue
            assessed[fld] += delta
            unexplained = rng.random() < cfg["unexplained_share"]
            text = self.cfg["reasons"]["unexplained"] if unexplained else r["text"]
            if text not in doc["explanations"]:
                doc["explanations"].append(text)
            truth["deviations"].append({"field": fld, "filed": filed[fld], "assessed": assessed[fld],
                                        "reason": None if unexplained else r["id"], "against": r["against"],
                                        "cite": r["cite"]})
        return assessed

    def _settle(self, truth: dict, filed_rest: int, assessed_rest: int) -> None:
        """Action for an assessment from its deviations (errors are added by the caller)."""
        if not truth["deviations"]:
            return
        against = [d for d in truth["deviations"] if d["against"]]
        effect = assessed_rest - filed_rest
        if against and (effect >= 5000 or truth["kind"] == "gewst_mess"):
            truth["action"] = "objection_review"
        else:
            truth["action"] = "inform_client"
        truth["tax_effect"] = effect

    def _interest(self, kind: str, year: int, base: int, bekannt: dt.date, truth: dict) -> int:
        start = dt.date(year + 2, 4, 1)  # 15 months after the end of the tax year
        if bekannt < start or base == 0:
            return 0
        months = cal.full_months(start, bekannt)
        rounded = abs(base) // 5000 * 5000
        cents = rounded * 15 * months // 10000 // 100 * 100
        if cents < 1000:
            cents = 0
        truth["interest"] = {"start": start.isoformat(), "months": months, "base": rounded,
                             "amount": cents if base > 0 else -cents}
        if cents and self.rng.random() < self.cfg["interest_errors"]:
            wrong = rounded * 15 * (months + 1) // 10000 // 100 * 100
            truth["errors"].append({"type": "interest", "correct": truth["interest"]["amount"],
                                    "stated": wrong if base > 0 else -wrong})
            return wrong if base > 0 else -wrong
        return truth["interest"]["amount"]

    def _k_est(self, c: Client, firm: dict, year: int, doc: dict, truth: dict, bekannt: dt.date) -> None:
        filed = c.filed["est"][year]
        assessed = self._deviate("est", filed, truth, doc)
        f = self._est_fields(c, year, assessed["einkuenfte_nsa"], assessed["einkuenfte_gewerbe"],
                             assessed["einkuenfte_vuv"], assessed["sonderausgaben"], assessed["agb"],
                             (filed["lst_est"], filed["vz_est"], filed["lst_soli"], filed["lst_kist"]))
        f["zinsen_est"] = self._interest("est", year, f["rest_est"], bekannt, truth)
        doc["fields"] = f
        doc["title"] = f"Bescheid für {year} über Einkommensteuer, Solidaritätszuschlag und Kirchensteuer"
        self._settle(truth, filed["rest_est"] + filed["rest_soli"] + filed["rest_kist"],
                     f["rest_est"] + f["rest_soli"] + f["rest_kist"])
        self._errors_to_action(truth)

    def _k_estimate(self, c: Client, firm: dict, year: int, doc: dict, truth: dict, bekannt: dt.date) -> None:
        base = c.filed["est"][year]
        nsa, gew = int(base["einkuenfte_nsa"] * 1.15) // 100 * 100, int(base["einkuenfte_gewerbe"] * 1.3) // 100 * 100
        f = self._est_fields(c, year, nsa, gew, base["einkuenfte_vuv"], 0, 0, (base["lst_est"], 0, base["lst_soli"],
                                                                                base["lst_kist"]))
        f["zinsen_est"] = 0
        doc["fields"] = f
        doc["title"] = f"Bescheid für {year} über Einkommensteuer, Solidaritätszuschlag und Kirchensteuer"
        doc["explanations"].append("Da Sie Ihre Steuererklärung trotz Aufforderung nicht abgegeben haben, wurden die "
                                   "Besteuerungsgrundlagen gemäß § 162 AO geschätzt.")
        doc["estimate"] = True
        doc["kind"] = "est"
        truth["kind"] = "est"
        truth["estimate"] = True
        truth["action"] = "objection_required"
        truth["unfiled"] = True

    def _k_kst(self, c: Client, firm: dict, year: int, doc: dict, truth: dict, bekannt: dt.date) -> None:
        filed = c.filed["kst"][year]
        a = self._deviate("kst", filed, truth, doc)
        kst = a["einkommen"] * 15 // 100
        f = {"einkommen": a["einkommen"], "kst": kst, "soli": round(kst * 0.055), "vz_kst": filed["vz_kst"],
             "rest_kst": kst - filed["vz_kst"]}
        f["zinsen_kst"] = self._interest("kst", year, f["rest_kst"], bekannt, truth)
        doc["fields"] = f
        doc["title"] = f"Bescheid für {year} über Körperschaftsteuer und Solidaritätszuschlag"
        self._settle(truth, filed["rest_kst"] + filed["soli"], f["rest_kst"] + f["soli"])
        self._errors_to_action(truth)

    def _k_ust(self, c: Client, firm: dict, year: int, doc: dict, truth: dict, bekannt: dt.date) -> None:
        filed = c.filed["ust"][year]
        a = self._deviate("ust", filed, truth, doc)
        ust = a["umsatz_19"] * 19 // 100 + a["umsatz_7"] * 7 // 100
        zl = ust - a["vorsteuer"]
        f = {"umsatz_19": a["umsatz_19"], "umsatz_7": a["umsatz_7"], "ust": ust, "vorsteuer": a["vorsteuer"],
             "zahllast": zl, "vz_ust": filed["vz_ust"], "rest_ust": zl - filed["vz_ust"]}
        f["zinsen_ust"] = self._interest("ust", year, f["rest_ust"], bekannt, truth)
        doc["fields"] = f
        doc["title"] = f"Bescheid für {year} über Umsatzsteuer"
        self._settle(truth, filed["rest_ust"], f["rest_ust"])
        self._errors_to_action(truth)

    def _k_gewst_mess(self, c: Client, firm: dict, year: int, doc: dict, truth: dict, bekannt: dt.date) -> None:
        filed = c.filed["gewst_mess"][year]
        a = self._deviate("gewst_mess", filed, truth, doc)
        ertrag, frei, mb = tax.messbetrag(a["gewinn"], a["hinzurechnungen"], a["kuerzungen"], c.kind != "company")
        doc["fields"] = {"gewinn": a["gewinn"], "hinzurechnungen": a["hinzurechnungen"], "kuerzungen": a["kuerzungen"],
                         "gewerbeertrag": ertrag, "freibetrag": frei, "messbetrag": mb}
        doc["title"] = f"Bescheid für {year} über den Gewerbesteuermessbetrag"
        doc["municipality"] = self.munis[c.municipality or "berlin"]["name"]
        self._settle(truth, filed["messbetrag"], mb)

    def _k_gewst(self, c: Client, firm: dict, year: int, doc: dict, truth: dict, bekannt: dt.date) -> None:
        rng, me = self.rng, self.cfg["municipal_errors"]
        m = self.munis[c.municipality or "berlin"]
        mess = c.filed["gewst_mess"][year]["messbetrag"]
        on = {"client_id": c.id, "firm": c.firm, "steuernummer": c.steuernummer, "kind": "gewst_mess", "year": year,
              "date": f"{year + 1}-{rng.randint(6, 9):02d}-{rng.randint(1, 28):02d}", "messbetrag": mess}
        self.onfile.append(on)
        used, hebesatz = mess, m["hebesatz"]
        if rng.random() < me["stale_messbetrag"]:
            changed = max(0, mess + rng.choice([-1, 1]) * 350 * rng.randint(3, 60))
            if changed != mess:
                self.onfile.append({**on, "date": f"{year + 1}-10-{rng.randint(1, 28):02d}", "messbetrag": changed,
                                    "changed": True})
                truth["errors"].append({"type": "stale_messbetrag", "stated": mess, "correct": changed})
                truth["messbetrag_on_file"] = changed
        if rng.random() < me["wrong_hebesatz"]:
            hebesatz = m["hebesatz"] + rng.choice([-30, -20, 20, 25, 40])
            truth["errors"].append({"type": "wrong_hebesatz", "stated": hebesatz, "correct": m["hebesatz"]})
        gewst = used * hebesatz // 100
        if rng.random() < me["arithmetic"]:
            stated = gewst + eur(rng.uniform(50, 900)) * rng.choice([-1, 1])
            truth["errors"].append({"type": "arithmetic", "stated": stated, "correct": gewst})
            gewst = stated
        vz = gewst * rng.choice([0, 50, 75, 100]) // 100 // 100 * 100
        doc["fields"] = {"messbetrag": used, "hebesatz": hebesatz * 100, "gewst": gewst, "vz_gewst": vz,
                         "rest_gewst": gewst - vz}
        doc["messbescheid_date"] = on["date"]
        doc["title"] = f"Gewerbesteuerbescheid für das Kalenderjahr {year}"
        truth["hebesatz_register"] = m["hebesatz"]
        self._errors_to_action(truth)

    def _k_vz_est(self, c: Client, firm: dict, year: int, doc: dict, truth: dict, bekannt: dt.date) -> None:
        f = c.filed["est"][2025]
        q = max(0, (f["est"] - f["lst_est"]) // 4 // 100 * 100)
        doc["fields"] = {"vz_quartal": q}
        doc["vz_year"] = 2027
        doc["title"] = "Bescheid über Vorauszahlungen zur Einkommensteuer ab 2027"
        doc["tax_year"] = 2027
        truth["tax_year"] = 2027
        truth["action"] = "inform_client"

    def _letter(self, c: Client, doc: dict, truth: dict, title: str, topic: str, weeks: int) -> None:
        posted = dt.date.fromisoformat(doc["date"])
        due = posted + dt.timedelta(weeks=weeks)
        doc["title"] = title
        doc["letter"] = {"topic": topic, "due": due.isoformat()}
        doc["fields"] = {}
        truth["action"] = "task"
        truth["deadline"] = due.isoformat()
        truth["deadline_basis"] = "authority"

    def _k_request(self, c: Client, firm: dict, year: int, doc: dict, truth: dict, bekannt: dt.date) -> None:
        topic = self.rng.choice(["Nachweise über die geltend gemachten Fahrtkosten",
                                 "Zuwendungsbestätigungen für die erklärten Spenden",
                                 "den Mietvertrag und die Nebenkostenabrechnung",
                                 "eine Aufstellung der Bewirtungsaufwendungen"])
        self._letter(c, doc, truth, f"Steuererklärung {year}: Anforderung von Unterlagen", topic, 4)

    def _k_reminder(self, c: Client, firm: dict, year: int, doc: dict, truth: dict, bekannt: dt.date) -> None:
        self._letter(c, doc, truth, f"Erinnerung an die Abgabe der Steuererklärung für {year}",
                     "die Abgabe der Steuererklärung", 3)

    def _k_audit(self, c: Client, firm: dict, year: int, doc: dict, truth: dict, bekannt: dt.date) -> None:
        posted = dt.date.fromisoformat(doc["date"])
        start = posted + dt.timedelta(weeks=6)
        doc["title"] = "Prüfungsanordnung"
        doc["letter"] = {"topic": f"Außenprüfung für die Jahre {year - 2} bis {year}", "due": start.isoformat()}
        doc["fields"] = {}
        truth["action"] = "task"
        truth["audit_start"] = start.isoformat()  # deadline stays the objection period

    def _errors_to_action(self, truth: dict) -> None:
        if truth["errors"]:
            truth["action"] = "objection_required"

    # ----------------------------------------------------------------- histories
    def histories(self) -> list[dict[str, Any]]:
        rng = self.rng
        out = []
        for c in self.clients:
            kinds = [k for k in ("est", "kst", "ust", "gewst_mess") if k in c.filed]
            for year in (2021, 2022):
                if rng.random() < 0.55:
                    k = rng.choice(kinds)
                    r = rng.choice(self.cfg["reasons"][k])
                    objected = r["against"] and rng.random() < 0.7
                    out.append({"client_id": c.id, "firm": c.firm, "year": year, "kind": k, "reason": r["id"],
                                "text": r["text"], "objection": objected,
                                "outcome": rng.choice(["abgeholfen", "teilweise abgeholfen", "zurückgenommen",
                                                       "zurückgewiesen"]) if objected else None})
        return out
