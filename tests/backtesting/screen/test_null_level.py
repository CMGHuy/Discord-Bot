"""v182 level null (spec Part B): each event's null bars copy its fill depth;
unfilled draws are replaced from the same pool on a child stream; the
next-open draw is unchanged."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import null, race as race_mod
from tests.backtesting.screen.helpers import random_walk

CAP = 10
SEED = [42, 7, 9]
EVENTS = np.array([30, 95, 160, 230])


def _setup(n=400, seed=7, atr_value=1.0):
    df = random_walk(n, seed=seed, start="2019-01-01")
    atr = pd.Series(atr_value, index=df.index)
    all_ = np.ones(n, dtype=bool)
    events = np.zeros(n, dtype=bool)
    events[EVENTS] = True
    return df, atr, all_, null.eligible_mask(events, all_, all_, CAP)


def _groups(df, atr, all_, eligible, k, *, depth=None, direction="short", seed=SEED):
    return null.draw_groups(df, EVENTS, eligible, k, seed, atr=atr, trend=all_,
                            direction=direction, depth=depth)


def _old_groups(df, eligible, k, seed, trend):
    """The v140 draw, inlined: the order every next-open null keeps."""
    rng = np.random.default_rng(seed)
    months = null.month_key(df.index)
    out = []
    for pos in EVENTS:
        pool = null.candidates(pos, eligible, months, trend)
        if len(pool) < null.MIN_CANDIDATES:
            continue
        out.append(np.sort(rng.choice(pool, size=min(k, len(pool)), replace=False)).tolist())
    return out


def _pools(df, eligible, all_):
    months = null.month_key(df.index)
    return [null.candidates(pos, eligible, months, all_) for pos in EVENTS]


def test_child_seed_extends_the_seed_and_wraps_an_int():
    assert null.LEVEL_STREAM == 1
    assert null.child_seed([42, 7, 9]) == [42, 7, 9, 1]
    assert null.child_seed(5) == [5, 1]
    assert null.child_seed(null.null_seed("x", "AAA"))[:3] == null.null_seed("x", "AAA")


def test_next_open_groups_keep_the_v140_draw_order():
    df, atr, all_, eligible = _setup()
    g = _groups(df, atr, all_, eligible, 20, direction="long")
    assert [x.tolist() for x in g.groups] == _old_groups(df, eligible, 20, SEED, all_)
    assert g.fills is None and g.null_unfilled == 0 and g.null_depths == ()
    assert g.null_slots == sum(len(x) for x in g.groups)
    draw = null.matched_null(df, EVENTS, eligible, 20, SEED, cap=CAP, atr=atr, trend=all_,
                             slippage_bps=0.0, commission=0.0)
    assert [x.tolist() for x in draw.groups] == [x.tolist() for x in g.groups]


def test_only_level_mode_creates_the_child_stream(monkeypatch):
    df, atr, all_, eligible = _setup()
    seeds = []
    real = np.random.default_rng

    def spy(seed=None):
        seeds.append(seed)
        return real(seed)

    monkeypatch.setattr(null.np.random, "default_rng", spy)
    _groups(df, atr, all_, eligible, 5)
    assert seeds == [SEED]
    seeds.clear()
    _groups(df, atr, all_, eligible, 5, depth=np.full(len(EVENTS), 1.0))
    assert seeds == [SEED, [42, 7, 9, 1]]


def test_zero_depth_fills_every_first_draw_at_its_open():
    df, atr, all_, eligible = _setup()
    plain = _groups(df, atr, all_, eligible, 5)
    level = _groups(df, atr, all_, eligible, 5, depth=np.zeros(len(EVENTS)))
    assert [x.tolist() for x in level.groups] == [x.tolist() for x in plain.groups]
    o = df["Open"].to_numpy()
    assert [f.tolist() for f in level.fills] == [o[x].tolist() for x in level.groups]
    assert level.null_unfilled == 0 and set(level.null_depths) == {0.0}


@pytest.mark.parametrize("direction", ["short", "long"])
def test_a_null_bar_fills_at_its_open_shifted_by_the_event_depth(direction):
    df, atr, all_, eligible = _setup()
    o, h, l = (df[k].to_numpy() for k in ("Open", "High", "Low"))
    a = atr.to_numpy()
    g = _groups(df, atr, all_, eligible, 5, depth=np.full(len(EVENTS), 0.5),
                direction=direction)
    sign = -1.0 if direction == "short" else 1.0
    for group, fills in zip(g.groups, g.fills):
        assert fills.tolist() == (o[group] + sign * 0.5 * a[group - 1]).tolist()
        reached = l[group] <= fills if direction == "short" else h[group] >= fills
        assert reached.all()


def test_unfilled_first_draws_are_replaced_from_the_same_pool():
    df, atr, all_, eligible = _setup()
    plain = _groups(df, atr, all_, eligible, 5)
    level = _groups(df, atr, all_, eligible, 5, depth=np.full(len(EVENTS), 1.0))
    again = _groups(df, atr, all_, eligible, 5, depth=np.full(len(EVENTS), 1.0))
    assert [x.tolist() for x in level.groups] == [x.tolist() for x in again.groups]
    assert [x.tolist() for x in level.groups] != [x.tolist() for x in plain.groups]
    for group, pool in zip(level.groups, _pools(df, eligible, all_)):
        assert set(group.tolist()) <= set(pool.tolist())
        assert group.tolist() == sorted(set(group.tolist()))
        assert not set(group.tolist()) & set(EVENTS.tolist())


def test_null_bar_with_nan_prior_atr_never_fills():
    df, atr, all_, eligible = _setup()
    bad = np.zeros(len(df), dtype=bool)
    bad[::3] = True
    atr = atr.mask(bad, np.nan)
    atr.iloc[1::9] = 0.0
    g = _groups(df, atr, all_, eligible, 5, depth=np.zeros(len(EVENTS)))
    a = atr.to_numpy()
    filled = np.concatenate(g.groups)
    assert np.isfinite(a[filled - 1]).all() and (a[filled - 1] > 0).all()
    plain = _groups(df, pd.Series(1.0, index=df.index), all_, eligible, 5)
    first = np.concatenate(plain.groups)
    assert (~np.isfinite(a[first - 1]) | (a[first - 1] <= 0)).any()     # non-vacuous


def test_event_with_no_fillable_null_drops_as_no_match():
    df, atr, all_, eligible = _setup()
    g = _groups(df, atr, all_, eligible, 20, depth=np.full(len(EVENTS), 50.0))
    pools = _pools(df, eligible, all_)
    assert g.groups == () and g.dropped_no_match == len(EVENTS)
    assert g.null_slots == sum(min(20, len(p)) for p in pools)
    assert g.null_unfilled == g.null_slots
    draw = null.matched_null(df, EVENTS, eligible, 20, SEED, cap=CAP, atr=atr, trend=all_,
                             slippage_bps=0.0, commission=0.0, direction="short",
                             depth=np.full(len(EVENTS), 50.0))
    assert draw.event_pos.size == 0 and len(draw.null_race) == 0
    assert draw.dropped_no_match == len(EVENTS)
    assert (draw.null_slots, draw.null_unfilled) == (g.null_slots, g.null_unfilled)


def test_pool_exhaustion_keeps_fewer_null_trades():
    df, atr, all_, eligible = _setup()
    g = _groups(df, atr, all_, eligible, 20, depth=np.full(len(EVENTS), 1.0))
    pools = _pools(df, eligible, all_)
    assert g.null_slots == sum(min(20, len(p)) for p in pools)
    assert g.null_unfilled == g.null_slots - sum(len(x) for x in g.groups)
    assert 0 < g.null_unfilled < g.null_slots
    assert any(len(x) < min(20, len(p)) for x, p in zip(g.groups, pools))


def test_null_depths_are_the_realised_depths_in_group_order():
    df, atr, all_, eligible = _setup()
    depth = np.array([0.25, 0.5, 0.75, 1.0])
    g = _groups(df, atr, all_, eligible, 5, depth=depth)
    kept = {int(p): d for p, d in zip(EVENTS, depth)}
    expected = [kept[int(p)] for p, grp in zip(g.event_pos, g.groups) for _ in grp]
    assert list(g.null_depths) == pytest.approx(expected, rel=1e-12)
    assert len(g.null_depths) == sum(len(x) for x in g.groups)


def test_depth_must_align_with_the_events():
    df, atr, all_, eligible = _setup()
    with pytest.raises(ValueError, match="depth"):
        _groups(df, atr, all_, eligible, 5, depth=np.zeros(len(EVENTS) - 1))


def _spy_race(monkeypatch):
    seen = []
    real_for = race_mod.race_for

    def race_for(shape):
        fn = real_for(shape)

        def spy(*args, **kwargs):
            seen.append(kwargs)
            return fn(*args, **kwargs)
        return spy

    monkeypatch.setattr(race_mod, "race_for", race_for)
    return seen


def test_level_matched_null_races_the_fills_with_the_level_factor(monkeypatch):
    df, atr, all_, eligible = _setup()
    seen = _spy_race(monkeypatch)
    depth = np.full(len(EVENTS), 0.5)
    g = _groups(df, atr, all_, eligible, 5, depth=depth)
    draw = null.matched_null(df, EVENTS, eligible, 5, SEED, cap=CAP, atr=atr, trend=all_,
                             slippage_bps=5.0, commission=0.0, direction="short",
                             depth=depth, level_factor=race_mod.REPRICE_SLIPPAGE_FACTOR)
    assert seen[-1]["fill"].tolist() == np.concatenate(g.fills).tolist()
    assert seen[-1]["level_factor"] == 3.0 and seen[-1]["direction"] == "short"
    expected = race_mod.race(df, np.concatenate(g.groups), CAP, atr=atr, slippage_bps=5.0,
                             commission=0.0, direction="short", fill=np.concatenate(g.fills),
                             level_factor=3.0)
    assert draw.null_race.r.tolist() == expected.r.tolist()
    assert (draw.null_slots, draw.null_unfilled, draw.null_depths) == (
        g.null_slots, g.null_unfilled, g.null_depths)
    null.matched_null(df, EVENTS, eligible, 5, SEED, cap=CAP, atr=atr, trend=all_,
                      slippage_bps=5.0, commission=0.0, direction="short")
    assert not ({"fill", "level_factor"} & set(seen[-1]))
