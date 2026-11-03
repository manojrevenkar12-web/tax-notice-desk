# Held-out set `blind-1`

**Author.** A Claude subagent (Claude Code) that had **not seen the desk's code**. It read exactly two files in
this repository: `heldout/WRITING_CASES.md` and `docs/NOTICE_RULES.md`. It did not open, list or search `tnd/`,
`tests/`, `config/`, `prompts/`, `reports/`, `fixtures/`, `data/`, `web/`, `corpus/` or any other folder under
`heldout/`, and it ran no project command. Python was used only outside the repository (a scratch directory) for
date arithmetic, holidays, money arithmetic, and to check that `cases.yaml` parses.

**Holidays used.** These come from the Python `holidays` package (0.108, `Germany(subdiv=…)`), checked against my own
knowledge. The dates that decide cases are: Allerheiligen 01.11.2024 (BY, BW, NW, RP, SL); Reformationstag 31.10.2025
and 31.10.2026 (BB, HB, HH, MV, NI, SN, ST, SH, TH); Buß- und Bettag 18.11.2026 (SN only); Heilige Drei Könige
06.01.2025 and 06.01.2027 (BY, BW, ST); Ostermontag 06.04.2026 and Pfingstmontag 25.05.2026 (nationwide);
Pfingstsonntag 24.05.2026 (BB, a Sunday anyway). Mariä Himmelfahrt (15 Aug, only some Bavarian municipalities) and
local holidays are not touched by any case.

**Conventions.** Amounts are in cents and `hebesatz` is percent × 100. Each `why` shows the arithmetic and the
calendar reasoning. Every notice keeps its own arithmetic consistent, except case-31, case-32 and case-55, which
are about arithmetic errors.

## Coverage

55 cases. By expected action: close 19, objection_review 10, objection_required 10, inform_client 9, task 3,
review 2, duplicate 1, misrouted 1.

| Topic | Cases |
|---|---|
| Kinds: est / kst / ust / gewst_mess / gewst / vz_est / request / reminder / audit | 29 / 07,17,45 / 06,08,13 / 34–37 / 22–33 / 15 / 50 / 51 / 52 |
| Channels: post / portal / municipal_post / municipal_digital / client_upload | 23 / 18 / 9 / 3 / 2 |
| Post before 2025 (3rd day), including a notice posted 30.12.2024 received in 2025 | 03, 10, 11 |
| Post from 2025 (4th day), weekend moves | 02, 04, 18, 20, 38, 39, 41, 42, 44, 46, 49, 52, 54, 55 … |
| Portal 2024 (notification + 3), 2025 (notification + 4, availability earlier), 2026 (availability + 4, notification later) | 05; 06, 29, 37, 47; 07, 08, 12–16, 25, 27, 35, 40, 43, 48 |
| Portal receipt on a weekend or holiday is not moved | 06, 07, 12, 13, 14, 15, 16, 25, 29, 40, 43, 47 |
| Boundary 2025/2026 (made available 29.12.2025, notification 30.12.2025) | 09 |
| Holiday in both Länder vs only one (1 Nov, Reformation Day, Buß- und Bettag, 6 Jan) | 10 vs 11; 23; 12 vs 13; 14 vs 15, 04 |
| Municipality's Land, not the client's, decides (client in BE, town in BB) | 23 |
| Month ends: 31 Jan → 28 Feb (a Saturday) → 2 Mar; 31 Mar → 30 Apr; one-month period ending on Easter Monday | 16; 17; 08 |
| Later postmark (noted, not used) | 18 |
| Forwarded copy with no original on file (both ways, earlier kept) | 19 |
| Forwarded copy of a notice already on the desk (`group: stadler-est-2025`) | 20 → 21 duplicate |
| No instructions on how to object: scan → one month; digital → one year | 24, 49; 25, 48 |
| Widerspruch at a town / Klage (NRW) / either (Bavaria) | 22, 23, 32; 26, 29, 31; 27, 28, 30, 33 |
| 50 € threshold: exactly +50.00 / +49.99 / mixed deviations netting +6 / kst +42 (+2.31 soli) | 38; 39; 40; 45 |
| Against the client: smaller refund, fewer prepayments credited, less input VAT, vGA, Hinzurechnung | 41; 10; 13; 17; 35 |
| In the client's favour only | 02, 08, 16, 37, 49 |
| Deviation of 1 € or less is not a deviation; a 1-cent Lohnsteuer difference still moves the remaining amount | 03; 39 |
| gewst_mess deviation absorbed by rounding to 100 € | 36 |
| Interest right: normal, exactly 10 €, under 10 € (none set), refund, 50 € rounding of the base decides | 05, 06, 07, 09, 40, 46; 02; 18; 49; 44 |
| Interest wrong: months miscounted, under-10 € interest charged, refund interest too low | 10; 42; 43 |
| Interest period not yet started (one day before) | 17 |
| Town: wrong Hebesatz / outdated Messbetrag / wrong tax / wrong remaining amount | 28, 29; 30; 31; 32 |
| Unusual town layouts and number formats | 22 (table), 23 (trailing minus `702,00-`), 25 (`EUR 1 234,56`, changed notice), 26 (rounded down to whole euros, still right), 27 (standard), 28 (prose letter; wrong Hebesatz), 29 (`1234,56`; wrong Hebesatz), 33 (combined with a prepayment notice) |
| Latest base notice on file: listed first and newer; newest on file belongs to another year | 25; 33 |
| Estimates (AO 162): no return / return crossed with the assessment | 46; 47 |
| Tax number without slashes; misrouted; unreadable tax number | 01; 53; 54 |
| A tax-office notice whose own arithmetic fails | 55 |

## Ambiguities found and how they were resolved

1. **Which date picks the portal regime at the 2025/2026 boundary.** The table's column is "posted or made available",
   so the availability date picks the row. A notice made available on 29.12.2025 with notification on 30.12.2025
   counts as received 03.01.2026 (notification + 4), not 02.01.2026 (case-09).
2. **Holidays and Bekanntgabe.** The "holiday in both Länder" rule is written under *Deadlines*. I also applied it
   to moving a post receipt day off a holiday (cases 04, 10, 11, 23), since this keeps the earlier date, as the page
   intends.
3. **Portal receipt on a weekend.** The receipt day is not moved, but the *end* of the one-month period still moves
   under AO 108(3) for every channel (cases 12–16, 25).
4. **What counts as "a scan"** when instructions are missing. I treated paper channels (`post`, `municipal_post`)
   as scans, which keep one month and note the year, and the office's own digital documents (`portal`,
   `municipal_digital`) as not scans, which get one year (cases 24, 49 vs 25, 48). No forwarded copy lacks
   instructions, so that question is not tested.
5. **How to compute the one-year period.** The same date one year later, moved off weekends and holidays (as for
   the month; BGB 188 / AO 108(3) by analogy).
6. **Municipal notices naming Klage instead of Widerspruch** (NRW, or Bavaria's choice). The page names only
   Widerspruch. I took one month (VwGO 74) as the deadline (cases 26, 29, 31).
7. **"The remaining amounts to pay go up by at least 50 €"**: the sum of rest_est, rest_soli and rest_kist, or
   rest_est alone? The threshold cases (38, 39) have no soli or church tax. Where soli or church tax exist (14, 45),
   both readings give the same action. "Up" is signed, so a smaller refund is an increase (case 41).
8. **A net change of mixed deviations.** "Against the client by less than 50 €" is read as the net change in the
   remaining amounts when one deviation is against the client and one in favour (case 40: +6 → inform_client).
9. **A difference of 1 € or less in one figure that still changes another.** In case 39 the Lohnsteuer differs by
   1 cent (not a deviation), but the remaining amount is taken as printed, so the increase is 49.99 €, not 50.00 €.
10. **gewst_mess: "any deviation against the client"** when rounding to 100 € absorbs it and the Messbetrag is
    unchanged. I followed the literal rule: objection_review (case 36). A careful clerk might call this
    inform_client. It is flagged here so a failure can be read either way.
11. **Wrong interest in the client's favour** (too little charged). The page says wrong interest →
    objection_required regardless of direction. I avoided the question: every interest error in this set is
    against the client (cases 10, 42, 43).
12. **Counting full months.** The end day is the receipt day itself. Interest cases avoid receipt on a month's last
    day, where inclusive vs exclusive would matter. The end is the moved day for post and the unmoved day for the
    portal. For a forwarded copy (case 19) the result is "no interest" either way.
13. **Refund interest rounding.** The base is the absolute amount rounded down to 50 € (toward zero), then the sign
    is applied (cases 43, 49).
14. **Interest base.** Only rest_est (rest_kst, rest_ust), never soli or church tax, matching the field list
    (`zinsen_est` only).
15. **Trade tax "= Messbetrag × Hebesatz ÷ 100"** is checked with the notice's *own* Messbetrag and Hebesatz. So a
    wrong Hebesatz or an outdated Messbetrag is reported as that error, not also as `arithmetic` (cases 28–30).
16. **A wrong remaining amount at a town** (rest ≠ tax − prepayments while the tax itself is right) is taken as
    "trade tax that does not compute" → objection_required with `arithmetic` (case 32).
17. **A tax-office notice whose own arithmetic fails.** No row covers it. "Values the desk cannot confirm … are
    not used to close anything" plus "could not read … with certainty" → review, with error `arithmetic`
    (case 55). objection_required would also be defensible.
18. **A correct gewst notice.** There is no filed return for gewst. I read "matches the filed return and passes
    every check" as "passes every check" for gewst → close.
19. **Deadline of a duplicate.** Case 21 expects the original's deadline. The case is built so that computing it
    as a forwarded copy gives the same date.
20. **Deadline of a misrouted notice.** No client's register is involved, so `deadline: null` (case 53). For an
    unreadable tax number (review), the deadline is still computed from the legible date and the authority's Land
    (case 54).
21. **"Latest" base notice.** Latest by date, for the notice's year, regardless of list order (cases 25, 33).
22. **Rounding of soli and church tax** is not defined. All figures are chosen so that 5.5 % comes out in whole
    cents. Church tax is shown at 8 % (BY) or 9 % but is not a rule of the page, so it is not checked.
23. **The kind of an estimate** stays `est` (the page has no separate kind); the action is objection_required even
    when a filed return exists (case 47).
24. **The register's years.** The register is stated for 2023–2025; case 29 (2023) uses the same value.
25. **Size of the set.** WRITING_CASES.md allows 40–60; the request asked for 45–55. The set has 55.
