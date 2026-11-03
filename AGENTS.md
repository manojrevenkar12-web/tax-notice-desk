# Working on tax-notice-desk

## Fast feedback

- `pytest -q` (about 10 seconds; the desk tests need PostgreSQL at `TND_TEST_OWNER_URL`, default
  `postgresql://postgres@127.0.0.1:5544/tnd_test`; builds `data/` on first run).
- `ruff check tnd tests && ruff format --check tnd tests && mypy tnd`.
- `tnd eval dev` for real numbers; `tnd release` applies `config/gates.yaml` on test.
- OCR and model answers are cached in `fixtures/ocr_cache/` and `fixtures/llm_cache/` (committed) by the hash of
  the input. `TND_LLM=off` turns a model cache miss into an error; CI runs that way and reproduces the reports.

## Invariants (each has a test)

1. **The desk never sees the truth.** `tnd/` outside `tnd/sim` and `tnd/evals` imports neither and never names
   the answer key (`tests/test_isolation.py`).
2. **A deadline is never late.** Where the law is unsettled the earlier date is kept; the desk's deadline code and
   the simulator's independent calendar must agree (`tests/test_rules.py`, property test). Release gate:
   `late_deadlines = 0`.
3. **Untrusted values never close a notice.** A value is trusted only if it came in a data file, or the notice's
   own arithmetic holds with it. Gate: `verified_wrong_values = 0`, `closed_but_needed_action = 0`.
4. **Models read, rules decide.** The model may read a scan the rules could not confirm (its values are used
   only if the arithmetic then holds) and may word a draft (used only if the verifier passes). Actions, deadlines
   and checks are code over `config/rules.yaml`.
5. **Four eyes on deadlines; released drafts are final.** Enforced by constraints and triggers
   (`tests/test_desk.py`).
6. **Tenancy in PostgreSQL.** Forced row-level security per firm; the mailroom routes documents through a
   function; group operations reads aggregates only; the runtime role cannot delete or change the schema.
7. **Settings live in `config/`.** Rules carry their sources. A change in behaviour bumps the version there.

## Held-out rule

`heldout/<set>/` holds cases written by someone who has not read the code. Never change the desk to pass a set
before its first run is recorded in `reports/heldout/<set>/first_run.json`, which is never rewritten. If you study
a set's failures, write `regression` to `heldout/<set>/STATUS` and have someone who has not seen the code write a
new set from `heldout/WRITING_CASES.md` only.
