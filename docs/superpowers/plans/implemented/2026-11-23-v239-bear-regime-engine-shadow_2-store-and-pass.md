# v239 — Bear-regime engine (shadow): Part 2 — config, store, notice, pass

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V239-7" -A 400 <this file>`); never read the file whole.

**Spec:** [2026-11-23-v239-bear-regime-engine-shadow-design.md](../specs/2026-11-23-v239-bear-regime-engine-shadow-design.md) — its `## Code reconciliation` section overrides the text above it.
**Index:** [2026-11-23-v239-bear-regime-engine-shadow_0-index.md](2026-11-23-v239-bear-regime-engine-shadow_0-index.md) — Global Constraints, Parallelisation, the task ledger and the eight "Decisions this index fixes" apply to every task here.

Tasks: V239-5 (config field, mode reader), V239-6 (table, Alembic `v239_001`, insert-once repository), V239-7 (`bear_regime` notify kind and the transition notice), V239-8 (the scan-pass engine). V239-5 and V239-6 can start beside lane A; V239-7 needs V239-2/2b/3; V239-8 needs V239-2..7.

# Phase 2 — Config, store, notice, pass

### Task V239-5: `BEAR_REGIME_MODE` config field and mode reader

**Model:** haiku — one config field, one mode reader and doc lines, all copied from the v209 `MARKET_SHOCK_MODE` pattern.

**Files:**
- Modify: `swingbot/config.py` (new Field directly after `SHOCK_READINGS_KEEP_DAYS`, before `# --- Database ---`; one `_MODE_VALUES` entry after `"MARKET_SHOCK_MODE"`)
- Modify: `tests/test_config_v209_keys.py` (its neighbour assertion: the field after the v209 block is now `BEAR_REGIME_MODE`, not `DATABASE_URL`)
- Modify: `.env.example` (new section directly after the `SHOCK_READINGS_KEEP_DAYS=180` line)
- Modify: `docs/deploy/DEPLOY_HETZNER.md` (new `### v239` section directly above `### v209: market shock tables`)
- Create: `swingbot/core/scanning/regime_scan.py`
- Test: `tests/test_config_v239_keys.py` (suite `config`, `tests/test_*.py`)

**Interfaces:**
- Consumes: `config.FIELDS`, `config.Field`, `config._MODE_VALUES`, `config._MODE_FALLBACK`, `config._cast(field, raw)`, `config._apply_env()`, `config.searchable_attrs()` (all exist; `tests/test_config_v209_keys.py` uses each).
- Produces (ledger contract, final): `config.BEAR_REGIME_MODE` (select, section `"Bear Regime"`, default `"shadow"`, options `off`/`shadow`/`live`, unknown → `off`); `regime_scan.MODES = ("off", "shadow", "live")`; `regime_scan.regime_mode() -> str`. V239-8 extends `regime_scan.py`; V239-12 imports `regime_mode`.

**Why the v209 test changes:** `test_fields_sit_together_between_chart_patterns_and_database` pins the field that follows the v209 block. The new section sits there (the next shadow detector beside the last one), so that one line moves to `BEAR_REGIME_MODE`; no other v209 assertion changes.

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_v239_keys.py`:

```python
"""v239: BEAR_REGIME_MODE (spec § Config) and the regime pass's mode reader."""
import pathlib

import pytest

from swingbot import config
from swingbot.core.scanning import regime_scan

REPO = pathlib.Path(__file__).resolve().parents[1]
ATTR = "BEAR_REGIME_MODE"


def _field():
    return next(f for f in config.FIELDS if f.attr == ATTR)


def test_field_is_a_hot_reloadable_excluded_select_in_its_own_section():
    field = _field()
    assert (field.key, field.section, field.type, field.default) == (
        ATTR, "Bear Regime", "select", "shadow")
    assert field.hot_reloadable is True
    assert field.sensitive is False
    assert field.search_class == "excluded"
    assert ATTR not in config.searchable_attrs()
    assert "v239" in field.help
    assert "identical to shadow" in field.help
    assert "falls back to off" in field.help


def test_field_sits_after_market_shock_and_before_database():
    attrs = [f.attr for f in config.FIELDS]
    at = attrs.index(ATTR)
    assert attrs[at - 1] == "SHOCK_READINGS_KEEP_DAYS"
    assert attrs[at + 1] == "DATABASE_URL"


def test_mode_is_off_shadow_live_and_a_typo_falls_back_to_off():
    field = _field()
    assert [value for value, _label in field.options] == ["off", "shadow", "live"]
    assert config._MODE_VALUES[ATTR] == ("off", "shadow", "live")
    assert ATTR not in config._MODE_FALLBACK
    assert config._cast(field, "SHADOW") == "shadow"
    assert config._cast(field, "live") == "live"
    assert config._cast(field, "off") == "off"
    assert config._cast(field, "on") == "off"
    assert config._cast(field, "") == "off"


def test_module_attr_is_shadow_on_a_clean_env(monkeypatch):
    monkeypatch.delenv(ATTR, raising=False)
    try:
        config._apply_env()
        assert config.BEAR_REGIME_MODE == "shadow"
    finally:
        monkeypatch.undo()
        config._apply_env()


def test_env_example_lists_the_key_with_its_default():
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    assert f"\n{ATTR}=shadow\n" in text


def test_deploy_doc_names_the_flag_the_table_and_the_rollback():
    text = (REPO / "docs/deploy/DEPLOY_HETZNER.md").read_text(encoding="utf-8")
    assert "### v239: bear-regime engine (`market_regime_days`)" in text
    assert f"python3 scripts/ops/env_set.py {ATTR} off" in text
    assert "%bear_regime%" in text


def test_modes():
    assert regime_scan.MODES == ("off", "shadow", "live")


@pytest.mark.parametrize("value, mode", [
    ("off", "off"), ("shadow", "shadow"), ("live", "live"), (" SHADOW ", "shadow"),
    ("bogus", "off"), ("", "off"), (None, "off"),
])
def test_regime_mode_reads_config_and_falls_back_to_off(monkeypatch, value, mode):
    monkeypatch.setattr(config, ATTR, value)
    assert regime_scan.regime_mode() == mode
```

- [ ] **Step 2: Run it to see it fail**

Run: `python scripts/dev/testrun.py file tests/test_config_v239_keys.py`
Expected: collection error, `ModuleNotFoundError: No module named 'swingbot.core.scanning.regime_scan'`.

- [ ] **Step 3: Add the config field**

In `swingbot/config.py`, directly after the `SHOCK_READINGS_KEEP_DAYS` Field (its last line is `help="v209. The nightly recap prunes market_shock_readings older than this."),`) and before `    # --- Database ---`, insert:

```python
    # --- Bear Regime (v239) ---
    Field("BEAR_REGIME_MODE", "BEAR_REGIME_MODE", "Bear Regime",
          "Bear-regime engine (v239)",
          type="select", default="shadow",
          options=[("off", "Off -- no fetch, no row, no stamp, no alert line, no notice, no banner"),
                   ("shadow", "Shadow -- label, record, show, notify; change no trade"),
                   ("live", "Live -- identical to shadow until a screened follow-on spec")],
          help="v239. Once per NYSE session the first scan pass labels the coming session from "
               "completed daily SPY and ^VIX bars: BEAR, CORRECTION, NORMAL or UNKNOWN, plus a "
               "VIX stress flag and a pullback trigger. shadow: one row per session in "
               "market_regime_days, every new plan's entry_context gains bear_regime and "
               "regime_action (what the engine would do), every alert carries a Trend line, a "
               "confirmed change posts one ops notice and the site shows a Trend banner -- no "
               "long is blocked, no short issued, no plan cancelled. live: in v239 identical to "
               "shadow. off: a byte-identical kill switch. An unknown value falls back to off."),
```

In the `_MODE_VALUES` dict, directly after `    "MARKET_SHOCK_MODE": ("off", "shadow", "live"),`, add:

```python
    "BEAR_REGIME_MODE": ("off", "shadow", "live"),
```

Do not add it to `_MODE_FALLBACK`: an unknown value must land on `off`.

- [ ] **Step 4: Move the v209 neighbour assertion**

In `tests/test_config_v209_keys.py`, `test_fields_sit_together_between_chart_patterns_and_database`, replace

```python
    assert attrs[start + len(V209_FIELDS)] == "DATABASE_URL"
```

with

```python
    assert attrs[start + len(V209_FIELDS)] == "BEAR_REGIME_MODE"   # v239's section follows
```

- [ ] **Step 5: Create the mode reader**

Create `swingbot/core/scanning/regime_scan.py`:

```python
"""v239: the bear-regime pass -- every wiring decision of the daily trend engine.

`regime_mode` reads BEAR_REGIME_MODE; an unknown value is `off`, the
byte-identical kill switch (no fetch, no row, no stamp, no line, no notice).
`live` behaves exactly like `shadow` in v239. V239-8 adds regime_for_pass.

Spec: docs/superpowers/specs/2026-11-23-v239-bear-regime-engine-shadow-design.md
"""
from __future__ import annotations

from swingbot import config

MODES = ("off", "shadow", "live")


def regime_mode() -> str:
    mode = str(getattr(config, "BEAR_REGIME_MODE", "off") or "off").strip().lower()
    return mode if mode in MODES else "off"
```

- [ ] **Step 6: Document the key in `.env.example`**

Directly after the line `SHOCK_READINGS_KEEP_DAYS=180` in `.env.example`, insert (one blank line before the comment):

```
# --- Bear Regime (v239; hot-reloadable) ---
# The daily bear-regime engine. shadow (default) labels each NYSE session
# BEAR / CORRECTION / NORMAL / UNKNOWN from completed SPY and ^VIX bars,
# records it once in market_regime_days, stamps new plans, adds a Trend line
# to alerts and notifies the ops channel on a confirmed change -- and changes
# no trade; live is the same as shadow in v239; off is a byte-identical kill
# switch.
BEAR_REGIME_MODE=shadow
```

- [ ] **Step 7: Document deploy, read-back and rollback**

In `docs/deploy/DEPLOY_HETZNER.md`, directly above the heading that starts `### v209: market shock tables`, insert this block (it ends with one blank line):

````markdown
### v239: bear-regime engine (`market_regime_days`)

Revision `v239_001` creates `market_regime_days`: one write-once row per NYSE
session, keyed by the session the label is **for** (`session_date` = D;
`last_bar_date` = the last completed SPY bar it read). The first scan pass of
a session that finds no row for D (any pass: scheduled scan, `!check`, admin
scan, SHORT lane) fetches SPY and ^VIX daily through `get_daily_data` (2y;
^VIX is yfinance only, SPY Alpaca first), labels D and runs
`INSERT … ON CONFLICT DO NOTHING`; every later pass reads the row. A label
from a stale SPY bar is not stored, so the next pass retries. A row is never
updated and nothing is backfilled. A confirmed state change (two sessions)
or a pullback day enqueues one `bear_regime` event in the v197 notify queue
(`manual_close_notify`), delivered as a plain status embed to
`DISCORD_CHANNEL_OPS_ID` (falls back to the trades channel), at most one per
session. The table raises no SSE events.

| Flag | Production value | Set |
|---|---|---|
| `BEAR_REGIME_MODE` | `shadow` (label, record, stamp, show; **no trade changes**) | explicitly in `.env` right after the v239 deploy |

**Read-back:**

    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot -c \"SELECT session_date, last_bar_date, state, stress, pullback_trigger, spy_provider, vix_provider, computed_at FROM market_regime_days ORDER BY session_date DESC LIMIT 10\""

**Rollback, in this order:**
1. Behaviour: `python3 scripts/ops/env_set.py BEAR_REGIME_MODE off`, then `docker compose restart bot admin`. That means no fetch, no row, no `bear_regime` / `regime_action` key, no Trend line, no notice and no banner.
2. Schema: § Rolling back (`alembic downgrade <down_revision of v239_001>` from the new image; it was `v228_001` when planned).
3. Queue: the previous image does not know the `bear_regime` kind. After an image rollback check `SELECT count(*) FROM manual_close_notify WHERE delivered_at IS NULL AND doc::text LIKE '%bear_regime%'` and, if it is not `0`, ask before deleting those rows.

The table stays after a behaviour rollback; dropping it is never needed to roll back.
````

- [ ] **Step 8: Run both config files to see them pass**

Run: `python scripts/dev/testrun.py file tests/test_config_v239_keys.py`
Expected: `0 failed`.

Run: `python scripts/dev/testrun.py file tests/test_config_v209_keys.py`
Expected: `0 failed`.

- [ ] **Step 9: Commit**

```bash
git add swingbot/config.py swingbot/core/scanning/regime_scan.py tests/test_config_v239_keys.py tests/test_config_v209_keys.py .env.example docs/deploy/DEPLOY_HETZNER.md
git commit -m "feat(v239): BEAR_REGIME_MODE config field and regime_mode reader"
```

### Task V239-6: `market_regime_days` table, Alembic `v239_001`, the `bear_regime` queue kind

**Model:** opus — a new hybrid table, an Alembic revision that must keep exactly one head and round-trip down and up, and a new notify-queue kind with its payload validator.

**Files:**
- Modify: `swingbot/core/db/schema.py` (new table directly after the `market_shock_state = register(...)` block; new `PROMOTION_REASONS["market_regime_days"]` entry directly after the `"feed_posts"` entry, the dict's last)
- Create: `swingbot/core/db/migrations/versions/v239_001_market_regime.py`
- Modify: `tests/db/test_unknown_field_round_trip.py` (one `NOT_REPOSITORY_BACKED` entry: the table enumeration fails without it)
- Modify: `swingbot/core/infra/lifecycle_events.py` (`KINDS` gains `"bear_regime"`; a validator table replaces the `market_shock` branch in `_validate_payload`)
- Modify: `tests/infra/test_lifecycle_events_market_shock.py` (its `KINDS` pin gains the fourth kind)
- Test: `tests/db/test_v239_market_regime_schema.py` (suite `storage`), `tests/infra/test_lifecycle_events_bear_regime.py` (suite `infra`)

**Interfaces:**
- Consumes: `schema.register`, `schema.standard_columns`, `schema.PROMOTION_REASONS`, `schema.contract_violations`, `schema.promoted_for`, `events.TABLE_CHANNELS`, `lifecycle_events.make_event` / `validate_event` / `_aware` (all exist). Nothing new from `swingbot.core.market`.
- Produces (ledger contract, final): `schema.market_regime_days` (PK `session_date` = D; the 16 `RegimeDay.to_row()` columns, `computed_at TIMESTAMPTZ NOT NULL`, `doc`, `updated_at`; CHECK `market_regime_days_state`); revision `"v239_001"`. V239-6b writes the repository on it.
  - `lifecycle_events.KINDS == ("trade_closed", "plan_transition", "market_shock", "bear_regime")`; `lifecycle_events.REGIME_NOTICE_KINDS = ("transition", "pullback")`. A `bear_regime` payload (V239-7 builds it in `regime_notices.notice_payload`) has `kind` in `REGIME_NOTICE_KINDS`, a non-empty `new_label`, an `old_label` that is a string or `None` (and differs from `new_label` on a transition), an aware `occurred_at`, an ISO `session_date`, `open_longs` / `gap_sessions` each a non-negative int or `None`, `unfilled` a list of dicts or `None`, and an optional bool `pullback`.

**Why the queue kind lives here:** it is a storage contract (an unknown kind fails `validate_event` inside `enqueue`), it needs nothing from lane A, and V239-7 then only builds and renders the payload.

- [ ] **Step 0: Sync the local replica**

These tests reach Postgres: run `/replicate-prod-db` first (shared `swing-db` container, port 56789). Then confirm the head this revision sits on:

Run: `python -m alembic heads`
Expected: `v228_001 (head)`. If another revision is the head, use its id as `down_revision` in Step 5 and in the schema test below, everywhere `v228_001` appears.

- [ ] **Step 1: Write the failing schema test**

Create `tests/db/test_v239_market_regime_schema.py`:

```python
"""v239: revision v239_001 -- market_regime_days, one write-once row per session."""
import pathlib

import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.script import ScriptDirectory

from swingbot.core.db import events, schema

REPO = pathlib.Path(__file__).resolve().parents[2]
NAME = "market_regime_days"
PREVIOUS = "v228_001"   # = python -m alembic heads before this revision
FLOATS = ("spy_close", "sma50", "sma200", "sma50_lag5", "sma200_lag20", "spy_high_prev",
          "vix_close", "vix_max5")
PROMOTED = ("last_bar_date", "state", "stress", "pullback_trigger", "pullback_reason",
            *FLOATS, "spy_provider", "vix_provider", "computed_at")


def test_registered_with_reasons_contract_and_no_sse():
    table = schema.METADATA.tables[NAME]
    assert schema.promoted_for(NAME) == PROMOTED
    assert set(schema.PROMOTION_REASONS[NAME]) == set(PROMOTED)
    assert all(len(reason) <= 100 for reason in schema.PROMOTION_REASONS[NAME].values())
    assert schema.contract_violations(table) == []
    assert NAME not in events.TABLE_CHANNELS


def test_columns_key_and_state_check():
    t = schema.market_regime_days
    assert [c.name for c in t.primary_key.columns] == ["session_date"]
    assert isinstance(t.c.session_date.type, sa.Date)
    assert isinstance(t.c.last_bar_date.type, sa.Date) and t.c.last_bar_date.nullable is True
    for name in ("state", "pullback_trigger", "computed_at"):
        assert t.c[name].nullable is False, name
    for name in FLOATS:
        assert t.c[name].nullable is True and isinstance(t.c[name].type, sa.Float), name
    for name in ("stress", "pullback_reason", "spy_provider", "vix_provider"):
        assert t.c[name].nullable is True, name
    assert isinstance(t.c.stress.type, sa.Boolean)
    assert t.c.computed_at.type.timezone is True
    checks = {c.name: str(c.sqltext) for c in t.constraints if isinstance(c, sa.CheckConstraint)}
    assert checks == {"market_regime_days_state":
                      "state IN ('BEAR', 'CORRECTION', 'NORMAL', 'UNKNOWN')"}
    assert list(t.indexes) == []


def test_v239_001_sits_on_the_previous_head_and_keeps_one_head():
    scripts = ScriptDirectory.from_config(Config(str(REPO / "alembic.ini")))
    assert scripts.get_revision("v239_001").down_revision == PREVIOUS
    heads = scripts.get_heads()
    assert len(heads) == 1
    assert "v239_001" in {r.revision for r in scripts.iterate_revisions(heads[0], "base")}


def test_downgrade_drops_the_table_and_upgrade_restores_it(db_engine_empty):
    cfg = Config(str(REPO / "alembic.ini"))
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        downgrade(cfg, PREVIOUS)
        remaining = set(sa.inspect(connection).get_table_names())
        assert NAME not in remaining
        assert "manual_close_notify" in remaining
        upgrade(cfg, "head")    # leave the shared empty-schema engine at head
        assert NAME in set(sa.inspect(connection).get_table_names())
```

- [ ] **Step 2: Write the failing queue-kind test**


Create `tests/infra/test_lifecycle_events_bear_regime.py`:

```python
"""v239: the bear_regime kind of the v197 notify queue -- validation only."""
import pytest

from swingbot.core.infra import lifecycle_events
from swingbot.core.infra.lifecycle_events import make_event, validate_event

AT = "2026-11-18T21:05:00+00:00"


def payload(**over):
    return dict(occurred_at=AT, session_date="2026-11-19", kind="transition",
                old_label="Correction", new_label="Correction · Stress",
                numbers="SPY −5.7% vs SMA200 · −9.3% vs SMA50 · VIX 37.6", open_longs=3,
                unfilled=[{"ticker": "AAPL", "entry": 101.5}], gap_sessions=1,
                pullback=False) | over


def event(**over):
    return make_event(transition_id="market_regime:2026-11-19", kind="bear_regime",
                      target_channel_id="7", occurred_at=AT, payload=payload(**over))


def test_kinds_gain_bear_regime_last():
    assert lifecycle_events.KINDS[-1] == "bear_regime"
    assert lifecycle_events.REGIME_NOTICE_KINDS == ("transition", "pullback")


def test_valid_transition_pullback_and_first_reading_events_pass():
    validate_event(event())
    validate_event(event(kind="pullback", old_label=None, new_label="Pullback watch"))
    validate_event(event(old_label=None, open_longs=None, unfilled=None, gap_sessions=None))


@pytest.mark.parametrize("over", [
    {"kind": "bogus"}, {"new_label": ""}, {"new_label": None}, {"old_label": 3},
    {"old_label": "Correction", "new_label": "Correction"},
    {"occurred_at": "2026-11-18T21:05:00"}, {"session_date": "11/19/2026"},
    {"session_date": None}, {"open_longs": -1}, {"open_longs": True}, {"gap_sessions": "5"},
    {"unfilled": "AAPL"}, {"unfilled": [1]}, {"pullback": "yes"},
])
def test_a_malformed_payload_is_refused(over):
    with pytest.raises(ValueError):
        event(**over)


def test_the_shock_kind_still_validates_its_own_payload():
    with pytest.raises(ValueError, match="invalid_shock_label"):
        make_event(transition_id="t", kind="market_shock", target_channel_id="7",
                   occurred_at=AT, payload=payload())
```

In `tests/infra/test_lifecycle_events_market_shock.py`, `test_kinds_gain_market_shock_last`, replace the assertion with:

```python
    assert lifecycle_events.KINDS == ("trade_closed", "plan_transition", "market_shock",
                                      "bear_regime")   # v239 appends bear_regime
```

- [ ] **Step 3: Run both to see them fail**

Run: `python scripts/dev/testrun.py file tests/db/test_v239_market_regime_schema.py`
Expected: FAIL, `KeyError: 'market_regime_days'`.

Run: `python scripts/dev/testrun.py file tests/infra/test_lifecycle_events_bear_regime.py`
Expected: FAIL, `ValueError: invalid_event_kind_or_identity` on every `event()` call.

- [ ] **Step 4: Declare the table**


In `swingbot/core/db/schema.py`, directly after the `market_shock_state = register(...)` block (it ends `"last_notice_at"))`), insert:

```python
# v239: the bear-regime engine's day labels (core/market/bear_regime.py). One
# write-once row per NYSE session, keyed by the session the label is FOR (D),
# inserted only by repositories/market_regime.insert_once (ON CONFLICT DO
# NOTHING); never updated, never backfilled. doc holds {"unknown_reason"}.
# No SSE trigger.
_REGIME_FLOATS = ("spy_close", "sma50", "sma200", "sma50_lag5", "sma200_lag20",
                  "spy_high_prev", "vix_close", "vix_max5")
market_regime_days = register(sa.Table("market_regime_days", METADATA,
    sa.Column("session_date", sa.Date, primary_key=True),
    sa.Column("last_bar_date", sa.Date),
    sa.Column("state", sa.Text, nullable=False),
    sa.Column("stress", sa.Boolean),
    sa.Column("pullback_trigger", sa.Boolean, nullable=False),
    sa.Column("pullback_reason", sa.Text),
    *[sa.Column(name, sa.Float(53)) for name in _REGIME_FLOATS],
    sa.Column("spy_provider", sa.Text),
    sa.Column("vix_provider", sa.Text),
    sa.Column("computed_at", sa.TIMESTAMP(timezone=True), nullable=False),
    *standard_columns(),
    sa.CheckConstraint("state IN ('BEAR', 'CORRECTION', 'NORMAL', 'UNKNOWN')",
                       name="market_regime_days_state")),
    ("last_bar_date", "state", "stress", "pullback_trigger", "pullback_reason",
     *_REGIME_FLOATS, "spy_provider", "vix_provider", "computed_at"))
```

In `PROMOTION_REASONS`, directly after the `"feed_posts": {...},` entry, add:

```python
    "market_regime_days": {
        "last_bar_date": "date of the last SPY bar the label read (s unless stale); parity input",
        "state": "NOT NULL BEAR/CORRECTION/NORMAL/UNKNOWN; episodes, banner, notice, shadow SQL",
        "stress": "VIX close >= 25 on s; NULL when no ^VIX bar is dated s",
        "pullback_trigger": "NOT NULL panic-easing day inside a correction; notice and banner chip",
        "pullback_reason": "vix_gap when a VIX bar of the 5-bar window is missing; else NULL",
        "spy_close": "SPY close at s; the number line and parity",
        "sma50": "SMA50 at s; the number line and parity",
        "sma200": "SMA200 at s; the number line and parity",
        "sma50_lag5": "SMA50 at s-5; the CORRECTION slope test and parity",
        "sma200_lag20": "SMA200 at s-20; the BEAR/CORRECTION slope tests and parity",
        "spy_high_prev": "SPY high at s-1; the pullback trigger and parity",
        "vix_close": "^VIX close at s; stress, the number line and parity",
        "vix_max5": "max ^VIX close over s-4..s; the pullback trigger",
        "spy_provider": "source of the SPY frame (alpaca/yfinance); explains a parity mismatch",
        "vix_provider": "source of the ^VIX frame (yfinance); explains a parity mismatch",
        "computed_at": "NOT NULL time the label was computed; read-back and audit",
    },
```

- [ ] **Step 5: Write the revision**


Create `swingbot/core/db/migrations/versions/v239_001_market_regime.py`:

```python
"""v239: market_regime_days -- the bear-regime engine's one write-once row per session.

Additive: rollback is this revision's downgrade (drop the table); leaving it
after a code rollback is also safe (older code never reads it). An image-only
rollback to an older image must run `alembic downgrade v228_001` from this image
first (docs/deploy/DEPLOY_HETZNER.md § v239).

Revision ID: v239_001
Revises: v228_001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v239_001"
down_revision = "v228_001"   # = python -m alembic heads on the branch at implementation time
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)
_FLOATS = ("spy_close", "sma50", "sma200", "sma50_lag5", "sma200_lag20", "spy_high_prev",
           "vix_close", "vix_max5")


def _standard():
    return [sa.Column("doc", postgresql.JSONB(), nullable=False,
                      server_default=sa.text("'{}'::jsonb")),
            sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now())]


def upgrade() -> None:
    op.create_table("market_regime_days",
        sa.Column("session_date", sa.Date, primary_key=True),
        sa.Column("last_bar_date", sa.Date),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("stress", sa.Boolean),
        sa.Column("pullback_trigger", sa.Boolean, nullable=False),
        sa.Column("pullback_reason", sa.Text),
        *[sa.Column(name, sa.Float(53)) for name in _FLOATS],
        sa.Column("spy_provider", sa.Text),
        sa.Column("vix_provider", sa.Text),
        sa.Column("computed_at", _TS, nullable=False),
        *_standard(),
        sa.CheckConstraint("state IN ('BEAR', 'CORRECTION', 'NORMAL', 'UNKNOWN')",
                           name="market_regime_days_state"))


def downgrade() -> None:
    op.drop_table("market_regime_days")
```

- [ ] **Step 6: Register the table with the round-trip test**


In `tests/db/test_unknown_field_round_trip.py`, add to `NOT_REPOSITORY_BACKED`, directly after the `"feed_posts"` entry:

```python
    "market_regime_days": "write-once (insert_once only, ON CONFLICT DO NOTHING); promoted columns plus "
                          "doc {unknown_reason}; its round trip is tests/db/test_market_regime_repository.py",
```

- [ ] **Step 7: Add the queue kind and its validator**


In `swingbot/core/infra/lifecycle_events.py`:

1. Change `from datetime import datetime` to `from datetime import date, datetime`.
2. Replace the `KINDS` line and its comment with:

```python
#: v210/v239: the v197 queue's event kinds; market_shock and bear_regime are status
#: notices, not lifecycle events.
KINDS = ("trade_closed", "plan_transition", "market_shock", "bear_regime")
REGIME_NOTICE_KINDS = ("transition", "pullback")
```

3. In `_validate_payload`, replace

```python
    if kind == "market_shock":
        _validate_shock_payload(payload)
        return
```

with

```python
    validator = _STATUS_VALIDATORS.get(kind)
    if validator is not None:
        validator(payload)
        return
```

4. Directly after `_validate_shock_payload`, add:

```python
def _count_or_none(value) -> bool:
    return value is None or (isinstance(value, int) and not isinstance(value, bool)
                             and value >= 0)


def _iso_day(value) -> None:
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("invalid_session_date") from None


def _validate_regime_lists(payload):
    if not (_count_or_none(payload.get("open_longs"))
            and _count_or_none(payload.get("gap_sessions"))):
        raise ValueError("invalid_regime_counts")
    unfilled = payload.get("unfilled")
    if unfilled is not None and not (isinstance(unfilled, list)
                                     and all(isinstance(row, dict) for row in unfilled)):
        raise ValueError("invalid_unfilled")
    if not isinstance(payload.get("pullback", False), bool):
        raise ValueError("invalid_pullback_flag")


def _validate_regime_payload(payload):
    """v239: a bear-regime notice (regime_notices.notice_payload)."""
    kind, new, old = payload.get("kind"), payload.get("new_label"), payload.get("old_label")
    if kind not in REGIME_NOTICE_KINDS:
        raise ValueError("invalid_regime_notice_kind")
    if not (isinstance(new, str) and new) or not (old is None or isinstance(old, str)):
        raise ValueError("invalid_regime_label")
    if kind == "transition" and old == new:
        raise ValueError("regime_notice_without_transition")
    _aware(payload.get("occurred_at"))
    _iso_day(payload.get("session_date"))
    _validate_regime_lists(payload)


#: Status notices carry their own payload shape (no ticker, no lifecycle fields).
_STATUS_VALIDATORS = {"market_shock": _validate_shock_payload,
                      "bear_regime": _validate_regime_payload}
```

- [ ] **Step 8: Run the tests to see them pass**


Run: `python scripts/dev/testrun.py file tests/db/test_v239_market_regime_schema.py`
Expected: `0 failed` (none skipped: a skip means the shared `swing-db` container is not reachable; start it and re-run).

Run: `python scripts/dev/testrun.py file tests/db/test_unknown_field_round_trip.py`
Expected: `0 failed`.

Run: `python scripts/dev/testrun.py file tests/infra/test_lifecycle_events_bear_regime.py`
Expected: `0 failed`.

Run: `python scripts/dev/testrun.py file tests/infra/test_lifecycle_events_market_shock.py`
Expected: `0 failed`.

Run: `python -m radon cc -s -n C swingbot/core/infra/lifecycle_events.py`
Expected: no output.

Run: `python -m alembic heads`
Expected: `v239_001 (head)`.

- [ ] **Step 9: Commit**


```bash
git add swingbot/core/db/schema.py swingbot/core/db/migrations/versions/v239_001_market_regime.py tests/db/test_unknown_field_round_trip.py tests/db/test_v239_market_regime_schema.py swingbot/core/infra/lifecycle_events.py tests/infra/test_lifecycle_events_bear_regime.py tests/infra/test_lifecycle_events_market_shock.py
git commit -m "feat(v239): market_regime_days table, v239_001 revision and the bear_regime queue kind"
```

### Task V239-6b: `MarketRegimeRepository` — insert once, notice only from the winner

**Model:** opus — a race-free insert-once write whose notice must come only from the winning transaction, pinned by a two-connection concurrency test.

**Files:**
- Create: `swingbot/core/db/repositories/market_regime.py`
- Test: `tests/db/test_market_regime_repository.py` (suite `storage`)

**Interfaces:**
- Consumes: `schema.market_regime_days` (V239-6); `Repository(table, key)` and its `_tx(conn)` (`repositories/base.py`); `NotifyQueueRepository.enqueue(event, *, conn)` and `.count(conn=)`; `codec.sanitise_non_finite`; `lifecycle_events.make_event` (tests only, with the existing `plan_transition` kind so this task does not wait for V239-7). Nothing from `swingbot.core.market`: the db layer restates the states and columns, as `market_shock.LABELS` does, and V239-8 pins them equal to `bear_regime`.
- Produces (ledger contract, final):
  - `market_regime.STATES = ("BEAR", "CORRECTION", "NORMAL", "UNKNOWN")`; `market_regime.COLUMNS` (the 16 `RegimeDay.to_row()` columns, in field order).
  - `class MarketRegimeRepository(Repository)` (key `session_date`): `insert_once(row: dict, *, notice_event: dict | None = None, conn=None) -> bool` (True only for the transaction whose row went in; it alone enqueues `notice_event`, in the same transaction); `day(session_date: date, *, conn=None) -> dict | None`; `latest(*, before: date | None = None, conn=None) -> dict | None`; `recent(limit: int = 60, *, conn=None) -> list[dict]` (oldest first).
  - A read row is a dict: the 16 `COLUMNS` (dates as `date`, numbers as `float`, booleans), `computed_at` (aware `datetime`) and `doc` (dict), the shape `RegimeDay.from_row` reads.
  - `market_regime_repo() -> MarketRegimeRepository` (process singleton).
  - `insert_once` requires `row["computed_at"]` (aware `datetime` or ISO string), a `session_date` and a `state` in `STATES`, and raises `ValueError` otherwise, before touching the database. `doc` defaults to `{}`.

- [ ] **Step 0: Sync the local replica**

These tests reach Postgres: run `/replicate-prod-db` first (shared `swing-db` container, port 56789), unless a sibling task in this session already did.

- [ ] **Step 1: Write the failing repository test**

Create `tests/db/test_market_regime_repository.py`:

```python
"""v239: MarketRegimeRepository -- write once per session; the notice only from the
winning insert, in its transaction."""
import threading
from datetime import date, datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from swingbot.core.db.repositories import market_regime as mr
from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository
from swingbot.core.infra.lifecycle_events import make_event

T0 = datetime(2026, 11, 18, 21, 5, tzinfo=timezone.utc)
D0 = date(2026, 11, 19)


def _row(day=D0, state="CORRECTION", **over) -> dict:
    base = dict(session_date=day, last_bar_date=day - timedelta(days=1), state=state,
                stress=True, pullback_trigger=False, pullback_reason=None, spy_close=650.0,
                sma50=700.0, sma200=690.0, sma50_lag5=705.0, sma200_lag20=680.0,
                spy_high_prev=655.0, vix_close=30.5, vix_max5=33.0, spy_provider="alpaca",
                vix_provider="yfinance", computed_at=T0, doc={"unknown_reason": None})
    return {**base, **over}


def _notice(transition="t-1", at=T0):
    payload = {"ticker": "AAPL", "direction": "bullish", "prior_status": "PENDING",
               "new_status": "CANCELLED", "reason": "probe", "occurred_at": at.isoformat(),
               "plan_id": "P-1"}
    return make_event(transition_id=transition, kind="plan_transition",
                      target_channel_id="123", occurred_at=at.isoformat(), payload=payload)


@pytest.fixture
def repo():
    return mr.MarketRegimeRepository()


def test_the_singleton_is_reused():
    assert mr.market_regime_repo() is mr.market_regime_repo()


def test_columns_and_states_are_the_classifier_row():
    assert mr.STATES == ("BEAR", "CORRECTION", "NORMAL", "UNKNOWN")
    assert len(mr.COLUMNS) == 16 and mr.COLUMNS[:3] == ("session_date", "last_bar_date", "state")


def test_an_empty_table_reads_as_nothing(repo, db_conn):
    assert repo.day(D0, conn=db_conn) is None
    assert repo.latest(conn=db_conn) is None
    assert repo.recent(conn=db_conn) == []


def test_a_row_round_trips(repo, db_conn):
    assert repo.insert_once(_row(), conn=db_conn) is True
    got = repo.day(D0, conn=db_conn)
    assert {k: got[k] for k in mr.COLUMNS} == {k: _row()[k] for k in mr.COLUMNS}
    assert got["computed_at"] == T0 and got["doc"] == {"unknown_reason": None}


def test_an_unknown_row_keeps_its_nulls_and_reason(repo, db_conn):
    row = {name: None for name in mr.COLUMNS} | dict(
        session_date=D0, state="UNKNOWN", pullback_trigger=False, computed_at=T0,
        doc={"unknown_reason": "short_history"})
    repo.insert_once(row, conn=db_conn)
    got = repo.day(D0, conn=db_conn)
    assert got["state"] == "UNKNOWN" and got["stress"] is None and got["spy_close"] is None
    assert got["last_bar_date"] is None and got["doc"] == {"unknown_reason": "short_history"}


def test_iso_strings_are_accepted(repo, db_conn):
    row = _row(session_date="2026-11-19", last_bar_date="2026-11-18",
               computed_at=T0.isoformat())
    repo.insert_once(row, conn=db_conn)
    got = repo.day(D0, conn=db_conn)
    assert got["last_bar_date"] == date(2026, 11, 18) and got["computed_at"] == T0


@pytest.mark.parametrize("over, error", [
    ({"computed_at": None}, "computed_at_required"),
    ({"computed_at": datetime(2026, 11, 18, 21, 5)}, "timezone_required"),
    ({"state": "SHOCK"}, "unknown regime state"),
    ({"session_date": None}, "session_date_required"),
])
def test_a_bad_row_is_refused_before_the_database(repo, over, error):
    with pytest.raises(ValueError, match=error):
        repo.insert_once(_row(**over), conn=object())   # never reached: not a connection


def test_a_second_insert_for_the_session_is_refused_and_changes_nothing(repo, db_conn):
    assert repo.insert_once(_row(), conn=db_conn) is True
    assert repo.insert_once(_row(spy_close=1.0, state="BEAR"), conn=db_conn) is False
    got = repo.day(D0, conn=db_conn)
    assert (got["state"], got["spy_close"]) == ("CORRECTION", 650.0)


def test_only_the_winning_insert_enqueues_its_notice(repo, db_conn):
    queue = NotifyQueueRepository()
    before = queue.count(conn=db_conn)
    assert repo.insert_once(_row(), notice_event=_notice("t-a"), conn=db_conn) is True
    assert repo.insert_once(_row(), notice_event=_notice("t-b"), conn=db_conn) is False
    assert queue.count(conn=db_conn) == before + 1


def test_a_notice_that_fails_rolls_the_row_back_with_it(repo, db_conn):
    bad = {**_notice(), "event_id": "not-the-identity"}
    with pytest.raises(ValueError):
        with db_conn.begin_nested():
            repo.insert_once(_row(), notice_event=bad, conn=db_conn)
    assert repo.day(D0, conn=db_conn) is None


def test_latest_and_recent_read_by_session(repo, db_conn):
    days = [D0 - timedelta(days=n) for n in (3, 0, 1, 2)]
    for day in days:
        repo.insert_once(_row(day), conn=db_conn)
    assert repo.latest(conn=db_conn)["session_date"] == D0
    assert repo.latest(before=D0, conn=db_conn)["session_date"] == D0 - timedelta(days=1)
    assert repo.latest(before=D0 - timedelta(days=3), conn=db_conn) is None
    assert [r["session_date"] for r in repo.recent(conn=db_conn)] == sorted(days)
    assert [r["session_date"] for r in repo.recent(2, conn=db_conn)] == sorted(days)[-2:]


def test_two_concurrent_writers_insert_once_and_enqueue_one_notice(db_engine, db_committed):
    repo, barrier, results = mr.MarketRegimeRepository(), threading.Barrier(2), {}

    def writer(name, spy_close):
        with db_engine.connect() as connection:
            barrier.wait(timeout=10)
            with connection.begin():
                results[name] = repo.insert_once(_row(spy_close=spy_close),
                                                 notice_event=_notice(f"t-{name}"),
                                                 conn=connection)

    threads = [threading.Thread(target=writer, args=args) for args in (("a", 650.0), ("b", 651.0))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert sorted(results.values()) == [False, True]
    winner = "a" if results["a"] else "b"
    assert repo.day(D0, conn=db_committed)["spy_close"] == {"a": 650.0, "b": 651.0}[winner]
    assert NotifyQueueRepository().count(conn=db_committed) == 1
    assert db_committed.execute(sa.text("SELECT count(*) FROM market_regime_days")).scalar() == 1
```

- [ ] **Step 2: Run it to see it fail**

Run: `python scripts/dev/testrun.py file tests/db/test_market_regime_repository.py`
Expected: collection error, `ImportError: cannot import name 'market_regime'`.

- [ ] **Step 3: Write the repository**

Create `swingbot/core/db/repositories/market_regime.py`:

```python
"""v239: the bear-regime engine's day store (market_regime_days).

Writer: core/scanning/regime_scan.regime_for_pass, once per session D. The
first pass that finds no row computes the day and calls `insert_once`:
INSERT ... ON CONFLICT (session_date) DO NOTHING RETURNING, and the notice is
enqueued in the same transaction only when a row came back -- so of two
racing processes exactly one row and at most one notice survive, and a notice
never outlives a rolled-back row. A row is never updated. Readers: the pass
(`day`, `recent`), the admin API (`day`, `recent`) and parity exports.
"""
from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from swingbot.core.db.codec import sanitise_non_finite
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository
from swingbot.core.db.schema import market_regime_days as days

#: Restated from core/market/bear_regime (STATES, ROW_COLUMNS) so the db layer
#: imports nothing from core/market; tests/regime/test_regime_pass.py pins them equal.
STATES = ("BEAR", "CORRECTION", "NORMAL", "UNKNOWN")
COLUMNS = ("session_date", "last_bar_date", "state", "stress", "pullback_trigger",
           "pullback_reason", "spy_close", "sma50", "sma200", "sma50_lag5", "sma200_lag20",
           "spy_high_prev", "vix_close", "vix_max5", "spy_provider", "vix_provider")
_DATES = ("session_date", "last_bar_date")


def _day(value) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    return value if isinstance(value, dt.date) else dt.date.fromisoformat(value)


def _instant(value) -> dt.datetime:
    if value is None:
        raise ValueError("computed_at_required")
    stamp = value if isinstance(value, dt.datetime) else dt.datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        raise ValueError("timezone_required")
    return stamp


def _values(row: dict) -> dict:
    if row.get("state") not in STATES:
        raise ValueError(f"unknown regime state {row.get('state')!r}")
    values = {name: row.get(name) for name in COLUMNS}
    for name in _DATES:
        values[name] = _day(values[name])
    if values["session_date"] is None:
        raise ValueError("session_date_required")
    values.update(pullback_trigger=bool(values["pullback_trigger"]),
                  computed_at=_instant(row.get("computed_at")),
                  doc=sanitise_non_finite(dict(row.get("doc") or {})),
                  updated_at=sa.func.clock_timestamp())
    return values


def _read(row) -> dict:
    mapping = row._mapping
    return {**{name: mapping[name] for name in COLUMNS},
            "computed_at": mapping["computed_at"], "doc": dict(mapping["doc"] or {})}


class MarketRegimeRepository(Repository):
    def __init__(self):
        super().__init__(days, key="session_date")
        self._queue = NotifyQueueRepository()

    def insert_once(self, row: dict, *, notice_event: dict | None = None, conn=None) -> bool:
        """Insert the day unless the session already has one; enqueue only on a win."""
        values = _values(row)
        statement = (pg_insert(days).values(**values)
                     .on_conflict_do_nothing(index_elements=[days.c.session_date])
                     .returning(days.c.session_date))
        with self._tx(conn) as connection:
            won = connection.execute(statement).scalar_one_or_none() is not None
            if won and notice_event is not None:
                self._queue.enqueue(notice_event, conn=connection)
        return won

    def day(self, session_date: dt.date, *, conn=None) -> dict | None:
        statement = sa.select(days).where(days.c.session_date == _day(session_date))
        with self._tx(conn) as connection:
            row = connection.execute(statement).one_or_none()
        return None if row is None else _read(row)

    def latest(self, *, before: dt.date | None = None, conn=None) -> dict | None:
        statement = sa.select(days).order_by(days.c.session_date.desc()).limit(1)
        if before is not None:
            statement = statement.where(days.c.session_date < _day(before))
        with self._tx(conn) as connection:
            row = connection.execute(statement).one_or_none()
        return None if row is None else _read(row)

    def recent(self, limit: int = 60, *, conn=None) -> list[dict]:
        """The newest `limit` rows, oldest first."""
        statement = sa.select(days).order_by(days.c.session_date.desc()).limit(int(limit))
        with self._tx(conn) as connection:
            rows = connection.execute(statement).all()
        return [_read(row) for row in reversed(rows)]


_repo: MarketRegimeRepository | None = None


def market_regime_repo() -> MarketRegimeRepository:
    global _repo
    if _repo is None:
        _repo = MarketRegimeRepository()
    return _repo
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/db/test_market_regime_repository.py`
Expected: `0 failed` (none skipped).

Run: `python -m radon cc -s -n C swingbot/core/db/repositories/market_regime.py`
Expected: no output (every function below C).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/db/repositories/market_regime.py tests/db/test_market_regime_repository.py
git commit -m "feat(v239): MarketRegimeRepository -- insert once, notice only from the winner"
```

### Task V239-7: The `bear_regime` transition notice

**Model:** sonnet — a payload builder and a renderer copied from the v210 `market_shock` pattern; the decision of *when* to notify belongs to V239-8.

**Files:**
- Modify: `swingbot/core/scanning/lifecycle_notifications.py` (a renderer table replaces the `market_shock` branch in `build_lifecycle_notification`)
- Create: `swingbot/core/scanning/regime_notices.py`
- Test: `tests/regime/test_regime_notices.py` (suite `market-signals`)

**Interfaces:**
- Consumes: `bear_regime.RegimeDay` (fields `session_date`, `pullback_trigger`, `spy_close`, `sma50`, `sma200`, `vix_close`), `bear_regime.CORRECTION` (V239-2/2b); `regime_episodes.Transition(old: str | None, new: str)` and the `*_KEY` constants (V239-3); `regime_text.LABELS`, `WORDS`, `PULLBACK`, `number_line(*, spy_close, sma50, sma200, vix_close) -> str | None` (V239-3); `lifecycle_events.make_event`, `validate_event` and the `bear_regime` kind with its payload validator (V239-6); `ui.status_embed(title, description, colour)`; `kinds.HEALTH_RED`, `WATCH_STOP_ORANGE`, `MANAGE_AMBER`, `HEALTH_GREEN`, `RESULT_GREY`, `SETUP_RAMP`, `SYSTEM_SLATE`; `PlanStatus.PENDING` (`swingbot/core/planning/plan_types.py`); `config.DISCORD_CHANNEL_OPS_ID`, `config.DISCORD_CHANNEL_TRADES_ID`.
- Produces (ledger contract, final; V239-8 calls every one):
  - `regime_notices.KIND = "bear_regime"`; `FOOTER = "Shadow: no long blocked, no short issued, no plan cancelled."`; `GAP_NOTE_SESSIONS = 5`; `UNFILLED_BUDGET = 3500`.
  - `unfilled_bullish_rows(plans: Iterable, *, new_state: str) -> list[dict]` (`{"ticker": str, "entry": float}`, by ticker; index decision 6).
  - `notice_payload(day: RegimeDay, transition: Transition | None, *, open_longs: int | None, unfilled: list[dict] | None, gap_sessions: int | None, now: datetime) -> dict` with keys `occurred_at`, `session_date`, `kind` (`"transition"` / `"pullback"`), `old_label`, `new_label`, `numbers`, `open_longs`, `unfilled`, `gap_sessions`, `pullback`. `None` for `open_longs` / `unfilled` means "could not be read" and renders as `unavailable`. Raises `ValueError` when there is neither a transition nor a pullback trigger.
  - `notice_event(payload: dict, *, session_date: date) -> dict` (`transition_id=f"market_regime:{session_date}"`, so one event per session).
  - `build_regime_embed(event: dict) -> discord.Embed`.

**Payload note.** The payload is the shape V239-6's validator checks. Beyond the ledger's nine keys the payload carries `pullback: bool`, so a transition that lands on a pullback day can say so in its body. Every value is JSON-native, because `NotifyQueueRepository.enqueue` compares the stored payload with the event's.

- [ ] **Step 1: Write the failing notice test**


Create `tests/regime/test_regime_notices.py`:

```python
"""v239 V239-7: the bear_regime notice -- payload, queue event and status embed."""
import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.infra.lifecycle_events import validate_event
from swingbot.core.market import bear_regime as br
from swingbot.core.market import regime_episodes as ep
from swingbot.core.presentation import kinds, regime_text
from swingbot.core.scanning import lifecycle_notifications, regime_notices as rn

NOW = datetime(2026, 11, 18, 21, 5, tzinfo=timezone.utc)
S, D = date(2026, 11, 18), date(2026, 11, 19)
NUMBERS = dict(spy_close=650.0, sma50=716.0, sma200=690.0, vix_close=37.6)


def _day(state=br.CORRECTION, stress=True, pullback=False):
    return br.RegimeDay(session_date=D, last_bar_date=S, state=state, stress=stress,
                        pullback_trigger=pullback, **NUMBERS)


def _plan(ticker="AAPL", status="PENDING", direction="bullish", entry=101.5, ctx=None):
    return SimpleNamespace(ticker=ticker, status=status, direction=direction,
                           trigger_price=entry, entry_context=ctx or {})


def _payload(transition=ep.Transition(ep.CORRECTION_KEY, ep.CORRECTION_STRESS_KEY), **kw):
    args = dict(open_longs=3, unfilled=[{"ticker": "AAPL", "entry": 101.5}], gap_sessions=1)
    day = kw.pop("day", _day())
    return rn.notice_payload(day, transition, now=NOW, **{**args, **kw})


@pytest.fixture(autouse=True)
def _channels(monkeypatch):
    monkeypatch.setattr(config, "DISCORD_CHANNEL_OPS_ID", "11")
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_ID", "22")


def test_constants():
    assert rn.KIND == "bear_regime"
    assert rn.FOOTER == "Shadow: no long blocked, no short issued, no plan cancelled."
    assert (rn.GAP_NOTE_SESSIONS, rn.UNFILLED_BUDGET) == (5, 3500)


def test_unfilled_rows_are_pending_longs_issued_under_another_state():
    plans = [_plan("MSFT", ctx={"bear_regime": "NORMAL"}), _plan("AAPL"),
             _plan("NVDA", ctx={"bear_regime": "BEAR"}), _plan("AMD", status="ACTIVE"),
             _plan("TSLA", direction="bearish"), _plan("META", entry=None)]
    assert rn.unfilled_bullish_rows(plans, new_state=br.BEAR) == [
        {"ticker": "AAPL", "entry": 101.5}, {"ticker": "MSFT", "entry": 101.5}]


def test_transition_payload_shape_and_json_native():
    payload = _payload()
    assert set(payload) == {"occurred_at", "session_date", "kind", "old_label", "new_label",
                            "numbers", "open_longs", "unfilled", "gap_sessions", "pullback"}
    assert (payload["kind"], payload["old_label"], payload["new_label"]) == (
        "transition", "Correction", "Correction · Stress")
    assert payload["numbers"] == regime_text.number_line(**NUMBERS)
    assert (payload["session_date"], payload["occurred_at"]) == ("2026-11-19", NOW.isoformat())
    assert json.loads(json.dumps(payload)) == payload


def test_first_reading_and_pullback_headlines():
    first = _payload(ep.Transition(None, ep.CORRECTION_KEY))
    assert first["old_label"] is None
    assert rn.headline(first) == "Regime: first reading → Correction"
    pull = _payload(None, day=_day(stress=False, pullback=True))
    assert (pull["kind"], pull["new_label"]) == ("pullback", "Pullback watch")
    assert rn.headline(pull) == "Regime: Pullback watch"
    assert rn.headline(_payload()) == "Regime: Correction → Correction · Stress"


def test_a_notice_needs_a_transition_or_a_pullback():
    with pytest.raises(ValueError, match="regime_notice_without_cause"):
        _payload(None)


def test_one_event_per_session_to_the_ops_channel(monkeypatch):
    built = rn.notice_event(_payload(), session_date=D)
    validate_event(built)
    assert (built["kind"], built["transition_id"]) == ("bear_regime", "market_regime:2026-11-19")
    assert built["target_channel_id"] == "11"
    assert rn.notice_event(_payload(gap_sessions=2), session_date=D)["event_id"] == built["event_id"]
    monkeypatch.setattr(config, "DISCORD_CHANNEL_OPS_ID", "")
    assert rn.notice_event(_payload(), session_date=D)["target_channel_id"] == "22"


def _embed(**kw):
    event = rn.notice_event(_payload(**kw), session_date=D)
    return event, rn.build_regime_embed(event)


def test_the_embed_reads_headline_numbers_counts_list_and_footer():
    event, embed = _embed()
    lines = embed.description.split("\n")
    assert embed.title == "Regime: Correction → Correction · Stress"
    assert embed.colour.value == kinds.WATCH_STOP_ORANGE
    assert lines[0] == regime_text.number_line(**NUMBERS)
    assert "For session 2026-11-19." in lines and "Open longs: 3" in lines
    assert "Unfilled bullish plans from the old state (1):" in lines and "AAPL 101.50" in lines
    assert lines[-1] == rn.FOOTER
    assert embed.footer.text == f"Event {event['event_id']}" and embed.timestamp == NOW
    assert all(ord(ch) < 0x2600 for ch in embed.title + embed.description)   # no glyphs


def test_gap_note_only_past_five_sessions():
    assert _embed(gap_sessions=8)[1].description.startswith("After a gap of 8 sessions.\n")
    assert "gap" not in _embed(gap_sessions=5)[1].description


def test_unreadable_counts_and_an_empty_list_say_so():
    text = _embed(open_longs=None, unfilled=None)[1].description
    assert "Open longs: unavailable" in text
    assert "Unfilled bullish plans from the old state: unavailable" in text
    assert "Unfilled bullish plans from the old state: none." in _embed(unfilled=[])[1].description


def test_a_long_list_stops_at_the_budget():
    rows = [{"ticker": f"T{i:04d}", "entry": 100.0 + i} for i in range(1000)]
    text = _embed(unfilled=rows)[1].description
    assert len(text) <= 4096
    shown = sum(1 for line in text.split("\n") if line.startswith("T"))
    assert f"… and {1000 - shown} more" in text


def test_a_transition_on_a_pullback_day_says_so():
    text = _embed(day=_day(stress=False, pullback=True),
                  transition=ep.Transition(ep.NORMAL_KEY, ep.CORRECTION_KEY))[1].description
    assert "Pullback watch: panic easing inside a correction." in text


@pytest.mark.parametrize("new, colour", [
    (ep.BEAR_KEY, kinds.HEALTH_RED), (ep.CORRECTION_KEY, kinds.MANAGE_AMBER),
    (ep.NORMAL_KEY, kinds.HEALTH_GREEN), (ep.UNKNOWN_KEY, kinds.RESULT_GREY),
])
def test_colour_follows_the_new_state(new, colour):
    assert _embed(transition=ep.Transition(ep.CORRECTION_STRESS_KEY, new))[1].colour.value == colour


def test_the_queue_dispatches_the_kind_to_this_renderer():
    event = rn.notice_event(_payload(), session_date=D)
    embed = lifecycle_notifications.build_lifecycle_notification(event)
    assert embed.title == "Regime: Correction → Correction · Stress"
    broken = {**event, "payload": {**event["payload"], "kind": "bogus"}}
    with pytest.raises(lifecycle_notifications.BlockedDelivery) as blocked:
        lifecycle_notifications.build_lifecycle_notification(broken)
    assert blocked.value.code == "malformed_payload"
```

- [ ] **Step 2: Run it to see it fail**

Run: `python scripts/dev/testrun.py file tests/regime/test_regime_notices.py`
Expected: collection error, `ImportError: cannot import name 'regime_notices'`.

- [ ] **Step 3: Write the notice module**


Create `swingbot/core/scanning/regime_notices.py`:

```python
"""v239: bear_regime notices for the v197 notify queue.

Payload half: the unfilled bullish plans issued under the old state, the
payload and the queue event -- one per session (transition_id
market_regime:<D>). Renderer half: one plain status embed in the v210 style:
headline in the shared vocabulary, the number line, the open-long count, the
unfilled bullish plans one per line, and the shadow footer. No Kind, no
disclaimer, no glyphs. WHEN to notify is regime_scan's call (V239-8). Pure
apart from config, read only for the target channel.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime

import discord

from swingbot import config
from swingbot.core import presentation as ui
from swingbot.core.infra.lifecycle_events import make_event
from swingbot.core.market import bear_regime as br
from swingbot.core.market import regime_episodes as ep
from swingbot.core.planning.plan_types import PlanStatus
from swingbot.core.presentation import kinds, regime_text

KIND = "bear_regime"
FOOTER = "Shadow: no long blocked, no short issued, no plan cancelled."
GAP_NOTE_SESSIONS = 5
#: Discord caps a description at 4096 characters; the rest of the body fits in 596.
UNFILLED_BUDGET = 3500
FIRST_READING = "first reading"
NO_NUMBERS = "Numbers unavailable."
UNAVAILABLE = "unavailable"
_UNFILLED = "Unfilled bullish plans from the old state"
_LABELS = regime_text.LABELS
COLOURS = {_LABELS[ep.BEAR_KEY]: kinds.HEALTH_RED,
           _LABELS[ep.CORRECTION_STRESS_KEY]: kinds.WATCH_STOP_ORANGE,
           _LABELS[ep.CORRECTION_KEY]: kinds.MANAGE_AMBER,
           _LABELS[ep.NORMAL_KEY]: kinds.HEALTH_GREEN,
           _LABELS[ep.UNKNOWN_KEY]: kinds.RESULT_GREY,
           _LABELS[regime_text.PULLBACK]: kinds.SETUP_RAMP[3]}


def _unfilled_under_old_state(plan, new_state: str) -> bool:
    if getattr(plan, "status", None) != PlanStatus.PENDING:
        return False
    if getattr(plan, "direction", None) != "bullish" or not getattr(plan, "ticker", None):
        return False
    stamped = (getattr(plan, "entry_context", None) or {}).get("bear_regime")
    return stamped != new_state and getattr(plan, "trigger_price", None) is not None


def unfilled_bullish_rows(plans: Iterable, *, new_state: str) -> list[dict]:
    """PENDING bullish plans not stamped with ``new_state`` (no stamp = the old state)."""
    rows = [{"ticker": str(plan.ticker), "entry": float(plan.trigger_price)}
            for plan in plans if _unfilled_under_old_state(plan, new_state)]
    return sorted(rows, key=lambda row: row["ticker"])


def _labels(transition: ep.Transition | None) -> tuple[str, str | None, str]:
    if transition is None:
        return "pullback", None, _LABELS[regime_text.PULLBACK]
    old = _LABELS[transition.old] if transition.old is not None else None
    return "transition", old, _LABELS[transition.new]


def notice_payload(day: br.RegimeDay, transition: ep.Transition | None, *,
                   open_longs: int | None, unfilled: list[dict] | None,
                   gap_sessions: int | None, now: datetime) -> dict:
    if transition is None and not day.pullback_trigger:
        raise ValueError("regime_notice_without_cause")
    kind, old, new = _labels(transition)
    return {"occurred_at": now.isoformat(), "session_date": day.session_date.isoformat(),
            "kind": kind, "old_label": old, "new_label": new,
            "numbers": regime_text.number_line(spy_close=day.spy_close, sma50=day.sma50,
                                               sma200=day.sma200, vix_close=day.vix_close),
            "open_longs": open_longs, "unfilled": None if unfilled is None else list(unfilled),
            "gap_sessions": gap_sessions, "pullback": bool(day.pullback_trigger)}


def notice_event(payload: dict, *, session_date: date) -> dict:
    """The queue event; one per session. The channel is computed here, never via the bot."""
    channel = config.DISCORD_CHANNEL_OPS_ID or config.DISCORD_CHANNEL_TRADES_ID or None
    return make_event(transition_id=f"market_regime:{session_date}", kind=KIND,
                      target_channel_id=channel, occurred_at=payload["occurred_at"],
                      payload=payload)


def headline(payload: dict) -> str:
    if payload["kind"] == "pullback":
        return f"Regime: {payload['new_label']}"
    return f"Regime: {payload['old_label'] or FIRST_READING} → {payload['new_label']}"


def _unfilled_block(rows: list[dict] | None) -> list[str]:
    if rows is None:
        return [f"{_UNFILLED}: {UNAVAILABLE}"]
    if not rows:
        return [f"{_UNFILLED}: none."]
    lines, used = [f"{_UNFILLED} ({len(rows)}):"], 0
    for row in rows:
        line = f"{row['ticker']} {row['entry']:.2f}"
        if used + len(line) + 1 > UNFILLED_BUDGET:
            break
        lines.append(line)
        used += len(line) + 1
    shown = len(lines) - 1
    if shown < len(rows):
        lines.append(f"… and {len(rows) - shown} more")
    return lines


def _body(payload: dict) -> str:
    gap = payload.get("gap_sessions")
    lines = [f"After a gap of {gap} sessions."] if gap is not None and gap > GAP_NOTE_SESSIONS else []
    lines.append(payload.get("numbers") or NO_NUMBERS)
    if payload["kind"] == "transition" and payload.get("pullback"):
        lines.append(f"{_LABELS[regime_text.PULLBACK]}: {regime_text.WORDS[regime_text.PULLBACK]}.")
    longs = payload.get("open_longs")
    lines += [f"For session {payload['session_date']}.", "",
              f"Open longs: {UNAVAILABLE if longs is None else longs}",
              *_unfilled_block(payload.get("unfilled")), "", FOOTER]
    return "\n".join(lines)


def build_regime_embed(event: dict) -> discord.Embed:
    """The status embed for one validated bear_regime event."""
    payload = event["payload"]
    colour = COLOURS.get(payload["new_label"], kinds.SYSTEM_SLATE)
    embed = ui.status_embed(headline(payload), _body(payload), colour)
    embed.set_footer(text=f"Event {event['event_id']}")
    embed.timestamp = datetime.fromisoformat(payload["occurred_at"])
    return embed
```

- [ ] **Step 4: Dispatch the kind in the renderer**


In `swingbot/core/scanning/lifecycle_notifications.py`:

1. Change `from swingbot.core.scanning import shock_notices` to `from swingbot.core.scanning import regime_notices, shock_notices`.
2. Directly after the `_BLOCKED_CODES = ...` statement, add:

```python
#: v210/v239: status notices render as plain status embeds, without transition fields.
_STATUS_RENDERERS = {"market_shock": shock_notices.build_shock_embed,
                     "bear_regime": regime_notices.build_regime_embed}
```

3. In `build_lifecycle_notification`, replace

```python
        if event["kind"] == "market_shock":
            return shock_notices.build_shock_embed(event)
```

with

```python
        render = _STATUS_RENDERERS.get(event["kind"])
        if render is not None:
            return render(event)
```

- [ ] **Step 5: Run the tests to see them pass**


Run: `python scripts/dev/testrun.py file tests/regime/test_regime_notices.py`
Expected: `0 failed`.

Run: `python scripts/dev/testrun.py file tests/scanning/test_shock_notice_render.py`
Expected: `0 failed` (the shock renderer still dispatches through the table).

Run: `python -m radon cc -s -n C swingbot/core/scanning/lifecycle_notifications.py swingbot/core/scanning/regime_notices.py`
Expected: no output.

- [ ] **Step 6: Commit**


```bash
git add swingbot/core/scanning/lifecycle_notifications.py swingbot/core/scanning/regime_notices.py tests/regime/test_regime_notices.py
git commit -m "feat(v239): the bear_regime transition notice and its renderer dispatch"
```

