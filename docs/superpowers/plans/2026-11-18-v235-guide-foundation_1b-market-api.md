# v235 — Guide foundation, Part 1b: market placeholders and API (V235-4, V235-5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V235-5" -A 400 <this file>`); never read the file whole.

**Spec:** v215 — [2026-11-06-v215-guide-page.md](../specs/2026-11-06-v215-guide-page.md) (Plan A only)
**Index:** [2026-11-18-v235-guide-foundation_0-index.md](2026-11-18-v235-guide-foundation_0-index.md) — Goal, Global Constraints, `## Parallelisation`, the task ledger and `## Handoff` bind both tasks.

Ledger part 1 (V235-1..V235-5) spans two files so neither passes the 1500-line cap: [`_1-backend.md`](2026-11-18-v235-guide-foundation_1-backend.md) holds V235-1, V235-2, V235-2b, V235-3 and V235-3b (the shared facts listed at its top apply here too); this file holds V235-4 and V235-5. Ids, files and cross-task contracts are the ledger's.

# Phase 1 (continued) — Backend: market values and the API

### Task V235-4: Market placeholders and alerts per week

**Model:** sonnet — mask-aware tables built from `admits()`/`live_horizons()` at call time and a dated aggregation over the live book with a provenance label.

**Files:**
- Create: `swingbot/admin/guide/live_market.py`
- Modify: `swingbot/admin/guide/placeholders.py` (import `MARKET_PLACEHOLDERS`; `PLACEHOLDERS = _merge(RISK_PLACEHOLDERS, MARKET_PLACEHOLDERS)`)
- Test: `tests/admin/test_guide_live_market.py` (suite `admin-core`)

**Interfaces:**
- Consumes: `chapters.anchor_for` (V235-2); `placeholders._merge`, `placeholders.provenance_label`, `placeholders.resolve` (V235-3b); `levels.ALL_STRATEGY_FAMILIES`, `levels.CLUSTER_TOLERANCE_PCT` (`swingbot/core/market/levels.py:484`, `:82`); `strategy_types.HORIZONS`, `horizon_order()`, `live_horizons()`, `admits(strategy, direction, horizon_key)`, `STRATEGY_GATES` (`swingbot/core/market/strategy_types.py`); `strategy.STRATEGY_FUNCS` (`swingbot/core/market/strategy.py:79`); `config.AVWAP_LEVELS_ENABLED`; `TradeLog().get_trades(status=None, limit=None, sort_by="opened_at")` (`swingbot/core/tracking/performance.py:1411`); `swallowed(log, tag, exc, msg, *args)`.
- Produces (final; consumed by V235-5..V235-7 and Plan B):
  - `live_market.MARKET_PLACEHOLDERS: dict[str, Callable[[], str]]` with exactly `levels.families`, `CLUSTER_TOLERANCE_PCT`, `horizons.table`, `gates.list`, `alerts.per_week`.
  - `live_market._load_trades: Callable[[], list[dict]]` and `live_market._now: Callable[[], datetime]`: module attributes, looked up at call time so tests monkeypatch them.
  - `registered_strategy_keys() -> tuple[str, ...]`: sorted union of `strategy.STRATEGY_FUNCS` and `strategy_types.STRATEGY_GATES` keys (19 today: 11 + 16 with 8 shared).
  - `strategy_file_slug(key: str) -> str`: `chapters.anchor_for(key, {})`, e.g. `"Break & Retest"` → `break-retest`; Plan B's `docs/guide/strategies/<slug>.md` names.
  - `placeholders.PLACEHOLDERS` now holds both tables (23 names).

Rendered forms:

| Name | Renders |
|---|---|
| `levels.families` | one `- <family>` line per `ALL_STRATEGY_FAMILIES` entry in order; the AVWAP line reads `- AVWAP (only when `AVWAP_LEVELS_ENABLED`; currently on|off)` |
| `CLUSTER_TOLERANCE_PCT` | `1.5%` |
| `horizons.table` | `| Horizon | Swing | Longest hold | Status |`, one row per `horizon_order()` key: `` `key` ``, `label`, `<max_holding_days> days`, `live` when in `live_horizons()` else `masked — research only` |
| `gates.list` | `| Strategy | Long | Short | Status |`, one row per `registered_strategy_keys()`; a side cell lists the horizons `admits()` allows (`every live horizon` when it equals `live_horizons()`, `—` when none); status `masked — research only` when both sides are `—`, else `live` |
| `alerts.per_week` | `<mean:.1f> alerts a week, mean of the last 8 full weeks (<provenance>)`; `no live alerts in the last 8 weeks (<provenance>)` when the count is 0; `not available right now (the live paper book could not be read)` when the trade log raises |

`alerts.per_week` window: weeks start Monday 00:00 UTC; the current, unfinished week is excluded; the window is `[monday_this_week − 8 weeks, monday_this_week)`. A trade counts when its ISO `opened_at` falls in the window (a `Z` suffix and naive stamps read as UTC; unparseable or missing stamps are skipped). The provenance is `provenance_label(source="live paper book", n=<count>, run_date=<today UTC ISO date>, costs_included=False)`. Paper trades are opened from alerts, so the count of trades opened is the alert count the spec asks for.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_guide_live_market.py`:

```python
"""v235 V235-4: market placeholders, alerts per week and registered keys."""
from datetime import datetime, timezone

import pytest

from swingbot import config
from swingbot.admin.guide import live_market as lm, live_risk, placeholders as ph
from swingbot.core.market import levels, strategy_types

MARKET_NAMES = {"levels.families", "CLUSTER_TOLERANCE_PCT", "horizons.table", "gates.list",
                "alerts.per_week"}
NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)   # a Wednesday


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setattr(lm, "_load_trades", lambda: [])
    monkeypatch.setattr(lm, "_now", lambda: NOW)


def _render(name: str) -> str:
    return ph.resolve("{{" + name + "}}")


def _row(table: str, first_cell: str) -> str:
    rows = [line for line in table.splitlines() if line.startswith(f"| {first_cell} |")]
    assert len(rows) == 1, (first_cell, table)
    return rows[0]


# --- registry ------------------------------------------------------------------

def test_market_table_has_exactly_the_planned_names():
    assert set(lm.MARKET_PLACEHOLDERS) == MARKET_NAMES


def test_registry_merges_both_tables_and_nothing_else():
    assert set(ph.PLACEHOLDERS) == set(live_risk.RISK_PLACEHOLDERS) | MARKET_NAMES


@pytest.mark.parametrize("name", sorted(MARKET_NAMES))
def test_every_market_placeholder_renders_plain_text(name):
    out = _render(name)
    assert out.strip() and "{{" not in out


def test_no_sensitive_field_value_reaches_a_market_placeholder(monkeypatch):
    for f in (f for f in config.FIELDS if f.sensitive):
        monkeypatch.setattr(config, f.attr, f"SENTINEL-{f.attr}", raising=False)
    rendered = "\n".join(_render(name) for name in sorted(MARKET_NAMES))
    assert "SENTINEL-" not in rendered


# --- levels ----------------------------------------------------------------------

@pytest.mark.parametrize("enabled, state", [(True, "on"), (False, "off")])
def test_families_list_every_family_and_mark_avwap(monkeypatch, enabled, state):
    monkeypatch.setattr(config, "AVWAP_LEVELS_ENABLED", enabled)
    lines = _render("levels.families").splitlines()
    assert len(lines) == len(levels.ALL_STRATEGY_FAMILIES)
    for line, family in zip(lines, levels.ALL_STRATEGY_FAMILIES):
        assert line.startswith(f"- {family}")
    assert f"- AVWAP (only when `AVWAP_LEVELS_ENABLED`; currently {state})" in lines


def test_cluster_tolerance_reads_the_module_constant(monkeypatch):
    assert _render("CLUSTER_TOLERANCE_PCT") == f"{levels.CLUSTER_TOLERANCE_PCT:g}%"
    monkeypatch.setattr(levels, "CLUSTER_TOLERANCE_PCT", 2.0)
    assert _render("CLUSTER_TOLERANCE_PCT") == "2%"


# --- horizons --------------------------------------------------------------------

def test_horizons_table_has_every_key_and_marks_masked_ones():
    table = _render("horizons.table")
    assert table.splitlines()[0] == "| Horizon | Swing | Longest hold | Status |"
    assert len(table.splitlines()) == len(strategy_types.HORIZONS) + 2
    for key, spec in strategy_types.HORIZONS.items():
        row = _row(table, f"`{key}`")
        assert spec["label"] in row and f"{spec['max_holding_days']} days" in row
    assert _row(table, "`1w`").endswith("| masked — research only |")
    assert _row(table, "`2w`").endswith("| live |")


def test_a_cell_that_admits_a_masked_horizon_shows_it_live(monkeypatch):
    monkeypatch.setitem(strategy_types.STRATEGY_GATES, strategy_types.TURTLE_SOUP,
                        {"directions": (), "cells": {("bullish", "1w")}})
    assert _row(_render("horizons.table"), "`1w`").endswith("| live |")


# --- gates -----------------------------------------------------------------------

def test_gates_list_has_one_row_per_registered_key():
    table = _render("gates.list")
    assert table.splitlines()[0] == "| Strategy | Long | Short | Status |"
    for key in lm.registered_strategy_keys():
        _row(table, key)


def test_gates_list_reads_admits():
    table = _render("gates.list")
    assert _row(table, "VWAP") == "| VWAP | 4w | — | live |"
    assert _row(table, "Break & Retest") == "| Break & Retest | 2m, 3m, 4m | 2m, 3m, 4m | live |"
    assert _row(table, "EMA Crossover") == ("| EMA Crossover | every live horizon | "
                                             "every live horizon | live |")
    assert _row(table, "Fibonacci") == "| Fibonacci | every live horizon | — | live |"
    assert _row(table, "Turtle Soup") == "| Turtle Soup | — | — | masked — research only |"


def test_gates_list_follows_a_cell_at_call_time(monkeypatch):
    monkeypatch.setitem(strategy_types.STRATEGY_GATES, strategy_types.TURTLE_SOUP,
                        {"directions": (), "cells": {("bullish", "2w")}})
    assert _row(_render("gates.list"), "Turtle Soup") == "| Turtle Soup | 2w | — | live |"


# --- registered keys ---------------------------------------------------------------

def test_registered_keys_are_the_sorted_union():
    from swingbot.core.market.strategy import STRATEGY_FUNCS
    keys = lm.registered_strategy_keys()
    assert keys == tuple(sorted(set(STRATEGY_FUNCS) | set(strategy_types.STRATEGY_GATES)))
    assert "EMA Crossover" in keys and "Turtle Soup" in keys


@pytest.mark.parametrize("key, slug", [
    ("Break & Retest", "break-retest"),
    ("Support/Resistance", "supportresistance"),
    ("Fibonacci Limit", "fibonacci-limit"),
    ("RSI", "rsi"),
])
def test_strategy_file_slug(key, slug):
    assert lm.strategy_file_slug(key) == slug


def test_strategy_file_slugs_are_unique():
    slugs = [lm.strategy_file_slug(k) for k in lm.registered_strategy_keys()]
    assert len(slugs) == len(set(slugs))


# --- alerts per week -----------------------------------------------------------------

def test_alerts_per_week_counts_the_last_eight_full_weeks(monkeypatch):
    trades = [
        {"opened_at": "2026-11-17T10:00:00+00:00"},   # this week: excluded
        {"opened_at": "2026-11-15T23:59:00+00:00"},   # last full week: in
        {"opened_at": "2026-09-21T00:00:00+00:00"},   # window start, inclusive: in
        {"opened_at": "2026-09-20T23:59:59+00:00"},   # before the window: out
        {"opened_at": "2026-10-01T10:00:00Z"},        # Z suffix: in
        {"opened_at": "2026-10-02T10:00:00"},         # naive, read as UTC: in
        {"opened_at": None},
        {"opened_at": "garbage"},
        {},
    ]
    monkeypatch.setattr(lm, "_load_trades", lambda: trades)
    assert _render("alerts.per_week") == (
        "0.5 alerts a week, mean of the last 8 full weeks (Source: live paper book; "
        "N = 4; as of 2026-11-18; costs not included; before tax)")


def test_alerts_per_week_empty_book():
    assert _render("alerts.per_week") == (
        "no live alerts in the last 8 weeks (Source: live paper book; N = 0; "
        "as of 2026-11-18; costs not included; before tax)")


def test_alerts_per_week_survives_an_unreadable_book(monkeypatch, caplog):
    def boom():
        raise RuntimeError("database down")
    monkeypatch.setattr(lm, "_load_trades", boom)
    assert _render("alerts.per_week") == (
        "not available right now (the live paper book could not be read)")
    assert "database down" in caplog.text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_live_market.py`
Expected: FAIL at collection: `ImportError: cannot import name 'live_market' from 'swingbot.admin.guide'`.

- [ ] **Step 3: Implement**

Create `swingbot/admin/guide/live_market.py`:

```python
"""v235: market placeholders for the guide -- level families, the cluster
tolerance, the horizon table, per-strategy gates and alerts per week -- plus
the registered strategy keys Plan B's cards are checked against.

Masks are read at call time through live_horizons() and admits(), never from
a hard-coded horizon, so a cell shipped in code shows up here with no edit.
alerts.per_week reads the live paper book and always carries its provenance.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

from swingbot import config
from swingbot.admin.guide.chapters import anchor_for
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.market import levels, strategy_types

log = logging.getLogger(__name__)

_WEEKS = 8
_MASKED = "masked — research only"
_NONE = "—"
_ALL_LIVE = "every live horizon"
_DIRECTIONS = ("bullish", "bearish")   # table columns Long, Short


def _load_trades() -> list[dict]:
    """Every live paper trade (patched in tests; the real read needs the database)."""
    from swingbot.core.tracking.performance import TradeLog
    return TradeLog().get_trades(status=None, limit=None, sort_by="opened_at") or []


def _now() -> datetime:
    return datetime.now(timezone.utc)


def registered_strategy_keys() -> tuple[str, ...]:
    """Sorted union of the signal functions and the gate table's keys."""
    from swingbot.core.market.strategy import STRATEGY_FUNCS
    return tuple(sorted(set(STRATEGY_FUNCS) | set(strategy_types.STRATEGY_GATES)))


def strategy_file_slug(key: str) -> str:
    """The docs/guide/strategies/<slug>.md name for a strategy key (anchor rule)."""
    return anchor_for(key, {})


def _family_line(name: str) -> str:
    if name != "AVWAP":
        return f"- {name}"
    state = "on" if config.AVWAP_LEVELS_ENABLED else "off"
    return f"- {name} (only when `AVWAP_LEVELS_ENABLED`; currently {state})"


def _families() -> str:
    return "\n".join(_family_line(name) for name in levels.ALL_STRATEGY_FAMILIES)


def _horizon_row(key: str, live: set[str]) -> str:
    spec = strategy_types.HORIZONS[key]
    status = "live" if key in live else _MASKED
    return f"| `{key}` | {spec['label']} | {spec['max_holding_days']} days | {status} |"


def _horizons_table() -> str:
    live = set(strategy_types.live_horizons())
    rows = ["| Horizon | Swing | Longest hold | Status |", "|---|---|---|---|"]
    rows += [_horizon_row(key, live) for key in strategy_types.horizon_order()]
    return "\n".join(rows)


def _side_cell(strategy: str, direction: str, live: tuple[str, ...]) -> str:
    admitted = tuple(hk for hk in strategy_types.horizon_order()
                     if strategy_types.admits(strategy, direction, hk))
    if not admitted:
        return _NONE
    return _ALL_LIVE if admitted == live else ", ".join(admitted)


def _gate_row(strategy: str, live: tuple[str, ...]) -> str:
    cells = [_side_cell(strategy, direction, live) for direction in _DIRECTIONS]
    status = _MASKED if all(cell == _NONE for cell in cells) else "live"
    return f"| {strategy} | {cells[0]} | {cells[1]} | {status} |"


def _gates_list() -> str:
    live = tuple(strategy_types.live_horizons())
    rows = ["| Strategy | Long | Short | Status |", "|---|---|---|---|"]
    rows += [_gate_row(key, live) for key in registered_strategy_keys()]
    return "\n".join(rows)


def _week_start(moment: datetime) -> datetime:
    day = moment.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return day - timedelta(days=day.weekday())


def _opened(trade: dict) -> datetime | None:
    raw = trade.get("opened_at")
    if not raw:
        return None
    try:
        stamp = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def _count_in_window(trades: list[dict], start: datetime, end: datetime) -> int:
    stamps = (_opened(trade) for trade in trades)
    return sum(1 for stamp in stamps if stamp is not None and start <= stamp < end)


def _alerts_per_week() -> str:
    from swingbot.admin.guide.placeholders import provenance_label   # placeholders imports us
    try:
        trades = _load_trades()
    except Exception as exc:  # the guide renders without the database
        swallowed(log, "ops.admin.guide.alerts_per_week", exc,
                  "guide: live paper book unreadable: %s", exc)
        return "not available right now (the live paper book could not be read)"
    now = _now()
    end = _week_start(now)
    count = _count_in_window(trades, end - timedelta(weeks=_WEEKS), end)
    label = provenance_label(source="live paper book", n=count,
                             run_date=now.date().isoformat(), costs_included=False)
    if count == 0:
        return f"no live alerts in the last {_WEEKS} weeks ({label})"
    return f"{count / _WEEKS:.1f} alerts a week, mean of the last {_WEEKS} full weeks ({label})"


MARKET_PLACEHOLDERS: dict[str, Callable[[], str]] = {
    "levels.families": _families,
    "CLUSTER_TOLERANCE_PCT": lambda: f"{levels.CLUSTER_TOLERANCE_PCT:g}%",
    "horizons.table": _horizons_table,
    "gates.list": _gates_list,
    "alerts.per_week": _alerts_per_week,
}
```

In `swingbot/admin/guide/placeholders.py`, replace the import line and the `PLACEHOLDERS` assignment:

```python
from swingbot.admin.guide.live_market import MARKET_PLACEHOLDERS
from swingbot.admin.guide.live_risk import RISK_PLACEHOLDERS
```

```python
PLACEHOLDERS: Mapping[str, Callable[[], str]] = _merge(RISK_PLACEHOLDERS, MARKET_PLACEHOLDERS)
```

`swallowed(...)` logs through `log` at WARNING with the message `guide: live paper book unreadable: database down`, which `caplog` captures. The tag `ops.admin.guide.alerts_per_week` is new and unique (`git grep -n "ops.admin.guide" -- swingbot` shows only this site).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_live_market.py`
Expected: PASS (`0 failed`).

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_placeholders.py`
Expected: PASS (V235-3/V235-3b's tests are unchanged and still green with the merged registry).

Run: `python scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py`
Expected: PASS (the new handler is tagged).

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/guide/live_market.py swingbot/admin/guide/placeholders.py tests/admin/test_guide_live_market.py
git commit -m "feat(guide): market placeholders -- families, horizons, gates, alerts per week (v235 V235-4)"
```

### Task V235-5: Guide API routes and access rows

**Model:** sonnet — a new v1 endpoint module that follows `research.py`/`versions.py`, plus the v207 access matrix rows; the failure paths (unknown placeholder, bad chapter) need care.

**Files:**
- Create: `swingbot/admin/api_v1/guide.py`
- Modify: `swingbot/admin/api_v1/__init__.py:210-213` (add `guide` to `register()`'s import tuple)
- Modify: `tests/admin/access_expectations.py:30-45` (`_VIEWER_GET`) and `:85-102` (`SAMPLE_PATHS`)
- Test: `tests/admin/test_api_v1_guide.py` (suite `admin`)

**Interfaces:**
- Consumes: `chapters.load_chapters` (V235-2b), `chapters.extract_headings`, `chapters.GuideFormatError`, `chapters.Chapter`, `chapters.guide_dir` (V235-2); `placeholders.resolve`, `placeholders.UnknownPlaceholder` (V235-3b; full registry from V235-4); `api_v1.ApiError(code, message, status)`, `api_v1.api_v1` blueprint, `api_v1.auth.require_auth`.
- Produces (final; the frontend models in V235-9 mirror this JSON):
  - `GET /api/v1/guide` → `{"chapters": [{"slug": str, "title": str, "order": int, "reviewed_for": str, "headings": [{"level": int, "text": str, "anchor": str}]}]}`, chapters by `order`; headings come from the **resolved** body (a heading with a placeholder carries its live text and anchor).
  - `GET /api/v1/guide/<slug>` → `{"slug": str, "title": str, "reviewed_for": str, "markdown": str}`, placeholders resolved.
  - Errors: unknown slug → 404 `not_found`; unknown placeholder → 500 `guide_placeholder` (the name is logged at ERROR, never returned or echoed as raw `{{…}}`); a malformed chapter file → 500 `guide_invalid`.
  - `guide._chapters() -> tuple[Chapter, ...]`, `functools.lru_cache(maxsize=1)` over `load_chapters()`: chapter files are read once per process.
  - `guide.clear_cache() -> None`: drops that cache (tests; a deploy restarts the process anyway).
  - Viewer-readable: `/api/v1/guide` is **not** added to `swingbot/admin/access.py:19` `ADMIN_ONLY_PREFIXES`.

Behaviour notes:
- Chapter files are cached per process (spec § API); placeholders resolve on **every** request, so live values (`alerts.per_week`, a hot-reloaded config cap) never freeze until a restart (index Handoff, plan-writer decisions).
- `lru_cache` does not cache a raised exception, so a fixed file is picked up on the next request after a redeploy; nothing else invalidates.
- Every v1 response already gets `Cache-Control: no-store` from the blueprint's `after_request`; the test pins it for these routes.
- `tests/admin/conftest.py`'s `client` fixture builds the app against the shared test database (`tests.store_seed`). If the run reports a database connection error, run `/replicate-prod-db` once (it starts the shared `swing-db` container) and re-run this file alone.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_api_v1_guide.py`:

```python
"""v235 V235-5: GET /api/v1/guide and /api/v1/guide/<slug>."""
import logging

import pytest

from swingbot import config
from swingbot.admin.guide import chapters as chapters_mod
from tests.admin.api_v1_contract import assert_error, assert_shape

_LOGIN = {"username": "admin", "password": "admin"}


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture
def guide_root(tmp_path, monkeypatch):
    """An empty docs/guide stand-in; the route module's cache is cleared around it."""
    from swingbot.admin.api_v1 import guide
    root = tmp_path / "guide"
    root.mkdir()
    monkeypatch.setattr(chapters_mod, "guide_dir", lambda: root)
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 2.0)
    guide.clear_cache()
    yield root
    guide.clear_cache()


def _chapter(root, order: int, slug: str, body: str, title: str = "") -> None:
    (root / f"{order:02d}-{slug}.md").write_text(
        f"---\ntitle: {title or slug.title()}\nslug: {slug}\norder: {order}\n"
        f"reviewed_for: 2.19.2\nsources: []\n---\n{body}", encoding="utf-8")


# --- auth --------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/api/v1/guide", "/api/v1/guide/what-it-is"])
def test_requires_auth(client, guide_root, path):
    assert client.get(path).status_code == 401


# --- index -------------------------------------------------------------------

def test_index_lists_chapters_by_order_with_headings(logged_in, guide_root):
    _chapter(guide_root, 12, "glossary", "## Terms\n### R multiple\n", title="Glossary")
    _chapter(guide_root, 1, "what-it-is", "> **In plain words** paper only.\n\n## The notice\n",
             title="What the bot is (and isn't)")
    resp = logged_in.get("/api/v1/guide")
    assert resp.status_code == 200
    assert "no-store" in resp.headers.get("Cache-Control", "")
    body = resp.get_json()
    assert_shape(body, {"chapters": list})
    first, second = body["chapters"]
    assert_shape(first, {"slug": str, "title": str, "order": int, "reviewed_for": str,
                         "headings": list}, where="chapters[0]")
    assert [first["slug"], second["slug"]] == ["what-it-is", "glossary"]
    assert first["title"] == "What the bot is (and isn't)"
    assert first["reviewed_for"] == "2.19.2"
    assert first["headings"] == [{"level": 2, "text": "The notice", "anchor": "the-notice"}]
    assert second["headings"] == [
        {"level": 2, "text": "Terms", "anchor": "terms"},
        {"level": 3, "text": "R multiple", "anchor": "r-multiple"},
    ]


def test_index_is_empty_without_chapters(logged_in, guide_root):
    assert logged_in.get("/api/v1/guide").get_json() == {"chapters": []}


def test_index_headings_come_from_the_resolved_body(logged_in, guide_root):
    _chapter(guide_root, 8, "sizing-risk", "## Stops past {{MAX_STOP_LOSS_PCT}}\n")
    heading = logged_in.get("/api/v1/guide").get_json()["chapters"][0]["headings"][0]
    assert heading == {"level": 2, "text": "Stops past 2%", "anchor": "stops-past-2"}


# --- one chapter -------------------------------------------------------------

def test_chapter_returns_resolved_markdown(logged_in, guide_root):
    _chapter(guide_root, 1, "what-it-is", "Stop cap {{ MAX_STOP_LOSS_PCT }}.\n", title="What")
    resp = logged_in.get("/api/v1/guide/what-it-is")
    assert resp.status_code == 200
    body = resp.get_json()
    assert_shape(body, {"slug": str, "title": str, "reviewed_for": str, "markdown": str})
    assert body == {"slug": "what-it-is", "title": "What", "reviewed_for": "2.19.2",
                    "markdown": "Stop cap 2%.\n"}


def test_placeholders_resolve_per_request_while_files_stay_cached(logged_in, guide_root,
                                                                  monkeypatch):
    _chapter(guide_root, 1, "what-it-is", "Cap {{MAX_STOP_LOSS_PCT}}\n")
    assert logged_in.get("/api/v1/guide/what-it-is").get_json()["markdown"] == "Cap 2%\n"
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 1.5)          # a hot reload
    _chapter(guide_root, 3, "pipeline", "New file\n")               # not served until restart
    assert logged_in.get("/api/v1/guide/what-it-is").get_json()["markdown"] == "Cap 1.5%\n"
    assert [c["slug"] for c in logged_in.get("/api/v1/guide").get_json()["chapters"]] == [
        "what-it-is"]


def test_unknown_slug_is_404(logged_in, guide_root):
    _chapter(guide_root, 1, "what-it-is", "Text\n")
    assert_error(logged_in.get("/api/v1/guide/nope"), "not_found", 404)


# --- failures ----------------------------------------------------------------

def test_unknown_placeholder_is_500_and_logged_never_raw(logged_in, guide_root, caplog):
    _chapter(guide_root, 1, "what-it-is", "Secret {{DISCORD_TOKEN}}\n")
    caplog.set_level(logging.ERROR, logger="swingbot.admin.api_v1.guide")
    resp = logged_in.get("/api/v1/guide/what-it-is")
    assert_error(resp, "guide_placeholder", 500)
    assert "{{" not in resp.get_data(as_text=True)
    assert "DISCORD_TOKEN" in caplog.text and "what-it-is" in caplog.text


def test_unknown_placeholder_also_fails_the_index(logged_in, guide_root):
    _chapter(guide_root, 1, "what-it-is", "## Heading\n\n{{nope}}\n")
    assert_error(logged_in.get("/api/v1/guide"), "guide_placeholder", 500)


def test_malformed_chapter_is_500_guide_invalid(logged_in, guide_root):
    (guide_root / "01-what-it-is.md").write_text("no front matter\n", encoding="utf-8")
    assert_error(logged_in.get("/api/v1/guide"), "guide_invalid", 500)
    assert_error(logged_in.get("/api/v1/guide/what-it-is"), "guide_invalid", 500)


# --- access ------------------------------------------------------------------

def test_guide_is_not_admin_only():
    from swingbot.admin import access
    assert not any("/api/v1/guide".startswith(p) for p in access.ADMIN_ONLY_PREFIXES)
```

`ADMIN_ONLY_PREFIXES` (`swingbot/admin/access.py:19`) holds full `/api/v1/...` prefixes matched on segment boundaries, so the last test compares the same form.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_guide.py`
Expected: FAIL: `ModuleNotFoundError: No module named 'swingbot.admin.api_v1.guide'` in the `guide_root` fixture (or 404s for the auth test).

- [ ] **Step 3: Implement the endpoint module**

Create `swingbot/admin/api_v1/guide.py`:

```python
"""GET /api/v1/guide and /api/v1/guide/<slug> -- the Insights -> Guide chapters (v235).

Chapters are Markdown files in docs/guide/ that ship in the image (`COPY . .`),
so what this serves is the guide as of the deployed build. The files are read
once per process (`_chapters`, lru_cache); `{{name}}` placeholders resolve on
every request, so live values (a hot-reloaded cap, alerts per week) are current.

Failure is loud and never leaks raw text: a malformed chapter is 500
`guide_invalid`; a placeholder outside the whitelist is 500 `guide_placeholder`
with the name logged here, never echoed. Viewer-readable (not in
access.ADMIN_ONLY_PREFIXES): the guide explains the bot, it changes nothing.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from flask import jsonify

from swingbot.admin.guide import chapters as _chapters_mod
from swingbot.admin.guide import placeholders as _placeholders
from swingbot.admin.guide.chapters import Chapter

from . import ApiError, api_v1
from .auth import require_auth

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _chapters() -> tuple[Chapter, ...]:
    return tuple(_chapters_mod.load_chapters())


def clear_cache() -> None:
    """Forget the cached chapter files (tests; a deploy restarts the process)."""
    _chapters.cache_clear()


def _loaded() -> tuple[Chapter, ...]:
    try:
        return _chapters()
    except _chapters_mod.GuideFormatError as exc:
        log.error("guide chapter invalid: %s", exc)
        raise ApiError("guide_invalid", "A guide chapter could not be read.", 500) from exc


def _resolved(chapter: Chapter) -> str:
    try:
        return _placeholders.resolve(chapter.body)
    except _placeholders.UnknownPlaceholder as exc:
        log.error("guide placeholder %r unknown in chapter %s", exc.name, chapter.slug)
        raise ApiError("guide_placeholder",
                       f"Guide chapter {chapter.slug} could not be rendered.", 500) from exc


def _summary(chapter: Chapter) -> dict[str, Any]:
    headings = _chapters_mod.extract_headings(_resolved(chapter))
    return {
        "slug": chapter.slug,
        "title": chapter.title,
        "order": chapter.order,
        "reviewed_for": chapter.reviewed_for,
        "headings": [{"level": h.level, "text": h.text, "anchor": h.anchor} for h in headings],
    }


@api_v1.route("/guide", methods=["GET"])
@require_auth
def guide_index():
    return jsonify({"chapters": [_summary(chapter) for chapter in _loaded()]})


@api_v1.route("/guide/<slug>", methods=["GET"])
@require_auth
def guide_chapter(slug: str):
    chapter = next((c for c in _loaded() if c.slug == slug), None)
    if chapter is None:
        raise ApiError("not_found", "No guide chapter has that name.", 404)
    return jsonify({
        "slug": chapter.slug,
        "title": chapter.title,
        "reviewed_for": chapter.reviewed_for,
        "markdown": _resolved(chapter),
    })
```

The 404 message does not echo the requested slug (no reflected input in an error body).

- [ ] **Step 4: Register the module**

In `swingbot/admin/api_v1/__init__.py`, inside `register()`, replace the import tuple (lines 210-213) with:

```python
    from . import (access_hook, analytics, benchmark, calendar, cancel_precision, dashboard,  # noqa: F401
                   equity, feed_posts, guide, jobs, live, market, market_updates, ops_health,
                   reports, research, risk, session, system, trade_commands, trades, users,
                   versions, watchlist)  # (routes + the v207 access hook)
```

Nothing is imported at that module's top level (its docstring: endpoint modules are imported only in `register()`).

- [ ] **Step 5: Add the access rows**

In `tests/admin/access_expectations.py`, add the two rules to `_VIEWER_GET` after `"/feed-posts/kinds"`:

```python
    "/cancel-precision", "/dashboard", "/equity/candles", "/events", "/feed-posts",
    "/feed-posts/kinds", "/guide", "/guide/<slug>", "/health", "/live",
```

and the slug sample to `SAMPLE_PATHS`, after the `/jobs/<job_id>/result` row:

```python
    f"{V1}/guide/<slug>": f"{V1}/guide/what-it-is",
```

`SPA_WORKSPACES` already holds `"insights"`, so `/insights/guide` and `/insights/guide/<slug>` are served by `spa.py` with no change here.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_guide.py`
Expected: PASS (`0 failed`).

Run: `python scripts/dev/testrun.py file tests/admin/test_access_contract.py`
Expected: PASS (every served rule has a row; `/api/v1/guide` and `/api/v1/guide/<slug>` are `viewer`).

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 7: Commit**

```bash
git add swingbot/admin/api_v1/guide.py swingbot/admin/api_v1/__init__.py tests/admin/access_expectations.py tests/admin/test_api_v1_guide.py
git commit -m "feat(api): GET /api/v1/guide and /guide/<slug>, viewer-readable (v235 V235-5)"
```
