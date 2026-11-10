# v211 — Shock-conditioned short screens, Part 2: runner level kind

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. Global Constraints, Review Focus, Parallelisation and the task ledger live in the index: [`2026-11-06-v211-shock-short-screens_0-index.md`](2026-11-06-v211-shock-short-screens_0-index.md) — every task here implicitly includes them.

**Spec:** [v209 — Market-shock detector (shadow) and shock-conditioned short screens](../specs/2026-11-05-v209-market-shock-detector-design.md) (§ Track 2 → The shared daily inputs: the declared `CONTEXT_KIND = "level"` extension; § Printed alongside each verdict for what later parts hang on these seams)

**Tasks:** V211-4 → V211-5 → V211-6, all in `.claude/worktrees/2026-11-06-v211-shock-short-screens` (created in V211-1). All three edit `scripts/backtest/screen_idea.py`, so they run in order.

**The one rule of this part:** the existing ideas take the existing path, byte for byte. `tests/backtest_scripts/test_screen_context_runner.py::PARITY_DIGESTS`, `tests/backtesting/screen/test_long_byte_identical.py`, `tests/backtest_scripts/test_screen_idea.py` and `tests/backtesting/screen/test_ideas_registry.py` pass **unedited** after every task. A red digest or golden is a stop and a report, never an update.

# Phase B — Runner level kind

### Task V211-4: Runner `CONTEXT_KIND = "level"`: idea field, level load path, `--pin-context`

**Model:** opus — a seam in the one-shot runner where a silent change to the z path re-prices every closed v174 screen; the parity pins must hold untouched.

**Files:**
- Modify: `swingbot/core/backtesting/screen/ideas/__init__.py` (module docstring, `CONTEXT_KINDS`, `Idea.context_kind`, `_context_problem`, `Idea.__post_init__`, `_load`)
- Modify: `scripts/backtest/screen_idea.py` (module docstring; `_context_frame`, new `_check_z`/`_check_level`/`_KIND_CHECKS`; `load_context`; `_universe_context`; `_context_step`; new `add_context_hashes`, `run_pin_context`, `_mode_runner`; `build_parser`; `main`)
- Create: `tests/backtest_scripts/test_screen_level_context.py`

**Interfaces:**
- Consumes: nothing from earlier v211 tasks (V211-1..3 may land in any order beside this one).
- Produces (index ledger, final):
  - `swingbot.core.backtesting.screen.ideas.CONTEXT_KINDS = ("z", "level")`
  - `Idea.context_kind: str = "z"` — the **last** dataclass field (after `family`), read from module attr `CONTEXT_KIND`; `"level"` with an empty `context` raises `ValueError`, a kind outside `CONTEXT_KINDS` raises `ValueError`.
  - `screen_idea.load_context(cache_dir, tickers, *, end=WINDOW_END, kind: str = "z") -> ContextData` — `"level"` runs `file_record`, `check_raw_index`, `load_frame`, `check_contiguous` and **not** `check_z_coverage`.
  - `screen_idea.add_context_hashes(records: Mapping[str, dict], path) -> list[str]`
  - `screen_idea.run_pin_context(args) -> int`; CLI `--pin-context` (in the `--dry-run`/`--count-only` exclusive group).
  - `screen_idea._mode_runner(args) -> Callable | None` — any later mode is added here, never as a new `main` branch.

**Why:** the spec (§ The shared daily inputs) needs a breadth fraction loaded as a context file. `trailing_z` divides by the close five bars earlier, which is `0.0` on calm days, so `check_z_coverage` refuses the file (brief T10). A level idea keeps every alignment check (raw index, SPY-session contiguity, file record, hash pin) and drops only the z-coverage floor. The pin file today holds only `TLT` and `UUP` (brief D6); `--pin-context` adds new context files to it without ever rewriting an existing entry, so V211-13 can pin `BREADTH_ATR1` and `^VIX` before shot 1.

- [ ] **Step 1: Write the failing tests** — create `tests/backtest_scripts/test_screen_level_context.py`:

```python
"""v211 CONTEXT_KIND = "level": the idea field, the level load path that
skips only the z-coverage floor, and --pin-context (never rewrites a pin)."""
import functools
import json
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import screen_idea  # noqa: E402

from swingbot.core.backtesting.screen import context as pit  # noqa: E402
from swingbot.core.backtesting.screen import verdict  # noqa: E402
from swingbot.core.backtesting.screen import ideas as ideas_pkg  # noqa: E402
from swingbot.core.backtesting.screen.ideas import CONTEXT_KINDS, IDEAS, Idea  # noqa: E402
from tests.backtesting.screen.helpers import frame, random_walk  # noqa: E402

CONTEXT_FROM = "2009-06-01"
LEVEL = ("BREADTH_ATR1", "^VIX")
SHOCK_PARAMS = {"breadth": "BREADTH_ATR1", "vix": "^VIX", "enter": 0.40,
                "release": 0.10, "side": "short"}


@pytest.fixture(autouse=True)
def fast_bootstrap(monkeypatch):
    """500 week resamples instead of 10,000: same code path, test-speed."""
    monkeypatch.setattr(screen_idea.verdict, "decide",
                        functools.partial(verdict.decide, n_resamples=500))


def _write_csv(path, df):
    df.rename_axis("Date").to_csv(path)


def _breadth(index) -> pd.DataFrame:
    """A breadth fraction that is exactly 0.0 on most sessions: 0.50 every
    40th session, 0.05 on the three after it (the z floor cannot pass it)."""
    values = np.zeros(len(index))
    values[::40] = 0.50
    for k in (1, 2, 3):
        values[k::40] = 0.05
    return frame(values, index=index, opens=values, highs=values, lows=values,
                 volumes=np.full(len(index), 400.0))


def _level_cache(tmp_path, *, tickers=("AAA", "BBB")) -> Path:
    """Stocks from 2010-01-04; SPY, TLT, UUP, ^VIX and BREADTH_ATR1 on one
    business-day calendar from 2009-06-01 (TLT/UUP because _hash_records
    spans the whole registered union); tmp_path/membership.csv."""
    cache = tmp_path / "cache"
    cache.mkdir()
    for seed, ticker in enumerate(tickers, start=1):
        _write_csv(cache / f"{ticker}.csv", random_walk(2700, seed=seed))
    spy = random_walk(2800, seed=50, start=CONTEXT_FROM)
    _write_csv(cache / "SPY.csv", spy)
    for seed, ticker in enumerate(("TLT", "UUP", "^VIX"), start=51):
        _write_csv(cache / f"{ticker}.csv", random_walk(2800, seed=seed, start=CONTEXT_FROM))
    _write_csv(cache / "BREADTH_ATR1.csv", _breadth(spy.index))
    (tmp_path / "membership.csv").write_text(
        "ticker,start_date,end_date\n" + "".join(f"{t},2000-01-01,\n" for t in tickers),
        encoding="utf-8")
    return cache


def _level_events(df, context):
    gate = context["BREADTH_ATR1"]["Close"] >= 0.40
    return pit.context_on(df.index, gate).rename("fake_level")


def _fake_level_idea(**overrides) -> Idea:
    fields = dict(name="fake_level", events=_level_events, time_cap_bars=10,
                  direction="short", params=SHOCK_PARAMS, summary="breadth >= 0.40",
                  source="test", context=LEVEL, context_kind="level")
    fields.update(overrides)
    return Idea(**fields)


@pytest.fixture
def level_registered(monkeypatch):
    idea = _fake_level_idea()
    monkeypatch.setitem(screen_idea.IDEAS, idea.name, idea)
    return idea


def _quiet(*_args, **_kwargs):
    return None


# --- the idea field -----------------------------------------------------------

def test_context_kinds_and_the_default():
    assert CONTEXT_KINDS == ("z", "level")
    assert Idea(name="x", events=lambda df: df["Close"] > 0, time_cap_bars=5).context_kind == "z"
    assert {idea.context_kind for idea in IDEAS.values()} == {"z"}


def test_a_level_idea_needs_context_and_a_known_kind():
    with pytest.raises(ValueError, match="a level context idea needs CONTEXT"):
        _fake_level_idea(context=())
    with pytest.raises(ValueError, match="context kind 'zz' is not one of"):
        _fake_level_idea(context_kind="zz")


def test_load_reads_the_module_attribute(monkeypatch):
    module = types.ModuleType("fake_level_mod")
    module.CAP, module.PARAMS, module.SUMMARY, module.SOURCE = 10, SHOCK_PARAMS, "s", "src"
    module.events, module.CONTEXT, module.CONTEXT_KIND = _level_events, LEVEL, "level"
    module.DIRECTION = "short"
    monkeypatch.setitem(sys.modules, f"{ideas_pkg.__name__}.fake_level_mod", module)
    idea = ideas_pkg._load("fake_level_mod")
    assert idea.context_kind == "level" and idea.context == LEVEL


# --- the level load path ------------------------------------------------------

def test_level_load_skips_only_the_z_coverage_floor(tmp_path):
    cache = _level_cache(tmp_path)
    with pytest.raises(pit.ContextError, match="defined z covers"):
        screen_idea.load_context(cache, ("BREADTH_ATR1",))
    data = screen_idea.load_context(cache, LEVEL, kind="level")
    assert list(data.frames) == list(LEVEL)
    breadth = data.frames["BREADTH_ATR1"]
    assert breadth.index.equals(data.calendar.index)
    assert (breadth["Close"] == 0.0).mean() > 0.5
    assert set(data.records) == set(LEVEL)


def test_level_load_keeps_the_session_check(tmp_path):
    cache = _level_cache(tmp_path)
    path = cache / "BREADTH_ATR1.csv"
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    _write_csv(path, df.drop(df.index[300]))
    with pytest.raises(pit.ContextError, match="SPY session"):
        screen_idea.load_context(cache, LEVEL, kind="level")


def test_level_load_keeps_the_raw_index_check(tmp_path):
    cache = _level_cache(tmp_path)
    path = cache / "^VIX.csv"
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df.index = df.index.tz_localize("UTC")
    _write_csv(path, df)
    with pytest.raises(pit.ContextError, match="tz-aware"):
        screen_idea.load_context(cache, LEVEL, kind="level")


def test_both_load_sites_pass_the_idea_kind(tmp_path, monkeypatch, level_registered):
    cache = _level_cache(tmp_path)
    kinds, real = [], screen_idea.load_context

    def spy(*args, **kwargs):
        kinds.append(kwargs.get("kind", "z"))
        return real(*args, **kwargs)

    monkeypatch.setattr(screen_idea, "load_context", spy)
    screen_idea._universe_context(level_registered, cache, "2019-12-31", None)
    args = types.SimpleNamespace(cache_dir=cache, end="2019-12-31",
                                 context_hashes=tmp_path / "hashes.json")
    data, reason = screen_idea._context_step(args, level_registered)
    assert reason is None and set(data.frames) == set(LEVEL)
    screen_idea._universe_context(IDEAS["bond_spike_rebound"], cache, "2019-12-31", None)
    assert kinds == ["level", "level", "z"]


# --- the pin file -------------------------------------------------------------

def _rec(sha):
    return {"sha256": sha}


def test_add_context_hashes_adds_only_the_missing_names(tmp_path):
    path = tmp_path / "hashes.json"
    path.write_text(json.dumps({"TLT": "a" * 64, "UUP": "b" * 64}, indent=2,
                               sort_keys=True) + "\n", encoding="utf-8")
    records = {"TLT": _rec("a" * 64), "UUP": _rec("b" * 64),
               "^VIX": _rec("c" * 64), "BREADTH_ATR1": _rec("d" * 64)}
    assert screen_idea.add_context_hashes(records, path) == ["BREADTH_ATR1", "^VIX"]
    expected = {"TLT": "a" * 64, "UUP": "b" * 64, "^VIX": "c" * 64, "BREADTH_ATR1": "d" * 64}
    assert path.read_text(encoding="utf-8") == json.dumps(expected, indent=2,
                                                          sort_keys=True) + "\n"


def test_add_context_hashes_never_rewrites_a_pin(tmp_path):
    path = tmp_path / "hashes.json"
    path.write_text(json.dumps({"TLT": "a" * 64}), encoding="utf-8")   # compact on purpose
    before = path.read_bytes()
    with pytest.raises(pit.ContextError, match="differs"):
        screen_idea.add_context_hashes({"TLT": _rec("f" * 64), "^VIX": _rec("c" * 64)}, path)
    assert path.read_bytes() == before
    assert screen_idea.add_context_hashes({"TLT": _rec("a" * 64)}, path) == []
    assert path.read_bytes() == before            # nothing to add: not even reformatted


def test_add_context_hashes_creates_an_absent_file(tmp_path):
    path = tmp_path / "sub" / "hashes.json"
    assert screen_idea.add_context_hashes({"UUP": _rec("b" * 64), "TLT": _rec("a" * 64)},
                                          path) == ["TLT", "UUP"]
    assert json.loads(path.read_text(encoding="utf-8")) == {"TLT": "a" * 64, "UUP": "b" * 64}


def _pin_argv(tmp_path, cache, *extra):
    return ["--idea", "fake_level", "--cache-dir", str(cache),
            "--membership", str(tmp_path / "membership.csv"),
            "--ledger", str(tmp_path / "ledger.jsonl"),
            "--results-dir", str(tmp_path / "results"),
            "--context-hashes", str(tmp_path / "hashes.json"), "--pin-context", *extra]


def _pin_existing(tmp_path, cache, names=("TLT", "UUP")):
    pinned = {t: pit.file_record(cache / f"{t}.csv")["sha256"] for t in names}
    (tmp_path / "hashes.json").write_text(json.dumps(pinned, indent=2, sort_keys=True) + "\n",
                                          encoding="utf-8")
    return pinned


def test_pin_context_adds_the_new_files_and_screens_nothing(tmp_path, monkeypatch, capsys,
                                                            level_registered):
    cache = _level_cache(tmp_path)
    pinned = _pin_existing(tmp_path, cache)
    monkeypatch.setattr(screen_idea, "screen_universe",
                        lambda *a, **k: pytest.fail("--pin-context screened"))
    assert screen_idea.main(_pin_argv(tmp_path, cache)) == 0
    out = capsys.readouterr().out
    assert "pinned BREADTH_ATR1 " in out and "pinned ^VIX " in out and "pinned TLT" not in out
    now = json.loads((tmp_path / "hashes.json").read_text(encoding="utf-8"))
    assert set(now) == {"TLT", "UUP", "BREADTH_ATR1", "^VIX"}
    assert {t: now[t] for t in pinned} == pinned
    assert now["^VIX"] == pit.file_record(cache / "^VIX.csv")["sha256"]
    assert not (tmp_path / "ledger.jsonl").exists() and not (tmp_path / "results").exists()
    assert screen_idea.main(_pin_argv(tmp_path, cache)) == 0
    assert "nothing to pin" in capsys.readouterr().out


def test_pin_context_refuses_a_changed_pinned_file(tmp_path, capsys, level_registered):
    cache = _level_cache(tmp_path)
    _pin_existing(tmp_path, cache)
    before = (tmp_path / "hashes.json").read_bytes()
    path = cache / "TLT.csv"
    path.write_bytes(path.read_bytes() + b"\n")
    assert screen_idea.main(_pin_argv(tmp_path, cache)) == 2
    err = capsys.readouterr().err
    assert err.startswith("refused: ") and "TLT.csv SHA-256" in err
    assert (tmp_path / "hashes.json").read_bytes() == before


def test_pin_context_refuses_a_missing_file(tmp_path, capsys, level_registered):
    cache = _level_cache(tmp_path)
    (cache / "^VIX.csv").unlink()
    assert screen_idea.main(_pin_argv(tmp_path, cache)) == 2
    assert "missing" in capsys.readouterr().err
    assert not (tmp_path / "hashes.json").exists()


def test_pin_context_excludes_the_other_modes():
    with pytest.raises(SystemExit) as exc:
        screen_idea.build_parser().parse_args(["--idea", "high52w", "--pin-context",
                                               "--dry-run"])
    assert exc.value.code == 2


def test_mode_runner_dispatch():
    parse = screen_idea.build_parser().parse_args
    assert screen_idea._mode_runner(parse(["--idea", "high52w"])) is None
    assert screen_idea._mode_runner(parse(["--idea", "high52w", "--count-only"])) \
        is screen_idea.run_count
    assert screen_idea._mode_runner(parse(["--idea", "high52w", "--pin-context"])) \
        is screen_idea.run_pin_context
```

- [ ] **Step 2: Run to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_level_context.py`
Expected: FAIL — `ImportError: cannot import name 'CONTEXT_KINDS'`.

- [ ] **Step 3: Implement the idea field** in `swingbot/core/backtesting/screen/ideas/__init__.py`

- Append to the module docstring: *"v211: a module with CONTEXT may also export CONTEXT_KIND ("z" default, or "level"). A "level" context is read as raw values (a breadth fraction, a VIX close): the runner loads it under the same raw-index and SPY-session checks but never z-scores it, and the v174 z diagnostics do not apply. A changed CONTEXT_KIND is a new idea with a new name."*
- `CONTEXT_KINDS = ("z", "level")` beside `ENTRY_MODES`, with a `#:` comment.
- `def _context_problem(idea: "Idea") -> str | None` returning `f"{idea.name}: context kind {idea.context_kind!r} is not one of {CONTEXT_KINDS}"` for an unknown kind or, for `"level"` with an empty `context`, `f"{idea.name}: a level context idea needs CONTEXT"`; else `None`.
- `Idea`: add `context_kind: str = "z"` as the **last** field (positional order of the existing fields unchanged). `__post_init__`: `problem = _side_problem(self) or _shape_problem(self) or _context_problem(self)`.
- `_load`: `context_kind=getattr(module, "CONTEXT_KIND", "z")`.

- [ ] **Step 4: Implement the level load path** in `scripts/backtest/screen_idea.py`

- `def _check_z(frame: pd.DataFrame, sessions: pd.DatetimeIndex, ticker: str) -> None` — exactly today's `screen_context.check_z_coverage(screen_context.trailing_z(frame["Close"]), sessions, ticker, event_start=EVENT_START)`.
- `def _check_level(frame, sessions, ticker) -> None` — a no-op; docstring: *"v211: a level context (a fraction that is 0.0 on calm days) is never z-scored, so the z-coverage floor does not apply; raw index and session contiguity were already checked."*
- `_KIND_CHECKS: dict[str, Callable] = {"z": _check_z, "level": _check_level}` (after both).
- `_context_frame(cache_dir, ticker, sessions, end, kind: str = "z")`: the existing body with the final `check_z_coverage` call replaced by `_KIND_CHECKS[kind](frame, sessions, ticker)`. Check order unchanged.
- `load_context(cache_dir, tickers, *, end=WINDOW_END, kind: str = "z")` passes `kind` to `_context_frame`.
- `_universe_context` and `_context_step` call `load_context(..., end=..., kind=idea.context_kind)`.

- [ ] **Step 5: Implement `--pin-context`** in `scripts/backtest/screen_idea.py`

- `def add_context_hashes(records: Mapping[str, dict], path) -> list[str]` — read `path` if it exists (else `{}`); for each `ticker, record` in sorted `records`: a pinned SHA different from `record["sha256"]` raises `screen_context.ContextError(f"{ticker}.csv SHA-256 {record['sha256'][:12]} differs from {pinned[ticker][:12]} pinned in {path}; a pin is never rewritten")` **before anything is written**; collect the missing names. None missing: return `[]`, file untouched. Otherwise write `json.dumps({**pinned, **added}, indent=2, sort_keys=True) + "\n"` (`mkdir(parents=True, exist_ok=True)`, `encoding="utf-8"`, `newline="\n"`) and return the added names sorted.
- `def run_pin_context(args) -> int` — `records = _hash_records(args.cache_dir)` and `added = add_context_hashes(records, args.context_hashes)` inside one `try` catching `screen_context.ContextError` → `print(f"refused: {exc}", file=sys.stderr)`, `return 2`. Print `f"pinned {t} {records[t]['sha256']} -> {args.context_hashes}"` per added name, or `f"nothing to pin: every context file is already pinned in {args.context_hashes}"`; return 0. Reads no ledger and no universe.
- `def _mode_runner(args) -> Callable[[argparse.Namespace], int] | None` — `run_count` for `args.count_only`, `run_pin_context` for `args.pin_context`, else `None`.
- `build_parser`: `mode.add_argument("--pin-context", action="store_true", help="v211: add the SHA-256 of every registered context file missing from --context-hashes; never rewrites a pinned one, screens nothing, writes nothing else")`.
- `main`: replace `if args.count_only: return run_count(args)` with `runner = _mode_runner(args)` / `if runner is not None: return runner(args)` — the same branch count.
- Module docstring, one paragraph: *"v211: an idea may declare CONTEXT_KIND = "level" (its context files load without the z-coverage floor); --pin-context adds newly registered context files to the hash pin, never rewriting a pinned one."*

- [ ] **Step 6: Run the new tests**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_level_context.py`
Expected: PASS, `0 failed`.

- [ ] **Step 7: Prove the existing paths are untouched (files unedited)**

Run each:
`python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_context_runner.py`
`python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_idea.py`
`python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py`
`python scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py`
Expected: every file `0 failed`, `0 xfailed`; `git diff --stat` lists none of these four files.

- [ ] **Step 8: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0; `main`, `_context_frame`, `load_context`, `Idea.__post_init__` no higher than baseline.

- [ ] **Step 9: Commit**

```bash
git add swingbot/core/backtesting/screen/ideas/__init__.py scripts/backtest/screen_idea.py tests/backtest_scripts/test_screen_level_context.py
git commit -m "feat(v211): screen runner CONTEXT_KIND=level load path and --pin-context (V211-4)"
```

### Task V211-5: Level branches: scope sentence, hypothesis, family overlap with context, v174 read-outs skipped

**Model:** opus — the ledger hypothesis is a one-shot, append-only record and four seams assume the v174 `z`/`series` PARAMS shape (brief D4, D5); every existing idea's text must stay byte-identical.

**Files:**
- Create: `tests/backtest_scripts/golden/hypotheses_pre_v211.json` (captured **first**, on the commit before this task's edits)
- Modify: `swingbot/core/backtesting/screen/diagnostics.py` (`scope_sentence`, new `_level_scope_sentence`)
- Modify: `scripts/backtest/screen_idea.py` (`ticker_context`, `_overlap`, `_restricted`, `with_diagnostics`, new `_level_hypothesis`, `hypothesis`, `render_results`)
- Modify: `tests/backtest_scripts/test_screen_level_context.py` (append)

**Interfaces:**
- Consumes (V211-4): `Idea.context_kind`, `load_context(..., kind="level")`; in the test file, `_level_cache`, `_fake_level_idea`, `level_registered`, `LEVEL`, `SHOCK_PARAMS`, `_quiet`.
- Produces (index ledger, final):
  - `diagnostics.scope_sentence(idea)` — for `idea.context_kind == "level"` returns the Global Constraints copy, `{enter}`/`{release}` = `idea.params["enter"]`/`["release"]` formatted `.2f`, `{cap}` = `idea.time_cap_bars`; the z branch is unchanged.
  - `screen_idea._level_hypothesis(idea) -> str` = `_short_hypothesis(idea) + f", context {', '.join(idea.context)} levels from {CONTEXT_START} (v211 shock screen). " + diagnostics.scope_sentence(idea)`; `hypothesis()` tests `context_kind == "level"` before anything else.
  - `ticker_context(...)["context"]` — the ticker's context mapping as passed (`None` for an idea without context). V211-11 reads it.
  - `_overlap` hands `ctx["context"]` to the family partner; `_restricted` returns `None` and `with_diagnostics` returns the summary object itself for a level idea; `render_results` appends `_render_context` only when `idea.context and idea.context_kind == "z"`.
  - `_context_run` is **not** changed here (V211-11 owns it).

**Why:** brief D4 — any truthy `idea.context` today forces the v174 path: `scope_sentence` indexes `params["z"]`, `["series"]`, `["lookback"]`, `["window"]` (a `KeyError` for shock PARAMS), `with_diagnostics` evaluates the idea on SPY's own calendar as if its raw mask were a shock-day mask, and `_restricted` assumes the same. D5 — `_overlap` calls the partner with `None` context, so a context partner raises. The spec's level branch gives each seam its own reading; the existing ideas never reach it.

- [ ] **Step 1: Capture the hypothesis golden on the base commit (before any edit in this task)**

Run from the worktree root:

```bash
python - <<'EOF'
import json, sys
from pathlib import Path
sys.path.insert(0, "scripts/backtest")
import screen_idea
golden = {name: screen_idea.hypothesis(idea) for name, idea in sorted(screen_idea.IDEAS.items())}
out = Path("tests/backtest_scripts/golden/hypotheses_pre_v211.json")
out.write_text(json.dumps(golden, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
               encoding="utf-8", newline="\n")
print(len(golden), sorted(golden))
EOF
```

Expected: `11` names — `high52w … range_breakdown_stop`, no `shock_*` name (V211-8/9 land after this task; a `shock_*` name means the base is wrong: stop and report). `git diff --stat` shows only the new JSON file.

- [ ] **Step 2: Write the failing tests** — append to `tests/backtest_scripts/test_screen_level_context.py`:

```python
# --- V211-5: level branches ---------------------------------------------------

from swingbot.core.backtesting.instrument import stats  # noqa: E402
from swingbot.core.backtesting.screen import diagnostics  # noqa: E402

GOLDEN = ROOT / "tests" / "backtest_scripts" / "golden" / "hypotheses_pre_v211.json"
ALWAYS = [("2000-01-01", "9999-12-31")]
LEVEL_SCOPE = (
    "Scope: a daily breadth-shock proxy (SHOCK_D: enter when BREADTH_ATR1 >= 0.40, "
    "release when BREADTH_ATR1 <= 0.10 and ^VIX closes down), not the live "
    "market-shock detector; a pass does not license the detector's labels, and a "
    "fail closes exactly this frozen definition (short only, the fixed 10-bar race) "
    "and is never re-run with a looser one.")


def test_every_pre_v211_hypothesis_is_byte_identical():
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert len(golden) == 11 and not any(name.startswith("shock_") for name in golden)
    assert {name: screen_idea.hypothesis(IDEAS[name]) for name in golden} == golden


def test_the_z_scope_sentence_is_unchanged():
    assert "UUP 5-day return z <= -2.0 vs its trailing 252 values, long only, the fixed " \
           "10-bar race" in diagnostics.scope_sentence(IDEAS["dollar_drop"])


def test_the_level_scope_sentence_is_the_frozen_copy():
    assert diagnostics.scope_sentence(_fake_level_idea()) == LEVEL_SCOPE


def test_the_level_hypothesis_names_short_context_and_scope():
    idea = _fake_level_idea()
    text = screen_idea.hypothesis(idea)
    assert text == (screen_idea._short_hypothesis(idea)
                    + ", context BREADTH_ATR1, ^VIX levels from 2009-06-01 (v211 shock "
                      "screen). " + LEVEL_SCOPE)
    assert "SHORT, entry next open, fixed 1.5/3.0 ATR race" in text
    v = screen_idea.verdict.Verdict("SCREEN-FAIL", 412, 0.01, -0.02, 0.04, 0.3, 4, {},
                                    {"exp_r": False, "ci": False, "years": False, "n": True})
    row = screen_idea.ledger_row(idea, v, "docs/x.md", "2026-11-06")
    stats.validate_ledger_row(row)
    assert row["hypothesis"] == text


def _level_inputs(tmp_path):
    cache = _level_cache(tmp_path)
    context = screen_idea.load_context(cache, LEVEL, kind="level")
    return cache, context, screen_idea.load_frame(cache / "AAA.csv")


def test_ticker_context_carries_the_context(tmp_path):
    _cache, data, df = _level_inputs(tmp_path)
    ctx = screen_idea.ticker_context(_fake_level_idea(), df, ALWAYS, data.frames)
    assert ctx["context"] is data.frames and ctx["raw"].any()
    assert screen_idea.ticker_context(IDEAS["high52w"], df, ALWAYS)["context"] is None


def test_overlap_hands_the_real_context_to_a_level_partner(tmp_path, monkeypatch):
    _cache, data, df = _level_inputs(tmp_path)
    seen = []

    def partner_events(frame_, context):
        seen.append(set(context))
        return _level_events(frame_, context)

    family = ("fake_level", "fake_level_b")
    own = _fake_level_idea(family=family)
    monkeypatch.setitem(screen_idea.IDEAS, own.name, own)
    monkeypatch.setitem(screen_idea.IDEAS, "fake_level_b",
                        _fake_level_idea(name="fake_level_b", events=partner_events,
                                         family=family))
    ctx = screen_idea.ticker_context(own, df, ALWAYS, data.frames)
    out = screen_idea._overlap(own, df, ctx)
    assert seen == [set(LEVEL)]
    assert out["own"] == out["other"] == out["both"] > 0


def test_restricted_and_z_diagnostics_skip_a_level_idea(tmp_path, monkeypatch):
    _cache, data, df = _level_inputs(tmp_path)
    idea = _fake_level_idea()
    ctx = screen_idea.ticker_context(idea, df, ALWAYS, data.frames)
    costs = {"slippage_bps": None, "commission": None}
    assert screen_idea._restricted(idea, "AAA", df, ctx, costs) is None
    monkeypatch.setattr(screen_idea.diagnostics, "compute",
                        lambda *a, **k: pytest.fail("z diagnostics ran for a level idea"))
    summary = {"verdict": None, "events": []}
    assert screen_idea.with_diagnostics(summary, [], idea, data, end="2019-12-31") is summary


def _level_argv(tmp_path, cache, *extra):
    return ["--idea", "fake_level", "--cache-dir", str(cache),
            "--membership", str(tmp_path / "membership.csv"),
            "--ledger", str(tmp_path / "ledger.jsonl"),
            "--results-dir", str(tmp_path / "results"), "--date", "2026-11-06",
            "--context-hashes", str(tmp_path / "hashes.json"), *extra]


def test_a_level_dry_run_prints_no_z_diagnostics_and_writes_nothing(tmp_path, capsys,
                                                                     level_registered):
    cache = _level_cache(tmp_path)
    assert screen_idea.main(_level_argv(tmp_path, cache, "--dry-run")) == 0
    out = capsys.readouterr().out
    assert "# v140 screen: `fake_level`" in out
    assert "## Intermarket diagnostics" not in out
    for written in ("ledger.jsonl", "results", "hashes.json"):
        assert not (tmp_path / written).exists()


def test_a_level_real_run_records_the_level_hypothesis_and_pins_four_files(
        tmp_path, level_registered):
    cache = _level_cache(tmp_path)
    assert screen_idea.main(_level_argv(tmp_path, cache)) == 0
    (row,) = stats.load_ledger(tmp_path / "ledger.jsonl")
    assert row["id"] == "screen-fake_level" and row["hypothesis"].endswith(LEVEL_SCOPE)
    assert (tmp_path / "results" / "2026-11-06-screen-fake_level.md").is_file()
    pinned = json.loads((tmp_path / "hashes.json").read_text(encoding="utf-8"))
    assert set(pinned) == {"TLT", "UUP", "BREADTH_ATR1", "^VIX"}
```

- [ ] **Step 3: Run to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_level_context.py`
Expected: FAIL — the level scope/hypothesis tests with `KeyError: 'z'`, `test_ticker_context_carries_the_context` with `KeyError: 'context'`, the overlap test with `ValueError: fake_level_b reads context ... none was loaded`; `test_every_pre_v211_hypothesis_is_byte_identical` and the V211-4 tests PASS.

- [ ] **Step 4: Implement the level scope sentence** in `swingbot/core/backtesting/screen/diagnostics.py`

- `def _level_scope_sentence(idea) -> str` returning exactly (Global Constraints copy):

```python
    p = idea.params
    return ("Scope: a daily breadth-shock proxy (SHOCK_D: enter when BREADTH_ATR1 >= "
            f"{p['enter']:.2f}, release when BREADTH_ATR1 <= {p['release']:.2f} and ^VIX "
            "closes down), not the live market-shock detector; a pass does not license "
            "the detector's labels, and a fail closes exactly this frozen definition "
            f"(short only, the fixed {idea.time_cap_bars}-bar race) and is never re-run "
            "with a looser one.")
```

- `scope_sentence(idea)`: first line `if getattr(idea, "context_kind", "z") == "level": return _level_scope_sentence(idea)`; the rest untouched. Docstring gains one line naming the v211 branch.

- [ ] **Step 5: Implement the runner branches** in `scripts/backtest/screen_idea.py`

- `ticker_context`: add `"context": context` to the returned dict (nothing reads ctx keys generically; `_control`'s `{**ctx, "raw": flags}` carries it along harmlessly).
- `_overlap`: `other = np.asarray(raw_events(partner, df, ctx.get("context")), dtype=bool)`; docstring: *"v211: the partner gets the same context frames (a level family shares CONTEXT); a partner without context ignores them."* The v182 pair (`range_breakdown_close`/`_stop`) has no context, so `_events_plain` drops the argument and its overlap is unchanged.
- `_restricted`: `if not idea.context or idea.context_kind == "level": return None`; docstring line: *"v211: a level idea's raw mask is a stock trigger, not a shock-day mask, so the restricted null does not apply."*
- `with_diagnostics`: `if not idea.context or idea.context_kind == "level" or data is None: return summary`.
- `def _level_hypothesis(idea) -> str` — the Interfaces formula; docstring: *"v211: the short text, the level context series, then the frozen scope (the ledger has no note field)."*
- `hypothesis`: `if idea.context_kind == "level": return _level_hypothesis(idea)` as the **first** test, before `if idea.context:`.
- `render_results`: `if idea.context and idea.context_kind == "z": sections.append(_render_context(idea, summary, run))`.

- [ ] **Step 6: Run the tests**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_level_context.py`
Expected: PASS, `0 failed`.

- [ ] **Step 7: Prove the existing paths are untouched (files unedited)**

Run each:
`python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_context_runner.py`
`python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_idea.py`
`python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py`
`python scripts/dev/testrun.py file tests/backtesting/screen/test_diagnostics.py`
Expected: `0 failed`, `0 xfailed`; `git diff --stat` lists none of them and no change to `PARITY_DIGESTS`.

- [ ] **Step 8: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (`hypothesis`, `render_results`, `with_diagnostics`, `scope_sentence` each stay < 15).

- [ ] **Step 9: Commit**

```bash
git add tests/backtest_scripts/golden/hypotheses_pre_v211.json swingbot/core/backtesting/screen/diagnostics.py scripts/backtest/screen_idea.py tests/backtest_scripts/test_screen_level_context.py
git commit -m "feat(v211): level branches for scope, hypothesis, family overlap; v174 read-outs skipped (V211-5)"
```

### Task V211-6: Opt-in per-ticker checkpoint for `screen_universe`

**Model:** sonnet — a bounded persistence helper on one function with a clear manifest contract; no statistics change.

**Files:**
- Modify: `scripts/backtest/screen_idea.py` (`import os`; new `CHECKPOINT_MANIFEST`, `_checkpoint_manifest`, `_Checkpoint`, `_open_checkpoint`, `_EMPTY`, `_screen_or_resume`; `screen_universe`; `build_parser`; new `_run_screens`; `main`)
- Create: `tests/backtest_scripts/test_screen_checkpoint.py`

**Interfaces:**
- Consumes (V211-4): `_mode_runner` already in `main`; nothing else.
- Produces (index ledger, final):
  - `screen_universe(idea, universe, cache_dir, *, start=WINDOW_START, end=WINDOW_END, tickers=None, out=print, context=None, checkpoint_dir: Path | None = None) -> tuple[list, Counter]` — `None` is today's behaviour, byte for byte, and writes nothing.
  - Checkpoint layout: `<checkpoint_dir>/manifest.json` = `{"idea": idea.name, "start": start, "end": end, "tickers_sha256": sha256("\n".join(names))}` (`names` = the ticker list actually screened, in order); one `<ticker>.pkl` (pickled `TickerScreen`) per finished ticker, written to `<ticker>.pkl.tmp` then `os.replace`d. A restart loads every existing pickle and skips that ticker; a manifest that differs raises `ValueError(f"checkpoint {directory} belongs to another run: ...")` **before** any ticker is screened. Empty-frame tickers are never pickled.
  - `_run_screens(args, idea, universe, data, spy) -> dict` — the summary `main` publishes (screen, `with_diagnostics`, `with_short_blocks`). **V211-11 adds `with_shock_blocks` inside this helper**, never in `main`.
  - CLI `--checkpoint-dir PATH` (default `None`). V211-13/14 pass `--checkpoint-dir data/screen_checkpoints/screen-<idea>`.

**Why:** a full PIT-universe shot is a long run; `working-conventions.md` § Long runs must checkpoint requires each finished unit (ticker) persisted as it completes, so a restart skips it. Every null draw is seeded per `(idea, ticker)` (`null.null_seed`), so a resumed ticker's `TickerScreen` is the one an uninterrupted run computes; the manifest stops a checkpoint from one idea, window or ticker list leaking into another (index Review Focus 3). The pickle is read back by the same entry point that wrote it (`screen_idea` imported in tests, `__main__` from the CLI); a checkpoint is never shared between the two.

- [ ] **Step 1: Write the failing tests** — create `tests/backtest_scripts/test_screen_checkpoint.py`:

```python
"""v211: screen_universe's opt-in per-ticker checkpoint -- a resumed run
equals an uninterrupted one, another run's checkpoint refuses, nothing is
written without --checkpoint-dir."""
import functools
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import screen_idea  # noqa: E402

from swingbot.core.backtesting.screen import verdict  # noqa: E402
from swingbot.core.backtesting.screen.ideas import IDEAS  # noqa: E402
from tests.backtesting.screen.helpers import random_walk  # noqa: E402

IDEA = IDEAS["turn_of_month"]


@pytest.fixture(autouse=True)
def fast_bootstrap(monkeypatch):
    monkeypatch.setattr(screen_idea.verdict, "decide",
                        functools.partial(verdict.decide, n_resamples=500))


def _write_csv(path, df):
    df.rename_axis("Date").to_csv(path)


def _universe(tmp_path):
    """AAA, BBB, DDD with 2010-2019 bars; CCC only after 2019 (an empty frame)."""
    cache = tmp_path / "cache"
    cache.mkdir()
    for seed, ticker in enumerate(("AAA", "BBB", "DDD"), start=1):
        _write_csv(cache / f"{ticker}.csv", random_walk(2700, seed=seed))
    _write_csv(cache / "CCC.csv", random_walk(60, seed=9, start="2020-06-01"))
    membership = tmp_path / "membership.csv"
    membership.write_text("ticker,start_date,end_date\n" + "".join(
        f"{t},2000-01-01,\n" for t in ("AAA", "BBB", "CCC", "DDD")), encoding="utf-8")
    return cache, screen_idea.load_universe(cache, membership)


def _quiet(*_args, **_kwargs):
    return None


def _same(a, b):
    assert [s.ticker for s in a] == [s.ticker for s in b]
    for x, y in zip(a, b):
        assert x.events == y.events and x.counters == y.counters
        assert x.null_outcomes == y.null_outcomes and repr(x.excess) == repr(y.excess)
        assert x.rank.equals(y.rank) and x.null_slots == y.null_slots


def test_without_a_directory_nothing_is_written(tmp_path):
    cache, universe = _universe(tmp_path)
    before = sorted(p.name for p in tmp_path.rglob("*"))
    screens, skipped = screen_idea.screen_universe(IDEA, universe, cache, out=_quiet)
    assert [s.ticker for s in screens] == ["AAA", "BBB", "DDD"]
    assert skipped == Counter({"empty_frame": 1})
    assert sorted(p.name for p in tmp_path.rglob("*")) == before


def test_a_resumed_run_equals_an_uninterrupted_run(tmp_path, monkeypatch):
    cache, universe = _universe(tmp_path)
    assert universe.cached == ["AAA", "BBB", "CCC", "DDD"]     # members_between sorts
    full, full_skipped = screen_idea.screen_universe(IDEA, universe, cache, out=_quiet)
    directory = tmp_path / "ckpt"
    real, calls = screen_idea.screen_ticker, []

    def dies_on_bbb(idea, ticker, *args, **kwargs):
        if ticker == "BBB":
            raise RuntimeError("killed")
        return real(idea, ticker, *args, **kwargs)

    monkeypatch.setattr(screen_idea, "screen_ticker", dies_on_bbb)
    with pytest.raises(RuntimeError, match="killed"):
        screen_idea.screen_universe(IDEA, universe, cache, out=_quiet, checkpoint_dir=directory)
    assert sorted(p.name for p in directory.iterdir()) == ["AAA.pkl", "manifest.json"]

    def counting(idea, ticker, *args, **kwargs):
        calls.append(ticker)
        return real(idea, ticker, *args, **kwargs)

    monkeypatch.setattr(screen_idea, "screen_ticker", counting)
    resumed, skipped = screen_idea.screen_universe(IDEA, universe, cache, out=_quiet,
                                                   checkpoint_dir=directory)
    assert calls == ["BBB", "DDD"]
    assert skipped == full_skipped
    _same(resumed, full)


def test_the_layout_and_the_manifest(tmp_path, monkeypatch):
    cache, universe = _universe(tmp_path)
    directory = tmp_path / "ckpt"
    moves, real_replace = [], screen_idea.os.replace

    def spy(src, dst):
        moves.append((Path(src).name, Path(dst).name))
        return real_replace(src, dst)

    monkeypatch.setattr(screen_idea.os, "replace", spy)
    screen_idea.screen_universe(IDEA, universe, cache, out=_quiet, checkpoint_dir=directory)
    assert sorted(p.name for p in directory.iterdir()) == [
        "AAA.pkl", "BBB.pkl", "DDD.pkl", "manifest.json"]       # CCC (empty frame) never pickled
    assert ("AAA.pkl.tmp", "AAA.pkl") in moves
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest == screen_idea._checkpoint_manifest(
        IDEA, "2010-01-01", "2019-12-31", ["AAA", "BBB", "CCC", "DDD"])
    assert set(manifest) == {"idea", "start", "end", "tickers_sha256"}
    assert manifest["idea"] == "turn_of_month" and len(manifest["tickers_sha256"]) == 64


@pytest.mark.parametrize("change", ["idea", "tickers", "end"])
def test_another_runs_checkpoint_refuses_before_screening(tmp_path, monkeypatch, change):
    cache, universe = _universe(tmp_path)
    directory = tmp_path / "ckpt"
    screen_idea.screen_universe(IDEA, universe, cache, out=_quiet, checkpoint_dir=directory)
    monkeypatch.setattr(screen_idea, "screen_ticker",
                        lambda *a, **k: pytest.fail("screened after a manifest mismatch"))
    idea = IDEAS["high52w"] if change == "idea" else IDEA
    kwargs = {"tickers": {"tickers": ["AAA"]}, "end": {"end": "2018-12-31"}}.get(change, {})
    with pytest.raises(ValueError, match="belongs to another run"):
        screen_idea.screen_universe(idea, universe, cache, out=_quiet,
                                    checkpoint_dir=directory, **kwargs)


def test_main_threads_the_checkpoint_dir(tmp_path):
    cache, _universe_ = _universe(tmp_path)
    directory = tmp_path / "ckpt"
    argv = ["--idea", "turn_of_month", "--cache-dir", str(cache),
            "--membership", str(tmp_path / "membership.csv"),
            "--ledger", str(tmp_path / "ledger.jsonl"),
            "--results-dir", str(tmp_path / "results"), "--date", "2026-11-06",
            "--dry-run", "--tickers", "AAA,BBB", "--checkpoint-dir", str(directory)]
    assert screen_idea.main(argv) == 0
    assert sorted(p.name for p in directory.iterdir()) == ["AAA.pkl", "BBB.pkl", "manifest.json"]
    assert screen_idea.build_parser().parse_args(["--idea", "high52w"]).checkpoint_dir is None


def test_a_checkpointed_dry_run_prints_the_same_doc(tmp_path, capsys):
    cache, _universe_ = _universe(tmp_path)
    base = ["--idea", "turn_of_month", "--cache-dir", str(cache),
            "--membership", str(tmp_path / "membership.csv"),
            "--ledger", str(tmp_path / "ledger.jsonl"),
            "--results-dir", str(tmp_path / "results"), "--date", "2026-11-06", "--dry-run"]
    assert screen_idea.main(base) == 0
    plain = capsys.readouterr().out
    assert screen_idea.main(base + ["--checkpoint-dir", str(tmp_path / "ckpt")]) == 0
    first = capsys.readouterr().out
    assert screen_idea.main(base + ["--checkpoint-dir", str(tmp_path / "ckpt")]) == 0
    resumed = capsys.readouterr().out
    doc = [line for line in plain.splitlines() if not line.startswith("[turn_of_month]")]
    for out in (first, resumed):
        assert [line for line in out.splitlines()
                if not line.startswith("[turn_of_month]")] == doc
```

- [ ] **Step 2: Run to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_checkpoint.py`
Expected: FAIL — `TypeError: screen_universe() got an unexpected keyword argument 'checkpoint_dir'` (and `unrecognized arguments: --checkpoint-dir` for the main tests); `test_without_a_directory_nothing_is_written` PASSES.

- [ ] **Step 3: Implement the checkpoint** in `scripts/backtest/screen_idea.py`

- `import os` and `import pickle` beside the other stdlib imports.
- `CHECKPOINT_MANIFEST = "manifest.json"`.
- `def _checkpoint_manifest(idea: Idea, start: str, end: str, names: list[str]) -> dict` — the four keys of the Interfaces block; `tickers_sha256 = hashlib.sha256("\n".join(names).encode("utf-8")).hexdigest()`.
- `class _Checkpoint` with `directory: Path | None`:
  - `load(self, ticker: str) -> TickerScreen | None` — `None` without a directory or without `<ticker>.pkl`; else `pickle.loads(path.read_bytes())`.
  - `save(self, screen: TickerScreen) -> None` — no-op without a directory; else write `pickle.dumps(screen, protocol=pickle.HIGHEST_PROTOCOL)` to `<ticker>.pkl.tmp`, then `os.replace(tmp, final)` (a kill mid-write never leaves a half pickle under the final name).
- `def _open_checkpoint(directory: Path | None, manifest: dict, out) -> _Checkpoint` — `None` → `_Checkpoint(None)`. Else `mkdir(parents=True, exist_ok=True)`; an existing `manifest.json` that differs from `manifest` raises `ValueError(f"checkpoint {directory} belongs to another run: {saved} != {manifest}")`; a missing one is written (`json.dumps(manifest, indent=2, sort_keys=True) + "\n"`). Print once via `out`: `f"[{manifest['idea']}] checkpoint {directory}: {k} ticker(s) already screened"` (`k` = count of `*.pkl`), with `flush=True` like the progress line (the `[<idea>]` prefix keeps it with the progress lines, outside the results doc).
- `_EMPTY = object()` — the empty-frame marker (a monkeypatched `screen_ticker` returning `None` in the existing tests must still be appended as today, so `None` cannot be the marker).
- `def _screen_or_resume(idea, ticker, universe, cache_dir, start, end, context, checkpoint) -> object` — `checkpoint.load(ticker)` if not `None`; else `load_frame(Path(cache_dir) / f"{ticker}.csv", start, end)`; `None` frame → `_EMPTY`; else `screen = screen_ticker(idea, ticker, df, universe.intervals.get(ticker, []), context=context)`, `checkpoint.save(screen)`, return it. The `screen_ticker` call is the same call as today (keyword `context=` only).
- `screen_universe(..., checkpoint_dir: Path | None = None)`: after `names` is built, `checkpoint = _open_checkpoint(checkpoint_dir, _checkpoint_manifest(idea, start, end, names), out)` when `checkpoint_dir` is set (pass `_Checkpoint(None)` otherwise, so the no-dir path prints nothing new); the loop body becomes `result = _screen_or_resume(...)`, then `skipped["empty_frame"] += 1` if `result is _EMPTY` else `screens.append(result)`; the progress print is unchanged. Docstring: one line for v211.
- `build_parser`: `p.add_argument("--checkpoint-dir", type=Path, default=None, help="v211: persist each finished ticker's screen here; a restart skips them (refuses another run's checkpoint)")`.
- `def _run_screens(args, idea: Idea, universe: Universe, data, spy) -> dict` — moves from `main`: the `tickers` split, the `screen_universe(...)` call (now also `checkpoint_dir=args.checkpoint_dir`), `with_diagnostics(summarise(screens, skipped), ...)` and `with_short_blocks(...)`; returns the summary.
- `main`: the tail becomes `return publish(args, idea, universe, _run_screens(args, idea, universe, data, spy), rows, data=data)` — two conditional expressions leave `main` (its CC drops).

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_checkpoint.py`
Expected: PASS, `0 failed`.

- [ ] **Step 5: Prove the existing paths are untouched (files unedited)**

Run each:
`python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_context_runner.py`
`python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_idea.py`
`python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_level_context.py`
`python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py`
Expected: `0 failed`, `0 xfailed`; the mutation tests that patch `screen_universe` (`test_context_mutation_refuses_before_any_publication_write`) still refuse, because `_run_screens` looks `screen_universe` up at call time.

- [ ] **Step 6: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0; `screen_universe` and `main` no higher than baseline.

- [ ] **Step 7: Commit**

```bash
git add scripts/backtest/screen_idea.py tests/backtest_scripts/test_screen_checkpoint.py
git commit -m "feat(v211): opt-in per-ticker checkpoint for the screen runner (V211-6)"
```
