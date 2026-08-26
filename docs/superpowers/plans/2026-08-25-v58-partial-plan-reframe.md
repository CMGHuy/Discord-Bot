# Reframe the PARTIAL plan display as a mini-position — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-08-25-v58-partial-plan-reframe-design.md`

**Goal:** Once a plan's TP1 fires, show the runner leg as its own position (entry/target/stop) and state the already-banked profit in R, %, and $ — everywhere a PARTIAL plan is displayed — without changing any stop/target/TP2 math.

**Architecture:** A small numeric helper (`banked_leg_pct_and_amount`) computes %/$ for the closed TP1 leg, reusing the render-time `account.compute_position_size` snapshot `embeds.py::leg_rows()` already uses. Each of the four surfaces (Discord TP1 alert, `!liveplans` board, admin dashboard/trades card tooltip, admin trade-detail page) wires that helper into its own existing formatting, in its own house style. The admin dashboard/trades surface needs three new nullable fields on the trade list row (`banked_fraction`, `banked_exit_price`, `banked_r`) — the trade-*detail* endpoint already exposes the equivalent via `legs_realized`, but the *list* endpoint strips its transient equivalent (`_legs`), so this is the one place the spec's "no backend schema change" claim needed a correction, caught during this plan's own research (see "Deviations from the spec" below).

**Tech Stack:** Python (discord.py embeds, Flask API), TypeScript/Angular (`@ngrx/signals` stores, zoneless signals, Vitest).

## Global Constraints

- **No change to `runner_floor`, `RUNNER_FLOOR_FRACTION`, `TP1_FRACTION`, or TP2 selection.** Every task in this plan is presentation-only.
- **TP2 is never re-derived at TP1-fire time.** Every "target" shown is `plan.tp2` (or its already-existing fallback to `plan.tp1`), read as-is.
- A %/$ figure that cannot be computed (no sizing/account data) is **omitted**, never shown as `0` and never a crash — same convention `embeds.py::leg_rows()` already uses for its own $ figures.
- `Edge: none (integrity)` — no backtest/validation run is part of this plan.
- Every new/changed narrow test passes before its task's commit (`python scripts/dev/testrun.py file <touched test file>`); `ng test` (or the touched spec file) for frontend tasks. The full suite runs once, in Task 9, per `docs/claude/document-conventions.md`.

### Deviations from the spec (found during this plan's research)

- **The admin dashboard/trades list row needs three new fields.** The spec's "no backend schema change" claim holds for the trade-*detail* endpoint (`GET /api/v1/trades/:id`, which already exposes `legs_realized` inside its permanent `detail` object) but not for the trade *list* endpoint (`GET /api/v1/trades`): its per-row `_legs` field is deliberately transient and stripped by `_strip_internal_fields` before the response is ever sent (`swingbot/admin/api_v1/trades.py:770-776`), so nothing about the banked leg reaches the dashboard/trades table today. Task 4 adds three small nullable fields (`banked_fraction`, `banked_exit_price`, `banked_r`) to the list row to close that gap — %, and $ are still computed *client-side* from those plus fields already on the row (`entry`, `shares`, `direction`), so no percentage/dollar math moves server-side.
- **`partial_position_line()` (embeds.py) and the `!liveplans` board line intentionally use different wording**, per the spec's own examples ("target 150.00" vs "TP2 150.00", "stop" vs "trail") — both call the same shared numeric helper, but format it in each surface's own house style rather than sharing one formatting function.
- **The admin trade-detail panel does not literally reuse `<sb-plan-cell>`** as the spec's prose suggested. This page's established layout is `<sb-panel heading="…"><dl>…` blocks (see the existing "Levels"/"Now"/"Stop to target" panels) — `PlanCell` is a compact table-row component, not a fit for this page's pattern. The new "Partial position" panel follows the page's own existing convention instead, and reuses `trade.target`/`trade.stop_loss` directly (already the correct tp2-or-tp1 / working_stop-fallback values per `_row_from_plan`) rather than re-deriving the same fallback a second time client-side.
- **Task 8's own Step 3 template, as originally written (`{{ fmt(stats.amount) }}`), cannot pass Task 8's own Step 1 test (`toContain('+50.00')`)** — `fmt` is bound to `num()` (`ui/format.ts`), which never signs its output, so the literal template block as drafted is a self-contradiction, caught during implementation, not before. Fixed as `{{ stats.amount > 0 ? '+' : '' }}{{ fmt(stats.amount) }}` — verified against the file's own established convention: `trade-detail.ts`'s pre-existing `realized_pnl_amount` row is unsigned/no-unit (colour-only via `pnlClass`), and the file has no `ConnectionStore`/currency wiring, so reusing `format.ts`'s purpose-built `money(value, unit)` (used for the identical figure in `PlanCell`, Task 5) would have required adding a new dependency the brief's Interfaces section didn't call for. Task-reviewer-confirmed necessary and correctly scoped; left as a Minor follow-up (not actioned in this plan) that `money()`/`ConnectionStore` would also fix the cross-page inconsistency of this panel showing no currency unit where `PlanCell` does.

## Parallelisation

- **Group 1 (backend, sequential within):** Task 1 → Task 2, Task 3 (both consume Task 1's helper; 2 and 3 touch disjoint files and can run in parallel with each other once Task 1 lands).
- **Group 2 (backend, independent):** Task 4 — a different file (`admin/api_v1/trades.py`) with no dependency on Tasks 1-3.
- **Group 3 (frontend, sequential within):** Task 5 → Task 6 (Task 6's template bindings consume Task 5's new `PlanCell` inputs and exported functions).
- **Group 4 (frontend, sequential within):** Task 7 → Task 8 (Task 8's template consumes Task 7's new store computed signals).
- Groups 1-4 are mutually independent (disjoint files, no shared symbols) and can all run in parallel with each other.
- **Task 9 (full-suite verification) is sequential, after every other task.**

---

### Task 1: Backend — the banked-leg %/$ helper

**Files:**
- Modify: `swingbot/core/scanning/embeds.py`
- Test: `tests/scanning/test_embeds_badges.py`

**Interfaces:**
- Produces: `banked_leg_pct_and_amount(plan, exit_price: float, fraction: float) -> tuple[float, float | None]` — importable as `swingbot.core.scanning.embeds.banked_leg_pct_and_amount`. Tasks 2 and 3 both consume this.

- [ ] **Step 1: Write the failing tests**

Add to `tests/scanning/test_embeds_badges.py` (after the existing `test_leg_rows_unsized` test):

```python
def test_banked_leg_pct_and_amount(monkeypatch):
    import swingbot.core.scanning.embeds as embeds
    monkeypatch.setattr(embeds.account, "compute_position_size",
                        lambda entry, stop: {"shares": 100.0,
                                             "position_value": 10_000.0,
                                             "mode": "risk_pct"})
    p = _plan(entry_price=100.0, stop_loss=95.0, direction="bullish")
    pct, amount = embeds.banked_leg_pct_and_amount(p, 110.0, 0.5)
    assert pct == 10.0
    assert amount == 500.0


def test_banked_leg_pct_and_amount_bearish_signs_correctly(monkeypatch):
    import swingbot.core.scanning.embeds as embeds
    monkeypatch.setattr(embeds.account, "compute_position_size",
                        lambda entry, stop: {"shares": 100.0,
                                             "position_value": 10_000.0,
                                             "mode": "risk_pct"})
    p = _plan(entry_price=100.0, stop_loss=105.0, direction="bearish")
    pct, amount = embeds.banked_leg_pct_and_amount(p, 90.0, 0.5)
    assert pct == 10.0     # price fell 10% -- a gain for a short
    assert amount == 500.0


def test_banked_leg_pct_and_amount_unsized(monkeypatch):
    import swingbot.core.scanning.embeds as embeds
    monkeypatch.setattr(embeds.account, "compute_position_size",
                        lambda entry, stop: None)
    p = _plan(entry_price=100.0, stop_loss=95.0, direction="bullish")
    pct, amount = embeds.banked_leg_pct_and_amount(p, 110.0, 0.5)
    assert pct == 10.0
    assert amount is None


def test_banked_leg_pct_and_amount_falls_back_to_trigger_price(monkeypatch):
    import swingbot.core.scanning.embeds as embeds
    monkeypatch.setattr(embeds.account, "compute_position_size",
                        lambda entry, stop: None)
    p = _plan(entry_price=None, trigger_price=100.0, stop_loss=95.0, direction="bullish")
    pct, _ = embeds.banked_leg_pct_and_amount(p, 105.0, 0.5)
    assert pct == 5.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_embeds_badges.py`
Expected: FAIL — `AttributeError: module 'swingbot.core.scanning.embeds' has no attribute 'banked_leg_pct_and_amount'`

- [ ] **Step 3: Add the function**

In `swingbot/core/scanning/embeds.py`, add this function immediately after `leg_rows()` (which ends around line 449, right before `def _v2_plan(item):`):

```python
def banked_leg_pct_and_amount(plan, exit_price: float, fraction: float) -> tuple[float, float | None]:
    """(%, $) for one already-closed leg of a scale-out plan.

    % is always computable from the plan's own entry (falling back to
    trigger_price the same way leg_rows() does, for a plan whose
    entry_price was never set) and the leg's own exit price. The $ amount
    needs a fresh account.compute_position_size() snapshot and is None when
    that returns nothing usable -- same render-time-snapshot convention and
    same silent-omission fallback leg_rows() already uses, not a zero and
    not a crash."""
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    sign = 1 if plan.direction == "bullish" else -1
    pct = (exit_price - entry) / entry * 100 * sign
    try:
        sizing = account.compute_position_size(entry, plan.stop_loss)
    except Exception:
        sizing = None
    amount = None
    if sizing and sizing.get("shares"):
        amount = sizing["shares"] * fraction * (exit_price - entry) * sign
    return pct, amount
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_embeds_badges.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/embeds.py tests/scanning/test_embeds_badges.py
git commit -m "feat(v58): add banked_leg_pct_and_amount, the %/\$ helper for a PARTIAL plan's TP1 leg"
```

---

### Task 2: Backend — Discord TP1-hit alert shows the runner as a position

**Files:**
- Modify: `swingbot/core/scanning/embeds.py`
- Test: `tests/scanning/test_transition_embeds.py`

**Interfaces:**
- Consumes: `banked_leg_pct_and_amount(plan, exit_price, fraction) -> tuple[float, float | None]` (Task 1).
- Produces: `partial_position_line(plan) -> str`, importable as `swingbot.core.scanning.embeds.partial_position_line`.

- [ ] **Step 1: Write the failing tests**

Replace the existing `test_tp1_partial_embed_mentions_runner_and_its_floor` test in `tests/scanning/test_transition_embeds.py` (it asserts the old static-text copy this task removes) with:

```python
def test_tp1_partial_embed_shows_banked_stats_and_partial_position(monkeypatch):
    import swingbot.core.scanning.embeds as embeds
    monkeypatch.setattr(embeds.account, "compute_position_size",
                        lambda entry, stop: {"shares": 100.0,
                                             "position_value": 10_000.0,
                                             "mode": "risk_pct"})
    e = _embed("tp1_partial", {"fraction": 0.5, "exit_price": 110.0, "r": 2.0},
              legs_realized=[{"fraction": 0.5, "exit_price": 110.0,
                              "r": 2.0, "reason": "tp1"}],
              working_stop=101.33)
    assert "💰" in e.title
    banked = next(f.value for f in e.fields if f.name == "Banked")
    assert "50% @ 110.00" in banked
    assert "+2.00R" in banked
    assert "+10.0%" in banked
    assert "+$500.00" in banked
    partial = next(f.value for f in e.fields if f.name == "Partial position")
    assert partial == "entry 110.00 → target 105.00 / stop 101.33"


def test_tp1_partial_embed_omits_dollar_figure_when_unsized(monkeypatch):
    import swingbot.core.scanning.embeds as embeds
    monkeypatch.setattr(embeds.account, "compute_position_size",
                        lambda entry, stop: None)
    e = _embed("tp1_partial", {"fraction": 0.5, "exit_price": 110.0, "r": 2.0},
              legs_realized=[{"fraction": 0.5, "exit_price": 110.0,
                              "r": 2.0, "reason": "tp1"}],
              working_stop=101.33)
    banked = next(f.value for f in e.fields if f.name == "Banked")
    assert "$" not in banked


def test_partial_position_line_falls_back_to_tp1_when_no_tp2():
    from swingbot.core.scanning.embeds import partial_position_line
    p = _plan(entry_price=100.0, stop_loss=95.0, tp1=102.0, tp2=None,
              legs_realized=[{"fraction": 0.5, "exit_price": 102.0,
                              "r": 1.4, "reason": "tp1"}],
              working_stop=101.33)
    assert partial_position_line(p) == ("entry 102.00 → target 102.00 "
                                        "(tp1, no tp2) / stop 101.33")


def test_partial_position_line_falls_back_to_runner_floor_when_no_working_stop():
    from swingbot.core.scanning.embeds import partial_position_line
    p = _plan(entry_price=100.0, stop_loss=95.0, tp1=102.0, tp2=105.0,
              legs_realized=[{"fraction": 0.5, "exit_price": 102.0,
                              "r": 1.4, "reason": "tp1"}],
              working_stop=None)
    # runner_floor(100, 102) = 100 + 2/3 * (102 - 100) = 101.33
    assert partial_position_line(p) == "entry 102.00 → target 105.00 / stop 101.33"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_transition_embeds.py`
Expected: FAIL — the new/renamed test can't find `partial_position_line`, and the existing `Banked`-field assertions don't match the old copy yet.

- [ ] **Step 3: Add `partial_position_line` and wire the `tp1_partial` branch**

In `swingbot/core/scanning/embeds.py`, add `runner_floor` to the existing plan_engine import:

```python
from swingbot.core.planning.plan_engine import WEAK_CAUTION_TEXT, badge_stats_line, runner_floor
```

Add this function immediately after `banked_leg_pct_and_amount` (Task 1):

```python
def partial_position_line(plan) -> str:
    """'entry 102.00 -> target 150.00 / stop 118.67' for the runner half of
    a PARTIAL plan -- the same entry -> target / stop shape used everywhere
    else in the bot's embeds, so it reads as one more position rather than
    a new format.

    Entry is the TP1 leg's own fill price (legs_realized[0]['exit_price']),
    not the plan's tp1 target level -- they are usually equal but the fill
    can differ on a gap-through. Falls back to plan.tp1 if legs_realized is
    somehow empty (a PARTIAL plan predating this field, same defensive
    fallback plan_manager.py's own PARTIAL step already uses).

    Target falls back to tp1 when the plan has no tp2 -- most strategies
    don't set one -- with a "(tp1, no tp2)" note, matching the precedent
    already set by admin/api_v1/trades.py's current_target."""
    leg = plan.legs_realized[0] if plan.legs_realized else None
    entry = leg["exit_price"] if leg else plan.tp1
    if plan.tp2 is not None:
        target, target_note = plan.tp2, ""
    else:
        target, target_note = plan.tp1, " (tp1, no tp2)"
    orig_entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    stop = (plan.working_stop if plan.working_stop is not None
           else runner_floor(orig_entry, plan.tp1))
    return f"entry {entry:.2f} → target {target:.2f}{target_note} / stop {stop:.2f}"
```

Replace the `tp1_partial` branch of `build_plan_event_embed` (currently):

```python
    elif event.transition == "tp1_partial":
        embed.add_field(name="Banked",
                        value=f"{d['fraction']:.0%} @ {d['exit_price']:.2f} "
                              f"({d['r']:+.2f}R)")
        embed.add_field(name="Runner",
                        value="runner active, stop protecting 2/3 of the TP1 move",
                        inline=False)
```

with:

```python
    elif event.transition == "tp1_partial":
        pct, amount = banked_leg_pct_and_amount(plan, d["exit_price"], d["fraction"])
        cur = config.CURRENCY_SYMBOL
        banked = (f"{d['fraction']:.0%} @ {d['exit_price']:.2f} "
                 f"({d['r']:+.2f}R · {pct:+.1f}%")
        if amount is not None:
            banked += f" · +{cur}{amount:,.2f}"
        banked += ")"
        embed.add_field(name="Banked", value=banked)
        embed.add_field(name="Partial position", value=partial_position_line(plan),
                        inline=False)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_transition_embeds.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/embeds.py tests/scanning/test_transition_embeds.py
git commit -m "feat(v58): Discord TP1-hit alert shows the runner as its own position"
```

---

### Task 3: Backend — `!liveplans` board shows TP2 and the full banked figure

**Files:**
- Modify: `swingbot/commands/plans.py`
- Test: `tests/planning/test_plans_command.py`

**Interfaces:**
- Consumes: `banked_leg_pct_and_amount` (Task 1), `swingbot.config.CURRENCY_SYMBOL`.

- [ ] **Step 1: Write the failing tests**

Replace the body of `test_board_groups_by_status` in `tests/planning/test_plans_command.py` with (the only change is the added `monkeypatch` fixture and the two final assertions):

```python
def test_board_groups_by_status(monkeypatch):
    import swingbot.core.scanning.embeds as embeds
    monkeypatch.setattr(embeds.account, "compute_position_size",
                        lambda entry, stop: {"shares": 100.0,
                                             "position_value": 10_000.0,
                                             "mode": "risk_pct"})
    pending = _plan(plan_id="a", ticker="AAPL", entry_type="stop_entry",
                    trigger_price=105.0, expiry_bars=5)
    active = _plan(plan_id="b", ticker="MSFT", entry_price=100.0)
    record_transition(active, PlanStatus.ACTIVE, at="t")
    partial = _plan(plan_id="c", ticker="NVDA", entry_price=100.0,
                    legs_realized=[{"fraction": 0.5, "exit_price": 110.0,
                                    "r": 2.0, "reason": "tp1"}],
                    working_stop=100.0)
    record_transition(partial, PlanStatus.ACTIVE, at="t")
    record_transition(partial, PlanStatus.PARTIAL, at="t")

    board = format_plans_board([pending, active, partial],
                               prices={"MSFT": 104.0})
    assert board.index("PENDING") < board.index("AAPL")
    assert board.index("ACTIVE") < board.index("MSFT")
    assert board.index("PARTIAL") < board.index("NVDA")
    assert "trigger 105.00" in board
    assert "banked +2.00R/+10.0%/+$500.00 on 50%" in board
    assert "entry 110.00 → TP2 105.00 / trail 100.00" in board


def test_board_partial_falls_back_to_tp1_when_no_tp2(monkeypatch):
    import swingbot.core.scanning.embeds as embeds
    monkeypatch.setattr(embeds.account, "compute_position_size",
                        lambda entry, stop: None)
    partial = _plan(plan_id="d", ticker="TSLA", entry_price=100.0, tp1=102.0, tp2=None,
                    legs_realized=[{"fraction": 0.5, "exit_price": 102.0,
                                    "r": 1.4, "reason": "tp1"}],
                    working_stop=101.0)
    record_transition(partial, PlanStatus.ACTIVE, at="t")
    record_transition(partial, PlanStatus.PARTIAL, at="t")
    board = format_plans_board([partial])
    assert "entry 102.00 → TP1 (no TP2) 102.00 / trail 101.00" in board
    assert "$" not in board
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_plans_command.py`
Expected: FAIL — `assert "banked +2.00R/+10.0%/+$500.00 on 50%" in board` fails against the old `"banked +2.00R on 50%"` copy.

- [ ] **Step 3: Wire the PARTIAL branch**

In `swingbot/commands/plans.py`, add two imports:

```python
from swingbot import config
from swingbot.core.scanning.embeds import banked_leg_pct_and_amount
```

Replace the PARTIAL branch of `format_plans_board` (currently):

```python
            else:  # PARTIAL
                leg = p.legs_realized[0] if p.legs_realized else None
                banked = (f"banked {leg['r']:+.2f}R on {leg['fraction']:.0%}"
                          if leg else "banked")
                lines.append(f"{icon} `{p.ticker}` {p.direction} — {banked}, "
                             f"trail {p.working_stop:.2f}")
```

with:

```python
            else:  # PARTIAL
                leg = p.legs_realized[0] if p.legs_realized else None
                if leg:
                    pct, amount = banked_leg_pct_and_amount(p, leg["exit_price"],
                                                            leg["fraction"])
                    cur = config.CURRENCY_SYMBOL
                    banked = f"banked {leg['r']:+.2f}R/{pct:+.1f}%"
                    if amount is not None:
                        banked += f"/+{cur}{amount:,.2f}"
                    banked += f" on {leg['fraction']:.0%}"
                    entry = leg["exit_price"]
                else:
                    banked, entry = "banked", p.tp1
                if p.tp2 is not None:
                    target, target_label = p.tp2, "TP2"
                else:
                    target, target_label = p.tp1, "TP1 (no TP2)"
                lines.append(f"{icon} `{p.ticker}` {p.direction} — {banked}, "
                             f"entry {entry:.2f} → {target_label} {target:.2f} "
                             f"/ trail {p.working_stop:.2f}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/planning/test_plans_command.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/plans.py tests/planning/test_plans_command.py
git commit -m "feat(v58): !liveplans PARTIAL row shows TP2 and the full banked figure"
```

---

### Task 4: Backend — expose the banked leg on the trade list row

**Files:**
- Modify: `swingbot/admin/api_v1/trades.py`
- Test: `tests/admin/test_api_v1_trades.py`

**Interfaces:**
- Produces: three new nullable keys on every `GET /api/v1/trades` and `GET /api/v1/trades/:id` row: `banked_fraction`, `banked_exit_price`, `banked_r`. Consumed by Task 5/6 (frontend).

- [ ] **Step 1: Write the failing tests**

In `tests/admin/test_api_v1_trades.py`, add three lines to the `TRADE_ROW` contract dict, right after `"target2": NULLABLE_NUMBER,`:

```python
    "target2": NULLABLE_NUMBER,
    # v58 -- the TP1 leg's own stats, once a PARTIAL plan has banked one.
    # None until then; a legacy trade never scale-outs so always None.
    "banked_fraction": NULLABLE_NUMBER,
    "banked_exit_price": NULLABLE_NUMBER,
    "banked_r": NULLABLE_NUMBER,
```

Update `test_partial_plan_shows_the_runner_target_and_stop` to set `legs_realized` and assert the new fields:

```python
def test_partial_plan_shows_the_runner_target_and_stop(seed, logged_in):
    """TP1 already banked -- the position this row now represents is the
    runner, so "the plan" has to mean working_stop/TP2, not the original
    entry stop/TP1 that already happened."""
    plan = _plan("11111111-1111-4111-8111-111111111111", status="PARTIAL")
    plan.update({"stop_loss": 95.0, "tp1": 110.0, "tp2": 130.0, "working_stop": 101.0,
                "legs_realized": [{"fraction": 0.5, "exit_price": 110.0,
                                   "r": 1.8, "reason": "tp1"}]})
    trade = _trade("aaaaaaaaaaaaaaaa", plan_id=plan["plan_id"], status="open")
    seed(plans=[plan], trades=[trade])

    row = logged_in.get("/api/v1/trades").get_json()["items"][0]
    assert row["target"] == 130.0      # tp2, not tp1
    assert row["stop_loss"] == 101.0   # working_stop, not the original stop
    assert row["target2"] == 130.0
    assert row["banked_fraction"] == 0.5
    assert row["banked_exit_price"] == 110.0
    assert row["banked_r"] == 1.8
```

Add a new test right after it:

```python
def test_partial_plan_with_no_legs_realized_has_null_banked_fields(seed, logged_in):
    """A PARTIAL plan predating legs_realized (or a race where the field
    hasn't been written yet) shows nothing rather than a wrong leg."""
    plan = _plan("11111111-1111-4111-8111-111111111111", status="PARTIAL")
    plan.update({"stop_loss": 95.0, "tp1": 110.0, "tp2": 130.0, "working_stop": 101.0,
                "legs_realized": []})
    trade = _trade("aaaaaaaaaaaaaaaa", plan_id=plan["plan_id"], status="open")
    seed(plans=[plan], trades=[trade])

    row = logged_in.get("/api/v1/trades").get_json()["items"][0]
    assert row["banked_fraction"] is None
    assert row["banked_exit_price"] is None
    assert row["banked_r"] is None
```

Add one assertion line to the end of `test_active_plan_is_unaffected_by_the_partial_fields`:

```python
    row = logged_in.get("/api/v1/trades").get_json()["items"][0]
    assert row["target"] == 110.0
    assert row["stop_loss"] == 95.0
    assert row["banked_fraction"] is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_trades.py`
Expected: FAIL — the contract dict now expects `banked_fraction`/`banked_exit_price`/`banked_r` on every row and the endpoint doesn't return them yet (`assert_collection` reports missing keys), and the new/updated tests fail their direct assertions.

- [ ] **Step 3: Add the fields to both row builders**

In `swingbot/admin/api_v1/trades.py`, inside `_row_from_plan`, right after the existing `is_partial = plan.get("status") == "PARTIAL"` line, add:

```python
    legs_realized = plan.get("legs_realized") or []
    banked_leg = legs_realized[0] if is_partial and legs_realized else None
```

In the dict `_row_from_plan` returns, add three keys right after `"target2": plan.get("tp2"),`:

```python
        "target2": plan.get("tp2"),
        "banked_fraction": banked_leg.get("fraction") if banked_leg else None,
        "banked_exit_price": banked_leg.get("exit_price") if banked_leg else None,
        "banked_r": banked_leg.get("r") if banked_leg else None,
```

In `_row_from_trade`, add three keys right after `"target2": t.get("target2"),`:

```python
        "target2": t.get("target2"),
        "banked_fraction": None,
        "banked_exit_price": None,
        "banked_r": None,
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_trades.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/trades.py tests/admin/test_api_v1_trades.py
git commit -m "feat(v58): expose the banked TP1 leg on the trade list row"
```

---

### Task 5: Frontend — `PlanCell` shows the banked leg in its tooltip

**Files:**
- Modify: `frontend/src/app/api/models.ts`
- Modify: `frontend/src/app/ui/plan-cell.ts`
- Test: `frontend/src/app/ui/plan-cell.spec.ts`

**Interfaces:**
- Consumes: nothing new (pure presentational inputs).
- Produces: `PlanCell` gains inputs `bankedFraction`, `bankedR`, `bankedPct`, `bankedAmount`, `bankedEntry` (all `number | null`) and `currency` (`string | null`). Exported functions `bankedLegPct(entry, bankedEntry, direction) -> number | null` and `bankedLegAmount(entry, bankedEntry, bankedFraction, shares, direction) -> number | null`, both from `frontend/src/app/ui/plan-cell.ts`. `TradeRow` gains `banked_fraction`, `banked_exit_price`, `banked_r` (all `number | null`). Consumed by Task 6.

- [ ] **Step 1: Add the three fields to `TradeRow`**

In `frontend/src/app/api/models.ts`, in the `TradeRow` interface, add right after `target2: number | null;`:

```typescript
  target2: number | null;
  /** The TP1 leg's own fraction/fill-price/R once a PARTIAL plan has banked
   *  it. All three null until then; a legacy trade never scale-outs so
   *  always null. */
  banked_fraction: number | null;
  banked_exit_price: number | null;
  banked_r: number | null;
```

- [ ] **Step 2: Write the failing tests**

Add to `frontend/src/app/ui/plan-cell.spec.ts`, right before the final closing `});`:

```typescript
  /* -- v58: the banked-leg tooltip clause -------------------------------- */

  function renderPartial(overrides: Partial<{
    bankedFraction: number | null; bankedR: number | null;
    bankedPct: number | null; bankedAmount: number | null;
    bankedEntry: number | null; currency: string | null;
  }> = {}) {
    const f = TestBed.createComponent(PlanCell);
    f.componentRef.setInput('entry', 51.0);
    f.componentRef.setInput('target', 150.0);
    f.componentRef.setInput('stop', 118.67);
    f.componentRef.setInput('trailing', true);
    f.componentRef.setInput('bankedFraction', overrides.bankedFraction ?? 0.5);
    f.componentRef.setInput('bankedR', overrides.bankedR ?? 0.85);
    f.componentRef.setInput('bankedPct', overrides.bankedPct ?? 4.1);
    f.componentRef.setInput('bankedAmount', overrides.bankedAmount ?? 42.0);
    f.componentRef.setInput('bankedEntry', overrides.bankedEntry ?? 102.0);
    f.componentRef.setInput('currency', overrides.currency ?? '$');
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  it('appends the banked leg to the tooltip once PARTIAL', () => {
    expect(renderPartial().querySelector('[title]')!.getAttribute('title')).toBe(
      'Entry 51.00 · Target 150.00 · Trailing stop 118.67 · '
      + '50% banked +0.85R (+4.10%, +42.00 $) @ 102.00',
    );
  });

  it('omits the dollar figure when amount or currency is unknown', () => {
    expect(renderPartial({ bankedAmount: null }).querySelector('[title]')!.getAttribute('title'))
      .toBe('Entry 51.00 · Target 150.00 · Trailing stop 118.67 · '
        + '50% banked +0.85R (+4.10%) @ 102.00');
  });

  it('omits the whole banked clause when nothing has banked yet', () => {
    const f = TestBed.createComponent(PlanCell);
    f.componentRef.setInput('entry', 178);
    f.componentRef.setInput('target', 195);
    f.componentRef.setInput('stop', 170);
    f.componentRef.setInput('trailing', true);
    f.detectChanges();
    expect(f.nativeElement.querySelector('[title]').getAttribute('title'))
      .toBe('Entry 178.00 · Target 195.00 · Trailing stop 170.00');
  });
```

Add to the same file, as a new top-level `describe` block after the `describe('PlanCell', ...)` block closes:

```typescript
describe('bankedLegPct / bankedLegAmount', () => {
  it('signs pct positive for a long that gained', () => {
    expect(bankedLegPct(100, 110, 'bullish')).toBe(10);
  });

  it('signs pct positive for a short that gained (price fell)', () => {
    expect(bankedLegPct(100, 90, 'bearish')).toBe(10);
  });

  it('is null when either price is unknown', () => {
    expect(bankedLegPct(null, 110, 'bullish')).toBeNull();
    expect(bankedLegPct(100, null, 'bullish')).toBeNull();
  });

  it('computes the dollar amount from shares and fraction', () => {
    expect(bankedLegAmount(100, 110, 0.5, 100, 'bullish')).toBe(500);
  });

  it('signs the dollar amount for a short', () => {
    expect(bankedLegAmount(100, 90, 0.5, 100, 'bearish')).toBe(500);
  });

  it('is null when shares are unknown', () => {
    expect(bankedLegAmount(100, 110, 0.5, null, 'bullish')).toBeNull();
  });
});
```

And add `bankedLegPct, bankedLegAmount` to the existing `import { PlanCell } from './plan-cell';` line, making it:

```typescript
import { PlanCell, bankedLegAmount, bankedLegPct } from './plan-cell';
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd frontend && npx ng test --watch=false`
Expected: FAIL — `plan-cell.ts` has no `bankedFraction` input, no `bankedLegPct`/`bankedLegAmount` exports.

- [ ] **Step 4: Implement**

In `frontend/src/app/ui/plan-cell.ts`, change the import line:

```typescript
import { money, num, pct, rMultiple, share } from './format';
```

Add these inputs to the `PlanCell` class, right after the existing `trailing` input:

```typescript
  /* -- v58: the banked TP1 leg, shown in the tooltip once PARTIAL -------- */

  /** Fraction of the position TP1 closed (0-1). Null until PARTIAL. */
  readonly bankedFraction = input<number | null>(null);
  /** The TP1 leg's own R-multiple. */
  readonly bankedR = input<number | null>(null);
  /** %-gain on the TP1 leg, from the position's ORIGINAL entry to the
   *  leg's own exit price -- not the same number as the R-multiple. */
  readonly bankedPct = input<number | null>(null);
  /** $-amount for the same leg. Null when size is unknown -- omitted
   *  rather than shown as zero. */
  readonly bankedAmount = input<number | null>(null);
  /** The TP1 leg's own fill price -- the runner's "entry" for display
   *  purposes, distinct from `entry` above (the original position entry). */
  readonly bankedEntry = input<number | null>(null);
  /** Needed to format `bankedAmount`; the caller's own currency symbol. */
  readonly currency = input<string | null>(null);
```

Replace the `tooltip` computed:

```typescript
  protected readonly tooltip = computed(() => {
    // Names the role, because the styling difference alone does not: an
    // unfilled plan and a filled one are one glyph apart otherwise.
    const lead = this.showsTrigger()
      ? `Trigger ${this.fmt(this.trigger())} (not yet filled)`
      : `Entry ${this.fmt(this.entry())}`;
    const stopWord = this.trailing() ? 'Trailing stop' : 'Stop';
    let out = `${lead} · Target ${this.fmt(this.target())} · ${stopWord} ${this.fmt(this.stop())}`;
    const fraction = this.bankedFraction();
    const r = this.bankedR();
    const entry = this.bankedEntry();
    if (fraction !== null && r !== null && entry !== null) {
      const extras: string[] = [];
      const pctVal = this.bankedPct();
      if (pctVal !== null) extras.push(pct(pctVal));
      const amountVal = this.bankedAmount();
      const currencyVal = this.currency();
      if (amountVal !== null && currencyVal !== null) extras.push(money(amountVal, currencyVal));
      const extraText = extras.length ? ` (${extras.join(', ')})` : '';
      out += ` · ${share(fraction * 100)} banked ${rMultiple(r)}${extraText} @ ${this.fmt(entry)}`;
    }
    return out;
  });
```

Add these two exported functions at the end of the file, after the closing `}` of the `PlanCell` class:

```typescript
/** %-gain on an already-banked leg, from the position's ORIGINAL entry to
 *  that leg's own fill price, signed by direction -- the number a trader
 *  means by "how much did that leg make", not the R-multiple alone. */
export function bankedLegPct(
  entry: number | null,
  bankedEntry: number | null,
  direction: string,
): number | null {
  if (entry === null || bankedEntry === null || entry === 0) return null;
  const raw = ((bankedEntry - entry) / entry) * 100;
  return direction === 'bearish' ? -raw : raw;
}

/** $-amount for the same leg -- the ORIGINAL share count times the fraction
 *  that leg closed, times the move from entry to its own fill price. Null
 *  when any input needed to compute it is unknown. */
export function bankedLegAmount(
  entry: number | null,
  bankedEntry: number | null,
  bankedFraction: number | null,
  shares: number | null,
  direction: string,
): number | null {
  if (entry === null || bankedEntry === null || bankedFraction === null || shares === null) {
    return null;
  }
  const raw = (bankedEntry - entry) * shares * bankedFraction;
  return direction === 'bearish' ? -raw : raw;
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false`
Expected: PASS (if it times out at exactly 60s with no tests run, that is the known flaky load issue documented in `docs/claude/testing-cost.md` — re-run once)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/api/models.ts frontend/src/app/ui/plan-cell.ts frontend/src/app/ui/plan-cell.spec.ts
git commit -m "feat(v58): PlanCell shows the banked TP1 leg in its tooltip"
```

---

### Task 6: Frontend — wire the banked leg into the dashboard and trades cards

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts`
- Modify: `frontend/src/app/workspaces/trades/trades.ts`

**Interfaces:**
- Consumes: `bankedLegPct`, `bankedLegAmount` (Task 5), `TradeRow.banked_fraction/banked_exit_price/banked_r` (Task 5), `PlanCell`'s new inputs (Task 5).

This task has no new automated test of its own — it is template wiring over already-tested pure functions and an already-tested component, the same shape `expectedPnlPct`'s existing wiring into `dashboard.ts` takes (Step 2 verifies by hand instead of adding a redundant test at this layer).

- [ ] **Step 1: Wire `dashboard.ts`**

Change the import line:

```typescript
import { PlanCell, bankedLegAmount, bankedLegPct } from '../../ui/plan-cell';
```

Add two protected class fields, next to the existing `protected expectedPnlPct = expectedPnlPct;` line:

```typescript
  protected bankedLegPct = bankedLegPct;
  protected bankedLegAmount = bankedLegAmount;
```

Replace the `#planCell` template (currently):

```html
    <ng-template #planCell let-row>
      <sb-plan-cell
        [entry]="row.entry"
        [target]="row.target"
        [stop]="row.stop_loss"
        [trigger]="row.trigger_price"
        [trailing]="row.status === 'PARTIAL'"
      />
    </ng-template>
```

with:

```html
    <ng-template #planCell let-row>
      <sb-plan-cell
        [entry]="row.entry"
        [target]="row.target"
        [stop]="row.stop_loss"
        [trigger]="row.trigger_price"
        [trailing]="row.status === 'PARTIAL'"
        [bankedFraction]="row.banked_fraction"
        [bankedR]="row.banked_r"
        [bankedEntry]="row.banked_exit_price"
        [bankedPct]="bankedLegPct(row.entry, row.banked_exit_price, row.direction)"
        [bankedAmount]="bankedLegAmount(row.entry, row.banked_exit_price, row.banked_fraction, row.shares, row.direction)"
        [currency]="connection.currency()"
      />
    </ng-template>
```

- [ ] **Step 2: Wire `trades.ts` the same way**

Change the import line:

```typescript
import { PlanCell, bankedLegAmount, bankedLegPct } from '../../ui/plan-cell';
```

Add the same two protected class fields as Step 1.

Replace the `#planCell` template (currently, same shape as dashboard.ts):

```html
    <ng-template #planCell let-row>
      <sb-plan-cell
        [entry]="row.entry"
        [target]="row.target"
        [stop]="row.stop_loss"
        [trigger]="row.trigger_price"
        [trailing]="row.status === 'PARTIAL'"
      />
    </ng-template>
```

with the identical replacement block from Step 1.

- [ ] **Step 3: Verify by hand**

Run: `python scripts/dev/testrun.py file tests/scanning/test_embeds_badges.py` is irrelevant here — this is a frontend-only task. Instead:

Run: `cd frontend && npx ng build` (production build; catches template binding typos that `ng test` would not, since neither template gained its own spec file in this task)
Expected: build succeeds with no new errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/dashboard.ts frontend/src/app/workspaces/trades/trades.ts
git commit -m "feat(v58): wire the banked TP1 leg into the dashboard and trades cards"
```

---

### Task 7: Frontend — `TradeDetailStore` computes the banked leg's stats

**Files:**
- Modify: `frontend/src/app/stores/trade-detail.store.ts`
- Test: `frontend/src/app/stores/trade-detail.narrowing.spec.ts`

**Interfaces:**
- Produces: `TradeDetailStore.bankedLeg: Signal<Leg | null>` and `TradeDetailStore.bankedStats: Signal<{ pct: number; amount: number | null } | null>`. Consumed by Task 8.

- [ ] **Step 1: Write the failing tests**

Add to `frontend/src/app/stores/trade-detail.narrowing.spec.ts`, as a new `describe` block after the existing one closes:

```typescript
describe('TradeDetailStore — banked leg stats (v58)', () => {
  let store: InstanceType<typeof TradeDetailStore>;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: new FakeEventStream() },
        TradeDetailStore,
      ],
    });
    store = TestBed.inject(TradeDetailStore);
    backend = TestBed.inject(HttpTestingController);
  });

  function openPartial(overrides: {
    entry?: number | null; shares?: number | null;
    direction?: string; legsRealized?: unknown[];
  } = {}) {
    store.setId(ID);
    TestBed.inject(ApplicationRef).tick();
    backend.expectOne(`/api/v1/trades/${ID}`).flush({
      id: ID,
      ticker: 'AAPL',
      strategy: 'RSI Divergence',
      status: 'PARTIAL',
      direction: overrides.direction ?? 'bullish',
      entry: overrides.entry === undefined ? 100 : overrides.entry,
      stop_loss: 101.33,
      target: 105,
      shares: overrides.shares === undefined ? 100 : overrides.shares,
      has_note: false,
      detail: {
        ...LEGACY_DETAIL,
        legs_realized: overrides.legsRealized
          ?? [{ fraction: 0.5, exit_price: 110, r: 2.0, reason: 'tp1' }],
      },
    });
  }

  it('reads the banked leg once PARTIAL', () => {
    openPartial();
    expect(store.bankedLeg()).toEqual({
      fraction: 0.5, exitPrice: 110, r: 2.0, reason: 'tp1',
    });
  });

  it('is null before anything has banked', () => {
    openPartial({ legsRealized: [] });
    expect(store.bankedLeg()).toBeNull();
  });

  it('computes pct and dollar amount from the ORIGINAL entry', () => {
    openPartial();
    expect(store.bankedStats()).toEqual({ pct: 10, amount: 500 });
  });

  it('signs the pct and amount correctly for a short', () => {
    openPartial({
      direction: 'bearish', entry: 100,
      legsRealized: [{ fraction: 0.5, exit_price: 90, r: 2.0, reason: 'tp1' }],
    });
    expect(store.bankedStats()).toEqual({ pct: 10, amount: 500 });
  });

  it('omits the dollar amount when shares are unknown', () => {
    openPartial({ shares: null });
    expect(store.bankedStats()).toEqual({ pct: 10, amount: null });
  });

  it('is null once the position is no longer PARTIAL', () => {
    store.setId(ID);
    TestBed.inject(ApplicationRef).tick();
    backend.expectOne(`/api/v1/trades/${ID}`).flush({
      id: ID, ticker: 'AAPL', strategy: 'RSI Divergence', status: 'CLOSED',
      direction: 'bullish', entry: 100, stop_loss: 101.33, target: 105,
      shares: 100, has_note: false,
      detail: {
        ...LEGACY_DETAIL,
        legs_realized: [{ fraction: 0.5, exit_price: 110, r: 2.0, reason: 'tp1' }],
      },
    });
    expect(store.bankedLeg()).toBeNull();
    expect(store.bankedStats()).toBeNull();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx ng test --watch=false`
Expected: FAIL — `store.bankedLeg is not a function`.

- [ ] **Step 3: Add the computed signals**

In `frontend/src/app/stores/trade-detail.store.ts`, inside the `withComputed(({ data, ... }) => ({ ... }))` call, add these two entries right after the existing `legs: computed<Leg[]>(...)` entry:

```typescript
    /** The TP1 leg, once a PARTIAL plan has banked it -- null before then.
     *  `trade.target`/`trade.stop_loss` are already the runner's own
     *  numbers once PARTIAL (server-side fallback, `admin/api_v1/trades.py`);
     *  this is the one fact those fields don't carry: what already closed,
     *  and at what price. */
    bankedLeg: computed<Leg | null>(() => {
      const trade = data();
      const detail = trade?.detail;
      if (!trade || !detail || trade.status !== 'PARTIAL') return null;
      return toLegs(detail.legs_realized ?? [])[0] ?? null;
    }),

    /** %-gain and $-amount for that leg, from the position's ORIGINAL entry
     *  (not the leg's own price) to the leg's exit -- the number a trader
     *  means by "how much did that leg make". `amount` is null when
     *  `shares` is unknown (a legacy record) -- omitted rather than shown
     *  as zero, same convention `embeds.py`'s server-side $ fallback uses. */
    bankedStats: computed<{ pct: number; amount: number | null } | null>(() => {
      const trade = data();
      const detail = trade?.detail;
      if (!trade || !detail || trade.status !== 'PARTIAL' || trade.entry === null) {
        return null;
      }
      const leg = toLegs(detail.legs_realized ?? [])[0];
      if (!leg || leg.exitPrice === null || leg.fraction === null) return null;
      const sign = trade.direction === 'bearish' ? -1 : 1;
      const pct = ((leg.exitPrice - trade.entry) / trade.entry) * 100 * sign;
      const amount = trade.shares === null
        ? null
        : trade.shares * leg.fraction * (leg.exitPrice - trade.entry) * sign;
      return { pct, amount };
    }),
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/stores/trade-detail.store.ts frontend/src/app/stores/trade-detail.narrowing.spec.ts
git commit -m "feat(v58): TradeDetailStore computes the banked TP1 leg's pct/dollar stats"
```

---

### Task 8: Frontend — trade-detail page shows the "Partial position" panel

**Files:**
- Modify: `frontend/src/app/workspaces/trades/trade-detail.ts`
- Test: `frontend/src/app/workspaces/trades/trade-detail.spec.ts`

**Interfaces:**
- Consumes: `store.bankedLeg()`, `store.bankedStats()` (Task 7).

- [ ] **Step 1: Write the failing tests**

Add to `frontend/src/app/workspaces/trades/trade-detail.spec.ts`, as a new `describe` block after the file's last existing one closes:

```typescript
describe('TradeDetail — partial position panel (v58)', () => {
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: new FakeEventStream() },
      ],
    });
    backend = TestBed.inject(HttpTestingController);
  });

  function renderPartial(legsRealized: unknown[] = [
    { fraction: 0.5, exit_price: 110, r: 2.0, reason: 'tp1' },
  ]) {
    const fixture = TestBed.createComponent(TradeDetail);
    fixture.componentRef.setInput('id', ID);
    fixture.componentRef.setInput('tab', 'live');
    fixture.detectChanges();
    backend.expectOne(`/api/v1/trades/${ID}`).flush(
      tradeResponse({ ...DETAIL, legs_realized: legsRealized, working_stop: 101.33 },
                    'PARTIAL'),
    );
    fixture.detectChanges();
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  it('shows the runner as its own position once PARTIAL', () => {
    const text = renderPartial();
    expect(text).toContain('Partial position');
    expect(text).toContain('110.00');   // the TP1 leg's own fill, as "Entry"
    expect(text).toContain('50%');
    expect(text).toContain('+2.00R');
  });

  it('shows the pct and dollar figures for the banked leg', () => {
    const text = renderPartial();
    // tradeResponse() defaults entry=100, shares=10: (110-100)*0.5*10 = 50
    expect(text).toContain('+10.00%');
    expect(text).toContain('+50.00');
  });

  it('does not render the panel before anything has banked', () => {
    expect(renderPartial([])).not.toContain('Partial position');
  });

  it('does not render the panel outside PARTIAL', () => {
    const fixture = TestBed.createComponent(TradeDetail);
    fixture.componentRef.setInput('id', ID);
    fixture.componentRef.setInput('tab', 'live');
    fixture.detectChanges();
    backend.expectOne(`/api/v1/trades/${ID}`).flush(tradeResponse(DETAIL, 'ACTIVE'));
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).not.toContain('Partial position');
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx ng test --watch=false`
Expected: FAIL — no "Partial position" text is rendered anywhere yet.

- [ ] **Step 3: Add the panel**

In `frontend/src/app/workspaces/trades/trade-detail.ts`, in the `@case ('live')` template block, insert this new `@if` block right after the closing `</sb-panel>` of the "Stop to target" panel and right before `<sb-panel heading="Actions">`:

```html
            @if (trade.status === 'PARTIAL' && store.bankedLeg(); as banked) {
              <sb-panel heading="Partial position">
                <dl>
                  <div>
                    <dt>Entry</dt>
                    <dd class="num">{{ fmt(banked.exitPrice) }}</dd>
                  </div>
                  <div>
                    <dt>Target</dt>
                    <dd class="num pos">{{ fmt(trade.target) }}</dd>
                  </div>
                  <div>
                    <dt>Trailing stop</dt>
                    <dd class="num neg">{{ fmt(trade.stop_loss) }}</dd>
                  </div>
                  <div>
                    <dt>Banked</dt>
                    <dd class="num">
                      @if (banked.fraction !== null) {
                        {{ fmtShare(banked.fraction * 100) }}
                      }
                      @ {{ fmt(banked.exitPrice) }}
                      @if (banked.r !== null) {
                        <span [class]="pnlClass(banked.r)">{{ fmtR(banked.r) }}</span>
                      }
                      @if (store.bankedStats(); as stats) {
                        <span class="muted muted-gap">{{ fmtPct(stats.pct) }}</span>
                        @if (stats.amount !== null) {
                          <span class="muted muted-gap" [class]="pnlClass(stats.amount)">
                            {{ fmt(stats.amount) }}
                          </span>
                        }
                      }
                    </dd>
                  </div>
                </dl>
              </sb-panel>
            }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/trades/trade-detail.ts frontend/src/app/workspaces/trades/trade-detail.spec.ts
git commit -m "feat(v58): trade-detail page shows the Partial position panel"
```

---

### Task 9: Full-suite verification

**Files:** none (verification only).

- [ ] **Step 1: Run the backend full suite**

Run: `python scripts/dev/testrun.py full` (or dispatch the `test-runner` subagent)
Expected: `0 failed`, `0 xfailed`. Fix forward from any failure — it is this plan's regression, not a reason to revisit earlier tasks.

- [ ] **Step 2: Run the frontend suite**

Run: `cd frontend && npx ng test --watch=false`
Expected: all green. Re-run once if it hits the documented 60s flaky-timeout (`docs/claude/testing-cost.md`).

- [ ] **Step 3: Production frontend build**

Run: `cd frontend && npx ng build`
Expected: clean build, no new errors or warnings from the templates touched in Tasks 6 and 8.

- [ ] **Step 4: Commit (only if Steps 1-3 required fixes)**

If everything was already green, there is nothing to commit here. Otherwise:

```bash
git add -A
git commit -m "fix(v58): address full-suite regressions from the PARTIAL plan reframe"
```
