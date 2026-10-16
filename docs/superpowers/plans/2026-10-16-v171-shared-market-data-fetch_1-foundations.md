# v171 Shared market-data fetch. Part 1: foundations (V171-1..V171-6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task V171-3:" -A 300 docs/superpowers/plans/2026-10-16-v171-shared-market-data-fetch_1-foundations.md`.

**Spec:** [`docs/superpowers/specs/2026-10-16-v171-shared-market-data-fetch-design.md`](../specs/2026-10-16-v171-shared-market-data-fetch-design.md) (this part: D1 storage and Failure behaviour, D2 windows and the admin fresh rule, D6 budget and breaker, D9 counters, Rollout "one flag per part")
**Index:** [`2026-10-16-v171-shared-market-data-fetch_0-index.md`](2026-10-16-v171-shared-market-data-fetch_0-index.md) carries the header (`Bump`, `Edge`, `Screen`), `## Global Constraints`, `## Review Focus`, `## Parallelisation` and the task ledger. Every task below implicitly includes the Global Constraints; the ledger's names, signatures and paths are final.

**Paths.** `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree), `$WT` = `$R/.claude/worktrees/2026-10-16-v171-shared-market-data-fetch` (created in V171-1). Never `cd`; use `git -C $WT` and `python $WT/scripts/dev/testrun.py file <test>`. All file paths below are relative to `$WT`. After every task run `git -C $R status --short` and confirm the main tree is clean.

**Contracts this part fixes for the later parts** (inside the ledger; read once): The side engine runs in **`AUTOCOMMIT`** with `pool_pre_ping=False` and the statement timeout passed as a libpq startup option, so a cache hit is exactly one statement on the wire (no `BEGIN`/`COMMIT`, no ping, no `SET`). Every repository method is a single atomic statement. **The layer never takes a budget token or sets the router asker scope itself.** Tokens are taken by the provider calls inside `fetch` (router and `yf_safe`, V171-8), so one provider call costs one token; callers wrap `get` in V171-8's `router.asker_scope(asker)`. The layer turns a `budget.BudgetDeferred` raised by `fetch` into `budget-deferred` outcomes, so V171-8's `yf_safe.BudgetDeferred` must be that class (`from swingbot.core.marketdata.shared.budget import BudgetDeferred`). Spot metals (`spot_metals.is_spot_metal`) passed to `layer.get` bypass the cache entirely: fetched with the rest, never keyed, leased or written. `counters.warn_fail_open(operation, exc)` is the one rate-limited fail-open logger (one `log.warning` per minute per (operation, error class)); `budget` and `layer` use it.

# Phase 1 — Foundations: flags, types, tables, counters, budget, layer

### Task V171-1: Worktree; per-part flags and D2/D6 knobs in config and `.env.example`

**Model:** haiku — config fields copied from the Field pattern, values fixed by Global Constraints

**Files:**
- Modify: `swingbot/config.py` (Data Sources block, directly after the `SPOT_QUOTE_MAX_AGE_SECONDS` Field; `_MODE_VALUES` near line 1371)
- Modify: `.env.example` (Data Sources block, directly after `SPOT_QUOTE_MAX_AGE_SECONDS=900`)
- Create: `tests/test_config_v171_keys.py`

**Interfaces:**
- Consumes: `config.Field`, `config.FIELDS`, `config._MODE_VALUES`, `config._cast`, `config.searchable_attrs()` (all exist).
- Produces: the config attributes listed in the ledger row for V171-1. Every later task reads them as `config.<ATTR>` at call time (never cached at import), so a SIGHUP reload takes effect on the next call.

- [ ] **Step 1: Create the worktree**

Invoke the `worktree-lifecycle` skill. If `git -C $R worktree list` already shows `.claude/worktrees/2026-10-16-v171-shared-market-data-fetch`, reuse it and resume at its first uncommitted task. Otherwise:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot worktree add E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v171-shared-market-data-fetch -b 2026-10-16-v171-shared-market-data-fetch main
```

Expected: `Preparing worktree (new branch '2026-10-16-v171-shared-market-data-fetch')`. Confirm the Alembic head is still the one the plan assumes: `python -m alembic -c $WT/alembic.ini heads` prints `v146_001 (head)`. If it prints another head, record it in the index's `## Progress` block; V171-3 uses that id as `down_revision`.

- [ ] **Step 2: Write the failing test**

Create `tests/test_config_v171_keys.py`:

```python
"""v171: the shared market-data layer's flags and knobs (spec D2, D6, Rollout)."""
import pathlib

import pytest

from swingbot import config

REPO = pathlib.Path(__file__).resolve().parents[1]

#: attr -> (type, default). Key == attr for every v171 field. Dict order is the FIELDS order.
V171_FIELDS = {
    "MARKETDATA_LAYER": ("select", "off"),
    "DAILY_DELTA_FETCH": ("checkbox", "false"),
    "PLAN_REBUILD_ENABLED": ("checkbox", "false"),
    "TAPE_SHARED_ENABLED": ("checkbox", "false"),
    "MARKETDATA_PG_TIMEOUT_MS": ("number", "250"),
    "MARKETDATA_LEASE_SECONDS": ("number", "30"),
    "QUOTE_MAX_AGE_REQUOTE_S": ("number", "5"),
    "QUOTE_MAX_AGE_MONITOR_S": ("number", "15"),
    "QUOTE_MAX_AGE_SCAN_S": ("number", "15"),
    "QUOTE_MAX_AGE_DASHBOARD_S": ("number", "15"),
    "QUOTE_MAX_AGE_ADMIN_S": ("number", "60"),
    "INDEX_QUOTE_MAX_AGE_S": ("number", "60"),
    "EARNINGS_MAX_AGE_S": ("number", "21600"),
    "REBUILD_PRICE_MAX_AGE_S": ("number", "60"),
    "TAPE_STALE_FALLBACK_S": ("number", "180"),
    "ALPACA_BUDGET_PER_MINUTE": ("number", "150"),
    "YF_BUDGET_PER_MINUTE": ("number", "60"),
    "DELTA_WINDOW_MAX_DAYS": ("number", "30"),
    "ALPACA_ANCHOR_DATE": ("text", "2017-01-03"),
    "REANCHOR_WEEKDAY": ("number", "6"),
    "REANCHOR_HOUR": ("number", "4"),
    "TAPE_PROXY_SYMBOLS": ("text", "^GSPC=SPY,^NDX=QQQ,^DJI=DIA,^VIX=VIXY,SI=F=SLV"),
}


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


@pytest.mark.parametrize("attr", sorted(V171_FIELDS))
def test_field_is_a_hot_reloadable_excluded_data_sources_knob(attr):
    field = _field(attr)
    kind, default = V171_FIELDS[attr]
    assert (field.key, field.section, field.type, field.default) == (
        attr, "Data Sources", kind, default)
    assert field.hot_reloadable is True
    assert field.search_class == "excluded"
    assert attr not in config.searchable_attrs()
    assert "v171" in field.help


def test_fields_sit_together_after_the_spot_quote_age():
    attrs = [f.attr for f in config.FIELDS]
    start = attrs.index("SPOT_QUOTE_MAX_AGE_SECONDS") + 1
    assert attrs[start:start + len(V171_FIELDS)] == list(V171_FIELDS)


def test_layer_mode_is_off_count_on_and_a_typo_falls_back_to_off():
    field = _field("MARKETDATA_LAYER")
    assert [value for value, _label in field.options] == ["off", "count", "on"]
    assert config._MODE_VALUES["MARKETDATA_LAYER"] == ("off", "count", "on")
    assert config._cast(field, "COUNT") == "count"
    assert config._cast(field, "on") == "on"
    assert config._cast(field, "shadow") == "off"


@pytest.mark.parametrize("attr", sorted(V171_FIELDS))
def test_default_casts_to_the_documented_value(attr):
    field = _field(attr)
    kind, default = V171_FIELDS[attr]
    expected = {"number": int, "checkbox": lambda v: v == "true"}.get(kind, str)(default)
    assert config._cast(field, field.default) == expected


@pytest.mark.parametrize("attr", sorted(V171_FIELDS))
def test_env_example_lists_the_key_with_its_default(attr):
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    assert f"\n{attr}={V171_FIELDS[attr][1]}\n" in text


def test_module_attributes_exist():
    for attr in V171_FIELDS:
        assert hasattr(config, attr), attr
```

- [ ] **Step 3: Run it to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/test_config_v171_keys.py`
Expected: FAIL with `StopIteration` in `_field` (no such Field yet).

- [ ] **Step 4: Add the Fields to `swingbot/config.py`**

Insert directly after the `SPOT_QUOTE_MAX_AGE_SECONDS` Field, in this order (the order test pins it). Every field keeps the defaults `hot_reloadable=True`, `search_class="excluded"`. Help copy is exact:

```python
    Field("MARKETDATA_LAYER", "MARKETDATA_LAYER", "Data Sources",
          "Shared market-data layer", type="select", default="off",
          options=["off", "count", "on"],
          help="v171. 'off' = exact pre-v171 fetch paths, no layer code runs. 'count' = every "
               "Alpaca/yfinance call is made exactly as today and counted per hour by provider, "
               "kind, asker and outcome (the baseline week). 'on' = one shared, Postgres-"
               "coordinated cache with per-asker freshness windows, cross-process single-flight "
               "and one money-first budget. Production ships 'count'."),
    Field("DAILY_DELTA_FETCH", "DAILY_DELTA_FETCH", "Data Sources",
          "Daily bars: delta fetch + write-back", type="checkbox", default="false",
          help="v171 D3/D4. On: the scan keeps closed daily bars on disk (Alpaca-basis "
               "market_data/daily_alpaca for Alpaca symbols, market_data/daily for the rest), "
               "fetches only a short recent window per scan and full-refetches on any "
               "adjustment change. Off: today's crawl."),
    Field("PLAN_REBUILD_ENABLED", "PLAN_REBUILD_ENABLED", "Data Sources",
          "Rebuild plans from a last-second quote", type="checkbox", default="false",
          help="v171 D5. On: every main-scan and SHORT-lane plan is re-priced from a quote "
               "at most 5 s old right before it posts, and its price gates re-run."),
    Field("TAPE_SHARED_ENABLED", "TAPE_SHARED_ENABLED", "Data Sources",
          "Admin tape from the bot's shared copy", type="checkbox", default="false",
          help="v171 D7. On: the bot fetches the index tape once a minute into the shared "
               "cache, with labelled ETF change-% proxies when Yahoo is blank; the admin reads "
               "that copy."),
    Field("MARKETDATA_PG_TIMEOUT_MS", "MARKETDATA_PG_TIMEOUT_MS", "Data Sources",
          "Layer: Postgres timeout (ms)", type="number", default="250", min=50, max=5000, step=50,
          help="v171. Statement timeout for every shared-cache read, lease and budget call. "
               "Past it the asker fetches directly (fail open)."),
    Field("MARKETDATA_LEASE_SECONDS", "MARKETDATA_LEASE_SECONDS", "Data Sources",
          "Layer: fetch lease (s)", type="number", default="30", min=5, max=300, step=5,
          help="v171. How long one process's claim on a key lasts; a dead holder's claim "
               "expires after this."),
    Field("QUOTE_MAX_AGE_REQUOTE_S", "QUOTE_MAX_AGE_REQUOTE_S", "Data Sources",
          "Max quote age: pre-post re-quote (s)", type="number", default="5", min=1, max=60, step=1,
          help="v171 D2/D5. The re-quote right before a plan posts."),
    Field("QUOTE_MAX_AGE_MONITOR_S", "QUOTE_MAX_AGE_MONITOR_S", "Data Sources",
          "Max quote age: stop monitor (s)", type="number", default="15", min=1, max=120, step=1,
          help="v171 D2. Trade monitor and plan manager."),
    Field("QUOTE_MAX_AGE_SCAN_S", "QUOTE_MAX_AGE_SCAN_S", "Data Sources",
          "Max quote age: scan (s)", type="number", default="15", min=1, max=120, step=1,
          help="v171 D2. The scan's live-prices phase and the SHORT lane."),
    Field("QUOTE_MAX_AGE_DASHBOARD_S", "QUOTE_MAX_AGE_DASHBOARD_S", "Data Sources",
          "Max quote age: admin Dashboard (s)", type="number", default="15", min=1, max=300, step=1,
          help="v171 D2. The admin page that always shows the latest price."),
    Field("QUOTE_MAX_AGE_ADMIN_S", "QUOTE_MAX_AGE_ADMIN_S", "Data Sources",
          "Max quote age: other admin pages (s)", type="number", default="60", min=5, max=600, step=5,
          help="v171 D2. Watchlist, Trades, Risk, Charts; shown with its age."),
    Field("INDEX_QUOTE_MAX_AGE_S", "INDEX_QUOTE_MAX_AGE_S", "Data Sources",
          "Max index-tape quote age (s)", type="number", default="60", min=5, max=600, step=5,
          help="v171 D2/D7."),
    Field("EARNINGS_MAX_AGE_S", "EARNINGS_MAX_AGE_S", "Data Sources",
          "Max earnings-date age (s)", type="number", default="21600", min=600, max=172800, step=600,
          help="v171 D2. Earnings dates for the alert path and the admin (6 h)."),
    Field("REBUILD_PRICE_MAX_AGE_S", "REBUILD_PRICE_MAX_AGE_S", "Data Sources",
          "Rebuild: max trade/quote age (s)", type="number", default="60", min=5, max=600, step=5,
          help="v171 D5. A last trade, then a bid/ask midpoint, younger than this re-prices "
               "the plan; otherwise the scan price is kept and flagged 'price not confirmed live'."),
    Field("TAPE_STALE_FALLBACK_S", "TAPE_STALE_FALLBACK_S", "Data Sources",
          "Tape: admin self-fetch after (s)", type="number", default="180", min=60, max=1800, step=30,
          help="v171 D7. When the bot's shared tape entry is older than this, the admin "
               "fetches the tape itself at admin priority."),
    Field("ALPACA_BUDGET_PER_MINUTE", "ALPACA_BUDGET_PER_MINUTE", "Data Sources",
          "Shared Alpaca budget (calls/min)", type="number", default="150", min=10, max=10000, step=10,
          help="v171 D6. One bucket for every process on the Alpaca account. Stop monitoring, "
               "the re-quote and the scan never wait behind background or admin calls."),
    Field("YF_BUDGET_PER_MINUTE", "YF_BUDGET_PER_MINUTE", "Data Sources",
          "Shared yfinance budget (calls/min)", type="number", default="60", min=5, max=2000, step=5,
          help="v171 D6. One bucket for the VM's egress IP (bot and admin)."),
    Field("DELTA_WINDOW_MAX_DAYS", "DELTA_WINDOW_MAX_DAYS", "Data Sources",
          "Delta fetch: max window (days)", type="number", default="30", min=7, max=120, step=1,
          help="v171 D4. A longer gap since the last verified bar means a full refetch."),
    Field("ALPACA_ANCHOR_DATE", "ALPACA_ANCHOR_DATE", "Data Sources",
          "Alpaca cache: anchor bar date", default="2017-01-03",
          help="v171 D4. The Alpaca-basis cache's adjustment fingerprint is the first bar on "
               "or after this date; any change in its adjusted close forces a full refetch."),
    Field("REANCHOR_WEEKDAY", "REANCHOR_WEEKDAY", "Data Sources",
          "Weekly re-anchor: weekday (0=Mon)", type="number", default="6", min=0, max=6, step=1,
          help="v171 D4. Weekly full refetch of every watchlist symbol, outside session."),
    Field("REANCHOR_HOUR", "REANCHOR_HOUR", "Data Sources",
          "Weekly re-anchor: hour (Berlin)", type="number", default="4", min=0, max=23, step=1,
          help="v171 D4."),
    Field("TAPE_PROXY_SYMBOLS", "TAPE_PROXY_SYMBOLS", "Data Sources",
          "Tape ETF proxies (index=ETF,...)",
          default="^GSPC=SPY,^NDX=QQQ,^DJI=DIA,^VIX=VIXY,SI=F=SLV",
          help="v171 D7. Shown as change % only, labelled as a proxy, when Yahoo is blank for "
               "the index. The last '=' separates the ETF (so 'SI=F=SLV' maps SI=F to SLV)."),
```

Add `"MARKETDATA_LAYER": ("off", "count", "on"),` to `_MODE_VALUES` directly after the `"PLAN_ENGINE_V2"` entry. `_MODE_FALLBACK` needs no entry (its default is `"off"`).

- [ ] **Step 5: Add the keys to `.env.example`**

Directly after `SPOT_QUOTE_MAX_AGE_SECONDS=900`:

```
# --- v171 shared market-data layer (all hot-reloadable) ---
# off = exact pre-v171 paths; count = pass-through + hourly call counts; on = shared cache,
# cross-process single-flight, money-first budget. Each part has its own flag; off restores today.
MARKETDATA_LAYER=off
DAILY_DELTA_FETCH=false
PLAN_REBUILD_ENABLED=false
TAPE_SHARED_ENABLED=false
MARKETDATA_PG_TIMEOUT_MS=250
MARKETDATA_LEASE_SECONDS=30
# Freshness windows (s) per asker (spec D2)
QUOTE_MAX_AGE_REQUOTE_S=5
QUOTE_MAX_AGE_MONITOR_S=15
QUOTE_MAX_AGE_SCAN_S=15
QUOTE_MAX_AGE_DASHBOARD_S=15
QUOTE_MAX_AGE_ADMIN_S=60
INDEX_QUOTE_MAX_AGE_S=60
EARNINGS_MAX_AGE_S=21600
REBUILD_PRICE_MAX_AGE_S=60
TAPE_STALE_FALLBACK_S=180
# One budget per provider, shared by every process (calls/min)
ALPACA_BUDGET_PER_MINUTE=150
YF_BUDGET_PER_MINUTE=60
# Daily-bar delta fetch and the weekly full re-anchor (weekday 0=Mon, hour Berlin)
DELTA_WINDOW_MAX_DAYS=30
ALPACA_ANCHOR_DATE=2017-01-03
REANCHOR_WEEKDAY=6
REANCHOR_HOUR=4
# Tape ETF proxies, change % only; the last '=' separates the ETF
TAPE_PROXY_SYMBOLS=^GSPC=SPY,^NDX=QQQ,^DJI=DIA,^VIX=VIXY,SI=F=SLV
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/test_config_v171_keys.py`
Expected: PASS (all parametrised cases).
Run: `python $WT/scripts/dev/testrun.py file tests/infra/test_env_example_sync.py` and `python $WT/scripts/dev/testrun.py file tests/test_config_v162_keys.py`
Expected: PASS (the sync test sees every new key; `TRAINING_DATA_SOURCE` still sits right after the breaker cool-down).

- [ ] **Step 7: Commit**

```bash
git -C $WT add swingbot/config.py .env.example tests/test_config_v171_keys.py
git -C $WT commit -m "feat(v171): per-part flags and freshness/budget knobs for the shared market-data layer"
```

### Task V171-2: Layer types: data kinds, askers with priority and window, `Entry`, `QuoteDetail`, cache keys, fresh override

**Model:** sonnet — pure types in one new package, values fixed by the spec

**Files:**
- Create: `swingbot/core/marketdata/shared/__init__.py` (docstring only: "v171 shared market-data layer: kinds, counters, budget, layer, tape. Spec D1/D2/D6/D9.")
- Create: `swingbot/core/marketdata/shared/kinds.py`
- Create: `tests/marketdata/test_shared_kinds.py`

**Interfaces:**
- Consumes: the V171-1 knobs (`config.QUOTE_MAX_AGE_*_S`, `INDEX_QUOTE_MAX_AGE_S`, `EARNINGS_MAX_AGE_S`).
- Produces (exactly the ledger row): `DataKind`, `Asker` (`.priority`, `.window_s(kind)`), `PROVIDER_ALPACA`, `PROVIDER_YF`, `cache_key`, `Entry` (`.age_s`), `QuoteDetail` (`.mid`, `.to_doc`, `.from_doc`), `OUTCOMES`, `fresh_request`, `is_fresh_request`, `resolve_asker`. Plus the constant `INTRADAY_MAX_AGE_S = 4 * 3600` (today's `data_store.INTRADAY_MAX_AGE_SECONDS`, duplicated here only as the intraday window so this module imports nothing from `data_store`; V171-24 asserts the two agree).

Window table (`Asker.window_s(kind)`, read from config at call time). `None` = persistent, `0.0` = never served from cache:

| kind | STOP_MONITOR | REQUOTE | SCAN | BACKGROUND | ADMIN_DASHBOARD | ADMIN_PAGE | ADMIN_FRESH |
|---|---|---|---|---|---|---|---|
| `QUOTE` | `QUOTE_MAX_AGE_MONITOR_S` | `QUOTE_MAX_AGE_REQUOTE_S` | `QUOTE_MAX_AGE_SCAN_S` | `QUOTE_MAX_AGE_SCAN_S` | `QUOTE_MAX_AGE_DASHBOARD_S` | `QUOTE_MAX_AGE_ADMIN_S` | 0.0 |
| `INDEX_QUOTE` | `INDEX_QUOTE_MAX_AGE_S` for every asker | | | | | | 0.0 |
| `EARNINGS` | `EARNINGS_MAX_AGE_S` for every asker | | | | | | 0.0 |
| `INTRADAY_BARS` | `INTRADAY_MAX_AGE_S` for every asker | | | | | | 0.0 |
| `DAILY_BARS` | 0.0 for every asker (bars live on disk; the layer only leases their key, V171-12 owns freshness) | | | | | | 0.0 |
| `METADATA` | `None` for every asker, **including `ADMIN_FRESH`** (ticker metadata is persistent, D2; a reload must not refetch company names for a whole watchlist) | | | | | | `None` |

Implement it table-driven (one dict for the per-asker quote attrs, one for the per-kind attrs), so `window_s` stays at CC <= 4.

- [ ] **Step 1: Write the failing test**

Create `tests/marketdata/test_shared_kinds.py`:

```python
"""v171 D2/D6: data kinds, askers, priorities, windows, cache keys, quote shape."""
from datetime import datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.core.marketdata.shared import kinds
from swingbot.core.marketdata.shared.kinds import (
    OUTCOMES, Asker, DataKind, Entry, QuoteDetail, cache_key, fresh_request,
    is_fresh_request, resolve_asker)

T0 = datetime(2026, 10, 16, 14, 30, tzinfo=timezone.utc)


def test_kind_values_are_short_stable_strings():
    assert [k.value for k in DataKind] == ["quote", "daily", "intraday", "index", "earnings", "meta"]


def test_priorities_put_money_first():
    assert [a.priority for a in Asker] == [1, 2, 3, 4, 5, 5, 5]
    assert Asker.STOP_MONITOR.priority < Asker.REQUOTE.priority < Asker.SCAN.priority


@pytest.mark.parametrize("asker,attr", [
    (Asker.STOP_MONITOR, "QUOTE_MAX_AGE_MONITOR_S"), (Asker.REQUOTE, "QUOTE_MAX_AGE_REQUOTE_S"),
    (Asker.SCAN, "QUOTE_MAX_AGE_SCAN_S"), (Asker.BACKGROUND, "QUOTE_MAX_AGE_SCAN_S"),
    (Asker.ADMIN_DASHBOARD, "QUOTE_MAX_AGE_DASHBOARD_S"), (Asker.ADMIN_PAGE, "QUOTE_MAX_AGE_ADMIN_S"),
])
def test_quote_window_reads_the_askers_knob_at_call_time(monkeypatch, asker, attr):
    monkeypatch.setattr(config, attr, 7)
    assert asker.window_s(DataKind.QUOTE) == 7.0


def test_default_quote_windows_match_the_spec():
    assert Asker.REQUOTE.window_s(DataKind.QUOTE) == 5.0
    assert Asker.ADMIN_DASHBOARD.window_s(DataKind.QUOTE) == 15.0
    assert Asker.ADMIN_PAGE.window_s(DataKind.QUOTE) == 60.0


def test_other_kind_windows():
    assert Asker.SCAN.window_s(DataKind.INDEX_QUOTE) == 60.0
    assert Asker.STOP_MONITOR.window_s(DataKind.EARNINGS) == 21600.0
    assert Asker.ADMIN_PAGE.window_s(DataKind.INTRADAY_BARS) == float(kinds.INTRADAY_MAX_AGE_S)
    assert Asker.SCAN.window_s(DataKind.DAILY_BARS) == 0.0
    assert Asker.SCAN.window_s(DataKind.METADATA) is None


def test_fresh_asker_is_zero_except_for_persistent_metadata():
    for kind in (DataKind.QUOTE, DataKind.INDEX_QUOTE, DataKind.EARNINGS, DataKind.INTRADAY_BARS):
        assert Asker.ADMIN_FRESH.window_s(kind) == 0.0
    assert Asker.ADMIN_FRESH.window_s(DataKind.METADATA) is None


def test_cache_key_upper_cases_the_symbol():
    assert cache_key(DataKind.QUOTE, "aapl") == "quote:AAPL:"
    assert cache_key(DataKind.INTRADAY_BARS, "msft", "1h") == "intraday:MSFT:1h"


def test_entry_age():
    entry = Entry(value=1.0, fetched_at=T0, source="alpaca", outcome="hit")
    assert entry.age_s(T0 + timedelta(seconds=12.5)) == 12.5


def test_quote_mid_needs_a_sane_two_sided_quote():
    q = QuoteDetail("AAPL", 100.0, T0, 99.9, 100.1, T0, "alpaca-iex")
    assert q.mid() == pytest.approx(100.0)
    assert QuoteDetail("AAPL", None, None, None, 100.1, T0, "x").mid() is None
    assert QuoteDetail("AAPL", None, None, 0.0, 100.1, T0, "x").mid() is None
    assert QuoteDetail("AAPL", None, None, 100.2, 100.1, T0, "x").mid() is None   # crossed


def test_quote_doc_round_trip_keeps_timestamps():
    q = QuoteDetail("AAPL", 100.0, T0, 99.9, 100.1, T0 + timedelta(seconds=2), "alpaca-iex")
    doc = q.to_doc()
    assert doc["trade_at"] == T0.isoformat()
    assert QuoteDetail.from_doc(doc) == q
    empty = QuoteDetail("XYZ", None, None, None, None, None, "yfinance-1m")
    assert QuoteDetail.from_doc(empty.to_doc()) == empty


def test_outcomes_are_the_d9_set():
    assert OUTCOMES == ("hit", "shared-wait", "fetched", "budget-deferred", "failed")


def test_fresh_request_resolves_admin_askers_only():
    assert resolve_asker(Asker.ADMIN_PAGE) is Asker.ADMIN_PAGE
    with fresh_request():
        assert is_fresh_request() is True
        assert resolve_asker(Asker.ADMIN_PAGE) is Asker.ADMIN_FRESH
        assert resolve_asker(Asker.ADMIN_DASHBOARD) is Asker.ADMIN_FRESH
        assert resolve_asker(Asker.STOP_MONITOR) is Asker.STOP_MONITOR
    assert is_fresh_request() is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_shared_kinds.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.core.marketdata.shared'`.

- [ ] **Step 3: Implement `swingbot/core/marketdata/shared/kinds.py`**

- `DataKind(str, Enum)` and `Asker(str, Enum)` with the ledger's members in the ledger's order; `Asker` values are the lower-case member names (`"stop_monitor"`, ..., `"admin_fresh"`), which are also what D9 stores in the `asker` column.
- `Asker.priority` is a property over a module dict `{STOP_MONITOR: 1, REQUOTE: 2, SCAN: 3, BACKGROUND: 4, ADMIN_DASHBOARD: 5, ADMIN_PAGE: 5, ADMIN_FRESH: 5}`.
- `Asker.window_s(kind)`: `ADMIN_FRESH` returns `0.0` unless `kind is METADATA`; `METADATA` returns `None`; `DAILY_BARS` returns `0.0`; `QUOTE` looks up the per-asker attr dict; the rest look up the per-kind attr dict (`INTRADAY_BARS` maps to the module constant). Values are `float(getattr(config, attr))`.
- `Entry` and `QuoteDetail` are `@dataclass(frozen=True)` with the ledger's fields in that order. `Entry.age_s(now=None)` uses `datetime.now(timezone.utc)` when `now` is None. `QuoteDetail.mid()` returns `(bid + ask) / 2` only when both are `> 0` and `ask >= bid`. `to_doc()` writes every field, datetimes as `isoformat()` (None stays None); `from_doc` is a `@classmethod` parsing them back with `datetime.fromisoformat`.
- `_FRESH: ContextVar[bool] = ContextVar("marketdata_fresh", default=False)`; `fresh_request()` is a `@contextmanager` that sets it and resets the token in `finally`; `resolve_asker` maps `ADMIN_PAGE`/`ADMIN_DASHBOARD` to `ADMIN_FRESH` when `is_fresh_request()`.
- No import of `sqlalchemy`, `yfinance` or `alpaca`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_shared_kinds.py`
Expected: PASS.
Run: `python -m radon cc -s -n C $WT/swingbot/core/marketdata/shared/kinds.py`
Expected: no output (every function below C).

- [ ] **Step 5: Commit**

```bash
git -C $WT add swingbot/core/marketdata/shared/__init__.py swingbot/core/marketdata/shared/kinds.py tests/marketdata/test_shared_kinds.py
git -C $WT commit -m "feat(v171): shared-layer kinds, askers with priority and freshness window, quote detail"
```

### Task V171-3: Tables `market_cache`, `provider_budget`, `market_fetch_counts`; Alembic `v171_001`; repositories; per-process side engine with statement timeout

**Model:** opus — an Alembic revision plus a new connection path that must fail open

**Files:**
- Modify: `swingbot/core/db/schema.py` (three tables after `gate_rejections`; one `PROMOTION_REASONS` block per table)
- Create: `swingbot/core/db/migrations/versions/v171_001_market_shared.py`
- Create: `swingbot/core/db/side_engine.py`
- Create: `swingbot/core/db/repositories/market_shared.py`
- Create: `tests/db/test_market_shared_repository.py`
- Create: `tests/db/test_side_engine.py`
- Modify: `tests/db/test_unknown_field_round_trip.py` (three `CASES` rows; `test_every_table_is_covered_or_excused` fails without them)

**Interfaces:**
- Consumes: `config.DATABASE_URL`, `config.MARKETDATA_PG_TIMEOUT_MS` (V171-1); `schema.register`, `standard_columns`, `Repository`, `engine.DatabaseUnavailable` (exist).
- Produces: the three tables, `side_engine.side_connection()`, `side_engine.reset()`, `side_engine.pool_limits()`, `market_shared_repo()` and every `MarketSharedRepository` method with the ledger's exact signatures. Also `MarketSharedRepository.cache`, `.budget`, `.counts`: plain `Repository` objects over each table (the round-trip test and V171-34's report read through them).

Row shapes (flat dicts in and out, `merge_doc` style): a `market_cache` record is `{"key", "kind", "symbol", "fetched_at", "source", "lease_holder", "lease_until", "value"}`; `value` (the encoded cached payload) and anything else unpromoted lives in `doc`. A lease-only row has `fetched_at=None` and no `value`.

- [ ] **Step 1: Write the failing repository test**

Create `tests/db/test_market_shared_repository.py` (fixtures `db_conn`, `db_committed` come from `tests/db/conftest.py`):

```python
"""v171 D1/D6/D9: shared cache rows, leases, the shared token bucket and breaker, counts."""
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from swingbot.core.db import events, schema
from swingbot.core.db.repositories import market_shared as store
from swingbot.core.db.repositories.market_shared import MarketSharedRepository

T0 = datetime(2026, 10, 16, 14, 0, tzinfo=timezone.utc)


@pytest.fixture
def repo():
    return MarketSharedRepository()


def _row(key="quote:AAPL:", value=None):
    return {"key": key, "kind": "quote", "symbol": key.split(":")[1], "fetched_at": T0,
            "source": "alpaca", "value": value if value is not None else {"price": 1.5}}


def test_write_then_read_many_keys_in_one_statement(repo, db_conn):
    repo.write_entries([_row(), _row("quote:MSFT:", {"price": 2.0})], conn=db_conn)
    got = repo.read_entries(["quote:AAPL:", "quote:MSFT:", "quote:NOPE:"], conn=db_conn)
    assert set(got) == {"quote:AAPL:", "quote:MSFT:"}
    assert got["quote:MSFT:"]["value"] == {"price": 2.0}
    assert got["quote:AAPL:"]["fetched_at"] == T0
    assert repo.read_entries([], conn=db_conn) == {}


def test_lease_is_exclusive_until_released_or_expired(repo, db_conn):
    assert repo.try_lease("quote:AAPL:", "A", 30, kind="quote", symbol="AAPL", conn=db_conn)
    assert not repo.try_lease("quote:AAPL:", "B", 30, kind="quote", symbol="AAPL", conn=db_conn)
    assert repo.try_lease("quote:AAPL:", "A", 30, kind="quote", symbol="AAPL", conn=db_conn)
    repo.release_lease("quote:AAPL:", "B", conn=db_conn)          # not B's: no effect
    assert not repo.try_lease("quote:AAPL:", "B", 30, kind="quote", symbol="AAPL", conn=db_conn)
    repo.release_lease("quote:AAPL:", "A", conn=db_conn)
    assert repo.try_lease("quote:AAPL:", "B", 30, kind="quote", symbol="AAPL", conn=db_conn)


def test_an_expired_lease_is_taken_by_the_next_asker(repo, db_conn):
    assert repo.try_lease("quote:AAPL:", "dead", 0.01, kind="quote", symbol="AAPL", conn=db_conn)
    db_conn.execute(sa.text("select pg_sleep(0.05)"))
    assert repo.try_lease("quote:AAPL:", "B", 30, kind="quote", symbol="AAPL", conn=db_conn)


def test_writing_a_value_clears_the_lease(repo, db_conn):
    repo.try_lease("quote:AAPL:", "A", 30, kind="quote", symbol="AAPL", conn=db_conn)
    repo.write_entries([_row()], conn=db_conn)
    row = repo.read_entries(["quote:AAPL:"], conn=db_conn)["quote:AAPL:"]
    assert row["lease_holder"] is None and row["lease_until"] is None


def test_take_token_respects_capacity_and_reserve(repo, db_conn):
    takes = [repo.take_token("alpaca", 3, 0, 0, conn=db_conn) for _ in range(4)]
    assert takes == [True, True, True, False]
    reserved = [repo.take_token("yfinance", 4, 0, 2, conn=db_conn) for _ in range(3)]
    assert reserved == [True, True, False]           # 4->3->2, a third would leave 1 < 2
    assert repo.take_token("yfinance", 4, 0, 0, conn=db_conn) is True    # tier 1-3: reserve 0


def test_take_token_refills_with_elapsed_time(repo, db_conn):
    assert [repo.take_token("alpaca", 1, 60, 0, conn=db_conn) for _ in range(2)] == [True, False]
    db_conn.execute(sa.text(
        "update provider_budget set stamp = stamp - interval '2 seconds' where provider='alpaca'"))
    assert repo.take_token("alpaca", 1, 60, 0, conn=db_conn) is True


def test_breaker_opens_after_n_failures_and_success_resets_the_count(repo, db_conn):
    assert repo.breaker_state("alpaca", conn=db_conn) == (0, None)
    for _ in range(2):
        repo.breaker_record("alpaca", False, 3, 300, conn=db_conn)
    assert repo.breaker_state("alpaca", conn=db_conn)[1] is None
    repo.breaker_record("alpaca", False, 3, 300, conn=db_conn)
    fails, open_until = repo.breaker_state("alpaca", conn=db_conn)
    assert fails == 3 and open_until > datetime.now(timezone.utc) + timedelta(seconds=290)
    repo.breaker_record("alpaca", True, 3, 300, conn=db_conn)
    assert repo.breaker_state("alpaca", conn=db_conn)[0] == 0


def test_a_breaker_row_created_first_leaves_the_bucket_full(repo, db_conn):
    repo.breaker_record("alpaca", False, 3, 300, conn=db_conn)
    assert repo.take_token("alpaca", 5, 5, 0, conn=db_conn) is True


def test_counts_increment_per_hour_and_key(repo, db_conn):
    row = (T0, "alpaca", "quote", "scan", "hit", 2)
    repo.add_counts([row], conn=db_conn)
    repo.add_counts([row, (T0, "alpaca", "quote", "scan", "fetched", 1)], conn=db_conn)
    got = repo.count_rows(T0, T0 + timedelta(hours=1), conn=db_conn)
    assert {(r["outcome"], r["n"]) for r in got} == {("hit", 4), ("fetched", 1)}
    assert repo.count_rows(T0 + timedelta(hours=1), T0 + timedelta(hours=2), conn=db_conn) == []


def test_tables_stream_no_sse_and_the_accessor_is_a_singleton():
    for name in ("market_cache", "provider_budget", "market_fetch_counts"):
        assert name in schema.METADATA.tables and name not in events.TABLE_CHANNELS
    assert store.market_shared_repo() is store.market_shared_repo()
```

- [ ] **Step 2: Write the failing side-engine test**

Create `tests/db/test_side_engine.py`:

```python
"""v171 D1: the layer's own tiny pool, autocommit, a hard statement timeout, fast fail-open."""
import multiprocessing
import time

import pytest
import sqlalchemy as sa

from swingbot import config
from swingbot.core.db import side_engine
from swingbot.core.db.engine import DatabaseUnavailable


@pytest.fixture
def side_db(db_committed, db_engine, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    monkeypatch.setattr(config, "MARKETDATA_PG_TIMEOUT_MS", 250)
    side_engine.reset()
    yield db_committed
    side_engine.reset()


def test_pool_is_one_plus_one_in_the_parent_and_one_in_a_worker(monkeypatch):
    assert side_engine.pool_limits() == (1, 1)
    monkeypatch.setattr(multiprocessing, "parent_process", lambda: object())
    assert side_engine.pool_limits() == (1, 0)


def test_statement_timeout_follows_the_knob(side_db, monkeypatch):
    with side_engine.side_connection() as conn:
        assert conn.execute(sa.text("show statement_timeout")).scalar_one() == "250ms"
    monkeypatch.setattr(config, "MARKETDATA_PG_TIMEOUT_MS", 300)
    with side_engine.side_connection() as conn:
        assert conn.execute(sa.text("show statement_timeout")).scalar_one() == "300ms"


def test_a_hung_statement_is_cancelled_at_the_timeout(side_db):
    started = time.monotonic()
    with pytest.raises(sa.exc.OperationalError):
        with side_engine.side_connection() as conn:
            conn.execute(sa.text("select pg_sleep(3)"))
    assert time.monotonic() - started < 1.0


def test_writes_are_autocommitted(side_db):
    with side_engine.side_connection() as conn:
        conn.execute(sa.text("insert into market_cache (key, kind, symbol) values ('k', 'quote', 'X')"))
    assert side_db.execute(sa.text("select count(*) from market_cache where key='k'")).scalar_one() == 1


def test_a_down_database_fails_fast_after_the_first_refusal(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL",
                        "postgresql+psycopg://u:p@127.0.0.1:1/none")
    side_engine.reset()
    with pytest.raises(Exception):
        with side_engine.side_connection():
            pass
    started = time.monotonic()
    with pytest.raises(DatabaseUnavailable):
        with side_engine.side_connection():
            pass
    assert time.monotonic() - started < 0.05
    side_engine.reset()


def test_no_url_is_database_unavailable(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", "")
    side_engine.reset()
    with pytest.raises(DatabaseUnavailable):
        with side_engine.side_connection():
            pass
```

- [ ] **Step 3: Add the round-trip cases**

In `tests/db/test_unknown_field_round_trip.py` import `MarketSharedRepository` and add to `CASES`:

```python
    "market_cache": (lambda: MarketSharedRepository().cache,
                     {"key": "quote:AAPL:", "kind": "quote", "symbol": "AAPL"}),
    "provider_budget": (lambda: MarketSharedRepository().budget,
                        {"provider": "alpaca", "tokens": 150.0, "stamp": TS}),
    "market_fetch_counts": (lambda: MarketSharedRepository().counts,
                            {"hour": TS, "provider": "alpaca", "kind": "quote", "asker": "scan",
                             "outcome": "hit", "n": 1}),
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/db/test_market_shared_repository.py`
Expected: FAIL with `ModuleNotFoundError: ... repositories.market_shared`.
Run: `python $WT/scripts/dev/testrun.py file tests/db/test_side_engine.py`
Expected: FAIL with `ImportError: cannot import name 'side_engine'`.

- [ ] **Step 5: Declare the tables in `swingbot/core/db/schema.py`**

After `gate_rejections`, with a comment `# v171: the shared market-data layer (spec D1/D6/D9). No SSE event; none in TABLE_CHANNELS.` Use `from sqlalchemy.dialects.postgresql import DOUBLE_PRECISION` for the float columns (the migration uses the same type, so the autogenerate parity test in `tests/db/test_migrations.py` stays clean):

- `market_cache`: `key Text PK`, `kind Text NOT NULL`, `symbol Text NOT NULL`, `fetched_at TIMESTAMPTZ NULL`, `source Text NULL`, `lease_holder Text NULL`, `lease_until TIMESTAMPTZ NULL`, `*standard_columns()`. Promoted: all seven.
- `provider_budget`: `provider Text PK`, `tokens DOUBLE_PRECISION NOT NULL`, `stamp TIMESTAMPTZ NOT NULL`, `breaker_failures Integer NOT NULL server_default '0'`, `breaker_open_until TIMESTAMPTZ NULL`, `*standard_columns()`. Promoted: all five.
- `market_fetch_counts`: `id BigInteger PK`, `hour TIMESTAMPTZ NOT NULL`, `provider`, `kind`, `asker`, `outcome` (Text NOT NULL), `n BigInteger NOT NULL`, `*standard_columns()`, `UniqueConstraint("hour", "provider", "kind", "asker", "outcome", name="market_fetch_counts_key_uq")`. Promoted: the six non-id columns.

Add one `PROMOTION_REASONS` line per promoted column, for example `"lease_until": "single-flight claim compared in the lease UPDATE's WHERE"`, `"tokens": "atomic refill-and-take arithmetic in one UPDATE"`, `"n": "upsert increment in SQL"`, `"hour": "market_fetch_counts_key_uq and the report's time range"`.

- [ ] **Step 6: Write the revision `swingbot/core/db/migrations/versions/v171_001_market_shared.py`**

Follow `v147_001_gate_rejections.py`: `revision = "v171_001"`, `down_revision = "v146_001"` (or the head V171-1 Step 1 recorded), docstring `"""market_cache, provider_budget, market_fetch_counts: the v171 shared market-data layer ... A new set of tables, so the downgrade drops them whole."""`. `upgrade()` creates the three tables column for column as Step 5 (same names, types, nullability, server defaults, the unique constraint name). `downgrade()` drops `market_fetch_counts`, `provider_budget`, `market_cache`.

- [ ] **Step 7: Implement `swingbot/core/db/side_engine.py`**

Module state: `_engine`, `_engine_sig` (the `(url, ms, pool_limits())` it was built with), `_down_until = 0.0` (monotonic), `_lock = threading.Lock()`. Constants `_CONNECT_TIMEOUT_S = 2`, `_DOWN_BACKOFF_S = 30.0`.

- `pool_limits()`: `(1, 0)` when `multiprocessing.parent_process() is not None`, else `(1, 1)`.
- `_url()`: the same checks as `engine.get_engine` (empty, or not `postgresql+psycopg://`) raising `DatabaseUnavailable`.
- `_get()`: under `_lock`, rebuild when the signature changed (dispose the old one). The engine:

```python
    create_engine(
        url, pool_size=size, max_overflow=overflow,
        pool_timeout=max(ms / 1000.0, 0.05),   # a busy pool fails open, never queues
        pool_pre_ping=False,                   # one statement per cache hit, no ping
        pool_recycle=300, isolation_level="AUTOCOMMIT", future=True,
        connect_args={"connect_timeout": _CONNECT_TIMEOUT_S,
                      "options": f"-c statement_timeout={ms} -c lock_timeout={ms}"})
```

- `side_connection()`: `@contextmanager`. If `time.monotonic() < _down_until`, raise `DatabaseUnavailable("side engine backing off")`. Wrap only `engine.connect()` in `try`; on `sa.exc.OperationalError`/`sa.exc.InterfaceError` set `_down_until = monotonic() + _DOWN_BACKOFF_S` and re-raise. Then `yield conn` inside `with` (statement errors propagate to the caller, which fails open).
- `reset()`: dispose, clear `_engine`, `_engine_sig`, `_down_until`.
- Module docstring states the connection budget from the Global Constraints (bot 2 + 2 live workers + admin 2 = at most 7 side connections) and that nothing outside `core/db` imports this module's SQLAlchemy objects (callers only use the context manager and pass `conn` back to the repository).

- [ ] **Step 8: Implement `swingbot/core/db/repositories/market_shared.py`**

`class MarketSharedRepository` (not a `Repository` subclass: it spans three tables). `__init__` builds `self.cache = Repository(market_cache, key="key")`, `self.budget = Repository(provider_budget, key="provider")`, `self.counts = Repository(market_fetch_counts, key="id")`. Every method takes `conn` (keyword-only, required) and issues exactly one statement. `now = sa.func.clock_timestamp()` throughout (not `now()`, which is frozen per transaction). The non-obvious statements:

```python
    def read_entries(self, keys, *, conn):
        if not keys:
            return {}
        c = market_cache.c
        param = sa.bindparam("keys", list(keys), type_=postgresql.ARRAY(sa.Text))
        rows = conn.execute(sa.select(market_cache).where(c.key == sa.any_(param))).all()
        return {row.key: self.cache._record(row) for row in rows}

    def write_entries(self, rows, *, conn):
        if not rows:
            return
        values = [{**self.cache._values(r), "lease_holder": None, "lease_until": None} for r in rows]
        ins = pg_insert(market_cache).values(values)
        x = ins.excluded
        conn.execute(ins.on_conflict_do_update(index_elements=[market_cache.c.key], set_={
            "kind": x.kind, "symbol": x.symbol, "fetched_at": x.fetched_at, "source": x.source,
            "doc": x.doc, "lease_holder": None, "lease_until": None, "updated_at": _now()}))

    def try_lease(self, key, holder, seconds, *, kind, symbol, conn):
        c = market_cache.c
        until = _now() + sa.func.make_interval(0, 0, 0, 0, 0, 0, float(seconds))
        ins = pg_insert(market_cache).values(key=key, kind=kind, symbol=symbol,
                                             lease_holder=holder, lease_until=until)
        stmt = ins.on_conflict_do_update(
            index_elements=[c.key],
            set_={"lease_holder": ins.excluded.lease_holder, "lease_until": ins.excluded.lease_until},
            where=sa.or_(c.lease_until.is_(None), c.lease_until < _now(), c.lease_holder == holder),
        ).returning(c.key)
        return conn.execute(stmt).first() is not None

    def take_token(self, provider, capacity, per_minute, reserve, *, conn):
        c = provider_budget.c
        elapsed = sa.extract("epoch", _now() - c.stamp)
        refilled = sa.func.least(float(capacity), c.tokens + elapsed * (float(per_minute) / 60.0))
        ins = pg_insert(provider_budget).values(provider=provider, tokens=float(capacity) - 1.0,
                                                stamp=_now())
        stmt = ins.on_conflict_do_update(
            index_elements=[c.provider],
            set_={"tokens": refilled - 1.0, "stamp": _now(), "updated_at": _now()},
            where=(refilled - 1.0 >= float(reserve)),
        ).returning(c.tokens)
        return conn.execute(stmt).first() is not None
```

- `release_lease`: `UPDATE market_cache SET lease_holder=NULL, lease_until=NULL WHERE key=:key AND lease_holder=:holder`.
- `breaker_state`: select `(breaker_failures, breaker_open_until)`; no row -> `(0, None)`.
- `breaker_record`: one upsert. Insert values `tokens=0.0`, `stamp=now - interval '1 hour'` (so a row first created by the breaker refills to full on the first take), `breaker_failures = 0 if ok else 1`, `breaker_open_until = now + cooldown if (not ok and 1 >= failures_to_open) else NULL`. On conflict: `ok` sets `breaker_failures = 0` only (like today's `_Breaker.record`, success never shortens an open window); a failure sets `breaker_failures = breaker_failures + 1` and `breaker_open_until = CASE WHEN breaker_failures + 1 >= :n THEN now + cooldown ELSE breaker_open_until END`.
- `add_counts`: aggregate the input rows by their first five fields first (one statement cannot touch a row twice), then one multi-row upsert `ON CONFLICT ON CONSTRAINT market_fetch_counts_key_uq DO UPDATE SET n = market_fetch_counts.n + excluded.n, updated_at = now`.
- `count_rows(since, until)`: `hour >= since AND hour < until`, ordered by `hour, provider, kind, asker, outcome`, returned as dicts with those six keys.
- `_repo` singleton and `market_shared_repo()` like `scheduled_repo()`.

- [ ] **Step 9: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/db/test_market_shared_repository.py`, then the same for `tests/db/test_side_engine.py`, `tests/db/test_unknown_field_round_trip.py`, `tests/db/test_migrations.py`, `tests/db/test_schema_contract.py`, `tests/db/test_trigger_coverage.py`
Expected: PASS for all six files (migrations: one head `v171_001`, autogenerate diff empty; schema contract: one reason per promoted column).
Run: `python -m radon cc -s -n C $WT/swingbot/core/db/side_engine.py $WT/swingbot/core/db/repositories/market_shared.py`
Expected: no output.

- [ ] **Step 10: Commit**

```bash
git -C $WT add swingbot/core/db/schema.py swingbot/core/db/migrations/versions/v171_001_market_shared.py swingbot/core/db/side_engine.py swingbot/core/db/repositories/market_shared.py tests/db/test_market_shared_repository.py tests/db/test_side_engine.py tests/db/test_unknown_field_round_trip.py
git -C $WT commit -m "feat(v171): market_cache, provider_budget, market_fetch_counts tables, repository and fail-fast side engine"
```

### Task V171-4: D9 counters: in-process tally, hourly flush to Postgres, worker snapshot and merge

**Model:** sonnet — one module over V171-3's repository, behaviour fixed by D9

**Files:**
- Create: `swingbot/core/marketdata/shared/counters.py`
- Create: `tests/marketdata/test_shared_counters.py`

**Interfaces:**
- Consumes: `kinds.DataKind`, `kinds.Asker`, `kinds.OUTCOMES` (V171-2); `side_engine.side_connection()`, `market_shared_repo().add_counts(rows, *, conn)` (V171-3).
- Produces (ledger): `count(provider, kind, asker, outcome, n=1)`, `snapshot_and_clear()`, `merge(rows)`, `flush(*, force=False) -> int`, `reset()`. Plus, used by V171-5 and V171-6 only: `warn_fail_open(operation: str, exc: BaseException) -> None` (one `log.warning` per minute per `(operation, type(exc).__name__)`, message `"market-data layer: %s failed open (%s: %s)"`).

Rows are keyed by `(hour_iso, provider, kind.value, asker.value, outcome)`, `hour_iso` = the UTC hour the call happened in (`now.replace(minute=0, second=0, microsecond=0).isoformat()`), so flushing every 60 s only increments that hour's rows; D9's "per hour" is the row grain, not the flush cadence. `_last_flush` starts at the import time's `time.monotonic()`: a spawned `_run_bounded` worker lives far under 60 s, never flushes on its own, and hands its rows back through `snapshot_and_clear()` (V171-9 wires that).

- [ ] **Step 1: Write the failing test**

Create `tests/marketdata/test_shared_counters.py`:

```python
"""v171 D9: per-call counts by provider, kind, asker and outcome."""
import contextlib
import logging
from datetime import datetime, timezone

import pytest

from swingbot import config
from swingbot.core.marketdata.shared import counters
from swingbot.core.marketdata.shared.kinds import Asker, DataKind

HOUR = datetime(2026, 10, 16, 14, 0, tzinfo=timezone.utc)


class FakeRepo:
    def __init__(self, fail=False):
        self.rows, self.fail = [], fail

    def add_counts(self, rows, *, conn):
        if self.fail:
            raise RuntimeError("db down")
        self.rows.extend(rows)


@pytest.fixture
def repo(monkeypatch):
    fake = FakeRepo()
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "count")
    monkeypatch.setattr(counters, "market_shared_repo", lambda: fake)
    monkeypatch.setattr(counters, "side_connection", lambda: contextlib.nullcontext(None))
    monkeypatch.setattr(counters, "_now", lambda: HOUR.replace(minute=17))
    counters.reset()
    yield fake
    counters.reset()


def test_off_mode_counts_nothing(repo, monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    counters.count("alpaca", DataKind.QUOTE, Asker.SCAN, "fetched")
    assert counters.snapshot_and_clear() == []


def test_counts_aggregate_by_hour_and_key(repo):
    counters.count("alpaca", DataKind.QUOTE, Asker.SCAN, "hit", 3)
    counters.count("alpaca", DataKind.QUOTE, Asker.SCAN, "hit")
    counters.count("yfinance", DataKind.EARNINGS, Asker.ADMIN_PAGE, "failed")
    assert sorted(counters.snapshot_and_clear()) == [
        (HOUR.isoformat(), "alpaca", "quote", "scan", "hit", 4),
        (HOUR.isoformat(), "yfinance", "earnings", "admin_page", "failed", 1)]
    assert counters.snapshot_and_clear() == []


def test_an_unknown_outcome_is_rejected(repo):
    with pytest.raises(ValueError):
        counters.count("alpaca", DataKind.QUOTE, Asker.SCAN, "maybe")


def test_merge_adds_worker_rows(repo):
    counters.count("alpaca", DataKind.QUOTE, Asker.SCAN, "fetched")
    counters.merge([(HOUR.isoformat(), "alpaca", "quote", "scan", "fetched", 5)])
    assert counters.snapshot_and_clear() == [(HOUR.isoformat(), "alpaca", "quote", "scan", "fetched", 6)]


def test_flush_waits_sixty_seconds_unless_forced(repo, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(counters, "_monotonic", lambda: clock[0])
    counters.reset()                                  # _last_flush = 1000
    counters.count("alpaca", DataKind.QUOTE, Asker.SCAN, "hit")
    assert counters.flush() == 0 and repo.rows == []
    clock[0] = 1061.0
    assert counters.flush() == 1
    assert repo.rows == [(HOUR, "alpaca", "quote", "scan", "hit", 1)]   # hour back to datetime
    counters.count("alpaca", DataKind.QUOTE, Asker.SCAN, "hit")
    assert counters.flush(force=True) == 1


def test_a_failed_flush_keeps_the_rows_and_warns_once(repo, monkeypatch, caplog):
    repo.fail = True
    counters.count("alpaca", DataKind.QUOTE, Asker.SCAN, "hit")
    with caplog.at_level(logging.WARNING):
        assert counters.flush(force=True) == 0
        assert counters.flush(force=True) == 0
    assert len([r for r in caplog.records if "failed open" in r.message]) == 1
    assert counters.snapshot_and_clear() == [(HOUR.isoformat(), "alpaca", "quote", "scan", "hit", 1)]


def test_warn_fail_open_is_per_operation_and_error_class(caplog):
    counters.reset()
    with caplog.at_level(logging.WARNING):
        counters.warn_fail_open("read", TimeoutError("x"))
        counters.warn_fail_open("read", TimeoutError("y"))
        counters.warn_fail_open("read", OSError("z"))
        counters.warn_fail_open("lease", TimeoutError("x"))
    assert len(caplog.records) == 3
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_shared_counters.py`
Expected: FAIL with `ImportError: cannot import name 'counters'`.

- [ ] **Step 3: Implement `swingbot/core/marketdata/shared/counters.py`**

- Imports at module level (tests patch them here): `from swingbot.core.db.side_engine import side_connection`, `from swingbot.core.db.repositories.market_shared import market_shared_repo`. Seams `_now()` (UTC `datetime.now`) and `_monotonic = time.monotonic`.
- State: `_tally: collections.Counter` keyed by the five-tuple, `_lock = threading.Lock()`, `_last_flush = time.monotonic()`, `_warned: dict[tuple[str, str], float]`.
- `count`: return at once when `config.MARKETDATA_LAYER == "off"`; `ValueError` for an outcome not in `OUTCOMES`; add `n` under the lock.
- `snapshot_and_clear`: under the lock, list of `(*key, n)` tuples, then clear. `merge(rows)`: add each row's `n` under its key (no mode check: the rows were already counted in a worker).
- `flush(force=False)`: return 0 when not forced and `_monotonic() - _last_flush < 60`; set `_last_flush`; take the snapshot; return 0 if empty; convert `hour_iso` with `datetime.fromisoformat`; one `add_counts` inside `with side_connection() as conn`. On any exception: `merge(rows)` back, `warn_fail_open("count flush", exc)`, return 0. Otherwise return `len(rows)`.
- `warn_fail_open`: key `(operation, type(exc).__name__)`; log only if the key's last warning is at least 60 s old by `_monotonic()`.
- `reset()`: clear the tally and `_warned`, `_last_flush = _monotonic()`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_shared_counters.py`
Expected: PASS.
Run: `python -m radon cc -s -n C $WT/swingbot/core/marketdata/shared/counters.py`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git -C $WT add swingbot/core/marketdata/shared/counters.py tests/marketdata/test_shared_counters.py
git -C $WT commit -m "feat(v171): D9 call counters with hourly rows, worker merge and fail-open flush"
```

### Task V171-5: D6 shared budget and breaker with tier reserves; admin storm never takes tier 1-3 budget

**Model:** opus — money-path budget shared across processes, a wrong reserve starves stop monitoring

**Files:**
- Create: `swingbot/core/marketdata/shared/budget.py`
- Create: `tests/marketdata/test_shared_budget.py`

**Interfaces:**
- Consumes: `kinds.Asker`, `resolve_asker`, `PROVIDER_ALPACA`, `PROVIDER_YF` (V171-2); `counters.warn_fail_open` (V171-4); `side_connection()`, `market_shared_repo().take_token / breaker_state / breaker_record` (V171-3); `config.ALPACA_BUDGET_PER_MINUTE`, `YF_BUDGET_PER_MINUTE`, `ALPACA_BREAKER_FAILURES`, `ALPACA_BREAKER_COOLDOWN_SECONDS`, `MARKETDATA_LAYER`.
- Produces (ledger): `RESERVE_FRACTION`, `capacity(provider)`, `take(provider, asker) -> bool`, `breaker_allows(provider) -> bool`, `breaker_record(provider, ok) -> None`. Plus `class BudgetDeferred(RuntimeError)`: raised by a provider wrapper when a tier 4-5 call is denied; V171-6 catches it and V171-8 re-exports it as `yf_safe.BudgetDeferred`.

Semantics, fixed here for V171-6 and V171-8:

- The bucket holds `capacity(provider)` tokens and refills at `capacity / 60` per second (the per-minute knob is both size and rate, like today's `_Bucket`).
- `take` resolves the asker first (`resolve_asker`, so a fresh admin reload is `ADMIN_FRESH`, still tier 5), then asks the repository with `reserve = capacity * RESERVE_FRACTION[asker.priority]`. True means one token was taken.
- `take` answers honestly for every tier: a tier 1-3 False means the shared bucket is truly empty (the same moment today's `_Bucket.take()` would refuse). Only tiers 4-5 are ever *deferred* (V171-6 serves them cached); what a tier 1-3 caller does on False stays the caller's today path (V171-8).
- `off`/`count` mode: `take` and `breaker_allows` return True and touch nothing; `breaker_record` is a no-op.
- Fail open: any exception from the side connection or the repository makes `take` and `breaker_allows` return True and `breaker_record` return, each after `counters.warn_fail_open("budget take" | "breaker read" | "breaker write", exc)`.
- The breaker is shared by provider name; the router's auth latch stays per process (V171-8).

- [ ] **Step 1: Write the failing test**

Create `tests/marketdata/test_shared_budget.py`:

```python
"""v171 D6: one budget per provider shared by every process; money first."""
import contextlib
from datetime import datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.core.db import side_engine
from swingbot.core.marketdata.shared import budget
from swingbot.core.marketdata.shared.kinds import PROVIDER_ALPACA, PROVIDER_YF, Asker, fresh_request


class FakeRepo:
    def __init__(self, raise_on=None):
        self.takes, self.records, self.raise_on = [], [], raise_on
        self.state = (0, None)

    def take_token(self, provider, capacity, per_minute, reserve, *, conn):
        if self.raise_on == "take":
            raise TimeoutError("statement timeout")
        self.takes.append((provider, capacity, per_minute, reserve))
        return True

    def breaker_state(self, provider, *, conn):
        if self.raise_on == "state":
            raise TimeoutError("statement timeout")
        return self.state

    def breaker_record(self, provider, ok, failures_to_open, cooldown_s, *, conn):
        self.records.append((provider, ok, failures_to_open, cooldown_s))


@pytest.fixture
def fake(monkeypatch):
    repo = FakeRepo()
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(config, "ALPACA_BUDGET_PER_MINUTE", 150)
    monkeypatch.setattr(config, "YF_BUDGET_PER_MINUTE", 60)
    monkeypatch.setattr(budget, "market_shared_repo", lambda: repo)
    monkeypatch.setattr(budget, "side_connection", lambda: contextlib.nullcontext(None))
    return repo


def test_reserves_by_tier():
    assert budget.RESERVE_FRACTION == {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.25, 5: 0.50}


def test_capacity_per_provider(fake):
    assert budget.capacity(PROVIDER_ALPACA) == 150.0 and budget.capacity(PROVIDER_YF) == 60.0
    with pytest.raises(ValueError):
        budget.capacity("polygon")


@pytest.mark.parametrize("asker,reserve", [
    (Asker.STOP_MONITOR, 0.0), (Asker.REQUOTE, 0.0), (Asker.SCAN, 0.0),
    (Asker.BACKGROUND, 37.5), (Asker.ADMIN_DASHBOARD, 75.0), (Asker.ADMIN_PAGE, 75.0)])
def test_take_passes_the_tier_reserve(fake, asker, reserve):
    assert budget.take(PROVIDER_ALPACA, asker) is True
    assert fake.takes == [(PROVIDER_ALPACA, 150.0, 150.0, reserve)]


def test_fresh_admin_reload_runs_at_tier_5(fake):
    with fresh_request():
        budget.take(PROVIDER_YF, Asker.ADMIN_PAGE)
    assert fake.takes == [(PROVIDER_YF, 60.0, 60.0, 30.0)]


@pytest.mark.parametrize("mode", ["off", "count"])
def test_off_and_count_never_touch_the_store(fake, monkeypatch, mode):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", mode)
    assert budget.take(PROVIDER_ALPACA, Asker.ADMIN_PAGE) is True
    assert budget.breaker_allows(PROVIDER_ALPACA) is True
    budget.breaker_record(PROVIDER_ALPACA, False)
    assert fake.takes == [] and fake.records == []


def test_store_errors_fail_open(fake):
    fake.raise_on = "take"
    assert budget.take(PROVIDER_ALPACA, Asker.STOP_MONITOR) is True
    fake.raise_on = "state"
    assert budget.breaker_allows(PROVIDER_ALPACA) is True


def test_breaker_reads_the_shared_open_window(fake):
    fake.state = (3, datetime.now(timezone.utc) + timedelta(seconds=120))
    assert budget.breaker_allows(PROVIDER_ALPACA) is False
    fake.state = (3, datetime.now(timezone.utc) - timedelta(seconds=1))
    assert budget.breaker_allows(PROVIDER_ALPACA) is True


def test_breaker_record_uses_the_alpaca_breaker_knobs(fake, monkeypatch):
    monkeypatch.setattr(config, "ALPACA_BREAKER_FAILURES", 4)
    monkeypatch.setattr(config, "ALPACA_BREAKER_COOLDOWN_SECONDS", 90)
    budget.breaker_record(PROVIDER_ALPACA, False)
    assert fake.records == [(PROVIDER_ALPACA, False, 4, 90.0)]


@pytest.fixture
def shared_db(db_committed, db_engine, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(config, "ALPACA_BUDGET_PER_MINUTE", 10)   # refill 1 token / 6 s
    side_engine.reset()
    yield db_committed
    side_engine.reset()


def test_admin_storm_never_takes_budget_from_tiers_1_to_3(shared_db):
    admin = sum(budget.take(PROVIDER_ALPACA, Asker.ADMIN_PAGE) for _ in range(100))
    with fresh_request():
        admin += sum(budget.take(PROVIDER_ALPACA, Asker.ADMIN_PAGE) for _ in range(100))
    background = sum(budget.take(PROVIDER_ALPACA, Asker.BACKGROUND) for _ in range(100))
    money = [budget.take(PROVIDER_ALPACA, a)
             for a in (Asker.STOP_MONITOR, Asker.REQUOTE, Asker.SCAN, Asker.STOP_MONITOR, Asker.SCAN)]
    assert admin == 5                 # 10 -> 5: half the bucket stays for tiers 1-4
    assert background == 2            # 5 -> 3: a quarter (2.5) stays for tiers 1-3
    assert all(money[:3])             # tiers 1-3 still get tokens after the storm
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_shared_budget.py`
Expected: FAIL with `ImportError: cannot import name 'budget'`.

- [ ] **Step 3: Implement `swingbot/core/marketdata/shared/budget.py`**

- Module-level imports `side_connection`, `market_shared_repo`, `counters` (tests patch the first two here).
- `_CAPACITY_ATTR = {PROVIDER_ALPACA: "ALPACA_BUDGET_PER_MINUTE", PROVIDER_YF: "YF_BUDGET_PER_MINUTE"}`; `capacity` raises `ValueError` for any other provider.
- `_on()` helper: `config.MARKETDATA_LAYER == "on"`.
- `take`: `if not _on(): return True`; `asker = resolve_asker(asker)`; `cap = capacity(provider)`; inside `try`: `with side_connection() as conn: return bool(repo.take_token(provider, cap, cap, cap * RESERVE_FRACTION[asker.priority], conn=conn))`; `except Exception as exc`: warn and return True.
- `breaker_allows`: `(_fails, open_until) = repo.breaker_state(...)`; allowed when `open_until is None or open_until <= datetime.now(timezone.utc)`; fail open True.
- `breaker_record`: `repo.breaker_record(provider, ok, int(config.ALPACA_BREAKER_FAILURES), float(config.ALPACA_BREAKER_COOLDOWN_SECONDS), conn=conn)`; fail open (warn, return). The yfinance provider shares the same knobs (there is no separate yfinance breaker config; V171-8 records yfinance verdicts only if it chooses to).
- `class BudgetDeferred(RuntimeError)` with docstring "A tier 4-5 provider call was refused by the shared budget; the layer serves the freshest cached value with its age instead."

- [ ] **Step 4: Run the test to verify it passes**

Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_shared_budget.py`
Expected: PASS, including the Postgres storm test (it skips only when the test Postgres is unreachable; a skip here is not green, start the DB and re-run).
Run: `python -m radon cc -s -n C $WT/swingbot/core/marketdata/shared/budget.py`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git -C $WT add swingbot/core/marketdata/shared/budget.py tests/marketdata/test_shared_budget.py
git -C $WT commit -m "feat(v171): shared money-first budget and breaker with tier reserves, fail open"
```

### Task V171-6: Layer core: `get` (cache, window, lease single-flight, batching, deadline rule, budget-deferred), `lease` for bar writers; modes off/count/on; fail open

**Model:** opus — cross-process concurrency on the money path, spans `core/db` and `core/marketdata`

**Files:**
- Create: `swingbot/core/marketdata/shared/layer.py`
- Create: `tests/marketdata/test_shared_layer.py`
- Create: `tests/db/test_shared_layer_postgres.py`

**Interfaces:**
- Consumes: everything in `kinds` (V171-2); `counters.count`, `counters.flush`, `counters.warn_fail_open` (V171-4); `budget.BudgetDeferred` (V171-5); `side_connection`, `market_shared_repo().read_entries / write_entries / try_lease / release_lease` (V171-3); `spot_metals.is_spot_metal` (exists); `config.MARKETDATA_LAYER`, `MARKETDATA_LEASE_SECONDS`.
- Produces (ledger, exact): `get(...) -> dict[str, Entry]`, `lease(...) -> ContextManager[bool]`, `last_cached(...) -> dict[str, Entry]`, `HOLDER_ID`. Results are keyed by the symbol exactly as the caller passed it; a symbol with no value is absent from the dict.

The contract every later task relies on:

| Situation (mode `on`) | Result | Outcome counted |
|---|---|---|
| cached, age <= window (`max_age_s` if given, else `asker.window_s(kind)`; `None` = any age) | cached value | `hit` |
| not fresh, no live foreign lease | leased by this call, fetched in **one** batched `fetch` call with every other such symbol, written back | `fetched` (`failed` if absent from the reply or its value is `None`) |
| a live lease held by another call | poll every 100 ms until a fresh value lands | `shared-wait` |
| foreign lease vanished or expired, still no fresh value | lease taken, fetched | `fetched` / `failed` |
| deadline passed while waiting, tier 1-2 | fetched by this call regardless of the lease | `fetched` / `failed` |
| deadline passed while waiting, tier 3-5 | last cached value of any age, else absent | `shared-wait` / `failed` |
| `fetch` raised `budget.BudgetDeferred` (only tier 4-5 calls are ever denied, V171-8) | last cached value of any age, else absent; this call's leases released | `budget-deferred` |
| `fetch` raised anything else | this call's leases released, the exception propagates (fails as today) | `failed` |
| cache read or lease statement errors or times out | the remaining symbols are fetched directly; write-back is still attempted, its error only warned | `fetched` / `failed` |
| spot metal symbol | fetched in the same batch, never keyed, leased or written | `fetched` / `failed` |

Mode `off`: `fetch(symbols)` once, wrapped as `Entry(outcome="fetched", source=provider)`, nothing counted, no Postgres. Mode `count`: the same call, plus a count per symbol (`fetched`, or `failed` when absent; when `fetch` raises, every symbol counts `failed` and the exception propagates), no cache read, no lease. Every `get` ends with `counters.flush()` (cheap: it writes at most once a minute). The layer never takes a budget token itself (see this part's header).

A `None` value in the `fetch` reply is a miss: it is never written, so a blank reply never overwrites the last good value (D7). Each `get` call leases under its own holder string `f"{HOLDER_ID}#{n}"` (`n` from an `itertools.count()`), so two threads of one process single-flight against each other too; `HOLDER_ID` itself is the process prefix from the ledger.

`lease(kind, symbol, *, asker, deadline_s=30.0)` (bar writers, V171-12): mode `off`/`count` or a spot symbol -> yields True with no Postgres. Mode `on`: lease free -> take it, yield True, release in `finally`. Held by another -> poll every 100 ms: holder released it (lease columns NULL) -> yield False (another holder finished: re-read, do not refetch); lease expired -> take it, yield True; deadline passed -> yield True for tiers 1-2, False for tiers 3-5. Any lease statement error -> warn, yield False (failed open; the ledger's meaning, V171-12 decides what a writer does with it).

`last_cached(kind, symbols, params="")`: mode `on` only (else `{}`); one read; every row with a `fetched_at` becomes `Entry(value=<stored value, not decoded>, fetched_at, source, outcome="hit")`; fail open `{}`; not counted.

- [ ] **Step 1: Write the failing unit test**

Create `tests/marketdata/test_shared_layer.py`:

```python
"""v171 D1/D2/D6: the shared layer against an in-memory repository."""
import contextlib
import logging
from datetime import datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.core.marketdata.shared import budget, counters, layer
from swingbot.core.marketdata.shared.kinds import Asker, DataKind, cache_key, fresh_request

T0 = datetime(2026, 10, 16, 14, 30, tzinfo=timezone.utc)
Q = DataKind.QUOTE


class Clock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return T0 + timedelta(seconds=self.t)

    def mono(self):
        return self.t

    def sleep(self, s):
        self.t += s


class FakeRepo:
    def __init__(self, clock):
        self.rows, self.clock, self.fail, self.reads = {}, clock, set(), 0

    def _check(self, op):
        if op in self.fail:
            raise TimeoutError(f"{op} timed out")

    def read_entries(self, keys, *, conn):
        self._check("read")
        self.reads += 1
        return {k: dict(self.rows[k]) for k in keys if k in self.rows}

    def write_entries(self, rows, *, conn):
        self._check("write")
        for r in rows:
            self.rows[r["key"]] = {**r, "lease_holder": None, "lease_until": None}

    def try_lease(self, key, holder, seconds, *, kind, symbol, conn):
        self._check("lease")
        row = self.rows.setdefault(key, {"key": key, "fetched_at": None, "lease_holder": None,
                                         "lease_until": None})
        free = row["lease_until"] is None or row["lease_until"] < self.clock.now()
        if free or row["lease_holder"] == holder:
            row.update(lease_holder=holder, lease_until=self.clock.now() + timedelta(seconds=seconds))
            return True
        return False

    def release_lease(self, key, holder, *, conn):
        row = self.rows.get(key)
        if row and row["lease_holder"] == holder:
            row.update(lease_holder=None, lease_until=None)

    def seed(self, sym, value, age_s, lease_holder=None, lease_for=0.0):
        self.rows[cache_key(Q, sym)] = {
            "key": cache_key(Q, sym), "kind": "quote", "symbol": sym, "source": "alpaca",
            "fetched_at": self.clock.now() - timedelta(seconds=age_s), "value": value,
            "lease_holder": lease_holder,
            "lease_until": (self.clock.now() + timedelta(seconds=lease_for)) if lease_holder else None}


@pytest.fixture
def env(monkeypatch):
    clock = Clock()
    repo = FakeRepo(clock)
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(layer, "market_shared_repo", lambda: repo)
    monkeypatch.setattr(layer, "side_connection", lambda: contextlib.nullcontext(None))
    monkeypatch.setattr(layer, "_now", clock.now)
    monkeypatch.setattr(layer, "_monotonic", clock.mono)
    monkeypatch.setattr(layer, "_sleep", lambda s: clock.sleep(s))   # late-bound: tests swap it
    monkeypatch.setattr(counters, "flush", lambda force=False: 0)
    counters.reset()
    return repo, clock


def fetcher(values, calls):
    def fetch(symbols):
        calls.append(list(symbols))
        return {s: values[s] for s in symbols if s in values}
    return fetch


def outcomes():
    return sorted((r[3], r[4], r[5]) for r in counters.snapshot_and_clear())


def test_off_mode_is_a_plain_pass_through(env, monkeypatch):
    repo, _ = env
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    calls = []
    got = layer.get(Q, ["AAPL"], fetcher({"AAPL": 1.0}, calls), asker=Asker.SCAN, provider="alpaca")
    assert got["AAPL"].value == 1.0 and got["AAPL"].outcome == "fetched"
    assert calls == [["AAPL"]] and repo.reads == 0 and outcomes() == []


def test_count_mode_fetches_every_time_and_counts(env, monkeypatch):
    repo, _ = env
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "count")
    calls = []
    for _ in range(2):
        layer.get(Q, ["AAPL", "MSFT"], fetcher({"AAPL": 1.0}, calls), asker=Asker.SCAN, provider="alpaca")
    assert len(calls) == 2 and repo.reads == 0
    assert outcomes() == [("scan", "failed", 2), ("scan", "fetched", 2)]


def test_miss_fetches_once_in_one_batch_then_hits(env):
    repo, clock = env
    calls = []
    fetch = fetcher({"AAPL": 1.0, "MSFT": 2.0}, calls)
    layer.get(Q, ["AAPL", "MSFT"], fetch, asker=Asker.SCAN, provider="alpaca")
    clock.sleep(10)
    got = layer.get(Q, ["AAPL", "MSFT"], fetch, asker=Asker.SCAN, provider="alpaca")
    assert calls == [["AAPL", "MSFT"]]
    assert got["MSFT"].outcome == "hit" and got["MSFT"].age_s(clock.now()) == 10.0
    assert repo.rows[cache_key(Q, "AAPL")]["lease_holder"] is None
    assert outcomes() == [("scan", "fetched", 2), ("scan", "hit", 2)]


@pytest.mark.parametrize("asker,refetch", [
    (Asker.SCAN, False), (Asker.REQUOTE, True), (Asker.ADMIN_PAGE, False)])
def test_each_asker_gets_its_own_window(env, asker, refetch):
    repo, _ = env
    repo.seed("AAPL", 1.0, age_s=10)
    calls = []
    layer.get(Q, ["AAPL"], fetcher({"AAPL": 2.0}, calls), asker=asker, provider="alpaca")
    assert bool(calls) is refetch


def test_a_fresh_admin_request_bypasses_reuse_and_max_age_overrides(env):
    repo, _ = env
    repo.seed("AAPL", 1.0, age_s=3)
    calls = []
    with fresh_request():
        layer.get(Q, ["AAPL"], fetcher({"AAPL": 2.0}, calls), asker=Asker.ADMIN_PAGE, provider="alpaca")
    repo.seed("MSFT", 1.0, age_s=3)
    layer.get(Q, ["MSFT"], fetcher({"MSFT": 2.0}, calls), asker=Asker.SCAN, provider="alpaca", max_age_s=1)
    repo.seed("NVDA", 1.0, age_s=0)  # max_age_s=0.0 (V171-19 re-quote): `is not None`, never truthiness
    layer.get(Q, ["NVDA"], fetcher({"NVDA": 2.0}, calls), asker=Asker.REQUOTE, provider="alpaca", max_age_s=0.0)
    assert calls == [["AAPL"], ["MSFT"], ["NVDA"]]


def test_a_waiter_gets_the_holders_result(env):
    repo, clock = env
    repo.seed("AAPL", 1.0, age_s=600, lease_holder="other", lease_for=30)
    original = clock.sleep

    def sleep_then_land(s):
        original(s)
        repo.rows[cache_key(Q, "AAPL")].update(value=9.0, fetched_at=clock.now(),
                                               lease_holder=None, lease_until=None)
    clock.sleep = sleep_then_land
    calls = []
    got = layer.get(Q, ["AAPL"], fetcher({"AAPL": 2.0}, calls), asker=Asker.SCAN, provider="alpaca")
    assert calls == [] and got["AAPL"].value == 9.0 and got["AAPL"].outcome == "shared-wait"


def test_deadline_tier_1_fetches_itself_tier_5_gets_the_stale_value(env):
    repo, _ = env
    repo.seed("AAPL", 1.0, age_s=600, lease_holder="hung", lease_for=300)
    calls = []
    got = layer.get(Q, ["AAPL"], fetcher({"AAPL": 2.0}, calls), asker=Asker.STOP_MONITOR,
                    provider="alpaca", deadline_s=0.5)
    assert calls == [["AAPL"]] and got["AAPL"].value == 2.0
    repo.seed("MSFT", 1.0, age_s=600, lease_holder="hung", lease_for=300)
    got = layer.get(Q, ["MSFT"], fetcher({"MSFT": 2.0}, calls), asker=Asker.ADMIN_PAGE,
                    provider="alpaca", deadline_s=0.5)
    assert calls == [["AAPL"]] and got["MSFT"].value == 1.0 and got["MSFT"].age_s(clock.now()) > 500


def test_budget_deferred_serves_the_freshest_cached_value(env):
    repo, _ = env
    repo.seed("AAPL", 1.0, age_s=600)

    def denied(symbols):
        raise budget.BudgetDeferred("tier 5")
    got = layer.get(Q, ["AAPL", "NEW"], denied, asker=Asker.ADMIN_PAGE, provider="alpaca")
    assert got["AAPL"].value == 1.0 and got["AAPL"].outcome == "budget-deferred" and "NEW" not in got
    assert repo.rows[cache_key(Q, "AAPL")]["lease_holder"] is None
    assert outcomes() == [("admin_page", "budget-deferred", 2)]


def test_a_failing_fetch_releases_leases_and_raises(env):
    repo, _ = env

    def boom(symbols):
        raise ConnectionError("provider down")
    with pytest.raises(ConnectionError):
        layer.get(Q, ["AAPL"], boom, asker=Asker.SCAN, provider="alpaca")
    assert repo.rows[cache_key(Q, "AAPL")]["lease_holder"] is None
    assert outcomes() == [("scan", "failed", 1)]


@pytest.mark.parametrize("op", ["read", "lease"])
def test_postgres_errors_fail_open_to_a_direct_fetch(env, caplog, op):
    repo, _ = env
    repo.fail.add(op)
    calls = []
    with caplog.at_level(logging.WARNING):
        got = layer.get(Q, ["AAPL"], fetcher({"AAPL": 2.0}, calls), asker=Asker.STOP_MONITOR,
                        provider="alpaca")
    assert calls == [["AAPL"]] and got["AAPL"].value == 2.0
    assert any("failed open" in r.message for r in caplog.records)


def test_a_blank_reply_never_overwrites_the_last_good_value(env):
    repo, _ = env
    repo.seed("AAPL", 1.0, age_s=600)
    layer.get(Q, ["AAPL"], lambda s: {"AAPL": None}, asker=Asker.SCAN, provider="alpaca")
    assert repo.rows[cache_key(Q, "AAPL")]["value"] == 1.0


def test_spot_metals_are_fetched_but_never_cached(env):
    repo, _ = env
    calls = []
    got = layer.get(Q, ["XAUUSD", "AAPL"], fetcher({"XAUUSD": 4000.0, "AAPL": 1.0}, calls),
                    asker=Asker.SCAN, provider="alpaca")
    assert got["XAUUSD"].value == 4000.0 and calls == [["AAPL", "XAUUSD"]]
    assert not any("XAUUSD" in k for k in repo.rows)


def test_encode_and_decode_wrap_the_stored_value(env):
    repo, _ = env
    layer.get(Q, ["AAPL"], lambda s: {"AAPL": 1.5}, asker=Asker.SCAN, provider="alpaca",
              encode=lambda v: {"p": v}, decode=lambda d: d["p"])
    assert repo.rows[cache_key(Q, "AAPL")]["value"] == {"p": 1.5}
    got = layer.get(Q, ["AAPL"], lambda s: {}, asker=Asker.SCAN, provider="alpaca",
                    decode=lambda d: d["p"])
    assert got["AAPL"].value == 1.5
    assert layer.last_cached(Q, ["AAPL"])["AAPL"].value == {"p": 1.5}


def test_lease_for_bar_writers(env, monkeypatch):
    repo, _ = env
    with layer.lease(DataKind.DAILY_BARS, "AAPL", asker=Asker.BACKGROUND) as held:
        assert held is True
        assert repo.rows[cache_key(DataKind.DAILY_BARS, "AAPL")]["lease_holder"].startswith(layer.HOLDER_ID)
    assert repo.rows[cache_key(DataKind.DAILY_BARS, "AAPL")]["lease_holder"] is None
    repo.try_lease(cache_key(DataKind.DAILY_BARS, "MSFT"), "other", 300, kind="daily", symbol="MSFT", conn=None)
    with layer.lease(DataKind.DAILY_BARS, "MSFT", asker=Asker.BACKGROUND, deadline_s=0.3) as held:
        assert held is False
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "count")
    with layer.lease(DataKind.DAILY_BARS, "MSFT", asker=Asker.BACKGROUND) as held:
        assert held is True
```

- [ ] **Step 2: Write the failing Postgres test**

Create `tests/db/test_shared_layer_postgres.py`:

```python
"""v171 Review Focus 1-2 on real Postgres: one statement per hit, a hung database
fails open inside the statement timeout, a dead holder never strands waiters."""
import threading
import time

import pytest
import sqlalchemy as sa

from swingbot import config
from swingbot.core.db import side_engine
from swingbot.core.marketdata.shared import counters, layer
from swingbot.core.marketdata.shared.kinds import Asker, DataKind

Q = DataKind.QUOTE


@pytest.fixture
def side_db(db_committed, db_engine, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(config, "MARKETDATA_PG_TIMEOUT_MS", 250)
    monkeypatch.setattr(counters, "flush", lambda force=False: 0)   # no count write in the statement tally
    side_engine.reset()
    yield db_committed
    side_engine.reset()


def test_a_cache_hit_is_one_statement(side_db):
    layer.get(Q, ["AAPL", "MSFT"], lambda s: {x: 1.0 for x in s}, asker=Asker.SCAN, provider="alpaca")
    statements = []
    sa.event.listen(side_engine._get(), "before_cursor_execute",
                    lambda *a, **k: statements.append(a[2]))
    got = layer.get(Q, ["AAPL", "MSFT"], lambda s: {}, asker=Asker.SCAN, provider="alpaca")
    assert {e.outcome for e in got.values()} == {"hit"} and len(statements) == 1


def test_hung_cache_read_fails_open_within_timeout(side_db, db_engine):
    blocker = db_engine.connect()
    tx = blocker.begin()
    blocker.execute(sa.text("LOCK TABLE market_cache IN ACCESS EXCLUSIVE MODE"))
    try:
        started = time.monotonic()
        got = layer.get(Q, ["AAPL"], lambda s: {"AAPL": 2.0}, asker=Asker.STOP_MONITOR,
                        provider="alpaca")
        assert got["AAPL"].value == 2.0 and time.monotonic() - started < 1.5
    finally:
        tx.rollback()
        blocker.close()


def test_a_dead_holder_never_strands_waiters(side_db):
    side_db.execute(sa.text(
        "insert into market_cache (key, kind, symbol, fetched_at, source, lease_holder, lease_until, doc)"
        " values ('quote:AAPL:', 'quote', 'AAPL', clock_timestamp() - interval '10 minutes', 'alpaca',"
        " 'dead', clock_timestamp() + interval '1 minute', '{\"value\": 1.0}')"))
    side_db.commit()
    stale = layer.get(Q, ["AAPL"], lambda s: {"AAPL": 2.0}, asker=Asker.ADMIN_PAGE,
                      provider="alpaca", deadline_s=0.3)
    assert stale["AAPL"].value == 1.0 and stale["AAPL"].age_s() > 500
    fresh = layer.get(Q, ["AAPL"], lambda s: {"AAPL": 2.0}, asker=Asker.STOP_MONITOR,
                      provider="alpaca", deadline_s=0.3)
    assert fresh["AAPL"].value == 2.0
    side_db.execute(sa.text("update market_cache set lease_holder='dead2', fetched_at=null,"
                            " lease_until=clock_timestamp() - interval '1 second'"))
    side_db.commit()
    again = layer.get(Q, ["AAPL"], lambda s: {"AAPL": 3.0}, asker=Asker.ADMIN_PAGE, provider="alpaca")
    assert again["AAPL"].value == 3.0 and again["AAPL"].outcome == "fetched"


def test_two_concurrent_askers_make_one_provider_call(side_db):
    calls = []

    def slow(symbols):
        calls.append(symbols)
        time.sleep(0.4)
        return {s: 5.0 for s in symbols}
    results = []
    threads = [threading.Thread(target=lambda: results.append(
        layer.get(Q, ["NVDA"], slow, asker=Asker.SCAN, provider="alpaca"))) for _ in range(2)]
    for t in threads:
        t.start()
        time.sleep(0.05)
    for t in threads:
        t.join()
    assert len(calls) == 1 and sorted(r["NVDA"].outcome for r in results) == ["fetched", "shared-wait"]
```

- [ ] **Step 3: Run both to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_shared_layer.py` and `python $WT/scripts/dev/testrun.py file tests/db/test_shared_layer_postgres.py`
Expected: FAIL with `ImportError: cannot import name 'layer'`.

- [ ] **Step 4: Implement `swingbot/core/marketdata/shared/layer.py`**

Module-level imports and seams the tests patch: `side_connection`, `market_shared_repo`, `_now()` (UTC), `_monotonic = time.monotonic`, `_sleep = time.sleep`, `_POLL_S = 0.1`, `identity = lambda v: v`. Hold one call's parameters in a small `@dataclass class _Call` (kind, fetch, asker after `resolve_asker`, provider, params, window, deadline at `_monotonic() + deadline_s`, encode, decode, holder) so the helpers take one argument. Keep every function under CC 15; suggested split, each a few lines:

- `get`: dedupe symbols preserving order; dispatch on mode to `_passthrough(call, symbols, counted)` or `_get_on(call, symbols)`; `counters.flush()`; return.
- `_get_on`: split spot; `rows = _read(call, keys)` (None = failed open -> `_fetch_direct` for all); `_classify` into hits / waiting / need; `_claim(call, need)` returns owned and lost (a lease error -> warn, all of `need` treated as owned without a lease); `_fetch_and_store(call, owned + spot)`; `_wait(call, waiting + lost)`; merge the dicts.
- `_fetch_and_store`: the BudgetDeferred / other-exception / `None`-value rules of the table above; write rows `{"key", "kind": kind.value, "symbol": sym.upper(), "fetched_at": _now(), "source": provider, "value": encode(v)}` for non-spot symbols only; release the leases of owned symbols that got no value; a write error is warned, never raised.
- `_wait`: loop while symbols are pending and before the deadline: `_sleep(_POLL_S)`, re-read only the pending keys, move fresh rows to the result (`shared-wait`), and collect rows whose lease is NULL or expired for one `_claim` + `_fetch_and_store` round. A read error mid-wait -> treat the pending rest as past the deadline. Past the deadline -> `_after_deadline`: tiers 1-2 `_fetch_and_store` without a lease; tiers 3-5 serve the last row read (`shared-wait`) or count `failed`.
- **Never hold a side connection while `fetch` runs or while sleeping**: every Postgres touch is its own short `with side_connection()` block (a worker's pool is one connection, and a slow provider must not pin it).
- `_entry(row, call, outcome)` builds `Entry(call.decode(row["value"]), row["fetched_at"], row.get("source") or call.provider, outcome)`; a row is fresh when it has `fetched_at` and `"value"` and (`window is None` or age <= window); a lease is live when `lease_until > _now()` and `lease_holder != call.holder`.
- `lease` and `last_cached` per the rules above; `lease` reads the lease state with `read_entries([key])` while polling.
- Module docstring: the outcome table's first column in one paragraph, the fail-open rule, and "this module takes no budget tokens; provider calls inside `fetch` do".

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_shared_layer.py` and `python $WT/scripts/dev/testrun.py file tests/db/test_shared_layer_postgres.py`
Expected: PASS for both (the Postgres file must not skip; start the test DB if it does).
Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_shared_kinds.py` (and `test_shared_counters.py`, `test_shared_budget.py`)
Expected: PASS (the part's earlier modules unchanged).
Run: `python -m radon cc -s -n C $WT/swingbot/core/marketdata/shared/`
Expected: no output.
Run: `git -C $WT grep -n "sqlalchemy" -- swingbot/core/marketdata/`
Expected: no match (Postgres stays behind `core/db`).

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/core/marketdata/shared/layer.py tests/marketdata/test_shared_layer.py tests/db/test_shared_layer_postgres.py
git -C $WT commit -m "feat(v171): shared market-data layer core with cross-process single-flight, windows and fail-open"
```
