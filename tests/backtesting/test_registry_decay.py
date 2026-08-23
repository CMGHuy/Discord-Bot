"""Read-time decay verdicts derived from a registry row's run_date."""
from __future__ import annotations

import datetime as dt

import pytest

from swingbot.core.backtesting import registry

TODAY = dt.date(2026, 8, 22)


@pytest.mark.parametrize("run_date,expected", [
    ("2026-08-01", "fresh"),      # 21 days
    ("2026-05-25", "fresh"),      # 89 days
    ("2026-05-24", "aging"),      # 90 days -- boundary belongs to the stricter side
    ("2026-03-01", "aging"),      # 174 days
    ("2026-02-23", "stale"),      # 180 days -- boundary belongs to the stricter side
    ("2025-01-01", "stale"),
])
def test_decay_bands_and_boundaries(run_date, expected):
    assert registry.decay_for(run_date, today=TODAY) == expected


@pytest.mark.parametrize("bad", ["", None, "not-a-date", "2026-13-45"])
def test_unusable_run_date_is_unknown_never_fresh(bad):
    assert registry.decay_for(bad, today=TODAY) == "unknown"


def test_future_run_date_is_fresh_not_negative_nonsense():
    assert registry.decay_for("2026-12-01", today=TODAY) == "fresh"


def test_badge_carries_decay(tmp_path):
    fixture = tmp_path / "reg.json"
    fixture.write_text(
        '[{"source":"confluence","strategy":"ALL","horizon":"2m","status":"WEAK",'
        '"n":402,"win_rate":48.8,"expectancy_r":-0.226,'
        '"window":"2024-01-01..2025-12-31","run_date":"2020-01-01"}]',
        encoding="utf-8")
    try:
        registry.load_registry(fixture)
        badge = registry.get_badge("confluence", "ALL", "2m")
        assert badge.decay == "stale"
    finally:
        registry.reload_registry()   # _CACHE is module-global; never leak a fixture


def test_default_badge_decay_is_unknown():
    # The n=0 fallback at registry.py:71 has no run_date to reason from.
    assert registry.Badge(status="WEAK", n=0, win_rate=0.0, expectancy_r=0.0).decay == "unknown"


def test_decay_is_not_persisted(tmp_path):
    # Guard against a future "optimisation" that writes the verdict into the JSON.
    import json
    from pathlib import Path
    raw = json.loads(Path(registry._PATH).read_text(encoding="utf-8"))
    assert all("decay" not in row for row in raw), "decay must be derived, never stored"


def test_thresholds_are_one_and_two_missed_quarters():
    assert registry.DECAY_AGING_DAYS == 90
    assert registry.DECAY_STALE_DAYS == 180
