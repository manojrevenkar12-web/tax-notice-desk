# What the desk concludes about a notice

This is the contract for the tax-notice desk: what a careful tax adviser expects it to conclude about each
incoming notice, from the notice, the firm's records and the law alone. Held-out sets in `heldout/` are
written from this page; the code in `tnd/` implements it.

Amounts are in cents. Rounding is to whole cents unless a rule says otherwise. Dates are calendar dates in
Germany.

## What the desk knows

- The group's clients: firm, name, tax number (Steuernummer), the Land the client and the firm are in, and for
  businesses the municipality that levies their trade tax (Gewerbesteuer).
- The returns each firm filed: for each client, tax (`est`, `kst`, `ust`, `gewst_mess`) and year, the figures
  as filed.
- The trade-tax base notices (Gewerbesteuermessbescheide) already on file, with their date and Messbetrag.
- The group's register of municipal Hebesätze per municipality and year.
- For each client, earlier notices and what came of objections.
- For each incoming document: how it arrived (`portal` = made available for download, with the date it was made
  available and the date of the notification; `post` = paper mail, with the date stamped on arrival and the
  postmark; `municipal_digital`; `municipal_post`; `client_upload` = the client forwarded a copy), and the date
  it entered the desk.

## Kinds of notice

| kind | what it is |
|---|---|
| `est` | income tax assessment (Einkommensteuer, Solidaritätszuschlag, Kirchensteuer) |
| `kst` | corporate income tax assessment |
| `ust` | annual VAT assessment |
| `gewst_mess` | trade-tax base notice from the tax office (Gewerbesteuermessbescheid) |
| `gewst` | trade-tax notice from the municipality (Gewerbesteuerbescheid) |
| `vz_est` | income tax prepayment notice (Vorauszahlungsbescheid) |
| `request` | the office asks for documents by a date |
| `reminder` | the office reminds that a return is missing, by a date |
| `audit` | audit order (Prüfungsanordnung) |

An `est` notice that says the bases were estimated because no return was filed (Schätzung, AO § 162) is an
estimate.

## Who the notice is for

The notice is for the client whose tax number it carries. Tax numbers compare by their digits only
(`27/123/45678` and `2712345678` are the same). A notice whose tax number no client of the group has is
`misrouted`; the desk still computes its deadline from the notice, so whoever it is passed on to knows the
date. A second copy of a notice already on the desk (same client, kind, tax year and notice date) is a
`duplicate` of the first one.

## When a notice counts as received (Bekanntgabe)

The notice date is the date printed on it; for paper mail it is taken as the day it was posted.

| channel | posted or made available | counts as received |
|---|---|---|
| post | before 1 January 2025 | 3rd day after posting (AO § 122 Abs. 2 Nr. 1, old version) |
| post | from 1 January 2025 | 4th day after posting (AO § 122 Abs. 2 Nr. 1 as amended by PostModG) |
| portal | before 1 January 2025 | 3rd day after the notification was sent |
| portal | in 2025 | 4th day after the notification was sent |
| portal | from 1 January 2026 | 4th day after the notice was made available (AO § 122a Abs. 4 as amended) |

For post, if the day it counts as received is a Saturday, Sunday or holiday, it moves to the next working day
(AO § 108 Abs. 3; BFH III B 85/13). For the portal this is not settled, so the desk does **not** move it: it
keeps the earlier date and notes the later one. A municipal notice follows the same rules by its channel
(`municipal_post` like post, `municipal_digital` like portal).

A later postmark can rebut the presumption, but the desk keeps the date from the notice and only notes it.

For a forwarded copy (`client_upload`) the desk does not know how the original arrived: it computes the deadline
both ways (post and portal, with the notice date as the posting and availability date) and keeps the earlier one.

## Deadlines

- An assessment or other notice that can be challenged: the objection period is **one month** after it counts
  as received (AO § 355 Abs. 1); for a municipal notice that names Widerspruch, also one month (VwGO § 70). The
  period ends on the day of the following month with the same number; if that month has no such day, on its
  last day (BGB § 188). If the end falls on a Saturday, Sunday or holiday, it moves to the next working day
  (AO § 108 Abs. 3).
- If the notice has **no instructions on how to object** (no Rechtsbehelfsbelehrung), the period is one year
  (AO § 356 Abs. 2). When the desk read a scan and could not find the instructions, it cannot tell a missing
  passage from a badly read one, so it keeps one month (earlier) and notes the year. Paper mail (`post`,
  `municipal_post`) always reaches the desk as a scan.
- A `request` or `reminder` sets its own date: the deadline is that date, as written (not moved). A date
  before the notice's own date is an earlier deadline it recalls, not the one it sets.
- An `audit` order's deadline is the objection period; the audit start date is recorded separately.
- **Holidays**: a day counts as a holiday only if it is a statutory holiday both in the Land of the firm and in
  the Land of the authority (for a municipality, its own Land; for a tax office, the client's Land). This keeps
  the earlier date when Länder differ.

The deadline register never holds a date later than the real deadline. An earlier date is acceptable only where
this page says so.

## What is checked

**Assessments** (`est`, `kst`, `ust`, `gewst_mess`) are compared with the return the firm filed for that client,
tax and year. A figure differs when the difference exceeds 1 € (100 cents). A difference is **against the
client** when it raises income, tax or turnover, or lowers deductions, input VAT, credits or prepayments.

**Interest** (`est`, `kst`, `ust`): AO §§ 233a, 238, 239. The interest period starts 15 months after the end of
the tax year (1 April of the second following year) and ends on the day the notice counts as received. Interest
is 0.15 % per full month, on the remaining tax for that tax (assessed tax minus withholding and prepayments)
rounded down to a multiple of 50 €, rounded down to full euros; under 10 € no interest is set. A refund earns
interest the same way (negative). The notice's interest is wrong if it differs from this by more than 1 €.

**Municipal trade tax** (`gewst`):
- the Hebesatz must be the register's for that municipality and year;
- the Messbetrag must be the one on the latest base notice on file for that client and year;
- trade tax = Messbetrag × Hebesatz ÷ 100, to the cent; the notice is wrong if it differs by more than 1 €.

**The notice's own arithmetic** must hold for its values to be trusted (for example, remaining amount = tax −
withholding − prepayments). Values the desk cannot confirm this way are not used to close anything. A notice from the tax office whose
printed figures do not compute is `review` with the error `arithmetic`.

## What happens with the notice (action)

| action | when |
|---|---|
| `duplicate` | a second copy (see above) |
| `misrouted` | no client of the group has the tax number |
| `task` | `request`, `reminder`, `audit` |
| `objection_required` | an estimate (AO § 162); or the notice is wrong on its face: wrong Hebesatz, an outdated Messbetrag, trade tax that does not compute, or wrong interest |
| `objection_review` | an assessment deviates from the filed return against the client, and the remaining amounts to pay (or the Messbetrag, for `gewst_mess`) go up by at least 50 €; for `gewst_mess` any deviation against the client |
| `inform_client` | a prepayment notice; or deviations only in the client's favour, or against the client by less than 50 € |
| `close` | an assessment that matches the filed return and passes every check |
| `review` | the desk could not read or match the notice with certainty (including a tax number it could not read: that is not `misrouted`) |

Earlier rows win. `review` is never wrong in itself (it costs a person's time), but `close` on a notice that
needed action is the worst mistake the desk can make.

## Explanations

For each deviation and each error, the desk shows what changed, what the office says, the paragraphs of law that
apply in the version in force for that tax year (and says when its copy of a law is outdated for that year), the
firm's playbook entry, and what happened with the same issue for this client before.
