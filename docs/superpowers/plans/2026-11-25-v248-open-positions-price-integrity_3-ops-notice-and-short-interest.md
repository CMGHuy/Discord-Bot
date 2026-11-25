# v248 — Open-positions price integrity — Part 3: the held-price ops notice and the short-interest pool fix

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V248-8" -A 400 <this file>`); never read the file whole.

**Spec:** [2026-11-25-v248-open-positions-price-integrity-design.md](../specs/2026-11-25-v248-open-positions-price-integrity-design.md) § 5 (ops notice: stale held price during the regular session), § 6 (short-interest job fits its pool), and the § Testing rows 5 and 6.
**Index:** [2026-11-25-v248-open-positions-price-integrity_0-index.md](2026-11-25-v248-open-positions-price-integrity_0-index.md) — Goal, Global Constraints, Review Focus, Parallelisation, the task ledger and the binding "Decisions the spec left open" (8 and 10 govern this part) live there; every task below implicitly includes them.
**Brief:** `.superpowers/briefs/2026-11-25-v248-open-positions-price-integrity.md` §3m (ops_watch pattern), §3n (short interest), §4 (ops-watch and short-interest test patterns), §7 traps.

Tasks: V248-7 (pure verdict, lines, embed), V248-8 (`held_price_watch` loop), V248-9 (short interest).

Order: V248-4 (part 2) → V248-7 → V248-8: both read `config.HELD_PRICE_STALE_ALERT_MIN`, and V248-8 consumes V248-7's verdict, `HeldPriceItem`, `held_price_lines` and `notices.held_price_embed` from the same file. **V248-9 is independent** of every other task and may run at any time.

Decisions made in this part (within the ledger):
- **The tick runs only when `admin_refresh.refresher_on()`.** The never-fetch door (`market_values.read_quotes`) is filled by the refresher; with it off the door is empty and every held ticker would read as unpriced, which is exactly the spurious notice § Rollout 3 forbids.
- **The verdict is per ticker and pure.** `age_s` is the age of the *live trade* price: `None` whenever the quote has no price (a bid/ask-only doc such as DOCU's still carries an `age_s` from `quote_at`; that age is ignored). Boot grace = `threshold_min` minutes of uptime, as `stale_scan_verdict` does with its threshold. A recovery is "a live trade no older than the threshold". After its one recovery a ticker stays quiet for the rest of the session day.
- **The ops-notice store rows** use the same row shape as part 2's `yf_backoff` rows: `{"key", "kind": "ops_held_price", "symbol", "fetched_at": now, "source": "ops_watch", "value": {"notified_at": iso, "recovered_at": iso | None}}`, read back as `record["value"]`.
- **Post first, then write the dedupe row** (the `scan_watchdog` order): a failed send raises, writes nothing, and the next tick retries. A failed write after a good send is logged at WARNING; the next tick may repeat that one notice.
- **Short-interest summary text** comes from a new pure `short_interest.summary_line(result, total) -> tuple[int, str]` so it is unit-tested beside the module; `loops.daily_short_interest_refresh` only logs it (Decision 10: the summary stays in the loop).

Tests here use in-memory fakes only (no Postgres): `tests/scanning/test_ops_watch.py`, `tests/commands/test_loop_guard.py`, `tests/market/test_short_interest.py`. The one DB-backed neighbour, `tests/commands/test_scheduled_jobs.py`, runs after `/replicate-prod-db` in the shared `swing-db` container. Every command runs from the worktree root.

---

# Phase 4 — An operator hears about a blind held price before the partner sees it

### Task V248-7: Ops held-price verdict (truth table), phone-readable lines, embed

**Model:** sonnet — a pure verdict, a line formatter and one embed builder in the existing ops-watch pattern, pinned by a truth table; no I/O.

**Files:**
- Modify: `swingbot/commands/scanning/ops_watch.py` (new section after `provider_verdict`, before the `# --- v148 OH18` divider; three new imports)
- Modify: `swingbot/commands/scanning/notices.py` (new builder after `provider_recovered_embed`, end of file)
- Test: `tests/scanning/test_ops_watch.py` (append a `# --- v248` section)

**Interfaces:**
- Consumes: `session.now_et(now)`, `session.NYSE_HOLIDAYS`, `session.RTH_OPEN` (`swingbot/core/market/session.py:30, 126, 19`); `notices.system_embed(kind, detail, description)`; `Kind.HEALTH_ALERT`, `Kind.HEALTH_RECOVERED`. `config.HELD_PRICE_STALE_ALERT_MIN` (V248-4) is read by V248-8 and passed in here as `threshold_min`.
- Produces (V248-8):
  - `ops_watch.PRE_OPEN_AT = dt.time(9, 0)`; `ops_watch.ERROR_CHARS = 60`
  - `@dataclass(frozen=True) class HeldPriceItem: symbol: str; age_s: float | None; error: str | None; prev_close: bool; no_price: bool`
  - `held_price_verdict(*, session: str, age_s: float | None, has_last_close: bool, uptime_s: float, threshold_min: int, notified: bool, recovered: bool, pre_open: bool) -> str | None` — `"alert"`, `"recover"` or `None`
  - `held_price_lines(items: Sequence[HeldPriceItem], *, limit: int = 10) -> list[str]`
  - `in_pre_open_window(now: dt.datetime) -> bool`
  - `notices.held_price_embed(lines: list[str], *, recovery: bool)` (a `system_embed` PushEmbed)

**Why.** Spec § 5: one Discord line per held ticker whose live trade price is stale (older than `HELD_PRICE_STALE_ALERT_MIN`, default 10 min) or absent during the regular session; a held ticker with no price at all (no live trade, no `last_close`) is paged on first sight; before the open only the 09:00–09:30 ET pre-open window pages, and only no-price-at-all tickers (index Decision 8); once per ticker per session day, plus one recovery. This task is the pure half: the truth table and the text. V248-8 does the reading, the dedupe store and the posting.

**Verdict rule** (the one algorithm the signature leaves open; implement exactly this order):

```
threshold_s = threshold_min * 60
fresh = age_s is not None and age_s <= threshold_s
if notified:
    return "recover" if fresh and not recovered else None      # one recovery, then quiet all day
if age_s is None and not has_last_close:                       # no price at all
    return "alert" if session == "regular" or pre_open else None   # bypasses age and uptime
if session != "regular" or uptime_s < threshold_s:
    return None
return None if fresh else "alert"                              # stale live trade, or on prev close
```

`session` is compared with `session.SESSION_REGULAR` (`"regular"`). Split it into two small helpers if that reads better; it must stay < 15. Note the keyword `session` shadows the module name inside this function only: import the constant as `from swingbot.core.market.session import SESSION_REGULAR` or compare with the module attribute captured at module level (`_REGULAR = session.SESSION_REGULAR`).

**Line format** (exact copy; `•` is U+2022 and `·` U+00B7, as in the existing ops notices):

- `• <SYM> · last trade <age>` when `age_s` is set, else `• <SYM> · no live trade`;
- then ` · prev close` when `prev_close`, or ` · no price at all` when `no_price`;
- then ` · <error>` when `error` is set: whitespace collapsed to single spaces (`" ".join(error.split())`), and when longer than `ERROR_CHARS` cut to `error[:ERROR_CHARS - 1] + "…"` (exactly 60 characters);
- `<age>`: `N s ago` under 60 s; `N min ago` under 120 min; `N h ago` under 48 h; else `N d ago` (all floors);
- more than `limit` items: the first `limit` lines, then one line `+N more`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/scanning/test_ops_watch.py` (`dt`, `pytest`, `NOW`, `notices`, `ops_watch`, `kinds`, `Kind` are already imported or defined at the top of the file):

```python
# --- v248 § 5: held-price verdict, lines and embed ---------------------------------

def _held(**kw):
    base = dict(session="regular", age_s=11 * 60, has_last_close=True, uptime_s=3600,
                threshold_min=10, notified=False, recovered=False, pre_open=False)
    return ops_watch.held_price_verdict(**{**base, **kw})


@pytest.mark.parametrize("kwargs, expected", [
    ({}, "alert"),                                                    # live trade 11 min old
    ({"age_s": 600}, None),                                           # exactly 10 min: not older
    ({"age_s": 30}, None),
    ({"age_s": None}, "alert"),                                       # prev close in the session
    ({"session": "extended"}, None),
    ({"session": "closed"}, None),
    ({"session": "extended", "age_s": None}, None),                   # prev close pre-market is normal
    ({"session": "extended", "age_s": None, "pre_open": True}, None), # ... even at 09:00 ET
    ({"session": "extended", "pre_open": True}, None),                # a stale trade pre-open: not paged
    ({"uptime_s": 599}, None),                                        # boot grace
    ({"uptime_s": 600}, "alert"),                                     # up exactly the threshold
    ({"age_s": None, "uptime_s": 599}, None),                         # prev close keeps the grace
    ({"age_s": None, "has_last_close": False, "uptime_s": 5}, "alert"),   # no price at all: first sight
    ({"age_s": None, "has_last_close": False, "session": "extended"}, None),
    ({"age_s": None, "has_last_close": False, "session": "extended", "pre_open": True}, "alert"),
    ({"age_s": None, "has_last_close": False, "session": "closed", "pre_open": True}, "alert"),
    ({"notified": True}, None),                                       # once per ticker per day
    ({"notified": True, "age_s": None}, None),                        # still blind
    ({"notified": True, "age_s": 30}, "recover"),
    ({"notified": True, "age_s": 600}, "recover"),                    # at the line counts as fresh
    ({"notified": True, "age_s": 30, "session": "extended"}, "recover"),
    ({"notified": True, "recovered": True, "age_s": 30}, None),       # one recovery only
    ({"notified": True, "recovered": True, "age_s": 3600}, None),     # no second alert that day
    ({"threshold_min": 30}, None),                                    # hot-reloaded threshold
    ({"threshold_min": 30, "age_s": 31 * 60}, "alert"),
])
def test_held_price_verdict(kwargs, expected):
    assert _held(**kwargs) == expected


@pytest.mark.parametrize("utc, expected", [
    (dt.datetime(2026, 11, 25, 14, 0, tzinfo=dt.timezone.utc), True),    # Wed 09:00 ET (EST)
    (dt.datetime(2026, 11, 25, 13, 59, tzinfo=dt.timezone.utc), False),  # 08:59 ET
    (dt.datetime(2026, 11, 25, 14, 29, tzinfo=dt.timezone.utc), True),   # 09:29 ET
    (dt.datetime(2026, 11, 25, 14, 30, tzinfo=dt.timezone.utc), False),  # 09:30: the open
    (dt.datetime(2026, 10, 12, 13, 5, tzinfo=dt.timezone.utc), True),    # Mon 09:05 ET (EDT)
    (dt.datetime(2026, 11, 27, 14, 5, tzinfo=dt.timezone.utc), True),    # half-day still opens 09:30
    (dt.datetime(2026, 11, 26, 14, 5, tzinfo=dt.timezone.utc), False),   # Thanksgiving
    (dt.datetime(2026, 11, 28, 14, 5, tzinfo=dt.timezone.utc), False),   # Saturday
])
def test_in_pre_open_window(utc, expected):
    assert ops_watch.in_pre_open_window(utc) is expected


def _item(sym, age_s=None, error=None, prev_close=False, no_price=False):
    return ops_watch.HeldPriceItem(sym, age_s, error, prev_close, no_price)


def test_held_price_lines_read_one_ticker_per_line():
    assert ops_watch.held_price_lines([
        _item("AAPL", age_s=14 * 60 + 5, error="no quote"),
        _item("DOCU", prev_close=True, error="no quote"),
        _item("NEWCO", no_price=True),
        _item("SNDK", age_s=12),
    ]) == [
        "• AAPL · last trade 14 min ago · no quote",
        "• DOCU · no live trade · prev close · no quote",
        "• NEWCO · no live trade · no price at all",
        "• SNDK · last trade 12 s ago",
    ]


@pytest.mark.parametrize("age_s, text", [
    (59, "59 s ago"), (60, "1 min ago"), (119 * 60 + 59, "119 min ago"),
    (120 * 60, "2 h ago"), (47 * 3600 + 59 * 60, "47 h ago"), (48 * 3600, "2 d ago"),
])
def test_held_price_line_ages(age_s, text):
    assert ops_watch.held_price_lines([_item("AAPL", age_s=age_s)]) == [f"• AAPL · last trade {text}"]


def test_a_long_error_is_cut_to_sixty_characters_on_one_line():
    error = "YFPricesMissingError('possibly delisted;\n  no price data found (period=1d)') and more"
    (line,) = ops_watch.held_price_lines([_item("DOCU", prev_close=True, error=error)])
    tail = line.split(" · ", 3)[3]
    assert len(tail) == 60 and tail.endswith("…") and "\n" not in line
    assert tail.startswith("YFPricesMissingError('possibly delisted; no price data")


def test_an_error_of_exactly_sixty_characters_is_kept_whole():
    (line,) = ops_watch.held_price_lines([_item("DOCU", prev_close=True, error="e" * 60)])
    assert line.endswith(" · " + "e" * 60)


def test_more_than_ten_tickers_end_with_a_count():
    lines = ops_watch.held_price_lines([_item(f"T{i:02d}", no_price=True) for i in range(13)])
    assert len(lines) == 11 and lines[9].startswith("• T09 ") and lines[10] == "+3 more"
    assert len(ops_watch.held_price_lines([_item(f"T{i}", no_price=True) for i in range(10)])) == 10
    assert ops_watch.held_price_lines([]) == []


def test_the_held_price_alert_and_recovery_embeds():
    alert = notices.held_price_embed(["• DOCU · no live trade · prev close"], recovery=False)
    assert alert.push_text.startswith(f"{kinds.badge(Kind.HEALTH_ALERT)} SYSTEM · {Kind.HEALTH_ALERT.label}")
    assert alert.color.value == kinds.HEALTH_RED
    assert "held position price stale" in alert.title
    assert alert.description.startswith("• DOCU · no live trade · prev close\n")
    assert "No trade is changed" in alert.description

    rec = notices.held_price_embed(["• DOCU · last trade 12 s ago"], recovery=True)
    assert rec.color.value == kinds.HEALTH_GREEN
    assert "held position price live again" in rec.title
    assert rec.description == "• DOCU · last trade 12 s ago"
```

(2026-11-27 is the day after Thanksgiving, an NYSE early close: `session.is_early_close` covers it, and its pre-open still pages.)

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_ops_watch.py`
Expected: FAIL — `AttributeError: module 'swingbot.commands.scanning.ops_watch' has no attribute 'held_price_verdict'` (likewise `HeldPriceItem`, `in_pre_open_window`, `held_price_lines`, `notices.held_price_embed`); the existing tests still pass.

- [ ] **Step 3: Implement the pure half in `ops_watch.py`**

Add `from dataclasses import dataclass`, `from typing import Sequence` and `from swingbot.core.market import session` to the module imports (never `loops`: `test_ops_watch_never_imports_loops_at_module_level` guards that). New section `# --- v248 § 5: held-price verdict and lines ---` after `provider_verdict`:

- `PRE_OPEN_AT = dt.time(9, 0)` with `#: 30 min before the open, when resting orders are placed (spec § 5).`; `ERROR_CHARS = 60`.
- `HeldPriceItem` as in Interfaces; docstring: one held ticker as the notice shows it; `age_s` is the live trade's age, `None` when there is no live trade.
- `held_price_verdict(...)`: the verdict rule above; docstring names the three readings and that the caller passes `session.session_state(now)`.
- `in_pre_open_window(now)`: `et = session.now_et(now)`; False on a weekend or an `session.NYSE_HOLIDAYS` date; else `PRE_OPEN_AT <= et.time() < session.RTH_OPEN`.
- `held_price_lines(items, *, limit=10)`: the line format above, with private helpers `_age_words(age_s: float) -> str` and `_short_error(error: str) -> str`.

- [ ] **Step 4: Implement `notices.held_price_embed`**

Append to `swingbot/commands/scanning/notices.py`, after `provider_recovered_embed`:

```python
_HELD_PRICE_FOOTNOTE = ("No trade is changed: the panel shows the last trade or the previous "
                        "close. Check the refresher and the Alpaca feed.")


def held_price_embed(lines: list[str], *, recovery: bool):
    """v248 § 5: held tickers whose live price is stale or missing in the session,
    or their one recovery. `lines` come from ops_watch.held_price_lines."""
    body = "\n".join(lines)
    if recovery:
        return system_embed(Kind.HEALTH_RECOVERED, "held position price live again", body)
    return system_embed(Kind.HEALTH_ALERT, "held position price stale",
                        f"{body}\n{_HELD_PRICE_FOOTNOTE}")
```

- [ ] **Step 5: Run them to verify they pass, then the complexity gate**

Run: `python scripts/dev/testrun.py file tests/scanning/test_ops_watch.py`
Expected: PASS, `0 failed`.

Run: `python scripts/dev/complexity_gate.py`
Expected: no new offender; `held_price_verdict` and `held_price_lines` below 15.

- [ ] **Step 6: Commit**

```bash
git add swingbot/commands/scanning/ops_watch.py swingbot/commands/scanning/notices.py tests/scanning/test_ops_watch.py
git commit -m "feat(v248): held-price ops verdict, phone lines and embed"
```

### Task V248-8: `held_price_watch` loop: read-only quotes, shared-store dedupe (restart-safe), pre-open check, guard + registration

**Model:** sonnet — an async tick and a guarded loop in the existing `scan_watchdog` pattern; the logic is V248-7's verdict, this task wires reads, a dedupe store and the post, all behind fakes.

**Files:**
- Modify: `swingbot/commands/scanning/ops_watch.py` (new section after `check_provider_health`; the guard line at EOF beside `scan_watchdog`'s; four new imports)
- Modify: `swingbot/commands/scanning/loops.py:1370-1376` (`_always_on_loops`: `ops_watch.held_price_watch` right after `ops_watch.scan_watchdog`)
- Test: `tests/scanning/test_ops_watch.py` (append), `tests/commands/test_loop_guard.py:98-104`

**Interfaces:**
- Consumes (V248-7): `HeldPriceItem`, `held_price_verdict(...)`, `held_price_lines(items, *, limit=10)`, `in_pre_open_window(now)`, `notices.held_price_embed(lines, *, recovery)`. (V248-4): `config.HELD_PRICE_STALE_ALERT_MIN`. (V248-1): `MarketQuote` gained a trailing `error_at` field with a default; build it by keyword. Existing: `market_values.read_quotes(symbols, *, kind=..., enqueue=True, now=None) -> dict[str, MarketQuote]` and `market_values.last_close_fields(symbols) -> {SYM: {"last_close", "last_close_date"}}` (`swingbot/admin/market_values.py:110, 135`); `admin_refresh.refresher_on()` (`swingbot/core/marketdata/shared/admin_refresh.py:40`); `market_shared_repo().read_entries(keys, *, conn) / .write_entries(rows, *, conn)` (`swingbot/core/db/repositories/market_shared.py:45, 56`); `side_connection()` (`swingbot/core/db/side_engine.py:86`); `trades_repo().open_trades()` (`swingbot/core/db/repositories/trades.py:18, 82`); `session.session_state`, `session.session_date`, `session.SESSION_REGULAR`; `_post(embed) -> bool`; `BOOTED_AT`.
- Produces: `async ops_watch.held_price_tick(now: dt.datetime | None = None) -> dict[str, list[str]]` (`{"alert": [...], "recover": [...]}`, the symbols actually posted, sorted); `@tasks.loop(minutes=2) ops_watch.held_price_watch`; `ops_watch.HELD_PRICE_KIND = "ops_held_price"`; `ops_watch.held_notice_key(symbol: str, day: str) -> str` → `"ops_held_price:<SYM>:<YYYY-MM-DD>"` (`day` = `session.session_date(now)`, the ET date); store value `{"notified_at": iso, "recovered_at": iso | None}`.

**Why.** Spec § 5 and Review Focus 3–4: the check runs every 2 min in the bot; it reads quotes with `read_quotes(enqueue=False)` so it never triggers a fetch or a budget take; the once-per-ticker-per-session-day dedupe and the recovery flag live in `market_cache` under kind `ops_held_price` so a deploy or restart does not re-notify; a busy side pool skips the tick; outside the regular session only the 09:00–09:30 ET pre-open window runs; and the whole tick is off while the refresher is off (the door would be empty and everything would look blind: part 3's header).

**Tick flow (the algorithm; keep every function < 15):**

```
now = now or utc now;  out = {"alert": [], "recover": []}
pre_open = in_pre_open_window(now);  state = session.session_state(now)
if not admin_refresh.refresher_on() or (state != SESSION_REGULAR and not pre_open): return out
symbols = await to_thread(_held_tickers);  if not symbols: return out
view = await to_thread(_read_held_view, symbols, now);  if view is None: return out   # busy pool
for verdict, items in _judge(symbols, view, now, state, pre_open).items():          # "alert" first
    if items and await _post(notices.held_price_embed(held_price_lines(items), recovery=verdict == "recover")):
        await to_thread(_mark_held, items, verdict, view, now)
        out[verdict] = [i.symbol for i in items];  log it (WARNING for alert, INFO for recover)
    elif items: log.warning("held price watch: %s verdict but no ops channel configured; not posted", verdict)
return out
```

Private helpers (names are this task's own; tests patch `_held_tickers`):

- `_held_tickers() -> list[str]`: `from swingbot.core.db.repositories import trades as trades_mod` **inside** the function; sorted unique upper-case tickers of `trades_mod.trades_repo().open_trades()`, falsy tickers dropped.
- `@dataclass(frozen=True) class _HeldView: quotes: dict; closes: dict; marks: dict` (`marks` = `{key: record}` from `read_entries`).
- `_read_held_view(symbols, now) -> _HeldView | None`: `from swingbot.admin import market_values` inside; `quotes = market_values.read_quotes(symbols, enqueue=False, now=now)`; `closes = market_values.last_close_fields([s for s in symbols if no priced quote])`; `marks` via `with side_connection() as conn: market_shared_repo().read_entries([held_notice_key(s, day) ...], conn=conn)`. Any `(DatabaseUnavailable, sa.exc.TimeoutError)` from these reads → `swallowed(log, "ops.held_price_watch.busy", exc, "held price watch: store busy, tick skipped", level=logging.INFO)` and `None`. Other exceptions propagate to the loop's guard.
- `_judge(symbols, view, now, state, pre_open) -> dict[str, list[HeldPriceItem]]`: per symbol build `HeldPriceItem(symbol, age_s=quote.age_s if quote has a price else None, error=quote.error if quote else None, prev_close=not live and symbol in closes, no_price=not live and symbol not in closes)` and call `held_price_verdict(session=state, age_s=item.age_s, has_last_close=symbol in view.closes, uptime_s=(now - BOOTED_AT).total_seconds(), threshold_min=int(config.HELD_PRICE_STALE_ALERT_MIN), notified=key in view.marks, recovered=bool(value.get("recovered_at")), pre_open=pre_open)`, where `value = (view.marks.get(key) or {}).get("value") or {}`. Returns `{"alert": [...], "recover": [...]}` in symbol order.
- `_mark_held(items, verdict, view, now) -> None`: one `write_entries` call with rows `{"key": held_notice_key(sym, day), "kind": HELD_PRICE_KIND, "symbol": sym, "fetched_at": now, "source": "ops_watch", "value": ...}`; alert → `{"notified_at": now.isoformat(), "recovered_at": None}`; recover → `{"notified_at": <stored notified_at, else now.isoformat()>, "recovered_at": now.isoformat()}`. Any exception → `swallowed(log, "ops.held_price_watch.write", exc, "held price watch: dedupe write failed; the next tick may repeat the notice", level=logging.WARNING)`.

- [ ] **Step 1: Write the failing tests**

At the top of `tests/scanning/test_ops_watch.py` add `import contextlib`, `import sqlalchemy as sa` and `from swingbot.core.db.engine import DatabaseUnavailable` (`asyncio`, `logging`, `config`, `loops`, `swallowed_mod`, `_FakeChannel` and the `channel` fixture already exist in the file). Append:

```python
# --- v248 § 5: held_price_watch -------------------------------------------------------

class _FakeShared:
    def __init__(self):
        self.rows = {}

    def read_entries(self, keys, *, conn):
        return {k: dict(self.rows[k]) for k in keys if k in self.rows}

    def write_entries(self, rows, *, conn):
        for row in rows:
            self.rows[row["key"]] = dict(row)


def _q(sym, price, age_s, error=None):
    from swingbot.admin.market_values import MarketQuote
    as_of = None if age_s is None else (NOW - dt.timedelta(seconds=age_s)).isoformat()
    return MarketQuote(symbol=sym, price=price, as_of=as_of, age_s=age_s, refreshing=False,
                       error=error)


@pytest.fixture
def held(monkeypatch):
    """AAPL's live trade is 14 min old; DOCU has bid/ask only (no trade) and a daily
    close; NEWCO has nothing at all. NOW is Mon 2026-10-12 11:00 ET, regular session."""
    from swingbot.admin import market_values as mv
    state = {"tickers": ["AAPL", "DOCU", "NEWCO"], "enqueue": [], "shared": _FakeShared(),
             "quotes": {"AAPL": _q("AAPL", 101.0, 14 * 60, "no quote"),
                        "DOCU": _q("DOCU", None, 15 * 3600, "no quote")},
             "closes": {"DOCU": {"last_close": 80.0, "last_close_date": "2026-10-09"}}}

    def read_quotes(symbols, *, kind=None, enqueue=True, now=None):
        state["enqueue"].append(enqueue)
        return {s: state["quotes"][s] for s in symbols if s in state["quotes"]}

    monkeypatch.setattr(mv, "read_quotes", read_quotes)
    monkeypatch.setattr(mv, "last_close_fields",
                        lambda symbols: {s: state["closes"][s] for s in symbols if s in state["closes"]})
    monkeypatch.setattr(ops_watch, "_held_tickers", lambda: list(state["tickers"]))
    monkeypatch.setattr(ops_watch, "market_shared_repo", lambda: state["shared"])
    monkeypatch.setattr(ops_watch, "side_connection", contextlib.nullcontext)
    monkeypatch.setattr(ops_watch, "BOOTED_AT", NOW - dt.timedelta(hours=2))
    monkeypatch.setattr(config, "HELD_PRICE_STALE_ALERT_MIN", 10)
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "on")
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    return state


def _held_tick(now=NOW):
    return asyncio.run(ops_watch.held_price_tick(now))


QUIET = {"alert": [], "recover": []}


def test_stale_and_blind_held_prices_alert_once_in_one_message(held, channel):
    assert _held_tick() == {"alert": ["AAPL", "DOCU", "NEWCO"], "recover": []}
    assert len(channel.sent) == 1
    embed = channel.sent[0]["embed"]
    assert "held position price stale" in embed.title
    assert embed.description.splitlines()[:3] == [
        "• AAPL · last trade 14 min ago · no quote",
        "• DOCU · no live trade · prev close · no quote",      # never a bid/ask midpoint
        "• NEWCO · no live trade · no price at all"]
    assert _held_tick() == QUIET and len(channel.sent) == 1
    row = held["shared"].rows["ops_held_price:AAPL:2026-10-12"]
    assert row["kind"] == "ops_held_price" and row["symbol"] == "AAPL" and row["source"] == "ops_watch"
    assert row["value"] == {"notified_at": NOW.isoformat(), "recovered_at": None}


def test_a_fresh_price_recovers_once_and_the_day_stays_quiet(held, channel):
    _held_tick()
    held["quotes"]["AAPL"] = _q("AAPL", 102.0, 12)
    assert _held_tick() == {"alert": [], "recover": ["AAPL"]}
    assert "held position price live again" in channel.sent[1]["embed"].title
    assert channel.sent[1]["embed"].description == "• AAPL · last trade 12 s ago"
    assert held["shared"].rows["ops_held_price:AAPL:2026-10-12"]["value"] == {
        "notified_at": NOW.isoformat(), "recovered_at": NOW.isoformat()}
    held["quotes"]["AAPL"] = _q("AAPL", 102.0, 40 * 60)       # stale again the same day
    assert _held_tick() == QUIET and len(channel.sent) == 2


def test_the_dedupe_survives_a_restart(held, channel, monkeypatch):
    _held_tick()
    fresh = _FakeChannel()
    monkeypatch.setattr(loops, "_ops_channel", lambda: fresh)
    monkeypatch.setattr(ops_watch, "BOOTED_AT", NOW)          # the bot just came back
    assert _held_tick() == QUIET and fresh.sent == []


def test_a_new_session_day_alerts_again(held, channel):
    _held_tick()
    assert _held_tick(NOW + dt.timedelta(days=1))["alert"] == ["AAPL", "DOCU", "NEWCO"]
    assert "ops_held_price:NEWCO:2026-10-13" in held["shared"].rows


def test_the_boot_grace_holds_back_all_but_no_price_at_all(held, channel, monkeypatch):
    monkeypatch.setattr(ops_watch, "BOOTED_AT", NOW - dt.timedelta(minutes=5))
    assert _held_tick() == {"alert": ["NEWCO"], "recover": []}


def test_the_tick_never_enqueues_a_fetch(held, channel):
    _held_tick()
    assert held["enqueue"] == [False]


def test_outside_the_session_only_the_pre_open_check_runs(held, channel):
    pre_market = dt.datetime(2026, 10, 12, 12, 0, tzinfo=dt.timezone.utc)    # 08:00 ET
    assert _held_tick(pre_market) == QUIET
    assert held["enqueue"] == [] and channel.sent == []
    pre_open = dt.datetime(2026, 10, 12, 13, 5, tzinfo=dt.timezone.utc)      # 09:05 ET
    assert _held_tick(pre_open) == {"alert": ["NEWCO"], "recover": []}       # DOCU on prev close: normal
    after_hours = dt.datetime(2026, 10, 12, 21, 0, tzinfo=dt.timezone.utc)   # 17:00 ET
    assert _held_tick(after_hours) == QUIET


def test_the_pre_open_check_is_quiet_on_an_nyse_holiday(held, channel):
    thanksgiving = dt.datetime(2026, 11, 26, 14, 5, tzinfo=dt.timezone.utc)
    assert _held_tick(thanksgiving) == QUIET and channel.sent == []


@pytest.mark.parametrize("exc", [DatabaseUnavailable("side engine backing off"),
                                 sa.exc.TimeoutError("QueuePool limit of size 1 overflow 1 reached")])
def test_a_busy_side_pool_skips_the_tick(held, channel, monkeypatch, exc):
    def busy():
        raise exc
    monkeypatch.setattr(ops_watch, "side_connection", busy)
    assert _held_tick() == QUIET and channel.sent == []


def test_the_tick_reads_nothing_with_the_refresher_off(held, channel, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "off")
    assert _held_tick() == QUIET
    assert held["enqueue"] == [] and channel.sent == []


def test_no_held_tickers_reads_no_quotes(held, channel):
    held["tickers"] = []
    assert _held_tick() == QUIET and held["enqueue"] == []


def test_no_ops_channel_posts_nothing_and_stores_nothing(held, monkeypatch):
    monkeypatch.setattr(loops, "_ops_channel", lambda: None)
    assert _held_tick() == QUIET and held["shared"].rows == {}


def test_twelve_blind_tickers_share_one_message(held, channel):
    held["tickers"] = [f"N{i:02d}" for i in range(12)]
    assert len(_held_tick()["alert"]) == 12 and len(channel.sent) == 1
    lines = channel.sent[0]["embed"].description.splitlines()
    assert lines[9].startswith("• N09 ") and lines[10] == "+2 more"
    assert len(held["shared"].rows) == 12                      # every ticker deduped, listed or not


def test_a_failed_send_stores_nothing_and_the_next_tick_retries(held, monkeypatch):
    monkeypatch.setattr(loops, "_ops_channel", lambda: _FakeChannel(fail=True))
    with pytest.raises(RuntimeError, match="discord down"):
        _held_tick()
    assert held["shared"].rows == {}
    good = _FakeChannel()
    monkeypatch.setattr(loops, "_ops_channel", lambda: good)
    assert _held_tick()["alert"] == ["AAPL", "DOCU", "NEWCO"] and len(good.sent) == 1


def test_a_raising_held_price_tick_leaves_the_loop_running(monkeypatch, caplog):
    async def boom(now=None):
        raise RuntimeError("db down")
    monkeypatch.setattr(ops_watch, "held_price_tick", boom)
    with caplog.at_level(logging.ERROR, logger=ops_watch.log.name):
        assert asyncio.run(ops_watch.held_price_watch.coro()) is None
    assert swallowed_mod.snapshot()["ops.held_price_watch"]["count"] == 1
    assert "held price watch tick failed" in caplog.text


def test_held_tickers_are_the_open_trades_upper_cased_and_unique(monkeypatch):
    from swingbot.core.db.repositories import trades as trades_mod

    class _Repo:
        def open_trades(self, *, conn=None):
            return [{"ticker": "docu"}, {"ticker": "AAPL"}, {"ticker": None}, {"ticker": "aapl"}]

    monkeypatch.setattr(trades_mod, "trades_repo", lambda: _Repo())
    assert ops_watch._held_tickers() == ["AAPL", "DOCU"]


def test_the_held_price_watch_runs_every_two_minutes_after_the_scan_watchdog():
    order = loops._always_on_loops()
    assert order.index(ops_watch.held_price_watch) == order.index(ops_watch.scan_watchdog) + 1
    assert ops_watch.held_price_watch.minutes == 2
```

In `tests/commands/test_loop_guard.py::test_every_background_loop_has_the_guard`, change `assert len(found) >= 17` to `assert len(found) >= 18` and add `assert "held_price_watch" in found` right after it.

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_ops_watch.py`
Expected: FAIL — `AttributeError: ... has no attribute '_held_tickers'` / `'held_price_tick'` / `'held_price_watch'`; V248-7's tests and the older ones still pass.

Run: `python scripts/dev/testrun.py file tests/commands/test_loop_guard.py`
Expected: FAIL on `assert "held_price_watch" in found`.

- [ ] **Step 3: Implement the tick, the loop and the guard in `ops_watch.py`**

Add the imports `import sqlalchemy as sa`, `from swingbot.core.db.engine import DatabaseUnavailable`, `from swingbot.core.db.repositories.market_shared import market_shared_repo`, `from swingbot.core.db.side_engine import side_connection` and `from swingbot.core.marketdata.shared import admin_refresh` (module level: the tests patch `ops_watch.market_shared_repo` and `ops_watch.side_connection`). Import `market_values` and the trades repository inside their helpers only.

New section `# --- v248 § 5: the held-price watch loop ---` after `check_provider_health`: `HELD_PRICE_KIND`, `held_notice_key`, `_STORE_BUSY = (DatabaseUnavailable, sa.exc.TimeoutError)`, `_held_tickers`, `_HeldView`, `_read_held_view`, `_held_item`, `_judge`, `_mark_held`, `held_price_tick` — all as in the tick flow and helper list above — then:

```python
@tasks.loop(minutes=2)
async def held_price_watch():
    """v248 § 5: a held position's live price stale or missing in the regular
    session, paged once per ticker per session day. Never raises."""
    try:
        await held_price_tick()
    except Exception as exc:
        swallowed(log, "ops.held_price_watch", exc, "held price watch tick failed",
                  level=logging.ERROR, exc_info=True)
```

At the end of the file, below `loop_guard.restart_on_error(scan_watchdog, "scan_watchdog")`, add `loop_guard.restart_on_error(held_price_watch, "held_price_watch")`.

- [ ] **Step 4: Register the loop**

In `swingbot/commands/scanning/loops.py::_always_on_loops`, insert `ops_watch.held_price_watch` immediately after `ops_watch.scan_watchdog`; `tape_feed` stays last (`tests/commands/test_scheduled_jobs.py::test_daily_short_interest_refresh_is_always_on_and_tape_feed_stays_last` pins that).

- [ ] **Step 5: Run them to verify they pass, then the neighbours and the gate**

Run: `python scripts/dev/testrun.py file tests/scanning/test_ops_watch.py`
Expected: PASS, `0 failed`.

Run: `python scripts/dev/testrun.py file tests/commands/test_loop_guard.py`
Expected: PASS, `0 failed`.

Run `/replicate-prod-db` once (shared `swing-db`, port 56789), then: `python scripts/dev/testrun.py file tests/commands/test_scheduled_jobs.py`
Expected: PASS, `0 failed` (the loop order test).

Run: `python scripts/dev/complexity_gate.py`
Expected: no new offender; `held_price_tick`, `_judge` and `_read_held_view` below 15.

- [ ] **Step 6: Commit**

```bash
git add swingbot/commands/scanning/ops_watch.py swingbot/commands/scanning/loops.py tests/scanning/test_ops_watch.py tests/commands/test_loop_guard.py
git commit -m "feat(v248): held_price_watch ops loop with restart-safe dedupe"
```

# Phase 5 — The nightly short-interest job keeps every symbol it can fetch

### Task V248-9: Short interest: workers = side-pool capacity, one serial retry pass, `retried`/`recovered` summary, 10 % WARNING

**Model:** sonnet — a worker count, one serial retry pass and a pure summary line in a self-contained module, with an exact-dict result change three existing tests pin.

**Files:**
- Modify: `swingbot/core/market/short_interest.py:139-171` (`_fetch_all`, `refresh_short_interest`; new `_fetch_one`, `_worker_count`, `_retry_serially`, `summary_line`)
- Modify: `swingbot/commands/scanning/loops.py:1074-1078` (`daily_short_interest_refresh` logs `summary_line`)
- Test: `tests/market/test_short_interest.py` (update l.71, l.75, l.190; append new tests)

**Interfaces:**
- Consumes: `side_engine.pool_limits() -> tuple[int, int]` (`swingbot/core/db/side_engine.py:30`; `(1, 1)` in the bot, `(1, 0)` in a spawned worker).
- Produces: `refresh_short_interest(symbols, *, now=None, fetch=None) -> {"updated": int, "failed": list[str], "retried": int, "recovered": int}`; `short_interest._worker_count() -> int`; `short_interest.FAILED_WARN_PCT = 10`; `short_interest.summary_line(result: dict, total: int) -> tuple[int, str]` (a `logging` level and the text). No other task consumes these.

**Why.** Spec § 6 and Cause 4: `_fetch_all` runs `ThreadPoolExecutor(max_workers=4)` against a side pool of 1+1 with a 0.25 s timeout, so every weekday about 30 of 92 symbols fail on `QueuePool limit of size 1 overflow 1 reached`. The workers drop to `max(1, sum(pool_limits()))` (2 in the bot); that lowers contention but other bot threads share the pool at 22:40 UTC, so the real fix is **one serial retry pass** over the symbols whose fetch returned `None`. The summary keeps its shape and adds `retried N, recovered M`; when `failed` is still above 10 % of the symbols it logs at WARNING, the check that the fix worked (§ Rollout 2). No pool size or timeout changes.

- [ ] **Step 1: Update the pinned result shapes and write the failing tests**

In `tests/market/test_short_interest.py` the three exact-dict asserts gain the two new keys (every failure is retried once, serially):

```python
# l.71
    assert si.refresh_short_interest(["gme", "BAD"], now=NOW, fetch=fetch) == {
        "updated": 1, "failed": ["BAD"], "retried": 1, "recovered": 0}
# l.75
    assert si.refresh_short_interest(["GME"], now=NOW, fetch=lambda t: 1 / 0) == {
        "updated": 0, "failed": ["GME"], "retried": 1, "recovered": 0}
# l.190
    assert si.refresh_short_interest(["GME"], now=NOW) == {
        "updated": 0, "failed": ["GME"], "retried": 1, "recovered": 0}
```

Append (add `import logging` and `import threading` at the top of the file):

```python
# --- v248 § 6: the job fits its pool -----------------------------------------------

@pytest.mark.parametrize("limits, workers", [((1, 1), 2), ((1, 0), 1), ((0, 0), 1)])
def test_workers_equal_the_side_pool_capacity(monkeypatch, limits, workers):
    from swingbot.core.db import side_engine
    monkeypatch.setattr(side_engine, "pool_limits", lambda: limits)
    assert si._worker_count() == workers


def test_the_parallel_pass_uses_the_pool_capacity(monkeypatch):
    from swingbot.core.db import side_engine
    monkeypatch.setattr(side_engine, "pool_limits", lambda: (1, 1))
    seen = []
    real = si.ThreadPoolExecutor

    def recording(max_workers=None, **kw):
        seen.append(max_workers)
        return real(max_workers=max_workers, **kw)

    monkeypatch.setattr(si, "ThreadPoolExecutor", recording)
    si.refresh_short_interest(["GME", "TSLA"], now=NOW, fetch=_parsed)
    assert seen == [2]


def test_a_failed_first_pass_is_retried_once_serially(monkeypatch):
    main = threading.get_ident()
    calls, retry_threads = [], []

    def flaky(ticker):
        calls.append(ticker)
        if ticker == "FLAKY" and calls.count("FLAKY") == 1:
            raise RuntimeError("QueuePool limit of size 1 overflow 1 reached")
        if ticker == "DEAD":
            if calls.count("DEAD") == 2:
                retry_threads.append(threading.get_ident())
            raise RuntimeError("no .info")
        if calls.count(ticker) == 2:
            retry_threads.append(threading.get_ident())
        return _parsed(ticker)

    result = si.refresh_short_interest(["GME", "FLAKY", "DEAD"], now=NOW, fetch=flaky)
    assert result == {"updated": 2, "failed": ["DEAD"], "retried": 2, "recovered": 1}
    assert sorted(calls) == ["DEAD", "DEAD", "FLAKY", "FLAKY", "GME"]    # each failure retried once
    assert calls[-2:] in (["FLAKY", "DEAD"], ["DEAD", "FLAKY"])           # the retry pass runs last
    assert retry_threads == [main, main]                                  # ... on the calling thread
    assert si.cached_short_interest("FLAKY") is not None


def test_nothing_is_retried_when_the_first_pass_succeeds():
    calls = []
    result = si.refresh_short_interest(["GME", "TSLA"], now=NOW,
                                       fetch=lambda t: calls.append(t) or _parsed(t))
    assert result == {"updated": 2, "failed": [], "retried": 0, "recovered": 0}
    assert sorted(calls) == ["GME", "TSLA"]


@pytest.mark.parametrize("result, total, level, text", [
    ({"updated": 65, "failed": ["X"] * 27, "retried": 30, "recovered": 3}, 92, logging.WARNING,
     "65 updated, 27 failed of 92 symbols, retried 30, recovered 3"),
    ({"updated": 83, "failed": ["X"] * 9, "retried": 12, "recovered": 3}, 92, logging.INFO,
     "83 updated, 9 failed of 92 symbols, retried 12, recovered 3"),       # 9.8 %: not above 10 %
    ({"updated": 9, "failed": ["X"], "retried": 1, "recovered": 0}, 10, logging.INFO,
     "9 updated, 1 failed of 10 symbols, retried 1, recovered 0"),         # exactly 10 %: not above
    ({"updated": 0, "failed": [], "retried": 0, "recovered": 0}, 0, logging.INFO,
     "0 updated, 0 failed of 0 symbols, retried 0, recovered 0"),          # no symbols: no division
    ({"updated": 2, "failed": []}, 2, logging.INFO,
     "2 updated, 0 failed of 2 symbols, retried 0, recovered 0"),          # an older result shape
])
def test_summary_line(result, total, level, text):
    assert si.summary_line(result, total) == (level, text)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_short_interest.py`
Expected: FAIL — the three updated asserts (`retried`/`recovered` missing), `AttributeError: ... has no attribute '_worker_count'` / `'summary_line'`, and `seen == [4]` in the pool test.

- [ ] **Step 3: Implement in `short_interest.py`**

- `_fetch_one(sym, fetch) -> tuple[str, dict | None]`: today's inner `one`, moved to module level unchanged (same `swallowed(..., "marketdata.short_interest.fetch", ..., level=logging.DEBUG)`).
- `_worker_count() -> int`: `from swingbot.core.db import side_engine` inside (keeps the module's import surface as today); `return max(1, sum(side_engine.pool_limits()))`; docstring: one worker per side-pool connection; contention with other bot threads remains, which the retry pass absorbs (v248 § 6).
- `_fetch_all(symbols, fetch)`: `with ThreadPoolExecutor(max_workers=_worker_count()) as pool: return list(pool.map(lambda s: _fetch_one(s, fetch), symbols))` (keyword `max_workers=` so the test's recorder sees it).
- `_retry_serially(symbols, fetch) -> list[tuple[str, dict | None]]`: `[_fetch_one(s, fetch) for s in symbols]` on the calling thread.
- `refresh_short_interest`: first pass `_fetch_all`; `retry = [s for s, r in first if r is None]`; `second = _retry_serially(retry, fetch)`; merge with the retry result winning (`results = dict(first); results.update(second)`), then the existing updated/failed split, cache write and `_drop_from_queue(updated)`; return `{"updated": len(updated), "failed": sorted(failed), "retried": len(retry), "recovered": sum(r is not None for _, r in second)}`. Keep it < 15: move the updated/failed split into a helper `_split(results, entries) -> tuple[list[str], list[str]]` if needed.
- `FAILED_WARN_PCT = 10` and:

```python
def summary_line(result: dict, total: int) -> tuple[int, str]:
    """v248 § 6: the nightly summary and its level -- WARNING while more than
    FAILED_WARN_PCT % of the symbols still failed after the retry pass."""
    failed = len(result.get("failed", []))
    text = (f"{result.get('updated', 0)} updated, {failed} failed of {total} symbols, "
            f"retried {result.get('retried', 0)}, recovered {result.get('recovered', 0)}")
    warn = total > 0 and failed * 100 > FAILED_WARN_PCT * total
    return (logging.WARNING if warn else logging.INFO), text
```

- [ ] **Step 4: Log it from the loop**

In `swingbot/commands/scanning/loops.py::daily_short_interest_refresh`, replace the `log.info("daily_short_interest_refresh: %d updated, %d failed of %d symbols", ...)` call with:

```python
        level, text = short_interest.summary_line(result, len(symbols))
        log.log(level, "daily_short_interest_refresh: %s", text)
```

(`tests/commands/test_scheduled_jobs.py` stubs `refresh_short_interest` with `{"updated": 2, "failed": []}`; `summary_line`'s `.get(..., 0)` keeps that stub valid.)

- [ ] **Step 5: Run them to verify they pass, then the loop's neighbour and the gate**

Run: `python scripts/dev/testrun.py file tests/market/test_short_interest.py`
Expected: PASS, `0 failed`.

Run `/replicate-prod-db` once if no sibling task did this session (shared `swing-db`, port 56789), then: `python scripts/dev/testrun.py file tests/commands/test_scheduled_jobs.py`
Expected: PASS, `0 failed`.

Run: `python scripts/dev/complexity_gate.py`
Expected: no new offender; `refresh_short_interest` below 15.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/market/short_interest.py swingbot/commands/scanning/loops.py tests/market/test_short_interest.py
git commit -m "fix(v248): short-interest job sized to the side pool, failures retried once"
```

