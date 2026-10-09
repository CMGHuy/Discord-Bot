# v144 Next-session plans: Part 3, the outlook run, its loops, close-out

> Part of [`_0-index`](2026-10-09-v144-next-session-plans_0-index.md), which holds the header, the global constraints, the parallelisation map and the open-point answer. Read those first; they apply to every task here.

# Phase 4 — The outlook lane

### Task V144-10: Digest, card and wrap-up rendering

**Files:**
- Modify: `swingbot/core/presentation/kinds.py` (two `Kind` members after `DEEP_SCAN`)
- Create: `swingbot/core/scanning/outlook_types.py`, `swingbot/core/scanning/outlook_context.py`, `swingbot/core/scanning/outlook_embeds.py`
- Test: `tests/scanning/test_outlook_embeds.py`

**Interfaces:**
- Consumes: `session_expiry.cancel_reason` (V144-3); `TradePlanV2.cancel_reason_message` (V144-1); `analytics.partials.is_filled`; `presentation.kinds.side_word`; `scanning.regime.get_market_regime`.
- Produces:
  - `Kind.OUTLOOK` (SYSTEM, "OUTLOOK", 🌙) and `Kind.OUTLOOK_WRAPUP` (SYSTEM, "OUTLOOK WRAP-UP", 🌅).
  - `outlook_types.OutlookLine(ticker, direction, strategy, entry, stop, target, risk_dollars=None, reason=None)` (frozen).
  - `outlook_types.OutlookResult(run_date, target, bar_date=None, unavailable=None, regime_lines, plans, watch, near_misses, skipped, alerts)`.
  - `outlook_context`: `weekly_phrase(daily)`, `hourly_phrase(hourly, direction)`, `context_line(daily, hourly, direction) -> str | None`, `regime_line(symbol, daily)`, `regime_lines(frames: dict) -> list[str]`.
  - `outlook_embeds`: `WATCH_NOTE`, `CONTEXT_FIELD`, `day_label(day)`, `digest_text(result) -> str`, `card_badge(valid_session)`, `decorate_card(embed, *, valid_session, context_line) -> None`, `count_line(plans) -> str`, `wrapup_text(day, plans) -> str`.

- [ ] **Step 1: Invoke `alert-surface`.**

- [ ] **Step 2: Write the failing tests**

```python
# tests/scanning/test_outlook_embeds.py
"""v144: the outlook's words -- digest, card decoration, wrap-up. Pure rendering."""
import datetime as dt

import discord
import pandas as pd

from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from swingbot.core.presentation import kinds
from swingbot.core.presentation.kinds import Family, Kind
from swingbot.core.scanning import outlook_context as ctx
from swingbot.core.scanning import outlook_embeds as oe
from swingbot.core.scanning.outlook_types import OutlookLine, OutlookResult
from tests.planning.test_plan_engine_model import _plan

SUNDAY, MONDAY = dt.date(2026, 10, 11), dt.date(2026, 10, 12)


def _line(ticker="AAPL", **kw):
    base = dict(ticker=ticker, direction="bullish", strategy="Break & Retest",
                entry=102.0, stop=100.5, target=106.0)
    base.update(kw)
    return OutlookLine(**base)


def test_the_two_kinds_are_system_notices():
    assert Kind.OUTLOOK.family is Family.SYSTEM and Kind.OUTLOOK_WRAPUP.family is Family.SYSTEM
    assert kinds.badge(Kind.OUTLOOK) == "🌙" and Kind.OUTLOOK_WRAPUP.label == "OUTLOOK WRAP-UP"


def test_no_session_tomorrow():
    text = oe.digest_text(OutlookResult(run_date=dt.date(2027, 3, 25), target=None))
    assert text == "No NYSE session tomorrow (Friday 2027-03-26) — no outlook issued."


def test_unavailable_says_why_and_nothing_else():
    text = oe.digest_text(OutlookResult(run_date=SUNDAY, target=MONDAY, unavailable="no closed SPY daily bar"))
    assert text == "**Outlook for Monday 2026-10-12**\nOutlook unavailable: no closed SPY daily bar"


def test_an_empty_run_is_one_line():
    text = oe.digest_text(OutlookResult(run_date=SUNDAY, target=MONDAY, regime_lines=["SPY: Bullish"]))
    assert text == "**Outlook for Monday 2026-10-12** — no plans, no watch names, no near-misses."


def test_a_full_digest_lists_every_section():
    result = OutlookResult(
        run_date=SUNDAY, target=MONDAY, regime_lines=["SPY: Bullish (SPY +4.1% vs rising 200EMA)"],
        plans=[_line(risk_dollars=120.0), _line("MSFT", risk_dollars=None)],
        watch=[_line("NVDA", strategy="RSI")],
        near_misses=[_line("AMD", reason="risk_cap (stop 2.6% from entry)")],
        skipped=["TSLA"])
    assert oe.digest_text(result).splitlines() == [
        "**Outlook for Monday 2026-10-12**",
        "SPY: Bullish (SPY +4.1% vs rising 200EMA)",
        "**Plans (2)**",
        "• AAPL LONG · Break & Retest · entry 102.00 stop 100.50 target 106.00 · risk $120",
        "• MSFT LONG · Break & Retest · entry 102.00 stop 100.50 target 106.00 · risk n/a",
        f"**Watch — {oe.WATCH_NOTE} (1)**",
        "• NVDA LONG · RSI · entry 102.00 stop 100.50 target 106.00",
        "**Near-misses (1)**",
        "• AMD LONG · Break & Retest · risk_cap (stop 2.6% from entry)",
        "**Skipped — outlook plan already open (1)**: TSLA",
    ]


def test_the_card_gets_its_badge_and_context():
    embed = discord.Embed(description="headline")
    oe.decorate_card(embed, valid_session=MONDAY, context_line="Weekly: above 20w MA, higher lows")
    assert embed.description == "🌙 **Outlook · valid Monday 2026-10-12 only**\nheadline"
    assert [(f.name, f.value) for f in embed.fields] == [
        (oe.CONTEXT_FIELD, "Weekly: above 20w MA, higher lows")]
    bare = discord.Embed(description="x")
    oe.decorate_card(bare, valid_session=MONDAY, context_line=None)
    assert bare.fields == []


def _outlook(plan_id, **kw):
    return _plan(plan_id=plan_id, entry_type="stop_entry", origin="next_session",
                 valid_session=MONDAY.isoformat(), **kw)


def test_the_wrapup_lists_fills_and_reasons_and_counts():
    filled = _outlook("o1", ticker="AAPL")
    filled.entry_price = 102.05
    record_transition(filled, PlanStatus.ACTIVE, reason="stop_entry_fill", at="t")
    missed = _outlook("o2", ticker="MSFT", direction="bearish")
    record_transition(missed, PlanStatus.CANCELLED, reason="never_triggered", at="t")
    missed.cancel_reason_message = "Low 98.60 stopped 0.6% (0.4 ATR) short of the 98.00 trigger"
    broke = _outlook("o3", ticker="NVDA")
    record_transition(broke, PlanStatus.CANCELLED, reason="never_triggered", at="t")
    broke.cancel_reason_message = "High 101.40 stopped 0.6% short of the 102.00 trigger"
    assert oe.wrapup_text(MONDAY, [filled, missed, broke]).splitlines() == [
        "**Outlook wrap-up · Monday 2026-10-12**",
        "• AAPL LONG — filled at 102.05",
        "• MSFT SHORT — cancelled (never_triggered): Low 98.60 stopped 0.6% (0.4 ATR) short of the 98.00 trigger",
        "• NVDA LONG — cancelled (never_triggered): High 101.40 stopped 0.6% short of the 102.00 trigger",
        "3 issued · 1 filled · 2 cancelled (never_triggered ×2)",
    ]


def test_count_line_with_nothing_cancelled():
    assert oe.count_line([]) == "0 issued · 0 filled · 0 cancelled"


def _daily(weeks=30, rising=True):
    days = pd.bdate_range(end=pd.Timestamp("2026-10-09"), periods=weeks * 5)
    step = 0.2 if rising else -0.2
    close = pd.Series([100 + step * i for i in range(len(days))], index=days)
    return pd.DataFrame({"Open": close, "High": close + 0.5, "Low": close - 0.5, "Close": close,
                         "Volume": 1e6})


def test_the_weekly_phrase_reads_the_20_week_ma_and_the_last_two_lows():
    assert ctx.weekly_phrase(_daily()) == "Weekly: above 20w MA, higher lows"
    assert ctx.weekly_phrase(_daily(rising=False)) == "Weekly: below 20w MA, lower lows"
    assert ctx.weekly_phrase(_daily(weeks=10)) is None


def test_the_hourly_phrase_and_the_joined_context_line():
    hourly = pd.DataFrame({"High": [101.0] * 7, "Low": [99.1] + [99.5] * 6, "Close": [100.0] * 7})
    assert ctx.hourly_phrase(hourly, "bullish") == "Hourly: holding 1h swing low 99.10"
    assert ctx.hourly_phrase(hourly, "bearish") == "Hourly: below 1h swing high 101.00"
    assert ctx.hourly_phrase(hourly.head(3), "bullish") is None
    assert ctx.context_line(_daily(), hourly, "bullish") == \
        "Weekly: above 20w MA, higher lows · Hourly: holding 1h swing low 99.10"
    assert ctx.context_line(None, None, "bullish") is None


def test_regime_lines_skip_a_symbol_without_enough_history():
    lines = ctx.regime_lines({"SPY": _daily(weeks=50), "QQQ": _daily(weeks=10)})
    assert len(lines) == 1 and lines[0].startswith("SPY: Bullish")
    assert lines[0].endswith("· Weekly: above 20w MA, higher lows")
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_outlook_embeds.py`
Expected: FAIL with `ImportError` (no `outlook_embeds`) and `AttributeError: OUTLOOK`.

- [ ] **Step 4: The two kinds.** In `swingbot/core/presentation/kinds.py`, after `DEEP_SCAN = KindSpec(Family.SYSTEM, "WEEKEND DEEP SCAN", emoji="🔭")`, add:

```python
    OUTLOOK = KindSpec(Family.SYSTEM, "OUTLOOK", emoji="🌙")                 # v144: 23:30 digest
    OUTLOOK_WRAPUP = KindSpec(Family.SYSTEM, "OUTLOOK WRAP-UP", emoji="🌅")  # v144: after D's close
```

- [ ] **Step 5: Create `swingbot/core/scanning/outlook_types.py`**

```python
"""v144: the outlook run's result, as plain data for the renderers and posters."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass(frozen=True)
class OutlookLine:
    """One digest row: an issued plan, a watch name or a near-miss."""
    ticker: str
    direction: str
    strategy: str
    entry: float
    stop: float
    target: float
    risk_dollars: float | None = None    # issued plans only
    reason: str | None = None            # near-misses only


@dataclass
class OutlookResult:
    run_date: dt.date                    # the Berlin date of the 23:30 slot
    target: dt.date | None               # the session D the plans are valid for; None = no session tomorrow
    bar_date: dt.date | None = None      # the closed bar the scan read (Sunday -> Friday)
    unavailable: str | None = None       # set = nothing was issued, and this says why
    regime_lines: list[str] = field(default_factory=list)
    plans: list[OutlookLine] = field(default_factory=list)
    watch: list[OutlookLine] = field(default_factory=list)
    near_misses: list[OutlookLine] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    alerts: list[tuple] = field(default_factory=list)   # (embed, chart_path, plan, simple_embed)
```

- [ ] **Step 6: Create `swingbot/core/scanning/outlook_context.py`**

```python
"""v144: the display-only context on an outlook card and the digest's regime
lines. Weekly and hourly price action is shown, never used as a gate: a gate
would be a new filter, and a new filter needs a SCREEN-PASS first."""
from __future__ import annotations

import pandas as pd

from swingbot.core.scanning.regime import get_market_regime

_WEEKLY_MA = 20
_HOURLY_SWING_BARS = 7


def _weekly(daily) -> pd.DataFrame | None:
    if daily is None or len(daily) == 0:
        return None
    frame = daily[["High", "Low", "Close"]].copy()
    frame.index = pd.DatetimeIndex(frame.index)
    weekly = frame.resample("W-FRI").agg({"High": "max", "Low": "min", "Close": "last"}).dropna()
    return weekly if len(weekly) > _WEEKLY_MA else None


def weekly_phrase(daily) -> str | None:
    weekly = _weekly(daily)
    if weekly is None:
        return None
    ma = float(weekly["Close"].rolling(_WEEKLY_MA).mean().iloc[-1])
    side = "above" if float(weekly["Close"].iloc[-1]) > ma else "below"
    lows = "higher lows" if float(weekly["Low"].iloc[-1]) > float(weekly["Low"].iloc[-2]) else "lower lows"
    return f"Weekly: {side} 20w MA, {lows}"


def hourly_phrase(hourly, direction: str) -> str | None:
    if hourly is None or len(hourly) < _HOURLY_SWING_BARS:
        return None
    recent = hourly.tail(_HOURLY_SWING_BARS)
    close = float(recent["Close"].iloc[-1])
    if direction == "bullish":
        level = float(recent["Low"].min())
        return f"Hourly: {'holding' if close > level else 'at'} 1h swing low {level:.2f}"
    level = float(recent["High"].max())
    return f"Hourly: {'below' if close < level else 'at'} 1h swing high {level:.2f}"


def context_line(daily, hourly, direction: str) -> str | None:
    parts = [part for part in (weekly_phrase(daily), hourly_phrase(hourly, direction)) if part]
    return " · ".join(parts) or None


def regime_line(symbol: str, daily) -> str | None:
    if daily is None or len(daily) == 0:
        return None
    try:
        label = get_market_regime(daily, symbol).label
    except Exception:
        return None                       # too little history for the 200EMA regime
    weekly = weekly_phrase(daily)
    return f"{symbol}: {label}" + (f" · {weekly}" if weekly else "")


def regime_lines(frames: dict) -> list[str]:
    return [line for line in (regime_line(symbol, frame) for symbol, frame in frames.items()) if line]
```

- [ ] **Step 7: Create `swingbot/core/scanning/outlook_embeds.py`**

```python
"""v144: the outlook's words -- the 23:30 digest, an outlook card's badge and
context field, and the wrap-up. Pure: no bot import; commands/scanning/outlook.py
turns the text into SYSTEM embeds and posts it."""
from __future__ import annotations

import datetime as dt
from collections import Counter

from swingbot.core.analytics.partials import is_filled
from swingbot.core.planning.plan_types import PlanStatus
from swingbot.core.planning.session_expiry import cancel_reason
from swingbot.core.presentation.kinds import side_word

OUTLOOK_BADGE = "🌙"
WATCH_NOTE = "market entry: fills at the signal close, no resting order for tomorrow"
CONTEXT_FIELD = "Context (display only)"


def day_label(day: dt.date) -> str:
    return f"{day:%A} {day.isoformat()}"


def _head(line) -> str:
    return f"{line.ticker} {side_word(line.direction)} · {line.strategy}"


def _levels(line) -> str:
    return f"entry {line.entry:.2f} stop {line.stop:.2f} target {line.target:.2f}"


def _plan_row(line) -> str:
    risk = "risk n/a" if line.risk_dollars is None else f"risk ${line.risk_dollars:,.0f}"
    return f"{_head(line)} · {_levels(line)} · {risk}"


def _watch_row(line) -> str:
    return f"{_head(line)} · {_levels(line)}"


def _near_row(line) -> str:
    return f"{_head(line)} · {line.reason}"


def _sections(result) -> list[str]:
    blocks = (("Plans", result.plans, _plan_row),
              (f"Watch — {WATCH_NOTE}", result.watch, _watch_row),
              ("Near-misses", result.near_misses, _near_row))
    lines: list[str] = []
    for title, rows, render in blocks:
        if rows:
            lines.append(f"**{title} ({len(rows)})**")
            lines.extend(f"• {render(row)}" for row in rows)
    if result.skipped:
        lines.append(f"**Skipped — outlook plan already open ({len(result.skipped)})**: "
                     f"{', '.join(result.skipped)}")
    return lines


def _is_empty(result) -> bool:
    return not (result.plans or result.watch or result.near_misses or result.skipped)


def digest_text(result) -> str:
    """The 23:30 digest. Always says something, so silence never means failure."""
    if result.target is None:
        tomorrow = result.run_date + dt.timedelta(days=1)
        return f"No NYSE session tomorrow ({day_label(tomorrow)}) — no outlook issued."
    head = f"**Outlook for {day_label(result.target)}**"
    if result.unavailable:
        return f"{head}\nOutlook unavailable: {result.unavailable}"
    if _is_empty(result):
        return f"{head} — no plans, no watch names, no near-misses."
    return "\n".join([head, *result.regime_lines, *_sections(result)])


def card_badge(valid_session: dt.date) -> str:
    return f"{OUTLOOK_BADGE} **Outlook · valid {day_label(valid_session)} only**"


def decorate_card(embed, *, valid_session: dt.date, context_line: str | None) -> None:
    """The outlook badge above the regular plan embed's description, and the
    display-only context field. The ⚠ overlap field is lane_overlap's."""
    embed.description = f"{card_badge(valid_session)}\n{embed.description or ''}"[:4096]
    if context_line:
        embed.add_field(name=CONTEXT_FIELD, value=context_line, inline=False)


def _code(plan) -> str:
    return cancel_reason(plan) or "cancelled"


def _wrapup_row(plan) -> str:
    head = f"{plan.ticker} {side_word(plan.direction)}"
    if plan.status == PlanStatus.CANCELLED:
        return f"{head} — cancelled ({_code(plan)}): {plan.cancel_reason_message or _code(plan)}"
    if is_filled(plan):
        return f"{head} — filled at {plan.entry_price:.2f}"
    return f"{head} — {str(plan.status).lower()}"


def count_line(plans: list) -> str:
    filled = sum(1 for plan in plans if is_filled(plan))
    codes = Counter(_code(plan) for plan in plans if plan.status == PlanStatus.CANCELLED)
    detail = f" ({', '.join(f'{code} ×{n}' for code, n in sorted(codes.items()))})" if codes else ""
    return f"{len(plans)} issued · {filled} filled · {sum(codes.values())} cancelled{detail}"


def wrapup_text(day: dt.date, plans: list) -> str:
    return "\n".join([f"**Outlook wrap-up · {day_label(day)}**",
                      *(f"• {_wrapup_row(plan)}" for plan in plans), count_line(plans)])
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_outlook_embeds.py` and `python scripts/dev/testrun.py file tests/presentation/test_kinds.py`.
Expected: both PASS. `test_kinds` is table-driven over every `Kind` and checks family, badge/label uniqueness and the glyph rules.

If `test_regime_lines_skip_a_symbol_without_enough_history` fails on the label prefix: the fixture rises monotonically, so `get_market_regime` labels it `Bullish (...)`; read `scanning/regime.py:get_market_regime` and fix the fixture, not the code.

- [ ] **Step 9: Complexity check and commit**

Run: `python -m radon cc -s -n C swingbot/core/scanning/outlook_types.py swingbot/core/scanning/outlook_context.py swingbot/core/scanning/outlook_embeds.py`. Expected: no output.

```bash
git add swingbot/core/presentation/kinds.py swingbot/core/scanning/outlook_types.py swingbot/core/scanning/outlook_context.py swingbot/core/scanning/outlook_embeds.py tests/scanning/test_outlook_embeds.py
git commit -m "feat(v144): outlook digest, card decoration and wrap-up rendering

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V144-11: The outlook run (`outlook_run`)

**Files:**
- Create: `swingbot/core/scanning/outlook_run.py`
- Modify: `swingbot/core/scanning/short_run.py` (`_log_trade(..., origin=None)`)
- Test: `tests/scanning/test_outlook_run.py`

**Interfaces:**
- Consumes:
  - V144-1: `NEXT_SESSION`; `TradePlanV2.origin`/`.valid_session`; `log_trade(origin=)`.
  - V144-8: `outlook_session.target_session`, `signal_session`.
  - V144-9: `lane_overlap.append_overlap_field`.
  - V144-10: `outlook_types.*`, `outlook_context.context_line`/`regime_lines`, `outlook_embeds.decorate_card`.
  - Live pieces: `analyze._scan_one`, `analyze.ScanIO`, `analyze._live_stop_requested`, `analyze._live_track_record`, `qualify.qualify_short_item`/`QualifyContext`/`Accepted`, `dedup.dedup_scan_items`, `fetch._fetch_cold_frames`/`map_tickers`/`_etf_symbol_of_sector`/`_sector_etfs_for_tickers`/`_fetch_frames`, `scan_run._scan_tickers`/`_hard_filters_snapshot`/`get_regime`/`_earnings_in_window`, `short_run._stamp_context`/`_fit_trendline`/`_render_chart`/`_log_trade`, `data_refresh.is_stale`, `data_store.load_normalized`/`load_from_disk`, `account.compute_position_size`, `embeds.build_embed`/`build_simple_alert`, `plan_table.plan_numbers_for_display`.
- Produces:
  - `run_outlook(run_date, *, now=None) -> OutlookResult`: synchronous and heavy, so call it via `asyncio.to_thread`.
  - `closed_frames(symbols, bar_date, now) -> dict`.
  - `outlook_open_tickers() -> set[str]`.
  - `short_run._log_trade(item, nums, explanation, fit, alerts, origin=None)`.

- [ ] **Step 1: Invoke `no-lookahead` and `alert-surface`.** NO-LOOKAHEAD is the reason for `closed_frames`. The live crawl's cache-first read (`fetch._load_cached_daily`, `SCAN_CACHE_MAX_AGE_HOURS` = 6) would accept a CSV written mid-session, whose last bar is partial. A cached file is used only if it was written after the bar date's close; otherwise it is refetched. `live_prices={}` makes every scenario price off the closed bar, as the replay does.

- [ ] **Step 2: Write the failing tests**

```python
# tests/scanning/test_outlook_run.py
"""v144: the 23:30 outlook run -- closed bars only, live gates, three routes."""
import datetime as dt
from types import SimpleNamespace

import discord
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.scanning import outlook_run as orun
from swingbot.core.scanning import qualify, short_run
from swingbot.core.scanning.outlook_types import OutlookResult
from swingbot.core.tracking.performance import TradeLog
from tests.planning.test_plan_engine_model import _plan

FRIDAY, SUNDAY, MONDAY = dt.date(2026, 10, 9), dt.date(2026, 10, 11), dt.date(2026, 10, 12)
NOW = dt.datetime(2026, 10, 11, 21, 30, tzinfo=dt.timezone.utc)      # Sunday 23:30 Berlin


def _frame(last):
    days = pd.bdate_range(end=pd.Timestamp(last), periods=5)
    return pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": 1.0}, index=days)


# --- closed bars ----------------------------------------------------------------

def test_closed_frames_trusts_only_a_cache_written_after_the_close(monkeypatch):
    windows = {}

    def is_stale(symbol, timeframe, max_age_hours):
        windows[symbol] = max_age_hours
        return symbol != "WARM"

    monkeypatch.setattr(orun.data_refresh, "is_stale", is_stale)
    monkeypatch.setattr(orun.data_store, "load_normalized", lambda s, tf: _frame(FRIDAY))
    monkeypatch.setattr(orun.fetch, "_fetch_cold_frames",
                        lambda cold, progress: [(s, _frame(FRIDAY if s == "COLD" else FRIDAY - dt.timedelta(days=1)))
                                                for s in cold])
    frames = orun.closed_frames(["WARM", "COLD", "OLD", "WARM"], FRIDAY, NOW)
    assert sorted(frames) == ["COLD", "WARM"]          # OLD's last bar is Thursday: dropped
    assert windows["WARM"] == pytest.approx(49.5)      # Fri 16:00 ET -> Sun 21:30 UTC


def test_before_the_close_the_cache_is_never_read(monkeypatch):
    monkeypatch.setattr(orun.data_refresh, "is_stale", lambda *a, **k: pytest.fail("cache consulted"))
    assert orun._cached_after_close("AAPL", -1.0) is None


# --- the short-circuits ----------------------------------------------------------

def test_no_session_tomorrow_scans_nothing(monkeypatch):
    monkeypatch.setattr(orun, "closed_frames", lambda *a: pytest.fail("scanned"))
    result = orun.run_outlook(dt.date(2027, 3, 25), now=NOW)
    assert result.target is None and result.unavailable is None and result.plans == []


def test_the_v2_engine_must_be_on(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "shadow")
    monkeypatch.setattr(orun, "closed_frames", lambda *a: pytest.fail("scanned"))
    result = orun.run_outlook(SUNDAY, now=NOW)
    assert (result.target, result.bar_date) == (MONDAY, FRIDAY)
    assert result.unavailable == "PLAN_ENGINE_V2 is not 'on', so no plan can be built"


def test_a_missing_regime_bar_issues_nothing(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(config, "MARKET_REGIME_TICKER", "SPY")
    monkeypatch.setattr(orun.scan_run, "_scan_tickers", lambda: ["AAPL"])
    monkeypatch.setattr(orun, "closed_frames", lambda symbols, bar_date, now: {"AAPL": _frame(FRIDAY)})
    result = orun.run_outlook(SUNDAY, now=NOW)
    assert result.unavailable == "no closed SPY daily bar for 2026-10-09"
    assert result.plans == [] and result.alerts == []


# --- gates and routes ------------------------------------------------------------

def _item(ticker, *, met=True, entry_type="stop_entry", rejected=None, score=50):
    scenario = SimpleNamespace(entry=102.0, stop_loss=100.5, take_profit=106.0, stop_distance_pct=2.6,
                               target2_price=None)
    plan_v2 = None if entry_type is None else SimpleNamespace(
        entry_type=entry_type, direction="bullish", strategy="Break & Retest",
        trigger_price=102.0, stop_loss=100.5, tp1=106.0)
    return SimpleNamespace(
        all_requirements_met=met, plan_v2_rejected=rejected, plan=scenario, plan_v2=plan_v2,
        conf=SimpleNamespace(score=score),
        result=SimpleNamespace(ticker=ticker, trend="bullish", strategy="Break & Retest", horizon_key="4w"))


def test_verdicts_keep_accepted_items_and_word_plan_stage_rejections(monkeypatch):
    def verdict(candidate, item, context):
        if item.plan_v2_rejected:
            return qualify.Rejected(item, "plan", item.plan_v2_rejected)
        if item.result.ticker == "RS":
            return qualify.Rejected(item, "rs", "rs_blocked")
        return qualify.Accepted(item)

    monkeypatch.setattr(orun.qualify, "qualify_short_item", verdict)
    items = [_item("OK"), _item("CAP", rejected="risk_cap"), _item("RS"), _item("UNMET", met=False)]
    accepted, near = orun._verdicts(items, context=None)
    assert [item.result.ticker for item in accepted] == ["OK"]
    assert [(line.ticker, line.reason) for line in near] == [("CAP", "risk_cap (stop 2.6% from entry)")]


def test_route_issues_stop_entries_lists_market_entries_and_skips_open_tickers(monkeypatch):
    issued = []
    monkeypatch.setattr(orun, "_issue", lambda item, plan, result, frames, spy: issued.append(item.result.ticker))
    result = OutlookResult(run_date=SUNDAY, target=MONDAY)
    ordered = [_item("AAPL"), _item("AAPL"), _item("MSFT", entry_type="market"),
               _item("TSLA"), _item("NONE", entry_type=None)]
    orun._route(ordered, {"TSLA"}, result, frames={}, spy=None)
    assert issued == ["AAPL"]                           # once per ticker
    assert [line.ticker for line in result.watch] == ["MSFT"]
    assert result.skipped == ["AAPL", "TSLA"]


def test_issue_stamps_the_plan_and_logs_an_outlook_trade(monkeypatch):
    logged = {}
    monkeypatch.setattr(orun, "build_explanation", lambda *a, **k: "why")
    monkeypatch.setattr(orun.scan_run, "_earnings_in_window", lambda *a: None)
    monkeypatch.setattr(orun, "plan_numbers_for_display", lambda plan, legacy: dict(legacy))
    monkeypatch.setattr(orun.short_run, "_fit_trendline", lambda *a: None)
    monkeypatch.setattr(orun.short_run, "_log_trade",
                        lambda item, nums, explanation, fit, alerts, origin=None: logged.update(origin=origin) or "T1")
    monkeypatch.setattr(orun, "_card", lambda *a: ("card",))
    monkeypatch.setattr(orun, "_risk_dollars", lambda plan: 120.0)
    item = _item("AAPL")
    item.target_confluence = item.stop_confluence = None
    item.combined_from = []
    plan = _plan(entry_type="stop_entry", trigger_price=102.0, stop_loss=100.5, tp1=106.0)
    result = OutlookResult(run_date=SUNDAY, target=MONDAY)
    orun._issue(item, plan, result, frames={}, spy=None)
    assert (plan.origin, plan.valid_session) == ("next_session", "2026-10-12")
    assert logged["origin"] == "next_session" and item.paper_logged is True
    assert result.alerts == [("card",)]
    assert result.plans[0].risk_dollars == 120.0 and result.plans[0].entry == 102.0


def test_the_card_carries_the_badge(monkeypatch):
    monkeypatch.setattr(orun.short_run, "_render_chart", lambda *a: (None, None))
    monkeypatch.setattr(orun, "build_embed", lambda *a, **k: discord.Embed(description="body"))
    monkeypatch.setattr(orun, "build_simple_alert", lambda item: None)
    monkeypatch.setattr(orun, "_hourly", lambda ticker: None)
    item = _item("AAPL")
    item.conf.level, item.htf_info = 3, None
    plan = _plan(entry_type="stop_entry")
    embed, chart_path, card_plan, simple = orun._card(item, plan, MONDAY, "why", {}, None, {}, None, "T1", None)
    assert embed.description.startswith("🌙 **Outlook · valid Monday 2026-10-12 only**")
    assert card_plan is plan and chart_path is None


def test_open_tickers_count_only_the_outlook_lane():
    PlanStore().add(_plan(plan_id="o1", ticker="AAPL", origin="next_session", valid_session="2026-10-12"))
    PlanStore().add(_plan(plan_id="r1", ticker="MSFT"))
    TradeLog().log_trade(ticker="NVDA", strategy="MACD", horizon_key="3m", direction="bullish",
                         confidence_level=3, confidence_label="Medium", entry=100.0, stop_loss=98.0,
                         take_profit=105.0, origin="next_session")
    TradeLog().log_trade(ticker="AMD", strategy="MACD", horizon_key="3m", direction="bullish",
                         confidence_level=3, confidence_label="Medium", entry=100.0, stop_loss=98.0,
                         take_profit=105.0)
    assert orun.outlook_open_tickers() == {"AAPL", "NVDA"}


def test_log_trade_passes_the_origin_through(monkeypatch):
    seen = {}
    monkeypatch.setattr(short_run.scan_run, "_logged_plan_fields", lambda *a: ([], 2.0))
    monkeypatch.setattr(short_run.scan_run, "_persist_plan_v2", lambda plan, alerts: None)
    monkeypatch.setattr(short_run.trade_log, "log_trade", lambda **kw: seen.update(kw) or "T1")
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    plan_v2 = _plan(entry_type="stop_entry")
    item = SimpleNamespace(
        result=SimpleNamespace(ticker="AAPL", strategy="RSI", horizon_key="4w", trend="bullish"),
        plan=SimpleNamespace(stop_sources=[], target2_sources=[]), plan_v2=plan_v2, level_map=None,
        conf=SimpleNamespace(level=3, label="Medium", score=60, breakdown={}), combined_from=[])
    nums = {"entry": 102.0, "stop_loss": 100.5, "take_profit": 106.0, "target2": None}
    assert short_run._log_trade(item, nums, "why", None, [], origin="next_session") == "T1"
    assert seen["origin"] == "next_session"
    short_run._log_trade(item, nums, "why", None, [])
    assert seen["origin"] is None
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_outlook_run.py`
Expected: FAIL with `ImportError` (no `outlook_run`).

- [ ] **Step 4: `short_run._log_trade` takes an origin.** Change its signature to `def _log_trade(item, nums, explanation, fit, alerts, origin=None):`. Add one keyword to its `trade_log.log_trade(...)` call, after `entry_context=plan_v2.entry_context if plan_v2 is not None else None`: `, origin=origin`. That is a pass-through only; the regular SHORT lane keeps calling it without the argument.

- [ ] **Step 5: Create `swingbot/core/scanning/outlook_run.py`**

```python
"""v144: the 23:30 next-session outlook -- the last closed bar, tomorrow's plans.

It runs the live scan's own pieces, never copies:
  * frames -- `closed_frames`, bars whose last row is the signal session's
    closed bar (a cache file written before that close is refetched);
  * scoring -- `analyze._scan_one` with OUTLOOK_IO (no open-trade monitoring, so
    23:30 closes nothing) and `live_prices={}`, as the replay does;
  * gates -- `qualify.qualify_short_item` with no confirmation store (a once-a-
    night run has no scan-to-scan debounce), then dedup and the live sort.

Each accepted item goes one of three ways. A `stop_entry` plan is issued as an
outlook plan (origin next_session, valid_session = the target session) with a
placeholder trade. A market-entry plan is a WATCH name only: it would be born
ACTIVE at a price nobody can trade at 23:30 (spec v144 amendment 1). A plan the
builder rejected is a near-miss. Issuance is the last step, after the whole scan
succeeded, so a failing scan issues nothing. Nothing here touches the regular
lane's confirmation store, plans or trades.
"""
from __future__ import annotations

import datetime as dt
import logging

from swingbot import config
from swingbot.core.edge import factors as rs_factors
from swingbot.core.edge import regime2
from swingbot.core.market import opex
from swingbot.core.market.explain import build_explanation
from swingbot.core.market.session import US_MARKET_TZ, session_close
from swingbot.core.market.strategy import HORIZONS, LEGACY_HORIZONS
from swingbot.core.marketdata import data_refresh, data_store
from swingbot.core.planning import account as account_module
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking.origin import NEXT_SESSION
from swingbot.scan_params import ScanParams

from . import (analyze, dedup, fetch, lane_overlap, outlook_context, outlook_embeds,
               outlook_session, qualify, scan_run, short_run)
from .embeds import build_embed, build_simple_alert
from .outlook_types import OutlookLine, OutlookResult
from .plan_table import plan_numbers_for_display
from .singletons import trade_log

log = logging.getLogger(__name__)

REGIME_SYMBOLS = ("SPY", "QQQ")
STOP_ENTRY = "stop_entry"
OUTLOOK_IO = analyze.ScanIO(stop_requested=analyze._live_stop_requested,
                            monitor_scan=lambda *a: ([], []), monitor_open=lambda *a: ([], []),
                            track_record=analyze._live_track_record)


# --- closed bars ------------------------------------------------------------------

def _hours_since_close(bar_date: dt.date, now: dt.datetime) -> float:
    closed_at = dt.datetime.combine(bar_date, session_close(bar_date), tzinfo=US_MARKET_TZ)
    return (now - closed_at).total_seconds() / 3600.0


def _cached_after_close(symbol: str, hours: float):
    """The cached daily frame only if the file was written after the close."""
    if hours <= 0:
        return None
    try:
        if data_refresh.is_stale(symbol, "daily", max_age_hours=hours):
            return None
        return data_store.load_normalized(symbol, "daily")
    except Exception:
        log.debug("outlook: cache read failed for %s -- fetching", symbol, exc_info=True)
        return None


def _ends_on(frame, day: dt.date) -> bool:
    return frame is not None and len(frame) > 0 and frame.index[-1].date() == day


def closed_frames(symbols, bar_date: dt.date, now: dt.datetime) -> dict:
    """{symbol: daily frame whose last bar is bar_date's closed bar}."""
    hours = _hours_since_close(bar_date, now)
    frames, cold = {}, []
    for symbol in dict.fromkeys(symbols):
        frame = _cached_after_close(symbol, hours)
        if frame is None:
            cold.append(symbol)
        else:
            frames[symbol] = frame
    for symbol, frame in fetch._fetch_cold_frames(cold, None):
        if frame is not None:
            frames[symbol] = frame
    return {symbol: frame for symbol, frame in frames.items() if _ends_on(frame, bar_date)}


# --- scoring and gates ------------------------------------------------------------

def _scored_items(frames: dict, spy) -> tuple[list, object, float | None]:
    tier = opex.current_tier()
    params = ScanParams.from_config()
    min_confluence = opex.effective_min_confluence(params.min_target_confluence_count, tier)
    min_level = opex.effective_min_confidence_level(tier)
    hard = scan_run._hard_filters_snapshot(params)
    rs_cache = rs_factors.refresh_rs_cache(frames, spy)
    breadth = rs_factors.breadth_pct_above_50ema(frames)
    regime = scan_run.get_regime(spy)
    per_ticker = fetch.map_tickers(
        lambda ticker: analyze._scan_one(
            ticker, frames[ticker], list(LEGACY_HORIZONS), None, regime, min_confluence, min_level,
            rs_cache=rs_cache, spy_df=spy, breadth=breadth, live_prices={}, hard_filters=hard,
            opex_tier_today=tier, io=OUTLOOK_IO),
        list(frames))
    items = [item for result in per_ticker if result is not None for item in result["items"]]
    return items, regime, breadth


def _sector_inputs(tickers: list) -> tuple[dict, dict, dict]:
    try:
        etf_of = fetch._etf_symbol_of_sector()
        sector_of, needed = fetch._sector_etfs_for_tickers(tickers)
        return sector_of, etf_of, (fetch._fetch_frames(needed) if needed else {})
    except Exception:
        log.warning("outlook: sector ETFs unavailable -- ticker-only RS", exc_info=True)
        return {}, {}, {}


def _regimes(spy):
    try:
        return regime2.regime_series(spy)
    except Exception:
        return None


def _context(frames: dict, spy, regime, breadth) -> qualify.QualifyContext:
    sector_of, etf_of, sector_frames = _sector_inputs(list(frames))
    return qualify.QualifyContext(
        frames=frames, spy=spy, sector_of=sector_of, etf_symbol_of=etf_of,
        sector_frames=sector_frames, regime=regime, regimes=_regimes(spy), breadth=breadth)


def _scenario_line(item, reason: str | None = None) -> OutlookLine:
    scenario = item.plan
    return OutlookLine(item.result.ticker, item.result.trend, item.result.strategy,
                       float(scenario.entry), float(scenario.stop_loss), float(scenario.take_profit),
                       reason=reason)


def _near_reason(item) -> str:
    stop_pct = getattr(item.plan, "stop_distance_pct", float("nan"))
    return f"{item.plan_v2_rejected} (stop {stop_pct:.1f}% from entry)"


def _verdicts(items: list, context) -> tuple[list, list[OutlookLine]]:
    """(accepted items, near-miss lines). Only a fully-qualifying item reaches
    the plan builder; a plan-stage rejection is a near-miss, the rest is silence."""
    accepted, near = [], []
    for item in items:
        if not item.all_requirements_met:
            continue
        verdict = qualify.qualify_short_item(None, item, context)
        if isinstance(verdict, qualify.Accepted):
            accepted.append(item)
        elif verdict.stage == "plan":
            near.append(_scenario_line(item, _near_reason(item)))
    return accepted, near


def _ordered(accepted: list) -> list:
    deduped = dedup.dedup_scan_items(accepted)
    deduped.sort(key=lambda item: (item.all_requirements_met, item.conf.score), reverse=True)
    return deduped


# --- routing and issuance ---------------------------------------------------------

def outlook_open_tickers() -> set[str]:
    """Tickers already holding an open outlook plan or trade. Regular plans and
    trades never count: the lanes are independent (spec v144 § Independence)."""
    plans = {plan.ticker for plan in PlanStore().open_plans() if plan.origin == NEXT_SESSION}
    trades = {trade["ticker"] for trade in trade_log.get_trades(status="open", limit=None) or []
              if trade.get("origin") == NEXT_SESSION}
    return plans | trades


def _plan_line(item, plan, risk: float | None = None) -> OutlookLine:
    return OutlookLine(item.result.ticker, plan.direction, plan.strategy, float(plan.trigger_price),
                       float(plan.stop_loss), float(plan.tp1), risk_dollars=risk)


def _risk_dollars(plan) -> float | None:
    try:
        sizing = account_module.compute_position_size(plan.trigger_price, plan.stop_loss)
    except Exception:
        return None
    if not sizing or not sizing.get("shares"):
        return None
    return round(float(sizing["shares"]) * abs(float(plan.trigger_price) - float(plan.stop_loss)), 2)


def _route(ordered: list, open_tickers: set, result: OutlookResult, frames: dict, spy) -> None:
    for item in ordered:
        plan, ticker = item.plan_v2, item.result.ticker
        if plan is None:
            continue
        if ticker in open_tickers:
            if ticker not in result.skipped:
                result.skipped.append(ticker)
        elif plan.entry_type != STOP_ENTRY:
            result.watch.append(_plan_line(item, plan))
        else:
            _issue(item, plan, result, frames, spy)
            open_tickers.add(ticker)


def _issue(item, plan, result: OutlookResult, frames: dict, spy) -> None:
    """Persist one outlook plan and its placeholder trade, then build its card."""
    ticker, horizon = item.result.ticker, HORIZONS[item.result.horizon_key]
    plan.origin, plan.valid_session = NEXT_SESSION, result.target.isoformat()
    scenario = item.plan
    explanation = build_explanation(
        item.result, earnings_info=scan_run._earnings_in_window(ticker, horizon["max_holding_days"]),
        target_confluence=item.target_confluence, stop_confluence=item.stop_confluence,
        confirmed_by=item.combined_from, plan=plan)
    nums = plan_numbers_for_display(plan, {"entry": scenario.entry, "stop_loss": scenario.stop_loss,
                                           "take_profit": scenario.take_profit,
                                           "target2": scenario.target2_price})
    item.paper_logged, item.not_logged_reason = True, None
    df = frames.get(ticker)
    fit = short_run._fit_trendline(df, scenario, horizon, item.result.trend)
    trade_id = short_run._log_trade(item, nums, explanation, fit, result.alerts, origin=NEXT_SESSION)
    result.alerts.append(_card(item, plan, result.target, explanation, nums, df, frames, spy, trade_id, fit))
    result.plans.append(_plan_line(item, plan, risk=_risk_dollars(plan)))


def _hourly(ticker: str):
    try:
        return data_store.load_from_disk(ticker, "hourly")
    except Exception:
        return None                    # display-only context; never fails a card


def _card(item, plan, target, explanation, nums, df, frames, spy, trade_id, fit) -> tuple:
    chart_path, chart_filename = short_run._render_chart(item, nums, df, frames, spy, trade_id, fit)
    embed = build_embed(item, explanation, trade_log.get_stats(item.conf.level), None, chart_filename,
                        htf_info=item.htf_info, layout=config.ALERT_EMBED_LAYOUT)
    outlook_embeds.decorate_card(
        embed, valid_session=target,
        context_line=outlook_context.context_line(df, _hourly(item.result.ticker), plan.direction))
    lane_overlap.append_overlap_field(embed, item.result.ticker, viewer_origin=NEXT_SESSION)
    return (embed, chart_path, plan, build_simple_alert(item))


# --- the run ----------------------------------------------------------------------

def _blocker(result: OutlookResult) -> str | None:
    if config.PLAN_ENGINE_V2 != "on":
        return "PLAN_ENGINE_V2 is not 'on', so no plan can be built"
    if result.bar_date is None:
        return "no NYSE session on or before the run date in the calendar"
    return None


def _fill(result: OutlookResult, now: dt.datetime) -> None:
    tickers = scan_run._scan_tickers()
    frames = closed_frames([*tickers, config.MARKET_REGIME_TICKER, *REGIME_SYMBOLS], result.bar_date, now)
    spy = frames.get(config.MARKET_REGIME_TICKER)
    if spy is None:
        result.unavailable = (f"no closed {config.MARKET_REGIME_TICKER} daily bar for "
                              f"{result.bar_date.isoformat()}")
        return
    result.regime_lines = outlook_context.regime_lines({s: frames.get(s) for s in REGIME_SYMBOLS})
    scan_frames = short_run._stamp_context({t: frames[t] for t in tickers if t in frames}, spy)
    items, regime, breadth = _scored_items(scan_frames, spy)
    accepted, result.near_misses = _verdicts(items, _context(scan_frames, spy, regime, breadth))
    _route(_ordered(accepted), outlook_open_tickers(), result, scan_frames, spy)


def run_outlook(run_date: dt.date, *, now: dt.datetime | None = None) -> OutlookResult:
    """The whole 23:30 run for one Berlin run date. Synchronous and heavy:
    call it through asyncio.to_thread."""
    now = now or dt.datetime.now(dt.timezone.utc)
    result = OutlookResult(run_date=run_date, target=outlook_session.target_session(run_date),
                           bar_date=outlook_session.signal_session(run_date))
    if result.target is None:
        return result
    result.unavailable = _blocker(result)
    if result.unavailable is None:
        _fill(result, now)
    return result
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_outlook_run.py`, then `python scripts/dev/testrun.py file tests/scanning/test_short_lane_scan.py` and `python scripts/dev/testrun.py file tests/scanning/test_short_alert_parity.py` (the regular SHORT lane still calls `_log_trade` without an origin).
Expected: all PASS.

- [ ] **Step 7: Complexity check and commit**

Run: `python -m radon cc -s -n C swingbot/core/scanning/outlook_run.py swingbot/core/scanning/short_run.py`. Expected: no output for `outlook_run.py`, and no new line for `short_run.py`.

```bash
git add swingbot/core/scanning/outlook_run.py swingbot/core/scanning/short_run.py tests/scanning/test_outlook_run.py
git commit -m "feat(v144): the outlook run -- closed bars, live gates, stop entries issued, market entries watched

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V144-12: The `next_session_scan` and `next_session_wrapup` loops

**Files:**
- Create: `swingbot/commands/scanning/outlook.py`
- Modify: `swingbot/commands/scanning/loops.py`:
  - imports: `outlook` in the `from . import ...` line, plus `from swingbot.core.scanning import outlook_session`
  - after `weekend_deep_scan_task`: `_next_session_fired_date`, `_outlook_now`, `_scheduled_job_fired_since`, `next_session_scan`, `next_session_wrapup`
  - `_always_on_loops`
- Test: `tests/commands/test_outlook_loops.py`

**Interfaces:**
- Consumes:
  - V144-2: `PlanStore.for_session`.
  - V144-8: `config.NEXT_SESSION_SCAN_*`; `outlook_session.parse_slot`, `latest_slot_date`, `fire_allowed`, `target_session`, `wrapup_due`, `wrapup_candidates`.
  - V144-10: `outlook_embeds.digest_text`/`wrapup_text`, `Kind.OUTLOOK`/`OUTLOOK_WRAPUP`.
  - V144-11: `outlook_run.run_outlook`.
  - Existing: `notices.system_embed`/`chunk_text`/`send_guarded`, `alerts._send_alerts`, `scan_run._scan_lock`, `logsetup.scan_context`/`new_scan_id`, `silent_channel.silence`, `_mark_scheduled_job_fired`.
- Produces:
  - `outlook.run_next_session_outlook(run_date) -> OutlookResult | None`.
  - `outlook.post_wrapup_when_terminal(day) -> bool` (True = done, so mark it fired).
  - `outlook.digest_embeds(result) -> list`.
  - `loops.next_session_scan`, `loops.next_session_wrapup` (both `@tasks.loop(minutes=1)`, started by `_always_on_loops`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/commands/test_outlook_loops.py
"""v144: the outlook loops fire once per slot, never into a running session,
and the wrap-up waits for every plan of D to be terminal."""
import asyncio
import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from swingbot import config
from swingbot.commands.scanning import loops as loops_mod
from swingbot.commands.scanning import outlook as outlook_cmd
from swingbot.core.db.repositories.scheduled import scheduled_repo
from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.scanning.outlook_types import OutlookLine, OutlookResult
from tests.planning.test_plan_engine_model import _plan

BERLIN, ET = ZoneInfo("Europe/Berlin"), ZoneInfo("America/New_York")
SUNDAY, MONDAY = dt.date(2026, 10, 11), dt.date(2026, 10, 12)


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, **kwargs):
        self.sent.append(kwargs)


@pytest.fixture
def scan(monkeypatch):
    calls = []

    async def run(run_date):
        calls.append(run_date)

    monkeypatch.setattr(config, "NEXT_SESSION_SCAN_ENABLED", True)
    monkeypatch.setattr(config, "NEXT_SESSION_SCAN_TIME", "23:30")
    monkeypatch.setattr(loops_mod, "_next_session_fired_date", None)
    monkeypatch.setattr(loops_mod.outlook, "run_next_session_outlook", run)

    def tick(now):
        monkeypatch.setattr(loops_mod, "_outlook_now", lambda: now)
        monkeypatch.setattr(loops_mod, "_next_session_fired_date", None)   # as after a restart
        asyncio.run(loops_mod.next_session_scan.coro())
    return calls, tick


def test_fires_once_at_the_sunday_slot(scan):
    calls, tick = scan
    tick(dt.datetime(2026, 10, 11, 23, 29, tzinfo=BERLIN))
    tick(dt.datetime(2026, 10, 11, 23, 30, tzinfo=BERLIN))
    tick(dt.datetime(2026, 10, 11, 23, 31, tzinfo=BERLIN))
    # 23:29: Thursday's slot is the latest, but Friday's RTH open has passed, so it
    # is marked and skipped, never run. 23:30 runs Sunday's; 23:31 sees it fired.
    assert calls == [SUNDAY]
    assert scheduled_repo().fired_on("next_session_scan") == "2026-10-11"


def test_never_runs_disabled(scan, monkeypatch):
    calls, tick = scan
    monkeypatch.setattr(config, "NEXT_SESSION_SCAN_ENABLED", False)
    tick(dt.datetime(2026, 10, 11, 23, 30, tzinfo=BERLIN))
    assert calls == []


def test_a_late_fire_before_the_rth_open_still_runs(scan):
    calls, tick = scan
    scheduled_repo().mark("next_session_scan", "2026-10-08")       # Thursday's ran
    tick(dt.datetime(2026, 10, 12, 8, 0, tzinfo=BERLIN))           # Monday morning: Sunday's was missed
    assert calls == [SUNDAY]


def test_a_late_fire_after_the_rth_open_is_skipped_and_marked(scan):
    calls, tick = scan
    scheduled_repo().mark("next_session_scan", "2026-10-08")
    tick(dt.datetime(2026, 10, 12, 15, 45, tzinfo=BERLIN))         # 09:45 ET Monday
    assert calls == []
    assert scheduled_repo().fired_on("next_session_scan") == "2026-10-11"


def test_friday_and_saturday_evenings_never_fire(scan):
    calls, tick = scan
    scheduled_repo().mark("next_session_scan", "2026-10-08")
    tick(dt.datetime(2026, 10, 9, 23, 30, tzinfo=BERLIN))
    tick(dt.datetime(2026, 10, 10, 23, 30, tzinfo=BERLIN))
    assert calls == []


# --- the wrap-up loop ---------------------------------------------------------------

@pytest.fixture
def wrap(monkeypatch):
    answers, asked = {}, []

    async def post(day):
        asked.append(day)
        return answers.get(day, True)

    monkeypatch.setattr(loops_mod.outlook, "post_wrapup_when_terminal", post)

    def tick(now):
        monkeypatch.setattr(loops_mod, "_outlook_now", lambda: now)
        asyncio.run(loops_mod.next_session_wrapup.coro())
    return answers, asked, tick


def test_the_wrapup_waits_for_the_close_plus_15(wrap):
    answers, asked, tick = wrap
    scheduled_repo().mark("next_session_wrapup", "2026-10-09")
    tick(dt.datetime(2026, 10, 12, 16, 10, tzinfo=ET))
    assert asked == []
    tick(dt.datetime(2026, 10, 12, 16, 15, tzinfo=ET))
    assert asked == [MONDAY]
    assert scheduled_repo().fired_on("next_session_wrapup") == "2026-10-12"


def test_a_pending_plan_keeps_the_wrapup_open(wrap):
    answers, asked, tick = wrap
    scheduled_repo().mark("next_session_wrapup", "2026-10-09")
    answers[MONDAY] = False
    tick(dt.datetime(2026, 10, 12, 16, 20, tzinfo=ET))
    tick(dt.datetime(2026, 10, 12, 16, 21, tzinfo=ET))
    assert asked == [MONDAY, MONDAY]
    assert scheduled_repo().fired_on("next_session_wrapup") == "2026-10-09"


# --- posting --------------------------------------------------------------------------

def _outlook(plan_id, **kw):
    return _plan(plan_id=plan_id, entry_type="stop_entry", origin="next_session",
                 valid_session=MONDAY.isoformat(), **kw)


def test_post_wrapup_waits_then_posts_once_terminal(monkeypatch):
    channel = FakeChannel()
    monkeypatch.setattr(outlook_cmd, "_alerts_channel", lambda: channel)
    store = PlanStore()
    pending = _outlook("o1")
    store.add(pending)
    assert asyncio.run(outlook_cmd.post_wrapup_when_terminal(MONDAY)) is False
    assert channel.sent == []
    record_transition(pending, PlanStatus.CANCELLED, reason="never_triggered", at="t")
    pending.cancel_reason_message = "High 101.40 stopped 0.6% short of the 102.00 trigger"
    store.update(pending)
    assert asyncio.run(outlook_cmd.post_wrapup_when_terminal(MONDAY)) is True
    (message,) = channel.sent
    assert "1 issued · 0 filled · 1 cancelled (never_triggered ×1)" in message["embed"].description


def test_a_session_without_outlook_plans_is_done_silently(monkeypatch):
    channel = FakeChannel()
    monkeypatch.setattr(outlook_cmd, "_alerts_channel", lambda: channel)
    assert asyncio.run(outlook_cmd.post_wrapup_when_terminal(MONDAY)) is True
    assert channel.sent == []


def test_run_posts_the_digest_then_the_cards(monkeypatch):
    channel, sent_alerts = FakeChannel(), []
    result = OutlookResult(run_date=SUNDAY, target=MONDAY, plans=[OutlookLine(
        "AAPL", "bullish", "Break & Retest", 102.0, 100.5, 106.0, risk_dollars=120.0)],
        alerts=[("embed", None, None, None)])

    async def send_alerts(destination, alerts, route_by_confidence=False):
        sent_alerts.append((destination, alerts))

    monkeypatch.setattr(outlook_cmd, "_alerts_channel", lambda: channel)
    monkeypatch.setattr(outlook_cmd.outlook_run, "run_outlook", lambda run_date: result)
    monkeypatch.setattr(outlook_cmd, "_send_alerts", send_alerts)
    monkeypatch.setattr(outlook_cmd.scan_run, "_scan_lock", asyncio.Lock())
    assert asyncio.run(outlook_cmd.run_next_session_outlook(SUNDAY)) is result
    (digest,) = channel.sent
    assert digest["embed"].description.startswith("**Outlook for Monday 2026-10-12**")
    assert sent_alerts == [(channel, result.alerts)]


def test_a_failing_scan_posts_outlook_unavailable(monkeypatch):
    channel = FakeChannel()

    def boom(run_date):
        raise RuntimeError("boom")

    monkeypatch.setattr(outlook_cmd, "_alerts_channel", lambda: channel)
    monkeypatch.setattr(outlook_cmd.outlook_run, "run_outlook", boom)
    monkeypatch.setattr(outlook_cmd.scan_run, "_scan_lock", asyncio.Lock())
    result = asyncio.run(outlook_cmd.run_next_session_outlook(SUNDAY))
    assert result.unavailable == "scan failed (RuntimeError: boom)" and result.alerts == []
    assert "Outlook unavailable: scan failed (RuntimeError: boom)" in channel.sent[0]["embed"].description


def test_both_loops_start_with_the_bot():
    assert loops_mod.next_session_scan in loops_mod._always_on_loops()
    assert loops_mod.next_session_wrapup in loops_mod._always_on_loops()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/commands/test_outlook_loops.py`
Expected: FAIL with `ImportError: cannot import name 'outlook'`.

- [ ] **Step 3: Create `swingbot/commands/scanning/outlook.py`**

```python
"""v144: post the next-session outlook and its wrap-up (the Discord side).

The scan itself is core (scanning/outlook_run.py), run off the event loop and
under the same scan lock every other scan holds. A failing scan still posts a
digest saying "Outlook unavailable", and issues nothing. Everything goes to the
alerts channel (silenced, like every alert there); cards go through
_send_alerts, so they get the plan buttons and the simple-channel mirror.
"""
import asyncio
import logging

from swingbot import config
from swingbot.bot_core import bot
from swingbot.core.infra.logsetup import new_scan_id, scan_context
from swingbot.core.infra.silent_channel import silence
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.presentation.kinds import Kind
from swingbot.core.scanning import outlook_embeds, outlook_run, outlook_session, scan_run
from swingbot.core.scanning.outlook_types import OutlookResult

from . import notices
from .alerts import _send_alerts

log = logging.getLogger(__name__)


def _alerts_channel():
    cid = config.DISCORD_CHANNEL_TRADES_ID
    return silence(bot.get_channel(int(cid))) if cid else None


def _safe_outlook(run_date) -> OutlookResult:
    try:
        return outlook_run.run_outlook(run_date)
    except Exception as exc:
        log.exception("next_session_scan: the outlook scan failed")
        return OutlookResult(run_date=run_date, target=outlook_session.target_session(run_date),
                             unavailable=f"scan failed ({type(exc).__name__}: {exc})"[:300])


def digest_embeds(result: OutlookResult) -> list:
    detail = result.target.strftime("%A") if result.target else "no session"
    return [notices.system_embed(Kind.OUTLOOK, detail, chunk)
            for chunk in notices.chunk_text(outlook_embeds.digest_text(result))]


async def run_next_session_outlook(run_date) -> OutlookResult | None:
    channel = _alerts_channel()
    if channel is None:
        log.warning("next_session_scan: DISCORD_CHANNEL_TRADES_ID not set or channel not found; no outlook posted")
        return None
    with scan_context(new_scan_id()):
        async with scan_run._scan_lock:
            result = await asyncio.to_thread(_safe_outlook, run_date)
    for embed in digest_embeds(result):
        await notices.send_guarded(channel, embed, what="outlook digest")
    if result.alerts:
        await _send_alerts(channel, result.alerts)
    log.info("next_session_scan: %s -> %d plan(s), %d watch, %d near-miss(es)%s", run_date,
             len(result.plans), len(result.watch), len(result.near_misses),
             f" (unavailable: {result.unavailable})" if result.unavailable else "")
    return result


async def post_wrapup_when_terminal(day) -> bool:
    """Post D's wrap-up once none of its outlook plans is still PENDING.
    True = done (posted, or nothing to post); False = ask again next minute."""
    plans = await asyncio.to_thread(PlanStore().for_session, day)
    if any(plan.status == PlanStatus.PENDING for plan in plans):
        return False
    if not plans:
        return True
    channel = _alerts_channel()
    if channel is None:
        log.warning("next_session_wrapup: no alerts channel; %s's wrap-up not posted", day)
        return True
    for chunk in notices.chunk_text(outlook_embeds.wrapup_text(day, plans)):
        await notices.send_guarded(channel, notices.system_embed(Kind.OUTLOOK_WRAPUP, day.strftime("%A"), chunk),
                                   what="outlook wrap-up")
    return True
```

- [ ] **Step 4: The loops.** In `swingbot/commands/scanning/loops.py`:
  1. Change `from . import notices, presence, recap, runstate` to `from . import notices, outlook, presence, recap, runstate`, and add `from swingbot.core.scanning import outlook_session` beside the other `swingbot.core` imports.
  2. After `weekend_deep_scan_task` (and before `weekly_earnings_refresh`), add:

```python
_next_session_fired_date: dt.date | None = None   # process-local fast path; persisted below


def _outlook_now() -> dt.datetime:
    """v144: the outlook loops' Berlin clock. A function so tests can set it
    without replacing datetime.datetime for every module."""
    return dt.datetime.now(SESSION_TZ)


def _scheduled_job_fired_since(job: str, day: dt.date) -> bool:
    """v144: True when `job` already fired for `day` or a later one (ISO dates
    order lexically). Lets one job own a run date that is not today."""
    from swingbot.core.db.repositories.scheduled import scheduled_repo
    fired = scheduled_repo().fired_on(job)
    return fired is not None and fired >= day.isoformat()


@tasks.loop(minutes=1)
async def next_session_scan():
    """v144: the 23:30 outlook, Sunday-Thursday, same minute-poll + persisted
    fired-once guard as weekend_deep_scan_task. A slot missed while the bot was
    down fires late, but never after the RTH open of the session it targets:
    then it is marked done and logged, so it is skipped exactly once."""
    global _next_session_fired_date
    if not config.NEXT_SESSION_SCAN_ENABLED:
        return
    now = _outlook_now()
    run_date = outlook_session.latest_slot_date(now, outlook_session.parse_slot(config.NEXT_SESSION_SCAN_TIME))
    if (run_date is None or _next_session_fired_date == run_date
            or _scheduled_job_fired_since('next_session_scan', run_date)):
        return
    _next_session_fired_date = run_date
    _mark_scheduled_job_fired('next_session_scan', run_date)
    if not outlook_session.fire_allowed(now, run_date):
        log.warning("next_session_scan: %s's outlook skipped -- its session's RTH open has passed", run_date)
        return
    try:
        await outlook.run_next_session_outlook(run_date)
    except Exception:
        log.exception("next_session_scan: outlook failed")


@tasks.loop(minutes=1)
async def next_session_wrapup():
    """v144: the outlook wrap-up, 15 minutes after each session's official close
    (ET, half-day aware), posted once every outlook plan of that session is
    terminal. A session still owing one after a restart is retried each minute."""
    now = _outlook_now()
    for day in outlook_session.wrapup_candidates(now):
        if not outlook_session.wrapup_due(now, day) or _scheduled_job_fired_since('next_session_wrapup', day):
            continue
        try:
            done = await outlook.post_wrapup_when_terminal(day)
        except Exception:
            log.exception("next_session_wrapup: wrap-up for %s failed", day)
            continue
        if done:
            _mark_scheduled_job_fired('next_session_wrapup', day)
```

  3. In `_always_on_loops`, append `next_session_scan, next_session_wrapup` to the returned tuple after `pitr_watch_loop`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/commands/test_outlook_loops.py`. Expected: PASS.
Then `python scripts/dev/testrun.py file tests/commands/test_scheduled_jobs.py`, `python scripts/dev/testrun.py file tests/commands/test_scheduled_jobs_db.py`, `python scripts/dev/testrun.py file tests/commands/test_pitr_watch_loop.py`, `python scripts/dev/testrun.py file tests/commands/test_scanning_package.py`. Expected: all PASS.

- [ ] **Step 6: Complexity check and commit**

Run: `python -m radon cc -s -n C swingbot/commands/scanning/outlook.py swingbot/commands/scanning/loops.py`. Expected: no new line (`next_session_scan` is B).

```bash
git add swingbot/commands/scanning/outlook.py swingbot/commands/scanning/loops.py tests/commands/test_outlook_loops.py
git commit -m "feat(v144): next_session_scan and next_session_wrapup loops

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 5 — Verification

### Task V144-13: Full-suite verification

**Files:** none edited unless the run names a regression.

- [ ] **Step 1: Confirm every task landed.** In the worktree:

```bash
git log --oneline main..HEAD
for f in docs/superpowers/plans/2026-10-09-v144-next-session-plans_*.md; do
  echo "$(basename $f): $(grep -o '^### Task V144-[0-9]*' $f | tr '\n' ' ')"
done
```

Expected: 12 feature commits (V144-1 .. V144-12) and the task ids V144-1 .. V144-13 across the parts, none missing.

- [ ] **Step 2: Complexity gate over every file the plan touched**

```bash
python -m radon cc -s -n C $(git diff --name-only main...HEAD -- '*.py' | grep -v '^tests/')
```

Expected:
- The only C-or-worse lines are the pre-existing ones named in the index's Global Constraints, at their recorded grades: `_sync_run_scan` F (100), `build_embed` E (33), `log_trade` C (15), `_on_event` C (15), `dashboard` D (25), `_realized` C (16), `instruction_for` C (13), plus `plan_manager.py`'s pre-existing `_step_active`, `poll`, `_feed_bookkeeping`, `_step_partial`, `_check_bar_active`.
- Nothing new.

- [ ] **Step 3: The full suite, once.** Dispatch the `test-runner` subagent (or run `python scripts/dev/testrun.py full`) over the worktree. Expected: `0 failed`, `0 xfailed`. A changed pass count is not a failure. **If it is not green, fix forward from the failures it names**: they are this plan's regressions, and this task is not done until the run is green. The plan touches no `frontend/` file, so there is no Angular run.

- [ ] **Step 4: Hand off for close-out.** Report to the controller:
  - the suite verdict;
  - the Alembic head (`python -m alembic heads` prints `v144_001 (head)`);
  - that the feature ships inert (`NEXT_SESSION_SCAN_ENABLED=false`).

  The merge, the `bot minor` bump with its `version_history.json` regeneration, and the plan's move to `implemented/` are the `close-out` skill's job. Enabling the flag on production is the partner's decision, made through `mirror-prod`.
