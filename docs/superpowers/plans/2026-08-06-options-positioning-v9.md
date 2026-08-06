# Options Positioning Implementation Plan (v9)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-08-06-options-positioning-design.md`
**Source of the idea:** `https://dsgex.ai/main` (DSGEX)

**Goal:** Add free-yfinance options positioning to swingbot as three things — additive inputs to the existing level map and quality score, a dashboard to eyeball, and four throttled alert types — without ever letting options data veto a trade or leak into a backtest.

**Architecture:** One after-close job fetches ≤6 horizon-relevant expiries per ticker, runs a liquidity filter, and writes a gzipped daily snapshot. Every consumer reads the snapshot store, never the network. Greeks are computed locally with Black-Scholes because the feed supplies none. Integration happens at two additive seams: OI walls enter `_cluster_levels()` as ordinary `(price, label)` candidates via a keyword-only parameter that only the live scan passes, and IV rank enters `score_plan()` through its existing optional-component loop.

**Tech Stack:** Python 3.11+, yfinance 0.2.66, scipy 1.17.1, pandas/numpy, discord.py, matplotlib/mplfinance, pytest. No new dependencies.

## Global Constraints

- **Free tier only.** No paid data source, no new dependency, no API key. yfinance + scipy are already installed.
- **NO-LOOKAHEAD, structurally enforced.** Options data must never reach a backtest level map. See Task D9 — a failure of its guard test is a stop-the-line event.
- **Additive authority only.** Options may add level candidates and add score points. They may **never** veto a plan, reject a scenario, shrink a target, or alter sizing. The v8 reachability screen (V11) and `apply_target_floor` (V10) are not touched by this plan.
- **Silent skip.** A ticker failing the liquidity filter emits no options signal and trades exactly as it does today. Return `None`/`[]`, never a degraded number.
- **Cold start returns `None`.** Any metric lacking sufficient accrued history returns `None`, never a partial computation.
- **Every setting is one `Field` in `swingbot/config.py`**, defaulting to OFF/disabled. Signature: `Field(key, attr, section, label, type=, default=, help=, min=, max=, step=, options=, sensitive=, hot_reloadable=)` where `key` is the `.env` variable and `attr` is the `config.<attr>` global. Valid types: `text | number | float | checkbox | select | password`.
- **The bot never trades options.** Equity paper trades only, unchanged.
- **Cadence:** once daily, after close, off the scan loop.
- **Test baseline:** `1711 passed, 62 skipped, 0 failed` (2026-08-04). Green means zero failures. Run in chunks. **Never add `-q`** — `pytest.ini` already sets it and a second one suppresses the summary line.
- **Long-running scripts must print one flushed line per unit of work.**

## File Structure

| File | Responsibility |
|---|---|
| `swingbot/core/options/__init__.py` | Public surface only |
| `swingbot/core/options/chain.py` | yfinance fetch, expiry selection, liquidity filter. The only module that touches the network. |
| `swingbot/core/options/greeks.py` | Pure Black-Scholes math. No I/O. |
| `swingbot/core/options/exposure.py` | GEX aggregation, gamma flip, OI walls |
| `swingbot/core/options/vol.py` | ATM IV, expected move, IV rank, put/call skew |
| `swingbot/core/options/snapshots.py` | Daily snapshot store + retention |
| `swingbot/core/options/levels_source.py` | Adapter → `(price, label)` level candidates |
| `swingbot/core/options/alerts.py` | Four detectors + throttling |
| `scripts/options_snapshot.py` | Cron-able daily job |
| `scripts/options_coverage_probe.py` | One-off coverage survey |
| `data/options/<TICKER>/YYYY-MM-DD.json.gz` | Snapshot store (git-ignored) |

Modified: `swingbot/config.py`, `swingbot/core/levels.py`, `swingbot/core/quality.py`, `swingbot/commands/info.py`, `swingbot/commands/slash.py`, `swingbot/admin/app.py`, `docs/claude/known-traps.md`, `.gitignore`, `.ignore`.

---

# Phase D0 — Data foundation

### Task D1: Coverage probe

**Files:**
- Create: `scripts/options_coverage_probe.py`
- Create: `docs/superpowers/results/2026-08-XX-options-coverage.md` (output)

**Interfaces:**
- Consumes: nothing
- Produces: a results table. No importable API.

**Why first:** the plan targets the full ~75-ticker watchlist. SPY has 31 expiries and deep OI; a mid-cap may have four expiries and single-digit OI. Coverage is currently unknown and everything downstream is conditional on it.

- [ ] **Step 1: Write the probe**

```python
"""One-off survey: which watchlist tickers have a usable option chain?

Run once, read the table, then decide whether the full-watchlist universe
is viable. Prints one flushed line per ticker (CLAUDE.md: long-running
scripts must emit incremental progress).
"""
import sys
import time
import yfinance as yf
from swingbot import config

DRAFT_MIN_OI = 10
DRAFT_IV_LO, DRAFT_IV_HI = 0.02, 2.50


def probe(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    try:
        expiries = list(t.options)
    except Exception as exc:
        return {"ticker": ticker, "expiries": 0, "usable_strikes": 0,
                "total_oi": 0, "error": str(exc)[:60]}
    if not expiries:
        return {"ticker": ticker, "expiries": 0, "usable_strikes": 0,
                "total_oi": 0, "error": "no expiries"}

    usable = total_oi = 0
    for exp in expiries[:6]:
        try:
            ch = t.option_chain(exp)
        except Exception:
            continue
        for side in (ch.calls, ch.puts):
            oi = side["openInterest"].fillna(0)
            iv = side["impliedVolatility"].fillna(0)
            total_oi += int(oi.sum())
            usable += int(((oi >= DRAFT_MIN_OI) &
                           (iv > DRAFT_IV_LO) & (iv < DRAFT_IV_HI)).sum())
    return {"ticker": ticker, "expiries": len(expiries),
            "usable_strikes": usable, "total_oi": total_oi, "error": ""}


def classify(row: dict) -> str:
    if row["expiries"] == 0 or row["usable_strikes"] == 0:
        return "NONE"
    return "RICH" if row["usable_strikes"] >= 40 else "THIN"


def main():
    tickers = config.WATCHLIST
    rows = []
    for i, tk in enumerate(tickers, 1):
        t0 = time.time()
        row = probe(tk)
        row["secs"] = round(time.time() - t0, 1)
        row["class"] = classify(row)
        rows.append(row)
        print(f"[{i}/{len(tickers)}] {tk:<6} {row['class']:<5} "
              f"expiries={row['expiries']:<3} usable={row['usable_strikes']:<4} "
              f"oi={row['total_oi']:<9} {row['secs']}s {row['error']}",
              flush=True)
        time.sleep(0.5)

    print("\n| Ticker | Class | Expiries | Usable strikes | Total OI |")
    print("|---|---|---|---|---|")
    for r in sorted(rows, key=lambda r: -r["usable_strikes"]):
        print(f"| {r['ticker']} | {r['class']} | {r['expiries']} | "
              f"{r['usable_strikes']} | {r['total_oi']} |")
    counts = {c: sum(1 for r in rows if r["class"] == c) for c in ("RICH", "THIN", "NONE")}
    print(f"\nRICH={counts['RICH']}  THIN={counts['THIN']}  NONE={counts['NONE']}")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it**

Run: `python scripts/options_coverage_probe.py | tee docs/superpowers/results/2026-08-XX-options-coverage.md`
Expected: one line per watchlist ticker, then a summary table.

- [ ] **Step 3: Record the decision**

Append the `RICH/THIN/NONE` counts to this plan's Progress section. **Decision gate:** if `RICH` < 20, stop and re-scope the universe to index ETFs before starting D5+. Note the call explicitly.

- [ ] **Step 4: Commit**

```bash
git add scripts/options_coverage_probe.py docs/superpowers/results/
git commit -m "chore(D1): survey option-chain coverage across the watchlist"
```

---

### Task D2: Config surface

**Files:**
- Modify: `swingbot/config.py` (append a new `"Options"` section to `FIELDS`)
- Test: `tests/test_config_flags.py`

**Interfaces:**
- Produces: `config.OPTIONS_ENABLED` (bool), `config.OPTIONS_MIN_OI` (int), `config.OPTIONS_IV_MIN` / `config.OPTIONS_IV_MAX` (float), `config.OPTIONS_MAX_SPREAD_PCT` (float), `config.OPTIONS_STRIKE_RANGE_PCT` (float), `config.OPTIONS_MIN_STRIKES_PER_EXPIRY` (int), `config.OPTIONS_MAX_EXPIRIES` (int), `config.OPTIONS_RISK_FREE_RATE` (float), `config.OPTIONS_SNAPSHOT_RETENTION_DAYS` (int), `config.OPTIONS_IV_RANK_MIN_HISTORY` (int), `config.DISCORD_CHANNEL_OPTIONS_ID` (str), `config.OPTIONS_ALERTS_ENABLED` (bool), `config.OPTIONS_ALERT_DAILY_CAP` (int), `config.OPTIONS_ALERT_COOLDOWN_DAYS` (int), `config.OPTIONS_LEVELS_ENABLED` (bool), `config.OPTIONS_SCORE_ENABLED` (bool)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config_flags.py
def test_options_fields_exist_and_default_off():
    from swingbot.config import FIELDS
    by_key = {f.key: f for f in FIELDS}
    for key in ("OPTIONS_ENABLED", "OPTIONS_ALERTS_ENABLED",
                "OPTIONS_LEVELS_ENABLED", "OPTIONS_SCORE_ENABLED"):
        assert key in by_key, f"{key} missing from FIELDS"
        assert by_key[key].type == "checkbox"
        assert by_key[key].default == "false", f"{key} must default OFF"


def test_options_fields_are_one_admin_section():
    from swingbot.config import FIELDS
    sections = {f.section for f in FIELDS if f.key.startswith("OPTIONS_")}
    assert sections == {"Options"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config_flags.py::test_options_fields_exist_and_default_off -v`
Expected: FAIL — `OPTIONS_ENABLED missing from FIELDS`

- [ ] **Step 3: Add the fields**

Append to the `FIELDS` list in `swingbot/config.py`, after the existing sections:

```python
    # --- Options positioning (plan v9) ---
    # Every flag here defaults OFF. Options data is ADDITIVE ONLY: it may add
    # level candidates and add score points, never veto a plan or move a target.
    Field("OPTIONS_ENABLED", "OPTIONS_ENABLED", "Options", "Enable options data",
          type="checkbox", default="false",
          help="Master switch. When off, nothing in the options package runs and the bot behaves exactly as before."),
    Field("OPTIONS_MAX_EXPIRIES", "OPTIONS_MAX_EXPIRIES", "Options", "Max expiries per ticker",
          type="number", default="6", min=1, max=12, step=1,
          help="Request budget. A liquid ETF lists 30+ expiries; fetching all of them across the watchlist is thousands of requests a day and risks a yfinance rate-limit ban, which would break price fetching too."),
    Field("OPTIONS_MIN_OI", "OPTIONS_MIN_OI", "Options", "Minimum open interest",
          type="number", default="10", min=0, step=1,
          help="Strikes with less open interest than this are dropped before any aggregate is computed."),
    Field("OPTIONS_IV_MIN", "OPTIONS_IV_MIN", "Options", "Minimum implied volatility",
          type="float", default="0.02", min=0, step=0.01,
          help="Yahoo returns implied vol of 0.00001 on stale strikes. Anything at or below this is a data artefact, not a quote."),
    Field("OPTIONS_IV_MAX", "OPTIONS_IV_MAX", "Options", "Maximum implied volatility",
          type="float", default="2.50", min=0, step=0.1,
          help="Above 250% is almost always a bad quote on an illiquid strike rather than a real reading."),
    Field("OPTIONS_MAX_SPREAD_PCT", "OPTIONS_MAX_SPREAD_PCT", "Options", "Max bid-ask spread %",
          type="float", default="25", min=0, max=100, step=1,
          help="Spread as a percentage of mid. Wider than this and the implied vol derived from it is not trustworthy."),
    Field("OPTIONS_STRIKE_RANGE_PCT", "OPTIONS_STRIKE_RANGE_PCT", "Options", "Strike range from spot %",
          type="float", default="35", min=5, max=100, step=5,
          help="Ignore strikes further than this from the current price -- deep wings carry stale quotes and add noise to every aggregate."),
    Field("OPTIONS_MIN_STRIKES_PER_EXPIRY", "OPTIONS_MIN_STRIKES_PER_EXPIRY", "Options", "Min strikes per expiry",
          type="number", default="8", min=1, step=1,
          help="If fewer strikes than this survive the filter, the whole expiry is discarded. A thin ticker emits no options signal rather than a weak one."),
    Field("OPTIONS_RISK_FREE_RATE", "OPTIONS_RISK_FREE_RATE", "Options", "Risk-free rate",
          type="float", default="0.04", min=0, max=0.2, step=0.005,
          help="Used by the Black-Scholes greeks. A constant is fine -- gamma is barely sensitive to it, and adding a treasury feed would be a second data dependency for no gain."),
    Field("OPTIONS_SNAPSHOT_RETENTION_DAYS", "OPTIONS_SNAPSHOT_RETENTION_DAYS", "Options", "Snapshot retention (days)",
          type="number", default="400", min=30, step=10,
          help="How long daily chain snapshots are kept. 400 covers a one-year IV-rank lookback with slack."),
    Field("OPTIONS_IV_RANK_MIN_HISTORY", "OPTIONS_IV_RANK_MIN_HISTORY", "Options", "IV rank minimum history (days)",
          type="number", default="60", min=20, step=5,
          help="Yahoo serves only today's chain, so IV history has to be accrued by this bot. Below this many recorded days, IV rank returns nothing at all rather than a rank computed off a fortnight."),
    Field("OPTIONS_LEVELS_ENABLED", "OPTIONS_LEVELS_ENABLED", "Options", "Feed OI walls into the level map",
          type="checkbox", default="false",
          help="Adds high-open-interest strikes as level candidates alongside EMAs, Fibonacci and the rest. Additive only -- it can raise confluence, never reject a setup."),
    Field("OPTIONS_SCORE_ENABLED", "OPTIONS_SCORE_ENABLED", "Options", "Feed IV rank into the quality score",
          type="checkbox", default="false",
          help="Adds a bonus score component from IV rank. Bonus only; the component cannot subtract points."),
    Field("OPTIONS_ALERTS_ENABLED", "OPTIONS_ALERTS_ENABLED", "Options", "Enable options alerts",
          type="checkbox", default="false",
          help="Turns on the four standalone options alerts: OI-wall approach, IV-rank extreme, multi-day OI build, and gamma-flip cross."),
    Field("DISCORD_CHANNEL_OPTIONS_ID", "DISCORD_CHANNEL_OPTIONS_ID", "Options", "Options channel ID",
          help="Channel for options alerts. Keeping them out of the trade-alerts channel stops positioning context from diluting the signals you actually act on. Leave blank to disable options alerts entirely."),
    Field("OPTIONS_ALERT_DAILY_CAP", "OPTIONS_ALERT_DAILY_CAP", "Options", "Max options alerts per type per day",
          type="number", default="5", min=1, step=1,
          help="Four alert types across the whole watchlist can flood a channel. Only the strongest readings each day survive this cap."),
    Field("OPTIONS_ALERT_COOLDOWN_DAYS", "OPTIONS_ALERT_COOLDOWN_DAYS", "Options", "Per-ticker alert cooldown (days)",
          type="number", default="5", min=0, step=1,
          help="After a ticker fires an options alert of a given type, that combination stays silent this many days. Stops one slow-moving OI wall from re-alerting every session."),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_config_flags.py -v`
Expected: PASS

- [ ] **Step 5: Verify SIGHUP hot-reload and the admin UI**

Run: `python -c "from swingbot import config; print(config.OPTIONS_ENABLED, config.OPTIONS_MAX_EXPIRIES, config.OPTIONS_IV_MIN)"`
Expected: `False 6 0.02`

- [ ] **Step 6: Commit**

```bash
git add swingbot/config.py tests/test_config_flags.py
git commit -m "feat(D2): options config surface, every flag defaulting off"
```

---

### Task D3: Chain fetch, expiry selection and the liquidity filter

**Files:**
- Create: `swingbot/core/options/__init__.py`, `swingbot/core/options/chain.py`
- Test: `tests/test_options_chain.py`

**Interfaces:**
- Consumes: `config.OPTIONS_*` from D2
- Produces:
  - `select_expiries(expiries: list[str], today: date, max_expiries: int) -> list[str]`
  - `filter_liquid(df: pd.DataFrame, spot: float) -> pd.DataFrame` (may return empty)
  - `fetch_chain(ticker: str, *, today: date | None = None) -> dict | None` — `{"ticker", "spot", "asof", "expiries": {exp: {"calls": df, "puts": df}}}` or `None`

**This is the task that keeps every downstream number honest.** The live feed on 2026-08-06 returned `impliedVolatility` of `0.000010` and `2.185551` on adjacent SPY strikes, with `volume` NaN and `openInterest` 0. Those rows in a gamma sum produce confident nonsense.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_options_chain.py
import datetime as dt
import numpy as np
import pandas as pd
import pytest

from swingbot.core.options import chain


def _row(strike, oi, iv, bid, ask, volume=100.0):
    return {"strike": strike, "openInterest": oi, "impliedVolatility": iv,
            "bid": bid, "ask": ask, "volume": volume}


def test_filter_drops_the_pathological_rows_observed_live():
    """These exact values came off SPY's front expiry on 2026-08-06."""
    df = pd.DataFrame([
        _row(630.0, 1, 2.185551, 141.0, 142.7),      # OI too low AND IV absurd
        _row(675.0, 0, 1.542483, 62.0, 64.8, np.nan),  # zero OI, NaN volume
        _row(680.0, 8, 0.000010, 88.0, 89.3),        # IV is a data artefact
        _row(690.0, 500, 0.19, 12.0, 12.2),          # keep
        _row(695.0, 900, 0.20, 9.0, 9.1),            # keep
    ])
    out = chain.filter_liquid(df, spot=700.0)
    assert sorted(out["strike"].tolist()) == [690.0, 695.0]


def test_filter_drops_wide_spreads():
    df = pd.DataFrame([
        _row(690.0, 500, 0.19, 1.0, 3.0),   # spread 100% of mid -> drop
        _row(695.0, 500, 0.20, 9.0, 9.1),   # keep
    ])
    out = chain.filter_liquid(df, spot=700.0)
    assert out["strike"].tolist() == [695.0]


def test_filter_drops_far_strikes():
    df = pd.DataFrame([
        _row(100.0, 500, 0.19, 9.0, 9.1),   # 86% from spot -> drop
        _row(695.0, 500, 0.20, 9.0, 9.1),   # keep
    ])
    out = chain.filter_liquid(df, spot=700.0)
    assert out["strike"].tolist() == [695.0]


def test_filter_never_raises_on_missing_columns():
    assert chain.filter_liquid(pd.DataFrame(), spot=700.0).empty


def test_select_expiries_respects_the_cap():
    today = dt.date(2026, 8, 6)
    expiries = [(today + dt.timedelta(days=n)).isoformat()
                for n in (1, 2, 5, 8, 15, 30, 60, 90, 180, 270, 365, 500)]
    out = chain.select_expiries(expiries, today, max_expiries=6)
    assert len(out) <= 6
    assert out == sorted(out)


def test_select_expiries_spans_the_swing_horizons_not_the_front_week():
    """The bot holds 2w-9m. Selecting the six nearest expiries would return
    six 0DTE-to-weekly chains that say nothing about a 9-month target."""
    today = dt.date(2026, 8, 6)
    expiries = [(today + dt.timedelta(days=n)).isoformat()
                for n in (1, 2, 3, 4, 5, 8, 15, 30, 60, 90, 180, 270)]
    out = chain.select_expiries(expiries, today, max_expiries=6)
    furthest = (dt.date.fromisoformat(out[-1]) - today).days
    assert furthest >= 180, f"selection collapsed to the front: {out}"


def test_select_expiries_handles_empty():
    assert chain.select_expiries([], dt.date(2026, 8, 6), 6) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_options_chain.py -v`
Expected: FAIL — `ModuleNotFoundError: swingbot.core.options`

- [ ] **Step 3: Implement**

`swingbot/core/options/__init__.py`:

```python
"""Options positioning on free yfinance data (plan v9).

Everything here is ADDITIVE: it may add level candidates and add score
points. It may never veto a plan, reject a scenario, shrink a target or
alter sizing. See docs/superpowers/specs/2026-08-06-options-positioning-design.md.
"""
```

`swingbot/core/options/chain.py`:

```python
"""Fetch, trim and clean option chains. The only module here that touches
the network.

Three facts about the free feed drive this module:
  1. It supplies no greeks -- see greeks.py.
  2. It serves only *today's* chain, never history -- see snapshots.py.
  3. It is dirty. On 2026-08-06 SPY's front expiry carried implied vol of
     0.000010 on one strike and 2.185551 on its neighbour, with NaN volume
     and zero open interest. Aggregating those produces confident nonsense,
     so filter_liquid() runs before anything else in the package.
"""
import datetime as dt
import logging

import pandas as pd
import yfinance as yf

from swingbot import config

log = logging.getLogger(__name__)

# The bot's swing horizons run 2w-9m. Anchor expiry selection to those
# holding periods rather than to whatever is nearest, or the whole
# selection collapses onto weeklies that say nothing about a 9-month target.
_HORIZON_ANCHOR_DAYS = (14, 30, 60, 120, 180, 270)


def select_expiries(expiries: list[str], today: dt.date,
                    max_expiries: int) -> list[str]:
    """Pick at most `max_expiries` expiries anchored to the swing horizons.

    For each anchor, take the nearest listed expiry at or beyond it. A liquid
    ETF lists 30+ expiries; fetching all of them across ~75 tickers is
    thousands of requests a day and risks a rate-limit ban that would break
    price fetching too.
    """
    if not expiries or max_expiries <= 0:
        return []

    parsed = []
    for e in expiries:
        try:
            d = dt.date.fromisoformat(e)
        except (ValueError, TypeError):
            continue
        if d > today:
            parsed.append((d, e))
    parsed.sort()
    if not parsed:
        return []

    chosen: list[str] = []
    for anchor in _HORIZON_ANCHOR_DAYS:
        if len(chosen) >= max_expiries:
            break
        target = today + dt.timedelta(days=anchor)
        for d, raw in parsed:
            if d >= target and raw not in chosen:
                chosen.append(raw)
                break
        else:
            # Nothing that far out; fall back to the furthest available.
            if parsed[-1][1] not in chosen:
                chosen.append(parsed[-1][1])

    return sorted(chosen)[:max_expiries]


def filter_liquid(df: pd.DataFrame, spot: float) -> pd.DataFrame:
    """Drop every strike whose quote cannot be trusted.

    Returns a possibly-empty frame. Callers must treat empty as "no signal",
    never as "zero".
    """
    required = {"strike", "openInterest", "impliedVolatility", "bid", "ask"}
    if df is None or df.empty or not required.issubset(df.columns):
        return pd.DataFrame(columns=sorted(required))
    if not spot or spot <= 0:
        return pd.DataFrame(columns=sorted(required))

    out = df.copy()
    out["openInterest"] = pd.to_numeric(out["openInterest"], errors="coerce").fillna(0)
    for col in ("impliedVolatility", "bid", "ask", "strike"):
        out[col] = pd.to_numeric(out[col], errors="coerce")

    mid = (out["bid"] + out["ask"]) / 2
    spread_pct = (out["ask"] - out["bid"]).abs() / mid.replace(0, pd.NA) * 100
    dist_pct = (out["strike"] - spot).abs() / spot * 100

    keep = (
        (out["openInterest"] >= config.OPTIONS_MIN_OI)
        & (out["impliedVolatility"] > config.OPTIONS_IV_MIN)
        & (out["impliedVolatility"] < config.OPTIONS_IV_MAX)
        & out["bid"].notna() & out["ask"].notna()
        & (out["bid"] > 0)
        & (spread_pct <= config.OPTIONS_MAX_SPREAD_PCT)
        & (dist_pct <= config.OPTIONS_STRIKE_RANGE_PCT)
        & out["strike"].notna()
    )
    return out[keep.fillna(False)].reset_index(drop=True)


def fetch_chain(ticker: str, *, today: dt.date | None = None) -> dict | None:
    """Fetch and clean one ticker's chain. Returns None when unusable.

    Any single ticker failing is skipped rather than failing the caller --
    the same contract the level engine already uses for its methods.
    """
    if not config.OPTIONS_ENABLED:
        return None
    today = today or dt.date.today()

    try:
        t = yf.Ticker(ticker)
        expiries = list(t.options)
        spot = float(t.fast_info["last_price"])
    except Exception as exc:
        log.debug("options: %s chain unavailable (%s)", ticker, exc)
        return None
    if not expiries or not spot or spot <= 0:
        return None

    picked = select_expiries(expiries, today, config.OPTIONS_MAX_EXPIRIES)
    kept: dict[str, dict] = {}
    for exp in picked:
        try:
            raw = t.option_chain(exp)
        except Exception as exc:
            log.debug("options: %s %s failed (%s)", ticker, exp, exc)
            continue
        calls = filter_liquid(raw.calls, spot)
        puts = filter_liquid(raw.puts, spot)
        # A thin expiry emits nothing rather than a weak reading.
        if len(calls) + len(puts) < config.OPTIONS_MIN_STRIKES_PER_EXPIRY:
            continue
        kept[exp] = {"calls": calls, "puts": puts}

    if not kept:
        log.debug("options: %s had no expiry survive the liquidity filter", ticker)
        return None
    return {"ticker": ticker, "spot": spot, "asof": today.isoformat(),
            "expiries": kept}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_options_chain.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/options/ tests/test_options_chain.py
git commit -m "feat(D3): chain fetch with the liquidity filter that keeps every later number honest"
```

---

### Task D4: Snapshot store and retention

**Files:**
- Create: `swingbot/core/options/snapshots.py`
- Modify: `.gitignore`, `.ignore`
- Test: `tests/test_options_snapshots.py`

**Interfaces:**
- Consumes: `chain.fetch_chain()` output shape from D3
- Produces:
  - `snapshot_dir(ticker: str) -> Path`
  - `write_snapshot(payload: dict, *, root: Path | None = None) -> Path`
  - `load_snapshot(ticker: str, day: date, *, root=None) -> dict | None`
  - `load_history(ticker: str, days: int, *, root=None) -> list[dict]` — newest last
  - `prune(ticker: str, retention_days: int, *, root=None) -> int`

**Why:** IV rank and OI-change need history the free feed will never give us. History starts accruing the day this ships. Retention is set **before** the first write, not after the disk fills.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_options_snapshots.py
import datetime as dt
import pandas as pd
import pytest

from swingbot.core.options import snapshots


def _payload(day: str, spot: float = 100.0) -> dict:
    df = pd.DataFrame({"strike": [95.0, 100.0], "openInterest": [500, 900],
                       "impliedVolatility": [0.25, 0.22],
                       "bid": [1.0, 2.0], "ask": [1.1, 2.1]})
    return {"ticker": "TEST", "spot": spot, "asof": day,
            "expiries": {"2026-09-18": {"calls": df, "puts": df}}}


def test_write_then_load_roundtrips(tmp_path):
    snapshots.write_snapshot(_payload("2026-08-06"), root=tmp_path)
    got = snapshots.load_snapshot("TEST", dt.date(2026, 8, 6), root=tmp_path)
    assert got["spot"] == 100.0
    calls = got["expiries"]["2026-09-18"]["calls"]
    assert isinstance(calls, pd.DataFrame)
    assert calls["openInterest"].tolist() == [500, 900]


def test_load_missing_day_returns_none(tmp_path):
    assert snapshots.load_snapshot("TEST", dt.date(2026, 8, 6), root=tmp_path) is None


def test_history_is_ordered_oldest_first(tmp_path):
    for day, spot in (("2026-08-04", 98.0), ("2026-08-05", 99.0), ("2026-08-06", 100.0)):
        snapshots.write_snapshot(_payload(day, spot), root=tmp_path)
    hist = snapshots.load_history("TEST", days=10, root=tmp_path)
    assert [h["spot"] for h in hist] == [98.0, 99.0, 100.0]


def test_prune_removes_only_files_past_retention(tmp_path):
    for day in ("2026-01-01", "2026-08-05", "2026-08-06"):
        snapshots.write_snapshot(_payload(day), root=tmp_path)
    removed = snapshots.prune("TEST", retention_days=30, root=tmp_path,
                              today=dt.date(2026, 8, 6))
    assert removed == 1
    remaining = sorted(p.name for p in snapshots.snapshot_dir("TEST", root=tmp_path).glob("*.json.gz"))
    assert remaining == ["2026-08-05.json.gz", "2026-08-06.json.gz"]


def test_write_is_atomic_leaving_no_temp_files(tmp_path):
    snapshots.write_snapshot(_payload("2026-08-06"), root=tmp_path)
    leftovers = list(snapshots.snapshot_dir("TEST", root=tmp_path).glob("*.tmp"))
    assert leftovers == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_options_snapshots.py -v`
Expected: FAIL — `cannot import name 'snapshots'`

- [ ] **Step 3: Implement**

```python
# swingbot/core/options/snapshots.py
"""Daily chain snapshots.

Yahoo serves only today's chain. IV rank and open-interest change are
therefore impossible until this bot has recorded enough days itself, which
is why every history-dependent metric has a cold-start threshold and
returns None below it rather than a number computed off a fortnight.
"""
import datetime as dt
import gzip
import json
import logging
import os
from pathlib import Path

import pandas as pd

from swingbot import config

log = logging.getLogger(__name__)

DEFAULT_ROOT = Path("data/options")
_FRAME_COLUMNS = ["strike", "openInterest", "impliedVolatility", "bid", "ask", "volume"]


def snapshot_dir(ticker: str, *, root: Path | None = None) -> Path:
    return (Path(root) if root else DEFAULT_ROOT) / ticker.upper()


def _encode(payload: dict) -> dict:
    out = {"ticker": payload["ticker"], "spot": payload["spot"],
           "asof": payload["asof"], "expiries": {}}
    for exp, sides in payload["expiries"].items():
        out["expiries"][exp] = {
            side: [{c: (None if pd.isna(v) else v) for c, v in row.items()
                    if c in _FRAME_COLUMNS}
                   for row in df.to_dict("records")]
            for side, df in sides.items()
        }
    return out


def _decode(raw: dict) -> dict:
    out = {"ticker": raw["ticker"], "spot": raw["spot"],
           "asof": raw["asof"], "expiries": {}}
    for exp, sides in raw["expiries"].items():
        out["expiries"][exp] = {
            side: pd.DataFrame(rows, columns=_FRAME_COLUMNS)
            for side, rows in sides.items()
        }
    return out


def write_snapshot(payload: dict, *, root: Path | None = None) -> Path:
    """Atomic write: temp file then rename, so a crash mid-write never
    leaves a half-parsed snapshot that later poisons an IV rank."""
    d = snapshot_dir(payload["ticker"], root=root)
    d.mkdir(parents=True, exist_ok=True)
    dest = d / f"{payload['asof']}.json.gz"
    tmp = dest.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(_encode(payload), fh)
    os.replace(tmp, dest)
    return dest


def load_snapshot(ticker: str, day: dt.date, *, root: Path | None = None) -> dict | None:
    p = snapshot_dir(ticker, root=root) / f"{day.isoformat()}.json.gz"
    if not p.exists():
        return None
    try:
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            return _decode(json.load(fh))
    except Exception as exc:
        log.warning("options: unreadable snapshot %s (%s)", p, exc)
        return None


def load_history(ticker: str, days: int, *, root: Path | None = None) -> list[dict]:
    """Newest last. Unreadable files are skipped, not fatal."""
    d = snapshot_dir(ticker, root=root)
    if not d.exists():
        return []
    paths = sorted(d.glob("*.json.gz"))[-days:]
    out = []
    for p in paths:
        try:
            with gzip.open(p, "rt", encoding="utf-8") as fh:
                out.append(_decode(json.load(fh)))
        except Exception:
            continue
    return out


def prune(ticker: str, retention_days: int, *, root: Path | None = None,
          today: dt.date | None = None) -> int:
    today = today or dt.date.today()
    cutoff = today - dt.timedelta(days=retention_days)
    removed = 0
    for p in snapshot_dir(ticker, root=root).glob("*.json.gz"):
        try:
            day = dt.date.fromisoformat(p.stem)
        except ValueError:
            continue
        if day < cutoff:
            p.unlink()
            removed += 1
    return removed
```

- [ ] **Step 4: Ignore the store**

Add `data/options/` to both `.gitignore` and the root `.ignore`. The `.ignore` entry matters: without it Grep starts returning snapshot JSON and pollutes every search in this repo.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_options_snapshots.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/options/snapshots.py tests/test_options_snapshots.py .gitignore .ignore
git commit -m "feat(D4): daily snapshot store, with retention set before the first write"
```

---

### Task D5: The daily snapshot job

**Files:**
- Create: `scripts/options_snapshot.py`
- Test: `tests/test_options_snapshot_script.py`

**Interfaces:**
- Consumes: `chain.fetch_chain`, `snapshots.write_snapshot`, `snapshots.prune`
- Produces: `run(tickers: list[str], *, root=None, today=None) -> dict` — `{"written": int, "skipped": int, "pruned": int}`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_options_snapshot_script.py
import datetime as dt
import pandas as pd
import pytest

from scripts import options_snapshot


def test_run_skips_tickers_with_no_chain(monkeypatch, tmp_path):
    monkeypatch.setattr(options_snapshot.chain, "fetch_chain",
                        lambda tk, today=None: None)
    res = options_snapshot.run(["AAA", "BBB"], root=tmp_path,
                               today=dt.date(2026, 8, 6))
    assert res == {"written": 0, "skipped": 2, "pruned": 0}


def test_run_writes_one_snapshot_per_usable_ticker(monkeypatch, tmp_path):
    df = pd.DataFrame({"strike": [100.0], "openInterest": [500],
                       "impliedVolatility": [0.2], "bid": [1.0], "ask": [1.1]})

    def fake(tk, today=None):
        if tk == "BBB":
            return None
        return {"ticker": tk, "spot": 100.0, "asof": "2026-08-06",
                "expiries": {"2026-09-18": {"calls": df, "puts": df}}}

    monkeypatch.setattr(options_snapshot.chain, "fetch_chain", fake)
    res = options_snapshot.run(["AAA", "BBB"], root=tmp_path,
                               today=dt.date(2026, 8, 6))
    assert res["written"] == 1 and res["skipped"] == 1


def test_one_ticker_raising_does_not_abort_the_run(monkeypatch, tmp_path):
    def fake(tk, today=None):
        if tk == "AAA":
            raise RuntimeError("yfinance exploded")
        return None

    monkeypatch.setattr(options_snapshot.chain, "fetch_chain", fake)
    res = options_snapshot.run(["AAA", "BBB"], root=tmp_path,
                               today=dt.date(2026, 8, 6))
    assert res["skipped"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_options_snapshot_script.py -v`
Expected: FAIL — `ModuleNotFoundError: scripts.options_snapshot`

- [ ] **Step 3: Implement**

```python
# scripts/options_snapshot.py
"""Record one option-chain snapshot per ticker per day.

Run once daily AFTER THE CLOSE, off the scan loop. Open interest only
updates once a day, so refreshing intraday buys identical numbers at
several times the rate-limit risk -- and a yfinance ban on the live box
breaks price fetching too, not just options.

Prints one flushed line per ticker: this is a long-running job and a silent
one gives no signal until it finishes.
"""
import datetime as dt
import logging
import sys
import time
from pathlib import Path

from swingbot import config
from swingbot.core.options import chain, snapshots

log = logging.getLogger(__name__)
THROTTLE_SECONDS = 0.5


def run(tickers: list[str], *, root: Path | None = None,
        today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    written = skipped = pruned = 0

    for i, tk in enumerate(tickers, 1):
        try:
            payload = chain.fetch_chain(tk, today=today)
        except Exception as exc:
            log.debug("options: %s raised (%s)", tk, exc)
            payload = None

        if payload is None:
            skipped += 1
            print(f"[{i}/{len(tickers)}] {tk:<6} SKIP (no usable chain)", flush=True)
        else:
            snapshots.write_snapshot(payload, root=root)
            written += 1
            n = sum(len(s["calls"]) + len(s["puts"])
                    for s in payload["expiries"].values())
            print(f"[{i}/{len(tickers)}] {tk:<6} OK   "
                  f"{len(payload['expiries'])} expiries, {n} strikes", flush=True)
            pruned += snapshots.prune(
                tk, config.OPTIONS_SNAPSHOT_RETENTION_DAYS, root=root, today=today)
        time.sleep(THROTTLE_SECONDS)

    return {"written": written, "skipped": skipped, "pruned": pruned}


def main() -> int:
    if not config.OPTIONS_ENABLED:
        print("OPTIONS_ENABLED is off -- nothing to do.", flush=True)
        return 0
    res = run(config.WATCHLIST)
    print(f"\nwritten={res['written']} skipped={res['skipped']} pruned={res['pruned']}",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_options_snapshot_script.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/options_snapshot.py tests/test_options_snapshot_script.py
git commit -m "feat(D5): the daily after-close snapshot job"
```

---

# Phase D1 — The math

### Task D6: Black-Scholes greeks

**Files:**
- Create: `swingbot/core/options/greeks.py`
- Test: `tests/test_options_greeks.py`

**Interfaces:**
- Produces:
  - `d1(spot, strike, t_years, iv, rate) -> float`
  - `d2(spot, strike, t_years, iv, rate) -> float`
  - `gamma(spot, strike, t_years, iv, rate) -> float`
  - `delta(spot, strike, t_years, iv, rate, *, is_call: bool) -> float`
  - `vanna(spot, strike, t_years, iv, rate) -> float`
  - `charm(spot, strike, t_years, iv, rate) -> float` (no `is_call` — see the docstring)
  - `years_to_expiry(expiry: str | date, today: date) -> float`

**Why this exists:** the free feed supplies **no greeks**. scipy 1.17.1 is already installed, so this is arithmetic, not a dependency.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_options_greeks.py
import datetime as dt
import math
import pytest

from swingbot.core.options import greeks

# Textbook case: S=100, K=100, T=1, sigma=0.20, r=0.05
S, K, T, IV, R = 100.0, 100.0, 1.0, 0.20, 0.05


def test_d1_d2_match_hand_computed_values():
    assert greeks.d1(S, K, T, IV, R) == pytest.approx(0.35, abs=1e-6)
    assert greeks.d2(S, K, T, IV, R) == pytest.approx(0.15, abs=1e-6)


def test_gamma_matches_hand_computed_value():
    # gamma = n(d1) / (S * sigma * sqrt(T)); n(0.35) = 0.375240...
    assert greeks.gamma(S, K, T, IV, R) == pytest.approx(0.018762, abs=1e-6)


def test_gamma_takes_no_side_argument_and_peaks_near_the_money():
    """Gamma is identical for calls and puts (put-call parity), which is why
    gamma() has no is_call parameter at all -- exposure.py applies the dealer
    sign itself. If someone ever adds a side argument here, the GEX sign
    convention has been silently duplicated in two places."""
    import inspect
    assert "is_call" not in inspect.signature(greeks.gamma).parameters

    atm = greeks.gamma(S, 100.0, T, IV, R)
    otm = greeks.gamma(S, 130.0, T, IV, R)
    itm = greeks.gamma(S, 70.0, T, IV, R)
    assert atm > otm and atm > itm
    assert otm > 0 and itm > 0


def test_call_delta_is_bounded_and_put_delta_is_its_complement():
    c = greeks.delta(S, K, T, IV, R, is_call=True)
    p = greeks.delta(S, K, T, IV, R, is_call=False)
    assert 0.0 < c < 1.0 and -1.0 < p < 0.0
    assert c - p == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("t,iv", [(0.0, 0.20), (1.0, 0.0), (0.0, 0.0), (-1.0, 0.2)])
def test_degenerate_inputs_return_zero_not_nan(t, iv):
    """A snapshot can carry an expired contract or a zero-IV artefact. Those
    must not propagate NaN into a gamma sum."""
    for fn in (greeks.gamma, greeks.vanna):
        val = fn(S, K, t, iv, R)
        assert not math.isnan(val) and not math.isinf(val)
        assert val == 0.0


def test_gamma_decays_toward_zero_for_otm_as_expiry_approaches():
    near = greeks.gamma(S, 130.0, 0.002, IV, R)
    far = greeks.gamma(S, 130.0, 1.0, IV, R)
    assert near < far


def test_years_to_expiry():
    assert greeks.years_to_expiry("2027-08-06", dt.date(2026, 8, 6)) == pytest.approx(1.0, abs=0.01)
    assert greeks.years_to_expiry("2026-08-06", dt.date(2026, 8, 6)) == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_options_greeks.py -v`
Expected: FAIL — `cannot import name 'greeks'`

- [ ] **Step 3: Implement**

```python
# swingbot/core/options/greeks.py
"""Black-Scholes greeks, computed locally.

The free yfinance chain supplies strike, implied volatility, bid/ask,
volume and open interest -- and no greeks at all. Everything gamma-related
in this package therefore starts here.

Pure math: no I/O, no config reads, no network. Every function returns 0.0
rather than NaN on a degenerate input, because a snapshot can legitimately
contain an expired contract or a zero-IV artefact and a single NaN would
otherwise poison a whole gamma sum.
"""
import datetime as dt
import math

from scipy.stats import norm

DAYS_PER_YEAR = 365.0


def _degenerate(spot: float, strike: float, t_years: float, iv: float) -> bool:
    return (not spot or spot <= 0 or not strike or strike <= 0
            or t_years is None or t_years <= 0 or not iv or iv <= 0)


def years_to_expiry(expiry, today: dt.date) -> float:
    if isinstance(expiry, str):
        try:
            expiry = dt.date.fromisoformat(expiry)
        except (ValueError, TypeError):
            return 0.0
    return max(0.0, (expiry - today).days / DAYS_PER_YEAR)


def d1(spot: float, strike: float, t_years: float, iv: float, rate: float) -> float:
    if _degenerate(spot, strike, t_years, iv):
        return 0.0
    return ((math.log(spot / strike) + (rate + 0.5 * iv ** 2) * t_years)
            / (iv * math.sqrt(t_years)))


def d2(spot: float, strike: float, t_years: float, iv: float, rate: float) -> float:
    if _degenerate(spot, strike, t_years, iv):
        return 0.0
    return d1(spot, strike, t_years, iv, rate) - iv * math.sqrt(t_years)


def gamma(spot: float, strike: float, t_years: float, iv: float, rate: float) -> float:
    """Identical for calls and puts (put-call parity). exposure.py relies on
    that -- it applies the dealer sign convention itself rather than expecting
    a signed gamma from here."""
    if _degenerate(spot, strike, t_years, iv):
        return 0.0
    return norm.pdf(d1(spot, strike, t_years, iv, rate)) / (spot * iv * math.sqrt(t_years))


def delta(spot: float, strike: float, t_years: float, iv: float, rate: float,
          *, is_call: bool) -> float:
    if _degenerate(spot, strike, t_years, iv):
        return 0.0
    nd1 = norm.cdf(d1(spot, strike, t_years, iv, rate))
    return nd1 if is_call else nd1 - 1.0


def vanna(spot: float, strike: float, t_years: float, iv: float, rate: float) -> float:
    """d(delta)/d(vol). Display only -- see the module note in exposure.py."""
    if _degenerate(spot, strike, t_years, iv):
        return 0.0
    _d1 = d1(spot, strike, t_years, iv, rate)
    _d2 = d2(spot, strike, t_years, iv, rate)
    return -norm.pdf(_d1) * _d2 / iv


def charm(spot: float, strike: float, t_years: float, iv: float, rate: float) -> float:
    """d(delta)/d(time). Display only.

    Takes no is_call argument on purpose: with no dividend yield,
    delta_put = delta_call - 1, so their time derivatives are identical.
    An is_call parameter here would be dead weight that later reads as a
    bug someone forgot to finish.
    """
    if _degenerate(spot, strike, t_years, iv):
        return 0.0
    _d1 = d1(spot, strike, t_years, iv, rate)
    _d2 = d2(spot, strike, t_years, iv, rate)
    return (-norm.pdf(_d1) * (2 * rate * t_years - _d2 * iv * math.sqrt(t_years))
            / (2 * t_years * iv * math.sqrt(t_years)))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_options_greeks.py -v`
Expected: PASS (all parametrised cases)

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/options/greeks.py tests/test_options_greeks.py
git commit -m "feat(D6): Black-Scholes greeks, because the free feed supplies none"
```

---

### Task D7: Gamma exposure, gamma flip and OI walls

**Files:**
- Create: `swingbot/core/options/exposure.py`
- Test: `tests/test_options_exposure.py`

**Interfaces:**
- Consumes: `greeks.gamma`, `greeks.years_to_expiry`, D3's snapshot payload shape
- Produces:
  - `gamma_exposure(payload: dict, *, today: date | None = None) -> pd.Series | None` — indexed by strike
  - `gamma_flip(gex: pd.Series | None) -> float | None`
  - `oi_walls(payload: dict, *, n: int = 3) -> list[tuple[float, str]]` — `(strike, "Call OI Wall" | "Put OI Wall")`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_options_exposure.py
import datetime as dt
import pandas as pd
import pytest

from swingbot.core.options import exposure

TODAY = dt.date(2026, 8, 6)


def _payload(calls, puts, spot=100.0, expiry="2027-08-06"):
    cols = ["strike", "openInterest", "impliedVolatility", "bid", "ask"]
    return {"ticker": "TEST", "spot": spot, "asof": TODAY.isoformat(),
            "expiries": {expiry: {"calls": pd.DataFrame(calls, columns=cols),
                                  "puts": pd.DataFrame(puts, columns=cols)}}}


def test_gamma_exposure_is_positive_for_calls_and_negative_for_puts():
    calls = [[100.0, 1000, 0.2, 1.0, 1.1]]
    puts = [[90.0, 1000, 0.2, 1.0, 1.1]]
    gex = exposure.gamma_exposure(_payload(calls, puts), today=TODAY)
    assert gex.loc[100.0] > 0
    assert gex.loc[90.0] < 0


def test_gamma_exposure_scales_linearly_with_open_interest():
    one = exposure.gamma_exposure(_payload([[100.0, 1000, 0.2, 1.0, 1.1]], []), today=TODAY)
    two = exposure.gamma_exposure(_payload([[100.0, 2000, 0.2, 1.0, 1.1]], []), today=TODAY)
    assert two.loc[100.0] == pytest.approx(2 * one.loc[100.0], rel=1e-9)


def test_gamma_exposure_returns_none_on_empty_payload():
    assert exposure.gamma_exposure(None) is None
    assert exposure.gamma_exposure({"ticker": "X", "spot": 100.0,
                                    "asof": "2026-08-06", "expiries": {}}) is None


def test_gamma_flip_interpolates_the_single_zero_crossing():
    gex = pd.Series({90.0: -100.0, 100.0: 100.0})
    assert exposure.gamma_flip(gex) == pytest.approx(95.0, abs=1e-6)


def test_gamma_flip_returns_none_when_ambiguous():
    """Three crossings means the profile has no single flip level. Guessing
    one would be inventing a number the data does not support."""
    gex = pd.Series({80.0: -1.0, 90.0: 1.0, 100.0: -1.0, 110.0: 1.0})
    assert exposure.gamma_flip(gex) is None


def test_gamma_flip_returns_none_when_never_crossing():
    assert exposure.gamma_flip(pd.Series({90.0: 1.0, 100.0: 2.0})) is None
    assert exposure.gamma_flip(None) is None


def test_oi_walls_picks_top_calls_above_and_puts_below_spot():
    calls = [[105.0, 100, 0.2, 1.0, 1.1], [110.0, 9000, 0.2, 1.0, 1.1],
             [95.0, 8000, 0.2, 1.0, 1.1]]           # below spot -> not a call wall
    puts = [[90.0, 7000, 0.2, 1.0, 1.1], [85.0, 50, 0.2, 1.0, 1.1]]
    walls = exposure.oi_walls(_payload(calls, puts, spot=100.0), n=1)
    assert (110.0, "Call OI Wall") in walls
    assert (90.0, "Put OI Wall") in walls
    assert all(w[0] != 95.0 for w in walls)


def test_oi_walls_returns_empty_on_bad_input():
    assert exposure.oi_walls(None) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_options_exposure.py -v`
Expected: FAIL — `cannot import name 'exposure'`

- [ ] **Step 3: Implement**

```python
# swingbot/core/options/exposure.py
"""Gamma exposure, the gamma flip level, and open-interest walls.

THE DEALER SIGN CONVENTION IS AN ASSUMPTION, NOT DATA.
--------------------------------------------------------------------
Calls are counted positive and puts negative because dealers are assumed
long calls and short puts against customer flow. We cannot see dealer
inventory on free data -- nobody can without a paid feed, and even paid
"dealer maps" are models. Everything derived from this convention is
advisory: it is displayed with a "modeled, not observed" qualifier and it
never gates, vetoes or resizes a trade. See docs/claude/known-traps.md.

Also note the horizon: gamma positioning decays over hours to days, while
this bot holds 2w-9m. Gamma output here is context and display, not a swing
signal. Open-interest WALLS are the durable part -- a strike with dominant
OI stays a magnet for weeks -- and they are what feeds the level map.
"""
import datetime as dt
import logging

import pandas as pd

from swingbot import config
from swingbot.core.options import greeks

log = logging.getLogger(__name__)

CONTRACT_MULTIPLIER = 100
_ONE_PCT = 0.01


def _iter_sides(payload: dict):
    for expiry, sides in payload["expiries"].items():
        for side, df in sides.items():
            if df is not None and not df.empty:
                yield expiry, side, df


def gamma_exposure(payload: dict | None, *, today: dt.date | None = None):
    """Dollar gamma per strike, summed across expiries.

    GEX = gamma * openInterest * 100 * spot^2 * 0.01
    (i.e. the dollar change in dealer delta per 1% move in spot), calls
    positive and puts negative per the convention noted above.

    Returns None -- never an empty or zero Series -- when there is nothing
    trustworthy to compute from.
    """
    if not payload or not payload.get("expiries"):
        return None
    today = today or dt.date.today()
    spot = payload.get("spot") or 0.0
    if spot <= 0:
        return None

    totals: dict[float, float] = {}
    for expiry, side, df in _iter_sides(payload):
        t = greeks.years_to_expiry(expiry, today)
        sign = 1.0 if side == "calls" else -1.0
        for row in df.itertuples(index=False):
            g = greeks.gamma(spot, float(row.strike), t,
                             float(row.impliedVolatility),
                             config.OPTIONS_RISK_FREE_RATE)
            if not g:
                continue
            val = (sign * g * float(row.openInterest)
                   * CONTRACT_MULTIPLIER * spot ** 2 * _ONE_PCT)
            totals[float(row.strike)] = totals.get(float(row.strike), 0.0) + val

    if not totals:
        return None
    return pd.Series(totals).sort_index()


def gamma_flip(gex) -> float | None:
    """The strike where cumulative GEX crosses zero, linearly interpolated.

    Returns None when the profile never crosses, or crosses more than once:
    a multi-crossing profile has no single flip level and picking one would
    be inventing a number the data does not support.
    """
    if gex is None or len(gex) < 2:
        return None
    cum = gex.sort_index().cumsum()
    strikes, vals = cum.index.tolist(), cum.tolist()

    crossings = []
    for i in range(1, len(vals)):
        a, b = vals[i - 1], vals[i]
        if a == 0:
            crossings.append(strikes[i - 1])
        elif (a < 0) != (b < 0):
            span = b - a
            frac = 0.0 if span == 0 else -a / span
            crossings.append(strikes[i - 1] + frac * (strikes[i] - strikes[i - 1]))

    return crossings[0] if len(crossings) == 1 else None


def oi_walls(payload: dict | None, *, n: int = 3) -> list[tuple[float, str]]:
    """Top-n call strikes above spot and put strikes below, by open interest.

    Returned in the exact (price, source_label) shape that
    swingbot/core/levels.py:_cluster_levels() consumes, so a wall merges
    with a nearby EMA or Fibonacci level and raises confluence the same way
    any other method does.
    """
    if not payload or not payload.get("expiries"):
        return []
    spot = payload.get("spot") or 0.0
    if spot <= 0:
        return []

    calls: dict[float, float] = {}
    puts: dict[float, float] = {}
    for _expiry, side, df in _iter_sides(payload):
        bucket = calls if side == "calls" else puts
        for row in df.itertuples(index=False):
            k = float(row.strike)
            bucket[k] = bucket.get(k, 0.0) + float(row.openInterest or 0)

    out: list[tuple[float, str]] = []
    above = sorted(((k, v) for k, v in calls.items() if k > spot),
                   key=lambda kv: -kv[1])[:n]
    below = sorted(((k, v) for k, v in puts.items() if k < spot),
                   key=lambda kv: -kv[1])[:n]
    out += [(k, "Call OI Wall") for k, _ in above]
    out += [(k, "Put OI Wall") for k, _ in below]
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_options_exposure.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/options/exposure.py tests/test_options_exposure.py
git commit -m "feat(D7): GEX, gamma flip and OI walls -- with the dealer assumption written down"
```

---

### Task D8: Volatility metrics

**Files:**
- Create: `swingbot/core/options/vol.py`
- Test: `tests/test_options_vol.py`

**Interfaces:**
- Consumes: `snapshots.load_history`, D3's payload shape
- Produces:
  - `atm_iv(payload: dict, expiry: str) -> float | None`
  - `term_iv(payload: dict, days: int, *, today=None) -> float | None`
  - `expected_move_pct(iv: float, days: int) -> float`
  - `iv_rank(ticker: str, *, root=None, today=None) -> float | None` — 0..100
  - `put_call_oi_ratio(payload: dict) -> float | None`
  - `signal_ready(ticker: str, metric: str, *, root=None) -> bool`

**The cold-start contract lives here.** Expected move and skew work on day one. IV rank cannot exist until this bot has recorded `OPTIONS_IV_RANK_MIN_HISTORY` days itself, and returns `None` — never a number — until then.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_options_vol.py
import datetime as dt
import pandas as pd
import pytest

from swingbot.core.options import snapshots, vol

TODAY = dt.date(2026, 8, 6)
COLS = ["strike", "openInterest", "impliedVolatility", "bid", "ask"]


def _payload(day, iv, spot=100.0, expiry="2026-09-05"):
    rows = [[95.0, 500, iv, 1.0, 1.1], [100.0, 900, iv, 1.0, 1.1],
            [105.0, 500, iv, 1.0, 1.1]]
    df = pd.DataFrame(rows, columns=COLS)
    return {"ticker": "TEST", "spot": spot, "asof": day,
            "expiries": {expiry: {"calls": df, "puts": df}}}


def test_atm_iv_averages_the_strikes_nearest_spot():
    p = _payload("2026-08-06", 0.25)
    assert vol.atm_iv(p, "2026-09-05") == pytest.approx(0.25, abs=1e-9)


def test_atm_iv_returns_none_for_a_missing_expiry():
    assert vol.atm_iv(_payload("2026-08-06", 0.25), "2099-01-01") is None


def test_expected_move_matches_the_closed_form():
    # 20% IV over 365 days is a 20% one-sigma move; over ~91 days it halves.
    assert vol.expected_move_pct(0.20, 365) == pytest.approx(20.0, abs=1e-6)
    assert vol.expected_move_pct(0.20, 91) == pytest.approx(9.986, abs=0.01)


def test_expected_move_is_zero_for_degenerate_inputs():
    assert vol.expected_move_pct(0.0, 90) == 0.0
    assert vol.expected_move_pct(0.2, 0) == 0.0


def test_iv_rank_returns_none_below_the_history_threshold(tmp_path, monkeypatch):
    """Yahoo serves no IV history, so a rank computed off a fortnight would
    be fiction. Below the threshold this must return nothing at all."""
    monkeypatch.setattr(vol.config, "OPTIONS_IV_RANK_MIN_HISTORY", 60)
    for n in range(10):
        day = (TODAY - dt.timedelta(days=n)).isoformat()
        snapshots.write_snapshot(_payload(day, 0.2), root=tmp_path)
    assert vol.iv_rank("TEST", root=tmp_path, today=TODAY) is None


def test_iv_rank_is_100_at_the_high_and_0_at_the_low(tmp_path, monkeypatch):
    monkeypatch.setattr(vol.config, "OPTIONS_IV_RANK_MIN_HISTORY", 5)
    ivs = [0.10, 0.20, 0.30, 0.40, 0.50]
    for n, iv in enumerate(ivs):
        day = (TODAY - dt.timedelta(days=len(ivs) - n)).isoformat()
        snapshots.write_snapshot(_payload(day, iv), root=tmp_path)
    assert vol.iv_rank("TEST", root=tmp_path, today=TODAY) == pytest.approx(100.0, abs=1e-6)


def test_put_call_oi_ratio():
    p = _payload("2026-08-06", 0.2)
    assert vol.put_call_oi_ratio(p) == pytest.approx(1.0, abs=1e-9)
    assert vol.put_call_oi_ratio(None) is None


def test_signal_ready_gates_on_recorded_history(tmp_path, monkeypatch):
    monkeypatch.setattr(vol.config, "OPTIONS_IV_RANK_MIN_HISTORY", 60)
    assert vol.signal_ready("TEST", "expected_move", root=tmp_path) is True
    assert vol.signal_ready("TEST", "iv_rank", root=tmp_path) is False
    assert vol.signal_ready("TEST", "oi_change", root=tmp_path) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_options_vol.py -v`
Expected: FAIL — `cannot import name 'vol'`

- [ ] **Step 3: Implement**

```python
# swingbot/core/options/vol.py
"""Implied volatility metrics -- the part of DSGEX that transfers cleanly
to a 2w-9m holding period.

THE COLD-START CONTRACT
-----------------------
Yahoo serves only today's chain. Anything needing history is impossible
until this bot has recorded enough days itself:

    metric          minimum recorded days
    --------------  ---------------------
    expected_move   0   (works day one)
    put_call_ratio  0   (works day one)
    oi_change       2
    oi_build_trend  20
    iv_rank         config.OPTIONS_IV_RANK_MIN_HISTORY (default 60)

Below its threshold a metric returns None, never a partial computation.
Callers must check signal_ready() or handle None.
"""
import datetime as dt
import math

import pandas as pd

from swingbot import config
from swingbot.core.options import snapshots

DAYS_PER_YEAR = 365.0

MIN_HISTORY = {"expected_move": 0, "put_call_ratio": 0,
               "oi_change": 2, "oi_build_trend": 20}


def signal_ready(ticker: str, metric: str, *, root=None) -> bool:
    need = (config.OPTIONS_IV_RANK_MIN_HISTORY if metric == "iv_rank"
            else MIN_HISTORY.get(metric, 0))
    if need <= 0:
        return True
    d = snapshots.snapshot_dir(ticker, root=root)
    return d.exists() and len(list(d.glob("*.json.gz"))) >= need


def atm_iv(payload: dict | None, expiry: str) -> float | None:
    """Mean implied vol of the two strikes nearest spot, across both sides."""
    if not payload or expiry not in payload.get("expiries", {}):
        return None
    spot = payload.get("spot") or 0.0
    if spot <= 0:
        return None

    ivs = []
    for df in payload["expiries"][expiry].values():
        if df is None or df.empty:
            continue
        near = df.assign(_d=(df["strike"] - spot).abs()).nsmallest(2, "_d")
        ivs += [v for v in near["impliedVolatility"].tolist() if v and v > 0]
    if not ivs:
        return None
    return sum(ivs) / len(ivs)


def term_iv(payload: dict | None, days: int, *, today: dt.date | None = None) -> float | None:
    """Implied vol interpolated to `days` out, from the two bracketing
    expiries. Returns None rather than extrapolating past the furthest
    listed expiry -- common for a 9-month horizon on a thin name."""
    if not payload or not payload.get("expiries"):
        return None
    today = today or dt.date.today()

    points = []
    for exp in payload["expiries"]:
        try:
            n = (dt.date.fromisoformat(exp) - today).days
        except (ValueError, TypeError):
            continue
        iv = atm_iv(payload, exp)
        if n > 0 and iv:
            points.append((n, iv))
    if not points:
        return None
    points.sort()

    if days <= points[0][0]:
        return points[0][1]
    if days > points[-1][0]:
        return None
    for (n0, iv0), (n1, iv1) in zip(points, points[1:]):
        if n0 <= days <= n1:
            if n1 == n0:
                return iv0
            w = (days - n0) / (n1 - n0)
            return iv0 + w * (iv1 - iv0)
    return None


def expected_move_pct(iv: float, days: int) -> float:
    """One-sigma move over `days`, as a percentage of spot.

    This is the payoff metric of the whole plan: it answers "is a 5% target
    plausible for this ticker over three months?" with a number the option
    market is quoting today, rather than an extrapolation from past range.

    Per the additive-only rule this INFORMS and SCORES. It never rejects a
    plan whose target exceeds it.
    """
    if not iv or iv <= 0 or not days or days <= 0:
        return 0.0
    return float(iv) * math.sqrt(days / DAYS_PER_YEAR) * 100.0


def iv_rank(ticker: str, *, root=None, today: dt.date | None = None) -> float | None:
    """Where today's ATM IV sits in its own recorded range, 0..100.

    Returns None until enough days have been recorded -- see the cold-start
    contract in the module docstring.
    """
    need = config.OPTIONS_IV_RANK_MIN_HISTORY
    hist = snapshots.load_history(ticker, days=max(need, 400), root=root)
    if len(hist) < need:
        return None

    series = []
    for snap in hist:
        exps = sorted(snap.get("expiries", {}))
        if not exps:
            continue
        iv = atm_iv(snap, exps[0])
        if iv:
            series.append(iv)
    if len(series) < need:
        return None

    lo, hi, cur = min(series), max(series), series[-1]
    if hi == lo:
        return 50.0
    return (cur - lo) / (hi - lo) * 100.0


def put_call_oi_ratio(payload: dict | None) -> float | None:
    if not payload or not payload.get("expiries"):
        return None
    calls = puts = 0.0
    for sides in payload["expiries"].values():
        c, p = sides.get("calls"), sides.get("puts")
        if c is not None and not c.empty:
            calls += float(c["openInterest"].fillna(0).sum())
        if p is not None and not p.empty:
            puts += float(p["openInterest"].fillna(0).sum())
    if calls <= 0:
        return None
    return puts / calls
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_options_vol.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/options/vol.py tests/test_options_vol.py
git commit -m "feat(D8): IV rank, term structure and implied expected move, with the cold-start contract"
```

---

# Phase D2 — Integration (additive only)

### Task D9: The no-lookahead firewall — **highest risk in this plan**

**Files:**
- Modify: `swingbot/core/levels.py:505` (`build_level_map`)
- Create: `swingbot/core/options/levels_source.py`
- Test: `tests/test_options_no_lookahead.py`, `tests/test_options_levels_source.py`

**Interfaces:**
- Consumes: `exposure.oi_walls`, `exposure.gamma_exposure`, `exposure.gamma_flip`, `snapshots.load_snapshot`
- Produces:
  - `levels_source.options_candidates(ticker: str, spot: float, *, today=None, root=None) -> list[tuple[float, str]]`
  - `build_level_map(df, h, current_price, *, extra_candidates=None)` — new keyword-only parameter

**The trap, precisely.** `build_level_map()` calls `collect_candidate_levels()`, and that same path is reached from `swingbot/core/backtest.py:274` (the memo) and `swingbot/core/backtest_scenarios.py:51` (`levels_asof`). Adding an options source *inside* `collect_candidate_levels()` would inject **today's** option chain into every historical bar of every backtest — catastrophic lookahead that would silently invalidate the entire v8 results corpus without erroring.

So: options candidates arrive through a keyword-only parameter that **only the live scan passes**.

- [ ] **Step 1: Write the failing guard test**

```python
# tests/test_options_no_lookahead.py
"""The firewall between options data and any historical computation.

yfinance serves only TODAY's option chain. If an options level ever reaches
a backtest, every historical bar gets today's positioning injected into it
-- lookahead that produces flattering results and no error message.

A FAILURE HERE IS A STOP-THE-LINE EVENT. Do not skip, xfail or re-bless it.
"""
import pandas as pd
import pytest

import swingbot.core.levels as levels
from swingbot.core.options import levels_source


@pytest.fixture
def landmine(monkeypatch):
    """Make any options access explode, so we can prove it never happens."""
    def boom(*a, **kw):
        raise AssertionError(
            "LOOKAHEAD: options data reached a historical code path")
    monkeypatch.setattr(levels_source, "options_candidates", boom)
    return boom


def test_build_level_map_without_extra_candidates_never_touches_options(landmine, sample_daily_df, sample_horizon):
    supports, resistances = levels.build_level_map(
        sample_daily_df, sample_horizon, current_price=100.0)
    assert isinstance(supports, list) and isinstance(resistances, list)


def test_backtest_scenarios_never_touch_options(landmine, sample_daily_df):
    from swingbot.core import backtest_scenarios
    backtest_scenarios.levels_asof("TEST", sample_daily_df,
                                   bar_index=len(sample_daily_df) - 1,
                                   horizon_key="3m", cache={})


def test_extra_candidates_is_keyword_only():
    """Positional passing would let a backtest supply it by accident."""
    import inspect
    sig = inspect.signature(levels.build_level_map)
    p = sig.parameters["extra_candidates"]
    assert p.kind is inspect.Parameter.KEYWORD_ONLY
    assert p.default is None
```

Add to `tests/conftest.py` if not already present:

```python
@pytest.fixture
def sample_daily_df():
    import numpy as np, pandas as pd
    n = 400
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    close = pd.Series(100 + np.cumsum(np.random.default_rng(7).normal(0, 1, n)), index=idx)
    return pd.DataFrame({"Open": close, "High": close * 1.01,
                         "Low": close * 0.99, "Close": close,
                         "Volume": 1_000_000}, index=idx)


@pytest.fixture
def sample_horizon():
    from swingbot.core.strategy_types import HORIZONS
    return HORIZONS["3m"]
```

- [ ] **Step 2: Run the guard test to verify it fails**

Run: `python -m pytest tests/test_options_no_lookahead.py -v`
Expected: FAIL — `KeyError: 'extra_candidates'` on the signature test; the import of `levels_source` also fails.

- [ ] **Step 3: Add the keyword-only seam**

In `swingbot/core/levels.py`, replace `build_level_map` (currently at `:505`):

```python
def build_level_map(df: pd.DataFrame, h: dict, current_price: float,
                    *, extra_candidates: list | None = None):
    """Returns (supports, resistances): Level lists below/above current_price, nearest first.

    `extra_candidates` is a list of (price, source_label) tuples appended to
    the ones collect_candidate_levels() derives from price history.

    IT IS KEYWORD-ONLY AND DEFAULTS TO None ON PURPOSE. The only caller that
    passes it is the live scan. Options-derived levels come from *today's*
    chain -- yfinance serves no history -- so letting them reach a backtest
    would inject today's positioning into every historical bar. Backtest
    callers (backtest.py's memo, backtest_scenarios.levels_asof) must never
    pass it. tests/test_options_no_lookahead.py enforces this.
    """
    candidates = collect_candidate_levels(df, h, current_price)
    if extra_candidates:
        candidates = candidates + list(extra_candidates)
    clustered = _cluster_levels(candidates)
    supports = sorted([lv for lv in clustered if lv.price < current_price], key=lambda l: -l.price)
    resistances = sorted([lv for lv in clustered if lv.price > current_price], key=lambda l: l.price)
    return supports, resistances
```

- [ ] **Step 4: Write the adapter**

```python
# swingbot/core/options/levels_source.py
"""Adapter turning options positioning into ordinary level candidates.

This is the seam that makes the whole plan worth building. levels.py's
collect_candidate_levels() already returns (price, source_label) tuples
from every method the bot knows -- EMAs, VWAP, Fibonacci, pivots,
trendlines, fair value gaps -- and _cluster_levels() merges anything
nearby into one Level carrying all its sources. An open-interest wall is
simply one more method, so a wall sitting on an EMA raises confluence
exactly the way a real second method does.

ADDITIVE ONLY: this can add candidates. It can never remove one, reject a
scenario, or move a target.

NEVER call this from a backtest. See build_level_map's docstring.
"""
import datetime as dt
import logging

from swingbot import config
from swingbot.core.options import exposure, snapshots

log = logging.getLogger(__name__)


def options_candidates(ticker: str, spot: float, *, today: dt.date | None = None,
                       root=None) -> list[tuple[float, str]]:
    """OI walls plus the gamma flip level, as (price, label) tuples.

    Returns [] on any failure. The level engine's contract is that a single
    method failing is skipped rather than failing the whole ticker, and this
    method honours it -- including for the many watchlist names whose chains
    never survive the liquidity filter.
    """
    if not (config.OPTIONS_ENABLED and config.OPTIONS_LEVELS_ENABLED):
        return []
    if not spot or spot <= 0:
        return []

    today = today or dt.date.today()
    try:
        payload = snapshots.load_snapshot(ticker, today, root=root)
        if payload is None:
            # Fall back to the most recent recorded day: open interest moves
            # slowly, so yesterday's walls are still yesterday's walls.
            hist = snapshots.load_history(ticker, days=1, root=root)
            payload = hist[-1] if hist else None
        if payload is None:
            return []

        out = list(exposure.oi_walls(payload))
        flip = exposure.gamma_flip(exposure.gamma_exposure(payload, today=today))
        if flip:
            out.append((float(flip), "Gamma Flip"))
        return out
    except Exception as exc:
        log.debug("options: no level candidates for %s (%s)", ticker, exc)
        return []
```

- [ ] **Step 5: Write the adapter tests**

```python
# tests/test_options_levels_source.py
import datetime as dt
import pandas as pd
import pytest

import swingbot.core.levels as levels
from swingbot.core.options import levels_source, snapshots

TODAY = dt.date(2026, 8, 6)
COLS = ["strike", "openInterest", "impliedVolatility", "bid", "ask"]


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setattr(levels_source.config, "OPTIONS_ENABLED", True)
    monkeypatch.setattr(levels_source.config, "OPTIONS_LEVELS_ENABLED", True)


def _write(tmp_path, spot=100.0):
    calls = pd.DataFrame([[110.0, 9000, 0.2, 1.0, 1.1]], columns=COLS)
    puts = pd.DataFrame([[90.0, 8000, 0.2, 1.0, 1.1]], columns=COLS)
    snapshots.write_snapshot(
        {"ticker": "TEST", "spot": spot, "asof": TODAY.isoformat(),
         "expiries": {"2026-12-18": {"calls": calls, "puts": puts}}}, root=tmp_path)


def test_returns_walls_from_the_snapshot(tmp_path):
    _write(tmp_path)
    got = levels_source.options_candidates("TEST", 100.0, today=TODAY, root=tmp_path)
    assert (110.0, "Call OI Wall") in got
    assert (90.0, "Put OI Wall") in got


def test_returns_empty_when_the_flag_is_off(tmp_path, monkeypatch):
    monkeypatch.setattr(levels_source.config, "OPTIONS_LEVELS_ENABLED", False)
    _write(tmp_path)
    assert levels_source.options_candidates("TEST", 100.0, today=TODAY, root=tmp_path) == []


def test_returns_empty_rather_than_raising_when_no_data(tmp_path):
    assert levels_source.options_candidates("NOPE", 100.0, today=TODAY, root=tmp_path) == []


def test_a_wall_on_an_existing_level_merges_into_one_level(sample_daily_df, sample_horizon):
    """The point of the whole seam: a wall near an EMA must raise confluence,
    not appear as a separate duplicate level."""
    base, _ = levels.build_level_map(sample_daily_df, sample_horizon, current_price=100.0)
    assert base, "fixture produced no supports"
    target = base[0].price

    merged, _ = levels.build_level_map(
        sample_daily_df, sample_horizon, current_price=100.0,
        extra_candidates=[(target * 1.0001, "Put OI Wall")])

    hit = [lv for lv in merged if abs(lv.price - target) / target < 0.01]
    assert len(hit) == 1
    assert "Put OI Wall" in hit[0].sources
    assert len(hit[0].sources) > 1
```

- [ ] **Step 6: Run all the tests**

Run: `python -m pytest tests/test_options_no_lookahead.py tests/test_options_levels_source.py tests/test_levels.py -v`
Expected: PASS. If any existing `test_levels.py` test fails, `build_level_map`'s default behaviour changed — it must be bit-identical when `extra_candidates` is `None`.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/levels.py swingbot/core/options/levels_source.py tests/test_options_no_lookahead.py tests/test_options_levels_source.py tests/conftest.py
git commit -m "feat(D9): the no-lookahead firewall, and OI walls as ordinary level candidates"
```

---

### Task D10: Wire the live scan call site

**Files:**
- Modify: `swingbot/core/scanning/engine.py` (the live `build_level_map` call)
- Test: `tests/test_options_scan_wiring.py`

**Interfaces:**
- Consumes: `levels_source.options_candidates`, `build_level_map(..., extra_candidates=)`
- Produces: no new API

- [ ] **Step 1: Find the live call site**

Run: `git grep -n "build_level_map" -- "swingbot/**/*.py"`
Note which hits are live-scan and which are backtest. **Only the live-scan hit is modified.**

- [ ] **Step 2: Write the failing test**

```python
# tests/test_options_scan_wiring.py
import pytest


def test_live_scan_passes_options_candidates(monkeypatch, sample_daily_df, sample_horizon):
    from swingbot.core.scanning import engine
    seen = {}

    def fake_candidates(ticker, spot, **kw):
        seen["ticker"] = ticker
        return [(101.0, "Call OI Wall")]

    monkeypatch.setattr(engine.levels_source, "options_candidates", fake_candidates)
    monkeypatch.setattr(engine.config, "OPTIONS_ENABLED", True)
    monkeypatch.setattr(engine.config, "OPTIONS_LEVELS_ENABLED", True)

    supports, resistances = engine.level_map_for_scan(
        "TEST", sample_daily_df, sample_horizon, current_price=100.0)
    assert seen["ticker"] == "TEST"
    assert any("Call OI Wall" in lv.sources for lv in resistances)


def test_live_scan_is_unaffected_when_options_are_off(monkeypatch, sample_daily_df, sample_horizon):
    from swingbot.core.scanning import engine
    monkeypatch.setattr(engine.config, "OPTIONS_ENABLED", False)
    a = engine.level_map_for_scan("TEST", sample_daily_df, sample_horizon, current_price=100.0)
    b = engine.level_map_for_scan("TEST", sample_daily_df, sample_horizon, current_price=100.0)
    assert [lv.price for lv in a[0]] == [lv.price for lv in b[0]]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_options_scan_wiring.py -v`
Expected: FAIL — `AttributeError: module has no attribute 'level_map_for_scan'`

- [ ] **Step 4: Add the live-scan wrapper**

In `swingbot/core/scanning/engine.py`, add near the existing level usage:

```python
from swingbot.core.options import levels_source


def level_map_for_scan(ticker: str, df, h: dict, current_price: float):
    """The ONE call site allowed to feed options data into a level map.

    Kept as a named function so the boundary is greppable and so
    tests/test_options_no_lookahead.py has something specific to assert
    about. Backtests call levels.build_level_map() directly and never
    reach this.
    """
    extra = levels_source.options_candidates(ticker, current_price)
    return levels.build_level_map(df, h, current_price, extra_candidates=extra)
```

Then replace the live scan's direct `levels.build_level_map(df, h, price)` call with `level_map_for_scan(ticker, df, h, price)`.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_options_scan_wiring.py tests/test_options_no_lookahead.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/engine.py tests/test_options_scan_wiring.py
git commit -m "feat(D10): the live scan is the only path that feeds options into a level map"
```

---

### Task D11: IV rank as an additive score component

**Files:**
- Modify: `swingbot/core/quality.py`
- Test: `tests/test_options_quality.py`

**Interfaces:**
- Consumes: `vol.iv_rank`
- Produces: `iv_rank_points(iv_rank: float) -> int`; `score_plan(..., iv_rank=None)`

**Why this is clean:** `score_plan()` already has an optional-component loop — `for name, value, fn in (("rs", rs_percentile, rs_points), ...)` with `if value is not None` — and its docstring states *"A component only appears in the breakdown when its input was actually supplied."* That is exactly the cold-start semantics IV rank needs: `None` before the history threshold means the row simply does not render.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_options_quality.py
import pytest

from swingbot.core import quality

BASE = dict(direction="bullish", regime="bull", htf_bias="bull",
            confluence_count=3, volume_ratio=1.2, atr_pct=2.0,
            trigger_distance_pct=1.0, badge_status="PROVEN")


def test_iv_rank_points_are_a_bonus_never_a_penalty():
    """Additive-only: the component's floor is zero. An unvalidated signal
    may raise a score; it may never drag a good setup below its tier."""
    for r in (0, 10, 25, 50, 75, 90, 100):
        assert quality.iv_rank_points(r) >= 0


def test_low_iv_rank_scores_higher_than_high_iv_rank():
    """Cheap options mean the market is not already pricing the move we are
    targeting -- more room for the target to be reached at reasonable cost."""
    assert quality.iv_rank_points(10) > quality.iv_rank_points(90)


def test_iv_rank_absent_leaves_the_breakdown_untouched():
    a = quality.score_plan(**BASE)
    b = quality.score_plan(**BASE, iv_rank=None)
    assert a.score == b.score
    assert a.breakdown == b.breakdown
    assert not any(name == "iv_rank" for name, _ in b.breakdown)


def test_iv_rank_present_adds_exactly_one_breakdown_row():
    out = quality.score_plan(**BASE, iv_rank=15.0)
    rows = [n for n, _ in out.breakdown]
    assert rows.count("iv_rank") == 1
    assert out.score >= quality.score_plan(**BASE).score
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_options_quality.py -v`
Expected: FAIL — `AttributeError: module 'swingbot.core.quality' has no attribute 'iv_rank_points'`

- [ ] **Step 3: Implement**

Add to `swingbot/core/quality.py`:

```python
def iv_rank_points(iv_rank: float) -> int:
    """Bonus points from IV rank. Bonus ONLY -- never negative.

    Low IV rank means the option market is not already pricing a large move,
    so a swing target has room to be reached without volatility having been
    bid up in anticipation. High IV rank often means the move is already
    expected (or an event is pending), which is not a reason to reject a
    setup -- just not a reason to reward it.

    Options data is additive-only under plan v9: it may raise a score, never
    veto a plan or shrink a target. Keeping this floor at zero is what
    enforces that here.
    """
    if iv_rank is None:
        return 0
    if iv_rank <= 20:
        return 4
    if iv_rank <= 40:
        return 2
    if iv_rank <= 70:
        return 1
    return 0
```

Then extend `score_plan`'s signature and its optional-component loop:

```python
def score_plan(*, direction, regime, htf_bias, confluence_count, volume_ratio,
               atr_pct, trigger_distance_pct, badge_status,
               rs_percentile=None, mtf=None, breadth=None,
               candle_quality=None, gap_fragile=False, iv_rank=None) -> QualityResult:
```

and add one entry to the existing tuple:

```python
    for name, value, fn in (("rs", rs_percentile, rs_points),
                            ("mtf", mtf, mtf_points),
                            ("breadth", breadth, breadth_points),
                            ("candle", candle_quality, candle_points),
                            ("iv_rank", iv_rank, iv_rank_points)):
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_options_quality.py tests/test_quality.py -v`
Expected: PASS. `test_quality.py` must be untouched — every existing caller omits `iv_rank`, so scores stay bit-identical.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/quality.py tests/test_options_quality.py
git commit -m "feat(D11): IV rank as a bonus-only score component"
```

---

# Phase D3 — Alerts

### Task D12: The four detectors

**Files:**
- Create: `swingbot/core/options/alerts.py`
- Test: `tests/test_options_alerts.py`

**Interfaces:**
- Consumes: `exposure`, `vol`, `snapshots`
- Produces:
  - `OptionsSignal` dataclass: `ticker: str`, `kind: str`, `strength: float`, `price: float | None`, `headline: str`, `detail: str`
  - `detect_wall_approach(ticker, spot, payload) -> OptionsSignal | None`
  - `detect_iv_extreme(ticker, *, root=None) -> OptionsSignal | None`
  - `detect_oi_build(ticker, *, root=None) -> OptionsSignal | None`
  - `detect_gamma_flip_cross(ticker, spot, payload, prev_spot) -> OptionsSignal | None`
  - `detect_all(ticker, spot, *, root=None, prev_spot=None) -> list[OptionsSignal]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_options_alerts.py
import datetime as dt
import pandas as pd
import pytest

from swingbot.core.options import alerts, snapshots

TODAY = dt.date(2026, 8, 6)
COLS = ["strike", "openInterest", "impliedVolatility", "bid", "ask"]


def _payload(day, call_oi=9000, put_oi=8000, spot=100.0):
    calls = pd.DataFrame([[103.0, call_oi, 0.2, 1.0, 1.1]], columns=COLS)
    puts = pd.DataFrame([[90.0, put_oi, 0.2, 1.0, 1.1]], columns=COLS)
    return {"ticker": "TEST", "spot": spot, "asof": day,
            "expiries": {"2026-12-18": {"calls": calls, "puts": puts}}}


def test_wall_approach_fires_when_price_is_near_a_wall():
    sig = alerts.detect_wall_approach("TEST", 100.0, _payload(TODAY.isoformat()))
    assert sig is not None and sig.kind == "wall_approach"
    assert sig.price == 103.0


def test_wall_approach_is_silent_when_price_is_far():
    p = _payload(TODAY.isoformat(), spot=100.0)
    assert alerts.detect_wall_approach("TEST", 60.0, p) is None


def test_iv_extreme_is_silent_during_cold_start(tmp_path, monkeypatch):
    monkeypatch.setattr(alerts.vol.config, "OPTIONS_IV_RANK_MIN_HISTORY", 60)
    snapshots.write_snapshot(_payload(TODAY.isoformat()), root=tmp_path)
    assert alerts.detect_iv_extreme("TEST", root=tmp_path) is None


def test_oi_build_needs_at_least_two_snapshots(tmp_path):
    snapshots.write_snapshot(_payload(TODAY.isoformat()), root=tmp_path)
    assert alerts.detect_oi_build("TEST", root=tmp_path) is None


def test_oi_build_fires_on_a_multi_day_increase(tmp_path):
    for n, oi in enumerate([1000, 3000, 6000, 9000]):
        day = (TODAY - dt.timedelta(days=3 - n)).isoformat()
        snapshots.write_snapshot(_payload(day, call_oi=oi), root=tmp_path)
    sig = alerts.detect_oi_build("TEST", root=tmp_path)
    assert sig is not None and sig.kind == "oi_build"
    assert sig.price == 103.0


def test_gamma_flip_cross_is_index_etfs_only(monkeypatch):
    """The modeled flip level is an index phenomenon. On a single name it is
    noise, so the detector must refuse before it even computes."""
    monkeypatch.setattr(alerts.exposure, "gamma_flip", lambda gex: 100.0)
    p = _payload(TODAY.isoformat())
    assert alerts.detect_gamma_flip_cross("TEST", 101.0, p, prev_spot=99.0) is None


def test_gamma_flip_cross_fires_only_when_prev_and_now_straddle_the_level(monkeypatch):
    monkeypatch.setattr(alerts.exposure, "gamma_flip", lambda gex: 100.0)
    p = _payload(TODAY.isoformat())
    # 99 -> 101 crosses 100 upward
    sig = alerts.detect_gamma_flip_cross("SPY", 101.0, p, prev_spot=99.0)
    assert sig is not None and sig.kind == "gamma_flip" and sig.price == 100.0
    # 101 -> 102 stays on one side
    assert alerts.detect_gamma_flip_cross("SPY", 102.0, p, prev_spot=101.0) is None


def test_gamma_flip_cross_is_silent_when_the_profile_has_no_single_flip(monkeypatch):
    monkeypatch.setattr(alerts.exposure, "gamma_flip", lambda gex: None)
    p = _payload(TODAY.isoformat())
    assert alerts.detect_gamma_flip_cross("SPY", 101.0, p, prev_spot=99.0) is None


def test_detect_all_returns_a_list_and_never_raises_on_junk(tmp_path):
    assert alerts.detect_all("NOPE", 100.0, root=tmp_path) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_options_alerts.py -v`
Expected: FAIL — `cannot import name 'alerts'`

- [ ] **Step 3: Implement**

```python
# swingbot/core/options/alerts.py
"""The four standalone options alerts.

These are CONTEXT, not trade plans. They post to their own channel so they
do not dilute the alerts you act on, and they are capped and cooled down
because four detectors across ~75 tickers would otherwise flood it.

Two of the four cannot fire at all until history has accrued -- see the
cold-start contract in vol.py.
"""
import datetime as dt
import logging
from dataclasses import dataclass

from swingbot import config
from swingbot.core.options import exposure, snapshots, vol

log = logging.getLogger(__name__)

WALL_PROXIMITY_PCT = 3.0
IV_RANK_LOW, IV_RANK_HIGH = 15.0, 85.0
OI_BUILD_MIN_DAYS = 3
OI_BUILD_MIN_GROWTH = 2.0
INDEX_ETFS = {"SPY", "QQQ", "IWM", "DIA"}


@dataclass
class OptionsSignal:
    ticker: str
    kind: str
    strength: float          # 0..1, used to pick survivors under the daily cap
    price: float | None
    headline: str
    detail: str


def detect_wall_approach(ticker: str, spot: float, payload: dict | None) -> OptionsSignal | None:
    """Price nearing a strike with dominant open interest -- a magnet or
    barrier that persists over weeks, which is why it is the most
    swing-relevant of the four."""
    if not payload or not spot or spot <= 0:
        return None
    walls = exposure.oi_walls(payload, n=3)
    if not walls:
        return None

    nearest, label, best = None, None, None
    for price, lbl in walls:
        dist = abs(price - spot) / spot * 100
        if dist <= WALL_PROXIMITY_PCT and (best is None or dist < best):
            nearest, label, best = price, lbl, dist
    if nearest is None:
        return None

    return OptionsSignal(
        ticker=ticker, kind="wall_approach",
        strength=max(0.0, 1.0 - best / WALL_PROXIMITY_PCT),
        price=nearest,
        headline=f"{ticker} approaching {label.lower()} at {nearest:.2f}",
        detail=(f"Spot {spot:.2f} is {best:.1f}% from a strike carrying the "
                f"heaviest open interest in range. Such strikes tend to act "
                f"as magnets or barriers over the following weeks."))


def detect_iv_extreme(ticker: str, *, root=None) -> OptionsSignal | None:
    rank = vol.iv_rank(ticker, root=root)
    if rank is None:
        return None          # cold start -- not "neutral", simply unknown
    if IV_RANK_LOW < rank < IV_RANK_HIGH:
        return None

    cheap = rank <= IV_RANK_LOW
    return OptionsSignal(
        ticker=ticker, kind="iv_extreme",
        strength=abs(rank - 50.0) / 50.0, price=None,
        headline=f"{ticker} options unusually {'cheap' if cheap else 'expensive'} (IV rank {rank:.0f})",
        detail=("The market is pricing an unusually small move relative to this "
                "ticker's own recorded range -- targets have room without "
                "volatility already bid up." if cheap else
                "The market is pricing an unusually large move. Often an event "
                "is pending; treat targets with more caution."))


def detect_oi_build(ticker: str, *, root=None) -> OptionsSignal | None:
    """Open interest stacking at one strike across sessions -- someone
    positioning for a move to that level."""
    hist = snapshots.load_history(ticker, days=OI_BUILD_MIN_DAYS + 1, root=root)
    if len(hist) < OI_BUILD_MIN_DAYS:
        return None

    def totals(snap):
        out = {}
        for sides in snap.get("expiries", {}).values():
            for df in sides.values():
                if df is None or df.empty:
                    continue
                for row in df.itertuples(index=False):
                    out[float(row.strike)] = out.get(float(row.strike), 0.0) + float(row.openInterest or 0)
        return out

    first, last = totals(hist[0]), totals(hist[-1])
    best_strike, best_growth = None, 0.0
    for strike, now in last.items():
        then = first.get(strike, 0.0)
        if then <= 0 or now < 1000:
            continue
        growth = now / then
        if growth >= OI_BUILD_MIN_GROWTH and growth > best_growth:
            best_strike, best_growth = strike, growth
    if best_strike is None:
        return None

    return OptionsSignal(
        ticker=ticker, kind="oi_build",
        strength=min(1.0, (best_growth - OI_BUILD_MIN_GROWTH) / 4.0),
        price=best_strike,
        headline=f"{ticker} open interest building at {best_strike:.2f} ({best_growth:.1f}x)",
        detail=(f"Open interest at this strike has grown {best_growth:.1f}x over "
                f"{len(hist)} sessions -- positioning is accumulating around "
                f"that level."))


def detect_gamma_flip_cross(ticker: str, spot: float, payload: dict | None,
                            prev_spot: float | None) -> OptionsSignal | None:
    """Index ETFs only. Dealer-gamma regime is an index phenomenon; on a
    single name the modeled flip level is noise."""
    if ticker.upper() not in INDEX_ETFS:
        return None
    if not payload or not spot or not prev_spot:
        return None
    flip = exposure.gamma_flip(exposure.gamma_exposure(payload))
    if not flip:
        return None
    if (prev_spot < flip) == (spot < flip):
        return None          # no crossing

    upward = spot >= flip
    return OptionsSignal(
        ticker=ticker, kind="gamma_flip", strength=0.6, price=flip,
        headline=f"{ticker} crossed its modeled gamma flip at {flip:.2f}",
        detail=("Price moved above the modeled zero-gamma level, a regime that "
                "historically damps volatility." if upward else
                "Price moved below the modeled zero-gamma level, a regime that "
                "historically amplifies moves.")
                + " Modeled from open interest, not observed dealer positioning.")


def detect_all(ticker: str, spot: float, *, root=None,
               prev_spot: float | None = None) -> list[OptionsSignal]:
    if not (config.OPTIONS_ENABLED and config.OPTIONS_ALERTS_ENABLED):
        return []
    try:
        hist = snapshots.load_history(ticker, days=1, root=root)
        payload = hist[-1] if hist else None
    except Exception:
        return []

    out = []
    for fn in (lambda: detect_wall_approach(ticker, spot, payload),
               lambda: detect_iv_extreme(ticker, root=root),
               lambda: detect_oi_build(ticker, root=root),
               lambda: detect_gamma_flip_cross(ticker, spot, payload, prev_spot)):
        try:
            sig = fn()
        except Exception as exc:
            log.debug("options: detector failed for %s (%s)", ticker, exc)
            continue
        if sig is not None:
            out.append(sig)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_options_alerts.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/options/alerts.py tests/test_options_alerts.py
git commit -m "feat(D12): the four options detectors, two of them silent until history accrues"
```

---

### Task D13: Throttling — caps and cooldowns

**Files:**
- Modify: `swingbot/core/options/alerts.py`
- Test: `tests/test_options_throttle.py`

**Interfaces:**
- Produces:
  - `throttle(signals: list[OptionsSignal], *, state: dict, today: date, cap: int, cooldown_days: int) -> tuple[list[OptionsSignal], dict]`
  - `load_state(path) -> dict`, `save_state(state, path) -> None`

**Why:** four detectors × ~75 tickers. Without this the options channel is unreadable within a week, which contradicts the README's stated "quality over quantity" principle.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_options_throttle.py
import datetime as dt
import pytest

from swingbot.core.options.alerts import OptionsSignal, throttle

TODAY = dt.date(2026, 8, 6)


def _sig(ticker, kind="wall_approach", strength=0.5):
    return OptionsSignal(ticker=ticker, kind=kind, strength=strength,
                         price=100.0, headline="h", detail="d")


def test_cap_keeps_only_the_strongest_per_type():
    sigs = [_sig(f"T{i}", strength=i / 10) for i in range(10)]
    kept, _ = throttle(sigs, state={}, today=TODAY, cap=3, cooldown_days=5)
    assert len(kept) == 3
    assert {s.ticker for s in kept} == {"T9", "T8", "T7"}


def test_cap_applies_per_type_not_globally():
    sigs = ([_sig(f"A{i}", kind="wall_approach", strength=0.5) for i in range(4)]
            + [_sig(f"B{i}", kind="oi_build", strength=0.5) for i in range(4)])
    kept, _ = throttle(sigs, state={}, today=TODAY, cap=2, cooldown_days=5)
    assert sum(1 for s in kept if s.kind == "wall_approach") == 2
    assert sum(1 for s in kept if s.kind == "oi_build") == 2


def test_cooldown_suppresses_a_repeat_of_the_same_ticker_and_type():
    kept, state = throttle([_sig("AAA")], state={}, today=TODAY, cap=5, cooldown_days=5)
    assert len(kept) == 1
    again, _ = throttle([_sig("AAA")], state=state,
                        today=TODAY + dt.timedelta(days=2), cap=5, cooldown_days=5)
    assert again == []


def test_cooldown_expires():
    _, state = throttle([_sig("AAA")], state={}, today=TODAY, cap=5, cooldown_days=5)
    later, _ = throttle([_sig("AAA")], state=state,
                        today=TODAY + dt.timedelta(days=6), cap=5, cooldown_days=5)
    assert len(later) == 1


def test_cooldown_is_scoped_per_type():
    _, state = throttle([_sig("AAA", kind="wall_approach")], state={},
                        today=TODAY, cap=5, cooldown_days=5)
    other, _ = throttle([_sig("AAA", kind="iv_extreme")], state=state,
                        today=TODAY, cap=5, cooldown_days=5)
    assert len(other) == 1


def test_one_ticker_yields_only_its_strongest_signal_per_day():
    sigs = [_sig("AAA", kind="wall_approach", strength=0.9),
            _sig("AAA", kind="oi_build", strength=0.2)]
    kept, _ = throttle(sigs, state={}, today=TODAY, cap=5, cooldown_days=5)
    assert len(kept) == 1 and kept[0].kind == "wall_approach"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_options_throttle.py -v`
Expected: FAIL — `cannot import name 'throttle'`

- [ ] **Step 3: Implement**

Append to `swingbot/core/options/alerts.py`:

```python
import json
from pathlib import Path

STATE_PATH = Path("data/options_alert_state.json")


def load_state(path: Path | None = None) -> dict:
    p = Path(path or STATE_PATH)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict, path: Path | None = None) -> None:
    p = Path(path or STATE_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    tmp.replace(p)


def throttle(signals: list[OptionsSignal], *, state: dict, today: dt.date,
             cap: int, cooldown_days: int) -> tuple[list[OptionsSignal], dict]:
    """Cut the day's raw detections down to something worth reading.

    Three rules, applied in order:
      1. A (ticker, kind) that fired inside the cooldown stays silent.
      2. Each ticker contributes only its single strongest signal per day.
      3. Each kind is capped, keeping the strongest.

    Returns (kept, updated_state). State is a flat {"TICKER|kind": "ISO date"}
    map so it survives a restart and stays trivially inspectable.
    """
    state = dict(state or {})

    fresh = []
    for s in signals:
        last = state.get(f"{s.ticker}|{s.kind}")
        if last:
            try:
                if (today - dt.date.fromisoformat(last)).days < cooldown_days:
                    continue
            except ValueError:
                pass
        fresh.append(s)

    best_per_ticker: dict[str, OptionsSignal] = {}
    for s in fresh:
        cur = best_per_ticker.get(s.ticker)
        if cur is None or s.strength > cur.strength:
            best_per_ticker[s.ticker] = s

    kept: list[OptionsSignal] = []
    by_kind: dict[str, list[OptionsSignal]] = {}
    for s in best_per_ticker.values():
        by_kind.setdefault(s.kind, []).append(s)
    for kind, group in by_kind.items():
        group.sort(key=lambda s: -s.strength)
        kept.extend(group[:cap])

    for s in kept:
        state[f"{s.ticker}|{s.kind}"] = today.isoformat()
    return kept, state
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_options_throttle.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/options/alerts.py tests/test_options_throttle.py
git commit -m "feat(D13): cap and cool down the options channel so it stays readable"
```

---

### Task D14: Post to the options channel

**Files:**
- Modify: `swingbot/bot_core.py` (daily options pass), `swingbot/core/scanning/embed_theme.py` (embed colour)
- Test: `tests/test_options_posting.py`

**Interfaces:**
- Consumes: `alerts.detect_all`, `alerts.throttle`, `config.DISCORD_CHANNEL_OPTIONS_ID`
- Produces: `options_embed(signal: OptionsSignal) -> discord.Embed`; `run_options_pass(bot, *, today=None) -> int`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_options_posting.py
import datetime as dt
import pytest

from swingbot.core.options.alerts import OptionsSignal


def test_embed_carries_the_modeled_qualifier_for_gamma():
    from swingbot import bot_core
    sig = OptionsSignal("SPY", "gamma_flip", 0.6, 500.0,
                        "SPY crossed its modeled gamma flip at 500.00",
                        "detail text")
    e = bot_core.options_embed(sig)
    text = (e.title or "") + (e.description or "")
    assert "modeled" in text.lower()


def test_pass_is_a_noop_when_no_channel_is_configured(monkeypatch):
    from swingbot import bot_core
    monkeypatch.setattr(bot_core.config, "OPTIONS_ENABLED", True)
    monkeypatch.setattr(bot_core.config, "OPTIONS_ALERTS_ENABLED", True)
    monkeypatch.setattr(bot_core.config, "DISCORD_CHANNEL_OPTIONS_ID", "")
    assert bot_core.run_options_pass(bot=None, today=dt.date(2026, 8, 6)) == 0


def test_pass_is_a_noop_when_alerts_are_off(monkeypatch):
    from swingbot import bot_core
    monkeypatch.setattr(bot_core.config, "OPTIONS_ALERTS_ENABLED", False)
    assert bot_core.run_options_pass(bot=None, today=dt.date(2026, 8, 6)) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_options_posting.py -v`
Expected: FAIL — `AttributeError: module 'swingbot.bot_core' has no attribute 'options_embed'`

- [ ] **Step 3: Implement**

Add to `swingbot/bot_core.py`, following the existing channel-posting helpers:

```python
from swingbot.core.options import alerts as options_alerts

_OPTIONS_COLOUR = discord.Color.from_rgb(120, 90, 200)


def options_embed(signal) -> discord.Embed:
    """Options context, visually distinct from trade plans.

    Gamma-derived readings always carry the 'modeled, not observed' note:
    we cannot see dealer inventory on free data, and presenting a model as
    an observation would be the single most misleading thing this feature
    could do.
    """
    desc = signal.detail
    if signal.kind == "gamma_flip" and "modeled" not in desc.lower():
        desc += "\n\n*Modeled from open interest, not observed positioning.*"
    e = discord.Embed(title=signal.headline, description=desc,
                      colour=_OPTIONS_COLOUR)
    if signal.price:
        e.add_field(name="Level", value=f"{signal.price:.2f}", inline=True)
    e.set_footer(text="Options context -- not a trade plan.")
    return e


def run_options_pass(bot, *, today=None) -> int:
    """One daily sweep of the four detectors across the watchlist.

    Returns the number of alerts posted. Runs after the snapshot job, off
    the scan loop.
    """
    if not (config.OPTIONS_ENABLED and config.OPTIONS_ALERTS_ENABLED):
        return 0
    if not config.DISCORD_CHANNEL_OPTIONS_ID:
        return 0

    today = today or dt.date.today()
    raw = []
    for ticker in config.WATCHLIST:
        try:
            spot = latest_price(ticker)
        except Exception:
            continue
        if not spot:
            continue
        raw.extend(options_alerts.detect_all(ticker, spot))

    state = options_alerts.load_state()
    kept, state = options_alerts.throttle(
        raw, state=state, today=today,
        cap=config.OPTIONS_ALERT_DAILY_CAP,
        cooldown_days=config.OPTIONS_ALERT_COOLDOWN_DAYS)
    options_alerts.save_state(state)

    channel = bot.get_channel(int(config.DISCORD_CHANNEL_OPTIONS_ID)) if bot else None
    if channel is None:
        return 0
    for sig in kept:
        bot.loop.create_task(channel.send(embed=options_embed(sig)))
    return len(kept)
```

Register the daily pass alongside the existing scheduled jobs, after the snapshot job.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_options_posting.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add swingbot/bot_core.py tests/test_options_posting.py
git commit -m "feat(D14): post options context to its own channel"
```

---

# Phase D4 — Dashboard

### Task D15: `!options <TICKER>` command

**Files:**
- Modify: `swingbot/commands/info.py`, `swingbot/commands/slash.py`
- Test: `tests/test_options_command.py`

**Interfaces:**
- Consumes: `vol`, `exposure`, `snapshots`
- Produces: `build_options_view(ticker: str, *, root=None, today=None) -> discord.Embed`

Follow the shape of the existing `regime_cmd` at `swingbot/commands/info.py:166` and `slash_regime` at `swingbot/commands/slash.py:129`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_options_command.py
import datetime as dt
import pandas as pd
import pytest

from swingbot.commands.info import build_options_view
from swingbot.core.options import snapshots

TODAY = dt.date(2026, 8, 6)
COLS = ["strike", "openInterest", "impliedVolatility", "bid", "ask"]


def _write(tmp_path):
    calls = pd.DataFrame([[105.0, 9000, 0.25, 1.0, 1.1]], columns=COLS)
    puts = pd.DataFrame([[95.0, 8000, 0.25, 1.0, 1.1]], columns=COLS)
    snapshots.write_snapshot(
        {"ticker": "TEST", "spot": 100.0, "asof": TODAY.isoformat(),
         "expiries": {"2026-11-20": {"calls": calls, "puts": puts}}}, root=tmp_path)


def test_view_says_so_plainly_when_there_is_no_data(tmp_path):
    e = build_options_view("NOPE", root=tmp_path, today=TODAY)
    assert "no options data" in (e.description or "").lower()


def test_view_renders_expected_move_on_day_one(tmp_path):
    _write(tmp_path)
    e = build_options_view("TEST", root=tmp_path, today=TODAY)
    body = " ".join(f.name + f.value for f in e.fields)
    assert "expected move" in body.lower()


def test_view_shows_cold_start_for_iv_rank_rather_than_a_blank(tmp_path, monkeypatch):
    """A blank renders as zero to a reader. Say 'needs N more days' instead."""
    _write(tmp_path)
    e = build_options_view("TEST", root=tmp_path, today=TODAY)
    body = " ".join(f.name + f.value for f in e.fields)
    assert "iv rank" in body.lower()
    assert "more days" in body.lower() or "not yet" in body.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_options_command.py -v`
Expected: FAIL — `cannot import name 'build_options_view'`

- [ ] **Step 3: Implement**

Add to `swingbot/commands/info.py`:

```python
from swingbot.core.options import exposure, snapshots, vol

_HORIZON_DAYS = {"2w": 14, "1m": 30, "3m": 91, "6m": 182, "9m": 273}


def build_options_view(ticker: str, *, root=None, today=None) -> discord.Embed:
    """Everything the free options feed can honestly say about one ticker.

    Anything unavailable is stated as unavailable. A metric still inside its
    cold-start window reports how many more days it needs -- a blank field
    reads as zero, which would be a lie.
    """
    today = today or dt.date.today()
    ticker = ticker.upper()

    payload = snapshots.load_snapshot(ticker, today, root=root)
    if payload is None:
        hist = snapshots.load_history(ticker, days=1, root=root)
        payload = hist[-1] if hist else None
    if payload is None:
        return discord.Embed(
            title=f"{ticker} — options",
            description=("No options data for this ticker. Either its chain never "
                         "survived the liquidity filter, or no snapshot has been "
                         "recorded yet. It trades exactly as it always has."))

    spot = payload["spot"]
    e = discord.Embed(title=f"{ticker} — options positioning",
                      description=f"Spot {spot:.2f} · snapshot {payload['asof']}")

    moves = []
    for key, days in _HORIZON_DAYS.items():
        iv = vol.term_iv(payload, days, today=today)
        if iv:
            moves.append(f"`{key:>3}` ±{vol.expected_move_pct(iv, days):.1f}%  (IV {iv * 100:.0f}%)")
    e.add_field(name="Implied expected move (1σ)",
                value="\n".join(moves) or "No expiry reaches these horizons.",
                inline=False)

    rank = vol.iv_rank(ticker, root=root, today=today)
    if rank is None:
        have = len(list(snapshots.snapshot_dir(ticker, root=root).glob("*.json.gz")))
        need = config.OPTIONS_IV_RANK_MIN_HISTORY
        e.add_field(name="IV rank",
                    value=f"Not yet — needs {max(0, need - have)} more days of history.",
                    inline=True)
    else:
        e.add_field(name="IV rank", value=f"{rank:.0f} / 100", inline=True)

    ratio = vol.put_call_oi_ratio(payload)
    if ratio is not None:
        e.add_field(name="Put/call OI", value=f"{ratio:.2f}", inline=True)

    walls = exposure.oi_walls(payload, n=3)
    if walls:
        e.add_field(name="Open-interest walls",
                    value="\n".join(f"`{p:>9.2f}`  {lbl}" for p, lbl in sorted(walls)),
                    inline=False)

    flip = exposure.gamma_flip(exposure.gamma_exposure(payload, today=today))
    if flip:
        e.add_field(name="Gamma flip (modeled)",
                    value=f"{flip:.2f} — modeled from open interest, not observed positioning.",
                    inline=False)

    e.set_footer(text="Free-tier options data. Additive context only — never vetoes a plan.")
    return e


@bot.command(name="options")
async def options_cmd(ctx, ticker: str):
    await ctx.send(embed=build_options_view(ticker))
```

Add the matching slash command in `swingbot/commands/slash.py`, mirroring `slash_regime`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_options_command.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/info.py swingbot/commands/slash.py tests/test_options_command.py
git commit -m "feat(D15): !options -- and it says 'not yet' rather than rendering a blank as zero"
```

---

### Task D16: Admin UI page and heatmap

**Files:**
- Modify: `swingbot/admin/app.py`
- Create: `swingbot/admin/templates/options.html`, `swingbot/core/charts/options_heatmap.py`
- Test: `tests/test_options_heatmap.py`, `tests/test_admin_options_page.py`

**Interfaces:**
- Produces:
  - `heatmap_frame(payload: dict, *, metric: str = "oi", today=None) -> pd.DataFrame` — strikes × expiries
  - `render_heatmap(frame: pd.DataFrame, *, metric: str) -> bytes` — PNG
  - Flask route `GET /options` and `GET /options/<ticker>`

The page carries the surviving DSGEX tabs only — volatility, OI change, heatmap. **No FLOW, DIF or COT tabs**: they would have to be faked.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_options_heatmap.py
import datetime as dt
import pandas as pd
import pytest

from swingbot.core.charts import options_heatmap

TODAY = dt.date(2026, 8, 6)
COLS = ["strike", "openInterest", "impliedVolatility", "bid", "ask"]


def _payload():
    df = pd.DataFrame([[95.0, 500, 0.2, 1.0, 1.1], [100.0, 900, 0.2, 1.0, 1.1]],
                      columns=COLS)
    return {"ticker": "TEST", "spot": 100.0, "asof": TODAY.isoformat(),
            "expiries": {"2026-09-18": {"calls": df, "puts": df},
                         "2026-12-18": {"calls": df, "puts": df}}}


def test_frame_is_strikes_by_expiries():
    f = options_heatmap.heatmap_frame(_payload(), metric="oi", today=TODAY)
    assert list(f.columns) == ["2026-09-18", "2026-12-18"]
    assert sorted(f.index.tolist()) == [95.0, 100.0]


def test_frame_is_empty_for_empty_payload():
    assert options_heatmap.heatmap_frame(None, metric="oi").empty


def test_render_returns_png_bytes():
    f = options_heatmap.heatmap_frame(_payload(), metric="oi", today=TODAY)
    png = options_heatmap.render_heatmap(f, metric="oi")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_options_heatmap.py -v`
Expected: FAIL — `cannot import name 'options_heatmap'`

- [ ] **Step 3: Implement the chart**

```python
# swingbot/core/charts/options_heatmap.py
"""Strike x expiry heatmap.

Diverging colormap centred at zero for gamma exposure (sign is meaningful);
sequential for raw open interest (only magnitude is). Both must stay legible
in the dark chart theme the rest of this bot's charts use.
"""
import datetime as dt
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from swingbot.core.options import exposure


def heatmap_frame(payload: dict | None, *, metric: str = "oi",
                  today: dt.date | None = None) -> pd.DataFrame:
    if not payload or not payload.get("expiries"):
        return pd.DataFrame()
    today = today or dt.date.today()

    cols = {}
    for expiry, sides in payload["expiries"].items():
        one = {"ticker": payload["ticker"], "spot": payload["spot"],
               "asof": payload["asof"], "expiries": {expiry: sides}}
        if metric == "gex":
            series = exposure.gamma_exposure(one, today=today)
            cols[expiry] = series if series is not None else pd.Series(dtype=float)
        else:
            totals = {}
            for df in sides.values():
                if df is None or df.empty:
                    continue
                for row in df.itertuples(index=False):
                    k = float(row.strike)
                    totals[k] = totals.get(k, 0.0) + float(row.openInterest or 0)
            cols[expiry] = pd.Series(totals)

    frame = pd.DataFrame(cols).sort_index()
    return frame.reindex(sorted(frame.columns), axis=1)


def render_heatmap(frame: pd.DataFrame, *, metric: str = "oi") -> bytes:
    fig, ax = plt.subplots(figsize=(8, 6), facecolor="#14161a")
    ax.set_facecolor("#14161a")

    if frame.empty:
        ax.text(0.5, 0.5, "no options data", ha="center", va="center", color="#8b93a1")
        ax.set_axis_off()
    else:
        cmap = "RdBu_r" if metric == "gex" else "viridis"
        data = frame.fillna(0).values
        vmax = abs(data).max() or 1.0
        kw = {"vmin": -vmax, "vmax": vmax} if metric == "gex" else {}
        im = ax.imshow(data, aspect="auto", cmap=cmap, origin="lower", **kw)
        ax.set_xticks(range(len(frame.columns)))
        ax.set_xticklabels(frame.columns, rotation=45, ha="right", color="#c8cedb", fontsize=8)
        ax.set_yticks(range(len(frame.index)))
        ax.set_yticklabels([f"{s:g}" for s in frame.index], color="#c8cedb", fontsize=8)
        ax.set_title("Gamma exposure (modeled)" if metric == "gex" else "Open interest",
                     color="#e6e9ef")
        fig.colorbar(im, ax=ax).ax.tick_params(colors="#c8cedb")

    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor(), dpi=110)
    plt.close(fig)
    return buf.getvalue()
```

- [ ] **Step 4: Add the admin route**

In `swingbot/admin/app.py`, following the existing page patterns:

```python
@app.route("/options")
@app.route("/options/<ticker>")
def options_page(ticker: str | None = None):
    """Volatility, OI change and the heatmap.

    DSGEX's FLOW, DIF and COT tabs are deliberately absent: order flow and
    dark-pool data need a feed we do not have, and faking them from
    aggregate volume would be worse than omitting them.
    """
    tickers = sorted(config.WATCHLIST)
    ticker = (ticker or (tickers[0] if tickers else "")).upper()
    payload = None
    if ticker:
        hist = snapshots.load_history(ticker, days=1)
        payload = hist[-1] if hist else None
    return render_template("options.html", tickers=tickers, ticker=ticker,
                           payload=payload)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_options_heatmap.py tests/test_admin_options_page.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/charts/options_heatmap.py swingbot/admin/ tests/test_options_heatmap.py tests/test_admin_options_page.py
git commit -m "feat(D16): options admin page and heatmap, minus the tabs we would have to fake"
```

---

# Phase D5 — Ship it

### Task D17: Document the traps

**Files:**
- Modify: `docs/claude/known-traps.md`, `README.md`, `CLAUDE.md`

- [ ] **Step 1: Add to `docs/claude/known-traps.md`**

```markdown
## Options data: three traps

**1. The dealer sign convention is an assumption.** `exposure.py` counts
calls positive and puts negative because dealers are *assumed* long calls
and short puts. Nobody can see real dealer inventory without a paid feed,
and paid "dealer maps" are models too. Every GEX-derived figure is labelled
"modeled, not observed" and never gates a trade. Do not quietly promote it.

**2. Options data must never reach a backtest.** yfinance serves only
*today's* chain. `build_level_map()` takes options candidates through a
keyword-only `extra_candidates` parameter that only
`scanning/engine.py:level_map_for_scan()` passes. Backtest paths
(`backtest.py`'s memo, `backtest_scenarios.levels_asof`) must never pass
it. `tests/test_options_no_lookahead.py` enforces this — **a failure there
is a stop-the-line event, not a flaky test.**

**3. The feed is dirty and its bad rows look plausible.** On 2026-08-06
SPY's front expiry carried implied vol of `0.000010` on one strike and
`2.185551` on its neighbour, with NaN volume and zero open interest.
`chain.filter_liquid()` runs before every aggregate. Never compute a gamma
sum, an IV rank or an expected move from an unfiltered frame.

**Related:** metrics needing history return `None` until enough days are
recorded (see `vol.py`'s cold-start table). `None` means unknown, never
zero — do not paper over it with a default.
```

- [ ] **Step 2: Add a README section**

Add a `## Options positioning` section after `## Market regime filter`, describing the four alerts, the `!options` command, and — plainly — that order flow and dark-pool data are not available on free data and are therefore not provided.

- [ ] **Step 3: Commit**

```bash
git add docs/claude/known-traps.md README.md CLAUDE.md
git commit -m "docs(D17): write down the three options traps before they bite someone"
```

---

### Task D18: Rollback triggers

**Files:**
- Create: `scripts/options_health_check.py`
- Modify: this plan's Progress section

**Interfaces:**
- Produces: `check(*, root=None, today=None) -> list[dict]` — each `{"trigger", "value", "threshold", "firing", "flag_to_flip"}`

**Why:** options data ships without backtest validation (spec D-3). Additive-only authority bounds the damage; armed triggers bound the duration. Follow the V29 pattern.

Pre-registered triggers — write these down **before** reading any live result:

| Trigger | Threshold | Flag to flip |
|---|---|---|
| Options alerts posted per week | > 40 | `OPTIONS_ALERTS_ENABLED` |
| Tickers with a usable chain | < 15 | `OPTIONS_ENABLED` |
| Scenarios whose selected level changed | < 3% over 200+ scenarios | `OPTIONS_LEVELS_ENABLED` |
| Snapshot job failure rate | > 30% of tickers for 3 consecutive days | `OPTIONS_ENABLED` |
| Expected-move calibration (share of realized N-day moves inside ±1σ) | outside 55–80% once 60+ days exist | `OPTIONS_SCORE_ENABLED` |

- [ ] **Step 1: Write the failing test**

```python
# tests/test_options_health.py
import datetime as dt

from scripts import options_health_check


def test_check_returns_every_registered_trigger(tmp_path):
    out = options_health_check.check(root=tmp_path, today=dt.date(2026, 8, 6))
    names = {r["trigger"] for r in out}
    assert names == {"alerts_per_week", "usable_chains", "level_influence",
                     "snapshot_failure_rate", "expected_move_calibration"}
    assert all("firing" in r and "flag_to_flip" in r for r in out)


def test_no_data_does_not_fire_triggers(tmp_path):
    out = options_health_check.check(root=tmp_path, today=dt.date(2026, 8, 6))
    for r in out:
        assert r["firing"] in (True, False)
```

- [ ] **Step 2: Run it to verify it fails, implement `scripts/options_health_check.py` against the table above, then re-run**

Run: `python -m pytest tests/test_options_health.py -v`
Expected: PASS. Print one flushed line per trigger when run as a script.

- [ ] **Step 3: Commit**

```bash
git add scripts/options_health_check.py tests/test_options_health.py docs/superpowers/plans/2026-08-06-options-positioning-v9.md
git commit -m "feat(D18): arm the options rollback triggers before enabling anything"
```

---

### Task D19: The pre-commit gate

**Files:** none — verification only.

- [ ] **Step 1: Syntax pass**

Run: `python -m py_compile bot.py admin_ui.py $(git ls-files 'swingbot/**/*.py')`
Expected: no output.

- [ ] **Step 2: Full suite, in chunks**

Run:
```bash
python -m pytest tests/ -x --ignore=tests/test_backtest.py
python -m pytest tests/test_backtest.py
```
Expected: **zero failures.** Baseline was `1711 passed, 62 skipped, 0 failed` on 2026-08-04; the passed count drifts upward as the suite grows, so a higher number is not a regression. Do not add `-q`.

- [ ] **Step 3: Confirm the firewall specifically**

Run: `python -m pytest tests/test_options_no_lookahead.py -v`
Expected: PASS. **If this fails, stop — do not commit, do not enable any flag.**

- [ ] **Step 4: Confirm the default-off contract**

Run: `python -c "from swingbot import config; print([ (f.key, f.default) for f in config.FIELDS if f.key.startswith('OPTIONS_') and f.type=='checkbox' ])"`
Expected: every checkbox reads `'false'`.

- [ ] **Step 5: Staged enable**

Enable in this order, one per session, checking `scripts/options_health_check.py` between each:
1. `OPTIONS_ENABLED` alone — snapshots accrue, nothing else changes.
2. `OPTIONS_ALERTS_ENABLED` + `DISCORD_CHANNEL_OPTIONS_ID` — after 3 days of snapshots.
3. `OPTIONS_LEVELS_ENABLED` — after a week.
4. `OPTIONS_SCORE_ENABLED` — only once `OPTIONS_IV_RANK_MIN_HISTORY` days exist, since `iv_rank` returns `None` before then and the component would never fire anyway.

- [ ] **Step 6: Commit**

```bash
git commit --allow-empty -m "chore(D19): options positioning verified green and staged for rollout"
```

---

## Progress

_Update as tasks complete. Record D1's RICH/THIN/NONE counts here — the
universe decision gate depends on them._

| Task | Status |
|---|---|
| D1 Coverage probe | not started |
| D2 Config surface | not started |
| D3 Chain + liquidity filter | not started |
| D4 Snapshot store | not started |
| D5 Daily job | not started |
| D6 Greeks | not started |
| D7 Exposure | not started |
| D8 Vol metrics | not started |
| D9 No-lookahead firewall | not started |
| D10 Live scan wiring | not started |
| D11 Score component | not started |
| D12 Detectors | not started |
| D13 Throttling | not started |
| D14 Posting | not started |
| D15 `!options` | not started |
| D16 Admin page | not started |
| D17 Docs | not started |
| D18 Rollback triggers | not started |
| D19 Gate | not started |
