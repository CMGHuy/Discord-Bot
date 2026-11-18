# v237 — Guide trading core, part 1: placeholders, cards loader, content checks

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V237-3" -A 400 <this file>`); never read the file whole.

**Spec:** v215 — [2026-11-06-v215-guide-page.md](../specs/2026-11-06-v215-guide-page.md), Plan B ("Trading core").
**Index:** [2026-11-18-v237-guide-trading-core_0-index.md](2026-11-18-v237-guide-trading-core_0-index.md) — Goal, Global Constraints, `## Parallelisation`, the task ledger and the binding `## Handoff` live there; every task below implicitly includes the index's Global Constraints.
**Brief:** `.superpowers/briefs/2026-11-18-v237-guide-trading-core.md`.

This part builds the machinery chapters 4–8 stand on: the sizing placeholders read the stored account row (V237-1), new rule and gate-switch placeholder tables (V237-2, V237-3), the strategy card parser and the "costs not recorded" provenance (V237-4), the `strategies.cards` placeholder (V237-5) and the content checks over cards (V237-6). No chapter or card text is written here.

**Starting state.** v235 and v236 are merged on `main` before V237-1 starts (index `Depends on`). The files this part edits were created by those plans: `swingbot/admin/guide/{chapters,live_risk,live_market,placeholders}.py`, `tests/admin/test_guide_{placeholders,live_market,content,chapter_text}.py`, `tests/scripts/test_guide_sources.py`, `scripts/dev/guide_sources.py`. Before each task, `git grep -n` the symbols it says it consumes; a missing one means v235/v236 is not merged — stop and report, never recreate it.

**Test runs.** No test in this part opens the database: `live_market._load_trades` and (from V237-1) `live_risk._load_account` are patched by autouse fixtures. A connection error therefore means a fixture is missing in that module — add it, never skip the test.

# Phase 1 — Live values and the card contract

### Task V237-1: Sizing placeholders read the stored account row

**Model:** sonnet — rewires three existing placeholders to a database-backed reader with a logged fallback and adjusts v235's tests across several modules without losing their coverage.

**Why.** `RISK_PER_TRADE_PCT`, `MAX_RISK_AMOUNT_ABSOLUTE`, `POSITION_SIZING_MODE`, `MAX_POSITION_SIZE_PCT`, `MAX_POSITION_VALUE_ABSOLUTE` and `MAX_OPEN_POSITIONS` in `.env` only *seed* a brand-new account row (`swingbot/core/planning/account.py:130 _SEED_ENV_KEYS`); every alert is sized from the stored row `load_account_config()` returns (`account.py:160`), which `!account risk …` edits at any time. v235's placeholders read `config.X`, so the guide could print the seed while the sizer uses something else (index Handoff 4). The heat caps (`PORTFOLIO_HEAT_CAP_PCT`, `CORRELATED_HEAT_CAP_PCT`, `SECTOR_HEAT_CAP_PCT`) and `RISK_PER_TRADE_PCT.max` (the schema `Field.max`) keep reading config: the scan reads those from config.

**Files:**
- Modify (created by v235 V235-3): `swingbot/admin/guide/live_risk.py`
- Test: `tests/admin/test_guide_placeholders.py` (V235-3/3b: edit three tests, add a fixture and tests)
- Modify (fixture only): `tests/admin/test_guide_content.py` (V235-6), `tests/admin/test_guide_chapter_text.py` (V236-8), and any other module Step 5's grep lists

**Interfaces:**
- Consumes: `account.load_account_config(*, conn=None) -> dict` (`swingbot/core/planning/account.py:160`; row keys `risk_pct`, `max_risk_amount_absolute`, `sizing_mode`, `max_position_pct` (a percent: `balance * max_position_pct / 100`, `account.py:575`), `max_position_value_absolute`, `max_open_positions`); `swallowed(log, tag, exc, msg="", *args)` (`swingbot/core/infra/swallowed.py:62`); v235's `live_risk._pct`, `_money`, `_field`, `_cfg_pct`, `RISK_PLACEHOLDERS`.
- Produces (ledger): `live_risk._load_account: Callable[[], dict]` (module attribute, looked up at call time, monkeypatched in tests); `live_risk.UNAVAILABLE = "not available right now"`; `live_risk._account_value(key: str) -> object | None` (`None` after `swallowed(log, "ops.admin.guide.account_row", exc, ...)`, or when the key is absent); `RISK_PLACEHOLDERS` = 21 names: v235's 18 plus `MAX_POSITION_SIZE_PCT` (`"10%"` for a row value `10.0`; the schema default `0.1` renders `"0.1%"`), `MAX_POSITION_VALUE_ABSOLUTE` (`"$1,000"`), `MAX_OPEN_POSITIONS` (`"30"`); test dict `_ACCOUNT_ROW` and autouse fixture `_stored_account` in every guide test module that resolves chapter bodies.

Rendered forms of the six account-row names (each read when it renders; a failed read or a missing key renders `not available right now`):

| Name | Row key | Renders (fixture row) |
|---|---|---|
| `RISK_PER_TRADE_PCT` | `risk_pct` | `1%` |
| `MAX_RISK_AMOUNT_ABSOLUTE` | `max_risk_amount_absolute` | `$100` |
| `POSITION_SIZING_MODE` | `sizing_mode` | ``Fixed risk % per trade (`risk_pct`)`` |
| `MAX_POSITION_SIZE_PCT` | `max_position_pct` | `10%` |
| `MAX_POSITION_VALUE_ABSOLUTE` | `max_position_value_absolute` | `$1,000` |
| `MAX_OPEN_POSITIONS` | `max_open_positions` | `30` |

`_load_account` is a module-level `def` that imports `load_account_config` at call time (the ledger's "`= account.load_account_config`" in callable form): `swingbot.core.planning.account` pulls in the trade store, and a call-time import keeps `import swingbot.admin.guide.live_risk` free of it, the way v235 handles `gap_sizing`. Tests replace the attribute either way.

- [ ] **Step 1: Confirm the consumed names**

Run: `git grep -n "^def load_account_config\|^_SEED_ENV_KEYS" swingbot/core/planning/account.py`
Expected: two lines (`:130`, `:160` today).

Run: `git grep -n "^RISK_PLACEHOLDERS\|^def _money\|^def _pct\|^def _cfg_pct\|^def _field\|^def _sizing_mode" swingbot/admin/guide/live_risk.py`
Expected: six lines (v235 V235-3).

- [ ] **Step 2: Write the failing tests**

In `tests/admin/test_guide_placeholders.py`:

(a) Extend `RISK_NAMES` and add the row fixture — replace the set's last line `"sizing.risk_ceiling", "sizing.gap", "version.bot",` and its closing `}` with:

```python
    "sizing.risk_ceiling", "sizing.gap", "version.bot",
    "MAX_POSITION_SIZE_PCT", "MAX_POSITION_VALUE_ABSOLUTE", "MAX_OPEN_POSITIONS",
}

#: The stored account row the sizer reads (account.load_account_config()).
_ACCOUNT_ROW = {
    "risk_pct": 1.0, "max_risk_amount_absolute": 100.0, "sizing_mode": "risk_pct",
    "max_position_pct": 10.0, "max_position_value_absolute": 1000.0, "max_open_positions": 30,
}


@pytest.fixture(autouse=True)
def _stored_account(monkeypatch):
    """live_risk._load_account would read the database."""
    monkeypatch.setattr(live_risk, "_load_account", lambda: dict(_ACCOUNT_ROW))


def _row_with(monkeypatch, **values):
    monkeypatch.setattr(live_risk, "_load_account", lambda: {**_ACCOUNT_ROW, **values})
```

(b) In `test_config_values_are_read_at_call_time`'s parametrize list, delete the four rows whose attr is `"RISK_PER_TRADE_PCT"` or `"MAX_RISK_AMOUNT_ABSOLUTE"` (`("RISK_PER_TRADE_PCT", 1.0, "1%")` and the three `MAX_RISK_AMOUNT_ABSOLUTE` rows). Those names no longer read config; their cases move to the row test in (e).

(c) Replace `test_sizing_mode_uses_the_option_label` with:

```python
@pytest.mark.parametrize("mode, text", [
    ("risk_pct", "Fixed risk % per trade (`risk_pct`)"),
    ("vol_target", "Volatility-targeted (portfolio vol budget) (`vol_target`)"),
    ("unheard_of", "unheard_of (`unheard_of`)"),
])
def test_sizing_mode_uses_the_option_label(monkeypatch, mode, text):
    _row_with(monkeypatch, sizing_mode=mode)
    assert _risk("POSITION_SIZING_MODE") == text
```

(d) In `test_resolve_substitutes_every_occurrence`, replace the line `monkeypatch.setattr(config, "RISK_PER_TRADE_PCT", 1.0)` with `_row_with(monkeypatch, risk_pct=1.0)` (expected text unchanged).

(e) Append after `test_version_bot`:

```python
# --- the stored account row ----------------------------------------------------

@pytest.mark.parametrize("name, key, value, text", [
    ("RISK_PER_TRADE_PCT", "risk_pct", 1.0, "1%"),
    ("RISK_PER_TRADE_PCT", "risk_pct", 0.5, "0.5%"),
    ("MAX_RISK_AMOUNT_ABSOLUTE", "max_risk_amount_absolute", 100.0, "$100"),
    ("MAX_RISK_AMOUNT_ABSOLUTE", "max_risk_amount_absolute", 62.5, "$62.50"),
    ("MAX_RISK_AMOUNT_ABSOLUTE", "max_risk_amount_absolute", 1500.0, "$1,500"),
    ("MAX_POSITION_SIZE_PCT", "max_position_pct", 10.0, "10%"),
    ("MAX_POSITION_SIZE_PCT", "max_position_pct", 0.1, "0.1%"),
    ("MAX_POSITION_VALUE_ABSOLUTE", "max_position_value_absolute", 1000.0, "$1,000"),
    ("MAX_OPEN_POSITIONS", "max_open_positions", 30, "30"),
    ("MAX_OPEN_POSITIONS", "max_open_positions", 5, "5"),
])
def test_account_values_come_from_the_stored_row(monkeypatch, name, key, value, text):
    _row_with(monkeypatch, **{key: value})
    assert _risk(name) == text


@pytest.mark.parametrize("name", [
    "RISK_PER_TRADE_PCT", "MAX_RISK_AMOUNT_ABSOLUTE", "MAX_POSITION_SIZE_PCT",
    "MAX_POSITION_VALUE_ABSOLUTE", "MAX_OPEN_POSITIONS"])
def test_the_env_seed_is_not_what_renders(monkeypatch, name):
    before = _risk(name)
    monkeypatch.setattr(config, name, 1.99)
    assert _risk(name) == before


def test_sizing_mode_ignores_the_env_seed(monkeypatch):
    monkeypatch.setattr(config, "POSITION_SIZING_MODE", "kelly")
    assert _risk("POSITION_SIZING_MODE") == "Fixed risk % per trade (`risk_pct`)"


def test_the_row_is_read_on_every_render(monkeypatch):
    calls = []
    monkeypatch.setattr(live_risk, "_load_account",
                        lambda: calls.append(1) or dict(_ACCOUNT_ROW))
    _risk("RISK_PER_TRADE_PCT")
    _risk("RISK_PER_TRADE_PCT")
    assert len(calls) == 2


ACCOUNT_NAMES = ["RISK_PER_TRADE_PCT", "MAX_RISK_AMOUNT_ABSOLUTE", "POSITION_SIZING_MODE",
                 "MAX_POSITION_SIZE_PCT", "MAX_POSITION_VALUE_ABSOLUTE", "MAX_OPEN_POSITIONS"]


@pytest.mark.parametrize("name", ACCOUNT_NAMES)
def test_an_unreadable_row_renders_not_available(monkeypatch, caplog, name):
    def boom():
        raise RuntimeError("database down")
    monkeypatch.setattr(live_risk, "_load_account", boom)
    assert _risk(name) == live_risk.UNAVAILABLE == "not available right now"
    assert "database down" in caplog.text


@pytest.mark.parametrize("name", ACCOUNT_NAMES)
def test_a_row_without_the_key_renders_not_available(monkeypatch, name):
    monkeypatch.setattr(live_risk, "_load_account", lambda: {})
    assert _risk(name) == live_risk.UNAVAILABLE


def test_heat_caps_and_the_risk_maximum_still_read_config(monkeypatch):
    monkeypatch.setattr(config, "PORTFOLIO_HEAT_CAP_PCT", 7.0)
    assert _risk("PORTFOLIO_HEAT_CAP_PCT") == "7%"
    field = next(f for f in config.FIELDS if f.attr == "RISK_PER_TRADE_PCT")
    assert _risk("RISK_PER_TRADE_PCT.max") == f"{float(field.max):g}%"
```

`test_risk_table_has_exactly_the_planned_names`, `test_every_risk_placeholder_renders_plain_text`, `test_every_risk_name_is_registered`, `test_resolve_renders_each_risk_name_like_the_table` and both secrets tests pick up the three new names through `RISK_NAMES` with no edit.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_placeholders.py`
Expected: FAIL — every test errors at setup with `AttributeError: <module 'swingbot.admin.guide.live_risk' ...> has no attribute '_load_account'` (the autouse fixture).

- [ ] **Step 4: Implement the account-row reader**

In `swingbot/admin/guide/live_risk.py`:

(a) Add one paragraph to the module docstring, after its first paragraph:

```text
Sizing settings an operator edits with !account (risk per trade, the dollar
risk cap, the sizing mode, the position caps, the open-position limit) come
from the stored account row the sizer reads, never from their .env seeds.
```

(b) Add `import logging` to the standard-library imports and `from swingbot.core.infra.swallowed import swallowed` to the `swingbot` imports; below the imports add:

```python
log = logging.getLogger(__name__)

UNAVAILABLE = "not available right now"
```

(c) Delete v235's `_sizing_mode` and add, right after `_field`:

```python
def _load_account() -> dict:
    """The stored account row (patched in tests; the real read needs the database)."""
    from swingbot.core.planning.account import load_account_config
    return load_account_config()


def _account_value(key: str):
    """One setting from the stored account row; None when it cannot be read."""
    try:
        return _load_account().get(key)
    except Exception as exc:  # the guide renders without the database
        swallowed(log, "ops.admin.guide.account_row", exc,
                  "guide: account row unreadable: %s", exc)
        return None


def _from_account(key: str, render: Callable[[object], str]) -> Callable[[], str]:
    def placeholder() -> str:
        value = _account_value(key)
        return UNAVAILABLE if value is None else render(value)
    return placeholder


def _mode_text(value) -> str:
    label = dict(_field("POSITION_SIZING_MODE").options).get(value, value)
    return f"{label} (`{value}`)"


def _count(value) -> str:
    return str(int(value))
```

(d) In `RISK_PLACEHOLDERS`, replace these three entries

```python
    "RISK_PER_TRADE_PCT": _cfg_pct("RISK_PER_TRADE_PCT"),
    "MAX_RISK_AMOUNT_ABSOLUTE": lambda: _money(config.MAX_RISK_AMOUNT_ABSOLUTE),
    "POSITION_SIZING_MODE": _sizing_mode,
```

(they are not adjacent in the dict; replace each line where it stands) with

```python
    "RISK_PER_TRADE_PCT": _from_account("risk_pct", _pct),
    "MAX_RISK_AMOUNT_ABSOLUTE": _from_account("max_risk_amount_absolute", _money),
    "POSITION_SIZING_MODE": _from_account("sizing_mode", _mode_text),
```

and add, after `"version.bot": _bot_version,`:

```python
    "MAX_POSITION_SIZE_PCT": _from_account("max_position_pct", _pct),
    "MAX_POSITION_VALUE_ABSOLUTE": _from_account("max_position_value_absolute", _money),
    "MAX_OPEN_POSITIONS": _from_account("max_open_positions", _count),
```

The tag must be new: `git grep -n "ops.admin.guide.account_row" -- swingbot` prints only this site.

- [ ] **Step 5: Give every chapter-resolving test module the fixture**

Run: `git grep -ln "placeholders.resolve\|load_chapters()\|guide_dir()" -- tests/admin tests/scripts`
Expected: at least `tests/admin/test_guide_content.py` and `tests/admin/test_guide_chapter_text.py`. Any other listed module whose tests resolve a *real* chapter body (or synthetic text naming one of the six account-row names) also needs the fixture; a module that only resolves synthetic text without those names (e.g. `test_api_v1_guide.py`'s `{{MAX_STOP_LOSS_PCT}}` chapters in `tmp_path`) needs nothing.

In each module that needs it, add `live_risk` to the existing `from swingbot.admin.guide import …` line and put this directly below `_no_live_book`:

```python
#: The stored account row the sizer reads; live_risk._load_account would open the database.
_ACCOUNT_ROW = {
    "risk_pct": 1.0, "max_risk_amount_absolute": 100.0, "sizing_mode": "risk_pct",
    "max_position_pct": 10.0, "max_position_value_absolute": 1000.0, "max_open_positions": 30,
}


@pytest.fixture(autouse=True)
def _stored_account(monkeypatch):
    monkeypatch.setattr(live_risk, "_load_account", lambda: dict(_ACCOUNT_ROW))
```

Why each module carries its own copy instead of `tests/admin/conftest.py`: the conftest serves every admin test, and patching the account reader there would hide a real `load_account_config` regression in unrelated tests.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_placeholders.py`
Expected: PASS (`0 failed`).

Run each module Step 5 touched:
`python scripts/dev/testrun.py file tests/admin/test_guide_content.py`
`python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: PASS each (chapter 3's "Sizing and caps" and the glossary still render with no `{{`).

Run: `python scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py`
Expected: PASS (the new handler is tagged).

Run: `python scripts/dev/complexity_gate.py` then `python -m pyflakes swingbot/admin/guide/`
Expected: exit 0; no pyflakes output (`config` and `_cfg_pct` are still used by the heat caps and stop placeholders).

- [ ] **Step 7: Commit**

```bash
git add swingbot/admin/guide/live_risk.py tests/admin/test_guide_placeholders.py tests/admin/test_guide_content.py tests/admin/test_guide_chapter_text.py
git commit -m "feat(guide): sizing placeholders read the stored account row, not the .env seed (v237 V237-1)"
```

(Add any further module Step 5 touched to `git add`.)

### Task V237-2: Plan, level and throttle rule placeholders

**Model:** sonnet — a new whitelist table of twenty-two values read from config, module constants and one ladder tuple, with exact rendered wording later chapters quote.

**Why.** Chapters 7–8 may not type a bare number before `%` (`_BARE_PCT`, index Global Constraints) and chapters 4–8 take every rule number from a placeholder, so a changed default can never leave stale prose (index Handoff 7). v235 covers stops, risk and heat; this task adds the rule numbers chapters 4, 7 and 8 explain: reward and R:R floors, confluence counts, dedup and confirmation, the hard planned-loss cap and the clamp level, the scale-out share and runner floor, the breakeven trigger, the chandelier trail, plan expiry, the level-lifecycle touch/break multiples and the drawdown throttle.

**Files:**
- Create: `swingbot/admin/guide/live_rules.py`
- Modify (created by v235 V235-3b): `swingbot/admin/guide/placeholders.py` (import and `_merge` line)
- Test: create `tests/admin/test_guide_rules.py` (suite `admin-core` via `tests/admin/test_[b-z]*.py`; no `suites.toml` edit); modify `tests/admin/test_guide_live_market.py` (`test_registry_merges_both_tables_and_nothing_else`)

**Interfaces:**
- Consumes: `live_risk._num`, `_pct`, `_flag` (V235-3); `placeholders._merge`, `PLACEHOLDERS`, `resolve` (V235-3b/4); `live_market.MARKET_PLACEHOLDERS` (V235-4); `risk_limits.HARD_MAX_PLANNED_LOSS_PCT` (`swingbot/core/risk_limits.py:9`); `builders.CLAMP_HEADROOM_PCT` (`swingbot/core/planning/builders.py:564`); `params.TP1_FRACTION`, `RUNNER_FLOOR_FRACTION`, `TRAIL_ATR_MULT`, `DEFAULT_EXPIRY_BARS` (`swingbot/core/planning/params.py:15-21`); `strategy_types.BREAKEVEN_TRIGGER_FRACTION` (`swingbot/core/market/strategy_types.py:241`); `levels_lifecycle.TOUCH_ATR_MULT`, `BREAK_ATR_MULT` (`swingbot/core/market/levels_lifecycle.py:54,58`); `throttle.DD_LADDER`, `RESUME_DD_PCT`, `STREAK_TRIGGER`, `STREAK_MULT`, `STREAK_RECOVERY_WINS` (`swingbot/core/edge/throttle.py:13,14,38-40`); config fields `MIN_REWARD_PCT`, `MIN_RISK_REWARD_RATIO`, `MAX_RISK_REWARD_RATIO`, `CONFLUENCE_DEVIATION_PCT`, `MIN_TARGET_CONFLUENCE_COUNT`, `DEDUP_TOLERANCE_PCT`, `SIGNAL_CONFIRMATION_SCANS`, `MIN_ALERT_CONFIDENCE_LEVEL`, `DD_THROTTLE_ENABLED`, `KILLSWITCH_DEFAULT_ON`.
- Produces (ledger): `live_rules.RULE_PLACEHOLDERS: dict[str, Callable[[], str]]` with exactly the 22 names below; `placeholders.PLACEHOLDERS = _merge(RISK_PLACEHOLDERS, MARKET_PLACEHOLDERS, RULE_PLACEHOLDERS)`.

| Name | Source | Renders (defaults today) |
|---|---|---|
| `MIN_REWARD_PCT` | config | `3%` (schema default; a `.env` may differ) |
| `MIN_RISK_REWARD_RATIO` / `MAX_RISK_REWARD_RATIO` | config | `1.5:1` / `2.5:1` |
| `CONFLUENCE_DEVIATION_PCT` | config | `5%` |
| `MIN_TARGET_CONFLUENCE_COUNT` | config | `2` |
| `DEDUP_TOLERANCE_PCT` | config | `2%` |
| `SIGNAL_CONFIRMATION_SCANS` | config | `1` |
| `MIN_ALERT_CONFIDENCE_LEVEL` | config | `4` |
| `stop.hard_cap` | `risk_limits.HARD_MAX_PLANNED_LOSS_PCT` | `2%` |
| `stop.clamp_level` | `HARD_MAX_PLANNED_LOSS_PCT - builders.CLAMP_HEADROOM_PCT` | `1.75%` |
| `plan.tp1_share` | `params.TP1_FRACTION` | `50%` |
| `plan.runner_floor` | `params.RUNNER_FLOOR_FRACTION` | `67%` |
| `plan.breakeven_trigger` | `strategy_types.BREAKEVEN_TRIGGER_FRACTION` | `50%` |
| `plan.trail_atr` | `params.TRAIL_ATR_MULT` | `2.5 × ATR(14)` |
| `plan.expiry_bars` | `params.DEFAULT_EXPIRY_BARS` | `5 bars` |
| `levels.touch_atr` / `levels.break_atr` | `levels_lifecycle.TOUCH_ATR_MULT` / `BREAK_ATR_MULT` | `0.25 × ATR` / `1 × ATR` |
| `throttle.ladder` | `throttle.DD_LADDER` | a Markdown table `\| Drawdown from peak \| New-entry size \|`, first row `\| up to 8% \| full size \|`, then one `\| more than N% \| M% of normal \|` row per rung, the `0.0` rung reading `paused` |
| `throttle.resume` | `throttle.RESUME_DD_PCT` | `15%` |
| `throttle.streak` | `STREAK_TRIGGER`, `STREAK_MULT`, `STREAK_RECOVERY_WINS` | `after 4 losses in a row, new entries are sized at 0.5 × normal until 2 wins land` |
| `DD_THROTTLE_ENABLED` / `KILLSWITCH_DEFAULT_ON` | config | `on` / `off` |

Fractions render as whole percents (`round(v * 100)`): `2/3` → `67%`. The ladder mirrors `throttle.current_throttle` (`dd > threshold` picks the rung), so the rows say "more than".

- [ ] **Step 1: Confirm the consumed names**

Run: `git grep -n "^HARD_MAX_PLANNED_LOSS_PCT\|^CLAMP_HEADROOM_PCT\|^TP1_FRACTION\|^RUNNER_FLOOR_FRACTION\|^TRAIL_ATR_MULT\|^DEFAULT_EXPIRY_BARS\|^BREAKEVEN_TRIGGER_FRACTION\|^TOUCH_ATR_MULT\|^BREAK_ATR_MULT\|^DD_LADDER\|^RESUME_DD_PCT\|^STREAK_" -- swingbot`
Expected: fourteen lines in the files named above.

Run: `git grep -n "^PLACEHOLDERS" swingbot/admin/guide/placeholders.py`
Expected: `PLACEHOLDERS: Mapping[str, Callable[[], str]] = _merge(RISK_PLACEHOLDERS, MARKET_PLACEHOLDERS)`.

- [ ] **Step 2: Write the failing tests**

Create `tests/admin/test_guide_rules.py`:

```python
"""v237 V237-2: plan, level and throttle rule placeholders."""
import pytest

from swingbot import config
from swingbot.admin.guide import live_rules, placeholders as ph
from swingbot.core import risk_limits
from swingbot.core.edge import throttle
from swingbot.core.market import levels_lifecycle, strategy_types
from swingbot.core.planning import builders, params

RULE_NAMES = {
    "MIN_REWARD_PCT", "MIN_RISK_REWARD_RATIO", "MAX_RISK_REWARD_RATIO",
    "CONFLUENCE_DEVIATION_PCT", "MIN_TARGET_CONFLUENCE_COUNT", "DEDUP_TOLERANCE_PCT",
    "SIGNAL_CONFIRMATION_SCANS", "MIN_ALERT_CONFIDENCE_LEVEL",
    "stop.hard_cap", "stop.clamp_level",
    "plan.tp1_share", "plan.runner_floor", "plan.breakeven_trigger", "plan.trail_atr",
    "plan.expiry_bars", "levels.touch_atr", "levels.break_atr",
    "throttle.ladder", "throttle.resume", "throttle.streak",
    "DD_THROTTLE_ENABLED", "KILLSWITCH_DEFAULT_ON",
}


def _render(name: str) -> str:
    return ph.resolve("{{" + name + "}}")


def test_rule_table_has_exactly_the_planned_names():
    assert set(live_rules.RULE_PLACEHOLDERS) == RULE_NAMES


@pytest.mark.parametrize("name", sorted(RULE_NAMES))
def test_every_rule_placeholder_is_registered_and_renders_plain_text(name):
    out = _render(name)
    assert out == live_rules.RULE_PLACEHOLDERS[name]()
    assert out.strip() and "{{" not in out


@pytest.mark.parametrize("attr, value, text", [
    ("MIN_REWARD_PCT", 3.0, "3%"),
    ("MIN_REWARD_PCT", 2.5, "2.5%"),
    ("MIN_RISK_REWARD_RATIO", 1.5, "1.5:1"),
    ("MAX_RISK_REWARD_RATIO", 2.5, "2.5:1"),
    ("MAX_RISK_REWARD_RATIO", 3.0, "3:1"),
    ("CONFLUENCE_DEVIATION_PCT", 5.0, "5%"),
    ("MIN_TARGET_CONFLUENCE_COUNT", 2, "2"),
    ("DEDUP_TOLERANCE_PCT", 2.0, "2%"),
    ("SIGNAL_CONFIRMATION_SCANS", 1, "1"),
    ("SIGNAL_CONFIRMATION_SCANS", 3, "3"),
    ("MIN_ALERT_CONFIDENCE_LEVEL", 4, "4"),
    ("MIN_ALERT_CONFIDENCE_LEVEL", "3", "3"),
    ("DD_THROTTLE_ENABLED", False, "off"),
    ("DD_THROTTLE_ENABLED", True, "on"),
    ("KILLSWITCH_DEFAULT_ON", False, "off"),
    ("KILLSWITCH_DEFAULT_ON", True, "on"),
])
def test_config_rules_are_read_at_call_time(monkeypatch, attr, value, text):
    monkeypatch.setattr(config, attr, value)
    assert _render(attr) == text


def test_stop_cap_and_clamp_level_follow_the_constants(monkeypatch):
    assert _render("stop.hard_cap") == f"{risk_limits.HARD_MAX_PLANNED_LOSS_PCT:g}%"
    assert _render("stop.clamp_level") == "1.75%"
    monkeypatch.setattr(builders, "CLAMP_HEADROOM_PCT", 0.5)
    assert _render("stop.clamp_level") == "1.5%"
    monkeypatch.setattr(risk_limits, "HARD_MAX_PLANNED_LOSS_PCT", 3.0)
    assert (_render("stop.hard_cap"), _render("stop.clamp_level")) == ("3%", "2.5%")


def test_plan_shape_values(monkeypatch):
    assert _render("plan.tp1_share") == "50%"
    assert _render("plan.runner_floor") == "67%"
    assert _render("plan.breakeven_trigger") == "50%"
    assert _render("plan.trail_atr") == "2.5 × ATR(14)"
    assert _render("plan.expiry_bars") == "5 bars"
    monkeypatch.setattr(params, "TP1_FRACTION", 0.4)
    monkeypatch.setattr(params, "TRAIL_ATR_MULT", 3.0)
    monkeypatch.setattr(params, "DEFAULT_EXPIRY_BARS", 7)
    monkeypatch.setattr(strategy_types, "BREAKEVEN_TRIGGER_FRACTION", 0.6)
    assert _render("plan.tp1_share") == "40%"
    assert _render("plan.trail_atr") == "3 × ATR(14)"
    assert _render("plan.expiry_bars") == "7 bars"
    assert _render("plan.breakeven_trigger") == "60%"


def test_level_lifecycle_multiples(monkeypatch):
    assert _render("levels.touch_atr") == "0.25 × ATR"
    assert _render("levels.break_atr") == "1 × ATR"
    monkeypatch.setattr(levels_lifecycle, "BREAK_ATR_MULT", 1.5)
    assert _render("levels.break_atr") == "1.5 × ATR"


def test_throttle_ladder_table():
    assert _render("throttle.ladder").splitlines() == [
        "| Drawdown from peak | New-entry size |",
        "|---|---|",
        "| up to 8% | full size |",
        "| more than 8% | 75% of normal |",
        "| more than 12% | 50% of normal |",
        "| more than 16% | 25% of normal |",
        "| more than 20% | paused |",
    ]


def test_throttle_ladder_follows_the_tuple(monkeypatch):
    monkeypatch.setattr(throttle, "DD_LADDER", ((5.0, 0.5), (10.0, 0.0)))
    assert _render("throttle.ladder").splitlines()[2:] == [
        "| up to 5% | full size |", "| more than 5% | 50% of normal |",
        "| more than 10% | paused |"]


def test_throttle_resume_and_streak(monkeypatch):
    assert _render("throttle.resume") == "15%"
    assert _render("throttle.streak") == (
        "after 4 losses in a row, new entries are sized at 0.5 × normal until 2 wins land")
    monkeypatch.setattr(throttle, "STREAK_TRIGGER", 3)
    assert _render("throttle.streak").startswith("after 3 losses in a row")


def test_no_sensitive_field_value_reaches_a_rule_placeholder(monkeypatch):
    for f in (f for f in config.FIELDS if f.sensitive):
        monkeypatch.setattr(config, f.attr, f"SENTINEL-{f.attr}", raising=False)
        assert f.attr not in live_rules.RULE_PLACEHOLDERS
    rendered = "\n".join(_render(name) for name in sorted(RULE_NAMES))
    assert "SENTINEL-" not in rendered
```

In `tests/admin/test_guide_live_market.py`, change the import line to

```python
from swingbot.admin.guide import live_market as lm, live_risk, live_rules, placeholders as ph
```

and replace `test_registry_merges_both_tables_and_nothing_else` with:

```python
def test_registry_merges_both_tables_and_nothing_else():
    assert set(ph.PLACEHOLDERS) == (set(live_risk.RISK_PLACEHOLDERS) | MARKET_NAMES
                                    | set(live_rules.RULE_PLACEHOLDERS))
```

(The name stays: the controller's ledger and V237-3/V237-5 edit the same test by name.)

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_rules.py`
Expected: FAIL at collection: `ImportError: cannot import name 'live_rules' from 'swingbot.admin.guide'`.

- [ ] **Step 4: Implement the rule table**

Create `swingbot/admin/guide/live_rules.py`:

```python
"""v237: plan, level and throttle rule numbers for the guide.

Chapters 4, 7 and 8 explain these rules; every number they quote comes from
here, read when the placeholder renders (config globals follow the SIGHUP
hot reload, module constants are read by attribute), so a changed default
never leaves stale prose. Only names in RULE_PLACEHOLDERS exist.
"""
from __future__ import annotations

from typing import Callable

from swingbot import config
from swingbot.admin.guide.live_risk import _flag, _num, _pct
from swingbot.core import risk_limits
from swingbot.core.edge import throttle
from swingbot.core.market import levels_lifecycle, strategy_types
from swingbot.core.planning import builders, params


def _share(fraction) -> str:
    """A fraction as a whole percent: 0.5 -> '50%', 2/3 -> '67%'."""
    return f"{round(float(fraction) * 100)}%"


def _ratio(value) -> str:
    return f"{_num(value)}:1"


def _cfg(attr: str, render: Callable[[object], str]) -> Callable[[], str]:
    return lambda: render(getattr(config, attr))


def _clamp_level() -> str:
    return _pct(risk_limits.HARD_MAX_PLANNED_LOSS_PCT - builders.CLAMP_HEADROOM_PCT)


def _ladder_size(mult: float) -> str:
    return "paused" if mult <= 0 else f"{_share(mult)} of normal"


def _ladder() -> str:
    rungs = throttle.DD_LADDER
    rows = ["| Drawdown from peak | New-entry size |", "|---|---|",
            f"| up to {_pct(rungs[0][0])} | full size |"]
    rows += [f"| more than {_pct(dd)} | {_ladder_size(mult)} |" for dd, mult in rungs]
    return "\n".join(rows)


def _streak() -> str:
    return (f"after {throttle.STREAK_TRIGGER} losses in a row, new entries are sized at "
            f"{_num(throttle.STREAK_MULT)} × normal until "
            f"{throttle.STREAK_RECOVERY_WINS} wins land")


RULE_PLACEHOLDERS: dict[str, Callable[[], str]] = {
    "MIN_REWARD_PCT": _cfg("MIN_REWARD_PCT", _pct),
    "MIN_RISK_REWARD_RATIO": _cfg("MIN_RISK_REWARD_RATIO", _ratio),
    "MAX_RISK_REWARD_RATIO": _cfg("MAX_RISK_REWARD_RATIO", _ratio),
    "CONFLUENCE_DEVIATION_PCT": _cfg("CONFLUENCE_DEVIATION_PCT", _pct),
    "MIN_TARGET_CONFLUENCE_COUNT": _cfg("MIN_TARGET_CONFLUENCE_COUNT", _num),
    "DEDUP_TOLERANCE_PCT": _cfg("DEDUP_TOLERANCE_PCT", _pct),
    "SIGNAL_CONFIRMATION_SCANS": _cfg("SIGNAL_CONFIRMATION_SCANS", _num),
    "MIN_ALERT_CONFIDENCE_LEVEL": _cfg("MIN_ALERT_CONFIDENCE_LEVEL", _num),
    "stop.hard_cap": lambda: _pct(risk_limits.HARD_MAX_PLANNED_LOSS_PCT),
    "stop.clamp_level": _clamp_level,
    "plan.tp1_share": lambda: _share(params.TP1_FRACTION),
    "plan.runner_floor": lambda: _share(params.RUNNER_FLOOR_FRACTION),
    "plan.breakeven_trigger": lambda: _share(strategy_types.BREAKEVEN_TRIGGER_FRACTION),
    "plan.trail_atr": lambda: f"{_num(params.TRAIL_ATR_MULT)} × ATR(14)",
    "plan.expiry_bars": lambda: f"{params.DEFAULT_EXPIRY_BARS} bars",
    "levels.touch_atr": lambda: f"{_num(levels_lifecycle.TOUCH_ATR_MULT)} × ATR",
    "levels.break_atr": lambda: f"{_num(levels_lifecycle.BREAK_ATR_MULT)} × ATR",
    "throttle.ladder": _ladder,
    "throttle.resume": lambda: _pct(throttle.RESUME_DD_PCT),
    "throttle.streak": _streak,
    "DD_THROTTLE_ENABLED": _cfg("DD_THROTTLE_ENABLED", _flag),
    "KILLSWITCH_DEFAULT_ON": _cfg("KILLSWITCH_DEFAULT_ON", _flag),
}
```

`_cfg` takes only the literal attribute names written in this table, so no secret is reachable. If `python -c "import swingbot.admin.guide.live_rules"` reports a circular import through `builders`, move `from swingbot.core.planning import builders` inside `_clamp_level` (a call-time import); the tests patch the module object either way.

In `swingbot/admin/guide/placeholders.py`, add the import beside the other two and extend the merge:

```python
from swingbot.admin.guide.live_market import MARKET_PLACEHOLDERS
from swingbot.admin.guide.live_risk import RISK_PLACEHOLDERS
from swingbot.admin.guide.live_rules import RULE_PLACEHOLDERS
```

```python
PLACEHOLDERS: Mapping[str, Callable[[], str]] = _merge(
    RISK_PLACEHOLDERS, MARKET_PLACEHOLDERS, RULE_PLACEHOLDERS)
```

`_merge` raises `ValueError("guide placeholder defined twice: …")` at import if a name clashes with v235's tables; none of the 22 does (`CLUSTER_TOLERANCE_PCT` stays in the market table).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_rules.py`
Expected: PASS (`0 failed`).

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_live_market.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_placeholders.py`
Expected: PASS (unchanged; the registry now carries 21 + 5 + 22 = 48 names).

Run: `python scripts/dev/complexity_gate.py` then `python -m pyflakes swingbot/admin/guide/`
Expected: exit 0; no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/admin/guide/live_rules.py swingbot/admin/guide/placeholders.py tests/admin/test_guide_rules.py tests/admin/test_guide_live_market.py
git commit -m "feat(guide): plan, level and throttle rule placeholders (v237 V237-2)"
```

### Task V237-3: Gate switch table

**Model:** sonnet — sixteen gates whose "applied / measured, not used" verdict must match how each setting is actually consumed in the scan, coupled pairs included.

**Why.** Chapter 6 must say which gates the live scan applies today and must not hard-code it: several gates are built, measured and switched off (index Handoff 5), and a flag flip has to change the chapter the same day. `{{gates.switches}}` reads each setting and decides "applied" from the same condition the code uses (e.g. the headroom veto needs `HEADROOM_SCOPE != off` *and* `HEADROOM_MIN_R > 0`, `swingbot/core/backtesting/arms/reachability.py:69`). The single-flag placeholders of the same table follow in V237-3b (split: this task alone passed 20 KB).

**Files:**
- Create: `swingbot/admin/guide/live_switches.py`
- Modify (created by v235 V235-3b): `swingbot/admin/guide/placeholders.py` (import and `_merge` line)
- Test: create `tests/admin/test_guide_switches.py`; modify `tests/admin/test_guide_live_market.py` (`test_registry_merges_both_tables_and_nothing_else`)

**Interfaces:**
- Consumes: `live_risk._num`, `_flag` (V235-3); `live_rules.RULE_PLACEHOLDERS` (V237-2); `placeholders._merge` (V235-3b); `strategy_types.REGIME_ALLOW` (`swingbot/core/market/strategy_types.py:393`, empty today); the config settings in the table below (all exist: `python -c "from swingbot import config; print(config.HEADROOM_SCOPE)"` prints `off`).
- Produces (ledger): `@dataclass(frozen=True) SwitchRow(label: str, settings: tuple[str, ...], active: Callable[[], bool])`; `live_switches.SWITCH_ROWS: tuple[SwitchRow, ...]` (16 rows, order below); `live_switches.APPLIED = "applied"`, `NOT_USED = "measured, not used"`; `live_switches.SWITCH_PLACEHOLDERS` holding `gates.switches` (V237-3b adds the ten single flags); `live_switches._cfg(attr, render)` (V237-3b reuses it); `PLACEHOLDERS = _merge(RISK_PLACEHOLDERS, MARKET_PLACEHOLDERS, RULE_PLACEHOLDERS, SWITCH_PLACEHOLDERS)`.

`SWITCH_ROWS` (label · settings · applied when — each read from the code that consumes the setting):

| # | Label | Settings | Applied when | Where the code reads it |
|---|---|---|---|---|
| 1 | Market regime gate | `REGIME_GATES_ENABLED` | flag on **and** `REGIME_ALLOW` has a non-empty entry | `entry_filters.apply_regime_gate` (`:123`) |
| 2 | Adjacent-horizon alignment | `MTF_ADJACENT_GATE` | flag on | `mtf.adjacent_aligned` |
| 3 | Relative strength, long arm | `RS_GATE`, `RS_LEADER_PERCENTILE` | `RS_GATE` on **and** leader percentile > 0 | `edge/rs_gate.py:38` (0 disables the long arm, `rs_gate.py:5`) |
| 4 | Relative strength, short arm | `RS_GATE`, `RS_LAGGARD_PERCENTILE` | `RS_GATE` on **and** laggard percentile > 0 | `rs_gate.py:45` |
| 5 | Dead-cat bounce veto | `DEAD_CAT_BOUNCE_VETO` | flag on | `scanning/analyze.py:69` |
| 6 | Earnings blackout | `EARNINGS_BLACKOUT_SESSIONS` | > 0 | `edge/gates.py:65` |
| 7 | Pullback volume dry-up | `PULLBACK_DRYUP_SCOPE`, `PULLBACK_DRYUP_MAX_RATIO` | scope ≠ `off` **and** ratio > 0 | `reachability.py:47` |
| 8 | Headroom to the first target | `HEADROOM_SCOPE`, `HEADROOM_MIN_R` | scope ≠ `off` **and** min R > 0 | `reachability.py:69` |
| 9 | S/R minimum level touches | `SR_MIN_LEVEL_TOUCHES` | > 0 | `entry_filters.py:893` |
| 10 | MA Ribbon confirm bars | `MA_RIBBON_CONFIRM_BARS` | > 1 | `entry_filters.py:811` (`if confirm > 1`) |
| 11 | RSI Divergence turn confirmation | `RSI_DIV_MIN_CONSECUTIVE_TURN` | > 1 | `entry_filters.py:1073` (`if min_turn > 1`) |
| 12 | FVG level mode | `FVG_LEVELS_MODE` | ≠ `all` (the unfiltered baseline) | `levels.py:181` |
| 13 | Next-open market entry and gap reclaim | `MARKET_ENTRY_NEXT_OPEN`, `GAP_RECLAIM_ATR` | `MARKET_ENTRY_NEXT_OPEN` on (gap reclaim is honoured only then, `planning/gap_reclaim.py:79`) | `builders.py:416` |
| 14 | Data-driven stops | `DATA_DRIVEN_STOPS_ENABLED` | flag on | `backtest.py:391`, `edge/stops.py` |
| 15 | Stall exit | `STALL_EXIT_ENABLED` | flag on | `override_verdict.py:282` |
| 16 | Runner structure exit | `RUNNER_STRUCTURE_EXIT` | ≠ `off` | `exit_sim.runner_structure_step` |

`gates.switches` renders `| Gate | Setting | Now | In the live scan |`, one row per `SWITCH_ROWS` entry: settings as `` `NAME` `` joined by `, `; "Now" as the current values in the same order (booleans `on`/`off`, numbers via `_num`, strings in backticks, an empty string as `(empty)`); the last cell `applied` or `measured, not used`.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_guide_switches.py`:

```python
"""v237 V237-3/V237-3b: gate switches and single-flag placeholders."""
import pytest

from swingbot import config
from swingbot.admin.guide import live_switches as ls, placeholders as ph
from swingbot.core.market import strategy_types

SWITCH_NAMES = {"gates.switches"}
LABELS = [
    "Market regime gate", "Adjacent-horizon alignment", "Relative strength, long arm",
    "Relative strength, short arm", "Dead-cat bounce veto", "Earnings blackout",
    "Pullback volume dry-up", "Headroom to the first target", "S/R minimum level touches",
    "MA Ribbon confirm bars", "RSI Divergence turn confirmation", "FVG level mode",
    "Next-open market entry and gap reclaim", "Data-driven stops", "Stall exit",
    "Runner structure exit",
]
#: Every setting at its schema default (swingbot/config.py), so tests never see a local .env.
DEFAULTS = {
    "REGIME_GATES_ENABLED": False, "MTF_ADJACENT_GATE": False, "RS_GATE": True,
    "RS_LEADER_PERCENTILE": 0.0, "RS_LAGGARD_PERCENTILE": 25.0, "DEAD_CAT_BOUNCE_VETO": False,
    "EARNINGS_BLACKOUT_SESSIONS": 0, "PULLBACK_DRYUP_SCOPE": "off", "PULLBACK_DRYUP_MAX_RATIO": 0.0,
    "HEADROOM_SCOPE": "off", "HEADROOM_MIN_R": 0.0, "SR_MIN_LEVEL_TOUCHES": 0,
    "MA_RIBBON_CONFIRM_BARS": 1, "RSI_DIV_MIN_CONSECUTIVE_TURN": 1, "FVG_LEVELS_MODE": "all",
    "MARKET_ENTRY_NEXT_OPEN": False, "GAP_RECLAIM_ATR": 0.0, "DATA_DRIVEN_STOPS_ENABLED": False,
    "STALL_EXIT_ENABLED": False, "RUNNER_STRUCTURE_EXIT": "off", "STRATEGY_ALERTS_MODE": "off",
    "STRATEGY_ALERTS_LIVE_STRATEGIES": "", "HTF_CONFLUENCE_ENABLED": True,
    "AVWAP_LEVELS_ENABLED": True, "LEVEL_LIFECYCLE_STOPS_ENABLED": True,
    "SCALE_OUT_ENABLED": True, "PLAN_ENGINE_V2": "on",
}


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    for attr, value in DEFAULTS.items():
        monkeypatch.setattr(config, attr, value)
    monkeypatch.setattr(strategy_types, "REGIME_ALLOW", {})


def _render(name: str) -> str:
    return ph.resolve("{{" + name + "}}")


def _row(label: str) -> str:
    rows = [line for line in _render("gates.switches").splitlines()
            if line.startswith(f"| {label} |")]
    assert len(rows) == 1, label
    return rows[0]


def test_switch_table_has_exactly_the_planned_names():
    assert set(ls.SWITCH_PLACEHOLDERS) == SWITCH_NAMES


@pytest.mark.parametrize("name", sorted(SWITCH_NAMES))
def test_every_switch_placeholder_is_registered_and_renders(name):
    out = _render(name)
    assert out == ls.SWITCH_PLACEHOLDERS[name]() and out.strip() and "{{" not in out


def test_rows_in_order_and_every_setting_is_a_config_field():
    assert [row.label for row in ls.SWITCH_ROWS] == LABELS
    fields = {f.attr for f in config.FIELDS}
    for row in ls.SWITCH_ROWS:
        assert row.settings and set(row.settings) <= fields, row.label
    lines = _render("gates.switches").splitlines()
    assert lines[0] == "| Gate | Setting | Now | In the live scan |"
    assert lines[1] == "|---|---|---|---|"
    assert len(lines) == 2 + len(LABELS)


def test_at_schema_defaults_only_the_rs_short_arm_is_applied():
    applied = [label for label in LABELS if _row(label).endswith(f"| {ls.APPLIED} |")]
    assert applied == ["Relative strength, short arm"]
    assert _row("Dead-cat bounce veto") == (
        "| Dead-cat bounce veto | `DEAD_CAT_BOUNCE_VETO` | off | measured, not used |")
    assert _row("Headroom to the first target") == (
        "| Headroom to the first target | `HEADROOM_SCOPE`, `HEADROOM_MIN_R` | `off`, 0 "
        "| measured, not used |")
    assert _row("Relative strength, short arm") == (
        "| Relative strength, short arm | `RS_GATE`, `RS_LAGGARD_PERCENTILE` | on, 25 | applied |")


@pytest.mark.parametrize("label, changes", [
    ("Market regime gate", {"REGIME_GATES_ENABLED": True}),
    ("Adjacent-horizon alignment", {"MTF_ADJACENT_GATE": True}),
    ("Relative strength, long arm", {"RS_LEADER_PERCENTILE": 80.0}),
    ("Dead-cat bounce veto", {"DEAD_CAT_BOUNCE_VETO": True}),
    ("Earnings blackout", {"EARNINGS_BLACKOUT_SESSIONS": 2}),
    ("Pullback volume dry-up", {"PULLBACK_DRYUP_SCOPE": "strategy", "PULLBACK_DRYUP_MAX_RATIO": 0.6}),
    ("Headroom to the first target", {"HEADROOM_SCOPE": "confluence", "HEADROOM_MIN_R": 1.0}),
    ("S/R minimum level touches", {"SR_MIN_LEVEL_TOUCHES": 2}),
    ("MA Ribbon confirm bars", {"MA_RIBBON_CONFIRM_BARS": 3}),
    ("RSI Divergence turn confirmation", {"RSI_DIV_MIN_CONSECUTIVE_TURN": 2}),
    ("FVG level mode", {"FVG_LEVELS_MODE": "displacement"}),
    ("Next-open market entry and gap reclaim", {"MARKET_ENTRY_NEXT_OPEN": True}),
    ("Data-driven stops", {"DATA_DRIVEN_STOPS_ENABLED": True}),
    ("Stall exit", {"STALL_EXIT_ENABLED": True}),
    ("Runner structure exit", {"RUNNER_STRUCTURE_EXIT": "hl_trail"}),
])
def test_each_gate_flips_to_applied_with_its_settings(monkeypatch, label, changes):
    assert _row(label).endswith(f"| {ls.NOT_USED} |")
    for attr, value in changes.items():
        monkeypatch.setattr(config, attr, value)
    if label == "Market regime gate":
        assert _row(label).endswith(f"| {ls.NOT_USED} |")   # flag alone: REGIME_ALLOW is empty
        monkeypatch.setattr(strategy_types, "REGIME_ALLOW", {"RSI": ("bull",)})
    assert _row(label).endswith(f"| {ls.APPLIED} |")


@pytest.mark.parametrize("label, changes", [
    ("Pullback volume dry-up", {"PULLBACK_DRYUP_SCOPE": "strategy"}),
    ("Pullback volume dry-up", {"PULLBACK_DRYUP_MAX_RATIO": 0.6}),
    ("Headroom to the first target", {"HEADROOM_SCOPE": "strategy"}),
    ("Headroom to the first target", {"HEADROOM_MIN_R": 1.0}),
    ("Relative strength, short arm", {"RS_GATE": False}),
    ("Next-open market entry and gap reclaim", {"GAP_RECLAIM_ATR": 0.5}),
])
def test_half_a_coupled_switch_is_not_applied(monkeypatch, label, changes):
    for attr, value in changes.items():
        monkeypatch.setattr(config, attr, value)
    assert _row(label).endswith(f"| {ls.NOT_USED} |")


def test_empty_string_setting_renders_as_empty(monkeypatch):
    monkeypatch.setattr(config, "FVG_LEVELS_MODE", "")
    assert "| `FVG_LEVELS_MODE` | (empty) |" in _row("FVG level mode")


def test_no_sensitive_setting_is_a_switch():
    sensitive = {f.attr for f in config.FIELDS if f.sensitive}
    assert not sensitive & {s for row in ls.SWITCH_ROWS for s in row.settings}
    assert not sensitive & set(ls.SWITCH_PLACEHOLDERS)
```

In `tests/admin/test_guide_live_market.py`, extend the import line with `live_switches` and replace the merge test with:

```python
def test_registry_merges_both_tables_and_nothing_else():
    assert set(ph.PLACEHOLDERS) == (set(live_risk.RISK_PLACEHOLDERS) | MARKET_NAMES
                                    | set(live_rules.RULE_PLACEHOLDERS)
                                    | set(live_switches.SWITCH_PLACEHOLDERS))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_switches.py`
Expected: FAIL at collection: `ImportError: cannot import name 'live_switches' from 'swingbot.admin.guide'`.

- [ ] **Step 3: Implement**

Create `swingbot/admin/guide/live_switches.py`:

```python
"""v237: which gates the live scan applies, read from the settings themselves.

Chapter 6 lists every built gate with its setting, its current value and
whether the live scan applies it. "Applied" uses the same condition as the
code that consumes the setting (a coupled pair needs both halves), so a gate
that is built but switched off reads "measured, not used" and flips the day
its flag flips. Only the attribute names written in this module are read.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from swingbot import config
from swingbot.admin.guide.live_risk import _flag, _num
from swingbot.core.market import strategy_types

APPLIED = "applied"
NOT_USED = "measured, not used"


@dataclass(frozen=True)
class SwitchRow:
    label: str
    settings: tuple[str, ...]
    active: Callable[[], bool]


def _on(attr: str) -> Callable[[], bool]:
    return lambda: bool(getattr(config, attr))


def _above(attr: str, floor: float) -> Callable[[], bool]:
    return lambda: float(getattr(config, attr)) > floor


def _not(attr: str, baseline: str) -> Callable[[], bool]:
    return lambda: str(getattr(config, attr)) != baseline


def _both(*checks: Callable[[], bool]) -> Callable[[], bool]:
    return lambda: all(check() for check in checks)


def _regime_allow_set() -> bool:
    return any(strategy_types.REGIME_ALLOW.values())


SWITCH_ROWS: tuple[SwitchRow, ...] = (
    SwitchRow("Market regime gate", ("REGIME_GATES_ENABLED",),
              _both(_on("REGIME_GATES_ENABLED"), _regime_allow_set)),
    SwitchRow("Adjacent-horizon alignment", ("MTF_ADJACENT_GATE",), _on("MTF_ADJACENT_GATE")),
    SwitchRow("Relative strength, long arm", ("RS_GATE", "RS_LEADER_PERCENTILE"),
              _both(_on("RS_GATE"), _above("RS_LEADER_PERCENTILE", 0))),
    SwitchRow("Relative strength, short arm", ("RS_GATE", "RS_LAGGARD_PERCENTILE"),
              _both(_on("RS_GATE"), _above("RS_LAGGARD_PERCENTILE", 0))),
    SwitchRow("Dead-cat bounce veto", ("DEAD_CAT_BOUNCE_VETO",), _on("DEAD_CAT_BOUNCE_VETO")),
    SwitchRow("Earnings blackout", ("EARNINGS_BLACKOUT_SESSIONS",),
              _above("EARNINGS_BLACKOUT_SESSIONS", 0)),
    SwitchRow("Pullback volume dry-up", ("PULLBACK_DRYUP_SCOPE", "PULLBACK_DRYUP_MAX_RATIO"),
              _both(_not("PULLBACK_DRYUP_SCOPE", "off"), _above("PULLBACK_DRYUP_MAX_RATIO", 0))),
    SwitchRow("Headroom to the first target", ("HEADROOM_SCOPE", "HEADROOM_MIN_R"),
              _both(_not("HEADROOM_SCOPE", "off"), _above("HEADROOM_MIN_R", 0))),
    SwitchRow("S/R minimum level touches", ("SR_MIN_LEVEL_TOUCHES",),
              _above("SR_MIN_LEVEL_TOUCHES", 0)),
    SwitchRow("MA Ribbon confirm bars", ("MA_RIBBON_CONFIRM_BARS",),
              _above("MA_RIBBON_CONFIRM_BARS", 1)),
    SwitchRow("RSI Divergence turn confirmation", ("RSI_DIV_MIN_CONSECUTIVE_TURN",),
              _above("RSI_DIV_MIN_CONSECUTIVE_TURN", 1)),
    SwitchRow("FVG level mode", ("FVG_LEVELS_MODE",), _not("FVG_LEVELS_MODE", "all")),
    SwitchRow("Next-open market entry and gap reclaim", ("MARKET_ENTRY_NEXT_OPEN", "GAP_RECLAIM_ATR"),
              _on("MARKET_ENTRY_NEXT_OPEN")),
    SwitchRow("Data-driven stops", ("DATA_DRIVEN_STOPS_ENABLED",), _on("DATA_DRIVEN_STOPS_ENABLED")),
    SwitchRow("Stall exit", ("STALL_EXIT_ENABLED",), _on("STALL_EXIT_ENABLED")),
    SwitchRow("Runner structure exit", ("RUNNER_STRUCTURE_EXIT",), _not("RUNNER_STRUCTURE_EXIT", "off")),
)


def _value(value) -> str:
    if isinstance(value, bool):
        return _flag(value)
    if isinstance(value, (int, float)):
        return _num(value)
    return f"`{value}`" if str(value) else "(empty)"


def _switch_row(row: SwitchRow) -> str:
    names = ", ".join(f"`{name}`" for name in row.settings)
    now = ", ".join(_value(getattr(config, name)) for name in row.settings)
    verdict = APPLIED if row.active() else NOT_USED
    return f"| {row.label} | {names} | {now} | {verdict} |"


def _switches() -> str:
    rows = ["| Gate | Setting | Now | In the live scan |", "|---|---|---|---|"]
    return "\n".join(rows + [_switch_row(row) for row in SWITCH_ROWS])


def _cfg(attr: str, render: Callable[[object], str]) -> Callable[[], str]:
    return lambda: render(getattr(config, attr))


SWITCH_PLACEHOLDERS: dict[str, Callable[[], str]] = {
    "gates.switches": _switches,
}
```

`_value` checks `bool` before `int` because `True` is an `int`. `_cfg` and the row helpers take only the literal names written in this module. `_cfg` is unused until V237-3b; `pyflakes` does not flag an unused module-level function.

In `swingbot/admin/guide/placeholders.py`, add `from swingbot.admin.guide.live_switches import SWITCH_PLACEHOLDERS` beside the other table imports and change the merge to:

```python
PLACEHOLDERS: Mapping[str, Callable[[], str]] = _merge(
    RISK_PLACEHOLDERS, MARKET_PLACEHOLDERS, RULE_PLACEHOLDERS, SWITCH_PLACEHOLDERS)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_switches.py`
Expected: PASS (`0 failed`).

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_live_market.py`
Expected: PASS.

Run: `python scripts/dev/complexity_gate.py` then `python -m pyflakes swingbot/admin/guide/`
Expected: exit 0; no output.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/guide/live_switches.py swingbot/admin/guide/placeholders.py tests/admin/test_guide_switches.py tests/admin/test_guide_live_market.py
git commit -m "feat(guide): gate switch table -- applied vs measured, not used, read from the settings (v237 V237-3)"
```

### Task V237-3b: Single-flag switch placeholders

**Model:** sonnet — ten small config readers on the V237-3 table, including an option-label lookup and an allow-list whose empty value means "every strategy".

**Why.** Chapters 4, 5 and 7 say inline whether a mechanism is on today — strategy alerts and their allow-list, the RS gate and its percentiles, higher-horizon flags, AVWAP levels, level-lifecycle stops, scale-out, the v2 plan engine. A typed "on" or "off" would go stale with the next `.env` change; these placeholders read the setting. Split from V237-3 (the combined task passed 20 KB).

**Files:**
- Modify: `swingbot/admin/guide/live_switches.py` (V237-3)
- Test: `tests/admin/test_guide_switches.py` (V237-3: extend `SWITCH_NAMES`, append tests)

**Interfaces:**
- Consumes: `live_switches._cfg`, `SWITCH_PLACEHOLDERS` (V237-3); `live_risk._field`, `_flag`, `_num` (V235-3); `config.Field.options` of `STRATEGY_ALERTS_MODE` (`[("off", "Off"), ("shadow", "Shadow -- …"), ("live", "Live -- alerts + paper trades")]`); `STRATEGY_ALERTS_LIVE_STRATEGIES` help (`swingbot/config.py:1355`: "Empty = all strategies"; `scanning/strategy_pass.py:234 return not deps.live_allow or strategy in deps.live_allow`).
- Produces (ledger): `SWITCH_PLACEHOLDERS` with exactly `gates.switches`, `STRATEGY_ALERTS_MODE`, `STRATEGY_ALERTS_LIVE_STRATEGIES`, `RS_GATE`, `RS_LEADER_PERCENTILE`, `RS_LAGGARD_PERCENTILE`, `HTF_CONFLUENCE_ENABLED`, `AVWAP_LEVELS_ENABLED`, `LEVEL_LIFECYCLE_STOPS_ENABLED`, `SCALE_OUT_ENABLED`, `PLAN_ENGINE_V2`. The registry merge from V237-3 picks the new names up with no edit (`test_registry_merges_both_tables_and_nothing_else` compares against `set(live_switches.SWITCH_PLACEHOLDERS)`).

| Name | Renders |
|---|---|
| `RS_GATE`, `HTF_CONFLUENCE_ENABLED`, `AVWAP_LEVELS_ENABLED`, `LEVEL_LIFECYCLE_STOPS_ENABLED`, `SCALE_OUT_ENABLED` | `on` / `off` |
| `RS_LEADER_PERCENTILE`, `RS_LAGGARD_PERCENTILE` | `0`, `25` (numbers via `_num`; a percentile, not a percent: no `%` sign) |
| `STRATEGY_ALERTS_MODE` | option label + value: ``Off (`off`)``; an unknown value renders as itself |
| `STRATEGY_ALERTS_LIVE_STRATEGIES` | `every strategy` when empty or only commas/blanks; otherwise the trimmed names joined by `, ` |
| `PLAN_ENGINE_V2` | the value in backticks: `` `on` `` / `` `shadow` `` / `` `off` `` (a three-way select, not a flag) |

- [ ] **Step 1: Write the failing tests**

In `tests/admin/test_guide_switches.py`, replace `SWITCH_NAMES = {"gates.switches"}` with:

```python
SWITCH_NAMES = {
    "gates.switches", "STRATEGY_ALERTS_MODE", "STRATEGY_ALERTS_LIVE_STRATEGIES", "RS_GATE",
    "RS_LEADER_PERCENTILE", "RS_LAGGARD_PERCENTILE", "HTF_CONFLUENCE_ENABLED",
    "AVWAP_LEVELS_ENABLED", "LEVEL_LIFECYCLE_STOPS_ENABLED", "SCALE_OUT_ENABLED", "PLAN_ENGINE_V2",
}
```

and append:

```python
# --- single flags (V237-3b) ------------------------------------------------------

@pytest.mark.parametrize("name, value, text", [
    ("RS_GATE", True, "on"),
    ("RS_GATE", False, "off"),
    ("RS_LEADER_PERCENTILE", 0.0, "0"),
    ("RS_LEADER_PERCENTILE", 80.0, "80"),
    ("RS_LAGGARD_PERCENTILE", 25.0, "25"),
    ("RS_LAGGARD_PERCENTILE", 12.5, "12.5"),
    ("HTF_CONFLUENCE_ENABLED", True, "on"),
    ("HTF_CONFLUENCE_ENABLED", False, "off"),
    ("AVWAP_LEVELS_ENABLED", True, "on"),
    ("AVWAP_LEVELS_ENABLED", False, "off"),
    ("LEVEL_LIFECYCLE_STOPS_ENABLED", True, "on"),
    ("LEVEL_LIFECYCLE_STOPS_ENABLED", False, "off"),
    ("SCALE_OUT_ENABLED", True, "on"),
    ("SCALE_OUT_ENABLED", False, "off"),
    ("PLAN_ENGINE_V2", "on", "`on`"),
    ("PLAN_ENGINE_V2", "shadow", "`shadow`"),
    ("PLAN_ENGINE_V2", "off", "`off`"),
])
def test_single_flags_read_config_at_call_time(monkeypatch, name, value, text):
    monkeypatch.setattr(config, name, value)
    assert _render(name) == text


@pytest.mark.parametrize("mode, text", [
    ("off", "Off (`off`)"),
    ("live", "Live -- alerts + paper trades (`live`)"),
    ("someday", "someday (`someday`)"),
])
def test_strategy_mode_uses_the_option_label(monkeypatch, mode, text):
    monkeypatch.setattr(config, "STRATEGY_ALERTS_MODE", mode)
    assert _render("STRATEGY_ALERTS_MODE") == text


def test_strategy_mode_shadow_label_comes_from_the_field(monkeypatch):
    field = next(f for f in config.FIELDS if f.attr == "STRATEGY_ALERTS_MODE")
    monkeypatch.setattr(config, "STRATEGY_ALERTS_MODE", "shadow")
    assert _render("STRATEGY_ALERTS_MODE") == f"{dict(field.options)['shadow']} (`shadow`)"


@pytest.mark.parametrize("value, text", [
    ("", "every strategy"),
    (" , ,", "every strategy"),
    (None, "every strategy"),
    ("MACD", "MACD"),
    ("MACD,Volume Profile", "MACD, Volume Profile"),
    (" MACD , Volume Profile ,", "MACD, Volume Profile"),
])
def test_live_strategies_allow_list(monkeypatch, value, text):
    monkeypatch.setattr(config, "STRATEGY_ALERTS_LIVE_STRATEGIES", value)
    assert _render("STRATEGY_ALERTS_LIVE_STRATEGIES") == text


def test_no_sensitive_value_reaches_a_switch_placeholder(monkeypatch):
    for f in (f for f in config.FIELDS if f.sensitive):
        monkeypatch.setattr(config, f.attr, f"SENTINEL-{f.attr}", raising=False)
    rendered = "\n".join(_render(name) for name in sorted(SWITCH_NAMES))
    assert "SENTINEL-" not in rendered
```

`test_switch_table_has_exactly_the_planned_names` and `test_every_switch_placeholder_is_registered_and_renders` (V237-3) now cover all eleven names through `SWITCH_NAMES`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_switches.py`
Expected: FAIL — `test_switch_table_has_exactly_the_planned_names` (ten names missing) and the new tests with `UnknownPlaceholder: unknown guide placeholder: RS_GATE` (and the other names); V237-3's row tests still pass.

- [ ] **Step 3: Implement**

In `swingbot/admin/guide/live_switches.py`, change the `live_risk` import to

```python
from swingbot.admin.guide.live_risk import _field, _flag, _num
```

add above `SWITCH_PLACEHOLDERS`:

```python
def _strategy_mode() -> str:
    value = config.STRATEGY_ALERTS_MODE
    label = dict(_field("STRATEGY_ALERTS_MODE").options).get(value, value)
    return f"{label} (`{value}`)"


def _live_strategies() -> str:
    parts = str(config.STRATEGY_ALERTS_LIVE_STRATEGIES or "").split(",")
    names = [part.strip() for part in parts if part.strip()]
    return ", ".join(names) if names else "every strategy"


def _backticked(value) -> str:
    return f"`{value}`"
```

and replace the `SWITCH_PLACEHOLDERS` assignment with:

```python
SWITCH_PLACEHOLDERS: dict[str, Callable[[], str]] = {
    "gates.switches": _switches,
    "STRATEGY_ALERTS_MODE": _strategy_mode,
    "STRATEGY_ALERTS_LIVE_STRATEGIES": _live_strategies,
    "RS_GATE": _cfg("RS_GATE", _flag),
    "RS_LEADER_PERCENTILE": _cfg("RS_LEADER_PERCENTILE", _num),
    "RS_LAGGARD_PERCENTILE": _cfg("RS_LAGGARD_PERCENTILE", _num),
    "HTF_CONFLUENCE_ENABLED": _cfg("HTF_CONFLUENCE_ENABLED", _flag),
    "AVWAP_LEVELS_ENABLED": _cfg("AVWAP_LEVELS_ENABLED", _flag),
    "LEVEL_LIFECYCLE_STOPS_ENABLED": _cfg("LEVEL_LIFECYCLE_STOPS_ENABLED", _flag),
    "SCALE_OUT_ENABLED": _cfg("SCALE_OUT_ENABLED", _flag),
    "PLAN_ENGINE_V2": _cfg("PLAN_ENGINE_V2", _backticked),
}
```

Every name a placeholder reads is written literally here; none is a sensitive field (`test_no_sensitive_setting_is_a_switch`, V237-3).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_switches.py`
Expected: PASS (`0 failed`).

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_live_market.py`
Expected: PASS (the registry now carries 21 + 5 + 22 + 11 = 59 names).

Run: `python scripts/dev/complexity_gate.py` then `python -m pyflakes swingbot/admin/guide/`
Expected: exit 0; no output.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/guide/live_switches.py tests/admin/test_guide_switches.py
git commit -m "feat(guide): single-flag switch placeholders -- strategy alerts, RS, scale-out, plan engine (v237 V237-3b)"
```

### Task V237-4: Strategy card loader and "costs not recorded"

**Model:** sonnet — a strict front-matter parser reusing v235's chapter helpers, and a three-way provenance wording change whose old callers must render exactly as before.

**Why.** Chapter 5 shows one card per registered strategy; the idea and entry rule are prose in `docs/guide/strategies/<slug>.md`, checked like chapters (sources, `reviewed_for`). The file name alone cannot name the strategy (`Support/Resistance` → `supportresistance` is lossy), so every card carries a required `strategy:` field holding the exact registry key (index Handoff 1). Registry rows do not record whether costs were included, so a card badge says "costs not recorded" — never "costs included" (Handoff 3); `provenance_label` gains that third state.

Card file shape (V237-7 writes nineteen of them):

```markdown
---
strategy: "Break & Retest"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/entry_filters.py:break_retest_entries
---
**Idea.** …
```

Rules `parse_card` enforces (each a `GuideFormatError` whose message starts with the file name, through v235's `chapters._fail`):
- opens with `---` and closes the front matter with `---` (v235 `_split_front_matter`); parses with `yaml.safe_load` into a mapping (`_load_meta`);
- `strategy`: a non-empty string; `reviewed_for`: an `X.Y.Z` string; `sources`: a **non-empty** list of non-empty strings (a chapter may have none, a card may not);
- the file stem equals `live_market.strategy_file_slug(strategy)`;
- the body (after the front matter, blank lines trimmed) is non-empty, has no line starting with `#` (the page adds `### <strategy>` itself, V237-5), and contains no `{{` (figures come only from the registry badge; a card resolves no placeholder).

**Files:**
- Create: `swingbot/admin/guide/cards.py`
- Modify (created by v235 V235-3b): `swingbot/admin/guide/placeholders.py` (`provenance_label`)
- Test: create `tests/admin/test_guide_cards.py`; modify `tests/admin/test_guide_placeholders.py` (append one test)

**Interfaces:**
- Consumes: `chapters.GuideFormatError`, `guide_dir()`, `_split_front_matter(text, path)`, `_load_meta(raw, path)`, `_fail(path, problem)`, `_is_text`, `_is_version` (V235-2/2b, `swingbot/admin/guide/chapters.py`); `live_market.strategy_file_slug(key)` (V235-4).
- Produces (ledger): `@dataclass(frozen=True) StrategyCard(path: Path, strategy: str, reviewed_for: str, sources: tuple[str, ...], body: str)`; `cards.cards_dir(root: Path | None = None) -> Path` (`(root or chapters.guide_dir()) / "strategies"`, `root` being the guide directory); `cards.parse_card(path: Path) -> StrategyCard`; `cards.load_cards(root: Path | None = None) -> list[StrategyCard]` (every `*.md` in `cards_dir(root)`, sorted by file name; `[]` when the folder is absent); `placeholders.provenance_label(*, source: str, n: int, run_date: str, costs_included: bool | None) -> str` — `None` renders `costs not recorded`, `True`/`False` unchanged.

`StrategyCard` has the `.path`, `.sources` and `.reviewed_for` that v235's `source_problems`, `version_problems` (`tests/admin/test_guide_content.py`) and `guide_sources.touched()` read, so V237-6 runs them over cards unchanged.

- [ ] **Step 1: Confirm the consumed names**

Run: `git grep -n "^def _split_front_matter\|^def _load_meta\|^def _fail\|^def _is_text\|^def _is_version\|^def guide_dir\|^class GuideFormatError" swingbot/admin/guide/chapters.py`
Expected: seven lines.

Run: `git grep -n "^def strategy_file_slug\|^def provenance_label" swingbot/admin/guide/`
Expected: one line each (`live_market.py`, `placeholders.py`).

- [ ] **Step 2: Write the failing tests**

Create `tests/admin/test_guide_cards.py`:

```python
"""v237 V237-4: strategy card files under docs/guide/strategies/."""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from swingbot.admin.guide import cards, chapters
from swingbot.admin.guide.chapters import GuideFormatError

_SOURCE = "swingbot/core/market/entry_filters.py:break_retest_entries"


def _card(folder: Path, name: str, *, front: str | None = None,
          body: str = "**Idea.** Buy the retest of a broken high.\n",
          strategy: str = "Break & Retest", reviewed_for: str = "2.19.2",
          sources=(_SOURCE,)) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    if front is None:
        src = "".join(f"  - {s}\n" for s in sources)
        front = f'strategy: "{strategy}"\nreviewed_for: {reviewed_for}\nsources:\n{src}'
    path = folder / name
    path.write_text(f"---\n{front}---\n{body}", encoding="utf-8")
    return path


# --- parse_card ------------------------------------------------------------------

def test_parse_card_reads_every_field(tmp_path):
    path = _card(tmp_path, "break-retest.md", body="\n**Idea.** Retest.\n\n- one\n\n")
    card = cards.parse_card(path)
    assert card == cards.StrategyCard(path=path, strategy="Break & Retest",
                                      reviewed_for="2.19.2", sources=(_SOURCE,),
                                      body="**Idea.** Retest.\n\n- one")


def test_parse_card_accepts_crlf_and_a_slash_in_the_key(tmp_path):
    path = _card(tmp_path, "supportresistance.md", strategy="Support/Resistance")
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    card = cards.parse_card(path)
    assert card.strategy == "Support/Resistance" and "\r" not in card.body


def test_strategy_card_is_frozen(tmp_path):
    card = cards.parse_card(_card(tmp_path, "break-retest.md"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        card.strategy = "RSI"


@pytest.mark.parametrize("front, message", [
    ("reviewed_for: 2.19.2\nsources:\n  - a.py\n", "front matter lacks 'strategy'"),
    ('strategy: ""\nreviewed_for: 2.19.2\nsources:\n  - a.py\n', "'strategy' must be a non-empty string"),
    ("strategy: 7\nreviewed_for: 2.19.2\nsources:\n  - a.py\n", "'strategy' must be a non-empty string"),
    ("strategy: RSI\nsources:\n  - a.py\n", "front matter lacks 'reviewed_for'"),
    ("strategy: RSI\nreviewed_for: 2.19\nsources:\n  - a.py\n", "'reviewed_for' must be an X.Y.Z version string"),
    ("strategy: RSI\nreviewed_for: 2.19.2\n", "front matter lacks 'sources'"),
    ("strategy: RSI\nreviewed_for: 2.19.2\nsources: []\n", "'sources' must be a non-empty list"),
    ("strategy: RSI\nreviewed_for: 2.19.2\nsources: a.py\n", "'sources' must be a non-empty list"),
    ("strategy: RSI\nreviewed_for: 2.19.2\nsources:\n  - ''\n", "'sources' must be a non-empty list"),
])
def test_parse_card_rejects_bad_front_matter(tmp_path, front, message):
    path = _card(tmp_path, "rsi.md", front=front)
    with pytest.raises(GuideFormatError, match=message) as info:
        cards.parse_card(path)
    assert str(info.value).startswith("rsi.md: ")


def test_parse_card_requires_front_matter(tmp_path):
    path = tmp_path / "rsi.md"
    path.write_text("**Idea.** No front matter.\n", encoding="utf-8")
    with pytest.raises(GuideFormatError, match="rsi.md: must open with a '---'"):
        cards.parse_card(path)


def test_parse_card_requires_the_file_name_to_match_the_key(tmp_path):
    path = _card(tmp_path, "break-and-retest.md")
    with pytest.raises(GuideFormatError,
                       match="break-and-retest.md: file name must be break-retest.md"):
        cards.parse_card(path)


@pytest.mark.parametrize("body, message", [
    ("", "body is empty"),
    ("\n\n  \n", "body is empty"),
    ("**Idea.** x\n## Entry rule\n- y\n", "line 2 is a heading"),
    ("# Title\n**Idea.** x\n", "line 1 is a heading"),
    ("**Idea.** Risk {{RISK_PER_TRADE_PCT}}.\n", "may not contain a placeholder"),
])
def test_parse_card_rejects_bad_bodies(tmp_path, body, message):
    path = _card(tmp_path, "break-retest.md", body=body)
    with pytest.raises(GuideFormatError, match=message):
        cards.parse_card(path)


def test_a_hash_inside_a_line_is_not_a_heading(tmp_path):
    card = cards.parse_card(_card(tmp_path, "break-retest.md", body="**Idea.** Rank #1 setup.\n"))
    assert card.body == "**Idea.** Rank #1 setup."


# --- load_cards ------------------------------------------------------------------

def test_load_cards_sorted_by_file_name_and_md_only(tmp_path):
    folder = tmp_path / "strategies"
    _card(folder, "rsi.md", strategy="RSI")
    _card(folder, "break-retest.md")
    (folder / "notes.txt").write_text("not a card", encoding="utf-8")
    assert [c.path.name for c in cards.load_cards(tmp_path)] == ["break-retest.md", "rsi.md"]


def test_load_cards_missing_folder_is_empty(tmp_path):
    assert cards.load_cards(tmp_path) == []
    assert cards.load_cards(tmp_path / "absent") == []


def test_load_cards_raises_on_the_first_malformed_card(tmp_path):
    folder = tmp_path / "strategies"
    _card(folder, "break-retest.md")
    (folder / "rsi.md").write_text("no front matter\n", encoding="utf-8")
    with pytest.raises(GuideFormatError, match="rsi.md"):
        cards.load_cards(tmp_path)


def test_cards_dir_defaults_to_the_guide_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(chapters, "guide_dir", lambda: tmp_path)
    assert cards.cards_dir() == tmp_path / "strategies"
    assert cards.cards_dir(tmp_path / "x") == tmp_path / "x" / "strategies"
    _card(tmp_path / "strategies", "break-retest.md")
    assert [c.strategy for c in cards.load_cards()] == ["Break & Retest"]
```

Append to `tests/admin/test_guide_placeholders.py`:

```python
def test_provenance_label_when_costs_were_not_recorded():
    label = ph.provenance_label(source="validation-window backtest 2024-01-01..2025-12-31",
                                n=112, run_date="2026-08-17", costs_included=None)
    assert label == ("Source: validation-window backtest 2024-01-01..2025-12-31; N = 112; "
                     "as of 2026-08-17; costs not recorded; before tax")
    assert "costs included" not in label
```

(v235's `test_provenance_label_names_every_part_and_ends_before_tax` keeps pinning the `True`/`False` wording.)

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_cards.py`
Expected: FAIL at collection: `ImportError: cannot import name 'cards' from 'swingbot.admin.guide'`.

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_placeholders.py`
Expected: FAIL in `test_provenance_label_when_costs_were_not_recorded` only (`costs not included` printed for `None`).

- [ ] **Step 4: Implement the card loader**

Create `swingbot/admin/guide/cards.py`:

```python
"""v237: strategy cards -- docs/guide/strategies/<slug>.md, one per registered key.

A card is prose about one strategy: its idea, entry rule and where the rule
fires. Its front matter names the exact registry key (`strategy:`), the code
it describes (`sources:`) and the bot version it was checked against
(`reviewed_for:`). The card body has no heading (the strategies.cards
placeholder adds `### <key>`) and no placeholder: every figure on a card
comes from the registry badge, never from prose.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from swingbot.admin.guide import chapters
from swingbot.admin.guide.live_market import strategy_file_slug


@dataclass(frozen=True)
class StrategyCard:
    path: Path
    strategy: str
    reviewed_for: str
    sources: tuple[str, ...]
    body: str


def _is_card_sources(value) -> bool:
    return isinstance(value, list) and bool(value) and all(chapters._is_text(v) for v in value)


#: (key, check, what the key must be) -- one rule per row, as in chapters._FIELD_RULES.
_CARD_RULES = (
    ("strategy", chapters._is_text, "a non-empty string"),
    ("reviewed_for", chapters._is_version, "an X.Y.Z version string"),
    ("sources", _is_card_sources, "a non-empty list of non-empty strings"),
)


def cards_dir(root: Path | None = None) -> Path:
    """The strategies/ folder under the guide directory `root` (default guide_dir())."""
    return (Path(root) if root is not None else chapters.guide_dir()) / "strategies"


def _check_meta(meta: dict, path: Path) -> None:
    for key, check, wanted in _CARD_RULES:
        if key not in meta:
            raise chapters._fail(path, f"front matter lacks '{key}'")
        if not check(meta[key]):
            raise chapters._fail(path, f"'{key}' must be {wanted}, got {meta[key]!r}")
    expected = strategy_file_slug(meta["strategy"].strip())
    if path.stem != expected:
        raise chapters._fail(path, f"file name must be {expected}.md for strategy "
                                   f"{meta['strategy']!r}")


def _check_body(body: str, path: Path) -> None:
    if not body.strip():
        raise chapters._fail(path, "body is empty")
    for number, line in enumerate(body.splitlines(), start=1):
        if line.startswith("#"):
            raise chapters._fail(path, f"line {number} is a heading; the page adds "
                                       "'### <strategy>' itself")
    if "{{" in body:
        raise chapters._fail(path, "a card may not contain a placeholder; "
                                   "figures come from the registry badge")


def parse_card(path: Path) -> StrategyCard:
    """One card file -> StrategyCard; GuideFormatError names the file on any defect."""
    try:
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    except (OSError, UnicodeDecodeError) as exc:
        raise chapters._fail(path, f"unreadable ({exc})") from exc
    raw, body = chapters._split_front_matter(text, path)
    meta = chapters._load_meta(raw, path)
    _check_meta(meta, path)
    body = body.strip("\n")
    _check_body(body, path)
    return StrategyCard(path=path, strategy=meta["strategy"].strip(),
                        reviewed_for=meta["reviewed_for"],
                        sources=tuple(item.strip() for item in meta["sources"]), body=body)


def load_cards(root: Path | None = None) -> list[StrategyCard]:
    """Every strategies/*.md card under the guide directory, by file name; [] if none."""
    folder = cards_dir(root)
    if not folder.is_dir():
        return []
    return [parse_card(path) for path in sorted(folder.glob("*.md")) if path.is_file()]
```

The body line numbers in messages count from the first body line after the trimmed blank lines (the tests pin `line 1`/`line 2` against bodies with no leading blank line). `chapters.guide_dir` is looked up at call time so tests that patch it (V235-5's API tests, `test_cards_dir_defaults_to_the_guide_dir`) reach the cards too.

In `swingbot/admin/guide/placeholders.py`, replace `provenance_label` with:

```python
def _costs_text(costs_included: bool | None) -> str:
    if costs_included is None:
        return "costs not recorded"
    return "costs included" if costs_included else "costs not included"


def provenance_label(*, source: str, n: int, run_date: str, costs_included: bool | None) -> str:
    """Where a performance figure comes from; always ends with 'before tax'.

    costs_included=None: the source does not record whether costs were
    deducted (registry rows carry no friction flag) -- never claim either way.
    """
    return f"Source: {source}; N = {n}; as of {run_date}; {_costs_text(costs_included)}; before tax"
```

`live_market._alerts_per_week` (`costs_included=False`) renders exactly as before.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_cards.py`
Expected: PASS (`0 failed`).

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_placeholders.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_live_market.py`
Expected: PASS (`alerts.per_week` still prints `costs not included`).

Run: `python scripts/dev/complexity_gate.py` then `python -m pyflakes swingbot/admin/guide/`
Expected: exit 0; no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/admin/guide/cards.py swingbot/admin/guide/placeholders.py tests/admin/test_guide_cards.py tests/admin/test_guide_placeholders.py
git commit -m "feat(guide): strategy card parser and 'costs not recorded' provenance (v237 V237-4)"
```

