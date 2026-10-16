"""v148 O2: constant-time credential checks and one login limiter shared by
the SPA login, v1 Basic auth and app.require_auth's Basic path."""
import base64
import re
import threading
from pathlib import Path

import pytest
from tests.admin.api_v1_contract import assert_error

from swingbot.admin import login_limiter
from swingbot.admin.login_limiter import LoginLimiter

_WRONG = {"username": "admin", "password": "wrong"}
_RIGHT = {"username": "admin", "password": "admin"}
_FIFTEEN = "Too many failed sign-ins. Try again in 15 minutes."


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _basic(user: str, password: str) -> dict:
    token = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def _fail_login(client, n: int, **kwargs) -> None:
    for _ in range(n):
        assert client.post("/api/v1/session", json=_WRONG, **kwargs).status_code == 401


# --- LoginLimiter -------------------------------------------------------------

def test_five_failures_lock_the_key_for_the_window():
    limiter = LoginLimiter(clock=_Clock())
    for _ in range(4):
        limiter.fail("203.0.113.7")
    assert limiter.check("203.0.113.7") is None
    limiter.fail("203.0.113.7")
    assert limiter.check("203.0.113.7") == 900
    assert limiter.check("198.51.100.9") is None


def test_the_window_slides_off_the_oldest_failure():
    clock = _Clock()
    limiter = LoginLimiter(clock=clock)
    limiter.fail("k")                      # t = 1000
    clock.now = 1100.0
    for _ in range(4):
        limiter.fail("k")                  # t = 1100
    assert limiter.check("k") == 800       # until the t=1000 failure ages out
    clock.now = 1900.0
    assert limiter.check("k") is None      # four left inside the window
    limiter.fail("k")                      # a fifth inside the window again
    assert limiter.check("k") == 100       # 1100 + 900 - 1900


def test_success_clears_the_key():
    limiter = LoginLimiter(clock=_Clock())
    for _ in range(4):
        limiter.fail("k")
    limiter.succeed("k")
    for _ in range(4):
        limiter.fail("k")
    assert limiter.check("k") is None


def test_memory_is_bounded_by_the_keys_seen_inside_the_window():
    clock = _Clock()
    limiter = LoginLimiter(clock=clock)
    for i in range(100):
        limiter.fail(f"10.0.0.{i}")
    assert len(limiter) == 100
    clock.now += 901
    limiter.check("anyone")
    assert len(limiter) == 0


def test_concurrent_failures_are_all_counted():
    limiter = LoginLimiter(max_failures=4000, clock=_Clock())

    def hammer():
        for _ in range(500):
            limiter.fail("k")

    threads = [threading.Thread(target=hammer) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert limiter.check("k") is not None   # 8 x 500 = exactly the 4000 that lock


def test_reset_forgets_everything():
    limiter = LoginLimiter(clock=_Clock())
    for _ in range(5):
        limiter.fail("k")
    limiter.reset()
    assert limiter.check("k") is None and len(limiter) == 0


@pytest.mark.parametrize("seconds, text", [
    (1, "1 minute"), (60, "1 minute"), (61, "2 minutes"), (900, "15 minutes"),
])
def test_message_rounds_up_to_whole_minutes(seconds, text):
    assert login_limiter.rate_limited_message(seconds) == (
        f"Too many failed sign-ins. Try again in {text}.")


# --- credentials_match ----------------------------------------------------------

def test_credentials_match_always_compares_both_fields(admin_app, monkeypatch):
    from swingbot.admin import app as app_mod

    calls = []
    real = app_mod.hmac.compare_digest
    monkeypatch.setattr(app_mod.hmac, "compare_digest",
                        lambda a, b: calls.append((a, b)) or real(a, b))

    assert app_mod.credentials_match("nobody", "admin") is False
    # No short-circuit on the wrong username: the password is compared too.
    assert calls == [(b"nobody", b"admin"), (b"admin", b"admin")]
    calls.clear()
    assert app_mod.credentials_match("admin", "admin") is True
    assert len(calls) == 2
    assert app_mod.credentials_match("admin", "wrong") is False


def test_no_plain_comparison_against_the_admin_credentials_is_left():
    admin = Path(__file__).resolve().parents[2] / "swingbot" / "admin"
    plain = re.compile(r"[=!]=\s*(_app\.)?ADMIN_(USERNAME|PASSWORD)\b"
                       r"|ADMIN_(USERNAME|PASSWORD)\s*[=!]=")
    offenders = [str(p) for p in admin.rglob("*.py") if plain.search(p.read_text(encoding="utf-8"))]
    assert offenders == []


# --- the three paths --------------------------------------------------------------

def test_spa_login_locks_after_five_failures_even_for_the_right_password(client):
    _fail_login(client, 5)
    r = client.post("/api/v1/session", json=_RIGHT)
    assert_error(r, "rate_limited", 429)
    assert r.get_json()["error"]["message"] == _FIFTEEN
    assert 899 <= int(r.headers["Retry-After"]) <= 900


def test_v1_basic_auth_locks_after_five_failures(client):
    for _ in range(5):
        assert_error(client.get("/api/v1/health", headers=_basic("admin", "wrong")), "auth", 401)
    r = client.get("/api/v1/health", headers=_basic("admin", "admin"))
    assert_error(r, "rate_limited", 429)
    assert 899 <= int(r.headers["Retry-After"]) <= 900


def test_app_require_auth_basic_path_answers_a_plain_text_429(admin_app):
    from swingbot.admin import app as app_mod

    view = app_mod.require_auth(lambda: "ok")

    def call(user, password):
        with admin_app.test_request_context("/", headers=_basic(user, password)):
            return admin_app.make_response(view())

    assert call("admin", "admin").get_data(as_text=True) == "ok"
    for _ in range(5):
        assert call("admin", "wrong").status_code == 401
    r = call("admin", "admin")
    assert r.status_code == 429
    assert r.mimetype == "text/plain"
    assert r.get_data(as_text=True) == _FIFTEEN
    assert 899 <= int(r.headers["Retry-After"]) <= 900


def test_the_three_paths_share_one_count(client):
    _fail_login(client, 3)
    for _ in range(2):
        assert client.get("/api/v1/health", headers=_basic("admin", "wrong")).status_code == 401
    assert_error(client.post("/api/v1/session", json=_RIGHT), "rate_limited", 429)
    assert_error(client.get("/api/v1/health", headers=_basic("admin", "admin")), "rate_limited", 429)


def test_a_right_password_clears_the_count(client):
    _fail_login(client, 4)
    assert client.post("/api/v1/session", json=_RIGHT).status_code == 200
    _fail_login(client, 5)   # the fifth is still a plain 401: the count restarted


def test_the_key_is_cf_connecting_ip(client):
    a = {"CF-Connecting-IP": "203.0.113.7"}
    b = {"CF-Connecting-IP": "198.51.100.9"}
    _fail_login(client, 5, headers=a)
    assert_error(client.post("/api/v1/session", json=_RIGHT, headers=a), "rate_limited", 429)
    # Same socket peer (the test client, as cloudflared is in production),
    # different client address: not locked.
    assert client.post("/api/v1/session", json=_RIGHT, headers=b).status_code == 200


def test_requests_without_credentials_never_count(client):
    for _ in range(10):
        assert_error(client.get("/api/v1/health"), "auth", 401)
        assert_error(client.post("/api/v1/session", json={}), "auth", 401)
    assert client.get("/api/v1/health", headers=_basic("admin", "admin")).status_code == 200


def test_the_lock_lifts_once_the_window_has_passed(client, monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(login_limiter, "LIMITER", LoginLimiter(clock=clock))
    _fail_login(client, 5)
    assert_error(client.post("/api/v1/session", json=_RIGHT), "rate_limited", 429)
    clock.now += 901
    assert client.post("/api/v1/session", json=_RIGHT).status_code == 200
