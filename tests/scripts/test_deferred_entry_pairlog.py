"""v229 pair log: append once per trade id, never rewritten, torn tail redone."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))

from deferred_entry import pairlog  # noqa: E402


def _pair(trade_id, **extra):
    return {"trade_id": trade_id, "entry_date": "2026-11-03", "rule_hash": "0123abcd4567ef89", **extra}


def test_default_log_is_the_relative_data_path():
    assert pairlog.DEFAULT_LOG == "data/v229/pairs.jsonl"


def test_a_missing_log_reads_as_empty(tmp_path):
    assert pairlog.read_pairs(tmp_path / "nope.jsonl") == {}


def test_append_then_read_round_trips_in_file_order(tmp_path):
    path = tmp_path / "v229" / "pairs.jsonl"          # parent does not exist yet
    for tid in ("t-2", "t-1", "t-3"):
        pairlog.append_pair(path, _pair(tid, arms={"C": {"r_net": -1.02}}))
    pairs = pairlog.read_pairs(path)
    assert list(pairs) == ["t-2", "t-1", "t-3"]
    assert pairs["t-1"]["arms"]["C"]["r_net"] == pytest.approx(-1.02)
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n") and text.count("\n") == 3


def test_a_duplicate_trade_id_is_refused_and_the_file_is_untouched(tmp_path):
    path = tmp_path / "pairs.jsonl"
    pairlog.append_pair(path, _pair("t-1"))
    before = path.read_bytes()
    with pytest.raises(pairlog.PairLogError, match="t-1"):
        pairlog.append_pair(path, _pair("t-1", note="again"))
    assert path.read_bytes() == before


def test_known_ids_skip_the_reread_and_are_updated(tmp_path, monkeypatch):
    path = tmp_path / "pairs.jsonl"
    known = set(pairlog.read_pairs(path))
    monkeypatch.setattr(pairlog, "read_pairs", lambda _p: pytest.fail("re-read despite known"))
    pairlog.append_pair(path, _pair("t-1"), known=known)
    pairlog.append_pair(path, _pair("t-2"), known=known)
    assert known == {"t-1", "t-2"}
    with pytest.raises(pairlog.PairLogError):
        pairlog.append_pair(path, _pair("t-2"), known=known)


def test_a_pair_without_trade_id_is_refused(tmp_path):
    with pytest.raises(pairlog.PairLogError, match="trade_id"):
        pairlog.append_pair(tmp_path / "pairs.jsonl", {"entry_date": "2026-11-03"})
    assert not (tmp_path / "pairs.jsonl").exists()


def test_nan_is_refused_rather_than_written_as_invalid_json(tmp_path):
    with pytest.raises(pairlog.PairLogError, match="serialis"):
        pairlog.append_pair(tmp_path / "pairs.jsonl", _pair("t-1", r=float("nan")))


def test_every_append_is_fsynced(tmp_path, monkeypatch):
    calls = []
    real = pairlog.os.fsync
    monkeypatch.setattr(pairlog.os, "fsync", lambda fd: (calls.append(fd), real(fd)))
    pairlog.append_pair(tmp_path / "pairs.jsonl", _pair("t-1"))
    assert len(calls) == 1


def test_a_torn_last_line_is_dropped_truncated_and_redone(tmp_path):
    path = tmp_path / "pairs.jsonl"
    pairlog.append_pair(path, _pair("t-1"))
    pairlog.append_pair(path, _pair("t-2"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"trade_id": "t-3", "arms": {"C"')          # killed mid-write
    assert list(pairlog.read_pairs(path)) == ["t-1", "t-2"]
    assert path.read_text(encoding="utf-8").count("\n") == 2
    pairlog.append_pair(path, _pair("t-3"))
    assert list(pairlog.read_pairs(path)) == ["t-1", "t-2", "t-3"]


def test_a_complete_json_tail_without_newline_is_still_torn(tmp_path):
    """append_pair writes line+newline in one call, so a line without its
    newline was never finished, even when the bytes happen to parse."""
    path = tmp_path / "pairs.jsonl"
    path.write_text(json.dumps(_pair("t-1")) + "\n" + json.dumps(_pair("t-2")), encoding="utf-8")
    assert list(pairlog.read_pairs(path)) == ["t-1"]


def test_a_malformed_line_inside_the_file_is_refused(tmp_path):
    path = tmp_path / "pairs.jsonl"
    path.write_text(json.dumps(_pair("t-1")) + "\nnot json\n" + json.dumps(_pair("t-3")) + "\n",
                    encoding="utf-8")
    with pytest.raises(pairlog.PairLogError, match="line 2"):
        pairlog.read_pairs(path)


@pytest.mark.parametrize("line", ['["t-1"]', '{"entry_date": "2026-11-03"}', '{"trade_id": ""}'])
def test_a_line_that_is_not_a_pair_is_refused(tmp_path, line):
    path = tmp_path / "pairs.jsonl"
    path.write_text(line + "\n", encoding="utf-8")
    with pytest.raises(pairlog.PairLogError, match="line 1"):
        pairlog.read_pairs(path)


def test_a_duplicate_id_already_in_the_file_is_refused(tmp_path):
    path = tmp_path / "pairs.jsonl"
    path.write_text(json.dumps(_pair("t-1")) + "\n" + json.dumps(_pair("t-1")) + "\n", encoding="utf-8")
    with pytest.raises(pairlog.PairLogError, match="duplicate"):
        pairlog.read_pairs(path)


def test_blank_lines_are_skipped(tmp_path):
    path = tmp_path / "pairs.jsonl"
    path.write_text(json.dumps(_pair("t-1")) + "\n\n" + json.dumps(_pair("t-2")) + "\n", encoding="utf-8")
    assert list(pairlog.read_pairs(path)) == ["t-1", "t-2"]


def test_an_empty_file_reads_as_empty(tmp_path):
    path = tmp_path / "pairs.jsonl"
    path.write_bytes(b"")
    assert pairlog.read_pairs(path) == {}
