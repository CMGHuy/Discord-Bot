# v222 — Market-shock detector: index + VIX entry path — Part 2: Stage 2 intraday confirmation (V222-6..V222-8)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** bot patch
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md`](../specs/2026-11-09-v222-shock-index-vix-path-design.md)
**Index:** [`2026-11-09-v222-shock-index-vix-path_0-index.md`](2026-11-09-v222-shock-index-vix-path_0-index.md) — Goal, Architecture, **Global Constraints** (frozen survival rule, Stage 2 day list, the SPY-half reading and "only Alpaca fixtures count") and the task ledger live there; every task below implicitly includes them.

## Parallelisation

See the index. Inside this part: V222-6 and V222-7 touch disjoint files and share no
contract (V222-7 reads fixture JSON, never imports the builder), so they may run in
parallel with each other and with Part 1's code tasks. V222-8 needs both, and V222-5's
frozen `M/data/v222/stage2_days.json` (gate 1 passed).

Conventions for every task in this part (same as Part 1):

- `W` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector`
  (code, tests, commits on branch `2026-11-05-v209-market-shock-detector`).
- `M` = `E:/Documents/Private/Projects/Discord-Bot` (main tree: the spec's `## Results`,
  and the gitignored stage data in `M/data/v222/`).
- Never `cd`; run tests by the absolute path of `W`'s runner, e.g.
  `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scripts/test_build_shock_replay_fixture.py`.
- **Nothing in this part opens 2026-11-05's outcome.** The builder's 2026-11-05 default
  stays byte-identical and is only exercised through synthetic test frames; the
  evaluator refuses a day list that contains 2026-11-05.

# Phase 2 — Stage 2 intraday confirmation

### Task V222-6: Fixture builder parameterised by session date (DST, optional VIX anchor)

**Model:** sonnet — one existing script gains a session parameter with stubbed network seams; no `swingbot/core` change.

Split: this task makes the builder's library functions session-aware; V222-6b adds the
CLI flags and output paths on top of it.

**Files:**
- Modify: `.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/data/build_shock_replay_fixture.py`
- Modify: `.claude/worktrees/2026-11-05-v209-market-shock-detector/tests/scripts/test_build_shock_replay_fixture.py`

**Interfaces:**
- Consumes (exist on the v209 branch): `swingbot.core.market.session.US_MARKET_TZ`, `RTH_OPEN`, `session_close(d) -> time` (13:00 ET on a half-day, else 16:00); `alpaca_history.fetch.fetch_raw(provider, ticker, timeframe, start, end, *, limiter)`; `shock_scan.build_snapshot(...)` (computes `minutes_since_open` from the ET open, so it is already DST-correct).
- Produces (for V222-6b, V222-8):
  - `VixAnchor(at: datetime, level: float, chg_pct: float)` — frozen dataclass, `at` tz-aware UTC.
  - `SessionSpec(day: date, open_utc: datetime, close_utc: datetime, turn_utc: datetime, daily_start: date, vix_anchor: VixAnchor | None)` — frozen dataclass.
  - `session_spec(day: date, vix_anchor: VixAnchor | None = None, daily_start: date | None = None) -> SessionSpec` — open 09:30 ET and close `session_close(day)` ET as UTC; `turn_utc = open_utc + 6 min`; `daily_start` defaults to `day - 130 days`.
  - `DEFAULT_SPEC = session_spec(date(2026, 11, 5), VixAnchor(15:20 UTC, 21.13, 27.21), daily_start=date(2026, 7, 1))`; the old constants (`SESSION`, `OPEN_UTC`, `CLOSE_UTC`, `TURN_UTC`, `VIX_TAPE_*`, `VIX_PRIOR`, `DAILY_START`) stay, derived from it.
  - keyword `spec: SessionSpec = DEFAULT_SPEC` (last positional-or-keyword parameter) on `step_times`, `vix_path`, `fixture_step`, `synthetic_steps`, `load_or_fetch`, `long_entries`, `_fetch_all`, `_synthetic_fixture`; keyword-only `spec=DEFAULT_SPEC` on `build_fixture`.
  - Fixture dict for a non-default spec gains two keys after `steps`: `"session": "<iso>"`, `"vix_anchor": None | {"at", "level", "chg_pct"}`; `vix_interpolated` is `True` only with an anchor; with no anchor every step's `vix` is `{"level": None, "chg_pct": None}`.

**Byte-identity rule.** With `DEFAULT_SPEC` the fixture is the same bytes as before: same
keys in the same order (`source, vix_interpolated, note, steps`, then `main` adds
`long_entries`), same note text, same VIX formula and float order, no new key. Do **not**
rebuild or open `tests/fixtures/shock_replay_2026_11_05.json` (nothing reads 2026-11-05
before V222-13); the tests pin the default through synthetic frames and the existing
literal VIX values.

- [ ] **Step 1: Write the failing tests**

Append to `W/tests/scripts/test_build_shock_replay_fixture.py` (change the datetime import
to `from datetime import date, datetime, timedelta, timezone`; keep every existing test
unchanged):

```python
def D(day, h, m):
    return datetime(day.year, day.month, day.day, h, m, tzinfo=UTC)


def _daily_to(end_day, close=100.0, n=30):
    idx = pd.date_range(end=f"{end_day} 05:00", periods=n, freq="B", tz=UTC)
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": 1000}, index=idx)


def test_session_spec_follows_new_york_daylight_saving():
    est = bsr.session_spec(date(2026, 11, 5))
    assert (est.open_utc, est.close_utc, est.turn_utc) == (T(14, 30), T(21, 0), T(14, 36))
    friday = date(2026, 3, 6)                       # EST; DST starts 2026-03-08
    assert bsr.session_spec(friday).open_utc == D(friday, 14, 30)
    monday = date(2026, 3, 9)                       # EDT
    dst = bsr.session_spec(monday)
    assert (dst.open_utc, dst.close_utc, dst.turn_utc) == (
        D(monday, 13, 30), D(monday, 20, 0), D(monday, 13, 36))
    assert dst.daily_start == monday - timedelta(days=130) and dst.vix_anchor is None


def test_a_half_day_closes_at_one_pm_new_york():
    day = date(2025, 11, 28)                        # Friday after Thanksgiving, EST
    spec = bsr.session_spec(day)
    assert spec.close_utc == D(day, 18, 0)
    steps = bsr.step_times(spec)
    assert (steps[0], steps[-1], len(steps)) == (D(day, 14, 45), D(day, 18, 0), 14)


def test_the_default_spec_is_the_frozen_replay_day():
    spec = bsr.DEFAULT_SPEC
    assert (spec.day, spec.daily_start) == (date(2026, 11, 5), date(2026, 7, 1))
    assert spec.vix_anchor == bsr.VixAnchor(T(15, 20), 21.13, 27.21)
    assert bsr.step_times() == bsr.step_times(spec)
    assert (bsr.OPEN_UTC, bsr.CLOSE_UTC, bsr.TURN_UTC) == (T(14, 30), T(21, 0), T(14, 36))


def test_steps_on_a_daylight_saving_day_start_an_hour_earlier_in_utc():
    day = date(2020, 3, 16)
    steps = bsr.step_times(bsr.session_spec(day))
    assert (steps[0], steps[-1], len(steps)) == (D(day, 13, 45), D(day, 20, 0), 26)


def test_no_anchor_means_no_vix_at_any_step():
    spec = bsr.session_spec(date(2020, 3, 16))
    assert bsr.vix_path(D(spec.day, 15, 0), spec) == {"level": None, "chg_pct": None}


def test_an_anchor_on_another_day_interpolates_from_that_open():
    day = date(2020, 3, 16)
    spec = bsr.session_spec(day, bsr.VixAnchor(D(day, 14, 30), 80.0, 25.0))
    assert bsr.vix_path(D(day, 13, 30), spec) == {"level": 64.0, "chg_pct": 0.0}
    assert bsr.vix_path(D(day, 14, 0), spec)["chg_pct"] == pytest.approx(12.5)
    assert bsr.vix_path(D(day, 19, 0), spec) == {"level": 80.0, "chg_pct": 25.0}


def test_a_step_on_a_daylight_saving_day_uses_the_new_york_open(monkeypatch):
    monkeypatch.setattr("swingbot.core.marketdata.asset_class.classify",
                        lambda t: "etf" if t in ("SPY", "QQQ") else "equity")
    day = date(2020, 3, 16)
    spec = bsr.session_spec(day)
    daily = {"AAA": bsr.to_daily(_daily_to("2020-03-13", 100.0)),
             "SPY": bsr.to_daily(_daily_to("2020-03-13", 500.0))}
    bars = {"AAA": _m15([99.0, 97.0], D(day, 13, 30)),
            "SPY": _m15([498.0, 495.0], D(day, 13, 30))}
    step = bsr.fixture_step(D(day, 14, 0), daily, bars, {"AAA": "Tech"}, spec)
    assert step["minutes_since_open"] == 30.0 and step["spy"]["last"] == 495.0
    assert step["spy"]["prev_close"] == 500.0
    assert step["vix"] == {"level": None, "chg_pct": None}


def test_load_or_fetch_asks_for_the_spec_windows(tmp_path, monkeypatch):
    calls = []

    def fake_fetch(provider, ticker, timeframe, start, end, *, limiter):
        calls.append((timeframe, start, end))
        return None

    monkeypatch.setattr(bsr, "fetch_raw", fake_fetch)
    day = date(2020, 3, 16)
    bsr.load_or_fetch("AAA", None, None, tmp_path, bsr.session_spec(day))
    assert calls == [("daily", day - timedelta(days=130), datetime(2020, 3, 16, tzinfo=UTC)),
                     ("15min", day, D(day, 20, 0))]
    calls.clear()
    bsr.load_or_fetch("BBB", None, None, tmp_path)
    assert calls == [("daily", date(2026, 7, 1), datetime(2026, 11, 5, tzinfo=UTC)),
                     ("15min", date(2026, 11, 5), T(21, 0))]


def test_long_entries_follow_the_spec_turn_and_close():
    trades = [{"ticker": "A", "direction": "bullish", "opened_at": "2020-03-16T13:40:00+00:00"},
              {"ticker": "B", "direction": "bullish", "opened_at": "2020-03-16T13:30:00+00:00"},
              {"ticker": "C", "direction": "bullish", "opened_at": "2020-03-16T20:05:00+00:00"}]
    assert bsr.long_entries(trades, bsr.session_spec(date(2020, 3, 16))) == [
        {"ticker": "A", "opened_at": "2020-03-16T13:40:00+00:00"}]


def test_the_default_synthetic_fixture_keeps_the_old_keys():
    fx = bsr._synthetic_fixture("why")
    assert list(fx) == ["source", "vix_interpolated", "note", "steps"]
    assert fx["vix_interpolated"] is True


def test_a_session_fixture_records_its_day_and_anchor():
    day = date(2020, 3, 16)
    bare = bsr._synthetic_fixture("why", bsr.session_spec(day))
    assert list(bare) == ["source", "vix_interpolated", "note", "steps", "session", "vix_anchor"]
    assert (bare["session"], bare["vix_anchor"], bare["vix_interpolated"]) == (
        "2020-03-16", None, False)
    assert bare["steps"][0]["as_of"] == "2020-03-16T13:45:00+00:00"
    anchored = bsr._synthetic_fixture(
        "why", bsr.session_spec(day, bsr.VixAnchor(D(day, 14, 30), 80.0, 25.0)))
    assert anchored["vix_interpolated"] is True
    assert anchored["vix_anchor"] == {"at": "2020-03-16T14:30:00+00:00", "level": 80.0,
                                      "chg_pct": 25.0}
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scripts/test_build_shock_replay_fixture.py`
Expected: FAIL — `AttributeError: module 'build_shock_replay_fixture' has no attribute 'session_spec'` (and the other new names); the nine existing tests still pass.

- [ ] **Step 3: Implement**

In `W/scripts/data/build_shock_replay_fixture.py`:

1. Imports: `from dataclasses import asdict, dataclass`; `from datetime import date, datetime, time, timedelta, timezone`; `from swingbot.core.market import session, shock  # noqa: E402`.

2. Replace the block from `UTC = timezone.utc` through `vix_path` (lines 45-82) with:

```python
UTC = timezone.utc
STEP = timedelta(minutes=15)
TURN_AFTER_OPEN = timedelta(minutes=6)
DAILY_LOOKBACK = timedelta(days=130)


@dataclass(frozen=True)
class VixAnchor:
    at: datetime
    level: float
    chg_pct: float


@dataclass(frozen=True)
class SessionSpec:
    day: date
    open_utc: datetime
    close_utc: datetime
    turn_utc: datetime
    daily_start: date
    vix_anchor: VixAnchor | None


def _ny_to_utc(day: date, at: time) -> datetime:
    return datetime.combine(day, at, tzinfo=session.US_MARKET_TZ).astimezone(UTC)


def session_spec(day: date, vix_anchor: VixAnchor | None = None,
                 daily_start: date | None = None) -> SessionSpec:
    """Open 09:30 and the official close in New York time, as UTC (DST-aware)."""
    open_utc = _ny_to_utc(day, session.RTH_OPEN)
    return SessionSpec(day=day, open_utc=open_utc,
                       close_utc=_ny_to_utc(day, session.session_close(day)),
                       turn_utc=open_utc + TURN_AFTER_OPEN,
                       daily_start=daily_start or day - DAILY_LOOKBACK,
                       vix_anchor=vix_anchor)


SESSION = date(2026, 11, 5)


def _at(h: int, m: int) -> datetime:
    return datetime(SESSION.year, SESSION.month, SESSION.day, h, m, tzinfo=UTC)


DEFAULT_SPEC = session_spec(SESSION, VixAnchor(_at(15, 20), 21.13, 27.21),
                            daily_start=date(2026, 7, 1))
OPEN_UTC = DEFAULT_SPEC.open_utc
CLOSE_UTC = DEFAULT_SPEC.close_utc
TURN_UTC = DEFAULT_SPEC.turn_utc
VIX_TAPE_AT = DEFAULT_SPEC.vix_anchor.at
VIX_TAPE_LEVEL = DEFAULT_SPEC.vix_anchor.level
VIX_TAPE_CHG = DEFAULT_SPEC.vix_anchor.chg_pct
VIX_PRIOR = VIX_TAPE_LEVEL / (1 + VIX_TAPE_CHG / 100)
DAILY_START = DEFAULT_SPEC.daily_start
DEFAULT_OUT = ROOT / "tests/fixtures/shock_replay_2026_11_05.json"
DEFAULT_CACHE = ROOT / "market_data/shock_replay_2026_11_05"
BENCHMARKS = ("SPY", "QQQ")
RATE_PER_MINUTE = 120
SYNTH_SECTORS = ("Information Technology", "Financials", "Health Care", "Industrials",
                 "Consumer Discretionary")
_COLS = ["open", "high", "low", "close", "volume"]
NO_VIX = {"level": None, "chg_pct": None}


def step_times(spec: SessionSpec = DEFAULT_SPEC) -> list[datetime]:
    out, t = [], spec.open_utc + STEP
    while t <= spec.close_utc:
        out.append(t)
        t += STEP
    return out


def vix_path(t: datetime, spec: SessionSpec = DEFAULT_SPEC) -> dict:
    anchor = spec.vix_anchor
    if anchor is None:
        return dict(NO_VIX)
    frac = min(1.0, max(0.0, (t - spec.open_utc) / (anchor.at - spec.open_utc)))
    chg = anchor.chg_pct * frac
    prior = anchor.level / (1 + anchor.chg_pct / 100)
    return {"level": round(prior * (1 + chg / 100), 4), "chg_pct": round(chg, 4)}
```

`vix_path` keeps the old float order for the default, so
`test_vix_path_climbs_to_the_tape_reading_then_holds` stays green unchanged.

3. Thread `spec` through (bodies otherwise unchanged):

```python
def _minutes_since_open(t: datetime, spec: SessionSpec = DEFAULT_SPEC) -> float:
    return (t - spec.open_utc).total_seconds() / 60.0


def fixture_step(t: datetime, daily: dict, bars15: dict, sector_of: Mapping[str, str],
                 spec: SessionSpec = DEFAULT_SPEC) -> dict:
    live = {tk: v for tk in daily if (v := last_at(bars15.get(tk), t)) is not None}
    snap = shock_scan.build_snapshot(
        daily, live, sector_of, now=t, quotes_at=t,
        vix=shock.VixTape(None, None, None), th=shock.ShockThresholds(),
        spy_ticker="SPY", spy_df=daily.get("SPY"))
    return {"as_of": t.isoformat(), "minutes_since_open": round(snap.minutes_since_open, 4),
            "vix": vix_path(t, spec), "spy": _round_row(snap.spy), "qqq": _round_row(snap.qqq),
            "names": [_round_row(n) for n in sorted(snap.names, key=lambda n: n.ticker)]}


def synthetic_steps(spec: SessionSpec = DEFAULT_SPEC) -> list[dict]:
    spy = {"ticker": "SPY", "sector": None, "last": 494.0, "prev_close": 500.0,
           "atr14": 5.0, "is_equity": False}
    qqq = {"ticker": "QQQ", "sector": None, "last": 391.0, "prev_close": 400.0,
           "atr14": 6.0, "is_equity": False}
    return [{"as_of": t.isoformat(), "minutes_since_open": _minutes_since_open(t, spec),
             "vix": vix_path(t, spec), "spy": spy, "qqq": qqq,
             "names": _synth_names(_minutes_since_open(t, spec))} for t in step_times(spec)]


def load_or_fetch(ticker, provider, limiter, cache_dir: Path, spec: SessionSpec = DEFAULT_SPEC):
    path = Path(cache_dir) / f"{ticker}.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        return _frame(data["daily"]), _frame(data["m15"])
    daily = fetch_raw(provider, ticker, "daily", spec.daily_start,
                      datetime.combine(spec.day, time(0), tzinfo=UTC), limiter=limiter)
    m15 = fetch_raw(provider, ticker, "15min", spec.day, spec.close_utc, limiter=limiter)
    _atomic_write(path, {"daily": _rows(daily), "m15": _rows(m15)})
    return daily, m15


def long_entries(trades: list[dict], spec: SessionSpec = DEFAULT_SPEC) -> list[dict]:
    keep = [t for t in trades if t.get("direction") == "bullish"
            and spec.turn_utc <= datetime.fromisoformat(t["opened_at"]) < spec.close_utc]
    keep.sort(key=lambda t: datetime.fromisoformat(t["opened_at"]))
    return [{"ticker": t["ticker"], "opened_at": t["opened_at"]} for t in keep]
```

`_fetch_all(tickers, provider, limiter, cache_dir, spec=DEFAULT_SPEC)` passes `spec` to
`load_or_fetch`.

4. Provenance, notes and the two fixture builders (replace `_synthetic_fixture` and
   `build_fixture`):

```python
def _provenance(spec: SessionSpec) -> dict:
    """Extra keys for a non-default session; none for DEFAULT_SPEC (byte-identical)."""
    if spec == DEFAULT_SPEC:
        return {}
    a = spec.vix_anchor
    anchor = None if a is None else {"at": a.at.isoformat(), "level": a.level,
                                     "chg_pct": a.chg_pct}
    return {"session": spec.day.isoformat(), "vix_anchor": anchor}


def _vix_note(spec: SessionSpec) -> str:
    a = spec.vix_anchor
    if a is None:
        return "no VIX anchor: VIX absent at every step, so the VIX half is unconfirmed"
    return (f"VIX interpolated linearly from the {a.at:%H:%M} UTC anchor "
            f"({a.level}, {a.chg_pct:+.2f}%)")


def _alpaca_note(spec: SessionSpec, n: int) -> str:
    if spec == DEFAULT_SPEC:
        return (f"{n} tickers with daily + 15-minute Alpaca bars; VIX interpolated "
                "linearly from the 15:20 UTC tape reading (21.13, +27.21%); long_entries "
                "comes from the trade log")
    return (f"{n} tickers with daily + 15-minute Alpaca bars; {_vix_note(spec)}; "
            "long_entries comes from the trade log")


def _synthetic_fixture(note: str, spec: SessionSpec = DEFAULT_SPEC) -> dict:
    return {"source": "synthetic", "vix_interpolated": spec.vix_anchor is not None,
            "note": note, "steps": synthetic_steps(spec), **_provenance(spec)}


def build_fixture(tickers, *, provider, limiter, cache_dir,
                  spec: SessionSpec = DEFAULT_SPEC) -> dict:
    from swingbot.core.scanning import fetch
    daily, bars15 = _fetch_all(tickers, provider, limiter, cache_dir, spec)
    both = [t for t in daily if t in bars15]
    equities = [t for t in both if asset_class.classify(t) == "equity"]
    if len(equities) < shock.ShockThresholds().min_names:
        return _synthetic_fixture(
            f"alpaca: fewer than {shock.ShockThresholds().min_names} equities with daily + "
            f"15-minute bars ({len(equities)}); synthetic sequence shaped on the day", spec)
    sector_of = fetch._sector_etfs_for_tickers(list(tickers))[0]
    daily = {t: daily[t] for t in both}
    steps = [fixture_step(t, daily, bars15, sector_of, spec) for t in step_times(spec)]
    return {"source": "alpaca", "vix_interpolated": spec.vix_anchor is not None,
            "note": _alpaca_note(spec, len(both)), "steps": steps, **_provenance(spec)}
```

`_build` and `main` are unchanged in this task (they keep calling the defaults).

- [ ] **Step 4: Run the tests**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scripts/test_build_shock_replay_fixture.py`
Expected: PASS (old and new tests, `0 failed`).

- [ ] **Step 5: Commit (v209 branch)**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector add scripts/data/build_shock_replay_fixture.py tests/scripts/test_build_shock_replay_fixture.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector commit -m "feat(v222): replay fixture builder by session spec, DST-aware, optional VIX anchor (V222-6)"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the main-tree status shows nothing from this task.

### Task V222-6b: Builder CLI `--session` / `--vix-anchor` and per-session output paths

**Model:** sonnet — argparse and path plumbing over V222-6's functions, one script, stubbed provider.

**Files:**
- Modify: `.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/data/build_shock_replay_fixture.py`
- Modify: `.claude/worktrees/2026-11-05-v209-market-shock-detector/tests/scripts/test_build_shock_replay_fixture.py`

**Interfaces:**
- Consumes (V222-6): `VixAnchor`, `SessionSpec`, `session_spec`, `DEFAULT_SPEC`, `SESSION`, `DEFAULT_OUT`, `DEFAULT_CACHE`, `ROOT`, `_synthetic_fixture(note, spec)`, `build_fixture(..., spec=)`, `long_entries(trades, spec)`; the test helper `D(day, h, m)` added in V222-6.
- Produces (for V222-8):
  - `parse_anchor(text: str, day: date) -> VixAnchor` — `"HH:MM,LEVEL,CHG"`, time in UTC; `ValueError` on any other shape.
  - `resolve_spec(args) -> SessionSpec` — `DEFAULT_SPEC` when neither flag is given, else `session_spec(args.session or SESSION, anchor)`.
  - `default_paths(spec) -> tuple[Path, Path]` — `(DEFAULT_OUT, DEFAULT_CACHE)` for `DEFAULT_SPEC`, else `(ROOT/"market_data"/"shock_replay_<yyyy_mm_dd>.json", ROOT/"market_data"/"shock_replay_<yyyy_mm_dd>")`.
  - CLI: `--session YYYY-MM-DD`, `--vix-anchor HH:MM,LEVEL,CHG`, `--out`, `--cache-dir` (both default to `default_paths(spec)`), `--tickers`, `--synthetic`; a bad anchor exits `2` and writes nothing.

With neither new flag the run writes the same bytes to the same default path as before
(`--out` / `--cache-dir` now default to `None` and resolve to `DEFAULT_OUT` /
`DEFAULT_CACHE`).

- [ ] **Step 1: Write the failing tests**

Append to `W/tests/scripts/test_build_shock_replay_fixture.py`:

```python
def test_parse_anchor_reads_utc_time_level_and_change():
    day = date(2020, 3, 16)
    assert bsr.parse_anchor("14:30,80.0,25.0", day) == bsr.VixAnchor(D(day, 14, 30), 80.0, 25.0)
    for bad in ("14:30,80.0", "nope", "14-30,80,25", "14:30,x,25"):
        with pytest.raises(ValueError):
            bsr.parse_anchor(bad, day)


def test_default_paths_name_the_session():
    assert bsr.default_paths(bsr.DEFAULT_SPEC) == (bsr.DEFAULT_OUT, bsr.DEFAULT_CACHE)
    out, cache = bsr.default_paths(bsr.session_spec(date(2020, 3, 16)))
    assert out == bsr.ROOT / "market_data" / "shock_replay_2020_03_16.json"
    assert cache == bsr.ROOT / "market_data" / "shock_replay_2020_03_16"


def test_no_flag_resolves_to_the_default_spec():
    assert bsr.resolve_spec(bsr._parse([])) is bsr.DEFAULT_SPEC
    args = bsr._parse(["--session", "2020-03-16"])
    assert bsr.resolve_spec(args) == bsr.session_spec(date(2020, 3, 16))


def test_the_default_run_writes_exactly_the_old_keys_and_note(tmp_path, monkeypatch):
    _, fx = _run(tmp_path, monkeypatch, FakeProvider())
    assert list(fx) == ["source", "vix_interpolated", "note", "steps", "long_entries"]
    assert fx["note"].startswith("alpaca: fewer than 20 equities with daily + 15-minute bars (")
    assert fx["note"].endswith("); synthetic sequence shaped on the day")
    assert [s["as_of"] for s in fx["steps"]] == [t.isoformat() for t in bsr.step_times()]


def test_a_session_run_records_its_day_and_absent_vix(tmp_path, monkeypatch):
    monkeypatch.setattr(bsr, "_trades", lambda: [])
    out = tmp_path / "fx.json"
    rc = bsr.main(["--session", "2020-03-16", "--tickers", "AAA,BBB", "--out", str(out),
                   "--cache-dir", str(tmp_path / "cache")],
                  provider=FakeProvider(), limiter=bsr.TokenBucket(10**6))
    fx = json.loads(out.read_text())
    assert rc == 0 and fx["session"] == "2020-03-16" and fx["vix_anchor"] is None
    assert fx["vix_interpolated"] is False and fx["long_entries"] == []
    assert fx["steps"][0]["as_of"] == "2020-03-16T13:45:00+00:00"
    assert all(s["vix"] == {"level": None, "chg_pct": None} for s in fx["steps"])
    assert sorted(p.stem for p in (tmp_path / "cache").glob("*.json")) == [
        "AAA", "BBB", "QQQ", "SPY"]


def test_a_session_run_with_an_anchor_records_it(tmp_path, monkeypatch):
    monkeypatch.setattr(bsr, "_trades", lambda: [])
    out = tmp_path / "fx.json"
    assert bsr.main(["--session", "2020-03-16", "--vix-anchor", "14:30,80,25", "--synthetic",
                     "--out", str(out)]) == 0
    fx = json.loads(out.read_text())
    assert fx["vix_interpolated"] is True
    assert fx["vix_anchor"] == {"at": "2020-03-16T14:30:00+00:00", "level": 80.0,
                                "chg_pct": 25.0}


def test_a_bad_anchor_exits_two_and_writes_nothing(tmp_path):
    out = tmp_path / "fx.json"
    assert bsr.main(["--session", "2020-03-16", "--vix-anchor", "nope", "--out", str(out)]) == 2
    assert not out.exists()


def test_a_bad_session_date_is_an_argparse_error():
    with pytest.raises(SystemExit) as exc:
        bsr.main(["--session", "2020-13-40"])
    assert exc.value.code == 2
```

(On the 2020-03-16 session the `FakeProvider` daily frame ends 2026-11-04 and only two
equities exist, so the run takes the synthetic path, which is all the CLI tests need.
`classify` is not stubbed, so the equity count in the default note is not pinned, only its
text around it.)

- [ ] **Step 2: Run the tests to see them fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scripts/test_build_shock_replay_fixture.py`
Expected: FAIL — `AttributeError: ... has no attribute 'parse_anchor'` / `'default_paths'` / `'resolve_spec'`, and `unrecognized arguments: --session` for the CLI tests.

- [ ] **Step 3: Implement**

In `W/scripts/data/build_shock_replay_fixture.py`:

1. Docstring: add a paragraph after the first one: "v222 V222-6/6b: `--session YYYY-MM-DD`
   builds the same fixture for any session (open and close from New York time, so DST
   and half-days are handled); `--vix-anchor HH:MM,LEVEL,CHG` (UTC) interpolates VIX
   from one tape reading, otherwise VIX is absent at every step. Non-default sessions
   write `market_data/shock_replay_<yyyy_mm_dd>.json` and cache to
   `market_data/shock_replay_<yyyy_mm_dd>/`. With neither flag the output is unchanged."
   Usage line: `python scripts/data/build_shock_replay_fixture.py [--session YYYY-MM-DD] [--vix-anchor HH:MM,LEVEL,CHG] [--tickers A,B] [--synthetic] [--out P] [--cache-dir D]`.

2. Add after `build_fixture`, and replace `_parse`, `_build` and `main` (`_tickers` and
   `_trades` stay):

```python
def parse_anchor(text: str, day: date) -> VixAnchor:
    """``HH:MM,LEVEL,CHG`` with the time in UTC; ValueError on any other shape."""
    hhmm, level, chg = text.split(",")
    hour, minute = (int(x) for x in hhmm.split(":"))
    return VixAnchor(datetime.combine(day, time(hour, minute), tzinfo=UTC),
                     float(level), float(chg))


def resolve_spec(args) -> SessionSpec:
    if args.session is None and args.vix_anchor is None:
        return DEFAULT_SPEC
    day = args.session or SESSION
    anchor = parse_anchor(args.vix_anchor, day) if args.vix_anchor else None
    return session_spec(day, anchor)


def default_paths(spec: SessionSpec) -> tuple[Path, Path]:
    if spec == DEFAULT_SPEC:
        return DEFAULT_OUT, DEFAULT_CACHE
    stem = f"shock_replay_{spec.day:%Y_%m_%d}"
    return ROOT / "market_data" / f"{stem}.json", ROOT / "market_data" / stem


def _parse(argv) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--session", default=None, type=date.fromisoformat)
    ap.add_argument("--vix-anchor", default=None)
    ap.add_argument("--tickers", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--cache-dir", default=None)
    ap.add_argument("--synthetic", action="store_true")
    return ap.parse_args(argv)


def _build(args, provider, limiter, spec: SessionSpec, cache_dir: Path) -> dict:
    if args.synthetic:
        return _synthetic_fixture(
            "--synthetic requested; synthetic sequence shaped on the day", spec)
    try:
        provider = provider or make_provider()
        limiter = limiter or TokenBucket(RATE_PER_MINUTE)
        return build_fixture(_tickers(args), provider=provider, limiter=limiter,
                             cache_dir=cache_dir, spec=spec)
    except Exception as exc:
        return _synthetic_fixture(f"alpaca unavailable: {type(exc).__name__}: {exc}; "
                                  "synthetic sequence shaped on the day", spec)


def main(argv=None, *, provider=None, limiter=None) -> int:
    args = _parse(argv)
    try:
        spec = resolve_spec(args)
    except ValueError as exc:
        print(f"bad --session / --vix-anchor: {exc}", file=sys.stderr)
        return 2
    out_default, cache_default = default_paths(spec)
    out = Path(args.out) if args.out else out_default
    cache_dir = Path(args.cache_dir) if args.cache_dir else cache_default
    fixture = _build(args, provider, limiter, spec, cache_dir)
    entries = long_entries(_trades(), spec)
    fixture["long_entries"] = entries
    if _TRADES_ERROR:
        fixture["note"] += f"; long entries unavailable: {_TRADES_ERROR[-1]}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fixture, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out}: {fixture['source']}, {len(fixture['steps'])} steps, "
          f"{len(entries)} long entries")
    return 0
```

`"14-30,80,25"` fails in `hhmm.split(":")` unpacking and `"14:30,x,25"` in `float("x")`;
both are `ValueError`, so `main` returns 2 before anything is fetched or written.

- [ ] **Step 4: Run the tests and the complexity gate**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scripts/test_build_shock_replay_fixture.py`
Expected: PASS (`0 failed`; the existing `_run`-based tests still pass with the `None` defaults).

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/complexity_gate.py`
Expected: exit 0 (`main` is about 6; every new function is under 5).

- [ ] **Step 5: Commit (v209 branch)**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector add scripts/data/build_shock_replay_fixture.py tests/scripts/test_build_shock_replay_fixture.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector commit -m "feat(v222): builder --session and --vix-anchor flags, per-session output paths (V222-6b)"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the main-tree status shows nothing from this task.


### Task V222-7: Intraday SPY-half evaluator and survival rule

**Model:** opus — statistical code that decides gate 2 (the survival rule); it must mirror the detector's settle, two-reading and insufficient-hold rules exactly.

Split: this task builds the per-day rule and the survival rule; V222-7b adds the day list,
fixture checks, `evaluate`, the markdown report and the CLI on top of it (same module).

**Files:**
- Create: `.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/backtest/shock_index_intraday.py`
- Create: `.claude/worktrees/2026-11-05-v209-market-shock-detector/tests/backtest_scripts/test_shock_index_intraday.py`

`tests/backtest_scripts/` is already a suite path in `tests/suites.toml`; no suite change.

**Interfaces:**
- Consumes (exist on the v209 branch): `swingbot.core.market.shock` — `NameRow(ticker, sector, last, prev_close, atr14, is_equity)`, `VixTape(level, chg_pct, as_of)`, `ShockSnapshot(as_of, session_date, minutes_since_open, names, spy, qqq, vix)`, `measure(snapshot, prev, th) -> ShockReading`, `ShockThresholds` (`open_settle_min = 15`, `min_names = 20`), `ShockReading.spy_atr_move / minutes_since_open / insufficient / as_of / session_date`. The fixture JSON written by V222-6/6b (`source`, `vix_interpolated`, `note`, `steps[]` with `as_of`, `minutes_since_open`, `vix{level,chg_pct}`, `spy`, `qqq`, `names[]`, then `session`, `vix_anchor`). It reads JSON only and never imports the builder.
- Produces (for V222-7b, V222-8):
  - `SURVIVAL_SHOCK_SHARE = 0.75`, `EXCLUDED_DAY = date(2026, 11, 5)`, `EPS = 1e-9`, `KINDS = ("shock", "quiet")`.
  - `step_readings(fx: dict, th: shock.ShockThresholds = shock.ShockThresholds()) -> list[shock.ShockReading]`
  - `spy_half_first_fire(readings, k: float, open_settle_min: int = 15) -> datetime | None`
  - `day_table(readings, k: float, open_settle_min: int = 15) -> list[dict]` (keys `as_of, minutes_since_open, spy_atr_move, settled, insufficient, meets, streak, fires`)
  - `survives(shock_fired: list[bool], quiet_fired: list[bool]) -> bool`
  - test helpers in the test module, reused by V222-7b: `SESSION`, `OPEN`, `_fx(moves, *, start_min=15, source="alpaca", session=SESSION, interpolated=False)`, `_at(minutes)`.

**The rule this task pins (index § Global Constraints, Stage 2 reading).** For a cell
`(k, v)` a day *fires* when `-spy_atr_move + 1e-9 >= k` holds on two consecutive
readings that are both settled (`minutes_since_open + 1e-9 >= 15`), exactly as
`shock._from_normal` counts `entry_streak`: a settled qualifying reading adds one, any
other sufficient reading resets the streak to 0, and an `insufficient` reading holds it
(`shock.step` returns the state unchanged for one). A missing SPY row
(`spy_atr_move is None`) never meets. The VIX half is never judged here (V222-7b reports
it as unconfirmed).

- [ ] **Step 1: Write the failing tests**

Create `W/tests/backtest_scripts/test_shock_index_intraday.py`:

```python
"""v222 V222-7: the SPY half of the index rule over frozen historical days."""
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import shock_index_intraday as sii  # noqa: E402

UTC = timezone.utc
SESSION = "2020-03-16"                                   # EDT: the open is 13:30 UTC
OPEN = datetime(2020, 3, 16, 13, 30, tzinfo=UTC)


def _name(i):
    return {"ticker": f"N{i}", "sector": "Tech", "last": 99.6, "prev_close": 100.0,
            "atr14": 2.0, "is_equity": True}


def _spy(move):
    if move is None:
        return None
    return {"ticker": "SPY", "sector": None, "last": 400.0 + 4.0 * move,
            "prev_close": 400.0, "atr14": 4.0, "is_equity": False}


def _fx(moves, *, start_min=15, source="alpaca", session=SESSION, interpolated=False):
    steps = []
    for i, move in enumerate(moves):
        minutes = start_min + 15 * i
        steps.append({"as_of": (OPEN + timedelta(minutes=minutes)).isoformat(),
                      "minutes_since_open": float(minutes),
                      "vix": {"level": None, "chg_pct": None},
                      "spy": _spy(move), "qqq": None,
                      "names": [_name(j) for j in range(25)]})
    return {"source": source, "vix_interpolated": interpolated, "note": "test",
            "steps": steps, "session": session, "vix_anchor": None}


def _at(minutes):
    return OPEN + timedelta(minutes=minutes)


def test_the_frozen_constants():
    assert sii.SURVIVAL_SHOCK_SHARE == 0.75
    assert sii.EXCLUDED_DAY == date(2026, 11, 5)
    assert sii.EPS == 1e-9
    assert sii.KINDS == ("shock", "quiet")


def test_step_readings_measure_every_step_on_the_fixture_session():
    readings = sii.step_readings(_fx([-0.5, -1.5, None]))
    assert len(readings) == 3
    assert {r.session_date for r in readings} == {date(2020, 3, 16)}
    assert readings[0].spy_atr_move == pytest.approx(-0.5)
    assert readings[1].spy_atr_move == pytest.approx(-1.5)
    assert readings[2].spy_atr_move is None
    assert all(r.vix_chg_pct is None for r in readings)       # no VIX on the day
    assert not any(r.insufficient for r in readings)          # 25 names >= min_names 20


def test_step_readings_fall_back_to_the_first_step_date_without_a_session_key():
    fx = _fx([-1.0])
    del fx["session"]
    assert sii.step_readings(fx)[0].session_date == date(2020, 3, 16)


def test_two_consecutive_settled_readings_fire_at_the_second():
    fx = _fx([-2.0, -2.0, -2.0], start_min=0)                 # 0 min is inside the settle window
    assert sii.spy_half_first_fire(sii.step_readings(fx), 1.0) == _at(30)


def test_a_broken_streak_starts_again():
    fx = _fx([-1.5, -0.5, -1.5, -1.5])
    assert sii.spy_half_first_fire(sii.step_readings(fx), 1.25) == _at(60)


@pytest.mark.parametrize("move, fires", [(-1.25, True), (-1.24, False)])
def test_the_threshold_is_met_with_the_detector_tolerance(move, fires):
    fired = sii.spy_half_first_fire(sii.step_readings(_fx([move, move])), 1.25)
    assert (fired is not None) is fires


def test_a_missing_spy_row_never_meets_and_resets_the_streak():
    readings = sii.step_readings(_fx([-2.0, None, -2.0]))
    assert sii.spy_half_first_fire(readings, 1.0) is None


def test_an_insufficient_reading_holds_the_streak():
    fx = _fx([-2.0, -2.0, -2.0])
    fx["steps"][1]["names"] = []                              # n_names 0 < 20: held
    readings = sii.step_readings(fx)
    assert readings[1].insufficient
    assert sii.spy_half_first_fire(readings, 1.0) == _at(45)


def test_the_settle_window_follows_the_argument():
    readings = sii.step_readings(_fx([-2.0, -2.0, -2.0]))    # 15, 30, 45 min
    assert sii.spy_half_first_fire(readings, 1.0, open_settle_min=30) == _at(45)


def test_an_empty_day_never_fires():
    assert sii.spy_half_first_fire([], 1.0) is None and sii.day_table([], 1.0) == []


def test_day_table_has_one_row_per_step():
    rows = sii.day_table(sii.step_readings(_fx([-0.5, -1.5, -1.5])), 1.0)
    assert [r["streak"] for r in rows] == [0, 1, 2]
    assert [r["fires"] for r in rows] == [False, False, True]
    assert rows[0] == {"as_of": _at(15).isoformat(), "minutes_since_open": 15.0,
                       "spy_atr_move": pytest.approx(-0.5), "settled": True,
                       "insufficient": False, "meets": False, "streak": 0, "fires": False}


@pytest.mark.parametrize("shock_fired, quiet_fired, expected", [
    ([True] * 4 + [False], [False] * 5, True),                # 0.80
    ([True] * 3 + [False], [False] * 4, True),                # exactly 0.75
    ([True] * 3 + [False] * 2, [False] * 5, False),           # 0.60
    ([True] * 5, [False] * 4 + [True], False),                # one quiet fire kills it
    ([], [False], False),                                     # no shock day, no verdict
])
def test_survival_rule(shock_fired, quiet_fired, expected):
    assert sii.survives(shock_fired, quiet_fired) is expected
```

(`json` is imported now for V222-7b's tests.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/backtest_scripts/test_shock_index_intraday.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'shock_index_intraday'`.

- [ ] **Step 3: Implement the core of `W/scripts/backtest/shock_index_intraday.py`**

Module header (the docstring's first line becomes the CLI description in V222-7b):

```python
"""v222 Stage 2: the SPY half of the index rule replayed over frozen historical days.

Reads one fixture per day of data/v222/stage2_days.json (built by
scripts/data/build_shock_replay_fixture.py --session), measures every step with
shock.measure, and asks whether -spy_atr_move >= k holds on two consecutive settled
readings. No real intraday VIX exists for these days, so the VIX half is never
confirmed (spec Stage 2). Only source == "alpaca" fixtures count; 2026-11-05 is refused.
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot.core.market import shock  # noqa: E402

SURVIVAL_SHOCK_SHARE = 0.75
EXCLUDED_DAY = date(2026, 11, 5)
EPS = 1e-9
KINDS = ("shock", "quiet")
```

The streak counter is the one piece the tests do not fully determine. Write it as one
helper that every public function uses, so the table and the first fire never disagree:

```python
def _settled(r: shock.ShockReading, open_settle_min: int) -> bool:
    return r.minutes_since_open + EPS >= open_settle_min


def _spy_meets(r: shock.ShockReading, k: float) -> bool:
    return r.spy_atr_move is not None and -r.spy_atr_move + EPS >= k


def _streaks(readings, k: float, open_settle_min: int) -> list[tuple[shock.ShockReading, int]]:
    """(reading, streak after it), as shock._from_normal counts entry_streak.

    An insufficient reading holds the streak (shock.step returns the state unchanged)."""
    streak, out = 0, []
    for r in readings:
        if not r.insufficient:
            streak = streak + 1 if _settled(r, open_settle_min) and _spy_meets(r, k) else 0
        out.append((r, streak))
    return out
```

Then, each a few lines (bodies follow from the tests):

- `_snapshot(step: dict, session: date) -> shock.ShockSnapshot` — as the replay test's
  `_snapshot` does (`tests/market/test_shock_replay_2026_11_05.py`, untracked on the
  branch: read it, do not edit it): `as_of = datetime.fromisoformat(step["as_of"])`;
  `shock.VixTape(vix.get("level"), vix.get("chg_pct"), as_of)` from `step.get("vix") or {}`;
  `shock.NameRow(**d)` for every name; `spy` / `qqq` rows or None.
- `_session(fx) -> date` — `date.fromisoformat(fx["session"])` when the key is present and
  non-empty, else the first step's `as_of` date.
- `step_readings(fx, th=shock.ShockThresholds())` — chain `prev` through `shock.measure`
  per step, as the replay test's `_replay` does, without `shock.step` (the state machine is
  not what Stage 2 measures; `_streaks` mirrors its entry rule).
- `spy_half_first_fire(readings, k, open_settle_min=15)` — `as_of` of the first reading
  whose streak reaches 2, else None.
- `day_table(readings, k, open_settle_min=15)` — one dict per `_streaks` row with the keys
  in the Interfaces block; `fires = streak >= 2`; `as_of` as an ISO string.
- `survives(shock_fired, quiet_fired)` — False when `shock_fired` is empty or any quiet day
  fired, else `sum(shock_fired) / len(shock_fired) + EPS >= SURVIVAL_SHOCK_SHARE`.

- [ ] **Step 4: Run the tests and the complexity gate**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/backtest_scripts/test_shock_index_intraday.py`
Expected: PASS (`0 failed`).

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/complexity_gate.py`
Expected: exit 0 (`_streaks` is about 4; nothing else above 3).

- [ ] **Step 5: Commit (v209 branch)**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector add scripts/backtest/shock_index_intraday.py tests/backtest_scripts/test_shock_index_intraday.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector commit -m "feat(v222): Stage 2 SPY-half rule and survival rule (V222-7)"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the main-tree status shows nothing from this task.

### Task V222-7b: Stage 2 day list, fixture checks, `evaluate`, report and CLI

**Model:** opus — decides which cell is frozen at gate 2 and when no verdict may be drawn; a lenient default here would freeze a cell on missing evidence.

**Files:**
- Modify: `.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/backtest/shock_index_intraday.py`
- Modify: `.claude/worktrees/2026-11-05-v209-market-shock-detector/tests/backtest_scripts/test_shock_index_intraday.py`

**Interfaces:**
- Consumes: V222-7 (same module) `SURVIVAL_SHOCK_SHARE`, `EXCLUDED_DAY`, `EPS`, `KINDS`, `step_readings`, `spy_half_first_fire`, `day_table`, `survives`; test helpers `SESSION`, `_fx`, `_at`.
- Consumes at run time (V222-8): `M/data/v222/stage2_days.json` = `{"shock": [iso...], "quiet": [iso...], "cells": [[k, v]...]}` (V222-5).
- Produces (for V222-8):
  - `load_days(path) -> dict`
  - `fixture_path(fixtures_dir: Path, iso: str) -> Path` — `shock_replay_<yyyy_mm_dd>.json`, the same name V222-6b's `default_paths` gives a non-default session.
  - `fixture_status(fx: dict | None, iso: str) -> str` — `ok`, `missing`, `synthetic`, `wrong-session`.
  - `evaluate(days: dict, fixtures: dict[str, dict | None]) -> dict` — keys `complete, days, cells, survivors, frozen`; `days[iso]` keys `kind, status, vix, first_fire, tables`; `cells[i]` keys `k, v, shock_fired, quiet_fired, survives, vix_half`.
  - `render_md(report: dict) -> str`
  - CLI `--days-json --fixtures-dir --out-json --out-md`; exit `0` complete, `3` incomplete (some day's fixture missing, synthetic or for another session: written, but no verdict), `2` bad day list (unreadable, no shock days, no cells, or 2026-11-05 present; nothing written).

**The verdict rule.** The VIX half is never confirmed: an interpolated VIX (anchor) and an
absent one both report `unconfirmed`, so `v` does not change whether a day fires; among
surviving cells with the same `k` the most sensitive (lowest `v`) is frozen. Cells are
sorted `(k, v)` ascending before the first survivor is taken, so the frozen cell does not
depend on the order in `stage2_days.json`. A survival verdict exists only when **every**
frozen day has an `ok` fixture; otherwise `complete` is False, `survivors` is `[]` and
`frozen` is None (a missing day is never read as "did not fire").

- [ ] **Step 1: Write the failing tests**

Append to `W/tests/backtest_scripts/test_shock_index_intraday.py`:

```python
def _days_file(tmp_path, **over):
    days = {"shock": ["2020-03-16"], "quiet": ["2020-02-14"], "cells": [[1.0, 10.0]], **over}
    path = tmp_path / "stage2_days.json"
    path.write_text(json.dumps(days), encoding="utf-8")
    return path


@pytest.mark.parametrize("over", [
    {"shock": ["2020-03-16", "2026-11-05"]},
    {"quiet": ["2026-11-05"]},
    {"shock": []},
    {"cells": []},
    {"quiet": None},
])
def test_load_days_refuses_a_bad_list(tmp_path, over):
    with pytest.raises(ValueError):
        sii.load_days(_days_file(tmp_path, **over))


def test_load_days_returns_the_frozen_list(tmp_path):
    assert sii.load_days(_days_file(tmp_path)) == {
        "shock": ["2020-03-16"], "quiet": ["2020-02-14"], "cells": [[1.0, 10.0]]}


def test_fixture_path_uses_the_builder_session_name(tmp_path):
    assert sii.fixture_path(tmp_path, "2020-03-16") == tmp_path / "shock_replay_2020_03_16.json"


@pytest.mark.parametrize("fx, status", [
    (None, "missing"),
    (_fx([-1.0], source="synthetic"), "synthetic"),
    (_fx([-1.0], session="2020-03-17"), "wrong-session"),
    (_fx([-1.0]), "ok"),
])
def test_fixture_status(fx, status):
    assert sii.fixture_status(fx, SESSION) == status


SHOCK_DAYS = ["2020-03-16", "2020-03-12", "2020-03-09", "2020-03-18"]
QUIET_DAYS = ["2020-02-14", "2020-02-12"]


def _fixtures(shock_move, quiet_move):
    out = {d: _fx([shock_move] * 3, session=d) for d in SHOCK_DAYS}
    out.update({d: _fx([quiet_move] * 3, session=d) for d in QUIET_DAYS})
    return out


def _days(cells):
    return {"shock": SHOCK_DAYS, "quiet": QUIET_DAYS, "cells": cells}


def test_evaluate_freezes_the_most_sensitive_survivor_whatever_the_list_order():
    fixtures = _fixtures(-1.6, -0.3)
    fixtures["2020-03-18"] = _fx([-1.3] * 3, session="2020-03-18")   # below k = 1.5
    report = sii.evaluate(_days([[1.5, 10.0], [1.0, 15.0], [1.0, 10.0]]), fixtures)
    assert report["complete"] is True
    assert report["survivors"] == [[1.0, 10.0], [1.0, 15.0], [1.5, 10.0]]   # 1.5: 3/4 = 0.75
    assert report["frozen"] == [1.0, 10.0]
    cell = report["cells"][0]
    assert (cell["k"], cell["v"], cell["shock_fired"], cell["quiet_fired"]) == (
        1.0, 10.0, [True] * 4, [False, False])
    assert cell["vix_half"] == "unconfirmed"
    day = report["days"]["2020-03-18"]
    assert day["kind"] == "shock" and day["status"] == "ok"
    assert day["first_fire"] == {"1.0": _at(30).isoformat(), "1.5": None}
    assert len(day["tables"]["1.0"]) == 3
    assert day["vix"] == "unconfirmed (no intraday VIX)"
    assert list(report["days"]) == SHOCK_DAYS + QUIET_DAYS


def test_a_quiet_day_fire_means_no_survivor():
    report = sii.evaluate(_days([[1.0, 10.0]]), _fixtures(-1.6, -1.1))
    assert report["complete"] is True
    assert report["survivors"] == [] and report["frozen"] is None


def test_an_interpolated_vix_is_still_unconfirmed():
    fixtures = _fixtures(-1.6, -0.3)
    fixtures["2020-03-16"] = _fx([-1.6] * 3, interpolated=True)
    day = sii.evaluate(_days([[1.0, 10.0]]), fixtures)["days"]["2020-03-16"]
    assert day["vix"] == "unconfirmed (interpolated from one tape reading)"


def test_a_missing_or_synthetic_day_leaves_no_verdict():
    fixtures = _fixtures(-1.6, -0.3)
    fixtures["2020-03-09"] = None
    fixtures["2020-02-12"] = _fx([-0.3] * 3, source="synthetic", session="2020-02-12")
    report = sii.evaluate(_days([[1.0, 10.0]]), fixtures)
    assert report["complete"] is False
    assert report["survivors"] == [] and report["frozen"] is None
    assert report["days"]["2020-03-09"]["status"] == "missing"
    assert report["days"]["2020-03-09"]["tables"] == {}
    assert report["days"]["2020-02-12"]["status"] == "synthetic"


def _write_fixtures(fixtures_dir, fixtures):
    fixtures_dir.mkdir()
    for iso, fx in fixtures.items():
        sii.fixture_path(fixtures_dir, iso).write_text(json.dumps(fx), encoding="utf-8")


def _cli(tmp_path, days_path):
    out_json, out_md = tmp_path / "out" / "stage2.json", tmp_path / "out" / "stage2.md"
    rc = sii.main(["--days-json", str(days_path), "--fixtures-dir", str(tmp_path / "fx"),
                   "--out-json", str(out_json), "--out-md", str(out_md)])
    return rc, out_json, out_md


def test_cli_writes_json_and_markdown(tmp_path):
    _write_fixtures(tmp_path / "fx", _fixtures(-1.6, -0.3))
    days_path = _days_file(tmp_path, shock=SHOCK_DAYS, quiet=QUIET_DAYS,
                           cells=[[1.0, 10.0], [2.0, 25.0]])
    rc, out_json, out_md = _cli(tmp_path, days_path)
    assert rc == 0
    report = json.loads(out_json.read_text(encoding="utf-8"))
    assert report["frozen"] == [1.0, 10.0] and report["survivors"] == [[1.0, 10.0]]
    md = out_md.read_text(encoding="utf-8")
    assert "Complete: yes" in md and "Frozen cell: [1.0, 10.0]" in md
    assert "| 1.0 | 10.0 | 4/4 | 0/2 | yes |" in md
    assert "| 2.0 | 25.0 | 0/4 | 0/2 | no |" in md
    assert "## 2020-03-16 (shock)" in md and "streak k=1.0" in md
    assert "first SPY-half fire, k=1.0: 14:00 UTC" in md
    assert "first SPY-half fire, k=2.0: none" in md
    assert "| 13:45 | 15 | -1.60 | yes |  | 1 | 0 |" in md


def test_cli_exits_3_when_a_fixture_is_missing(tmp_path):
    fixtures = _fixtures(-1.6, -0.3)
    del fixtures["2020-03-12"]
    _write_fixtures(tmp_path / "fx", fixtures)
    days_path = _days_file(tmp_path, shock=SHOCK_DAYS, quiet=QUIET_DAYS)
    rc, out_json, out_md = _cli(tmp_path, days_path)
    assert rc == 3
    assert json.loads(out_json.read_text(encoding="utf-8"))["frozen"] is None
    assert "Complete: NO" in out_md.read_text(encoding="utf-8")


def test_cli_exits_2_on_a_list_with_2026_11_05_and_writes_nothing(tmp_path):
    days_path = _days_file(tmp_path, shock=["2026-11-05"])
    rc, out_json, out_md = _cli(tmp_path, days_path)
    assert rc == 2 and not out_json.exists() and not out_md.exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/backtest_scripts/test_shock_index_intraday.py`
Expected: FAIL — `AttributeError: module 'shock_index_intraday' has no attribute 'load_days'` (and `fixture_path`, `fixture_status`, `evaluate`, `main`); V222-7's tests still pass.

- [ ] **Step 3: Implement in `W/scripts/backtest/shock_index_intraday.py`**

Add `import argparse` and `import json` to the imports, and below `KINDS`:

```python
VIX_INTERPOLATED = "unconfirmed (interpolated from one tape reading)"
VIX_ABSENT = "unconfirmed (no intraday VIX)"
```

Then, in this order (bodies follow from the tests):

- `load_days(path)` — read JSON (UTF-8); raise `ValueError` when `shock` or `quiet` is not
  a list, `shock` is empty, `cells` is empty or absent, or `EXCLUDED_DAY.isoformat()` is in
  either list.
- `fixture_path(fixtures_dir, iso)` — `fixtures_dir / f"shock_replay_{iso.replace('-', '_')}.json"`.
- `fixture_status(fx, iso)` — `missing` (None), `synthetic` (`source != "alpaca"`),
  `wrong-session` (`fx.get("session") != iso`), else `ok`.
- `_day_report(kind, fx, iso, ks) -> dict` — `vix` is `VIX_INTERPOLATED` when `fx` and
  `fx.get("vix_interpolated")`, else `VIX_ABSENT`; `first_fire` (ISO string or None) and
  `tables` (`day_table` rows) keyed by `str(k)` and filled only for an `ok` fixture, one
  `step_readings` per day reused for every `k`.
- `_cell_report(k, v, day_reports, days) -> dict` — a day fired when
  `day_reports[iso]["first_fire"].get(str(k)) is not None`; `shock_fired` / `quiet_fired`
  in list order; `survives(...)`; `vix_half = "unconfirmed"`.
- `evaluate(days, fixtures)` — `ks = sorted({float(k) for k, _ in days["cells"]})`; day
  reports for shock days then quiet days (`fixtures.get(iso)`); cells from
  `sorted((float(k), float(v)) for k, v in days["cells"])`;
  `complete = all(d["status"] == "ok" ...)`; `survivors = [[c["k"], c["v"]] ...]` only when
  complete; `frozen = survivors[0]` if survivors else None.
- `render_md(report)` — lines: `# v222 Stage 2 — SPY half on frozen days`; `Complete: yes`
  or `Complete: NO (see each day's fixture status)`; `VIX half: unconfirmed on every day (no
  real intraday VIX exists for these sessions).`; the cell table
  `| k | v | shock days fired | quiet days fired | survives |` with rows
  `| {k} | {v} | {sum}/{len} | {sum}/{len} | yes|no |`; `Frozen cell: [k, v]` or
  `Frozen cell: NONE`; then `_day_md(iso, day)` per day.
- `_day_md(iso, day) -> list[str]` — `## <iso> (<kind>)`; bullets `- fixture: <status>`,
  `- VIX half: <vix>`, and per `k` `- first SPY-half fire, k=<k>: HH:MM UTC` (characters
  11..16 of the ISO string) or `none`; for an `ok` day one table with header
  `| UTC | min | SPY ATR move | settled | held | streak k=<k> ... |`, one row per step from
  `_row_md(row, streaks)`.
- `_row_md(row, streaks: list[int]) -> str` — `| HH:MM | <minutes:.0f> | <move:+.2f or —> |
  yes|no | yes or empty | <streak> | ... |` (single spaces around every cell, so an empty
  `held` cell is two spaces, as the CLI test pins).
- `_parse(argv)` (four required `type=Path` flags; description = the docstring's first
  line) and `main(argv=None) -> int` — on `OSError` / `ValueError` from `load_days` print
  `bad day list: <exc>` to stderr and return 2 before writing; read each day's fixture
  (`None` when the file does not exist); `evaluate`; `mkdir(parents=True, exist_ok=True)`
  for both outputs' parents; write `json.dumps(report, indent=1)` and `render_md(report)`
  as UTF-8; print `complete: <bool>; survivors: <list>; frozen: <cell or NONE>`; return `0`
  when complete else `3`.
- `if __name__ == "__main__": raise SystemExit(main())`.

- [ ] **Step 4: Run the tests and the complexity gate**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/backtest_scripts/test_shock_index_intraday.py`
Expected: PASS (`0 failed`).

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/complexity_gate.py`
Expected: exit 0 (`load_days` and `_day_md` are the largest, both under 10).

- [ ] **Step 5: Commit (v209 branch)**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector add scripts/backtest/shock_index_intraday.py tests/backtest_scripts/test_shock_index_intraday.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector commit -m "feat(v222): Stage 2 day list, fixture checks, verdict and report CLI (V222-7b)"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the main-tree status shows nothing from this task.

### Task V222-8: Build Stage 2 fixtures, run, write Results, freeze the cell, gate 2

**Model:** sonnet — runs finished scripts and transcribes their output; no new code.

**Files:**
- Modify: `docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md` (main tree, `## Results`: new `### Stage 2 — intraday results`, below V222-5's `### Stage 2 — frozen day list`)
- Outputs (main tree, gitignored `data/`): `M/data/v222/stage2/shock_replay_<yyyy_mm_dd>.json` (one per frozen day), `M/data/v222/stage2/cache/<yyyy_mm_dd>/` (per-ticker checkpoints), `M/data/v222/stage2.json`, `M/data/v222/stage2.md`

**Interfaces:**
- Consumes: V222-5 `M/data/v222/stage2_days.json` (`shock`, `quiet`, `cells`); V222-6/6b builder CLI `--session YYYY-MM-DD --out P --cache-dir D` (no `--vix-anchor`: no real intraday VIX tape reading exists for a historical day, so none is invented); V222-7/7b evaluator CLI `--days-json --fixtures-dir --out-json --out-md` and its exit codes `0` / `2` / `3`.
- Produces (for V222-9..V222-14): Results § Stage 2 with the frozen cell `index_atr_k = FROZEN_K`, `index_vix_chg = FROZEN_V` (the evaluator's `frozen`), or **NO-LIFT**.

No test code: every script was tested in V222-6..V222-7b. Run from any directory; every
path is absolute; never `cd`. **Do not open, build or replay 2026-11-05 in this task.**
The builder reads the Alpaca keys from `.env`; never print their values.

- [ ] **Step 1: Preconditions**

Gate 1 has passed (the partner's answer is recorded after V222-5) and the day list is frozen:

```bash
python -c "import json; d=json.load(open('E:/Documents/Private/Projects/Discord-Bot/data/v222/stage2_days.json', encoding='utf-8')); days=d['shock']+d['quiet']; assert '2026-11-05' not in days; assert 5 <= len(days) <= 10, len(days); assert d['cells']; print(len(d['shock']), 'shock,', len(d['quiet']), 'quiet, cells', d['cells'])"
```

Expected: one line such as `5 shock, 5 quiet, cells [[1.0, 10.0], ...]`. An assertion
error stops the task: report it, never edit the list (it is frozen in the spec).

- [ ] **Step 2: Build one Alpaca fixture per frozen day (network; checkpointed)**

```bash
M=E:/Documents/Private/Projects/Discord-Bot
W=$M/.claude/worktrees/2026-11-05-v209-market-shock-detector
for d in $(python -c "import json; d=json.load(open('$M/data/v222/stage2_days.json', encoding='utf-8')); print(' '.join(d['shock'] + d['quiet']))"); do
  t=${d//-/_}
  python $W/scripts/data/build_shock_replay_fixture.py --session $d --out $M/data/v222/stage2/shock_replay_$t.json --cache-dir $M/data/v222/stage2/cache/$t || echo "BUILD FAILED $d"
done
```

Each run prints `wrote <path>: <source>, <n> steps, <m> long entries`. The ticker list is
the builder's default (the current watchlist) for every day, so the days are comparable;
only SPY decides the SPY half, the names only decide whether a reading is sufficient.
Per-ticker raw bars checkpoint into `cache/<yyyy_mm_dd>/`, so a restart skips finished
tickers. If the loop runs for more than a few minutes, dispatch it with
`run_in_background` and wait for its exit; never re-run finished days by hand.

- [ ] **Step 3: Check every fixture is Alpaca-sourced and complete**

```bash
python -c "import json,pathlib; [print(p.name, (f:=json.loads(p.read_text(encoding='utf-8')))['source'], f.get('session'), len(f['steps']), 'steps,', f['vix_interpolated'], '|', f['note'][:90]) for p in sorted(pathlib.Path('E:/Documents/Private/Projects/Discord-Bot/data/v222/stage2').glob('shock_replay_*.json'))]"
```

Expected: one line per frozen day, source `alpaca`, `session` equal to the day,
`vix_interpolated` False, 26 steps (fewer only on a half-day session). A `synthetic`
day or a missing file: re-run the Step 2 command for that one day once (the cache
resumes); still not `alpaca` → stop and ask the partner (`AskUserQuestion`, recommended
option "report the day as missing and decide; never swap in another day"). The evaluator
would refuse a verdict anyway (exit 3).

- [ ] **Step 4: Run the evaluator**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/backtest/shock_index_intraday.py --days-json E:/Documents/Private/Projects/Discord-Bot/data/v222/stage2_days.json --fixtures-dir E:/Documents/Private/Projects/Discord-Bot/data/v222/stage2 --out-json E:/Documents/Private/Projects/Discord-Bot/data/v222/stage2.json --out-md E:/Documents/Private/Projects/Discord-Bot/data/v222/stage2.md
```

Expected: exit `0` and a last line `complete: True; survivors: [...]; frozen: [k, v]` or
`frozen: NONE`. Exit `3` (incomplete) → Step 3's stop applies; exit `2` → the day list is
bad, stop and report.

- [ ] **Step 5: Write the Results (main tree spec), below `### Stage 2 — frozen day list`**

Add `### Stage 2 — intraday results` with, in this order:

1. One provenance table, a row per frozen day: day, kind (shock/quiet), fixture source
   (`alpaca`), tickers with both bar sets (from the fixture `note`), steps, VIX
   (`none — VIX half unconfirmed`), build date (UTC).
2. The cell table from `stage2.md` unchanged (`k | v | shock days fired | quiet days fired | survives`).
3. One line per day: the first SPY-half fire time per judged `k` (from `stage2.md`).
4. The line: "The VIX half of the rule is unconfirmed on every Stage 2 day: no real
   intraday VIX exists for these sessions, and no interpolated VIX was built. Cells with the
   same `index_atr_k` therefore fire on the same days; the frozen `index_vix_chg` is the
   lowest one among the surviving cells (most sensitive), per the frozen winner rule."
5. The verdict, as its own bold line: **Frozen cell: `index_atr_k = <k>`,
   `index_vix_chg = <v>`** — or **NO-LIFT: no cell fires on at least 75 % of the shock
   days and on none of the quiet days**.
6. Each day's step table from `stage2.md`, inside one `<details><summary>Per-step tables
   (N days)</summary> ... </details>` block so the spec stays readable.

Write only from `stage2.json` / `stage2.md`; nothing is rounded or re-chosen by hand.

- [ ] **Step 6: Commit on `main` (controller)**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot add docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "docs(v222): Stage 2 intraday results and the frozen cell"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: only the spec was committed; `data/v222/` stays untracked-ignored.

- [ ] **Step 7: Gate 2 (partner, `AskUserQuestion`, recommended option first)**

- A frozen cell: ask "Stage 2 results are in the spec; freeze `index_atr_k = <k>`,
  `index_vix_chg = <v>` and start Part 3 (implementation, then the one Stage 3 replay)?"
  (recommended: freeze and proceed). The answer goes in the spec under the verdict line
  ("Gate 2: passed by the partner on <date>"), committed with the next Results edit.
- No survivor: report it; recommended option "close v222 as NO-LIFT (plan to `no-lift/`,
  nothing ships; v209's release is decided separately)". Never add a day, drop a quiet day,
  relax the 75 % rule or move the grid.
- Incomplete (a day without an Alpaca fixture): stop and ask; the recommended option keeps
  the frozen list and reports the gap.

No Part 3 task starts before the partner passes gate 2.
