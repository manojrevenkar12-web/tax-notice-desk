# Held-out set blind-2

Written by a Claude subagent that had **not seen the code** or any other held-out set. It read only two files:
`docs/NOTICE_RULES.md` and `heldout/WRITING_CASES.md`. Nothing in `tnd/`, `tests/`, `config/`, `prompts/`,
`reports/`, `fixtures/`, `data/`, `web/`, `corpus/` or `heldout/blind-1` was opened, and the desk was not run.

All 55 cases are in `cases.yaml`. People, firms, tax numbers and amounts are made up. Every date and amount was
computed with a small script (Python, `holidays` package for statutory holidays per Land, `dateutil` for
BGB § 188 month ends). Each case's `why` shows the arithmetic.

| action | cases |
|---|---|
| close | 22 |
| objection_review | 9 |
| inform_client | 8 |
| objection_required | 8 (3 interest, 1 wrong Hebesatz, 1 outdated Messbetrag, 1 town arithmetic, 2 estimates) |
| review | 3 (2 arithmetic, 1 unreadable tax number) |
| task | 3 (request, reminder, audit) |
| misrouted | 1 |
| duplicate | 1 (group `g-albers`, original first) |

## Ambiguities in NOTICE_RULES.md and the choice made

1. "The remaining amounts to pay go up by at least 50 €": all of them together, or each tax separately? Chose the total (case-08: ESt +47,00 € and KiSt +3,76 € = 50,76 € gives objection_review).
2. "Go up" compared with what? Chose the remaining amounts that follow from the filed return (tax − withholding − prepayments as filed).
3. Exactly 50,00 € counts ("at least"); 49,00 € does not (case-06, case-07).
4. A difference of exactly 1 € or less is not a deviation; a case uses 0,60 € (case-09).
5. Refund interest: the rule says round down to full euros "the same way"; AO § 239 Abs. 2 rounds to the taxpayer's advantage (up for refunds). Avoided: every refund-interest case comes out at whole euros.
6. Interest when 0 full months have passed (period started, notice received within April): no interest (case-01).
7. Interest is computed on the remaining income tax, corporate tax or VAT only, not on Soli or church tax ("the remaining tax for that tax").
8. Interest period end for post that was moved past a weekend: the moved date counts as received. Avoided where it would change the number of months (case-19).
9. Interest that is wrong in the client's favour, or interest the office left out: not tested; every wrong-interest case is against the client.
10. Holidays only when they hold in both Länder: applied to moving the received day for post as well as to the deadline end (case-11, case-12).
11. Portal rows are picked by the date the notice was made available (the column header says "posted or made available"). A notice made available in 2025 with its notification in 2026 is not tested.
12. A forwarded copy in 2025 has no notification date: the notice date would be used for both. Only forwarded copies from 2026 are used.
13. Whether a forwarded copy counts as a scan when its instructions are missing: not tested.
14. A duplicate's deadline: the copy's own client_upload computation. The case is chosen so it equals the original's (case-55).
15. A correct municipal trade-tax notice has no filed return to match, but the `close` row speaks of a matching assessment. Chose `close` when every check passes.
16. Municipal notices in NRW name only Klage (VwGO § 74), not Widerspruch. Taken as valid instructions with one month (case-40 to case-43). Bavarian notices offering either one also get one month.
17. A municipal notice without instructions: the rule names AO § 356; VwGO § 58 Abs. 2 also gives one year. Applied to municipal_digital (case-46).
18. Wrong Hebesatz or outdated Messbetrag where the notice's own product holds: only `wrong_hebesatz` / `stale_messbetrag`, not also `arithmetic` (case-39, case-42).
19. A town's trade tax that does not compute gets `objection_required` with error `arithmetic`; tax-office arithmetic errors get `review` (case-43 vs case-20, case-30).
20. "Earlier rows win" against "arithmetic is review": avoided. Arithmetic errors sit only in total lines whose parts all match the return.
21. "Latest base notice on file" is read as latest by notice date (case-42).
22. Holiday Land for a misrouted or unreadable notice (no known client): the tax office's own Land. The dates chosen do not depend on it.
23. Prepayment notices can be challenged, so they get the one-month deadline (case-48, case-49).
24. An audit order's start date has no field in `expect`; it is given in `why` only (case-52).
25. Payment dates printed on notices ("fällig am", "bitte zahlen Sie bis") are not objection deadlines; some notices print them as a distraction (case-01, case-07, case-47).
26. A request date on a Sunday is not moved ("as written"; case-50).
27. Regional holidays that hold only in parts of a Land (Mariä Himmelfahrt, Augsburger Friedensfest, Fronleichnam in parts of SN/TH) are avoided. Berlin's one-off holiday on 08.05.2025 is used as statutory (case-01).
28. Simplified relations in WRITING_CASES.md give no formula for income tax, Soli or church tax. The notices use the § 32a EStG tariff for the year, the Soli exemption threshold, and 8 %/9 % church tax. The desk only has to compare them with the return.
