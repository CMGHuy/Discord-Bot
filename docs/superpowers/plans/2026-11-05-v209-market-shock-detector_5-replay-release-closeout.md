# v209 — Market-shock detector (shadow), Track 1 — Part 5: replay, release, close-out

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v209 — Market-shock detector](../specs/2026-11-05-v209-market-shock-detector-design.md) (main @ ea65d908; the replay target is 15:00 UTC, not 14:36)
**Index:** [`_0-index.md`](2026-11-05-v209-market-shock-detector_0-index.md) — Global Constraints, Review Focus, Parallelisation and the task ledger apply to every task below.
**Brief:** `.superpowers/briefs/2026-11-05-v209-market-shock-detector.md` (§6 replay feasibility, D8 rollback, T7 tape flags)

Tasks: V209-12 (the 2026-11-05 replay fixture and its test), V209-13 (release
in `shadow`: production checks, rollback line, bot bump, deploy) and V209-14
(`/panel` and `/close-out` without a second bump).

**Scope note (partner, 2026-11-06):** the `market_shock` Discord notice and the
admin tape badge (old V209-9..V209-11, part 4) moved to their own follow-on
plan. This part does not depend on them, the release is a **bot minor bump
only** (no `ui` line), and the shadow soak is checked through the
`market_shock_readings` / `market_shock_state` rows, never through notices.

# Phase G — Replay

### Task V209-12: 2026-11-05 replay fixture (Alpaca, synthetic fallback) + replay test

**Model:** sonnet — a bounded script and tests on fixed contracts; the network fetch and checkpointing follow the existing `alpaca_history` pattern.

> **Amended by A1** ([A1 index](2026-11-05-v209-market-shock-detector-a1_0-index.md), V209-A1-2b): the builder gains a session date, DST-aware bounds, a daily-VIX path and a validation mode writing gzip fixtures under `tests/fixtures/shock_replay/` (never synthetic); the 2026-11-05 path and its committed fixture are unchanged.

V209-12 was split at the 20 KB task cap: this task builds the fixture builder, its tests and the committed fixture; **V209-12b** adds the replay test over that fixture and runs straight after it.

**Files:**
- Create: `scripts/data/build_shock_replay_fixture.py`
- Create: `tests/fixtures/shock_replay_2026_11_05.json` (written by the script, committed)
- Create: `tests/scripts/test_build_shock_replay_fixture.py` (suite owning `tests/scripts/`)

No new `tests/` directory, so `tests/suites.toml` does not change.

**Interfaces:**
- Consumes: `shock.ShockThresholds`, `NameRow`, `VixTape`, `ShockSnapshot`, `ShockState`, `measure`, `step` (V209-2..V209-4); `shock_scan.build_snapshot(frames, live_prices, sector_of, *, now, quotes_at, vix, th, spy_ticker, spy_df=None, qqq_ticker="QQQ")` (V209-6). These already exist: `alpaca_history.fetch.fetch_raw(provider, ticker, timeframe, start, end, *, limiter, sleep=...)` and `to_store_frame(timeframe, raw)`; `alpaca_history.guards.TokenBucket(rate_per_minute)`; `fetch_alpaca_history.make_provider()` (raises `AlpacaAuthError` without keys); `swingbot.core.scanning.fetch._sector_etfs_for_tickers(tickers) -> (sector_of, etfs)`; `swingbot.core.marketdata.watchlist.load_watchlist()`; `swingbot.core.scanning.singletons.trade_log.get_trades(limit=None)` (rows with `ticker`, `direction`, ISO `opened_at`).
- Produces (V209-12b reads it): the fixture JSON
  `{"source": "alpaca" | "synthetic", "vix_interpolated": true, "note": str, "long_entries": [{"ticker", "opened_at"}], "steps": [{"as_of", "minutes_since_open", "vix": {"level", "chg_pct"}, "spy": NameRow-dict, "qqq": NameRow-dict | null, "names": [NameRow-dict]}]}`.
  `long_entries` is an addition to the ledger's shape, consumed only by V209-12b's report. A NameRow-dict is `dataclasses.asdict(NameRow)`.

**Fixed facts (spec § Track 1 tests; brief §6):**
- 2026-11-05 is on Eastern Standard Time, so the session runs 14:30–21:00 UTC. The steps are the 15-minute bar ends from **14:45 to 21:00 UTC**, 26 in all; 14:45 is the first reading the open-settle rule counts.
- Each name's `last` at step `t` is the close of the last 15-minute bar that has finished by `t` (bar start + 15 min ≤ `t`). `prev_close` and `atr14` come from the daily bars up to and including 2026-11-04, exactly as `build_snapshot` derives them, with `quotes_at = now = t`.
- VIX comes from the tape reading at 15:20 UTC: level 21.13, change +27.21 % (prior close = 21.13 / 1.2721). `chg_pct` rises linearly from 0 at 14:30 to 27.21 at 15:20, then holds. Level = prior × (1 + chg/100). This is marked `vix_interpolated: true`, and `note` explains it.
- Acceptance: the first SHOCK `as_of` ≤ **2026-11-05T15:00:00Z**. The settle rule and the two-reading rule make 15:00 also the earliest possible SHOCK. The test reports how many longs opened at or after 14:36 UTC (the spec counts 18) opened before that SHOCK.
- If Alpaca cannot be used (no keys, an auth or fetch error, or fewer than `ShockThresholds().min_names` = 20 equities with both bar sets), the script writes a **synthetic** fixture with the reason in `note`. It never skips, and the replay test fails when the fixture file is missing.
- **If the Alpaca fixture's first SHOCK is later than 15:00 UTC, that is a measured answer.** Stop and report the per-step table (time, breadth, sectors, speed, label) to the controller. Never tune a threshold, edit the fixture, or switch to the synthetic path to make the test pass.
- **Checkpoint** (working-conventions § Long runs must checkpoint): each ticker's raw daily and 15-minute bars are written to `market_data/shock_replay_2026_11_05/<TICKER>.json` (gitignored) as soon as the ticker is fetched, and a rerun skips tickers already on disk. About 80 tickers × 2 calls at 120/min takes about 1.5 minutes, so progress prints every 10 tickers.

- [ ] **Step 1: Write the failing builder tests**

`tests/scripts/test_build_shock_replay_fixture.py`:

```python
"""v209 V209-12: the 2026-11-05 replay fixture builder."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "data"))
import build_shock_replay_fixture as bsr  # noqa: E402

from swingbot.core.market import shock  # noqa: E402

UTC = timezone.utc


def T(h, m):
    return datetime(2026, 11, 5, h, m, tzinfo=UTC)


def _daily(close=100.0, n=30):
    idx = pd.date_range(end="2026-11-04 05:00", periods=n, freq="B", tz=UTC)
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": 1000}, index=idx)


def _m15(closes, start=None):
    start = start or T(14, 30)
    idx = pd.DatetimeIndex([start + timedelta(minutes=15 * i) for i in range(len(closes))])
    return pd.DataFrame({"open": closes, "high": closes, "low": closes, "close": closes,
                         "volume": 10}, index=idx)


class FakeProvider:
    def __init__(self):
        self.calls = []

    def history_bars(self, ticker, timeframe, start, end):
        self.calls.append((ticker, timeframe))
        return _m15([99.0, 97.0, 95.0]) if timeframe == "15min" else _daily()


def test_steps_are_the_bar_ends_from_the_settled_open_to_the_close():
    steps = bsr.step_times()
    assert (steps[0], steps[-1], len(steps)) == (T(14, 45), T(21, 0), 26)
    assert all(b - a == timedelta(minutes=15) for a, b in zip(steps, steps[1:]))


def test_last_is_the_close_of_the_last_finished_bar():
    bars = _m15([10.0, 11.0])                    # bars start 14:30 and 14:45
    assert bsr.last_at(bars, T(14, 40)) is None
    assert bsr.last_at(bars, T(14, 45)) == 10.0
    assert bsr.last_at(bars, T(15, 0)) == 11.0
    assert bsr.last_at(None, T(15, 0)) is None


def test_vix_path_climbs_to_the_tape_reading_then_holds():
    prior = 21.13 / 1.2721
    assert bsr.vix_path(T(14, 30)) == {"level": round(prior, 4), "chg_pct": 0.0}
    assert bsr.vix_path(T(14, 55))["chg_pct"] == pytest.approx(13.605, abs=1e-3)
    late = bsr.vix_path(T(18, 0))
    assert late["chg_pct"] == pytest.approx(27.21)
    assert late["level"] == pytest.approx(21.13, abs=1e-3)


def test_a_step_applies_the_live_snapshot_rules(monkeypatch):
    monkeypatch.setattr("swingbot.core.marketdata.asset_class.classify",
                        lambda t: "etf" if t in ("SPY", "QQQ") else "equity")
    daily = {"AAA": bsr.to_daily(_daily(100.0)), "SPY": bsr.to_daily(_daily(500.0))}
    bars = {"AAA": _m15([99.0, 97.0]), "SPY": _m15([498.0, 495.0])}
    step = bsr.fixture_step(T(15, 0), daily, bars, {"AAA": "Tech"})
    (aaa,) = [n for n in step["names"] if n["ticker"] == "AAA"]
    assert (aaa["last"], aaa["prev_close"], aaa["sector"], aaa["is_equity"]) == (97.0, 100.0, "Tech", True)
    assert aaa["atr14"] == pytest.approx(2.0)
    assert step["spy"]["last"] == 495.0 and step["qqq"] is None
    assert step["as_of"] == "2026-11-05T15:00:00+00:00" and step["minutes_since_open"] == 30.0
    assert step["vix"] == bsr.vix_path(T(15, 0))


def test_long_entries_keep_longs_from_the_turn_to_the_close_sorted():
    trades = [
        {"ticker": "AMD", "direction": "bullish", "opened_at": "2026-11-05T15:10:00+00:00"},
        {"ticker": "STX", "direction": "bullish", "opened_at": "2026-11-05T14:36:00+00:00"},
        {"ticker": "MU", "direction": "bullish", "opened_at": "2026-11-05T14:20:00+00:00"},
        {"ticker": "SNDK", "direction": "bearish", "opened_at": "2026-11-05T15:00:00+00:00"},
        {"ticker": "LRCX", "direction": "bullish", "opened_at": "2026-11-06T14:40:00+00:00"},
    ]
    assert bsr.long_entries(trades) == [
        {"ticker": "STX", "opened_at": "2026-11-05T14:36:00+00:00"},
        {"ticker": "AMD", "opened_at": "2026-11-05T15:10:00+00:00"},
    ]


def test_synthetic_steps_are_sufficient_and_sector_balanced():
    steps = bsr.synthetic_steps()
    assert [s["as_of"] for s in steps] == [t.isoformat() for t in bsr.step_times()]
    names = steps[0]["names"]
    sectors = {n["sector"] for n in names}
    assert sum(n["is_equity"] for n in names) >= shock.ShockThresholds().min_names
    assert all(sum(n["sector"] == s for n in names) >= 2 for s in sectors)


def _run(tmp_path, monkeypatch, provider, tickers=("AAA", "BBB")):
    monkeypatch.setattr(bsr, "_trades", lambda: [])
    out = tmp_path / "fx.json"
    rc = bsr.main(["--tickers", ",".join(tickers), "--out", str(out),
                   "--cache-dir", str(tmp_path / "cache")],
                  provider=provider, limiter=bsr.TokenBucket(10**6))
    return rc, json.loads(out.read_text())


def test_too_few_names_falls_back_to_synthetic_and_says_why(tmp_path, monkeypatch):
    rc, fx = _run(tmp_path, monkeypatch, FakeProvider())
    assert rc == 0 and fx["source"] == "synthetic" and fx["vix_interpolated"] is True
    assert "fewer than 20 equities" in fx["note"] and len(fx["steps"]) == 26


def test_missing_keys_fall_back_to_synthetic(tmp_path, monkeypatch):
    def no_keys():
        raise bsr.AlpacaAuthError("ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY are not set")
    monkeypatch.setattr(bsr, "make_provider", no_keys)
    _, fx = _run(tmp_path, monkeypatch, None)
    assert fx["source"] == "synthetic" and "AlpacaAuthError" in fx["note"]


def test_each_ticker_is_checkpointed_and_a_rerun_fetches_nothing(tmp_path, monkeypatch):
    _run(tmp_path, monkeypatch, FakeProvider())
    cached = sorted(p.stem for p in (tmp_path / "cache").glob("*.json"))
    assert cached == ["AAA", "BBB", "QQQ", "SPY"]
    again = FakeProvider()
    _run(tmp_path, monkeypatch, again)
    assert again.calls == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_build_shock_replay_fixture.py`
Expected: FAIL (`ModuleNotFoundError: build_shock_replay_fixture`).

- [ ] **Step 3: Implement `scripts/data/build_shock_replay_fixture.py`**

Module docstring: v209 V209-12, what the fixture is, the 14:45–21:00 UTC steps, the interpolated VIX, the synthetic fallback, the checkpoint directory, and usage (`python scripts/data/build_shock_replay_fixture.py [--tickers A,B] [--synthetic]`). Bootstrap `sys.path` the way `fetch_alpaca_history.py:30-35` does (repo root plus `scripts/data`), then import `fetch_raw`, `to_store_frame` and `TokenBucket` from `alpaca_history`, and `make_provider` and `AlpacaAuthError` from `fetch_alpaca_history`, as module attributes the tests can patch.

Constants: `SESSION = date(2026, 11, 5)`, `OPEN_UTC = 14:30`, `CLOSE_UTC = 21:00`, `TURN_UTC = 14:36` (all aware UTC on `SESSION`); `STEP = timedelta(minutes=15)`; `VIX_TAPE_AT = 15:20 UTC`, `VIX_TAPE_LEVEL = 21.13`, `VIX_TAPE_CHG = 27.21`, `VIX_PRIOR = VIX_TAPE_LEVEL / (1 + VIX_TAPE_CHG / 100)`; `DAILY_START = date(2026, 7, 1)`; `DEFAULT_OUT = ROOT / "tests/fixtures/shock_replay_2026_11_05.json"`; `DEFAULT_CACHE = ROOT / "market_data/shock_replay_2026_11_05"`; `BENCHMARKS = ("SPY", "QQQ")`; `RATE_PER_MINUTE = 120`. Every float in the output is rounded to 4 places.

Functions (each under CC 15):
- `step_times() -> list[datetime]`: `OPEN_UTC + STEP` through `CLOSE_UTC`.
- `vix_path(t: datetime) -> dict`: `chg = VIX_TAPE_CHG * min(1, max(0, (t − OPEN_UTC) / (VIX_TAPE_AT − OPEN_UTC)))`, then `{"level": round(VIX_PRIOR * (1 + chg / 100), 4), "chg_pct": round(chg, 4)}`.
- `last_at(bars: pd.DataFrame | None, t: datetime) -> float | None`: from the bars where `index + STEP <= t`, return the last `close`, or `None` when there is none.
- `to_daily(raw: pd.DataFrame) -> pd.DataFrame`: `to_store_frame("daily", raw)`, the `Open..Volume` frame `build_snapshot` reads.
- `fixture_step(t, daily: dict[str, pd.DataFrame], bars15: dict[str, pd.DataFrame], sector_of: Mapping[str, str]) -> dict`:
  - Call `shock_scan.build_snapshot(daily, live, sector_of, now=t, quotes_at=t, vix=shock.VixTape(None, None, None), th=shock.ShockThresholds(), spy_ticker="SPY", spy_df=daily.get("SPY"))`, where `live = {tk: last_at(bars15.get(tk), t)}` with every `None` dropped.
  - Return `as_of` (ISO), `minutes_since_open`, `vix_path(t)`, `spy` and `qqq` as rounded `asdict` dicts (or `None`), and `names` sorted by ticker.
- `synthetic_steps() -> list[dict]`: the same step times, VIX from `vix_path`, `minutes_since_open = (t − OPEN_UTC)` in minutes.
  - 40 equities `S01..S40` in five sectors of 8 (`Information Technology`, `Financials`, `Health Care`, `Industrials`, `Consumer Discretionary`), each with `prev_close 100.0` and `atr14 2.0`.
  - Down share 0.65 before minute 150, 0.25 after; in each sector the first `round(share × 8)` members are down.
  - A down name's `last` is `prev − 1.6 × atr`; every other name's is `prev − 0.3 × atr`.
  - SPY: prev 500, ATR 5, `last` 494.0. QQQ: prev 400, ATR 6, `last` 391.0. Both carry `is_equity=False` and `sector=None`.
  - This is shaped on the day: a broad, multi-sector drop from the open, easing in the afternoon.
- `load_or_fetch(ticker, provider, limiter, cache_dir: Path) -> tuple[pd.DataFrame | None, pd.DataFrame | None]`:
  - When `<cache_dir>/<ticker>.json` exists, read it. Otherwise fetch daily with `fetch_raw(provider, ticker, "daily", DAILY_START, datetime(2026, 11, 5, tzinfo=UTC), limiter=limiter)` and 15-minute bars with `fetch_raw(provider, ticker, "15min", SESSION, CLOSE_UTC, limiter=limiter)`.
  - Write both to the file atomically (`.tmp`, then `os.replace`) **before** returning, as `{"daily": rows | null, "m15": rows | null}`, where `rows = [[iso_utc, open, high, low, close, volume], ...]`.
  - Rebuild a frame with `pd.to_datetime(..., utc=True)` and lowercase columns. A cached ticker makes no provider call.
- `long_entries(trades: list[dict]) -> list[dict]`: `direction == "bullish"` and `TURN_UTC <= opened_at < CLOSE_UTC`, as `{"ticker", "opened_at"}`, sorted by `opened_at`.
- `_trades() -> list[dict]`: `singletons.trade_log.get_trades(limit=None)`, imported inside the function. On any exception, return `[]`; `main` appends `"long entries unavailable: <ExcType>"` to the note.
- `build_fixture(tickers, *, provider, limiter, cache_dir) -> dict`:
  - Add the benchmarks to the tickers and fetch each through `load_or_fetch`, printing `[i/n] TICKER` every 10 tickers.
  - Daily frames go through `to_daily`; the 15-minute frames stay raw (UTC index). Take `sector_of` from `fetch._sector_etfs_for_tickers(list(tickers))[0]`.
  - Count the equities that have both bar sets (`asset_class.classify(t) == "equity"`). Below `ShockThresholds().min_names`, return the synthetic fixture with the note `"alpaca: fewer than 20 equities with daily + 15-minute bars (<k>); synthetic sequence shaped on the day"`.
  - Otherwise return `source: "alpaca"` with `[fixture_step(t, daily, bars15, sector_of) for t in step_times()]`. Its note names the ticker count, the VIX interpolation from the 15:20 UTC tape reading, and that `long_entries` comes from the trade log.
- `main(argv=None, *, provider=None, limiter=None) -> int`:
  - Flags: `--tickers` (comma list, default `load_watchlist()`), `--out`, `--cache-dir`, `--synthetic`.
  - Get the provider from `make_provider()` when none is passed, and the limiter from `TokenBucket(RATE_PER_MINUTE)` when none is passed. On `AlpacaAuthError` or any fetch exception, write synthetic with `note = f"alpaca unavailable: {type(exc).__name__}: {exc}; synthetic sequence shaped on the day"`.
  - Always write `vix_interpolated: true` and `long_entries` (`long_entries(_trades())`), with `json.dumps(fixture, indent=1)` plus a newline.
  - Print `wrote <out>: <source>, <n> steps, <k> long entries` and return 0.

- [ ] **Step 4: Run the builder tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_build_shock_replay_fixture.py`
Expected: PASS, 9 tests.

- [ ] **Step 5: Build the real fixture**

Run `/replicate-prod-db` first, so `load_watchlist()` and the trade log read the production replica (one shared `swing-db`; `.env` values never printed). Then:

```bash
python scripts/data/build_shock_replay_fixture.py
```

Expected: `wrote tests/fixtures/shock_replay_2026_11_05.json: alpaca, 26 steps, <k> long entries`. A `synthetic` result is acceptable only with its reason in `note`; repeat that reason in the commit message. `git check-ignore market_data/shock_replay_2026_11_05/SPY.json` must print the path (the cache is never committed).

- [ ] **Step 6: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: no new violation.

- [ ] **Step 7: Commit**

```bash
git add scripts/data/build_shock_replay_fixture.py tests/fixtures/shock_replay_2026_11_05.json tests/scripts/test_build_shock_replay_fixture.py
git commit -m "test(v209): 2026-11-05 replay fixture builder + frozen fixture (<source>) (V209-12)"
```

### Task V209-12b: replay test over the 2026-11-05 fixture

**Model:** sonnet — one test module over a frozen fixture and the finished detector; the only judgment is reading a miss as a measured answer.

> **Superseded by Amendment A1** ([A1 index](2026-11-05-v209-market-shock-detector-a1_0-index.md), V209-A1-4). The run below produced the measured miss (a382234d: NORMAL all session). A1 renames this test to `tests/market/test_shock_acceptance_a1.py` and replaces its rules: the `≤ 15:00 UTC` gate and the synthetic escape are gone, 2026-11-05 is reported in-sample only, and the gate is recall and per-class precision over the frozen validation days. Do not implement the steps below.

Split from V209-12 at the 20 KB cap; it runs straight after V209-12, on that task's committed fixture.

**Files:**
- Create: `tests/market/test_shock_replay_2026_11_05.py` (suite `market-signals`; no `suites.toml` change)

**Interfaces:**
- Consumes: the fixture JSON V209-12 produces (shape in V209-12's Interfaces, including `long_entries`); `shock.ShockThresholds`, `NameRow`, `VixTape`, `ShockSnapshot`, `ShockState`, `measure(snapshot, prev, th)`, `step(state, reading, th)` (V209-2..V209-4).
- Produces: none (the acceptance test of Track 1's replay).

**Rules (spec § Track 1 tests, as amended at ea65d908):**
- The detector runs with default `ShockThresholds()` (the config defaults) from a fresh `ShockState()`. Each step's `measure` gets the previous reading as `prev`, and the step's VIX is stamped with the step's own `as_of`, so it is fresh.
- First SHOCK `as_of` ≤ **2026-11-05T15:00:00Z**. The second assertion (≥ 15:00) pins that the open-settle and two-reading rules still hold on the day, so together they pin SHOCK at exactly the first moment the rules allow.
- The report line counts the `long_entries` opened before the first SHOCK. It is printed, not asserted against the spec's 18.
- A missing fixture fails. **A miss on an `alpaca` fixture is a measured answer:** stop and report the per-step table (time, `breadth_frac`, `sectors_down`/`sectors_total`, `breadth_speed`, label) to the controller. Never tune a threshold, regenerate the fixture, or switch to synthetic to make it pass.

- [ ] **Step 1: Write the replay test**

`tests/market/test_shock_replay_2026_11_05.py`:

```python
"""v209 V209-12: the detector replayed over the frozen 2026-11-05 session.

Built by scripts/data/build_shock_replay_fixture.py. A missing fixture
fails: this test never skips (spec, Track 1 tests)."""
import json
from datetime import date, datetime, timezone
from pathlib import Path

from swingbot.core.market import shock

UTC = timezone.utc
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "shock_replay_2026_11_05.json"
SESSION = date(2026, 11, 5)
DEADLINE = datetime(2026, 11, 5, 15, 0, tzinfo=UTC)


def _fixture() -> dict:
    assert FIXTURE.exists(), "run scripts/data/build_shock_replay_fixture.py (V209-12)"
    return json.loads(FIXTURE.read_text())


def _row(d):
    return shock.NameRow(**d) if d else None


def _snapshot(step) -> shock.ShockSnapshot:
    as_of = datetime.fromisoformat(step["as_of"])
    vix = shock.VixTape(step["vix"]["level"], step["vix"]["chg_pct"], as_of)
    return shock.ShockSnapshot(
        as_of=as_of, session_date=SESSION, minutes_since_open=step["minutes_since_open"],
        names=tuple(_row(n) for n in step["names"]), spy=_row(step["spy"]),
        qqq=_row(step["qqq"]), vix=vix)


def _replay(fx, th=shock.ShockThresholds()):
    state, prev, out = shock.ShockState(), None, []
    for step in fx["steps"]:
        reading = shock.measure(_snapshot(step), prev, th)
        state, prev = shock.step(state, reading, th), reading
        out.append((reading, state.label))
    return out


def _first_shock(fx) -> datetime:
    return next(r.as_of for r, label in _replay(fx) if label == "SHOCK")


def test_the_fixture_has_the_frozen_shape():
    fx = _fixture()
    assert fx["source"] in ("alpaca", "synthetic") and fx["vix_interpolated"] is True
    assert isinstance(fx["note"], str) and fx["note"]
    times = [datetime.fromisoformat(s["as_of"]) for s in fx["steps"]]
    assert times == sorted(times) and len(times) == 26
    assert times[0] == datetime(2026, 11, 5, 14, 45, tzinfo=UTC)
    assert times[-1] == datetime(2026, 11, 5, 21, 0, tzinfo=UTC)


def test_every_reading_up_to_the_deadline_is_sufficient():
    early = [r for r, _ in _replay(_fixture()) if r.as_of <= DEADLINE]
    assert early and not any(r.insufficient for r in early)


def test_the_detector_reaches_shock_no_later_than_fifteen_hundred_utc():
    assert _first_shock(_fixture()) <= DEADLINE


def test_settle_and_two_readings_still_hold_on_the_day():
    # 15:00 is the earliest SHOCK the spec's rules allow on 15-minute steps
    assert _first_shock(_fixture()) >= DEADLINE


def test_report_the_longs_opened_before_the_first_shock(capsys):
    fx = _fixture()
    first = _first_shock(fx)
    entries = fx["long_entries"]
    before = [e for e in entries if datetime.fromisoformat(e["opened_at"]) < first]
    assert 0 <= len(before) <= len(entries)
    with capsys.disabled():
        print(f"\nv209 replay ({fx['source']}): {len(before)} of {len(entries)} longs "
              f"opened at/after 14:36 UTC opened before the first SHOCK at {first:%H:%M} UTC")
```

- [ ] **Step 2: Run it**

Run: `python scripts/dev/testrun.py file tests/market/test_shock_replay_2026_11_05.py`
Expected: PASS, 5 tests, plus the line `v209 replay (<source>): <x> of <n> longs opened at/after 14:36 UTC opened before the first SHOCK at 15:00 UTC`. The detector and fixture already exist, so there is no red phase; a failure here is the measured answer the Rules describe, not a code bug to fix in this task.

- [ ] **Step 3: Commit**

Put the report line in the commit body, and note how far `<n>` is from the spec's 18 if it differs.

```bash
git add tests/market/test_shock_replay_2026_11_05.py
git commit -m "test(v209): replay 2026-11-05 -- first SHOCK 15:00 UTC, <x> of <n> post-14:36 longs before it (V209-12b)"
```

# Phase H — Release

### Task V209-13: Release: prod checks, rollback line, bump, deploy in `shadow`

**Model:** opus — it touches production (schema migration, `.env`, deploy) and a wrong rollback line or a skipped check costs a live session.

> **A1 precondition** ([A1 index](2026-11-05-v209-market-shock-detector-a1_0-index.md)): this task runs only after V209-A1-4 recorded **PASS** in `.superpowers/sdd/progress.md`. On an A1 FAIL it does not run; v209 closes `no-lift/`.

**Files:**
- Modify: `docs/deploy/DEPLOY_HETZNER.md`. Add one paragraph to `## Rolling back`, and add a new `### v209: market shock tables` section after `### v205: daily FX rates (fx_daily_rates)`, before `## Accessing the admin UI`.
- Modify: `VERSION.json` (the `bot` line only)
- Modify: `swingbot/admin/version_history.json` (regenerated)

**Interfaces:**
- Consumes: every Track 1 task on the plan branch: V209-1, 2, 2b, 3, 4, 5, 5b, 6, 6a, 6b, 7, 8, 8b, 12 and 12b. The notice and badge tasks (old V209-9..11) are **not** part of this release. Also consumes the revision `v209_001` (V209-5), `config.MARKET_SHOCK_MODE` (V209-1), `shock_scan.shock_mode()` (V209-6) and `loops._prune_shock_readings` (V209-5b). These already exist: `scripts/ops/ssh-hetzner.sh`, `scripts/ops/env_set.py`, `scripts/dev/build_version_matrix.py`, `deploy/deploy.sh` (runs `alembic upgrade head` with the new image before `up`).
- Produces (V209-14 relies on these):
  - Production runs the new image at Alembic `v209_001`, with `MARKET_SHOCK_MODE=shadow` set explicitly in the VM's `.env`.
  - The release commit `release(bot): <version> -- v209 market-shock detector (shadow)` touches `VERSION.json` alone, and is followed by `chore(bot): <version> -- v209 market-shock detector (shadow)` for `version_history.json`. V209-14's double-bump guard looks for exactly that release subject.

**Rules:**
- **Production is the Hetzner VM**, reached only through `bash scripts/ops/ssh-hetzner.sh "<cmd>"`, with stdin piped for scripts. Steps 2 and 8 are read-only. Step 7 changes `.env`, so follow the **`mirror-prod`** skill: the change is written down before it is made, and it is mirrored by the deploy-doc text this task commits in Step 3 (the schema default in `config.py` is already `shadow`, from V209-1).
- **`.env` values are never printed.** Every production check prints a comparison (`True`/`False`), a count or an age, never a raw setting.
- **Bump: bot minor only** (index `Bump:` as amended by the scope change). Read `VERSION.json` from disk at Step 5; never trust a number written here. `ui` and `ui_updated` stay byte-identical.
- No full suite locally. The push to `main` runs CI, and its `deploy` job ships only when every suite is green (`working-conventions.md` § Pipeline watch: watch the run and fix failures until green).
- Do not mention a Discord shock notice or a tape badge in any release text: they ship with the follow-on plan.

- [ ] **Step 1: Preconditions on the plan worktree**

```bash
git log --oneline main..HEAD          # lists every Track 1 task commit (V209-1 .. V209-12b)
python -m alembic heads               # exactly one line: v209_001 (head)
python scripts/dev/complexity_gate.py # no new violation
python scripts/dev/testrun.py changed --dry-run   # shows which suites CI will lean on; nothing to run here
```

Expected: every task id from the Interfaces list appears in a commit subject, and there is one head, `v209_001`. If a task is missing, stop and report it; this task never implements one.

- [ ] **Step 2: Production checks (read-only)**

**A1 empty-table check, first** (V209-A1-1 Step 1 again, right before the deploy): production `SELECT to_regclass('market_shock_readings') IS NOT NULL` prints `f`, and `grep -c '^SHOCK_SECTORS_FRAC' .env` prints `0`; the local replica holds no `market_shock_readings` rows (drop any, as in V209-A1-1). `depth_frac` is a required field with no read-time upcasting, so a pre-A1 row must not exist anywhere. Any other result: stop and report.

Run against the **running (pre-v209) image**:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot alembic current"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && grep -c '^MARKET_SHOCK_MODE=' .env || true"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" <<'PY'
from datetime import datetime, timezone
from swingbot import config
from swingbot.core.marketdata.shared import tape
from swingbot.core.scanning import fetch
print("TAPE_SHARED_ENABLED on:", bool(config.TAPE_SHARED_ENABLED))
print("MARKETDATA_LAYER on:", str(config.MARKETDATA_LAYER).lower() == "on")
print("DAILY_DELTA_FETCH on:", str(config.DAILY_DELTA_FETCH).lower() in ("true", "1"))
e = tape.read_tape(["^VIX"]).get("^VIX")
age = None if e is None or e.as_of is None else (datetime.now(timezone.utc) - (e.as_of if e.as_of.tzinfo else e.as_of.replace(tzinfo=timezone.utc))).total_seconds()
print("VIX row:", e is not None, "proxy:", None if e is None else e.is_proxy, "age_s:", None if age is None else round(age))
q = fetch._fetch_live_prices([config.MARKET_REGIME_TICKER]).get(config.MARKET_REGIME_TICKER)
print("live SPY quote > 0:", bool(q) and float(q) > 0)
PY
```

Expected:
- `alembic current` prints `v197_001 (head)`.
- The `MARKET_SHOCK_MODE` count is `0` (key not set yet).
- The three flags print `True`, `VIX row: True proxy: False`, and `live SPY quote > 0: True`.
- `age_s` stays under 600 during NYSE regular hours; outside them a large age is expected. Record it, and recheck it in Step 8.

**Stop and report** instead of continuing if any of these hold:
- `alembic current` is not `v197_001`, because then `v209_001`'s `down_revision` does not match production.
- The tape or layer flag is `False`, because VIX would read as missing for every reading.
- The live quote fails, because every name would leave the reading.

This task never flips those flags. Record the printed lines (no values beyond these) in `.superpowers/sdd/progress.md`.

- [ ] **Step 3: Deploy doc**

In `docs/deploy/DEPLOY_HETZNER.md` § Rolling back, insert this paragraph directly after the "Find the tag under **your profile → Packages …**" paragraph:

```markdown
**Rolling back past v209: downgrade first, from the new image.** The image-only
path above aborts before `up` when the older image does not know `v209_001`.
Before switching to an image older than v209, run the downgrade from the image
that is still running, then deploy the older tag:

    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot alembic downgrade v197_001"

This drops `market_shock_state` and `market_shock_readings` (the shadow log is
lost). Plans keep `entry_context.shock_state`; older readers ignore the key.
Check `alembic history` first: a revision stacked on `v209_001` later is rolled
back too. `scripts/ops/rollback_to.sh` needs no extra step, because PITR
restores the database at the target's own revision.
```

Then add this section after the `### v205: daily FX rates` section, before `## Accessing the admin UI`:

```markdown
### v209: market shock tables (`market_shock_state`, `market_shock_readings`)

The bot's scheduled `session_scan` takes one shock reading per pass while the
NYSE regular session is open (no holidays, stops at a half-day close) and steps
a NORMAL / SHOCK / RECOVERY state. That is about 390 / `SCAN_INTERVAL_MINUTES`
rows per full session in `market_shock_readings` and one row (`id = 1`) in
`market_shock_state`. `!check`, the recap, the admin-UI scan and the SHORT lane
read the stored label and never write. Neither table raises SSE events.
Every new plan carries `entry_context.shock_state`.

| Flag | Production value | Set |
|---|---|---|
| `MARKET_SHOCK_MODE` | `shadow` (measure, record, stamp; **no trade changes**) | explicitly in `.env` right after the v209 deploy (V209-13) |

**Retention.** `daily_recap` deletes readings older than
`SHOCK_READINGS_KEEP_DAYS` (180) in every mode. It skips the days the recap
does not run, and the delete is idempotent.

**Read-back:**

    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot -c \"SELECT session_date, count(*), min(as_of), max(as_of), sum((state_after = 'SHOCK')::int) AS shock FROM market_shock_readings GROUP BY 1 ORDER BY 1 DESC LIMIT 5\""
    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot -c \"SELECT label, since, session_date, last_reading_id, updated_at FROM market_shock_state\""

**Rollback, in this order:**
1. Behaviour: `python3 scripts/ops/env_set.py MARKET_SHOCK_MODE off`, then `docker compose restart bot`. That means no readings, no state writes and no `shock_state` key, as in bot 2.16.5.
2. Schema: § Rolling back (`alembic downgrade v197_001` from the new image).
3. `scripts/ops/rollback_to.sh` (`--dry-run` first), only for damaged data.

The tables stay until a later spec retires the detector.
```

Check: `grep -n "Rolling back past v209\|### v209: market shock tables" docs/deploy/DEPLOY_HETZNER.md` prints both lines.

```bash
git add docs/deploy/DEPLOY_HETZNER.md
git commit -m "docs(v209): deploy -- downgrade-first rollback line and the market shock tables section (V209-13)"
```

- [ ] **Step 4: Bring the branch up to date**

Follow the **`worktree-lifecycle`** skill: check for concurrent sessions, then merge `main` into the plan branch. On a conflict, resolve it in the branch, run the narrow test of each file touched, and commit the merge. Re-run `python -m alembic heads`; expected is still exactly one head, `v209_001`. If `main` gained a revision on `v197_001`, there are two heads: stop and report, never re-parent here.

- [ ] **Step 5: Release commit (bot minor)**

Read `VERSION.json`. Set `bot` to the next minor (`X.Y.Z → X.(Y+1).0`; from today's `2.16.5` that is `2.17.0`). Set `bot_updated` to now in Berlin time and the existing format `YYYY-MM-DD HH-MM-SS`. Git Bash has no timezone data, so compute it from `date -u` plus 1 h (CET in November). Leave `ui` and `ui_updated` unchanged.

```bash
git diff --stat                        # VERSION.json only, 2 lines changed
git add VERSION.json
git commit -m "release(bot): <version> -- v209 market-shock detector (shadow)"
python scripts/dev/build_version_matrix.py
python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py
git add swingbot/admin/version_history.json
git commit -m "chore(bot): <version> -- v209 market-shock detector (shadow)"
```

Expected: the matrix test passes, and `git log --oneline -2` shows the `release(bot)` commit followed by the `chore(bot)` commit. Never combine or reorder them.

- [ ] **Step 6: Merge, push, watch CI until the deploy job is green**

Merge the plan branch into `main` per `worktree-lifecycle` (no fast-forward over another session's work), then `git push origin main`. Then watch the run:

```bash
gh run list --branch main --limit 1
gh run watch <run-id> --exit-status
```

On a failing suite, read only the failing job's log (`gh run view <run-id> --log-failed`). Fix the failure in a scoped commit, re-run that one test locally (`python scripts/dev/testrun.py file <test>`), push, and watch again until every job, `deploy` included, is green. A fix never weakens a v209 pin.

- [ ] **Step 7: Set the mode explicitly on production (`mirror-prod`)**

Change, written down first: the VM's `/opt/swing-bot/.env` gains `MARKET_SHOCK_MODE=shadow`, the value the deploy doc and the `config.py` default already state. Then:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot alembic current"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && python3 scripts/ops/env_set.py MARKET_SHOCK_MODE shadow && docker compose restart bot"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" <<'PY'
from swingbot.core.scanning import shock_scan
print("shock mode is shadow:", shock_scan.shock_mode() == "shadow")
PY
```

Expected: `v209_001 (head)` and `shock mode is shadow: True`. The mirror is Step 3's committed doc section, together with V209-1's `config.py` default. Nothing else changes on the VM.

- [ ] **Step 8: Shadow soak check (next NYSE regular session)**

Run this after at least two scheduled passes inside regular hours (14:30–21:00 UTC in November, 15:30–22:00 Berlin). If the deploy landed outside those hours, record `soak pending` in `.superpowers/sdd/progress.md` and run this step in the next session; the task is not done until it passes.

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot -At -c \"SELECT count(*) FROM market_shock_readings WHERE session_date = (now() AT TIME ZONE 'America/New_York')::date\""
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot -At -c \"SELECT count(*) FROM market_shock_readings WHERE (as_of AT TIME ZONE 'America/New_York')::time NOT BETWEEN '09:30' AND '16:00'\""
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot -At -c \"SELECT label, last_reading_id IS NOT NULL FROM market_shock_state\""
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot -At -c \"SELECT count(*) FILTER (WHERE doc->'entry_context' ? 'shock_state'), count(*) FROM plans WHERE created_at > now() - interval '6 hours'\""
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose logs --since 6h bot 2>&1 | grep -ci 'scan.shock' || true"
```

Expected:
- Today's reading count is at least 2.
- The outside-hours count is `0`.
- One state row, with a label in `NORMAL|SHOCK|RECOVERY` and `t`.
- Every plan created since the deploy carries the key (the two counts are equal; `0|0` on a quiet day is not a failure).
- Re-run Step 2's VIX line: the age is under 600 s.
- Any `scan.shock` log line is a swallowed error. Report it with its tag; never silence it.

Record the five results, the release version and the release commit SHA in `.superpowers/sdd/progress.md`.

- [ ] **Step 9: Commit**

Nothing is left to commit. Step 3 committed the doc; Step 5 committed the release and the regeneration; any CI fix was committed in Step 6. Confirm `git status --short` is clean on the plan branch, then hand V209-14 the release commit SHA from `git log --oneline -1 --grep="^release(bot): .* -- v209" -- VERSION.json`.

# Phase I — Close-out

### Task V209-14: `/panel` (staff-engineer, quant-researcher, veteran-trader) + `/close-out` without a second bump

**Model:** sonnet — a scripted ritual with one guard; the panel's judgment runs in its own expert agents.

> **A1:** the close-out also moves the A1 amendment stem ([A1 index](2026-11-05-v209-market-shock-detector-a1_0-index.md) and its parts 1 and 2); on an A1 FAIL the controller moves both stems to `no-lift/` instead and this task's panel is not run.

**Files:**
- Move (by `/close-out` Step 6), into `docs/superpowers/plans/implemented/`, the v209 Track 1 plan files:
  - `docs/superpowers/plans/2026-11-05-v209-market-shock-detector_0-index.md`
  - `docs/superpowers/plans/2026-11-05-v209-market-shock-detector_1-detector-core.md`
  - `docs/superpowers/plans/2026-11-05-v209-market-shock-detector_1b-detector-exit.md`
  - `docs/superpowers/plans/2026-11-05-v209-market-shock-detector_2-storage-and-wiring.md`
  - `docs/superpowers/plans/2026-11-05-v209-market-shock-detector_3-scan-wiring-and-stamp.md`
  - `docs/superpowers/plans/2026-11-05-v209-market-shock-detector_3b-byte-identical-pins.md`
  - `docs/superpowers/plans/2026-11-05-v209-market-shock-detector_5-replay-release-closeout.md`
- **Not touched:**
  - `..._4-notices-and-admin.md`, which belongs to the follow-on notice/badge plan.
  - The spec `docs/superpowers/specs/2026-11-05-v209-market-shock-detector-design.md`. It stays in `specs/`: Track 2's plan and the follow-on still build from it, and Track 2's plan closes it.
  - `VERSION.json` and `swingbot/admin/version_history.json`.

**Interfaces:**
- Consumes: V209-13's release commit `release(bot): <version> -- v209 market-shock detector (shadow)` (on `VERSION.json` alone) and its SHA; V209-13 Step 8's soak results in `.superpowers/sdd/progress.md`; V209-12b's replay report line.
- Produces: none (last task).

**Rules:**
- **Precondition:** V209-13 Step 8 passed, meaning production `market_shock_readings` has regular-hours rows for a session after the deploy, no outside-hours rows, and a `market_shock_state` row. With `soak pending`, stop and wait; never close a plan whose shadow log is not writing.
- **Double-bump guard** (index ledger, V209-14 row). Before `/close-out` Step 3:
  - Run `git log --oneline -- VERSION.json` and confirm that V209-13's `release(bot): ... -- v209` commit is present, and that `VERSION.json` still holds that version.
  - If so, tell the close-out that the bump is already released: Steps 3–4 are skipped, Step 5's prediction check still runs, and the close-out commit message records `bump released in V209-13 (<sha>)`.
  - If the release commit is missing, **stop and report: never bump here.**
- The close-out runs on `main` after V209-13's merge (`/close-out` standing permission, CLAUDE.md). It removes the plan worktree only after `git rev-list --count main..<branch>` prints `0`, and it never deletes a branch containing `backup` (`git-safety.md`).

- [ ] **Step 1: Check the precondition**

```bash
tail -40 .superpowers/sdd/progress.md
```

Expected: V209-13's Step 8 lines show today's reading count ≥ 2, `0` outside-hours rows, a state row, and the release SHA. Anything else: stop and report.

- [ ] **Step 2: `/panel staff-engineer,quant-researcher,veteran-trader`**

Invoke the `panel` skill with those three roles. The target is the plan's merged diff (`<merge>^1...<branch>`, the merge commit of V209-13 Step 6) plus the evidence: V209-12b's replay report line, and V209-13's Step 2 and Step 8 results. Each role reviews one at a time through the `expert-reviewer` agent.

Expected: the merged findings list. **An unresolved `BLOCKING` finding stops the close-out:** report it to the controller with the role, the finding and the file. It is fixed by a new task, never inside this one. Non-blocking findings are recorded in the close-out commit body.

- [ ] **Step 3: Double-bump guard**

```bash
git log --oneline -- VERSION.json | head -5
git log --oneline -1 --grep="^release(bot): .* -- v209 market-shock detector" -- VERSION.json
python -c "import json; print(json.load(open('VERSION.json'))['bot'])"
```

Expected:
- The second command prints exactly one commit, `<sha> release(bot): <version> -- v209 market-shock detector (shadow)`.
- The third prints that same `<version>`.
- `git log -1 --format=%s -- VERSION.json` is that same release commit, so no later bump has landed.

If the release commit is missing, or `VERSION.json` holds a different version: **stop and report. Never bump in this task.**

- [ ] **Step 4: `/close-out` with the bump marked as released**

Invoke the `close-out` skill and state up front: *"The bump for v209 was released in V209-13 (`<sha>`, bot `<version>`): skip Steps 3–4; run Step 5's prediction check; move only the Track 1 plan files and the three A1 amendment files listed in this task; leave the spec and `_4-notices-and-admin.md` in place."*

- Step 2 of the close-out is already done (this task's Step 2).
- **Step 5 (prediction check):** the delivered level is **bot minor** and `Edge: none (integrity)`.
  - If the index header still reads `**Bump:** bot minor, ui patch`, amend it to `**Bump:** bot minor`, with the clause `(ui patch moved to the follow-on notice/badge plan with the tape badge)`.
  - Fold that edit into the move commit.
- **Step 6:**

```bash
git mv docs/superpowers/plans/2026-11-05-v209-market-shock-detector_0-index.md \
       docs/superpowers/plans/2026-11-05-v209-market-shock-detector_1-detector-core.md \
       docs/superpowers/plans/2026-11-05-v209-market-shock-detector_1b-detector-exit.md \
       docs/superpowers/plans/2026-11-05-v209-market-shock-detector_2-storage-and-wiring.md \
       docs/superpowers/plans/2026-11-05-v209-market-shock-detector_3-scan-wiring-and-stamp.md \
       docs/superpowers/plans/2026-11-05-v209-market-shock-detector_3b-byte-identical-pins.md \
       docs/superpowers/plans/2026-11-05-v209-market-shock-detector_5-replay-release-closeout.md \
       docs/superpowers/plans/2026-11-05-v209-market-shock-detector-a1_0-index.md \
       docs/superpowers/plans/2026-11-05-v209-market-shock-detector-a1_1-rule-and-tooling.md \
       docs/superpowers/plans/2026-11-05-v209-market-shock-detector-a1_2-data-and-acceptance.md \
       docs/superpowers/plans/implemented/
git status --short     # ten renames (plus the index header edit, if Step 5 amended it); VERSION.json untouched
```

- **Step 7 (worktree):** run `git rev-list --count main..<v209 branch>`; it must print `0`. Then remove the worktree and its branch per `document-lifecycle.md`. If the branch name contains `backup`, stop and ask instead.

- [ ] **Step 5: Verify**

```bash
ls docs/superpowers/plans/implemented/ | grep -c "2026-11-05-v209-market-shock-detector_"   # 6
ls docs/superpowers/specs/2026-11-05-v209-market-shock-detector-design.md                     # still there
ls docs/superpowers/plans/2026-11-05-v209-market-shock-detector_4-notices-and-admin.md        # still there
git diff HEAD --stat -- VERSION.json swingbot/admin/version_history.json                       # empty
```

Expected: `6`, both paths listed, and an empty diff.

- [ ] **Step 6: Commit**

```bash
git commit -m "docs(v209): close out Track 1 -- plan to implemented/, bump released in V209-13 (<sha>)

Panel (staff-engineer, quant-researcher, veteran-trader): <non-blocking findings, one line each>.
Replay: <V209-12b report line>. Shadow soak: <V209-13 Step 8 counts>."
git push origin main
gh run watch "$(gh run list --branch main --limit 1 --json databaseId -q '.[0].databaseId')" --exit-status
```

Expected: the CI run is green (documents only; no test changes).

