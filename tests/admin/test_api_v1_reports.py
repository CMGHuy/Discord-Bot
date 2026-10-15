"""GET /api/v1/reports/* — the v146 and v147 results, served unchanged (v150).

The endpoints compute nothing. Each calls one loader and wraps what it
returns: `None` is "not yet run" (a 200, a state the page renders), a dict
passes through untouched, and a loader that raises is a real fault (the
writers are atomic, so a present-but-unparseable file cannot be a race).
"""
import ast
import pathlib

import pytest

from tests.admin.api_v1_contract import NULLABLE_STR, assert_shape

_LOGIN = {"username": "admin", "password": "admin"}
_ENVELOPE = {"status": str, "generated_at": NULLABLE_STR, "result": (dict, type(None))}

# (url, the module attribute that loads it)
_REPORTS = [
    ("/api/v1/reports/expectancy-attribution", "_load_attribution"),
    ("/api/v1/reports/gate-counterfactual", "_load_gates"),
]


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture
def reports(client):
    # `client` first: it loads swingbot.admin.app, which registers the
    # endpoint modules; importing one cold is a circular import.
    from swingbot.admin.api_v1 import reports as module
    return module


@pytest.mark.parametrize("url, _loader", _REPORTS)
def test_requires_auth(client, url, _loader):
    assert client.get(url).status_code == 401


@pytest.mark.parametrize("url, loader", _REPORTS)
def test_never_run_is_a_200_not_run(logged_in, reports, monkeypatch, url, loader):
    monkeypatch.setattr(reports, loader, lambda: None)
    resp = logged_in.get(url)
    assert resp.status_code == 200
    body = resp.get_json()
    assert_shape(body, _ENVELOPE)
    assert body == {"status": "not_run", "generated_at": None, "result": None}


@pytest.mark.parametrize("url, loader", _REPORTS)
def test_a_result_passes_through_unchanged(logged_in, reports, monkeypatch, url, loader):
    result = {"generated_at": "2026-10-09T21:30:00+00:00", "verdict": "WEAK",
              "nested": {"buckets": [{"label": "0-5", "n": 12, "thin": True}],
                         "none": None, "float": 0.125}}
    monkeypatch.setattr(reports, loader, lambda: result)
    body = logged_in.get(url).get_json()
    assert_shape(body, _ENVELOPE)
    assert body["status"] == "ok"
    assert body["generated_at"] == "2026-10-09T21:30:00+00:00"
    assert body["result"] == result


@pytest.mark.parametrize("url, loader", _REPORTS)
def test_a_result_without_generated_at_still_serves(logged_in, reports, monkeypatch, url, loader):
    monkeypatch.setattr(reports, loader, lambda: {"verdict": "WEAK"})
    body = logged_in.get(url).get_json()
    assert (body["status"], body["generated_at"]) == ("ok", None)


@pytest.mark.parametrize("url, loader", _REPORTS)
def test_a_loader_that_raises_is_a_500_never_a_silent_not_run(
        logged_in, reports, monkeypatch, url, loader):
    def boom():
        raise ValueError("Expecting value: line 1 column 1 (char 0)")

    monkeypatch.setattr(reports, loader, boom)
    resp = logged_in.get(url)
    assert resp.status_code == 500
    error = resp.get_json()["error"]
    assert error["code"] == "report_unreadable"
    assert "Expecting value" in error["message"]


def test_one_report_failing_does_not_affect_the_other(logged_in, reports, monkeypatch):
    def boom():
        raise OSError("disk")

    monkeypatch.setattr(reports, "_load_attribution", boom)
    monkeypatch.setattr(reports, "_load_gates", lambda: None)
    assert logged_in.get(_REPORTS[0][0]).status_code == 500
    assert logged_in.get(_REPORTS[1][0]).get_json()["status"] == "not_run"


def test_the_real_loaders_answer_without_a_report_file(logged_in):
    """Unpatched, against the test data dir: no file yet, so `not_run`."""
    for url, _loader in _REPORTS:
        assert logged_in.get(url).get_json()["status"] == "not_run"


def test_no_module_level_import_from_swingbot_core(reports):
    """The report modules load only when a report endpoint is called.

    The spec asked for a fresh-interpreter `sys.modules` check; an api_v1
    module cannot be imported on its own (it reaches `swingbot.admin.app`,
    which registers every endpoint), so this pins the same intent statically.
    """
    tree = ast.parse(pathlib.Path(reports.__file__).read_text(encoding="utf-8"))
    offenders = []
    for node in tree.body:
        names = []
        if isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        elif isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        offenders += [name for name in names if name.startswith("swingbot.core")]
    assert offenders == []
