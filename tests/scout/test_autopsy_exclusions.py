"""v200 Part 2: the August stall exclusion -- the open-at-any-moment rule, the
committed file, and the trade ids rebuilt from the rule against a production extract."""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
from autopsy import exclusions, rows  # noqa: E402

FIXTURE = ROOT / "tests" / "scout" / "fixtures" / "stall_2026_08_trades.csv"
UTC = dt.timezone.utc
W = exclusions.Window(dt.datetime(2026, 8, 3, 16, 18, 2, tzinfo=UTC),
                      dt.datetime(2026, 8, 4, 18, 55, 15, tzinfo=UTC))


def _at(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text).replace(tzinfo=UTC)


def _trade(tid, opened, closed, kind="trade"):
    return SimpleNamespace(row_kind=kind, trade_id=tid,
                           opened_at_utc=_at(opened) if opened else None,
                           closed_at_utc=_at(closed) if closed else None)


@pytest.mark.parametrize("opened, closed", [
    ("2026-08-01T14:00:00", "2026-08-04T18:55:15"),   # opened before, closed by the catch-up batch
    ("2026-08-01T14:00:00", "2026-08-03T17:00:00"),   # closed by hand inside the window
    ("2026-08-03T17:00:00", "2026-08-10T15:00:00"),   # opened inside, closed long after
    ("2026-07-20T14:00:00", "2026-08-03T16:18:02"),   # closed exactly at the window start
    ("2026-08-01T14:00:00", "2026-08-20T15:00:00"),   # spans the whole window
])
def test_open_at_any_moment_is_excluded_whatever_the_close(opened, closed):
    assert exclusions.open_in_window(_at(opened), _at(closed), W) is True


@pytest.mark.parametrize("opened, closed", [
    ("2026-07-20T14:00:00", "2026-08-03T16:18:01"),   # closed one second before the start
    ("2026-08-04T18:55:15", "2026-08-06T15:00:00"),   # opened exactly at the window end
    ("2026-08-05T14:00:00", "2026-08-07T15:00:00"),   # opened after the window
])
def test_closed_just_before_the_window_is_kept(opened, closed):
    assert exclusions.open_in_window(_at(opened), _at(closed), W) is False


def test_a_trade_missing_a_timestamp_is_never_matched():
    assert exclusions.open_in_window(None, _at("2026-08-04T00:00:00"), W) is False
    assert exclusions.open_in_window(_at("2026-08-03T17:00:00"), None, W) is False


def test_rebuild_returns_sorted_unique_trade_ids_of_trade_rows_only():
    data = [_trade("T9", "2026-08-01T14:00:00", "2026-08-04T18:55:15"),
            _trade("T2", "2026-08-03T17:00:00", "2026-08-05T15:00:00"),
            _trade("T2", "2026-08-03T17:00:00", "2026-08-05T15:00:00"),
            _trade("P1", "2026-08-03T17:00:00", "2026-08-05T15:00:00", kind="plan"),
            _trade("T5", "2026-07-01T14:00:00", "2026-07-02T15:00:00")]
    assert exclusions.rebuild_trade_ids(data, [W]) == ["T2", "T9"]
    assert exclusions.rebuild_trade_ids([], [W]) == []


def _write(tmp_path, payload) -> Path:
    path = tmp_path / "exclusions.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


GOOD = {"k": {"reason": "r", "rule": "u",
              "windows": [{"start": "2026-08-03T16:18:02Z", "end": "2026-08-04T18:55:15Z"}],
              "trade_ids": ["T2", "T1"]}}


def test_load_parses_utc_windows_ids_and_records_the_file_hash(tmp_path):
    path = _write(tmp_path, GOOD)
    inputs = {}
    [ex] = exclusions.load_exclusions(path, input_fingerprints=inputs)
    assert ex.key == "k" and ex.trade_ids == frozenset({"T1", "T2"})
    assert ex.windows == (W,)
    assert inputs == {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()}


@pytest.mark.parametrize("window", [
    {"start": "2026-08-04T18:55:15Z", "end": "2026-08-03T16:18:02Z"},   # start after end
    {"start": "2026-08-03T16:18:02", "end": "2026-08-04T18:55:15Z"},    # no offset
])
def test_load_refuses_a_bad_window_naming_the_key(tmp_path, window):
    payload = {"k": dict(GOOD["k"], windows=[window])}
    with pytest.raises(ValueError, match="k"):
        exclusions.load_exclusions(_write(tmp_path, payload))


def test_load_refuses_an_entry_missing_a_field(tmp_path):
    payload = {"k": {key: v for key, v in GOOD["k"].items() if key != "rule"}}
    with pytest.raises(ValueError, match="rule"):
        exclusions.load_exclusions(_write(tmp_path, payload))


def test_the_committed_file_has_one_stall_entry_with_two_windows():
    [ex] = exclusions.load_exclusions()
    assert ex.key == "stall_2026_08"
    assert len(ex.windows) == 2
    assert ex.windows[0].start == dt.datetime(2026, 8, 3, 16, 18, 2, tzinfo=UTC)
    assert ex.windows[0].end == dt.datetime(2026, 8, 4, 18, 55, 15, tzinfo=UTC)
    assert ex.windows[1].end == dt.datetime(2026, 8, 5, 15, 34, 1, tzinfo=UTC)
    assert ex.windows[0].end <= ex.windows[1].start < ex.windows[1].end
    assert ex.trade_ids


def _fixture_rows():
    with FIXTURE.open(encoding="utf-8", newline="") as fh:
        return [SimpleNamespace(row_kind="trade", trade_id=r["trade_id"],
                                opened_at_utc=rows._timestamp(r["opened_at"]),
                                closed_at_utc=rows._timestamp(r["closed_at"]))
                for r in csv.DictReader(fh)]


def test_the_committed_trade_ids_are_rebuilt_exactly_from_the_rule():
    [ex] = exclusions.load_exclusions()
    rebuilt = exclusions.rebuild_trade_ids(_fixture_rows(), ex.windows)
    assert rebuilt == sorted(ex.trade_ids)


def test_the_fixture_holds_near_misses_beside_the_excluded_trades():
    """The extract is a band around the windows, not only the excluded trades."""
    [ex] = exclusions.load_exclusions()
    ids = {r.trade_id for r in _fixture_rows()}
    assert ex.trade_ids <= ids
    assert ids - ex.trade_ids


def test_the_cli_prints_the_rebuilt_ids_as_json(tmp_path, capsys):
    header = list(rows.EXPORT_COLUMNS)
    rec = {c: "" for c in header}
    rec.update(row_kind="trade", trade_id="T1", plan_id="P1", ticker="AAA", direction="bullish",
               opened_at="2026-08-03T17:00:00+00:00", closed_at="2026-08-05T15:00:00+00:00",
               entry="100", stop_loss="98", r_realized="-1.0")
    path = tmp_path / "rows.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        writer.writerow(rec)
    assert exclusions.main([str(path)]) == 0
    assert json.loads(capsys.readouterr().out) == ["T1"]
