"""v162 AH16: the admin Tuning page chooses its training data (spec §3).

Without this the TRAINING_DATA_SOURCE flip would silently change every
admin-run grid (staff-engineer BLOCKING finding). The flag is always on the
argv, so a stored job says which data it ran on."""
import pytest

from swingbot import config
from swingbot.admin.jobs import assert_train_only, build_tune_args
from tests.admin.api_v1_contract import assert_error, assert_shape
from tests.store_seed import seed_store

_LOGIN = {"username": "admin", "password": "admin"}


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture
def default_yfinance(monkeypatch):
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance")


# --- build_tune_args ---------------------------------------------------------

def test_the_config_default_is_emitted_when_no_source_is_given(default_yfinance):
    assert build_tune_args("RSI", None) == ["--strategy", "RSI", "--data-source", "yfinance"]


def test_the_default_is_read_at_call_time_not_import_time(monkeypatch):
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "alpaca")
    assert build_tune_args("RSI", {})[2:4] == ["--data-source", "alpaca"]
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance")
    assert build_tune_args("RSI", {})[2:4] == ["--data-source", "yfinance"]


def test_an_explicit_source_wins_over_the_default(default_yfinance):
    args = build_tune_args("RSI", {"data_source": "alpaca", "be_trigger": 0.6})
    assert args == ["--strategy", "RSI", "--data-source", "alpaca", "--be-trigger", "0.6"]


def test_an_empty_source_means_the_default(default_yfinance):
    assert build_tune_args("RSI", {"data_source": ""})[3] == "yfinance"


@pytest.mark.parametrize("bad", ["polygon", "ALPACA", 5, ["alpaca"]])
def test_a_source_outside_the_whitelist_is_refused(default_yfinance, bad):
    with pytest.raises(ValueError, match="data_source"):
        build_tune_args("RSI", {"data_source": bad})


def test_the_source_flag_never_trips_the_train_only_guard(default_yfinance):
    assert_train_only(build_tune_args("RSI", {"data_source": "alpaca"}))  # must not raise


# --- POST /jobs/tune -----------------------------------------------------------

class _CapturingManager:
    def __init__(self):
        self.calls = []

    def start(self, kind, args):
        self.calls.append((kind, list(args)))
        return "job123"


def _patch_manager(monkeypatch, manager):
    # api_v1/jobs.py binds the manager at import; patch that reference.
    monkeypatch.setattr("swingbot.admin.api_v1.jobs.job_manager", manager)


def test_start_tune_passes_the_chosen_source_to_the_job(logged_in, monkeypatch, default_yfinance):
    manager = _CapturingManager()
    _patch_manager(monkeypatch, manager)
    r = logged_in.post("/api/v1/jobs/tune",
                       json={"strategy": "VWAP", "params": {"data_source": "alpaca"}})
    assert r.status_code == 200
    assert manager.calls == [("tune", ["--strategy", "VWAP", "--data-source", "alpaca"])]


def test_start_tune_without_a_choice_uses_the_config_default(logged_in, monkeypatch, default_yfinance):
    manager = _CapturingManager()
    _patch_manager(monkeypatch, manager)
    logged_in.post("/api/v1/jobs/tune", json={"strategy": "VWAP"})
    assert manager.calls[0][1][2:] == ["--data-source", "yfinance"]


def test_start_tune_refuses_an_unknown_source(logged_in, monkeypatch):
    manager = _CapturingManager()
    _patch_manager(monkeypatch, manager)
    r = logged_in.post("/api/v1/jobs/tune",
                       json={"strategy": "VWAP", "params": {"data_source": "polygon"}})
    assert_error(r, "invalid", 400)
    assert "data_source" in r.get_json()["error"]["message"]
    assert manager.calls == []


# --- GET /jobs/tune/defaults -----------------------------------------------------

def test_defaults_require_auth(client):
    assert_error(client.get("/api/v1/jobs/tune/defaults"), "auth", 401)


def test_defaults_name_the_config_value_and_every_choice(logged_in, default_yfinance):
    body = logged_in.get("/api/v1/jobs/tune/defaults").get_json()
    assert_shape(body, {"data_source": str, "choices": list})
    assert body == {"data_source": "yfinance", "choices": ["alpaca", "yfinance"]}


# --- GET /jobs/<id>/result ---------------------------------------------------------

def _row():
    return {"params": {"a": 1}, "n_eval": 40, "win_rate": 82.0,
            "expectancy_r": 0.4, "excluded_share": 0.2}


def test_a_result_reports_the_source_it_ran_on(logged_in):
    seed_store("tuning", {"job1.json": {"strategy": "RSI", "grid": [_row()],
                                        "data_source": "alpaca",
                                        "provenance": {"data_source": "alpaca"}}})
    body = logged_in.get("/api/v1/jobs/job1/result").get_json()
    assert body["data_source"] == "alpaca"
    assert set(body) == {"job_id", "strategy", "grid", "data_source"}


def test_a_pre_v162_result_reads_as_yfinance(logged_in):
    """Old payloads carry no source; every one of them ran on yfinance."""
    seed_store("tuning", {"job1.json": {"strategy": "RSI", "grid": [_row()]}})
    assert logged_in.get("/api/v1/jobs/job1/result").get_json()["data_source"] == "yfinance"


def test_a_running_job_has_no_source_yet(logged_in):
    body = logged_in.get("/api/v1/jobs/stillgoing/result").get_json()
    assert body["data_source"] is None
