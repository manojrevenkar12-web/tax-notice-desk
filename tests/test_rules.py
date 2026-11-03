"""Deadlines, interest, trade tax and decisions, by the rules in docs/NOTICE_RULES.md."""

import datetime as dt

from hypothesis import given, settings
from hypothesis import strategies as st

from tnd.rules import checks
from tnd.rules.deadlines import add_months, bekanntgabe, objection_deadline
from tnd.rules.decide import decide
from tnd.sim import calendar as simcal

D = dt.date


def test_post_three_days_until_2024_four_from_2025():
    assert bekanntgabe("post", D(2024, 11, 4), ("BE", "BE"))[0] == D(2024, 11, 7)
    assert bekanntgabe("post", D(2025, 11, 3), ("BE", "BE"))[0] == D(2025, 11, 7)


def test_post_presumed_day_on_a_weekend_moves_to_monday():
    # Thursday 26.11.2026 + 4 = Monday 30.11.; Wednesday 25.11. + 4 = Sunday 29.11. -> Monday 30.11.
    assert bekanntgabe("post", D(2026, 11, 25), ("BE", "BE"))[0] == D(2026, 11, 30)


def test_portal_counts_from_notification_in_2025_and_from_provision_from_2026():
    day, rules, _, _ = bekanntgabe("portal", D(2025, 6, 2), ("BE", "BE"), D(2025, 6, 2), D(2025, 6, 3))
    assert day == D(2025, 6, 7) and "PostModG" in rules[0]
    day, rules, _, _ = bekanntgabe("portal", D(2026, 6, 2), ("BE", "BE"), D(2026, 6, 2), D(2026, 6, 3))
    assert day == D(2026, 6, 6) and "BEG" in rules[0]


def test_portal_day_is_not_moved_but_the_later_date_is_noted():
    day, _, notes, later = bekanntgabe("portal", D(2026, 11, 26), ("BE", "BE"), D(2026, 11, 26), D(2026, 11, 26))
    assert day == D(2026, 11, 30) - dt.timedelta(days=0) or day.weekday() >= 5
    day, _, notes, later = bekanntgabe("portal", D(2026, 11, 24), ("BE", "BE"), D(2026, 11, 24), D(2026, 11, 24))
    assert day == D(2026, 11, 28)  # a Saturday, kept
    assert later == D(2026, 11, 30) and notes


def test_month_end_and_one_year_without_instructions():
    assert add_months(D(2027, 1, 31), 1) == D(2027, 2, 28)
    dl = objection_deadline("post", D(2026, 12, 23), ("BE", "BE"), True, "Einspruch")
    assert dl.bekanntgabe == D(2026, 12, 28) and dl.due == D(2027, 1, 28)
    dl = objection_deadline("post", D(2026, 12, 23), ("BE", "BE"), False, "Einspruch")
    assert dl.due == D(2027, 12, 28) and "AO § 356 Abs. 2" in dl.rules


def test_a_holiday_counts_only_where_both_firm_and_authority_have_it():
    # 1 November is a holiday in Bavaria, not in Berlin. Posted Wednesday 28.10.2026 -> 4th day Sunday 1.11. ->
    # Monday 2.11. either way; the objection period then ends Wednesday 2.12.
    assert objection_deadline("post", D(2026, 10, 28), ("BY", "BY"), True, None).due == D(2026, 12, 2)
    # Epiphany (6.1.) is a holiday in BY, not in BE. Posted Thursday 2.12.2027 -> received Monday 6.12. -> the period
    # ends on Thursday 6.1.2028, which moves to Friday only where both the firm and the authority have the holiday
    assert objection_deadline("post", D(2027, 12, 2), ("BY", "BY"), True, None).due == D(2028, 1, 7)
    assert objection_deadline("post", D(2027, 12, 2), ("BE", "BY"), True, None).due == D(2028, 1, 6)


def test_a_postmark_after_the_notice_date_is_noted_never_used():
    dl = objection_deadline("post", D(2026, 11, 2), ("NW", "NW"), True, None, postmark=D(2026, 11, 6))
    assert dl.due == D(2026, 12, 7) and dl.later_possible and dl.later_possible > dl.due


@settings(max_examples=300, deadline=None)
@given(st.dates(D(2024, 1, 1), D(2027, 6, 30)), st.sampled_from(["post", "portal"]),
       st.sampled_from([("BE", "BE"), ("BY", "BY"), ("BE", "BB"), ("NW", "BY"), ("SN", "SN")]), st.booleans())
def test_the_desk_and_the_simulators_independent_calendar_agree(posted, channel, lands, instructions):
    notified = posted + dt.timedelta(days=1)
    ours = objection_deadline(channel, posted, lands, instructions, None, posted, notified)
    bk = simcal.received(channel, posted, posted, notified, lands)
    assert ours.bekanntgabe == bk
    assert ours.due == simcal.deadline(bk, 1 if instructions else 12, lands)


def test_interest_full_months_fifty_euro_base_ten_euro_minimum():
    # tax year 2024: starts 1.4.2026; notice effective 10.11.2026 -> 7 full months (1.4.-31.10.)
    cents, calc = checks.interest("est", 2024, 1234567, D(2026, 11, 10))
    assert calc["months"] == 7 and calc["base"] == 1230000
    assert cents == int(12300 * 0.0015 * 7) * 100 == 12900
    assert checks.interest("est", 2024, 50000, D(2026, 6, 30))[0] == 0  # 500 € x 0.15 % x 2 = 1.50 € < 10 €
    assert checks.interest("est", 2025, 1234567, D(2026, 11, 10))[0] == 0  # period not started
    assert checks.interest("est", 2023, -800000, D(2026, 11, 10))[0] < 0  # refunds earn interest too


def test_municipal_checks_find_hebesatz_stale_messbetrag_and_arithmetic():
    f = {"messbetrag": 350000, "hebesatz": 43000, "gewst": 1505000, "vz_gewst": 0, "rest_gewst": 1505000}
    types = {x.type for x in checks.check_gewst(f, "Berlin", 2025, 336000)}
    assert types == {"wrong_hebesatz", "stale_messbetrag"}
    f = {"messbetrag": 350000, "hebesatz": 41000, "gewst": 1500000, "vz_gewst": 0, "rest_gewst": 1500000}
    assert {x.type for x in checks.check_gewst(f, "Berlin", 2025, 350000)} == {"arithmetic"}
    f["gewst"] = f["rest_gewst"] = 1435000
    assert checks.check_gewst(f, "Berlin", 2025, 350000) == []


def test_direction_of_a_deviation():
    filed = {"einkuenfte_nsa": 5000000, "sonderausgaben": 400000}
    got = checks.compare("est", {"einkuenfte_nsa": 5100000, "sonderausgaben": 300000}, filed)
    assert [(f.field, f.against) for f in got] == [("einkuenfte_nsa", True), ("sonderausgaben", True)]
    assert checks.compare("est", {"einkuenfte_nsa": 5000050, "sonderausgaben": 400000}, filed) == []  # within 1 €


def test_decisions():
    dev = checks.Finding("deviation", "einkuenfte_nsa", 1, 2, None, True, True)
    err = checks.Finding("wrong_hebesatz")
    assert decide("est", True, True, None, [], 0, False, True).action == "close"
    assert decide("est", True, True, None, [dev], 6000, False, True).action == "objection_review"
    assert decide("est", True, True, None, [dev], 4999, False, True).action == "inform_client"
    assert decide("gewst", True, True, None, [err], 0, False, True).action == "objection_required"
    assert decide("est", False, True, None, [], 0, False, True).action == "review"
    assert decide("est", True, False, None, [], 0, False, True).action == "misrouted"
    assert decide("est", True, True, "n1", [], 0, False, True).action == "duplicate"
    assert decide("request", False, True, None, [], 0, False, True).action == "task"
    assert decide("est", True, True, None, [], 0, True, False).action == "objection_required"
