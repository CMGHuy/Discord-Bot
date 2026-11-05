"""v204 V204-2: the measure-first harness (no database, no app)."""
import json
import re
import subprocess

import pytest

from scripts.dev import time_admin_routes as tar
from swingbot.core.marketdata import data

VERDICT_LINE = re.compile(
    r"^- `(analytics\.performance|analytics\.equity_curve|calendar\.pnl)`: \*\*(request|snapshot)\*\* "
    r"\(warm max \d+\.\d{3} s, cold max \d+\.\d{3} s\)$", re.M)


@pytest.mark.parametrize("warm,cold,expected", [
    ([0.5] * 5, [1.0] * 5, "request"),
    ([0.1, 0.2, 0.51, 0.1, 0.1], [0.2] * 5, "snapshot"),
    ([0.1] * 5, [0.3, 1.01, 0.2, 0.2, 0.2], "snapshot"),
    ([], [0.1] * 5, "snapshot"),
    ([0.1] * 5, [], "snapshot"),
])
def test_verdict_rule(warm, cold, expected):
    assert tar.verdict(warm, cold) == expected


class FakeClient:
    def __init__(self, status=200):
        self.calls, self.status = [], status

    def get(self, path):
        self.calls.append(path)
        return type("Resp", (), {"status_code": self.status})()


def test_measure_warm_discards_one_warmup_and_times_each_run():
    client = FakeClient()
    times = tar.measure_warm(client, "/api/v1/calendar/pnl", runs=5)
    assert len(times) == 5 and all(t >= 0 for t in times)
    assert client.calls == ["/api/v1/calendar/pnl"] * 6


def test_timed_get_refuses_a_non_200():
    with pytest.raises(RuntimeError, match="503"):
        tar.timed_get(FakeClient(status=503), "/api/v1/calendar/pnl")


def test_poisoned_network_records_raises_and_restores():
    original = data.get_quote_batch
    with tar.poisoned_network() as calls:
        with pytest.raises(AssertionError):
            data.get_quote_batch(["AAPL"])
        assert calls == ["swingbot.core.marketdata.data.get_quote_batch"]
    assert data.get_quote_batch is original


def test_cold_run_with_a_network_call_is_a_defect(monkeypatch):
    out = json.dumps({"seconds": 0.1, "network": ["swingbot.core.marketdata.fx._refreshed_frame"]})
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, out, ""))
    with pytest.raises(tar.NetworkDefect, match="_refreshed_frame"):
        tar.measure_cold("calendar.pnl", runs=1)


def test_cold_run_collects_one_time_per_subprocess(monkeypatch):
    out = json.dumps({"seconds": 0.25, "network": []})
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, out, ""))
    assert tar.measure_cold("calendar.pnl", runs=3) == [0.25, 0.25, 0.25]


def test_render_has_exactly_one_verdict_line_per_route():
    results = {route: {"warm": [0.2] * 5, "cold": [0.7] * 5} for route in tar.ROUTES}
    results["calendar.pnl"]["cold"] = [1.4] * 5
    text = tar.render(results)
    found = VERDICT_LINE.findall(text)
    assert found == [("analytics.performance", "request"), ("analytics.equity_curve", "request"),
                     ("calendar.pnl", "snapshot")]
    assert "| route |" in text


def test_warm_network_defect_takes_precedence_over_response_status(monkeypatch, capsys):
    class ForbiddenClient:
        def get(self, path):
            try:
                data.get_quote_batch(["AAPL"])
            except AssertionError:
                return FakeClient(status=503).get(path)

    monkeypatch.setattr(tar, "_client", ForbiddenClient)
    assert tar.main([]) == 2
    assert "swingbot.core.marketdata.data.get_quote_batch" in capsys.readouterr().err


def test_cold_child_login_failure_keeps_parent_error_generic(monkeypatch, capsys):
    def failed_login(*args, **kwargs):
        raise subprocess.CalledProcessError(3, args[0], stderr="login failed")

    monkeypatch.setattr(subprocess, "run", failed_login)
    with pytest.raises(SystemExit) as exc:
        tar.measure_cold("calendar.pnl", runs=1)
    assert exc.value.code == 3
    assert capsys.readouterr().err == "login failed\n"




def test_measure_all_reports_route_progress_on_stderr(monkeypatch, capsys):
    monkeypatch.setattr(tar, "_client", FakeClient)
    monkeypatch.setattr(tar, "measure_cold", lambda route: [0.25] * 5)

    assert tar.main([]) == 0

    output = capsys.readouterr()
    assert output.err.splitlines() == [f"Measuring {route}" for route in tar.ROUTES]
    assert VERDICT_LINE.findall(output.out)



def test_provider_fallback_exits_two_without_results(monkeypatch, capsys, tmp_path):
    class NoNetworkTicker:
        fast_info = None

        def __init__(self, symbol):
            pass

        def history(self, **kwargs):
            return None

    class QuoteFallbackClient(FakeClient):
        def get(self, path):
            data.get_current_price_detail("AAPL")
            return super().get(path)

    monkeypatch.setattr(data.config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(data, "_marked_quotes", lambda *args, **kwargs: {})
    monkeypatch.setattr(data.yf, "Ticker", NoNetworkTicker)
    monkeypatch.setattr(tar, "_client", QuoteFallbackClient)
    monkeypatch.setattr(tar, "measure_cold", lambda route: [0.25] * 5)
    monkeypatch.setattr(tar, "_write_results", lambda out, body: out.write_text(body))
    out = tmp_path / "timings.md"

    assert tar.main(["--out", str(out)]) == 2

    assert "yfinance.Ticker" in capsys.readouterr().err
    assert not out.exists()
