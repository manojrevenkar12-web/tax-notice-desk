"""Reading notices: amounts in all their spellings, labels through OCR noise, towns' own layouts, and the
arithmetic that decides whether a value is trusted."""

import datetime as dt

from hypothesis import given
from hypothesis import strategies as st

from tnd.intake.parse import classify, extract, find, money
from tnd.intake.read import Reading, normalise
from tnd.knowledge.corpus import law_units
from tnd.knowledge.retrieve import search
from tnd.money import fmt


@given(st.integers(-(10**10), 10**10), st.sampled_from(["de", "eur", "de_plain", "trailing_minus"]))
def test_every_amount_format_reads_back(cents, style):
    assert money(fmt(cents, style)) == cents


def test_ocr_damage_in_numbers_is_undone():
    assert money(normalise("Gewerbesteuer von EUR 15 544, 37.")) == 1554437
    assert money(normalise("abzüglich Vorauszahlungssoll : .  119.175.80 €")) == 11917580
    assert money(normalise("Summe 4O.12l,00 €")) == 4012100


def test_labels_are_found_through_ocr_noise_but_not_inside_other_words():
    assert find("zu versteuerndes. Einkommen 46.074,00 €", "zu versteuerndes Einkommen", 0.84) is not None
    assert find("Der Fesigeseizter Messbetrag beträgt", "Festgesetzter Messbetrag", 0.84) is not None
    assert find("Gewerbesteuerbescheid für das Kalenderjahr 2025", "Gewerbesteuer", 0.84) is None


TOWN_PROSE = """Stadt Köln
Steuernummer: 214/2663/5728
Datum: 26.10.2026
Gewerbesteuerbescheid für das Kalenderjahr 2025
Grundlage: Gewerbesteuermessbescheid des Finanzamts vom 18.09.2026.
Der Festgesetzter Messbetrag beträgt EUR 3 272,50. Bei einem Hebesatz von 475,00 % ergibt sich eine
Gewerbesteuer von EUR 15 544,37. Hierauf werden Vorauszahlungen in Höhe von EUR 11 658,00 angerechnet, so
dass sich ein Betrag von EUR 3 886,37 ergibt.
Rechtsbehelfsbelehrung
Gegen diesen Bescheid kann innerhalb eines Monats nach Bekanntgabe Widerspruch erhoben werden."""

TOWN_TABLE = """Stadt Garching b. München
Steuernummer: 214/9701/6510
Datum: 26.10.2026
Gewerbesteuerbescheid für das Kalenderjahr 2025
Messbetrag lt. Messbescheid   Hebesatz (%)   Steuerbetrag
8.680,00 €   280,00 %   24.304,00 €
Anrechnung Vorauszahlungen 12.152,00 €
Differenz 12.152,00 €"""


def test_a_town_written_in_prose_reads_with_learned_labels():
    p = extract(
        Reading(TOWN_PROSE, "text"),
        {"vz_gewst": ["Vorauszahlungen in Höhe von"], "rest_gewst": ["ein Betrag von"], "gewst": ["Gewerbesteuer von"]},
    )
    assert p.kind == "gewst" and p.remedy == "Widerspruch" and p.messbescheid_date == "2026-09-18"
    assert p.fields == {
        "messbetrag": 327250,
        "hebesatz": 47500,
        "gewst": 1554437,
        "vz_gewst": 1165800,
        "rest_gewst": 388637,
    }
    assert p.verified


def test_a_town_table_reads_once_its_labels_are_learned_and_not_before():
    before = extract(Reading(TOWN_TABLE, "text"))
    assert not before.verified
    learned = {
        "messbetrag": ["Messbetrag lt. Messbescheid"],
        "gewst": ["Steuerbetrag"],
        "vz_gewst": ["Anrechnung Vorauszahlungen"],
        "rest_gewst": ["Differenz"],
    }
    p = extract(Reading(TOWN_TABLE, "text"), learned)
    assert p.fields["messbetrag"] == 868000 and p.fields["hebesatz"] == 28000 and p.fields["gewst"] == 2430400
    assert p.verified


def test_values_that_do_not_add_up_are_not_trusted():
    bad = TOWN_PROSE.replace("EUR 3 886,37", "EUR 3 886,73")
    p = extract(
        Reading(bad, "text"),
        {"vz_gewst": ["Vorauszahlungen in Höhe von"], "rest_gewst": ["ein Betrag von"], "gewst": ["Gewerbesteuer von"]},
    )
    assert not p.verified and "rest_gewst" in p.failed_checks


def test_classification():
    assert classify(TOWN_PROSE) == "gewst"
    assert classify("Finanzamt Köln-Süd\nBescheid für 2024 über Einkommensteuer, Solidaritätszuschlag") == "est"
    assert classify("Finanzamt\nErinnerung an die Abgabe der Steuererklärung für 2025") == "reminder"
    assert classify("Finanzamt\nPrüfungsanordnung\nGemäß § 196 AO") == "audit"


def test_the_law_as_in_force_on_a_date():
    v = {u.id: u for u in law_units() if u.ref == "AO § 122a" and u.paragraph == "(4)"}
    on = [u for u in v.values() if u.current(dt.date(2024, 6, 1))]
    assert len(on) == 1 and "dritten Tag" in on[0].text
    on = [u for u in v.values() if u.current(dt.date(2025, 6, 1))]
    assert len(on) == 1 and "vierten Tag nach Absendung" in on[0].text
    on = [u for u in v.values() if u.current(dt.date(2026, 6, 1))]
    assert len(on) == 1 and "vierten Tag nach der Bereitstellung" in on[0].text


def test_retrieval_marks_outdated_text_and_follows_citations():
    hits = search(
        "Die Aufwendungen für das häusliche Arbeitszimmer wurden nur mit der Tagespauschale berücksichtigt.",
        dt.date(2025, 12, 31),
        "einkuenfte_nsa",
        k=5,
    )
    estg4 = next(h for h in hits if h.unit.kind == "law" and h.unit.ref == "EStG § 4")
    assert estg4.stale and "2022" in estg4.stale
    hits = search("Die Besteuerungsgrundlagen wurden gemäß § 162 AO geschätzt.", dt.date(2025, 12, 31), None, k=3)
    assert hits[0].unit.ref == "AO § 162" and hits[0].why == "cited on the notice"


# The layout reader: layouts the labels have never seen. Values still count only if the arithmetic holds.
COLUMNS = """Finanzamt Musterstadt
Steuernummer: 21/815/08150
Datum: 03.11.2026

Bescheid für 2025 über Einkommensteuer und Kirchensteuer

Festsetzung            Einkommensteuer     Kirchenst. rk
festgesetzt werden          9.120,00 €          820,80 €
ab Steuerabzug vom Lohn     9.540,00 €          858,60 €
verbleibende Beträge          420,00-            37,80-

Einkünfte aus nichtselbständiger Arbeit        51.200,00 €
Sonderausgaben                                   2.050 €
zu versteuerndes Einkommen                      49.150 €
"""

TOWN_SENTENCES = """Stadt Leverkusen
Steuernummer: 230/5719/0812
Datum: 03.11.2026

Gewerbesteuer 2025
Auf der Grundlage des Steuermessbetrags von 1.050,00 € und eines Hebesatzes von 250 v. H. wird die
Gewerbesteuer für 2025 auf 2.625,00 € festgesetzt. Darauf sind Vorauszahlungen von 3.000,00 € angerechnet;
der Unterschied zu Ihren Gunsten von 375,00 € wird erstattet.
"""

TOWN_PIPES = """Stadt Markkleeberg
Steuernummer: 232/118/09911
Datum: 03.11.2026

Gewerbesteuerbescheid 2025
| Steuermessbetrag | Hebesatz | Gewerbesteuer |
|------------------|----------|---------------|
| 812,50 EUR       | 400 %    | 3.250,00 EUR  |
bisher gezahlt ............. 2.000,00
Abschlusszahlung ........... 1.250,00
"""


def test_a_column_table_with_whole_euros_and_trailing_minus_reads_without_learning():
    p = extract(Reading(COLUMNS, "text"))
    assert p.verified and p.tax_year == 2025
    assert p.fields["est"] == 912000 and p.fields["kist"] == 82080
    assert p.fields["rest_est"] == -42000 and p.fields["rest_kist"] == -3780
    assert p.fields["zve"] == 4915000 and p.fields["soli"] == 0  # a line the notice leaves out is zero
    assert set(p.method.values()) == {"layout"}


def test_a_town_in_sentences_and_a_town_in_pipes_read_without_learning():
    p = extract(Reading(TOWN_SENTENCES, "text"))
    assert p.verified and p.fields == {
        "messbetrag": 105000,
        "hebesatz": 25000,
        "gewst": 262500,
        "vz_gewst": 300000,
        "rest_gewst": -37500,
    }
    q = extract(Reading(TOWN_PIPES, "text"))
    assert q.verified and q.fields["hebesatz"] == 40000 and q.fields["rest_gewst"] == 125000


def test_the_layout_reader_proposes_and_the_arithmetic_still_decides():
    bad = extract(Reading(TOWN_PIPES.replace("1.250,00", "1.520,00"), "text"))
    assert not bad.verified and bad.does_not_compute  # every figure read, and the town's figures do not add up
