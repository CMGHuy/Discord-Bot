"""v200 Part 3: exit-model eras around the production deploy of b4ef2e87."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
from autopsy import cells, eras, report, rows  # noqa: E402

UTC = dt.timezone.utc
B = dt.datetime(2026, 9, 11, 14, 0, 0, tzinfo=UTC)      # 10:00 EDT on 2026-09-11


def _at(text):
    return None if text is None else dt.datetime.fromisoformat(text).replace(tzinfo=UTC)


def _row(opened, closed, gross=1.0):
    return rows.BookRow(row_kind="trade", gross_r=gross, net_r=gross,
                        opened_at_utc=_at(opened), closed_at_utc=_at(closed))


@pytest.mark.parametrize("opened, closed, era", [
    ("2026-09-08T14:00:00", "2026-09-11T13:59:59", "pre"),       # closed a second before
    ("2026-09-08T14:00:00", "2026-09-11T14:00:00", "straddle"),  # closed exactly at the boundary
    ("2026-09-08T14:00:00", "2026-09-15T15:00:00", "straddle"),  # opened before, closed after
    ("2026-09-11T15:00:00", "2026-09-15T15:00:00", "straddle"),  # boundary-day entry, after the deploy
    ("2026-09-12T02:00:00", "2026-09-15T15:00:00", "straddle"),  # 22:00 EDT on 09-11: still the boundary's Eastern day
    ("2026-09-12T13:30:00", "2026-09-15T15:00:00", "post"),      # the next Eastern day
    (None, "2026-09-01T15:00:00", "pre"),                         # closed before: opened is not needed
    (None, "2026-09-15T15:00:00", None),
    ("2026-09-08T14:00:00", None, None),
])
def test_era_of(opened, closed, era):
    assert eras.era_of(_row(opened, closed), B) == era


def test_era_stats_reports_every_era_and_skips_unplaced_rows():
    members = [_row("2026-09-01T14:00:00", "2026-09-03T15:00:00", 1.0),
               _row("2026-09-01T14:00:00", "2026-09-03T15:00:00", -1.0),
               _row("2026-09-01T14:00:00", "2026-09-03T15:00:00", 2.0),
               _row("2026-09-14T14:00:00", "2026-09-16T15:00:00", -0.5),
               _row(None, "2026-09-16T15:00:00", 9.0)]
    assert eras.era_stats(members, B) == {
        "pre": {"n": 3, "win_rate": 0.6667, "net_expr": 0.6667},
        "straddle": {"n": 0, "win_rate": None, "net_expr": None},
        "post": {"n": 1, "win_rate": 0.0, "net_expr": -0.5}}
    assert eras.era_stats([], B) == {k: {"n": 0, "win_rate": None, "net_expr": None}
                                     for k in eras.ERAS}


@pytest.mark.parametrize("pre, post, flip", [
    (0.2, -0.1, True), (-0.2, 0.1, True), (0.2, 0.1, False),
    (None, -0.1, False), (0.0, -0.1, False)])
def test_sign_flip(pre, post, flip):
    stats = {"pre": {"n": 1, "win_rate": 1.0, "net_expr": pre},
             "straddle": {"n": 0, "win_rate": None, "net_expr": None},
             "post": {"n": 1, "win_rate": 0.0, "net_expr": post}}
    assert eras.sign_flip(stats) is flip
    assert eras.sign_flip(None) is False


def test_the_boundary_is_a_utc_deploy_time_not_the_commit_time():
    assert eras.ERA_BOUNDARY_UTC.utcoffset() == dt.timedelta(0)
    assert eras.ERA_BOUNDARY_UTC != dt.datetime(2026, 9, 11, 7, 59, 35, tzinfo=UTC)
    assert eras.ERA_BOUNDARY_UTC > dt.datetime(2026, 9, 11, 7, 59, 35, tzinfo=UTC)
    assert eras.ERA_BOUNDARY_SOURCE.strip()


def test_cell_json_carries_eras_and_notes():
    cell = cells.CellStats(id="a=b", cut="a", value="b", n=1, weeks=1, win_rate=1.0,
                           net_expr=1.0, gross_expr=1.0, delta=None, ci=None, p=None, q=None,
                           thin=True)
    assert cell.to_json()["eras"] is None and cell.to_json()["notes"] == []
    cell.eras = {"pre": {"n": 1, "win_rate": 1.0, "net_expr": 1.0}}
    cell.notes.append("era sign flip")
    out = cell.to_json()
    assert out["eras"] == cell.eras and out["eras"] is not cell.eras
    assert out["notes"] == ["era sign flip"]


def _md_cell(**over):
    base = {"id": "regime=x", "cut": "regime", "value": "x", "n": 40, "weeks": 10,
            "win_rate": 0.5, "net_expr": 0.1, "gross_expr": 0.12, "delta": 0.05,
            "ci": [0.01, 0.09], "p": 0.04, "q": 0.08, "thin": False, "bar_covered_n": None,
            "extra": {"tickers": 1, "top_ticker_share": 1.0}, "notes": ["era sign flip"],
            "eras": {"pre": {"n": 30, "win_rate": 0.6, "net_expr": 0.25},
                     "straddle": {"n": 0, "win_rate": None, "net_expr": None},
                     "post": {"n": 10, "win_rate": 0.2, "net_expr": -0.35}}}
    base.update(over)
    return base


def test_the_markdown_row_shows_the_eras_and_the_flip_note():
    data = {"header": {"window": ["2026-01-08", "2026-10-26"], "n": 40, "pooled_net_expr": 0.1,
                       "pooled_win_rate": 0.5, "net_of_frictions": "modelled", "cells_tested": 1,
                       "bar_covered_n": 0, "resamples": 200, "seed": 42, "notes": [],
                       "era_boundary": {"utc": "2026-09-11T14:00:00Z", "source": "deploy log"}},
            "cells": [_md_cell()], "tallies": [],
            "giveback": {"n": 0, "mean": None, "median": None}}
    md = report.render_markdown(data).splitlines()
    assert ("- Exit-model era boundary (production deploy of b4ef2e87): 2026-09-11T14:00:00Z "
            "(source: deploy log); era columns carry no CI and no q") in md
    assert any("| eras pre / straddle / post (N WR net) |" in line for line in md)
    row = next(line for line in md if line.startswith("| regime=x |"))
    assert "| 30 60.0% +0.250 / 0 n/a / 10 20.0% -0.350 |" in row
    assert "era sign flip" in row
