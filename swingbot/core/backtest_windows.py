"""The TRAIN/VALIDATION date windows — one definition, imported everywhere.

Authoritative prose lives in `docs/claude/backtest-methodology.md`; this
module is what the code actually reads, so the two can no longer drift.

Plan v8 Task V6 widened TRAIN to 1999-01-01 because every current parameter
had been fitted on a bull-heavy 4-year slice of the ~25 years of daily
history already sitting on disk. Task V46 then found that widening the doc
had changed nothing in practice: nine call sites each carried their own
`TRAIN = ("2020-01-01", "2023-12-31")`, so a bare `--train` still ran the
old window while the methodology claimed 25 years — the same
documented-but-not-wired shape the plan had just spent a task removing
elsewhere. Hence one constant rather than nine copies.

`LEGACY_TRAIN_2020` is not a leftover. Three scripts under `scripts/` (the
two exit/sizing parity checks and the quality-score audit) compare fresh
runs against numbers recorded under the old window; silently redefining
`--train` underneath them would change what their comparison MEANS while
the output kept looking valid. They import the legacy window explicitly
and say so in their own docstrings. New work should use `TRAIN`.

(Those scripts are named here only in the general — `tests/test_quality.py`
enforces that nothing under `swingbot/` so much as mentions the audit
script by name, to keep the package from ever growing a dependency on
`scripts/`. This module is imported BY them, never the other way round.)
"""

TRAIN = ("1999-01-01", "2023-12-31")
VALIDATION = ("2024-01-01", "2025-12-31")

# The pre-V6 window. Only for comparisons against results recorded under it.
LEGACY_TRAIN_2020 = ("2020-01-01", "2023-12-31")
