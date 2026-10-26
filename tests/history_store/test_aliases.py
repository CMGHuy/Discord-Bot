"""v190 section 2.4: the committed rename table (membership symbol -> Alpaca
symbol with a date range). A malformed table stops the fetcher instead of
silently fetching the wrong issuer."""
import json
from pathlib import Path

import pandas as pd
import pytest

from alpaca_history import aliases

FB = {"member": "FB", "alpaca": "META", "start": "2016-01-04", "end": None,
      "note": "renamed 2022-06-09"}


def _write(tmp_path, doc) -> Path:
    path = tmp_path / "symbol_aliases.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _bars(start, end, freq="B"):
    idx = pd.date_range(start, end, freq=freq)
    return pd.DataFrame({"Close": range(len(idx))}, index=idx, dtype=float)


def test_path_is_relative_to_the_project_root():
    assert aliases.ALIASES_PATH == Path("data/universe/symbol_aliases.json")
    assert not aliases.ALIASES_PATH.is_absolute()


def test_absent_file_is_an_empty_table(tmp_path):
    assert aliases.load_aliases(tmp_path / "missing.json") == {}


def test_entries_are_keyed_by_member_and_upper_cased(tmp_path):
    path = _write(tmp_path, {"aliases": [FB, {"member": " brk.b ", "alpaca": "brk.b2",
                                              "start": "2016-01-04", "end": "2020-01-02"}]})
    got = aliases.load_aliases(path)
    assert got["FB"] == aliases.Alias("FB", "META", "2016-01-04", None)
    assert got["BRK.B"] == aliases.Alias("BRK.B", "BRK.B2", "2016-01-04", "2020-01-02")


@pytest.mark.parametrize("doc", [
    [FB],                                                   # not an object
    {"aliases": {}},
    {"aliases": [None]},
    {"aliases": [{**FB, "end": "2020-02-30"}]},
    {"aliases": [{**FB, "start": "20160104"}]},
    {"aliases": [{**FB, "start": None}]},
    {"aliases": [{**FB, "member": 42}]},
    {"rows": [FB]},                                         # no "aliases" list
    {"aliases": [{**FB, "alpaca": ""}]},                    # missing symbol
    {"aliases": [{k: v for k, v in FB.items() if k != "start"}]},
    {"aliases": [{**FB, "start": "2016-13-01"}]},           # not ISO
    {"aliases": [{**FB, "end": "2016-01-04"}]},             # end <= start
    {"aliases": [{**FB, "alpaca": "FB"}]},                  # aliases itself
    {"aliases": [FB, {**FB, "alpaca": "META2"}]},           # duplicate member
])
def test_a_malformed_table_is_refused_naming_the_file(tmp_path, doc):
    path = _write(tmp_path, doc)
    with pytest.raises(ValueError, match="symbol_aliases.json"):
        aliases.load_aliases(path)


def test_clip_keeps_the_alias_date_range_at_date_level():
    alias = aliases.Alias("FB", "META", "2016-03-01", "2016-03-08")
    got = alias.clip(_bars("2016-02-25", "2016-03-15"))
    assert got.index.min() == pd.Timestamp("2016-03-01")
    assert got.index.max() == pd.Timestamp("2016-03-07")
    hourly = alias.clip(_bars("2016-03-07 09:30", "2016-03-08 15:30", freq="h"))
    assert hourly.index.max() < pd.Timestamp("2016-03-08")


def test_clip_edge_cases():
    open_ended = aliases.Alias("FB", "META", "2016-03-01", None)
    frame = _bars("2016-03-01", "2016-03-04")
    assert len(open_ended.clip(frame)) == len(frame)
    assert open_ended.clip(None) is None
    assert aliases.Alias("FB", "META", "2017-01-03", None).clip(frame) is None


def test_invalid_json_names_the_file(tmp_path):
    path = tmp_path / "symbol_aliases.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="symbol_aliases.json"):
        aliases.load_aliases(path)


def test_clip_empty_and_timezone_aware_frames():
    alias = aliases.Alias("FB", "META", "2016-03-01", "2016-03-08")
    assert alias.clip(pd.DataFrame()) is None
    frame = _bars("2016-03-07 09:30", "2016-03-08 15:30", freq="h")
    frame.index = frame.index.tz_localize("America/New_York")
    got = alias.clip(frame)
    assert got.index.max().date().isoformat() == "2016-03-07"
