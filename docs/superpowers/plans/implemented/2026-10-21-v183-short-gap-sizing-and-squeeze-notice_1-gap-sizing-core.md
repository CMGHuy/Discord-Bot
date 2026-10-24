# v183 Part 1 — Gap-sizing core: switches, up-gap p99, gap floor, one sizing path, re-size sites

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [2026-10-21-v183-short-gap-sizing-and-squeeze-notice-design.md](../specs/2026-10-21-v183-short-gap-sizing-and-squeeze-notice-design.md)
**Index:** [2026-10-21-v183-short-gap-sizing-and-squeeze-notice_0-index.md](2026-10-21-v183-short-gap-sizing-and-squeeze-notice_0-index.md) — Goal, Architecture, Global Constraints, Contracts, Review Focus, Parallelisation and the task ledger live there; every task here implicitly includes the index's Global Constraints.

**Worktree:** every command below runs from `.claude/worktrees/2026-10-21-v183-short-gap-sizing-and-squeeze-notice` (created in V183-1 Step 1). Never edit the main tree; never touch v182 plan files.

**Scope of this part:** V183-1..V183-5. Spec sections: Part A rule, "Decided", "My calls" (switch, every sizing mode), panel additions "Adverse side only", "One sizing path", "Caps hold on the cut size" (shrink-only part), "Failures fall back loudly" (the gap path), Storage (no `entry_context` key, no Alembic).

# Phase 1 — Switches and the statistic

### Task V183-1: Worktree and the four v183 switches

**Model:** haiku — four declarative config Fields that copy a neighbour's pattern, plus a literal test.

**Files:**
- Modify: `swingbot/config.py` (the `FIELDS` list: after the `SECTOR_HEAT_CAP_PCT` Field ~:574, and after the `SHORT_UNIVERSE_FETCH_BUDGET_SECONDS` Field ~:1047; the `"live_only"` set in `_SEARCH_CLASSES` ~:1456)
- Modify: `.env.example` (after `SECTOR_HEAT_CAP_PCT=3.0` ~:356 and after `SHORT_UNIVERSE_FETCH_BUDGET_SECONDS=120` ~:597)
- Create: `tests/planning/test_v183_config_switches.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `config.SHORT_GAP_SIZING: bool` (default `True`), `config.SHORT_RISK_NOTICE: bool` (default `True`), `config.SHORT_SQUEEZE_SI_PCT: float` (default `10.0`), `config.SHORT_SQUEEZE_DTC: float` (default `5.0`). All four are hot-reloadable with `search_class == "live_only"`: they are live-only features that are never replayed, so they stay out of `ScanParams`. V183-4 reads `SHORT_GAP_SIZING`; V183-12 and V183-13 read the other three.

- [ ] **Step 1: Create the worktree**

```bash
cd /e/Documents/Private/Projects/Discord-Bot
git worktree list
git worktree add .claude/worktrees/2026-10-21-v183-short-gap-sizing-and-squeeze-notice -b 2026-10-21-v183-short-gap-sizing-and-squeeze-notice main
cd .claude/worktrees/2026-10-21-v183-short-gap-sizing-and-squeeze-notice
```

If `git worktree list` already shows this worktree, reuse it and resume at its first uncommitted task.

- [ ] **Step 2: Write the failing test** — `tests/planning/test_v183_config_switches.py`

```python
"""v183: the gap-sizing and short-notice switches and squeeze thresholds."""
import pathlib

import pytest

from swingbot import config

REPO = pathlib.Path(__file__).resolve().parents[2]

EXPECTED = {
    # attr: (section, type, default, cast default, min, max, step)
    "SHORT_GAP_SIZING": ("Account Defaults", "checkbox", "true", True, None, None, None),
    "SHORT_RISK_NOTICE": ("Universe & Scanning", "checkbox", "true", True, None, None, None),
    "SHORT_SQUEEZE_SI_PCT": ("Universe & Scanning", "float", "10.0", 10.0, 1, 100, 0.5),
    "SHORT_SQUEEZE_DTC": ("Universe & Scanning", "float", "5.0", 5.0, 0.5, 30, 0.5),
}


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


@pytest.mark.parametrize("attr", sorted(EXPECTED))
def test_field_schema(attr):
    section, ftype, default, cast, lo, hi, step = EXPECTED[attr]
    field = _field(attr)
    assert field.key == attr
    assert (field.section, field.type, field.default) == (section, ftype, default)
    assert (field.min, field.max, field.step) == (lo, hi, step)
    assert config._cast(field, field.default) == cast
    assert field.hot_reloadable is True
    assert field.search_class == "live_only"
    assert attr not in config.searchable_attrs()


@pytest.mark.parametrize("attr", sorted(EXPECTED))
def test_module_attribute_defaults(attr):
    assert getattr(config, attr) == EXPECTED[attr][3]
    assert type(getattr(config, attr)) is type(EXPECTED[attr][3])


def test_gap_switch_sits_with_the_heat_caps():
    attrs = [f.attr for f in config.FIELDS]
    assert attrs.index("SHORT_GAP_SIZING") == attrs.index("SECTOR_HEAT_CAP_PCT") + 1


def test_notice_fields_follow_the_short_lane_safeguards():
    attrs = [f.attr for f in config.FIELDS]
    base = attrs.index("SHORT_UNIVERSE_FETCH_BUDGET_SECONDS")
    assert attrs[base + 1:base + 4] == ["SHORT_RISK_NOTICE", "SHORT_SQUEEZE_SI_PCT", "SHORT_SQUEEZE_DTC"]


def test_help_names_the_revert_path_and_the_no_filter_rule():
    assert "byte-for-byte" in _field("SHORT_GAP_SIZING").help
    assert "never a filter" in _field("SHORT_RISK_NOTICE").help.lower()


def test_env_example_lists_all_four():
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    for line in ("SHORT_GAP_SIZING=true", "SHORT_RISK_NOTICE=true",
                 "SHORT_SQUEEZE_SI_PCT=10.0", "SHORT_SQUEEZE_DTC=5.0"):
        assert f"\n{line}\n" in text, line
```

- [ ] **Step 3: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/planning/test_v183_config_switches.py`
Expected: FAIL — `StopIteration` in `_field` (no such Field) for every parametrised case.

- [ ] **Step 4: Add the four Fields to `swingbot/config.py`**

Directly after the `SECTOR_HEAT_CAP_PCT` Field:

```python
    Field("SHORT_GAP_SIZING", "SHORT_GAP_SIZING", "Account Defaults",
          "SHORT gap-aware sizing (v183)", type="checkbox", default="true",
          help="v183. On (default): a SHORT plan is sized on max(stop distance, entry x the ticker's "
               "p99 up-gap over 250 completed bars), so a routine bad squeeze gap stays inside the per-trade "
               "dollar risk. The stop never moves and R stays measured on the stop; only the share count can "
               "shrink. The rule in force is stamped on each plan when it is created, so flipping this never "
               "changes an alerted plan. Off: every new short is sized on the stop, byte-for-byte as before "
               "v183. Longs are never affected."),
```

Directly after the `SHORT_UNIVERSE_FETCH_BUDGET_SECONDS` Field:

```python
    Field("SHORT_RISK_NOTICE", "SHORT_RISK_NOTICE", "Universe & Scanning",
          "SHORT squeeze/event notice (v183)", type="checkbox", default="true",
          help="v183. On (default): every SHORT alert and plan page shows short interest, days to cover and "
               "float (with their report date), any earnings and ex-dividend date inside the planned hold. "
               "Display only -- never a filter, score or gate. Off: short alerts are byte-for-byte as before v183."),
    Field("SHORT_SQUEEZE_SI_PCT", "SHORT_SQUEEZE_SI_PCT", "Universe & Scanning",
          "SHORT squeeze warning: short interest (% of float)", type="float", default="10.0",
          min=1, max=100, step=0.5,
          help="v183. The notice line is prefixed with the squeeze-risk warning when short interest is at "
               "least this % of the float (or days to cover reaches the threshold below). Display only."),
    Field("SHORT_SQUEEZE_DTC", "SHORT_SQUEEZE_DTC", "Universe & Scanning",
          "SHORT squeeze warning: days to cover", type="float", default="5.0",
          min=0.5, max=30, step=0.5,
          help="v183. The notice line is prefixed with the squeeze-risk warning when days to cover is at "
               "least this many days (or short interest reaches the threshold above). Display only."),
```

Then add the four attrs to the `"live_only"` set of `_SEARCH_CLASSES`, on a new line after `"ALERT_SYMBOL_COOLDOWN_HOURS",`:

```python
        "SHORT_GAP_SIZING", "SHORT_RISK_NOTICE", "SHORT_SQUEEZE_SI_PCT", "SHORT_SQUEEZE_DTC",
```

- [ ] **Step 5: Add the keys to `.env.example`**

After `SECTOR_HEAT_CAP_PCT=3.0`:

```
# v183: a SHORT is sized on max(stop distance, entry x its p99 up-gap over 250
# bars), so a routine squeeze gap stays inside the dollar risk. The stop never
# moves. false = size every new short on the stop, exactly as before v183.
SHORT_GAP_SIZING=true
```

After `SHORT_UNIVERSE_FETCH_BUDGET_SECONDS=120`:

```
# v183: every SHORT alert shows short interest / days to cover / float and any
# earnings or ex-dividend date in the hold. Display only, never a filter.
# The squeeze warning trips at either threshold.
SHORT_RISK_NOTICE=true
SHORT_SQUEEZE_SI_PCT=10.0
SHORT_SQUEEZE_DTC=5.0
```

- [ ] **Step 6: Run the test and the config classification tests**

Run: `python scripts/dev/testrun.py file tests/planning/test_v183_config_switches.py`
Expected: PASS (all cases).
Run: `python scripts/dev/testrun.py file tests/infra/test_scan_params_coverage.py`
Expected: PASS. `live_only` Fields need no `ScanParams` field.

- [ ] **Step 7: Commit**

```bash
git add swingbot/config.py .env.example tests/planning/test_v183_config_switches.py
git commit -m "feat(v183): SHORT_GAP_SIZING, SHORT_RISK_NOTICE and squeeze threshold switches"
```

### Task V183-2: Up-gap p99 in gap_stats

**Model:** sonnet — one pure function gains two keys; the test must pin that the adverse (up) side is measured, not the absolute gap.

**Files:**
- Modify: `swingbot/core/edge/gates.py:15-24` (`gap_stats`; new helper `_up_gap_stats` directly below it)
- Modify: `tests/edge/test_edge_gates.py` (append tests)

**Interfaces:**
- Consumes: nothing.
- Produces: `gap_stats(df, lookback=250)` returns the three existing keys unchanged, plus `"p99_up_gap_pct": float | None` (99th percentile, in %, of the gaps `Open / prev Close - 1 > 0` inside the same `lookback + 1` tail; `None` when there are none) and `"n_up": int`. Empty frame: `{"p90_gap_pct": 0.0, "p99_gap_pct": 0.0, "n": 0, "p99_up_gap_pct": None, "n_up": 0}`. V183-4 reads both new keys.

- [ ] **Step 1: Write the failing tests** — append to `tests/edge/test_edge_gates.py`

```python
def _signed_gaps(n=300, up_pct=2.0, down_pct=6.0):
    """Close flat at 100; even rows open up_pct above the prior close, odd rows
    open down_pct below it -> 250 gaps in the 251-row tail, 125 of them up."""
    idx = pd.bdate_range(start="2025-06-02", periods=n)
    opens = [100.0 * (1 + up_pct / 100) if i % 2 == 0 else 100.0 * (1 - down_pct / 100)
             for i in range(n)]
    closes = [100.0] * n
    return pd.DataFrame({"Open": opens, "High": [max(o, 100.0) * 1.01 for o in opens],
                         "Low": [min(o, 100.0) * 0.99 for o in opens], "Close": closes,
                         "Volume": [1_000_000.0] * n}, index=idx)


def test_up_gap_p99_measures_only_the_adverse_side_for_a_short():
    stats = gap_stats(_signed_gaps())
    assert stats["p99_gap_pct"] == pytest.approx(6.0)        # absolute: the down gaps dominate
    assert stats["p99_up_gap_pct"] == pytest.approx(2.0)     # up-gaps only
    assert stats["n_up"] == 125
    assert stats["n"] == 250


def test_existing_keys_are_unchanged_by_the_new_ones():
    stats = gap_stats(_with_gaps())
    assert stats["n"] == 250
    assert stats["p99_gap_pct"] >= stats["p90_gap_pct"]
    assert set(stats) == {"p90_gap_pct", "p99_gap_pct", "n", "p99_up_gap_pct", "n_up"}


def test_no_up_gaps_gives_none_not_zero():
    stats = gap_stats(_signed_gaps(up_pct=-1.0))             # every gap is a down gap
    assert stats["p99_up_gap_pct"] is None
    assert stats["n_up"] == 0


def test_flat_opens_are_not_up_gaps():
    stats = gap_stats(make_ohlcv(np.full(300, 100.0), spread_pct=1.0))
    assert stats["n_up"] == 0 and stats["p99_up_gap_pct"] is None


def test_empty_frame_carries_the_new_keys():
    empty = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    assert gap_stats(empty) == {"p90_gap_pct": 0.0, "p99_gap_pct": 0.0, "n": 0,
                                "p99_up_gap_pct": None, "n_up": 0}


def test_up_gap_lookback_bound_respected():
    df = _signed_gaps(n=400)
    df.iloc[:100, df.columns.get_loc("Open")] = 150.0          # huge up gaps OUTSIDE the 250-bar window
    assert gap_stats(df)["p99_up_gap_pct"] == pytest.approx(2.0)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/edge/test_edge_gates.py`
Expected: FAIL — `KeyError: 'p99_up_gap_pct'` (the existing tests in the file still pass).

- [ ] **Step 3: Implement in `swingbot/core/edge/gates.py`**

Replace `gap_stats` and add the helper:

```python
def gap_stats(df: pd.DataFrame, lookback: int = 250) -> dict:
    """Distribution of overnight gaps |Open / prev Close - 1| in percent.

    v183: also the adverse side for a short -- p99 of the UP gaps only
    (Open / prev Close - 1 > 0) over the same window, None when there are
    none, and their count. The three original keys are unchanged."""
    tail = df.tail(lookback + 1)
    signed = (tail["Open"] / tail["Close"].shift(1) - 1.0).dropna() * 100.0
    gaps = signed.abs()
    if gaps.empty:
        return {"p90_gap_pct": 0.0, "p99_gap_pct": 0.0, "n": 0, "p99_up_gap_pct": None, "n_up": 0}
    return {"p90_gap_pct": float(np.percentile(gaps, 90)),
            "p99_gap_pct": float(np.percentile(gaps, 99)),
            "n": int(len(gaps)),
            **_up_gap_stats(signed)}


def _up_gap_stats(signed: pd.Series) -> dict:
    """p99 and count of the strictly positive gaps (percent)."""
    up = signed[signed > 0]
    return {"p99_up_gap_pct": float(np.percentile(up, 99)) if len(up) else None,
            "n_up": int(len(up))}
```

The existing callers (`edge/context.py:105`, `scanning/analyze.py:222`) read only `p90_gap_pct` and need no change. `entry_context` is not touched, so no live-only key reaches backtests.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/edge/test_edge_gates.py`
Expected: PASS (old and new tests).
Run: `python scripts/dev/testrun.py file tests/edge/test_edge_context_structure.py`
Expected: PASS (`entry_context` reads only `p90_gap_pct`).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/edge/gates.py tests/edge/test_edge_gates.py
git commit -m "feat(v183): gap_stats reports the p99 of up-gaps, the short's adverse side"
```

# Phase 2 — The gap floor and the one sizing path

### Task V183-3: Gap floor in compute_position_size, every sizing mode

**Model:** opus — a legacy CC-18 money function changes, with a byte-identity requirement on the default path and a shrink-only invariant in five modes.

**Files:**
- Modify: `swingbot/core/planning/account.py:405-546` (`compute_position_size`; new helpers `_sizing_distance` and `_gap_fields` directly above it)
- Create: `tests/planning/test_gap_floor_sizing.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `compute_position_size(entry, stop_loss, account_cfg=None, *, strategy_stats=None, ticker_atr_pct=None, open_positions=0, gap_floor_pct: float | None = None) -> dict | None`
    - With `gap_floor_pct=None` (every existing caller), the result dict is identical to today, with no new keys.
    - With a value, the result also carries three keys:
      - `"gap_risk_amount"`: `round(shares × sizing_distance, 2)`, the cost of a p99 gap.
      - `"gap_sized"`: `True` only when the floor really lowered the final share count compared with the same cap chain on the stop distance.
      - `"gap_floor_pct"`: `float`.
  - `_sizing_distance(entry: float, stop_distance: float, gap_floor_pct: float | None) -> float`: `stop_distance` when the floor is `None`, else `max(stop_distance, entry × gap_floor_pct / 100)`. V183-4's `gap_risk_amount_for` reuses it.
  - `_gap_fields(shares: float, uncut_shares: float, sizing_distance: float, gap_floor_pct: float | None) -> dict`: returns `{}` when the floor is `None`.

**Rule (spec Part A):** `sizing_distance = max(|entry − stop|, entry × gap_floor_pct / 100)`. The division of the risk budget into shares (in the `risk_pct` branch) and the `MAX_RISK_AMOUNT_ABSOLUTE` cap both use `sizing_distance`. The two position caps and the `account_pct` allocation do not depend on distance, so they are unchanged.

What stays the same:
- `risk_amount` stays final shares × **stop** distance.
- `capped` keeps its meaning.
- The edge modes (`kelly`, `vol_target`, `min_of_all`) are rewritten to `risk_pct` before the branch, so they share it.
- `account_pct` feels the floor only through the absolute risk cap.

Because `sizing_distance ≥ stop_distance`, shares can only shrink. `uncut_shares` is the same cap chain on the stop distance; it is tracked with `min()` lines inside the existing blocks, so no branch is added and the baseline CC of 18 does not rise.

- [ ] **Step 1: Write the failing test** — `tests/planning/test_gap_floor_sizing.py`

```python
"""v183 Part A: the gap floor inside compute_position_size."""
import pytest

from swingbot import config
from swingbot.core.planning import account
from swingbot.core.planning.account import _gap_fields, _sizing_distance, compute_position_size

GAP_KEYS = {"gap_risk_amount", "gap_sized", "gap_floor_pct"}
WEAK = {"win_rate": 0.60, "avg_win_r": 0.3, "avg_loss_r": 1.0, "n": 200}


@pytest.fixture(autouse=True)
def _no_opex(monkeypatch):
    monkeypatch.setattr(account.opex, "size_mult", lambda *a, **k: 1.0)
    monkeypatch.setattr(config, "PORTFOLIO_TARGET_DAILY_VOL_PCT", 0.7)


def _cfg(mode="risk_pct", **over):
    cfg = {"balance": 10_000.0, "risk_pct": 1.0, "sizing_mode": mode, "position_pct": 10.0,
           "max_position_pct": 100.0, "max_position_value_absolute": 0, "max_risk_amount_absolute": 0}
    cfg.update(over)
    return cfg


def test_no_floor_is_todays_dict_exactly():
    out = compute_position_size(100.0, 98.0, _cfg())
    assert out == {"shares": 50.0, "risk_amount": 100.0, "position_value": 5000.0, "capped": False,
                   "balance": 10_000.0, "risk_pct": 1.0, "position_pct": 10.0, "max_position_pct": 100.0,
                   "max_position_value_absolute": 0.0, "max_risk_amount_absolute": 0.0, "mode": "risk_pct"}
    assert compute_position_size(100.0, 98.0, _cfg(), gap_floor_pct=None) == out


def test_gap_wider_than_stop_cuts_shares_and_keeps_risk_on_the_stop():
    # short: entry 100, stop 102 (2.00 away); p99 up-gap 3% -> sizes on 3.00
    out = compute_position_size(100.0, 102.0, _cfg(), gap_floor_pct=3.0)
    assert out["shares"] == 33.33
    assert out["risk_amount"] == 66.67          # final shares x STOP distance
    assert out["gap_risk_amount"] == 100.0      # final shares x sizing distance = the dollar cap
    assert out["gap_sized"] is True
    assert out["gap_floor_pct"] == 3.0
    assert out["mode"] == "risk_pct"


def test_stop_wider_than_gap_is_unchanged_but_reports_gap_risk():
    plain = compute_position_size(100.0, 105.0, _cfg())
    out = compute_position_size(100.0, 105.0, _cfg(), gap_floor_pct=3.0)
    assert {k: out[k] for k in plain} == plain
    assert set(out) - set(plain) == GAP_KEYS
    assert (out["shares"], out["gap_risk_amount"], out["gap_sized"]) == (20.0, 100.0, False)


def test_binding_position_cap_is_not_reported_as_a_gap_cut():
    # max_position_pct 20 -> at most 20 shares at 100 whatever the distance
    out = compute_position_size(100.0, 102.0, _cfg(max_position_pct=20.0), gap_floor_pct=3.0)
    assert out["shares"] == 20.0
    assert out["gap_sized"] is False
    assert out["gap_risk_amount"] == 60.0


def test_absolute_risk_cap_uses_the_sizing_distance():
    # stop-only: 50 shares, risk cap 60/2 = 30 -> 30 ; gap: 33.33, risk cap 60/3 = 20 -> 20
    plain = compute_position_size(100.0, 102.0, _cfg(max_risk_amount_absolute=60.0))
    out = compute_position_size(100.0, 102.0, _cfg(max_risk_amount_absolute=60.0), gap_floor_pct=3.0)
    assert plain["shares"] == 30.0
    assert out["shares"] == 20.0 and out["gap_sized"] is True and out["capped"] is True
    assert out["gap_risk_amount"] == 60.0       # never above the absolute dollar cap


def test_account_pct_feels_the_floor_only_through_the_absolute_risk_cap():
    free = compute_position_size(100.0, 101.0, _cfg("account_pct"), gap_floor_pct=3.0)
    assert free["shares"] == 10.0 and free["gap_sized"] is False and free["gap_risk_amount"] == 30.0
    capped = compute_position_size(100.0, 101.0, _cfg("account_pct", max_risk_amount_absolute=15.0),
                                   gap_floor_pct=3.0)
    assert capped["shares"] == 5.0 and capped["gap_sized"] is True
    assert capped["risk_amount"] == 5.0 and capped["gap_risk_amount"] == 15.0
    assert compute_position_size(100.0, 101.0, _cfg("account_pct", max_risk_amount_absolute=15.0))["shares"] == 10.0


@pytest.mark.parametrize("mode, kwargs, plain_shares, gap_shares", [
    ("risk_pct", {}, 50.0, 33.33),
    ("kelly", {"strategy_stats": WEAK}, 12.5, 8.33),
    ("vol_target", {"ticker_atr_pct": 3.0}, 35.0, 23.33),
    ("min_of_all", {"strategy_stats": WEAK, "ticker_atr_pct": 3.0}, 12.5, 8.33),
    ("account_pct", {}, 10.0, 10.0),
])
def test_every_mode_only_ever_shrinks(mode, kwargs, plain_shares, gap_shares):
    plain = compute_position_size(100.0, 102.0, _cfg(mode), **kwargs)
    out = compute_position_size(100.0, 102.0, _cfg(mode), gap_floor_pct=3.0, **kwargs)
    assert plain["shares"] == plain_shares
    assert out["shares"] == gap_shares
    assert out["shares"] <= plain["shares"]
    assert out["gap_sized"] is (gap_shares < plain_shares)
    assert out["risk_amount"] <= plain["risk_amount"]


def test_zero_balance_and_zero_stop_still_return_none():
    assert compute_position_size(100.0, 102.0, _cfg(balance=0.0), gap_floor_pct=3.0) is None
    assert compute_position_size(100.0, 100.0, _cfg(), gap_floor_pct=3.0) is None


def test_helpers():
    assert _sizing_distance(100.0, 2.0, None) == 2.0
    assert _sizing_distance(100.0, 2.0, 3.0) == 3.0
    assert _sizing_distance(100.0, 5.0, 3.0) == 5.0
    assert _gap_fields(10.0, 10.0, 3.0, None) == {}
    assert _gap_fields(10.0, 15.0, 3.0, 3.0) == {"gap_risk_amount": 30.0, "gap_sized": True, "gap_floor_pct": 3.0}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/planning/test_gap_floor_sizing.py`
Expected: FAIL — `ImportError: cannot import name '_gap_fields'`.

- [ ] **Step 3: Add the two helpers above `compute_position_size` in `swingbot/core/planning/account.py`**

```python
def _sizing_distance(entry: float, stop_distance: float, gap_floor_pct: float | None) -> float:
    """v183: the per-share distance the risk budget is divided by --
    the stop distance, or entry x gap_floor_pct% when that is wider."""
    if gap_floor_pct is None:
        return stop_distance
    return max(stop_distance, entry * float(gap_floor_pct) / 100.0)


def _gap_fields(shares: float, uncut_shares: float, sizing_distance: float,
                gap_floor_pct: float | None) -> dict:
    """v183: the gap keys of a floored sizing; {} without a floor, so every
    stop-only result keeps today's exact key set. gap_sized is true only
    when the floor actually lowered the final share count."""
    if gap_floor_pct is None:
        return {}
    return {"gap_risk_amount": round(shares * sizing_distance, 2),
            "gap_sized": round(shares, 2) < round(uncut_shares, 2),
            "gap_floor_pct": float(gap_floor_pct)}
```

- [ ] **Step 4: Thread the floor through `compute_position_size`**

Add the keyword to the signature: `open_positions: int = 0, gap_floor_pct: float | None = None) -> dict | None:`. Add to the docstring, after the cap list:

```
    v183 gap_floor_pct (shorts only, passed by planning.gap_sizing): the
    risk budget and the MAX_RISK_AMOUNT_ABSOLUTE cap divide by
    max(stop distance, entry x gap_floor_pct%) instead of the stop
    distance, so shares can only shrink. risk_amount stays shares x STOP
    distance; the result adds gap_risk_amount, gap_sized, gap_floor_pct.
    None (every other caller) -> today's result, key for key.
```

From `stop_distance = abs(entry - stop_loss)` to the `return`, the body becomes the following. The lines marked `# v183` are the only changes; everything else is verbatim:

```python
    stop_distance = abs(entry - stop_loss)
    sizing_distance = _sizing_distance(entry, stop_distance, gap_floor_pct)   # v183

    if mode == "account_pct":
        # Fixed allocation: the position is always exactly position_pct% of
        # the account, independent of how far away the stop sits.
        position_value = balance * position_pct / 100.0
        raw_shares = position_value / entry
        uncut_shares = raw_shares                                              # v183
    else:
        mode = "risk_pct"   # normalize anything unrecognized to the documented default
        if stop_distance <= 0:
            return None
        risk_amount = balance * risk_pct / 100.0
        raw_shares = risk_amount / sizing_distance                             # v183 (was / stop_distance)
        uncut_shares = risk_amount / stop_distance                             # v183
        position_value = raw_shares * entry

    capped = False
    max_position_value = balance * max_position_pct / 100.0
    uncut_shares = min(uncut_shares, max_position_value / entry)               # v183
    if position_value > max_position_value:
        raw_shares = max_position_value / entry
        capped = True

    # Absolute currency caps -- (comment block unchanged)
    if max_position_value_absolute > 0:
        max_shares_for_position = max_position_value_absolute / entry
        uncut_shares = min(uncut_shares, max_shares_for_position)              # v183
        if raw_shares > max_shares_for_position:
            raw_shares = max_shares_for_position
            capped = True
    if max_risk_amount_absolute > 0 and stop_distance > 0:
        uncut_shares = min(uncut_shares, max_risk_amount_absolute / stop_distance)   # v183
        max_shares_for_risk = max_risk_amount_absolute / sizing_distance       # v183 (was / stop_distance)
        if raw_shares > max_shares_for_risk:
            raw_shares = max_shares_for_risk
            capped = True

    # Always the REAL figures -- (comment block unchanged)
    position_value = raw_shares * entry
    risk_amount = raw_shares * stop_distance

    result = {
        # ... the eleven existing keys, verbatim ...
    }
    result.update(_gap_fields(raw_shares, uncut_shares, sizing_distance, gap_floor_pct))   # v183
    return result
```

With `gap_floor_pct=None`, `sizing_distance` is `stop_distance` itself, so every float is computed exactly as before and `_gap_fields` adds nothing.

- [ ] **Step 5: Run the tests and the existing sizing tests**

Run: `python scripts/dev/testrun.py file tests/planning/test_gap_floor_sizing.py`
Expected: PASS.
Run: `python scripts/dev/testrun.py file tests/edge/test_edge_sizing.py`
Expected: PASS (unchanged golden share counts).
Run: `python scripts/dev/testrun.py file tests/planning/test_stop_scope.py`
Expected: PASS (`risk_sizing_ok`, the seventh caller, is untouched).

- [ ] **Step 6: Check complexity did not rise**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0. `swingbot.core.planning.account:compute_position_size` stays at 18, and both new helpers are below 15.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/planning/account.py tests/planning/test_gap_floor_sizing.py
git commit -m "feat(v183): compute_position_size takes a gap floor that can only shrink shares"
```

### Task V183-4: One sizing path, plan stamp at creation

**Model:** opus — this task sets the shared contract that seven call sites and the paper book depend on. It also carries the byte-identity rules for long plan docs and switch-off shorts.

**Files:**
- Create: `swingbot/core/planning/gap_sizing.py`
- Create: `tests/planning/test_gap_sizing.py`
- Modify: `swingbot/core/planning/plan_types.py` (new last field of `TradePlanV2` after `price_confirmed` ~:197; `_OMIT_WHEN_NONE` and `plan_to_dict` ~:212-219)
- Modify: `swingbot/core/scanning/analyze.py` (import beside `stamp_entry_context` :36; new helper `_stamp_gap_sizing_live` directly above `attach_plan_v2` :461; one call after the `stamp_entry_context(...)` block ~:519-524)
- Modify: `swingbot/core/scanning/strategy_pass.py` (import beside the `params` import :12; one call in `build_strategy_plan_at` after `stamp_entry_context` :77)

**Interfaces:**
- Consumes:
  - `config.SHORT_GAP_SIZING` (V183-1).
  - `gap_stats(df, lookback)["p99_up_gap_pct"]` and `["n_up"]` (V183-2).
  - `account.compute_position_size(..., gap_floor_pct=...)` and `account._sizing_distance(entry, stop_distance, gap_floor_pct)` (V183-3).
- Produces (exact, from the index Contracts):
  - Constants: `RULE_GAP = "gap_p99"`, `RULE_STOP = "stop"`, `MIN_UP_GAPS = 60`, `LOOKBACK = 250`.
  - `gap_sizing_stamp(df, direction: str) -> dict | None`
  - `stamp_gap_sizing(plan, df) -> None`
  - `gap_floor_for(direction: str | None, gap_sizing: dict | None) -> float | None`
  - `size_for(entry, stop_loss, *, direction, gap_sizing, account_cfg=None, label: str = "") -> dict | None`
  - `size_for_plan(plan, entry=None, account_cfg=None) -> dict | None`
  - `size_for_trade(trade: dict, entry=None, account_cfg=None) -> dict | None`
  - `gap_risk_amount_for(shares, entry, stop_loss, gap_sizing) -> float | None`
  - `TradePlanV2.gap_sizing: dict | None = None`
  - `plan_types._OMIT_WHEN_NONE = ("gap_sizing",)`. V183-12 appends `"risk_notice"`.
  - The stamp shape is `{"rule": "gap_p99" | "stop", "up_gap_p99_pct": float | None, "n_up_gaps": int}`.
  - V183-5 and V183-6 call `size_for*`. V183-9 calls `gap_risk_amount_for`. V183-8 reads the `gap_*` keys of a `size_for` result.

**Decisions this task fixes (spec "One sizing path", "Failures fall back loudly", Storage; index Global Constraints):**
- **Where the stamp lives.** It is computed once, at the two live plan-creation sites, from **completed** daily bars. `analyze` drops today's still-forming bar through `strategy_pass.completed_frame`; the strategy pass already hands over `df_completed`.
- **Not in `entry_context`.** The stamp is a top-level plan field, never an `entry_context` key and never written by `stamp_entry_context`, which the backtests share. `FEATURE_KEYS` is not edited.
- **Readers.** Every reader takes the stamp only. A switch flip after creation never changes an alerted plan's rule.
- **Long and rule-`"stop"` results.** A long, or a short stamped rule `"stop"`, returns `account.compute_position_size(entry, stop_loss)` exactly. The call passes two positional args when `account_cfg is None`, as every patched test double expects.
- **Missing p99.** A short with no stamp (a pre-v183 plan) or with a `None` p99 gets the plain result plus `{"gap_risk_amount": None, "gap_sized": False, "gap_floor_pct": None}`, so V183-8 can print "gap risk n/a".
- **Missing p99 is logged once, at stamp time.** It is not logged at every re-size, because those run on every render.
- **An exception in the gap path** logs `"%s: gap sizing fell back to stop (%s)"` and returns the stop-only result. It never returns unsized.
- **Plan docs (controller ruling).** `plan_to_dict` omits `gap_sizing` while it is `None`, so a long plan doc keeps exactly its pre-v183 keys.
- **A rebuilt plan** (v171 requote, `scan_run._rebuild_item` → `analyze.attach_plan_v2` on the same frame) is re-stamped from the same completed bars, so it gets the same stamp (Review Focus 1).

- [ ] **Step 1: Write the failing test** — `tests/planning/test_gap_sizing.py`

```python
"""v183 Part A: the one sizing path, the plan stamp and the long plan-doc pin."""
import inspect
import json
import logging
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.planning import account
from swingbot.core.planning import gap_sizing as gs
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2, plan_from_dict, plan_to_dict
from swingbot.core.scanning import analyze
from swingbot.core.scanning import strategy_pass as sp

CFG = {"balance": 10_000.0, "risk_pct": 1.0, "sizing_mode": "risk_pct", "position_pct": 10.0,
       "max_position_pct": 100.0, "max_position_value_absolute": 0, "max_risk_amount_absolute": 0}
STAMP = {"rule": "gap_p99", "up_gap_p99_pct": 3.0, "n_up_gaps": 125}
NO_GAP = {"gap_risk_amount": None, "gap_sized": False, "gap_floor_pct": None}

# TradePlanV2's persisted keys, in order, before v183 -- a long plan doc must keep exactly these.
PRE_V183_PLAN_KEYS = [
    "plan_id", "ticker", "created_at", "source", "strategy", "horizon_key", "direction", "entry_type",
    "trigger_price", "entry_price", "expiry_bars", "stop_loss", "tp1", "tp1_fraction", "tp2",
    "breakeven_trigger_fraction", "trail_atr_mult", "quality_score", "quality_breakdown", "badge",
    "badge_stats", "status", "status_history", "working_stop", "legs_realized", "runner_high_close",
    "stop_mult_applied", "cohort_label", "cohort_stats", "risk_features", "ledger", "first_seen_price",
    "entry_context", "tp2_r_applied", "time_stop_days", "stall_exit_day", "hold_cap_bars", "pyramid_add",
    "confidence_level", "confidence_points", "confidence_unevaluated", "be_armed_session",
    "runner_floor_session", "notified_stop", "pending_notice", "issued_at", "acceptance_level",
    "acceptance_close_below", "stop_ceiling_pct", "pending_time_notices", "time_exit_due_date",
    "time_exit_unresolved_date", "time_exit_notified_date", "limit_cancel_level", "limit_strict_fill",
    "runner_path", "origin", "valid_session", "cancel_reason_message", "quote_at", "quote_kind",
    "quote_age_s", "quote_session", "price_confirmed",
]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(account.opex, "size_mult", lambda *a, **k: 1.0)
    monkeypatch.setattr(account, "load_account_config", lambda: dict(CFG))
    monkeypatch.setattr(config, "SHORT_GAP_SIZING", True)


def _signed_gaps(n=300, up_pct=2.0, down_pct=6.0, end=None):
    """Flat close 100; even rows gap up up_pct, odd rows gap down down_pct."""
    idx = pd.bdate_range(end=end, periods=n) if end else pd.bdate_range(start="2025-06-02", periods=n)
    opens = [100.0 * (1 + up_pct / 100) if i % 2 == 0 else 100.0 * (1 - down_pct / 100) for i in range(n)]
    return pd.DataFrame({"Open": opens, "High": [max(o, 100.0) * 1.01 for o in opens],
                         "Low": [min(o, 100.0) * 0.99 for o in opens], "Close": [100.0] * n,
                         "Volume": [1_000_000.0] * n}, index=idx)


def _plan(direction="bearish", **kw):
    short = direction == "bearish"
    base = dict(plan_id="p1", ticker="ZZZ", created_at="2026-10-20", source="confluence", strategy="MACD",
                horizon_key="3m", direction=direction, entry_type="stop_entry", trigger_price=100.0,
                entry_price=None, expiry_bars=5, stop_loss=102.0 if short else 98.0,
                tp1=95.0 if short else 105.0, tp1_fraction=0.5, tp2=None, breakeven_trigger_fraction=0.5,
                trail_atr_mult=2.0, quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
                status=PlanStatus.PENDING)
    base.update(kw)
    return TradePlanV2(**base)


# --- the stamp ---------------------------------------------------------------

def test_stamp_is_none_for_a_long():
    assert gs.gap_sizing_stamp(_signed_gaps(), "bullish") is None


def test_stamp_for_a_short_reads_the_up_gap_p99():
    stamp = gs.gap_sizing_stamp(_signed_gaps(), "bearish")
    assert stamp == {"rule": "gap_p99", "up_gap_p99_pct": pytest.approx(2.0), "n_up_gaps": 125}


def test_switch_off_stamps_rule_stop_and_still_records_the_p99(monkeypatch):
    monkeypatch.setattr(config, "SHORT_GAP_SIZING", False)
    stamp = gs.gap_sizing_stamp(_signed_gaps(), "bearish")
    assert stamp["rule"] == gs.RULE_STOP and stamp["up_gap_p99_pct"] == pytest.approx(2.0)


def test_too_few_up_gaps_records_no_p99():
    stamp = gs.gap_sizing_stamp(_signed_gaps(n=100), "bearish")    # 99 gaps, 49 up < 60
    assert stamp == {"rule": "gap_p99", "up_gap_p99_pct": None, "n_up_gaps": 49}


def test_stamp_never_raises_and_logs_the_fallback_once(caplog):
    short, long_ = _plan(), _plan("bullish")
    with caplog.at_level(logging.INFO, logger="swingbot.core.planning.gap_sizing"):
        gs.stamp_gap_sizing(short, None)
        gs.stamp_gap_sizing(long_, None)
    assert short.gap_sizing == {"rule": "gap_p99", "up_gap_p99_pct": None, "n_up_gaps": 0}
    assert long_.gap_sizing is None
    assert len([r for r in caplog.records if "ZZZ: gap sizing" in r.getMessage()]) == 1


def test_missing_p99_is_logged_at_stamp_time(caplog):
    plan = _plan()
    with caplog.at_level(logging.INFO, logger="swingbot.core.planning.gap_sizing"):
        gs.stamp_gap_sizing(plan, _signed_gaps(n=100))
    assert "ZZZ: gap sizing p99 n/a (49 up-gaps, need 60) -- sized on the stop" in caplog.text


# --- the one sizing path --------------------------------------------------------

def test_gap_floor_for():
    assert gs.gap_floor_for("bearish", STAMP) == 3.0
    assert gs.gap_floor_for("bullish", STAMP) is None
    assert gs.gap_floor_for("bearish", None) is None
    assert gs.gap_floor_for("bearish", {**STAMP, "rule": "stop"}) is None
    assert gs.gap_floor_for("bearish", {**STAMP, "up_gap_p99_pct": None}) is None
    assert gs.gap_floor_for("bearish", {**STAMP, "up_gap_p99_pct": 0.0}) is None


def test_long_is_compute_position_size_exactly_even_with_a_stray_stamp():
    plain = account.compute_position_size(100.0, 98.0)
    assert gs.size_for(100.0, 98.0, direction="bullish", gap_sizing=None) == plain
    assert gs.size_for(100.0, 98.0, direction="bullish", gap_sizing=STAMP) == plain


def test_short_with_the_gap_rule_is_cut():
    out = gs.size_for(100.0, 102.0, direction="bearish", gap_sizing=STAMP)
    assert (out["shares"], out["risk_amount"], out["gap_risk_amount"], out["gap_sized"]) == (33.33, 66.67, 100.0, True)


def test_short_with_rule_stop_is_todays_sizing_byte_for_byte():
    plain = account.compute_position_size(100.0, 102.0)
    out = gs.size_for(100.0, 102.0, direction="bearish", gap_sizing={**STAMP, "rule": "stop"})
    assert out == plain and json.dumps(out) == json.dumps(plain)


@pytest.mark.parametrize("stamp", [None, {**STAMP, "up_gap_p99_pct": None, "n_up_gaps": 40}])
def test_short_without_a_usable_p99_sizes_on_the_stop_and_says_n_a(stamp):
    plain = account.compute_position_size(100.0, 102.0)
    assert gs.size_for(100.0, 102.0, direction="bearish", gap_sizing=stamp) == {**plain, **NO_GAP}


def test_exception_in_the_gap_path_falls_back_loudly(monkeypatch, caplog):
    real = account.compute_position_size

    def flaky(entry, stop_loss, account_cfg=None, **kw):
        if kw.get("gap_floor_pct") is not None:
            raise RuntimeError("boom")
        return real(entry, stop_loss, account_cfg, **kw)

    monkeypatch.setattr(account, "compute_position_size", flaky)
    with caplog.at_level(logging.INFO, logger="swingbot.core.planning.gap_sizing"):
        out = gs.size_for(100.0, 102.0, direction="bearish", gap_sizing=STAMP, label="ZZZ")
    assert out == {**real(100.0, 102.0), **NO_GAP}
    assert "ZZZ: gap sizing fell back to stop (boom)" in caplog.text


def test_two_argument_test_doubles_keep_working(monkeypatch):
    monkeypatch.setattr(account, "compute_position_size", lambda entry, stop: {"shares": 10.0})
    assert gs.size_for(100.0, 98.0, direction="bullish", gap_sizing=None) == {"shares": 10.0}


def test_explicit_account_cfg_is_passed_through():
    cfg = {**CFG, "risk_pct": 2.0}
    assert gs.size_for(100.0, 98.0, direction="bullish", gap_sizing=None, account_cfg=cfg)["shares"] == 100.0
    assert gs.size_for(100.0, 102.0, direction="bearish", gap_sizing=STAMP, account_cfg=cfg)["shares"] == 66.67


def test_size_for_plan_and_trade_read_the_stamp():
    plan = _plan(gap_sizing=STAMP)
    assert gs.size_for_plan(plan)["shares"] == 33.33                       # trigger_price default
    assert gs.size_for_plan(plan, entry=101.0)["shares"] == 33.0           # stop 1.00 away, gap 3.03
    stub = SimpleNamespace(ticker="OLD", direction="bullish", trigger_price=100.0, entry_price=None, stop_loss=98.0)
    assert gs.size_for_plan(stub) == account.compute_position_size(100.0, 98.0)   # no gap_sizing attribute
    trade = {"ticker": "ZZZ", "direction": "bearish", "entry": 100.0, "stop_loss": 102.0, "gap_sizing": STAMP}
    assert gs.size_for_trade(trade)["shares"] == 33.33
    assert gs.size_for_trade({**trade, "gap_sizing": None}) == {**account.compute_position_size(100.0, 102.0), **NO_GAP}


def test_gap_risk_amount_for():
    assert gs.gap_risk_amount_for(33.33, 100.0, 102.0, STAMP) == 99.99
    assert gs.gap_risk_amount_for(20.0, 100.0, 105.0, STAMP) == 100.0      # stop wider than the gap
    assert gs.gap_risk_amount_for(20.0, 100.0, 102.0, {**STAMP, "rule": "stop"}) is None
    assert gs.gap_risk_amount_for(20.0, 100.0, 102.0, None) is None
    assert gs.gap_risk_amount_for(None, 100.0, 102.0, STAMP) is None


# --- the plan field and the long plan-doc pin -------------------------------------

def test_long_plan_doc_keeps_exactly_its_pre_v183_keys():
    d = plan_to_dict(_plan("bullish"))
    assert list(d) == PRE_V183_PLAN_KEYS
    assert "gap_sizing" not in json.dumps(d)


def test_stamped_short_round_trips_and_unstamped_omits_the_key():
    stamped = plan_to_dict(_plan(gap_sizing=STAMP))
    assert list(stamped) == PRE_V183_PLAN_KEYS + ["gap_sizing"]
    assert plan_from_dict(json.loads(json.dumps(stamped))).gap_sizing == STAMP
    assert "gap_sizing" not in plan_to_dict(_plan())
    assert plan_from_dict(plan_to_dict(_plan())).gap_sizing is None


# --- the two live stamp sites ---------------------------------------------------------

def _attach(monkeypatch, plan, df, now=None):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(analyze, "_build_quality_inputs", lambda *args, **kwargs: {})
    monkeypatch.setattr(analyze, "build_confluence_plan", lambda *args, **kwargs: plan)
    monkeypatch.setattr(analyze, "primary_strategy_for", lambda scenario: "MACD")
    monkeypatch.setattr(analyze, "stamp_entry_context",
                        lambda plan, df, asof: setattr(plan, "entry_context", {"stamped": True}))
    item = SimpleNamespace(rs_combined=None, sector_rs_percentile=None, conf=None, htf_bias=None,
                           target_confluence=None)
    scenario = SimpleNamespace(direction=plan.direction, entry=100.0)
    analyze.attach_plan_v2(item, scenario, df, "ZZZ", "3m", now=now)
    return item.plan_v2


def test_attach_plan_v2_stamps_a_short_outside_entry_context(monkeypatch):
    plan = _attach(monkeypatch, _plan(stop_loss=101.5), _signed_gaps())
    assert plan.gap_sizing == {"rule": "gap_p99", "up_gap_p99_pct": pytest.approx(2.0), "n_up_gaps": 125}
    assert plan.entry_context == {"stamped": True}


def test_attach_plan_v2_leaves_a_long_unstamped(monkeypatch):
    plan = _attach(monkeypatch, _plan("bullish"), _signed_gaps())
    assert plan.gap_sizing is None
    assert list(plan_to_dict(plan)) == PRE_V183_PLAN_KEYS


def test_strategy_plan_is_stamped_from_its_completed_frame(monkeypatch):
    monkeypatch.setattr(sp, "build_strategy_plan", lambda *args, **kwargs: _plan(source="strategy"))
    monkeypatch.setattr(sp, "stamp_badge", lambda plan: None)
    monkeypatch.setattr(sp, "stamp_cohort", lambda plan, state: None)
    monkeypatch.setattr(sp, "stamp_entry_context", lambda plan, df, asof: None)
    plan = sp.build_strategy_plan_at(_signed_gaps(), ticker="ZZZ", strategy="MACD", horizon_key="3m",
                                     direction="bearish", regime2_state="bear_quiet")
    assert plan.gap_sizing == {"rule": "gap_p99", "up_gap_p99_pct": pytest.approx(2.0), "n_up_gaps": 125}


def test_forming_bar_is_excluded_and_a_rebuild_gets_the_same_stamp():
    df = _signed_gaps(end="2026-10-21")
    df.iloc[-1, df.columns.get_loc("Open")] = 130.0                 # today's forming bar gaps up 30%
    first, rebuilt, after_close = _plan(), _plan(), _plan()
    analyze._stamp_gap_sizing_live(first, df, datetime(2026, 10, 21, 15, 0, tzinfo=timezone.utc))
    analyze._stamp_gap_sizing_live(rebuilt, df, datetime(2026, 10, 21, 19, 0, tzinfo=timezone.utc))
    analyze._stamp_gap_sizing_live(after_close, df, datetime(2026, 10, 21, 21, 30, tzinfo=timezone.utc))
    assert first.gap_sizing == rebuilt.gap_sizing
    assert first.gap_sizing["n_up_gaps"] == 125                     # forming bar not counted
    assert after_close.gap_sizing["n_up_gaps"] == 126               # after the close the bar is complete


def test_replay_never_stamps_and_entry_context_has_no_gap_sizing_key():
    from swingbot.core.backtesting import backtest_scenarios
    from swingbot.core.edge.context import FEATURE_KEYS
    assert "gap_sizing" not in inspect.getsource(backtest_scenarios)
    assert not any("gap_sizing" in key or "up_gap" in key for key in FEATURE_KEYS)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/planning/test_gap_sizing.py`
Expected: FAIL — `ImportError: cannot import name 'gap_sizing' from 'swingbot.core.planning'`.

- [ ] **Step 3: Create `swingbot/core/planning/gap_sizing.py`**

```python
"""v183 Part A: the one sizing path for plans and paper trades.

Every site that turns a plan or a paper trade into a share count calls
size_for / size_for_plan / size_for_trade, never compute_position_size
directly (stop_scope.risk_sizing_ok excepted: it runs before the stamp
exists, and a gap cut only lowers shares). The rule in force and the p99
up-gap are stamped on a SHORT plan once, at live creation, from completed
bars; every reader uses that stamp, so a later switch flip or a missing
frame never re-sizes an alerted plan differently. A long never reaches the
gap branch. Sizing and display only -- no filter, score or gate reads this.
"""
from __future__ import annotations

import logging

from swingbot import config
from swingbot.core.planning import account

log = logging.getLogger(__name__)

RULE_GAP = "gap_p99"
RULE_STOP = "stop"
MIN_UP_GAPS = 60
LOOKBACK = 250
_NO_GAP = {"gap_risk_amount": None, "gap_sized": False, "gap_floor_pct": None}


def _rule() -> str:
    return RULE_GAP if config.SHORT_GAP_SIZING else RULE_STOP


def gap_sizing_stamp(df, direction: str) -> dict | None:
    """The stamp for a plan created now from `df` (completed bars only); None for a long."""
    if direction != "bearish":
        return None
    from swingbot.core.edge.gates import gap_stats
    stats = gap_stats(df, lookback=LOOKBACK)
    n_up = int(stats["n_up"])
    p99 = stats["p99_up_gap_pct"] if n_up >= MIN_UP_GAPS else None
    return {"rule": _rule(), "up_gap_p99_pct": p99, "n_up_gaps": n_up}


def stamp_gap_sizing(plan, df) -> None:
    """Set plan.gap_sizing; never raises. A short without a usable p99 logs one line."""
    try:
        plan.gap_sizing = gap_sizing_stamp(df, plan.direction)
    except Exception as exc:
        plan.gap_sizing = ({"rule": _rule(), "up_gap_p99_pct": None, "n_up_gaps": 0}
                           if plan.direction == "bearish" else None)
        log.info("%s: gap sizing stamp failed (%s) -- sized on the stop", plan.ticker, exc)
        return
    if plan.gap_sizing is not None and plan.gap_sizing["up_gap_p99_pct"] is None:
        log.info("%s: gap sizing p99 n/a (%d up-gaps, need %d) -- sized on the stop",
                 plan.ticker, plan.gap_sizing["n_up_gaps"], MIN_UP_GAPS)


def gap_floor_for(direction: str | None, gap_sizing: dict | None) -> float | None:
    """The p99 floor (percent) to size on, or None: long, no stamp, rule stop, no p99."""
    if direction != "bearish" or not gap_sizing or gap_sizing.get("rule") != RULE_GAP:
        return None
    p99 = gap_sizing.get("up_gap_p99_pct")
    return float(p99) if p99 is not None and p99 > 0 else None


def _stop_only(entry, stop_loss, account_cfg):
    # Two positional args when no config is given: today's exact call shape.
    if account_cfg is None:
        return account.compute_position_size(entry, stop_loss)
    return account.compute_position_size(entry, stop_loss, account_cfg)


def _with_no_gap(result):
    return None if result is None else {**result, **_NO_GAP}


def size_for(entry, stop_loss, *, direction, gap_sizing, account_cfg=None, label: str = "") -> dict | None:
    """The share count for one plan or trade under its stamped rule."""
    if direction != "bearish" or (gap_sizing or {}).get("rule") == RULE_STOP:
        return _stop_only(entry, stop_loss, account_cfg)
    floor = gap_floor_for(direction, gap_sizing)
    if floor is None:
        return _with_no_gap(_stop_only(entry, stop_loss, account_cfg))
    try:
        return account.compute_position_size(entry, stop_loss, account_cfg, gap_floor_pct=floor)
    except Exception as exc:
        log.info("%s: gap sizing fell back to stop (%s)", label, exc)
        return _with_no_gap(_stop_only(entry, stop_loss, account_cfg))


def size_for_plan(plan, entry=None, account_cfg=None) -> dict | None:
    price = entry if entry is not None else (plan.trigger_price or plan.entry_price)
    return size_for(price, plan.stop_loss, direction=getattr(plan, "direction", None),
                    gap_sizing=getattr(plan, "gap_sizing", None), account_cfg=account_cfg,
                    label=getattr(plan, "ticker", ""))


def size_for_trade(trade: dict, entry=None, account_cfg=None) -> dict | None:
    price = entry if entry is not None else trade.get("entry")
    return size_for(price, trade.get("stop_loss"), direction=trade.get("direction"),
                    gap_sizing=trade.get("gap_sizing"), account_cfg=account_cfg,
                    label=trade.get("ticker", ""))


def gap_risk_amount_for(shares, entry, stop_loss, gap_sizing) -> float | None:
    """What a p99 gap would cost an open short of `shares`; None without a usable p99."""
    floor = gap_floor_for("bearish", gap_sizing)
    if floor is None or shares is None or entry is None or stop_loss is None:
        return None
    distance = account._sizing_distance(float(entry), abs(float(entry) - float(stop_loss)), floor)
    return round(float(shares) * distance, 2)
```

- [ ] **Step 4: Add the field and the omission to `swingbot/core/planning/plan_types.py`**

As the last field of `TradePlanV2`, after `price_confirmed`:

```python
    # v183 Part A (planning/gap_sizing.py): the sizing rule in force and the
    # p99 up-gap, stamped once at LIVE creation for shorts only --
    # {"rule": "gap_p99" | "stop", "up_gap_p99_pct": float | None,
    #  "n_up_gaps": int}. None for every long, every replayed plan and every
    # plan persisted before v183. Live config, so never an entry_context key.
    # Omitted from plan_to_dict while None (_OMIT_WHEN_NONE).
    gap_sizing: dict | None = None
```

Replace `plan_to_dict`:

```python
# v183: optional fields written only when set -- a None here is omitted, never
# stored as null, so every plan doc without them (every long) stays
# byte-identical to its pre-v183 shape. plan_from_dict defaults them back.
_OMIT_WHEN_NONE = ("gap_sizing",)


def plan_to_dict(plan: TradePlanV2) -> dict:
    d = dataclasses.asdict(plan)
    # tuples (quality_breakdown rows) -> lists so json round-trips cleanly
    d["quality_breakdown"] = [list(row) for row in d.get("quality_breakdown", [])]
    for key in _OMIT_WHEN_NONE:
        if d.get(key) is None:
            d.pop(key, None)
    return d
```

- [ ] **Step 5: Stamp at the two live creation sites**

In `swingbot/core/scanning/analyze.py`, add `from swingbot.core.planning.gap_sizing import stamp_gap_sizing` after the `stamp_entry_context` import (:36). Then add this helper directly above `attach_plan_v2`:

```python
def _stamp_gap_sizing_live(plan, df, now) -> None:
    """v183: stamp the gap-sizing rule from COMPLETED bars (today's forming
    bar dropped during the session). Never raises -- a frame problem leaves a
    short with no p99, which sizes on the stop."""
    from .strategy_pass import completed_frame
    try:
        frame = completed_frame(df, now or datetime.now(timezone.utc))
    except Exception:
        frame = None
    stamp_gap_sizing(plan, frame)
```

In `attach_plan_v2`, directly after the closing `})` of the `stamp_entry_context(plan, df, {...})` call, add:

```python
        _stamp_gap_sizing_live(plan, df, now)
```

In `swingbot/core/scanning/strategy_pass.py`, add `from swingbot.core.planning.gap_sizing import stamp_gap_sizing` after the `params` import (:12). In `build_strategy_plan_at`, directly after `stamp_entry_context(plan, df_completed, ...)`, add:

```python
    stamp_gap_sizing(plan, df_completed)
```

Do not touch `params.stamp_entry_context`, `edge/context.py` or `backtest_scenarios.py`: the replay must never stamp.

- [ ] **Step 6: Run the tests**

Run: `python scripts/dev/testrun.py file tests/planning/test_gap_sizing.py`
Expected: PASS.
Run: `python scripts/dev/testrun.py file tests/planning/test_plan_serialization.py`
Expected: PASS (round-trip over every field still holds; `gap_sizing` defaults back to `None`).
Run: `python scripts/dev/testrun.py file tests/scanning/test_live_context_stamp.py`
Expected: PASS.
Run: `python scripts/dev/testrun.py file tests/scanning/test_strategy_pass_emit.py`
Expected: PASS.

If `test_attach_plan_v2_stamps_a_short_outside_entry_context` fails on a bearish-only check inside `attach_plan_v2` that has nothing to do with v183, give the plan the geometry that check needs. Do not stub out `_stamp_gap_sizing_live`.

- [ ] **Step 7: Check complexity**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0. `attach_plan_v2` stays at 12, `build_strategy_plan_at` at 3, and every new function is below 15.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/planning/gap_sizing.py swingbot/core/planning/plan_types.py swingbot/core/scanning/analyze.py swingbot/core/scanning/strategy_pass.py tests/planning/test_gap_sizing.py
git commit -m "feat(v183): one gap-aware sizing path reading a per-plan stamp set at creation"
```

# Phase 3 — The re-size sites

### Task V183-5: The four re-size sites read the stamp

**Model:** opus — four call sites across scanning and admin must agree with the alert; two of them sit inside legacy functions (CC 24 and 17) that must not grow; and existing two-argument test doubles must keep working.

**Files:**
- Modify: `swingbot/core/scanning/plan_table.py:129-137` (`_sizing_snapshot`; import)
- Modify: `swingbot/core/scanning/outlook_run.py:199-209` (`_risk_dollars`; import)
- Modify: `swingbot/admin/dashboard.py:447` (`build_open_trade_views` sizing map; import)
- Modify: `swingbot/core/scanning/analyze.py:254-255` (`build_decision_context`; extend V183-4's import)
- Create: `tests/scanning/test_gap_sizing_resize_sites.py`

**Interfaces:**
- Consumes: `size_for(entry, stop_loss, *, direction, gap_sizing, account_cfg=None, label="")`, `size_for_plan(plan, entry=None, account_cfg=None)`, `TradePlanV2.gap_sizing` (V183-4); `compute_position_size(..., gap_floor_pct=...)` result keys `gap_risk_amount`, `gap_sized`, `gap_floor_pct` (V183-3).
- Produces:
  - `_sizing_snapshot(entry, plan) -> dict | None` keeps the same name and signature, and `execution_embeds` still imports it by name.
    - A stamped short now gets the gap keys and the cut shares.
    - An unstamped short gets the stop shares plus `gap_risk_amount=None`, `gap_sized=False`.
    - A long gets today's dict exactly.
  - V183-8's gap line reads these keys.
  - `outlook_run._risk_dollars(plan)` returns the cut shares × stop distance.
  - The dashboard `views["sizing"][trade_id]` and the decision chart's `ctx["sizing"]["shares"]` both reflect the stamp.

**What stays as it is (spec "Caps hold on the cut size"):**
- `ctx["sizing"]["heat_after"]` keeps adding the configured `candidate_risk_pct`, not the cut size. The cut only lowers shares, so the configured figure stays a valid upper bound.
- `stop_scope.risk_sizing_ok` (the seventh site, `stop_scope.py:71`) is not edited. It runs before the stamp exists, and a gap cut only shrinks shares.

- [ ] **Step 1: Write the failing test** — `tests/scanning/test_gap_sizing_resize_sites.py`

```python
"""v183: every re-size site sizes a stamped short through the one sizing path."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.admin import dashboard
from swingbot.core.planning import account
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2
from swingbot.core.scanning import analyze, execution_embeds, plan_table
from swingbot.core.scanning import outlook_run as orun

CFG = {"balance": 10_000.0, "risk_pct": 1.0, "sizing_mode": "risk_pct", "position_pct": 10.0,
       "max_position_pct": 100.0, "max_position_value_absolute": 0, "max_risk_amount_absolute": 0}
STAMP = {"rule": "gap_p99", "up_gap_p99_pct": 3.0, "n_up_gaps": 125}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(account.opex, "size_mult", lambda *a, **k: 1.0)
    monkeypatch.setattr(account, "load_account_config", lambda: dict(CFG))
    monkeypatch.setattr(analyze, "load_account_config", lambda: dict(CFG))
    monkeypatch.setattr(config, "SHORT_GAP_SIZING", True)


def _plan(direction="bearish", **kw):
    short = direction == "bearish"
    base = dict(plan_id="p1", ticker="ZZZ", created_at="2026-10-20", source="confluence", strategy="MACD",
                horizon_key="3m", direction=direction, entry_type="stop_entry", trigger_price=100.0,
                entry_price=None, expiry_bars=5, stop_loss=102.0 if short else 98.0,
                tp1=95.0 if short else 105.0, tp1_fraction=0.5, tp2=None, breakeven_trigger_fraction=0.5,
                trail_atr_mult=2.0, quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
                status=PlanStatus.PENDING)
    base.update(kw)
    return TradePlanV2(**base)


def _trade(tid, direction, stop, gap_sizing=None):
    t = {"id": tid, "ticker": "ZZZ", "direction": direction, "entry": 100.0, "stop_loss": stop,
         "take_profit": 95.0 if direction == "bearish" else 105.0,
         "opened_at": datetime.now(timezone.utc).isoformat()}
    if gap_sizing is not None:
        t["gap_sizing"] = gap_sizing
    return t


# --- plan_table._sizing_snapshot (Discord full/simple, v81 ticket) ----------------

def test_snapshot_cuts_a_stamped_short():
    out = plan_table._sizing_snapshot(100.0, _plan(gap_sizing=STAMP))
    assert (out["shares"], out["risk_amount"], out["gap_risk_amount"], out["gap_sized"]) == (33.33, 66.67, 100.0, True)


def test_snapshot_of_a_long_is_todays_dict():
    assert plan_table._sizing_snapshot(100.0, _plan("bullish")) == account.compute_position_size(100.0, 98.0)


def test_snapshot_of_a_switch_off_short_is_todays_dict():
    plan = _plan(gap_sizing={**STAMP, "rule": "stop"})
    assert plan_table._sizing_snapshot(100.0, plan) == account.compute_position_size(100.0, 102.0)


def test_snapshot_of_a_pre_v183_short_sizes_on_the_stop_and_flags_n_a():
    out = plan_table._sizing_snapshot(100.0, _plan())
    assert out["shares"] == 50.0 and out["gap_risk_amount"] is None and out["gap_sized"] is False


def test_a_later_switch_flip_never_resizes_an_alerted_plan(monkeypatch):
    plan = _plan(gap_sizing=STAMP)
    monkeypatch.setattr(config, "SHORT_GAP_SIZING", False)
    assert plan_table._sizing_snapshot(100.0, plan)["shares"] == 33.33


def test_execution_ticket_uses_the_same_snapshot():
    assert execution_embeds._sizing_snapshot is plan_table._sizing_snapshot


def test_snapshot_still_swallows_a_sizing_failure(monkeypatch):
    def boom(entry, stop):
        raise ValueError("no account")
    monkeypatch.setattr(account, "compute_position_size", boom)
    assert plan_table._sizing_snapshot(100.0, _plan("bullish")) is None


# --- outlook_run._risk_dollars (v144 outlook card) ------------------------------

def test_outlook_risk_dollars_uses_the_cut_shares():
    assert orun._risk_dollars(_plan(gap_sizing=STAMP)) == 66.67     # 33.333 shares x 2.00 stop distance
    assert orun._risk_dollars(_plan("bullish")) == 100.0             # 50 shares x 2.00, as today


# --- admin dashboard open-trade sizing map --------------------------------------

def test_dashboard_sizing_map_reads_the_trade_stamp(monkeypatch):
    monkeypatch.setattr(dashboard, "_open_trade_prices", lambda trades: {})
    trades = [_trade("s1", "bearish", 102.0, STAMP), _trade("l1", "bullish", 98.0),
              _trade("old", "bearish", 102.0)]
    sizing = dashboard.build_open_trade_views(trades, dict(CFG))["sizing"]
    assert sizing["s1"]["shares"] == 33.33 and sizing["s1"]["gap_sized"] is True
    assert sizing["l1"] == account.compute_position_size(entry=100.0, stop_loss=98.0, account_cfg=dict(CFG))
    assert sizing["old"]["shares"] == 50.0 and sizing["old"]["gap_risk_amount"] is None


# --- analyze.build_decision_context (decision chart sizing box) -----------------

def _decision_ctx(monkeypatch, plan):
    monkeypatch.setattr(analyze.trade_log, "get_trades", lambda **kw: [])
    monkeypatch.setattr(analyze.corr_mod, "cluster_exposure", lambda *a, **k: {"cluster": []})
    item = SimpleNamespace(plan_v2=plan, result=SimpleNamespace(ticker="ZZZ"))
    return analyze.build_decision_context(item, {}, None)


def test_decision_context_shows_the_cut_shares_and_keeps_heat_on_config_risk(monkeypatch):
    ctx = _decision_ctx(monkeypatch, _plan(gap_sizing=STAMP))
    assert ctx["sizing"]["shares"] == 33.33
    assert ctx["sizing"]["heat_after"] == ctx["sizing"]["heat_before"] + 1.0   # configured risk_pct, unchanged


def test_decision_context_of_a_long_is_unchanged(monkeypatch):
    ctx = _decision_ctx(monkeypatch, _plan("bullish"))
    assert ctx["sizing"]["shares"] == 50.0 and ctx["sizing"]["risk_pct"] == 1.0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scanning/test_gap_sizing_resize_sites.py`
Expected: FAIL. The stamped-short cases report `shares == 50.0`, and `KeyError: 'gap_risk_amount'` is raised. The long cases and `test_execution_ticket_uses_the_same_snapshot` already pass.

- [ ] **Step 3: Route the four sites through the one sizing path**

`swingbot/core/scanning/plan_table.py`: add `from swingbot.core.planning import gap_sizing` beside `from swingbot.core.planning import account` (keep the `account` import, since tests patch `plan_table.account`). Then:

```python
def _sizing_snapshot(entry, plan) -> dict | None:
    """A fresh sizing snapshot through the one v183 sizing path (a stamped
    short is gap-sized; a long is compute_position_size exactly), or None if
    sizing data isn't available -- swallows the exception rather than
    crashing, same render-time-snapshot convention used everywhere here."""
    try:
        return gap_sizing.size_for_plan(plan, entry=entry)
    except Exception as exc:
        swallowed(log, "scan.sizing_snapshot", exc, level=logging.DEBUG)
        return None
```

`swingbot/core/scanning/outlook_run.py`: add `from swingbot.core.planning import gap_sizing` after the `account_module` import. In `_risk_dollars`, replace the sizing line only:

```python
        sizing = gap_sizing.size_for_plan(plan, entry=plan.trigger_price)
```

The rest of `_risk_dollars` stays: the stop-distance multiplication, the `None` cases and the `swallowed` tag.

`swingbot/admin/dashboard.py`: add `from swingbot.core.planning.gap_sizing import size_for` after the `account` import at :31. Leave the existing `compute_position_size` import line as it is (it carries `# noqa: F401`). Replace line 447:

```python
        sizing_map[tid] = size_for(entry, sl, direction=t.get("direction"),
                                   gap_sizing=t.get("gap_sizing"), account_cfg=account_cfg,
                                   label=t.get("ticker", ""))
```

`swingbot/core/scanning/analyze.py`: extend V183-4's import to `from swingbot.core.planning.gap_sizing import size_for_plan, stamp_gap_sizing`. In `build_decision_context`, replace the two-line `account_module.compute_position_size(plan.trigger_price or plan.entry_price, plan.stop_loss, account_cfg)` call with:

```python
        sizing = size_for_plan(plan, account_cfg=account_cfg)
```

`size_for_plan`'s entry default is the same `plan.trigger_price or plan.entry_price`. The rest of the `ctx["sizing"]` block is unchanged, including `heat_after = heat_before + candidate_risk_pct`.

- [ ] **Step 4: Run the new tests and every test that patches these sites**

Run: `python scripts/dev/testrun.py file tests/scanning/test_gap_sizing_resize_sites.py`
Expected: PASS.
Run each of the following; Expected: PASS for every file (their two-argument `compute_position_size` doubles still receive two positional args):
- `python scripts/dev/testrun.py file tests/scanning/test_outlook_run.py`
- `python scripts/dev/testrun.py file tests/scanning/test_embeds_badges.py`
- `python scripts/dev/testrun.py file tests/scanning/test_transition_embeds.py`
- `python scripts/dev/testrun.py file tests/commands/test_plans_board.py`
- `python scripts/dev/testrun.py file tests/admin/test_admin_freshness.py`
- `python scripts/dev/testrun.py file tests/admin/test_dashboard_builders.py`
- `python scripts/dev/testrun.py file tests/charts/test_decision_chart.py`
- `python scripts/dev/testrun.py file tests/scanning/test_short_alert_parity.py`

If `test_admin_freshness.py::test_the_dashboard_summary_prices_at_the_dashboard_tier` now reaches the real sizer, that is fine: with `account_cfg={}` it returns `None`, as its double did. Leave the test as it is.

- [ ] **Step 5: Check complexity**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.
- `build_decision_context` may drop from 24 to 23, because the `or` moved into `size_for_plan`. If the gate reports that improvement, run `python scripts/dev/complexity_gate.py --update` to ratchet the baseline down. Otherwise drop `scripts/dev/complexity_baseline.json` from the commit below.
- `build_open_trade_views` stays at 17.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/plan_table.py swingbot/core/scanning/outlook_run.py swingbot/admin/dashboard.py swingbot/core/scanning/analyze.py tests/scanning/test_gap_sizing_resize_sites.py scripts/dev/complexity_baseline.json
git commit -m "feat(v183): plan table, outlook, dashboard and decision chart size through the gap stamp"
```

