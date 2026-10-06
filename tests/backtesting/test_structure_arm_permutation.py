import pandas as pd
import pytest

from swingbot.core.backtesting import armed_replay as ar
from swingbot.core.backtesting import structure_arm as sa
from swingbot.core.market import levels
from tests.backtesting.structure_arm_fixtures import MSB_FRAME, T1, cand, frame, params

CELL = sa.StructCell(sa.MSB, 5, 0.25)


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(ar, "atr", lambda df, period=14: pd.Series(1.0, index=df.index))
    df = frame(MSB_FRAME, n=45)
    confirmed = [(cand(25), ar.ArmOutcome("triggered", 28, "MSB", 25))]
    res, sup = [levels.Level(T1, ["Fibonacci"])], [levels.Level(90.0, ["Rolling S/R"])]
    kwargs = dict(level_cache={}, params=params(),
                  level_map_at=lambda j: (sup, res), confluence_at=lambda *a: 3)
    return df, confirmed, kwargs


def test_seed_42_is_deterministic_and_draws_stay_in_the_arm_window(setup):
    df, confirmed, kwargs = setup
    first = sa.structure_permutations("AAPL", df, "4w", CELL, confirmed, n=50, seed=42, **kwargs)
    again = sa.structure_permutations("AAPL", df, "4w", CELL, confirmed, n=50, seed=42, **kwargs)
    assert first == again and len(first) == 50
    window = {df.index[j].date().isoformat() for j in range(25, 31)}     # [i, i + N]
    assert all(len(perm) <= 1 for perm in first)
    assert all(row[0] in window and row[1].startswith("confluence:") and row[2] == "4w"
               for perm in first for row in perm)


def test_a_different_seed_draws_differently(setup):
    df, confirmed, kwargs = setup
    a = sa.structure_permutations("AAPL", df, "4w", CELL, confirmed, n=50, seed=42, **kwargs)
    b = sa.structure_permutations("AAPL", df, "4w", CELL, confirmed, n=50, seed=43, **kwargs)
    assert a != b


def test_every_draw_anchors_the_stop_at_the_arm_bar_with_the_frozen_buffer(setup, monkeypatch):
    """The arm bar IS the test bar, so delay_permutations' first-test scan
    returns i for every drawn bar, and plan_at sees b = 0.10."""
    df, confirmed, kwargs = setup
    seen = {}
    real = ar.plan_at

    def spy(*a, **k):
        seen[k["j"]] = (k["first_test_index"], k["cell"].b)
        return real(*a, **k)

    monkeypatch.setattr(ar, "plan_at", spy)
    sa.structure_permutations("AAPL", df, "4w", CELL, confirmed, n=200, seed=1, **kwargs)
    assert set(seen) <= set(range(25, 31)) and len(seen) >= 2
    assert set(seen.values()) == {(25, 0.10)}
