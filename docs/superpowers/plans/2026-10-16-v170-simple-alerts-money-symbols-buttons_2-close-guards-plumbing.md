# v170 Simple alerts, part 2: close messages, close-route and guard tests, `push_kwargs` view, `!pnl` single-trade extraction (V170-5..V170-9)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V170-6" -A 400 docs/superpowers/plans/2026-10-16-v170-simple-alerts-money-symbols-buttons_2-close-guards-plumbing.md`.

**Spec:** [`docs/superpowers/specs/2026-10-16-v170-simple-alerts-money-symbols-buttons-design.md`](../specs/2026-10-16-v170-simple-alerts-money-symbols-buttons-design.md)
**Index:** [`2026-10-16-v170-simple-alerts-money-symbols-buttons_0-index.md`](2026-10-16-v170-simple-alerts-money-symbols-buttons_0-index.md) — Global Constraints, the binding planning decisions, the close-route trace, Parallelisation and the Task ledger live there and bind every task below.
**Bump:** minor
**Edge:** none (integrity)

Paths: `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree), `$WT` = `$R/.claude/worktrees/2026-10-16-v170-simple-alerts-money-symbols-buttons` (the branch, created by V170-1 Step 0). Never `cd`; use absolute paths and `git -C $WT`. `python $WT/scripts/dev/testrun.py file tests/...` resolves test paths against `$WT`.

**Contracts this part consumes from part 1** (names fixed by the ledger; read them in `$WT` before starting, never redefine them):

- `tokens.FEED_SYMBOLS` (`entry ▶, stop 🛑, tp1 💰, runner 🏃, tp2 🎯, trail 〜, breakeven ⚖, expiry ⏳, invalid ⛔, if_fills 🔒, pnl 🧾, win ✅, loss ❌, flat ➖, at_or_above ≥, at_or_below ≤`), `tokens.fmt_money(amount, currency)`, `tokens.COST_BASIS = "(paper, gross)"` (V170-1).
- `TradeLog.trade_for_plan(plan_id) -> dict | None` (V170-2).
- `instructions.Money(currency, shares, realized_amount=None, record_shares=None)`, `instructions.money_from(shares, currency, *, realized_amount=None, priced=True)`, `instructions._S = tokens.FEED_SYMBOLS`, `ticket_for(plan, *, logged, not_logged_reason, money=None, warnings=(), level=None)` (V170-3).
- `instruction_for(plan, event, *, money=None)`; every transition builder takes `(plan, event, side, common, money)`; `execution_embeds._linked_trade(plan_id)` and `execution_embeds._event_money(plan)`, which builds `money_from(record["shares"], config.CURRENCY_SYMBOL, realized_amount=record.get("realized_pnl_amount"))` from the linked record or a no-$ `Money` when there is none (V170-4).

# Phase 3: close messages and their proofs

### Task V170-5: Close messages: outcome lead, exit glyph, `🧾` P&L line from the settled amount

**Model:** sonnet — a table-driven rewrite of one builder plus pinned-string tests; the money source is already wired by V170-4, nothing here touches persistence.

**Files:**
- Modify: `swingbot/core/presentation/instructions.py` (`_closed`, `_closed_event`; new `outcome_key`, `pnl_line`, `_EXIT_GLYPH_KEYS`, `_OUTCOME_TONES`, `_exit_word`, `_close_head`)
- Modify: `tests/presentation/test_instructions.py` (the three close tests and the progress-stall test; new close tests)
- Modify: `tests/scanning/test_execution_embeds.py` (two render tests through `_linked_trade`)

**Interfaces:**
- Consumes: `tokens.FEED_SYMBOLS`, `tokens.fmt_money`, `tokens.COST_BASIS` (V170-1); `instructions.Money`, `instructions._S` (V170-3); the builder signature `(plan, event, side, common, money)` and `execution_embeds._linked_trade` / `_event_money` (V170-4).
- Produces: `instructions.outcome_key(r: float) -> str` (`"win"` if `r > 0.05`, `"loss"` if `r < -0.05`, else `"flat"`); `instructions.pnl_line(r: float, money: Money | None) -> str` (`"🧾 <signed $> · <signed R> (paper, gross)"`, or `"🧾 <signed R> (paper, gross)"` when `money` is `None` or `money.realized_amount is None`). V170-6 and V170-7 read the rendered close through these.

The target shape (spec §2, index decision 4):

```
✅ EXITED @ 191.20 · 🎯 TP2
🧾 +$412.50 · +1.7R (paper, gross)
If your broker order did not fill: SELL AT MARKET
```

The extended-hours / progress-stall close keeps its verb and its market line, gains the outcome lead, and its old `−1.1R total` line becomes the `🧾` line:

```
❌ CLOSE AT MARKET now
BUY TO COVER AT MARKET: the bot exited on an extended-hours print @ 105.50; resting stop orders do not fire outside regular hours
🧾 −1.1R (paper, gross)
```

Rules, all from Global Constraints: the $ is the record's settled `realized_pnl_amount` only (A3), never recomputed here; `realized_amount is None` prints R only; R keeps U+2212 via `signed_r`, $ keeps ASCII `-` via `fmt_money`; every close P&L line ends `(paper, gross)`; no glyph literal in `instructions.py` (every glyph via `_S[...]`). R stays 1 dp (the spec example's `+1.65R` prints `+1.7R`/`+1.6R`).

- [ ] **Step 0: Confirm the V170-4 money source carries the settled amount**

Run: `git -C $WT grep -n "realized_amount\|realized_pnl_amount" swingbot/core/scanning/execution_embeds.py`
Expected: `_event_money` passes `realized_amount=<record>.get("realized_pnl_amount")` to `money_from`. If it does not, stop and report `BLOCKED: V170-4 _event_money does not pass realized_pnl_amount` to the controller (that is V170-4's contract; this task does not edit `execution_embeds.py`).

- [ ] **Step 1: Rewrite the close tests in `tests/presentation/test_instructions.py`**

Add the helper `_settled` directly under `_event` near the top of the file (it is used inside a `parametrize` list, so it must be defined at import time above its first use):

```python
def _settled(amount, *, shares=9, record_shares=9.9):
    """A close's money as V170-4 builds it from a linked, settled record."""
    return ins.Money(currency="$", shares=shares, realized_amount=amount,
                     record_shares=record_shares)
```

Replace `test_a_regular_session_stop_out`, `test_an_extended_hours_exit_says_close_at_market` and `test_a_trail_exit_warns_when_the_readers_stop_lagged` with:

```python
# --- closes (v170: outcome lead, exit glyph, settled $ beside R) -------------

def test_a_regular_session_stop_out():
    plan = _plan(status="CLOSED", entry_price=100.0, stop_loss=95.0, tp1=110.0)
    i = ins.instruction_for(plan, _event("closed", reason="loss", exit_price=94.5,
                                         session="regular", notified_stop=95.0,
                                         bot_stop=95.0), money=_settled(-49.5))
    assert (i.verb, i.tone) == (ins.EXITED, "bad")
    assert i.headline == "❌ EXITED @ 94.50 · 🛑 stop"
    assert i.lines == ("🧾 -$49.50 · −1.1R (paper, gross)",
                       "If your broker order did not fill: SELL AT MARKET")


def test_an_extended_hours_exit_says_close_at_market():
    plan = _plan(direction="bearish", status="CLOSED", entry_price=100.0,
                 stop_loss=105.0, tp1=90.0)
    i = ins.instruction_for(plan, _event("closed", reason="loss", exit_price=105.5,
                                         session="extended", notified_stop=105.0,
                                         bot_stop=105.0))
    assert (i.verb, i.tone) == (ins.CLOSE_AT_MARKET, "bad")
    assert i.headline == "❌ CLOSE AT MARKET now"
    assert i.lines == (
        "BUY TO COVER AT MARKET: the bot exited on an extended-hours print @ 105.50; "
        "resting stop orders do not fire outside regular hours",
        "🧾 −1.1R (paper, gross)",
    )


def test_a_trail_exit_warns_when_the_readers_stop_lagged():
    plan = _plan(status="CLOSED", entry_price=100.0, stop_loss=95.0, tp1=110.0,
                 working_stop=115.0,
                 legs_realized=[{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"},
                                {"fraction": 0.5, "exit_price": 115.0, "r": 3.0,
                                 "reason": "tp1_runner_trail"}])
    i = ins.instruction_for(plan, _event("closed", reason="tp1_runner_trail", exit_price=115.0,
                                         session="regular", notified_stop=113.9,
                                         bot_stop=115.0), money=_settled(250.0))
    assert (i.verb, i.tone) == (ins.EXITED, "good")
    assert i.headline == "✅ EXITED @ 115.00 · 〜 trail"
    assert i.lines == (
        "🧾 +$250.00 · +2.5R (paper, gross)",
        "If your broker order did not fill: SELL AT MARKET",
        "your last pinged stop was 113.90 — that order may still be open",
    )
```

Replace `test_progress_stall_close_says_close_at_market` with:

```python
def test_progress_stall_close_says_close_at_market():
    plan = _plan(status="CLOSED", entry_price=100.0, stop_loss=95.0, tp1=110.0,
                 working_stop=100.0,
                 legs_realized=[{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"},
                                {"fraction": 0.5, "exit_price": 112.0, "r": 2.4,
                                 "reason": "tp1_runner_progress_stall"}])
    i = ins.instruction_for(plan, _event("closed", reason="tp1_runner_progress_stall",
                                         exit_price=112.0, session="regular"))
    assert i.verb == ins.CLOSE_AT_MARKET
    assert i.headline.startswith("✅ CLOSE AT MARKET now — higher high failed")
    assert "no resting order covers this exit" in i.lines[0]
    assert i.lines[1] == "🧾 +2.2R (paper, gross)"
```

Append after it:

```python
def test_a_break_even_scratch_leads_flat_and_prints_zero_dollars_signed():
    plan = _plan(status="CLOSED", entry_price=100.0, stop_loss=95.0, tp1=110.0)
    i = ins.instruction_for(plan, _event("closed", reason="scratch", exit_price=100.0,
                                         session="regular"), money=_settled(0.0))
    assert (i.verb, i.tone) == (ins.EXITED, "neutral")
    assert i.headline == "➖ EXITED @ 100.00 · ⚖ break-even"
    assert i.lines[0] == "🧾 +$0.00 · 0.0R (paper, gross)"


def test_a_short_runner_tp2_win_flips_the_exit_verb():
    plan = _plan(direction="bearish", status="CLOSED", entry_price=100.0, stop_loss=105.0,
                 tp1=94.0, tp2=90.0,
                 legs_realized=[{"fraction": 0.5, "exit_price": 94.0, "r": 1.2, "reason": "tp1"},
                                {"fraction": 0.5, "exit_price": 90.0, "r": 2.0,
                                 "reason": "tp1_runner_tp2"}])
    i = ins.instruction_for(plan, _event("closed", reason="tp1_runner_tp2", exit_price=90.0,
                                         session="regular"),
                            money=_settled(80.0, shares=10, record_shares=10.0))
    assert (i.verb, i.tone) == (ins.EXITED, "good")
    assert i.headline == "✅ EXITED @ 90.00 · 🎯 TP2"
    assert i.lines == ("🧾 +$80.00 · +1.6R (paper, gross)",
                       "If your broker order did not fill: BUY TO COVER AT MARKET")


@pytest.mark.parametrize("money", [None, _settled(None)],
                         ids=["no linked record", "record not settled"])
def test_an_unsettled_close_prints_r_only_never_an_estimate(money):
    plan = _plan(status="CLOSED", entry_price=100.0, stop_loss=95.0, tp1=110.0)
    i = ins.instruction_for(plan, _event("closed", reason="loss", exit_price=94.5,
                                         session="regular"), money=money)
    assert i.lines[0] == "🧾 −1.1R (paper, gross)"
    assert not any("$" in text for text in (i.headline, *i.lines))


@pytest.mark.parametrize("reason,word", [
    ("loss", "🛑 stop"), ("scratch", "⚖ break-even"), ("win", "🎯 target"),
    ("tp1_runner_be", "🏃 runner floor"), ("tp1_runner_trail", "〜 trail"),
    ("tp1_runner_tp2", "🎯 TP2"), ("time_exit", "ten-session time exit"),
])
def test_every_exit_word_gets_its_glyph_where_the_table_has_one(reason, word):
    plan = _plan(status="CLOSED", entry_price=100.0, stop_loss=95.0, tp1=110.0)
    i = ins.instruction_for(plan, _event("closed", reason=reason, exit_price=104.0,
                                         session="regular"))
    assert i.headline == f"✅ EXITED @ 104.00 · {word}"


@pytest.mark.parametrize("r,key", [(0.06, "win"), (0.05, "flat"), (0.0, "flat"),
                                   (-0.05, "flat"), (-0.06, "loss")])
def test_outcome_key_uses_the_close_tone_bands(r, key):
    assert ins.outcome_key(r) == key


def test_pnl_line_signs_both_figures_and_states_the_cost_basis():
    assert ins.pnl_line(1.66, _settled(412.5)) == "🧾 +$412.50 · +1.7R (paper, gross)"
    assert ins.pnl_line(-1.0, _settled(-250.0)) == "🧾 -$250.00 · −1.0R (paper, gross)"
    assert ins.pnl_line(-1.0, _settled(None)) == "🧾 −1.0R (paper, gross)"
    assert ins.pnl_line(0.4, None) == "🧾 +0.4R (paper, gross)"
```

(`test_every_exit_word_gets_its_glyph_where_the_table_has_one`: a plan with no `legs_realized` takes the single-position R, (104 − 100) / 5 = +0.8R, so every row leads `✅`.)

- [ ] **Step 2: Add the render tests to `tests/scanning/test_execution_embeds.py`**

Add `from swingbot import config` to the imports, then append:

```python
def _closed_loss(plan):
    return PlanEvent(plan.plan_id, "closed",
                     {"reason": "loss", "exit_price": 95.0, "session": "regular"})


def test_a_close_prints_the_linked_records_settled_dollars(monkeypatch):
    monkeypatch.setattr(execution_embeds, "_linked_trade", lambda plan_id: {
        "plan_id": plan_id, "shares": 9.43, "realized_pnl_amount": -47.15,
        "status": "loss", "legs": []})
    plan = make_plan_v2()          # entry 100, stop 95
    embed = execution_embeds.build_instruction_embed(plan, _closed_loss(plan))
    money = tokens.fmt_money(-47.15, config.CURRENCY_SYMBOL)
    assert f"🧾 {money} · −1.0R (paper, gross)" in embed.description.splitlines()


def test_a_close_without_a_linked_record_prints_r_only(monkeypatch):
    monkeypatch.setattr(execution_embeds, "_linked_trade", lambda plan_id: None)
    plan = make_plan_v2()
    embed = execution_embeds.build_instruction_embed(plan, _closed_loss(plan))
    assert "🧾 −1.0R (paper, gross)" in embed.description.splitlines()
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/presentation/test_instructions.py`
Expected: FAIL — the close tests see the old `EXITED @ 94.50 — stop · −1.1R total` headline; `outcome_key` / `pnl_line` raise `AttributeError`.

Run: `python $WT/scripts/dev/testrun.py file tests/scanning/test_execution_embeds.py`
Expected: FAIL — the two new tests find no `🧾` line.

- [ ] **Step 4: Implement the close builder in `swingbot/core/presentation/instructions.py`**

Add below `_MARKET_EXIT_REASONS`:

```python
#: close reason -> the FEED_SYMBOLS key that leads its exit word in the close
#: headline (v170). Reasons with no key keep their bare word.
_EXIT_GLYPH_KEYS = {
    "loss": "stop",
    "scratch": "breakeven",
    "win": "tp2",
    "tp1_runner_be": "runner",
    "tp1_runner_trail": "trail",
    "tp1_runner_tp2": "tp2",
}

#: close outcome -> Instruction.tone (the bands the close always used).
_OUTCOME_TONES = {"win": "good", "loss": "bad", "flat": "neutral"}
```

Replace `_closed` and `_closed_event` (keep `_market_close_headline`, `_market_close_line` and `_staged_order_lines` exactly as they are) with:

```python
def outcome_key(r: float) -> str:
    """The FEED_SYMBOLS key that leads a close headline: the same ±0.05R
    bands the close's tone has always used."""
    if r > 0.05:
        return "win"
    if r < -0.05:
        return "loss"
    return "flat"


def pnl_line(r: float, money: Money | None) -> str:
    """A close's P&L line. The $ is the trade record's settled
    realized_pnl_amount -- the figure the account balance moved by -- and is
    printed only once the record is settled; otherwise R alone. Both are
    gross figures on the paper account (tokens.COST_BASIS)."""
    parts = [_S["pnl"]]
    if money is not None and money.realized_amount is not None:
        parts.append(f"{tokens.fmt_money(money.realized_amount, money.currency)} ·")
    return " ".join([*parts, signed_r(r), tokens.COST_BASIS])


def _exit_word(reason: str | None) -> str:
    word = _EXIT_WORDS.get(reason, reason or "closed")
    key = _EXIT_GLYPH_KEYS.get(reason)
    return f"{_S[key]} {word}" if key else word


def _close_head(detail: dict, side: dict, exit_price, lead: str,
                pnl: str) -> tuple[str, str, list[str]]:
    """(verb, headline, first lines) of a close: at market when no resting
    order covers the exit, else EXITED with the broker fallback line."""
    if detail.get("session") == "extended" or detail.get("reason") in _MARKET_EXIT_REASONS:
        return (CLOSE_AT_MARKET, f"{lead} {_market_close_headline(detail)}",
                [_market_close_line(side, exit_price, detail), pnl])
    headline = f"{lead} EXITED @ {_price(exit_price)} · {_exit_word(detail.get('reason'))}"
    return EXITED, headline, [pnl, f"If your broker order did not fill: {side['exit']}"]


def _closed(plan, detail: dict, side: dict, common: dict,
            money: Money | None = None) -> Instruction:
    exit_price = detail.get("exit_price")
    r = total_r(plan, exit_price)
    outcome = outcome_key(r)
    verb, headline, lines = _close_head(detail, side, exit_price, _S[outcome],
                                        pnl_line(r, money))
    told, held = detail.get("notified_stop"), detail.get("bot_stop")
    if told is not None and held is not None and not math.isclose(told, held, abs_tol=1e-6):
        lines.append(f"your last pinged stop was {_price(told)} — that order may still be open")
    lines.extend(_staged_order_lines(plan, detail, side))
    return Instruction(verb=verb, headline=headline, lines=tuple(lines),
                       tone=_OUTCOME_TONES[outcome], **common)
```

and the builder (its entry in `_BUILDERS` stays; only the body changes so the money reaches `_closed`):

```python
def _closed_event(plan, event, side: dict, common: dict, money: Money | None) -> Instruction:
    return _closed(plan, event.detail, side, common, money)
```

`Money` and `_S` are V170-3's names in this module; `from __future__ import annotations` keeps the `Money | None` annotations safe wherever `Money` sits in the file.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/presentation/test_instructions.py`
Expected: PASS, `0 failed`.

Run: `python $WT/scripts/dev/testrun.py file tests/scanning/test_execution_embeds.py`
Expected: PASS, `0 failed`.

Run the other files that render a close: `python $WT/scripts/dev/testrun.py file tests/scanning/test_compression_instructions.py`, then `python $WT/scripts/dev/testrun.py file tests/planning/test_compression_time_exit.py`
Expected: PASS (they assert `CANCEL or VERIFY` / staged-MOC text and ticker/direction, which this task keeps). If one pins an old close string, update that pin to the new shape and name the file in the commit message.

- [ ] **Step 6: Complexity and purity check**

Run: `python -m radon cc -s -n C $WT/swingbot/core/presentation/instructions.py`
Expected: no line for `_closed`, `_close_head`, `_exit_word`, `outcome_key`, `pnl_line`, `_closed_event` or `instruction_for`.

Run: `git -C $WT grep -n "import discord\|swingbot.core.scanning" swingbot/core/presentation/instructions.py`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git -C $WT add swingbot/core/presentation/instructions.py tests/presentation/test_instructions.py tests/scanning/test_execution_embeds.py
git -C $WT commit -m "feat(feed): close messages lead with the outcome, glyph the exit word, print the settled dollars beside R (v170)"
```

Then `git -C $R status --short` must show the main tree unchanged.

### Task V170-6: Close-route tests: every emitting route renders the record's settled $

**Model:** opus — an integration test across plan_manager, the trade log's settle path and the feed renderer on the test DB; clock and fill-continuity traps decide whether the pinned figures are deterministic.

**Files:**
- Create: `tests/scanning/test_feed_close_routes.py`

**Interfaces:**
- Consumes: `TradeLog.trade_for_plan` (V170-2); `execution_embeds.build_instruction_embed` with V170-4's `_linked_trade` / `_event_money` reading the real trade log; the close rendering of V170-5 (`🧾 <$> · <R> (paper, gross)`, R only when unsettled); `tokens.FEED_SYMBOLS`, `tokens.fmt_money`, `tokens.COST_BASIS` (V170-1). Existing: `PlanManager(store, price_fn, *, trade_log=, atr_fn=, auction_close_fn=)`, `PlanManager._on_event`, `performance.settle_legs`, `performance.account_module`, `tests.planning.test_plan_manager_pending._pending`, `tests.planning.test_compression_time_exit._short/_auction/_at/STD_TENTH`, `tests.fake_feed.FakePriceFeed`, `tests.store_seed.seed_store`.
- Produces: nothing consumed later (test-only).

This task writes no production code. It is the spec's §1 / A2 proof: on every route that emits a feed `closed` event, the trade is settled before the event renders, and the rendered close carries exactly the record's `realized_pnl_amount`. If any test here fails because the render lacks the record's figure, the defect is in V170-4/V170-5 wiring (or a settle-order bug): fix it there in a separate commit and name it; never weaken an assertion here.

**Why every poll passes `now=SATURDAY`:** `PlanManager.poll` records `_last_seen` only while `is_tape_open(now)`; with a live tape a stop breach fills **at the stop** (`poll_stop_fill`), with none it fills at the observed print. A wall-clock run therefore gives −2.0/share at 11:00 ET on a weekday and −3.0/share on a weekend for the same pre-TP1 stop (verified on the test DB while planning). A fixed Saturday clock makes every figure below deterministic. The trail route needs `atr_fn` (`_ratchet_chandelier` is a no-op without it); with ATR 4.0 and `trail_atr_mult` 2.5 the trail after the 140 print is 130, and the 118 print exits it. A notice event is re-sent until acked, so a run can carry the same `closed` twice: the tests take the first.

Figures reproduced on the test DB while planning (account 10,000, risk 1 %, max position 20 %, placeholder at 105, fill 106, record `shares` 9.43; time exit `shares` 10.0):

| route | prices | reason | per share | `realized_pnl_amount` |
|---|---|---|---|---|
| pre-TP1 stop | 106, 103 | `loss` | −3.00 | −28.29 |
| break-even scratch | 106, 108.5, 105 | `scratch` | −1.00 | −9.43 |
| runner trail (`tp2=None`, ATR 4) | 106, 116, 140, 118 | `tp1_runner_trail` | +11.00 | 103.73 |
| runner TP2 (`tp2=120`) | 106, 111, 121 | `tp1_runner_tp2` | +10.00 | 94.30 |
| runner floor (`tp2=120`) | 106, 111, 106.5, 105 | `tp1_runner_be` | +2.75 | 25.93 |
| time exit (compression short, auction 98) | — | `time_exit` | +2.00 | 20.00 |
| `_on_event` fallback (loss @ 103) | 106 | `loss` | −3.00 | −28.29 |

The tests pin the per-share figure against the record's own `shares` (so they do not depend on the sizing rule) and assert `realized_pnl_amount == settle_legs(record)`.

- [ ] **Step 0: Bring up the test database**

Run: `docker compose -f $R/docker-compose.yml --profile test up -d db-test` then `docker ps --format "{{.Names}} {{.Ports}}"`
Expected: a `swing-db-test` row. If its published port is not `55432`, export `TEST_DATABASE_URL=postgresql+psycopg://swingbot:swingbot@127.0.0.1:<port>/swingbot_test` for every `testrun.py` call in this task. A run that reports skips for this file is not green.

- [ ] **Step 1: Write the test file**

Create `tests/scanning/test_feed_close_routes.py`:

```python
"""v170 close routes: every route that emits a feed ``closed`` event renders
the trade record's settled realized_pnl_amount (spec §1 / A2).

Only plan_manager closes emit a feed close, and each settles the linked trade
(close_plan_trade -> TradeLog._settle_account_balance) before the event
exists. One test per emitting route, the _on_event fallback, and every
unsettled case, which must print R only. Reversal (close_trade_reversed),
manual close, backfill_exit_price, update_open_trades,
close_if_live_price_hit and check_near_tp_timeout settle but never emit a
feed message (the last three skip plan-linked trades), so they get no render
test here.

Every poll runs on a Saturday clock: with no live tape a stop breach fills at
the observed print (plan_manager._continuous stays off), so each route's
per-share P&L is fixed.
"""
import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from swingbot import config
from swingbot.core.market.strategy_types import COMPRESSION_SHORT
from swingbot.core.planning.plan_manager import PlanEvent, PlanManager
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.presentation import tokens
from swingbot.core.scanning import execution_embeds
from swingbot.core.tracking import performance
from swingbot.core.tracking.performance import TradeLog, settle_legs
from tests.fake_feed import FakePriceFeed
from tests.planning.test_compression_time_exit import STD_TENTH, _at, _auction, _short
from tests.planning.test_plan_manager_pending import _pending
from tests.store_seed import seed_store

SATURDAY = dt.datetime(2026, 10, 17, 12, 0, tzinfo=ZoneInfo("America/New_York"))
PNL = tokens.FEED_SYMBOLS["pnl"]


def _seed(tmp_path, monkeypatch, balance: float) -> TradeLog:
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
    seed_store("account", {"balance": balance, "risk_pct": 1.0, "max_position_pct": 20.0,
                           "sizing_mode": "risk_pct", "balance_history": []})
    return TradeLog()


@pytest.fixture
def trade_log(tmp_path, monkeypatch):
    return _seed(tmp_path, monkeypatch, balance=10000.0)


def _placeholder(trade_log: TradeLog) -> None:
    """scan_run's scan-time placeholder for the stop-entry plan, sized at the trigger."""
    trade_log.log_trade(
        ticker="AAPL", strategy="Fibonacci", horizon_key="4w", direction="bullish",
        confidence_level=None, confidence_label=None, entry=105.0, stop_loss=104.0,
        take_profit=110.0, plan_id="p1")


def _run(trade_log, prices, *, atr_fn=None, **plan_kw):
    """Fill the stop-entry plan at 106 and walk it through ``prices``, one poll
    per print. Returns the store and the first closed event."""
    feed = FakePriceFeed([("AAPL", p) for p in prices])
    store = PlanStore()
    store.add(_pending(stop_loss=104.0, **plan_kw))
    mgr = PlanManager(store, feed.get_price, trade_log=trade_log, atr_fn=atr_fn)
    events = []
    for _ in prices:
        events += mgr.poll(now=SATURDAY)
    closed = [e for e in events if e.transition == "closed"]
    assert closed, [e.transition for e in events]
    return store, closed[0]


def _pnl_lines(store, event) -> list[str]:
    embed = execution_embeds.build_instruction_embed(store.get("p1"), event)
    return [line for line in embed.description.splitlines() if line.startswith(PNL)]


def _assert_renders_settled(store, event, record) -> None:
    amount = record["realized_pnl_amount"]
    assert amount is not None, record
    lines = _pnl_lines(store, event)
    money = tokens.fmt_money(amount, config.CURRENCY_SYMBOL)
    assert len(lines) == 1, lines
    assert lines[0].startswith(f"{PNL} {money} · ")
    assert lines[0].endswith(tokens.COST_BASIS)


ROUTES = [
    # id, prices, plan overrides, ATR(14) for the chandelier, close reason, P&L per record share
    ("pre-TP1 stop", [106, 103], {}, None, "loss", -3.0),
    ("break-even scratch", [106, 108.5, 105], {}, None, "scratch", -1.0),
    ("runner trail", [106, 116, 140, 118], {"tp2": None}, 4.0, "tp1_runner_trail", 11.0),
    ("runner TP2", [106, 111, 121], {"tp2": 120.0}, None, "tp1_runner_tp2", 10.0),
    ("runner floor", [106, 111, 106.5, 105], {"tp2": 120.0}, None, "tp1_runner_be", 2.75),
]


@pytest.mark.parametrize("prices,plan_kw,atr,reason,per_share",
                         [route[1:] for route in ROUTES], ids=[route[0] for route in ROUTES])
def test_every_persist_terminal_route_renders_the_records_settled_dollars(
        trade_log, prices, plan_kw, atr, reason, per_share):
    _placeholder(trade_log)
    atr_fn = (lambda ticker: atr) if atr is not None else None
    store, event = _run(trade_log, prices, atr_fn=atr_fn, **plan_kw)
    assert event.detail["reason"] == reason
    record = trade_log.trade_for_plan("p1")
    assert record["realized_pnl_amount"] == settle_legs(record)
    assert record["realized_pnl_amount"] == pytest.approx(
        round(record["shares"] * per_share, 2), abs=0.01)
    _assert_renders_settled(store, event, record)


def test_the_time_exit_route_renders_the_records_settled_dollars(trade_log):
    trade_log.log_trade(
        ticker="AAPL", strategy=COMPRESSION_SHORT, horizon_key="2w", direction="bearish",
        confidence_level=None, confidence_label=None, entry=100.0, stop_loss=101.0,
        take_profit=95.0, plan_id="p1")
    store = PlanStore()
    store.add(_short())
    mgr = PlanManager(store, FakePriceFeed([("AAPL", 99.5)]).get_price,
                      auction_close_fn=_auction(98.0), trade_log=trade_log)
    mgr.poll(now=_at(STD_TENTH, 15, 40))
    closed = [e for e in mgr.poll(now=_at(STD_TENTH, 16, 0, 20)) if e.transition == "closed"]
    assert [e.detail["reason"] for e in closed] == ["time_exit"]
    record = trade_log.trade_for_plan("p1")
    assert record["realized_pnl_amount"] == pytest.approx(
        round(record["shares"] * 2.0, 2), abs=0.01)           # short 100 -> 98
    _assert_renders_settled(store, closed[0], record)


def test_the_on_event_fallback_settles_before_the_close_renders(trade_log):
    """_terminal_persisted False: _on_event closes the trade itself
    (close_plan_trade with a synthesized fraction=1.0 leg) before notify."""
    _placeholder(trade_log)
    store = PlanStore()
    store.add(_pending(stop_loss=104.0))
    mgr = PlanManager(store, FakePriceFeed([("AAPL", 106.0)]).get_price, trade_log=trade_log)
    mgr.poll(now=SATURDAY)                                      # filled at 106
    event = PlanEvent("p1", "closed", {"reason": "loss", "exit_price": 103.0,
                                       "session": "regular", "_terminal_persisted": False})
    mgr._on_event(store.get("p1"), event)
    record = trade_log.trade_for_plan("p1")
    assert record["status"] == "loss"
    assert record["realized_pnl_amount"] == pytest.approx(
        round(record["shares"] * -3.0, 2), abs=0.01)
    money = tokens.fmt_money(record["realized_pnl_amount"], config.CURRENCY_SYMBOL)
    assert _pnl_lines(store, event) == [f"{PNL} {money} · −1.5R {tokens.COST_BASIS}"]


# --- unsettled closes: R only, never an estimate -----------------------------

R_ONLY = f"{PNL} −1.5R {tokens.COST_BASIS}"          # fill 106, stop 104, exit 103


def test_a_trade_with_no_share_snapshot_closes_with_r_only(tmp_path, monkeypatch):
    """Balance 0 at open: the record never gets shares, so
    _settle_account_balance (and settle_legs) settle nothing."""
    trade_log = _seed(tmp_path, monkeypatch, balance=0.0)
    _placeholder(trade_log)
    store, event = _run(trade_log, [106, 103])
    record = trade_log.trade_for_plan("p1")
    assert not record["shares"]
    assert record["realized_pnl_amount"] is None
    assert _pnl_lines(store, event) == [R_ONLY]


def test_a_failed_balance_update_closes_with_r_only(trade_log, monkeypatch):
    def refuse(*_args, **_kwargs):
        raise RuntimeError("account store down")

    monkeypatch.setattr(performance.account_module, "apply_realized_pnl", refuse)
    _placeholder(trade_log)
    store, event = _run(trade_log, [106, 103])
    record = trade_log.trade_for_plan("p1")
    assert record["status"] == "loss" and record["shares"]
    assert record["realized_pnl_amount"] is None
    assert _pnl_lines(store, event) == [R_ONLY]


def test_a_plan_with_no_linked_trade_closes_with_r_only(tmp_path, monkeypatch):
    """A plan the bot never logged (no trade log wired): no record, no $ at all."""
    _seed(tmp_path, monkeypatch, balance=10000.0)
    store = PlanStore()
    store.add(_pending(stop_loss=104.0))
    feed = FakePriceFeed([("AAPL", p) for p in (106, 103)])
    mgr = PlanManager(store, feed.get_price)
    events = [e for _ in range(2) for e in mgr.poll(now=SATURDAY)]
    closed = [e for e in events if e.transition == "closed"]
    assert TradeLog().trade_for_plan("p1") is None
    assert _pnl_lines(store, closed[0]) == [R_ONLY]
```

- [ ] **Step 2: Run the file**

Run: `python $WT/scripts/dev/testrun.py file tests/scanning/test_feed_close_routes.py`
Expected: PASS, `0 failed`, **no skips** (V170-2..V170-5 already ship everything it exercises; this task adds proofs, not behaviour). A skip means the test DB is unreachable — fix Step 0, do not accept it.

If a route's per-share figure differs from the table, first check the clock (every `poll` must get `now=SATURDAY`) and, for the trail, `atr_fn`; then re-derive the figure by hand from `record["legs"]` and `record["entry"]` and report the difference to the controller before changing the pin. The render assertions are the requirement and never change.

- [ ] **Step 3: Guard the test against a vacuous pass**

Temporarily change `pnl_line` in `$WT/swingbot/core/presentation/instructions.py` to drop the $ part (replace its `if money is not None and money.realized_amount is not None:` with `if False:`), re-run the file, and confirm the five route tests, the time-exit test and the fallback test FAIL while the three R-only tests still pass. Revert the change (`git -C $WT diff --stat` shows only the new test file afterwards).

- [ ] **Step 4: Commit**

```bash
git -C $WT add tests/scanning/test_feed_close_routes.py
git -C $WT commit -m "test(feed): every emitting close route renders the record's settled dollars; unsettled closes print R only (v170)"
```

Then `git -C $R status --short` must show the main tree unchanged.

### Task V170-7: Guard tests: every glyph used, no glyph literal in `instructions.py`, broker verb on every order line

**Model:** sonnet — one new test module over pure builders; the order-line rule needs care so it is neither vacuous nor brittle against part 1's exact wording.

**Files:**
- Create: `tests/presentation/test_feed_guards.py`

**Interfaces:**
- Consumes: `tokens.FEED_SYMBOLS` (V170-1); `instructions.money_from`, `ticket_for(..., money=)` (V170-3); `instruction_for(..., money=)` (V170-4); the close shape (V170-5). Existing: `tests.planning.test_plan_engine_model._plan`, `tests.planning.test_compression_time_exit._short`, `PlanEvent`.
- Produces: `tests.presentation.test_feed_guards.rendered_feed() -> list[tuple[str, Instruction]]` — `(direction, instruction)` for every feed message kind in both directions (time-exit kinds: short only, the only strategy that has them). Nothing else imports it.

This is D2 and the symbol-table rules enforced (spec § Testing "Symbol-table tests", "Broker-verb guard test"). No production code changes: a failure here is a defect in V170-3/4/5 output, fixed there in a separate, named commit — never by loosening a rule below.

**The order-line rule.** A glyph from the order keys (`entry ▶`, `stop 🛑`, `tp1 💰`, `tp2 🎯`, `expiry ⏳`, `invalid ⛔`) leads either an order the reader places — and then the text right after it starts with that direction's broker verb — or, for exactly two reports, a fill that already happened (`▶ FILLED`, `💰 TP1 FILLED`). The rule runs over the headline and every line of every non-close message; close headlines are excluded because their exit word carries a glyph by design (`❌ EXITED @ 94.50 · 🛑 stop`), and their order line is checked separately (the exit verb).

- [ ] **Step 1: Write the test file**

Create `tests/presentation/test_feed_guards.py`:

```python
"""v170 guards over every execution-feed message kind (spec § Testing).

* every FEED_SYMBOLS key is used by at least one rendered message, and no
  glyph is shared by two keys;
* instructions.py writes no glyph literal (every glyph comes from the table);
* D2: every order line carries its broker verb for its direction, every
  cancel says CANCEL, every stop move says MOVE <stop verb>, and no message
  carries the other direction's verbs;
* the comparison glyphs follow the direction.
"""
from pathlib import Path

import pytest

from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.presentation import instructions as ins
from swingbot.core.presentation import tokens
from swingbot.core.presentation.instructions import Instruction
from tests.planning.test_compression_time_exit import _short
from tests.planning.test_plan_engine_model import _plan

S = tokens.FEED_SYMBOLS
DIRECTIONS = ("bullish", "bearish")

_LEVELS = {
    "bullish": dict(trigger_price=102.5, stop_loss=98.4, tp1=106.0, tp2=110.0),
    "bearish": dict(trigger_price=97.5, stop_loss=101.6, tp1=94.0, tp2=90.0),
}

_VERBS = {
    "bullish": dict(entry=("BUY STOP", "BUY AT MARKET"), stop="SELL STOP",
                    limit="SELL LIMIT", exit="SELL AT MARKET"),
    "bearish": dict(entry=("SELL STOP", "SELL SHORT AT MARKET"), stop="BUY STOP",
                    limit="BUY LIMIT", exit="BUY TO COVER AT MARKET"),
}

#: verbs that belong only to the other direction.
_FORBIDDEN = {
    "bullish": ("BUY LIMIT", "BUY TO COVER", "SELL SHORT", "MOVE BUY STOP"),
    "bearish": ("SELL LIMIT", "SELL AT MARKET", "BUY AT MARKET", "MOVE SELL STOP"),
}

_ORDER_KEYS = ("entry", "stop", "tp1", "tp2", "expiry", "invalid")
_CLOSE_VERBS = (ins.EXITED, ins.CLOSE_AT_MARKET)


def _allowed(direction: str) -> dict[str, tuple[str, ...]]:
    """What may follow each order glyph: the direction's order verb, or one
    of the two fill reports."""
    v = _VERBS[direction]
    return {"entry": (*v["entry"], "FILLED"),
            "stop": (v["stop"], f"MOVE {v['stop']}"),
            "tp1": (v["limit"], "TP1 FILLED"),
            "tp2": (v["limit"],),
            "expiry": ("CANCEL",),
            "invalid": ("CANCEL",)}


def _ev(transition, **detail):
    return PlanEvent("p1", transition, detail)


def _pending(direction, **kw):
    base = dict(entry_type="stop_entry", direction=direction, entry_price=None,
                tp1_fraction=0.5, trail_atr_mult=3.0, breakeven_trigger_fraction=0.5,
                created_at="2026-09-10", expiry_bars=5, status="PENDING",
                **_LEVELS[direction])
    base.update(kw)
    return _plan(**base)


def _held(direction, status="ACTIVE", **kw):
    return _pending(direction, entry_price=_LEVELS[direction]["trigger_price"],
                    status=status, **kw)


def _legs(direction):
    lv = _LEVELS[direction]
    return [{"fraction": 0.5, "exit_price": lv["tp1"], "r": 0.85, "reason": "tp1"},
            {"fraction": 0.5, "exit_price": lv["tp2"], "r": 1.83, "reason": "tp1_runner_tp2"}]


def _tickets(direction):
    money = ins.money_from(54.35, "$")
    kw = dict(logged=True, not_logged_reason=None, money=money, level=4)
    return [ins.ticket_for(_pending(direction), **kw),
            ins.ticket_for(_pending(direction, entry_type="market"), **kw),
            ins.ticket_for(_pending(direction, tp2=None), **kw),
            ins.ticket_for(_pending(direction), logged=False,
                           not_logged_reason="kill switch on", money=money)]


def _lifecycle(direction):
    lv = _LEVELS[direction]
    entry, live = lv["trigger_price"], ins.money_from(54.35, "$")
    partial = _held(direction, status="PARTIAL", legs_realized=_legs(direction)[:1])
    events = [
        (_held(direction), _ev("filled", entry_price=entry)),
        (_held(direction), _ev("be_moved", working_stop=entry)),
        (partial, _ev("tp1_partial", fraction=0.5, exit_price=lv["tp1"], r=0.85,
                      reason="tp1", working_stop=entry)),
        (partial, _ev("stop_moved", new=(entry + lv["tp1"]) / 2, r_moved=0.4)),
        (_pending(direction), _ev("cancelled_expired")),
        (_pending(direction), _ev("cancelled_invalidated")),
        (_pending(direction), _ev("cancelled_risk_cap", entry_price=entry,
                                  stop_loss=lv["stop_loss"], planned_loss_pct=4.0,
                                  max_planned_loss_pct=2.0)),
    ]
    return [ins.instruction_for(plan, event, money=live) for plan, event in events]


def _closes(direction):
    lv = _LEVELS[direction]
    entry = lv["trigger_price"]

    def settled(amount):
        return ins.money_from(54.35, "$", realized_amount=amount)

    closes = [
        (_held(direction, status="CLOSED", legs_realized=_legs(direction)),
         _ev("closed", reason="tp1_runner_tp2", exit_price=lv["tp2"], session="regular"),
         settled(300.0)),
        (_held(direction, status="CLOSED"),
         _ev("closed", reason="loss", exit_price=lv["stop_loss"], session="regular"),
         settled(-222.0)),
        (_held(direction, status="CLOSED"),
         _ev("closed", reason="scratch", exit_price=entry, session="regular"),
         settled(0.0)),
        (_held(direction, status="CLOSED"),
         _ev("closed", reason="loss", exit_price=lv["stop_loss"], session="extended"),
         None),
    ]
    return [ins.instruction_for(plan, event, money=money) for plan, event, money in closes]


def _time_exits():
    """The compression short is the only strategy with a time exit."""
    money = ins.money_from(12.6, "$")
    due = {"cover_fraction": 1.0, "auction_time": "2026-12-01T16:00:00-05:00",
           "late": False, "notice_id": "p1:time_exit_due:2026-12-01"}
    unresolved = {"cover_fraction": 1.0, "reason": "official closing-auction price unavailable",
                  "notice_id": "p1:time_exit_unresolved:2026-12-01"}
    closed = _short(status="CLOSED", time_exit_due_date="2026-12-01")
    return [ins.instruction_for(_short(), _ev("time_exit_due", **due), money=money),
            ins.instruction_for(_short(), _ev("time_exit_unresolved", **unresolved), money=money),
            ins.instruction_for(closed, _ev("closed", reason="time_exit", exit_price=98.0,
                                            session="regular"),
                                money=ins.money_from(12.6, "$", realized_amount=25.2))]


def rendered_feed() -> list[tuple[str, Instruction]]:
    """(direction, instruction) for every execution-feed message kind."""
    feed = [(d, i) for d in DIRECTIONS
            for i in (*_tickets(d), *_lifecycle(d), *_closes(d))]
    return feed + [("bearish", i) for i in _time_exits()]


def _texts(instruction: Instruction) -> tuple[str, ...]:
    return (instruction.headline, *instruction.lines)


def _order_glyph_hits(instruction: Instruction) -> list[tuple[str, str]]:
    """(key, text right after the glyph) for every order glyph in the message."""
    return [(key, after.lstrip())
            for text in _texts(instruction)
            for key in _ORDER_KEYS
            for after in text.split(S[key])[1:]]


FEED = rendered_feed()
#: every message but the closes, whose headline glyphs the exit word by design
#: (their order line, the exit verb, is checked separately).
ORDERED = [(d, i) for d, i in FEED if i.verb not in _CLOSE_VERBS]


# --- the symbol table ---------------------------------------------------------

def test_every_symbol_key_is_used_by_a_rendered_message():
    text = "\n".join(t for _d, i in FEED for t in _texts(i))
    unused = [key for key, glyph in S.items() if glyph not in text]
    assert unused == []


def test_no_glyph_is_shared_by_two_keys():
    assert len(set(S.values())) == len(S)


def test_instructions_py_writes_no_glyph_literal():
    source = Path(ins.__file__).read_text(encoding="utf-8")
    assert [key for key, glyph in S.items() if glyph in source] == []


# --- D2: broker verbs ----------------------------------------------------------

def test_rendered_feed_covers_every_message_kind_in_both_directions():
    for direction in DIRECTIONS:
        verbs = {i.verb for d, i in FEED if d == direction}
        assert verbs >= {ins.PLACE, ins.DO_NOT_PLACE, ins.FILLED, ins.MOVE_STOP,
                         ins.CANCEL, ins.EXITED, ins.CLOSE_AT_MARKET}, direction


@pytest.mark.parametrize("index", range(len(ORDERED)))
def test_every_order_glyph_leads_its_directions_broker_verb(index):
    direction, instruction = ORDERED[index]
    allowed = _allowed(direction)
    for key, after in _order_glyph_hits(instruction):
        assert after.startswith(allowed[key]), (key, after, instruction)


def test_every_place_ticket_quotes_entry_stop_and_target_orders():
    for direction, instruction in FEED:
        if instruction.verb != ins.PLACE:
            continue
        keys = [key for key, _after in _order_glyph_hits(instruction)]
        assert {"entry", "stop", "tp1"} <= set(keys), (direction, instruction)
        assert instruction.headline.startswith(f"{S['entry']} "), instruction.headline
    for direction in DIRECTIONS:
        runner = f"{S['tp2']} {_VERBS[direction]['limit']} "
        assert any(runner in t for d, i in FEED if d == direction and i.verb == ins.PLACE
                   for t in _texts(i)), direction


def test_every_stop_move_names_the_move_verb():
    for direction, instruction in FEED:
        if instruction.verb == ins.MOVE_STOP:
            move = f"MOVE {_VERBS[direction]['stop']}"
            assert any(move in t for t in _texts(instruction)), instruction


def test_every_cancel_says_cancel_and_names_the_entry_order():
    for direction, instruction in FEED:
        if instruction.verb == ins.CANCEL:
            assert f"CANCEL {_VERBS[direction]['entry'][0]}" in instruction.headline, instruction


def test_every_close_and_time_exit_names_the_exit_verb():
    for direction, instruction in FEED:
        if instruction.verb in _CLOSE_VERBS:
            exit_verb = _VERBS[direction]["exit"]
            assert any(exit_verb in t for t in _texts(instruction)), instruction


def test_no_message_carries_the_other_directions_verbs():
    for direction, instruction in FEED:
        text = "\n".join(_texts(instruction))
        assert [v for v in _FORBIDDEN[direction] if v in text] == [], instruction


# --- comparison glyphs ----------------------------------------------------------

@pytest.mark.parametrize("direction,arm,cancel", [
    ("bullish", "at_or_above", "at_or_below"),
    ("bearish", "at_or_below", "at_or_above"),
])
def test_comparison_glyphs_follow_the_direction(direction, arm, cancel):
    ticket = _tickets(direction)[0]                 # the stop-entry ticket
    breakeven = [t for t in ticket.lines if t.startswith(S["breakeven"])]
    assert len(breakeven) == 1 and S[arm] in breakeven[0] and S[cancel] not in breakeven[0]
    after_invalid = [after for key, after in _order_glyph_hits(ticket) if key == "invalid"]
    assert after_invalid and after_invalid[0].startswith(f"CANCEL if {S[cancel]} ")
```

- [ ] **Step 2: Run the file**

Run: `python $WT/scripts/dev/testrun.py file tests/presentation/test_feed_guards.py`
Expected: PASS, `0 failed`, no skips.

If a rule fails, read the failing instruction in the assertion message and decide which side is wrong: a missing verb or a stray glyph is a V170-3/4/5 defect (fix the builder in `swingbot/core/presentation/instructions.py`, re-run that task's test file, commit separately as `fix(feed): ...`); a fixture that does not match how plan_manager stamps an event's detail is a defect here (fix the fixture). Do not widen `_allowed`.

- [ ] **Step 3: Prove the guards bite**

Temporarily replace one `_S["stop"]` use in `$WT/swingbot/core/presentation/instructions.py` with the literal `🛑`, re-run the file: `test_instructions_py_writes_no_glyph_literal` must FAIL. Revert. Then temporarily change the long `"stop": "SELL STOP"` entry in `_sides` to `"stop": "STOP"`, re-run: the order-glyph and stop-move tests must FAIL. Revert; `git -C $WT diff --stat` shows only the new test file.

- [ ] **Step 4: Commit**

```bash
git -C $WT add tests/presentation/test_feed_guards.py
git -C $WT commit -m "test(feed): every glyph used once, no glyph literal in instructions.py, broker verb on every order line (v170)"
```

Then `git -C $R status --short` must show the main tree unchanged.

# Phase 4: plumbing for the buttons

### Task V170-8: `push_kwargs(embed, view=None)`

**Model:** haiku — a two-line additive change to one helper with its pinned test; no judgement beyond keeping the no-view output identical.

**Files:**
- Modify: `swingbot/core/presentation/components.py:132-135` (`push_kwargs`)
- Modify: `tests/presentation/test_components.py` (the `push_kwargs` tests near line 133)

**Interfaces:**
- Consumes: nothing from this plan.
- Produces: `components.push_kwargs(embed, view=None) -> dict` — the same dict as today when `view` is `None`; with a view, the same dict plus `"view": view` as the last key. `ui.push_kwargs` (the `swingbot.core.presentation` re-export) stays the same object. V170-12 calls `ui.push_kwargs(embed, view=...)`.

Global Constraints: `push_kwargs(embed)` output is byte-identical when no view is given; the `view` key is added only when a view is passed (some discord.py send paths reject `view=None`). About fourteen send sites call it (`alerts.py:201,220`, `follow_notify.py:332`, `loops.py:74,82,245`, `notices.py:38`, `recap.py:139`, `lifecycle_embeds.py:239,283,476,483,492`); none changes in this task.

- [ ] **Step 1: Write the failing tests**

In `tests/presentation/test_components.py`, keep `test_push_kwargs_adds_content_only_when_the_embed_has_a_push_line` exactly as it is (it is the byte-identical pin for the no-view output) and add after it:

```python
def test_push_kwargs_without_a_view_never_adds_the_view_key():
    pushed = c.push_embed(Kind.BOT_ONLINE)
    for kwargs in (c.push_kwargs(pushed), c.push_kwargs(pushed, view=None),
                   c.push_kwargs(pushed, None)):
        assert list(kwargs) == ["embed", "content"]
    plain = discord.Embed(title="x")
    assert list(c.push_kwargs(plain, view=None)) == ["embed"]


def test_push_kwargs_adds_a_given_view_last():
    view = object()                         # any object: push_kwargs never inspects it
    pushed = c.push_embed(Kind.BOT_ONLINE)
    assert c.push_kwargs(pushed, view=view) == {
        "embed": pushed, "content": "🤖 SYSTEM · ONLINE", "view": view}
    assert list(c.push_kwargs(pushed, view=view)) == ["embed", "content", "view"]
    plain = discord.Embed(title="x")
    assert c.push_kwargs(plain, view=view) == {"embed": plain, "view": view}
```

(`Kind` is already imported in this file; the existing test uses `Kind.BOT_ONLINE`.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/presentation/test_components.py`
Expected: FAIL — `TypeError: push_kwargs() got an unexpected keyword argument 'view'` (and `takes 1 positional argument but 2 were given`).

- [ ] **Step 3: Implement**

Replace `push_kwargs` in `swingbot/core/presentation/components.py`:

```python
def push_kwargs(embed, view=None) -> dict:
    """send() kwargs for one pushed embed: the embed, plus its content line if
    it has one, plus ``view`` only when one is given -- a send with no view
    gets exactly the kwargs it always did (some discord.py send paths reject
    ``view=None``)."""
    text = getattr(embed, "push_text", None)
    kwargs = {"embed": embed, "content": text} if text else {"embed": embed}
    if view is not None:
        kwargs["view"] = view
    return kwargs
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/presentation/test_components.py`
Expected: PASS, `0 failed` (including the unchanged `test_push_kwargs_adds_content_only_when_the_embed_has_a_push_line` and `test_the_package_exports_the_push_helpers`).

- [ ] **Step 5: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/core/presentation/components.py`
Expected: no line for `push_kwargs` (it is grade A).

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/core/presentation/components.py tests/presentation/test_components.py
git -C $WT commit -m "feat(ui): push_kwargs takes an optional view, added only when given (v170)"
```

Then `git -C $R status --short` must show the main tree unchanged.

### Task V170-9: Extract the single-trade price + unrealised body from `get_all_unrealized_pnl`

**Model:** sonnet — a behaviour-preserving extraction of a batch loop into a reusable per-trade function, with the existing `!pnl` test as the parity gate.

**Files:**
- Modify: `swingbot/core/scanning/scan_run.py:1249-1285` (`get_all_unrealized_pnl`; new `TradeQuote`, `_batch_prices`, `_daily_close`, `unrealized_for_trade`, `quote_trade` placed directly above it) and its imports (lines 7 and 33)
- Create: `tests/scanning/test_quote_trade.py`

**Interfaces:**
- Consumes: nothing from this plan. Existing: `scan_run.fetch.get_current_price_batch(tickers) -> {ticker: price}`, `scan_run.fetch.get_daily_data(ticker, period=...)`, `account.compute_unrealized_pnl(entry, stop_loss, take_profit, direction, current_price) -> UnrealizedPnL`.
- Produces (V170-10 consumes `quote_trade` and `TradeQuote`):
  - `scan_run.TradeQuote` — frozen dataclass `price: float | None`, `daily_close: date | None = None` (`None` = a live batch quote; a date = the daily-bar fallback, dated by its last bar).
  - `scan_run._batch_prices(tickers: list) -> dict` — one batch call, `{}` on any exception (logged).
  - `scan_run.unrealized_for_trade(trade: dict, price_cache: dict, daily_dates: dict) -> tuple[TradeQuote, UnrealizedPnL | None]` — `!pnl`'s per-trade body; fills `price_cache` / `daily_dates` in place; `pnl` is `None` when there is no price.
  - `scan_run.quote_trade(trade: dict) -> tuple[TradeQuote, UnrealizedPnL | None]` — one trade through a one-ticker batch.

Spec §3 / A5 / A6: `!pnl` and the P&L-now button price the open fraction through one function, so they cannot disagree; `get_all_unrealized_pnl` keeps its output and its one-batch-call behaviour, and `tests/scanning/test_unrealized_pnl_batch.py` passes **untouched** (Global Constraints). The daily fallback's bar date is the only "as-of" the data layer can give (A6), so it is carried out as `TradeQuote.daily_close`. A refactor never changes behaviour: the fallback condition stays `not price_cache.get(ticker)`, the daily fetch stays `period="5d"`, the float conversion stays inside the guarded block, and both log messages keep their text.

- [ ] **Step 1: Write the failing tests**

Create `tests/scanning/test_quote_trade.py`:

```python
"""v170: !pnl's per-trade body, extracted so the P&L-now button prices one
trade exactly the way !pnl prices it (spec §3, A5, A6)."""
import datetime as dt

import pandas as pd

from swingbot.core.planning.account import compute_unrealized_pnl
from swingbot.core.scanning import scan_run

TRADE = {"id": "t1", "ticker": "AAPL", "entry": 100.0, "stop_loss": 95.0,
         "take_profit": 110.0, "direction": "bullish"}
BAR_DAY = dt.date(2026, 10, 15)


def _no_daily(monkeypatch):
    monkeypatch.setattr(
        scan_run.fetch, "get_daily_data",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("daily fallback")))


def _daily(monkeypatch, closes):
    calls = []
    index = pd.date_range(end=pd.Timestamp(BAR_DAY), periods=len(closes), freq="D")

    def fake(ticker, period="2y"):
        calls.append((ticker, period))
        return pd.DataFrame({"Close": closes}, index=index)

    monkeypatch.setattr(scan_run.fetch, "get_daily_data", fake)
    return calls


def _daily_fails(monkeypatch):
    def fail(*_a, **_k):
        raise RuntimeError("yfinance down")
    monkeypatch.setattr(scan_run.fetch, "get_daily_data", fail)


def test_a_live_batch_price_marks_the_trade_with_no_daily_close(monkeypatch):
    _no_daily(monkeypatch)
    quote, pnl = scan_run.unrealized_for_trade(TRADE, {"AAPL": 101.0}, {})
    assert quote == scan_run.TradeQuote(price=101.0, daily_close=None)
    assert pnl == compute_unrealized_pnl(entry=100.0, stop_loss=95.0, take_profit=110.0,
                                         direction="bullish", current_price=101.0)


def test_a_missing_live_price_falls_back_to_the_daily_close_and_dates_it(monkeypatch):
    calls = _daily(monkeypatch, [99.0, 102.0])
    cache, dates = {}, {}
    quote, pnl = scan_run.unrealized_for_trade(TRADE, cache, dates)
    assert quote == scan_run.TradeQuote(price=102.0, daily_close=BAR_DAY)
    assert pnl.pct_change == 2.0
    assert calls == [("AAPL", "5d")]
    assert cache == {"AAPL": 102.0} and dates == {"AAPL": BAR_DAY}


def test_a_second_trade_on_the_same_ticker_reuses_the_cached_daily_close(monkeypatch):
    calls = _daily(monkeypatch, [99.0, 102.0])
    cache, dates = {}, {}
    scan_run.unrealized_for_trade(TRADE, cache, dates)
    quote, _pnl = scan_run.unrealized_for_trade(dict(TRADE, id="t2"), cache, dates)
    assert calls == [("AAPL", "5d")]
    assert quote == scan_run.TradeQuote(price=102.0, daily_close=BAR_DAY)


def test_no_price_anywhere_is_a_quote_without_a_price_never_an_exception(monkeypatch):
    _daily_fails(monkeypatch)
    quote, pnl = scan_run.unrealized_for_trade(TRADE, {}, {})
    assert quote == scan_run.TradeQuote(price=None) and pnl is None


def test_an_empty_daily_frame_is_no_price(monkeypatch):
    monkeypatch.setattr(scan_run.fetch, "get_daily_data",
                        lambda *_a, **_k: pd.DataFrame({"Close": []}))
    quote, pnl = scan_run.unrealized_for_trade(TRADE, {}, {})
    assert quote.price is None and pnl is None


def test_quote_trade_asks_a_one_ticker_batch(monkeypatch):
    calls = []
    monkeypatch.setattr(scan_run.fetch, "get_current_price_batch",
                        lambda tickers: calls.append(tickers) or {"AAPL": 104.0})
    _no_daily(monkeypatch)
    quote, pnl = scan_run.quote_trade(TRADE)
    assert calls == [["AAPL"]]
    assert quote == scan_run.TradeQuote(price=104.0) and pnl.pct_change == 4.0


def test_quote_trade_survives_a_failed_batch_and_a_failed_daily_fetch(monkeypatch):
    def fail(_tickers):
        raise TimeoutError("batch down")
    monkeypatch.setattr(scan_run.fetch, "get_current_price_batch", fail)
    _daily_fails(monkeypatch)
    assert scan_run.quote_trade(TRADE) == (scan_run.TradeQuote(price=None), None)


def test_all_unrealized_pnl_still_skips_a_trade_with_no_price(monkeypatch):
    trades = [TRADE, dict(TRADE, id="t2", ticker="MSFT")]

    class Log:
        def get_trades(self, **_kwargs):
            return trades

    monkeypatch.setattr(scan_run, "trade_log", Log())
    monkeypatch.setattr(scan_run.fetch, "get_current_price_batch",
                        lambda tickers: {"AAPL": 101.0})
    _daily_fails(monkeypatch)
    rows = scan_run.get_all_unrealized_pnl()
    assert [row["trade"]["id"] for row in rows] == ["t1"]
    assert rows[0]["pnl"].pct_change == 1.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/scanning/test_quote_trade.py`
Expected: FAIL — `AttributeError: module 'swingbot.core.scanning.scan_run' has no attribute 'unrealized_for_trade'` (and `TradeQuote`, `quote_trade`); `test_all_unrealized_pnl_still_skips_a_trade_with_no_price` already passes.

- [ ] **Step 3: Implement in `swingbot/core/scanning/scan_run.py`**

Imports: change line 7 `from datetime import datetime, timezone` to `from datetime import date, datetime, timezone`; add `from dataclasses import dataclass` beside the other stdlib imports (after `import time`); change line 33 to `from swingbot.core.planning.account import UnrealizedPnL, compute_unrealized_pnl, load_account_config`.

Replace `get_all_unrealized_pnl` (lines 1249-1285) with:

```python
@dataclass(frozen=True)
class TradeQuote:
    """The price one open trade is marked at, and where it came from: a live
    batch quote (``daily_close`` None) or the last daily bar's close
    (``daily_close`` = that bar's date). ``price`` None = no price at all.
    No price helper returns a quote timestamp, so this is the only as-of the
    data layer can give (v170 A6)."""

    price: float | None
    daily_close: date | None = None


def _batch_prices(tickers: list) -> dict:
    """One live-price request for every ticker; {} when it fails.

    This backs a display/report command, not a fill decision, so the batch
    helper's short resilient cache is appropriate. More importantly, it turns
    N serial Yahoo calls into one request for all open positions."""
    try:
        return fetch.get_current_price_batch(tickers)
    except Exception as exc:
        log.warning("get_all_unrealized_pnl: batch price fetch failed: %s", exc, exc_info=True)
        return {}


def _daily_close(ticker: str) -> tuple[float | None, date | None]:
    """The last daily close and its bar date: the fallback when the batch has
    no live price (incl. premarket/aftermarket) for ``ticker``."""
    try:
        df = fetch.get_daily_data(ticker, period="5d")
        if df is None or df.empty:
            return None, None
        last = df.index[-1]
        return float(df["Close"].iloc[-1]), (last.date() if hasattr(last, "date") else None)
    except Exception as exc:
        log.warning("get_all_unrealized_pnl: could not fetch price for %s: %s", ticker, exc,
                    exc_info=True)
        return None, None


def unrealized_for_trade(trade: dict, price_cache: dict,
                         daily_dates: dict) -> tuple[TradeQuote, UnrealizedPnL | None]:
    """!pnl's per-trade body: the trade's price (live from ``price_cache``,
    else the last daily close) and its unrealised % move. ``price_cache`` and
    ``daily_dates`` are shared across one batch and filled in place, so a
    second trade on the same ticker never refetches. ``pnl`` is None when
    there is no price."""
    ticker = trade["ticker"]
    if not price_cache.get(ticker):
        price_cache[ticker], daily_dates[ticker] = _daily_close(ticker)
    quote = TradeQuote(price_cache[ticker], daily_dates.get(ticker))
    if quote.price is None:
        return quote, None
    return quote, compute_unrealized_pnl(
        entry=trade["entry"],
        stop_loss=trade["stop_loss"],
        take_profit=trade["take_profit"],
        direction=trade["direction"],
        current_price=quote.price,
    )


def quote_trade(trade: dict) -> tuple[TradeQuote, UnrealizedPnL | None]:
    """One trade marked exactly as !pnl marks it, through a one-ticker batch
    (the v170 P&L-now button). A price failure is a quote with no price."""
    return unrealized_for_trade(trade, _batch_prices([trade["ticker"]]), {})


def get_all_unrealized_pnl() -> list:
    open_trades = trade_log.get_trades(status="open", limit=100)
    log.info("Computing unrealized P/L for %d open trade(s)", len(open_trades))
    tickers = list(dict.fromkeys(
        trade.get("ticker") for trade in open_trades if trade.get("ticker")
    ))
    price_cache = _batch_prices(tickers)
    daily_dates: dict = {}
    results = []
    for t in open_trades:
        _quote, pnl = unrealized_for_trade(t, price_cache, daily_dates)
        if pnl is not None:
            results.append({"trade": t, "pnl": pnl})
    return results
```

Behaviour check against the old body: the batch call, its `{}` fallback and its log line are `_batch_prices`; the per-ticker `not price_cache.get(ticker)` fallback, the `period="5d"` fetch, the `None` cache on failure and its log line are `_daily_close` via `unrealized_for_trade`; a `None` price still skips the row; `compute_unrealized_pnl` gets the same five arguments. `scanning/engine.py` re-exports only `get_all_unrealized_pnl`; leave it as is.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/scanning/test_quote_trade.py`
Expected: PASS, `0 failed`.

Run: `python $WT/scripts/dev/testrun.py file tests/scanning/test_unrealized_pnl_batch.py`
Expected: PASS, unchanged file (`git -C $WT diff --stat tests/scanning/test_unrealized_pnl_batch.py` prints nothing).

Run the `!pnl` render parity cases: `python $WT/scripts/dev/testrun.py changed`
Expected: PASS, `0 failed` (it selects the tests that reach `scan_run.py`, including the `!pnl` parity cases in `tests/commands/parity_cases/trades.py`).

- [ ] **Step 5: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/core/scanning/scan_run.py`
Expected: no line for `get_all_unrealized_pnl` (B 10 before, lower now), `unrealized_for_trade`, `_daily_close`, `_batch_prices` or `quote_trade`. Functions already ≥ 15 that this task does not touch (`_sync_run_scan`) may still print; nothing this task touched may.

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/core/scanning/scan_run.py tests/scanning/test_quote_trade.py
git -C $WT commit -m "refactor(pnl): extract !pnl's per-trade price and unrealised body into unrealized_for_trade/quote_trade (v170)"
```

Then `git -C $R status --short` must show the main tree unchanged.

