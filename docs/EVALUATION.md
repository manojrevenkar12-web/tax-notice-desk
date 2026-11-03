# How the desk is evaluated, and what has been looked at

Every number in the README comes from a report in `reports/`. CI regenerates the mail, replays OCR and model
answers from `fixtures/`, re-runs the release gate, and fails if `reports/release.json` changes. This page says
where each number comes from and which data has been studied, in order.

## The data

The group, its clients and its mail are synthetic. `tnd/sim` generates them from `config/world.yaml`:

- **Firms and clients.** Four firms in Berlin, Munich, Cologne and Leipzig, with 96 clients: employees,
  traders and GmbHs, some with businesses in other towns. Each client has the returns the firm filed for
  2023 to 2025.
- **Notices.** Income tax, corporate tax, VAT, trade-tax base notices, municipal trade-tax notices, prepayment
  notices, requests, reminders, audit orders and estimates. They arrive in four ways:
  - electronically, with a data file (as DIVA does);
  - as paper mail, scanned: printed to PDF, rasterised, rotated, blurred and speckled;
  - as municipal PDFs, some with embedded XML;
  - as copies the client forwards.

  The 12 towns each have their own layout, labels, number format and structure (lines, a table, or prose).
- **Answer key.** The truth is planted:
  - deviations from the return, with or without the office's reason;
  - wrong Hebesätze, outdated Messbeträge and arithmetic errors at towns;
  - wrong interest, missing instructions on how to object, late postmarks;
  - tax numbers nobody knows, and duplicate copies.

  It also holds the deadline and the action a careful adviser would take (`docs/NOTICE_RULES.md`).

| Split | Mail from | Notices | Used for |
|---|---|---|---|
| dev | 26.10.–27.11.2026 | 238 | development and error analysis |
| test | 30.11.2026–08.01.2027 | 230 | the release gates (`config/gates.yaml`) |
| heldout | 11.01.–12.02.2027 | 237 | run once at the end |

In January 2027 electronic delivery becomes the default (AO § 122a), so the held-out month is mostly
electronic and the test month mostly paper. The answer key's deadlines and interest are computed by
`tnd/sim/calendar.py`, separately from the desk's `tnd/rules`. A property test runs 300 random dates and
channels through both and requires them to agree.

The two implementations disagreed twice during development, and the simulator was wrong both times:

- its interest period started a year early;
- at the turn of 2024/2025 it chose the version of § 122a by the notification date instead of the date the
  notice was made available.

The truth files are read only by `tnd/evals`. `tests/test_isolation.py` checks that no shipping code imports
the simulator or the evaluation, or names the answer key.

## The gates

Zero means zero:

- no deadline later than the real one;
- no notice closed that needed action;
- no wrong notice treated as fine;
- no value the desk trusted that was wrong;
- no notice sent to the wrong client.

On top of those, floors apply to deadline exactness (0.97), action accuracy (0.85), kind accuracy (0.97), error
recall and precision (0.9) and retrieval recall (0.85), and a ceiling to the share of notices a person must read
first (0.25).

## What has been studied, in order

1. **dev**: everything was developed on it.
2. **test, first run** (`reports/first-runs/test.md`): did **not** ship. A refund's interest was read by the
   model with the wrong sign. That value passed the checks of the time, so it counted as a trusted wrong value
   and as a false interest error. The fix: interest on a refund must be negative, or the value is not trusted
   (`config/extraction.yaml` version 3). After it, test ships. **The test numbers in the README come from after
   this first run was studied.**
3. **held-out month, first and only run** (`reports/first-runs/heldout-month.md`): passes every gate. Looking at
   the confusion afterwards turned up two things, and neither was changed:
   - two identical prepayment notices on the same day were treated as one notice and its copy (a generator
     artefact; arguably the right call);
   - a forwarded copy of an audit order was not recognised as a copy, because the scan lost its tax year.
4. **blind-1, first and only blind run** (`reports/heldout/blind-1/first_run.json`): 55 cases by an author who
   saw only `docs/NOTICE_RULES.md` and `heldout/WRITING_CASES.md`. **7 of 55 passed; 2 deadlines were late.**
   - *Layouts.* 44 cases had values the desk could not read: the label reader knew the simulator's wording, and
     the author wrote what real offices print (taxes side by side in a column table, `ab Steuerabzug vom Lohn`,
     `42.740 €`, towns in sentences, pipe tables, `EUR 1 596,00`, `702,00-`). They all went to a person, so
     nothing was closed wrongly and no wrong value was trusted, but the desk saved nobody any work.
   - *Two late deadlines.* Two paper notices had no instructions on how to object. The desk assumed one month
     only when it had read a scan with OCR; these arrived as text, so it gave them a year.
   - *Smaller ones.* An estimate classified as a reminder (it said "trotz Erinnerung"); an audit order
     classified as a trade-tax base notice (its scope named the Gewerbesteuermessbetrag); a reminder whose
     deadline was taken from the original filing date it recalled; town years written as
     `Gewerbesteuerbescheid 2024`; interest on a refund printed without its minus sign.

   What changed, all general: the layout reader (`tnd/intake/layout.py`, `config/extraction.yaml: layout`),
   which reads any layout by what each amount is labelled with and lets the arithmetic choose among candidates;
   paper mail treated as a scan for the instructions rule; the classification and date fixes; and four
   clarifications to the contract (paper is a scan; a misrouted notice keeps its computed deadline; a reminder's
   earlier date is not its deadline; an office notice that does not compute is `review` with `arithmetic`).
   After that, blind-1 passes 54 of 55 (53 after blind-2's changes: a town notice whose remaining amount does not
   follow is now `review`, not `objection_required`); the other remaining case expects no deadline for a
   misrouted notice, which the contract now settles the other way. **blind-1 has been studied, so it is now a regression set** (`STATUS`),
   and its first run stays as it was.

   The same changes on the sim splits: test still ships with the same quality, with 14 model calls instead of
   44; dev is unchanged; without the model, test needs a person for 7.0 % of notices instead of 15.7 %.
5. **blind-2, first and only blind run** (`reports/heldout/blind-2/first_run.json`): 55 cases by a new author
   who saw only the clarified contract and the writing guide. **12 of 55 passed; 0 deadlines late; 0 notices
   closed that needed action.**
   - *Layouts again.* 40 misses went to a person because values were not read: a minus printed to mean
     "deducted" (`- 11.442,00 €`, `6.850-`), whole euros without a currency sign (`99.650`, `46 130`), `Euro`,
     `vom Hundert`, `KiSt`, sentences, tables with "declared" and "assessed" columns side by side.
   - *One false objection.* A correct town notice was marked `objection_required` with an arithmetic error: the
     rule added after blind-1 (a town notice whose remaining amount does not follow is an objection) fired on a
     misread prepayment. The rule is removed; such a notice is now `review`.
   - *One wrong value shown.* A prepayment notice printed the new quarterly amounts in a one-column table and
     last year's amount in a sentence; the desk took the sentence. Prepayment notices have no arithmetic that
     could have caught it; the due-date rows are now read first.
   - *Decision bugs found while studying it.* Prepayments or withholding that the office credited differently
     did not count as a deviation (they were not "primary" figures), and the 50 € test returned 0 when a notice
     or a return left out a line that is zero. Both are fixed for every kind.

   After the changes blind-2 passes 33 of 55, and every remaining miss is a notice sent to a person. Test still
   ships with the same numbers and dev is unchanged. **blind-2 has been studied, so it is now a regression set.**
   A third blind set has not been written yet.

## The model's part, measured

The same test month with the model switched off for reading (`reports/evals/test-no-model.json`):

| | with the model reading unclear scans | rules and OCR only |
|---|---|---|
| Notices a person must read first | 3.0 % | 7.0 % |
| Matching notices recorded without a person | 96.4 % | 86.9 % |
| Action accuracy | 97.0 % | 93.0 % |
| Trusted values that were wrong | 0 | 0 |
| Deadlines later than the real one | 0 | 0 |

The model reads only scans that the rules and two OCR passes could not confirm. Its values are used only if the
notice's own arithmetic then holds. On test it was asked 14 times, for $0.011 (44 times before the layout reader).

The feedback loop shows when the model is off. Without it, the first notice from a town needed a person 42 % of
the time; later notices from the same town needed one 24 % of the time, because each correction taught the desk
that town's labels.

## Limits

- **The data is synthetic.** It was built to be hard in documented ways: town layouts, OCR damage, the
  2025/2026 rule changes, conflicting holidays. Still, a real firm's mail is messier. The scans are cleaner than
  a fax and the layouts fewer than 600.
- **The data file is not ELSTER's.** The structured file with electronic notices uses an illustrative schema.
- **The law texts are from 2021.** They come from the public bundestag/gesetze repository, consolidated in
  2021. Later changes that matter for deadlines and interest are added with their text and source; others are
  only marked (`corpus/amendments.yaml`), and the desk says when its copy is outdated.
- **The Hebesätze are illustrative.** They are not a maintained register.
- **No real integrations.** Nothing was tested against a live DATEV, DIVA or ELSTER connection, a real
  mailroom, or a real advisor.
