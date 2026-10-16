# v170 Simple alerts: money beside R, symbol labels, plan buttons. Part 1: money, ticket, lifecycle

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this file whole**: `grep -n "^### Task V170-3" -A 300 <this file>`.

**Spec:** [`docs/superpowers/specs/2026-10-16-v170-simple-alerts-money-symbols-buttons-design.md`](../specs/2026-10-16-v170-simple-alerts-money-symbols-buttons-design.md)
**Index:** [`2026-10-16-v170-simple-alerts-money-symbols-buttons_0-index.md`](2026-10-16-v170-simple-alerts-money-symbols-buttons_0-index.md): `## Where to work` (worktree `$WT`, main tree `$R`, test database), `## Global Constraints`, `## Decisions taken while planning`, `## Parallelisation` and the `## Task ledger` all apply to every task below. Read them before starting.
**Bump:** minor
**Edge:** none (integrity)

Tasks in this part: V170-1 (tokens), V170-2 (`trade_for_plan`), V170-3 (`Money` and the ticket), V170-4 (lifecycle transitions). V170-5 (close messages) is in part 2 and rewrites `_closed`; nothing in this part changes close wording.

**Glyph reference used throughout** (all from `tokens.FEED_SYMBOLS`, created in V170-1): `▶` entry, `🛑` stop, `💰` tp1, `🏃` runner, `🎯` tp2, `〜` (U+301C) trail, `⚖` breakeven, `⏳` expiry, `⛔` invalid, `🔒` if_fills, `🧾` pnl, `✅` win, `❌` loss, `➖` flat, `≥` at_or_above, `≤` at_or_below. R strings keep U+2212 (`−1.0R`); dollar strings keep ASCII `-` (`-$248.40`).

# Phase 1: Money foundations

### Task V170-1: `tokens.fmt_money`, `FEED_SYMBOLS`, legend; `plan_table.signed_money` re-export

**Model:** haiku — a move of one pure function plus constant tables, fully specified below.

**Files:**
- Modify: `swingbot/core/presentation/tokens.py` (append after `fmt_r`, line 106)
- Modify: `swingbot/core/scanning/plan_table.py:133-145` (`signed_money` body becomes a re-export)
- Create: `tests/presentation/test_feed_symbols.py`

**Interfaces:**
- Consumes: nothing from this plan.
- Produces (ledger contract, final): `tokens.fmt_money(amount: float, currency: str) -> str`; `plan_table.signed_money` is the same object as `tokens.fmt_money`; `tokens.FEED_SYMBOLS: dict[str, str]` with keys in this order `entry, stop, tp1, runner, tp2, trail, breakeven, expiry, invalid, if_fills, pnl, win, loss, flat, at_or_above, at_or_below`; `tokens.FEED_SYMBOL_WORDS: dict[str, str]` (same keys, same order); `tokens.COST_BASIS = "(paper, gross)"`; `tokens.COST_BASIS_SENTENCE = "Feed dollars: paper account, before fees, slippage and tax."`; `tokens.feed_legend() -> str`.

- [ ] **Step 0: Create (or reuse) the worktree**

Use the `worktree-lifecycle` skill. If `git -C E:/Documents/Private/Projects/Discord-Bot worktree list` already lists `.claude/worktrees/2026-10-16-v170-simple-alerts-money-symbols-buttons`, reuse it. Otherwise:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot worktree add -b 2026-10-16-v170-simple-alerts-money-symbols-buttons E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v170-simple-alerts-money-symbols-buttons main
```

Below, `$WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v170-simple-alerts-money-symbols-buttons`. Every path in this task is under `$WT`.

- [ ] **Step 1: Write the failing test**

Create `$WT/tests/presentation/test_feed_symbols.py`:

```python
"""v170: the execution feed's money format and its one table of symbols."""
import pytest

from swingbot.core.presentation import tokens
from swingbot.core.scanning import plan_table

KEYS = ("entry", "stop", "tp1", "runner", "tp2", "trail", "breakeven", "expiry",
        "invalid", "if_fills", "pnl", "win", "loss", "flat", "at_or_above", "at_or_below")


@pytest.mark.parametrize("amount,expected", [
    (250.0, "+$250.00"),
    (-248.4, "-$248.40"),          # ASCII hyphen-minus, never U+2212 (A9)
    (0.0, "+$0.00"),               # zero and above carry '+'
    (12345.678, "+$12,345.68"),
    (-0.004, "-$0.00"),
])
def test_fmt_money_is_signed_with_an_ascii_minus(amount, expected):
    assert tokens.fmt_money(amount, "$") == expected


def test_signed_money_is_the_same_object_as_fmt_money():
    # instructions.py may not import scanning, so the helper moved to tokens;
    # every old importer keeps the name and the exact behaviour.
    assert plan_table.signed_money is tokens.fmt_money


def test_fmt_r_keeps_its_unicode_minus():
    assert tokens.fmt_r(-1.0) == "\u22121.0R"


def test_feed_symbols_has_every_key_in_order():
    assert tuple(tokens.FEED_SYMBOLS) == KEYS
    assert tokens.FEED_SYMBOLS == {
        "entry": "\u25b6", "stop": "\U0001f6d1", "tp1": "\U0001f4b0",
        "runner": "\U0001f3c3", "tp2": "\U0001f3af", "trail": "\u301c",
        "breakeven": "\u2696", "expiry": "\u23f3", "invalid": "\u26d4",
        "if_fills": "\U0001f512", "pnl": "\U0001f9fe", "win": "\u2705",
        "loss": "\u274c", "flat": "\u2796", "at_or_above": "\u2265",
        "at_or_below": "\u2264",
    }


def test_every_glyph_has_one_meaning():
    glyphs = list(tokens.FEED_SYMBOLS.values())
    assert len(glyphs) == len(set(glyphs))


def test_warning_glyph_stays_reserved():
    # the heat/cluster/kill-switch warnings own the warning sign (panel finding)
    assert "\u26a0" not in tokens.FEED_SYMBOLS.values()


def test_every_symbol_has_a_legend_word():
    assert tuple(tokens.FEED_SYMBOL_WORDS) == KEYS
    assert all(word.strip() for word in tokens.FEED_SYMBOL_WORDS.values())


def test_cost_basis_strings():
    assert tokens.COST_BASIS == "(paper, gross)"
    assert tokens.COST_BASIS_SENTENCE == (
        "Feed dollars: paper account, before fees, slippage and tax.")


def test_legend_is_generated_from_the_table():
    legend = tokens.feed_legend()
    assert legend.startswith("Feed symbols: ")
    assert legend.endswith(". " + tokens.COST_BASIS_SENTENCE)
    for key, glyph in tokens.FEED_SYMBOLS.items():
        assert f"{glyph} {tokens.FEED_SYMBOL_WORDS[key]}" in legend
    assert legend.count(" · ") == len(KEYS) - 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/presentation/test_feed_symbols.py`
Expected: FAIL with `AttributeError: module 'swingbot.core.presentation.tokens' has no attribute 'fmt_money'` (and the other new names).

- [ ] **Step 3: Implement**

Append to `$WT/swingbot/core/presentation/tokens.py` (after `fmt_r`):

```python
def fmt_money(amount: float, currency: str) -> str:
    """'+$500.00' / '-$500.00' -- an explicitly signed currency figure.

    One helper because this exact format string had been hand-copied into
    three surfaces (the two-leg sizing block, the TP1-hit alert and the
    !liveplans board) and got the sign wrong twice on the way: once as a
    hardcoded '+' with no abs() ('+$-500.00'), and once as a bare '' for the
    negative branch, which renders a banked *loss* as a positive-looking
    '$500.00'. The sign is the whole point of the figure, so it lives in
    exactly one place. v170 moved it here from scanning/plan_table.py
    (``signed_money`` there is this same object) so presentation/instructions
    can use it without importing scanning. The minus is ASCII, unlike
    fmt_r's U+2212 (v170 A9: changing either would alter every surface)."""
    return f"{'+' if amount >= 0 else '-'}{currency}{abs(amount):,.2f}"


#: v170: the execution feed's one table of symbols. Every glyph the feed
#: prints comes from here (presentation/instructions.py holds no glyph
#: literal), each glyph has exactly one meaning, and the !help legend is
#: generated from it. The warning sign stays reserved for block warnings.
FEED_SYMBOLS: dict[str, str] = {
    "entry": "▶",
    "stop": "🛑",
    "tp1": "💰",
    "runner": "🏃",
    "tp2": "🎯",
    "trail": "〜",
    "breakeven": "⚖",
    "expiry": "⏳",
    "invalid": "⛔",
    "if_fills": "🔒",
    "pnl": "🧾",
    "win": "✅",
    "loss": "❌",
    "flat": "➖",
    "at_or_above": "≥",
    "at_or_below": "≤",
}

#: The legend's word for each FEED_SYMBOLS key, same keys, same order.
FEED_SYMBOL_WORDS: dict[str, str] = {
    "entry": "entry",
    "stop": "stop",
    "tp1": "first target (TP1)",
    "runner": "runner",
    "tp2": "second target (TP2)",
    "trail": "trailing stop",
    "breakeven": "stop to break-even",
    "expiry": "time limit",
    "invalid": "invalidation",
    "if_fills": "if the stop fills",
    "pnl": "profit and loss",
    "win": "win",
    "loss": "loss",
    "flat": "flat",
    "at_or_above": "at or above",
    "at_or_below": "at or below",
}

#: Every feed P&L figure is paper and gross: the tracker knows no fees,
#: slippage or tax (tracking/performance.py module docstring).
COST_BASIS = "(paper, gross)"
COST_BASIS_SENTENCE = "Feed dollars: paper account, before fees, slippage and tax."


def feed_legend() -> str:
    """The !help legend line, built from FEED_SYMBOLS so it cannot drift."""
    pairs = " · ".join(f"{glyph} {FEED_SYMBOL_WORDS[key]}"
                       for key, glyph in FEED_SYMBOLS.items())
    return f"Feed symbols: {pairs}. {COST_BASIS_SENTENCE}"
```

Check the literal glyphs you typed against the test's escapes: `▶` U+25B6, `🛑` U+1F6D1, `💰` U+1F4B0, `🏃` U+1F3C3, `🎯` U+1F3AF, `〜` U+301C, `⚖` U+2696 (no variation selector), `⏳` U+23F3, `⛔` U+26D4, `🔒` U+1F512, `🧾` U+1F9FE, `✅` U+2705, `❌` U+274C, `➖` U+2796, `≥` U+2265, `≤` U+2264. The equality test fails on any mismatch. (Typing them as `"\u25b6"`-style escapes in `tokens.py` is equally fine.)

In `$WT/swingbot/core/scanning/plan_table.py`, add the import beside the existing `from swingbot.core.presentation.ansi import r_multiple`:

```python
from swingbot.core.presentation import tokens
```

and replace the whole `def signed_money(...)` function (lines 133-145, docstring included) with:

```python
#: v170: moved to presentation/tokens.py as fmt_money; this name stays for
#: every existing importer (scanning/embeds.py, lifecycle_embeds.py,
#: commands/plans.py and leg_rows below). Same object, not a wrapper.
signed_money = tokens.fmt_money
```

`leg_rows` (same module) keeps calling `signed_money(pnl, currency)` unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/presentation/test_feed_symbols.py`
Expected: PASS (all tests).

Run: `python $WT/scripts/dev/testrun.py changed`
Expected: `0 failed`. Existing `signed_money` users (`leg_rows`, lifecycle partial lines, `!liveplans`) render byte-identical output because the body is unchanged.

- [ ] **Step 5: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/core/presentation/tokens.py $WT/swingbot/core/scanning/plan_table.py`
Expected: no line naming `fmt_money` or `feed_legend` (both grade A).

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/core/presentation/tokens.py swingbot/core/scanning/plan_table.py tests/presentation/test_feed_symbols.py
git -C $WT commit -m "feat(v170): fmt_money and the feed symbol table in tokens

signed_money moves to tokens.fmt_money and stays importable from
plan_table as the same object; FEED_SYMBOLS, legend words and the
paper/gross cost-basis strings land beside it.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the last command shows the main tree unchanged (only what it showed before this task).

### Task V170-2: `TradeLog.trade_for_plan` (any status)

**Model:** sonnet — a thin DB accessor whose tests need the Postgres test database and the trade-log fixtures.

**Files:**
- Modify: `swingbot/core/tracking/performance.py` (new method directly after `get_trade_by_id`, line 1239-1240)
- Create: `tests/tracking/test_trade_for_plan.py`

**Interfaces:**
- Consumes: `trades_repo().by_plan_id(plan_id, *, conn=None) -> dict | None` (exists, `swingbot/core/db/repositories/trades.py:52`, any status, `limit=1`, unordered); `_json_record(row) -> dict` (exists, `performance.py:565`).
- Produces (ledger contract, final): `TradeLog.trade_for_plan(self, plan_id: str) -> dict | None` — the record in TradeLog's JSON shape (same shape `_all()` returns: `id`, `horizon_key`, float `entry`/`stop_loss`, `shares`, `legs`, `status`, `realized_pnl_amount`, …) or `None`. Consumed by V170-4 (`execution_embeds._linked_trade`) and V170-10 (`pnl_now._linked_trade`).

Spec A1: the repository already matches any status, so this is a wrapper, not a rescan. Index Decision 7: legacy data with two records for one plan id returns either one; add no preference logic.

- [ ] **Step 0: Test database up**

DB-backed tests SKIP when the test Postgres is unreachable, and a skip is not green here.

```bash
docker compose -f E:/Documents/Private/Projects/Discord-Bot/docker-compose.yml --profile test up -d db-test
docker ps --filter name=swing-db-test --format "{{.Names}} {{.Ports}}"
```

Expected: one `swing-db-test` row publishing `55432`. If the port differs, export `TEST_DATABASE_URL=postgresql+psycopg://swingbot:swingbot@127.0.0.1:<port>/swingbot_test` for every `testrun.py` call in this task.

- [ ] **Step 1: Write the failing test**

Create `$WT/tests/tracking/test_trade_for_plan.py`:

```python
"""v170 A1: TradeLog.trade_for_plan finds a plan's paper trade in ANY status.

append_leg_by_plan / close_plan_trade only match status == "open", so a
closed trade could not be found by plan id before this accessor. The feed's
lifecycle money and the P&L-now reply both read it."""
import pytest

from swingbot import config
from swingbot.core.tracking.performance import TradeLog
from tests.store_seed import seed_store


@pytest.fixture
def tlog(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", {
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
        "sizing_mode": "risk_pct", "balance_history": [],
    })
    return TradeLog()


def _log(tlog, plan_id="p1", ticker="INTU"):
    tlog.log_trade(
        ticker=ticker, strategy="EMA", horizon_key="5m",
        direction="bullish", confidence_level=4, confidence_label="High",
        entry=361.04, stop_loss=353.62, take_profit=373.92, plan_id=plan_id)


def test_an_open_trade_is_found_by_its_plan_id(tlog):
    _log(tlog)
    trade = tlog.trade_for_plan("p1")
    assert trade is not None
    assert (trade["plan_id"], trade["ticker"], trade["status"]) == ("p1", "INTU", "open")
    assert trade["entry"] == pytest.approx(361.04)
    assert trade["shares"] > 0
    assert trade["realized_pnl_amount"] is None


def test_a_closed_trade_is_still_found_with_its_settled_amount(tlog):
    _log(tlog)
    tlog.close_plan_trade("p1", {"fraction": 1.0, "exit_price": 370.0, "r": 1.2,
                                 "reason": "win"}, "win")
    trade = tlog.trade_for_plan("p1")
    assert trade is not None and trade["status"] == "win"
    shares = trade["shares"]
    assert trade["realized_pnl_amount"] == pytest.approx(shares * (370.0 - 361.04), abs=0.01)


def test_the_shape_matches_get_trade_by_id(tlog):
    _log(tlog)
    by_plan = tlog.trade_for_plan("p1")
    assert by_plan == tlog.get_trade_by_id(by_plan["id"])


def test_an_unknown_or_empty_plan_id_is_none(tlog):
    _log(tlog)
    assert tlog.trade_for_plan("nope") is None
    assert tlog.trade_for_plan("") is None
    assert tlog.trade_for_plan(None) is None


def test_another_plans_trade_is_never_returned(tlog):
    _log(tlog, plan_id="p1", ticker="INTU")
    _log(tlog, plan_id="p2", ticker="MSFT")
    assert tlog.trade_for_plan("p2")["ticker"] == "MSFT"


def test_it_does_not_rescan_the_whole_log(tlog, monkeypatch):
    _log(tlog)
    monkeypatch.setattr(TradeLog, "_all", lambda self: pytest.fail("rescanned every trade"))
    assert tlog.trade_for_plan("p1")["plan_id"] == "p1"
```

`test_a_closed_trade_is_still_found_with_its_settled_amount` checks the settle arithmetic loosely (one leg, fraction 1.0, `shares × (exit − entry)`); if `settle_legs` rounds differently the `abs=0.01` absorbs it. If it fails by more, read `settle_legs` (`performance.py:273`) and pin its exact formula instead of loosening the tolerance.

- [ ] **Step 2: Run test to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/tracking/test_trade_for_plan.py`
Expected: FAIL with `AttributeError: 'TradeLog' object has no attribute 'trade_for_plan'`. If the output says `skipped`, the test database is not reachable: fix Step 0 first.

- [ ] **Step 3: Implement**

In `$WT/swingbot/core/tracking/performance.py`, directly after `get_trade_by_id` (line 1239-1240), add:

```python
    def trade_for_plan(self, plan_id: str) -> dict | None:
        """The paper trade linked to ``plan_id``, in ANY status (v170 A1).

        append_leg_by_plan and close_plan_trade match only open trades; the
        execution feed's lifecycle money and the P&L-now button also need a
        closed one. A thin wrapper over the repository's own any-status
        lookup (limit 1, unordered): legacy data holding two records for one
        plan id returns either of them."""
        if not plan_id:
            return None
        from swingbot.core.db.repositories.trades import trades_repo
        row = trades_repo().by_plan_id(plan_id)
        return _json_record(row) if row else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/tracking/test_trade_for_plan.py`
Expected: 6 passed, 0 skipped.

- [ ] **Step 5: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/core/tracking/performance.py`
Expected: `trade_for_plan` absent from the output (grade A). The pre-existing C/D/E/F functions listed there (`update_open_trades`, `check_near_tp_timeout`, …) are untouched and out of scope.

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/core/tracking/performance.py tests/tracking/test_trade_for_plan.py
git -C $WT commit -m "feat(v170): TradeLog.trade_for_plan, any-status lookup by plan id

Thin wrapper over trades_repo().by_plan_id so the feed and the P&L-now
button can read a closed plan's trade record.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the main tree unchanged.

# Phase 2: Ticket and lifecycle messages

### Task V170-3: `Money`, `money_from`; ticket with symbols, verbs and "if hit" $; ticket wiring

**Model:** sonnet — a multi-file rewrite of a pinned-string surface with new helpers and exact float arithmetic.

**Files:**
- Modify: `swingbot/core/presentation/instructions.py` (module docstring 1-9; new block after `signed_r`, line 89; `ticket_for` 127-176 rewritten)
- Modify: `swingbot/core/scanning/execution_embeds.py:13-18` (imports), `:77-88` (`build_ticket_embed`), new `_ticket_money`
- Modify: `tests/presentation/test_instructions.py:1-12` (imports, constants), `:37-111` (the order-ticket section)
- Modify: `tests/scanning/test_execution_embeds.py:1-9` (imports), `:56-66` (`test_ticket_and_event_embeds`), new tests appended
- Modify: `tests/scanning/test_simple_alerts.py:127` and `:167-170`

**Interfaces:**
- Consumes: `tokens.FEED_SYMBOLS`, `tokens.fmt_money` (V170-1).
- Produces (ledger contract, final):
  - `instructions.Money` — `@dataclass(frozen=True)`: `currency: str`, `shares: int | None`, `realized_amount: float | None = None`, `record_shares: float | None = None`.
  - `instructions.money_from(shares: float | None, currency: str, *, realized_amount: float | None = None, priced: bool = True) -> Money`.
  - `instructions.ticket_for(plan, *, logged: bool, not_logged_reason: str | None, money: Money | None = None, warnings: tuple[str, ...] = (), level: int | None = None) -> Instruction` (`sizing` and `currency` kwargs removed).
  - Private helpers V170-4 and V170-5 reuse: `_S = tokens.FEED_SYMBOLS`, `_sign(direction) -> int`, `_printed(x) -> float`, `_r_at(plan, entry, level) -> float | None`, `_join(*parts) -> str`, `_priced(money) -> bool`, `_toward(direction) -> str`, `_against(direction) -> str`, `_dollars(amount, money) -> str`.
  - `execution_embeds._ticket_money(plan) -> Money`.

Rules this task enforces (index Global Constraints, spec §1-§2, A3, A9): every order line keeps its broker verb; projected $ = **printed** whole shares × **printed** move, signed by direction; the ticket's $ come from the same sizing snapshot the paper trade is logged from; the stop line shows the loss $ beside the gains; TP2 gets a figure only when `plan.tp2` is set; the trail gets none; R uses `(level − entry) / |entry − stop|` signed by direction; no glyph literal in `instructions.py`; the do-not-place ticket keeps its wording and gets no glyph (Decision 4).

- [ ] **Step 1: Write the failing tests**

In `$WT/tests/presentation/test_instructions.py`:

1. Add `import re` to the imports (after `import datetime as dt`).
2. Below `SIZING = {...}` (line 12, keep it: V170-4 still uses it until it rewrites the lifecycle tests) add:

```python
MONEY = ins.money_from(2439.02, "$")


def _spec_long(**kw):
    """The spec's §2 example ticket: 54 sh between 182.40 / 177.80 / 189.10 / 195.00."""
    base = dict(trigger_price=182.4, stop_loss=177.8, tp1=189.1, tp2=195.0,
                trail_atr_mult=2.0, created_at="2026-10-15")
    base.update(kw)
    return _long_pending(**base)


def _usd(line: str) -> float:
    """The signed dollar figure after 'if hit' in one line."""
    sign, digits = re.search(r"if hit ([+-])\$([\d,]+\.\d\d)", line).groups()
    return (1 if sign == "+" else -1) * float(digits.replace(",", ""))
```

(`_spec_long` must sit below `_long_pending`; put both new helpers right after `_event`.)

3. Replace the whole order-ticket section, from the `# --- the order ticket ---` comment (line 37) through the end of `test_no_blocks_means_no_warnings` (line 111), with:

```python
# --- money ------------------------------------------------------------------

def test_money_from_floors_shares_and_keeps_the_record_count():
    assert ins.money_from(54.41, "$", realized_amount=12.5) == ins.Money(
        currency="$", shares=54, realized_amount=12.5, record_shares=54.41)
    assert ins.money_from(None, "$") == ins.Money(currency="$", shares=None)
    assert ins.money_from(0.4, "$").shares is None             # under one share: unsized


def test_unpriced_money_keeps_the_share_count_and_drops_every_dollar():
    assert ins.money_from(54.41, "$", realized_amount=1.0, priced=False) == ins.Money(
        currency="$", shares=54, realized_amount=None, record_shares=None)


# --- the order ticket --------------------------------------------------------

def test_a_long_stop_entry_ticket_is_a_complete_bracket():
    t = ins.ticket_for(_long_pending(), logged=True, not_logged_reason=None,
                       money=MONEY, level=5)
    assert (t.verb, t.tone, t.level, t.ticker, t.plan_id) == (ins.PLACE, "level", 5, "AAPL", "p1")
    assert t.headline == "▶ BUY STOP 102.50 · 2,439 sh"
    assert t.lines == (
        "🛑 SELL STOP 98.40 · if hit -$9,999.90 · −1.0R",
        "💰 SELL LIMIT 106.00 · 1,219 sh · if hit +$4,266.50 · +0.9R",
        "🏃 1,220 sh: 🎯 SELL LIMIT 110.00 · if hit +$9,150.00 · +1.8R · "
        "〜 trail 3×ATR, stop moves pinged here",
        "⚖ stop → entry at ≥ 104.25",
        "⏳ CANCEL after Thu 17 Sep (5 sessions) · ⛔ CANCEL if ≤ 98.40 first",
    )
    assert t.warnings == ()


def test_the_spec_example_ticket():
    t = ins.ticket_for(_spec_long(), logged=True, not_logged_reason=None,
                       money=ins.money_from(54.9, "$"))
    assert t.headline == "▶ BUY STOP 182.40 · 54 sh"
    assert t.lines == (
        "🛑 SELL STOP 177.80 · if hit -$248.40 · −1.0R",
        "💰 SELL LIMIT 189.10 · 27 sh · if hit +$180.90 · +1.5R",
        "🏃 27 sh: 🎯 SELL LIMIT 195.00 · if hit +$340.20 · +2.7R · "
        "〜 trail 2×ATR, stop moves pinged here",
        "⚖ stop → entry at ≥ 185.75",
        "⏳ CANCEL after Thu 22 Oct (5 sessions) · ⛔ CANCEL if ≤ 177.80 first",
    )


@pytest.mark.parametrize("index,shares,level", [(0, 54, 177.80), (1, 27, 189.10), (2, 27, 195.00)])
def test_every_projected_dollar_is_printed_shares_times_printed_move(index, shares, level):
    t = ins.ticket_for(_spec_long(), logged=True, not_logged_reason=None,
                       money=ins.money_from(54.9, "$"))
    assert _usd(t.lines[index]) == pytest.approx(shares * (level - 182.40), abs=0.005)


def test_a_sized_short_ticket_flips_verbs_comparisons_and_signs():
    t = ins.ticket_for(_short_pending(tp2=90.0), logged=True, not_logged_reason=None,
                       money=ins.money_from(30.6, "$"))
    assert t.headline == "▶ SELL STOP 97.50 · 30 sh"
    assert t.lines == (
        "🛑 BUY STOP 101.60 · if hit -$123.00 · −1.0R",
        "💰 BUY LIMIT 94.00 · 15 sh · if hit +$52.50 · +0.9R",
        "🏃 15 sh: 🎯 BUY LIMIT 90.00 · if hit +$112.50 · +1.8R · "
        "〜 trail 2.5×ATR, stop moves pinged here",
        "⚖ stop → entry at ≤ 95.75",
        "⏳ CANCEL after Wed 16 Sep (3 sessions) · ⛔ CANCEL if ≥ 101.60 first",
    )


def test_a_short_ticket_survives_missing_sizing_with_r_only():
    t = ins.ticket_for(_short_pending(), logged=True, not_logged_reason=None, level=4)
    assert t.headline == "▶ SELL STOP 97.50 · size n/a"
    assert t.lines == (
        "🛑 BUY STOP 101.60 · if hit −1.0R",
        "💰 BUY LIMIT 94.00 · 50% · if hit +0.9R",
        "🏃 50%: 〜 trail 2.5×ATR, stop moves pinged here",
        "⚖ stop → entry at ≤ 95.75",
        "⏳ CANCEL after Wed 16 Sep (3 sessions) · ⛔ CANCEL if ≥ 101.60 first",
    )


def test_unpriced_money_prints_shares_but_no_dollars():
    t = ins.ticket_for(_spec_long(), logged=True, not_logged_reason=None,
                       money=ins.money_from(54.9, "$", priced=False))
    assert t.headline == "▶ BUY STOP 182.40 · 54 sh"
    assert not any("$" in line for line in t.lines)
    assert t.lines[1] == "💰 SELL LIMIT 189.10 · 27 sh · if hit +1.5R"


def test_no_tp2_means_no_runner_figure():
    t = ins.ticket_for(_spec_long(tp2=None), logged=True, not_logged_reason=None,
                       money=ins.money_from(54.9, "$"))
    assert t.lines[2] == "🏃 27 sh: 〜 trail 2×ATR, stop moves pinged here"


def test_a_market_entry_ticket_has_no_cancel_clause():
    t = ins.ticket_for(_long_pending(entry_type="market", trigger_price=100.0,
                                     stop_loss=95.0, tp1=110.0),
                       logged=True, not_logged_reason=None)
    assert t.headline == "▶ BUY AT MARKET ~100.00 · size n/a"
    assert not any("CANCEL" in line for line in t.lines)


def test_a_short_market_entry_says_sell_short():
    t = ins.ticket_for(_short_pending(entry_type="market"), logged=True,
                       not_logged_reason=None)
    assert t.headline.startswith("▶ SELL SHORT AT MARKET ~97.50")


def test_an_unlogged_alert_says_do_not_place_and_why():
    t = ins.ticket_for(_long_pending(), logged=False, not_logged_reason="already open",
                       money=MONEY)
    assert (t.verb, t.tone) == (ins.DO_NOT_PLACE, "inert")
    assert t.headline == "DO NOT PLACE — already open"
    assert t.lines == ("levels: entry 102.50 · stop 98.40 · TP1 106.00",)


def test_cap_blocks_keep_place_and_are_named_above_the_orders():
    warnings = ins.block_warnings(
        heat={"allowed": False, "open_heat": 6.2, "cap": 6.0},
        cluster={"allowed": False, "cluster": ["AMD", "NVDA"],
                 "correlated_heat": 4.1, "cap": 3.0},
        kill={"on": True, "reason": "3 consecutive losses"},
    )
    assert warnings == (
        "⚠ over portfolio heat cap — open 6.2% / cap 6.0%; the bot tracks this at full size",
        "⚠ over correlated-cluster cap — AMD, NVDA at 4.1% / cap 3.0%; "
        "the bot tracks this at full size",
        "⚠ kill switch on (3 consecutive losses) — the bot tracks this at full size",
    )
    t = ins.ticket_for(_long_pending(), logged=True, not_logged_reason=None,
                       money=MONEY, warnings=warnings)
    assert t.verb == ins.PLACE
    assert t.warnings == warnings


def test_no_blocks_means_no_warnings():
    assert ins.block_warnings(heat=None, cluster=None, kill=None) == ()
```

Where the figures come from (so a reviewer can re-derive them): `_long_pending` is trigger 102.50, stop 98.40 (risk 4.10), TP1 106.00, TP2 110.00; 2439.02 shares print as 2,439 with 1,219 at TP1 (floor of 1219.5) and 1,220 on the runner. Stop: 2,439 × −4.10 = −9,999.90, R −1.0. TP1: 1,219 × 3.50 = +4,266.50, R 3.5/4.1 = 0.85 → +0.9R. TP2: 1,220 × 7.50 = +9,150.00, R 7.5/4.1 = 1.83 → +1.8R. The spec example: 54 × −4.60 = −248.40; 27 × 6.70 = +180.90 (6.7/4.6 = 1.46 → +1.5R); 27 × 12.60 = +340.20 (12.6/4.6 = 2.74 → +2.7R); break-even trigger 182.40 + 0.5 × 6.70 = 185.75; created Thu 15 Oct 2026 + 5 weekdays = Thu 22 Oct. Short: 30 sh, 15 + 15; stop 30 × 4.10 against = −123.00; TP1 15 × 3.50 = +52.50; TP2 15 × 7.50 = +112.50. The R minus is U+2212 (`−1.0R`, `signed_r` unchanged); the dollar minus is ASCII (`-$`).

In `$WT/tests/scanning/test_execution_embeds.py`:

1. Add `from swingbot import config` to the imports, and `from swingbot.core.presentation.instructions import Instruction, Money` replacing the existing `Instruction`-only import.
2. In `test_ticket_and_event_embeds` (line 62) change the asserted headline to:

```python
    assert "**▶ BUY STOP 101.00 · size n/a**" in ticket.description
```

3. Append:

```python
def test_ticket_money_comes_from_the_sizing_snapshot(monkeypatch):
    monkeypatch.setattr(execution_embeds, "_sizing_snapshot",
                        lambda entry, plan: {"shares": 10.7, "risk_amount": 50.0})
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    item = make_item(plan_v2=make_plan_v2(entry_type="stop_entry", trigger_price=101.0))
    item.paper_logged = True
    text = execution_embeds.build_ticket_embed(item, item.plan_v2).description
    # make_plan_v2: entry_price 100, stop 95, TP1 110, TP2 120 -> 10 sh, 5 + 5
    assert "**▶ BUY STOP 101.00 · 10 sh**" in text
    assert "🛑 SELL STOP 95.00 · if hit -$50.00 · −1.0R" in text
    assert "💰 SELL LIMIT 110.00 · 5 sh · if hit +$50.00 · +2.0R" in text
    assert "🏃 5 sh: 🎯 SELL LIMIT 120.00 · if hit +$100.00 · +4.0R" in text


def test_ticket_money_without_a_snapshot_is_unsized(monkeypatch):
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    assert execution_embeds._ticket_money(make_plan_v2()) == Money(currency="$", shares=None)
```

In `$WT/tests/scanning/test_simple_alerts.py`:

- line 127: `assert "🏃 50%: 〜 trail 2×ATR" in embed.description`
- lines 167-170 become:

```python
    assert "**▶ BUY AT MARKET ~100.00 · size n/a**" in text
    assert "🛑 SELL STOP 95.00" in text
    assert "💰 SELL LIMIT 110.00 · 50%" in text
    assert "🎯 SELL LIMIT 120.00" in text
```

(line 171 `assert "115.00" not in text` stays.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/presentation/test_instructions.py`
Expected: FAIL — `AttributeError: module ... has no attribute 'money_from'` (collection-time for `MONEY`).

- [ ] **Step 3: Implement in `instructions.py`**

In `$WT/swingbot/core/presentation/instructions.py`:

1. Extend the module docstring's second paragraph so it reads:

```python
"""v81: the execution feed's broker instructions, as pure data.

Every message the simple-alerts channel sends -- an alert's order ticket and
each plan lifecycle event -- is projected here into the verb and the order
lines a reader places at a broker. No discord import, no I/O, no clock:
money (v170: a frozen Money), block annotations and every live stop arrive
as arguments or in the event's detail, which plan_manager stamps. Every
glyph comes from tokens.FEED_SYMBOLS; none is written here as a literal.
core/scanning/execution_embeds.py is the only thing that turns an
Instruction into a Discord embed.
"""
```

2. Directly after `signed_r` (ends line 89) insert:

```python
_S = tokens.FEED_SYMBOLS


@dataclass(frozen=True)
class Money:
    """The dollar inputs of one feed message (v170 §1, A3), as data.

    ``shares`` is the whole-share count the message prints (the floor of the
    position); ``record_shares`` the paper record's unrounded count, used
    only for realised figures (the record's own arithmetic).
    ``realized_amount`` is the record's settled ``realized_pnl_amount``.
    ``record_shares is None`` means no paper record backs the message: it
    still prints share counts but no dollar figure."""

    currency: str
    shares: int | None
    realized_amount: float | None = None
    record_shares: float | None = None


def money_from(shares: float | None, currency: str, *,
               realized_amount: float | None = None, priced: bool = True) -> Money:
    """The one constructor callers use. ``priced=False`` keeps the share
    count (a lifecycle message with no linked record sizes from today's
    snapshot, as before v170) and drops every dollar figure."""
    whole = math.floor(shares) if shares else 0
    return Money(currency=currency, shares=whole or None,
                 realized_amount=realized_amount if priced else None,
                 record_shares=float(shares) if priced and shares else None)


def _sign(direction: str) -> int:
    return 1 if direction == "bullish" else -1


def _printed(x: float) -> float:
    """``x`` as the message prints it, so printed shares × printed move is
    exactly the printed dollars (v170 §1)."""
    return float(_price(x))


def _r_at(plan, entry: float | None, level: float | None) -> float | None:
    """R of ``level`` measured from ``entry`` against the plan's stop, signed
    by direction; None when there is no entry, level or risk."""
    if entry is None or level is None:
        return None
    risk = abs(entry - plan.stop_loss)
    if not risk:
        return None
    return (level - entry) * _sign(plan.direction) / risk


def _join(*parts: str) -> str:
    """Join the non-empty parts with the feed's ' · ' separator."""
    return " · ".join(part for part in parts if part)


def _priced(money: Money | None) -> bool:
    """True when the message may print dollars: shares known and record-backed."""
    return money is not None and money.shares is not None and money.record_shares is not None


def _toward(direction: str) -> str:
    """The comparison glyph for price moving the trade's way."""
    return _S["at_or_above"] if direction == "bullish" else _S["at_or_below"]


def _against(direction: str) -> str:
    """The comparison glyph for price moving against the trade."""
    return _S["at_or_below"] if direction == "bullish" else _S["at_or_above"]


def _dollars(amount: float, money: Money) -> str:
    return tokens.fmt_money(amount, money.currency)


def _projected(plan, entry, level, shares: int | None, money: Money | None) -> str:
    """'If hit' dollars: printed shares × printed move, signed by direction;
    '' when the message is unpriced."""
    if not _priced(money) or shares is None or entry is None or level is None:
        return ""
    return _dollars(shares * (_printed(level) - _printed(entry)) * _sign(plan.direction), money)


def _if_hit(plan, entry, level, shares: int | None, money: Money | None) -> str:
    """'if hit <$> · <R>' for one ticket level; whichever figures exist."""
    r = _r_at(plan, entry, level)
    figures = _join(_projected(plan, entry, level, shares, money),
                    signed_r(r) if r is not None else "")
    return f"if hit {figures}" if figures else ""
```

3. Replace `ticket_for` (lines 127-176) with these three helpers and the new `ticket_for`:

```python
def _leg_sizes(plan, money: Money | None) -> tuple:
    """(size, TP1 qty, runner qty, TP1 shares, runner shares) for the ticket;
    percentages and None share counts when unsized."""
    whole = money.shares if money is not None else None
    if whole is None:
        return ("size n/a", f"{plan.tp1_fraction:.0%}", f"{1 - plan.tp1_fraction:.0%}",
                None, None)
    tp1_shares = math.floor(whole * plan.tp1_fraction)
    runner = whole - tp1_shares
    return f"{whole:,} sh", f"{tp1_shares:,} sh", f"{runner:,} sh", tp1_shares, runner


def _runner_line(plan, entry, side: dict, qty: str, shares: int | None,
                 money: Money | None) -> str:
    """The runner's TP2 order (with its 'if hit' figures) and its trail."""
    trail = f"{_S['trail']} trail {plan.trail_atr_mult:g}×ATR, stop moves pinged here"
    target = ""
    if plan.tp2 is not None:
        target = _join(f"{_S['tp2']} {side['limit']} {_price(plan.tp2)}",
                       _if_hit(plan, entry, plan.tp2, shares, money))
    return f"{_S['runner']} {qty}: {_join(target, trail)}"


def _cancel_line(plan) -> str:
    """A stop entry's two cancel conditions, each saying CANCEL (v170 panel)."""
    sessions = plan_view(plan, bars_since_created=0).bars_to_expiry
    if sessions is None:
        sessions = plan.expiry_bars
    last = approx_last_trigger_session(plan.created_at, plan.expiry_bars)
    return _join(f"{_S['expiry']} CANCEL after {last:%a %d %b} ({sessions} sessions)",
                 f"{_S['invalid']} CANCEL if {_against(plan.direction)} "
                 f"{_price(plan.stop_loss)} first")


def ticket_for(plan, *, logged: bool, not_logged_reason: str | None,
               money: Money | None = None, warnings: tuple[str, ...] = (),
               level: int | None = None) -> Instruction:
    """The order ticket for a new alert (v81 D1, D2, D4). ``logged`` is
    scan_run's own paper-trade decision; the verb mirrors it. v170: every
    order line keeps its broker verb and carries its 'if hit' R and, when
    ``money`` is priced, its dollars; the stop line's loss sits beside the
    gains."""
    side = _sides(plan.direction)
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    common = dict(ticker=plan.ticker, direction=plan.direction,
                  plan_id=plan.plan_id, level=level)
    if not logged:
        reason = not_logged_reason or "the bot is not tracking this setup"
        return Instruction(
            verb=DO_NOT_PLACE, headline=f"{DO_NOT_PLACE} — {reason}",
            lines=(f"levels: entry {_price(entry)} · stop {_price(plan.stop_loss)} · "
                   f"TP1 {_price(plan.tp1)}",),
            tone="inert", **common)

    size, tp1_qty, runner_qty, tp1_shares, runner_shares = _leg_sizes(plan, money)
    whole = money.shares if money is not None else None
    if plan.entry_type == "stop_entry":
        order = f"{side['entry_stop']} {_price(plan.trigger_price)}"
    else:
        order = f"{side['entry_market']} ~{_price(plan.trigger_price)}"
    lines = [
        _join(f"{_S['stop']} {side['stop']} {_price(plan.stop_loss)}",
              _if_hit(plan, entry, plan.stop_loss, whole, money)),
        _join(f"{_S['tp1']} {side['limit']} {_price(plan.tp1)}", tp1_qty,
              _if_hit(plan, entry, plan.tp1, tp1_shares, money)),
        _runner_line(plan, entry, side, runner_qty, runner_shares, money),
        f"{_S['breakeven']} stop → entry at {_toward(plan.direction)} "
        f"{_price(breakeven_trigger(plan, entry))}",
    ]
    if plan.entry_type == "stop_entry":
        lines.append(_cancel_line(plan))
    return Instruction(verb=PLACE, headline=f"{_S['entry']} {order} · {size}",
                       lines=tuple(lines), warnings=tuple(warnings), tone="level", **common)
```

`_whole_shares` stays for now (`_time_exit` and `instruction_for` still read `sizing`; V170-4 removes it).

- [ ] **Step 4: Implement in `execution_embeds.py`**

In `$WT/swingbot/core/scanning/execution_embeds.py` replace the instructions import (lines 13-15) with:

```python
from swingbot.core.presentation.instructions import (CLOSE_AT_MARKET, DO_NOT_PLACE, Instruction,
                                                     Money, block_warnings, instruction_for,
                                                     money_from, ticket_for, total_r)
```

Add above `build_ticket_embed`:

```python
def _ticket_money(plan) -> Money:
    """The ticket's money: the same sizing snapshot scan_run logs the paper
    trade from in the same scan (v170 §1); unsized when there is none."""
    sizing = _sizing_snapshot(_entry(plan), plan) or {}
    return money_from(sizing.get("shares"), config.CURRENCY_SYMBOL)
```

and replace `build_ticket_embed`'s `ticket_for(...)` call with:

```python
    instruction = ticket_for(
        plan, logged=item.paper_logged, not_logged_reason=item.not_logged_reason,
        money=_ticket_money(plan),
        warnings=block_warnings(heat=getattr(item, "heat_blocked", None),
                                cluster=getattr(item, "cluster_blocked", None),
                                kill=getattr(item, "kill_switch_blocked", None)),
        level=item.conf.level,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python $WT/scripts/dev/testrun.py file tests/presentation/test_instructions.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_execution_embeds.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_simple_alerts.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_compression_instructions.py
```

Expected: all four `0 failed`. If an asserted dollar string is off by one cent, print the raw float (`shares * (_printed(level) - _printed(entry))`) before touching the expectation: the printed-move rule is the contract, not the test literal.

Then: `python $WT/scripts/dev/testrun.py changed` — expected `0 failed`. Any other test still pinning an old ticket string (`size n/a` without `▶`, `TP1 SELL LIMIT`, `RUNNER`, `Cancel if:`) gets the new string, never an `in`-loosening.

- [ ] **Step 6: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/core/presentation/instructions.py $WT/swingbot/core/scanning/execution_embeds.py`
Expected: only `instruction_for` (C 13, rewritten by V170-4) may appear; `ticket_for`, `_leg_sizes`, `_runner_line`, `_cancel_line`, `_projected`, `money_from` must not.

- [ ] **Step 7: Commit**

```bash
git -C $WT add swingbot/core/presentation/instructions.py swingbot/core/scanning/execution_embeds.py tests/presentation/test_instructions.py tests/scanning/test_execution_embeds.py tests/scanning/test_simple_alerts.py
git -C $WT commit -m "feat(v170): Money and the order ticket with symbols and if-hit dollars

Every ticket line keeps its broker verb and shows its R and, when sized,
printed shares x printed move in dollars; the stop line carries the loss.
The ticket's money comes from the same sizing snapshot the paper trade
is logged from.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the main tree unchanged.

### Task V170-4: Lifecycle transitions table-driven with symbols, verbs, TP1 realised $ and stop-move projection; linked-record money

**Model:** sonnet — a table-driven refactor of `instruction_for` (C 13 today) plus new money arithmetic across two modules and four test files.

**Files:**
- Modify: `swingbot/core/presentation/instructions.py` (delete `_whole_shares`, lines 78-83; `_time_exit` and `_closed_event` take `money`; everything from `#: transitions whose instruction is a whole builder of its own.` to the end of the file is replaced)
- Modify: `swingbot/core/scanning/execution_embeds.py` (logger, `_linked_trade`, `_event_money`, `build_instruction_embed`)
- Modify: `tests/presentation/test_instructions.py` (delete `SIZING`; the `# --- lifecycle instructions ---` section up to the end of `test_cancellations_name_the_order_to_cancel`)
- Modify: `tests/scanning/test_execution_embeds.py` (autouse fixture; new tests)
- Modify: `tests/scanning/test_compression_instructions.py:22,32-35,127`

**Interfaces:**
- Consumes: from V170-3 `Money`, `money_from`, `_S`, `_sign`, `_printed`, `_r_at`, `_join`, `_priced`, `_dollars`; from V170-2 `TradeLog.trade_for_plan(plan_id) -> dict | None`; from V170-1 `tokens.FEED_SYMBOLS`.
- Produces (ledger contract, final):
  - `instructions.instruction_for(plan, event, *, money: Money | None = None) -> Instruction` — `sizing` kwarg removed; every transition dispatched through `_BUILDERS`; each builder is `(plan, event, side: dict, common: dict, money: Money | None) -> Instruction`. V170-5 replaces only the `"closed"` builder's body (`_closed_event` → `_closed(plan, event.detail, side, common, money)`).
  - `instructions.stop_projection(plan, new_stop: float, money: Money | None) -> tuple[float | None, float]` — ($ or None when unpriced, total R).
  - Private, reused by V170-5: `_leg_dollars(plan, entry, leg, money) -> float` (record arithmetic), `_leg_qty(money, fraction) -> str`.
  - `execution_embeds._linked_trade(plan_id: str) -> dict | None` (never raises; tests monkeypatch it); `execution_embeds._event_money(plan) -> Money`.

Rules (spec §1-§2, A3, index Decisions 2, 4, 5): stop moves say `MOVE SELL STOP` / `MOVE BUY STOP`; the TP1 line keeps its share count and prints realised $ from record arithmetic (`record_shares × fraction × (fill − entry) × sign`); the stop-move projection is `🔒 if it fills: <$> · <R> total`, open part printed shares × printed move, banked legs record arithmetic; `be_moved` carries the projection too; with no linked record, share counts come from today's snapshot and no $ prints; `▶` leads `FILLED`, `⏳` the expiry cancel, `⛔` the invalidation cancel, the risk-cap cancel and the time-exit texts get no glyph; close wording is untouched (V170-5).

- [ ] **Step 0: Test database up**

The lifecycle tests outside this task's files reach `TradeLog` through `_linked_trade`; it never raises, but run the DB check so `testrun.py changed` is not quietly skipping storage tests:

```bash
docker compose -f E:/Documents/Private/Projects/Discord-Bot/docker-compose.yml --profile test up -d db-test
docker ps --filter name=swing-db-test --format "{{.Names}} {{.Ports}}"
```

(Port other than `55432`: export `TEST_DATABASE_URL` as the index says.)

- [ ] **Step 1: Write the failing tests in `test_instructions.py`**

In `$WT/tests/presentation/test_instructions.py` delete the `SIZING = {...}` line (V170-3 kept it only for these tests). Replace everything from the `# --- lifecycle instructions ---` comment through the end of `test_cancellations_name_the_order_to_cancel` with:

```python
# --- lifecycle instructions --------------------------------------------------

def _tp1_leg():
    """The spec example's banked TP1 leg: half at 189.10 from 182.40 (risk 4.60)."""
    return {"fraction": 0.5, "exit_price": 189.1, "r": 6.7 / 4.6, "reason": "tp1"}


def test_filled():
    plan = _long_pending(status="ACTIVE", entry_price=102.61)
    i = ins.instruction_for(plan, _event("filled", entry_price=102.61))
    assert (i.verb, i.headline) == (ins.FILLED, "▶ FILLED @ 102.61 (bot)")
    assert i.lines == (
        "Confirm your broker filled; the bot's R is measured from 102.61",
        "Resting: 🛑 SELL STOP 98.40 · 💰 SELL LIMIT 106.00",
    )


def test_break_even_is_effective_immediately_and_projects_flat():
    plan = _long_pending(status="ACTIVE", entry_price=102.61, working_stop=102.61)
    i = ins.instruction_for(plan, _event("be_moved", working_stop=102.61), money=MONEY)
    assert (i.verb, i.headline) == (ins.MOVE_STOP, "🛑 MOVE SELL STOP → 102.61 now")
    assert i.lines == ("⚖ break-even", "🔒 if it fills: +$0.00 · 0.0R total")


def test_break_even_without_money_projects_r_only():
    plan = _long_pending(status="ACTIVE", entry_price=102.61, working_stop=102.61)
    i = ins.instruction_for(plan, _event("be_moved", working_stop=102.61))
    assert i.lines == ("⚖ break-even", "🔒 if it fills: 0.0R total")


def test_tp1_partial_names_the_filled_shares_the_realised_dollars_and_the_runner_stop():
    plan = _long_pending(status="PARTIAL", entry_price=102.61, working_stop=104.87)
    i = ins.instruction_for(plan, _event("tp1_partial", fraction=0.5, exit_price=106.0,
                                         r=0.8052, working_stop=104.87), money=MONEY)
    assert (i.verb, i.tone) == (ins.MOVE_STOP, "good")
    # realised = record 2439.02 × 0.5 × (106.00 − 102.61) = 4,134.14 (record arithmetic, A3)
    assert i.headline == "💰 TP1 FILLED 1,219 sh @ 106.00 · 🧾 +$4,134.14 · +0.8R"
    assert i.lines == ("🛑 MOVE SELL STOP on the runner → 104.87 now (runner floor)",)


def test_the_spec_example_tp1_uses_the_records_fractional_shares():
    plan = _spec_long(status="PARTIAL", entry_price=182.4, working_stop=186.87)
    event = _event("tp1_partial", working_stop=186.87, **_tp1_leg())
    i = ins.instruction_for(plan, event, money=ins.money_from(54.41, "$"))
    # 27 sh printed (floor of 54 × 0.5); $ = 54.41 × 0.5 × 6.70 = 182.27, not 27 × 6.70
    assert i.headline == "💰 TP1 FILLED 27 sh @ 189.10 · 🧾 +$182.27 · +1.5R"


@pytest.mark.parametrize("money,expected", [
    (ins.money_from(54.41, "$", priced=False), "💰 TP1 FILLED 27 sh @ 189.10 · 🧾 +1.5R"),
    (None, "💰 TP1 FILLED 50% @ 189.10 · 🧾 +1.5R"),
])
def test_tp1_without_a_linked_record_prints_no_dollars(money, expected):
    plan = _spec_long(status="PARTIAL", entry_price=182.4, working_stop=186.87)
    event = _event("tp1_partial", working_stop=186.87, **_tp1_leg())
    assert ins.instruction_for(plan, event, money=money).headline == expected


def test_a_trail_move():
    plan = _plan(status="PARTIAL", entry_price=100.0, stop_loss=95.0, tp1=110.0,
                 working_stop=115.0)
    i = ins.instruction_for(plan, _event("stop_moved", old=106.67, new=115.0,
                                         r_moved=1.666, effective="now"))
    assert i.headline == "🛑 MOVE SELL STOP → 115.00 now"
    assert i.lines == ("〜 trail; +1.7R since the last ping", "🔒 if it fills: +3.0R total")


def test_a_resent_runner_floor_is_labelled_as_the_floor():
    floor = runner_floor(100.0, 110.0)
    plan = _plan(status="PARTIAL", entry_price=100.0, stop_loss=95.0, tp1=110.0,
                 working_stop=floor)
    i = ins.instruction_for(plan, _event("stop_moved", old=95.0, new=floor,
                                         r_moved=2.333, effective="now"))
    assert i.headline == "🛑 MOVE SELL STOP → 106.67 now"
    assert i.lines == ("🏃 runner floor; +2.3R since the last ping",
                       "🔒 if it fills: +1.3R total")


def test_a_resent_break_even_is_effective_now():
    # "effective" is stamped "now" unconditionally (see stop_move_event) --
    # no same-session delay to keep, so a resent notice reads the same way.
    plan = _plan(status="ACTIVE", entry_price=100.0, stop_loss=95.0, tp1=110.0,
                 working_stop=100.0)
    i = ins.instruction_for(plan, _event("stop_moved", old=95.0, new=100.0,
                                         r_moved=1.0, effective="now"))
    assert i.headline == "🛑 MOVE SELL STOP → 100.00 now"
    assert i.lines == ("⚖ break-even; +1.0R since the last ping", "🔒 if it fills: 0.0R total")


def test_a_stop_move_projection_adds_the_banked_leg():
    plan = _spec_long(status="PARTIAL", entry_price=182.4, working_stop=186.0,
                      legs_realized=[_tp1_leg()])
    money = ins.money_from(54.41, "$")
    usd, r_total = ins.stop_projection(plan, 186.0, money)
    # open 27 sh × (186.00 − 182.40) = 97.20, banked 54.41 × 0.5 × 6.70 = 182.2735
    assert usd == pytest.approx(279.4735, abs=1e-6)
    # 0.5 × 1.4565 banked + 0.5 × 0.7826 open
    assert r_total == pytest.approx(1.1196, abs=1e-4)
    i = ins.instruction_for(plan, _event("stop_moved", old=185.0, new=186.0, r_moved=0.78,
                                         effective="now"), money=money)
    assert i.lines == ("〜 trail; +0.8R since the last ping",
                       "🔒 if it fills: +$279.47 · +1.1R total")


def test_a_short_stop_move_says_buy_stop_and_signs_a_loss():
    plan = _short_pending(status="ACTIVE", entry_price=97.5, working_stop=99.0)
    i = ins.instruction_for(plan, _event("stop_moved", old=101.6, new=99.0, r_moved=0.63,
                                         effective="now"), money=ins.money_from(30.6, "$"))
    assert i.headline == "🛑 MOVE BUY STOP → 99.00 now"
    # 30 sh × (99.00 − 97.50) against a short = −45.00; R −1.5/4.1 = −0.37
    assert i.lines == ("⚖ break-even; +0.6R since the last ping",
                       "🔒 if it fills: -$45.00 · −0.4R total")


def test_an_unpriced_projection_is_r_only():
    plan = _spec_long(status="PARTIAL", entry_price=182.4, legs_realized=[_tp1_leg()])
    usd, r_total = ins.stop_projection(plan, 186.0, ins.money_from(54.41, "$", priced=False))
    assert usd is None and r_total == pytest.approx(1.1196, abs=1e-4)


def test_cancellations_name_the_order_to_cancel():
    expired = ins.instruction_for(_long_pending(), _event("cancelled_expired", bars_waited=6))
    assert (expired.verb, expired.tone) == (ins.CANCEL, "inert")
    assert expired.headline == "⏳ CANCEL BUY STOP 102.50"
    assert expired.lines == ("not triggered within 5 sessions",)

    invalidated = ins.instruction_for(_short_pending(),
                                      _event("cancelled_invalidated", live_price=101.7))
    assert invalidated.headline == "⛔ CANCEL SELL STOP 97.50"
    assert invalidated.lines == ("price reached the stop 101.60 before triggering",)

    risk_capped = ins.instruction_for(_long_pending(), _event(
        "cancelled_risk_cap", entry_price=102.5, stop_loss=98.4,
        planned_loss_pct=4.0, max_planned_loss_pct=2.0))
    assert (risk_capped.verb, risk_capped.tone) == (ins.CANCEL, "inert")
    assert risk_capped.headline == "CANCEL BUY STOP 102.50"
    assert risk_capped.lines == (
        "triggered at 102.50 but risked 4.0% against stop 98.40 -- above the 2.0% cap; "
        "never filled",)
```

The close tests below that section (`test_a_regular_session_stop_out` onward) stay untouched: V170-4 changes no close wording.

- [ ] **Step 2: Write the failing tests for the wiring**

In `$WT/tests/scanning/test_execution_embeds.py`:

1. Directly below the imports (before the autouse fixture) add:

```python
_REAL_LINKED_TRADE = execution_embeds._linked_trade      # captured before the autouse patch
```

2. Replace the autouse fixture with:

```python
@pytest.fixture(autouse=True)
def _unsized(monkeypatch):
    monkeypatch.setattr(execution_embeds, "_sizing_snapshot", lambda entry, plan: None)
    monkeypatch.setattr(execution_embeds, "_linked_trade", lambda plan_id: None)
```

3. Append:

```python
def _tp1_event(plan):
    return PlanEvent(plan.plan_id, "tp1_partial", {
        "fraction": 0.5, "exit_price": 110.0, "r": 2.0, "working_stop": 106.67})


def test_lifecycle_money_comes_from_the_linked_record(monkeypatch):
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    monkeypatch.setattr(execution_embeds, "_linked_trade", lambda plan_id: {
        "plan_id": plan_id, "shares": 10.5, "realized_pnl_amount": None})
    monkeypatch.setattr(execution_embeds, "_sizing_snapshot",
                        lambda entry, plan: pytest.fail("re-sized at render time"))
    plan = make_plan_v2()          # entry 100, stop 95, TP1 110
    embed = execution_embeds.build_instruction_embed(plan, _tp1_event(plan))
    # 10 sh printed, 5 at TP1; realised = 10.5 × 0.5 × 10.00 = 52.50
    assert "**💰 TP1 FILLED 5 sh @ 110.00 · 🧾 +$52.50 · +2.0R**" in embed.description


def test_without_a_linked_record_shares_come_from_the_snapshot_and_no_dollars(monkeypatch):
    monkeypatch.setattr(execution_embeds, "_sizing_snapshot", lambda entry, plan: {"shares": 10.5})
    plan = make_plan_v2()
    embed = execution_embeds.build_instruction_embed(plan, _tp1_event(plan))
    assert "**💰 TP1 FILLED 5 sh @ 110.00 · 🧾 +2.0R**" in embed.description
    assert "$" not in embed.description


def test_event_money_carries_the_records_settled_amount(monkeypatch):
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    monkeypatch.setattr(execution_embeds, "_linked_trade", lambda plan_id: {
        "shares": 54.41, "realized_pnl_amount": 412.5})
    assert execution_embeds._event_money(make_plan_v2()) == Money(
        currency="$", shares=54, realized_amount=412.5, record_shares=54.41)


def test_a_record_without_shares_falls_back_to_the_unpriced_snapshot(monkeypatch):
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    monkeypatch.setattr(execution_embeds, "_linked_trade", lambda plan_id: {
        "shares": None, "realized_pnl_amount": None})
    monkeypatch.setattr(execution_embeds, "_sizing_snapshot", lambda entry, plan: {"shares": 7.9})
    assert execution_embeds._event_money(make_plan_v2()) == Money(currency="$", shares=7)


def test_linked_trade_never_raises(monkeypatch):
    from swingbot.core.tracking import performance

    class _Boom:
        def trade_for_plan(self, plan_id):
            raise RuntimeError("db down")

    monkeypatch.setattr(performance, "TradeLog", _Boom)
    assert _REAL_LINKED_TRADE("plan-1") is None
    assert _REAL_LINKED_TRADE("") is None


def test_be_moved_embed_projects_from_the_record(monkeypatch):
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    monkeypatch.setattr(execution_embeds, "_linked_trade", lambda plan_id: {
        "shares": 10.5, "realized_pnl_amount": None})
    plan = make_plan_v2()
    embed = execution_embeds.build_instruction_embed(
        plan, PlanEvent(plan.plan_id, "be_moved", {"working_stop": 100.0}))
    assert embed.description.splitlines() == [
        "**🛑 MOVE SELL STOP → 100.00 now**", "⚖ break-even", "🔒 if it fills: +$0.00 · 0.0R total"]
```

In `$WT/tests/scanning/test_compression_instructions.py`:

1. Line 22 becomes `from swingbot.core.presentation.instructions import instruction_for, money_from`.
2. The autouse `_setup` fixture (lines 32-35) gains a third line:

```python
    monkeypatch.setattr(execution_embeds, "_linked_trade", lambda plan_id: None)
```

3. Line 127 becomes:

```python
    text = _words(instruction_for(_short(), event, money=money_from(12.6, "$")))
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
python $WT/scripts/dev/testrun.py file tests/presentation/test_instructions.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_execution_embeds.py
```

Expected: FAIL — `TypeError: instruction_for() got an unexpected keyword argument 'money'` and `AttributeError: ... has no attribute '_linked_trade'` (at fixture setup).

- [ ] **Step 4: Implement in `instructions.py`**

In `$WT/swingbot/core/presentation/instructions.py`:

1. Delete `_whole_shares` (lines 78-83); nothing reads it after this task (`git grep -n _whole_shares` must come back empty at Step 6).

2. Directly after `_stop_kind` add the money and stop-move helpers:

```python
#: _stop_kind's word -> its FEED_SYMBOLS key.
_STOP_KIND_KEYS = {"break-even": "breakeven", "runner floor": "runner", "trail": "trail"}


def _leg_qty(money: Money | None, fraction: float) -> str:
    """Printed shares of one leg (floor of the printed position × fraction),
    or the fraction as a percentage when unsized."""
    whole = money.shares if money is not None else None
    return f"{math.floor(whole * fraction):,} sh" if whole is not None else f"{fraction:.0%}"


def _leg_dollars(plan, entry: float, leg: dict, money: Money) -> float:
    """A realised leg in record arithmetic (v170 A3): the paper record's own
    shares × fraction × (exit − entry), signed -- the figure the trade log
    banks, so it can differ from printed shares × move by under one share."""
    return (money.record_shares * leg["fraction"] * (leg["exit_price"] - entry)
            * _sign(plan.direction))


def _open_whole(money: Money, legs: list) -> int:
    """Printed shares still open: the printed position less each banked leg's printed count."""
    return max(0, money.shares - sum(math.floor(money.shares * leg["fraction"]) for leg in legs))


def stop_projection(plan, new_stop: float, money: Money | None) -> tuple[float | None, float]:
    """What the whole position totals if ``new_stop`` fills (v170 §2):
    ($ or None when unpriced, total R). Banked legs plus the open part
    stopped at ``new_stop``; the open part is printed shares × printed move,
    the banked legs are record arithmetic (the TP1 message's own figure).
    A projection -- a gap can fill worse -- and worded as one."""
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    legs = list(plan.legs_realized or [])
    open_fraction = max(0.0, 1.0 - sum(leg["fraction"] for leg in legs))
    r_total = (sum(leg["fraction"] * leg["r"] for leg in legs)
               + open_fraction * (_r_at(plan, entry, new_stop) or 0.0))
    r_total = round(r_total, 4) + 0.0           # float noise must not print '−0.0R'
    if not _priced(money):
        return None, r_total
    open_usd = (_open_whole(money, legs) * (_printed(new_stop) - _printed(entry))
                * _sign(plan.direction))
    return open_usd + sum(_leg_dollars(plan, entry, leg, money) for leg in legs), r_total


def _if_fills_line(plan, new_stop: float, money: Money | None) -> str:
    usd, r_total = stop_projection(plan, new_stop, money)
    figures = _join(_dollars(usd, money) if usd is not None else "", f"{signed_r(r_total)} total")
    return f"{_S['if_fills']} if it fills: {figures}"


def _move_stop_headline(side: dict, stop: float) -> str:
    """D2: a stop move names the broker order, MOVE SELL STOP / MOVE BUY STOP."""
    return f"{_S['stop']} MOVE {side['stop']} → {_price(stop)} now"
```

3. In `_time_exit`, change the signature to `def _time_exit(plan, event, side: dict, common: dict, money: Money | None) -> Instruction:` and replace its three sizing lines

```python
    whole = _whole_shares(sizing)
    fraction = detail.get("cover_fraction", 1.0)
    qty = f"{math.floor(whole * fraction):,} sh" if whole is not None else f"{fraction:.0%}"
```

with

```python
    qty = _leg_qty(money, detail.get("cover_fraction", 1.0))
```

4. Change `_closed_event` to:

```python
def _closed_event(plan, event, side: dict, common: dict, money: Money | None) -> Instruction:
    return _closed(plan, event.detail, side, common)
```

5. Replace everything from the `#: transitions whose instruction is a whole builder of its own.` comment to the end of the file (the old `_BUILDERS` and `instruction_for` with its inline cases) with:

```python
def _filled(plan, event, side: dict, common: dict, money: Money | None) -> Instruction:
    fill = _price(event.detail["entry_price"])
    return Instruction(
        verb=FILLED, headline=f"{_S['entry']} FILLED @ {fill} (bot)",
        lines=(f"Confirm your broker filled; the bot's R is measured from {fill}",
               f"Resting: {_S['stop']} {side['stop']} {_price(plan.stop_loss)} · "
               f"{_S['tp1']} {side['limit']} {_price(plan.tp1)}"),
        **common)


def _be_moved(plan, event, side: dict, common: dict, money: Money | None) -> Instruction:
    stop = event.detail["working_stop"]
    return Instruction(
        verb=MOVE_STOP, headline=_move_stop_headline(side, stop),
        lines=(f"{_S['breakeven']} break-even", _if_fills_line(plan, stop, money)),
        **common)


def _realised_leg(plan, leg: dict, money: Money | None) -> str:
    """A banked leg's dollars (record arithmetic), or '' when unpriced."""
    if not _priced(money) or plan.entry_price is None:
        return ""
    return _dollars(_leg_dollars(plan, plan.entry_price, leg, money), money)


def _tp1_partial(plan, event, side: dict, common: dict, money: Money | None) -> Instruction:
    detail = event.detail
    pnl = _join(_realised_leg(plan, detail, money), signed_r(detail["r"]))
    return Instruction(
        verb=MOVE_STOP,
        headline=(f"{_S['tp1']} TP1 FILLED {_leg_qty(money, detail['fraction'])} @ "
                  f"{_price(detail['exit_price'])} · {_S['pnl']} {pnl}"),
        lines=(f"{_S['stop']} MOVE {side['stop']} on the runner → "
               f"{_price(detail['working_stop'])} now (runner floor)",),
        tone="good", **common)


def _stop_moved(plan, event, side: dict, common: dict, money: Money | None) -> Instruction:
    new = event.detail["new"]
    kind = _stop_kind(plan, new)
    return Instruction(
        verb=MOVE_STOP, headline=_move_stop_headline(side, new),
        lines=(f"{_S[_STOP_KIND_KEYS[kind]]} {kind}; {signed_r(event.detail['r_moved'])} "
               "since the last ping",
               _if_fills_line(plan, new, money)),
        **common)


#: cancel transition -> its headline's FEED_SYMBOLS key ('' = no glyph, v170 Decision 4).
_CANCEL_LEADS = {"cancelled_expired": "expiry", "cancelled_invalidated": "invalid",
                 "cancelled_risk_cap": ""}


def _cancel_why(plan, transition: str, detail: dict) -> str:
    if detail.get("reason_message"):
        return detail["reason_message"]             # v144: an outlook plan states its reason
    if short_notice.is_compression(plan) and transition != "cancelled_invalidated":
        return short_notice.compression_cancel_why(plan, transition, detail)
    if transition == "cancelled_expired":
        return f"not triggered within {plan.expiry_bars} sessions"
    if transition == "cancelled_invalidated":
        return f"price reached the stop {_price(plan.stop_loss)} before triggering"
    return (f"triggered at {_price(detail['entry_price'])} but risked "
            f"{detail['planned_loss_pct']:.1f}% against stop "
            f"{_price(detail['stop_loss'])} -- above the "
            f"{detail['max_planned_loss_pct']:.1f}% cap; never filled")


def _cancelled(plan, event, side: dict, common: dict, money: Money | None) -> Instruction:
    key = _CANCEL_LEADS[event.transition]
    lead = f"{_S[key]} " if key else ""
    return Instruction(
        verb=CANCEL,
        headline=f"{lead}CANCEL {side['entry_stop']} {_price(plan.trigger_price)}",
        lines=(_cancel_why(plan, event.transition, event.detail),), tone="inert", **common)


#: Every feed transition's builder; each takes (plan, event, side, common, money).
_BUILDERS = {
    "filled": _filled,
    "be_moved": _be_moved,
    "tp1_partial": _tp1_partial,
    "stop_moved": _stop_moved,
    "cancelled_expired": _cancelled,
    "cancelled_invalidated": _cancelled,
    "cancelled_risk_cap": _cancelled,
    "time_exit_due": _time_exit,
    "time_exit_unresolved": _time_exit,
    "closed": _closed_event,
}


def instruction_for(plan, event, *, money: Money | None = None) -> Instruction:
    """The execution-feed instruction for one plan_manager PlanEvent (v81 D2,
    D3). Every live stop is read from ``event.detail``, which plan_manager
    stamps -- never recomputed here, so the feed cannot quote a stop the
    manager is not holding. v170: ``money`` (the linked paper record, or an
    unpriced snapshot) supplies share counts and dollars; every transition
    is one entry of _BUILDERS."""
    builder = _BUILDERS.get(event.transition)
    if builder is None:
        raise ValueError(f"no execution-feed instruction for {event.transition!r}")
    common = dict(ticker=plan.ticker, direction=plan.direction, plan_id=plan.plan_id)
    return builder(plan, event, _sides(plan.direction), common, money)
```

- [ ] **Step 5: Implement in `execution_embeds.py`**

In `$WT/swingbot/core/scanning/execution_embeds.py`:

1. Add `import logging` above `import discord`, and below the imports:

```python
log = logging.getLogger(__name__)
```

2. Above `build_instruction_embed` add:

```python
def _linked_trade(plan_id: str) -> dict | None:
    """The plan's paper-trade record in any status (TradeLog.trade_for_plan),
    or None. Never raises: a failed lookup renders the message without $.
    Imported here, not at module level, to keep scanning's import graph as
    it was."""
    if not plan_id:
        return None
    try:
        from swingbot.core.tracking.performance import TradeLog
        return TradeLog().trade_for_plan(plan_id)
    except Exception:
        log.warning("execution feed: trade lookup failed for plan %s", plan_id, exc_info=True)
        return None


def _event_money(plan) -> Money:
    """Lifecycle money from the plan's linked paper record (v170 §1): share
    counts and dollars from one record, so a trade opened at one balance is
    never re-sized against a later one. No linked record (or one without
    shares): today's sizing snapshot for the share counts, as before v170,
    and no dollar figure at all."""
    trade = _linked_trade(plan.plan_id)
    if trade and trade.get("shares"):
        return money_from(trade["shares"], config.CURRENCY_SYMBOL,
                          realized_amount=trade.get("realized_pnl_amount"))
    sizing = _sizing_snapshot(_entry(plan), plan) or {}
    return money_from(sizing.get("shares"), config.CURRENCY_SYMBOL, priced=False)
```

3. `build_instruction_embed`'s first line becomes:

```python
    instruction = instruction_for(plan, event, money=_event_money(plan))
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
python $WT/scripts/dev/testrun.py file tests/presentation/test_instructions.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_execution_embeds.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_compression_instructions.py
python $WT/scripts/dev/testrun.py file tests/planning/test_compression_time_exit.py
python $WT/scripts/dev/testrun.py file tests/presentation/test_surface_agreement.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_outlook_cancel_notices.py
git -C $WT grep -n "_whole_shares\|sizing=" -- swingbot/core/presentation/instructions.py
```

Expected: every run `0 failed`; the grep prints nothing. Then `python $WT/scripts/dev/testrun.py changed` — expected `0 failed` (it reaches `test_execution_feed_routing.py`, `test_loops_follow_notify.py`, `test_trade_monitor_task.py`, `test_posted_log.py`, `test_near_stop_event.py`, which assert titles and routing, not the changed body lines). A failure there that pins an old body string gets the new string.

- [ ] **Step 7: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/core/presentation/instructions.py $WT/swingbot/core/scanning/execution_embeds.py`
Expected: no output at all. `instruction_for` drops from C 13 to A; `_cancel_why` is about B 6; nothing touched reaches C.

- [ ] **Step 8: Commit**

```bash
git -C $WT add swingbot/core/presentation/instructions.py swingbot/core/scanning/execution_embeds.py tests/presentation/test_instructions.py tests/scanning/test_execution_embeds.py tests/scanning/test_compression_instructions.py
git -C $WT commit -m "feat(v170): lifecycle feed messages with symbols, stop verbs and money

instruction_for dispatches every transition through one builder table.
Stop moves say MOVE SELL STOP / MOVE BUY STOP and project 'if it fills'
dollars and R; TP1 prints its realised dollars from the paper record.
Lifecycle money comes from the plan's linked trade record; without one
the feed sizes from the snapshot as before and prints no dollars.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the main tree unchanged. Part 1 ends here; V170-5 (part 2) rewrites the close builder next.

