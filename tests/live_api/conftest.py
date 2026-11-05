"""v202 `/api/v1/live` fixtures. The app and client are tests/admin's, imported
not copied (DATA_DIR isolation, module reloads, account balance 10,000); the
tests live here because the admin suite sits near max_tests."""
import pytest

from tests.admin.conftest import _clear_login_limiter, admin_app, auth, client  # noqa: F401

_LOGIN = {"username": "admin", "password": "admin"}


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Every market-data entry point answers empty and records the call.
    `/live` must make none of them; `/risk` (heat-equality test) makes several."""
    calls: list[str] = []

    def recorder(name, value):
        def fake(*args, **kwargs):
            calls.append(name)
            return value
        return fake

    for name, value in (("get_daily_data", None), ("get_daily_data_batch", {}),
                        ("get_quote_batch", {})):
        monkeypatch.setattr(f"swingbot.core.marketdata.data.{name}",
                            recorder(name, value), raising=False)
    return calls


@pytest.fixture
def fresh_risk_cache():
    """`GET /risk` caches its collector for a few seconds; never reuse it."""
    import swingbot.admin.app  # noqa: F401 -- api_v1 imports resolve through the app
    from swingbot.admin.api_v1 import risk
    risk._invalidate_cache()
    yield
    risk._invalidate_cache()
