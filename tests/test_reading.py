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
