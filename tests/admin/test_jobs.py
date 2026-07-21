"""JobManager: subprocess job lifecycle. `kind="test"` allows a raw argv
(interpreter-relative) for tests -- `kind="tune"` (C31) always routes
through scripts/tune_strategy.py and the TRAIN-only guardrail."""
import time

import pytest


def _wait_until_done(mgr, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = mgr.status(job_id)
        if status and status["state"] in ("done", "failed"):
            return status
        time.sleep(0.05)
    raise TimeoutError(f"job {job_id} did not finish within {timeout}s")


def test_job_runs_and_tail_captures_output(admin_app):
    from swingbot.admin.jobs import JobManager
    mgr = JobManager()
    job_id = mgr.start("test", ["-c", "print('hi')"])
    status = _wait_until_done(mgr, job_id)
    assert status["state"] == "done"
    assert status["returncode"] == 0
    assert "hi" in mgr.tail(job_id)


def test_concurrent_start_raises_while_busy(admin_app):
    from swingbot.admin.jobs import JobManager
    mgr = JobManager()
    mgr.start("test", ["-c", "import time; time.sleep(2)"])
    with pytest.raises(RuntimeError, match="already running"):
        mgr.start("test", ["-c", "print('should not start')"])


class _FakeManagerOK:
    def start(self, kind, args):
        return "job123"


class _FakeManagerBusy:
    def start(self, kind, args):
        raise RuntimeError("job already running")


def test_api_jobs_tune_returns_job_id(client, auth, monkeypatch):
    monkeypatch.setattr("swingbot.admin.api.job_manager", _FakeManagerOK())
    r = client.post("/api/jobs/tune", data={"strategy": "RSI"}, headers=auth)
    assert r.get_json() == {"job_id": "job123"}


def test_api_jobs_tune_409_when_busy(client, auth, monkeypatch):
    monkeypatch.setattr("swingbot.admin.api.job_manager", _FakeManagerBusy())
    r = client.post("/api/jobs/tune", data={"strategy": "RSI"}, headers=auth)
    assert r.status_code == 409
    assert r.get_json() == {"error": "busy"}


def test_api_jobs_tune_400_on_malformed_params_json(client, auth, monkeypatch):
    monkeypatch.setattr("swingbot.admin.api.job_manager", _FakeManagerOK())
    r = client.post("/api/jobs/tune", data={"strategy": "RSI", "params": "not-json"}, headers=auth)
    assert r.status_code == 400


def test_api_jobs_tune_400_on_non_dict_params(client, auth, monkeypatch):
    monkeypatch.setattr("swingbot.admin.api.job_manager", _FakeManagerOK())
    r = client.post("/api/jobs/tune", data={"strategy": "RSI", "params": "42"}, headers=auth)
    assert r.status_code == 400


def test_api_jobs_tune_400_on_non_numeric_be_trigger(client, auth, monkeypatch):
    monkeypatch.setattr("swingbot.admin.api.job_manager", _FakeManagerOK())
    r = client.post(
        "/api/jobs/tune",
        data={"strategy": "RSI", "params": '{"be_trigger": [1,2,3]}'},
        headers=auth,
    )
    assert r.status_code == 400


def test_guardrail_blocks_validation_window():
    from swingbot.admin.jobs import assert_train_only, build_tune_args
    with pytest.raises(ValueError):
        assert_train_only(["--from", "2024-06-01", "--to", "2024-12-31"])
    with pytest.raises(ValueError):
        assert_train_only(["--validation"])
    assert_train_only(build_tune_args("RSI", None))  # must not raise


def test_guardrail_blocks_single_token_flag_equals_value():
    from swingbot.admin.jobs import assert_train_only
    with pytest.raises(ValueError):
        assert_train_only(["--from=2024-06-01"])


def test_guardrail_blocks_non_zero_padded_date():
    from swingbot.admin.jobs import assert_train_only
    with pytest.raises(ValueError):
        assert_train_only(["2024-1-1"])


def test_guardrail_no_false_positive_on_ordinary_args():
    from swingbot.admin.jobs import assert_train_only, build_tune_args
    assert_train_only(["--strategy", "RSI"])  # must not raise
    assert_train_only(build_tune_args("RSI", None))  # must not raise


def test_build_tune_args_rejects_unknown_strategy():
    from swingbot.admin.jobs import build_tune_args
    with pytest.raises(ValueError, match="unknown strategy"):
        build_tune_args("Not A Real Strategy", None)


def test_build_tune_args_passes_be_trigger_through():
    from swingbot.admin.jobs import build_tune_args
    args = build_tune_args("RSI", {"be_trigger": 0.6})
    assert args == ["--strategy", "RSI", "--be-trigger", "0.6"]


def test_build_tune_args_rejects_non_dict_params():
    from swingbot.admin.jobs import build_tune_args
    with pytest.raises(ValueError):
        build_tune_args("RSI", 42)


def test_build_tune_args_rejects_non_numeric_be_trigger():
    from swingbot.admin.jobs import build_tune_args
    with pytest.raises(ValueError):
        build_tune_args("RSI", {"be_trigger": [1, 2, 3]})


def test_job_manager_start_enforces_guardrail_even_if_caller_bypasses_builder(admin_app):
    from swingbot.admin.jobs import JobManager
    mgr = JobManager()
    with pytest.raises(ValueError):
        mgr.start("tune", ["--strategy", "RSI", "--from", "2024-01-01"])


import json
import os


def test_tuning_results_table_renders_and_highlights_passing_rows(client, auth):
    from swingbot import config
    results_dir = os.path.join(config.DATA_DIR, "tuning_results")
    os.makedirs(results_dir, exist_ok=True)
    payload = {
        "strategy": "MACD",
        "grid": [
            {"params": {"ext_atr": 0.75}, "n_eval": 40, "win_rate": 82.0, "expectancy_r": 0.09, "excluded_share": 0.2},
            {"params": {"ext_atr": 1.5}, "n_eval": 10, "win_rate": 60.0, "expectancy_r": -0.02, "excluded_share": 0.6},
        ],
        "best": None,
    }
    with open(os.path.join(results_dir, "job1.json"), "w") as f:
        json.dump(payload, f)

    r = client.get("/tuning?job_id=job1", headers=auth)
    html = r.data.decode("utf-8")
    assert "82.0" in html
    assert 'class="diff-add"' in html  # the passing row (N=40, WR=82, ExpR>0, excl=20%)


def test_load_result_rejects_path_traversal_job_id(admin_app):
    """job_id="../secret" resolves (via os.path.join(DATA_DIR, "tuning_results",
    "../secret.json")) to DATA_DIR/secret.json, one level above tuning_results/.
    Plant a real file exactly there so a regression here would leak it, proving
    the guard -- not just an absent-file coincidence -- is what blocks the read."""
    from swingbot import config
    from swingbot.admin.pages import _load_result

    os.makedirs(os.path.join(config.DATA_DIR, "tuning_results"), exist_ok=True)
    with open(os.path.join(config.DATA_DIR, "secret.json"), "w") as f:
        json.dump({"strategy": "LEAKED_SECRET", "grid": [], "best": None}, f)

    assert _load_result("../secret") is None
    assert _load_result("../../secret") is None


def test_tuning_page_ignores_path_traversal_job_id(client, auth):
    from swingbot import config

    os.makedirs(os.path.join(config.DATA_DIR, "tuning_results"), exist_ok=True)
    with open(os.path.join(config.DATA_DIR, "secret.json"), "w") as f:
        json.dump({"strategy": "LEAKED_SECRET", "grid": [], "best": None}, f)

    r = client.get("/tuning?job_id=" + "..%2fsecret", headers=auth)
    assert r.status_code == 200
    html = r.data.decode("utf-8")
    assert "LEAKED_SECRET" not in html  # the planted file must never be read/rendered
    assert "Results —" not in html  # no result card rendered for a rejected id
