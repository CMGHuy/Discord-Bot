# v237 — Guide trading core, part 1 (continued): `strategies.cards` and card checks

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V237-6" -A 400 <this file>`); never read the file whole.

**Spec:** v215 — [2026-11-06-v215-guide-page.md](../specs/2026-11-06-v215-guide-page.md), Plan B ("Trading core").
**Index:** [2026-11-18-v237-guide-trading-core_0-index.md](2026-11-18-v237-guide-trading-core_0-index.md) — Goal, Global Constraints, `## Parallelisation`, the task ledger and `## Handoff`.
**Part 1 head:** [2026-11-18-v237-guide-trading-core_1-placeholders.md](2026-11-18-v237-guide-trading-core_1-placeholders.md) (V237-1..V237-4; its "Starting state" and "Test runs" notes apply here too). This file holds part 1's last two tasks because the part passed 1500 lines.

# Phase 2 — Cards on the page and in the freshness gate

### Task V237-5: `strategies.cards` placeholder

**Model:** sonnet — joins three sources (card files, `admits()` masks, registry rows) into one block per strategy with strict no-row and provenance rules, and fails loudly on a missing or stray card.

**Why.** Chapter 5 renders one live card per registered strategy (spec v215 § chapter 5): the prose comes from the card file, the allowed directions and horizons from `admits()`, and the badge from the registry row with its own window, N, run date, "costs not recorded" and "before tax". A strategy with no registry row prints `no registry row` — or `no registry row — masked, research only` for the eight masked keys — and never a fake "WEAK, N = 0" (`registry.get_badge` falls back to `Badge("WEAK", 0, 0.0, 0.0)`, `swingbot/core/backtesting/registry.py:178`; index Handoff 2/3).

**Files:**
- Create: `swingbot/admin/guide/live_strategies.py`
- Modify (created by v235 V235-3b): `swingbot/admin/guide/placeholders.py` (import and `_merge` line)
- Test: create `tests/admin/test_guide_strategies.py`; modify `tests/admin/test_guide_live_market.py` (`test_registry_merges_both_tables_and_nothing_else`)

**Interfaces:**
- Consumes: `cards.load_cards`, `StrategyCard` (V237-4); `placeholders.provenance_label(..., costs_included=None)` (V237-4); `live_market.registered_strategy_keys()`, `_side_cell(strategy, direction, live)`, `_NONE` (`"—"`), `strategy_file_slug` (V235-4); `strategy_types.live_horizons()`; `registry.get_badge(source, strategy, horizon_key=None) -> Badge` and `Badge(status, n, win_rate, expectancy_r, window="", run_date="", decay="unknown", data_source="yfinance")` (`registry.py:79,142`; `win_rate` is stored as a percent, e.g. `49.1`; `window` as `"2024-01-01..2025-12-31"`); `chapters.GuideFormatError`.
- Produces (ledger): module attributes `live_strategies._load_cards: Callable[[], list[StrategyCard]]` (`= cards.load_cards`) and `live_strategies._badge: Callable[[str], Badge]` (`registry.get_badge("strategy", key)`), both looked up at call time and patched in tests; `NO_ROW = "no registry row"`, `NO_ROW_MASKED = "no registry row — masked, research only"`; `_VALIDATION_FROM = "2024-01-01"`; `window_kind(window: str) -> str`; `badge_line(key: str, masked: bool) -> str`; `STRATEGY_PLACEHOLDERS = {"strategies.cards": …}`; `PLACEHOLDERS = _merge(RISK_…, MARKET_…, RULE_…, SWITCH_…, STRATEGY_PLACEHOLDERS)`.

One block per key, in `registered_strategy_keys()` order, blocks separated by a blank line, each part its own paragraph:

```markdown
### MACD

**Status:** live

**Long:** 3m, 4m, 7m, 8m, 9m · **Short:** —

**Badge:** VALIDATED — ExpR +0.219R, win rate 50.0%; Source: validation-window backtest 2024-01-01..2025-12-31; N = 112; as of 2026-08-17; costs not recorded; before tax

<card body>
```

- Status `masked — research only` when both side cells are `—`, else `live` (the same rule as `gates.list`).
- `window_kind`: `TRAIN-window` when the row's window ends before `_VALIDATION_FROM` (the validation window start, `docs/claude/backtest-methodology.md`; no shared constant exists in `swingbot/`), else `validation-window`.
- No row ⇔ `badge.n == 0 and not badge.run_date`. A row with N but no run date prints `as of unknown date` (a badge never renders without N and a date).
- A registered key with no card raises `GuideFormatError("strategies/: no card for <keys>")`; a card whose `strategy` is not registered raises `GuideFormatError("<file>: strategy '<s>' is not a registered strategy")`.
- The `### <key>` headings come from this placeholder, so they reach the resolved heading list (TOC, search) but not `guide-anchors.json` (built from raw headings): no `?` link may target a card anchor (index plan-writer decisions).

- [ ] **Step 1: Confirm the consumed names**

Run: `git grep -n "^def _side_cell\|^_NONE\|^def registered_strategy_keys" swingbot/admin/guide/live_market.py`
Expected: three lines.

Run: `git grep -n "^def load_cards\|^class StrategyCard" swingbot/admin/guide/cards.py`
Expected: two lines (V237-4).

- [ ] **Step 2: Write the failing tests**

Create `tests/admin/test_guide_strategies.py`:

```python
"""v237 V237-5: the strategies.cards placeholder (chapter 5's live cards)."""
from __future__ import annotations

from pathlib import Path

import pytest

from swingbot.admin.guide import cards, live_market as lm, live_strategies as lst, placeholders as ph
from swingbot.admin.guide.chapters import GuideFormatError
from swingbot.core.backtesting.registry import Badge
from swingbot.core.market import strategy_types

_ROWS = {
    "MACD": Badge("VALIDATED", 112, 50.0, 0.219, window="2024-01-01..2025-12-31",
                  run_date="2026-08-17"),
    "Fibonacci": Badge("WEAK", 246, 35.4, 0.232, window="2020-01-01..2023-12-31",
                       run_date="2026-09-10"),
    "RSI": Badge("WEAK", 38, 23.7, -0.12, window="2020-01-01..2023-12-31", run_date="2026-09-10"),
}


def _fake_card(key: str) -> cards.StrategyCard:
    return cards.StrategyCard(path=Path(f"{lm.strategy_file_slug(key)}.md"), strategy=key,
                              reviewed_for="2.19.2", sources=("swingbot/core/market/entry_filters.py",),
                              body=f"**Idea.** Card for {key}.")


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setattr(lst, "_load_cards",
                        lambda: [_fake_card(k) for k in lm.registered_strategy_keys()])
    monkeypatch.setattr(lst, "_badge", lambda key: _ROWS.get(key, Badge("WEAK", 0, 0.0, 0.0)))


def _render() -> str:
    return ph.resolve("{{strategies.cards}}")


def _block(key: str) -> str:
    text = _render()
    start = text.index(f"### {key}\n")
    end = text.find("\n### ", start + 1)
    return (text[start:] if end < 0 else text[start:end]).rstrip("\n")


def _live() -> tuple[str, ...]:
    return tuple(strategy_types.live_horizons())


def test_strategy_table_has_exactly_one_name():
    assert set(lst.STRATEGY_PLACEHOLDERS) == {"strategies.cards"}
    assert "strategies.cards" in ph.PLACEHOLDERS


def test_one_block_per_registered_key_in_order():
    headings = [line for line in _render().splitlines() if line.startswith("### ")]
    assert headings == [f"### {key}" for key in lm.registered_strategy_keys()]
    assert "{{" not in _render()


def test_a_validated_row_renders_with_its_full_provenance():
    long_cell = lm._side_cell("MACD", "bullish", _live())
    assert _block("MACD").split("\n\n") == [
        "### MACD",
        "**Status:** live",
        f"**Long:** {long_cell} · **Short:** —",
        "**Badge:** VALIDATED — ExpR +0.219R, win rate 50.0%; Source: validation-window "
        "backtest 2024-01-01..2025-12-31; N = 112; as of 2026-08-17; costs not recorded; "
        "before tax",
        "**Idea.** Card for MACD.",
    ]


def test_a_train_window_row_says_so_and_a_negative_expr_keeps_its_sign():
    assert ("**Badge:** WEAK — ExpR +0.232R, win rate 35.4%; Source: TRAIN-window backtest "
            "2020-01-01..2023-12-31; N = 246") in _block("Fibonacci")
    assert "ExpR -0.120R, win rate 23.7%" in _block("RSI")


def test_side_cells_come_from_admits():
    assert "**Long:** 4w · **Short:** —" in _block("VWAP")
    assert "**Long:** every live horizon · **Short:** every live horizon" in _block("EMA Crossover")


def test_a_masked_key_without_a_row_never_prints_weak():
    block = _block("Turtle Soup")
    assert "**Status:** masked — research only" in block
    assert "**Long:** — · **Short:** —" in block
    assert f"**Badge:** {lst.NO_ROW_MASKED}" in block
    assert "WEAK" not in block and "N = 0" not in block


def test_a_live_key_without_a_row_prints_no_registry_row():
    block = _block("VWAP")
    assert f"**Badge:** {lst.NO_ROW}\n\n" in block
    assert "WEAK" not in block and "masked" not in block


def test_every_badge_carries_n_and_a_date():
    for line in (l for l in _render().splitlines() if l.startswith("**Badge:** ")):
        if lst.NO_ROW in line:
            continue
        assert "; N = " in line and "; as of " in line and line.endswith("; before tax"), line


def test_a_row_without_a_run_date_says_unknown_date(monkeypatch):
    monkeypatch.setattr(lst, "_badge", lambda key: Badge("WEAK", 9, 40.0, 0.1,
                                                         window="2024-01-01..2025-12-31"))
    assert "N = 9; as of unknown date;" in lst.badge_line("MACD", masked=False)


def test_a_masked_key_with_a_row_shows_the_row(monkeypatch):
    monkeypatch.setattr(lst, "_badge", lambda key: _ROWS["MACD"])
    assert lst.badge_line("Turtle Soup", masked=True).startswith("VALIDATED — ExpR +0.219R")


@pytest.mark.parametrize("window, kind", [
    ("2020-01-01..2023-12-31", "TRAIN-window"),
    ("2015-01-01..2022-12-31", "TRAIN-window"),
    ("2024-01-01..2025-12-31", "validation-window"),
    ("2020-01-01..2024-06-30", "validation-window"),
    ("", "validation-window"),
])
def test_window_kind(window, kind):
    assert lst.window_kind(window) == kind


def test_a_registered_key_without_a_card_fails(monkeypatch):
    keep = [k for k in lm.registered_strategy_keys() if k != "RSI"]
    monkeypatch.setattr(lst, "_load_cards", lambda: [_fake_card(k) for k in keep])
    with pytest.raises(GuideFormatError, match="strategies/: no card for RSI"):
        _render()


def test_a_card_for_an_unregistered_strategy_fails(monkeypatch):
    stray = cards.StrategyCard(path=Path("moon-phase.md"), strategy="Moon Phase",
                               reviewed_for="2.19.2", sources=("x.py",), body="**Idea.** No.")
    monkeypatch.setattr(lst, "_load_cards",
                        lambda: [_fake_card(k) for k in lm.registered_strategy_keys()] + [stray])
    with pytest.raises(GuideFormatError,
                       match="moon-phase.md: strategy 'Moon Phase' is not a registered strategy"):
        _render()


def test_the_default_badge_reader_asks_for_the_strategy_source(monkeypatch):
    from swingbot.core.backtesting import registry
    monkeypatch.undo()   # drops _offline's patches: lst._badge is the module's own function again
    calls = []
    monkeypatch.setattr(registry, "get_badge",
                        lambda source, strategy, horizon_key=None: calls.append((source, strategy))
                        or Badge("WEAK", 0, 0.0, 0.0))
    assert lst._badge("MACD").n == 0
    assert calls == [("strategy", "MACD")]
```

In `tests/admin/test_guide_live_market.py`, extend the import line with `live_strategies` and replace the merge test with:

```python
def test_registry_merges_both_tables_and_nothing_else():
    assert set(ph.PLACEHOLDERS) == (set(live_risk.RISK_PLACEHOLDERS) | MARKET_NAMES
                                    | set(live_rules.RULE_PLACEHOLDERS)
                                    | set(live_switches.SWITCH_PLACEHOLDERS)
                                    | set(live_strategies.STRATEGY_PLACEHOLDERS))
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_strategies.py`
Expected: FAIL at collection: `ImportError: cannot import name 'live_strategies' from 'swingbot.admin.guide'`.

- [ ] **Step 4: Implement**

Create `swingbot/admin/guide/live_strategies.py`:

```python
"""v237: the strategies.cards placeholder -- one block per registered strategy.

Each block joins three sources: the card file (idea, entry rule, where it
fires), admits() (the directions and horizons the live scan allows, so a
masked strategy says so) and the registry row (status, ExpR, win rate, with
the row's own window, N and run date, "costs not recorded" and "before tax").
A strategy with no row says "no registry row" -- never the WEAK / N = 0
default get_badge falls back to.
"""
from __future__ import annotations

from typing import Callable

from swingbot.admin.guide import cards, live_market
from swingbot.admin.guide.chapters import GuideFormatError
from swingbot.core.backtesting import registry
from swingbot.core.market import strategy_types

NO_ROW = "no registry row"
NO_ROW_MASKED = "no registry row — masked, research only"
_MASKED = "masked — research only"
#: Start of the validation window (docs/claude/backtest-methodology.md): a row
#: whose window ends before it was measured on TRAIN data.
_VALIDATION_FROM = "2024-01-01"

_load_cards: Callable[[], list[cards.StrategyCard]] = cards.load_cards


def _badge(key: str) -> registry.Badge:
    """The pooled strategy-source registry row (patched in unit tests)."""
    return registry.get_badge("strategy", key)


def window_kind(window: str) -> str:
    end = window.rpartition("..")[2]
    return "TRAIN-window" if end and end < _VALIDATION_FROM else "validation-window"


def badge_line(key: str, masked: bool) -> str:
    from swingbot.admin.guide.placeholders import provenance_label   # placeholders imports us
    badge = _badge(key)
    if badge.n == 0 and not badge.run_date:
        return NO_ROW_MASKED if masked else NO_ROW
    label = provenance_label(source=f"{window_kind(badge.window)} backtest {badge.window}",
                             n=badge.n, run_date=badge.run_date or "unknown date",
                             costs_included=None)
    return (f"{badge.status} — ExpR {badge.expectancy_r:+.3f}R, "
            f"win rate {badge.win_rate:.1f}%; {label}")


def _cards_by_key(keys: tuple[str, ...]) -> dict[str, cards.StrategyCard]:
    found: dict[str, cards.StrategyCard] = {}
    for card in _load_cards():
        if card.strategy not in keys:
            raise GuideFormatError(f"{card.path.name}: strategy {card.strategy!r} "
                                   "is not a registered strategy")
        found[card.strategy] = card
    missing = [key for key in keys if key not in found]
    if missing:
        raise GuideFormatError(f"strategies/: no card for {', '.join(missing)}")
    return found


def _card_block(key: str, card: cards.StrategyCard, live: tuple[str, ...]) -> str:
    long_cell = live_market._side_cell(key, "bullish", live)
    short_cell = live_market._side_cell(key, "bearish", live)
    masked = long_cell == short_cell == live_market._NONE
    return "\n\n".join([
        f"### {key}",
        f"**Status:** {_MASKED if masked else 'live'}",
        f"**Long:** {long_cell} · **Short:** {short_cell}",
        f"**Badge:** {badge_line(key, masked)}",
        card.body,
    ])


def _strategy_cards() -> str:
    keys = live_market.registered_strategy_keys()
    by_key = _cards_by_key(keys)
    live = tuple(strategy_types.live_horizons())
    return "\n\n".join(_card_block(key, by_key[key], live) for key in keys)


STRATEGY_PLACEHOLDERS: dict[str, Callable[[], str]] = {
    "strategies.cards": _strategy_cards,
}
```

In `swingbot/admin/guide/placeholders.py`, add `from swingbot.admin.guide.live_strategies import STRATEGY_PLACEHOLDERS` beside the other table imports and change the merge to:

```python
PLACEHOLDERS: Mapping[str, Callable[[], str]] = _merge(
    RISK_PLACEHOLDERS, MARKET_PLACEHOLDERS, RULE_PLACEHOLDERS, SWITCH_PLACEHOLDERS,
    STRATEGY_PLACEHOLDERS)
```

`badge_line` imports `provenance_label` at call time because `placeholders` imports this module (the same pattern as `live_market._alerts_per_week`). If importing `swingbot.core.backtesting.registry` at module level creates a cycle, move it inside `_badge` (the fake in `test_the_default_badge_reader_asks_for_the_strategy_source` patches the `registry` module object either way; the return annotation stays a string under `from __future__ import annotations`). `monkeypatch.undo()` in that test reverts the autouse `_offline` patches, so it is the one test that runs the unpatched `_badge` -- still without reading `validation_registry.json` (index Global Constraints).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_strategies.py`
Expected: PASS (`0 failed`).

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_live_market.py`
Expected: PASS.

Run: `python scripts/dev/complexity_gate.py` then `python -m pyflakes swingbot/admin/guide/`
Expected: exit 0; no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/admin/guide/live_strategies.py swingbot/admin/guide/placeholders.py tests/admin/test_guide_strategies.py tests/admin/test_guide_live_market.py
git commit -m "feat(guide): strategies.cards -- card prose, admits() masks and registry badge with provenance (v237 V237-5)"
```

### Task V237-6: Content checks extended to strategy cards

**Model:** sonnet — three new freshness checks over cards in the shared content test, each proven to fire on a synthetic card, plus a diff-helper test; no production code.

**Why.** Cards describe code just as chapters do, so the freshness gate must hold them to the same rules (spec v215 § Freshness gate; index Handoff 1): every card parses, names a registered strategy, cites `sources:` that still exist, and carries a `reviewed_for` no newer than the bot. v235's `strategy cards` check already pins the file set to the registered keys; this task adds the per-card checks. `scripts/dev/guide_sources.touched()` already accepts any object with `.path`/`.sources`; a test pins that it works on a `StrategyCard` and that its own lightweight `load_cards()` reads the same sources as `cards.load_cards()` (it is left as is, Handoff 1).

All three real-guide checks are vacuous until V237-7 adds `docs/guide/strategies/` (no folder → no cards → no problems).

**Files:**
- Test: modify `tests/admin/test_guide_content.py` (V235-6), `tests/scripts/test_guide_sources.py` (V235-7)

**Interfaces:**
- Consumes: `cards.cards_dir`, `parse_card`, `load_cards`, `StrategyCard` (V237-4); `chapters.GuideFormatError` (V235-2); in `test_guide_content.py` (V235-6): `source_problems(chapters, root=ROOT)`, `version_problems(chapters, bot)`, `_bot_version()`, `REAL_CHECKS`, `test_the_real_guide_passes`; `live_market.registered_strategy_keys` (V235-4); `guide_sources.touched(paths, docs)`, `guide_sources.load_cards(root=None)` (V235-7).
- Produces (ledger): `card_problems(root: Path | None = None) -> list[str]` in `tests/admin/test_guide_content.py` (parse errors and unregistered `strategy:` values, as strings, files in name order); `REAL_CHECKS` gains `"card format"` (`card_problems()`), `"card sources"` (`source_problems(cards.load_cards())`), `"card reviewed_for"` (`version_problems(cards.load_cards(), _bot_version())`). V237-7 names `test_the_real_guide_passes[card format]` in its fallback note.

- [ ] **Step 1: Confirm the consumed names**

Run: `git grep -n "^def source_problems\|^def version_problems\|^def _bot_version\|^REAL_CHECKS\|^def strategy_file_problems" tests/admin/test_guide_content.py`
Expected: five lines.

Run: `git grep -n "^def touched\|^def load_cards" scripts/dev/guide_sources.py`
Expected: two lines.

- [ ] **Step 2: Write the failing tests**

In `tests/admin/test_guide_content.py`, append the synthetic tests at the end of the file:

```python
# --- strategy cards (v237 V237-6) ------------------------------------------------------

def _write_card(folder: Path, name: str, *, strategy: str, body: str = "**Idea.** x\n",
                reviewed_for: str = "2.19.2",
                sources=("swingbot/core/market/entry_filters.py",)) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    src = "".join(f"  - {s}\n" for s in sources)
    path = folder / name
    path.write_text(f'---\nstrategy: "{strategy}"\nreviewed_for: {reviewed_for}\n'
                    f"sources:\n{src}---\n{body}", encoding="utf-8")
    return path


def test_real_checks_cover_the_cards():
    assert {"card format", "card sources", "card reviewed_for"} <= set(REAL_CHECKS)


def test_card_format_is_vacuous_without_a_folder(tmp_path):
    assert card_problems(tmp_path) == []
    (tmp_path / "strategies").mkdir()
    assert card_problems(tmp_path) == []


def test_card_format_reports_parse_errors_and_unregistered_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(live_market, "registered_strategy_keys",
                        lambda: ("Break & Retest", "RSI", "VWAP"))
    folder = tmp_path / "strategies"
    _write_card(folder, "rsi.md", strategy="RSI")
    _write_card(folder, "break-retest.md", strategy="Break & Retest", body="## Setup\n")
    _write_card(folder, "macd.md", strategy="MACD")
    _write_card(folder, "vwap.md", strategy="Vwap")   # slug matches, key does not
    assert card_problems(tmp_path) == [
        "break-retest.md: line 1 is a heading; the page adds '### <strategy>' itself",
        "macd.md: strategy 'MACD' is not registered",
        "vwap.md: strategy 'Vwap' is not registered",
    ]


def test_card_format_reports_a_file_name_that_does_not_match(tmp_path, monkeypatch):
    monkeypatch.setattr(live_market, "registered_strategy_keys", lambda: ("Break & Retest",))
    _write_card(tmp_path / "strategies", "break-and-retest.md", strategy="Break & Retest")
    assert card_problems(tmp_path) == [
        "break-and-retest.md: file name must be break-retest.md for strategy 'Break & Retest'"]


def test_source_and_version_checks_run_over_cards(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("def entries(): ...\n", encoding="utf-8")
    good = cards.StrategyCard(path=Path("rsi.md"), strategy="RSI", reviewed_for="2.19.2",
                              sources=("pkg/mod.py:entries", "pkg"), body="x")
    bad = cards.StrategyCard(path=Path("macd.md"), strategy="MACD", reviewed_for="2.20.0",
                             sources=("pkg/mod.py:gone", "pkg/none.py"), body="x")
    assert source_problems([good], root=tmp_path) == []
    assert source_problems([bad], root=tmp_path) == [
        "macd.md: gone is no longer defined in pkg/mod.py",
        "macd.md: source pkg/none.py does not exist"]
    assert version_problems([good, bad], "2.19.2") == [
        "macd.md: reviewed_for 2.20.0 is newer than bot 2.19.2"]


def test_real_card_checks_read_the_guide_folder(tmp_path, monkeypatch):
    from swingbot.admin.guide import chapters as chapters_mod
    monkeypatch.setattr(chapters_mod, "guide_dir", lambda: tmp_path)
    monkeypatch.setattr(live_market, "registered_strategy_keys", lambda: ("RSI",))
    _write_card(tmp_path / "strategies", "rsi.md", strategy="RSI", reviewed_for="99.0.0",
                sources=("swingbot/no_such_module.py",))
    assert REAL_CHECKS["card format"]([]) == []
    assert REAL_CHECKS["card sources"]([]) == [
        "rsi.md: source swingbot/no_such_module.py does not exist"]
    assert REAL_CHECKS["card reviewed_for"]([]) == [
        f"rsi.md: reviewed_for 99.0.0 is newer than bot {_bot_version()}"]
```

In `tests/scripts/test_guide_sources.py`, append:

```python
# --- strategy cards (v237 V237-6) ------------------------------------------------------

def test_touched_accepts_a_strategy_card(tmp_path):
    from swingbot.admin.guide.cards import StrategyCard
    card = StrategyCard(path=tmp_path / "rsi.md", strategy="RSI", reviewed_for="2.19.2",
                        sources=("swingbot/core/market/entry_filters.py:rsi_entries",
                                 "swingbot/core/edge"),
                        body="**Idea.** x")
    changed = ["swingbot/core/market/entry_filters.py", "swingbot/core/edge/heat.py", "README.md"]
    assert gs.touched(changed, [card]) == [
        (card, ["swingbot/core/edge/heat.py", "swingbot/core/market/entry_filters.py"])]
    assert gs.touched(["README.md"], [card]) == []


def test_both_card_loaders_read_the_same_sources(tmp_path):
    from swingbot.admin.guide import cards
    folder = tmp_path / "strategies"
    folder.mkdir()
    (folder / "rsi.md").write_text(
        '---\nstrategy: "RSI"\nreviewed_for: 2.19.2\nsources:\n'
        "  - swingbot/core/market/entry_filters.py:rsi_entries\n"
        "  - swingbot/core/market/strategy_types.py:admits\n---\n**Idea.** x\n",
        encoding="utf-8")
    assert ([(c.path.name, c.sources) for c in gs.load_cards(tmp_path)]
            == [(c.path.name, c.sources) for c in cards.load_cards(tmp_path)])
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_content.py`
Expected: FAIL in the new tests only — `NameError: name 'card_problems' is not defined`, `NameError: name 'cards' is not defined`, and `test_real_checks_cover_the_cards` (`card format` not in `REAL_CHECKS`); v235's tests still pass.

Run: `python scripts/dev/testrun.py file tests/scripts/test_guide_sources.py`
Expected: PASS already — `touched()` and both loaders exist; these two tests pin behaviour the cards rely on (a red here means `guide_sources` drifted: fix it, never the test).

- [ ] **Step 4: Add the card checks**

In `tests/admin/test_guide_content.py`:

(a) Add `cards` to the guide import line, which becomes (V237-1 already added `live_risk`):

```python
from swingbot.admin.guide import cards, live_market, live_risk, placeholders
```

and add `GuideFormatError` to the `from swingbot.admin.guide.chapters import (...)` list.

(b) Put the card check directly after `strategy_file_problems`:

```python
def card_problems(root: Path | None = None) -> list[str]:
    """Every card parses (cards.parse_card) and names a registered strategy key."""
    folder = cards.cards_dir(root)
    if not folder.is_dir():
        return []
    registered = set(live_market.registered_strategy_keys())
    problems = []
    for path in sorted(folder.glob("*.md")):
        try:
            card = cards.parse_card(path)
        except GuideFormatError as exc:
            problems.append(str(exc))
            continue
        if card.strategy not in registered:
            problems.append(f"{path.name}: strategy {card.strategy!r} is not registered")
    return problems
```

(c) Add three entries at the end of the `REAL_CHECKS` dict (after `"bare percent": bare_percent_problems,`):

```python
    "card format": lambda g: card_problems(),
    "card sources": lambda g: source_problems(cards.load_cards()),
    "card reviewed_for": lambda g: version_problems(cards.load_cards(), _bot_version()),
```

No production module changes in this task.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_content.py`
Expected: PASS (`0 failed`); `test_the_real_guide_passes[card format]`, `[card sources]`, `[card reviewed_for]` pass vacuously (no `docs/guide/strategies/` yet).

Run: `python scripts/dev/testrun.py file tests/scripts/test_guide_sources.py`
Expected: PASS.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (`card_problems` is about 5).

- [ ] **Step 6: Commit**

```bash
git add tests/admin/test_guide_content.py tests/scripts/test_guide_sources.py
git commit -m "test(guide): freshness gate covers strategy cards -- format, sources, reviewed_for (v237 V237-6)"
```

