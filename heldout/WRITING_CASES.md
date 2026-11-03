# Writing a held-out case set

A held-out set tests the desk on notices written by someone who has **not read the code**. Read only
`docs/NOTICE_RULES.md` and this file. Do not open `tnd/`, `tests/`, `config/` (except the register below, which
is reproduced here), `prompts/`, `reports/`, `fixtures/`, `data/`, `web/` or other sets in `heldout/`.

Write `heldout/<set>/cases.yaml`, a list of self-contained cases. Invent people, firms, tax numbers and amounts.
Write each notice's text the way real German notices read, and vary the wording, layout and number formats
(`1.234,56 €`, `EUR 1 234,56`, `1234,56`, trailing minus `12,00-`), especially for municipal notices: each town
writes its own. Compute every expected value from NOTICE_RULES.md alone and show the arithmetic in `why`.

```yaml
- id: case-01
  firm: { land: BE }                       # the firm's Land
  client: { name: "Lena Brandt", steuernummer: "27/615/02233", land: BE, kind: person }   # kind: person | trader | company
  filed:                                   # optional: the return the firm filed
    kind: est
    year: 2024
    fields: { einkuenfte_nsa: 5210000, ... }
  onfile:                                  # optional: Messbescheide on file (for gewst cases)
    - { year: 2024, date: "2025-08-14", messbetrag: 304500 }
  history: []                              # optional: [{year, kind, text, objection: true, outcome: abgeholfen}]
  document:
    channel: post                          # post | portal | municipal_post | municipal_digital | client_upload
    posted: "2026-11-27"                   # the date printed on the notice
    provided_at: null                      # portal: made available (YYYY-MM-DD)
    notified_at: null                      # portal: notification sent
    postmark: null                         # post: date on the envelope, if different
    received_at: "2026-12-01"
    text: |
      Finanzamt Charlottenburg
      ...
  expect:
    kind: est
    action: objection_review
    deadline: "2027-01-04"
    errors: []                             # any of: wrong_hebesatz, stale_messbetrag, arithmetic, interest
    fields: { zve: 5012300 }               # optional: values the desk must read
  why: "…"
```

The text must contain what a real notice contains for the desk to work with: the authority on the first line,
the tax number (`Steuernummer: …`), the date (`Datum: TT.MM.JJJJ`), a title naming the tax and year, the figures
with their labels, explanations if the office deviates, and the instructions on how to object (or not, for a
case about missing instructions). Field names for `filed` and `expect.fields`:

- `est`: `einkuenfte_nsa`, `einkuenfte_gewerbe`, `einkuenfte_vuv`, `summe_einkuenfte`, `sonderausgaben`, `agb`,
  `zve`, `est`, `soli`, `kist`, `lst_est`, `vz_est`, `rest_est`, `lst_soli`, `rest_soli`, `lst_kist`, `rest_kist`,
  `zinsen_est` (interest, if any)
- `kst`: `einkommen`, `kst`, `soli`, `vz_kst`, `rest_kst`, `zinsen_kst`
- `ust`: `umsatz_19`, `umsatz_7`, `ust`, `vorsteuer`, `zahllast`, `vz_ust`, `rest_ust`, `zinsen_ust`
- `gewst_mess`: `gewinn`, `hinzurechnungen`, `kuerzungen`, `gewerbeertrag`, `freibetrag`, `messbetrag`
- `gewst`: `messbetrag`, `hebesatz` (percent × 100, so 410 % is 41000), `gewst`, `vz_gewst`, `rest_gewst`
- `vz_est`: `vz_quartal`

Simplified relations the notices use (keep them consistent): `summe_einkuenfte = nsa + gewerbe + vuv`;
`zve = summe − sonderausgaben − agb`, rounded down to whole euros; `rest_X = X − lst_X − vz_X`;
`kst = 15 % of einkommen`, `soli = 5.5 % of kst`; `ust = 19 % of umsatz_19 + 7 % of umsatz_7`,
`zahllast = ust − vorsteuer`, `rest_ust = zahllast − vz_ust`; Gewerbeertrag = gewinn + hinzurechnungen −
kuerzungen rounded down to 100 €, freibetrag 24.500 € for persons and traders (0 for companies), messbetrag =
3.5 % of (Gewerbeertrag − freibetrag).

The group's register of Hebesätze (the same for 2023, 2024 and 2025), with each municipality's Land:
Berlin 410 (BE), Landeshauptstadt München 490 (BY), Gemeinde Grünwald 240 (BY), Stadt Garching b. München 280
(BY), Stadt Köln 475 (NW), Stadt Monheim am Rhein 250 (NW), Stadt Leverkusen 250 (NW), Bundesstadt Bonn 490 (NW),
Stadt Leipzig 460 (SN), Stadt Markkleeberg 400 (SN), Landeshauptstadt Potsdam 450 (BB), Gemeinde Schönefeld 240
(BB). A municipal notice must name one of them exactly in its first line.

Write 40 to 60 cases. Cover: every kind; every channel; the 2024/2025/2026 changes to when a notice counts as
received; weekends and holidays that differ between Länder (for example 1 November, Buß- und Bettag, 6 January,
Reformation Day), month ends (31 January → 28/29 February), a notice without instructions on how to object,
Widerspruch at a town; deviations against and in favour of the client, at and around 50 €; interest right and
wrong (including refunds and the 10 € minimum); towns with a wrong Hebesatz, an outdated Messbetrag, wrong
arithmetic, and towns that are right but write their notice in an unusual way; estimates; requests, reminders and
audit orders; a misrouted notice (a tax number no client has); a forwarded copy of a notice in the same set
(give both cases the same `group:` value, the original first). Where NOTICE_RULES.md leaves a case open, say so
in `why` and choose what a careful reader of it would expect.

Also write `heldout/<set>/README.md` (who wrote it, from what, every ambiguity you found) and
`heldout/<set>/STATUS` containing `blind`.

## The rule

A set is run once; its first run is kept in `reports/heldout/<set>/first_run.json` and never rewritten. Nobody
changes the desk to pass a set before that. Studying its failures makes it a `regression` set, and a new blind set
is written by someone else from this file only.
