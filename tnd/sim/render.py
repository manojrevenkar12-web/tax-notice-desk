"""Turn a simulated notice into what actually arrives: a PDF from the tax office's portal with its data file,
a municipal PDF with embedded XML, or a scan of paper mail. Towns each have their own layout, wording and
number format, as the roughly 600 paper formats in circulation do."""

from __future__ import annotations

import datetime as dt
import io
import random
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from PIL import Image, ImageFilter
from pypdf import PdfReader, PdfWriter
from reportlab import rl_config
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from ..money import fmt

rl_config.invariant = 1  # same input, same bytes: OCR results are cached by file hash
FIXED = time.gmtime(1767225600)  # 2026-01-01

FA_LABELS: dict[str, list[tuple[str, str]]] = {
    "est": [
        ("einkuenfte_nsa", "Einkünfte aus nichtselbständiger Arbeit"),
        ("einkuenfte_gewerbe", "Einkünfte aus Gewerbebetrieb"),
        ("einkuenfte_vuv", "Einkünfte aus Vermietung und Verpachtung"),
        ("summe_einkuenfte", "Summe der Einkünfte"),
        ("sonderausgaben", "Sonderausgaben"),
        ("agb", "außergewöhnliche Belastungen"),
        ("zve", "zu versteuerndes Einkommen"),
    ],
    "kst": [("einkommen", "zu versteuerndes Einkommen")],
    "ust": [
        ("umsatz_19", "steuerpflichtige Umsätze zu 19 %"),
        ("umsatz_7", "steuerpflichtige Umsätze zu 7 %"),
        ("ust", "Umsatzsteuer"),
        ("vorsteuer", "abziehbare Vorsteuerbeträge"),
        ("zahllast", "verbleibende Umsatzsteuer"),
    ],
    "gewst_mess": [
        ("gewinn", "Gewinn aus Gewerbebetrieb"),
        ("hinzurechnungen", "Hinzurechnungen"),
        ("kuerzungen", "Kürzungen"),
        ("gewerbeertrag", "Gewerbeertrag (abgerundet)"),
        ("freibetrag", "Freibetrag"),
        ("messbetrag", "Steuermessbetrag"),
    ],
}

MUNI_LABELS = {
    "messbetrag": [
        "Steuermessbetrag",
        "Gewerbesteuermessbetrag",
        "Messbetrag lt. Messbescheid",
        "Festgesetzter Messbetrag",
        "Messbetrag (Finanzamt)",
    ],
    "hebesatz": ["Hebesatz", "Hebesatz v.H.", "Hebesatz in %", "Hebesatz der Gemeinde", "Hebesatz (%)"],
    "gewst": [
        "Gewerbesteuer",
        "festgesetzte Gewerbesteuer",
        "Gewerbesteuer (Jahressteuer)",
        "Steuerbetrag",
        "Gewerbesteuer festgesetzt",
    ],
    "vz_gewst": [
        "Vorauszahlungen",
        "abzgl. geleistete Vorauszahlungen",
        "bisher festgesetzte Vorauszahlungen",
        "Vorauszahlungssoll",
        "Anrechnung Vorauszahlungen",
    ],
    "rest_gewst": [
        "Abschlusszahlung",
        "Restbetrag",
        "Nachzahlung / Erstattung",
        "noch zu zahlen (+) / Erstattung (-)",
        "Differenz",
    ],
}
NUMBER_STYLES = ["de", "eur", "de_plain", "trailing_minus"]
FONTS = [("Helvetica", "Helvetica-Bold"), ("Times-Roman", "Times-Bold"), ("Courier", "Courier-Bold")]


def de_date(iso: str) -> str:
    return dt.date.fromisoformat(iso).strftime("%d.%m.%Y")


def muni_style(muni_id: str) -> dict[str, Any]:
    r = random.Random(f"layout-{muni_id}")
    return {
        "labels": {k: r.choice(v) for k, v in MUNI_LABELS.items()},
        "numbers": r.choice(NUMBER_STYLES),
        "structure": r.choices(["lines", "table", "prose"], [5, 3, 2])[0],
        "font": r.choice(FONTS),
        "hebesatz": r.choice(["{} %", "{} v.H.", "{},00 %", "{}"]),
        "order": r.random() < 0.5,
    }


class Page:
    def __init__(self, font: tuple[str, str] = FONTS[0], size: float = 8.6) -> None:
        self.buf = io.BytesIO()
        self.c = canvas.Canvas(self.buf, pagesize=A4)
        self.font, self.bold = font
        self.size = size
        self.y = A4[1] - 18 * mm
        self.x = 20 * mm

    def text(self, s: str, bold: bool = False, size: float | None = None, x: float | None = None) -> None:
        self.c.setFont(self.bold if bold else self.font, size or self.size)
        self.c.drawString(x if x is not None else self.x, self.y, s)
        self.y -= (size or self.size) * 1.42

    def pair(self, label: str, value: str, x2: float = 150 * mm) -> None:
        self.c.setFont(self.font, self.size)
        self.c.drawString(self.x, self.y, label)
        self.c.drawRightString(x2 + 30 * mm, self.y, value)
        self.y -= self.size * 1.42

    def wrap(self, s: str, width: int = 105) -> None:
        line = ""
        for w in s.split():
            if len(line) + len(w) + 1 > width:
                self.text(line)
                line = w
            else:
                line = f"{line} {w}".strip()
        if line:
            self.text(line)

    def gap(self, n: float = 1) -> None:
        self.y -= self.size * 1.42 * n

    def pdf(self) -> bytes:
        self.c.showPage()
        self.c.save()
        return self.buf.getvalue()


def _head(p: Page, doc: dict) -> None:
    a = doc["authority"]
    p.text(a["name"], bold=True, size=11)
    p.text("Steuerverwaltung" if a["kind"] == "finanzamt" else "Steueramt / Kämmerei", size=7.5)
    p.gap(1.2)
    p.text(f"{doc['agent']['name']}")
    p.text(f"als Empfangsbevollmächtigte für {doc['addressee']['name']}")
    p.text(doc["agent"]["city"])
    p.gap(0.8)
    p.text(f"Steuernummer: {doc['addressee']['steuernummer']}", x=120 * mm)
    p.text(f"Datum: {de_date(doc['date'])}", x=120 * mm)
    p.text(f"Steuerpflichtige(r): {doc['addressee']['name']}, {doc['addressee']['address']}", x=20 * mm)
    p.gap(0.8)
    p.text(doc["title"], bold=True, size=10)
    p.gap(0.5)


def _flags(p: Page, doc: dict) -> None:
    if doc.get("vorbehalt"):
        p.wrap("Die Festsetzung steht nach § 164 Abs. 1 AO unter dem Vorbehalt der Nachprüfung.")
    for v in doc.get("vorlaeufig", []):
        p.wrap(f"Die Festsetzung ist gemäß § 165 Abs. 1 Satz 2 AO vorläufig hinsichtlich: {v}.")


def _remedy(p: Page, doc: dict) -> None:
    if not doc.get("appeal_instructions", True) or doc["kind"] in ("request", "reminder"):
        return
    p.gap(0.6)
    p.text("Rechtsbehelfsbelehrung", bold=True)
    if doc.get("remedy") == "Widerspruch":
        p.wrap(
            f"Gegen diesen Bescheid kann innerhalb eines Monats nach Bekanntgabe Widerspruch erhoben werden. "
            f"Der Widerspruch ist schriftlich oder zur Niederschrift bei {doc['authority']['name']} einzulegen."
        )
    else:
        p.wrap(
            f"Gegen diesen Bescheid ist der Einspruch gegeben. Der Einspruch ist bei {doc['authority']['name']} "
            "schriftlich einzureichen, diesem elektronisch zu übermitteln oder dort zur Niederschrift zu erklären. "
            "Die Frist für die Einlegung des Einspruchs beträgt einen Monat. Sie beginnt mit Ablauf des Tages, an "
            "dem Ihnen dieser Bescheid bekannt gegeben worden ist."
        )


def _explain(p: Page, doc: dict) -> None:
    if doc.get("explanations"):
        p.gap(0.4)
        p.text("Erläuterungen", bold=True)
        for e in doc["explanations"]:
            p.wrap(e)


def _interest(p: Page, f: dict, label: str, key: str, year: int, bekannt_hint: str | None) -> None:
    if f.get(key):
        p.gap(0.3)
        p.pair(f"Zinsen zur {label} (§ 233a AO)", fmt(f[key]))


def finanzamt_pdf(doc: dict) -> bytes:
    p = Page()
    _head(p, doc)
    f, k = doc["fields"], doc["kind"]
    if k in ("request", "reminder", "audit"):
        L = doc["letter"]
        if k == "request":
            p.wrap(
                f"Sehr geehrte Damen und Herren, zur Bearbeitung der Steuererklärung für {doc['tax_year']} "
                f"bitte ich Sie, {L['topic']} bis zum {de_date(L['due'])} einzureichen."
            )
        elif k == "reminder":
            p.wrap(
                f"Sehr geehrte Damen und Herren, die Steuererklärung für {doc['tax_year']} liegt noch nicht vor. "
                f"Bitte reichen Sie die Erklärung spätestens bis zum {de_date(L['due'])} ein. Andernfalls müssen die "
                "Besteuerungsgrundlagen geschätzt werden (§ 162 AO) und ein Verspätungszuschlag kann festgesetzt "
                "werden (§ 152 AO)."
            )
        else:
            p.wrap(
                f"Gemäß § 196 AO in Verbindung mit § 193 AO wird eine {L['topic']} angeordnet. "
                f"Die Prüfung beginnt am {de_date(L['due'])} in Ihren Geschäftsräumen. Bitte halten Sie die "
                "Unterlagen bereit (§ 200 AO)."
            )
        _remedy(p, doc)
        return p.pdf()
    if k == "vz_est":
        p.wrap(
            f"Die Vorauszahlungen zur Einkommensteuer werden ab dem Kalenderjahr {doc['vz_year']} wie folgt "
            "festgesetzt (§ 37 EStG):"
        )
        p.pair("Vorauszahlung je Quartal", fmt(f["vz_quartal"]))
        p.wrap("Fälligkeit: 10.03., 10.06., 10.09. und 10.12.")
        _remedy(p, doc)
        return p.pdf()
    p.text("Ermittlung der Besteuerungsgrundlagen", bold=True)
    for key, label in FA_LABELS[k]:
        p.pair(label, fmt(f[key]))
    p.gap(0.4)
    if k == "est":
        p.text("Festsetzung", bold=True)
        p.pair("Einkommensteuer", fmt(f["est"]))
        p.pair("Solidaritätszuschlag", fmt(f["soli"]))
        p.pair("Kirchensteuer", fmt(f["kist"]))
        for tax, a, b, c in (
            ("Einkommensteuer", "est", "lst_est", "vz_est"),
            ("Solidaritätszuschlag", "soli", "lst_soli", None),
            ("Kirchensteuer", "kist", "lst_kist", None),
        ):
            p.text(f"Abrechnung {tax}", bold=True)
            p.pair("festgesetzt", fmt(f[a]))
            p.pair("abzüglich Steuerabzugsbeträge", fmt(f[b]))
            if c:
                p.pair("abzüglich Vorauszahlungen", fmt(f[c]))
            rest = {"est": "rest_est", "soli": "rest_soli", "kist": "rest_kist"}[a]
            p.pair("verbleibende Beträge", fmt(f[rest]))
        _interest(p, f, "Einkommensteuer", "zinsen_est", doc["tax_year"], None)
    elif k == "kst":
        p.text("Festsetzung", bold=True)
        p.pair("Körperschaftsteuer", fmt(f["kst"]))
        p.pair("Solidaritätszuschlag", fmt(f["soli"]))
        p.text("Abrechnung Körperschaftsteuer", bold=True)
        p.pair("festgesetzt", fmt(f["kst"]))
        p.pair("abzüglich Vorauszahlungen", fmt(f["vz_kst"]))
        p.pair("verbleibende Beträge", fmt(f["rest_kst"]))
        _interest(p, f, "Körperschaftsteuer", "zinsen_kst", doc["tax_year"], None)
    elif k == "ust":
        p.text("Abrechnung Umsatzsteuer", bold=True)
        p.pair("festgesetzt", fmt(f["zahllast"]))
        p.pair("abzüglich Vorauszahlungssoll", fmt(f["vz_ust"]))
        p.pair("verbleibende Beträge", fmt(f["rest_ust"]))
        _interest(p, f, "Umsatzsteuer", "zinsen_ust", doc["tax_year"], None)
    elif k == "gewst_mess":
        p.wrap(
            f"Hebeberechtigte Gemeinde: {doc['municipality']}. Der Steuermessbetrag wird der Gemeinde mitgeteilt; "
            "sie setzt die Gewerbesteuer fest."
        )
    _flags(p, doc)
    _explain(p, doc)
    _remedy(p, doc)
    return p.pdf()


def municipal_pdf(doc: dict) -> bytes:
    st = muni_style(doc["authority"]["id"])
    p = Page(font=st["font"], size=8.8)
    _head(p, doc)
    f = doc["fields"]
    hs = st["hebesatz"].format(f["hebesatz"] // 100)
    num = st["numbers"]
    L = st["labels"]
    p.wrap(f"Grundlage: Gewerbesteuermessbescheid des Finanzamts vom {de_date(doc['messbescheid_date'])}.")
    rows = [
        ("messbetrag", fmt(f["messbetrag"], num)),
        ("hebesatz", hs),
        ("gewst", fmt(f["gewst"], num)),
        ("vz_gewst", fmt(f["vz_gewst"], num)),
        ("rest_gewst", fmt(f["rest_gewst"], num)),
    ]
    if st["structure"] == "prose":
        p.wrap(
            f"Der {L['messbetrag']} beträgt {rows[0][1]}. Bei einem Hebesatz von {hs} ergibt sich eine Gewerbesteuer "
            f"von {rows[2][1]}. Hierauf werden Vorauszahlungen in Höhe von {rows[3][1]} angerechnet, so dass sich "
            f"ein Betrag von {rows[4][1]} ergibt (positiv: Nachzahlung, negativ: Erstattung)."
        )
    elif st["structure"] == "table":
        p.text("   ".join(L[k] for k, _ in rows[:3]), bold=True)
        p.text("   ".join(v for _, v in rows[:3]))
        p.gap(0.5)
        for k, v in rows[3:]:
            p.pair(L[k], v)
    else:
        order = rows if st["order"] else [rows[1], rows[0], rows[2], rows[3], rows[4]]
        for k, v in order:
            p.pair(L[k], v)
    p.wrap("Die Abschlusszahlung ist einen Monat nach Bekanntgabe dieses Bescheids fällig.")
    _remedy(p, doc)
    return p.pdf()


def data_xml(doc: dict) -> str:
    """The structured data that comes with an electronic notice (an illustrative schema, not ELSTER's)."""
    parts = [
        f'<Bescheid art="{doc["kind"]}" jahr="{doc["tax_year"]}">',
        f"<Behoerde>{escape(doc['authority']['name'])}</Behoerde>",
        f"<Steuernummer>{doc['addressee']['steuernummer']}</Steuernummer>",
        f"<Datum>{doc['date']}</Datum>",
        f"<Vorbehalt>{'ja' if doc.get('vorbehalt') else 'nein'}</Vorbehalt>",
    ]
    for k, v in doc["fields"].items():
        parts.append(f'<Wert name="{k}">{v}</Wert>')
    if doc.get("letter"):
        parts.append(f"<Frist>{doc['letter']['due']}</Frist>")
    parts.append("</Bescheid>")
    return "\n".join(parts)


def embed(pdf: bytes, name: str, payload: str) -> bytes:
    w = PdfWriter()
    for page in PdfReader(io.BytesIO(pdf)).pages:
        w.add_page(page)
    w.add_attachment(name, payload.encode())
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


def scan(pdf: bytes, quality: str, seed: str) -> bytes:
    """Print, scan: an image-only PDF, slightly rotated and noisy."""
    r = random.Random(seed)
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "in.pdf"
        src.write_bytes(pdf)
        dpi = {"good": 200, "fair": 150, "poor": 120}[quality]
        subprocess.run(
            ["pdftoppm", "-r", str(dpi), "-gray", "-png", "-singlefile", str(src), str(Path(d) / "p")], check=True
        )
        img = Image.open(Path(d) / "p.png").convert("L")
    angle = r.uniform(-1.2, 1.2) * {"good": 0.4, "fair": 1, "poor": 1.6}[quality]
    img = img.rotate(angle, expand=False, fillcolor=255, resample=Image.Resampling.BICUBIC)
    if quality != "good":
        img = img.filter(ImageFilter.GaussianBlur(radius=0.5 if quality == "fair" else 0.85))
    px = img.load()
    assert px is not None
    w, h = img.size
    for _ in range(int(w * h * {"good": 0.0005, "fair": 0.002, "poor": 0.004}[quality])):
        x, y = r.randrange(w), r.randrange(h)
        px[x, y] = r.choice([0, 80, 200])
    out = io.BytesIO()
    img.convert("RGB").save(out, format="PDF", resolution=dpi, quality=70, creationDate=FIXED, modDate=FIXED)
    return out.getvalue()


def render(n: dict) -> dict[str, bytes]:
    """Files that arrive for one notice: {'pdf': ..., optional 'xml': ...}."""
    doc, meta = n["doc"], n["meta"]
    pdf = municipal_pdf(doc) if doc["authority"]["kind"] == "gemeinde" else finanzamt_pdf(doc)
    ch = meta["channel"]
    if ch == "portal":
        return {"pdf": pdf, "xml": data_xml(doc).encode()}
    if ch == "municipal_digital":
        return {"pdf": embed(pdf, "gewerbesteuer.xml", data_xml(doc))}
    return {"pdf": scan(pdf, meta.get("quality", "good"), n["id"])}
