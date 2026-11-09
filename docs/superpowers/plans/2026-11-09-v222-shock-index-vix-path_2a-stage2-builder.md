# v222 — Market-shock detector: index + VIX entry path — Part 2a: Stage 2 fixture builder (V222-6..V222-6d)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** bot patch
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md`](../specs/2026-11-09-v222-shock-index-vix-path-design.md)
**Index:** [`2026-11-09-v222-shock-index-vix-path_0-index.md`](2026-11-09-v222-shock-index-vix-path_0-index.md) — Goal, Architecture, **Global Constraints** (frozen survival rule, Stage 2 day list, the SPY-half reading and "only Alpaca fixtures count") and the task ledger live there; every task below implicitly includes them.

## Parallelisation

See the index. Inside this part: V222-6 → V222-6b → V222-6c → V222-6d is sequential (one
script and one test file). V222-6 and V222-6b share no contract with Part 2b's V222-7/7b
(the evaluator reads fixture JSON, never imports the builder), so they may run in parallel
with them and with Part 1's code tasks. V222-6c and V222-6d need V222-6b; V222-6d is the
only task before V222-13 that writes the committed 2026-11-05 fixture, and V222-13 needs it.

Conventions for every task in this part (same as Part 1 and Part 2b):

- `W` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector`
  (code, tests, commits on branch `2026-11-05-v209-market-shock-detector`).
- `M` = `E:/Documents/Private/Projects/Discord-Bot` (main tree: the spec's `## Results`,
  and the gitignored stage data in `M/data/v222/`).
- Never `cd`; run tests by the absolute path of `W`'s runner, e.g.
  `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scripts/test_build_shock_replay_fixture.py`.
- **Nothing in this part opens 2026-11-05's outcome.** Through V222-6b the builder's
  2026-11-05 default stays byte-identical and is only exercised through synthetic test
  frames. V222-6c moves it onto the real one-minute VIX bars (spec § VIX provenance,
  amended 2026-11-09) and V222-6d rebuilds the committed fixture, checking only its shape:
  no VIX value is printed and the detector is never run over it.

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
literal VIX values. (V222-6c later moves the default onto real one-minute VIX bars; from
then on this rule holds for `INTERPOLATED_SPEC`, the interpolated copy of the default.)

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


### Task V222-6c: Real one-minute VIX bars for the 2026-11-05 fixture

**Model:** sonnet — one more VIX source in the same builder (a CSV reader and a point-in-time lookup), stubbed with synthetic bars; the default spec moves onto the committed bars.

Why (spec § VIX provenance, amended 2026-11-09): the committed fixture's VIX is a straight
line from 0 % at 14:30 UTC to the 15:20 tape reading, so 14:45 reads about +8.2 %, below the
smallest grid value (10), and Stage 3 cannot pass in any cell by construction. The partner
decided the 2026-11-05 fixture takes VIX from real one-minute `^VIX` bars. Historical Stage 2
days are unchanged (no VIX, SPY half only).

Split: this task adds the bars source and moves `DEFAULT_SPEC` onto it; V222-6d adds the
`--vix-bars` CLI, rebuilds the committed fixture and aligns the replay test's provenance line.

**Never print, read or quote a VIX value** from the CSV or from any fixture, and never run
the detector over 2026-11-05: only structure (header rows, column names, row count,
timestamps, flags, hashes) is checked here. Stage 3 (V222-13) is the only reader.

**Files:**
- Create: `.claude/worktrees/2026-11-05-v209-market-shock-detector/tests/fixtures/vix_2026_11_05_1m.csv` (copied from `M/market_data/vix_intraday/VIX_2026-11-05_1m.csv`, gitignored in `M`)
- Modify: `.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/data/build_shock_replay_fixture.py`
- Modify: `.claude/worktrees/2026-11-05-v209-market-shock-detector/tests/scripts/test_build_shock_replay_fixture.py`

**Interfaces:**
- Consumes (V222-6/6b): `VixAnchor`, `SessionSpec`, `session_spec`, `DEFAULT_SPEC`, `SESSION`, `_at`, `ROOT`, `vix_path`, `_provenance`, `_vix_note`, `_alpaca_note`, `_synthetic_fixture`, `main`; test helpers `T`, `D`, `_run`, `FakeProvider`.
- Produces (for V222-6d, V222-13):
  - `load_vix_bars(path: Path) -> list[tuple[datetime, float]]` — yfinance `df.to_csv` shape (a `Price` row naming the columns, then `Ticker` and `Datetime` rows, then one row per UTC bar start); `(bar_start_utc, Close)` sorted; `ValueError` on a naive timestamp or no `Close` column.
  - `vix_from_bars(bars, t: datetime, prior: float) -> dict` — `{"level", "chg_pct"}` from the close of the last bar with `start + 1 min <= t`, change against `prior`, both `round(..., 4)` as `vix_path`; `ValueError` when no bar has finished by `t`.
  - `SessionSpec` gains `vix_bars: Path | None = None`, `vix_prior: float | None = None`; `ValueError` when `vix_bars` and `vix_anchor` are both set, or `vix_bars` lacks `vix_prior`. `session_spec(..., *, vix_bars=None, vix_prior=None)`.
  - `TAPE_ANCHOR = VixAnchor(15:20 UTC, 21.13, 27.21)`; `VIX_PRIOR` (unchanged value, 21.13 / 1.2721); `VIX_BARS = ROOT / "tests/fixtures/vix_2026_11_05_1m.csv"`; `VIX_BARS_SOURCE = "yfinance_1m"`.
  - `DEFAULT_SPEC` now reads `VIX_BARS` with `VIX_PRIOR` (no anchor); `INTERPOLATED_SPEC` = `DEFAULT_SPEC` with `TAPE_ANCHOR` and no bars (the old interpolated default).
  - Fixture with bars: `vix_interpolated: false` and a trailing `"vix_source": "yfinance_1m"`; the default 2026-11-05 fixture's keys are `source, vix_interpolated, note, steps, vix_source, long_entries`.

**Byte-identity rule (replaces V222-6's).** `INTERPOLATED_SPEC` produces the bytes the
builder produced before V222-6: keys `source, vix_interpolated, note, steps`, the old note,
the old VIX formula. `DEFAULT_SPEC` (bars) is no longer byte-identical by design. Existing
tests changed here, by name:
- `test_vix_path_climbs_to_the_tape_reading_then_holds` (V209-12): pass `bsr.INTERPOLATED_SPEC` as the second argument of all three `vix_path` calls; assertions unchanged.
- `test_too_few_names_falls_back_to_synthetic_and_says_why` (V209-12): `fx["vix_interpolated"] is True` → `is False`, add `and fx["vix_source"] == "yfinance_1m"`.
- `test_the_default_spec_is_the_frozen_replay_day` (V222-6): replace the `spec.vix_anchor == bsr.VixAnchor(...)` line with `assert spec.vix_anchor is None and bsr.TAPE_ANCHOR == bsr.VixAnchor(T(15, 20), 21.13, 27.21)`.
- `test_the_default_synthetic_fixture_keeps_the_old_keys` (V222-6): delete; superseded by the two default/interpolated tests below.
- `test_the_default_run_writes_exactly_the_old_keys_and_note` (V222-6b): rename to `test_the_default_run_writes_the_bars_keys_and_the_old_note`; key list `["source", "vix_interpolated", "note", "steps", "vix_source", "long_entries"]`; note assertions unchanged.

`test_a_step_applies_the_live_snapshot_rules` stays unchanged (both sides read the default
bars; no value is asserted).

- [ ] **Step 1: Copy the bars into the worktree, hash before and after**

```bash
M=E:/Documents/Private/Projects/Discord-Bot
W=$M/.claude/worktrees/2026-11-05-v209-market-shock-detector
sha256sum $M/market_data/vix_intraday/VIX_2026-11-05_1m.csv | cut -c1-16
cp $M/market_data/vix_intraday/VIX_2026-11-05_1m.csv $W/tests/fixtures/vix_2026_11_05_1m.csv
sha256sum $W/tests/fixtures/vix_2026_11_05_1m.csv | cut -c1-16
wc -l < $W/tests/fixtures/vix_2026_11_05_1m.csv
git -C $W check-ignore -q tests/fixtures/vix_2026_11_05_1m.csv && echo IGNORED || echo tracked-ok
```

Expected: both hashes `a095220d934e026a` (a mismatch stops the task: report it, never
re-download), `677` lines (3 header rows + 674 bars), `tracked-ok`. Never `cat`, `head`
or open the file.

- [ ] **Step 2: Write the failing tests**

Apply the five edits listed under the byte-identity rule, then append to
`W/tests/scripts/test_build_shock_replay_fixture.py` (add `from datetime import date` if
V222-6's import change is missing):

```python
VIX_HEAD = ["Price,Adj Close,Close,High,Low,Open,Volume",
            "Ticker,^VIX,^VIX,^VIX,^VIX,^VIX,^VIX", "Datetime,,,,,,"]


def _vix_csv(path, bars):
    """A yfinance ``df.to_csv`` file; Adj Close differs from Close on purpose."""
    rows = [f"{at:%Y-%m-%d %H:%M:%S}+00:00,{c + 100},{c},{c + 1},{c - 1},{c},0"
            for at, c in bars]
    path.write_text("\n".join(VIX_HEAD + rows) + "\n", encoding="utf-8")
    return path


def test_load_vix_bars_reads_the_yfinance_shape(tmp_path):
    path = _vix_csv(tmp_path / "v.csv", [(T(14, 30), 21.5), (T(14, 29), 20.0)])
    bars = bsr.load_vix_bars(path)
    assert bars == [(T(14, 29), 20.0), (T(14, 30), 21.5)]
    assert all(at.utcoffset() == timedelta(0) for at, _ in bars)


def test_a_bar_counts_once_it_has_finished():
    bars = [(T(14, 58), 20.0), (T(14, 59), 21.0), (T(15, 0), 30.0)]
    assert bsr.vix_from_bars(bars, T(15, 0), 20.0) == {"level": 21.0, "chg_pct": 5.0}
    assert bsr.vix_from_bars(bars, T(15, 1), 20.0) == {"level": 30.0, "chg_pct": 50.0}


def test_the_change_is_against_the_tape_prior_close():
    assert bsr.VIX_PRIOR == pytest.approx(21.13 / 1.2721)
    got = bsr.vix_from_bars([(T(15, 19), 21.13)], T(15, 20), bsr.VIX_PRIOR)
    assert got["level"] == 21.13 and got["chg_pct"] == pytest.approx(27.21)


def test_no_finished_bar_is_an_error():
    with pytest.raises(ValueError):
        bsr.vix_from_bars([(T(14, 59), 20.0)], T(14, 59), 20.0)
    with pytest.raises(ValueError):
        bsr.vix_from_bars([], T(15, 0), 20.0)


def test_bars_and_an_anchor_are_mutually_exclusive(tmp_path):
    day, path = date(2020, 3, 16), tmp_path / "v.csv"
    with pytest.raises(ValueError):
        bsr.session_spec(day, bsr.VixAnchor(D(day, 14, 30), 80.0, 25.0),
                         vix_bars=path, vix_prior=20.0)
    with pytest.raises(ValueError):
        bsr.session_spec(day, vix_bars=path)


def test_a_bars_fixture_is_point_in_time_and_says_so(tmp_path):
    day = date(2020, 3, 16)
    path = _vix_csv(tmp_path / "v.csv", [(D(day, 13, 0), 20.0), (D(day, 14, 59), 25.0)])
    spec = bsr.session_spec(day, vix_bars=path, vix_prior=20.0)
    fx = bsr._synthetic_fixture("why", spec)
    assert list(fx) == ["source", "vix_interpolated", "note", "steps", "session",
                        "vix_anchor", "vix_source"]
    assert (fx["vix_interpolated"], fx["vix_anchor"], fx["vix_source"]) == (
        False, None, "yfinance_1m")
    vix = {s["as_of"]: s["vix"] for s in fx["steps"]}
    assert vix["2020-03-16T14:45:00+00:00"] == {"level": 20.0, "chg_pct": 0.0}
    assert vix["2020-03-16T15:00:00+00:00"] == {"level": 25.0, "chg_pct": 25.0}
    assert "one-minute ^VIX bars" in bsr._vix_note(spec)


def test_the_default_spec_reads_the_committed_one_minute_bars():
    spec = bsr.DEFAULT_SPEC
    assert (spec.vix_anchor, spec.vix_bars, spec.vix_prior) == (
        None, bsr.VIX_BARS, bsr.VIX_PRIOR)
    assert bsr.VIX_BARS == bsr.ROOT / "tests" / "fixtures" / "vix_2026_11_05_1m.csv"
    bars = bsr.load_vix_bars(bsr.VIX_BARS)          # shape only: never a value
    assert (len(bars), bars[0][0], bars[-1][0]) == (674, T(8, 15), T(21, 14))
    fx = bsr._synthetic_fixture("why")
    assert list(fx) == ["source", "vix_interpolated", "note", "steps", "vix_source"]
    assert (fx["vix_interpolated"], fx["vix_source"]) == (False, "yfinance_1m")


def test_the_interpolated_copy_keeps_the_old_bytes():
    spec = bsr.INTERPOLATED_SPEC
    assert (spec.vix_anchor, spec.vix_bars) == (bsr.TAPE_ANCHOR, None)
    assert (spec.day, spec.daily_start, spec.open_utc) == (bsr.SESSION, date(2026, 7, 1),
                                                           T(14, 30))
    fx = bsr._synthetic_fixture("why", spec)
    assert list(fx) == ["source", "vix_interpolated", "note", "steps"]
    assert fx["vix_interpolated"] is True
    assert bsr._alpaca_note(spec, 3) == (
        "3 tickers with daily + 15-minute Alpaca bars; VIX interpolated linearly from the "
        "15:20 UTC tape reading (21.13, +27.21%); long_entries comes from the trade log")


```

- [ ] **Step 3: Run the tests to see them fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scripts/test_build_shock_replay_fixture.py`
Expected: FAIL — `AttributeError: ... has no attribute 'load_vix_bars'` / `'INTERPOLATED_SPEC'` / `'TAPE_ANCHOR'`, `unexpected keyword argument 'vix_bars'`, and the edited default tests.

- [ ] **Step 4: Implement**

In `W/scripts/data/build_shock_replay_fixture.py`:

1. Imports: add `import csv`, `from functools import lru_cache`, and `replace` to the
   `dataclasses` import. Docstring: replace the "VIX is not fetchable by minute ..."
   paragraph with: "VIX comes from real one-minute `^VIX` bars (yfinance, committed as
   `tests/fixtures/vix_2026_11_05_1m.csv`): each step reads the close of the last bar
   finished by the step, against the tape's prior close (21.13 / 1.2721), so the fixture
   records `vix_interpolated: false` and `vix_source: yfinance_1m` (v222 V222-6c)."

2. `SessionSpec` gains two trailing defaulted fields and a check; `session_spec` passes them:

```python
    vix_bars: Path | None = None
    vix_prior: float | None = None

    def __post_init__(self):
        if self.vix_bars is not None and self.vix_anchor is not None:
            raise ValueError("vix_bars and vix_anchor are mutually exclusive")
        if self.vix_bars is not None and self.vix_prior is None:
            raise ValueError("vix_bars needs vix_prior (the prior session's VIX close)")
```

`session_spec(day, vix_anchor=None, daily_start=None, *, vix_bars=None, vix_prior=None)`
adds `vix_bars=vix_bars, vix_prior=vix_prior` to its `SessionSpec(...)` call.

3. Replace V222-6's `DEFAULT_SPEC = ...`, `VIX_TAPE_*` and `VIX_PRIOR` lines with the
   block below; keep `OPEN_UTC`, `CLOSE_UTC`, `TURN_UTC` and `DAILY_START` (derived from
   `DEFAULT_SPEC`) after it:

```python
MINUTE = timedelta(minutes=1)
TAPE_ANCHOR = VixAnchor(_at(15, 20), 21.13, 27.21)
VIX_TAPE_AT = TAPE_ANCHOR.at
VIX_TAPE_LEVEL = TAPE_ANCHOR.level
VIX_TAPE_CHG = TAPE_ANCHOR.chg_pct
VIX_PRIOR = VIX_TAPE_LEVEL / (1 + VIX_TAPE_CHG / 100)
VIX_BARS = ROOT / "tests/fixtures/vix_2026_11_05_1m.csv"
VIX_BARS_SOURCE = "yfinance_1m"
DEFAULT_SPEC = session_spec(SESSION, daily_start=date(2026, 7, 1), vix_bars=VIX_BARS,
                            vix_prior=VIX_PRIOR)
INTERPOLATED_SPEC = replace(DEFAULT_SPEC, vix_anchor=TAPE_ANCHOR, vix_bars=None,
                            vix_prior=None)
```

4. Bars reader, lookup and `vix_path` (the anchor branch is unchanged):

```python
def load_vix_bars(path: Path) -> list[tuple[datetime, float]]:
    """yfinance ``df.to_csv`` one-minute bars: (UTC bar start, Close), sorted."""
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    close = rows[0].index("Close")
    out = []
    for row in rows[1:]:
        if not row or row[0] in ("Ticker", "Datetime") or not row[close]:
            continue
        at = datetime.fromisoformat(row[0])
        if at.tzinfo is None:
            raise ValueError(f"naive bar time {row[0]!r} in {path}")
        out.append((at.astimezone(UTC), float(row[close])))
    return sorted(out)


@lru_cache(maxsize=8)
def _bars(path: Path) -> tuple:
    return tuple(load_vix_bars(path))


def vix_from_bars(bars, t: datetime, prior: float) -> dict:
    """Point in time: the close of the last bar whose minute has ended by ``t``."""
    done = [close for start, close in bars if start + MINUTE <= t]
    if not done:
        raise ValueError(f"no one-minute VIX bar finished by {t.isoformat()}")
    return {"level": round(done[-1], 4), "chg_pct": round((done[-1] / prior - 1) * 100, 4)}


def vix_path(t: datetime, spec: SessionSpec = DEFAULT_SPEC) -> dict:
    if spec.vix_bars is not None:
        return vix_from_bars(_bars(spec.vix_bars), t, spec.vix_prior)
    ...  # V222-6's anchor / no-anchor body, unchanged
```

`list(csv.reader(...))[0].index("Close")` raises `ValueError` when the column is missing.

5. Provenance and notes (replace V222-6's `_provenance`; `_vix_note` gains a first branch;
   `_alpaca_note` keys the old text on `INTERPOLATED_SPEC`):

```python
def _session_keys(spec: SessionSpec) -> dict:
    a = spec.vix_anchor
    anchor = None if a is None else {"at": a.at.isoformat(), "level": a.level,
                                     "chg_pct": a.chg_pct}
    return {"session": spec.day.isoformat(), "vix_anchor": anchor}


def _provenance(spec: SessionSpec) -> dict:
    """No extra key for the 2026-11-05 specs; vix_source last whenever bars are used."""
    out = {} if spec in (DEFAULT_SPEC, INTERPOLATED_SPEC) else _session_keys(spec)
    if spec.vix_bars is not None:
        out["vix_source"] = VIX_BARS_SOURCE
    return out
```

`_vix_note(spec)` first returns, when `spec.vix_bars is not None`: `f"VIX from one-minute
^VIX bars ({spec.vix_bars.name}, yfinance): the close of the last bar finished by each
step, change against the prior session's close"`. In `_alpaca_note`, replace
`if spec == DEFAULT_SPEC:` with `if spec == INTERPOLATED_SPEC:` (old text, unchanged).
`_synthetic_fixture` and `build_fixture` already write `spec.vix_anchor is not None` and
`**_provenance(spec)`, so a bars spec writes `false` and `vix_source` with no further edit.

`_parse`, `resolve_spec` and `main` are unchanged in this task (V222-6d adds the CLI).

- [ ] **Step 5: Run the tests and the complexity gate, commit (v209 branch)**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scripts/test_build_shock_replay_fixture.py`
Expected: PASS, `0 failed`.

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/complexity_gate.py`
Expected: exit 0 (`load_vix_bars` about 6, the rest under 5).

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector add tests/fixtures/vix_2026_11_05_1m.csv scripts/data/build_shock_replay_fixture.py tests/scripts/test_build_shock_replay_fixture.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector commit -m "feat(v222): replay fixture VIX from real one-minute ^VIX bars, point-in-time (V222-6c)"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the main-tree status shows nothing from this task.


### Task V222-6d: Builder `--vix-bars` CLI and the rebuilt 2026-11-05 fixture

**Model:** sonnet — two argparse flags over V222-6c's functions, one checkpointed rebuild checked by shape only, one provenance line in the untracked replay test.

**Never print, read or quote a VIX value** from the CSV or from any fixture, and never run
the detector over the rebuilt fixture (V222-6c's rule). Stage 3 (V222-13) is the only reader.

**Files:**
- Modify: `.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/data/build_shock_replay_fixture.py`
- Modify: `.claude/worktrees/2026-11-05-v209-market-shock-detector/tests/scripts/test_build_shock_replay_fixture.py`
- Modify: `.claude/worktrees/2026-11-05-v209-market-shock-detector/tests/fixtures/shock_replay_2026_11_05.json` (rebuilt, Step 5)
- Modify (untracked, one line): `.claude/worktrees/2026-11-05-v209-market-shock-detector/tests/market/test_shock_replay_2026_11_05.py`

**Interfaces:**
- Consumes (V222-6b/6c): `parse_anchor`, `resolve_spec`, `_parse`, `main`, `session_spec(..., vix_bars=, vix_prior=)`, `_bars`, `VIX_PRIOR`, `SESSION`, `DEFAULT_SPEC`; test helpers `D`, `_vix_csv`.
- Produces (for V222-13, V222-14):
  - CLI `--vix-bars PATH` and `--vix-prior LEVEL` (`--vix-prior` defaults to `VIX_PRIOR` on 2026-11-05, required otherwise); `--vix-bars` with `--vix-anchor`, without a prior, or naming an unreadable file exits `2` and writes nothing.
  - The committed `tests/fixtures/shock_replay_2026_11_05.json` rebuilt from `DEFAULT_SPEC` (bars): `source` `alpaca`, 26 steps, `vix_interpolated: false`, `vix_source: "yfinance_1m"`, every non-VIX field equal to commit `eafc6eb8`'s.
  - `test_the_fixture_has_the_frozen_shape` in the untracked replay test asserts that provenance; the replay test's sha256 after this task (V222-14 Step 0 compares against it).

- [ ] **Step 1: Write the failing test**

Append to `W/tests/scripts/test_build_shock_replay_fixture.py`:

```python
def test_cli_vix_bars_records_the_source_and_refuses_bad_combinations(tmp_path, monkeypatch):
    monkeypatch.setattr(bsr, "_trades", lambda: [])
    day = date(2020, 3, 16)
    path = _vix_csv(tmp_path / "v.csv", [(D(day, 13, 0), 20.0)])
    out = tmp_path / "fx.json"
    assert bsr.main(["--session", "2020-03-16", "--vix-bars", str(path), "--vix-prior", "20",
                     "--synthetic", "--out", str(out)]) == 0
    fx = json.loads(out.read_text())
    assert (fx["vix_interpolated"], fx["vix_source"]) == (False, "yfinance_1m")
    bad = tmp_path / "bad.json"
    for argv in (["--vix-bars", str(path), "--vix-anchor", "15:20,21.13,27.21"],
                 ["--session", "2020-03-16", "--vix-bars", str(path)],
                 ["--vix-bars", str(tmp_path / "missing.csv")]):
        assert bsr.main([*argv, "--synthetic", "--out", str(bad)]) == 2
    assert not bad.exists()
```

- [ ] **Step 2: Run the tests to see it fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scripts/test_build_shock_replay_fixture.py`
Expected: FAIL — `unrecognized arguments: --vix-bars` (the rest pass).

- [ ] **Step 3: Implement**

In `W/scripts/data/build_shock_replay_fixture.py`, `_parse` adds `ap.add_argument("--vix-bars", default=None)` and
`ap.add_argument("--vix-prior", default=None, type=float)`; `resolve_spec` becomes:

```python
def _bars_prior(args, day: date) -> float | None:
    if args.vix_prior is not None or args.vix_bars is None:
        return args.vix_prior
    return VIX_PRIOR if day == SESSION else None      # SessionSpec then raises


def resolve_spec(args) -> SessionSpec:
    if args.session is None and args.vix_anchor is None and args.vix_bars is None:
        return DEFAULT_SPEC
    day = args.session or SESSION
    anchor = parse_anchor(args.vix_anchor, day) if args.vix_anchor else None
    bars = Path(args.vix_bars) if args.vix_bars else None
    spec = session_spec(day, anchor, vix_bars=bars, vix_prior=_bars_prior(args, day))
    if bars is not None:
        _bars(bars)                                   # unreadable file -> OSError here
    return spec
```

In `main`, catch `(ValueError, OSError)` around `resolve_spec` and print
`bad --session / --vix-anchor / --vix-bars: {exc}` (exit 2, nothing written). Usage line
gains `[--vix-bars PATH [--vix-prior LEVEL]]`.
Docstring: append to V222-6c's VIX paragraph "`--vix-anchor` (interpolated) and
`--vix-bars PATH [--vix-prior LEVEL]` (real bars, any session) are mutually exclusive."

- [ ] **Step 4: Run the tests and the complexity gate, commit (v209 branch)**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scripts/test_build_shock_replay_fixture.py`
Expected: PASS, `0 failed`.

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/complexity_gate.py`
Expected: exit 0 (`resolve_spec` about 6).

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector add scripts/data/build_shock_replay_fixture.py tests/scripts/test_build_shock_replay_fixture.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector commit -m "feat(v222): builder --vix-bars and --vix-prior flags (V222-6d)"
```

- [ ] **Step 5: Rebuild the committed 2026-11-05 fixture (checkpointed; shape checks only)**

The per-ticker cache `W/market_data/shock_replay_2026_11_05/` is reused, so only VIX
should change. `W` has no `.env`: the runner loads `M/.env` into the environment before
the builder imports `swingbot.config`; nothing prints a key.

```bash
python -c "from dotenv import load_dotenv; load_dotenv('E:/Documents/Private/Projects/Discord-Bot/.env'); import runpy, sys; sys.argv = ['build_shock_replay_fixture.py']; runpy.run_path('E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/data/build_shock_replay_fixture.py', run_name='__main__')"
```

Expected: one line `wrote .../tests/fixtures/shock_replay_2026_11_05.json: alpaca, 26 steps, <m> long entries`.
Then check structure only (every printed value is a flag, a count or a boolean):

```bash
python -c "import json, subprocess; W='E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector'; new=json.load(open(W+'/tests/fixtures/shock_replay_2026_11_05.json', encoding='utf-8')); old=json.loads(subprocess.run(['git','-C',W,'show','eafc6eb8:tests/fixtures/shock_replay_2026_11_05.json'],capture_output=True,text=True,check=True).stdout); strip=lambda f:[{k:v for k,v in s.items() if k!='vix'} for s in f['steps']]; print(new['source'], len(new['steps']), new['vix_interpolated'], new['vix_source'], list(new), strip(new)==strip(old), new['long_entries']==old['long_entries'])"
sha256sum E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/tests/fixtures/shock_replay_2026_11_05.json
```

Expected: `alpaca 26 False yfinance_1m ['source', 'vix_interpolated', 'note', 'steps', 'vix_source', 'long_entries'] True True`.
Anything else (`synthetic`, a `False` comparison) stops the task: report it, do not
commit the fixture, never patch it by hand. Never print `steps`, `vix` or `note`.

- [ ] **Step 6: Align the untracked replay test's provenance line (one line, no run of the detector)**

In `W/tests/market/test_shock_replay_2026_11_05.py::test_the_fixture_has_the_frozen_shape`,
replace `fx["vix_interpolated"] is True` with
`fx["vix_interpolated"] is False and fx["vix_source"] == "yfinance_1m"`. Nothing else in
the file changes (deadline, rules and the four other tests stay as they are); it stays
untracked until V222-14. Run that one test only (it reads shape, never the detector):

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/market/test_shock_replay_2026_11_05.py::test_the_fixture_has_the_frozen_shape`
Expected: `1 passed`. Never run the file's other tests here.

`sha256sum` the replay test and put both hashes (fixture, replay test) in the task report;
V222-14 Step 0 compares the replay test against that hash.

- [ ] **Step 7: Commit the rebuilt fixture (v209 branch)**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector add tests/fixtures/shock_replay_2026_11_05.json
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector commit -m "test(v222): rebuild the 2026-11-05 replay fixture with one-minute VIX bars (V222-6d)"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the main-tree status shows nothing from this task; `W`'s status shows only the
untracked replay test.
