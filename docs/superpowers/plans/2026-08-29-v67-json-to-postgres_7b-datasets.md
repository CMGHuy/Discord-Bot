# v67 — Part 7: Datasets and workflow (tasks P7-07…P7-12)

> Continuation of `2026-08-29-v67-json-to-postgres_7a-data-access.md`. Part of
> `2026-08-29-v67-json-to-postgres_0-index.md`. **Read the index's Global
> Constraints and the `_7a` file before starting any task here** — the profile
> table, the Alembic revision-id table and the exit criteria live there and are
> not repeated.

**Spec:** `docs/superpowers/specs/2026-08-29-v67-json-to-postgres-design.md`

**What this half is for.** `_7a` restored the access that the migration would
otherwise have taken away. This half is the part that makes the result better
than what it replaced: trade history as a DataFrame in one import, from any
profile, instead of `json.load` plus a hand-rolled normalisation every script
wrote for itself.

**What it deliberately does not touch.** `market_data/` and
`data/backtest_cache/*.csv` stay as files, per the spec — they are large,
regenerable, and read by pandas directly. Backtests keep reading them exactly
as they do today. The one thing that changes is where the *universe* those
fetches iterate comes from (P7-10).

---

### Task P7-07: DataFrame accessors

One import, one function, a DataFrame. This is what replaces every script's
private `json.load(...)` plus normalisation.

**Files:**
- Create: `swingbot/core/db/datasets.py`
- Test: `tests/db/test_datasets.py`

**Interfaces:**
- Consumes: `profiles.engine_for` (P7-04), the Part 2/5 tables.
- Produces, each taking `profile: str | None = None`:
  - `closed_trades_frame(since=None, strategy=None) -> pd.DataFrame`
  - `open_trades_frame() -> pd.DataFrame`
  - `plans_frame(status=None) -> pd.DataFrame`
  - `journal_frame() -> pd.DataFrame`
  - `telemetry_frame(days=90) -> pd.DataFrame`
  - `FRAMES: dict[str, Callable]` — name → accessor, for the export CLI

**The doc column is expanded into real columns.** A DataFrame with a `doc`
column of dicts is a DataFrame you cannot filter, group or plot — every caller
would `pd.json_normalize` it and they would each do it slightly differently.
The accessors do it once, so `df.r_multiple` works whether `r_multiple` is a
promoted column or a doc key. **That is the whole point of the codec surfacing
here rather than in each caller.**

- [ ] **Step 1: Write the failing tests**

Create `tests/db/test_datasets.py`:

```python
"""Trade history as a DataFrame, from any profile."""
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.db import datasets, profiles


@pytest.fixture
def seeded(monkeypatch, db_engine, db_committed):
    monkeypatch.setattr(config, "DATABASE_URL",
                        db_engine.url.render_as_string(hide_password=False))
    profiles.reset_engines()
    from swingbot.core.db.repositories.trades import TradeRepository
    repo = TradeRepository()
    with db_committed.begin():
        for i in range(6):
            win = i % 2 == 0
            repo.insert(dict(
                trade_id=f"D{i}", ticker=["AAPL", "MSFT"][i % 2],
                strategy=["RSI", "MACD"][i % 2], horizon="2w",
                direction="bullish",
                status="win" if win else "loss",
                opened_at=f"2026-01-{i + 1:02d}T15:00:00+00:00",
                closed_at=f"2026-02-{i + 1:02d}T15:00:00+00:00",
                entry=100.0 + i, stop_loss=95.0 + i,
                r_multiple=2.0 if win else -1.0,
                confidence_level=(i % 5) + 1,
                notes={"why": "breakout"}), conn=db_committed)
        repo.insert(dict(
            trade_id="OPEN", ticker="NVDA", strategy="RSI", horizon="2w",
            direction="bullish", status="open",
            opened_at="2026-03-01T15:00:00+00:00"), conn=db_committed)
    yield
    profiles.reset_engines()


def test_closed_trades_returns_a_dataframe(seeded):
    df = datasets.closed_trades_frame()
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 6


def test_open_trades_are_excluded_from_closed(seeded):
    assert "OPEN" not in set(datasets.closed_trades_frame()["trade_id"])


def test_doc_fields_become_real_columns(seeded):
    """A `doc` column of dicts is a DataFrame you cannot group or plot."""
    df = datasets.closed_trades_frame()
    assert "r_multiple" in df.columns
    assert "confidence_level" in df.columns
    assert "doc" not in df.columns


def test_promoted_and_doc_columns_are_indistinguishable_to_the_caller(seeded):
    df = datasets.closed_trades_frame()
    assert df["ticker"].notna().all()        # promoted
    assert df["r_multiple"].notna().all()    # doc


def test_numeric_columns_are_numeric_not_object(seeded):
    """NUMERIC comes back as Decimal, which breaks .mean() and every plot."""
    df = datasets.closed_trades_frame()
    assert pd.api.types.is_numeric_dtype(df["entry"])
    assert pd.api.types.is_numeric_dtype(df["r_multiple"])


def test_timestamps_are_datetimes(seeded):
    df = datasets.closed_trades_frame()
    assert pd.api.types.is_datetime64_any_dtype(df["closed_at"])


def test_a_nested_dict_field_survives_as_an_object_column(seeded):
    df = datasets.closed_trades_frame()
    assert df["notes"].iloc[0] == {"why": "breakout"}


def test_filter_by_strategy(seeded):
    df = datasets.closed_trades_frame(strategy="RSI")
    assert set(df["strategy"]) == {"RSI"}


def test_filter_by_since(seeded):
    df = datasets.closed_trades_frame(since="2026-02-04")
    assert len(df) < 6 and len(df) > 0


def test_an_empty_result_still_has_columns(seeded):
    """A frame with no rows and no columns breaks every caller that indexes
    one. This is the difference between 'no trades' and 'a crash'."""
    df = datasets.closed_trades_frame(strategy="DOES-NOT-EXIST")
    assert len(df) == 0
    assert "trade_id" in df.columns
    assert "r_multiple" in df.columns


def test_closed_trades_are_newest_first(seeded):
    df = datasets.closed_trades_frame()
    assert df["closed_at"].is_monotonic_decreasing


def test_every_named_frame_is_callable_and_returns_a_frame(seeded):
    for name, fn in datasets.FRAMES.items():
        assert isinstance(fn(), pd.DataFrame), name


def test_an_unknown_profile_raises(seeded):
    with pytest.raises(ValueError, match="not a known profile"):
        datasets.closed_trades_frame(profile="production")
```

`test_an_empty_result_still_has_columns` is the one that saves an afternoon:
`pd.DataFrame([])` has no columns, and every downstream `df["r_multiple"]`
raises `KeyError` rather than returning nothing.

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/db/test_datasets.py -q
```

Expected: `ModuleNotFoundError: No module named 'swingbot.core.db.datasets'`.

- [ ] **Step 3: Write it**

Create `swingbot/core/db/datasets.py`:

```python
"""Trading data as pandas DataFrames, from any database profile.

    from swingbot.core.db import datasets
    df = datasets.closed_trades_frame(profile="snapshot")
    df.groupby("strategy")["r_multiple"].mean()

This is the convenience the migration buys. Before it, every analysis script
did json.load() plus its own normalisation, and they each did it slightly
differently -- which is how two scripts come to disagree about the same number.

Three things every accessor guarantees, because getting any of them wrong
silently produces a frame that looks fine and computes wrong:

  * doc fields are expanded into real columns, so a caller cannot tell
    (and does not need to) whether a field is promoted or lives in doc;
  * NUMERIC columns are floats, not Decimals -- Decimal breaks .mean(),
    .plot() and every statistical function in the stack;
  * an empty result still carries its columns, so `df["r_multiple"]` on a
    no-rows frame returns an empty Series rather than raising KeyError.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

import pandas as pd
import sqlalchemy as sa

from swingbot.core.db import profiles
from swingbot.core.db.codec import merge_doc
from swingbot.core.db.schema import (journal_entries, plans, promoted_for,
                                     scan_telemetry, trades)

#: Columns to coerce to datetime, per table. Anything else is left alone.
_DATETIME_COLUMNS = {
    "trades": ("opened_at", "closed_at"),
    "plans": ("created_at",),
    "journal_entries": ("closed_at", "created_at"),
    "scan_telemetry": ("at",),
}


def _to_frame(rows: list[dict], table_name: str,
              extra_columns: tuple[str, ...] = ()) -> pd.DataFrame:
    """Flat records -> a typed DataFrame that is safe to index into."""
    # Columns are derived from the schema, not from the rows, so an empty
    # result keeps its shape. `extra_columns` names doc fields worth
    # guaranteeing even when no row happens to carry one.
    base = list(promoted_for(table_name)) + list(extra_columns)
    if not rows:
        return pd.DataFrame({c: pd.Series(dtype="object") for c in base})

    df = pd.DataFrame(rows)
    for column in base:
        if column not in df.columns:
            df[column] = pd.NA

    for column in df.columns:
        # Decimal from a NUMERIC column breaks .mean() and every plot.
        if df[column].map(lambda v: isinstance(v, Decimal)).any():
            df[column] = pd.to_numeric(df[column], errors="coerce")

    for column in _DATETIME_COLUMNS.get(table_name, ()):
        if column in df.columns:
            df[column] = pd.to_datetime(df[column], utc=True, errors="coerce")

    return df


def _select(table, where=None, order_by=None, limit=None,
            profile: str | None = None) -> list[dict]:
    stmt = sa.select(table)
    if where is not None:
        stmt = stmt.where(where)
    if order_by is not None:
        stmt = stmt.order_by(order_by)
    if limit is not None:
        stmt = stmt.limit(limit)
    engine = profiles.engine_for(profile)
    with engine.connect() as conn:
        rows = conn.execute(stmt).all()
    promoted = promoted_for(table.name)
    return [merge_doc(row._mapping, promoted) for row in rows]


# -- accessors -------------------------------------------------------------

_TRADE_EXTRAS = ("r_multiple", "realized_pnl_amount", "exit_price",
                 "confidence_level", "plan_id", "exit_reason")


def closed_trades_frame(*, since: str | None = None,
                        strategy: str | None = None,
                        profile: str | None = None) -> pd.DataFrame:
    """Every settled trade, newest first."""
    clauses = [trades.c.status != "open"]
    if since is not None:
        clauses.append(trades.c.closed_at >= since)
    if strategy is not None:
        clauses.append(trades.c.strategy == strategy)
    rows = _select(trades, where=sa.and_(*clauses),
                   order_by=trades.c.closed_at.desc(), profile=profile)
    return _to_frame(rows, "trades", _TRADE_EXTRAS)


def open_trades_frame(*, profile: str | None = None) -> pd.DataFrame:
    rows = _select(trades, where=trades.c.status == "open",
                   order_by=trades.c.opened_at.desc(), profile=profile)
    return _to_frame(rows, "trades", _TRADE_EXTRAS)


def plans_frame(*, status: str | None = None,
                profile: str | None = None) -> pd.DataFrame:
    where = plans.c.status == status if status is not None else None
    rows = _select(plans, where=where, order_by=plans.c.created_at.desc(),
                   profile=profile)
    return _to_frame(rows, "plans", ("entry", "stop_loss", "take_profit"))


def journal_frame(*, profile: str | None = None) -> pd.DataFrame:
    rows = _select(journal_entries,
                   order_by=journal_entries.c.closed_at.desc(), profile=profile)
    return _to_frame(rows, "journal_entries", ("tags", "note", "lesson"))


def telemetry_frame(*, days: int = 90,
                    profile: str | None = None) -> pd.DataFrame:
    import datetime as dt
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days))
    rows = _select(scan_telemetry, where=scan_telemetry.c.at >= cutoff,
                   order_by=scan_telemetry.c.at.asc(), profile=profile)
    return _to_frame(rows, "scan_telemetry",
                     ("tickers", "errors", "signals", "alerts", "open_heat"))


#: name -> accessor, for scripts/db/export_dataset.py and for anyone who wants
#: to iterate every dataset without importing each one by hand.
FRAMES: dict[str, Callable[..., pd.DataFrame]] = {
    "closed_trades": closed_trades_frame,
    "open_trades": open_trades_frame,
    "plans": plans_frame,
    "journal": journal_frame,
    "telemetry": telemetry_frame,
}
```

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/db/test_datasets.py
```

Expected: `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/db/datasets.py tests/db/test_datasets.py
git commit -m "feat(v67): add DataFrame accessors for trading data"
```

---

### Task P7-08: Dataset export

For the analysis that happens outside this repo — a notebook, a spreadsheet,
a model someone is training elsewhere.

**Files:**
- Create: `scripts/db/export_dataset.py`
- Modify: `Makefile`
- Test: `tests/scripts/test_export_dataset.py`

**Interfaces:**
- Consumes: `datasets.FRAMES` (P7-07).
- Produces:

```bash
python scripts/db/export_dataset.py closed_trades --profile snapshot -o trades.csv
python scripts/db/export_dataset.py --all --profile snapshot -o exports/datasets/
```

**Output goes to `exports/`, which the spec keeps as files** and which is
already gitignored. An export written into `data/` would sit next to the
database's own backups and be mistaken for one.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_export_dataset.py`:

```python
"""Dataset export for analysis outside this repo."""
import pathlib

import pandas as pd
import pytest

from swingbot import config
from scripts.db.export_dataset import main


@pytest.fixture
def seeded(monkeypatch, db_engine, db_committed, tmp_path):
    monkeypatch.setattr(config, "DATABASE_URL",
                        db_engine.url.render_as_string(hide_password=False))
    from swingbot.core.db import profiles
    profiles.reset_engines()
    from swingbot.core.db.repositories.trades import TradeRepository
    with db_committed.begin():
        TradeRepository().insert(dict(
            trade_id="E1", ticker="AAPL", strategy="RSI", horizon="2w",
            direction="bullish", status="win",
            opened_at="2026-01-02T15:00:00+00:00",
            closed_at="2026-02-02T15:00:00+00:00",
            entry=100.0, r_multiple=2.0), conn=db_committed)
    yield tmp_path
    profiles.reset_engines()


def test_csv_export(seeded):
    out = seeded / "trades.csv"
    assert main(["closed_trades", "-o", str(out)]) == 0
    df = pd.read_csv(out)
    assert list(df["trade_id"]) == ["E1"]


def test_the_export_has_the_expanded_columns(seeded):
    out = seeded / "trades.csv"
    main(["closed_trades", "-o", str(out)])
    df = pd.read_csv(out)
    assert "r_multiple" in df.columns
    assert "doc" not in df.columns


def test_all_writes_one_file_per_dataset(seeded):
    outdir = seeded / "datasets"
    assert main(["--all", "-o", str(outdir)]) == 0
    from swingbot.core.db.datasets import FRAMES
    written = {p.stem for p in outdir.glob("*.csv")}
    assert written == set(FRAMES)


def test_an_empty_dataset_still_writes_a_header(seeded):
    """A zero-byte file is indistinguishable from a failed export."""
    outdir = seeded / "datasets"
    main(["--all", "-o", str(outdir)])
    plans_csv = outdir / "plans.csv"
    assert plans_csv.stat().st_size > 0
    assert "plan_id" in plans_csv.read_text(encoding="utf-8").splitlines()[0]


def test_an_unknown_dataset_is_refused(seeded):
    with pytest.raises(SystemExit):
        main(["not_a_dataset", "-o", str(seeded / "x.csv")])


def test_it_refuses_to_write_into_data(seeded, monkeypatch):
    """An export in data/ sits beside the database's own backups and gets
    mistaken for one."""
    monkeypatch.setattr(config, "DATA_DIR", str(seeded / "data"))
    (seeded / "data").mkdir()
    assert main(["closed_trades", "-o", str(seeded / "data" / "t.csv")]) == 2


def test_parquet_when_available(seeded):
    pytest.importorskip("pyarrow")
    out = seeded / "trades.parquet"
    assert main(["closed_trades", "-o", str(out)]) == 0
    assert list(pd.read_parquet(out)["trade_id"]) == ["E1"]
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/scripts/test_export_dataset.py -q
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write it**

Create `scripts/db/export_dataset.py`:

```python
#!/usr/bin/env python3
"""Export a dataset for analysis outside this repo.

    python scripts/db/export_dataset.py closed_trades --profile snapshot -o trades.csv
    python scripts/db/export_dataset.py --all --profile snapshot -o exports/datasets/

Format follows the output extension: .csv, .parquet (needs pyarrow), .json.
Exports go under exports/, not data/ -- an export sitting beside the database's
own backups gets mistaken for one.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from swingbot import config                                  # noqa: E402
from swingbot.core.db import profiles                        # noqa: E402
from swingbot.core.db.datasets import FRAMES                 # noqa: E402


def _write(df, path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        df.to_parquet(path, index=False)
    elif suffix == ".json":
        df.to_json(path, orient="records", indent=2, date_format="iso")
    else:
        # index=False and a header even when empty: a zero-byte file is
        # indistinguishable from a failed export.
        df.to_csv(path, index=False)


def _refuses_data_dir(path: pathlib.Path) -> bool:
    try:
        data = pathlib.Path(config.DATA_DIR).resolve()
        return data == path.resolve().parent or data in path.resolve().parents
    except OSError:
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dataset", nargs="?", choices=sorted(FRAMES))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--profile", choices=profiles.PROFILES,
                    default=profiles.DEFAULT_PROFILE)
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args(argv)

    if not args.dataset and not args.all:
        ap.error("name a dataset, or pass --all")

    out = pathlib.Path(args.out)
    if _refuses_data_dir(out):
        print("export_dataset: refusing to write into data/ -- exports go "
              "under exports/, so they are not mistaken for a backup",
              file=sys.stderr)
        return 2

    names = sorted(FRAMES) if args.all else [args.dataset]
    for name in names:
        df = FRAMES[name](profile=args.profile)
        target = (out / f"{name}.csv") if args.all else out
        _write(df, target)
        print(f"export_dataset: {name}: {len(df)} row(s) -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Add a Makefile target:

```make
# make db-export PROFILE=snapshot
db-export:
	python scripts/db/export_dataset.py --all --profile $(or $(PROFILE),local) -o exports/datasets/
```

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/scripts/test_export_dataset.py
python scripts/db/export_dataset.py --all -o exports/datasets/
ls -la exports/datasets/
```

Expected: `0 failed`, and one CSV per dataset.

- [ ] **Step 5: Commit**

```bash
git add scripts/db/export_dataset.py Makefile tests/scripts/test_export_dataset.py
git commit -m "feat(v67): add cross-profile dataset export"
```

---

### Task P7-09: Analysis scripts take a profile

The scripts that read trade history should be able to read production's, from a
dev machine, without editing anything.

**Files:**
- Create: `scripts/db/profile_arg.py`
- Modify: `scripts/reports/shadow_parity_report.py`
- Modify: `scripts/ops/backfill_manual_close_price.py`
- Modify: `scripts/data/backfill_journal.py`
- Test: `tests/scripts/test_profile_arg.py`

**Interfaces:**
- Consumes: `profiles` (P7-04).
- Produces:
  - `add_profile_arg(parser) -> None` — adds `--db-profile`
  - `apply_profile(args) -> str` — validates, and **refuses a write-mode run
    against `prod-ro`**

**A backfill script is a write.** `backfill_manual_close_price.py` and
`backfill_journal.py` modify records; pointing either at `prod-ro` would fail
at the first write with a permission error, which is correct but obscure. The
helper refuses it up front with a sentence.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_profile_arg.py`:

```python
"""One --db-profile flag, added the same way everywhere."""
import argparse
import pathlib

import pytest

from scripts.db.profile_arg import add_profile_arg, apply_profile

REPO = pathlib.Path(__file__).resolve().parents[2]


def _parse(argv, writes=False):
    ap = argparse.ArgumentParser()
    add_profile_arg(ap, writes=writes)
    return ap.parse_args(argv)


def test_the_default_is_local():
    assert apply_profile(_parse([])) == "local"


def test_a_named_profile_is_returned():
    assert apply_profile(_parse(["--db-profile", "snapshot"])) == "snapshot"


def test_an_unknown_profile_is_refused_by_argparse():
    with pytest.raises(SystemExit):
        _parse(["--db-profile", "production"])


def test_a_read_only_script_may_use_prod_ro():
    assert apply_profile(_parse(["--db-profile", "prod-ro"])) == "prod-ro"


def test_a_writing_script_refuses_prod_ro():
    """Correct failure, but a permission error at the first write is obscure.
    Say it up front instead."""
    with pytest.raises(SystemExit) as exc:
        apply_profile(_parse(["--db-profile", "prod-ro"], writes=True))
    assert "read-only" in str(exc.value) or exc.value.code == 2


def test_a_writing_script_allows_snapshot():
    assert apply_profile(
        _parse(["--db-profile", "snapshot"], writes=True)) == "snapshot"


@pytest.mark.parametrize("script", [
    "scripts/reports/shadow_parity_report.py",
    "scripts/ops/backfill_manual_close_price.py",
    "scripts/data/backfill_journal.py",
])
def test_the_script_offers_the_flag(script):
    text = (REPO / script).read_text(encoding="utf-8")
    assert "add_profile_arg" in text, f"{script} has no --db-profile"


@pytest.mark.parametrize("script,writes", [
    ("scripts/reports/shadow_parity_report.py", False),
    ("scripts/ops/backfill_manual_close_price.py", True),
    ("scripts/data/backfill_journal.py", True),
])
def test_writing_scripts_declare_that_they_write(script, writes):
    text = (REPO / script).read_text(encoding="utf-8")
    if writes:
        assert "writes=True" in text, f"{script} writes but does not say so"
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/scripts/test_profile_arg.py -q
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write the helper**

Create `scripts/db/profile_arg.py`:

```python
"""One --db-profile flag, added the same way by every script that has one.

A script declares whether it WRITES. A writing script pointed at prod-ro would
fail at its first write with a permission error -- correct, but obscure, and
possibly a long way into a run. This says so before the run starts.
"""
from __future__ import annotations

import argparse

from swingbot.core.db import profiles


def add_profile_arg(parser: argparse.ArgumentParser, *,
                    writes: bool = False) -> None:
    parser.add_argument(
        "--db-profile", choices=profiles.PROFILES,
        default=profiles.DEFAULT_PROFILE,
        help=("which database to read: local (this machine), snapshot (a "
              "local copy of production, `make db-pull`), or prod-ro "
              "(production, read-only, needs `make db-tunnel`)."
              + (" This script writes, so prod-ro is refused." if writes else "")),
    )
    parser.set_defaults(_profile_writes=writes)


def apply_profile(args: argparse.Namespace) -> str:
    profile = getattr(args, "db_profile", profiles.DEFAULT_PROFILE)
    if getattr(args, "_profile_writes", False) and profiles.is_readonly(profile):
        raise SystemExit(
            f"this script writes, and --db-profile {profile} is read-only. "
            f"Use --db-profile snapshot to work against a copy of production, "
            f"or local for this machine's own database."
        )
    return profile
```

- [ ] **Step 4: Wire it into the three scripts**

`shadow_parity_report.py` — `add_profile_arg(ap)` (reads only), and pass the
resolved profile down to `load_lines()`, which gains a `profile=None`
parameter forwarded to the repository.

`backfill_manual_close_price.py` and `backfill_journal.py` —
`add_profile_arg(ap, writes=True)`, and use `profiles.engine_for(profile)` for
their connections rather than `get_engine()`.

Check each script's existing `argparse` setup before editing;
`backfill_manual_close_price.py` predates this plan and may not have one, in
which case adding argparse is part of this task rather than a separate concern.

- [ ] **Step 5: Run the tests**

```bash
python scripts/dev/testrun.py file tests/scripts/test_profile_arg.py
python scripts/reports/shadow_parity_report.py --help
python scripts/reports/shadow_parity_report.py --db-profile snapshot
```

Expected: `0 failed`, the flag in `--help`, and the report running against the
snapshot.

- [ ] **Step 6: Commit**

```bash
git add scripts/db/profile_arg.py scripts/reports/shadow_parity_report.py \
        scripts/ops/backfill_manual_close_price.py scripts/data/backfill_journal.py \
        tests/scripts/test_profile_arg.py
git commit -m "feat(v67): add --db-profile to the analysis scripts"
```

---

### Task P7-10: Fetch backtest data for production's universe

`market_data/` and `data/backtest_cache/*.csv` stay as files — that is the
spec's decision and this task does not revisit it. What changes is where the
**list of tickers** to fetch comes from: the watchlist is a table now, so a dev
machine can fetch exactly what production is scanning without anyone copying a
watchlist by hand.

**Files:**
- Modify: `scripts/data/fetch_backtest_data.py`
- Modify: `scripts/data/build_universe.py`
- Test: `tests/scripts/test_fetch_universe_source.py`

**Interfaces:**
- Consumes: `watchlist_repo` (P2-21), `profile_arg` (P7-09).
- Produces: `--db-profile` on both scripts, and
  `resolve_universe(args) -> list[str]` in `fetch_backtest_data.py`.

**The failure this prevents.** Today a local backtest runs against whatever
`data/watchlist.json` this checkout happens to have — which drifts from
production's the moment either changes. A backtest over the wrong universe
produces numbers that look fine and answer a question nobody asked.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_fetch_universe_source.py`:

```python
"""Which tickers a fetch iterates, and where that list comes from."""
import pathlib

import pytest

from swingbot import config

REPO = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture
def seeded(monkeypatch, db_engine, db_committed):
    monkeypatch.setattr(config, "DATABASE_URL",
                        db_engine.url.render_as_string(hide_password=False))
    from swingbot.core.db import profiles
    profiles.reset_engines()
    from swingbot.core.db.repositories.watchlist import WatchlistRepository
    repo = WatchlistRepository()
    with db_committed.begin():
        for ticker in ("AAPL", "MSFT", "NVDA"):
            repo.add(ticker, conn=db_committed)
    yield
    profiles.reset_engines()


def _args(**over):
    import argparse
    ns = argparse.Namespace(db_profile="local", universe=None, tickers=None)
    for k, v in over.items():
        setattr(ns, k, v)
    return ns


def test_the_watchlist_comes_from_the_database(seeded):
    from scripts.data.fetch_backtest_data import resolve_universe
    assert resolve_universe(_args()) == ["AAPL", "MSFT", "NVDA"]


def test_explicit_tickers_win(seeded):
    from scripts.data.fetch_backtest_data import resolve_universe
    assert resolve_universe(_args(tickers=["TSLA"])) == ["TSLA"]


def test_a_named_universe_still_reads_its_json_file(seeded):
    """sp500.json and etfs.json stay in git -- static reference data belonging
    with the code. This task does not move them."""
    from scripts.data.fetch_backtest_data import resolve_universe
    out = resolve_universe(_args(universe="sp500"))
    assert len(out) > 100


def test_an_empty_watchlist_is_an_error_not_an_empty_run(seeded, db_committed):
    """Fetching nothing and exiting 0 looks like success and leaves the cache
    empty, which surfaces as a confusing backtest hours later."""
    from scripts.data.fetch_backtest_data import resolve_universe
    from swingbot.core.db.repositories.watchlist import WatchlistRepository
    with db_committed.begin():
        WatchlistRepository().clear(conn=db_committed)
    with pytest.raises(SystemExit):
        resolve_universe(_args())


@pytest.mark.parametrize("script", [
    "scripts/data/fetch_backtest_data.py",
    "scripts/data/build_universe.py",
])
def test_the_script_offers_the_profile_flag(script):
    text = (REPO / script).read_text(encoding="utf-8")
    assert "add_profile_arg" in text


def test_the_docstring_records_that_the_caches_stay_files():
    text = (REPO / "scripts/data/fetch_backtest_data.py").read_text(
        encoding="utf-8")
    assert "backtest_cache" in text
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/scripts/test_fetch_universe_source.py -q
```

Expected: `ImportError: cannot import name 'resolve_universe'`.

- [ ] **Step 3: Add the universe resolver**

In `scripts/data/fetch_backtest_data.py`:

```python
def resolve_universe(args) -> list[str]:
    """The tickers this fetch will iterate.

    Precedence: explicit --tickers, then --universe (a git-committed reference
    file: sp500.json / etfs.json, which stay as files per the v67 spec), then
    the watchlist from the selected database profile.

    Reading the watchlist from a profile is the point: a local backtest used to
    run against whatever data/watchlist.json this checkout happened to have,
    which drifts from production's the moment either changes. A backtest over
    the wrong universe produces numbers that look fine and answer a question
    nobody asked.

    The OHLCV caches themselves (data/backtest_cache/*.csv, market_data/) are
    unchanged and stay as files -- large, regenerable, read by pandas directly.
    """
    if getattr(args, "tickers", None):
        return list(args.tickers)
    if getattr(args, "universe", None):
        return _load_named_universe(args.universe)      # existing code path

    from scripts.db.profile_arg import apply_profile
    from swingbot.core.db import profiles
    from swingbot.core.db.repositories.watchlist import WatchlistRepository

    profile = apply_profile(args)
    engine = profiles.engine_for(profile)
    with engine.connect() as conn:
        tickers = WatchlistRepository().tickers(conn=conn)
    if not tickers:
        raise SystemExit(
            f"the watchlist on the {profile!r} profile is empty, so this fetch "
            f"would do nothing and exit 0 -- which looks like success and "
            f"leaves the cache empty. Add tickers, pass --tickers, or use "
            f"--db-profile snapshot after `make db-pull`."
        )
    return tickers
```

Add `add_profile_arg(ap)` to both scripts' parsers, and route their existing
watchlist reads through `resolve_universe`.

- [ ] **Step 4: Run the tests and a real fetch**

```bash
python scripts/dev/testrun.py file tests/scripts/test_fetch_universe_source.py
python scripts/data/fetch_backtest_data.py --db-profile snapshot --tickers AAPL
```

Expected: `0 failed`, and one CSV appearing under `data/backtest_cache/`.

- [ ] **Step 5: Commit**

```bash
git add scripts/data/fetch_backtest_data.py scripts/data/build_universe.py \
        tests/scripts/test_fetch_universe_source.py
git commit -m "feat(v67): source the fetch universe from a database profile"
```

---

### Task P7-11: The local development quickstart

Six commands nobody should have to reconstruct from a plan file.

**Files:**
- Create: `docs/deploy/DB_LOCAL_DEV.md`
- Modify: `docs/setup.md`, `README.md`, `CLAUDE.md`
- Test: extend `tests/test_docs_consistency.py`

**Interfaces:**
- Consumes: everything in Part 7.
- Produces: nothing in code.

**`CLAUDE.md` is at its 200-line budget.** One line goes in — the `make db-pull`
/ `--db-profile snapshot` workflow, because that is the thing a session needs to
fire unprompted when asked to look at real trades. Everything else goes in the
new doc, and whatever it displaces moves to `docs/claude/architecture.md`.

- [ ] **Step 1: Extend the consistency test**

Add to `tests/test_docs_consistency.py`:

```python
def test_the_local_dev_guide_exists():
    doc = REPO / "docs" / "deploy" / "DB_LOCAL_DEV.md"
    assert doc.exists()
    text = doc.read_text(encoding="utf-8")
    for needle in ("make db-pull", "make db-tunnel", "--db-profile",
                   "swingbot_ro", "swingbot_snapshot"):
        assert needle in text, needle


def test_claude_md_names_the_snapshot_workflow():
    """The one Part 7 fact a session needs unprompted: how to look at real
    trades from a dev machine."""
    text = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    assert "db-pull" in text or "db-profile" in text


def test_no_doc_tells_anyone_to_scp_the_data_directory():
    for doc in DOCS + ["docs/deploy/DB_LOCAL_DEV.md"]:
        path = REPO / doc
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r"scp .*data/", line) and "was" not in line.lower():
                pytest.fail(f"{doc}:{i} still recommends scp: {line.strip()}")
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_docs_consistency.py -q
```

Expected: the three new tests fail.

- [ ] **Step 3: Write the guide**

Create `docs/deploy/DB_LOCAL_DEV.md`. Lead with the workflow, then the
reference:

```markdown
# Working with real data locally

Before v67 this was `scp` of `data/*.json`. Now:

    make db-pull                                     # production -> swingbot_snapshot
    python scripts/db/query.py --profile snapshot "select count(*) from trades"

That is the whole thing. The snapshot is a local database, full speed, no
network, and nothing you do to it can reach production.
```

Then sections for: the three profiles and when each is right; the `.env`
variables (`DATABASE_URL_SNAPSHOT`, `DATABASE_URL_PROD_RO`,
`POSTGRES_RO_PASSWORD`); reading production live with `make db-tunnel` and why
it is read-only; the DataFrame accessors with a worked example
(`datasets.closed_trades_frame(profile="snapshot").groupby("strategy")["r_multiple"].mean()`);
`--db-profile` on the analysis scripts; `make db-export`; and a troubleshooting
list — no SSH helper, an empty watchlist, `permission denied` from
`swingbot_ro` (that one is working as designed), and port 55434 already in use.

Add a pointer from `docs/setup.md` and a line in `README.md`'s documentation
index.

In `CLAUDE.md`, add one line to the Commands block:

```bash
make db-pull                                   # pull prod into a local snapshot; then --db-profile snapshot
```

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/test_docs_consistency.py
wc -l CLAUDE.md      # must be <= 200
```

Expected: `0 failed`, and `CLAUDE.md` within budget.

- [ ] **Step 5: Commit**

```bash
git add docs/deploy/DB_LOCAL_DEV.md docs/setup.md README.md CLAUDE.md \
        docs/claude/architecture.md tests/test_docs_consistency.py
git commit -m "docs(v67): document the local snapshot and read-only prod workflows"
```

---

### Task P7-12: Part 7 verification

**Files:**
- Create: `tests/db/test_part7_exit.py`

**Interfaces:**
- Consumes: everything in Part 7.
- Produces: nothing.

- [ ] **Step 1: Write the exit test**

Create `tests/db/test_part7_exit.py`:

```python
"""Checks that only make sense once every Part 7 task has landed."""
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]


def test_no_committed_file_points_at_production():
    """The property worth the most here. A DATABASE_URL naming the production
    host in a tracked file is a local run against production."""
    offenders = []
    for path in REPO.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.suffix not in (".py", ".sh", ".yml", ".yaml", ".md", ".json",
                               ".example", ".ini", ""):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if "167.233.26.185" in line and "postgres" in line.lower():
                offenders.append(f"{path.relative_to(REPO).as_posix()}:{i}")
    assert not offenders, f"production database URL in tracked files: {offenders}"


def test_the_readonly_role_is_the_only_role_the_tunnel_hands_out():
    text = (REPO / "scripts/ops/tunnel_prod_db.sh").read_text(encoding="utf-8")
    urls = re.findall(r"postgresql[^\s\"']*", text)
    assert urls
    assert all("swingbot_ro" in u for u in urls), urls


def test_the_pull_script_cannot_target_the_local_dev_database():
    text = (REPO / "scripts/ops/pull_prod_db.sh").read_text(encoding="utf-8")
    body = [l for l in text.splitlines() if not l.strip().startswith("#")]
    assert not any(re.search(r"\bswingbot\b(?!_snapshot|_ro)", l) for l in body)


@pytest.mark.parametrize("profile", ["local", "snapshot", "prod-ro"])
def test_every_profile_is_reachable_from_the_accessors(profile):
    """Not that it connects -- that the accessor accepts the name. A profile
    the datasets module rejects is a profile nobody can analyse with."""
    import inspect

    from swingbot.core.db import datasets, profiles
    assert profile in profiles.PROFILES
    for name, fn in datasets.FRAMES.items():
        assert "profile" in inspect.signature(fn).parameters, name


def test_every_dataset_has_an_export_name():
    from swingbot.core.db.datasets import FRAMES
    assert set(FRAMES) >= {"closed_trades", "open_trades", "plans",
                           "journal", "telemetry"}


def test_the_application_engine_and_the_profile_engines_are_separate():
    import swingbot.core.db.engine as app
    import swingbot.core.db.profiles as prof
    assert app.get_engine is not prof.engine_for
    src = pathlib.Path(prof.__file__).read_text(encoding="utf-8")
    assert "get_engine" not in src.replace("engine_for", ""), (
        "profiles.py must build its own engines, not reuse the app singleton")


def test_the_makefile_exposes_the_whole_workflow():
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    for target in ("db-pull:", "db-tunnel:", "db-query:", "db-export:"):
        assert target in makefile, target
```

- [ ] **Step 2: Run everything Part 7 touched**

```bash
python scripts/dev/testrun.py file tests/db/test_part7_exit.py
python scripts/dev/testrun.py fast
python -m pytest tests/db/ tests/scripts/ -q
```

Expected: `0 failed`, `0 xfailed` on all three. The last covers the `slow`
read-only-role tests the fast tier skips.

- [ ] **Step 3: Walk the workflow by hand, once**

Automated tests cannot prove the end-to-end path works, because they cannot
reach production. Do it:

```bash
make db-pull
python scripts/db/query.py --profile snapshot "select count(*), status from trades group by status"
python scripts/db/export_dataset.py closed_trades --profile snapshot -o exports/datasets/closed_trades.csv
python -c "
from swingbot.core.db import datasets
df = datasets.closed_trades_frame(profile='snapshot')
print(df.groupby('strategy')['r_multiple'].agg(['count','mean']))
"
```

Expected: real production counts, a CSV, and a per-strategy expectancy table.
**Compare that table against `!performance` on the live bot.** If they disagree,
that is a finding worth chasing before this part is called done — it means the
accessors and the application's own aggregation disagree about the same data.

- [ ] **Step 4: Commit**

```bash
git add tests/db/test_part7_exit.py
git commit -m "test(v67): pin Part 7 exit criteria"
```

---

## Part 7 exit criteria

Repeated from `_7a` so this file closes on its own terms:

1. A production snapshot pulls to a local database with one command, and never
   touches the local development database.
2. A local session reads production live through an SSH tunnel, as a role
   Postgres itself refuses writes from.
3. No committed file points `DATABASE_URL` at production.
4. Closed trades, plans and telemetry are available as pandas DataFrames from
   any profile, in one import.
5. `python scripts/dev/testrun.py fast` is green.
6. The end-to-end walk in P7-12 Step 3 has been done by hand, and the
   per-strategy expectancy it prints matches what the live bot reports.
