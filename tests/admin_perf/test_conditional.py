"""v218 V218-8: the conditional-response decorator (v206 P3-c).

Every input is monkeypatched on a tiny Flask app; the admitted-route behaviour
on the real app is tests/admin_perf/test_conditional_routes.py (V218-13)."""
import datetime as dt

import pytest
from flask import Flask, jsonify, request
from werkzeug.datastructures import MultiDict

from swingbot import config
from swingbot.admin import build_identity
from swingbot.admin.api_v1 import conditional as cond
from swingbot.admin.api_v1.read_scope import READ_SCOPE_ATTR, read_scope
from swingbot.core.infra import store_generation, store_snapshot
from swingbot.core.marketdata import fx_convert


@pytest.fixture
def inputs(monkeypatch):
    """The ETag's inputs, each one settable by a test."""
    state = {
        "build": "0123456789abcdef|img:1",
        "token": (1, 2, 3),
        "versions": ((5, "2026-11-04T10:00:00+00:00"), (7, "2026-11-04T11:00:00+00:00"), (2, None)),
        "fx": (40, dt.datetime(2026, 11, 4, 6, 0, tzinfo=dt.timezone.utc)),
        "today": dt.date(2026, 11, 4),
        "principal": ("admin", "boss", None),
    }
    monkeypatch.setattr(config, "ADMIN_STORE_SNAPSHOT", "on", raising=False)
    monkeypatch.setattr(store_generation, "connected", lambda: True)
    monkeypatch.setattr(build_identity, "build_version", lambda: state["build"])
    monkeypatch.setattr(store_generation, "token", lambda: state["token"])
    monkeypatch.setattr(store_snapshot, "request_versions", lambda: state["versions"])
    monkeypatch.setattr(cond, "_fx_version", lambda: state["fx"])
    monkeypatch.setattr(fx_convert, "berlin_today", lambda: state["today"])
    monkeypatch.setattr(cond, "_principal", lambda: state["principal"])
    return state


@pytest.fixture
def tiny():
    """GET /thing behind @conditional("thing"); ?ok=0 is not admitted, ?ok=boom makes admit
    raise, ?fail=<code> answers that status."""
    app = Flask(__name__)
    calls = []

    def admit(args):
        if args.get("ok") == "boom":
            raise RuntimeError("v218 boom")
        return args.get("ok") != "0"

    @app.get("/thing")
    @cond.conditional("thing", admit)
    @read_scope
    def thing():
        calls.append(request.args.to_dict())
        if request.args.get("fail"):
            return jsonify(error="nope"), int(request.args["fail"])
        return jsonify(n=len(calls))

    app.calls = calls
    return app


def _tag(args=None, key="thing"):
    with Flask(__name__).test_request_context("/thing", query_string=args or {}):
        return cond.compute_etag(key, request.args)


# --- tag shape and inputs ---------------------------------------------------

def test_the_tag_is_weak_and_32_hex(inputs):
    tag = _tag()
    assert tag.startswith('W/"') and tag.endswith('"')
    opaque = tag[3:-1]
    assert len(opaque) == 32 and int(opaque, 16) >= 0


def test_the_same_inputs_give_the_same_tag(inputs):
    assert _tag({"status": "CLOSED"}) == _tag({"status": "CLOSED"})


@pytest.mark.parametrize("name, value", [
    ("build", "fedcba9876543210|img:2"),
    ("token", (2, 2, 3)),
    ("token", (1, 3, 3)),
    ("token", (1, 2, 4)),
    ("versions", ((6, "2026-11-04T10:00:00+00:00"), (7, "2026-11-04T11:00:00+00:00"), (2, None))),
    ("versions", ((5, "2026-11-04T10:00:00+00:00"), (7, "2026-11-04T11:00:01+00:00"), (2, None))),
    ("versions", ((5, "2026-11-04T10:00:00+00:00"), (7, "2026-11-04T11:00:00+00:00"), (3, "x"))),
    ("fx", (41, dt.datetime(2026, 11, 4, 6, 0, tzinfo=dt.timezone.utc))),
    ("today", dt.date(2026, 11, 5)),
    ("principal", ("viewer", "anna", 7)),
])
def test_each_input_changes_the_tag_on_its_own(inputs, name, value):
    before = _tag({"status": "CLOSED"})
    inputs[name] = value
    assert _tag({"status": "CLOSED"}) != before


def test_the_query_and_the_route_key_change_the_tag(inputs):
    base = _tag({"status": "CLOSED"})
    assert _tag({"status": "CLOSED", "page": "2"}) != base
    assert _tag({"status": "CLOSED"}, key="other") != base


def test_the_inputs_are_exactly_the_documented_ones(inputs):
    with Flask(__name__).test_request_context("/thing?status=CLOSED"):
        got = cond.etag_inputs("thing", request.args)
    assert got == ("thing", inputs["build"], inputs["token"], inputs["versions"], inputs["fx"],
                   "status=CLOSED", "2026-11-04", inputs["principal"])


def test_normalised_query_ignores_order_and_keeps_every_value():
    a = MultiDict([("status", "CLOSED"), ("sort", "-closed_at"), ("ticker", "a"), ("ticker", "b")])
    b = MultiDict([("ticker", "a"), ("sort", "-closed_at"), ("ticker", "b"), ("status", "CLOSED")])
    assert cond.normalised_query(a) == cond.normalised_query(b)
    assert cond.normalised_query(a) != cond.normalised_query(MultiDict([("ticker", "a")]))
    assert cond.normalised_query(MultiDict()) == ""


# --- If-None-Match ----------------------------------------------------------

@pytest.mark.parametrize("header, hit", [
    (None, False), ("", False),
    ('W/"abc"', True), ('"abc"', True), ('W/"zzz", W/"abc"', True), ("*", True),
    ('W/"abcd"', False), ('W/"ab"', False),
])
def test_if_none_match_accepts_weak_strong_lists_and_star(header, hit):
    assert cond.if_none_match_hits(header, 'W/"abc"') is hit


# --- the decorator ----------------------------------------------------------

def test_a_200_carries_the_tag_and_private_no_cache(inputs, tiny):
    response = tiny.test_client().get("/thing")
    assert response.status_code == 200
    assert response.headers["ETag"].startswith('W/"')
    assert response.headers["Cache-Control"] == "private, no-cache"


def test_a_matching_if_none_match_is_a_bodiless_304_that_skips_the_view(inputs, tiny):
    client = tiny.test_client()
    tag = client.get("/thing").headers["ETag"]
    response = client.get("/thing", headers={"If-None-Match": tag})
    assert response.status_code == 304
    assert response.get_data() == b""
    assert response.headers["ETag"] == tag
    assert response.headers["Cache-Control"] == "private, no-cache"
    assert len(tiny.calls) == 1                     # the body was built once, for the 200


def test_a_stale_if_none_match_gets_a_fresh_200(inputs, tiny):
    client = tiny.test_client()
    tag = client.get("/thing").headers["ETag"]
    inputs["token"] = (9, 9, 9)
    response = client.get("/thing", headers={"If-None-Match": tag})
    assert response.status_code == 200 and response.headers["ETag"] != tag


@pytest.mark.parametrize("code", [400, 401, 403, 404, 500])
def test_an_error_status_never_carries_a_tag(inputs, tiny, code):
    response = tiny.test_client().get(f"/thing?fail={code}")
    assert response.status_code == code
    assert "ETag" not in response.headers
    assert response.headers.get("Cache-Control") != "private, no-cache"


@pytest.mark.parametrize("setup", ["switch_off", "disconnected", "fresh", "not_admitted",
                                   "admit_raises", "input_raises", "build_missing"])
def test_every_ineligible_or_failing_request_runs_the_view_without_a_tag(inputs, tiny, monkeypatch,
                                                                        setup):
    headers, query = {}, ""
    if setup == "switch_off":
        monkeypatch.setattr(config, "ADMIN_STORE_SNAPSHOT", "off", raising=False)
    elif setup == "disconnected":
        monkeypatch.setattr(store_generation, "connected", lambda: False)
    elif setup == "fresh":
        headers["X-Swingbot-Fresh"] = "1"
    elif setup == "not_admitted":
        query = "?ok=0"
    elif setup == "admit_raises":
        query = "?ok=boom"
    elif setup == "input_raises":
        monkeypatch.setattr(store_snapshot, "request_versions", _raise)
    else:
        monkeypatch.setattr(build_identity, "build_version", _raise_os)
    response = tiny.test_client().get("/thing" + query, headers={**headers, "If-None-Match": "*"})
    assert response.status_code == 200                 # '*' would 304 if a tag were computed
    assert "ETag" not in response.headers
    assert len(tiny.calls) == 1                         # the view ran, unchanged


def test_the_markers_survive_and_name_the_route():
    @cond.conditional("thing", lambda args: True)
    @read_scope
    def view():
        return "ok"

    assert getattr(view, cond.CONDITIONAL_ATTR) == "thing"
    assert getattr(view, READ_SCOPE_ATTR) is True
    assert view.__name__ == "view"


def _raise(*_a, **_k):
    raise RuntimeError("v218 boom")


def _raise_os(*_a, **_k):
    raise OSError("VERSION.json missing")


def test_the_real_principal_maps_a_session_and_a_basic_auth_caller(monkeypatch):
    """_principal() is patched everywhere else: pin its own two branches."""
    from swingbot.admin import app as admin_app
    flask_app = Flask(__name__)
    monkeypatch.setattr(admin_app, "resolve_principal",
                        lambda: {"role": "viewer", "username": "v", "user_id": 7})
    with flask_app.test_request_context("/"):
        assert cond._principal() == ("viewer", "v", 7)
    monkeypatch.setattr(admin_app, "resolve_principal", lambda: None)
    with flask_app.test_request_context(
            "/", headers={"Authorization": "Basic " + __import__("base64").b64encode(b"bot:pw").decode()}):
        assert cond._principal() == ("admin", "bot", None)
    with flask_app.test_request_context("/"):
        assert cond._principal() == ("admin", None, None)
