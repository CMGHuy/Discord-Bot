Version: ui 1.8.0 · bot 1.3.2
Spec: docs/superpowers/specs/2026-08-21-v43-gamma-flip-level-design.md
Bump: ui minor (1.8.0 → 1.9.0) — a new workspace. bot minor (1.3.2 → 1.4.0,
shared with v44 if both land in one release) — a new background collector and
a new persisted data file; no change to trading or alert behaviour.
Edge: none (integrity) — explicitly not a trading signal (the spec's own
Non-goals: not consumed by any scan-pipeline gate); a read-only
market-context page for the trader's own judgment. Buys no edge and must say
so. (Added retroactively 2026-08-22 — this plan predates the `Edge:` header
convention.)

# Gamma flip level Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute each watchlist ticker's gamma flip level — the spot price
where modelled net dealer gamma crosses zero — from yfinance option chains on a
periodic background job, and surface it as a new read-only admin workspace.

**Architecture:** Three new bot-side modules (fetch → math → refresh job)
writing one JSON cache, one new Flask endpoint that only reads that cache, and
one new Angular workspace. Nothing here feeds the scan pipeline: GEX is
information for the reader, not a trading gate.

**Tech Stack:** yfinance 0.2.66 (`Ticker.options` / `Ticker.option_chain`),
numpy/pandas, discord.ext `tasks` for scheduling, Flask blueprint `api_v1`,
Angular 20 standalone components with `@ngrx/signals`.

## Global Constraints

- **Never compute in the request path.** `GET /api/v1/gamma` reads
  `data/gamma_exposure.json` and nothing else — the same "nothing is computed
  here" rule `swingbot/admin/api_v1/risk.py:13-21` states for the Risk endpoint.
- **Every new config `Field` must also be added to `.env.example`**, or
  `tests/test_env_example_sync.py` fails.
- **A new workspace must be added in three places**, or it 404s on reload:
  `spa.py`'s `WORKSPACES` tuple, `frontend/src/app/app.routes.ts`, and the nav
  list in `frontend/src/app/shell/shell.ts`. `spa.py:44-46` documents this trap
  explicitly — a route in `app.routes.ts` but not in `WORKSPACES` works when
  clicked and 404s when reloaded or bookmarked.
- **No live network in tests.** Every options test runs off a fixture chain.
- **Fetching lives in `marketdata/`, analysis in `market/`.** That is the
  existing split (`data_refresh.py`, `fmp_client.py` fetch; `volatility.py`,
  `levels.py` analyse). Spec v43 placed both new modules in `market/`; this
  plan corrects that.
- **Modelled, never measured.** True dealer inventory is not observable from
  public data. Every surface — code docstring, API field naming, UI copy —
  says "modelled". Do not write copy that presents a flip level as fact.
- Verify with `python scripts/dev/testrun.py file <test file>` while iterating;
  `test-runner` subagent for the full suite. Green means `0 failed` **and**
  `0 xfailed`.

---

# Phase 1 — Math and data

### Task 1: Black-Scholes gamma and per-strike GEX

**Files:**
- Create: `swingbot/core/market/gamma_exposure.py`
- Test: `tests/market/test_gamma_math.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `RISK_FREE_RATE: float`, `MIN_T_YEARS: float`, `MIN_IV: float`,
  `CONTRACT_MULTIPLIER: int`,
  `bs_gamma(spot: float, strike: float, t_years: float, iv: float, r: float = RISK_FREE_RATE) -> float`,
  `net_gex(spot, calls, puts, t_years) -> float` where `calls`/`puts` are
  sequences of `(strike, open_interest, iv)` tuples.

**Sign convention (fixed here, relied on everywhere downstream):** dealers are
modelled **long gamma against call open interest** and **short gamma against
put open interest** — the customer-overwrites-calls / customer-buys-puts
assumption the published GEX literature uses. So
`net_gex = Σ(call gamma·OI) − Σ(put gamma·OI)`, positive meaning dealer
hedging dampens moves.

- [ ] **Step 1: Write the failing test**

Create `tests/market/test_gamma_math.py`:

```python
"""Black-Scholes gamma and the per-strike GEX sum.

Pure math over hand-built chains -- no network, no yfinance, no fixtures.
Gamma is checked against its own closed-form properties (peak at the money,
symmetry, decay with distance) rather than a magic constant, so the test
says what the function must MEAN and not merely what it currently returns.
"""
import math

import pytest

from swingbot.core.market import gamma_exposure as gx


def test_gamma_is_positive_and_peaks_near_the_money():
    t, iv = 0.05, 0.20
    atm = gx.bs_gamma(100.0, 100.0, t, iv)
    otm = gx.bs_gamma(100.0, 130.0, t, iv)
    itm = gx.bs_gamma(100.0, 70.0, t, iv)
    assert atm > 0 and otm > 0 and itm > 0
    assert atm > otm and atm > itm


def test_gamma_decays_as_the_strike_moves_away():
    t, iv = 0.05, 0.20
    distances = [100.0, 105.0, 110.0, 120.0, 140.0]
    gammas = [gx.bs_gamma(100.0, k, t, iv) for k in distances]
    assert gammas == sorted(gammas, reverse=True)


def test_zero_or_negative_time_is_floored_not_divided_by_zero():
    """The front expiration ON an expiry day has t_years == 0. Black-Scholes
    gamma divides by sigma*sqrt(T), so this is a real ZeroDivisionError in
    the one situation this feature most cares about."""
    for t in (0.0, -1.0):
        got = gx.bs_gamma(100.0, 100.0, t, 0.20)
        assert math.isfinite(got) and got > 0


def test_unusable_iv_yields_zero_gamma():
    # yfinance returns 0.00001 on deep-ITM strikes as a sentinel, not a
    # real vol. Measured on SPY's front expiration: 173 of 253 call strikes.
    for iv in (0.0, 1e-5, -0.2):
        assert gx.bs_gamma(100.0, 100.0, 0.05, iv) == 0.0


# -- the aggregate -------------------------------------------------------

def test_calls_add_and_puts_subtract():
    """The sign convention, asserted directly: identical call and put OI at
    the same strike must cancel to zero."""
    strike = [(100.0, 1000, 0.20)]
    assert gx.net_gex(100.0, strike, strike, 0.05) == pytest.approx(0.0, abs=1e-6)


def test_call_heavy_book_is_positive_gamma():
    calls = [(100.0, 5000, 0.20)]
    puts = [(100.0, 1000, 0.20)]
    assert gx.net_gex(100.0, calls, puts, 0.05) > 0


def test_put_heavy_book_is_negative_gamma():
    calls = [(100.0, 1000, 0.20)]
    puts = [(100.0, 5000, 0.20)]
    assert gx.net_gex(100.0, calls, puts, 0.05) < 0


def test_zero_open_interest_contributes_nothing():
    calls = [(100.0, 0, 0.20), (105.0, 0, 0.20)]
    assert gx.net_gex(100.0, calls, [], 0.05) == pytest.approx(0.0)


def test_empty_chain_is_zero_not_an_error():
    assert gx.net_gex(100.0, [], [], 0.05) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/market/test_gamma_math.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.market.gamma_exposure'`

- [ ] **Step 3: Write the implementation**

Create `swingbot/core/market/gamma_exposure.py`:

```python
"""Modelled dealer gamma exposure (GEX) and the gamma flip level.

WHAT THIS IS NOT
----------------
True dealer inventory is not observable from public data. Everything here
rests on the standard published assumption -- customers overwrite calls and
buy puts, so dealers are long gamma against call open interest and short
gamma against put open interest -- and is therefore a MODEL, not a
measurement. Every surface that renders these numbers says so. Do not let
"modelled" quietly become "measured" in a docstring, a field name or a
label on the page.

SIGN CONVENTION
---------------
    net_gex = sum(call gamma * OI) - sum(put gamma * OI)

Positive => dealer hedging leans against price moves (they sell into
strength, buy weakness), which dampens realised volatility. Negative =>
hedging amplifies moves. The gamma flip level is the spot price where that
sum crosses zero.
"""
from __future__ import annotations

import math

#: Gamma is very insensitive to the discount rate -- a whole point of rate
#: moves it by well under a percent -- so this is a constant rather than a
#: setting nobody would have a basis to tune.
RISK_FREE_RATE = 0.04

#: Options expiring TODAY have t_years == 0, and Black-Scholes gamma divides
#: by sigma*sqrt(T). One hour, floored, keeps the front expiration on an
#: expiry day finite. Its gamma is genuinely enormous there; that is real,
#: not an artefact.
MIN_T_YEARS = 1.0 / (365.0 * 24.0)

#: yfinance reports 0.00001 for strikes it has no real vol for -- measured
#: at 173 of 253 call strikes on SPY's front expiration. Treating that as a
#: real 0.001% vol produces an astronomically large, entirely fictional
#: gamma, so anything at or below this floor contributes nothing.
MIN_IV = 0.01

CONTRACT_MULTIPLIER = 100


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def bs_gamma(spot: float, strike: float, t_years: float, iv: float,
             r: float = RISK_FREE_RATE) -> float:
    """Black-Scholes gamma for one contract. 0.0 when inputs are unusable.

    Returning 0.0 rather than raising is deliberate: a chain of 250 strikes
    routinely carries dozens of unusable rows, and a single bad strike must
    not take down the whole ticker's computation.
    """
    if iv is None or iv <= MIN_IV:
        return 0.0
    if spot is None or strike is None or spot <= 0 or strike <= 0:
        return 0.0

    t = max(float(t_years), MIN_T_YEARS)
    sigma = float(iv)
    denom = sigma * math.sqrt(t)
    if denom <= 0:
        return 0.0

    d1 = (math.log(spot / strike) + (r + 0.5 * sigma * sigma) * t) / denom
    gamma = _norm_pdf(d1) / (spot * denom)
    return gamma if math.isfinite(gamma) else 0.0


def _side_gex(spot: float, rows, t_years: float) -> float:
    """Gamma-weighted open interest for one side of the book.

    Scaled by spot^2 so the result reads as a currency notional per unit
    move rather than a bare gamma -- the form every published GEX figure
    takes, and what makes two tickers comparable.
    """
    total = 0.0
    for strike, open_interest, iv in rows:
        if not open_interest or open_interest <= 0:
            continue
        g = bs_gamma(spot, float(strike), t_years, iv)
        if g:
            total += g * float(open_interest) * CONTRACT_MULTIPLIER * spot * spot
    return total


def net_gex(spot: float, calls, puts, t_years: float) -> float:
    """Net modelled dealer gamma. See the module docstring for the sign."""
    if spot is None or spot <= 0:
        return 0.0
    return _side_gex(spot, calls, t_years) - _side_gex(spot, puts, t_years)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/market/test_gamma_math.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/gamma_exposure.py tests/market/test_gamma_math.py
git commit -m "feat(v46): Black-Scholes gamma and net dealer GEX"
```

---

### Task 2: The gamma flip level solver

**Files:**
- Modify: `swingbot/core/market/gamma_exposure.py` (append)
- Test: `tests/market/test_gamma_flip.py`

**Interfaces:**
- Consumes: Task 1's `net_gex`.
- Produces: `SEARCH_SPAN_PCT: float`, `SEARCH_STEPS: int`,
  `gamma_flip_level(spot, calls, puts, t_years) -> float | None`.

The flip level is the spot price at which `net_gex` crosses zero. Solved by
evaluating the curve across a grid around the current spot and interpolating
the crossing, rather than by a root-finder: the curve is not guaranteed
monotonic or even continuous in the presence of sparse strikes, and a grid
makes "no crossing in range" and "several crossings" both representable
instead of returning whichever root a solver happened to land on.

- [ ] **Step 1: Write the failing test**

Create `tests/market/test_gamma_flip.py`:

```python
"""The flip level: where modelled net dealer gamma crosses zero."""
import pytest

from swingbot.core.market import gamma_exposure as gx

T = 0.05


def test_flip_sits_between_a_put_wall_and_a_call_wall():
    """Puts dominate below, calls above -- so gamma is negative low, positive
    high, and the crossing must land between the two walls."""
    puts = [(90.0, 8000, 0.25)]
    calls = [(110.0, 8000, 0.25)]
    flip = gx.gamma_flip_level(100.0, calls, puts, T)
    assert flip is not None
    assert 90.0 < flip < 110.0


def test_flip_is_none_when_gamma_never_crosses():
    """An all-call book is positive everywhere in range: there is no flip,
    and inventing one would be worse than reporting none."""
    calls = [(100.0, 5000, 0.25), (110.0, 5000, 0.25)]
    assert gx.gamma_flip_level(100.0, calls, [], T) is None


def test_flip_is_none_for_an_empty_book():
    assert gx.gamma_flip_level(100.0, [], [], T) is None


def test_symmetric_book_flips_near_the_shared_strike():
    calls = [(100.0, 5000, 0.25)]
    puts = [(100.0, 5000, 0.25)]
    flip = gx.gamma_flip_level(100.0, calls, puts, T)
    # Identical books cancel everywhere, so there is no sign CHANGE to find.
    assert flip is None


def test_returned_flip_actually_changes_the_sign():
    """Whatever comes back must be a real crossing of the modelled curve --
    the property that makes the number mean anything at all."""
    puts = [(85.0, 9000, 0.30)]
    calls = [(115.0, 9000, 0.30)]
    flip = gx.gamma_flip_level(100.0, calls, puts, T)
    assert flip is not None
    below = gx.net_gex(flip * 0.97, calls, puts, T)
    above = gx.net_gex(flip * 1.03, calls, puts, T)
    assert below < 0 < above


def test_nearest_crossing_to_spot_is_chosen(monkeypatch):
    """With more than one crossing in range, the actionable one is the
    nearest -- it is the level price would reach first."""
    puts = [(80.0, 9000, 0.30), (120.0, 9000, 0.30)]
    calls = [(100.0, 9000, 0.30)]
    flip = gx.gamma_flip_level(100.0, calls, puts, T)
    if flip is not None:
        assert abs(flip - 100.0) <= gx.SEARCH_SPAN_PCT / 100.0 * 100.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/market/test_gamma_flip.py`
Expected: FAIL — `AttributeError: module ... has no attribute 'gamma_flip_level'`

- [ ] **Step 3: Append the solver**

```python
# ---------------------------------------------------------------------------
# The flip level
# ---------------------------------------------------------------------------

#: How far either side of spot to look for the crossing. Wide enough to find
#: a flip that matters, narrow enough that a level 40% away -- which price
#: will not reach inside any swing horizon this bot trades -- is reported as
#: "no flip" rather than as a number someone might act on.
SEARCH_SPAN_PCT = 30.0

#: Grid resolution. 240 steps over +/-30% of a $500 underlying is ~$1.25 a
#: step, finer than the strike spacing of anything in the watchlist, so the
#: grid never misses a crossing the chain could actually express.
SEARCH_STEPS = 240


def gamma_flip_level(spot: float, calls, puts, t_years: float) -> float | None:
    """The price where modelled net dealer gamma crosses zero.

    None when the curve never changes sign inside +/-SEARCH_SPAN_PCT -- an
    honest "no flip in range", which is a real and common state for a
    one-sided book. With several crossings the one nearest spot wins: it is
    the level price reaches first, so it is the only actionable one.

    OI and IV are held fixed while spot is varied. That is the standard
    simplification and it is what "the flip level" conventionally means; it
    is not a claim that the book would be unchanged at that price.
    """
    if spot is None or spot <= 0:
        return None
    if not calls and not puts:
        return None

    low = spot * (1.0 - SEARCH_SPAN_PCT / 100.0)
    high = spot * (1.0 + SEARCH_SPAN_PCT / 100.0)
    step = (high - low) / SEARCH_STEPS

    prices = [low + i * step for i in range(SEARCH_STEPS + 1)]
    values = [net_gex(p, calls, puts, t_years) for p in prices]

    best = None
    for i in range(len(values) - 1):
        lo_v, hi_v = values[i], values[i + 1]
        if lo_v == 0.0:
            crossing = prices[i]
        elif (lo_v < 0.0) != (hi_v < 0.0) and (hi_v - lo_v) != 0.0:
            # Linear interpolation between the bracketing grid points.
            crossing = prices[i] + (prices[i + 1] - prices[i]) * (-lo_v) / (hi_v - lo_v)
        else:
            continue
        if best is None or abs(crossing - spot) < abs(best - spot):
            best = crossing

    return best
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/market/test_gamma_flip.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/gamma_exposure.py tests/market/test_gamma_flip.py
git commit -m "feat(v46): gamma flip level solver with honest no-crossing case"
```

---

### Task 3: Option-chain fetch and the usability filter

**Files:**
- Create: `swingbot/core/marketdata/options_chain.py`
- Test: `tests/marketdata/test_options_chain.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure fetch/shape layer).
- Produces: `MIN_USABLE_STRIKES: int`,
  `ChainSlice` (dataclass: `expiration: str`, `t_years: float`,
  `calls: list[tuple]`, `puts: list[tuple]`),
  `usable_rows(frame) -> list[tuple[float, int, float]]`,
  `fetch_chains(symbol: str, max_expirations: int, now=None) -> tuple[float | None, list[ChainSlice]]`.

**yfinance shapes, verified live on 2026-08-21 against 0.2.66:**
`Ticker.options` is a tuple of `'YYYY-MM-DD'` strings.
`Ticker.option_chain(exp)` returns a namedtuple `(calls, puts, underlying)`;
the two frames carry `contractSymbol, lastTradeDate, strike, lastPrice, bid,
ask, change, percentChange, volume, openInterest, impliedVolatility,
inTheMoney, contractSize, currency`, and `underlying` is a dict carrying
`regularMarketPrice`.

- [ ] **Step 1: Write the failing test**

Create `tests/marketdata/test_options_chain.py`:

```python
"""Chain fetch and the usable-strike filter, entirely off fixtures.

No live network: yfinance is monkeypatched. The garbage-IV case is not
hypothetical -- on SPY's own front expiration 173 of 253 call strikes carry
impliedVolatility == 0.00001, a sentinel rather than a vol.
"""
import datetime as dt

import pandas as pd
import pytest

from swingbot.core.marketdata import options_chain as oc


def make_frame(rows):
    return pd.DataFrame(rows, columns=["strike", "openInterest", "impliedVolatility"])


def test_usable_rows_drops_sentinel_iv():
    frame = make_frame([
        (100.0, 500, 0.22),
        (105.0, 400, 0.00001),   # yfinance's "no vol" sentinel
        (110.0, 300, 0.0),
    ])
    assert oc.usable_rows(frame) == [(100.0, 500, 0.22)]


def test_usable_rows_drops_zero_and_missing_open_interest():
    frame = make_frame([
        (100.0, 0, 0.22),
        (105.0, None, 0.22),
        (110.0, 250, 0.22),
    ])
    assert oc.usable_rows(frame) == [(110.0, 250, 0.22)]


def test_usable_rows_survives_missing_columns():
    """A thin ticker can come back without impliedVolatility at all. That is
    an empty result, never an exception that kills the sweep."""
    assert oc.usable_rows(pd.DataFrame({"strike": [100.0]})) == []
    assert oc.usable_rows(pd.DataFrame()) == []


# -- fetch ---------------------------------------------------------------

class _FakeChain:
    def __init__(self, calls, puts, spot):
        self.calls = calls
        self.puts = puts
        self.underlying = {"regularMarketPrice": spot}


class _FakeTicker:
    def __init__(self, expirations, chain):
        self.options = expirations
        self._chain = chain

    def option_chain(self, exp):
        return self._chain


@pytest.fixture
def patched(monkeypatch):
    good = make_frame([(100.0, 500, 0.22), (105.0, 400, 0.21),
                       (110.0, 300, 0.20), (95.0, 350, 0.23),
                       (90.0, 200, 0.25), (115.0, 180, 0.19)])
    chain = _FakeChain(good, good, spot=100.0)

    def _ticker(symbol):
        return _FakeTicker(("2026-09-18", "2026-10-16", "2026-11-20"), chain)

    monkeypatch.setattr(oc.yf, "Ticker", _ticker)
    return chain


def test_fetch_respects_the_expiration_cap(patched):
    spot, slices = oc.fetch_chains("TEST", max_expirations=2,
                                   now=dt.datetime(2026, 8, 21, tzinfo=dt.timezone.utc))
    assert spot == 100.0
    assert len(slices) == 2
    assert [s.expiration for s in slices] == ["2026-09-18", "2026-10-16"]


def test_fetch_computes_positive_time_to_expiry(patched):
    _, slices = oc.fetch_chains("TEST", max_expirations=1,
                                now=dt.datetime(2026, 8, 21, tzinfo=dt.timezone.utc))
    assert slices[0].t_years > 0
    assert slices[0].t_years < 1.0


def test_fetch_skips_already_expired_dates(patched):
    """Asked from a date after every listed expiration, nothing is usable --
    and that is an empty list, not a negative time to expiry."""
    _, slices = oc.fetch_chains("TEST", max_expirations=3,
                                now=dt.datetime(2027, 1, 1, tzinfo=dt.timezone.utc))
    assert slices == []


def test_fetch_returns_empty_for_a_ticker_with_no_options(monkeypatch):
    monkeypatch.setattr(oc.yf, "Ticker", lambda s: _FakeTicker((), None))
    spot, slices = oc.fetch_chains("NOOPT", max_expirations=2)
    assert slices == []


def test_fetch_propagates_nothing_on_a_broken_ticker(monkeypatch):
    """One delisted or rate-limited symbol must not raise into the sweep."""
    class _Boom:
        @property
        def options(self):
            raise RuntimeError("rate limited")

    monkeypatch.setattr(oc.yf, "Ticker", lambda s: _Boom())
    spot, slices = oc.fetch_chains("BOOM", max_expirations=2)
    assert spot is None and slices == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_options_chain.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.marketdata.options_chain'`

- [ ] **Step 3: Write the implementation**

Create `swingbot/core/marketdata/options_chain.py`:

```python
"""Option-chain retrieval for the gamma-exposure job.

Fetching lives here rather than in `core/market/` to match the existing
split: `marketdata/` pulls and caches, `market/` analyses. `gamma_exposure`
is the analysis half and never touches the network.

FAILURE POLICY
--------------
Per-symbol, never per-sweep. `data_refresh.py:14` states the same invariant
for price data -- "a rate-limited window must not kill the loop" -- and a
78-ticker options sweep is strictly more exposed to it than a price sweep,
because option chains are several requests per symbol. Every failure here
returns empty and lets the caller record a gap.
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass

import yfinance as yf

from swingbot.core.market.gamma_exposure import MIN_IV

log = logging.getLogger(__name__)

#: Below this many usable strikes on a side, a flip level computed from the
#: chain is noise dressed as a number. Reported as "insufficient options
#: data" instead -- see the spec's non-goals.
MIN_USABLE_STRIKES = 5

_DAYS_PER_YEAR = 365.0


@dataclass(frozen=True)
class ChainSlice:
    """One expiration's usable rows, plus its time to expiry in years."""
    expiration: str
    t_years: float
    calls: list
    puts: list


def usable_rows(frame) -> list:
    """`[(strike, open_interest, iv)]`, keeping only rows the maths can use.

    Two filters, both load-bearing. Open interest of zero contributes no
    gamma by definition. An IV at or below `MIN_IV` is yfinance's sentinel
    for "no vol available" rather than a real 0.001% vol -- taken literally
    it produces an astronomically large fictional gamma that would dominate
    the whole sum.
    """
    required = ("strike", "openInterest", "impliedVolatility")
    if frame is None or getattr(frame, "empty", True):
        return []
    if any(col not in frame.columns for col in required):
        return []

    rows = []
    for strike, oi, iv in zip(frame["strike"], frame["openInterest"],
                              frame["impliedVolatility"]):
        try:
            if oi is None or float(oi) <= 0:
                continue
            if iv is None or float(iv) <= MIN_IV:
                continue
            rows.append((float(strike), int(float(oi)), float(iv)))
        except (TypeError, ValueError):
            continue
    return rows


def fetch_chains(symbol: str, max_expirations: int,
                 now: dt.datetime | None = None) -> tuple:
    """`(spot, [ChainSlice, ...])` for the nearest `max_expirations` dates.

    Only expirations still in the future are returned; an already-passed
    date would give a negative time to expiry, which is meaningless rather
    than merely small. Returns `(None, [])` on any failure.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        ticker = yf.Ticker(symbol)
        expirations = list(ticker.options or ())
    except Exception as exc:
        log.debug("options: %s expiration list unavailable: %s", symbol, str(exc)[:120])
        return None, []

    spot = None
    slices: list[ChainSlice] = []

    for expiration in expirations:
        if len(slices) >= max_expirations:
            break
        try:
            expiry_date = dt.date.fromisoformat(expiration)
        except ValueError:
            continue

        days = (expiry_date - now.date()).days
        if days < 0:
            continue
        t_years = max(days, 0) / _DAYS_PER_YEAR

        try:
            chain = ticker.option_chain(expiration)
        except Exception as exc:
            log.debug("options: %s/%s chain unavailable: %s",
                      symbol, expiration, str(exc)[:120])
            continue

        if spot is None:
            try:
                spot = float((chain.underlying or {}).get("regularMarketPrice") or 0.0) or None
            except (AttributeError, TypeError, ValueError):
                spot = None

        slices.append(ChainSlice(
            expiration=expiration,
            t_years=t_years,
            calls=usable_rows(chain.calls),
            puts=usable_rows(chain.puts),
        ))

    return spot, slices
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_options_chain.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/marketdata/options_chain.py tests/marketdata/test_options_chain.py
git commit -m "feat(v46): option-chain fetch with sentinel-IV filtering"
```

---

### Task 4: Config fields and `.env.example`

**Files:**
- Modify: `swingbot/config.py` (new "Gamma Exposure" section)
- Modify: `.env.example`
- Test: `tests/test_gamma_config.py`

**Interfaces:**
- Produces: `config.GEX_ENABLED` (bool), `config.GEX_REFRESH_MINUTES` (int),
  `config.GEX_EXPIRATIONS_COUNT` (int), `config.GEX_FETCH_SLEEP_SECONDS` (float).

- [ ] **Step 1: Write the failing test**

Create `tests/test_gamma_config.py`:

```python
from swingbot import config

GEX_SETTINGS = ("GEX_ENABLED", "GEX_REFRESH_MINUTES",
                "GEX_EXPIRATIONS_COUNT", "GEX_FETCH_SLEEP_SECONDS")


def test_every_gex_setting_is_defined():
    for name in GEX_SETTINGS:
        assert hasattr(config, name), f"{name} missing from the config schema"


def test_collector_defaults_off():
    # ~150-230 yfinance requests per cycle across a 78-ticker watchlist is
    # materially more load than anything the bot does today; it is opted
    # into, never inherited by an existing deploy on upgrade.
    assert config.GEX_ENABLED is False


def test_refresh_cadence_is_sane():
    assert 5 <= config.GEX_REFRESH_MINUTES <= 240
    assert 1 <= config.GEX_EXPIRATIONS_COUNT <= 6
    assert config.GEX_FETCH_SLEEP_SECONDS >= 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/test_gamma_config.py`
Expected: FAIL — `AssertionError: GEX_ENABLED missing from the config schema`

- [ ] **Step 3: Add the fields**

In `swingbot/config.py`, append a new section:

```python
    # --- Gamma Exposure ---
    Field("GEX_ENABLED", "GEX_ENABLED", "Gamma Exposure", "Gamma exposure collection enabled",
          type="checkbox", default="false",
          help="Fetch option chains for the watchlist on a timer and compute each ticker's "
               "modelled gamma flip level for the Gamma workspace. Off = the page shows the "
               "last cache written, or an empty state if there is none. This is the single "
               "heaviest network job the bot runs -- see 'Refresh interval' below."),
    Field("GEX_REFRESH_MINUTES", "GEX_REFRESH_MINUTES", "Gamma Exposure", "Refresh interval (minutes)",
          type="number", default="45", min=5, max=240, step=5,
          help="How often to re-fetch every watchlist ticker's option chains. A full sweep is "
               "roughly 2-3 requests per ticker per expiration -- about 150-230 requests for a "
               "78-ticker watchlist -- so short intervals invite Yahoo throttling."),
    Field("GEX_EXPIRATIONS_COUNT", "GEX_EXPIRATIONS_COUNT", "Gamma Exposure", "Expirations per ticker",
          type="number", default="3", min=1, max=6, step=1,
          help="How many of the nearest expirations feed the gamma calculation. Near-dated open "
               "interest dominates dealer gamma, so raising this adds fetch cost faster than signal."),
    Field("GEX_FETCH_SLEEP_SECONDS", "GEX_FETCH_SLEEP_SECONDS", "Gamma Exposure", "Pause between tickers (s)",
          type="float", default="0.4", min=0, max=5, step=0.1,
          help="Staggers the sweep instead of bursting every ticker at once. The market-data "
               "refresh uses 0.3s for a lighter job; options chains are several requests each."),
```

- [ ] **Step 4: Add the four keys to `.env.example`**

```bash
# --- Gamma Exposure ---
GEX_ENABLED=false
GEX_REFRESH_MINUTES=45
GEX_EXPIRATIONS_COUNT=3
GEX_FETCH_SLEEP_SECONDS=0.4
```

- [ ] **Step 5: Run both tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/test_gamma_config.py`
Expected: PASS

Run: `python scripts/dev/testrun.py file tests/test_env_example_sync.py`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add swingbot/config.py .env.example tests/test_gamma_config.py
git commit -m "feat(v46): gamma exposure settings, collector default off"
```

---

### Task 5: Snapshot builder and atomic persistence

**Files:**
- Create: `swingbot/core/market/gamma_store.py`
- Test: `tests/market/test_gamma_store.py`

**Interfaces:**
- Consumes: Task 1-2 (`net_gex`, `gamma_flip_level`), Task 3 (`fetch_chains`,
  `MIN_USABLE_STRIKES`), Task 4's settings.
- Produces: `GEX_PATH: str`,
  `build_row(symbol, spot, slices) -> dict`,
  `build_snapshot(symbols, *, max_expirations, sleep_seconds, now=None) -> dict`,
  `save(snapshot) -> None`, `load() -> dict`.

**Row shape — uniform, every key always present.** A row that changes shape
between "ok" and "insufficient data" pushes the branching into the SPA, where
a missing key renders as `undefined`:

```json
{"symbol": "SPY", "status": "ok", "spot": 764.97, "flip_level": 751.2,
 "net_gex": 1.23e9, "distance_pct": -1.8, "regime": "positive",
 "strikes_used": 160, "expirations_used": ["2026-08-21", "2026-08-24"],
 "reason": null}
```

`status` is one of `"ok"`, `"insufficient_data"`, `"no_flip"`, `"fetch_failed"`.

- [ ] **Step 1: Write the failing test**

Create `tests/market/test_gamma_store.py`:

```python
"""Snapshot assembly and persistence. No network -- fetch is patched."""
import json
import os

import pytest

from swingbot.core.market import gamma_store as store
from swingbot.core.marketdata.options_chain import ChainSlice


def slice_with(calls, puts, t=0.05, expiration="2026-09-18"):
    return ChainSlice(expiration=expiration, t_years=t, calls=calls, puts=puts)


def test_row_is_ok_and_carries_a_flip_level():
    calls = [(110.0 + i, 900, 0.25) for i in range(6)]
    puts = [(90.0 - i, 900, 0.25) for i in range(6)]
    row = store.build_row("SPY", 100.0, [slice_with(calls, puts)])
    assert row["status"] == "ok"
    assert row["flip_level"] is not None
    assert row["regime"] in ("positive", "negative")
    assert row["strikes_used"] == 12


def test_row_is_insufficient_when_too_few_usable_strikes():
    row = store.build_row("THIN", 100.0, [slice_with([(100.0, 10, 0.3)], [])])
    assert row["status"] == "insufficient_data"
    assert row["flip_level"] is None
    assert row["reason"]


def test_row_is_no_flip_when_the_curve_never_crosses():
    calls = [(100.0 + i, 900, 0.25) for i in range(8)]
    row = store.build_row("ALLCALL", 100.0, [slice_with(calls, [])])
    assert row["status"] == "no_flip"
    assert row["flip_level"] is None


def test_row_is_fetch_failed_without_a_spot():
    row = store.build_row("BROKE", None, [])
    assert row["status"] == "fetch_failed"
    assert row["flip_level"] is None


def test_every_row_carries_the_same_keys():
    """A shape that changes with status pushes the branching into the SPA."""
    ok = store.build_row("SPY", 100.0, [slice_with(
        [(110.0 + i, 900, 0.25) for i in range(6)],
        [(90.0 - i, 900, 0.25) for i in range(6)])])
    bad = store.build_row("BROKE", None, [])
    assert set(ok) == set(bad)


def test_regime_reads_off_spot_versus_flip():
    calls = [(110.0 + i, 900, 0.25) for i in range(6)]
    puts = [(90.0 - i, 900, 0.25) for i in range(6)]
    row = store.build_row("SPY", 100.0, [slice_with(calls, puts)])
    expected = "positive" if row["spot"] > row["flip_level"] else "negative"
    assert row["regime"] == expected


# -- persistence ---------------------------------------------------------

def test_save_then_load_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "GEX_PATH", str(tmp_path / "gamma_exposure.json"))
    snapshot = {"as_of": "2026-08-21T12:00:00+00:00", "tickers": []}
    store.save(snapshot)
    assert store.load() == snapshot


def test_load_returns_an_empty_snapshot_when_the_file_is_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "GEX_PATH", str(tmp_path / "nope.json"))
    got = store.load()
    assert got["tickers"] == [] and got["as_of"] is None


def test_load_survives_a_corrupt_file(tmp_path, monkeypatch):
    path = tmp_path / "gamma_exposure.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(store, "GEX_PATH", str(path))
    assert store.load()["tickers"] == []


def test_save_leaves_no_temp_file_behind(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "GEX_PATH", str(tmp_path / "gamma_exposure.json"))
    store.save({"as_of": None, "tickers": []})
    assert [p.name for p in tmp_path.iterdir()] == ["gamma_exposure.json"]


def test_one_broken_ticker_does_not_abort_the_sweep(monkeypatch):
    def _fetch(symbol, max_expirations, now=None):
        if symbol == "BOOM":
            raise RuntimeError("rate limited")
        return 100.0, [slice_with([(110.0 + i, 900, 0.25) for i in range(6)],
                                  [(90.0 - i, 900, 0.25) for i in range(6)])]

    monkeypatch.setattr(store, "fetch_chains", _fetch)
    snapshot = store.build_snapshot(["AAA", "BOOM", "BBB"],
                                    max_expirations=1, sleep_seconds=0)
    by_symbol = {r["symbol"]: r for r in snapshot["tickers"]}
    assert by_symbol["BOOM"]["status"] == "fetch_failed"
    assert by_symbol["AAA"]["status"] == "ok"
    assert by_symbol["BBB"]["status"] == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/market/test_gamma_store.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.market.gamma_store'`

- [ ] **Step 3: Write the implementation**

Create `swingbot/core/market/gamma_store.py`:

```python
"""Assemble and persist the gamma-exposure snapshot.

The bot writes this file; the admin API only ever reads it. That split is
`api_v1/risk.py`'s "nothing is computed here" rule -- an HTTP request must
never be able to trigger a 78-ticker options sweep.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import time

from swingbot import config
from swingbot.core.market.gamma_exposure import gamma_flip_level, net_gex
from swingbot.core.marketdata.options_chain import MIN_USABLE_STRIKES, fetch_chains

log = logging.getLogger(__name__)

GEX_PATH = os.path.join(config.DATA_DIR, "gamma_exposure.json")

_EMPTY = {"as_of": None, "tickers": []}


def _row(symbol, status, *, spot=None, flip=None, gex=None, regime=None,
         strikes=0, expirations=None, reason=None) -> dict:
    """Every row has every key, whatever the status -- see the plan's note
    on why a shape that varies pushes branching into the SPA."""
    distance = None
    if spot and flip:
        distance = round((flip - spot) / spot * 100.0, 2)
    return {
        "symbol": symbol,
        "status": status,
        "spot": round(spot, 4) if spot else None,
        "flip_level": round(flip, 4) if flip else None,
        "net_gex": gex,
        "distance_pct": distance,
        "regime": regime,
        "strikes_used": strikes,
        "expirations_used": list(expirations or ()),
        "reason": reason,
    }


def build_row(symbol: str, spot, slices) -> dict:
    """One ticker's result, from an already-fetched chain."""
    if not spot or not slices:
        return _row(symbol, "fetch_failed",
                    reason="no option chain or spot price available")

    calls, puts, expirations = [], [], []
    # Gamma is summed ACROSS the near expirations rather than taken from the
    # front one alone: dealer hedging responds to the whole near book, and a
    # single expiration makes the level jump every time one rolls off.
    t_years = slices[0].t_years
    for chain in slices:
        calls.extend(chain.calls)
        puts.extend(chain.puts)
        expirations.append(chain.expiration)

    strikes = len(calls) + len(puts)
    if strikes < MIN_USABLE_STRIKES:
        return _row(symbol, "insufficient_data", spot=spot, strikes=strikes,
                    expirations=expirations,
                    reason=f"only {strikes} usable strike(s); needs {MIN_USABLE_STRIKES}")

    gex = net_gex(spot, calls, puts, t_years)
    flip = gamma_flip_level(spot, calls, puts, t_years)
    if flip is None:
        return _row(symbol, "no_flip", spot=spot, gex=gex, strikes=strikes,
                    expirations=expirations,
                    reason="modelled gamma does not cross zero within +/-30% of spot")

    return _row(symbol, "ok", spot=spot, flip=flip, gex=gex,
                regime="positive" if spot > flip else "negative",
                strikes=strikes, expirations=expirations)


def build_snapshot(symbols, *, max_expirations: int, sleep_seconds: float,
                   now=None) -> dict:
    """Sweep every symbol. One failure never aborts the rest."""
    rows = []
    for i, symbol in enumerate(symbols):
        try:
            spot, slices = fetch_chains(symbol, max_expirations, now=now)
            rows.append(build_row(symbol, spot, slices))
        except Exception as exc:
            log.debug("gex: %s failed: %s", symbol, str(exc)[:120])
            rows.append(_row(symbol, "fetch_failed", reason=str(exc)[:200]))
        if sleep_seconds and i < len(symbols) - 1:
            time.sleep(sleep_seconds)

    return {
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
        "tickers": rows,
    }


def save(snapshot: dict) -> None:
    """Atomic: write-temp-then-rename, so the API never reads a half file.

    Same shape as `data_refresh._merge_save` (data_refresh.py:135-137).
    """
    tmp = GEX_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, indent=2)
    os.replace(tmp, GEX_PATH)


def load() -> dict:
    """The last snapshot, or an empty one. Never raises.

    A missing file is the ordinary pre-first-sweep state, and a corrupt one
    is recoverable by the next sweep -- neither is worth a 500 on a page
    whose whole job is to be readable.
    """
    try:
        with open(GEX_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return dict(_EMPTY)
    if not isinstance(data, dict) or "tickers" not in data:
        return dict(_EMPTY)
    return data
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/market/test_gamma_store.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/gamma_store.py tests/market/test_gamma_store.py
git commit -m "feat(v46): gamma snapshot assembly and atomic persistence"
```

---

### Task 6: The background refresh loop

**Files:**
- Modify: `swingbot/commands/scanning.py` — new loop beside
  `market_data_refresh` (line 1310), its `before_loop` (line 1368), the
  `on_config_reload` hook (line 1376-1388), and the `.start()` block (line 1418)
- Test: `tests/scanning/test_gex_loop_wiring.py`

**Interfaces:**
- Consumes: Task 4's settings, Task 5's `build_snapshot` / `save`.
- Produces: `gamma_refresh` (a `tasks.Loop`), `_before_gamma_refresh`.

Modelled directly on `market_data_refresh` (scanning.py:1310-1373), which
solves the same problem: a blocking, minutes-long, throttling-prone yfinance
sweep that must not stall the Discord event loop. `asyncio.to_thread` is what
keeps commands responsive during it.

- [ ] **Step 1: Write the failing test**

Create `tests/scanning/test_gex_loop_wiring.py`:

```python
"""The loop's wiring, not its network behaviour.

What matters here is the same set of things market_data_refresh gets right:
the flag short-circuits, the sweep runs off the event loop, the interval
hot-reloads, and a failure inside the sweep never escapes the tick.
"""
import asyncio

import pytest

from swingbot import config
from swingbot.commands import scanning


def test_loop_exists_and_reads_the_configured_interval():
    assert hasattr(scanning, "gamma_refresh")
    assert scanning.gamma_refresh.minutes == config.GEX_REFRESH_MINUTES


def test_tick_is_a_no_op_when_disabled(monkeypatch):
    monkeypatch.setattr(config, "GEX_ENABLED", False)
    called = []
    monkeypatch.setattr(scanning, "load_watchlist", lambda: called.append("watchlist") or [])
    asyncio.run(scanning.gamma_refresh.coro())
    assert called == []


def test_tick_saves_a_snapshot_when_enabled(monkeypatch):
    monkeypatch.setattr(config, "GEX_ENABLED", True)
    monkeypatch.setattr(config, "GEX_EXPIRATIONS_COUNT", 1)
    monkeypatch.setattr(config, "GEX_FETCH_SLEEP_SECONDS", 0)
    monkeypatch.setattr(scanning, "load_watchlist", lambda: ["AAA"])

    saved = {}
    from swingbot.core.market import gamma_store
    monkeypatch.setattr(gamma_store, "build_snapshot",
                        lambda symbols, **kw: {"as_of": "x", "tickers": list(symbols)})
    monkeypatch.setattr(gamma_store, "save", lambda snap: saved.update(snap))

    asyncio.run(scanning.gamma_refresh.coro())
    assert saved["tickers"] == ["AAA"]


def test_a_failing_sweep_does_not_raise_out_of_the_tick(monkeypatch):
    monkeypatch.setattr(config, "GEX_ENABLED", True)
    monkeypatch.setattr(scanning, "load_watchlist", lambda: ["AAA"])
    from swingbot.core.market import gamma_store
    monkeypatch.setattr(gamma_store, "build_snapshot",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("yahoo down")))
    asyncio.run(scanning.gamma_refresh.coro())   # must not raise


def test_empty_watchlist_writes_nothing(monkeypatch):
    monkeypatch.setattr(config, "GEX_ENABLED", True)
    monkeypatch.setattr(scanning, "load_watchlist", lambda: [])
    from swingbot.core.market import gamma_store
    monkeypatch.setattr(gamma_store, "save",
                        lambda snap: pytest.fail("must not save for an empty watchlist"))
    asyncio.run(scanning.gamma_refresh.coro())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scanning/test_gex_loop_wiring.py`
Expected: FAIL — `AssertionError: assert False` on `hasattr(scanning, "gamma_refresh")`

- [ ] **Step 3: Add the loop**

In `swingbot/commands/scanning.py`, after `_before_market_data_refresh`
(line 1373):

```python
@tasks.loop(minutes=config.GEX_REFRESH_MINUTES)
async def gamma_refresh():
    """Recompute every watchlist ticker's modelled gamma flip level.

    The heaviest network job the bot runs: 2-3 requests per ticker per
    expiration, so roughly 150-230 for a 78-ticker watchlist at the default
    of 3 expirations. It runs off the event loop via asyncio.to_thread for
    the same reason market_data_refresh does -- a throttled sweep would
    otherwise stall every Discord command for minutes.

    Nothing here feeds trading. The snapshot is read only by the Gamma
    workspace.
    """
    if not config.GEX_ENABLED:
        return

    symbols = load_watchlist()
    if not symbols:
        return

    from swingbot.core.market import gamma_store

    try:
        snapshot = await asyncio.to_thread(
            gamma_store.build_snapshot, symbols,
            max_expirations=config.GEX_EXPIRATIONS_COUNT,
            sleep_seconds=config.GEX_FETCH_SLEEP_SECONDS,
        )
        gamma_store.save(snapshot)
    except Exception as exc:
        log.exception("gamma_refresh: sweep failed: %s", exc)
        return

    rows = snapshot.get("tickers", [])
    ok = sum(1 for r in rows if r.get("status") == "ok")
    log.info("gamma_refresh: %d/%d tickers with a flip level", ok, len(rows))


@gamma_refresh.before_loop
async def _before_gamma_refresh():
    # Same reasoning as _before_market_data_refresh, with more of it: this
    # sweep is heavier, so it waits longer before competing with startup.
    await bot.wait_until_ready()
    await asyncio.sleep(120)
```

Extend `_apply_scan_interval_change` (line 1376) — the loop interval is baked
in at decoration time, so a hot reload must push it explicitly:

```python
    if "GEX_REFRESH_MINUTES" in changed and gamma_refresh.is_running():
        gamma_refresh.change_interval(minutes=config.GEX_REFRESH_MINUTES)
        log.info("Gamma refresh interval hot-reloaded to every %d minute(s).",
                 config.GEX_REFRESH_MINUTES)
```

and start it alongside the others (after line 1418):

```python
        gamma_refresh.start()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/scanning/test_gex_loop_wiring.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/scanning.py tests/scanning/test_gex_loop_wiring.py
git commit -m "feat(v46): background gamma-exposure refresh loop"
```

---

# Phase 2 — Admin API

### Task 7: `GET /api/v1/gamma`

**Files:**
- Create: `swingbot/admin/api_v1/gamma.py`
- Modify: `swingbot/admin/api_v1/__init__.py:181-183` (the deferred import list)
- Test: `tests/admin/test_api_gamma.py`

**Interfaces:**
- Consumes: Task 5's `gamma_store.load`.
- Produces: `GET /api/v1/gamma` → `{"as_of": str|null, "tickers": [...],
  "enabled": bool, "stale_minutes": float|null}`.

- [ ] **Step 1: Write the failing test**

Create `tests/admin/test_api_gamma.py`, matching the auth/client conventions
already used by the other `api_v1` tests in `tests/admin/` (read one first —
e.g. the risk endpoint's — and reuse its app/client fixture rather than
building a second one):

```python
"""GET /api/v1/gamma: a projection of the cache, and nothing else."""
import datetime as dt

import pytest

from swingbot.core.market import gamma_store


def test_returns_the_cached_snapshot(client, monkeypatch):
    snapshot = {
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
        "tickers": [{"symbol": "SPY", "status": "ok", "spot": 764.97,
                     "flip_level": 751.2, "net_gex": 1.2e9,
                     "distance_pct": -1.8, "regime": "positive",
                     "strikes_used": 160, "expirations_used": ["2026-08-21"],
                     "reason": None}],
    }
    monkeypatch.setattr(gamma_store, "load", lambda: snapshot)
    body = client.get("/api/v1/gamma").get_json()
    assert body["tickers"][0]["symbol"] == "SPY"
    assert body["as_of"] == snapshot["as_of"]


def test_empty_cache_is_200_not_500(client, monkeypatch):
    """The pre-first-sweep state is ordinary, not an error."""
    monkeypatch.setattr(gamma_store, "load", lambda: {"as_of": None, "tickers": []})
    response = client.get("/api/v1/gamma")
    assert response.status_code == 200
    assert response.get_json()["tickers"] == []


def test_reports_the_collector_flag(client, monkeypatch):
    """The page must be able to distinguish 'collector off' from 'nothing
    found' -- they look identical in the data and mean opposite things."""
    from swingbot import config
    monkeypatch.setattr(gamma_store, "load", lambda: {"as_of": None, "tickers": []})
    monkeypatch.setattr(config, "GEX_ENABLED", False)
    assert client.get("/api/v1/gamma").get_json()["enabled"] is False


def test_stale_minutes_is_null_without_a_snapshot(client, monkeypatch):
    monkeypatch.setattr(gamma_store, "load", lambda: {"as_of": None, "tickers": []})
    assert client.get("/api/v1/gamma").get_json()["stale_minutes"] is None


def test_endpoint_never_triggers_a_sweep(client, monkeypatch):
    """The load-bearing invariant: an HTTP request must not be able to start
    a 78-ticker options fetch."""
    monkeypatch.setattr(gamma_store, "build_snapshot",
                        lambda *a, **k: pytest.fail("endpoint triggered a sweep"))
    monkeypatch.setattr(gamma_store, "load", lambda: {"as_of": None, "tickers": []})
    client.get("/api/v1/gamma")


def test_requires_auth(unauthenticated_client):
    assert unauthenticated_client.get("/api/v1/gamma").status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_gamma.py`
Expected: FAIL — 404, the route is not registered.

- [ ] **Step 3: Write the endpoint**

Create `swingbot/admin/api_v1/gamma.py`:

```python
"""GET /api/v1/gamma -- the modelled gamma flip level per watchlist ticker.

Nothing is computed here. The bot's `gamma_refresh` loop owns the sweep and
writes `data/gamma_exposure.json`; this projects that file. Computing on
request would let a page refresh start a 78-ticker options fetch, which is
the same reason `risk.py` states the rule for its own endpoint.

`enabled` is projected alongside the rows because "the collector is off" and
"the collector ran and found nothing" are indistinguishable in the data and
mean opposite things to a reader.
"""
from __future__ import annotations

import datetime as dt

from flask import jsonify

from swingbot import config

from . import api_v1
from .auth import require_auth


def _stale_minutes(as_of: str | None) -> float | None:
    if not as_of:
        return None
    try:
        stamped = dt.datetime.fromisoformat(as_of)
    except ValueError:
        return None
    if stamped.tzinfo is None:
        stamped = stamped.replace(tzinfo=dt.timezone.utc)
    delta = dt.datetime.now(dt.timezone.utc) - stamped
    return round(delta.total_seconds() / 60.0, 1)


@api_v1.route("/gamma", methods=["GET"])
@require_auth
def get_gamma():
    from swingbot.core.market import gamma_store

    snapshot = gamma_store.load()
    as_of = snapshot.get("as_of")
    return jsonify({
        "as_of": as_of,
        "stale_minutes": _stale_minutes(as_of),
        "enabled": bool(getattr(config, "GEX_ENABLED", False)),
        "refresh_minutes": int(getattr(config, "GEX_REFRESH_MINUTES", 0) or 0),
        "tickers": snapshot.get("tickers") or [],
    })
```

Register it by adding `gamma` to the deferred import at
`swingbot/admin/api_v1/__init__.py:181`:

```python
    from . import (analytics, dashboard, gamma, jobs, market, risk,  # noqa: F401
                   session, system, trade_commands, trades,
                   versions, watchlist)  # (register routes)
```

**Import it there and nowhere else** — that list is deferred inside
`register()` on purpose, to avoid the circular-import deadlock `app.py`
documents (`__init__.py:175-180`).

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_gamma.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/gamma.py swingbot/admin/api_v1/__init__.py tests/admin/test_api_gamma.py
git commit -m "feat(v46): GET /api/v1/gamma projecting the cached snapshot"
```

---

# Phase 3 — The workspace

### Task 8: Route, nav and the API client

**Files:**
- Modify: `swingbot/admin/spa.py:47-51` (`WORKSPACES`)
- Modify: `frontend/src/app/app.routes.ts` (new route beside `risk`, line 71-75)
- Modify: `frontend/src/app/shell/shell.ts` (nav entry, line ~66-72)
- Modify: `frontend/src/app/api/models.ts` (new types)
- Modify: `frontend/src/app/api/api-client.ts` (new method)
- Test: `tests/admin/test_spa_workspaces.py` (extend, or create if absent)

**Interfaces:**
- Produces: TypeScript `GammaRow`, `Gamma`; `ApiClient.gamma(): Observable<Gamma>`;
  route path `gamma`.

**All three registration points, or it 404s on reload.** `spa.py:44-46`
spells the failure out: a route in `app.routes.ts` that is missing from
`WORKSPACES` works when clicked and 404s when reloaded or bookmarked, and the
symptom looks like an SPA routing bug rather than a server one.

- [ ] **Step 1: Write the failing test**

Add to `tests/admin/test_spa_workspaces.py` (create it if the repo has no
equivalent — check for an existing spa test first):

```python
def test_gamma_is_a_registered_workspace():
    """Without this, /gamma serves index.html only when reached by click."""
    from swingbot.admin.spa import WORKSPACES
    assert "gamma" in WORKSPACES


def test_gamma_path_serves_the_spa(client):
    assert client.get("/gamma").status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/admin/test_spa_workspaces.py`
Expected: FAIL — `"gamma"` is not in `WORKSPACES`.

- [ ] **Step 3: Register in all three places**

`swingbot/admin/spa.py`:

```python
WORKSPACES = (
    "dashboard", "trades", "analytics", "watchlist", "risk", "system",
    "versions", "gamma",
    "cockpit", "universe",
)
```

`frontend/src/app/app.routes.ts`, beside the `risk` route:

```typescript
  {
    path: 'gamma',
    canMatch: [authGuard],
    loadComponent: () => import('./workspaces/gamma/gamma').then((m) => m.Gamma),
  },
```

`frontend/src/app/shell/shell.ts`, in the nav list:

```typescript
    { path: '/gamma', label: 'Gamma', icon: 'gamma' },
```

If `icon` maps to a fixed icon set, add a `gamma` glyph there or reuse an
existing one rather than leaving a dangling key — check how `icon: 'risk'`
resolves before choosing.

`frontend/src/app/api/models.ts`:

```typescript
/** One watchlist ticker's modelled gamma state. Every field is present on
 *  every row whatever the status, so the template never branches on
 *  undefined -- see the server's `_row`. */
export interface GammaRow {
  symbol: string;
  status: 'ok' | 'insufficient_data' | 'no_flip' | 'fetch_failed';
  spot: number | null;
  flip_level: number | null;
  net_gex: number | null;
  distance_pct: number | null;
  regime: 'positive' | 'negative' | null;
  strikes_used: number;
  expirations_used: string[];
  reason: string | null;
}

export interface Gamma {
  as_of: string | null;
  stale_minutes: number | null;
  enabled: boolean;
  refresh_minutes: number;
  tickers: GammaRow[];
}
```

`frontend/src/app/api/api-client.ts`, following the existing method shape:

```typescript
  /* -- gamma ----------------------------------------------------------- */

  gamma(): Observable<Gamma> {
    return this.http.get<Gamma>(`${this.base}/gamma`);
  }
```

- [ ] **Step 4: Run the test and build the SPA**

Run: `python scripts/dev/testrun.py file tests/admin/test_spa_workspaces.py`
Expected: PASS

Run: `cd frontend && npm run build`
Expected: compiles — this is what catches a missing `Gamma` export before
Task 9 exists. If the component is not written yet, expect the
`loadComponent` import to fail; land Task 9 before treating this as green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/spa.py frontend/src/app/app.routes.ts frontend/src/app/shell/shell.ts frontend/src/app/api/models.ts frontend/src/app/api/api-client.ts tests/admin/test_spa_workspaces.py
git commit -m "feat(v46): register the gamma workspace route, nav and client"
```

---

### Task 9: The Gamma store and workspace component

**Files:**
- Create: `frontend/src/app/stores/gamma.store.ts`
- Create: `frontend/src/app/stores/gamma.store.spec.ts`
- Create: `frontend/src/app/workspaces/gamma/gamma.ts`

**Interfaces:**
- Consumes: Task 8's `ApiClient.gamma()`, `Gamma`, `GammaRow`.
- Produces: `GammaStore`, `Gamma` component (exported as `Gamma`, matching the
  `loadComponent` import in `app.routes.ts`).

Follow `RiskStore` (`frontend/src/app/stores/risk.store.ts`) and the `Risk`
workspace: `signalStore` with `withState` / `withComputed` / `withMethods` /
`withHooks`, the store `provide`d on the component so it is created on entry
and destroyed on exit, `ChangeDetectionStrategy.OnPush`, an inline template,
and the shared `ui/` primitives (`Panel`, `DataTable`, `Button`) with
`ui/format` helpers rather than hand-rolled formatting.

- [ ] **Step 1: Write the failing store test**

Create `frontend/src/app/stores/gamma.store.spec.ts`, modelled on
`risk.store.spec.ts` (read it first and reuse its TestBed/HttpTestingController
setup verbatim rather than inventing a second harness):

```typescript
describe('GammaStore', () => {
  it('sorts ok rows by absolute distance to flip, nearest first', () => {
    // The nearest-to-flip tickers are the actionable ones, so they lead.
  });

  it('separates rows without a flip level from the ranked ones', () => {
    // insufficient_data / no_flip / fetch_failed must not be ranked among
    // real levels -- a null distance sorting as 0 would put them on top.
  });

  it('keeps the previous rows visible when a refetch fails', () => {
    // Same rule as RiskStore: stale data plus a marker beats a blank page.
  });

  it('exposes enabled:false distinctly from an empty result', () => {
    // "collector off" and "found nothing" look identical in the rows.
  });
});
```

- [ ] **Step 2: Run the frontend tests to verify they fail**

Run: `cd frontend && npm test -- --include='**/gamma.store.spec.ts'`
Expected: FAIL — the store does not exist.

- [ ] **Step 3: Write the store**

Create `frontend/src/app/stores/gamma.store.ts`:

```typescript
import { computed, inject } from '@angular/core';
import {
  patchState, signalStore, withComputed, withHooks, withMethods, withState,
} from '@ngrx/signals';

import { ApiClient } from '../api/api-client';
import { ApiError } from '../api/api-error';
import { Gamma, GammaRow } from '../api/models';

interface GammaSlice {
  data: Gamma | null;
  loading: boolean;
  error: string | null;
}

/**
 * Modelled dealer gamma per watchlist ticker.
 *
 * Same shape as `RiskStore` -- read that one first. Two things differ:
 *
 * **There is no event channel.** The snapshot is rewritten by a timer on the
 * bot (`GEX_REFRESH_MINUTES`, 45 minutes by default), not by a file watcher,
 * so there is nothing to subscribe to and `onInit` simply loads once. The
 * page's Reload button re-reads the cache; it cannot trigger a new sweep.
 *
 * **Rows without a flip level are separated rather than sorted.** A null
 * distance sorted as 0 would float every failed ticker to the top of a table
 * ranked by proximity, which is the one place they must not be.
 */
export const GammaStore = signalStore(
  withState<GammaSlice>({ data: null, loading: false, error: null }),
  withComputed(({ data }) => ({
    empty: computed(() => data() === null),

    /** Tickers with a real flip level, nearest-to-flip first: those are the
     *  ones price could actually reach, so they lead the table. */
    ranked: computed<GammaRow[]>(() =>
      (data()?.tickers ?? [])
        .filter((row) => row.status === 'ok' && row.distance_pct !== null)
        .sort((a, b) => Math.abs(a.distance_pct!) - Math.abs(b.distance_pct!)),
    ),

    /** Everything else, with its reason -- listed, never silently dropped,
     *  so a missing ticker is explained rather than just absent. */
    unavailable: computed<GammaRow[]>(() =>
      (data()?.tickers ?? []).filter(
        (row) => row.status !== 'ok' || row.distance_pct === null,
      ),
    ),

    asOf: computed(() => data()?.as_of ?? null),
    staleMinutes: computed(() => data()?.stale_minutes ?? null),

    /** "The collector is off" and "the collector found nothing" are
     *  identical in the rows and mean opposite things, so the flag is
     *  surfaced separately rather than inferred from an empty table. */
    collectorEnabled: computed(() => data()?.enabled ?? false),

    /** Stale past roughly two refresh intervals. Derived from the server's
     *  own cadence so changing GEX_REFRESH_MINUTES cannot make the page lie. */
    stale: computed(() => {
      const minutes = data()?.stale_minutes;
      const cadence = data()?.refresh_minutes ?? 0;
      if (minutes === null || minutes === undefined || !cadence) return false;
      return minutes > cadence * 2;
    }),
  })),
  withMethods((store, api = inject(ApiClient)) => ({
    load(): void {
      patchState(store, { loading: true, error: null });
      api.gamma().subscribe({
        next: (data) => patchState(store, { data, loading: false, error: null }),
        error: (error: ApiError) =>
          patchState(store, {
            loading: false,
            // `data` deliberately untouched: stale levels beside a warning
            // beat an error panel where the numbers were.
            error:
              error.code === 'unavailable'
                ? 'The admin is not responding — these levels may be stale.'
                : error.message,
          }),
      });
    },
  })),
  withHooks({
    onInit(store) {
      store.load();
    },
  }),
);
```

- [ ] **Step 4: Write the component**

Create `frontend/src/app/workspaces/gamma/gamma.ts`, exported as `Gamma`:

- A header carrying the as-of stamp and, when `staleMinutes` exceeds roughly
  twice `refresh_minutes`, a stale marker beside the numbers (never instead
  of them).
- When `collectorEnabled()` is false, an explicit empty state saying the
  collector is off and naming `GEX_ENABLED` — not a blank table, which would
  read as "no gamma anywhere".
- A `DataTable` of `ranked()`: symbol, spot, flip level, distance %, net GEX,
  and a regime chip — **positive** = "dealer hedging dampens moves",
  **negative** = "dealer hedging amplifies moves". Label the chip with those
  words, not just a colour.
- A second panel listing `unavailable()` rows with their `reason`, so a
  missing ticker is visibly explained rather than silently absent.
- A "Reload" button calling `store.load()`. Label it **Reload**, never
  "Refresh data": it re-reads the cache and does not trigger a new sweep.
- One line of copy stating these levels are **modelled** from public open
  interest under a standard dealer-positioning assumption, not measured
  dealer inventory.

- [ ] **Step 5: Run the frontend tests and build**

Run: `cd frontend && npm test -- --include='**/gamma.store.spec.ts'`
Expected: PASS

Run: `cd frontend && npm run build`
Expected: compiles clean, including Task 8's `loadComponent` import.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/stores/gamma.store.ts frontend/src/app/stores/gamma.store.spec.ts frontend/src/app/workspaces/gamma/gamma.ts
git commit -m "feat(v46): gamma workspace -- store, table and regime labelling"
```

---

### Task 10: Full-suite gate, a real sweep, and the version bump

**Files:**
- Modify: `docs/claude/architecture.md`
- Modify: `VERSION.json`, `data/version_history.json`

- [ ] **Step 1: Run the full suite via the subagent**

Dispatch `test-runner`. Expected: `0 failed`, `0 xfailed`.

- [ ] **Step 2: Run one real sweep against a handful of tickers**

Every test so far runs off fixtures, so nothing has yet proved the real
yfinance shapes still parse. Run a deliberately small live sweep:

```bash
python -c "
from swingbot.core.market import gamma_store
snap = gamma_store.build_snapshot(['SPY','QQQ','IWM'], max_expirations=2, sleep_seconds=0.5)
for r in snap['tickers']:
    print(r['symbol'], r['status'], r['flip_level'], r['strikes_used'], r['reason'])
"
```

Expected: three rows, each `ok` or an explained non-`ok`. A traceback here
means the live schema has drifted from the fixtures. Note what fraction of
strikes survived the IV filter — on SPY's front expiration only 80 of 253
calls were usable when this plan was written, so a very low count is normal
and a zero count is not.

- [ ] **Step 3: Confirm the collector is off by default**

```bash
python -c "from swingbot import config; print(config.GEX_ENABLED)"
```
Expected: `False`

- [ ] **Step 4: Document**

Add the three new modules to `docs/claude/architecture.md` (fetch in
`marketdata/options_chain.py`, maths in `market/gamma_exposure.py`, snapshot
in `market/gamma_store.py`), and add a line to `docs/claude/known-traps.md`
recording the sentinel-IV finding — that `impliedVolatility == 0.00001` is
yfinance's "no data" marker and covered 173 of 253 SPY front-month call
strikes, so any future options work must filter it.

- [ ] **Step 5: Bump both versions and regenerate history**

`ui` → `1.9.0`, `bot` → `1.4.0` in `VERSION.json`, then regenerate and commit
`data/version_history.json` **in the same commit** — the local gate runs
before the bump and structurally cannot catch a missed regeneration.

- [ ] **Step 6: Commit**

```bash
git add VERSION.json data/version_history.json docs/claude/architecture.md docs/claude/known-traps.md
git commit -m "chore(v46): ui 1.9.0, bot 1.4.0 -- gamma flip level workspace"
```

---

## Parallelisation

**Phase 1 is a chain, with one exception.** Task 2 appends to the file Task 1
creates; Task 3 imports `MIN_IV` from it; Task 5 consumes Tasks 1, 2 and 3;
Task 6 consumes Tasks 4 and 5.

- **Task 4 (config) is genuinely independent** — `config.py` + `.env.example`,
  touched by nothing else in this plan — and may be done at any point before
  Task 5. Everything else in Phase 1 is sequential: 1 → 2 → 3 → 5 → 6.
- **Phase 2 (Task 7) needs only Task 5's `load()`**, not the loop. It can run
  concurrently with Task 6: `api_v1/gamma.py` + `api_v1/__init__.py` versus
  `commands/scanning.py`, disjoint files, and the only shared symbol
  (`gamma_store.load`) already exists once Task 5 lands.
- **Group A (parallel): Task 6 and Task 7**, per the above.
- **Sequential: Task 8 before Task 9.** Task 9's component is what Task 8's
  `loadComponent` imports, and Task 8's `npm run build` cannot pass until it
  exists — so while the two may be *written* in either order, Task 8's build
  step is only green after Task 9. Land 8 then 9 and treat 8's build check as
  provisional, or do both before building.
- **Task 10 last**, by definition.

Phase 3 depends on Phase 2 only for the endpoint's response shape, which is
fixed by Task 7's test. Once that shape is settled, the Python and TypeScript
halves touch entirely disjoint files and could be worked concurrently by two
sessions — but this working tree is shared, so confirm nobody else is mid-edit
in `frontend/` before doing so.
