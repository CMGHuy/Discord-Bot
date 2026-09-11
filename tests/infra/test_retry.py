import pytest

from swingbot.core.infra.retry import with_retry


def test_returns_result_on_first_success():
    calls = []

    def fn(x):
        calls.append(x)
        return x * 2

    assert with_retry(fn, 3) == 6
    assert calls == [3]


def test_retries_transient_failure_then_succeeds(monkeypatch):
    sleeps = []
    monkeypatch.setattr("swingbot.core.infra.retry.time.sleep", lambda s: sleeps.append(s))

    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ValueError("transient")
        return "ok"

    result = with_retry(flaky, attempts=3, base_delay=1.0)

    assert result == "ok"
    assert attempts["n"] == 3
    assert sleeps == [1.0, 2.0]   # exponential backoff, one sleep per failed attempt


def test_raises_last_error_when_every_attempt_fails(monkeypatch):
    monkeypatch.setattr("swingbot.core.infra.retry.time.sleep", lambda s: None)

    def always_fails():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        with_retry(always_fails, attempts=2, base_delay=0.01)


def test_passes_through_args_and_kwargs():
    def fn(a, b, c=None):
        return (a, b, c)

    assert with_retry(fn, 1, 2, c=3) == (1, 2, 3)


def test_does_not_sleep_after_final_attempt(monkeypatch):
    sleeps = []
    monkeypatch.setattr("swingbot.core.infra.retry.time.sleep", lambda s: sleeps.append(s))

    def always_fails():
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        with_retry(always_fails, attempts=3, base_delay=1.0)

    assert sleeps == [1.0, 2.0]   # 2 sleeps between 3 attempts, none after the last
