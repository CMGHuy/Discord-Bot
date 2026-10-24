# v190 part 3 — Fetcher and integrity: `--universe sp500_pit` with aliases, causal coverage cuts, the reused-symbol detector, `check_history_store.py --pit`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** bot patch
**Edge:** none (integrity)
**Spec:** [2026-10-24-v190-pit-alpaca-universe-design.md](../specs/2026-10-24-v190-pit-alpaca-universe-design.md)
**Index:** [2026-10-24-v190-pit-alpaca-universe_0-index.md](2026-10-24-v190-pit-alpaca-universe_0-index.md) — Goal, Architecture, Global Constraints, Contracts, `## Parallelisation` and the task ledger live there; every task below implicitly includes the index's Global Constraints.

**Scope of this part:** V190-12..V190-15 — the fetcher reading its member list from `sp500_pit.json`, applying the rename alias table and never falling back to the mutable `market_data/daily` reference (spec §1, §2.2, §2.4); the causal coverage cuts (§2.1); the reused-symbol break test and its kept-side rule (§2.3); and `check_history_store.py --pit`, which assembles all of it into the frozen `_integrity.json` that Part 1's reader (V190-3) and selection (V190-4) consume, plus a Markdown summary.

**Working directory.** Every command below runs inside the worktree `.claude/worktrees/2026-10-24-v190-pit-alpaca-universe` (created in V190-1). Agent shells reset their cwd between calls, so `cd "$WT"` means: set `WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v190-pit-alpaca-universe` in the same command or substitute the path. **Never** run `fetch_alpaca_history.py` or `check_history_store.py` against the real `data/market_data_pit/` from a task in this part — a backfill is writing it (index Global Constraints, one fetcher per root). Tests build every store under `tmp_path`.

**Database.** No test in this part reaches Postgres; `/replicate-prod-db` is not needed.

**Test routing.** All new test files live in `tests/history_store/` (suite `history-store`); V190-2's `DATA_READERS` rows already route `data/market_data_pit/` and `data/universe/symbol_aliases.json` to that directory, so no `select_tests.py` edit is needed here.

**Facts this part relies on (verified at `ead984a3`).**
- `scripts/data/fetch_alpaca_history.py:73-79` (`_Run.market_dir: Path`), `:120` (`args.market_dir` default `ROOT / "market_data" / "daily"`), `:192-206` (`_daily_identity` calls `identity.reference_frame(ticker, backtest_dir=..., market_dir=...)`), `:186-189` (`_fetch` passes `ticker` to `fetch.fetch_store_frame`), `:282-293` (`_update_one`).
- `scripts/data/alpaca_history/identity.py:73-79` — `reference_frame` loops `(backtest_dir, market_dir)` and returns the first folder whose `_read_reference` is not `None`.
- `swingbot/core/marketdata/universe.py:89` — `UNIVERSE_DIR` is bound at import; tests monkeypatch `universe.UNIVERSE_DIR`. `load` keeps only rows carrying `symbol`, `name`, `sector`, `etf`, and upper-cases the symbol. `universe_symbols(name)` and `sector_map(name)` read through `load`.
- `scripts/data/check_history_store.py:47-55` — `read_frame(root, ticker, timeframe)` reads `<root>/<tf>/<SAFE>.csv` directly; it is the only reader V190-15 uses (constraint 3 below).
- `scripts/data/alpaca_history/store_io.py:33-38` — `sha256_file(path)`.
- `git config core.autocrlf` is `true` on this machine, so a working-tree `.py` file may carry CRLF while its git blob holds LF; V190-15's detector blob hash normalises CRLF before hashing so it equals `git hash-object`.

**Constraints from Part 1 that V190-15 honours (each pinned by a test there).**
1. `_integrity.json` `manifest_sha256["daily"]` is `store_io.sha256_file(<root>/daily/_manifest.json)` — V190-4 compares it and raises `StaleIntegrityError` on a difference.
2. `Integrity.exclusion` refuses every ticker absent from `doc["tickers"]`, so SPY, `config.MARKET_REGIME_TICKER` and every `etfs.json` symbol get an `admitted: true` entry when their data is sound; otherwise every v3 run stops at `require_context_frames`.
3. `history_store.load(store="pit")` raises `MissingStoreError` without `_integrity.json`, so V190-15 reads the store with `check_history_store.read_frame`, never `history_store.load`.

# Phase 5 — The fetcher on the point-in-time universe

### Task V190-12: Fetcher `--universe sp500_pit`, aliases, no identity fallback

**Model:** sonnet — a CLI extension inside one established script plus a small new reader; the rules are fixed below and every one has a test.

**Files:**
- Create: `scripts/data/alpaca_history/aliases.py`
- Create: `tests/history_store/test_aliases.py`
- Modify: `scripts/data/alpaca_history/identity.py` (`reference_frame` `:73-79`; new `reference_path`; module docstring)
- Modify: `scripts/data/fetch_alpaca_history.py` (docstring, `_Run` `:61-76`, `parse_args` `:99-121`, `_resolve_tickers` `:124-130`, `_make_run` `:149-152`, `_record_skip` `:175-183`, `_fetch` `:186-189`, `_daily_identity` `:192-206`, `_write` `:215-219`, `_write_timeframes` `:222-233`, `_update_one` `:282-293`)
- Modify: `tests/history_store/test_identity.py`
- Modify: `tests/history_store/test_fetch_alpaca_history.py`

**Interfaces:**
- Consumes: `history_store.store_root()` (the watchlist root; V190-2 keeps its no-argument meaning); `universe.universe_symbols(name)`, `universe.UNIVERSE_DIR`.
- Produces (used by V190-15, V190-18..V190-20):
  - `aliases.ALIASES_PATH = Path("data/universe/symbol_aliases.json")` — relative to the project root
  - `@dataclass(frozen=True) class Alias: member: str; alpaca: str; start: str; end: str | None` with `clip(frame: pd.DataFrame | None) -> pd.DataFrame | None` — keeps bars whose **date** satisfies `start <= date < end` (`end=None` open); empty or `None` → `None`
  - `aliases.load_aliases(path: Path) -> dict[str, Alias]` — keyed by member; `{}` when the file is absent; `ValueError` naming the path for: top level not an object with an `"aliases"` list; an entry missing `member`, `alpaca` or `start`; a non-ISO `start`/`end`; `end <= start`; `member == alpaca`; a duplicate member. Symbols are `.strip().upper()`; an entry's `"note"` is allowed and ignored.
  - File shape: `{"aliases": [{"member": "FB", "alpaca": "META", "start": "2016-01-04", "end": null, "note": "renamed 2022-06-09"}]}`
  - `identity.reference_path(ticker, *, backtest_dir: Path, market_dir: Path | None) -> Path | None` — the file `reference_frame` reads: the first of `backtest_dir/<SAFE>.csv`, then `market_dir/<SAFE>.csv` (skipped when `market_dir is None`), whose `_read_reference` is not `None`
  - `identity.reference_frame(ticker, *, backtest_dir, market_dir: Path | None)` — `_read_reference(reference_path(...))` or `None`; `market_dir=None` means **no fallback**
  - `fetch_alpaca_history.UNIVERSES = ("sp500_pit",)`
  - CLI `--universe sp500_pit`: the run's tickers are the universe file's symbols unless `--tickers` is also given, in which case `--tickers` is the list (the context pass: `--universe sp500_pit --tickers SPY,QQQ,...`); requires an explicit `--root` that is not the watchlist store's root; sets `args.market_dir = None` (no identity fallback); `--market-dir` beside it is refused
  - CLI `--aliases PATH`: only with `--universe` (default `ROOT / aliases.ALIASES_PATH`); parsed into `args.alias_map: dict[str, Alias]` (`{}` without `--universe`)
  - An aliased member is fetched under `alias.alpaca`, clipped by `Alias.clip`, written and keyed under the member symbol, and every manifest entry for it (written **or** skipped) carries `"alias": "<alpaca symbol>"`. Non-aliased entries carry no `alias` key (watchlist manifests byte-identical). `--mode update` hands an aliased member to the full path (never `update.update_ticker`, which would ask Alpaca for the membership symbol).

- [ ] **Step 1: Write the failing alias-reader tests**

Create `tests/history_store/test_aliases.py`:

```python
"""v190 section 2.4: the committed rename table (membership symbol -> Alpaca
symbol with a date range). A malformed table stops the fetcher instead of
silently fetching the wrong issuer."""
import json
from pathlib import Path

import pandas as pd
import pytest

from alpaca_history import aliases

FB = {"member": "FB", "alpaca": "META", "start": "2016-01-04", "end": None,
      "note": "renamed 2022-06-09"}


def _write(tmp_path, doc) -> Path:
    path = tmp_path / "symbol_aliases.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _bars(start, end, freq="B"):
    idx = pd.date_range(start, end, freq=freq)
    return pd.DataFrame({"Close": range(len(idx))}, index=idx, dtype=float)


def test_path_is_relative_to_the_project_root():
    assert aliases.ALIASES_PATH == Path("data/universe/symbol_aliases.json")
    assert not aliases.ALIASES_PATH.is_absolute()


def test_absent_file_is_an_empty_table(tmp_path):
    assert aliases.load_aliases(tmp_path / "missing.json") == {}


def test_entries_are_keyed_by_member_and_upper_cased(tmp_path):
    path = _write(tmp_path, {"aliases": [FB, {"member": " brk.b ", "alpaca": "brk.b2",
                                              "start": "2016-01-04", "end": "2020-01-02"}]})
    got = aliases.load_aliases(path)
    assert got["FB"] == aliases.Alias("FB", "META", "2016-01-04", None)
    assert got["BRK.B"] == aliases.Alias("BRK.B", "BRK.B2", "2016-01-04", "2020-01-02")


@pytest.mark.parametrize("doc", [
    [FB],                                                   # not an object
    {"rows": [FB]},                                         # no "aliases" list
    {"aliases": [{**FB, "alpaca": ""}]},                    # missing symbol
    {"aliases": [{k: v for k, v in FB.items() if k != "start"}]},
    {"aliases": [{**FB, "start": "2016-13-01"}]},           # not ISO
    {"aliases": [{**FB, "end": "2016-01-04"}]},             # end <= start
    {"aliases": [{**FB, "alpaca": "FB"}]},                  # aliases itself
    {"aliases": [FB, {**FB, "alpaca": "META2"}]},           # duplicate member
])
def test_a_malformed_table_is_refused_naming_the_file(tmp_path, doc):
    path = _write(tmp_path, doc)
    with pytest.raises(ValueError, match="symbol_aliases.json"):
        aliases.load_aliases(path)


def test_clip_keeps_the_alias_date_range_at_date_level():
    alias = aliases.Alias("FB", "META", "2016-03-01", "2016-03-08")
    got = alias.clip(_bars("2016-02-25", "2016-03-15"))
    assert got.index.min() == pd.Timestamp("2016-03-01")
    assert got.index.max() == pd.Timestamp("2016-03-07")
    hourly = alias.clip(_bars("2016-03-07 09:30", "2016-03-08 15:30", freq="h"))
    assert hourly.index.max() < pd.Timestamp("2016-03-08")


def test_clip_edge_cases():
    open_ended = aliases.Alias("FB", "META", "2016-03-01", None)
    frame = _bars("2016-03-01", "2016-03-04")
    assert len(open_ended.clip(frame)) == len(frame)
    assert open_ended.clip(None) is None
    assert aliases.Alias("FB", "META", "2017-01-03", None).clip(frame) is None
```

- [ ] **Step 2: Add the failing identity tests**

Append to `tests/history_store/test_identity.py` (after `test_no_reference_is_none`):

```python
def test_no_market_dir_means_backtest_cache_only(tmp_path):
    """v190 section 2.2: on the PIT store the mutable market_data/daily cache is never a reference."""
    _csv(tmp_path / "md", "AAPL.csv", "Date,Open,High,Low,Close,Volume\n2016-01-04,1,1,1,12,5\n")
    assert identity.reference_frame("AAPL", backtest_dir=tmp_path / "bc", market_dir=None) is None
    assert identity.reference_path("AAPL", backtest_dir=tmp_path / "bc", market_dir=None) is None
    assert identity.reference_path("AAPL", backtest_dir=tmp_path / "bc",
                                   market_dir=tmp_path / "md") == tmp_path / "md" / "AAPL.csv"


def test_reference_path_names_the_file_reference_frame_reads(tmp_path):
    _csv(tmp_path / "bc", "MSFT.csv", "Date,Open,High,Low,Close,Volume\n2016-01-04,1,1,1,10,5\n")
    _csv(tmp_path / "md", "MSFT.csv", "Date,Open,High,Low,Close,Volume\n2016-01-04,1,1,1,99,5\n")
    assert identity.reference_path("MSFT", backtest_dir=tmp_path / "bc",
                                   market_dir=tmp_path / "md") == tmp_path / "bc" / "MSFT.csv"
    _csv(tmp_path / "bc", "MSFT.csv", "Date,Open\n2016-01-04,1\n")          # no Close column
    assert identity.reference_path("MSFT", backtest_dir=tmp_path / "bc",
                                   market_dir=tmp_path / "md") == tmp_path / "md" / "MSFT.csv"
```

- [ ] **Step 3: Add the failing fetcher tests**

Append to `tests/history_store/test_fetch_alpaca_history.py`:

```python
# --- v190: --universe sp500_pit, aliases, no identity fallback -------------------------

from alpaca_history import aliases as alias_mod  # noqa: E402
from swingbot.core.marketdata import universe as universe_mod  # noqa: E402

FB_TO_META = {"member": "FB", "alpaca": "META", "start": "2023-06-01", "end": None,
              "note": "renamed 2022-06-09"}


@pytest.fixture
def pit(dirs, tmp_path, monkeypatch):
    """dirs plus a PIT root, a fixture universe dir and a (not yet written) alias table."""
    folder = tmp_path / "universe"
    folder.mkdir()
    monkeypatch.setattr(universe_mod, "UNIVERSE_DIR", str(folder))
    return {**dirs, "pit": tmp_path / "market_data_pit", "universe": folder,
            "aliases": tmp_path / "symbol_aliases.json"}


def _members(pit, *symbols) -> None:
    rows = [{"symbol": s, "name": s, "sector": "Unknown", "etf": False} for s in symbols]
    (pit["universe"] / "sp500_pit.json").write_text(json.dumps(rows), encoding="utf-8")


def _alias_table(pit, *entries) -> None:
    pit["aliases"].write_text(json.dumps({"aliases": list(entries)}), encoding="utf-8")


def _pit_argv(pit, *extra: str) -> list[str]:
    return ["--universe", "sp500_pit", "--start", "2023-01-01", "--root", str(pit["pit"]),
            "--backtest-dir", str(pit["bt"]), "--aliases", str(pit["aliases"]), *extra]


def test_universe_run_fetches_the_member_list(pit):
    cli = load_cli()
    _members(pit, "AAPL", "NVDA")
    prov = FakeHistory(["AAPL", "NVDA"])
    assert cli.main(_pit_argv(pit), provider=prov, now=NOW) == 0
    assert {c[0] for c in prov.calls} == {"AAPL", "NVDA"}
    assert set(_manifest(pit["pit"], "daily")["tickers"]) == {"AAPL", "NVDA"}
    assert not (pit["root"] / "daily").exists()          # the watchlist store is untouched


def test_universe_run_never_falls_back_to_the_market_dir_reference(pit):
    cli = load_cli()
    write_reference(pit["md"], "NVDA", DAYS, daily_closes(DAYS))
    assert cli.main(_argv(pit, "NVDA"), provider=FakeHistory(["NVDA"]), now=NOW) == 0
    assert _manifest(pit["root"], "daily")["tickers"]["NVDA"]["status"] == "ok"   # watchlist: fallback
    _members(pit, "NVDA")
    assert cli.main(_pit_argv(pit), provider=FakeHistory(["NVDA"]), now=NOW) == 0
    assert _manifest(pit["pit"], "daily")["tickers"]["NVDA"]["status"] == "flagged: no-reference"


def test_alias_fetches_the_alpaca_symbol_and_stores_the_member(pit):
    cli = load_cli()
    _members(pit, "FB")
    _alias_table(pit, FB_TO_META)
    write_reference(pit["bt"], "FB", DAYS, daily_closes(DAYS))      # reference under the member
    prov = FakeHistory(["META"])
    assert cli.main(_pit_argv(pit), provider=prov, now=NOW) == 0
    assert {c[0] for c in prov.calls} == {"META"}
    for tf in TF:
        assert (pit["pit"] / tf / "FB.csv").exists() and not (pit["pit"] / tf / "META.csv").exists()
        entry = _manifest(pit["pit"], tf)["tickers"]["FB"]
        assert entry["alias"] == "META" and entry["status"] == "ok"
    daily = pd.read_csv(pit["pit"] / "daily" / "FB.csv", index_col="Date", parse_dates=True)
    assert daily.index.min() >= pd.Timestamp("2023-06-01")


def test_alias_without_bars_is_skipped_with_the_alias_recorded(pit):
    cli = load_cli()
    _members(pit, "FB")
    _alias_table(pit, FB_TO_META)
    assert cli.main(_pit_argv(pit), provider=FakeHistory([]), now=NOW) == 0
    entry = _manifest(pit["pit"], "daily")["tickers"]["FB"]
    assert entry["status"] == cli.NO_BARS and entry["alias"] == "META"


def test_watchlist_entries_carry_no_alias_key(dirs):
    cli = load_cli()
    assert cli.main(_argv(dirs, "AAPL"), provider=FakeHistory(["AAPL"]), now=NOW) == 0
    for tf in TF:
        assert "alias" not in _manifest(dirs["root"], tf)["tickers"]["AAPL"]


def test_tickers_replace_the_member_list_for_the_context_pass(pit):
    cli = load_cli()
    _members(pit, "AAPL")
    prov = FakeHistory(["SPY"])
    assert cli.main(_pit_argv(pit, "--tickers", "SPY"), provider=prov, now=NOW) == 0
    assert {c[0] for c in prov.calls} == {"SPY"}
    assert set(_manifest(pit["pit"], "daily")["tickers"]) == {"SPY"}


def test_update_mode_hands_an_aliased_member_to_the_full_path(pit):
    cli = load_cli()
    _members(pit, "FB")
    _alias_table(pit, FB_TO_META)
    assert cli.main(_pit_argv(pit), provider=FakeHistory(["META"]), now=NOW) == 0
    prov = FakeHistory(["META"])
    assert cli.main(_pit_argv(pit, "--mode", "update"), provider=prov, now=NOW) == 0
    assert all(call[0] == "META" for call in prov.calls)


def test_an_empty_universe_file_stops_the_run(pit):
    cli = load_cli()
    _members(pit)
    with pytest.raises(SystemExit, match="sp500_pit"):
        cli.main(_pit_argv(pit), provider=FakeHistory([]), now=NOW)


def test_universe_flag_combinations_that_are_refused(pit, store_root):
    cli = load_cli()
    pit_root = ["--root", str(pit["pit"])]
    for argv in (["--universe", "sp500_pit"],                                     # no --root
                 ["--universe", "sp500_pit", "--root", str(store_root)],          # the watchlist root
                 ["--universe", "sp500_pit", *pit_root, "--market-dir", str(pit["md"])],
                 ["--aliases", str(pit["aliases"])],                              # aliases alone
                 ["--universe", "sp500", *pit_root]):                             # unknown universe
        with pytest.raises(SystemExit):
            cli.parse_args(argv)
    _alias_table(pit, FB_TO_META, {**FB_TO_META, "alpaca": "META2"})               # duplicate member
    with pytest.raises(SystemExit):
        cli.parse_args(["--universe", "sp500_pit", *pit_root, "--aliases", str(pit["aliases"])])


def test_parse_args_universe_defaults(pit):
    cli = load_cli()
    plain = cli.parse_args([])
    assert plain.universe is None and plain.alias_map == {} and plain.market_dir is not None
    args = cli.parse_args(["--universe", "sp500_pit", "--root", str(pit["pit"]),
                           "--aliases", str(pit["aliases"])])
    assert args.market_dir is None and args.alias_map == {}
    default = cli.parse_args(["--universe", "sp500_pit", "--root", str(pit["pit"])])
    assert default.aliases == cli.ROOT / alias_mod.ALIASES_PATH
```

- [ ] **Step 4: Run the tests to verify they fail**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/history_store/test_aliases.py
cd "$WT" && python scripts/dev/testrun.py file tests/history_store/test_identity.py
cd "$WT" && python scripts/dev/testrun.py file tests/history_store/test_fetch_alpaca_history.py
```

Expected: FAIL — `ImportError: cannot import name 'aliases'`, `AttributeError: ... has no attribute 'reference_path'`, `unrecognized arguments: --universe`.

- [ ] **Step 5: Implement `scripts/data/alpaca_history/aliases.py`**

Module docstring: v190 §2.4 — the committed table maps a membership symbol whose own symbol has no Alpaca bars (FB→META style) to the Alpaca symbol that carries its history over `[start, end)`; the fetcher fetches the Alpaca symbol and stores it under the membership symbol; the identity reference stays the membership symbol's; a member left unmapped stays listed under `no_bars` in the integrity report. Names exactly as in Interfaces. Validation goes through one `_alias(entry, path) -> Alias` helper (each refusal a `ValueError(f"{path}: <what is wrong>")`) plus a duplicate check in `load_aliases`. `Alias.clip` compares on `frame.index.normalize()` — the same date-level rule as `pit_integrity.apply_trim` (V190-3).

- [ ] **Step 6: Implement `identity.reference_path` and the no-fallback `reference_frame`**

`reference_path` walks `(backtest_dir, market_dir)`, skipping a `None` folder, and returns the first `Path(folder) / f"{safe_symbol(ticker)}.csv"` whose `_read_reference` is not `None`; `reference_frame` returns `_read_reference(path)` for that path, else `None`. The module docstring's first paragraph gains: "On the PIT store (`--universe`, v190) `market_dir` is `None`: `backtest_cache_ext` is the only reference, never the mutable root `market_data/daily` cache."

- [ ] **Step 7: Wire `--universe` and `--aliases` into `fetch_alpaca_history.py`**

- Import `aliases` beside the other `alpaca_history` modules. The docstring gains the PIT usage line `python scripts/data/fetch_alpaca_history.py --universe sp500_pit --root data/market_data_pit --backtest-dir data/backtest_cache_ext --timeframes daily` and one sentence: a `--universe` run writes its own root (never the watchlist store), uses `backtest_cache_ext` as its only identity reference, and applies `data/universe/symbol_aliases.json`.
- `UNIVERSES = ("sp500_pit",)` beside `RUN_ORDER`.
- `_Run`: `market_dir: Path | None`; new last field `aliases: dict = field(default_factory=dict)`.
- `parse_args`: add `--universe` (`choices=UNIVERSES`, default `None`) and `--aliases` (`type=Path`, default `None`); `--market-dir` keeps default `None` in argparse and is filled after parsing. After `ap.parse_args(argv)` call `_check_universe_args(ap, args)` **before** any default is filled, then fill `root`/`backtest_dir` as today, then `args.market_dir = None if args.universe else (args.market_dir or ROOT / "market_data" / "daily")`, then `args.alias_map = _alias_map(ap, args)`.
- `_check_universe_args(ap, args) -> None` — `ap.error(...)` for: `--aliases` without `--universe`; `--universe` without `--root`; `--universe` with `--market-dir`; `--universe` whose `Path(args.root).resolve() == Path(history_store.store_root()).resolve()` (message: "a --universe run never writes the watchlist store; pass the PIT root").
- `_alias_map(ap, args) -> dict` — `{}` without `--universe`; else `aliases.load_aliases(args.aliases or ROOT / aliases.ALIASES_PATH)`, a `ValueError` becoming `ap.error(str(exc))`. The resolved path is stored back in `args.aliases`.
- `_resolve_tickers`: `--tickers` wins (today's line); else with `args.universe` return `_universe_members(args.universe)`; else today's watchlist call. `_universe_members(name)` imports `universe` locally, returns `sorted({s.upper() for s in universe.universe_symbols(name)})`, and raises `SystemExit(f"--universe {name}: {universe.UNIVERSE_DIR}/{name}.json is missing or empty")` on an empty list.
- `_make_run`: `market_dir=Path(args.market_dir) if args.market_dir else None`, `aliases=dict(getattr(args, "alias_map", None) or {})`.
- `_fetch(run, ticker, timeframe)`: `alias = run.aliases.get(ticker)`; fetch `alias.alpaca if alias else ticker`; return `alias.clip(frame) if alias else frame`.
- `_with_alias(entry: dict, run: _Run, ticker: str) -> dict` — sets `entry["alias"] = alias.alpaca` when the ticker is aliased; returns `entry`. Used by `_write`, by the `NO_BARS` branch of `_write_timeframes` and by `_record_skip`.
- `_record_skip`: an entry is stale when `(entry.get("status"), entry.get("alias"))` differs from `(reason, <alias symbol or None>)`.
- `_daily_identity`: call shape unchanged — `run.market_dir` may now be `None`, which `reference_frame` reads as no fallback; the reference is read under the **member** ticker.
- `_update_one`: the first condition becomes `identity.skip_reason(ticker) or ticker in run.aliases or not _updatable(run, ticker)`.

- [ ] **Step 8: Run the tests to verify they pass**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/history_store/
```

Expected: `0 failed`, `0 xfailed` (every existing fetcher, identity and update test unchanged).

- [ ] **Step 9: Complexity gate**

```bash
cd "$WT" && python scripts/dev/complexity_gate.py
```

Expected: exit 0 (`parse_args` stays flat because the checks live in `_check_universe_args` and `_alias_map`).

- [ ] **Step 10: Commit**

```bash
cd "$WT" && git add scripts/data/alpaca_history/aliases.py scripts/data/alpaca_history/identity.py scripts/data/fetch_alpaca_history.py tests/history_store/test_aliases.py tests/history_store/test_identity.py tests/history_store/test_fetch_alpaca_history.py && git commit -m "feat(alpaca-history): --universe sp500_pit with rename aliases and no market_data identity fallback (v190)"
```

# Phase 6 — Integrity detectors

### Task V190-13: Causal coverage cuts

**Model:** opus — no-lookahead territory: a span-level verdict was the quant-engineer's blocking finding; every cut here must be decided from bars on or before its date, or delisted names drop out and survivorship comes back.

**Files:**
- Create: `scripts/data/alpaca_history/pit_coverage.py`
- Create: `tests/history_store/test_pit_coverage.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (pandas only; the module never imports `swingbot` so V190-15 and V190-21 can call it on any root).
- Produces (used by V190-15, V190-21):
  - `STORE_START = "2016-01-04"`, `STORE_END = "2025-12-31"`, `STORE_END_EXCL = "2026-01-01"` (the day after `STORE_END`; spans are half-open)
  - `MAX_MISSING_RUN = 5`, `TRAILING_SESSIONS = 60`, `MIN_TRAILING_SHARE = 0.95`
  - `RUN_REASON = "missing run of {n} sessions"` (formatted with the run length), `TRAILING_REASON = "trailing 60-session coverage under 95%"`
  - `expected_sessions(spy_daily: pd.DataFrame | None) -> pd.DatetimeIndex` — SPY's bar dates, normalised, unique, sorted, inside `[STORE_START, STORE_END]`; `ValueError` ("no SPY daily bars in the PIT store: SPY is the session calendar") when `None`, empty, or nothing falls inside the window
  - `clip_span(span: tuple[str, str]) -> tuple[str, str] | None` — `(max(start, STORE_START), min(end, STORE_END_EXCL))`; `None` when the result is empty
  - `missing_runs(bars, sessions, span) -> list[tuple[str, str, int]]` — **every** run of consecutive expected sessions inside `span` without a bar, in date order, as `(first missing session, end_excl, sessions)`; `end_excl` is the next calendar session after the run, or `span[1]` when the run reaches the span's end
  - `trailing_failures(bars, sessions, span) -> list[tuple[str, str]]` — runs of in-span sessions whose trailing window (the last `TRAILING_SESSIONS` calendar sessions up to and including the date, fewer only at the calendar's start) holds under `MIN_TRAILING_SHARE` of its sessions with a bar; same `(start, end_excl)` convention
  - `coverage_entry(bars, sessions, spans) -> tuple[list[dict], list[tuple[str, str, str]]]` — per clipped span one `{"span": [start, end_excl], "expected": int, "present": int, "missing_runs": [[start, end_excl, n], ...]}`; signal cuts = every missing run with `n > MAX_MISSING_RUN` (reason `RUN_REASON`) plus every trailing failure (reason `TRAILING_REASON`), sorted by `(start, end_excl, reason)`; spans that clip to `None` produce nothing
  - `bars` may be a `DatetimeIndex`, any timestamps (normalised to dates inside), or `None` (no bars); `sessions` is `expected_sessions(...)`'s output

- [ ] **Step 1: Write the failing tests**

Create `tests/history_store/test_pit_coverage.py`:

```python
"""v190 section 2.1: coverage cuts at date level, never a span-level verdict.
A run of more than 5 missing sessions is cut; a signal date needs 95% of its
trailing 60 sessions present -- decided from bars on or before the date, so
a delisted name's ragged tail never removes its earlier history."""
import pandas as pd
import pytest

from alpaca_history import pit_coverage as pc

SESSIONS = pd.bdate_range("2017-01-02", "2017-12-29")     # the fixture calendar
SPAN = ("2017-01-02", "2018-01-01")


def _iso(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m-%d")


def _without(*ranges) -> pd.DatetimeIndex:
    """SESSIONS minus the inclusive date ranges given."""
    keep = SESSIONS
    for start, end in ranges:
        keep = keep[(keep < pd.Timestamp(start)) | (keep > pd.Timestamp(end))]
    return keep


def _days(runs) -> set[str]:
    """Every calendar session inside the (start, end_excl, ...) runs."""
    out = set()
    for run in runs:
        inside = SESSIONS[(SESSIONS >= pd.Timestamp(run[0])) & (SESSIONS < pd.Timestamp(run[1]))]
        out |= {_iso(d) for d in inside}
    return out


def test_frozen_values():
    assert (pc.STORE_START, pc.STORE_END, pc.STORE_END_EXCL) == ("2016-01-04", "2025-12-31", "2026-01-01")
    assert (pc.MAX_MISSING_RUN, pc.TRAILING_SESSIONS, pc.MIN_TRAILING_SHARE) == (5, 60, 0.95)
    assert pc.RUN_REASON.format(n=9) == "missing run of 9 sessions"
    assert pc.TRAILING_REASON == "trailing 60-session coverage under 95%"


# --- the calendar and the window --------------------------------------------------------

def test_expected_sessions_are_spys_dates_inside_the_store_window():
    idx = pd.date_range("2015-12-28", "2026-01-09", freq="B")
    spy = pd.DataFrame({"Close": 1.0}, index=idx)
    got = pc.expected_sessions(spy)
    assert got.min() == pd.Timestamp("2016-01-04") and got.max() == pd.Timestamp("2025-12-31")
    stamped = pd.DataFrame({"Close": 1.0}, index=pd.DatetimeIndex(
        ["2016-01-05 16:00", "2016-01-04 16:00", "2016-01-05 16:00"]))
    assert list(pc.expected_sessions(stamped)) == [pd.Timestamp("2016-01-04"), pd.Timestamp("2016-01-05")]


@pytest.mark.parametrize("spy", [None, pd.DataFrame({"Close": []}, index=pd.DatetimeIndex([])),
                                 pd.DataFrame({"Close": 1.0}, index=pd.bdate_range("2014-01-02", "2015-12-31"))])
def test_no_spy_calendar_is_refused(spy):
    with pytest.raises(ValueError, match="SPY"):
        pc.expected_sessions(spy)


def test_clip_span():
    assert pc.clip_span(("2010-01-01", "9999-12-31")) == ("2016-01-04", "2026-01-01")
    assert pc.clip_span(("2018-03-01", "2019-01-02")) == ("2018-03-01", "2019-01-02")
    assert pc.clip_span(("2012-01-03", "2015-06-01")) is None
    assert pc.clip_span(("2026-02-02", "9999-12-31")) is None


# --- missing runs -----------------------------------------------------------------------

def test_every_missing_run_is_listed_with_its_length():
    bars = _without(("2017-03-01", "2017-03-13"), ("2017-04-03", "2017-04-04"))
    assert pc.missing_runs(bars, SESSIONS, SPAN) == [
        ("2017-03-01", "2017-03-14", 9), ("2017-04-03", "2017-04-05", 2)]


def test_a_run_reaching_the_span_end_ends_at_the_span_end():
    bars = _without(("2017-06-16", "2017-12-29"))
    span = ("2017-01-02", "2017-07-01")
    runs = pc.missing_runs(bars, SESSIONS, span)
    assert runs[-1][:2] == ("2017-06-16", "2017-07-01")
    assert runs[-1][2] == len(SESSIONS[(SESSIONS >= "2017-06-16") & (SESSIONS < "2017-07-01")])


def test_missing_runs_ignore_sessions_outside_the_span():
    bars = _without(("2017-01-02", "2017-02-28"))
    assert pc.missing_runs(bars, SESSIONS, ("2017-03-01", "2018-01-01")) == []


# --- the trailing-60 rule ---------------------------------------------------------------

def test_three_missing_sessions_in_sixty_pass():
    bars = _without(("2017-06-01", "2017-06-05"))           # Thu, Fri, Mon: 3 sessions
    assert pc.trailing_failures(bars, SESSIONS, SPAN) == []


def test_four_missing_fail_until_the_first_leaves_the_window():
    bars = _without(("2017-06-01", "2017-06-06"))           # 4 sessions
    m = SESSIONS.get_loc(pd.Timestamp("2017-06-01"))
    assert pc.trailing_failures(bars, SESSIONS, SPAN) == [(_iso(SESSIONS[m + 3]), _iso(SESSIONS[m + 60]))]


def test_a_short_window_at_the_calendar_start_is_judged_on_what_exists():
    assert pc.trailing_failures(SESSIONS, SESSIONS, SPAN) == []
    first_missing = SESSIONS[1:]                            # 1 of the first 2 sessions missing
    assert pc.trailing_failures(first_missing, SESSIONS, SPAN)[0][0] == "2017-01-02"


def test_the_verdict_on_a_date_never_reads_a_later_bar():
    """Causality: dropping every bar after d leaves the verdict on dates <= d unchanged."""
    bars = _without(("2017-03-06", "2017-03-08"), ("2017-05-01", "2017-05-12"), ("2017-09-11", "2017-09-12"))
    full = _days(pc.trailing_failures(bars, SESSIONS, SPAN))
    for cut in ("2017-03-07", "2017-05-05", "2017-08-31", "2017-09-12"):
        early = _days(pc.trailing_failures(bars[bars <= cut], SESSIONS, SPAN))
        assert {d for d in early if d <= cut} == {d for d in full if d <= cut}, cut


def test_an_ipo_inside_a_span_is_cut_until_its_trailing_window_fills():
    listing = pd.Timestamp("2017-05-01")
    bars = SESSIONS[SESSIONS >= listing]
    runs = pc.trailing_failures(bars, SESSIONS, ("2017-05-01", "2018-01-01"))
    k = SESSIONS.get_loc(listing)
    assert runs == [("2017-05-01", _iso(SESSIONS[k + 56]))]   # the 57th session: 57 of 60 = 95%


# --- coverage_entry ---------------------------------------------------------------------

def test_full_coverage_has_no_cut():
    coverage, cuts = pc.coverage_entry(SESSIONS, SESSIONS, [SPAN])
    assert cuts == []
    assert coverage == [{"span": ["2017-01-02", "2018-01-01"], "expected": len(SESSIONS),
                         "present": len(SESSIONS), "missing_runs": []}]


def test_a_long_run_gives_a_run_cut_and_trailing_cuts():
    bars = _without(("2017-03-01", "2017-03-13"))
    coverage, cuts = pc.coverage_entry(bars, SESSIONS, [SPAN])
    assert ("2017-03-01", "2017-03-14", "missing run of 9 sessions") in cuts
    assert any(reason == pc.TRAILING_REASON for _, _, reason in cuts)
    assert cuts == sorted(cuts)
    assert coverage[0]["present"] == len(SESSIONS) - 9
    assert coverage[0]["missing_runs"] == [["2017-03-01", "2017-03-14", 9]]


def test_a_short_run_is_listed_but_not_cut_as_a_run():
    bars = _without(("2017-04-03", "2017-04-04"))
    coverage, cuts = pc.coverage_entry(bars, SESSIONS, [SPAN])
    assert coverage[0]["missing_runs"] == [["2017-04-03", "2017-04-05", 2]]
    assert cuts == []


def test_a_zero_coverage_span_is_cut_whole():
    span = ("2017-02-01", "2017-05-01")
    coverage, cuts = pc.coverage_entry(None, SESSIONS, [span])
    inside = {_iso(d) for d in SESSIONS[(SESSIONS >= span[0]) & (SESSIONS < span[1])]}
    assert coverage[0]["present"] == 0 and coverage[0]["expected"] == len(inside)
    assert _days(cuts) >= inside
    assert {reason for _, _, reason in cuts} == {pc.RUN_REASON.format(n=len(inside)), pc.TRAILING_REASON}


def test_a_delisted_names_ragged_tail_never_cuts_its_earlier_history():
    bars = SESSIONS[SESSIONS <= "2017-06-15"]                # stops 11 sessions before its exit
    _, cuts = pc.coverage_entry(bars, SESSIONS, [("2017-01-02", "2017-07-01")])
    assert cuts and min(start for start, _, _ in cuts) >= "2017-06-16"


def test_spans_outside_the_store_window_produce_nothing():
    assert pc.coverage_entry(SESSIONS, SESSIONS, [("2012-01-03", "2015-06-01")]) == ([], [])
    coverage, _ = pc.coverage_entry(SESSIONS, SESSIONS, [("2012-01-03", "2015-06-01"), SPAN])
    assert [c["span"] for c in coverage] == [["2017-01-02", "2018-01-01"]]


def test_intraday_timestamps_count_as_their_date():
    stamped = pd.DatetimeIndex([d + pd.Timedelta(hours=15, minutes=30) for d in SESSIONS])
    assert pc.coverage_entry(stamped, SESSIONS, [SPAN])[1] == []
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/history_store/test_pit_coverage.py
```

Expected: FAIL — `ImportError: cannot import name 'pit_coverage' from 'alpaca_history'`.

- [ ] **Step 3: Implement `scripts/data/alpaca_history/pit_coverage.py`**

Module docstring: v190 §2.1 — the PIT store's session calendar is SPY's own daily bars (the NYSE calendar in `swingbot/core/market/session.py` starts 2018-01-01 and cannot cover 2016–2017); no whole-span verdict, because a span share would let bars missing in 2024 decide a 2017 date and push delisted names out of the mask (quant-engineer finding 1); every run is listed, runs over `MAX_MISSING_RUN` are cut, and the trailing rule reads only sessions up to the date; an IPO inside a span is cut until 57 of its trailing 60 sessions exist, which no indicator warm-up would use anyway; thresholds are frozen in `_integrity.json` and may be recalibrated only in V190-21, before any strategy result is read. Pure pandas, no `swingbot` import.

Notes the signatures leave open:

- `_days(bars) -> pd.DatetimeIndex` normalises `None` → empty, any timestamps → unique sorted dates.
- `_span_positions(sessions, span) -> np.ndarray` — integer positions of the calendar sessions with `span[0] <= s < span[1]`.
- One grouping helper serves both rules:

```python
def _group(positions, sessions: pd.DatetimeIndex, span_end: str) -> list[tuple[str, str, int]]:
    """Consecutive calendar positions -> (first session, end_excl, length)."""
    runs, start = [], None
    for i, pos in enumerate(positions):
        if start is None:
            start = pos
        last = i + 1 == len(positions) or positions[i + 1] != pos + 1
        if last:
            nxt = sessions[pos + 1].strftime("%Y-%m-%d") if pos + 1 < len(sessions) else span_end
            runs.append((sessions[start].strftime("%Y-%m-%d"), min(nxt, span_end), int(pos - start + 1)))
            start = None
    return runs
```

- `trailing_failures`: `present = sessions.isin(days).astype(int)`; `csum = present.cumsum()`; for position `i` the window count is `csum[i] - csum[i - TRAILING_SESSIONS]` (or `csum[i]` when `i < TRAILING_SESSIONS`) and its length `min(i + 1, TRAILING_SESSIONS)`; a position fails when `count / length < MIN_TRAILING_SHARE`; group the failing in-span positions with `_group` and drop the length.
- `coverage_entry` clips each span, skips `None`, builds the coverage dict and the cuts in a `_span_coverage(days, sessions, span)` helper so `coverage_entry` stays a loop and a sort.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/history_store/test_pit_coverage.py
```

Expected: `0 failed`, `0 xfailed`.

- [ ] **Step 5: Complexity gate**

```bash
cd "$WT" && python scripts/dev/complexity_gate.py
```

Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
cd "$WT" && git add scripts/data/alpaca_history/pit_coverage.py tests/history_store/test_pit_coverage.py && git commit -m "feat(alpaca-history): causal coverage cuts for the PIT store -- missing runs and the trailing-60 rule (v190)"
```

### Task V190-14: Reused-symbol detector and kept side

**Model:** opus — the MON trap: a wrong kept side lets an exit walk or a warm-up indicator read another issuer's bars, and a loose rule trims real history; the thresholds must be calibratable (V190-21) without touching the logic.

**Files:**
- Create: `scripts/data/alpaca_history/reuse.py`
- Create: `tests/history_store/test_reuse.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (pandas/numpy only; no `swingbot` import).
- Produces (used by V190-15, V190-21):
  - `MEDIAN_WINDOW = 50` — the "50-day median" of volume and price level on each side of a candidate
  - `@dataclass(frozen=True) class Thresholds: break_move: float = 0.50; break_ratio: float = 10.0; revert_sessions: int = 20; gap_sessions: int = 20; edge_sessions: int = 20`; `THRESHOLDS = Thresholds()`
  - `@dataclass(frozen=True) class Break: date: str; kind: str` — `date` is the first bar after the jump (ISO); `kind` one of `"price+volume"`, `"price"`, `"volume"`, `"move"` (stretch scan, see below), `"edge"`
  - `find_breaks(frame: pd.DataFrame | None, thresholds: Thresholds = THRESHOLDS, *, sessions_from: str | None = None) -> list[Break]` — in date order
  - `series_gaps(frame, spans: list[tuple[str, str]], reference_last: str | None, sessions: pd.DatetimeIndex, thresholds=THRESHOLDS) -> list[dict]` — each `{"kind": "start" | "end" | "reference-end", "from": iso, "to": iso_excl, "sessions": int}`, in that kind order
  - `resolve(breaks: list[Break], spans: list[tuple[str, str]], frame: pd.DataFrame, thresholds=THRESHOLDS) -> dict` — `{"trim": {"keep_from": iso | None, "keep_before": iso | None, "reason": str} | None, "breaks": [{"date", "kind", "resolution"}]}`; resolutions `"trim_after"`, `"trim_before"`, `"in_span"`, `"unresolved"` (exported as `TRIM_AFTER`, `TRIM_BEFORE`, `IN_SPAN`, `UNRESOLVED`); trim reasons `REASON_AFTER = "break after last membership end"`, `REASON_BEFORE = "break before first membership start"` (the strings V190-3's fixtures use), joined `"; "` before-first when both apply
  - The `trim` dict is exactly the `_integrity.json` per-ticker `trim` object (index § Contracts) and `pit_integrity.Integrity.trim_window` reads `(keep_from, keep_before)` from it.

**The rules (spec §2.3; Claude's call, frozen here, recalibrated only in V190-21 before any strategy result is read):**

| Rule | Definition |
|---|---|
| Candidate | bar `i >= 1` with a finite `abs(Close[i] / Close[i-1] - 1) > break_move`; a NaN or non-positive close is never a candidate |
| Edge | fewer than `edge_sessions` bars before `i` (`i < edge_sessions`) or after it (`n - 1 - i < edge_sessions`): kind `"edge"`, no further test (the no-revert test cannot run) |
| No revert | every close in `Close[i : i + revert_sessions + 1]` differs from the median of `Close[i - revert_sessions : i]` by more than `break_move` (relative); a one-bar spike and its return leg both fail this |
| Level shift | `max(a/b, b/a) >= break_ratio` for the medians of `Volume` (kind `"volume"`) or of `Close` (kind `"price"`), `MEDIAN_WINDOW` bars after (`[i, i+50)`) versus before (`[i-50, i)`); both → `"price+volume"`; a non-positive or NaN median on one side only is an infinite ratio, on both sides a ratio of 1 |
| Stretch scan | with `sessions_from` set, a non-edge, non-reverting candidate dated on or after it that has **no** level shift is still a break, kind `"move"` — "the break test runs on that stretch with priority, whatever the price or volume does" (a reuse by an issuer of similar size); before `sessions_from` the level shift stays required |
| Gaps | sessions counted on the SPY calendar `sessions` over half-open ranges: `start` = `[first bar, first membership start)`; `end` = `[last membership end, last bar + 1 day)`; `reference-end` = `[reference_last + 1 day, last bar + 1 day)`; a gap is listed when its count is `> gap_sessions`; no spans → no start/end gap; an open span (`9999-12-31`) → no end gap |
| Kept side | break dated before the first membership start → `trim_before`, `keep_from` = the latest such date; dated on or after the last membership end → `trim_after`, `keep_before` = the earliest such date; anything else (inside a span, or between two spans) → `unresolved` when it lies within `edge_sessions` bars of the frame's first or last bar (computed from `frame` and `thresholds`, whatever its kind), else `in_span`. No spans (a context symbol: SPY, an ETF) → no side can be kept: every break is `in_span` or `unresolved` |

`in_span` and `unresolved` never trim; V190-15 refuses admission for them with the break named, so the builder resolves each by hand in V190-21 — never silently.

- [ ] **Step 1: Write the failing tests**

Create `tests/history_store/test_reuse.py`:

```python
"""v190 section 2.3: the reused-symbol break test (the MON case), the
series-start/end gaps against membership and the yfinance reference, and
the kept side, which follows the membership spans -- never the break."""
import numpy as np
import pandas as pd
import pytest

from alpaca_history import reuse, store_io

SESSIONS = pd.bdate_range("2016-01-04", "2019-12-31")


def _series(n=600, start="2016-01-04", close=100.0, volume=1e6) -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=n)
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close,
                         "Volume": volume}, index=idx, dtype=float)


def _shift(frame, at: int, *, close=None, volume=None) -> pd.DataFrame:
    """From bar `at` on, the close and/or volume take a new level."""
    out = frame.copy()
    if close is not None:
        out.iloc[at:, out.columns.get_loc("Close")] = close
    if volume is not None:
        out.iloc[at:, out.columns.get_loc("Volume")] = volume
    return out


def _date(frame, i) -> str:
    return frame.index[i].strftime("%Y-%m-%d")


def test_frozen_thresholds():
    t = reuse.THRESHOLDS
    assert (t.break_move, t.break_ratio, t.revert_sessions, t.gap_sessions, t.edge_sessions) == (
        0.50, 10.0, 20, 20, 20)
    assert reuse.MEDIAN_WINDOW == 50
    assert reuse.Thresholds() == reuse.THRESHOLDS


# --- find_breaks ------------------------------------------------------------------------

def test_an_issuer_change_is_a_break():
    """MON: a $100 name trading 1M shares a day becomes an $8 name trading 20k."""
    frame = _shift(_series(), 400, close=8.0, volume=2e4)
    assert reuse.find_breaks(frame) == [reuse.Break(_date(frame, 400), "price+volume")]


def test_volume_alone_or_price_alone_is_enough():
    vol = _shift(_series(), 300, close=45.0, volume=5e4)      # -55%, 20x less volume
    assert reuse.find_breaks(vol) == [reuse.Break(_date(vol, 300), "volume")]
    price = _shift(_series(), 300, close=1000.0)              # 10x the level, same volume
    assert reuse.find_breaks(price) == [reuse.Break(_date(price, 300), "price")]


def test_a_one_bar_spike_reverts_and_is_not_a_break():
    frame = _series()
    frame.iloc[300, frame.columns.get_loc("Close")] = 300.0
    assert reuse.find_breaks(frame) == []
    assert reuse.find_breaks(frame, sessions_from=_date(frame, 0)) == []


def test_a_large_move_without_a_level_shift_is_not_a_break():
    frame = _shift(_series(), 300, close=40.0)                # -60%, price ratio 2.5, same volume
    assert reuse.find_breaks(frame) == []


def test_on_a_flagged_stretch_the_move_alone_counts():
    """Reuse by an issuer of similar size: no 10x shift, so only the stretch scan sees it."""
    frame = _shift(_series(), 300, close=40.0)
    assert reuse.find_breaks(frame, sessions_from=_date(frame, 250)) == [
        reuse.Break(_date(frame, 300), "move")]
    assert reuse.find_breaks(frame, sessions_from=_date(frame, 301)) == []


def test_moves_of_at_most_fifty_percent_are_never_candidates():
    crash = _shift(_series(), 300, close=55.0, volume=2e4)    # -45%, persistent, 50x less volume
    assert reuse.find_breaks(crash) == []
    raw_forward_split = _shift(_series(), 300, close=50.0, volume=2e6)   # exactly -50%
    assert reuse.find_breaks(raw_forward_split, sessions_from=_date(raw_forward_split, 0)) == []


def test_splits_are_adjusted_away_by_the_store():
    """A split never reaches the detector as a jump: the store is fetched with Adjustment.ALL."""
    assert store_io.ADJUSTMENT == "all"
    adjusted = _series()
    adjusted["Close"] = np.linspace(50.0, 60.0, len(adjusted))
    assert reuse.find_breaks(adjusted) == []


def test_breaks_near_either_end_are_edge_breaks():
    early = _shift(_series(), 5, close=8.0, volume=2e4)
    assert reuse.find_breaks(early) == [reuse.Break(_date(early, 5), "edge")]
    late = _shift(_series(), 590, close=8.0, volume=2e4)
    assert reuse.find_breaks(late) == [reuse.Break(_date(late, 590), "edge")]


def test_degenerate_frames_have_no_break():
    assert reuse.find_breaks(None) == []
    assert reuse.find_breaks(_series(n=0)) == []
    assert reuse.find_breaks(_series(n=1)) == []
    frame = _series()
    frame.iloc[300, frame.columns.get_loc("Close")] = np.nan
    assert reuse.find_breaks(frame) == []


# --- series_gaps ------------------------------------------------------------------------

def test_series_running_past_membership_and_reference_are_flagged():
    frame = _series(n=len(SESSIONS))                         # 2016-01-04 .. 2019-12-31
    gaps = reuse.series_gaps(frame, [("2017-01-03", "2018-06-08")], "2018-06-07", SESSIONS)
    assert [g["kind"] for g in gaps] == ["start", "end", "reference-end"]
    start, end, ref = gaps
    assert (start["from"], start["to"]) == ("2016-01-04", "2017-01-03")
    assert start["sessions"] == len(SESSIONS[SESSIONS < "2017-01-03"])
    assert (end["from"], end["to"]) == ("2018-06-08", "2020-01-01")
    assert (ref["from"], ref["to"]) == ("2018-06-08", "2020-01-01")


def test_the_gap_threshold_is_more_than_twenty_sessions():
    span_start = SESSIONS[100].strftime("%Y-%m-%d")
    twenty = _series(n=400, start=SESSIONS[80].strftime("%Y-%m-%d"))
    assert reuse.series_gaps(twenty, [(span_start, "9999-12-31")], None, SESSIONS) == []
    twenty_one = _series(n=400, start=SESSIONS[79].strftime("%Y-%m-%d"))
    assert [g["sessions"] for g in reuse.series_gaps(
        twenty_one, [(span_start, "9999-12-31")], None, SESSIONS)] == [21]


def test_no_gap_for_an_open_span_or_without_spans():
    frame = _series(n=len(SESSIONS))
    assert reuse.series_gaps(frame, [("2016-01-04", "9999-12-31")], None, SESSIONS) == []
    assert reuse.series_gaps(frame, [], None, SESSIONS) == []
    assert reuse.series_gaps(None, [("2016-01-04", "9999-12-31")], "2017-01-03", SESSIONS) == []


# --- resolve: the kept side follows the spans --------------------------------------------

MON_SPANS = [("2010-01-04", "2018-06-08")]


def test_a_break_after_the_last_membership_end_keeps_the_bars_before_it():
    frame = _series(n=len(SESSIONS))
    got = reuse.resolve([reuse.Break("2018-09-04", "price+volume")], MON_SPANS, frame)
    assert got == {"trim": {"keep_from": None, "keep_before": "2018-09-04",
                            "reason": "break after last membership end"},
                   "breaks": [{"date": "2018-09-04", "kind": "price+volume", "resolution": "trim_after"}]}


def test_a_break_before_the_first_membership_start_keeps_the_bars_after_it():
    frame = _series(n=len(SESSIONS))
    got = reuse.resolve([reuse.Break("2016-06-01", "volume")], [("2017-01-03", "9999-12-31")], frame)
    assert got["trim"] == {"keep_from": "2016-06-01", "keep_before": None,
                           "reason": "break before first membership start"}
    assert got["breaks"][0]["resolution"] == "trim_before"


def test_a_break_inside_or_between_spans_is_left_for_the_builder():
    frame = _series(n=len(SESSIONS))
    for spans in (MON_SPANS, [("2010-01-04", "2017-01-03"), ("2017-06-01", "2018-06-08")]):
        got = reuse.resolve([reuse.Break("2017-03-01", "price")], spans, frame)
        assert got["trim"] is None and got["breaks"][0]["resolution"] == "in_span"


def test_edge_breaks_resolve_by_side_or_stay_unresolved():
    frame = _series(n=len(SESSIONS))
    last = frame.index[-3].strftime("%Y-%m-%d")
    after = reuse.resolve([reuse.Break(last, "edge")], MON_SPANS, frame)
    assert after["breaks"][0]["resolution"] == "trim_after" and after["trim"]["keep_before"] == last
    inside = reuse.resolve([reuse.Break(last, "edge")], [("2010-01-04", "9999-12-31")], frame)
    assert inside["trim"] is None and inside["breaks"][0]["resolution"] == "unresolved"


def test_several_breaks_keep_the_innermost_bars():
    frame = _series(n=len(SESSIONS))
    breaks = [reuse.Break("2019-03-01", "price"), reuse.Break("2016-03-01", "volume"),
              reuse.Break("2018-09-04", "price"), reuse.Break("2016-09-01", "price")]
    got = reuse.resolve(breaks, [("2017-01-03", "2018-06-08")], frame)
    assert got["trim"] == {"keep_from": "2016-09-01", "keep_before": "2018-09-04",
                           "reason": "break before first membership start; break after last membership end"}
    assert [b["date"] for b in got["breaks"]] == ["2016-03-01", "2016-09-01", "2018-09-04", "2019-03-01"]


def test_without_spans_every_break_needs_the_builder():
    """A context symbol (SPY, an ETF) has no membership: no side can be kept automatically."""
    frame = _series(n=len(SESSIONS))
    got = reuse.resolve([reuse.Break("2017-03-01", "price"),
                         reuse.Break(frame.index[-2].strftime("%Y-%m-%d"), "edge")], [], frame)
    assert got["trim"] is None
    assert [b["resolution"] for b in got["breaks"]] == ["in_span", "unresolved"]


def test_no_break_no_trim():
    assert reuse.resolve([], MON_SPANS, _series()) == {"trim": None, "breaks": []}
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/history_store/test_reuse.py
```

Expected: FAIL — `ImportError: cannot import name 'reuse' from 'alpaca_history'`.

- [ ] **Step 3: Implement `scripts/data/alpaca_history/reuse.py`**

Module docstring: v190 §2.3 — why (MON: the yfinance reference ends at Monsanto's exit, so the vendor identity check sees nothing after the symbol's reuse); the break test runs on **every** member over the whole stored series; the gaps exist because price and volume alone miss a similar-size reuse and the ~220 `no-reference` names have no yfinance series; the kept side follows membership, so a trade open at exit walks only the member's own bars and warm-up indicators never read an earlier issuer; splits never reach the detector because the store is fetched with `Adjustment.ALL`; the detector looks forward from a candidate, which is fine because its output is a frozen data decision taken before any strategy result is read — it is never a signal; the rules table above, verbatim. No `swingbot` import.

Implement the table with small helpers so each stays well under complexity 15:

- `_ratio(a: float, b: float) -> float` — the level-shift ratio with the non-positive/NaN rules.
- `_persistent(closes: np.ndarray, i: int, thresholds) -> bool` — the no-revert rule (`np.nanmedian` of the before window; `False` when that median is not positive).
- `_shift_kind(frame, i, thresholds) -> str | None` — table-driven: `{(True, True): "price+volume", (True, False): "price", (False, True): "volume"}.get((price_shift, volume_shift))`.
- `_classify(frame, closes, i, thresholds, sessions_from) -> str | None` — edge, then persistence, then shift, then the stretch rule.
- `find_breaks` computes the move vector once (`np.errstate(divide="ignore", invalid="ignore")`) and classifies only the candidates.
- `_count(sessions, start, end_excl) -> int` for the gaps; `resolve` sorts the breaks by date, finds each break's bar position with `frame.index.normalize().searchsorted(...)` for the edge test, and builds the trim from the collected `trim_before` / `trim_after` dates.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/history_store/test_reuse.py
```

Expected: `0 failed`, `0 xfailed`.

- [ ] **Step 5: Complexity gate**

```bash
cd "$WT" && python scripts/dev/complexity_gate.py
```

Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
cd "$WT" && git add scripts/data/alpaca_history/reuse.py tests/history_store/test_reuse.py && git commit -m "feat(alpaca-history): reused-symbol break test, series gaps and the membership-side trim (v190)"
```

# Phase 7 — The frozen integrity report

### Task V190-15: `check_history_store.py --pit`: `_integrity.json` and summary

**Model:** sonnet — assembly of V190-12..V190-14 into a fixed document shape inside an existing CLI; the shape, the admission order and every reason string are fixed below, and the round-trip tests catch a mismatch with Part 1's reader.

**Files:**
- Modify: `scripts/data/check_history_store.py` (docstring, imports `:16-31`, `parse_args` `:176-184`, `main` `:187-196`; new constants and functions)
- Create: `tests/history_store/test_check_history_store_pit.py`

**Interfaces:**
- Consumes:
  - `identity.reference_path`, `identity.reference_frame(..., market_dir=None)` (V190-12); `identity.identity_check`, `identity.OK`, `identity.NO_REFERENCE` (existing)
  - `pit_coverage.STORE_START`, `STORE_END`, `STORE_END_EXCL`, `MAX_MISSING_RUN`, `TRAILING_SESSIONS`, `MIN_TRAILING_SHARE`, `expected_sessions`, `clip_span`, `coverage_entry` (V190-13)
  - `reuse.THRESHOLDS`, `Thresholds`, `find_breaks`, `series_gaps`, `resolve` (V190-14)
  - `pit_integrity.INTEGRITY_NAME`, `SCHEMA_VERSION`, `integrity_path`, `apply_trim` (V190-3); `history_store.PIT`, `store_root(store)`, `resolve_data_root(name)` (V190-2); `pit_membership.load_intervals`, `membership_file_for` (existing); `store_io.sha256_file` (existing)
- Produces (used by V190-17, V190-21, V190-22):
  - CLI: `--pit` (store_true), `--backtest-dir PATH` (default `history_store.resolve_data_root("backtest_cache_ext")`), `--results-dir PATH` (default `ROOT / "docs" / "superpowers" / "results"`); `--pit`'s `--root` default is `history_store.store_root(history_store.PIT)`. Without `--pit` the command is today's check, unchanged.
  - `build_integrity(root: Path, *, intervals: dict[str, list[tuple[str, str]]], backtest_dir: Path, thresholds: reuse.Thresholds, now: datetime) -> dict` — the `_integrity.json` document (index § Contracts shape)
  - `write_integrity(root: Path, doc: dict) -> Path` — atomic write of `<root>/_integrity.json` (`<name>.tmp` then `os.replace`), bytes `json.dumps(doc, indent=1) + "\n"` in UTF-8 with `\n` line endings; returns the path
  - `render_integrity_md(doc: dict) -> str` — the Markdown summary
  - `detector_blob(path: Path) -> str` — the git blob id (`sha1(b"blob <len>\0" + bytes)`) of the file's bytes with `\r\n` normalised to `\n`, equal to `git hash-object` under `core.autocrlf=true`
  - `context_symbols() -> list[str]` — sorted, de-duplicated `CALENDAR_TICKER`, `config.MARKET_REGIME_TICKER` and every `universe.sector_map("etfs")` symbol (called as `universe.sector_map`, so a test can monkeypatch it — the same sources `fetch_backtest_data.require_context_frames` reads, V190-6)
  - constants `DETECTORS = ("scripts/data/alpaca_history/reuse.py", "scripts/data/alpaca_history/pit_coverage.py")`, `REFERENCE_SOURCE = "backtest_cache_ext"`, `NO_BARS = "skipped: no Alpaca bars"` (equal to `fetch_alpaca_history.NO_BARS`), `NOT_FETCHED = "not fetched"`, `NO_WINDOW_BARS = "no daily bars in the store window"`, `TRIM_EMPTY = "integrity trim leaves no bars"`, `PIT_ADMITTED = ("ok", "flagged: no-reference")`, `SUMMARY_NAME = "{month}-v190-pit-integrity-report.md"` (`month` = `now` as `YYYY-MM`; V190-21 writes its own `...-v190-pit-integrity.md` beside it)
  - **Additive keys beyond the index's shape** (the V190-3 reader ignores unknown keys; `docs/claude/schema-evolution.md`): top-level `"aliases": {member: alpaca}` from the daily manifest's `alias` entries (V190-12), and per ticker `"gaps": [...]` (`reuse.series_gaps` output) — the spec's "flagged" start/end gaps must be recorded somewhere.

**The document, field by field.**

| Field | Source |
|---|---|
| `schema` | `pit_integrity.SCHEMA_VERSION` |
| `generated_at` | `now` as `%Y-%m-%dT%H:%M:%SZ` (UTC) |
| `store_start`, `store_end` | `pit_coverage.STORE_START`, `STORE_END` |
| `thresholds` | `{"max_missing_run", "trailing_sessions", "min_trailing_share"}` from `pit_coverage` plus `dataclasses.asdict(thresholds)` |
| `detector_sha` | `{rel: detector_blob(ROOT / rel) for rel in DETECTORS}` |
| `manifest_sha256` | per timeframe `store_io.sha256_file(<root>/<tf>/_manifest.json)`, `None` when absent (**constraint 1**: V190-4 compares `"daily"`) |
| `aliases` | `{t: entry["alias"]}` for daily-manifest entries carrying one |
| `no_bars` | sorted tickers whose daily-manifest status is `NO_BARS`; they get **no** `tickers` entry |
| `tickers` | one entry per ticker in `sorted(members ∪ daily-manifest tickers ∪ context_symbols())`, minus `no_bars`; `members` = the `intervals` symbols with at least one span that `pit_coverage.clip_span` keeps |

**One ticker entry.** Starts from a blank entry (`admitted False`, `reason None`, `identity None`, `identity_manifest` = the daily-manifest `status` or `None`, `reference {"source": None, "sha256": None}`, `dropped_before 0`, `first_bar`/`last_bar None`, `coverage []`, `signal_cuts []`, `trim None`, `breaks []`, `gaps []`), then:

1. No daily-manifest entry → reason `NOT_FETCHED`; stop. Status starting `skipped:` → reason = the status; stop.
2. `frame = read_frame(root, ticker, "daily")` cut to bars `<= STORE_END` (**constraint 3**: never `history_store.load`); `None` or empty → reason `NO_WINDOW_BARS`; stop.
3. Reference: `path = identity.reference_path(ticker, backtest_dir=..., market_dir=None)`; `reference = {"source": REFERENCE_SOURCE, "sha256": store_io.sha256_file(path)}` when found; `identity = identity.identity_check(frame, ref)[0].status` (re-derived; `ref` `None` → `flagged: no-reference`).
4. `dropped_before` = calendar sessions in `[STORE_START, <manifest identity["dropped_before"]>)`, `0` when the manifest identity has none (the fetcher's bars-before-reference trim, made visible).
5. `first_bar`, `last_bar` from the cut frame.
6. Coverage: `spans = intervals.get(ticker, [])`; `pit_coverage.coverage_entry(frame.index, sessions, spans or [(STORE_START, STORE_END_EXCL)])` → `coverage`, `signal_cuts` (triples as lists). A context symbol has no membership, so it is measured over the store window; its cuts are recorded and never reach a signal mask (it has no spans).
7. Reuse: `gaps = reuse.series_gaps(frame, spans, <reference's last bar date or None>, sessions, thresholds)`; `sessions_from` = the earliest `"from"` among the `end` / `reference-end` gaps, else `None`; `breaks = reuse.find_breaks(frame, thresholds, sessions_from=sessions_from)`; `resolved = reuse.resolve(breaks, spans, frame, thresholds)` → `trim`, `breaks`.
8. Admission, first match wins: `identity` not in `PIT_ADMITTED` → `f"identity re-derived: {identity}"`; a break resolved `unresolved` → `f"unresolved break {date} ({kind})"`; a break resolved `in_span` → `f"in-span break {date} ({kind}): resolve by hand"`; `trim` set and `pit_integrity.apply_trim(frame, (keep_from, keep_before))` is `None` → `TRIM_EMPTY`; otherwise `admitted True`, `reason None`. **Constraint 2**: SPY, the regime ticker and the ETFs pass through the same rules, so sound context data is admitted; a broken one is excluded with its reason and `require_context_frames` names it.

`sessions = pit_coverage.expected_sessions(read_frame(root, CALENDAR_TICKER, "daily"))` — its `ValueError` (no SPY) propagates.

**The summary** (`render_integrity_md`), sections in this order, each a helper: title `# v190 PIT store integrity report` with `generated_at`; a line stating the report is "frozen before any strategy result is read" and that `--mode update` on the store after it makes every v3 run stop with `StaleIntegrityError`; counts (tickers, admitted, excluded, no bars, aliases); thresholds table (every key of `thresholds`); manifest sha256 and detector sha tables; excluded table (ticker · reason); trims table (ticker · keep_from · keep_before · reason); breaks table (ticker · date · kind · resolution); signal-cut table (ticker · start · end_excl · reason); bars dropped before the reference (ticker · count, non-zero only); reference sources (count per source, `none` included); no-bars list with the alias table. Empty sections print `none`.

**`--pit` run** (`run_pit(args) -> int`, called first in `main` when `args.pit`): `--tickers` → print `refused: --pit reads the whole store; --tickers does not apply` and return 2; `verify_hashes(root)` problems → print each as `HASH ...`, then `refused: hash problems -- no integrity report written`, return 1; membership `intervals = pit_membership.load_intervals(pit_membership.membership_file_for("sp500_pit"))`, empty → `refused: no sp500 membership file`, return 1; `build_integrity(..., thresholds=reuse.THRESHOLDS, now=datetime.now(timezone.utc))`, a `ValueError` → `refused: <message>`, return 1; then `write_integrity`, write the summary to `results_dir / SUMMARY_NAME.format(month=...)` (`mkdir(parents=True, exist_ok=True)`, UTF-8), print `integrity: <a> admitted, <e> excluded, <n> no bars -- <path> sha256 <first 12> -- summary <md path>`, return 0.

- [ ] **Step 1: Write the failing tests**

Create `tests/history_store/test_check_history_store_pit.py`:

```python
"""v190 section 2: check_history_store.py --pit freezes the PIT store's
integrity verdict into _integrity.json -- identity re-derived against
backtest_cache_ext only, causal coverage cuts, the reused-symbol trim, the
context symbols admitted -- and the file round-trips through Part 1's reader
and training_data's PIT selection. Fixture stores under tmp_path only."""
from __future__ import annotations

import importlib.util
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from alpaca_history import pit_coverage, reuse, store_io
from swingbot import config
from swingbot.core.marketdata import history_store, pit_integrity, training_data, universe

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 25, 10, 0, tzinfo=timezone.utc)
SESSIONS = pd.bdate_range("2016-01-04", "2018-12-31")      # SPY's bars: the fixture calendar
OPEN = "9999-12-31"
NO_BARS = "skipped: no Alpaca bars"
ETFS = {"SPY": "Broad Market", "XLK": "Information Technology"}
INTERVALS = {
    "AAA": [("2010-01-04", OPEN)], "MON": [("2010-01-04", "2017-06-01")],
    "DEL": [("2012-01-03", "2017-03-01")], "GAP": [("2010-01-04", OPEN)],
    "MIS": [("2010-01-04", OPEN)], "FALL": [("2010-01-04", OPEN)],
    "INS": [("2010-01-04", OPEN)], "FB": [("2012-05-18", OPEN)],
    "NOTF": [("2016-06-01", OPEN)], "OLD": [("2005-01-03", "2014-06-02")],
}
DETECTORS = ("scripts/data/alpaca_history/reuse.py", "scripts/data/alpaca_history/pit_coverage.py")


def _load():
    spec = importlib.util.spec_from_file_location(
        "check_history_store", ROOT / "scripts" / "data" / "check_history_store.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _bars(days, close=100.0, volume=1e6) -> pd.DataFrame:
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close,
                         "Volume": volume}, index=pd.DatetimeIndex(days, name="Date"), dtype=float)


def _reissued(at: str) -> pd.DataFrame:
    """A $100, 1M-share name that becomes an $8, 20k-share name from `at` on."""
    frame = _bars(SESSIONS)
    frame.loc[frame.index >= at, "Close"] = 8.0
    frame.loc[frame.index >= at, "Volume"] = 2e4
    return frame


class PitStore:
    """Daily CSVs, references and hand-built manifests in the PIT store layout."""

    def __init__(self, tmp_path: Path):
        self.root = tmp_path / "data" / "market_data_pit"
        self.bt = tmp_path / "backtest_cache_ext"
        self.fallback = tmp_path / "market_data_daily"        # never passed to the check
        self.entries: dict[str, dict] = {}

    def add(self, ticker, frame, *, status="ok", reference=None, fallback=None, ident=None):
        path = self.root / "daily" / f"{ticker}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index_label="Date")
        for folder, ref in ((self.bt, reference), (self.fallback, fallback)):
            if ref is not None:
                folder.mkdir(parents=True, exist_ok=True)
                ref.to_csv(folder / f"{ticker}.csv", index_label="Date")
        self.entries[ticker] = {"status": status, "sha256": store_io.sha256_file(path),
                                "identity": ident or {"status": status, "dropped_before": None}}

    def skip(self, ticker, status, *, alias=None):
        self.entries[ticker] = {"status": status, "sha256": None, "identity": None,
                                **({"alias": alias} if alias else {})}

    def save(self) -> "PitStore":
        for tf in history_store.TIMEFRAMES:
            folder = self.root / tf
            folder.mkdir(parents=True, exist_ok=True)
            tickers = self.entries if tf == "daily" else {}
            (folder / "_manifest.json").write_text(json.dumps(
                {"timeframe": tf, "feed": "sip", "adjustment": "all", "hash": "h", "tickers": tickers}),
                encoding="utf-8")
        return self


def _store(tmp_path, *, spy=True) -> PitStore:
    s = PitStore(tmp_path)
    full = _bars(SESSIONS)
    if spy:
        s.add("SPY", full, reference=full)
    s.add("XLK", full, reference=full)
    late = SESSIONS[SESSIONS >= "2016-02-01"]
    s.add("AAA", _bars(late), reference=full,
          ident={"status": "ok", "median_ratio": 1.0, "overlap": len(late), "dropped_before": "2016-02-01"})
    s.add("MON", _reissued("2017-09-01"), reference=full[full.index < "2017-06-01"])
    s.add("DEL", _bars(SESSIONS[SESSIONS < "2017-03-01"]), status="flagged: no-reference")
    s.add("GAP", _bars(SESSIONS[(SESSIONS < "2017-03-01") | (SESSIONS > "2017-03-13")]),
          status="flagged: no-reference")
    s.add("MIS", full, status="flagged: price-mismatch", reference=full.assign(Close=200.0))
    s.add("FALL", full, fallback=full)                        # fetched "ok" through the old fallback
    s.add("INS", _reissued("2017-06-01"), status="flagged: no-reference")
    s.skip("FB", NO_BARS, alias="META")
    return s.save()


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("HISTORY_STORE_DIR", str(tmp_path / "watchlist_store"))
    monkeypatch.delenv("BACKTEST_CACHE_DIR", raising=False)
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "alpaca")
    monkeypatch.setattr(config, "MARKET_REGIME_TICKER", "SPY")
    monkeypatch.setattr(universe, "sector_map", lambda name: dict(ETFS) if name == "etfs" else {})
    training_data.reset()
    yield tmp_path
    training_data.reset()


def _build(chk, store):
    return chk.build_integrity(store.root, intervals=INTERVALS, backtest_dir=store.bt,
                               thresholds=reuse.THRESHOLDS, now=NOW)


@pytest.fixture
def built(env):
    chk = _load()
    store = _store(env)
    return chk, store, _build(chk, store)


# --- the document ------------------------------------------------------------------------

def test_header_thresholds_and_hashes(built):
    chk, store, doc = built
    assert (doc["schema"], doc["generated_at"]) == (pit_integrity.SCHEMA_VERSION, "2026-10-25T10:00:00Z")
    assert (doc["store_start"], doc["store_end"]) == ("2016-01-04", "2025-12-31")
    assert doc["thresholds"] == {"max_missing_run": 5, "trailing_sessions": 60, "min_trailing_share": 0.95,
                                 "break_move": 0.5, "break_ratio": 10.0, "revert_sessions": 20,
                                 "gap_sessions": 20, "edge_sessions": 20}
    for tf in history_store.TIMEFRAMES:      # V190-4 compares "daily" for freshness
        assert doc["manifest_sha256"][tf] == store_io.sha256_file(store.root / tf / "_manifest.json")


def test_detector_shas_are_the_git_blob_ids(built):
    _, _, doc = built
    assert set(doc["detector_sha"]) == set(DETECTORS)
    for rel in DETECTORS:
        want = subprocess.run(["git", "hash-object", rel], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
        assert doc["detector_sha"][rel] == want


def test_context_symbols_are_admitted(built):
    _, _, doc = built
    for symbol in ("SPY", "XLK"):
        entry = doc["tickers"][symbol]
        assert entry["admitted"] is True and entry["reason"] is None, symbol
        assert entry["reference"]["source"] == "backtest_cache_ext"
        assert entry["signal_cuts"] == [] and entry["trim"] is None


def test_mon_is_trimmed_after_its_exit(built):
    _, _, doc = built
    mon = doc["tickers"]["MON"]
    assert mon["admitted"] is True and mon["identity"] == "ok"
    assert mon["trim"] == {"keep_from": None, "keep_before": "2017-09-01",
                           "reason": "break after last membership end"}
    assert mon["breaks"] == [{"date": "2017-09-01", "kind": "price+volume", "resolution": "trim_after"}]
    assert {g["kind"] for g in mon["gaps"]} == {"end", "reference-end"}
    assert (mon["first_bar"], mon["last_bar"]) == ("2016-01-04", "2018-12-31")


def test_a_delisted_member_without_a_reference_is_admitted(built):
    _, _, doc = built
    dead = doc["tickers"]["DEL"]
    assert dead["admitted"] is True and dead["identity"] == "flagged: no-reference"
    assert dead["reference"] == {"source": None, "sha256": None}
    assert dead["signal_cuts"] == [] and dead["trim"] is None


def test_the_market_data_fallback_is_never_a_reference(built):
    _, _, doc = built
    fall = doc["tickers"]["FALL"]
    assert (fall["identity_manifest"], fall["identity"]) == ("ok", "flagged: no-reference")
    assert fall["reference"]["source"] is None and fall["admitted"] is True


def test_a_re_derived_mismatch_is_excluded_with_its_reason(built):
    _, store, doc = built
    mis = doc["tickers"]["MIS"]
    assert mis["admitted"] is False
    assert mis["reason"] == "identity re-derived: flagged: price-mismatch"
    assert mis["reference"]["sha256"] == store_io.sha256_file(store.bt / "MIS.csv")


def test_coverage_cuts_and_bars_dropped_before_the_reference(built):
    _, _, doc = built
    gap = doc["tickers"]["GAP"]
    assert ["2017-03-01", "2017-03-14", "missing run of 9 sessions"] in gap["signal_cuts"]
    assert gap["coverage"][0]["missing_runs"] == [["2017-03-01", "2017-03-14", 9]]
    assert gap["admitted"] is True
    aaa = doc["tickers"]["AAA"]
    assert aaa["dropped_before"] == len(SESSIONS[SESSIONS < "2016-02-01"])
    assert ["2016-01-04", "2016-02-01", "missing run of 20 sessions"] in aaa["signal_cuts"]


def test_an_in_span_break_waits_for_the_builder(built):
    _, _, doc = built
    ins = doc["tickers"]["INS"]
    assert ins["admitted"] is False and ins["trim"] is None
    assert ins["reason"] == "in-span break 2017-06-01 (price+volume): resolve by hand"


def test_no_bars_aliases_and_unfetched_members(built):
    _, _, doc = built
    assert doc["no_bars"] == ["FB"] and "FB" not in doc["tickers"]
    assert doc["aliases"] == {"FB": "META"}
    assert doc["tickers"]["NOTF"]["admitted"] is False
    assert doc["tickers"]["NOTF"]["reason"] == "not fetched"
    assert "OLD" not in doc["tickers"]                     # no span inside the store window


def test_the_check_never_reads_through_history_store_load(env, monkeypatch):
    """Constraint 3: history_store.load(store='pit') refuses until this very file exists."""
    chk = _load()
    store = _store(env)
    monkeypatch.setattr(history_store, "load", lambda *a, **k: pytest.fail("history_store.load called"))
    assert "MON" in _build(chk, store)["tickers"]


def test_no_spy_calendar_is_refused(env):
    chk = _load()
    with pytest.raises(ValueError, match="SPY"):
        _build(chk, _store(env, spy=False))


# --- the file and its readers ------------------------------------------------------------

def test_the_written_file_round_trips_through_the_reader(built):
    chk, store, doc = built
    path = chk.write_integrity(store.root, doc)
    assert path == store.root / pit_integrity.INTEGRITY_NAME
    assert path.read_bytes().endswith(b"\n") and b"\r\n" not in path.read_bytes()
    got = pit_integrity.load_integrity(store.root)
    assert got.doc == json.loads(json.dumps(doc))
    assert got.trim_window("MON") == (None, "2017-09-01")
    assert ("2017-03-01", "2017-03-14") in got.signal_cuts("GAP")
    assert got.exclusion("FB") == pit_integrity.NO_BARS_REASON
    assert got.exclusion("SPY") is None and got.exclusion("XLK") is None
    assert got.exclusion("MIS") == "identity re-derived: flagged: price-mismatch"


def test_training_data_selects_the_store_with_this_report_and_context_passes(built):
    """Constraints 1 and 2 end to end: fresh manifest hash, context symbols admitted."""
    import fetch_backtest_data as fbd
    chk, store, doc = built
    chk.write_integrity(store.root, doc)
    assert training_data.select("alpaca", "pit", "2025-12-31") == "alpaca"
    excluded = training_data.excluded()
    assert excluded["INS"].startswith("integrity: in-span break")
    assert {"MIS", "FB"} <= set(excluded)
    assert not {"SPY", "XLK", "MON", "DEL", "FALL", "AAA"} & set(excluded)
    fbd.require_context_frames()                           # no SystemExit
    assert training_data.load_daily("MON").index.max() < pd.Timestamp("2017-09-01")


def test_a_manifest_rewritten_after_the_freeze_is_stale(built):
    chk, store, doc = built
    chk.write_integrity(store.root, doc)
    manifest = store.root / "daily" / "_manifest.json"
    manifest.write_text(manifest.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(training_data.StaleIntegrityError):
        training_data.select("alpaca", "pit", "2025-12-31")


# --- the summary and the CLI -------------------------------------------------------------

def test_the_summary_names_every_cut_and_its_reason(built):
    chk, _, doc = built
    text = chk.render_integrity_md(doc)
    for needle in ("MIS", "identity re-derived: flagged: price-mismatch", "INS", "resolve by hand",
                   "NOTF", "not fetched", "MON", "2017-09-01", "break after last membership end",
                   "FB", "META", "missing run of 9 sessions", "break_ratio",
                   "frozen before any strategy result is read"):
        assert needle in text, needle


def _membership_csv(env) -> None:
    folder = env / "data" / "universe"
    folder.mkdir(parents=True, exist_ok=True)
    rows = ["ticker,start_date,end_date"] + [
        f"{t},{s},{'' if e == OPEN else e}" for t, spans in INTERVALS.items() for s, e in spans]
    (folder / "sp500_membership.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_main_pit_writes_the_report_and_the_summary(env, capsys):
    chk = _load()
    store = _store(env)
    _membership_csv(env)
    results = env / "results"
    argv = ["--pit", "--root", str(store.root), "--backtest-dir", str(store.bt),
            "--results-dir", str(results)]
    assert chk.main(argv) == 0
    doc = pit_integrity.load_integrity(store.root).doc
    assert doc["tickers"]["MON"]["trim"]["keep_before"] == "2017-09-01"
    summaries = list(results.glob("*-v190-pit-integrity-report.md"))
    assert len(summaries) == 1 and "MON" in summaries[0].read_text(encoding="utf-8")
    assert "admitted" in capsys.readouterr().out


def test_main_pit_refuses_a_ticker_list_and_a_damaged_store(env):
    chk = _load()
    store = _store(env)
    _membership_csv(env)
    base = ["--pit", "--root", str(store.root), "--backtest-dir", str(store.bt),
            "--results-dir", str(env / "results")]
    assert chk.main([*base, "--tickers", "MON"]) == 2
    (store.root / "daily" / "AAA.csv").write_text("Date,Close\n2016-02-01,1\n", encoding="utf-8")
    assert chk.main(base) == 1
    assert not (store.root / pit_integrity.INTEGRITY_NAME).exists()


def test_the_watchlist_check_is_unchanged_by_default():
    args = _load().parse_args([])
    assert args.pit is False and args.backtest_dir is None
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/history_store/test_check_history_store_pit.py
```

Expected: FAIL — `AttributeError: module 'check_history_store' has no attribute 'build_integrity'` (and `parse_args` has no `pit`).

- [ ] **Step 3: Implement the `--pit` mode in `scripts/data/check_history_store.py`**

- Docstring: add the `--pit` usage (`python scripts/data/check_history_store.py --pit --root data/market_data_pit --backtest-dir data/backtest_cache_ext`) and a paragraph: v190 §2 — builds and freezes `<root>/_integrity.json` (coverage cuts, vendor identity re-derived against `backtest_cache_ext` only, reused-symbol trims, the context symbols) plus a Markdown summary; it reads files directly because `history_store.load(store="pit")` refuses until the report exists; the report is built once, before any strategy result is read, and any later manifest rewrite makes it stale.
- `sys.path` gains `ROOT / "scripts" / "data"` (beside `ROOT`) so `from alpaca_history import identity, pit_coverage, reuse, store_io` resolves when the script runs directly; also import `pit_integrity`, `pit_membership`, `universe` from `swingbot.core.marketdata` and `config` from `swingbot`.
- Constants and public functions exactly as in Interfaces; `build_integrity` holds the run state in a small `@dataclass class _PitRun` (root, sessions, daily-manifest tickers, intervals, backtest_dir, thresholds) and delegates each ticker to `_ticker_entry(ticker, run) -> dict`, which itself calls `_blank_entry`, `_reference_part`, `_coverage_part`, `_reuse_part` and `_admission` — each well under complexity 15, steps 1–8 above in order.
- `parse_args` gains the three flags; `main` starts with `if args.pit: return run_pit(args)`, the rest unchanged.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/history_store/
```

Expected: `0 failed`, `0 xfailed` (`test_check_history_store.py` unchanged and green: the default mode is today's).

- [ ] **Step 5: Complexity gate**

```bash
cd "$WT" && python scripts/dev/complexity_gate.py
```

Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
cd "$WT" && git add scripts/data/check_history_store.py tests/history_store/test_check_history_store_pit.py && git commit -m "feat(history-store): check_history_store --pit freezes _integrity.json and its summary (v190)"
```

