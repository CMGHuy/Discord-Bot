# v152 part 4: the follower notifier, `/notify`, the full suites

**Spec:** [`docs/superpowers/specs/2026-10-09-v152-discord-notify-taken-cooldown-slash-design.md`](../specs/2026-10-09-v152-discord-notify-taken-cooldown-slash-design.md) § D1 (Copy rule, Delivery, Idempotent with its own retry, Message, `/notify`), § Testing, § Parallelisation
**Index:** [`2026-10-10-v152-discord-notify-taken-cooldown_0-index.md`](2026-10-10-v152-discord-notify-taken-cooldown_0-index.md): Global Constraints, Decisions fixed by this index, the task ledger and `## Parallelisation` live there and bind every task below.

Tasks V152-16 .. V152-18 (V152-19 and V152-20 live in [`_4b-full-suite`](2026-10-10-v152-discord-notify-taken-cooldown_4b-full-suite.md); split only to stay under 1500 lines). **V152-16, V152-17 and V152-18 are v151-gated** (index § Precondition): each starts with a precondition step and stops with `BLOCKED: v151 not merged` when it fails. V152-19 is not gated (it reads only V152-14's tables and V152-3's prefs repository). V152-20 runs last, after every other task of the plan.

Contracts consumed from earlier parts (names are the ledger's, not re-derived here):

- V152-14 (part 3) creates `swingbot/commands/scanning/follow_notify.py` with `NOTIFY_EVENTS`, `EVENT_LABELS`, `FOLLOWING_ONLY`, `WATCH_DEFAULTS`, `notify_event_for(event) -> str | None`, `kind_for(event, notify_event) -> Kind`, `mentions_user(kinds, notify_event, prefs) -> bool`, `eligible_mentions(followers, notify_event, prefs_by_user) -> list[int]`, `posts_message(notify_event, followers) -> bool`. V152-16 and V152-17 **append** to that file; they never rewrite its policy section.
- V152-13: the `near_stop` `PlanEvent` detail is `{"stop": float, "price": float, "r_dist": float}`.
- V152-3 / V152-4: `followers_repo().followers(plan_id) -> dict[int, frozenset[str]]`, `notify_prefs_repo().prefs(user_id)`, `.prefs_many(user_ids)`, `.set_pref(user_id, key, value)`; `notifications_repo().claim / mark_sent / record_failure / pending_older_than / claimed_keys`, `MAX_ATTEMPTS = 5`. `pending_older_than` returns `list_all` records: the promoted `plan_id`, `event`, `state` plus the doc keys `transition`, `detail`, `attempts`.
- V152-6: `swingbot.commands.views.chart_only_view(plan_id) -> discord.ui.View` (one persistent `ChartButton`).
- v151: `apply_chrome(..., link_base=)` sets `embed.url` to `<base>/plans/<plan_id>` when the base is valid; `config.ADMIN_PUBLIC_URL`; `tests/scanning/test_embed_plan_link.py` with its `MODULES` dict (path → count of `X.apply_chrome(... plan_id=...)` calls).

Test ids: plan ids are 36-char dashed uuids (the persistent Chart button's template rejects anything else), user ids are 18-digit snowflakes. Tests that touch a store run on the per-worker Postgres the autouse `_store_database` fixture (`tests/conftest.py:173`) provides and truncates. No pytest-asyncio: coroutines run through `asyncio.run`.

# Phase 1: the notifier (v151-gated)

### Task V152-16: **[v151]** Copy table + notify embed builder

**Model:** sonnet — a pure renderer against fixed copy and a fixed v151 call contract; no I/O, no concurrency.

**Files:**
- Modify: `swingbot/commands/scanning/follow_notify.py` (created by V152-14; append a "Copy" section below the policy section, merge the new imports into the existing import block)
- Create: `tests/commands/test_follow_notify_copy.py`
- Modify (created by v151 / V151-6): `tests/scanning/test_embed_plan_link.py` (one `MODULES` entry)

**Contract (ledger):** `FORBIDDEN_PHRASES: tuple[str, ...]`, `FOOTER = "Paper plan update, not advice."`, `COPY: dict[str, Callable]` keyed by every name in `NOTIFY_EVENTS`, `message_line(plan, notify_event: str, transition: str, detail: dict) -> str`, `build_notify_embed(plan, notify_event: str, transition: str, detail: dict) -> PushEmbed`. V152-17 sends what `build_notify_embed` returns, from a live event and from a stored `(transition, detail)` pair alike, so the builder reads only `plan`, `transition` and `detail` — never a `PlanEvent` the caller has to keep.

**Copy decisions (spec § Copy rule, made concrete here):**
- One shape for every line: `Paper plan update: <TICKER> <long|short> <event phrase>`, then — only while the plan (as loaded now) is ACTIVE or PARTIAL — ` Stop now at <resting_stop>, remaining target <target>.` The remaining target is `tp1` on an ACTIVE plan and `tp2` on a PARTIAL one (`none` when `tp2` is unset). This one suffix is what makes "a breakeven or trail move since the last message is never silent" true for every event without a per-event rule.
- The tp1 runner floor is **not** breakeven (`exit_sim.runner_floor`: two thirds of entry→TP1 locked in), so the spec's example "(breakeven)" is not printed; the stop price itself is the fact.
- Close R is the fraction-weighted `instructions.total_r(plan, exit_price)` (the same total the feed's result embed prints), signed: `+1.0R`, `0.0R`, `−1.0R` (`ui.fmt_r`'s minus).
- The push line (`push_text`, which `ui.push_kwargs` turns into `content`) **is** the copy line, so a phone preview shows the factual sentence; the title still comes from the kinds registry (`🔭 ▲ LONG AAPL · NEARING STOP`, …). The footer is the registry footer plus ` · Paper plan update, not advice.`
- `apply_chrome` is called exactly once, as `ui.apply_chrome(embed, kind=kind, plan_id=plan.plan_id, r=..., link_base=config.ADMIN_PUBLIC_URL)` — the attribute-call shape v151's AST guard counts.

- [ ] **Step 0: Precondition — v151 merged**

Run: `git grep -n "link_base" swingbot/core/presentation/components.py`
Run: `git grep -n "ADMIN_PUBLIC_URL" swingbot/config.py`
Run: `git ls-files tests/scanning/test_embed_plan_link.py`
Expected: each prints at least one line. If any prints nothing, **stop: report `BLOCKED: v151 not merged`**. Do not stub `link_base`, do not add a URL key, do not create the guard file.

Also confirm V152-14 is in: `git grep -n "def kind_for\|^NOTIFY_EVENTS" swingbot/commands/scanning/follow_notify.py` prints two lines.

- [ ] **Step 1: Write the failing copy tests**

Create `tests/commands/test_follow_notify_copy.py`:

```python
"""v152 D1: the follower-notify copy rule.

Every notify message is a factual paper-plan update: no imperative, a footer
ending "Paper plan update, not advice.", and on an ACTIVE or PARTIAL plan the
current resting stop and the remaining target. Pure: plans are built in
memory and nothing touches a store.
"""
import pytest

from swingbot import config
from swingbot.commands.scanning import follow_notify as fn
from swingbot.core import presentation as ui
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import resting_stop
from swingbot.core.presentation import components
from swingbot.core.presentation.kinds import Kind
from tests.planning.test_plan_engine_model import _plan

PID = "0f8fad5b-d9cb-469f-a165-70867728950e"
BASE = "https://swingbot.example.com"
DIRECTIONS = ("bullish", "bearish")
OPEN = (PlanStatus.ACTIVE, PlanStatus.PARTIAL)
FILLED = (PlanStatus.ACTIVE, PlanStatus.PARTIAL, PlanStatus.CLOSED)


@pytest.fixture(autouse=True)
def linked(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PUBLIC_URL", BASE)
    monkeypatch.setattr(components, "_WARNED_BASES", set())


def _plan_for(direction: str, status: str):
    s = 1 if direction == "bullish" else -1
    entry, stop, tp1, tp2 = 100.0, 100.0 - 5 * s, 100.0 + 2 * s, 100.0 + 5 * s
    partial = status == PlanStatus.PARTIAL
    legs = [{"fraction": 0.5, "exit_price": tp1, "r": 0.4, "reason": "tp1"}] if partial else []
    return _plan(plan_id=PID, direction=direction, entry_type="stop_entry",
                 trigger_price=entry, entry_price=entry if status in FILLED else None,
                 stop_loss=stop, tp1=tp1, tp2=tp2, status=status,
                 working_stop=(100.0 + 1.33 * s) if partial else None, legs_realized=legs)


def _near(plan):
    stop = resting_stop(plan)
    sign = 1 if plan.direction == "bullish" else -1
    risk = abs(plan.entry_price - plan.stop_loss)
    return {"stop": stop, "price": stop + sign * 0.21 * risk, "r_dist": 0.21}


def _close(reason: str, level: str):
    return lambda plan: {"reason": reason, "exit_price": getattr(plan, level),
                         "leg": {"fraction": 1.0, "exit_price": getattr(plan, level),
                                 "r": 0.0, "reason": reason}}


CASES = [
    ("near_stop", "near_stop", PlanStatus.ACTIVE, _near),
    ("near_stop", "near_stop", PlanStatus.PARTIAL, _near),
    ("tp1", "tp1_partial", PlanStatus.PARTIAL,
     lambda p: {"fraction": 0.5, "exit_price": p.tp1, "r": 0.4, "reason": "tp1"}),
    ("tp1", "closed", PlanStatus.CLOSED, _close("win", "tp1")),
    ("tp2", "closed", PlanStatus.CLOSED, _close("tp1_runner_tp2", "tp2")),
    ("stopped", "closed", PlanStatus.CLOSED, _close("loss", "stop_loss")),
    ("stopped", "closed", PlanStatus.CLOSED, _close("scratch", "entry_price")),
    ("stopped", "closed", PlanStatus.CLOSED, _close("tp1_runner_be", "tp1")),
    ("stopped", "closed", PlanStatus.CLOSED, _close("tp1_runner_trail", "tp1")),
    ("expired", "cancelled_expired", PlanStatus.CANCELLED, lambda p: {"bars_waited": 5}),
    ("closed_other", "closed", PlanStatus.CLOSED, _close("time_exit", "entry_price")),
    ("closed_other", "closed", PlanStatus.CLOSED, _close("stall_exit", "entry_price")),
    ("closed_other", "closed", PlanStatus.CLOSED, _close("tp1_runner_progress_stall", "tp1")),
    ("closed_other", "cancelled_invalidated", PlanStatus.CANCELLED,
     lambda p: {"live_price": p.stop_loss}),
    ("closed_other", "cancelled_risk_cap", PlanStatus.CANCELLED,
     lambda p: {"entry_price": p.trigger_price, "stop_loss": p.stop_loss,
                "planned_loss_pct": 0.09, "max_planned_loss_pct": 0.08}),
]
GRID = [(case, direction) for case in CASES for direction in DIRECTIONS]
IDS = [f"{c[0]}-{c[1]}-{c[2]}-{d}" for c, d in GRID]


def _render(case, direction):
    notify_event, transition, status, detail_fn = case
    plan = _plan_for(direction, status)
    detail = detail_fn(plan)
    return plan, fn.build_notify_embed(plan, notify_event, transition, detail)


def _texts(embed) -> list[str]:
    texts = [ui.push_kwargs(embed).get("content") or "", embed.title or "",
             embed.description or "", embed.footer.text or ""]
    for field in embed.fields:
        texts += [field.name or "", field.value or ""]
    return texts


def test_the_forbidden_list_is_the_spec_list():
    assert fn.FORBIDDEN_PHRASES == ("exit now", "move stop", "move your stop", "take profit",
                                    "sell now", "buy now", "close your", "you should")


def test_every_notify_event_has_a_template():
    assert set(fn.COPY) == set(fn.NOTIFY_EVENTS)


@pytest.mark.parametrize("case, direction", GRID, ids=IDS)
def test_no_forbidden_phrase_in_content_title_description_fields_or_footer(case, direction):
    _, embed = _render(case, direction)
    hits = [(phrase, text) for text in _texts(embed) for phrase in fn.FORBIDDEN_PHRASES
            if phrase in text.lower()]
    assert not hits


@pytest.mark.parametrize("case, direction", GRID, ids=IDS)
def test_the_footer_ends_with_the_paper_plan_line(case, direction):
    _, embed = _render(case, direction)
    assert embed.footer.text.endswith("Paper plan update, not advice.")
    assert fn.FOOTER == "Paper plan update, not advice."


@pytest.mark.parametrize("case, direction", GRID, ids=IDS)
def test_the_kind_is_never_an_imperative_label(case, direction):
    _, embed = _render(case, direction)
    assert embed.kind not in (Kind.MOVE_STOP, Kind.CANCEL)


@pytest.mark.parametrize("case, direction", GRID, ids=IDS)
def test_the_push_line_is_the_factual_copy_line(case, direction):
    _, embed = _render(case, direction)
    content = ui.push_kwargs(embed)["content"]
    assert content == embed.description
    assert content.startswith(f"Paper plan update: AAPL {'long' if direction == 'bullish' else 'short'} ")


@pytest.mark.parametrize("case, direction", GRID, ids=IDS)
def test_the_title_links_to_the_plan_page(case, direction):
    _, embed = _render(case, direction)
    assert embed.url == f"{BASE}/plans/{PID}"


OPEN_GRID = [(c, d) for c, d in GRID if c[2] in OPEN]


@pytest.mark.parametrize("case, direction", OPEN_GRID,
                         ids=[f"{c[0]}-{c[2]}-{d}" for c, d in OPEN_GRID])
def test_an_open_plan_message_states_resting_stop_and_remaining_target(case, direction):
    plan, embed = _render(case, direction)
    target = plan.tp2 if plan.status == PlanStatus.PARTIAL else plan.tp1
    assert (f"Stop now at {ui.fmt_price(resting_stop(plan))}, "
            f"remaining target {ui.fmt_price(target)}.") in embed.description


def test_a_terminal_message_carries_no_levels_suffix():
    plan = _plan_for("bullish", PlanStatus.CLOSED)
    line = fn.message_line(plan, "stopped", "closed", _close("loss", "stop_loss")(plan))
    assert "Stop now at" not in line


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_near_stop_states_the_r_distance_and_the_last_price(direction):
    plan = _plan_for(direction, PlanStatus.ACTIVE)
    detail = _near(plan)
    line = fn.message_line(plan, "near_stop", "near_stop", detail)
    assert f"is 0.21R from its stop, last {ui.fmt_price(detail['price'])}." in line
    assert f"Stop now at {ui.fmt_price(plan.stop_loss)}" in line


def test_tp1_partial_states_the_new_stop_and_tp2():
    plan = _plan_for("bullish", PlanStatus.PARTIAL)
    line = fn.message_line(plan, "tp1", "tp1_partial", {"exit_price": 102.0, "r": 0.4})
    assert line == ("Paper plan update: AAPL long reached TP1 at 102.00. "
                    "Stop now at 101.33, remaining target 105.00.")


def test_a_pre_tp1_loss_is_minus_one_r_at_the_stop():
    plan = _plan_for("bullish", PlanStatus.CLOSED)
    line = fn.message_line(plan, "stopped", "closed", _close("loss", "stop_loss")(plan))
    assert line == f"Paper plan update: AAPL long closed at its stop 95.00: {ui.fmt_r(-1.0)}."


def test_a_scratch_is_flat_at_breakeven():
    plan = _plan_for("bearish", PlanStatus.CLOSED)
    line = fn.message_line(plan, "stopped", "closed", _close("scratch", "entry_price")(plan))
    assert line == "Paper plan update: AAPL short closed at breakeven 100.00: 0.0R."


def test_a_no_tp2_win_closes_at_tp1_with_a_positive_r():
    plan = _plan_for("bullish", PlanStatus.CLOSED)
    line = fn.message_line(plan, "tp1", "closed", _close("win", "tp1")(plan))
    assert line == "Paper plan update: AAPL long closed at TP1 102.00: +0.4R."


@pytest.mark.parametrize("reason, phrase", [
    ("time_exit", "closed by time exit at"),
    ("stall_exit", "closed by stall exit at"),
    ("tp1_runner_progress_stall", "closed by structure exit at"),
    ("some_future_reason", "closed by some future reason at"),
])
def test_closed_other_names_the_exit(reason, phrase):
    plan = _plan_for("bullish", PlanStatus.CLOSED)
    assert phrase in fn.message_line(plan, "closed_other", "closed", _close(reason, "entry_price")(plan))


@pytest.mark.parametrize("transition, phrase", [
    ("cancelled_invalidated", "cancelled: invalidated before entry."),
    ("cancelled_risk_cap", "cancelled: risk cap reached."),
])
def test_closed_other_names_the_cancel(transition, phrase):
    plan = _plan_for("bullish", PlanStatus.CANCELLED)
    assert fn.message_line(plan, "closed_other", transition, {}).endswith(phrase)


def test_expired_is_one_plain_line():
    plan = _plan_for("bearish", PlanStatus.CANCELLED)
    assert fn.message_line(plan, "expired", "cancelled_expired", {"bars_waited": 5}) == \
        "Paper plan update: AAPL short expired unfilled."
```

The `0.4R` win figure is `total_r` over a pre-TP1 plan with no legs: `(102 − 100) / 5 = 0.4`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/commands/test_follow_notify_copy.py`
Expected: FAIL — `AttributeError: module 'swingbot.commands.scanning.follow_notify' has no attribute 'FORBIDDEN_PHRASES'` (and `build_notify_embed`, `COPY`, `message_line`).

- [ ] **Step 3: Add the copy section to `follow_notify.py`**

Merge these into the module's import block (keep every import V152-14 already has; do not duplicate one):

```python
from typing import Callable

from swingbot import config
from swingbot.core import presentation as ui
from swingbot.core.planning.plan_manager import PlanEvent, resting_stop
from swingbot.core.planning.plan_types import PlanStatus
from swingbot.core.presentation.instructions import total_r
```

Append below the policy section:

```python
# --------------------------------------------------------------------------
# Copy (V152-16): factual paper-plan wording, one template per notify event.
# --------------------------------------------------------------------------

#: Never in content, title, description, fields or footer (spec § Copy rule).
FORBIDDEN_PHRASES: tuple[str, ...] = (
    "exit now", "move stop", "move your stop", "take profit",
    "sell now", "buy now", "close your", "you should",
)
FOOTER = "Paper plan update, not advice."

_SIDE = {"bullish": "long", "bearish": "short"}
_OPEN_STATUSES = frozenset({PlanStatus.ACTIVE, PlanStatus.PARTIAL})
_STOP_PHRASES = {
    "loss": "at its stop",
    "scratch": "at breakeven",
    "tp1_runner_be": "at its runner stop",
    "tp1_runner_trail": "at its trailing stop",
}
_EXIT_LABELS = {
    "time_exit": "time exit",
    "stall_exit": "stall exit",
    "tp1_runner_progress_stall": "structure exit",
}
_CANCEL_LABELS = {
    "cancelled_invalidated": "invalidated before entry",
    "cancelled_risk_cap": "risk cap reached",
}


def _price(value) -> str:
    return ui.fmt_price(None if value is None else float(value))


def _signed_r(r: float) -> str:
    r = round(float(r), 1) + 0.0          # + 0.0 turns -0.0 into 0.0
    return f"+{ui.fmt_r(r)}" if r > 0 else ui.fmt_r(r)


def _close_r(plan, detail: dict) -> float:
    return total_r(plan, detail.get("exit_price"))


def _exit_tail(plan, detail: dict) -> str:
    return f"{_price(detail.get('exit_price'))}: {_signed_r(_close_r(plan, detail))}."


def _near_stop_text(plan, transition: str, detail: dict) -> str:
    return f"is {float(detail['r_dist']):.2f}R from its stop, last {_price(detail.get('price'))}."


def _tp1_text(plan, transition: str, detail: dict) -> str:
    if transition == "closed":
        return f"closed at TP1 {_exit_tail(plan, detail)}"
    return f"reached TP1 at {_price(detail.get('exit_price', plan.tp1))}."


def _tp2_text(plan, transition: str, detail: dict) -> str:
    return f"closed at TP2 {_exit_tail(plan, detail)}"


def _stopped_text(plan, transition: str, detail: dict) -> str:
    phrase = _STOP_PHRASES.get(detail.get("reason", ""), "at its stop")
    return f"closed {phrase} {_exit_tail(plan, detail)}"


def _expired_text(plan, transition: str, detail: dict) -> str:
    return "expired unfilled."


def _closed_other_text(plan, transition: str, detail: dict) -> str:
    if transition == "closed":
        reason = str(detail.get("reason", ""))
        label = _EXIT_LABELS.get(reason, reason.replace("_", " "))
        return f"closed by {label} at {_exit_tail(plan, detail)}"
    return f"cancelled: {_CANCEL_LABELS.get(transition, 'withdrawn before entry')}."


COPY: dict[str, Callable[[object, str, dict], str]] = {
    "near_stop": _near_stop_text,
    "tp1": _tp1_text,
    "tp2": _tp2_text,
    "stopped": _stopped_text,
    "expired": _expired_text,
    "closed_other": _closed_other_text,
}


def _levels_suffix(plan) -> str:
    """The resting stop and remaining target, while the plan is still open."""
    if plan.status not in _OPEN_STATUSES:
        return ""
    target = plan.tp2 if plan.status == PlanStatus.PARTIAL else plan.tp1
    return f" Stop now at {_price(resting_stop(plan))}, remaining target {_price(target)}."


def message_line(plan, notify_event: str, transition: str, detail: dict) -> str:
    """The one factual sentence a notify message carries (content and description)."""
    side = _SIDE.get(plan.direction, plan.direction)
    text = COPY[notify_event](plan, transition, detail)
    return f"Paper plan update: {plan.ticker} {side} {text}{_levels_suffix(plan)}"


def build_notify_embed(plan, notify_event: str, transition: str, detail: dict) -> ui.PushEmbed:
    """The notify embed: registry title, the copy line as push line and
    description, the plan-page link (v151) and the paper-plan footer."""
    kind = kind_for(PlanEvent(plan.plan_id, transition, dict(detail)), notify_event)
    line = message_line(plan, notify_event, transition, detail)
    embed = ui.push_embed(kind, plan.ticker, plan.direction, description=line)
    embed.push_text = line
    r = _close_r(plan, detail) if transition == "closed" else None
    ui.apply_chrome(embed, kind=kind, plan_id=plan.plan_id, r=r,
                    link_base=config.ADMIN_PUBLIC_URL)
    embed.set_footer(text=f"{embed.footer.text} · {FOOTER}")
    return embed
```

`ui.fmt_price(None)` prints the registry's absent mark, so a PARTIAL plan with no `tp2` reads `remaining target —` rather than raising.

- [ ] **Step 4: Add `follow_notify.py` to v151's link guard**

In `tests/scanning/test_embed_plan_link.py`, add one entry to the `MODULES` dict (keep the existing ones):

```python
    "swingbot/commands/scanning/follow_notify.py": 1,
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/commands/test_follow_notify_copy.py`
Expected: PASS.
Run: `python scripts/dev/testrun.py file tests/scanning/test_embed_plan_link.py`
Expected: PASS (the new parametrised case finds one `apply_chrome(plan_id=...)` call with `link_base=config.ADMIN_PUBLIC_URL`).
Run: `python scripts/dev/testrun.py file tests/commands/test_follow_notify_policy.py`
Expected: PASS (V152-14's policy tests are untouched).
Run: `python scripts/dev/testrun.py file tests/presentation/test_no_adhoc_color.py`
Expected: PASS (no `discord.Color` in `follow_notify.py`).

- [ ] **Step 6: Complexity**

Run: `pip install radon` (once), then `python -m radon cc -s -n C swingbot/commands/scanning/follow_notify.py`
Expected: no output (every function < 15).

- [ ] **Step 7: Commit**

```bash
git add swingbot/commands/scanning/follow_notify.py tests/commands/test_follow_notify_copy.py tests/scanning/test_embed_plan_link.py
git commit -m "feat(v152): follower-notify copy table and embed builder, linked per v151 (V152-16)"
```

### Task V152-17: **[v151]** Delivery: claim, send, mention, retry sweep

**Model:** opus — idempotency and retry semantics across Discord sends and database claims, where a wrong ordering either drops a message or posts it twice.

**Swallowed-error ratchet (audit 2026-10-10):** this task adds `except Exception` handlers. If `tests/infra/test_swallowed_ratchet.py` exists (v148 merged), apply the index Global Constraints bullet "Swallowed-error ratchet (v148)" to every one that does not re-raise (`except Exception as exc:` + `swallowed(log, "ops.<module>.<function>", exc, level=logging.DEBUG)` first, keep the existing log line, unique tag) and run `python scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py` before the commit. Otherwise write them as planned.

**Files:**
- Modify: `swingbot/commands/scanning/follow_notify.py` (append a "Delivery" section below V152-16's copy section; merge the new imports)
- Create: `tests/commands/test_follow_notify_delivery.py`

**Contract (ledger):** `async notify_followers(bot, events: list[PlanEvent]) -> int` (messages sent), `async retry_pending_notifications(bot, now: dt.datetime | None = None) -> int`, the module cache `_CLAIMED: set[tuple[str, str]] | None`, `_notify_channel(bot)`. V152-18 calls the two coroutines from `loops.py`.

**Ordering, and why (spec § Idempotent, with its own retry; index decisions 11–12):**
1. Map the event (`notify_event_for`); unmapped → nothing.
2. Cache check: a key already in `_CLAIMED` returns before any DB call.
3. Load the plan and its audience (followers + prefs) in `to_thread`; a missing plan → nothing; `posts_message` false (`closed_other` without a Following follower) → nothing, **no claim**, so a later follow still lets the next re-fired event through.
4. Claim `(plan_id, notify_event)` with `doc = {"transition", "detail"}` (detail keys starting `_` dropped — they are manager bookkeeping, e.g. `_terminal_persisted`). Zero rows → someone claimed it: cache the key, send nothing.
5. Send. Failure → `record_failure` (attempts + 1; `failed` at `MAX_ATTEMPTS` with one WARNING); the row stays `pending` for the sweep. Success → `mark_sent`; a failed `mark_sent` leaves the row `pending`, so the sweep re-sends once — the spec's "at most one duplicate".
6. The sweep re-sends `pending` rows whose `updated_at` is older than 60 s, from the stored `(transition, detail)` and the plan **as it is now**. `record_failure` bumps `updated_at`, so attempts are at least a minute apart.

Empty `DISCORD_CHANNEL_NOTIFY_ID`, a non-numeric id, or a channel the bot cannot see → both coroutines return 0 before any DB call: nothing is sent and nothing is claimed. The channel is resolved with `bot.get_channel(int(...))` and never passed through `silence()`.

- [ ] **Step 0: Precondition — v151 merged and V152-16 in**

Run: `git grep -n "link_base" swingbot/core/presentation/components.py`
Run: `git grep -n "ADMIN_PUBLIC_URL" swingbot/config.py`
Run: `git ls-files tests/scanning/test_embed_plan_link.py`
Expected: each prints at least one line; otherwise **stop: report `BLOCKED: v151 not merged`**.
Run: `git grep -n "def build_notify_embed" swingbot/commands/scanning/follow_notify.py` and `git grep -n "def chart_only_view" swingbot/commands/views.py`
Expected: one line each (V152-16 and V152-6 are committed).

- [ ] **Step 1: Write the failing delivery tests**

Create `tests/commands/test_follow_notify_delivery.py`:

```python
"""v152 D1: follower notifications -- claim, send, mention, retry.

Runs on the per-worker test Postgres (tests/conftest.py _store_database): the
plans, followers, prefs and claims are real rows. Discord is a fake channel.
"""
import asyncio
import datetime as dt
import logging

import pytest

from swingbot import config
from swingbot.commands import views
from swingbot.commands.scanning import follow_notify as fn
from swingbot.core.db.repositories.followers import followers_repo
from swingbot.core.db.repositories.notifications import MAX_ATTEMPTS, notifications_repo
from swingbot.core.db.repositories.notify_prefs import notify_prefs_repo
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.planning.plan_store import PlanStore
from tests.planning.test_plan_engine_model import _plan

PID = "0f8fad5b-d9cb-469f-a165-70867728950e"
PID2 = "7c9e6679-7425-40de-944b-e07fc1f90ae7"
MISSING = "16fd2706-8baf-433b-82eb-8c7fada847da"
NOTIFY_ID = 112233445566778899
FOLLOWER = 123456789012345678
WATCHER = 876543210987654321
TP1 = {"fraction": 0.5, "exit_price": 102.0, "r": 0.4, "reason": "tp1",
       "closed_at": "2026-10-12T15:00:00+00:00"}


class Chan:
    def __init__(self, fail: int = 0):
        self.sent: list[dict] = []
        self.fail = fail

    async def send(self, **kwargs):
        if self.fail:
            self.fail -= 1
            raise RuntimeError("discord down")
        self.sent.append(kwargs)
        return object()


class Bot:
    def __init__(self, chan):
        self.chan = chan

    def get_channel(self, channel_id):
        return self.chan if channel_id == NOTIFY_ID else None


@pytest.fixture(autouse=True)
def notify_on(monkeypatch):
    monkeypatch.setattr(config, "DISCORD_CHANNEL_NOTIFY_ID", str(NOTIFY_ID))
    monkeypatch.setattr(config, "ADMIN_PUBLIC_URL", "")
    monkeypatch.setattr(fn, "_CLAIMED", None)


def _store(status: str, plan_id: str = PID):
    partial = status == PlanStatus.PARTIAL
    plan = _plan(plan_id=plan_id, entry_type="stop_entry", trigger_price=100.0,
                 entry_price=100.0, status=status,
                 working_stop=101.33 if partial else None,
                 legs_realized=[dict(TP1)] if partial else [])
    PlanStore().add(plan)
    return plan


def _follow(user_id: int, kind: str, plan_id: str = PID) -> None:
    followers_repo().add(plan_id, user_id, kind, status_at_press="ACTIVE")


def _rows() -> dict:
    return {(r["plan_id"], r["event"]): r for r in notifications_repo().list_all()}


def _notify(bot, *events) -> int:
    return asyncio.run(fn.notify_followers(bot, list(events)))


def _sweep(bot, minutes: float = 2.0) -> int:
    now = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes)
    return asyncio.run(fn.retry_pending_notifications(bot, now=now))


def _tp1_event(plan_id: str = PID) -> PlanEvent:
    return PlanEvent(plan_id, "tp1_partial", dict(TP1))


@pytest.mark.parametrize("raw", ["", "   ", "not-a-number"])
def test_no_usable_channel_key_sends_and_claims_nothing(monkeypatch, raw):
    monkeypatch.setattr(config, "DISCORD_CHANNEL_NOTIFY_ID", raw)
    _store(PlanStatus.PARTIAL)
    chan = Chan()
    assert _notify(Bot(chan), _tp1_event()) == 0
    assert _sweep(Bot(chan)) == 0
    assert chan.sent == [] and _rows() == {}


def test_a_channel_the_bot_cannot_see_sends_and_claims_nothing(monkeypatch):
    monkeypatch.setattr(config, "DISCORD_CHANNEL_NOTIFY_ID", "999999999999999999")
    _store(PlanStatus.PARTIAL)
    chan = Chan()
    assert _notify(Bot(chan), _tp1_event()) == 0
    assert chan.sent == [] and _rows() == {}


def test_a_following_follower_is_mentioned_and_the_claim_is_marked_sent():
    _store(PlanStatus.PARTIAL)
    _follow(FOLLOWER, "taken")
    chan = Chan()
    assert _notify(Bot(chan), _tp1_event()) == 1
    [kwargs] = chan.sent
    assert kwargs["content"].endswith(f"<@{FOLLOWER}>")
    assert kwargs["content"].startswith("Paper plan update: AAPL long reached TP1 at 102.00.")
    mentions = kwargs["allowed_mentions"]
    assert [user.id for user in mentions.users] == [FOLLOWER]
    assert mentions.roles is False and mentions.everyone is False
    assert not kwargs.get("silent")
    assert _rows()[(PID, "tp1")]["state"] == "sent"


def test_the_message_carries_only_the_persistent_chart_button():
    _store(PlanStatus.PARTIAL)
    chan = Chan()
    _notify(Bot(chan), _tp1_event())
    view = chan.sent[0]["view"]
    assert view.timeout is None
    assert [type(item) for item in view.children] == [views.ChartButton]


def test_no_follower_posts_silently_without_a_mention():
    _store(PlanStatus.PARTIAL)
    chan = Chan()
    assert _notify(Bot(chan), _tp1_event()) == 1
    [kwargs] = chan.sent
    assert kwargs["silent"] is True
    assert kwargs["allowed_mentions"].users is False
    assert "<@" not in kwargs["content"]


def test_a_second_identical_event_posts_nothing_even_after_a_restart(monkeypatch):
    _store(PlanStatus.PARTIAL)
    chan = Chan()
    assert _notify(Bot(chan), _tp1_event()) == 1
    assert _notify(Bot(chan), _tp1_event()) == 0
    monkeypatch.setattr(fn, "_CLAIMED", None)          # a restart: the cache reseeds from the table
    assert _notify(Bot(chan), _tp1_event()) == 0
    assert len(chan.sent) == 1


def test_a_cached_claim_costs_no_database_call(monkeypatch):
    _store(PlanStatus.PARTIAL)
    chan = Chan()
    _notify(Bot(chan), _tp1_event())
    calls = []
    monkeypatch.setattr(fn, "_load_plan", lambda plan_id: calls.append(("plan", plan_id)))
    monkeypatch.setattr(fn, "_claim", lambda *a: calls.append(("claim", a)) or True)
    assert _notify(Bot(chan), _tp1_event()) == 0
    assert calls == []


def test_closed_other_needs_a_following_follower_and_mentions_only_them(monkeypatch):
    _store(PlanStatus.CLOSED)
    _follow(WATCHER, "watch")
    event = PlanEvent(PID, "closed", {"reason": "stall_exit", "exit_price": 101.0,
                                      "leg": {"fraction": 1.0, "exit_price": 101.0,
                                              "r": 0.2, "reason": "stall_exit"},
                                      "_terminal_persisted": True})
    chan = Chan()
    assert _notify(Bot(chan), event) == 0
    assert chan.sent == [] and _rows() == {}            # not posted, not claimed
    _follow(FOLLOWER, "taken")
    assert _notify(Bot(chan), event) == 1
    [kwargs] = chan.sent
    assert f"<@{FOLLOWER}>" in kwargs["content"] and f"<@{WATCHER}>" not in kwargs["content"]
    assert [user.id for user in kwargs["allowed_mentions"].users] == [FOLLOWER]
    assert "_terminal_persisted" not in _rows()[(PID, "closed_other")]["detail"]


def test_watch_only_near_stop_is_off_by_default_and_a_toggle_turns_it_on():
    _store(PlanStatus.ACTIVE)
    _store(PlanStatus.ACTIVE, plan_id=PID2)
    _follow(WATCHER, "watch")
    _follow(WATCHER, "watch", plan_id=PID2)
    near = {"stop": 95.0, "price": 96.05, "r_dist": 0.21}
    chan = Chan()
    assert _notify(Bot(chan), PlanEvent(PID, "near_stop", dict(near))) == 1
    assert chan.sent[0]["silent"] is True                 # posts, mentions nobody
    notify_prefs_repo().set_pref(WATCHER, "near_stop", True)
    assert _notify(Bot(chan), PlanEvent(PID2, "near_stop", dict(near))) == 1
    assert chan.sent[1]["content"].endswith(f"<@{WATCHER}>")


def test_watch_mode_silent_drops_the_watch_mention_but_still_posts():
    _store(PlanStatus.PARTIAL)
    _follow(WATCHER, "watch")
    notify_prefs_repo().set_pref(WATCHER, "watch_mode", "silent")
    chan = Chan()
    assert _notify(Bot(chan), _tp1_event()) == 1
    assert chan.sent[0]["silent"] is True


def test_a_failed_send_stays_pending_and_the_sweep_retries_it():
    _store(PlanStatus.PARTIAL)
    chan = Chan(fail=1)
    assert _notify(Bot(chan), _tp1_event()) == 0
    row = _rows()[(PID, "tp1")]
    assert row["state"] == "pending" and row["attempts"] == 1
    assert _sweep(Bot(chan), minutes=0) == 0              # younger than a minute: left alone
    assert _sweep(Bot(chan)) == 1
    assert _rows()[(PID, "tp1")]["state"] == "sent"
    assert chan.sent[0]["content"].startswith("Paper plan update: AAPL long reached TP1")


def test_five_failed_attempts_mark_the_row_failed_with_a_warning(caplog):
    _store(PlanStatus.PARTIAL)
    chan = Chan(fail=MAX_ATTEMPTS)
    _notify(Bot(chan), _tp1_event())
    with caplog.at_level(logging.WARNING, logger=fn.__name__):
        for attempt in range(2, MAX_ATTEMPTS + 1):
            assert _sweep(Bot(chan), minutes=2 * attempt) == 0
    assert _rows()[(PID, "tp1")]["state"] == "failed"
    assert any("giving up" in r.getMessage() for r in caplog.records)
    assert _sweep(Bot(chan), minutes=60) == 0             # failed rows are never retried
    assert chan.sent == []


def test_a_lost_sent_write_re_sends_once_then_settles(monkeypatch):
    _store(PlanStatus.PARTIAL)
    chan = Chan()

    def broken(plan_id, notify_event):
        raise RuntimeError("db blip")

    monkeypatch.setattr(fn, "_mark_sent", broken)
    assert _notify(Bot(chan), _tp1_event()) == 1
    assert _rows()[(PID, "tp1")]["state"] == "pending"
    monkeypatch.undo()
    monkeypatch.setattr(config, "DISCORD_CHANNEL_NOTIFY_ID", str(NOTIFY_ID))
    monkeypatch.setattr(config, "ADMIN_PUBLIC_URL", "")
    assert _sweep(Bot(chan)) == 1
    assert _sweep(Bot(chan), minutes=10) == 0
    assert len(chan.sent) == 2 and chan.sent[0]["content"] == chan.sent[1]["content"]
    assert _rows()[(PID, "tp1")]["state"] == "sent"


def test_unmapped_events_and_unknown_plans_send_nothing_and_do_not_stop_the_batch():
    _store(PlanStatus.PARTIAL)
    chan = Chan()
    events = [PlanEvent(PID, "be_moved", {"working_stop": 100.0, "live_price": 101.0}),
              PlanEvent(MISSING, "tp1_partial", dict(TP1)),
              _tp1_event()]
    assert _notify(Bot(chan), *events) == 1
    assert set(_rows()) == {(PID, "tp1")}
```

`monkeypatch.undo()` in `test_a_lost_sent_write_re_sends_once_then_settles` also reverts the autouse fixture's patches, so the test re-applies the two config values; `_CLAIMED` going back to `None` is harmless (the sweep never reads it).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/commands/test_follow_notify_delivery.py`
Expected: FAIL — `AttributeError: module 'swingbot.commands.scanning.follow_notify' has no attribute '_CLAIMED'` from the fixture.

- [ ] **Step 3: Add the delivery section to `follow_notify.py`**

Merge these into the import block (keep existing ones; add `import logging` and `log = logging.getLogger(__name__)` below the imports if the module has no `log` yet):

```python
import asyncio
import datetime as dt
import logging

import discord

from swingbot.core.db.repositories.notifications import MAX_ATTEMPTS
from swingbot.core.infra.posted_log import log_posted
```

Append below the copy section:

```python
# --------------------------------------------------------------------------
# Delivery (V152-17): claim, send, mention, retry sweep.
# --------------------------------------------------------------------------

#: A pending row is re-sent once it has sat this long since its last attempt.
RETRY_AFTER = dt.timedelta(seconds=60)

#: (plan_id, notify_event) keys already claimed, in any state. Seeded once
#: from plan_notifications; after the first claim a near-stop that fires on
#: every in-band tick costs one set lookup and no database call.
_CLAIMED: set[tuple[str, str]] | None = None
_BAD_CHANNEL_IDS: set[str] = set()


def _notify_channel(bot):
    """The notify channel, or None when D1 is off or the id is unusable.
    Never wrapped in silence(): the mentions must ping."""
    raw = str(getattr(config, "DISCORD_CHANNEL_NOTIFY_ID", "") or "").strip()
    if not raw:
        return None
    try:
        return bot.get_channel(int(raw))
    except (TypeError, ValueError):
        if raw not in _BAD_CHANNEL_IDS:
            _BAD_CHANNEL_IDS.add(raw)
            log.warning("follow_notify: DISCORD_CHANNEL_NOTIFY_ID=%r is not a channel id; "
                        "follower notifications are off", raw)
        return None


# Sync store calls: always run through asyncio.to_thread.

def _load_plan(plan_id: str):
    from swingbot.core.planning.plan_store import PlanStore
    return PlanStore().get(plan_id)


def _audience(plan_id: str) -> tuple[dict, dict]:
    from swingbot.core.db.repositories.followers import followers_repo
    from swingbot.core.db.repositories.notify_prefs import notify_prefs_repo
    followers = followers_repo().followers(plan_id)
    prefs = notify_prefs_repo().prefs_many(list(followers)) if followers else {}
    return followers, prefs


def _claim(plan_id: str, notify_event: str, doc: dict) -> bool:
    from swingbot.core.db.repositories.notifications import notifications_repo
    return notifications_repo().claim(plan_id, notify_event, doc)


def _mark_sent(plan_id: str, notify_event: str) -> None:
    from swingbot.core.db.repositories.notifications import notifications_repo
    notifications_repo().mark_sent(plan_id, notify_event)


def _record_failure(plan_id: str, notify_event: str) -> str:
    from swingbot.core.db.repositories.notifications import notifications_repo
    return notifications_repo().record_failure(plan_id, notify_event)


def _pending_rows(cutoff: dt.datetime) -> list[dict]:
    from swingbot.core.db.repositories.notifications import notifications_repo
    return notifications_repo().pending_older_than(cutoff)


def _claimed_keys() -> set[tuple[str, str]]:
    from swingbot.core.db.repositories.notifications import notifications_repo
    return notifications_repo().claimed_keys()


async def _claimed_cache() -> set[tuple[str, str]]:
    global _CLAIMED
    if _CLAIMED is None:
        try:
            _CLAIMED = set(await asyncio.to_thread(_claimed_keys))
        except Exception:
            log.warning("follow_notify: could not seed the claim cache; "
                        "claims still dedupe in the database", exc_info=True)
            _CLAIMED = set()
    return _CLAIMED


def _stored_detail(detail: dict) -> dict:
    """The event detail as the claim stores it: manager bookkeeping keys dropped."""
    return {key: value for key, value in (detail or {}).items() if not str(key).startswith("_")}


def _send_kwargs(embed, mentions: list[int], plan_id: str) -> dict:
    """push_kwargs plus the Chart button, and either the mentions or silent."""
    from swingbot.commands.views import chart_only_view
    kwargs = ui.push_kwargs(embed)
    kwargs["view"] = chart_only_view(plan_id)
    if not mentions:
        kwargs.update(silent=True, allowed_mentions=discord.AllowedMentions.none())
        return kwargs
    tags = " ".join(f"<@{user_id}>" for user_id in mentions)
    kwargs["content"] = f"{kwargs.get('content', '')}\n{tags}".strip()
    kwargs["allowed_mentions"] = discord.AllowedMentions(
        users=[discord.Object(id=user_id) for user_id in mentions], roles=False, everyone=False)
    return kwargs


async def _note_failure(plan_id: str, notify_event: str) -> None:
    try:
        state = await asyncio.to_thread(_record_failure, plan_id, notify_event)
    except Exception:
        log.warning("follow_notify: could not count the failed attempt for %s on plan %s",
                    notify_event, plan_id, exc_info=True)
        return
    if state == "failed":
        log.warning("follow_notify: giving up on %s for plan %s after %d attempts",
                    notify_event, plan_id, MAX_ATTEMPTS)


async def _send_and_settle(channel, plan, notify_event: str, transition: str,
                           detail: dict, audience: tuple[dict, dict]) -> int:
    """Send one claimed message; mark it sent, or count the failed attempt."""
    followers, prefs = audience
    try:
        embed = build_notify_embed(plan, notify_event, transition, detail)
        mentions = eligible_mentions(followers, notify_event, prefs)
        await channel.send(**_send_kwargs(embed, mentions, plan.plan_id))
    except Exception:
        log.warning("follow_notify: %s for plan %s not sent; the retry sweep will try again",
                    notify_event, plan.plan_id, exc_info=True)
        await _note_failure(plan.plan_id, notify_event)
        return 0
    log_posted(embed, plan.ticker, channel)
    try:
        await asyncio.to_thread(_mark_sent, plan.plan_id, notify_event)
    except Exception:
        log.warning("follow_notify: %s for plan %s was sent but not marked sent; "
                    "the sweep may send it once more", notify_event, plan.plan_id, exc_info=True)
    return 1


async def _deliver(channel, claimed: set, event: PlanEvent) -> int:
    notify_event = notify_event_for(event)
    key = (event.plan_id, notify_event)
    if notify_event is None or key in claimed:
        return 0
    plan = await asyncio.to_thread(_load_plan, event.plan_id)
    if plan is None:
        return 0
    audience = await asyncio.to_thread(_audience, event.plan_id)
    if not posts_message(notify_event, audience[0]):
        return 0
    doc = {"transition": event.transition, "detail": _stored_detail(event.detail)}
    inserted = await asyncio.to_thread(_claim, event.plan_id, notify_event, doc)
    claimed.add(key)
    if not inserted:
        return 0
    return await _send_and_settle(channel, plan, notify_event, event.transition,
                                  event.detail, audience)


async def notify_followers(bot, events: list[PlanEvent]) -> int:
    """Post each mappable plan event to the notify channel once; returns messages sent.

    Independent of the execution feed: loops._post_plan_events calls it
    whatever the feed did. One event's failure never stops the batch."""
    channel = _notify_channel(bot)
    if channel is None or not events:
        return 0
    claimed = await _claimed_cache()
    sent = 0
    for event in events:
        try:
            sent += await _deliver(channel, claimed, event)
        except Exception:
            log.warning("follow_notify: could not handle %s for plan %s",
                        event.transition, event.plan_id, exc_info=True)
    return sent


async def _retry_row(channel, row: dict) -> int:
    plan = await asyncio.to_thread(_load_plan, row["plan_id"])
    if plan is None:
        return 0
    audience = await asyncio.to_thread(_audience, row["plan_id"])
    return await _send_and_settle(channel, plan, row["event"], row.get("transition", ""),
                                  row.get("detail") or {}, audience)


async def retry_pending_notifications(bot, now: dt.datetime | None = None) -> int:
    """Re-send pending claims older than RETRY_AFTER; returns messages sent.
    Runs once per trade_monitor tick, whether or not the tick had events."""
    channel = _notify_channel(bot)
    if channel is None:
        return 0
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        rows = await asyncio.to_thread(_pending_rows, now - RETRY_AFTER)
    except Exception:
        log.warning("follow_notify: could not read pending notifications", exc_info=True)
        return 0
    sent = 0
    for row in rows:
        try:
            sent += await _retry_row(channel, row)
        except Exception:
            log.warning("follow_notify: retry of %s for plan %s failed",
                        row.get("event"), row.get("plan_id"), exc_info=True)
    return sent
```

`_deliver` adds the key to the cache whether or not this call inserted it, so the cache always mirrors the table after a claim attempt.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/commands/test_follow_notify_delivery.py`
Expected: PASS. (Needs `db-test` up; a store test without it skips with the start command — start it, a skip is not a pass.)
Run: `python scripts/dev/testrun.py file tests/commands/test_follow_notify_copy.py`, then the same for `tests/commands/test_follow_notify_policy.py` and `tests/scanning/test_embed_plan_link.py`
Expected: PASS (the delivery section adds no `apply_chrome` call; the guard count stays 1).

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C swingbot/commands/scanning/follow_notify.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/commands/scanning/follow_notify.py tests/commands/test_follow_notify_delivery.py
git commit -m "feat(v152): follower notifications -- idempotent claim, mentions, retry sweep (V152-17)"
```

### Task V152-18: **[v151]** D1 `loops.py`: feed and notifier independent, per-tick sweep

**Model:** sonnet — a contained split of one coroutine plus one call, against fixed callee contracts.

**Swallowed-error ratchet (audit 2026-10-10):** this task adds `except Exception` handlers. If `tests/infra/test_swallowed_ratchet.py` exists (v148 merged), apply the index Global Constraints bullet "Swallowed-error ratchet (v148)" to every one that does not re-raise (`except Exception as exc:` + `swallowed(log, "ops.<module>.<function>", exc, level=logging.DEBUG)` first, keep the existing log line, unique tag) and run `python scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py` before the commit. Otherwise write them as planned.

**Files:**
- Modify: `swingbot/commands/scanning/loops.py` (`_post_plan_events` at `:489-503` becomes `_post_feed` + `_post_plan_events`; new `_retry_notifications` after it; one call in `trade_monitor` after the `if plan_events:` block at `:620-621`)
- Create: `tests/commands/test_loops_follow_notify.py`

**Contract (ledger):** `loops._post_feed(plan_events) -> list` (async; the feed's deliveries, `[]` when it raised), `_post_plan_events` = feed → notifier in its own `try` → ack when there were deliveries, `loops._retry_notifications() -> None` (async) called on every `trade_monitor` tick. V152-15 edited `_session_scan_tick`, `daily_recap` and added `_post_cooldown_note` / `_prune_alert_posts` in this file; this task touches none of them.

**Why the order:** the spec makes the notifier independent of the feed (`loops.py:494-498` early returns no longer gate it), and keeps the ack last so a feed delivery is recorded only after it reached Discord, exactly as today. The sweep sits **outside** `if plan_events:` (index decision 12): a tick with no events is exactly when a failed send from an earlier tick still needs retrying. With `DISCORD_CHANNEL_NOTIFY_ID` empty both follow-notify coroutines return before any DB call (V152-17), so every existing `trade_monitor` test keeps its behaviour.

- [ ] **Step 0: Precondition — v151 merged and V152-17 in**

Run: `git grep -n "link_base" swingbot/core/presentation/components.py`
Run: `git grep -n "ADMIN_PUBLIC_URL" swingbot/config.py`
Run: `git ls-files tests/scanning/test_embed_plan_link.py`
Expected: each prints at least one line; otherwise **stop: report `BLOCKED: v151 not merged`**.
Run: `git grep -n "async def notify_followers\|async def retry_pending_notifications" swingbot/commands/scanning/follow_notify.py`
Expected: two lines (V152-17 committed). Run: `git grep -n "apply_cooldown=True" swingbot/commands/scanning/loops.py`
Expected: one line (V152-15 committed; same file).

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_loops_follow_notify.py`:

```python
"""v152 D1: trade_monitor feeds the execution feed and the follower notifier
independently, and sweeps failed follower notifications on every tick.

No pytest-asyncio in this repo -- coroutines are driven with asyncio.run().
"""
import asyncio
import logging

from swingbot.commands import scanning as scanning_mod
from swingbot.commands.scanning import loops
from swingbot.core.planning.plan_manager import Delivery, PlanEvent
from swingbot.core.scanning import engine as scan_engine

PID = "0f8fad5b-d9cb-469f-a165-70867728950e"
EVENT = PlanEvent(PID, "tp1_partial", {"exit_price": 102.0, "r": 0.4})
DELIVERED = [Delivery(PID, "notice", "tp1_partial")]


def _wire(monkeypatch, calls: list, *, feed=None, feed_raises=False, notify_raises=False):
    async def fake_feed(bot, events):
        calls.append("feed")
        if feed_raises:
            raise RuntimeError("feed down")
        return feed

    async def fake_notify(bot, events):
        calls.append("notify")
        assert events == [EVENT]
        if notify_raises:
            raise RuntimeError("notifier down")
        return 1

    acked = []

    def fake_ack(deliveries):
        calls.append("ack")
        acked.append(deliveries)

    monkeypatch.setattr("swingbot.core.scanning.embeds.notify_plan_events", fake_feed)
    monkeypatch.setattr("swingbot.commands.scanning.follow_notify.notify_followers", fake_notify)
    monkeypatch.setattr("swingbot.core.planning.plan_manager.ack_notified", fake_ack)
    return acked


def test_feed_then_notifier_then_ack(monkeypatch):
    calls = []
    acked = _wire(monkeypatch, calls, feed=DELIVERED)
    asyncio.run(loops._post_plan_events([EVENT]))
    assert calls == ["feed", "notify", "ack"]
    assert acked == [DELIVERED]


def test_a_raising_feed_still_runs_the_notifier_and_acks_nothing(monkeypatch, caplog):
    calls = []
    acked = _wire(monkeypatch, calls, feed_raises=True)
    with caplog.at_level(logging.WARNING, logger=loops.__name__):
        asyncio.run(loops._post_plan_events([EVENT]))
    assert calls == ["feed", "notify"]
    assert acked == []
    assert any("failed to post plan events" in r.getMessage() for r in caplog.records)


def test_a_feed_that_delivers_nothing_still_runs_the_notifier(monkeypatch):
    calls = []
    acked = _wire(monkeypatch, calls, feed=[])
    asyncio.run(loops._post_plan_events([EVENT]))
    assert calls == ["feed", "notify"]
    assert acked == []


def test_a_raising_notifier_never_costs_the_feed_its_ack(monkeypatch, caplog):
    calls = []
    acked = _wire(monkeypatch, calls, feed=DELIVERED, notify_raises=True)
    with caplog.at_level(logging.WARNING, logger=loops.__name__):
        asyncio.run(loops._post_plan_events([EVENT]))
    assert calls == ["feed", "notify", "ack"]
    assert acked == [DELIVERED]
    assert any("follower notifications failed" in r.getMessage() for r in caplog.records)


def test_post_feed_returns_the_deliveries_or_an_empty_list(monkeypatch):
    calls = []
    _wire(monkeypatch, calls, feed=DELIVERED)
    assert asyncio.run(loops._post_feed([EVENT])) == DELIVERED
    _wire(monkeypatch, calls, feed_raises=True)
    assert asyncio.run(loops._post_feed([EVENT])) == []


def _quiet_tick(monkeypatch, tick_events):
    monkeypatch.setattr(scan_engine, "is_scan_running", lambda: False)
    monkeypatch.setattr(loops.trade_log, "get_trades", lambda status=None, limit=None: [])
    monkeypatch.setattr("swingbot.core.planning.plan_manager.run_manager_tick", lambda: list(tick_events))


def test_every_tick_sweeps_pending_notifications_even_without_events(monkeypatch):
    _quiet_tick(monkeypatch, [])
    sweeps = []

    async def fake_sweep(bot, now=None):
        sweeps.append(bot)
        return 0

    monkeypatch.setattr("swingbot.commands.scanning.follow_notify.retry_pending_notifications", fake_sweep)
    asyncio.run(scanning_mod.trade_monitor.coro())
    assert sweeps == [loops.bot]


def test_a_tick_with_events_posts_them_and_sweeps_once(monkeypatch):
    _quiet_tick(monkeypatch, [EVENT])
    calls = []
    _wire(monkeypatch, calls, feed=[])

    async def fake_sweep(bot, now=None):
        calls.append("sweep")
        return 0

    monkeypatch.setattr("swingbot.commands.scanning.follow_notify.retry_pending_notifications", fake_sweep)
    asyncio.run(scanning_mod.trade_monitor.coro())
    assert calls == ["feed", "notify", "sweep"]


def test_a_raising_sweep_never_escapes_the_monitor(monkeypatch, caplog):
    _quiet_tick(monkeypatch, [])

    async def broken_sweep(bot, now=None):
        raise RuntimeError("db down")

    monkeypatch.setattr("swingbot.commands.scanning.follow_notify.retry_pending_notifications", broken_sweep)
    with caplog.at_level(logging.WARNING, logger=loops.__name__):
        asyncio.run(scanning_mod.trade_monitor.coro())
    assert any("retry sweep failed" in r.getMessage() for r in caplog.records)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/commands/test_loops_follow_notify.py`
Expected: FAIL — `test_a_raising_feed_still_runs_the_notifier_and_acks_nothing` sees `calls == ["feed"]` (today's early return), `_post_feed` / the sweep tests raise `AttributeError` or record no sweep.

- [ ] **Step 3: Split `_post_plan_events` and add the sweep helper**

In `swingbot/commands/scanning/loops.py`, replace the whole `async def _post_plan_events` (`:489-503`) with:

```python
async def _post_feed(plan_events) -> list:
    """Post plan events to the execution feed; the deliveries that reached
    Discord, or [] when the feed raised."""
    from swingbot.core.scanning.embeds import notify_plan_events
    try:
        return list(await notify_plan_events(bot, plan_events) or [])
    except Exception as exc:
        log.warning("trade_monitor: failed to post plan events: %s", exc, exc_info=True)
        return []


async def _post_plan_events(plan_events) -> None:
    """The execution feed, then the follower notifier whatever the feed did
    (v152 D1), then record only the feed deliveries that reached Discord."""
    from swingbot.core.planning import plan_manager
    from .follow_notify import notify_followers
    deliveries = await _post_feed(plan_events)
    try:
        await notify_followers(bot, plan_events)
    except Exception as exc:
        log.warning("trade_monitor: follower notifications failed: %s", exc, exc_info=True)
    if not deliveries:
        return
    try:
        await asyncio.to_thread(plan_manager.ack_notified, deliveries)
    except Exception as exc:
        log.warning("trade_monitor: could not record feed deliveries (they will be re-sent): %s", exc, exc_info=True)


async def _retry_notifications() -> None:
    """Re-send follower notifications whose send failed (v152 D1). Every tick."""
    from .follow_notify import retry_pending_notifications
    try:
        await retry_pending_notifications(bot)
    except Exception as exc:
        log.warning("trade_monitor: notification retry sweep failed: %s", exc, exc_info=True)
```

The imports stay lazy, as today's body had them, so the tests' module-attribute patches reach the call.

- [ ] **Step 4: Call the sweep on every tick**

In `trade_monitor`, directly after

```python
    if plan_events:
        await _post_plan_events(plan_events)
```

add, at the same indentation as the `if` (outside it):

```python
    await _retry_notifications()
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/commands/test_loops_follow_notify.py`
Expected: PASS.
Run: `python scripts/dev/testrun.py file tests/commands/test_trade_monitor_task.py`
Expected: PASS (`test_trade_monitor_acknowledges_feed_deliveries` still sees `acked == [delivered]`; with the notify key empty the real notifier and sweep return 0 without a DB call).
Run: `python scripts/dev/testrun.py file tests/commands/test_loops_cooldown.py`, then the same for `tests/commands/test_store_write_halt.py`
Expected: PASS (V152-15's wiring and the halt re-post are untouched).
Run: `python scripts/dev/testrun.py changed --dry-run` and run any further listed file that imports `loops`.

- [ ] **Step 6: Complexity**

Run: `python -m radon cc -s -n C swingbot/commands/scanning/loops.py`
Expected: `_post_feed`, `_post_plan_events` and `_retry_notifications` are not listed; `trade_monitor`'s figure is unchanged from the base commit (before the commit HEAD is the base: `git show HEAD:swingbot/commands/scanning/loops.py > /tmp/loops_base.py && python -m radon cc -s /tmp/loops_base.py | grep trade_monitor` — the call adds no branch). Never `git stash` in a shared worktree.

- [ ] **Step 7: Commit**

```bash
git add swingbot/commands/scanning/loops.py tests/commands/test_loops_follow_notify.py
git commit -m "feat(v152): trade_monitor runs the follower notifier independent of the feed, sweeps retries per tick (V152-18)"
```
