# v130 — Swing significance tiers and BOS/CHoCH events: Implementation Plan (part 1: tiers, events and the snapshot)

> **For agentic workers:** this is part 1 of 2. The header block, Preconditions, Spec corrections and frozen readings, Global Constraints, File map, Review Focus and Parallelisation live in [`2026-10-03-v130-swing-significance-structure-events_0-index.md`](./2026-10-03-v130-swing-significance-structure-events_0-index.md) and apply to every task here. Read the index first, then pull one task (V130-1 .. V130-5) with `/task-brief <id>`; never read this file whole.

# Phase 1 — Tiers and events

### Task V130-1: Swing tiers and the major-pivot table

**Files:**
- Modify: `swingbot/core/market/structure.py` (append; add `import bisect`)
- Create: `tests/market/structure_tier_fixtures.py`
- Test: `tests/market/test_structure_tiers.py`

**Interfaces:**
- Consumes (v121): `PIVOT_K`, `pivot_confirmations(df, k) -> (sh_flags, sl_flags)` indexed by confirmation bar, `atr(df, 14)`, fixtures `zigzag`, `frame`, `UP`, `wavy_frame`; `tests.fixtures.ohlcv_parity.load_ohlcv(ticker)`.
- Produces: `SWING_MAJOR_ATR_M = 2.0`; `TIER_COLUMNS = ("kind", "pos", "price", "major_pos")`; `MAJOR_COLUMNS = ("last_msh_pos", "last_msh", "prior_msh_pos", "prior_msh", "last_msl_pos", "last_msl", "prior_msl_pos", "prior_msl")`; `pivot_tiers(df) -> pd.DataFrame` (one row per confirmed pivot, `kind` is `"sh"`/`"sl"`, `major_pos` is float, NaN while minor); `major_pivots(df) -> pd.DataFrame` (one row per bar, `MAJOR_COLUMNS`, NaN where fewer exist); private `_tiers(df, atr14, k=PIVOT_K)` and `_major_table(df, atr14)` taking a precomputed ATR array (V130-3 uses them to compute ATR once).
- Fixtures produced: `IMPACT_LATER`, `NO_BREAK`, `EARLY`, `UNDERCUT`, `NO_REF`, `WEAK`, `DOWN`, `tier_frame(points, *, mirror=False, leg=8, half=0.5)`, `weak_frame(*, mirror=False)`.

- [ ] **Step 1: Write the shared fixtures.**

```python
# tests/market/structure_tier_fixtures.py
"""Hand-built frames with known swing tiers and BOS/CHoCH events (v130).

Bars have an ABSOLUTE half-range (not a percent of price), so ATR14 at a pivot
is easy to reason about. ``mirror=True`` reflects every close around 250, which
turns each swing low into a swing high at the same bar."""
import numpy as np

from tests.conftest import make_ohlcv
from tests.market.structure_fixtures import zigzag

# One swing low at bar 16 below a swing high at bar 8; the low's reference high is 110.5.
IMPACT_LATER = [100, 110, 104, 118]     # reaction is there by bar 19; the close clears 110.5 at bar 20
NO_BREAK = [100, 120, 104, 114]         # 5 ATR of reaction, never closes above 120.5
EARLY = [100, 103, 101, 115]            # both conditions already hold at bar 18 = i + 2
UNDERCUT = [100, 110, 104, 109, 103, 118]   # the bar-16 low is undercut before any break
NO_REF = [110, 100, 120]                # leg=16: a swing low at bar 16 with no swing high before it
# Wide bars up to the bar-32 low (ATR14 = 4.0), narrow bars after: the close clears the
# reference high (109.0) at bar 36 on 1.6 ATR of reaction; 2 ATR arrives at bar 38.
WEAK = [100, 110, 104, 107, 105.5, 114]
# Falling major highs AND falling major lows, then a relief rally. Events (bar, kind, direction):
# (70, bos, bearish), (94, choch, bullish), (102, bos, bearish), (110, bos, bullish).
# Mirrored: the same bars with bullish <-> bearish swapped.
DOWN = [130, 120, 124, 116, 128, 110, 113, 106, 118, 100, 103, 96, 108, 90, 115]


def tier_frame(points, *, mirror=False, leg=8, half=0.5):
    closes = zigzag([250 - p for p in points] if mirror else points, leg=leg)
    df = make_ohlcv(closes, spread_pct=0.0)
    df["High"], df["Low"] = df["Close"] + half, df["Close"] - half
    return df


def weak_frame(*, mirror=False):
    half = np.where(np.arange(41) <= 32, 2.0, 0.25)
    return tier_frame(WEAK, mirror=mirror, half=half)
```

- [ ] **Step 2: Write the failing tests.**

```python
# tests/market/test_structure_tiers.py
import numpy as np
import pandas as pd
import pytest

from swingbot.core.market import structure as st
from swingbot.core.market.indicators import atr
from tests.conftest import make_ohlcv
from tests.fixtures.ohlcv_parity import load_ohlcv
from tests.market.structure_fixtures import UP, frame, wavy_frame
from tests.market.structure_tier_fixtures import (EARLY, IMPACT_LATER, NO_BREAK, NO_REF, UNDERCUT, tier_frame,
                                                  weak_frame)

MIRRORS = [(False, "sl"), (True, "sh")]


def _major_pos(df, kind, pos):
    tiers = st.pivot_tiers(df)
    row = tiers[(tiers["kind"] == kind) & (tiers["pos"] == pos)]
    assert len(row) == 1, tiers
    value = row["major_pos"].iloc[0]
    return None if pd.isna(value) else int(value)


def _same(a, b):
    return all((pd.isna(x) and pd.isna(y)) or x == y for x, y in zip(a, b))


def _reference_side(own, other, ext, opp, close, atr14, k, m):
    """Low-side reading of the spec, one bar at a time (slow on purpose)."""
    out = {}
    for i in own:
        refs, major = [p for p in other if p < i], None
        for j in range(i + 1, len(close) if refs and atr14[i] > 0 else 0):
            if ext[j] < ext[i]:
                break
            if j >= i + k and close[j] > opp[refs[-1]] and opp[i:j + 1].max() - ext[i] >= m * atr14[i]:
                major = j
                break
        out[int(i)] = major
    return out


def _reference(df, m=2.0, k=3):
    sh, sl = st.pivot_confirmations(df, k)
    sh_pos, sl_pos = list(np.flatnonzero(sh) - k), list(np.flatnonzero(sl) - k)
    high, low, close = (df[c].to_numpy(float) for c in ("High", "Low", "Close"))
    atr14 = atr(df, 14).to_numpy(float)
    lows = _reference_side(sl_pos, sh_pos, low, high, close, atr14, k, m)
    highs = _reference_side(sh_pos, sl_pos, -high, -low, -close, atr14, k, m)
    return {("sl", i): bar for i, bar in lows.items()} | {("sh", i): bar for i, bar in highs.items()}


def _random_walk(n=600, seed=7):
    closes = 100 * np.exp(np.cumsum(np.random.default_rng(seed).normal(0.0003, 0.015, n)))
    return make_ohlcv(closes, spread_pct=2.0)


@pytest.mark.parametrize("mirror,kind", MIRRORS)
def test_break_with_under_two_atr_of_reaction_stays_minor(mirror, kind):
    df = weak_frame(mirror=mirror)
    close = float(df["Close"].iloc[36])
    broken = close < float(df["Low"].iloc[24]) if mirror else close > float(df["High"].iloc[24])
    assert broken                                        # the reference swing IS closed through at bar 36
    assert atr(df, 14).iloc[32] == pytest.approx(4.0)
    assert _major_pos(df.iloc[:38], kind, 32) is None    # through bar 37: 1.9 ATR of reaction, still minor


@pytest.mark.parametrize("mirror,kind", MIRRORS)
def test_major_at_the_bar_the_reaction_arrives(mirror, kind):
    assert _major_pos(weak_frame(mirror=mirror), kind, 32) == 38


@pytest.mark.parametrize("mirror,kind", MIRRORS)
def test_big_reaction_without_a_break_stays_minor(mirror, kind):
    assert _major_pos(tier_frame(NO_BREAK, mirror=mirror), kind, 16) is None


@pytest.mark.parametrize("mirror,kind", MIRRORS)
def test_major_at_the_bar_the_break_arrives(mirror, kind):
    df = tier_frame(IMPACT_LATER, mirror=mirror)
    assert _major_pos(df.iloc[:20], kind, 16) is None    # bar 19: confirmed, reaction there, no break yet
    assert _major_pos(df, kind, 16) == 20


@pytest.mark.parametrize("mirror,kind", MIRRORS)
def test_never_major_before_the_pivot_is_confirmed(mirror, kind):
    df = tier_frame(EARLY, mirror=mirror)
    early = st.pivot_tiers(df.iloc[:19])                 # bar 18: both conditions hold, the low is unconfirmed
    assert early[early["pos"] == 16].empty
    assert _major_pos(df, kind, 16) == 19                # i + 3


@pytest.mark.parametrize("mirror,kind", MIRRORS)
def test_an_undercut_low_can_never_become_major(mirror, kind):
    df = tier_frame(UNDERCUT, mirror=mirror)
    assert _major_pos(df, kind, 16) is None
    assert _major_pos(df, kind, 32) == 36                # the low that undercut it does qualify


@pytest.mark.parametrize("mirror,kind", MIRRORS)
def test_no_reference_swing_stays_minor(mirror, kind):
    df = tier_frame(NO_REF, mirror=mirror, leg=16)
    assert atr(df, 14).iloc[16] > 0                      # not the ATR guard: there is simply no reference
    assert _major_pos(df, kind, 16) is None


@pytest.mark.parametrize("df", [wavy_frame(), _random_walk(), frame(UP), frame(UP, mirror=True),
                                load_ohlcv("TSLA").iloc[:700]], ids=["wavy", "walk", "up", "down", "tsla"])
def test_tiers_match_the_literal_spec_reading(df):
    tiers = st.pivot_tiers(df)
    got = {(r.kind, int(r.pos)): None if pd.isna(r.major_pos) else int(r.major_pos) for r in tiers.itertuples()}
    assert got == _reference(df)
    assert tuple(tiers.columns) == st.TIER_COLUMNS


def test_a_clean_uptrend_has_major_lows_and_no_major_high():
    majors = st.major_pivots(frame(UP)).iloc[-1]
    assert (majors["last_msl_pos"], majors["prior_msl_pos"]) == (64, 48)
    assert pd.isna(majors["last_msh_pos"])               # no high was ever followed by a close below a swing low


@pytest.mark.parametrize("df", [wavy_frame(), _random_walk(300)], ids=["wavy", "walk"])
def test_major_pivots_are_truncation_stable_on_every_cut(df):
    full = st.major_pivots(df)
    assert tuple(full.columns) == st.MAJOR_COLUMNS and full.index.equals(df.index)
    for t in range(len(df)):
        assert _same(st.major_pivots(df.iloc[:t + 1]).iloc[-1], full.iloc[t]), t


def test_major_pivots_are_truncation_stable_on_a_real_symbol():
    df = load_ohlcv("TSLA").iloc[:700]
    full = st.major_pivots(df)
    assert full["last_msh_pos"].notna().any() and full["last_msl_pos"].notna().any()
    for t in range(60, len(df), 7):
        assert _same(st.major_pivots(df.iloc[:t + 1]).iloc[-1], full.iloc[t]), t


def test_a_major_is_never_known_before_its_qualifying_bar():
    df = _random_walk()
    tiers, majors = st.pivot_tiers(df), st.major_pivots(df)
    major = tiers[tiers["major_pos"].notna()]
    assert len(major) > 10
    assert (major["major_pos"] >= major["pos"] + st.PIVOT_K).all()
    for row in major.itertuples():
        column = "last_msh_pos" if row.kind == "sh" else "last_msl_pos"
        assert not (majors[column].iloc[:int(row.major_pos)] == row.pos).any(), row


def test_majors_sort_by_pivot_index_not_by_when_they_qualified():
    majors = st.major_pivots(weak_frame())               # low 32 qualifies at 38, the OLDER low 16 at 39
    assert majors["last_msl_pos"].iloc[38] == 32 and pd.isna(majors["prior_msl_pos"].iloc[38])
    assert (majors["last_msl_pos"].iloc[39], majors["prior_msl_pos"].iloc[39]) == (32, 16)


def test_flat_and_nan_frames_do_not_raise():
    assert st.pivot_tiers(make_ohlcv(np.full(80, 100.0), spread_pct=0.0)).empty
    df = wavy_frame().copy()
    df.iloc[40:42, df.columns.get_loc("High")] = np.nan
    assert len(st.major_pivots(df)) == len(df)
```

- [ ] **Step 3:** Run `python scripts/dev/testrun.py file tests/market/test_structure_tiers.py`; expect FAIL (`AttributeError: module ... has no attribute 'pivot_tiers'`).

- [ ] **Step 4: Implement.** Add `import bisect` above `import math` at the top of `swingbot/core/market/structure.py`, then append below v121's last function:

```python
# swingbot/core/market/structure.py -- append
# --- v130: swing significance tiers and BOS/CHoCH events -------------------
SWING_MAJOR_ATR_M = 2.0     # frozen; a follow-on that searches it pre-registers its own grid
TIER_COLUMNS = ("kind", "pos", "price", "major_pos")
MAJOR_COLUMNS = ("last_msh_pos", "last_msh", "prior_msh_pos", "prior_msh",
                 "last_msl_pos", "last_msl", "prior_msl_pos", "prior_msl")


def _first_true(mask: np.ndarray) -> int | None:
    hits = np.flatnonzero(mask)
    return int(hits[0]) if len(hits) else None


def _major_bar(ext: np.ndarray, opp: np.ndarray, close: np.ndarray, i: int,
               ref: float | None, atr_at: float, k: int) -> int | None:
    """First bar ``j >= i + k`` at which the swing low at ``i`` is major, else None.

    Low-side form; a swing high is passed with every array negated. ``ext`` is
    the pivot's own extreme series, ``opp`` the opposite one, ``ref`` the
    reference swing's price. An undercut on any bar ``i+1 .. j`` disqualifies."""
    if ref is None or not atr_at > 0:
        return None
    start = i + k
    reaction = np.fmax.accumulate(opp[i:])[k:] - ext[i]
    hit = _first_true((close[start:] > ref) & (reaction >= SWING_MAJOR_ATR_M * atr_at))
    if hit is None:
        return None
    j = start + hit
    return None if (ext[i + 1:j + 1] < ext[i]).any() else j


def _side_tiers(kind: str, own: np.ndarray, other: np.ndarray, ext: np.ndarray, opp: np.ndarray,
                close: np.ndarray, atr14: np.ndarray, k: int) -> list[tuple]:
    rows = []
    for i in own:
        before = int(np.searchsorted(other, i))          # reference pivots strictly before i
        ref = float(opp[other[before - 1]]) if before else None
        rows.append((kind, int(i), abs(float(ext[i])), _major_bar(ext, opp, close, int(i), ref, atr14[i], k)))
    return rows


def _tiers(df: pd.DataFrame, atr14: np.ndarray, k: int = PIVOT_K) -> pd.DataFrame:
    sh, sl = pivot_confirmations(df, k)
    sh_pos, sl_pos = np.flatnonzero(sh) - k, np.flatnonzero(sl) - k
    high, low, close = (df[c].to_numpy(float) for c in ("High", "Low", "Close"))
    rows = (_side_tiers("sl", sl_pos, sh_pos, low, high, close, atr14, k)
            + _side_tiers("sh", sh_pos, sl_pos, -high, -low, -close, atr14, k))
    table = pd.DataFrame(rows, columns=list(TIER_COLUMNS)).astype({"major_pos": float})
    return table.sort_values(["pos", "kind"], kind="stable").reset_index(drop=True)


def pivot_tiers(df: pd.DataFrame) -> pd.DataFrame:
    """One row per confirmed k=3 pivot: ``kind`` ("sh"/"sl"), ``pos``, ``price``
    and ``major_pos`` -- the bar it became major at (NaN = still minor). A
    row's ``major_pos`` reads only bars ``<= major_pos``, so it never changes
    once set, whatever is appended to the frame."""
    return _tiers(df, atr(df, 14).to_numpy(float))


def _known_majors(n: int, side: pd.DataFrame) -> list[np.ndarray]:
    """Per bar: (last_pos, last_price, prior_pos, prior_price) of the pivots that
    are major AS OF that bar, ordered by pivot index (not by when they qualified)."""
    out = [np.full(n, np.nan) for _ in range(4)]
    known: list[tuple[int, float]] = []
    for pos, price, bar in sorted(zip(side["pos"], side["price"], side["major_pos"].astype(int)),
                                  key=lambda row: row[2]):
        bisect.insort(known, (int(pos), float(price)))
        out[0][bar:], out[1][bar:] = known[-1]
        if len(known) > 1:
            out[2][bar:], out[3][bar:] = known[-2]
    return out


def _major_table(df: pd.DataFrame, atr14: np.ndarray) -> pd.DataFrame:
    tiers = _tiers(df, atr14)
    majors = tiers[tiers["major_pos"].notna()]
    columns = (_known_majors(len(df), majors[majors["kind"] == "sh"])
               + _known_majors(len(df), majors[majors["kind"] == "sl"]))
    return pd.DataFrame(dict(zip(MAJOR_COLUMNS, columns)), index=df.index)


def major_pivots(df: pd.DataFrame) -> pd.DataFrame:
    """Per bar ``t``: positional index and price of the last two major swing
    highs and lows known at ``t`` (NaN where fewer exist). Truncation-stable."""
    return _major_table(df, atr(df, 14).to_numpy(float))
```

How the low-side form covers highs: a swing high is passed with `ext = -High`, `opp = -Low`, `close = -Close`. "Close above the reference high" becomes "close below the reference low", the running max of `opp` becomes the running min of Low, and "strictly lower low" becomes "strictly higher high". `price` is stored as `abs(ext[i])` so highs come back positive. `np.fmax.accumulate` skips NaN bars instead of poisoning every later bar.

- [ ] **Step 5:** Run `python scripts/dev/testrun.py file tests/market/test_structure_tiers.py`; expect PASS (26 tests; the two every-cut truncation tests take about 3 s each). Run `python scripts/dev/testrun.py file tests/market/test_structure_pivots.py` and `... file tests/market/test_structure_features.py`; expect PASS unchanged. Run `python -m radon cc -s -n C swingbot/core/market/structure.py`; expect no output.
- [ ] **Step 6:** Commit.

```bash
git add swingbot/core/market/structure.py tests/market/structure_tier_fixtures.py tests/market/test_structure_tiers.py
git commit -m "feat(v130): causal major/minor swing tiers on v121's k=3 pivots"
```

### Task V130-2: BOS and CHoCH events

**Files:**
- Modify: `swingbot/core/market/structure.py` (append)
- Test: `tests/market/test_structure_events.py`

**Interfaces:**
- Consumes (V130-1): `major_pivots(df)`, `pivot_tiers(df)`, `MAJOR_COLUMNS`, fixtures `DOWN`, `tier_frame`. Consumes (v121): `_state(piv)`, which reads `piv["last_sh"]`, `piv["prior_sh"]`, `piv["last_sl"]`, `piv["prior_sl"]` and returns `"up" | "down" | "mixed" | None`.
- Produces: `EVENT_COLUMNS = ("event_kind", "event_direction", "event_pos")`; `structure_events(df) -> pd.DataFrame` (one row per bar: `event_kind` is `"bos"`/`"choch"`/`None`, `event_direction` is `"bullish"`/`"bearish"`/`None`, `event_pos` is float, NaN if none); private `_major_state(row) -> str | None` (takes one `major_pivots` row) and `_events_table(df, majors) -> pd.DataFrame` (takes a precomputed `major_pivots` frame).

The `DOWN` fixture, bar by bar (prototyped): pivots at bars 16, 32, 48, 64, 80, 96 (highs) and 24, 56, 88, 104 (lows) become major; the lows at bars 8, 40 and 72 never do. The major state is `None` until bar 61, `down` at bars 62–69, `mixed` at 70–84, `down` at 85–101 and `mixed` from 102. Bar 70 closes below the major low at bar 56 with the state `down` at bar 69 → bearish `bos`. Bar 94 closes above the major high at bar 80 with the state `down` → bullish `choch`. Bar 102 closes below the major low at bar 88, state `down` → bearish `bos`. Bar 110 closes above the major high at bar 96, state `mixed` → bullish `bos`. Closes through major pivots before bar 62 fire nothing because the state is still `None`.

- [ ] **Step 1: Write the failing tests.**

```python
# tests/market/test_structure_events.py
import numpy as np
import pandas as pd
import pytest

from swingbot.core.market import structure as st
from tests.conftest import make_ohlcv
from tests.fixtures.ohlcv_parity import load_ohlcv
from tests.market.structure_fixtures import UP, frame, wavy_frame
from tests.market.structure_tier_fixtures import DOWN, tier_frame

SIDES = [(False, "bearish", "bullish"), (True, "bullish", "bearish")]   # mirror, trend side, counter side


def _fired(df):
    events = st.structure_events(df)
    first = events[events["event_pos"].notna()].drop_duplicates("event_pos")
    return [(int(row.event_pos), row.event_kind, row.event_direction) for row in first.itertuples()]


def _same(a, b):
    return all((pd.isna(x) and pd.isna(y)) or x == y for x, y in zip(a, b))


def _random_walk(n=300, seed=7):
    closes = 100 * np.exp(np.cumsum(np.random.default_rng(seed).normal(0.0003, 0.015, n)))
    return make_ohlcv(closes, spread_pct=2.0)


@pytest.mark.parametrize("mirror,trend,counter", SIDES)
def test_the_fixture_fires_exactly_its_four_events(mirror, trend, counter):
    assert _fired(tier_frame(DOWN, mirror=mirror)) == [
        (70, "bos", trend), (94, "choch", counter), (102, "bos", trend), (110, "bos", counter)]


@pytest.mark.parametrize("mirror,trend,counter", SIDES)
def test_a_break_with_the_trend_is_a_bos(mirror, trend, counter):
    df = tier_frame(DOWN, mirror=mirror)
    assert st._major_state(st.major_pivots(df).iloc[69]) == ("up" if mirror else "down")
    assert tuple(st.structure_events(df).iloc[70]) == ("bos", trend, 70)


@pytest.mark.parametrize("mirror,trend,counter", SIDES)
def test_a_break_against_the_trend_is_a_choch(mirror, trend, counter):
    df = tier_frame(DOWN, mirror=mirror)
    assert st._major_state(st.major_pivots(df).iloc[93]) == ("up" if mirror else "down")
    assert tuple(st.structure_events(df).iloc[94]) == ("choch", counter, 94)


@pytest.mark.parametrize("mirror", [False, True])
def test_later_closes_beyond_the_same_pivot_fire_nothing(mirror):
    df = tier_frame(DOWN, mirror=mirror)
    close, level = df["Close"].to_numpy(), st.major_pivots(df)["last_msl" if mirror else "last_msh"].iloc[93]
    beyond = close[95:98] < level if mirror else close[95:98] > level
    assert beyond.all()                                   # bars 95..97 also close beyond the broken pivot
    assert (st.structure_events(df)["event_pos"].iloc[94:102] == 94).all()


@pytest.mark.parametrize("mirror", [False, True])
def test_no_event_before_structure_exists(mirror):
    events = st.structure_events(tier_frame(DOWN, mirror=mirror)).iloc[:70]
    assert events["event_kind"].isna().all() and events["event_pos"].isna().all()


def test_a_clean_uptrend_fires_nothing():
    assert _fired(frame(UP)) == []                         # no major high exists, so major state is None


@pytest.mark.parametrize("df", [wavy_frame(), _random_walk(), tier_frame(DOWN), tier_frame(DOWN, mirror=True)],
                         ids=["wavy", "walk", "down", "up"])
def test_events_are_truncation_stable_on_every_cut(df):
    full = st.structure_events(df)
    assert tuple(full.columns) == st.EVENT_COLUMNS and full.index.equals(df.index)
    for t in range(len(df)):
        assert _same(st.structure_events(df.iloc[:t + 1]).iloc[-1], full.iloc[t]), t


def test_events_are_truncation_stable_on_a_real_symbol():
    df = load_ohlcv("TSLA").iloc[:700]
    full = st.structure_events(df)
    assert {kind for _, kind, _ in _fired(df)} == {"bos", "choch"}
    for t in range(60, len(df), 7):
        assert _same(st.structure_events(df.iloc[:t + 1]).iloc[-1], full.iloc[t]), t


@pytest.mark.parametrize("df", [_random_walk(600), load_ohlcv("TSLA").iloc[:700]], ids=["walk", "tsla"])
def test_an_event_reads_only_majors_known_the_bar_before(df):
    majors, close = st.major_pivots(df), df["Close"].to_numpy()
    tiers = st.pivot_tiers(df)
    major_bar = {(r.kind, int(r.pos)): r.major_pos for r in tiers.itertuples()}
    fired = _fired(df)
    assert fired
    for bar, _, direction in fired:
        before = majors.iloc[bar - 1]
        kind, pos, level = (("sh", before["last_msh_pos"], before["last_msh"]) if direction == "bullish"
                            else ("sl", before["last_msl_pos"], before["last_msl"]))
        assert major_bar[(kind, int(pos))] < bar            # never on the bar the pivot became major
        assert close[bar] > level if direction == "bullish" else close[bar] < level
```

- [ ] **Step 2:** Run `python scripts/dev/testrun.py file tests/market/test_structure_events.py`; expect FAIL (`AttributeError: module ... has no attribute 'structure_events'`).

- [ ] **Step 3: Implement.** Append to `swingbot/core/market/structure.py`:

```python
# swingbot/core/market/structure.py -- append
EVENT_COLUMNS = ("event_kind", "event_direction", "event_pos")


def _major_state(row) -> str | None:
    """v121's ``_state`` rule on the major columns of one ``major_pivots`` row."""
    return _state({"last_sh": row["last_msh"], "prior_sh": row["prior_msh"],
                   "last_sl": row["last_msl"], "prior_sl": row["prior_msl"]})


def _first_breaks(close: np.ndarray, level_pos: np.ndarray, level: np.ndarray, sign: int) -> list[int]:
    """Bars whose close is the FIRST beyond a major pivot, judged against the
    pivot that was the last major at the bar before (so never the bar it
    became major on). ``sign`` +1 breaks upward, -1 downward."""
    beyond = sign * (close[1:] - level[:-1]) > 0          # NaN level -> False
    bars, seen = [], set()
    for bar in np.flatnonzero(beyond) + 1:
        pivot = level_pos[bar - 1]
        if pivot not in seen:
            seen.add(pivot)
            bars.append(int(bar))
    return bars


def _events_table(df: pd.DataFrame, majors: pd.DataFrame) -> pd.DataFrame:
    n = len(df)
    close = df["Close"].to_numpy(float)
    kind, direction = np.full(n, None, dtype=object), np.full(n, None, dtype=object)
    pos = np.full(n, np.nan)
    ups = _first_breaks(close, majors["last_msh_pos"].to_numpy(), majors["last_msh"].to_numpy(), 1)
    downs = _first_breaks(close, majors["last_msl_pos"].to_numpy(), majors["last_msl"].to_numpy(), -1)
    for bar, side in sorted([(b, "bullish") for b in ups] + [(b, "bearish") for b in downs]):
        state = _major_state(majors.iloc[bar - 1])
        if state is None:
            continue                                      # no structure yet: no event, pivot spent
        against = "down" if side == "bullish" else "up"
        kind[bar:], direction[bar:], pos[bar:] = ("choch" if state == against else "bos"), side, bar
    return pd.DataFrame(dict(zip(EVENT_COLUMNS, (kind, direction, pos))), index=df.index)


def structure_events(df: pd.DataFrame) -> pd.DataFrame:
    """Per bar ``t``: the latest BOS/CHoCH at a bar ``<= t`` -- ``event_kind``
    ("bos"/"choch"/None), ``event_direction`` ("bullish"/"bearish"/None) and
    ``event_pos`` (NaN if none). Truncation-stable."""
    return _events_table(df, major_pivots(df))
```

`_first_breaks` compares `close[1:]` with `level[:-1]`: bar `j`'s close against the last major known at `j − 1`. That one-bar offset is the whole same-bar guard, so do not "simplify" it to an aligned comparison. A NaN level compares `False`, so bars before the first major fire nothing. Slice assignment (`kind[bar:] = ...`) forward-fills the latest event; a later event overwrites the tail.

- [ ] **Step 4:** Run `python scripts/dev/testrun.py file tests/market/test_structure_events.py`; expect PASS (18 tests). Run `python -m radon cc -s -n C swingbot/core/market/structure.py`; expect no output.
- [ ] **Step 5:** Commit.

```bash
git add swingbot/core/market/structure.py tests/market/test_structure_events.py
git commit -m "feat(v130): BOS/CHoCH events on breaks of major swings"
```

### Task V130-3: The eight snapshot keys

**Files:**
- Modify: `swingbot/core/market/structure.py` (append)
- Test: `tests/market/test_major_structure_features.py`

**Interfaces:**
- Consumes (V130-1, V130-2): `_major_table(df, atr14)`, `_events_table(df, majors)`, `_major_state(row)`, `major_pivots`, `structure_events`. Consumes (v121): `confirmed_pivots(df)` (columns `last_sl_pos`, `last_sh_pos`), `MIN_BARS = 60`, `_num(value)`, `atr`.
- Produces: `MAJOR_KEYS = ("structure_state_major", "structure_aligned_major", "major_sh_atr", "major_sl_atr", "struct_event_last", "struct_event_bars_ago", "last_sl_reaction_atr", "last_sh_reaction_atr")`; `major_structure_features(df, direction) -> dict` with exactly `MAJOR_KEYS` in that order. Types: `structure_state_major` is `"up" | "down" | "mixed" | None`; `structure_aligned_major` is Python `bool` or `None`; `struct_event_last` is one of `"bos_with"`, `"bos_against"`, `"choch_with"`, `"choch_against"` or `None`; `struct_event_bars_ago` is `int` or `None`; the four `*_atr` keys are floats rounded to 6 or `None`.

`major_sh_atr` and `major_sl_atr` are named by side and not direction-signed (as v121's `swing_high_atr`/`swing_low_atr`); a negative value means the close is already beyond that major pivot. "with" means the event's direction equals the trade's.

- [ ] **Step 1: Write the failing tests.**

```python
# tests/market/test_major_structure_features.py
import numpy as np
import pytest

from swingbot.core.market import structure as st
from swingbot.core.market.indicators import atr
from tests.conftest import make_ohlcv
from tests.fixtures.ohlcv_parity import load_ohlcv
from tests.market.structure_fixtures import UP, frame, wavy_frame
from tests.market.structure_tier_fixtures import DOWN, tier_frame


def _cut(mirror, last_bar):
    return tier_frame(DOWN, mirror=mirror).iloc[:last_bar + 1]


@pytest.mark.parametrize("mirror,state", [(False, "down"), (True, "up")])
def test_major_state_and_alignment_follow_the_trade_direction(mirror, state):
    df = _cut(mirror, 93)
    with_trend, counter = ("bullish", "bearish") if mirror else ("bearish", "bullish")
    assert st.major_structure_features(df, with_trend)["structure_state_major"] == state
    assert st.major_structure_features(df, with_trend)["structure_aligned_major"] is True
    assert st.major_structure_features(df, counter)["structure_aligned_major"] is False


@pytest.mark.parametrize("mirror,with_side,against_side", [(False, "bullish", "bearish"), (True, "bearish", "bullish")])
def test_choch_is_labelled_with_or_against_the_trade(mirror, with_side, against_side):
    df = _cut(mirror, 96)                                  # CHoCH fired at bar 94
    out = st.major_structure_features(df, with_side)
    assert (out["struct_event_last"], out["struct_event_bars_ago"]) == ("choch_with", 2)
    assert type(out["struct_event_bars_ago"]) is int
    assert st.major_structure_features(df, against_side)["struct_event_last"] == "choch_against"


@pytest.mark.parametrize("mirror,with_side,against_side", [(False, "bearish", "bullish"), (True, "bullish", "bearish")])
def test_bos_is_labelled_with_or_against_the_trade(mirror, with_side, against_side):
    df = _cut(mirror, 70)                                  # BOS fired on the final bar
    out = st.major_structure_features(df, with_side)
    assert (out["struct_event_last"], out["struct_event_bars_ago"]) == ("bos_with", 0)
    assert st.major_structure_features(df, against_side)["struct_event_last"] == "bos_against"


def test_major_distances_are_side_named_not_direction_signed():
    df = _cut(False, 93)
    majors = st.major_pivots(df).iloc[-1]
    close, atr14 = float(df["Close"].iloc[-1]), float(atr(df, 14).iloc[-1])
    out = st.major_structure_features(df, "bullish")
    assert out["major_sh_atr"] == pytest.approx((majors["last_msh"] - close) / atr14, abs=1e-6)
    assert out["major_sl_atr"] == pytest.approx((close - majors["last_msl"]) / atr14, abs=1e-6)
    assert out["major_sh_atr"] == st.major_structure_features(df, "bearish")["major_sh_atr"]


def test_reaction_of_the_last_swing_low_in_atr_at_the_pivot():
    df = _cut(False, 96)                                   # last confirmed k=3 low is bar 88, rally still running
    high, low = df["High"].to_numpy(), df["Low"].to_numpy()
    expected = round((high[88:].max() - low[88]) / float(atr(df, 14).iloc[88]), 6)
    out = st.major_structure_features(df, "bullish")
    assert st.confirmed_pivots(df).iloc[-1]["last_sl_pos"] == 88
    assert out["last_sl_reaction_atr"] == expected
    assert out["last_sh_reaction_atr"] is None             # the last swing high (bar 80) has been taken out


def test_reaction_mirror_for_the_last_swing_high():
    df = _cut(True, 96)
    high, low = df["High"].to_numpy(), df["Low"].to_numpy()
    expected = round((high[88] - low[88:].min()) / float(atr(df, 14).iloc[88]), 6)
    out = st.major_structure_features(df, "bearish")
    assert out["last_sh_reaction_atr"] == expected
    assert out["last_sl_reaction_atr"] is None


def test_no_major_high_leaves_state_and_event_none_but_keeps_the_low_side():
    out = st.major_structure_features(frame(UP), "bullish")
    assert out["structure_state_major"] is None and out["structure_aligned_major"] is None
    assert out["major_sh_atr"] is None and out["major_sl_atr"] > 0
    assert out["struct_event_last"] is None and out["struct_event_bars_ago"] is None


def test_short_frame_returns_all_none():
    df = tier_frame(DOWN)
    out = st.major_structure_features(df.iloc[:59], "bullish")
    assert tuple(out) == st.MAJOR_KEYS
    assert all(value is None for value in out.values())
    assert st.major_structure_features(df.iloc[:60], "bullish")["major_sl_atr"] is not None
    assert all(value is None for value in st.major_structure_features(None, "bullish").values())


def test_flat_prices_give_all_none():
    out = st.major_structure_features(make_ohlcv(np.full(80, 100.0), spread_pct=0.0), "bullish")
    assert all(value is None for value in out.values())


def test_nan_bars_do_not_raise():
    df = tier_frame(DOWN).copy()
    df.iloc[40:42, df.columns.get_loc("High")] = np.nan
    df.iloc[50, df.columns.get_loc("Close")] = np.nan
    assert set(st.major_structure_features(df, "bullish")) == set(st.MAJOR_KEYS)


@pytest.mark.parametrize("df", [wavy_frame(), tier_frame(DOWN), load_ohlcv("TSLA").iloc[:400]],
                         ids=["wavy", "down", "tsla"])
@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_features_equal_the_full_frame_rows_at_every_cut(df, direction):
    """The dict at cut t must be derivable from row t of the full-frame tables."""
    majors, events = st.major_pivots(df), st.structure_events(df)
    for t in range(59, len(df), 5):
        out = st.major_structure_features(df.iloc[:t + 1], direction)
        assert out["structure_state_major"] == st._major_state(majors.iloc[t]), t
        kind, side, pos = events.iloc[t]
        expected = None if kind is None else f"{kind}_{'with' if side == direction else 'against'}"
        assert out["struct_event_last"] == expected, t
        assert out["struct_event_bars_ago"] == (None if kind is None else t - int(pos)), t
```

- [ ] **Step 2:** Run `python scripts/dev/testrun.py file tests/market/test_major_structure_features.py`; expect FAIL (`AttributeError: module ... has no attribute 'major_structure_features'`).

- [ ] **Step 3: Implement.** Append to `swingbot/core/market/structure.py`:

```python
# swingbot/core/market/structure.py -- append
MAJOR_KEYS = ("structure_state_major", "structure_aligned_major", "major_sh_atr", "major_sl_atr",
              "struct_event_last", "struct_event_bars_ago", "last_sl_reaction_atr", "last_sh_reaction_atr")


def _reaction_atr(ext: np.ndarray, opp: np.ndarray, atr14: np.ndarray, pos) -> float | None:
    """Low-side form: (max opp since the pivot - pivot extreme) / ATR14[pivot].
    None when there is no pivot, it has been undercut, or its ATR is 0/NaN."""
    if pd.isna(pos):
        return None
    i = int(pos)
    if (ext[i + 1:] < ext[i]).any() or not atr14[i] > 0:
        return None
    return _num((np.fmax.reduce(opp[i:]) - ext[i]) / atr14[i])


def _event_keys(event, t: int, direction: str) -> dict:
    if event["event_kind"] is None:
        return {"struct_event_last": None, "struct_event_bars_ago": None}
    side = "with" if event["event_direction"] == direction else "against"
    return {"struct_event_last": f"{event['event_kind']}_{side}",
            "struct_event_bars_ago": int(t - event["event_pos"])}


def major_structure_features(df: pd.DataFrame, direction: str) -> dict:
    """Every MAJOR_KEYS value at ``df``'s final bar, expressed for the trade's
    direction. Reads only ``df``; < 60 bars returns all None."""
    out = dict.fromkeys(MAJOR_KEYS)
    if df is None or len(df) < MIN_BARS:
        return out
    atr14 = atr(df, 14).to_numpy(float)
    majors = _major_table(df, atr14)
    last, t = majors.iloc[-1], len(df) - 1
    state, atr_value = _major_state(last), _num(atr14[-1])
    high, low = df["High"].to_numpy(float), df["Low"].to_numpy(float)
    close, piv = float(df["Close"].iloc[-1]), confirmed_pivots(df).iloc[-1]
    out.update(structure_state_major=state,
               structure_aligned_major=None if state is None else state == ("up" if direction == "bullish" else "down"),
               major_sh_atr=_num((last["last_msh"] - close) / atr_value) if atr_value else None,
               major_sl_atr=_num((close - last["last_msl"]) / atr_value) if atr_value else None,
               last_sl_reaction_atr=_reaction_atr(low, high, atr14, piv["last_sl_pos"]),
               last_sh_reaction_atr=_reaction_atr(-high, -low, atr14, piv["last_sh_pos"]))
    out.update(_event_keys(_events_table(df, majors).iloc[-1], t, direction))
    return out
```

`_num(nan)` returns `None`, which is how a missing major pivot becomes `None` for `major_*_atr` without a branch. ATR is computed once and passed to `_major_table`; `_events_table` reuses the same `majors` frame, so the tier scan runs once per call.

- [ ] **Step 4:** Run `python scripts/dev/testrun.py file tests/market/test_major_structure_features.py`; expect PASS (19 tests). Run `python -m radon cc -s -n C swingbot/core/market/structure.py`; expect no output (the prototype's highest new score was B (7)).
- [ ] **Step 5:** Commit.

```bash
git add swingbot/core/market/structure.py tests/market/test_major_structure_features.py
git commit -m "feat(v130): major-structure, event and reaction snapshot keys"
```

# Phase 2 — Snapshot integration and storage

### Task V130-4: Merge the major keys into the entry snapshot

**Files:**
- Modify: `swingbot/core/edge/context.py`
- Modify: `tests/edge/test_edge_context_structure.py` (one line)
- Create: `tests/fixtures/v130/entry_context_witness.json` (generated in Step 1)
- Test: `tests/edge/test_edge_context_major.py`

**Interfaces:**
- Consumes (V130-3): `major_structure_features(df, direction) -> dict`, `MAJOR_KEYS`. Consumes (v121): `FEATURE_KEYS` (34 keys), the line `out.update(structure_features(df, direction))` inside `entry_context`.
- Produces: `FEATURE_KEYS` = the existing 34 keys in their current order, then the eight `MAJOR_KEYS` in order (42 total). `entry_context(df, *, direction, horizon_key, stop, target, asof=None)` signature unchanged.

- [ ] **Step 0:** Re-run the Preconditions block. `len(FEATURE_KEYS)` must be 34 before this task starts.

- [ ] **Step 1: Write the witness test FIRST and capture the witness from the unchanged code.**

```python
# tests/edge/test_edge_context_major.py
"""v130: entry_context carries the major-tier keys; everything older is untouched.

Run ``python -m tests.edge.test_edge_context_major`` on UNCHANGED code to
(re)capture the witness file. Never recapture after touching context.py."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from swingbot.core.edge.context import FEATURE_KEYS, entry_context
from tests.market.structure_fixtures import wavy_frame
from tests.market.structure_tier_fixtures import DOWN, tier_frame

WITNESS = Path(__file__).resolve().parents[1] / "fixtures" / "v130" / "entry_context_witness.json"
MAJOR_NEW = ("structure_state_major", "structure_aligned_major", "major_sh_atr", "major_sl_atr",
             "struct_event_last", "struct_event_bars_ago", "last_sl_reaction_atr", "last_sh_reaction_atr")
ASOF = {"regime2_state": "bull_quiet", "rs_pctile": 64.0, "sector_pctile": None, "rs_combined": 61.0}
FRAMES = {"wavy": wavy_frame, "down": lambda: tier_frame(DOWN), "up": lambda: tier_frame(DOWN, mirror=True)}


def _context(df, direction):
    close = float(df["Close"].iloc[-1])
    sign = 1 if direction == "bullish" else -1
    return entry_context(df, direction=direction, horizon_key="2w",
                         stop=close - sign * 6.0, target=close + sign * 12.0, asof=ASOF)


def _snapshots():
    return {f"{name}/{direction}": _context(build(), direction)
            for name, build in FRAMES.items() for direction in ("bullish", "bearish")}


def test_every_older_key_is_byte_identical_to_the_witness():
    witness = json.loads(WITNESS.read_text(encoding="utf-8"))
    now = json.loads(json.dumps(_snapshots()))
    assert set(witness) == set(now)
    for case, before in witness.items():
        assert len(before) == 34, case                      # 20 pre-v121 keys + v121's 14
        assert {key: now[case][key] for key in before} == before, case


if __name__ == "__main__":
    WITNESS.parent.mkdir(parents=True, exist_ok=True)
    WITNESS.write_text(json.dumps(_snapshots(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {WITNESS}")
```

Capture and run, **before touching `context.py`**:

```bash
python -m tests.edge.test_edge_context_major
python scripts/dev/testrun.py file tests/edge/test_edge_context_major.py
```

Expected: `wrote .../tests/fixtures/v130/entry_context_witness.json`, then PASS (the witness is a characterisation of today's 34 keys on six snapshots, not a red test). Commit it on its own so the before-state is in history:

```bash
git add tests/edge/test_edge_context_major.py tests/fixtures/v130/entry_context_witness.json
git commit -m "test(v130): witness entry_context values before the major-tier merge"
```

- [ ] **Step 2: Add the failing merge tests** to the same file, **above** the `if __name__ == "__main__":` block; put the new import with the others at the top.

```python
from swingbot.core.market.structure import MAJOR_KEYS, major_structure_features   # top of file


def test_feature_keys_append_the_major_keys_last():
    assert len(FEATURE_KEYS) == 42
    assert FEATURE_KEYS[34:] == MAJOR_NEW == MAJOR_KEYS
    assert FEATURE_KEYS[20] == "structure_state" and FEATURE_KEYS[33] == "impulse_range_decay"


@pytest.mark.parametrize("name", sorted(FRAMES))
@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_snapshot_carries_the_major_features(name, direction):
    df = FRAMES[name]()
    out = _context(df, direction)
    assert set(out) == set(FEATURE_KEYS)
    assert {key: out[key] for key in MAJOR_KEYS} == major_structure_features(df, direction)


def test_the_fixture_snapshot_is_not_vacuous():
    out = _context(tier_frame(DOWN).iloc[:97], "bullish")       # two bars after the bullish CHoCH at bar 94
    assert (out["struct_event_last"], out["struct_event_bars_ago"]) == ("choch_with", 2)
    assert out["structure_state_major"] == "down" and out["structure_aligned_major"] is False
    assert out["structure_state"] is not None                   # v121's k=3 state sits beside it


@pytest.mark.parametrize("bars", [10, 40, 59])
def test_short_frames_leave_every_major_key_none(bars):
    out = _context(wavy_frame().iloc[:bars], "bullish")
    assert set(out) == set(FEATURE_KEYS)
    assert all(out[key] is None for key in MAJOR_NEW)


def test_live_stamp_carries_the_major_keys():
    from swingbot.core.planning.params import stamp_entry_context
    df = tier_frame(DOWN).iloc[:97]
    close = float(df["Close"].iloc[-1])
    plan = SimpleNamespace(direction="bearish", horizon_key="2w", stop_loss=close + 6.0,
                           tp1=close - 12.0, entry_context=None)
    stamp_entry_context(plan, df, ASOF)
    assert set(plan.entry_context) == set(FEATURE_KEYS)
    assert plan.entry_context["struct_event_last"] == "choch_against"
```

- [ ] **Step 3:** Run `python scripts/dev/testrun.py file tests/edge/test_edge_context_major.py`; expect the witness PASS and the new tests FAIL (`ImportError`/`len(FEATURE_KEYS) == 34`).

- [ ] **Step 4: Implement.** In `swingbot/core/edge/context.py`, extend v121's import:

```python
from swingbot.core.market.structure import major_structure_features, structure_features
```

Append to the end of the `FEATURE_KEYS` tuple (after `"impulse_range_decay"`):

```python
                # v130: major-tier structure and BOS/CHoCH events (market/structure.py)
                "structure_state_major", "structure_aligned_major", "major_sh_atr", "major_sl_atr",
                "struct_event_last", "struct_event_bars_ago", "last_sl_reaction_atr", "last_sh_reaction_atr")
```

Inside `entry_context`, directly after v121's `out.update(structure_features(df, direction))` line, add one unconditional line:

```python
    out.update(major_structure_features(df, direction))   # v130; all None below 60 bars
```

The `len(df) < 20` early return already leaves every new key `None` through the `{key: None for key in FEATURE_KEYS}` default, and `major_structure_features` covers 20..59 bars itself. No branch is added.

In `tests/edge/test_edge_context_structure.py`, change v121's assertion `assert FEATURE_KEYS[20:] == STRUCTURE_NEW` to:

```python
    assert FEATURE_KEYS[20:34] == STRUCTURE_NEW
```

- [ ] **Step 5:** Run `python scripts/dev/testrun.py file tests/edge/test_edge_context_major.py` and `... file tests/edge/test_edge_context_structure.py`, then the existing context suites: `... file tests/backtesting/test_backtest_context.py`, `... file tests/backtesting/test_replay_context.py`, `... file tests/scanning/test_live_context_stamp.py`, `... file tests/scanning/test_strategy_pass_emit.py`. Expect PASS (they assert `set(context) == set(FEATURE_KEYS)`, still true). Run `python -m radon cc -s swingbot/core/edge/context.py` and confirm `entry_context` is still `C (17)`, not higher.
- [ ] **Step 6: No-lookahead review.** Invoke the `no-lookahead` skill on `swingbot/core/market/structure.py` and `swingbot/core/edge/context.py`. Confirm in the review note: tiers come only from `pivot_confirmations` and bars `>= i`, and `_major_bar` returns the *first* qualifying bar (so appending bars never changes it); `_known_majors` writes a pivot only from its `major_pos` forward; `_first_breaks` compares `close[1:]` with `level[:-1]`; `_reaction_atr` and every snapshot key read the final row of the frame given; there is no `shift(-n)`, `iloc[t+…]` or centred window. Fix any finding before committing.
- [ ] **Step 7:** Commit.

```bash
git add swingbot/core/edge/context.py tests/edge/test_edge_context_major.py tests/edge/test_edge_context_structure.py
git commit -m "feat(v130): entry_context carries major-tier structure and BOS/CHoCH keys"
```

### Task V130-5: Re-check the snapshot's storage shape (JSONB doc, no revision)

**Files:**
- Test: `tests/db/test_entry_context_major_doc.py`. No schema, migration or repository change.

**Interfaces:** Consumes existing `TradeRepository` (`db/repositories/trades.py`; `insert`/`get` inherited from `repositories/base.py`), `tracking.performance._db_record` / `_json_record`, `db.schema.trades`, the `db_conn` fixture (`tests/db/conftest.py`). Produces nothing later tasks import. It uses literal key names, so it does not wait for v121 or for V130-1..4.

- [ ] **Step 1:** Invoke the `schema-change` skill and confirm against `docs/claude/schema-evolution.md`: an added field on a hybrid table lands in `doc`, migration none. `trades` promotes `trade_id, ticker, strategy, horizon, direction, status, opened_at, closed_at, entry, stop_loss`; `entry_context` is not among them. Record "add → doc, no revision" in the commit body. If `entry_context` has become a typed column since v121, stop and report BLOCKED: the plan then needs an additive Alembic revision.

- [ ] **Step 2: Write the tests.**

```python
# tests/db/test_entry_context_major_doc.py
"""v130: the major-tier snapshot keys ride in trades.doc JSONB -- add, no revision."""
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.db.schema import trades
from swingbot.core.tracking.performance import _db_record, _json_record

MAJOR = {"structure_state_major": "down", "structure_aligned_major": False, "major_sh_atr": -2.294486,
         "major_sl_atr": 9.001443, "struct_event_last": "choch_against", "struct_event_bars_ago": 2,
         "last_sl_reaction_atr": 11.861716, "last_sh_reaction_atr": None}


def _trade(trade_id, context):
    return {"id": trade_id, "ticker": "AAPL", "strategy": "RSI", "horizon_key": "2w",
            "direction": "bullish", "status": "open", "opened_at": "2026-10-03T15:00:00+00:00",
            "entry_context": context}


def test_entry_context_is_still_a_doc_payload_not_a_column():
    assert "entry_context" not in trades.c


def test_major_keys_round_trip_with_their_types(db_conn):
    context = {"vol_ratio_20": 1.2, "structure_state": "up"} | MAJOR
    repository = TradeRepository()
    repository.insert(_db_record(_trade("V130-T1", context)), conn=db_conn)
    back = _json_record(repository.get("V130-T1", conn=db_conn))["entry_context"]
    assert back == context
    assert type(back["struct_event_bars_ago"]) is int
    assert back["structure_aligned_major"] is False and back["last_sh_reaction_atr"] is None
    assert back["struct_event_last"] == "choch_against"


def test_a_pre_v130_record_reads_every_major_key_as_none(db_conn):
    repository = TradeRepository()
    repository.insert(_db_record(_trade("V130-T0", {"structure_state": "up"})), conn=db_conn)
    back = _json_record(repository.get("V130-T0", conn=db_conn))["entry_context"]
    assert all(back.get(key) is None for key in MAJOR)
    assert back == {"structure_state": "up"}       # nothing upcast on read
```

- [ ] **Step 3:** Run `python scripts/dev/testrun.py file tests/db/test_entry_context_major_doc.py`; expect PASS immediately (it characterises existing storage). It needs the Compose test Postgres (`TEST_DATABASE_URL`); if the container is down the two `db_conn` tests **skip** — start it per `tests/db/conftest.py` and re-run until all three run. A skip is not a pass. (This file was written without a reachable test database, so this step is its first real execution.)
- [ ] **Step 4:** Commit.

```bash
git add tests/db/test_entry_context_major_doc.py
git commit -m "test(v130): major-tier snapshot keys live in trades.doc -- add, no revision"
```
