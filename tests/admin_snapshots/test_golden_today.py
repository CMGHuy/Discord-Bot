"""v204 V204-1: today's request code reproduces the frozen golden payloads."""
import json
import os

import pytest

from tests.admin_snapshots import record_golden
from tests.admin_snapshots.golden_book import (  # noqa: F401 (fixtures)
    GOLDEN_MONTH,
    GOLDEN_NAMES,
    _clear_login_limiter,
    admin_app,
    assert_matches_golden,
    client,
    golden_book,
    golden_payload,
    normalise,
)


@pytest.mark.skipif(os.environ.get("V204_RECORD_GOLDEN") != "1", reason="recorded once, in V204-1")
def test_record_golden(golden_book):
    payloads = record_golden.capture(golden_book.client)
    assert golden_book.network_calls == []
    record_golden.write(payloads)


def test_capture_is_deterministic(golden_book):
    from swingbot.admin.api_v1 import risk

    first = record_golden.capture(golden_book.client)
    risk._invalidate_cache()
    second = record_golden.capture(golden_book.client)
    assert golden_book.network_calls == []
    assert {n: normalise(b) for n, b in first.items()} == {n: normalise(b) for n, b in second.items()}


def test_today_matches_golden(golden_book):
    payloads = record_golden.capture(golden_book.client)
    assert golden_book.network_calls == []
    for name in GOLDEN_NAMES:
        assert_matches_golden(name, payloads[name])


def _assert_risk_figures(body):
    assert len(body["positions"]) == 3
    assert body["unmapped_count"] == 1
    assert body["heat"]["open_pct"] is not None
    assert body["metrics"]["benchmark_symbol"] == "SPY"
    assert body["correlation"]["values"], "correlation came back empty: bars did not reach risk"


def test_golden_book_carries_real_figures():
    _assert_risk_figures(golden_payload("risk"))
    assert golden_payload("performance_main")["totals"]["closed"] == 12
    assert golden_payload("equity_curve_main")["points_n"] == 12
    assert golden_payload("calendar_pnl")["month"] == GOLDEN_MONTH
    assert golden_payload("analytics_snapshot")["equity_curve"]["points"]
    assert golden_payload("sparkline")["points"]
    assert all("checked_at" not in json.dumps(golden_payload(n)) for n in GOLDEN_NAMES)


def test_golden_files_are_never_overwritten(tmp_path):
    (tmp_path / "risk.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError, match="frozen"):
        record_golden.write({name: {} for name in GOLDEN_NAMES}, directory=tmp_path)
